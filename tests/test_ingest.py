"""Tests for findings → evidence ingest pipeline."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from atlas.research.ingest import (
    _block_content_hash, _evidence_id, claim_hash, due_revalidations,
    ingest_finding, mark_revalidated, parse_finding,
)


FINDING_TEMPLATE = """<!-- atlas-finding
claim: "Test claim: X predicts Y at horizon H"
experiment_id: test_exp_{suffix}
spec_hash: test-spec-v1{suffix}
data_range: "2025-01-01 to 2025-06-01"
evidence_class: out_of_sample_test
quality: moderate
direction: supports
summary: "OOS t=-2.10"
stats:
  n_oos: 200
  t_stat: -2.10
generation_method: test_method
{extra}
-->

# Test finding
"""


def _write(path: Path, suffix: str = "", extra: str = "") -> Path:
    path.write_text(FINDING_TEMPLATE.format(suffix=suffix, extra=extra))
    return path


def test_parse_finding_requires_fields(tmp_path):
    p = tmp_path / "bad.md"
    p.write_text("<!-- atlas-finding\nclaim: x\n-->")
    with pytest.raises(ValueError, match="missing required"):
        parse_finding(p)


def test_parse_finding_raises_without_block(tmp_path):
    p = tmp_path / "no_block.md"
    p.write_text("# just a markdown file")
    with pytest.raises(ValueError, match="No <!-- atlas-finding"):
        parse_finding(p)


def test_ingest_creates_all_three_records(tmp_path):
    finding = _write(tmp_path / "f.md")
    state = tmp_path / "state"
    method_log = tmp_path / "methodology.jsonl"
    queue = tmp_path / "queue.jsonl"
    ids = ingest_finding(finding, state, method_log, queue)

    assert (state / "hypotheses" / f"{ids['hypothesis_id']}.json").exists()
    assert (state / "experiments" / f"{ids['experiment_id']}.json").exists()
    assert (state / "evidence" / f"{ids['evidence_id']}.json").exists()
    assert method_log.exists()


def test_ingest_is_idempotent_on_hypothesis(tmp_path):
    f1 = _write(tmp_path / "f1.md", suffix="_a")
    f2 = _write(tmp_path / "f2.md", suffix="_b")
    state = tmp_path / "state"
    ml = tmp_path / "m.jsonl"
    q = tmp_path / "q.jsonl"

    ids1 = ingest_finding(f1, state, ml, q)
    ids2 = ingest_finding(f2, state, ml, q)
    # Same claim → same hypothesis id; different experiment ids.
    assert ids1["hypothesis_id"] == ids2["hypothesis_id"]
    assert ids1["experiment_id"] != ids2["experiment_id"]


def test_claim_hash_stable():
    h1 = claim_hash("X predicts Y")
    h2 = claim_hash("X predicts Y")
    h3 = claim_hash("X predicts Z")
    assert h1 == h2 and h1 != h3


def test_revalidation_queue(tmp_path, monkeypatch):
    finding = _write(tmp_path / "f.md",
                     extra="revalidate_after_days: 30\nscript: scripts/f.py")
    state = tmp_path / "s"
    ml = tmp_path / "m.jsonl"
    q = tmp_path / "q.jsonl"
    ids = ingest_finding(finding, state, ml, q)

    # Not due yet (30 days).
    assert due_revalidations(q) == []

    # Due in the future → still none.
    future = datetime.now(timezone.utc) + timedelta(days=31)
    assert len(due_revalidations(q, now=future)) == 1

    # After marking done, nothing due.
    mark_revalidated(q, ids["experiment_id"])
    assert due_revalidations(q, now=future) == []


def test_reingest_with_different_spec_hash_raises(tmp_path):
    finding = _write(tmp_path / "f.md", suffix="_x")
    state = tmp_path / "s"
    ml = tmp_path / "m.jsonl"
    q = tmp_path / "q.jsonl"
    ingest_finding(finding, state, ml, q)

    # Edit the spec_hash and re-ingest — must fail.
    finding.write_text(finding.read_text().replace("test-spec-v1_x", "test-spec-v2_x"))
    with pytest.raises(ValueError, match="different spec_hash"):
        ingest_finding(finding, state, ml, q)


# ── Finding 2: deterministic evidence ID ──────────────────────────────────────

def test_evidence_id_is_deterministic(tmp_path):
    """Same file ingested twice produces the same evidence ID."""
    f = _write(tmp_path / "f.md", suffix="_det")
    state = tmp_path / "s"
    ml = tmp_path / "m.jsonl"
    q = tmp_path / "q.jsonl"

    ids1 = ingest_finding(f, state, ml, q)
    # Second call hits the dedup path and returns the same ev_id.
    ids2 = ingest_finding(f, state, ml, q)
    assert ids1["evidence_id"] == ids2["evidence_id"]


def test_evidence_id_changes_when_block_edited(tmp_path):
    """Editing the finding block post-ingest produces a different evidence ID
    on re-ingest, surfacing the mutation as a distinct record."""
    f = _write(tmp_path / "f.md", suffix="_edit")
    state = tmp_path / "s"
    ml = tmp_path / "m.jsonl"
    q = tmp_path / "q.jsonl"

    ids1 = ingest_finding(f, state, ml, q)

    # Edit a field that doesn't touch spec_hash — simulates post-hoc summary tweak.
    original = f.read_text()
    f.write_text(original.replace('summary: "OOS t=-2.10"', 'summary: "OOS t=-2.10 (revised)"'))
    # New experiment_id required because block changed; use a different suffix.
    f.write_text(f.read_text().replace("experiment_id: test_exp__edit", "experiment_id: test_exp__edit_v2"))

    ids2 = ingest_finding(f, state, ml, q)
    assert ids1["evidence_id"] != ids2["evidence_id"]


def test_content_hash_stored_in_evidence(tmp_path):
    """Evidence record contains a non-empty source_hash field."""
    f = _write(tmp_path / "f.md", suffix="_ch")
    state = tmp_path / "s"
    ml = tmp_path / "m.jsonl"
    q = tmp_path / "q.jsonl"

    ids = ingest_finding(f, state, ml, q)

    import json as _json
    ev_path = state / "evidence" / f"{ids['evidence_id']}.json"
    ev_data = _json.loads(ev_path.read_text())
    assert ev_data.get("source_hash"), "source_hash must be set on evidence record"
    assert len(ev_data["source_hash"]) == 16


def test_block_content_hash_stored_in_experiment(tmp_path):
    """Experiment parameters contain block_content_hash at ingest time."""
    f = _write(tmp_path / "f.md", suffix="_bch")
    state = tmp_path / "s"
    ml = tmp_path / "m.jsonl"
    q = tmp_path / "q.jsonl"

    ids = ingest_finding(f, state, ml, q)

    import json as _json
    exp_path = state / "experiments" / f"{ids['experiment_id']}.json"
    exp_data = _json.loads(exp_path.read_text())
    assert exp_data["parameters"].get("block_content_hash"), \
        "block_content_hash must be in experiment parameters"


# ── Finding 2: concurrency — two workers ingesting the same file ───────────────

def test_concurrent_ingest_no_duplicate_evidence(tmp_path):
    """Two threads ingesting the same finding file produce exactly one evidence record."""
    f = _write(tmp_path / "f.md", suffix="_conc")
    state = tmp_path / "s"
    ml = tmp_path / "m.jsonl"
    q = tmp_path / "q.jsonl"

    results: list[dict] = []
    errors: list[Exception] = []

    def worker():
        try:
            r = ingest_finding(f, state, ml, q)
            results.append(r)
        except Exception as e:
            errors.append(e)

    t1 = threading.Thread(target=worker)
    t2 = threading.Thread(target=worker)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"Workers raised: {errors}"
    # Both workers must return the same evidence ID.
    assert results[0]["evidence_id"] == results[1]["evidence_id"]
    # Exactly one evidence file on disk.
    ev_files = list((state / "evidence").glob("*.json"))
    assert len(ev_files) == 1, f"Expected 1 evidence file, found {len(ev_files)}"


# ── Finding 3: revalidation queue dedup-on-read ───────────────────────────────

def test_revalidation_dedup_on_read(tmp_path):
    """Duplicate queue entries for the same experiment_id are collapsed to one
    by due_revalidations(), as if concurrent writers both appended."""
    finding = _write(tmp_path / "f.md",
                     extra="revalidate_after_days: 1\nscript: scripts/f.py")
    state = tmp_path / "s"
    ml = tmp_path / "m.jsonl"
    q = tmp_path / "q.jsonl"

    # Manually append two identical entries (simulating concurrent writers).
    ingest_finding(finding, state, ml, q)
    ingest_finding(finding, state, ml, q)  # hits evidence dedup; but re-appends queue

    future = datetime.now(timezone.utc) + timedelta(days=2)
    due = due_revalidations(q, now=future)
    assert len(due) == 1, f"Expected 1 due entry after dedup, got {len(due)}"
