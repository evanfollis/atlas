"""Alternative data sources — sentiment, on-chain, mining.

Free APIs, no keys required. All return daily-frequency DataFrames
aligned to UTC midnight timestamps for easy joining with price data.
"""

import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests


class AlternativeData:
    """Fetches and caches non-price data from free public APIs."""

    def __init__(self, cache_dir: Path) -> None:
        self.cache_dir = cache_dir / "alternative"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, source: str, params: str) -> Path:
        key = hashlib.md5(f"{source}:{params}".encode()).hexdigest()
        return self.cache_dir / f"{source}_{key}.csv"

    def _fetch_json(self, url: str, retries: int = 2) -> dict | list | None:
        for attempt in range(retries + 1):
            try:
                r = requests.get(url, timeout=30)
                r.raise_for_status()
                return r.json()
            except Exception:
                if attempt < retries:
                    time.sleep(1)
        return None

    def fetch_fear_greed(self, limit: int = 1000) -> pd.DataFrame:
        """Fetch Fear & Greed Index (0=extreme fear, 100=extreme greed).

        Daily values. Causal mechanism: extreme fear → capitulation selling
        exhausted → reversal likely. Extreme greed → overleveraged longs →
        vulnerable to liquidation cascades.
        """
        cache = self._cache_path("fng", str(limit))
        if cache.exists():
            return pd.read_csv(cache, index_col="timestamp", parse_dates=True)

        data = self._fetch_json(f"https://api.alternative.me/fng/?limit={limit}")
        if not data or "data" not in data:
            return pd.DataFrame(columns=["fear_greed", "classification"])

        rows = []
        for entry in data["data"]:
            rows.append({
                "timestamp": pd.Timestamp(int(entry["timestamp"]), unit="s", tz="UTC"),
                "fear_greed": int(entry["value"]),
                "classification": entry["value_classification"],
            })

        df = pd.DataFrame(rows).set_index("timestamp").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df.to_csv(cache)
        return df

    def fetch_onchain_volume(self, timespan: str = "2years") -> pd.DataFrame:
        """Fetch estimated Bitcoin transaction volume (USD).

        Causal mechanism: surges in on-chain volume during price extremes
        signal large holders repositioning. High volume + price decline →
        distribution phase. High volume + price rise → accumulation.
        """
        cache = self._cache_path("onchain_vol", timespan)
        if cache.exists():
            return pd.read_csv(cache, index_col="timestamp", parse_dates=True)

        data = self._fetch_json(
            f"https://api.blockchain.info/charts/estimated-transaction-volume-usd"
            f"?timespan={timespan}&format=json&rollingAverage=24hours"
        )
        if not data or "values" not in data:
            return pd.DataFrame(columns=["onchain_volume_usd"])

        rows = []
        for entry in data["values"]:
            rows.append({
                "timestamp": pd.Timestamp(int(entry["x"]), unit="s", tz="UTC"),
                "onchain_volume_usd": float(entry["y"]),
            })

        df = pd.DataFrame(rows).set_index("timestamp").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df.to_csv(cache)
        return df

    def fetch_hashrate(self, timespan: str = "2years") -> pd.DataFrame:
        """Fetch Bitcoin hashrate and difficulty.

        Causal mechanism: hashrate drops signal miner capitulation (unprofitable
        miners shutting down → forced selling of BTC reserves to cover costs).
        Hashrate recovery after capitulation historically precedes price recovery.
        """
        cache = self._cache_path("hashrate", timespan)
        if cache.exists():
            return pd.read_csv(cache, index_col="timestamp", parse_dates=True)

        data = self._fetch_json(
            f"https://api.blockchain.info/charts/hash-rate"
            f"?timespan={timespan}&format=json&rollingAverage=7days"
        )
        if not data or "values" not in data:
            return pd.DataFrame(columns=["hashrate"])

        rows = []
        for entry in data["values"]:
            rows.append({
                "timestamp": pd.Timestamp(int(entry["x"]), unit="s", tz="UTC"),
                "hashrate": float(entry["y"]),
            })

        df = pd.DataFrame(rows).set_index("timestamp").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df.to_csv(cache)
        return df

    def fetch_mempool_size(self, timespan: str = "2years") -> pd.DataFrame:
        """Fetch Bitcoin mempool size (bytes).

        Causal mechanism: mempool congestion → higher fees → users delay
        transactions → reduced selling pressure. Clearing mempool after
        congestion → pent-up transactions execute → volatility spike.
        """
        cache = self._cache_path("mempool", timespan)
        if cache.exists():
            return pd.read_csv(cache, index_col="timestamp", parse_dates=True)

        data = self._fetch_json(
            f"https://api.blockchain.info/charts/mempool-size"
            f"?timespan={timespan}&format=json&rollingAverage=24hours"
        )
        if not data or "values" not in data:
            return pd.DataFrame(columns=["mempool_bytes"])

        rows = []
        for entry in data["values"]:
            rows.append({
                "timestamp": pd.Timestamp(int(entry["x"]), unit="s", tz="UTC"),
                "mempool_bytes": float(entry["y"]),
            })

        df = pd.DataFrame(rows).set_index("timestamp").sort_index()
        df = df[~df.index.duplicated(keep="last")]
        df.to_csv(cache)
        return df

    def fetch_all(self) -> dict[str, pd.DataFrame]:
        """Fetch all alternative data sources. Returns dict keyed by source name."""
        sources = {}
        for name, fetcher in [
            ("fear_greed", self.fetch_fear_greed),
            ("onchain_volume", self.fetch_onchain_volume),
            ("hashrate", self.fetch_hashrate),
            ("mempool", self.fetch_mempool_size),
        ]:
            try:
                df = fetcher()
                if not df.empty:
                    sources[name] = df
            except Exception:
                pass
        return sources


def align_to_price(alt_df: pd.DataFrame, price_df: pd.DataFrame, method: str = "ffill") -> pd.DataFrame:
    """Align daily alternative data to price bar timestamps.

    Alternative data is daily; price data may be 1h/4h/1d.
    Forward-fill to avoid lookahead bias — each bar sees only
    the most recent daily value available at that time.
    """
    combined = alt_df.reindex(price_df.index, method=method)
    return combined
