#!/usr/bin/env bash
# deploy-check.sh — surfaces deployment-state drift for atlas.
#
# Verifies:
#   - HEAD is pushed to origin/main;
#   - the installed unit is byte-identical to the versioned unit;
#   - the unit is active, restarted after the deployed commit, and configured
#     with the external runtime root + bounded root exception controls; and
#   - required runtime directories exist.
#
# Any failed invariant exits non-zero. This is a deploy gate, not a best-effort
# diagnostic.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

echo "atlas deploy state — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

failures=0
fail() {
  echo "FAIL: $*" >&2
  failures=$((failures + 1))
}

git fetch --quiet origin main || fail "could not refresh origin/main"
ahead=$(git rev-list --count origin/main..HEAD)
echo "Unpushed commits on main: ${ahead}"
if [[ "${ahead}" != "0" ]]; then
  fail "HEAD has ${ahead} unpushed commit(s)"
  echo "  Outstanding:"
  git log --oneline origin/main..HEAD | sed 's/^/    /'
fi

if systemctl is-active --quiet atlas-runner.service 2>/dev/null; then
  active="active"
else
  active="inactive/unknown"
  fail "atlas-runner.service is not active"
fi
echo
echo "atlas-runner.service: ${active}"

last_commit_iso=$(git log -1 --format=%cI 2>/dev/null || echo "")
start_raw=$(systemctl show atlas-runner.service --property=ActiveEnterTimestamp --value 2>/dev/null || echo "")
echo "Last commit:   ${last_commit_iso}"
echo "Service start: ${start_raw:-unknown}"

if [[ -n "${last_commit_iso}" && -n "${start_raw}" ]]; then
  last_epoch=$(date -d "${last_commit_iso}" +%s 2>/dev/null || echo "0")
  start_epoch=$(date -d "${start_raw}" +%s 2>/dev/null || echo "0")
  if (( last_epoch > 0 && start_epoch > 0 && last_epoch > start_epoch )); then
    fail "last commit is newer than service start; restart is required"
  fi
fi

installed=/etc/systemd/system/atlas-runner.service
if ! cmp -s deploy/atlas-runner.service "${installed}"; then
  fail "installed unit differs from deploy/atlas-runner.service"
fi

unit_text=$(systemctl cat atlas-runner.service)
for required in \
  "ATLAS_RUNTIME_ROOT=/opt/workspace/runtime/projects/atlas" \
  "NoNewPrivileges=true" \
  "ProtectSystem=strict" \
  "CapabilityBoundingSet=" \
  "ReadWritePaths=/opt/workspace/runtime/projects/atlas"; do
  if ! grep -Fq "${required}" <<<"${unit_text}"; then
    fail "installed unit is missing ${required}"
  fi
done

runtime_root=/opt/workspace/runtime/projects/atlas
for required_dir in state sessions runs cache; do
  if [[ ! -d "${runtime_root}/${required_dir}" ]]; then
    fail "runtime directory missing: ${runtime_root}/${required_dir}"
  fi
done

if (( failures > 0 )); then
  echo
  echo "atlas deploy check: ${failures} failure(s)" >&2
  exit 1
fi

echo
echo "atlas deploy check: PASS"
