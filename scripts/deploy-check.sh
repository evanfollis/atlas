#!/usr/bin/env bash
# deploy-check.sh — surfaces deployment-state drift for atlas.
#
# Reports:
#   - whether the local branch has commits not yet pushed to origin/main
#   - the most recent commit time vs. the atlas-runner.service start time
#     (a commit newer than the service start means the running process is
#     stale relative to disk)
#
# Exits 0 in all cases — this is a diagnostic, not a gate. Pair with the
# deploy/README.md push-and-restart rule.

set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

echo "atlas deploy state — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo

# Unpushed commits on main.
git fetch --quiet origin main 2>/dev/null || true
ahead=$(git rev-list --count origin/main..HEAD 2>/dev/null || echo "?")
echo "Unpushed commits on main: ${ahead}"
if [[ "${ahead}" != "0" && "${ahead}" != "?" ]]; then
  echo "  Outstanding:"
  git log --oneline origin/main..HEAD | sed 's/^/    /'
fi

# Service liveness.
if systemctl is-active --quiet atlas-runner.service 2>/dev/null; then
  active="active"
else
  active="inactive/unknown"
fi
echo
echo "atlas-runner.service: ${active}"

# Compare last commit time vs. service start time.
last_commit_iso=$(git log -1 --format=%cI 2>/dev/null || echo "")
# systemctl prints the start time in a format date(1) can parse directly.
start_raw=$(systemctl show atlas-runner.service --property=ActiveEnterTimestamp --value 2>/dev/null || echo "")
echo "Last commit:   ${last_commit_iso}"
echo "Service start: ${start_raw:-unknown}"

if [[ -n "${last_commit_iso}" && -n "${start_raw}" ]]; then
  last_epoch=$(date -d "${last_commit_iso}" +%s 2>/dev/null || echo "0")
  start_epoch=$(date -d "${start_raw}" +%s 2>/dev/null || echo "0")
  if (( last_epoch > 0 && start_epoch > 0 && last_epoch > start_epoch )); then
    echo
    echo "WARN: last commit is newer than service start. Restart with:"
    echo "  sudo systemctl restart atlas-runner.service"
    echo "Or document the gap in CURRENT_STATE.md per deploy/README.md."
  fi
fi
