# Atlas command interface — Repository Architecture Standard v1.0.0 (ADR-0050).
# The Makefile only delegates; business logic stays in the package and pyproject.
# Required checks never mask failures (no `|| true`, no ignored exit codes).

# Use the project venv when present (local dev), else the ambient interpreter
# (CI installs into the runner's Python). Keeps `make check` identical in both.
PY := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python)
PIP := $(PY) -m pip

.DEFAULT_GOAL := help

.PHONY: help setup check test lint typecheck build run eval deploy-check

help:  ## Show available targets
	@echo "Atlas — service (active, agentic_risk=agentic). Targets:"
	@echo "  setup         create/refresh the .venv dev environment"
	@echo "  check         full pre-merge gate: lint + test + repo/clean/prompt validate"
	@echo "  test          full hermetic pytest suite (no network/credentials)"
	@echo "  lint          ruff lint gate"
	@echo "  typecheck     mypy (ADVISORY: scoped ramp, not yet in 'check' — see docs/architecture.md)"
	@echo "  build         build the wheel/sdist without deploying"
	@echo "  run           run one autonomous cycle locally (atlas run --once)"
	@echo "  eval          prompt/agent eval gate — N/A: Atlas has 0 in-product prompt artifacts"
	@echo "  deploy-check  verify deploy inputs/safety without deploying"

setup:  ## Create/refresh the local dev environment
	test -d .venv || python3 -m venv .venv
	.venv/bin/python -m pip install -e ".[dev]"

# check composes every applicable deterministic gate. clean-check runs last so it
# observes the post-test tree. Prompt-inventory + repo.toml validation live in
# check_repo.py. Any failure fails the whole gate.
check: lint test  ## Full pre-merge gate (must be green from a clean checkout)
	$(PY) scripts/check_repo.py

test:  ## Full hermetic test suite
	$(PY) -m pytest -q

lint:  ## Lint gate (ruff)
	$(PY) -m ruff check src tests scripts

typecheck:  ## Static types (advisory ramp — see docs/architecture.md §Type coverage)
	$(PY) -m mypy src/atlas/models src/atlas/storage

build:  ## Build distribution artifacts (no deploy)
	$(PY) -m build

run:  ## Run one autonomous research cycle locally
	.venv/bin/atlas run --once

eval:  ## No governed prompt artifacts in Atlas (see check_repo prompt-inventory)
	@echo "N/A: Atlas ships 0 in-product prompt/LLM artifacts (ADR-0039)."
	@echo "The prompt-inventory guard runs inside 'make check' (scripts/check_repo.py)."

deploy-check:  ## Verify deploy inputs/safety gates without deploying
	bash scripts/deploy-check.sh
