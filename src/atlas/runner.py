"""Autonomous research loop — the production runtime for Atlas.

Runs continuously: scan → generate → test → evaluate → decide → update graph → repeat.
"""

import hashlib
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from atlas.analysis.backtest import run_backtest
from atlas.analysis.statistics import bootstrap_sharpe, mean_return_test, sharpe_significance
from atlas.data.market import MarketData
from atlas.generation.hypotheses import from_graph_gaps, from_signal
from atlas.generation.signals import scan_all
from atlas.models.events import EventType, SessionEvent
from atlas.models.evidence import Evidence, EvidenceClass, EvidenceDirection, EvidenceQuality
from atlas.models.experiment import Experiment, ExperimentStatus
from atlas.models.hypothesis import Hypothesis, HypothesisStatus
from atlas.models.primitive import ReasoningPrimitive
from atlas.models.session import CycleOutcome, CycleStatus, ResearchCycle
from atlas.storage.event_store import EventStore
from atlas.storage.graph_store import GraphStore

log = logging.getLogger("atlas.runner")

# Pairs and timeframes to scan
DEFAULT_UNIVERSE = [
    ("BTC/USDT", "4h"),
    ("ETH/USDT", "4h"),
    ("BTC/USDT", "1d"),
    ("ETH/USDT", "1d"),
]


def _claim_hash(claim: str) -> str:
    """Stable ID from claim text so the same hypothesis persists across cycles."""
    return hashlib.sha256(claim.encode()).hexdigest()[:12]


class AutonomousRunner:
    """Runs the full research loop autonomously."""

    def __init__(self, base_dir: Path, exchange_id: str = "kraken") -> None:
        self.base_dir = base_dir
        self.state_dir = base_dir / ".atlas"
        self.market = MarketData(cache_dir=base_dir / "data", exchange_id=exchange_id)
        self.events = EventStore(base_dir / "sessions")
        self.graph_store = GraphStore(base_dir / "graph")
        self.methodology_log = base_dir / "methodology.jsonl"

    def _save_obj(self, kind: str, obj_id: str, data: dict) -> None:
        d = self.state_dir / kind
        d.mkdir(parents=True, exist_ok=True)
        with open(d / f"{obj_id}.json", "w") as f:
            json.dump(data, f, indent=2, default=str)

    def _load_obj(self, kind: str, obj_id: str) -> dict | None:
        p = self.state_dir / kind / f"{obj_id}.json"
        if p.exists():
            with open(p) as f:
                return json.load(f)
        return None

    def _list_objs(self, kind: str) -> list[dict]:
        d = self.state_dir / kind
        if not d.exists():
            return []
        objs = []
        for p in sorted(d.glob("*.json")):
            with open(p) as f:
                objs.append(json.load(f))
        return objs

    def _log_methodology(self, entry: dict) -> None:
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self.methodology_log, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def _find_existing_hypothesis(self, claim: str) -> Hypothesis | None:
        """Find an existing hypothesis with the same claim."""
        target_hash = _claim_hash(claim)
        data = self._load_obj("hypotheses", target_hash)
        if data:
            return Hypothesis.model_validate(data)
        return None

    def _find_active_cycle(self, hypothesis_id: str) -> ResearchCycle | None:
        """Find an active cycle for a hypothesis."""
        for data in self._list_objs("cycles"):
            cycle = ResearchCycle.model_validate(data)
            if cycle.hypothesis_id == hypothesis_id and cycle.status == CycleStatus.ACTIVE:
                return cycle
        return None

    def scan_signals(self, oos_cutoff: float = 0.7) -> list[tuple[str, str, list, pd.DataFrame]]:
        """Phase 1: Scan in-sample data only for signals.

        Returns (symbol, timeframe, signals, full_df) tuples.
        Signals are detected on the first 70% of data to avoid OOS contamination.
        """
        results = []
        for symbol, timeframe in DEFAULT_UNIVERSE:
            try:
                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=500)
                split_idx = int(len(df) * oos_cutoff)
                is_df = df.iloc[:split_idx]

                # Scan signals on in-sample data ONLY
                signals = scan_all(is_df)
                if signals:
                    results.append((symbol, timeframe, signals, df))
                    log.info("Found %d signals for %s %s (in-sample scan)",
                             len(signals), symbol, timeframe)
                    self._log_methodology({
                        "phase": "signal_intake",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "n_signals": len(signals),
                        "methods": list({s.method for s in signals}),
                        "is_bars": split_idx,
                        "total_bars": len(df),
                    })
            except Exception as e:
                log.warning("Failed to scan %s %s: %s", symbol, timeframe, e)
        return results

    def generate_hypotheses(self, signal_results: list[tuple[str, str, list, pd.DataFrame]]) -> list[Hypothesis]:
        """Phase 2: Convert signals into hypotheses. Reuse existing hypothesis IDs."""
        candidates = []

        for symbol, timeframe, signals, _ in signal_results:
            for signal in signals:
                h = from_signal(signal, symbol, timeframe)
                if h:
                    candidates.append(h)

        # Graph-driven generation
        graph = self.graph_store.load()
        gap_hypotheses = from_graph_gaps(graph)
        candidates.extend(gap_hypotheses)

        # Deduplicate and resolve to durable IDs
        seen_claims = set()
        unique = []
        for h in candidates:
            if h.claim in seen_claims:
                continue
            seen_claims.add(h.claim)

            # Check for existing hypothesis with same claim
            existing = self._find_existing_hypothesis(h.claim)
            if existing:
                if existing.status in (HypothesisStatus.PROMOTED, HypothesisStatus.FALSIFIED):
                    log.debug("Skipping already-resolved hypothesis: %s", existing.id)
                    continue
                unique.append(existing)
            else:
                # Assign stable ID from claim hash
                h.id = _claim_hash(h.claim)
                unique.append(h)

        # Limit per cycle
        selected = unique[:3]

        # Apply Bonferroni correction: adjust alpha for number of tests this cycle
        n_tests = max(1, len(selected))
        for h in selected:
            h.significance_threshold = h.significance_threshold / n_tests

        self._log_methodology({
            "phase": "hypothesis_generation",
            "total_generated": len(candidates),
            "unique": len(unique),
            "selected": len(selected),
            "bonferroni_n": n_tests,
            "adjusted_alpha": selected[0].significance_threshold if selected else None,
        })

        return selected

    def _build_signal_from_hypothesis(self, h: Hypothesis, is_df: pd.DataFrame) -> pd.Series:
        """Build a trading signal series using in-sample data only."""
        prices = is_df["close"]
        returns = prices.pct_change().dropna()

        if "autocorrelation" in h.tags:
            lag = 1
            for tag in h.tags:
                if tag.startswith("lag_"):
                    lag = int(tag.split("_")[1])
            if "momentum" in h.tags:
                signals = (returns.rolling(lag).mean() > 0).astype(int).replace(0, -1)
            else:
                signals = (returns.rolling(lag).mean() < 0).astype(int).replace(0, -1)
        elif "mean_reversion" in h.tags:
            window = 20
            for tag in h.tags:
                if tag.startswith("ma_"):
                    window = int(tag.split("_")[1])
            ma = prices.rolling(window).mean()
            std = prices.rolling(window).std()
            z = (prices - ma) / std
            signals = pd.Series(0, index=prices.index)
            signals[z < -2.0] = 1
            signals[z > 2.0] = -1
        elif "volatility" in h.tags or "regime" in h.tags:
            vol = returns.rolling(20).std()
            vol_ma = vol.rolling(50).mean()
            signals = pd.Series(0, index=prices.index)
            signals[vol < vol_ma * 0.7] = 1
            signals[vol > vol_ma * 1.5] = -1
        elif "volume" in h.tags:
            if "volume" in is_df.columns:
                vol_z = (is_df["volume"] - is_df["volume"].rolling(20).mean()) / is_df["volume"].rolling(20).std()
                ret_dir = returns.rolling(3).mean()
                signals = pd.Series(0, index=prices.index)
                mask = vol_z > 3.0
                signals[mask & (ret_dir > 0)] = 1
                signals[mask & (ret_dir < 0)] = -1
            else:
                signals = pd.Series(0, index=prices.index)
        else:
            signals = (prices.pct_change(20) > 0).astype(int).replace(0, -1)

        return signals

    def run_experiment(self, h: Hypothesis, df: pd.DataFrame, symbol: str, timeframe: str) -> tuple[Experiment, Evidence | None]:
        """Phase 3: Design, execute, and evaluate an experiment.

        Signal is built on in-sample (first 70%), then applied to OOS (last 30%).
        The signal construction uses ONLY in-sample data — no information leakage.
        """
        tf_periods = {"1h": 365 * 24, "4h": 365 * 6, "1d": 365, "1w": 52}
        periods_per_year = tf_periods.get(timeframe, 365 * 6)

        exp = Experiment(
            hypothesis_id=h.id,
            description=f"Backtest {h.claim[:80]} on {symbol} {timeframe}",
            method="backtest",
            parameters={"symbol": symbol, "timeframe": timeframe, "lookback": len(df)},
            success_criteria=f"OOS Sharpe > 0 with p < {h.significance_threshold:.4f} (Bonferroni-adjusted)",
            failure_criteria=f"OOS Sharpe not significantly different from zero (p >= {h.significance_threshold:.4f})",
        )
        self._save_obj("experiments", exp.id, exp.model_dump())

        try:
            split_idx = int(len(df) * 0.7)
            is_df = df.iloc[:split_idx]
            oos_df = df.iloc[split_idx:]

            # Build signal on in-sample ONLY
            is_signals = self._build_signal_from_hypothesis(h, is_df)

            # For OOS: apply the same signal logic to OOS data independently
            # This means the signal parameters come from IS, but the signal
            # values on OOS bars are computed from OOS data
            oos_signals = self._build_signal_from_hypothesis(h, oos_df)

            is_result = run_backtest(is_df["close"], is_signals, periods_per_year=periods_per_year)
            oos_result = run_backtest(oos_df["close"], oos_signals, periods_per_year=periods_per_year)

            # Statistical tests on OOS with Bonferroni-adjusted alpha
            alpha = h.significance_threshold
            oos_sharpe = sharpe_significance(oos_result.returns, alpha=alpha)
            oos_mean = mean_return_test(oos_result.returns, alpha=alpha)
            oos_boot = bootstrap_sharpe(oos_result.returns, periods_per_year=periods_per_year, alpha=alpha)

            exp.status = ExperimentStatus.COMPLETED
            exp.results = {
                "in_sample": {
                    "sharpe": is_result.sharpe_ratio,
                    "total_return": is_result.total_return,
                    "max_drawdown": is_result.max_drawdown,
                },
                "out_of_sample": {
                    "sharpe": oos_result.sharpe_ratio,
                    "total_return": oos_result.total_return,
                    "max_drawdown": oos_result.max_drawdown,
                    "sharpe_p": oos_sharpe.p_value,
                    "mean_p": oos_mean.p_value,
                    "bootstrap_ci": [oos_boot.ci_lower, oos_boot.ci_upper],
                    "bonferroni_alpha": alpha,
                },
            }
            self._save_obj("experiments", exp.id, exp.model_dump())

            # Evaluate evidence quality
            oos = exp.results["out_of_sample"]
            # Require BOTH sharpe and bootstrap to agree for strong
            both_significant = oos_sharpe.significant and oos_boot.significant
            is_positive = oos_result.sharpe_ratio > 0

            if both_significant and is_positive:
                quality = EvidenceQuality.STRONG
                direction = EvidenceDirection.SUPPORTS
            elif is_positive and (oos_sharpe.significant or oos_boot.significant):
                quality = EvidenceQuality.MODERATE
                direction = EvidenceDirection.SUPPORTS
            elif oos_result.sharpe_ratio < -0.5 and both_significant:
                quality = EvidenceQuality.STRONG
                direction = EvidenceDirection.CONTRADICTS
            elif not is_positive and (oos_sharpe.p_value < 0.15 or oos_boot.p_value < 0.15):
                quality = EvidenceQuality.MODERATE
                direction = EvidenceDirection.CONTRADICTS
            else:
                quality = EvidenceQuality.WEAK
                direction = EvidenceDirection.INCONCLUSIVE

            ev = Evidence(
                experiment_id=exp.id,
                hypothesis_id=h.id,
                evidence_class=EvidenceClass.OUT_OF_SAMPLE_TEST,
                quality=quality,
                direction=direction,
                summary=f"OOS Sharpe={oos_result.sharpe_ratio:.2f} (p={oos_sharpe.p_value:.3f}, "
                        f"α={alpha:.4f}), IS Sharpe={is_result.sharpe_ratio:.2f}. "
                        f"Bootstrap CI=[{oos_boot.ci_lower:.2f}, {oos_boot.ci_upper:.2f}]",
                statistics=oos,
            )
            self._save_obj("evidence", ev.id, ev.model_dump())

            log.info("Experiment %s: OOS Sharpe=%.2f p=%.3f (α=%.4f) → %s %s",
                     exp.id, oos_result.sharpe_ratio, oos_sharpe.p_value, alpha,
                     quality.value, direction.value)

            return exp, ev

        except Exception as e:
            log.error("Experiment %s failed: %s", exp.id, e)
            exp.status = ExperimentStatus.FAILED
            exp.results = {"error": str(e)}
            self._save_obj("experiments", exp.id, exp.model_dump())
            return exp, None

    def evaluate_and_decide(self, h: Hypothesis, cycle: ResearchCycle) -> str:
        """Phase 4-5: Evaluate accumulated evidence and decide.

        Promotion requires:
        - ≥2 strong supporting evidence from DISTINCT experiments
        - ≥1 must be OOS or live
        - No unaddressed strong contradictory evidence
        """
        evidence = [Evidence.model_validate(d) for d in self._list_objs("evidence")
                    if d.get("hypothesis_id") == h.id]

        if not evidence:
            return "continue"

        strong_support = [e for e in evidence
                          if e.quality == EvidenceQuality.STRONG
                          and e.direction == EvidenceDirection.SUPPORTS]
        strong_contradict = [e for e in evidence
                             if e.quality == EvidenceQuality.STRONG
                             and e.direction == EvidenceDirection.CONTRADICTS]
        oos_support = [e for e in strong_support
                       if e.evidence_class in (EvidenceClass.OUT_OF_SAMPLE_TEST, EvidenceClass.LIVE_OBSERVATION)]

        # Check distinct experiments for strong support
        distinct_experiments = len({e.experiment_id for e in strong_support})

        # Kill if strong contradictory evidence
        if len(strong_contradict) >= 2:
            h.status = HypothesisStatus.FALSIFIED
            self._save_obj("hypotheses", h.id, h.model_dump())
            cycle.status = CycleStatus.CLOSED
            cycle.outcome = CycleOutcome.KILLED
            cycle.decision_rationale = f"Falsified: {len(strong_contradict)} strong contradictory evidence records"
            self._save_obj("cycles", cycle.id, cycle.model_dump())
            self.events.append(SessionEvent(
                session_id=cycle.id,
                event_type=EventType.DECISION_MADE,
                details={"action": "kill", "reason": cycle.decision_rationale},
            ))
            return "kill"

        # Block promotion if ANY strong contradictory evidence exists
        if strong_contradict:
            log.info("Hypothesis %s has %d strong contradictions — cannot promote",
                     h.id, len(strong_contradict))
            return "continue"

        # Promote if gate is met with distinct experiments
        if distinct_experiments >= 2 and len(oos_support) >= 1:
            primitive = ReasoningPrimitive(
                claim=h.claim,
                hypothesis_id=h.id,
                evidence_ids=[e.id for e in strong_support],
                confidence=min(0.95, 0.5 + 0.15 * distinct_experiments),
                tags=h.tags,
                causal_parents=[h.parent_primitive_id] if h.parent_primitive_id else [],
            )
            self._save_obj("primitives", primitive.id, primitive.model_dump())

            graph = self.graph_store.load()
            try:
                graph.add_primitive(primitive)
            except ValueError as e:
                log.warning("Could not link parent: %s — adding as root", e)
                primitive.causal_parents = []
                graph.add_primitive(primitive)
            self.graph_store.save(graph)

            h.status = HypothesisStatus.PROMOTED
            self._save_obj("hypotheses", h.id, h.model_dump())
            cycle.status = CycleStatus.CLOSED
            cycle.outcome = CycleOutcome.PROMOTED
            cycle.decision_rationale = (
                f"Promoted: {distinct_experiments} distinct strong experiments, "
                f"{len(oos_support)} OOS. Graph: {graph.node_count} nodes."
            )
            self._save_obj("cycles", cycle.id, cycle.model_dump())
            self.events.append(SessionEvent(
                session_id=cycle.id,
                event_type=EventType.PRIMITIVE_PROMOTED,
                details={"primitive_id": primitive.id, "claim": h.claim},
            ))
            self._log_methodology({
                "phase": "decision", "hypothesis_id": h.id, "action": "promote",
                "primitive_id": primitive.id, "graph_nodes": graph.node_count,
            })
            return "promote"

        # Kill if all evidence is weak/contradictory after enough attempts
        all_weak_or_negative = all(
            e.direction != EvidenceDirection.SUPPORTS or e.quality == EvidenceQuality.WEAK
            for e in evidence
        )
        if all_weak_or_negative and len(evidence) >= 3:
            h.status = HypothesisStatus.FALSIFIED
            self._save_obj("hypotheses", h.id, h.model_dump())
            cycle.status = CycleStatus.CLOSED
            cycle.outcome = CycleOutcome.KILLED
            cycle.decision_rationale = f"Killed: {len(evidence)} evidence records, none strong/supporting"
            self._save_obj("cycles", cycle.id, cycle.model_dump())
            self.events.append(SessionEvent(
                session_id=cycle.id,
                event_type=EventType.DECISION_MADE,
                details={"action": "kill", "reason": cycle.decision_rationale},
            ))
            return "kill"

        return "continue"

    def run_cycle(self) -> dict:
        """Execute one complete research cycle."""
        log.info("=== Starting research cycle ===")
        cycle_report = {"timestamp": datetime.now(timezone.utc).isoformat(), "hypotheses": []}

        # Phase 1: Scan in-sample data for signals
        signal_results = self.scan_signals()
        cycle_report["signals_found"] = sum(len(s) for _, _, s, _ in signal_results)

        # Phase 2: Generate hypotheses (with durable IDs and Bonferroni correction)
        hypotheses = self.generate_hypotheses(signal_results)
        cycle_report["hypotheses_generated"] = len(hypotheses)

        if not hypotheses:
            log.info("No hypotheses generated this cycle")
            return cycle_report

        # Build a lookup from hypothesis claim to the full df
        claim_to_data: dict[str, tuple[str, str, pd.DataFrame]] = {}
        for symbol, timeframe, signals, df in signal_results:
            for signal in signals:
                h_candidate = from_signal(signal, symbol, timeframe)
                if h_candidate:
                    claim_to_data[h_candidate.claim] = (symbol, timeframe, df)

        # Phase 3-5: For each hypothesis, run experiments and decide
        for h in hypotheses:
            # Persist hypothesis (or it already exists with same ID)
            if not self._load_obj("hypotheses", h.id):
                self._save_obj("hypotheses", h.id, h.model_dump())

            # Find or create cycle
            cycle = self._find_active_cycle(h.id)
            if not cycle:
                cycle = ResearchCycle(hypothesis_id=h.id)
                self._save_obj("cycles", cycle.id, cycle.model_dump())
                self.events.append(SessionEvent(
                    session_id=cycle.id,
                    event_type=EventType.HYPOTHESIS_FORMULATED,
                    details={"hypothesis_id": h.id, "claim": h.claim},
                ))

            h_report = {"id": h.id, "claim": h.claim, "experiments": []}

            # Get data for this hypothesis
            if h.claim in claim_to_data:
                symbol, timeframe, df = claim_to_data[h.claim]
            else:
                # Graph-gap hypothesis — use BTC/USDT 4h as default
                symbol, timeframe = "BTC/USDT", "4h"
                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=500)

            # Run experiment
            exp, ev = self.run_experiment(h, df, symbol, timeframe)
            if ev:
                cycle.experiment_ids.append(exp.id)
                cycle.evidence_ids.append(ev.id)
                self._save_obj("cycles", cycle.id, cycle.model_dump())
                h_report["experiments"].append({
                    "id": exp.id,
                    "evidence_quality": ev.quality.value,
                    "evidence_direction": ev.direction.value,
                })

            # Decide
            decision = self.evaluate_and_decide(h, cycle)
            h_report["decision"] = decision
            cycle_report["hypotheses"].append(h_report)

            log.info("Hypothesis %s: %s → %s", h.id, h.claim[:60], decision)

        # Phase 6: Report graph state
        graph = self.graph_store.load()
        cycle_report["graph_nodes"] = graph.node_count
        cycle_report["graph_edges"] = graph.edge_count

        log.info("=== Cycle complete: %d hypotheses tested, graph has %d nodes ===",
                 len(hypotheses), graph.node_count)

        return cycle_report

    def run_continuous(self, interval_seconds: int = 3600) -> None:
        """Run the research loop continuously."""
        log.info("Starting continuous research loop (interval=%ds)", interval_seconds)
        while True:
            try:
                report = self.run_cycle()
                reports_dir = self.base_dir / "reports"
                reports_dir.mkdir(exist_ok=True)
                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
                with open(reports_dir / f"cycle_{ts}.json", "w") as f:
                    json.dump(report, f, indent=2, default=str)
            except Exception as e:
                log.error("Cycle failed: %s", e, exc_info=True)
                self._log_methodology({
                    "phase": "cycle_failure",
                    "error": str(e),
                })

            log.info("Sleeping %ds until next cycle", interval_seconds)
            time.sleep(interval_seconds)
