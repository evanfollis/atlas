"""Runtime path contract for Atlas.

Atlas historically stored mutable state beside the checkout.  That remains the
default for local development and backwards compatibility.  Production may set
``ATLAS_RUNTIME_ROOT`` to place mutable state under the workspace runtime tree
without moving the tracked causal graph or changing the repository root.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    """Resolved authoritative and mutable paths for one Atlas process."""

    repository: Path
    state: Path
    sessions: Path
    reports: Path
    cache: Path
    graph: Path
    predictions: Path
    methodology: Path
    revalidation_queue: Path


def resolve_runtime_paths(
    repository: Path,
    runtime_root: Path | None = None,
) -> RuntimePaths:
    """Resolve paths, preserving the legacy checkout layout when unset.

    ``runtime_root`` takes precedence over ``ATLAS_RUNTIME_ROOT`` so tests and
    callers can be explicit.  The graph intentionally remains in the checkout:
    it is a tracked, runner-owned scientific record with a separate migration
    decision and must not be silently reclassified as ordinary runtime state.
    """

    repository = repository.resolve()
    configured = runtime_root
    if configured is None:
        raw = os.environ.get("ATLAS_RUNTIME_ROOT")
        configured = Path(raw) if raw else None

    if configured is None:
        return RuntimePaths(
            repository=repository,
            state=repository / ".atlas",
            sessions=repository / "sessions",
            reports=repository / "reports",
            cache=repository / "data",
            graph=repository / "graph",
            predictions=repository / "predictions.jsonl",
            methodology=repository / "methodology.jsonl",
            revalidation_queue=repository / "pending_revalidation.jsonl",
        )

    root = configured.resolve()
    state = root / "state"
    return RuntimePaths(
        repository=repository,
        state=state,
        sessions=root / "sessions",
        reports=root / "runs",
        cache=root / "cache",
        graph=repository / "graph",
        predictions=state / "predictions.jsonl",
        methodology=state / "methodology.jsonl",
        revalidation_queue=state / "pending_revalidation.jsonl",
    )
