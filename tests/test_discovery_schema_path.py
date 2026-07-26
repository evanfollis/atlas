from pathlib import Path

from atlas.adapters.discovery.migrate import default_schema_dir


def test_discovery_schema_path_keeps_compatibility_default(monkeypatch) -> None:
    monkeypatch.delenv("ATLAS_CANON_SCHEMA_DIR", raising=False)

    assert default_schema_dir() == Path(
        "/opt/workspace/projects/context-repository/"
        "spec/discovery-framework/schemas"
    )


def test_discovery_schema_path_accepts_environment_override(
    monkeypatch, tmp_path: Path
) -> None:
    schema_dir = tmp_path / "schemas"
    monkeypatch.setenv("ATLAS_CANON_SCHEMA_DIR", str(schema_dir))

    assert default_schema_dir() == schema_dir
