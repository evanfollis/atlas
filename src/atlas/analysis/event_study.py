"""Event-study framework — Phase B1.

Around a list of timestamped events, compute per-event return windows and
summary cumulative abnormal returns (CAR) against a matched-control
benchmark drawn from non-event periods.

Deliberate design choices:
  - Caller supplies the return series (pandas Series, DatetimeIndex, UTC).
  - Event-time alignment is bar-index based: we find the nearest bar ≥ event
    timestamp and anchor k=0 there. k<0 is pre-event, k>0 is post-event.
  - "Abnormal return" = event return − matched-control mean return at same k.
  - Matched controls are random non-event windows of the same length, drawn
    from bars outside a ±buffer of any event. Seed is explicit for
    reproducibility.
  - Caller decides significance: we expose per-event paths, CAR distribution,
    and control-sampled CAR distribution. Reject/accept decisions are the
    caller's, not this module's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

import numpy as np
import pandas as pd


@dataclass
class EventStudyResult:
    event_paths: pd.DataFrame        # rows=event index, cols=k ∈ [-pre, +post]
    event_car: pd.Series             # per-event CAR over [k0_car .. k1_car]
    control_car: np.ndarray          # CAR distribution from n_controls matched windows
    p_two_sided: float               # frac of |control_car| ≥ |mean event_car|
    mean_event_car: float
    median_event_car: float
    k0_car: int
    k1_car: int


def event_study(
    returns: pd.Series,
    events: list[datetime],
    pre: int = 5,
    post: int = 20,
    car_window: tuple[int, int] | None = None,
    n_controls: int = 1000,
    buffer: int = 30,
    rng_seed: int | None = None,
) -> EventStudyResult:
    """Run an event study on a return series.

    Args:
        returns: per-bar simple returns, DatetimeIndex.
        events: list of event timestamps (tz-aware UTC recommended).
        pre, post: bars before / after event to include in the window.
        car_window: (k0, k1) inclusive for CAR summation; defaults to (0, post).
        n_controls: number of matched non-event windows to draw.
        buffer: bars around any event to exclude from control sampling.
        rng_seed: for reproducibility.

    Returns:
        EventStudyResult with per-event paths, event CAR per event, control
        CAR distribution, and a two-sided empirical p-value comparing
        mean event CAR to the control distribution.
    """
    if car_window is None:
        car_window = (0, post)
    k0_car, k1_car = car_window
    if not (-pre <= k0_car <= k1_car <= post):
        raise ValueError(f"car_window {car_window} must lie in [-{pre}, {post}]")

    returns = returns.sort_index()
    idx = returns.index

    # Anchor each event to the first bar >= event timestamp.
    event_anchors: list[int] = []
    for ev in events:
        ev_ts = pd.Timestamp(ev)
        if ev_ts.tz is None:
            ev_ts = ev_ts.tz_localize("UTC")
        pos = idx.searchsorted(ev_ts, side="left")
        if pos < pre or pos + post >= len(idx):
            continue  # event too close to series edges
        event_anchors.append(int(pos))

    if not event_anchors:
        raise ValueError("No events fit inside the returns series with requested window")

    ks = list(range(-pre, post + 1))
    rows = []
    for a in event_anchors:
        rows.append(returns.iloc[a - pre : a + post + 1].values)
    event_paths = pd.DataFrame(rows, columns=ks)

    # Per-event CAR over [k0_car, k1_car]
    car_cols = [k for k in ks if k0_car <= k <= k1_car]
    event_car = event_paths[car_cols].sum(axis=1)

    # Build control sampling pool: bar indices far from any event.
    blocked = np.zeros(len(idx), dtype=bool)
    for a in event_anchors:
        lo = max(0, a - buffer - pre)
        hi = min(len(idx), a + buffer + post + 1)
        blocked[lo:hi] = True
    # Also need room on both sides for a full window
    valid = np.where(~blocked)[0]
    valid = valid[(valid >= pre) & (valid + post < len(idx))]
    if len(valid) < n_controls:
        # Fall back: sample with replacement if pool is small
        replace = True
    else:
        replace = False

    rng = np.random.default_rng(rng_seed)
    anchors = rng.choice(valid, size=n_controls, replace=replace)
    control_car = np.empty(n_controls)
    k0_offset = k0_car + pre  # offset into window array
    k1_offset = k1_car + pre
    rv = returns.values
    for i, a in enumerate(anchors):
        control_car[i] = rv[a + k0_car : a + k1_car + 1].sum()

    mean_event_car = float(event_car.mean())
    median_event_car = float(event_car.median())
    # Two-sided empirical p: fraction of control_car with |.| ≥ |observed mean|
    p_two = float((np.abs(control_car) >= abs(mean_event_car)).mean())

    return EventStudyResult(
        event_paths=event_paths,
        event_car=event_car,
        control_car=control_car,
        p_two_sided=p_two,
        mean_event_car=mean_event_car,
        median_event_car=median_event_car,
        k0_car=k0_car,
        k1_car=k1_car,
    )
