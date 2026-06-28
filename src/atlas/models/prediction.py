"""Prediction — a dated, falsifiable forward forecast scored against realized data.

The forward-prediction ledger converts the recurring signal scan into a
calibration engine. Instead of re-backtesting an already-exhausted hypothesis
space, Atlas registers what each detected pattern implies *forward* and scores
it once the window closes. This produces genuinely out-of-sample-in-time
evidence (`live_observation`) that the backtest space cannot — forward time
always supplies new data.

Three properties are load-bearing (see CAUSAL_LOOP_AUDIT.md Q5):

1. **Bucketed id** — the scan fires the same claims every hour. Keying the id on
   a non-overlapping horizon *bucket* (not the cycle timestamp) yields exactly
   one prediction per claim per forward window, idempotent across hourly cycles.
   Otherwise hundreds of overlapping, pseudo-replicated predictions corrupt
   calibration and the "distinct experiments" promotion gate.
2. **Frozen strategy spec** — `symbol`, `timeframe`, and `strategy_tags` snapshot
   everything `_build_signal_from_hypothesis` needs to reconstruct the position
   series. The scorer replays this frozen spec on the forward window only; it
   never re-detects or re-fits. That is what makes the evidence OOS-in-time
   rather than a deferred backtest.
3. **Conservative null default** — on 1h price features after fees the honest
   expectation is that refutations hold forward (`no_significant_edge`), not
   that the ledger unfreezes the loop into promotions. Promotions need new
   feature space; a forward "edge" on the current features should be suspected
   as noise first.
"""

from datetime import datetime, timezone
import hashlib

from pydantic import BaseModel, Field


def _norm_horizon(horizon_days: float) -> str:
    """Stable string form so 7 and 7.0 never produce divergent ids/buckets."""
    if not (horizon_days > 0):  # rejects 0, negative, and NaN (NaN > 0 is False)
        raise ValueError(f"horizon_days must be positive, got {horizon_days!r}")
    return f"{float(horizon_days):g}"


def prediction_id(hypothesis_id: str, horizon_days: float, bucket: int) -> str:
    """Deterministic id: one prediction per (claim, horizon, non-overlapping window)."""
    raw = f"{hypothesis_id}:{_norm_horizon(horizon_days)}:{bucket}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


class Prediction(BaseModel):
    id: str
    hypothesis_id: str
    claim: str

    # --- Frozen strategy spec (reconstructs the position series, no re-fit) ---
    symbol: str
    timeframe: str
    strategy_tags: list[str] = Field(default_factory=list)

    # --- Non-overlapping forward window ---
    horizon_days: float
    bucket: int                 # floor(asof_epoch / horizon_seconds) + 1
    window_start_ts: datetime   # forward window opens (fully in the future at registration)
    resolve_ts: datetime        # window_start + horizon; scoreable once now >= this
    asof_ts: datetime           # when first registered

    # --- The forecast ---
    statement: str
    predicted_label: str = "no_significant_edge"
    predicted_prob_up: float = 0.5  # probabilistic directional forecast (for Brier scoring in 2b)

    # --- Resolution (filled by the 2b scorer) ---
    status: str = "open"        # open | resolved | unresolvable
    realized_return: float | None = None
    realized_sharpe: float | None = None
    realized_label: str | None = None
    brier_score: float | None = None
    outcome: str | None = None  # confirmed_null | edge_appeared | inconclusive
    resolved_at: datetime | None = None

    @staticmethod
    def forward_bucket(now: datetime, horizon_days: float) -> tuple[int, datetime, datetime]:
        """Next fully-forward, non-overlapping window after `now`.

        All cycles within one horizon window resolve to the same bucket, so
        registration is idempotent across the hourly cycle.
        """
        _norm_horizon(horizon_days)  # validate (>0, finite) before arithmetic
        horizon_s = horizon_days * 86400.0
        bucket = int(now.timestamp() // horizon_s) + 1
        window_start = datetime.fromtimestamp(bucket * horizon_s, tz=timezone.utc)
        resolve = datetime.fromtimestamp((bucket + 1) * horizon_s, tz=timezone.utc)
        return bucket, window_start, resolve
