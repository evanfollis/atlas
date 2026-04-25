"""Regression tests for scripts/migrate_claim_hash.py two-phase-commit.

The claim-hash migration must be crash-safe: if the process dies between
Phase 5 (evidence re-link) and Phase D (old-file deletion), a re-run must
converge to the same end state as a clean run with no orphaned references.
"""

import importlib.util
import json
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_claim_hash.py"


def _load_script():
    """Load scripts/migrate_claim_hash.py as a module (it is not on sys.path)."""
    spec = importlib.util.spec_from_file_location("migrate_claim_hash", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["migrate_claim_hash"] = mod
    spec.loader.exec_module(mod)
    return mod


def _seed(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    hyp = tmp_path / ".atlas" / "hypotheses"
    exp = tmp_path / ".atlas" / "experiments"
    evi = tmp_path / ".atlas" / "evidence"
    for d in (hyp, exp, evi):
        d.mkdir(parents=True)

    # Old ID that will not match canonical form (trailing punctuation + upper case)
    old_id = "deadbeef00000000"
    claim_text = "BTC reverts post-funding.  "  # extra ws + trailing punct
    (hyp / f"{old_id}.json").write_text(json.dumps({
        "id": old_id,
        "claim": claim_text,
        "rationale": "r",
        "falsification_criteria": "f",
        "significance_threshold": 0.05,
        "status": "falsified",
    }))
    (exp / "exp-001.json").write_text(json.dumps({
        "id": "exp-001",
        "hypothesis_id": old_id,
        "parameters": {},
    }))
    (evi / "ev-001.json").write_text(json.dumps({
        "id": "ev-001",
        "hypothesis_id": old_id,
        "summary": "s",
    }))
    meta = tmp_path / ".atlas" / "schema_version.json"
    return hyp, exp, evi, meta


def test_clean_run_produces_no_orphans(tmp_path):
    mod = _load_script()
    hyp, exp, evi, meta = _seed(tmp_path)
    counts = mod.run_migration(hyp, exp, evi, meta, verbose=False)
    assert counts["hypotheses_migrated"] == 1
    assert counts["experiments_relinked"] == 1
    assert counts["evidence_relinked"] == 1
    assert counts["orphan_experiments"] == 0
    assert counts["orphan_evidence"] == 0

    # Old file is gone; new canonical-id file exists.
    remaining = list(hyp.glob("*.json"))
    assert len(remaining) == 1
    new_file = remaining[0]
    data = json.loads(new_file.read_text())
    assert data["id"] == new_file.stem  # id matches filename
    assert data["id"] != "deadbeef00000000"  # it was re-keyed


def test_crash_between_relink_and_delete_is_recoverable(monkeypatch, tmp_path):
    """Simulate a crash AFTER Phases 4–5 re-link completed but BEFORE
    Phase D deletes old files. The intermediate state must be safe: old and
    new hypothesis files coexist, experiment/evidence all point at the
    *new* id, and a re-run produces a clean final state with no orphans."""
    mod = _load_script()
    hyp, exp, evi, meta = _seed(tmp_path)

    # Monkey-patch Path.unlink for files in hyp_dir only — evidence/experiment
    # rewrites via write_text() still work. This simulates a crash after
    # the re-link is persisted but before the Phase D unlinks happen.
    original_unlink = Path.unlink
    hyp_abs = hyp.resolve()

    def skip_hyp_unlink(self, *args, **kwargs):
        if self.resolve().parent == hyp_abs:
            raise RuntimeError("simulated crash before Phase D completes")
        return original_unlink(self, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", skip_hyp_unlink)

    try:
        mod.run_migration(hyp, exp, evi, meta, verbose=False)
    except RuntimeError as exc:
        assert "simulated crash" in str(exc)
    else:
        raise AssertionError("expected simulated crash")

    # Verify intermediate state: both the old and the new hypothesis files
    # exist; the experiment and the evidence have been re-linked to the new id.
    hyp_files = sorted(p.stem for p in hyp.glob("*.json"))
    assert "deadbeef00000000" in hyp_files  # old file still present (Phase D didn't run)
    assert len(hyp_files) == 2               # new file was written in Phase 3W

    exp_data = json.loads((exp / "exp-001.json").read_text())
    evi_data = json.loads((evi / "ev-001.json").read_text())
    new_id = [f for f in hyp_files if f != "deadbeef00000000"][0]
    assert exp_data["hypothesis_id"] == new_id
    assert evi_data["hypothesis_id"] == new_id

    # Now restore normal unlink and re-run. A second pass must converge.
    monkeypatch.setattr(Path, "unlink", original_unlink)
    counts = mod.run_migration(hyp, exp, evi, meta, verbose=False)
    assert counts["orphan_experiments"] == 0
    assert counts["orphan_evidence"] == 0

    # Exactly one hypothesis file remains, matching the canonical id.
    final = list(hyp.glob("*.json"))
    assert len(final) == 1
    assert final[0].stem == new_id
    assert json.loads(final[0].read_text())["id"] == new_id


def test_idempotent_when_already_canonical(tmp_path):
    """Running migration twice must leave state unchanged on the second run."""
    mod = _load_script()
    hyp, exp, evi, meta = _seed(tmp_path)
    mod.run_migration(hyp, exp, evi, meta, verbose=False)
    snapshot = {p.name: p.read_text() for p in hyp.glob("*.json")}
    counts = mod.run_migration(hyp, exp, evi, meta, verbose=False)
    assert counts["hypotheses_migrated"] == 0
    assert {p.name: p.read_text() for p in hyp.glob("*.json")} == snapshot


def _seed_merge_collision(tmp_path: Path) -> tuple[Path, Path, Path, Path]:
    """Seed two hypotheses whose claims canonicalize to the same id but
    diverge on every other field. Without --allow-merge the migration must
    refuse to consolidate them."""
    hyp = tmp_path / ".atlas" / "hypotheses"
    exp = tmp_path / ".atlas" / "experiments"
    evi = tmp_path / ".atlas" / "evidence"
    for d in (hyp, exp, evi):
        d.mkdir(parents=True)

    common_canonical = "btc reverts post-funding"
    (hyp / "aaaa000000000001.json").write_text(json.dumps({
        "id": "aaaa000000000001",
        "claim": "BTC reverts post-funding.",
        "rationale": "rationale variant A",
        "falsification_criteria": "criteria A",
        "significance_threshold": 0.05,
        "status": "falsified",
        "tags": ["a"],
    }))
    (hyp / "bbbb000000000002.json").write_text(json.dumps({
        "id": "bbbb000000000002",
        "claim": "BTC reverts post-funding!",  # canonicalizes the same
        "rationale": "rationale variant B (would be lost)",
        "falsification_criteria": "criteria B (would be lost)",
        "significance_threshold": 0.01,           # diverges
        "status": "supported",                    # diverges
        "tags": ["b"],
    }))
    meta = tmp_path / ".atlas" / "schema_version.json"
    return hyp, exp, evi, meta


def test_merge_groups_refuse_without_allow_merge(tmp_path, capsys):
    """A merge group must abort the migration unless --allow-merge is set."""
    mod = _load_script()
    hyp, exp, evi, meta = _seed_merge_collision(tmp_path)

    try:
        mod.run_migration(hyp, exp, evi, meta, verbose=False)
    except SystemExit as exc:
        assert exc.code == 2
    else:
        raise AssertionError("expected SystemExit(2) when merges are present without --allow-merge")

    # Both hypothesis files are still on disk — nothing was consolidated.
    remaining = sorted(p.stem for p in hyp.glob("*.json"))
    assert remaining == ["aaaa000000000001", "bbbb000000000002"]

    err = capsys.readouterr().err
    assert "merge groups detected" in err
    assert "--allow-merge" in err
    assert "rationale" in err and "status" in err  # field-divergence audit


def test_merge_groups_proceed_with_allow_merge(tmp_path):
    """With --allow-merge the consolidation runs and the second record is
    dropped (claim_variants captures only the claim text, by design)."""
    mod = _load_script()
    hyp, exp, evi, meta = _seed_merge_collision(tmp_path)
    counts = mod.run_migration(
        hyp, exp, evi, meta, verbose=False, allow_merge=True,
    )
    assert counts["hypotheses_migrated"] == 2

    final = sorted(p.stem for p in hyp.glob("*.json"))
    assert len(final) == 1
    survivor = json.loads((hyp / f"{final[0]}.json").read_text())
    # claim_variants captures the second claim text; non-claim fields
    # default to the first sorted record's values (the documented loss).
    assert "claim_variants" in survivor
    assert survivor["rationale"] == "rationale variant A"
    assert survivor["significance_threshold"] == 0.05
