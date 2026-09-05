"""Market-data cache freshness and late-listing pagination regressions."""

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

from atlas.data.market import MarketData


_HOUR_MS = 3_600_000


def _row(timestamp_ms: int, close: float = 1.0) -> list[float]:
    return [timestamp_ms, close, close, close, close, 1.0]


class _FakeExchange:
    id = "bitstamp"

    def __init__(self, handler) -> None:
        self.handler = handler
        self.calls: list[int] = []

    def fetch_ohlcv(self, symbol, timeframe, since, limit):
        self.calls.append(since)
        return self.handler(symbol, timeframe, since, limit, len(self.calls))


def _market(tmp_path: Path, exchange: _FakeExchange) -> MarketData:
    market = MarketData.__new__(MarketData)
    market.cache_dir = tmp_path
    market.exchange = exchange
    return market


def _cache_path(market: MarketData) -> Path:
    key = market._cache_key("ohlcv", "BTC/USD", "1h", 0, 100000)
    return market._cache_path(key)


def test_late_listed_asset_survives_more_than_24_empty_pages(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("atlas.data.market.time.sleep", lambda _: None)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def handler(_symbol, _timeframe, _since, _limit, call_number):
        if call_number <= 25:
            return []
        if call_number == 26:
            return [_row(now_ms - _HOUR_MS)]
        return []

    exchange = _FakeExchange(handler)
    market = _market(tmp_path, exchange)

    df = market.fetch_ohlcv("BTC/USDT", "1h")

    assert len(exchange.calls) == 27
    assert len(df) == 1


def test_stale_main_cache_fetches_and_merges_tail(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("atlas.data.market.time.sleep", lambda _: None)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    old_ms = now_ms - int(timedelta(days=3).total_seconds() * 1000)

    def handler(_symbol, _timeframe, _since, _limit, call_number):
        if call_number == 1:
            return [
                _row(ts, close=2.0)
                for ts in range(old_ms + _HOUR_MS, now_ms, _HOUR_MS)
            ]
        return []

    exchange = _FakeExchange(handler)
    market = _market(tmp_path, exchange)
    cached = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]},
        index=pd.to_datetime([old_ms], unit="ms", utc=True),
    )
    cached.index.name = "timestamp"
    cached.to_csv(_cache_path(market))

    df = market.fetch_ohlcv("BTC/USDT", "1h")

    assert exchange.calls[0] == old_ms + _HOUR_MS
    assert df.iloc[0]["close"] == 1.0
    assert (df.iloc[1:]["close"] == 2.0).all()
    persisted = pd.read_csv(_cache_path(market))
    assert len(persisted) == len(df)
    assert df.attrs["atlas_requested_symbol"] == "BTC/USDT"
    assert df.attrs["atlas_exchange_symbol"] == "BTC/USD"
    assert df.attrs["atlas_quote_alias"] is True


def test_fresh_main_cache_avoids_exchange_call(tmp_path: Path) -> None:
    now = datetime.now(timezone.utc)
    exchange = _FakeExchange(lambda *_: (_ for _ in ()).throw(AssertionError("network called")))
    market = _market(tmp_path, exchange)
    cached = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]},
        index=pd.DatetimeIndex([now - timedelta(hours=1)], name="timestamp"),
    )
    cached.to_csv(_cache_path(market))

    df = market.fetch_ohlcv("BTC/USDT", "1h")

    assert len(df) == 1
    assert exchange.calls == []


def test_failed_stale_refresh_preserves_valid_cache(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("atlas.data.market.time.sleep", lambda _: None)
    old = datetime.now(timezone.utc) - timedelta(days=3)
    exchange = _FakeExchange(lambda *_: (_ for _ in ()).throw(RuntimeError("exchange down")))
    market = _market(tmp_path, exchange)
    cached = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [7.0], "volume": [1.0]},
        index=pd.DatetimeIndex([old], name="timestamp"),
    )
    cached.to_csv(_cache_path(market))

    with pytest.raises(RuntimeError, match="incomplete OHLCV refresh"):
        market.fetch_ohlcv("BTC/USDT", "1h")

    assert list(pd.read_csv(_cache_path(market))["close"]) == [7.0]


def test_partial_initial_fetch_is_rejected_and_not_cached(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("atlas.data.market.time.sleep", lambda _: None)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def handler(_symbol, _timeframe, _since, _limit, call_number):
        if call_number == 1:
            # A batch ending far from the present is not a complete history.
            return [_row(now_ms - int(timedelta(days=30).total_seconds() * 1000))]
        raise RuntimeError("exchange failed mid-pagination")

    market = _market(tmp_path, _FakeExchange(handler))

    df = market.fetch_ohlcv("BTC/USDT", "1h")

    assert df.empty
    assert not _cache_path(market).exists()


def test_empty_page_after_data_far_from_present_is_not_skipped(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("atlas.data.market.time.sleep", lambda _: None)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def handler(_symbol, _timeframe, _since, _limit, call_number):
        if call_number == 1:
            return [_row(now_ms - int(timedelta(days=30).total_seconds() * 1000))]
        return []

    market = _market(tmp_path, _FakeExchange(handler))

    df = market.fetch_ohlcv("BTC/USDT", "1h")

    assert df.empty
    assert not _cache_path(market).exists()


def test_hidden_interval_gap_is_rejected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("atlas.data.market.time.sleep", lambda _: None)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def handler(_symbol, _timeframe, _since, _limit, call_number):
        if call_number == 1:
            return [_row(now_ms - (3 * _HOUR_MS)), _row(now_ms - _HOUR_MS)]
        return []

    market = _market(tmp_path, _FakeExchange(handler))

    df = market.fetch_ohlcv("BTC/USDT", "1h")

    assert df.empty
    assert not _cache_path(market).exists()


def test_explicit_since_cache_refreshes_by_default(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("atlas.data.market.time.sleep", lambda _: None)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    old_ms = now_ms - int(timedelta(days=3).total_seconds() * 1000)
    since = datetime.fromtimestamp(old_ms / 1000, timezone.utc).isoformat()
    exchange = _FakeExchange(
        lambda *_args: [_row(now_ms - _HOUR_MS)] if len(exchange.calls) == 1 else []
    )
    market = _market(tmp_path, exchange)
    key = market._cache_key("ohlcv", "BTC/USD", "1h", old_ms, 100000)
    path = market._cache_path(key)
    cached = pd.DataFrame(
        {"open": [1.0], "high": [1.0], "low": [1.0], "close": [1.0], "volume": [1.0]},
        index=pd.to_datetime([old_ms], unit="ms", utc=True),
    )
    cached.index.name = "timestamp"
    cached.to_csv(path)

    with pytest.raises(RuntimeError, match="non-contiguous OHLCV refresh"):
        market.fetch_ohlcv("BTC/USDT", "1h", since=since)

    assert len(exchange.calls) == 2
    # The 3-day hole is rejected and the last known-good cache stays on disk.
    assert list(pd.read_csv(path)["close"]) == [1.0]


def test_invalid_cache_is_replaced_only_after_complete_fetch(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr("atlas.data.market.time.sleep", lambda _: None)
    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)

    def handler(_symbol, _timeframe, _since, _limit, call_number):
        if call_number == 1:
            return [_row(now_ms - _HOUR_MS)]
        return []

    market = _market(tmp_path, _FakeExchange(handler))
    _cache_path(market).write_text("timestamp,close\ninvalid,1\n")

    df = market.fetch_ohlcv("BTC/USDT", "1h")

    assert len(df) == 1
    assert set(pd.read_csv(_cache_path(market)).columns) == {
        "timestamp", "open", "high", "low", "close", "volume",
    }
