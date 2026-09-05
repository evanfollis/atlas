"""Market data fetching via ccxt with local caching.

Uses Bitstamp for deep history (paginated, 6+ years). Provider failover is not
implemented; incomplete or stale refreshes fail closed.
Bitstamp exposes USD pairs for this universe.  The current caller-facing USDT
names are compatibility aliases, not evidence that USD and USDT are identical.
"""

import hashlib
import os
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

# The autonomous scanner runs hourly, but a full-history exchange refresh is
# needlessly expensive at that cadence.  One day is short enough to keep the
# research window current while bounding Bitstamp traffic.
DEFAULT_CACHE_MAX_AGE = timedelta(days=1)


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

    @staticmethod
    def _read_cache(path: Path, timeframe: str) -> pd.DataFrame:
        df = pd.read_csv(path, index_col="timestamp", parse_dates=True)
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            raise ValueError(f"OHLCV cache missing columns: {sorted(required - set(df.columns))}")
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("OHLCV cache timestamp index is not datetime")
        if not df.index.is_monotonic_increasing or df.index.has_duplicates:
            raise ValueError("OHLCV cache timestamp index is unordered or duplicated")
        if not MarketData._is_contiguous(df, timeframe):
            raise ValueError("OHLCV cache contains an interval gap")
        return df

    @staticmethod
    def _last_timestamp_ms(df: pd.DataFrame) -> int | None:
        if df.empty:
            return None
        last = pd.Timestamp(df.index[-1])
        if last.tzinfo is None:
            last = last.tz_localize("UTC")
        else:
            last = last.tz_convert("UTC")
        return int(last.timestamp() * 1000)

    @staticmethod
    def _write_cache(path: Path, df: pd.DataFrame) -> None:
        """Replace a cache atomically so readers never see a partial CSV."""
        tmp = path.with_suffix(f"{path.suffix}.{os.getpid()}.tmp")
        try:
            df.to_csv(tmp)
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)

    def _annotate_provenance(
        self,
        df: pd.DataFrame,
        requested_symbol: str,
        exchange_symbol: str,
    ) -> pd.DataFrame:
        """Attach non-persistent provider identity to every returned frame."""
        df.attrs.update({
            "atlas_exchange_id": self.exchange.id,
            "atlas_requested_symbol": requested_symbol,
            "atlas_exchange_symbol": exchange_symbol,
            "atlas_quote_alias": requested_symbol != exchange_symbol,
        })
        return df

    def _fetch_ohlcv_pages(
        self,
        exchange_symbol: str,
        timeframe: str,
        since_ts: int,
        limit: int,
    ) -> tuple[pd.DataFrame, bool]:
        """Fetch paginated bars, including assets listed long after `since_ts`.

        Empty pre-listing pages are expected for a deep-history request.  The
        previous fixed 24-page cutoff stopped around late 2017 for a 2015 1h
        request, so it could never reach Bitstamp's SOL history.  Advancing to
        the bounded `now_ms` endpoint is finite without an arbitrary cutoff.
        """
        page_size = 1000
        tf_ms = _TF_SECONDS.get(timeframe, 4 * 3600) * 1000
        stride_ms = page_size * tf_ms
        all_raw = []
        fetch_since = since_ts
        now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

        while fetch_since < now_ms:
            batch = None
            for attempt in range(3):
                try:
                    batch = self.exchange.fetch_ohlcv(
                        exchange_symbol, timeframe, since=fetch_since, limit=page_size,
                    )
                    break
                except Exception:
                    if attempt == 2:
                        return self._rows_to_frame(all_raw), False
                    time.sleep(0.3)

            if not batch:
                if all_raw:
                    # Once a listing has begun, an empty page is a valid end
                    # marker only near the present.  Treat an earlier empty page
                    # as incomplete rather than skipping an unknown interval.
                    complete = fetch_since >= now_ms - (2 * tf_ms)
                    return self._rows_to_frame(all_raw), complete
                fetch_since += stride_ms
                time.sleep(0.3)
                continue

            all_raw.extend(batch)
            new_since = batch[-1][0] + 1
            if new_since <= fetch_since:
                new_since = fetch_since + stride_ms
            fetch_since = new_since
            time.sleep(0.3)

        return self._rows_to_frame(all_raw), True

    @staticmethod
    def _rows_to_frame(all_raw: list) -> pd.DataFrame:
        if not all_raw:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(
            all_raw,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        return df.drop_duplicates(subset=["timestamp"]).set_index("timestamp").sort_index()

    @staticmethod
    def _is_contiguous(df: pd.DataFrame, timeframe: str) -> bool:
        """Reject hidden holes; crypto OHLCV is expected at every interval."""
        if len(df) < 2:
            return True
        expected = pd.Timedelta(seconds=_TF_SECONDS.get(timeframe, 4 * 3600))
        return bool((df.index.to_series().diff().dropna() == expected).all())

    def fetch_ohlcv(
        self,
        symbol: str = "BTC/USDT",
        timeframe: str = "4h",
        since: str | None = None,
        limit: int = 100000,
        cache_max_age: timedelta | None = DEFAULT_CACHE_MAX_AGE,
    ) -> pd.DataFrame:
        # Map USDT symbols to exchange-native pairs (Bitstamp uses USD, not USDT)
        if self.exchange.id == "bitstamp":
            exchange_symbol = _BITSTAMP_SYMBOLS.get(symbol, symbol)
        else:
            exchange_symbol = symbol

        since_ts = int(datetime.fromisoformat(since).timestamp() * 1000) if since else None
        cache_key = self._cache_key("ohlcv", exchange_symbol, timeframe, since_ts or 0, limit)
        cache_path = self._cache_path(cache_key)

        cached = None
        if cache_path.exists():
            try:
                cached = self._read_cache(cache_path, timeframe)
            except (OSError, ValueError, TypeError, pd.errors.ParserError):
                # A generated cache is replaceable, but only after a complete
                # fresh fetch succeeds. Leave the bad file untouched on failure.
                cached = None

        if cached is not None and not cached.empty:
            # Every cache ages out by default. Callers that require a frozen
            # replay artifact can opt into cache_max_age=None explicitly.
            last_ms = self._last_timestamp_ms(cached)
            now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
            if (
                cache_max_age is None
                or now_ms - last_ms <= int(cache_max_age.total_seconds() * 1000)
            ):
                return self._annotate_provenance(cached, symbol, exchange_symbol)

            tf_ms = _TF_SECONDS.get(timeframe, 4 * 3600) * 1000
            tail, complete = self._fetch_ohlcv_pages(
                exchange_symbol,
                timeframe,
                last_ms + tf_ms,
                limit,
            )
            if not complete or tail.empty:
                # Keep the last-known-good cache on disk, but fail visibly:
                # silently returning it would make degraded freshness look like
                # a normal research scan.
                raise RuntimeError(f"incomplete OHLCV refresh for {exchange_symbol} {timeframe}")
            df = pd.concat([cached, tail])
            df = df[~df.index.duplicated(keep="last")].sort_index()
            if not self._is_contiguous(df, timeframe):
                raise RuntimeError(f"non-contiguous OHLCV refresh for {exchange_symbol} {timeframe}")
            if len(df) > limit:
                df = df.iloc[-limit:]
            self._write_cache(cache_path, df)
            return self._annotate_provenance(df, symbol, exchange_symbol)

        if since_ts is None:
            # Default: fetch from 2015 (Bitstamp's deep history)
            since_ts = int(datetime(2015, 1, 1, tzinfo=timezone.utc).timestamp() * 1000)

        df, complete = self._fetch_ohlcv_pages(exchange_symbol, timeframe, since_ts, limit)
        if not complete:
            # Partial history must never become research input or a durable
            # cache that looks complete on the next cycle.
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if df.empty:
            return self._annotate_provenance(df, symbol, exchange_symbol)
        if not self._is_contiguous(df, timeframe):
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        if len(df) > limit:
            df = df.iloc[-limit:]
        self._write_cache(cache_path, df)
        return self._annotate_provenance(df, symbol, exchange_symbol)

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
