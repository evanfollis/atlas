"""Market data fetching via ccxt with local caching.

Uses Bitstamp for deep history (paginated, 6+ years) with Kraken as fallback.
Bitstamp uses USD pairs; we normalize to USDT-equivalent for consistency.
"""

import hashlib
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ccxt
import pandas as pd


# Bitstamp symbol mapping (uses USD, not USDT)
_BITSTAMP_SYMBOLS = {
    "BTC/USDT": "BTC/USD",
    "ETH/USDT": "ETH/USD",
    "SOL/USDT": "SOL/USD",
}

# Timeframe to seconds for pagination stride calculation
_TF_SECONDS = {
    "1h": 3600,
    "4h": 4 * 3600,
    "1d": 86400,
    "1w": 7 * 86400,
}


class MarketData:
    def __init__(self, cache_dir: Path, exchange_id: str = "bitstamp") -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.exchange = getattr(ccxt, exchange_id)()

    def _cache_key(self, method: str, symbol: str, timeframe: str, since: int, limit: int) -> str:
        raw = f"{self.exchange.id}:{method}:{symbol}:{timeframe}:{since}:{limit}"
        return hashlib.md5(raw.encode()).hexdigest()

    def _cache_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.csv"

    def fetch_ohlcv(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "4h",
        since: str | None = None,
        limit: int = 100000,
    ) -> pd.DataFrame:
        # Map USDT symbols to exchange-native pairs
        exchange_symbol = _BITSTAMP_SYMBOLS.get(symbol, symbol)

        since_ts = int(datetime.fromisoformat(since).timestamp() * 1000) if since else None
        cache_key = self._cache_key("ohlcv", exchange_symbol, timeframe, since_ts or 0, limit)
        cache_path = self._cache_path(cache_key)

        if cache_path.exists():
            return pd.read_csv(cache_path, index_col="timestamp", parse_dates=True)

        # Paginate: fetch in 1000-bar pages with stride-based starts
        page_size = 1000
        tf_ms = _TF_SECONDS.get(timeframe, 4 * 3600) * 1000
        stride_ms = page_size * tf_ms  # how far each page covers in time

        if since_ts is None:
            # Default: fetch from 2015 (Bitstamp's deep history)
            since_ts = int(datetime(2015, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

        all_raw = []
        fetch_since = since_ts
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
        empty_pages = 0  # skip-ahead counter for sparse/missing early data

        while fetch_since < now_ms and len(all_raw) < limit:
            try:
                batch = self.exchange.fetch_ohlcv(
                    exchange_symbol, timeframe, since=fetch_since, limit=page_size,
                )
            except Exception:
                break

            if not batch:
                # Skip ahead by one stride; tolerate up to N consecutive empty pages
                empty_pages += 1
                if empty_pages > 24:  # gave up after ~2 years of empty stride
                    break
                fetch_since += stride_ms
                time.sleep(0.3)
                continue

            empty_pages = 0
            all_raw.extend(batch)

            # Advance: last bar + one tf stride
            new_since = batch[-1][0] + 1
            if new_since <= fetch_since:
                # Make sure we always advance
                new_since = fetch_since + stride_ms
            fetch_since = new_since
            time.sleep(0.3)  # rate limit

        if not all_raw:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(all_raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = df.drop_duplicates(subset=["timestamp"]).set_index("timestamp").sort_index()
        # Trim to requested limit
        if len(df) > limit:
            df = df.iloc[-limit:]
        df.to_csv(cache_path)
        return df

    def fetch_funding_rate(
        self,
        symbol: str = "BTC/USDT",
        since: str | None = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        since_ts = int(datetime.fromisoformat(since).timestamp() * 1000) if since else None
        cache_key = self._cache_key("funding", symbol, "8h", since_ts or 0, limit)
        cache_path = self._cache_path(cache_key)

        if cache_path.exists():
            return pd.read_csv(cache_path, index_col="timestamp", parse_dates=True)

        raw = self.exchange.fetch_funding_rate_history(symbol, since=since_ts, limit=limit)
        df = pd.DataFrame(raw)
        if not df.empty:
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
            df = df.set_index("timestamp")
            df.to_csv(cache_path)
        return df
