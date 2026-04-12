"""Tests for StateStore immutability enforcement."""

import pytest
from pathlib import Path

from atlas.storage.state_store import StateStore


@pytest.fixture
def store(tmp_path: Path) -> StateStore:
    return StateStore(tmp_path)


def test_save_and_load(store: StateStore) -> None:
    store.save("hypotheses", "h1", {"claim": "X causes Y", "status": "formulated"})
    loaded = store.load("hypotheses", "h1")
    assert loaded is not None
    assert loaded["claim"] == "X causes Y"


def test_load_missing_returns_none(store: StateStore) -> None:
    assert store.load("hypotheses", "nonexistent") is None


def test_list_all_empty(store: StateStore) -> None:
    assert store.list_all("hypotheses") == []


def test_list_all(store: StateStore) -> None:
    store.save("hypotheses", "h1", {"claim": "A"})
    store.save("hypotheses", "h2", {"claim": "B"})
    objs = store.list_all("hypotheses")
    assert len(objs) == 2


def test_immutable_field_blocks_mutation(store: StateStore) -> None:
    store.save("hypotheses", "h1", {
        "claim": "X causes Y",
        "rationale": "because",
        "significance_threshold": 0.05,
    })
    with pytest.raises(ValueError, match="Cannot modify pre-registered field 'claim'"):
        store.save("hypotheses", "h1", {
            "claim": "CHANGED",
            "rationale": "because",
            "significance_threshold": 0.05,
        })


def test_immutable_threshold_blocks_mutation(store: StateStore) -> None:
    store.save("hypotheses", "h1", {
        "claim": "X causes Y",
        "significance_threshold": 0.05,
    })
    with pytest.raises(ValueError, match="significance_threshold"):
        store.save("hypotheses", "h1", {
            "claim": "X causes Y",
            "significance_threshold": 0.025,
        })


def test_mutable_field_allows_update(store: StateStore) -> None:
    store.save("hypotheses", "h1", {"claim": "X", "status": "formulated"})
    store.save("hypotheses", "h1", {"claim": "X", "status": "promoted"})
    loaded = store.load("hypotheses", "h1")
    assert loaded["status"] == "promoted"


def test_experiment_immutability(store: StateStore) -> None:
    store.save("experiments", "e1", {
        "hypothesis_id": "h1",
        "description": "test backtest",
        "method": "backtest",
        "parameters": {"lookback": 20},
    })
    with pytest.raises(ValueError, match="method"):
        store.save("experiments", "e1", {
            "hypothesis_id": "h1",
            "description": "test backtest",
            "method": "observation",
            "parameters": {"lookback": 20},
        })


def test_immutable_field_cannot_be_omitted(store: StateStore) -> None:
    store.save("hypotheses", "h1", {
        "claim": "X causes Y",
        "significance_threshold": 0.05,
        "status": "formulated",
    })
    with pytest.raises(ValueError, match="Cannot omit pre-registered field 'claim'"):
        store.save("hypotheses", "h1", {
            "significance_threshold": 0.05,
            "status": "promoted",
        })


def test_non_guarded_kind_allows_any_mutation(store: StateStore) -> None:
    store.save("cycles", "c1", {"status": "active"})
    store.save("cycles", "c1", {"status": "closed"})
    assert store.load("cycles", "c1")["status"] == "closed"
