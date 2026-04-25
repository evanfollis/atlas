"""Autonomous research loop — the production runtime for Atlas.

Runs continuously: scan → generate → test → evaluate → decide → update graph → repeat.
"""

import json
import logging
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from atlas.analysis.backtest import run_backtest, walk_forward_backtest
from atlas.analysis.statistics import bootstrap_sharpe, mean_return_test, sharpe_significance
from atlas.data.alternative import AlternativeData, align_to_price
from atlas.data.market import MarketData
from atlas.generation.calendar_signals import scan_calendar
from atlas.generation.composite_hypotheses import COMPOSITE_GENERATORS
from atlas.generation.composite_signals import scan_composite
from atlas.generation.hypotheses import from_graph_gaps, from_signal
from atlas.generation.signals import scan_all, detect_cross_asset_spread, detect_lead_lag
from atlas.models.events import EventType, SessionEvent
from atlas.models.evidence import Evidence, EvidenceClass, EvidenceDirection, EvidenceQuality
from atlas.models.experiment import Experiment, ExperimentStatus
from atlas.models.hypothesis import Hypothesis, HypothesisStatus
from atlas.models.primitive import ReasoningPrimitive
from atlas.models.session import CycleOutcome, CycleStatus, ResearchCycle
from atlas.storage.event_store import EventStore
from atlas.storage.graph_store import GraphStore
from atlas.storage.state_store import StateStore
from atlas.utils import claim_hash as _claim_hash

log = logging.getLogger("atlas.runner")

# Pairs and timeframes to scan.
# 1h gives ~4300 bars (6 months) which clears the 833-bar walk-forward minimum.
# 4h yields only ~720 bars — below the gate, so every hypothesis stalls at "continue".
DEFAULT_UNIVERSE = [
    ("BTC/USDT", "1h"),
    ("ETH/USDT", "1h"),
    ("SOL/USDT", "1h"),
]

# Minimum bars a dataset must have before atlas will scan it for signals.
# Set to the walk-forward minimum (833 bars) so any dataset we scan can also
# sustain anchored-expanding walk-forward validation — otherwise we'd burn
# Bonferroni budget on hypotheses that cannot clear the OOS gate regardless
# of signal strength. Symbols below the floor are skipped and logged via
# methodology so the skip is visible in telemetry instead of silent.
MIN_BARS_FOR_RESEARCH = 833

# Existing dataset evidence is only a cache while it is fresh. After this
# window the same symbol/timeframe should be retested against newly available
# market data instead of freezing the hypothesis forever.
DATASET_RETEST_AFTER = timedelta(days=1)

# Frozen-loop escalation: after this many consecutive cycle.completed events
# whose decisions are all "continue", the runner emits a cycle.escalated event
# and writes an URGENT handoff. Matches the workspace S3-P2 rule "self-monitoring
# systems must self-report stuck states; threshold is 3 consecutive same-reason
# skips" (CLAUDE.md §Architecture Governance).
FROZEN_LOOP_ESCALATION_AFTER = 3


def evaluate_promotion_gate(evidence: list[Evidence]) -> dict:
    """Pure predicate: return promotion-gate metrics for one hypothesis.

    Single source of truth shared by `evaluate_and_decide` (which acts on the
    verdict) and `atlas strategy readiness` (which counts how many hypotheses
    would pass). Adding a parallel implementation here would silently drift
    from the runner.

    Gate (per CLAUDE.md §Promotion Gate and atlas review #2):
      - ≥2 strong supporting evidence records
      - from ≥2 DISTINCT experiments
      - ≥1 of those strong supports is OOS or LIVE
      - 0 strong contradictory evidence records
    """
    strong_support = [e for e in evidence
                      if e.quality == EvidenceQuality.STRONG
                      and e.direction == EvidenceDirection.SUPPORTS]
    strong_contradict = [e for e in evidence
                         if e.quality == EvidenceQuality.STRONG
                         and e.direction == EvidenceDirection.CONTRADICTS]
    oos_support = [e for e in strong_support
                   if e.evidence_class in (EvidenceClass.OUT_OF_SAMPLE_TEST,
                                           EvidenceClass.LIVE_OBSERVATION)]
    distinct_experiments = len({e.experiment_id for e in strong_support})

    promotable = (
        not strong_contradict
        and distinct_experiments >= 2
        and len(oos_support) >= 1
    )

    return {
        "strong_support": strong_support,
        "strong_contradict": strong_contradict,
        "oos_support": oos_support,
        "distinct_experiments": distinct_experiments,
        "promotable": promotable,
    }



class AutonomousRunner:
    """Runs the full research loop autonomously."""

    def __init__(self, base_dir: Path, exchange_id: str = "bitstamp") -> None:
        self.base_dir = base_dir
        self.state = StateStore(base_dir / ".atlas")
        self.market = MarketData(cache_dir=base_dir / "data", exchange_id=exchange_id)
        self.alt_data = AlternativeData(cache_dir=base_dir / "data")
        self.events = EventStore(base_dir / "sessions")
        self.graph_store = GraphStore(base_dir / "graph")
        self.methodology_log = base_dir / "methodology.jsonl"

    def _save_obj(self, kind: str, obj_id: str, data: dict) -> None:
        self.state.save(kind, obj_id, data)

    def _load_obj(self, kind: str, obj_id: str) -> dict | None:
        return self.state.load(kind, obj_id)

    def _list_objs(self, kind: str) -> list[dict]:
        return self.state.list_all(kind)

    def _log_methodology(self, entry: dict) -> None:
        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
        with open(self.methodology_log, "a") as f:
            f.write(json.dumps(entry, default=str) + "\n")

    def _emit_telemetry(self, event_type: str, level: str = "info", details: dict | None = None) -> None:
        """Append one event to the shared workspace telemetry stream."""
        import uuid
        event = {
            "project": "atlas",
            "source": "atlas.runner",
            "eventType": event_type,
            "level": level,
            "sourceType": "system",
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
            "id": str(uuid.uuid4()),
        }
        if details:
            event["details"] = details
        telemetry_path = self.TELEMETRY_PATH
        try:
            telemetry_path.parent.mkdir(parents=True, exist_ok=True)
            with open(telemetry_path, "a") as f:
                f.write(json.dumps(event, default=str) + "\n")
        except Exception as exc:
            log.warning("Failed to emit telemetry event %s: %s", event_type, exc)

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

    def _fresh_tested_datasets(
        self,
        existing_evidence: list[Evidence],
        now: datetime | None = None,
    ) -> set[tuple[str, str]]:
        """Return datasets with recent evidence for the hypothesis."""
        now = now or datetime.now(timezone.utc)
        fresh: set[tuple[str, str]] = set()
        newest_by_dataset: dict[tuple[str, str], datetime] = {}

        for evidence in existing_evidence:
            exp_data = self._load_obj("experiments", evidence.experiment_id)
            if not exp_data:
                continue
            params = exp_data.get("parameters", {})
            key = (params.get("symbol", ""), params.get("timeframe", ""))
            if not all(key):
                continue
            created_at = evidence.created_at
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if key not in newest_by_dataset or created_at > newest_by_dataset[key]:
                newest_by_dataset[key] = created_at

        for key, created_at in newest_by_dataset.items():
            if now - created_at < DATASET_RETEST_AFTER:
                fresh.add(key)

        return fresh

    def scan_signals(self, oos_cutoff: float = 0.7) -> list[tuple[str, str, list, pd.DataFrame]]:
        """Phase 1: Scan in-sample data only for signals.

        Returns (symbol, timeframe, signals, full_df) tuples.
        Signals are detected on the first 70% of data to avoid OOS contamination.
        """
        results = []
        skipped_short: set[tuple[str, str]] = set()
        for symbol, timeframe in DEFAULT_UNIVERSE:
            try:
                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=100000)
                if len(df) < MIN_BARS_FOR_RESEARCH:
                    skipped_short.add((symbol, timeframe))
                    log.warning(
                        "Skipping %s %s: %d bars < MIN_BARS_FOR_RESEARCH=%d",
                        symbol, timeframe, len(df), MIN_BARS_FOR_RESEARCH,
                    )
                    self._log_methodology({
                        "phase": "signal_intake",
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "skipped": "insufficient_history",
                        "bars": len(df),
                        "min_required": MIN_BARS_FOR_RESEARCH,
                    })
                    continue
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

        # Cross-asset detectors: compare pairs at the same timeframe
        is_data: dict[tuple[str, str], pd.DataFrame] = {}
        for symbol, timeframe, _, df in results:
            split_idx = int(len(df) * oos_cutoff)
            is_data[(symbol, timeframe)] = df.iloc[:split_idx]

        # Also load pairs not yet in results. Honor the min-bars gate here
        # so cross-asset detectors don't pair a short dataset against a
        # long one (would produce signals atlas then can't walk-forward).
        for symbol, timeframe in DEFAULT_UNIVERSE:
            if (symbol, timeframe) in is_data or (symbol, timeframe) in skipped_short:
                continue
            try:
                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=100000)
                if len(df) < MIN_BARS_FOR_RESEARCH:
                    skipped_short.add((symbol, timeframe))
                    continue
                is_data[(symbol, timeframe)] = df.iloc[:int(len(df) * oos_cutoff)]
            except Exception:
                pass

        timeframes_seen = set()
        for (sym, tf) in is_data:
            timeframes_seen.add(tf)

        cross_signals = []
        for tf in timeframes_seen:
            pairs_at_tf = [(sym, df) for (sym, t), df in is_data.items() if t == tf]
            for i, (sym_a, df_a) in enumerate(pairs_at_tf):
                for sym_b, df_b in pairs_at_tf[i + 1:]:
                    cross_signals.extend(detect_cross_asset_spread(
                        df_a["close"], df_b["close"], sym_a, sym_b,
                    ))
                    ret_a = df_a["close"].pct_change().dropna()
                    ret_b = df_b["close"].pct_change().dropna()
                    cross_signals.extend(detect_lead_lag(ret_a, ret_b, sym_a, sym_b))
                    cross_signals.extend(detect_lead_lag(ret_b, ret_a, sym_b, sym_a))

        # Composite signals: multi-source (sentiment, on-chain, mining + price)
        composite_signals = []
        try:
            alt_sources = self.alt_data.fetch_all()
            if alt_sources:
                for symbol, timeframe, _, df in results:
                    split_idx = int(len(df) * oos_cutoff)
                    is_prices = df["close"].iloc[:split_idx]
                    csigs = scan_composite(is_prices, alt_sources)
                    for s in csigs:
                        s.symbol = symbol
                        s.timeframe = timeframe
                    composite_signals.extend(csigs)
                log.info("Found %d composite signals from %d alt sources",
                         len(composite_signals), len(alt_sources))
        except Exception as e:
            log.warning("Composite signal scan failed: %s", e)

        # Calendar signals: temporal patterns (EOM, weekend, US session)
        calendar_signals = []
        for symbol, timeframe, _, df in results:
            split_idx = int(len(df) * oos_cutoff)
            is_prices = df["close"].iloc[:split_idx]
            csigs = scan_calendar(is_prices)
            for s in csigs:
                s.symbol = symbol
                s.timeframe = timeframe
            calendar_signals.extend(csigs)
        if calendar_signals:
            log.info("Found %d calendar signals", len(calendar_signals))
        composite_signals.extend(calendar_signals)

        extra_signals = cross_signals + composite_signals
        if extra_signals:
            # Attach extra signals to the BTC/USDT 1h anchor
            anchor = ("BTC/USDT", "1h")
            anchor_found = False
            for idx, (sym, tf, sigs, df) in enumerate(results):
                if (sym, tf) == anchor:
                    results[idx] = (sym, tf, sigs + extra_signals, df)
                    anchor_found = True
                    break
            if not anchor_found and results:
                sym, tf, sigs, df = results[0]
                results[0] = (sym, tf, sigs + extra_signals, df)
            log.info("Found %d cross-asset + %d composite signals",
                     len(cross_signals), len(composite_signals))

        return results

    def generate_hypotheses(self, signal_results: list[tuple[str, str, list, pd.DataFrame]]) -> list[Hypothesis]:
        """Phase 2: Convert signals into hypotheses. Reuse existing hypothesis IDs."""
        candidates: list[tuple[Hypothesis, str]] = []  # (hypothesis, source_method)

        for symbol, timeframe, signals, _ in signal_results:
            for signal in signals:
                # Try composite generators first, then single-source
                gen = COMPOSITE_GENERATORS.get(signal.method)
                if gen:
                    sym = signal.symbol or symbol
                    tf = signal.timeframe or timeframe
                    candidates.append((gen(signal, sym, tf), signal.method))
                else:
                    h = from_signal(signal, symbol, timeframe)
                    if h:
                        candidates.append((h, signal.method))

        # Graph-driven generation
        graph = self.graph_store.load()
        gap_hypotheses = from_graph_gaps(graph)
        candidates.extend([(h, "graph_gaps") for h in gap_hypotheses])

        # Deduplicate and resolve to durable IDs
        seen_claims: set[str] = set()
        unique: list[tuple[Hypothesis, str]] = []
        for h, method in candidates:
            if h.claim in seen_claims:
                continue
            seen_claims.add(h.claim)

            # Check for existing hypothesis with same claim
            existing = self._find_existing_hypothesis(h.claim)
            if existing:
                if existing.status in (HypothesisStatus.PROMOTED, HypothesisStatus.FALSIFIED):
                    log.debug("Skipping already-resolved hypothesis: %s", existing.id)
                    continue
                unique.append((existing, method))
            else:
                # Assign stable ID from claim hash
                h.id = _claim_hash(h.claim)
                unique.append((h, method))

        # Prioritize: calendar > composite > single-source, break ties by method promotion weight
        method_weights = self.compute_method_weights()

        def _score(item: tuple[Hypothesis, str]) -> float:
            h, method = item
            base = 0.0
            if "calendar" in h.tags:
                base = 2.0
            elif "composite" in h.tags:
                base = 1.0
            return base + method_weights.get(method, 0.5)

        prioritized = sorted(unique, key=_score, reverse=True)
        selected_pairs = prioritized[:5]
        selected = [h for h, _ in selected_pairs]

        # Apply Bonferroni correction: compute adjusted alpha per cycle
        # but do NOT mutate h.significance_threshold (pre-registered, immutable)
        # Store on each hypothesis object for this cycle (not persisted on model)
        n_tests = max(1, len(selected))
        for h in selected:
            h._bonferroni_n = n_tests  # type: ignore[attr-defined]

        # Log method → hypothesis_id attribution for future weight computation
        method_hypothesis_ids: dict[str, list[str]] = {}
        for h, method in selected_pairs:
            method_hypothesis_ids.setdefault(method, []).append(h.id)

        self._log_methodology({
            "phase": "hypothesis_generation",
            "total_generated": len(candidates),
            "unique": len(unique),
            "selected": len(selected),
            "bonferroni_n": n_tests,
            "adjusted_alpha": (selected[0].significance_threshold / n_tests) if selected else None,
        })
        self._log_methodology({
            "phase": "hypothesis_sources",
            "method_hypothesis_ids": method_hypothesis_ids,
        })

        return selected

    def compute_method_weights(self) -> dict[str, float]:
        """Read methodology.jsonl to compute per-method promotion rate.

        Uses Laplace smoothing: (promotions + 1) / (promotions + kills + 2).
        Methods with no history get 0.5 (neutral). Reads hypothesis_sources
        records to map method → hypothesis_id, then decision records for outcomes.
        """
        if not self.methodology_log.exists():
            return {}

        method_to_hyps: dict[str, set[str]] = {}
        hyp_outcomes: dict[str, str] = {}

        with open(self.methodology_log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                phase = rec.get("phase", "")
                if phase == "hypothesis_sources":
                    for method, ids in rec.get("method_hypothesis_ids", {}).items():
                        method_to_hyps.setdefault(method, set()).update(ids)
                elif phase == "decision":
                    hid = rec.get("hypothesis_id")
                    action = rec.get("action")
                    if hid and action:
                        hyp_outcomes[hid] = action

        weights: dict[str, float] = {}
        for method, hyp_ids in method_to_hyps.items():
            promotes = sum(1 for hid in hyp_ids if hyp_outcomes.get(hid) == "promote")
            kills = sum(1 for hid in hyp_ids if hyp_outcomes.get(hid) == "kill")
            weights[method] = (promotes + 1) / (promotes + kills + 2)

        return weights

    def _build_composite_signal(self, h: Hypothesis, is_df: pd.DataFrame) -> pd.Series | None:
        """Build regime-holding signal from composite hypothesis.

        Returns None if required alt data is unavailable.
        These signals trade rarely — enter on trigger, hold for N bars, then flat.
        """
        prices = is_df["close"]
        holding = 20
        for tag in h.tags:
            if tag.startswith("hold_"):
                holding = int(tag.split("_")[1])

        try:
            alt_sources = self.alt_data.fetch_all()
        except Exception:
            return None

        signals = pd.Series(0, index=prices.index)

        if "fear_capitulation" in h.tags:
            fg = alt_sources.get("fear_greed")
            if fg is None or "fear_greed" not in fg.columns:
                return None
            fg_aligned = fg["fear_greed"].reindex(prices.index, method="ffill").fillna(50)
            rolling_high = prices.rolling(60).max()
            drawdown = (prices - rolling_high) / rolling_high
            trigger = (fg_aligned < 25) & (drawdown < -0.10)
            signals = self._apply_regime_hold(trigger, holding, direction=1)

        elif "greed_euphoria" in h.tags:
            fg = alt_sources.get("fear_greed")
            if fg is None or "fear_greed" not in fg.columns:
                return None
            fg_aligned = fg["fear_greed"].reindex(prices.index, method="ffill").fillna(50)
            rolling_low = prices.rolling(60).min()
            rally = (prices - rolling_low) / rolling_low
            trigger = (fg_aligned > 75) & (rally > 0.15)
            signals = self._apply_regime_hold(trigger, holding, direction=-1)

        elif "onchain_divergence" in h.tags:
            ov = alt_sources.get("onchain_volume")
            if ov is None or "onchain_volume_usd" not in ov.columns:
                return None
            ov_aligned = ov["onchain_volume_usd"].reindex(prices.index, method="ffill")
            px_trend = prices.pct_change(20)
            ov_trend = ov_aligned.pct_change(20)
            if "bullish" in h.tags:
                trigger = (px_trend < -0.10) & (ov_trend > 0.10)
                signals = self._apply_regime_hold(trigger, holding, direction=1)
            else:
                trigger = (px_trend > 0.10) & (ov_trend < -0.10)
                signals = self._apply_regime_hold(trigger, holding, direction=-1)

        elif "miner_capitulation" in h.tags:
            hr = alt_sources.get("hashrate")
            if hr is None or "hashrate" not in hr.columns:
                return None
            hr_aligned = hr["hashrate"].reindex(prices.index, method="ffill")
            hr_peak = hr_aligned.rolling(30).max()
            hr_dd = (hr_aligned - hr_peak) / hr_peak
            was_down = hr_dd.rolling(30).min() < -0.10
            recovering = hr_dd > -0.03
            trigger = was_down & recovering & (~(was_down & recovering).shift(1).fillna(False))
            signals = self._apply_regime_hold(trigger, holding, direction=1)

        elif "end_of_month" in h.tags:
            # Short last 3 days of month if negative drift, long if positive
            dom = prices.index.day
            eom_mask = pd.Series(dom >= 29, index=prices.index)
            direction = -1 if "negative" in h.tags else 1
            signals = pd.Series(0, index=prices.index)
            signals.loc[eom_mask] = direction
            return signals

        elif "weekend_skip" in h.tags:
            # Long only on weekdays, flat on weekends
            dow = prices.index.dayofweek
            weekday_mask = pd.Series(dow < 5, index=prices.index)
            signals = pd.Series(0, index=prices.index)
            signals.loc[weekday_mask] = 1
            return signals

        elif "us_session" in h.tags:
            # Long only during US session (13:00-21:00 UTC)
            hour = prices.index.hour
            us_mask = pd.Series((hour >= 13) & (hour < 21), index=prices.index)
            signals = pd.Series(0, index=prices.index)
            signals.loc[us_mask] = 1
            return signals

        elif "regime_confluence" in h.tags:
            fg = alt_sources.get("fear_greed")
            ov = alt_sources.get("onchain_volume")
            if fg is None or ov is None:
                return None
            fg_aligned = fg["fear_greed"].reindex(prices.index, method="ffill").fillna(50)
            ov_aligned = ov["onchain_volume_usd"].reindex(prices.index, method="ffill")
            ov_trend = ov_aligned.pct_change(20)
            if "bullish" in h.tags:
                px_low = prices.rolling(60).min()
                trigger = (fg_aligned < 25) & (ov_trend > 0.05) & (prices <= px_low * 1.05)
                signals = self._apply_regime_hold(trigger, holding, direction=1)
            else:
                px_high = prices.rolling(60).max()
                trigger = (fg_aligned > 75) & (ov_trend < -0.05) & (prices >= px_high * 0.95)
                signals = self._apply_regime_hold(trigger, holding, direction=-1)
        else:
            return None

        return signals.reindex(prices.index).fillna(0)

    @staticmethod
    def _apply_regime_hold(trigger: pd.Series, holding_period: int, direction: int) -> pd.Series:
        """Convert trigger events into held positions.

        Enter on trigger, hold for holding_period bars, then go flat.
        If a new trigger fires during a hold, extend the hold.
        This produces sparse signals — only a few trades per year.
        """
        signals = pd.Series(0, index=trigger.index)
        bars_remaining = 0
        for i in range(len(trigger)):
            if trigger.iloc[i]:
                bars_remaining = holding_period
            if bars_remaining > 0:
                signals.iloc[i] = direction
                bars_remaining -= 1
        return signals

    def _build_signal_from_hypothesis(self, h: Hypothesis, is_df: pd.DataFrame) -> pd.Series:
        """Build a trading signal series using in-sample data only."""
        # Try composite signal builder first
        if "composite" in h.tags:
            composite = self._build_composite_signal(h, is_df)
            if composite is not None:
                return composite

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
        elif "momentum" in h.tags and any(t.startswith("lookback_") for t in h.tags):
            lookback = 20
            for tag in h.tags:
                if tag.startswith("lookback_"):
                    lookback = int(tag.split("_")[1])
            rolling_ret = returns.rolling(lookback).sum()
            if "reversal" in h.tags:
                signals = -(rolling_ret > 0).astype(int).replace(0, -1)
            else:
                signals = (rolling_ret > 0).astype(int).replace(0, -1)
        elif "vol_scaling" in h.tags:
            # Volatility-scaled strategy: reduce position in high-vol, increase in low-vol
            vol = returns.abs().rolling(20).mean()
            vol_ma = vol.rolling(50).mean()
            vol_ratio = (vol / vol_ma).reindex(prices.index).fillna(1.0)
            signals = pd.Series(1, index=prices.index)  # default long
            signals.loc[vol_ratio > 1.5] = 0    # step out in high vol
            signals.loc[vol_ratio < 0.7] = 1    # full position in low vol
        elif "pairs_trading" in h.tags:
            # Pairs trading: use price z-score as proxy for spread dislocation
            ma = prices.rolling(50).mean()
            std = prices.rolling(50).std()
            z = ((prices - ma) / std).reindex(prices.index).fillna(0)
            signals = pd.Series(0, index=prices.index)
            signals.loc[z < -1.5] = 1   # buy when spread is low
            signals.loc[z > 1.5] = -1   # sell when spread is high
        elif "lead_lag" in h.tags:
            # Lead-lag: trade the follower based on the leader's return
            # Since we only have the follower's data here, use its own lagged returns
            # as a proxy (the signal builder gets the follower's data)
            lag_ret = returns.shift(1).reindex(prices.index).fillna(0)
            signals = pd.Series(0, index=prices.index)
            signals.loc[lag_ret > 0] = 1
            signals.loc[lag_ret < 0] = -1
        elif "skew" in h.tags:
            # Skew strategy: positive skew → buy dips, negative skew → fade rallies
            ma = prices.rolling(20).mean()
            std = prices.rolling(20).std()
            z = (prices - ma) / std
            signals = pd.Series(0, index=prices.index)
            if "positive" in h.tags:
                # Buy when below MA (dips), expecting asymmetric upside
                signals[z < -1.0] = 1
            else:
                # Sell when above MA (rallies), expecting mean reversion / crash
                signals[z > 1.0] = -1
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

        Walk-forward evaluation only: the harness does NOT fit state on the
        training window (see walk_forward_backtest docstring). All current
        signal builders are stateless rolling indicators whose no-lookahead
        guarantee comes from past-anchored windows, not from train/test
        separation. Trainable signals would require extending the harness.
        """
        tf_periods = {"1h": 365 * 24, "4h": 365 * 6, "1d": 365, "1w": 52}
        periods_per_year = tf_periods.get(timeframe, 365 * 6)

        # Bonferroni-adjusted alpha: persisted on the experiment so it survives restarts
        bonferroni_n = getattr(h, "_bonferroni_n", 1)
        adjusted_alpha = h.significance_threshold / bonferroni_n

        exp = Experiment(
            hypothesis_id=h.id,
            description=f"Backtest {h.claim[:80]} on {symbol} {timeframe}",
            method="backtest",
            parameters={
                "symbol": symbol, "timeframe": timeframe, "lookback": len(df),
                "bonferroni_n": bonferroni_n, "adjusted_alpha": adjusted_alpha,
            },
            success_criteria=f"OOS Sharpe > 0 with p < {adjusted_alpha:.4f} (Bonferroni-adjusted)",
            failure_criteria=f"OOS Sharpe not significantly different from zero (p >= {adjusted_alpha:.4f})",
        )
        self._save_obj("experiments", exp.id, exp.model_dump())

        try:
            # Walk-forward validation: expanding train window with 5 OOS folds
            signal_builder = lambda sub_df: self._build_signal_from_hypothesis(h, sub_df)
            wf = walk_forward_backtest(
                df, signal_builder,
                n_folds=5, train_ratio=0.7,
                periods_per_year=periods_per_year, fee_bps=26,
            )

            # Statistical tests on concatenated OOS returns with Bonferroni-adjusted alpha
            alpha = adjusted_alpha
            oos_sharpe = sharpe_significance(wf.oos_returns, periods_per_year=periods_per_year, alpha=alpha)
            oos_mean = mean_return_test(wf.oos_returns, alpha=alpha)
            oos_boot = bootstrap_sharpe(wf.oos_returns, periods_per_year=periods_per_year, alpha=alpha)

            exp.status = ExperimentStatus.COMPLETED
            exp.results = {
                "walk_forward": {
                    "n_folds": wf.n_folds,
                    "mean_oos_sharpe": wf.aggregate_oos_sharpe,
                    "folds": wf.folds,
                },
                "out_of_sample": {
                    "sharpe": wf.aggregate_oos_sharpe,
                    "total_return": float((1 + wf.oos_returns).prod() - 1),
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
            is_positive = wf.aggregate_oos_sharpe > 0

            if both_significant and is_positive:
                quality = EvidenceQuality.STRONG
                direction = EvidenceDirection.SUPPORTS
            elif is_positive and (oos_sharpe.significant or oos_boot.significant):
                quality = EvidenceQuality.MODERATE
                direction = EvidenceDirection.SUPPORTS
            elif wf.aggregate_oos_sharpe < -0.5 and both_significant:
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
                summary=f"Walk-forward OOS Sharpe={wf.aggregate_oos_sharpe:.2f} ({wf.n_folds} folds, "
                        f"p={oos_sharpe.p_value:.3f}, α={alpha:.4f}). "
                        f"Bootstrap CI=[{oos_boot.ci_lower:.2f}, {oos_boot.ci_upper:.2f}]",
                statistics=oos,
            )
            self._save_obj("evidence", ev.id, ev.model_dump())

            log.info("Experiment %s: WF OOS Sharpe=%.2f (%d folds) p=%.3f (α=%.4f) → %s %s",
                     exp.id, wf.aggregate_oos_sharpe, wf.n_folds, oos_sharpe.p_value, alpha,
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

        gate = evaluate_promotion_gate(evidence)
        strong_support = gate["strong_support"]
        strong_contradict = gate["strong_contradict"]
        oos_support = gate["oos_support"]
        distinct_experiments = gate["distinct_experiments"]

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
        self._emit_telemetry("cycle.started")
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

            # Determine which datasets to test on. Primary from signal source,
            # plus additional datasets for cross-validation (distinct experiments).
            existing_evidence = [Evidence.model_validate(d) for d in self._list_objs("evidence")
                                 if d.get("hypothesis_id") == h.id]
            fresh_tested_datasets = self._fresh_tested_datasets(existing_evidence)

            # Build candidate datasets: primary first, then cross-validation pairs
            datasets = []
            if h.claim in claim_to_data:
                sym, tf, df = claim_to_data[h.claim]
                datasets.append((sym, tf, df))

            # Extract the base asset from tags for cross-validation
            base_asset = None
            for tag in h.tags:
                if "usdt" in tag:
                    base_asset = tag.replace("_", "/").upper()
                    break

            # Add cross-validation datasets (same strategy, different data)
            for sym, tf in DEFAULT_UNIVERSE:
                if (sym, tf) not in fresh_tested_datasets and (not datasets or (sym, tf) != (datasets[0][0], datasets[0][1])):
                    try:
                        xdf = self.market.fetch_ohlcv(symbol=sym, timeframe=tf, limit=100000)
                        if len(xdf) >= 200:
                            datasets.append((sym, tf, xdf))
                    except Exception:
                        continue
                if len(datasets) >= 3:
                    break

            if not datasets:
                symbol, timeframe = "BTC/USDT", "1h"
                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=100000)
                datasets.append((symbol, timeframe, df))

            # Test on each dataset (distinct experiments for promotion gate)
            n_folds = 5
            min_bars = n_folds * 50 / 0.3  # each OOS fold needs ≥50 bars
            for symbol, timeframe, df in datasets:
                if (symbol, timeframe) in fresh_tested_datasets:
                    continue
                if len(df) < min_bars:
                    log.info("Skipping %s %s: %d bars too short for %d-fold walk-forward (need %d)",
                             symbol, timeframe, len(df), n_folds, int(min_bars))
                    continue
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
            self._emit_telemetry(
                "hypothesis.decided",
                level="info" if decision != "error" else "error",
                details={
                    "hypothesis_id": h.id,
                    "decision": decision,
                    "total_evidence_store_size": len(self.state.list_all("evidence")),
                },
            )

        # Phase 6: Report graph state
        graph = self.graph_store.load()
        cycle_report["graph_nodes"] = graph.node_count
        cycle_report["graph_edges"] = graph.edge_count

        log.info("=== Cycle complete: %d hypotheses tested, graph has %d nodes ===",
                 len(hypotheses), graph.node_count)

        # Decision breakdown: how many hypotheses landed in each terminal state
        # this cycle. A cycle where every decision is "continue" produces no new
        # epistemic state — surfacing this explicitly is how meta-scan detects
        # the frozen-loop failure mode (Pattern 2 of the 2026-04-24 synthesis).
        decisions_by_kind: dict[str, int] = {}
        for hrep in cycle_report["hypotheses"]:
            kind = hrep.get("decision", "unknown")
            decisions_by_kind[kind] = decisions_by_kind.get(kind, 0) + 1

        self._emit_telemetry(
            "cycle.completed",
            details={
                "hypotheses_evaluated": len(cycle_report["hypotheses"]),
                "total_evidence_store_size": len(self.state.list_all("evidence")),
                "signals_found": cycle_report.get("signals_found", 0),
                "graph_nodes": graph.node_count,
                "graph_edges": graph.edge_count,
                "decisions_by_kind": decisions_by_kind,
            },
        )

        # S3-P2 frozen-loop escalation: if the last N completed cycles were
        # all-continue (no kills, promotions, or pivots), the loop is producing
        # no epistemic state and the silent-monitor failure mode applies.
        try:
            self._maybe_escalate_frozen_loop()
        except Exception as exc:  # never let escalation crash a cycle
            log.warning("Frozen-loop escalation check failed: %s", exc)

        return cycle_report

    # --------------------------------------------------------------------
    # S3-P2 frozen-loop escalation
    # --------------------------------------------------------------------

    TELEMETRY_PATH = Path("/opt/workspace/runtime/.telemetry/events.jsonl")
    HANDOFF_DIR = Path("/opt/workspace/runtime/.handoff")

    def _read_recent_runner_events(self, max_events: int = 200) -> list[dict]:
        """Return the most recent atlas.runner events from the workspace
        telemetry stream. Reads the file once; cheap enough for a per-cycle
        check at our cadence."""
        path = self.TELEMETRY_PATH
        if not path.exists():
            return []
        events: list[dict] = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                except Exception:
                    continue
                if e.get("source") == "atlas.runner":
                    events.append(e)
        return events[-max_events:]

    def _maybe_escalate_frozen_loop(self) -> None:
        """Emit a `cycle.escalated` event and write an URGENT handoff if the
        last `FROZEN_LOOP_ESCALATION_AFTER` cycle.completed events were all
        all-continue (and we have not already escalated this streak).

        Vacuous cycles (no hypotheses evaluated) are skipped — they neither
        contribute to nor break the streak. Idempotency: if a cycle.escalated
        event newer than the streak's first cycle already exists, skip.
        """
        events = self._read_recent_runner_events()
        if not events:
            return

        completed = [e for e in events if e.get("eventType") == "cycle.completed"]
        if len(completed) < FROZEN_LOOP_ESCALATION_AFTER:
            return

        # Walk back from most recent, counting non-vacuous all-continue cycles.
        streak: list[dict] = []
        for e in reversed(completed):
            details = e.get("details", {}) or {}
            n = details.get("hypotheses_evaluated", 0)
            if n <= 0:
                continue  # vacuous — skip
            kinds = details.get("decisions_by_kind", {}) or {}
            if set(kinds.keys()) == {"continue"}:
                streak.append(e)
                if len(streak) >= FROZEN_LOOP_ESCALATION_AFTER:
                    break
            else:
                return  # streak broken

        if len(streak) < FROZEN_LOOP_ESCALATION_AFTER:
            return

        streak_start_ts = streak[-1].get("timestamp", 0)

        # Idempotent: skip if a cycle.escalated event already covers this streak.
        for e in events:
            if (e.get("eventType") == "cycle.escalated"
                    and e.get("timestamp", 0) >= streak_start_ts):
                return

        self._emit_telemetry(
            "cycle.escalated",
            level="warning",
            details={
                "reason": "frozen_loop_all_continue",
                "consecutive_cycles": len(streak),
                "streak_start_ts": streak_start_ts,
                "decisions_by_kind": (
                    streak[0].get("details", {}).get("decisions_by_kind", {})
                ),
                "total_evidence_store_size": (
                    streak[0].get("details", {}).get("total_evidence_store_size", 0)
                ),
            },
        )
        self._write_frozen_loop_handoff(streak)

    def _write_frozen_loop_handoff(self, streak: list[dict]) -> None:
        """Drop one URGENT handoff to general/atlas describing the streak.
        Dedup by glob — if any URGENT-atlas-frozen-loop-*.md exists, skip."""
        try:
            self.HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
            existing = list(self.HANDOFF_DIR.glob("URGENT-atlas-frozen-loop-*.md"))
            if existing:
                return
            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%MZ")
            path = self.HANDOFF_DIR / f"URGENT-atlas-frozen-loop-{now_iso}.md"
            evidence_size = (streak[0].get("details", {})
                             .get("total_evidence_store_size", 0))
            body = (
                "---\n"
                f"priority: critical\n"
                f"created: {datetime.now(timezone.utc).isoformat()}\n"
                "from: atlas.runner (self-emitted via S3-P2 escalation gate)\n"
                "to: atlas / general\n"
                "---\n\n"
                "# atlas — frozen loop (auto-escalated)\n\n"
                f"The autonomous loop has produced {len(streak)} consecutive\n"
                "all-continue cycles with no kill/promote/pivot decisions.\n"
                f"Evidence store size at streak start: {evidence_size}.\n\n"
                "## Likely causes\n\n"
                "- Dataset retest cache is too aggressive (DATASET_RETEST_AFTER) —\n"
                "  hypothesis is being re-evaluated against the same evidence.\n"
                "- All available data has been exhausted under the current signal\n"
                "  detectors; new detectors or new data sources needed.\n"
                "- A bug is silently dropping experiment runs.\n\n"
                "## Diagnostic\n\n"
                "  grep '\"eventType\": \"cycle.completed\"' \\\n"
                "    /opt/workspace/runtime/.telemetry/events.jsonl | tail -10\n"
                "  .venv/bin/atlas strategy readiness\n\n"
                "Delete this file once the root cause is addressed; the gate is\n"
                "idempotent and will re-fire only on a new streak.\n"
            )
            path.write_text(body)
            log.warning("Wrote frozen-loop URGENT handoff to %s", path)
        except Exception as exc:
            log.warning("Failed to write frozen-loop handoff: %s", exc)

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
                self._emit_telemetry("cycle.failed", level="error", details={"error": str(e)})

            log.info("Sleeping %ds until next cycle", interval_seconds)
            time.sleep(interval_seconds)
