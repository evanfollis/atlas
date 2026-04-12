"""Dune Analytics API client — free tier.

Executes saved queries and returns results as DataFrames. Uses CSV cache
keyed by query_id + parameter hash.

Auth: requires DUNE_API_KEY env var. Free tier: ~2500 datapoints/month,
10 queries/min. Designed for daily-refresh research, not tick-level.
"""

import hashlib
import json
import os
import time
from pathlib import Path

import pandas as pd
import requests


BASE = "https://api.dune.com/api/v1"


class DuneClient:
    def __init__(self, cache_dir: Path, api_key: str | None = None) -> None:
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key or os.environ.get("DUNE_API_KEY")
        if not self.api_key:
            raise RuntimeError("DUNE_API_KEY not set (env var or constructor arg)")
        self.session = requests.Session()
        self.session.headers.update({"X-Dune-API-Key": self.api_key})

    def _cache_path(self, query_id: int, params: dict | None) -> Path:
        raw = f"{query_id}:{json.dumps(params or {}, sort_keys=True)}"
        h = hashlib.md5(raw.encode()).hexdigest()
        return self.cache_dir / f"dune_{query_id}_{h[:8]}.csv"

    def execute_query(self, query_id: int, params: dict | None = None,
                      max_wait_sec: int = 300, use_cache: bool = True) -> pd.DataFrame:
        """Submit a saved Dune query, poll for completion, return rows as DataFrame."""
        cpath = self._cache_path(query_id, params)
        if use_cache and cpath.exists():
            return pd.read_csv(cpath)

        body = {"query_parameters": params} if params else {}
        resp = self.session.post(f"{BASE}/query/{query_id}/execute", json=body)
        resp.raise_for_status()
        exec_id = resp.json()["execution_id"]

        # Poll
        deadline = time.time() + max_wait_sec
        while time.time() < deadline:
            sr = self.session.get(f"{BASE}/execution/{exec_id}/status")
            sr.raise_for_status()
            s = sr.json()
            state = s.get("state", "")
            if state == "QUERY_STATE_COMPLETED":
                break
            if state in ("QUERY_STATE_FAILED", "QUERY_STATE_CANCELLED"):
                raise RuntimeError(f"Dune query {query_id} {state}: {s}")
            time.sleep(3)
        else:
            raise TimeoutError(f"Dune query {query_id} did not complete in {max_wait_sec}s")

        rr = self.session.get(f"{BASE}/execution/{exec_id}/results")
        rr.raise_for_status()
        r = rr.json()
        rows = r.get("result", {}).get("rows", [])
        df = pd.DataFrame(rows)
        if use_cache:
            df.to_csv(cpath, index=False)
        return df

    def get_latest_result(self, query_id: int, use_cache: bool = True) -> pd.DataFrame:
        """Get cached/latest results of a query without re-executing (cheap)."""
        cpath = self._cache_path(query_id, None)
        if use_cache and cpath.exists():
            return pd.read_csv(cpath)
        resp = self.session.get(f"{BASE}/query/{query_id}/results")
        resp.raise_for_status()
        r = resp.json()
        rows = r.get("result", {}).get("rows", [])
        df = pd.DataFrame(rows)
        if use_cache:
            df.to_csv(cpath, index=False)
        return df
