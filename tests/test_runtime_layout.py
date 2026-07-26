from pathlib import Path

from atlas.runner import AutonomousRunner
from atlas.runtime_paths import resolve_runtime_paths


def test_runtime_paths_preserve_legacy_layout(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ATLAS_RUNTIME_ROOT", raising=False)

    paths = resolve_runtime_paths(tmp_path)

    assert paths.state == tmp_path / ".atlas"
    assert paths.sessions == tmp_path / "sessions"
    assert paths.reports == tmp_path / "reports"
    assert paths.cache == tmp_path / "data"
    assert paths.graph == tmp_path / "graph"
    assert paths.predictions == tmp_path / "predictions.jsonl"
    assert paths.methodology == tmp_path / "methodology.jsonl"
    assert paths.revalidation_queue == tmp_path / "pending_revalidation.jsonl"


def test_runtime_root_externalizes_only_mutable_state(tmp_path: Path) -> None:
    repository = tmp_path / "checkout"
    runtime = tmp_path / "runtime"
    repository.mkdir()

    paths = resolve_runtime_paths(repository, runtime)

    assert paths.state == runtime / "state"
    assert paths.sessions == runtime / "sessions"
    assert paths.reports == runtime / "runs"
    assert paths.cache == runtime / "cache"
    assert paths.predictions == runtime / "state" / "predictions.jsonl"
    assert paths.methodology == runtime / "state" / "methodology.jsonl"
    assert paths.revalidation_queue == runtime / "state" / "pending_revalidation.jsonl"
    assert paths.graph == repository / "graph"


def test_runner_uses_explicit_runtime_root(tmp_path: Path) -> None:
    repository = tmp_path / "checkout"
    runtime = tmp_path / "runtime"
    repository.mkdir()

    runner = AutonomousRunner(repository, runtime_root=runtime)

    assert runner.state.base_dir == runtime / "state"
    assert runner.events.base_dir == runtime / "sessions"
    assert runner.market.cache_dir == runtime / "cache"
    assert runner.predictions.path == runtime / "state" / "predictions.jsonl"
    assert runner.graph_store.path == repository / "graph"
