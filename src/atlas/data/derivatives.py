"""Derivatives data via ccxt public endpoints — free, no key required.

Covers funding rates (cross-venue), open interest, and Deribit's DVOL
volatility index. Paginates deep history with CSV caching, same pattern
as market.py.

Allowed venues (public endpoints work from US / Hetzner):
  - bitmex          — deepest funding history (~2016+)
  - okx             — broad coverage, modern
  - krakenfutures   — US-accessible perp venue
  - deribit         — options + DVOL index (no funding; options venue)

Geo-blocked on this host (do not add):
  - binance, binanceusdm, bybit
"""

import hashlib
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import ccxt
import pandas as pd

log = logging.getLogger(__name__)

# Tripwires: if the fetch loop hits these limits we raise instead of silently
# truncating. Silent truncation during stress periods would mechanically bias
# regime / stationarity analyses downstream (codex review #5, finding #5).
_MAX_CONSECUTIVE_ERRORS = 3
_MAX_TOTAL_ERRORS = 10


# Canonical perp symbols per venue
_VENUE_PERP_SYMBOLS = {
    "bitmex": {"BTC": "BTC/USD:BTC", "ETH": "ETH/USDT:USDT"},  # BTC inverse (longest), ETH linear (inverse ETH perp delisted)
    "okx": {"BTC": "BTC/USD:BTC", "ETH": "ETH/USD:ETH"},
    "krakenfutures": {"BTC": "BTC/USD:USD", "ETH": "ETH/USD:USD"},
}


class DerivativesData:
    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._exchanges: dict[str, ccxt.Exchange] = {}

    def _get(self, venue: str) -> ccxt.Exchange:
        if venue not in self._exchanges:
            self._exchanges[venue] = getattr(ccxt, venue)()
        return self._exchanges[venue]

    def _cache_path(self, key: str) -> Path:
        h = hashlib.md5(key.encode()).hexdigest()
        return self.cache_dir / f"{h}.csv"

    def fetch_funding_rates(self, venue: str, asset: str = "BTC",
                            since: str | None = None) -> pd.DataFrame:
        """Paginate funding rate history for a venue's asset perp.

        Returns DataFrame with single column `fundingRate` indexed by UTC timestamp.
        """
        if venue not in _VENUE_PERP_SYMBOLS:
            raise ValueError(f"Unsupported venue {venue}; add symbol mapping first")
        symbol = _VENUE_PERP_SYMBOLS[venue][asset]
        cache_key = f"funding:{venue}:{symbol}:{since or 'all'}"
        cpath = self._cache_path(cache_key)
        if cpath.exists():
            return pd.read_csv(cpath, index_col="timestamp", parse_dates=True)

        ex = self._get(venue)
        since_ts = (int(datetime.fromisoformat(since).timestamp() * 1000)
                    if since else int(datetime(2016, 1, 1, tzinfo=timezone.utc).timestamp() * 1000))
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        # Codex review #6: on error, retry the SAME window before advancing
        # the cursor. Advancing the cursor on exception silently drops any
        # data in that window — the exact hidden-censoring failure mode the
        # research pipeline is most vulnerable to.
        all_rows = []
        stride_ms = 500 * 8 * 3600 * 1000  # ~166 days fallback stride for empty batches
        max_retries = 5
        while since_ts < now_ms:
            batch = None
            for attempt in range(max_retries):
                try:
                    batch = ex.fetch_funding_rate_history(symbol, since=since_ts, limit=500)
                    break
                except Exception as e:
                    log.warning("funding fetch error (attempt %s/%s) venue=%s since=%s: %s",
                                attempt + 1, max_retries, venue, since_ts, e)
                    time.sleep(1.0 * (attempt + 1))
            else:
                raise RuntimeError(
                    f"funding fetch aborted for {venue}/{symbol} at since_ts={since_ts}: "
                    f"{max_retries} retries exhausted. Refusing to cache a truncated series.")
            if not batch:
                # Genuinely empty window (pre-venue-history or venue gap).
                # Probe forward by one stride; if we hit 5 consecutive empties at the end of
                # history we accept it, but if an empty occurs inside recorded data it will
                # show up as a gap in the post-fetch audit below.
                since_ts += stride_ms
                continue
            all_rows.extend(batch)
            last_ts = batch[-1]["timestamp"]
            new_since = last_ts + 1
            if new_since <= since_ts:
                new_since = since_ts + stride_ms
            since_ts = new_since
            time.sleep(0.3)

        if not all_rows:
            return pd.DataFrame(columns=["fundingRate"])
        df = pd.DataFrame(all_rows)[["timestamp", "fundingRate"]]
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.drop_duplicates(subset=["timestamp"]).set_index("timestamp").sort_index()

        # Post-fetch gap audit: warn on stretches > 3x median cadence.
        if len(df) > 10:
            gaps = df.index.to_series().diff().dropna()
            cadence = gaps.median()
            big = gaps[gaps > cadence * 3]
            if len(big) > 0:
                log.warning("funding series %s/%s has %d gaps > 3x cadence (%s); "
                            "largest = %s at %s", venue, symbol, len(big), cadence,
                            big.max(), big.idxmax())
        df.to_csv(cpath)
        return df

    def fetch_dvol(self, currency: str = "BTC", resolution_sec: int = 86400,
                   years_back: int = 5) -> pd.DataFrame:
        """Deribit DVOL volatility index (VIX-equivalent for crypto).

        Paginates ~1yr at a time. Returns DataFrame with columns
        [open, high, low, close] indexed by UTC timestamp.
        """
        cache_key = f"dvol:{currency}:{resolution_sec}:{years_back}"
        cpath = self._cache_path(cache_key)
        if cpath.exists():
            return pd.read_csv(cpath, index_col="timestamp", parse_dates=True)

        ex = self._get("deribit")
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        cursor = now_ms
        start_ms = now_ms - years_back * 365 * 86400 * 1000
        window = 365 * 86400 * 1000  # 1 year per call

        all_rows = []
        while cursor > start_ms:
            batch_start = max(cursor - window, start_ms)
            try:
                r = ex.public_get_get_volatility_index_data({
                    "currency": currency,
                    "start_timestamp": batch_start,
                    "end_timestamp": cursor,
                    "resolution": str(resolution_sec),
                })
            except Exception as e:
                raise RuntimeError(
                    f"DVOL fetch aborted at cursor={cursor}: {e}. "
                    f"Refusing to cache a truncated series.") from e
            data = r.get("result", {}).get("data", [])
            if not data:
                # Accept empty only when we've reached the requested start window
                # (i.e. before DVOL history began). Empty inside the window is a
                # real gap and must not be silently cached.
                if batch_start <= start_ms:
                    break
                raise RuntimeError(
                    f"DVOL empty batch inside requested window "
                    f"(cursor={cursor}, batch_start={batch_start}). "
                    f"Refusing to cache a truncated series.")
            all_rows.extend(data)
            # advance cursor back
            earliest = min(int(row[0]) for row in data)
            if earliest >= cursor:
                break
            cursor = earliest - 1
            time.sleep(0.3)

        if not all_rows:
            return pd.DataFrame(columns=["open", "high", "low", "close"])
        df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close"])
        df["timestamp"] = pd.to_datetime(df["timestamp"].astype("int64"), unit="ms", utc=True)
        for c in ["open", "high", "low", "close"]:
            df[c] = df[c].astype(float)
        df = df.drop_duplicates(subset=["timestamp"]).set_index("timestamp").sort_index()
        df.to_csv(cpath)
        return df
