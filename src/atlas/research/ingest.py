"""Finding → Evidence pipeline.

Parses a structured `<!-- atlas-finding ... -->` HTML comment at the top of
a finding markdown file and emits:

  - a Hypothesis record keyed by claim hash (idempotent)
  - an Experiment record (pre-registered spec, immutable on re-ingest)
  - an Evidence record linking the two
  - an append to methodology.jsonl (for meta-learning)
  - an optional entry in the revalidation queue

This is the bridge between the markdown-based research writeups (how the
human works) and the state store (what the promotion gate sees).

Finding-block schema (YAML-ish key: value, fenced by HTML comments):

    <!-- atlas-finding
    claim: "BitMEX+Kraken mean funding predicts BTC 24h reversal"
    experiment_id: zmf_delta_2026_04_13
    spec_hash: <SHA of pre-reg text, see spec_hash.compute()>
    data_range: "2025-04-09 to 2026-04-12"
    evidence_class: out_of_sample_test
    quality: moderate
    direction: supports
    summary: "OOS t=-2.03 on level, n=331"
    stats:
      n_oos: 331
      t_stat: -2.03
      beta: -0.00256
    generation_method: residualized_interaction_narrow_retest
    revalidate_after_days: 90  # optional; when to re-run against disjoint data
    script: scripts/zmf_delta.py
    -->

Everything after the closing `-->` is the human narrative; the system
only cares about this block.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml

from atlas.models.evidence import Evidence, EvidenceClass, EvidenceDirection, EvidenceQuality
from atlas.models.experiment import Experiment, ExperimentStatus
from atlas.models.hypothesis import Hypothesis, HypothesisStatus
from atlas.storage.state_store import StateStore
from atlas.utils import claim_hash


log = logging.getLogger("atlas.ingest")

FINDING_BLOCK = re.compile(r"<!--\s*atlas-finding\s*(.*?)-->", re.DOTALL)


def parse_finding(md_path: Path) -> dict[str, Any]:
    """Extract the atlas-finding block from a markdown file."""
    text = md_path.read_text()
    m = FINDING_BLOCK.search(text)
    if not m:
        raise ValueError(f"No <!-- atlas-finding ... --> block in {md_path}")
    data = yaml.safe_load(m.group(1))
    required = {"claim", "experiment_id", "spec_hash", "evidence_class",
                "quality", "direction", "summary", "generation_method"}
    missing = required - set(data)
    if missing:
        raise ValueError(f"{md_path}: missing required fields: {sorted(missing)}")
    return data


def ingest_finding(
    md_path: Path,
    state_dir: Path,
    methodology_log: Path,
    revalidation_queue: Path,
) -> dict[str, str]:
    """Parse finding, write Hypothesis/Experiment/Evidence, append methodology,
    enqueue revalidation if requested. Idempotent on re-run."""
    block = parse_finding(md_path)
    store = StateStore(state_dir)

    hyp_id = claim_hash(block["claim"])
    existing_hyp = store.load("hypotheses", hyp_id)
    if existing_hyp is None:
        hyp = Hypothesis(
            id=hyp_id,
            claim=block["claim"],
            rationale=block.get("rationale", block["claim"]),
            falsification_criteria=block.get(
                "falsification_criteria",
                "OOS |t| < threshold or sign-flip IS→OOS"),
            significance_threshold=float(block.get("significance_threshold", 0.05)),
            status=HypothesisStatus.TESTING,
        )
        store.save("hypotheses", hyp_id, json.loads(hyp.model_dump_json()))
    # else: immutability guards in StateStore prevent accidental edits.

    exp_id = block["experiment_id"]
    existing_exp = store.load("experiments", exp_id)
    if existing_exp is None:
        exp = Experiment(
            id=exp_id,
            hypothesis_id=hyp_id,
            description=block["summary"],
            method=block.get("generation_method", "script"),
            success_criteria=block.get("success_criteria", "pre-registered"),
            failure_criteria=block.get("failure_criteria", "pre-registered"),
            parameters={"spec_hash": block["spec_hash"],
                        "script": block.get("script", ""),
                        "data_range": block.get("data_range", "")},
            status=ExperimentStatus.COMPLETED,
        )
        store.save("experiments", exp_id, json.loads(exp.model_dump_json()))
    else:
        if existing_exp.get("parameters", {}).get("spec_hash") != block["spec_hash"]:
            raise ValueError(
                f"Experiment {exp_id} already exists with a different spec_hash. "
                f"If the pre-reg text changed, use a new experiment_id."
            )

    existing_ev = [
        e for e in store.list_all("evidence")
        if e.get("hypothesis_id") == hyp_id and e.get("experiment_id") == exp_id
    ]
    if existing_ev:
        log.warning(
            "Evidence already recorded for (hypothesis=%s, experiment=%s) — skipping",
            hyp_id, exp_id,
        )
        return {"hypothesis_id": hyp_id, "experiment_id": exp_id, "evidence_id": existing_ev[0]["id"]}

    ev = Evidence(
        experiment_id=exp_id,
        hypothesis_id=hyp_id,
        evidence_class=EvidenceClass(block["evidence_class"]),
        quality=EvidenceQuality(block["quality"]),
        direction=EvidenceDirection(block["direction"]),
        summary=block["summary"],
        statistics=block.get("stats", {}),
        data_range=block.get("data_range", ""),
    )
    store.save("evidence", ev.id, json.loads(ev.model_dump_json()))

    # Methodology log — append-only, one row per ingest.
    methodology_log.parent.mkdir(parents=True, exist_ok=True)
    with methodology_log.open("a") as f:
        f.write(json.dumps({
            "ts": datetime.now(timezone.utc).isoformat(),
            "hypothesis_id": hyp_id,
            "experiment_id": exp_id,
            "evidence_id": ev.id,
            "generation_method": block["generation_method"],
            "evidence_class": block["evidence_class"],
            "quality": block["quality"],
            "direction": block["direction"],
            "finding_path": str(md_path),
        }) + "\n")

    # Revalidation queue (optional).
    if "revalidate_after_days" in block and block.get("script"):
        already_queued = False
        if revalidation_queue.exists():
            for line in revalidation_queue.read_text().splitlines():
                if line.strip() and json.loads(line).get("experiment_id") == exp_id:
                    already_queued = True
                    break
        if not already_queued:
            due = datetime.now(timezone.utc) + timedelta(days=int(block["revalidate_after_days"]))
            revalidation_queue.parent.mkdir(parents=True, exist_ok=True)
            with revalidation_queue.open("a") as f:
                f.write(json.dumps({
                    "finding_path": str(md_path),
                    "script": block["script"],
                    "experiment_id": exp_id,
                    "hypothesis_id": hyp_id,
                    "spec_hash": block["spec_hash"],
                    "due_at": due.isoformat(),
                    "enqueued_at": datetime.now(timezone.utc).isoformat(),
                }) + "\n")

    return {"hypothesis_id": hyp_id, "experiment_id": exp_id, "evidence_id": ev.id}


def due_revalidations(queue_path: Path, now: datetime | None = None) -> list[dict]:
    """Return queue entries whose due_at has passed and which have not yet
    been marked done in a sibling `<queue>.done` file."""
    if not queue_path.exists():
        return []
    now = now or datetime.now(timezone.utc)
    done_path = queue_path.with_suffix(queue_path.suffix + ".done")
    done_keys: set[str] = set()
    if done_path.exists():
        for line in done_path.read_text().splitlines():
            if line.strip():
                done_keys.add(json.loads(line)["experiment_id"])
    out = []
    for line in queue_path.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["experiment_id"] in done_keys:
            continue
        due = datetime.fromisoformat(r["due_at"])
        if due <= now:
            out.append(r)
    return out


def mark_revalidated(queue_path: Path, experiment_id: str) -> None:
    done_path = queue_path.with_suffix(queue_path.suffix + ".done")
    with done_path.open("a") as f:
        f.write(json.dumps({
            "experiment_id": experiment_id,
            "done_at": datetime.now(timezone.utc).isoformat(),
        }) + "\n")
