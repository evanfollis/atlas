"""Autonomous research loop — the production runtime for Atlas.

Runs continuously: scan → generate → test → evaluate → decide → update graph → repeat.
"""

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

    def _log_methodology(self, entry: dict) -> None:
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self.methodology_log, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def scan_signals(self) -> list[tuple[str, str, list]]:
        """Phase 1: Scan market data for signals across the universe."""
        results = []
        for symbol, timeframe in DEFAULT_UNIVERSE:
            try:
                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=500)
                signals = scan_all(df)
                if signals:
                    results.append((symbol, timeframe, signals))
                    log.info("Found %d signals for %s %s", len(signals), symbol, timeframe)
                    self._log_methodology({
                        "phase": "signal_intake",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "n_signals": len(signals),
                        "methods": list({s.method for s in signals}),
                    })
            except Exception as e:
                log.warning("Failed to scan %s %s: %s", symbol, timeframe, e)
        return results

    def generate_hypotheses(self, signal_results: list[tuple[str, str, list]]) -> list[Hypothesis]:
        """Phase 2: Convert signals into hypotheses. Also check graph gaps."""
        hypotheses = []

        # Signal-driven generation
        for symbol, timeframe, signals in signal_results:
            for signal in signals:
                h = from_signal(signal, symbol, timeframe)
                if h:
                    hypotheses.append(h)

        # Graph-driven generation
        graph = self.graph_store.load()
        gap_hypotheses = from_graph_gaps(graph)
        hypotheses.extend(gap_hypotheses)

        # Deduplicate by claim similarity (exact match for now)
        seen_claims = set()
        unique = []
        for h in hypotheses:
            if h.claim not in seen_claims:
                seen_claims.add(h.claim)
                unique.append(h)

        # Rank by signal strength / graph importance — take top N
        # For now, limit to 3 per cycle to avoid overwhelming
        selected = unique[:3]

        self._log_methodology({
            "phase": "hypothesis_generation",
            "total_generated": len(hypotheses),
            "unique": len(unique),
            "selected": len(selected),
            "methods_used": list({h.tags[-1] if h.tags else "unknown" for h in selected}),
        })

        return selected

    def _build_signal_from_hypothesis(self, h: Hypothesis, df, prices):
        """Build a trading signal series based on hypothesis tags/type."""
        returns = prices.pct_change().dropna()

        if "autocorrelation" in h.tags:
            # Lag-based momentum or contrarian
            lag = 1
            for tag in h.tags:
                if tag.startswith("lag_"):
                    lag = int(tag.split("_")[1])
            if "momentum" in h.tags:
                signals = (returns.rolling(lag).mean() > 0).astype(int).replace(0, -1)
            else:
                signals = (returns.rolling(lag).mean() < 0).astype(int).replace(0, -1)
        elif "mean_reversion" in h.tags:
            # Z-score mean reversion
            window = 20
            for tag in h.tags:
                if tag.startswith("ma_"):
                    window = int(tag.split("_")[1])
            ma = prices.rolling(window).mean()
            std = prices.rolling(window).std()
            z = (prices - ma) / std
            signals = pd.Series(0, index=prices.index)
            signals[z < -2.0] = 1   # Buy below -2σ
            signals[z > 2.0] = -1   # Sell above +2σ
        elif "volatility" in h.tags or "regime" in h.tags:
            # Trade vol regime: go long after compression, short after expansion
            vol = returns.rolling(20).std()
            vol_ma = vol.rolling(50).mean()
            signals = pd.Series(0, index=prices.index)
            signals[vol < vol_ma * 0.7] = 1   # Compression → expect breakout
            signals[vol > vol_ma * 1.5] = -1  # Expansion → expect reversion
        elif "volume" in h.tags:
            # Volume spike → trade in direction of move
            if "volume" in df.columns:
                vol_z = (df["volume"] - df["volume"].rolling(20).mean()) / df["volume"].rolling(20).std()
                ret_dir = returns.rolling(3).mean()
                signals = pd.Series(0, index=prices.index)
                mask = vol_z > 3.0
                signals[mask & (ret_dir > 0)] = 1
                signals[mask & (ret_dir < 0)] = -1
            else:
                signals = pd.Series(0, index=prices.index)
        else:
            # Default: simple momentum
            signals = (prices.pct_change(20) > 0).astype(int).replace(0, -1)

        return signals

    def run_experiment(self, h: Hypothesis, symbol: str, timeframe: str) -> tuple[Experiment, Evidence | None]:
        """Phase 3: Design, execute, and evaluate an experiment for a hypothesis."""
        # Determine periods_per_year
        tf_periods = {"1h": 365 * 24, "4h": 365 * 6, "1d": 365, "1w": 52}
        periods_per_year = tf_periods.get(timeframe, 365 * 6)

        exp = Experiment(
            hypothesis_id=h.id,
            description=f"Backtest {h.claim[:80]} on {symbol} {timeframe}",
            method="backtest",
            parameters={"symbol": symbol, "timeframe": timeframe, "lookback": 500},
            success_criteria=f"Sharpe > 0 with p < {h.significance_threshold}",
            failure_criteria=f"Sharpe not significantly different from zero (p >= {h.significance_threshold})",
        )
        self._save_obj("experiments", exp.id, exp.model_dump())

        try:
            df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=500)
            prices = df["close"]

            # Split: first 70% in-sample, last 30% out-of-sample
            split_idx = int(len(df) * 0.7)
            is_df = df.iloc[:split_idx]
            oos_df = df.iloc[split_idx:]
            is_prices = is_df["close"]
            oos_prices = oos_df["close"]

            # Build signal on full data, then split
            signals = self._build_signal_from_hypothesis(h, df, prices)

            # In-sample backtest
            is_signals = signals.reindex(is_prices.index)
            is_result = run_backtest(is_prices, is_signals, periods_per_year=periods_per_year)

            # Out-of-sample backtest
            oos_signals = signals.reindex(oos_prices.index)
            oos_result = run_backtest(oos_prices, oos_signals, periods_per_year=periods_per_year)

            # Statistical tests on OOS
            oos_sharpe = sharpe_significance(oos_result.returns, alpha=h.significance_threshold)
            oos_mean = mean_return_test(oos_result.returns, alpha=h.significance_threshold)
            oos_boot = bootstrap_sharpe(oos_result.returns, periods_per_year=periods_per_year, alpha=h.significance_threshold)

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
                },
            }
            self._save_obj("experiments", exp.id, exp.model_dump())

            # Evaluate evidence
            oos = exp.results["out_of_sample"]
            is_significant = oos_sharpe.significant or oos_boot.significant
            is_positive = oos_result.sharpe_ratio > 0

            if is_significant and is_positive:
                quality = EvidenceQuality.STRONG
                direction = EvidenceDirection.SUPPORTS
            elif is_positive and oos_sharpe.p_value < 0.15:
                quality = EvidenceQuality.MODERATE
                direction = EvidenceDirection.SUPPORTS
            elif oos_result.sharpe_ratio < -0.5 and is_significant:
                quality = EvidenceQuality.STRONG
                direction = EvidenceDirection.CONTRADICTS
            elif not is_positive:
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
                summary=f"OOS Sharpe={oos_result.sharpe_ratio:.2f} (p={oos_sharpe.p_value:.3f}), "
                        f"IS Sharpe={is_result.sharpe_ratio:.2f}. "
                        f"Bootstrap CI=[{oos_boot.ci_lower:.2f}, {oos_boot.ci_upper:.2f}]",
                statistics=oos,
            )
            self._save_obj("evidence", ev.id, ev.model_dump())

            log.info("Experiment %s: OOS Sharpe=%.2f p=%.3f → %s %s",
                     exp.id, oos_result.sharpe_ratio, oos_sharpe.p_value,
                     quality.value, direction.value)

            return exp, ev

        except Exception as e:
            log.error("Experiment %s failed: %s", exp.id, e)
            exp.status = ExperimentStatus.FAILED
            exp.results = {"error": str(e)}
            self._save_obj("experiments", exp.id, exp.model_dump())
            return exp, None

    def evaluate_and_decide(self, h: Hypothesis, cycle: ResearchCycle) -> str:
        """Phase 4-5: Evaluate evidence and make promotion/kill decision."""
        evidence_dir = self.state_dir / "evidence"
        if not evidence_dir.exists():
            return "continue"

        evidence = []
        for p in evidence_dir.glob("*.json"):
            with open(p) as f:
                ev = Evidence.model_validate(json.load(f))
                if ev.hypothesis_id == h.id:
                    evidence.append(ev)

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
            self._log_methodology({
                "phase": "decision",
                "hypothesis_id": h.id,
                "action": "kill",
                "n_evidence": len(evidence),
                "strong_support": len(strong_support),
                "strong_contradict": len(strong_contradict),
            })
            return "kill"

        # Promote if gate is met
        if len(strong_support) >= 2 and len(oos_support) >= 1:
            primitive = ReasoningPrimitive(
                claim=h.claim,
                hypothesis_id=h.id,
                evidence_ids=[e.id for e in strong_support],
                confidence=min(0.95, 0.5 + 0.15 * len(strong_support)),
                tags=h.tags,
                causal_parents=[h.parent_primitive_id] if h.parent_primitive_id else [],
            )
            self._save_obj("primitives", primitive.id, primitive.model_dump())

            graph = self.graph_store.load()
            try:
                graph.add_primitive(primitive)
                self.graph_store.save(graph)
            except ValueError as e:
                # Parent not in graph — add without edges
                log.warning("Could not link parent: %s", e)
                primitive.causal_parents = []
                graph.add_primitive(primitive)
                self.graph_store.save(graph)

            h.status = HypothesisStatus.PROMOTED
            self._save_obj("hypotheses", h.id, h.model_dump())
            cycle.status = CycleStatus.CLOSED
            cycle.outcome = CycleOutcome.PROMOTED
            cycle.decision_rationale = (
                f"Promoted: {len(strong_support)} strong support, "
                f"{len(oos_support)} OOS. Graph now has {graph.node_count} nodes."
            )
            self._save_obj("cycles", cycle.id, cycle.model_dump())
            self.events.append(SessionEvent(
                session_id=cycle.id,
                event_type=EventType.PRIMITIVE_PROMOTED,
                details={"primitive_id": primitive.id, "claim": h.claim},
            ))
            self._log_methodology({
                "phase": "decision",
                "hypothesis_id": h.id,
                "action": "promote",
                "primitive_id": primitive.id,
                "graph_nodes": graph.node_count,
            })
            return "promote"

        # Not enough evidence — kill if all evidence is weak/contradictory
        all_weak_or_negative = all(
            e.direction != EvidenceDirection.SUPPORTS or e.quality == EvidenceQuality.WEAK
            for e in evidence
        )
        if all_weak_or_negative and len(evidence) >= 2:
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

        # Phase 1: Scan
        signal_results = self.scan_signals()
        cycle_report["signals_found"] = sum(len(s) for _, _, s in signal_results)

        # Phase 2: Generate hypotheses
        hypotheses = self.generate_hypotheses(signal_results)
        cycle_report["hypotheses_generated"] = len(hypotheses)

        if not hypotheses:
            log.info("No hypotheses generated this cycle")
            return cycle_report

        # Phase 3-5: For each hypothesis, run experiments and decide
        for h in hypotheses:
            self._save_obj("hypotheses", h.id, h.model_dump())
            cycle = ResearchCycle(hypothesis_id=h.id)
            self._save_obj("cycles", cycle.id, cycle.model_dump())

            self.events.append(SessionEvent(
                session_id=cycle.id,
                event_type=EventType.HYPOTHESIS_FORMULATED,
                details={"hypothesis_id": h.id, "claim": h.claim},
            ))

            h_report = {"id": h.id, "claim": h.claim, "experiments": []}

            # Extract symbol/timeframe from tags
            symbol = "BTC/USDT"
            timeframe = "4h"
            for tag in h.tags:
                if "btc" in tag and "usdt" in tag:
                    symbol = "BTC/USDT"
                elif "eth" in tag and "usdt" in tag:
                    symbol = "ETH/USDT"
                if tag in ("1h", "4h", "1d", "1w"):
                    timeframe = tag

            # Run experiment
            exp, ev = self.run_experiment(h, symbol, timeframe)
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
                # Save cycle report
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
