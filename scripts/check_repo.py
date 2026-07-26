#!/usr/bin/env python3
"""Repository-standard validator + truthful clean-check (ADR-0050).

Run via `make check`. Three gates, none of which mask failures:

1. repo.toml validates — required keys, allowed enum values, and every
   *declared* artifact path obeys its role:
     - authoritative / historical paths must exist;
     - runtime / generated paths must exist AND be excluded from source
       control (nothing tracked under them).
2. Prompt inventory — Atlas ships zero in-product prompt/LLM artifacts
   (prior prompteval scan = 0). Assert that remains true so a new ungoverned
   prompt surface can't land silently (ADR-0039). If one ever appears, this
   fails and directs the author to the create-eval-loop skill.
3. Truthful clean-check — the working tree must be clean EXCEPT for
   `graph/causal_graph.json`, which the live runner rewrites every cycle
   (attributed dirty/live state, preserved by design). Any *other* dirty path
   fails the gate. This is honest: it declares its one exception rather than
   pretending the tree is pristine.

Exit non-zero on any failure.
"""
from __future__ import annotations

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
    for role in ("authoritative", "historical"):
        for p in arts.get(role, []):
            if not (REPO / p).exists():
                errs.append(f"declared {role} path missing: {p}")
    for role in ("runtime", "generated"):
        for p in arts.get(role, []):
            if not (REPO / p).exists():
                errs.append(f"declared {role} path missing: {p}")
            tracked = _tracked_under(p)
            if tracked:
                errs.append(
                    f"{role} path {p!r} must be excluded from source control "
                    f"but {len(tracked)} tracked file(s) found (e.g. {tracked[0]})"
                )
    return errs


def check_prompt_inventory() -> list[str]:
    hits: list[str] = []
    for py in (REPO / "src").rglob("*.py"):
        text = py.read_text(errors="ignore").lower()
        for pat in PROMPT_PATTERNS:
            if pat.lower() in text:
                hits.append(f"{py.relative_to(REPO)}: matches {pat!r}")
    if hits:
        return [
            "ungoverned prompt/LLM surface detected in src (ADR-0039). "
            "Run the create-eval-loop skill before shipping:",
            *hits,
        ]
    return []


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
