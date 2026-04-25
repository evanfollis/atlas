---
name: Atlas deploy notes
description: Service unit, push-and-restart deployment rule, and the code_landed_NOT_deployed escape hatch
type: reference
updated: 2026-04-25
---

# Atlas — deployment notes

Atlas runs as a systemd service: `atlas-runner.service`. The unit at
`/etc/systemd/system/atlas-runner.service` is mirrored here at
`deploy/atlas-runner.service` for re-installation.

## Push-and-restart rule

After committing any change to `src/atlas/` that affects runtime behavior,
the same session must either:

1. **Push and restart**:
   ```
   git push origin main
   sudo systemctl restart atlas-runner.service
   ```
   Then verify with `scripts/deploy-check.sh` and `journalctl -u atlas-runner -n 20 --no-pager`.

2. **Or explicitly note the deployment gap** in `CURRENT_STATE.md` under
   "Known broken or degraded":
   ```
   - **<short title> — DELIVERY STATE: code_landed_NOT_deployed**:
     Fix at <commit> committed but not deployed because <reason>.
     ETA: <date>. Action required: <command to deploy>.
   ```

This rule exists because the frozen-loop fix (`bf6fc4e`) sat committed but
not deployed for 26+ hours while the running service kept emitting
`{"continue": 5}` cycles — the synthesis pattern "Code landed but not
deployed" (see `runtime/.meta/cross-cutting-2026-04-25T15-28-05Z.md`).

## Re-install (after host re-image or unit drift)

```
sudo install -m644 deploy/atlas-runner.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now atlas-runner.service
```

## Operational commands

| Action | Command |
|---|---|
| Status | `systemctl status atlas-runner.service` |
| Logs (live) | `journalctl -u atlas-runner.service -f` |
| Logs (recent) | `journalctl -u atlas-runner.service -n 50 --no-pager` |
| Stop / start / restart | `sudo systemctl stop\|start\|restart atlas-runner.service` |
| Telemetry stream | `tail -f /opt/workspace/runtime/.telemetry/events.jsonl \| grep '"project": "atlas"'` |
| Last cycle.completed | `grep '"eventType": "cycle.completed"' /opt/workspace/runtime/.telemetry/events.jsonl \| tail -1` |
| Deploy-state check | `scripts/deploy-check.sh` |

## Tuning

The service unit's `RestartSec=300` and `StartLimitBurst=3` per
`StartLimitIntervalSec=3600` prevent a startup-failure crash loop from
burning Bitstamp API quota. If transient network failures need faster
recovery, drop `RestartSec` and raise `StartLimitBurst`.
