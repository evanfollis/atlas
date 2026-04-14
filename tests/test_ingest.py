"""Tests for findings → evidence ingest pipeline."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from atlas.research.ingest import (
    claim_hash, due_revalidations, ingest_finding, mark_revalidated, parse_finding,
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
