"""Centralized config loader. Single import point for secrets and paths.

Auto-loads `<repo-root>/.env` on import (only if present; silent otherwise).
Scripts and modules should call the helpers here rather than touching
`os.environ` directly — this gives one place to enforce validation and
error messages, and closes the "I forgot the .env was there" failure mode.
"""
from __future__ import annotations

import os
from pathlib import Path


def _repo_root() -> Path:
    # Walk upward from this file; the repo root is the directory with pyproject.toml.
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "pyproject.toml").exists():
            return parent
    return Path.cwd()


REPO_ROOT = _repo_root()
ENV_PATH = REPO_ROOT / ".env"


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        # Don't override explicit environment; .env is the fallback.
        os.environ.setdefault(k, v)


_load_env_file(ENV_PATH)


def require_env(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise RuntimeError(
            f"{name} not set. Add it to {ENV_PATH} or export in the shell."
        )
    return v


def dune_key() -> str:
    return require_env("DUNE_API_KEY")
