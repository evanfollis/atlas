"""Runtime paths are env-injected (ADR-0050 §5) with behavior-preserving
defaults — the exact pre-existing absolute locations when nothing is set."""
import importlib
from pathlib import Path

import atlas.runner as runner_mod


def test_defaults_preserve_prior_absolute_locations() -> None:
    # With no override, the paths are byte-identical to the pre-migration
    # hardcoded literals, so an unconfigured deploy behaves exactly as before.
    assert runner_mod._DEFAULT_TELEMETRY_PATH == \
        "/opt/workspace/runtime/.telemetry/events.jsonl"
    assert runner_mod._DEFAULT_HANDOFF_DIR == \
        "/opt/workspace/supervisor/handoffs/INBOX"
    assert runner_mod.AutonomousRunner.TELEMETRY_PATH == \
        Path(runner_mod._DEFAULT_TELEMETRY_PATH)
    assert runner_mod.AutonomousRunner.SUPERVISOR_HANDOFF_DIR == \
        Path(runner_mod._DEFAULT_HANDOFF_DIR)


def test_workspace_root_env_injects_both_paths(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_WORKSPACE_ROOT", "/tmp/atlas-ws")
    m = importlib.reload(runner_mod)
    try:
        assert m.AutonomousRunner.TELEMETRY_PATH == \
            Path("/tmp/atlas-ws/runtime/.telemetry/events.jsonl")
        assert m.AutonomousRunner.SUPERVISOR_HANDOFF_DIR == \
            Path("/tmp/atlas-ws/supervisor/handoffs/INBOX")
    finally:
        monkeypatch.delenv("ATLAS_WORKSPACE_ROOT", raising=False)
        importlib.reload(m)  # restore defaults for the rest of the session


def test_explicit_path_env_overrides_default(monkeypatch) -> None:
    monkeypatch.setenv("ATLAS_TELEMETRY_PATH", "/tmp/custom/events.jsonl")
    m = importlib.reload(runner_mod)
    try:
        assert m.AutonomousRunner.TELEMETRY_PATH == Path("/tmp/custom/events.jsonl")
    finally:
        monkeypatch.delenv("ATLAS_TELEMETRY_PATH", raising=False)
        importlib.reload(m)
