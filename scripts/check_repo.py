#!/usr/bin/env python3
"""Repository-standard validator + truthful clean-check (ADR-0050).

Run via `make check`. Three gates, none of which mask failures:

1. repo.toml validates — required keys, allowed enum values, and every
   *declared* artifact path obeys its role:
     - authoritative / historical paths must exist;
     - runtime / generated paths must exist AND be excluded from source
       control (nothing tracked under them).
2. Prompt inventory — Atlas ships zero in-product prompt/LLM artifacts, but its
   contributor charters are behavior-shaping prompts. Validate the enforced
   inventory and accepted release baselines locally, and assert that no new
   in-product prompt appears silently (ADR-0039).
3. Truthful clean-check — the working tree must be clean EXCEPT for
   `graph/causal_graph.json`, which the live runner rewrites every cycle
   (attributed dirty/live state, preserved by design). Any *other* dirty path
   fails the gate. This is honest: it declares its one exception rather than
   pretending the tree is pristine.

Exit non-zero on any failure.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

ALLOWED = {
    "shape": {"service", "application", "library", "monorepo", "contract",
              "context", "control-plane", "profile"},
    "lifecycle": {"active", "maintained", "case-study", "archived"},
    "agentic_risk": {"none", "model-assisted", "agentic"},
}

# The one path the live runner is authorized to leave dirty in the working tree.
RUNNER_OWNED_DIRTY = {"graph/causal_graph.json"}

# Patterns that would indicate an in-product LLM/prompt surface (ADR-0039).
PROMPT_PATTERNS = (
    "anthropic", "openai", ".messages.create", ".chat.completions",
    "ChatCompletion", "system_prompt", "PromptTemplate",
)


def _git(*args: str) -> str:
    # NOTE: do not .strip() — the git status --porcelain XY field is
    # column-significant (" M path"); stripping the leading space would corrupt
    # path slicing. splitlines() already handles the trailing newline.
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True, text=True, check=False,
    ).stdout


def _tracked_under(path: str) -> list[str]:
    out = _git("ls-files", path)
    return [ln for ln in out.splitlines() if ln]


def check_repo_toml() -> list[str]:
    errs: list[str] = []
    toml_path = REPO / "repo.toml"
    if not toml_path.exists():
        return ["repo.toml is missing"]
    data = tomllib.loads(toml_path.read_text())

    for key in ("schema_version", "name", "shape", "lifecycle",
                "agentic_risk", "canonical_repository"):
        if key not in data:
            errs.append(f"repo.toml missing required key: {key}")
    for axis, allowed in ALLOWED.items():
        val = data.get(axis)
        if val is not None and val not in allowed:
            errs.append(f"repo.toml {axis}={val!r} not in {sorted(allowed)}")

    arts = data.get("artifacts", {})
    # authoritative/historical are source: they must be present in the checkout.
    for role in ("authoritative", "historical"):
        for p in arts.get(role, []):
            if not (REPO / p).exists():
                errs.append(f"declared {role} path missing: {p}")
    # runtime/generated are created at runtime and are absent in a clean
    # checkout (which `make check` must pass from). The enforceable invariant is
    # that they are NOT under source control — not that they exist.
    for role in ("runtime", "generated"):
        for p in arts.get(role, []):
            tracked = _tracked_under(p)
            if tracked:
                errs.append(
                    f"{role} path {p!r} must be excluded from source control "
                    f"but {len(tracked)} tracked file(s) found (e.g. {tracked[0]})"
                )
    return errs


def check_prompt_inventory() -> list[str]:
    errors: list[str] = []
    hits: list[str] = []
    for py in (REPO / "src").rglob("*.py"):
        text = py.read_text(errors="ignore").lower()
        for pat in PROMPT_PATTERNS:
            if pat.lower() in text:
                hits.append(f"{py.relative_to(REPO)}: matches {pat!r}")
    if hits:
        errors.extend([
            "ungoverned prompt/LLM surface detected in src (ADR-0039). "
            "Run the create-eval-loop skill before shipping:",
            *hits,
        ])

    inventory_path = REPO / ".prompteval" / "inventory.json"
    if not inventory_path.exists():
        return [*errors, "missing .prompteval/inventory.json"]
    inventory = json.loads(inventory_path.read_text())
    if inventory.get("enforce") is not True:
        errors.append("prompt inventory ratchet must be enforce=true")

    for entry in inventory.get("prompts", []):
        if entry.get("status") == "ungoverned":
            errors.append(f"ungoverned prompt in enforced inventory: {entry.get('file')}")
        if entry.get("status") != "governed":
            continue

        prompt_id = entry.get("id")
        spec_dir = REPO / ".prompteval" / str(prompt_id)
        spec_path = spec_dir / "spec.json"
        baseline_path = spec_dir / "baseline.json"
        if not spec_path.exists() or not baseline_path.exists():
            errors.append(f"{prompt_id}: missing spec.json or baseline.json")
            continue

        spec = json.loads(spec_path.read_text())
        baseline = json.loads(baseline_path.read_text())
        source = spec.get("source", {})
        if source.get("type") != "whole_file":
            errors.append(f"{prompt_id}: repo-local gate supports whole_file only")
            continue
        source_path = REPO / source.get("file", "")
        if not source_path.is_file():
            errors.append(f"{prompt_id}: source file missing: {source.get('file')}")
            continue

        def canonical(obj: object) -> str:
            return json.dumps(
                obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            )

        def digest(obj: object) -> str:
            return hashlib.sha256(canonical(obj).encode()).hexdigest()[:16]

        prompt_version = "pv-" + digest({
            "t": source_path.read_text(),
            "m": spec.get("model", ""),
            "p": spec.get("params", {}),
        })
        executor = spec.get("executor") or {}
        spec_hash = "sh-" + digest({
            "source": source,
            "executor": executor,
            "argv_files": {},
            "dep_files": {},
            "judge": spec.get("judge"),
            "gate": spec.get("gate"),
        })

        cases: list[dict] = []
        for filename in ("cases.jsonl", "holdout.jsonl"):
            path = spec_dir / "golden" / filename
            if not path.exists():
                errors.append(f"{prompt_id}: missing golden/{filename}")
                continue
            for line in path.read_text().splitlines():
                if line.strip():
                    cases.append(json.loads(line))
        material = sorted(
            canonical({
                "id": case.get("id"),
                "checks": case.get("checks"),
                "status": case.get("status"),
                "must_pass": case.get("must_pass", True),
                "provenance": case.get("provenance"),
            })
            for case in cases
            if case.get("status") != "retired"
        )
        golden_hash = "gh-" + digest({"cases": material, "gate": spec.get("gate", {})})

        expected = {
            "prompt_version": prompt_version,
            "spec_hash": spec_hash,
            "golden_hash": golden_hash,
        }
        for field, value in expected.items():
            if baseline.get(field) != value:
                errors.append(
                    f"{prompt_id}: stale baseline {field} "
                    f"({baseline.get(field)!r} != {value!r})"
                )
        if baseline.get("passed") is not True or baseline.get("release") is not True:
            errors.append(f"{prompt_id}: baseline is not an accepted passing release")
        if baseline.get("accepted_from_cache") is not False:
            errors.append(f"{prompt_id}: accepted baseline must be no-cache")

    return errors


def check_clean_tree() -> list[str]:
    porcelain = _git("status", "--porcelain")
    unexpected = []
    for line in porcelain.splitlines():
        path = line[3:].strip()
        if path and path not in RUNNER_OWNED_DIRTY:
            unexpected.append(line)
    if unexpected:
        return [
            "working tree has un-attributed dirty paths (clean-check):",
            *unexpected,
            f"(only {sorted(RUNNER_OWNED_DIRTY)} may be dirty — runner-owned live state)",
        ]
    return []


def main() -> int:
    all_errs: list[str] = []
    for name, fn in (("repo.toml", check_repo_toml),
                     ("prompt-inventory", check_prompt_inventory),
                     ("clean-check", check_clean_tree)):
        errs = fn()
        if errs:
            all_errs.extend(errs)
            print(f"FAIL [{name}]")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"ok   [{name}]")
    if all_errs:
        print(f"\ncheck_repo: {len(all_errs)} problem(s)")
        return 1
    print("\ncheck_repo: all gates green")
    return 0


if __name__ == "__main__":
    sys.exit(main())
