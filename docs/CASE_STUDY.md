# Atlas — what it is, what it has actually done, and what it has not

*A truthful case study built from the system's own receipts. Numbers below
are as of 2026-07-19 and are reproducible with the commands shown. This
document deliberately separates **engineering facts** (the machine runs) from
**scientific claims** (a market statement is true). Conflating the two is the
exact error this system exists to avoid.*

---

## 1. What Atlas is

Atlas is an autonomous research loop that applies the scientific method to
build a causal graph of **validated** knowledge. It generates its own
hypotheses, pre-registers a falsification criterion and significance threshold
for each, runs walk-forward experiments, classifies the evidence, and makes an
explicit promote / kill / continue / pivot decision — with no human in the
loop. The architecture is domain-agnostic; it is currently pointed at crypto
markets (Bitstamp hourly bars for BTC, ETH, SOL).

The design commitment that matters most: **a claim only becomes a "reasoning
primitive" (a trusted node) if it clears a promotion gate** — at least two
strong, independent pieces of evidence, at least one of them out-of-sample or
from live observation, meeting the pre-registered threshold, with no
unaddressed strong contradiction. Pre-registered fields are immutable in code.

## 2. The observation route

Every cycle a hypothesis is tested along one or both of two paths:

- **Backtest path.** Scan the training data for a pattern → form a hypothesis →
  run an anchored expanding-window walk-forward backtest (5 out-of-sample
  folds, 26 bps fee per position change) → record `out_of_sample_test`
  evidence → decide. Signal scanning is restricted to training data; the
  out-of-sample folds are never used to pick the signal.
- **Forward-prediction ledger.** For each detected pattern, register a *dated*
  forward prediction. When its 7-day window closes, replay the **frozen**
  strategy on the realized data and write a `live_observation` evidence
  record. A single 7-day window is mostly noise, so this evidence is capped at
  **moderate** — two lucky windows can never clear the promotion gate on their
  own. This is the "un-exhaustible" path: forward time keeps closing windows
  even when the backtest hypothesis space is exhausted.

```
signal scan ─▶ hypothesis (pre-registered) ─▶ walk-forward OOS ─▶ evidence ─▶ decide ─▶ graph
        └────▶ dated forward prediction ─▶ (window closes) ─▶ replay ─▶ live_observation ─▶ evidence
```

## 3. What has actually run (the receipts)

Reproduce: `.venv/bin/atlas strategy readiness` and the counts under `.atlas/`.

| Measure | Value |
|---|---|
| Hypotheses formulated | 85 (73 falsified · 7 infeasible · 5 formulated-blocked) |
| Evidence records | 293 (253 out-of-sample · 40 live-observation) |
| Evidence by direction | 122 contradicts · 5 supports · 166 inconclusive |
| Forward predictions registered | 80 across 4 windows (buckets 2948–2951); 40 resolved |
| Forward-window outcomes | 36 confirmed-null · 3 edge-appeared · 1 inconclusive |
| Causal-graph nodes | 69 — **all refuted** |
| Causal-graph edges | 0 |
| **Promoted reasoning primitives** | **0** |

These are **engineering-and-measurement facts**: the loop runs, the ledger
scores itself autonomously (bucket 2949 was scored unattended on 2026-07-16),
telemetry is emitted every cycle, and 191 tests pass. None of that is evidence
that any market claim is true.

## 4. What Atlas has actually proven — and what it has not

**Proven (negative knowledge, which is real knowledge):** Atlas can *kill*
hypotheses rigorously. 73 conjectures have been falsified against
out-of-sample data; 36 forward windows independently confirmed the null (no
edge net of fees). The causal graph is, today, honestly a **map of refuted
claims** — 69 dead ends that a future search does not need to revisit. Under
this project's own standard ("the causal graph earns its name or loses it"),
it is currently closer to a refutation ledger than a causal graph, and it is
labelled as such rather than dressed up.

**Not proven (and not claimed):**

- **Zero validated causal claims.** The promotion gate has never fired. There
  are 0 promoted primitives and 0 causal edges. No market statement has earned
  the label "validated."
- The 3 `edge_appeared` forward windows are **not** validated edges. A 7-day
  window is mostly noise (why the evidence is capped at moderate); they are
  flagged for follow-up, not counted as findings.
- **Backtest ≠ live.** The model charges a 26 bps fee per position change but
  ignores slippage, funding, market impact, and liquidity. No capital
  conclusion should be drawn.
- **The loop is currently hypothesis-space-exhausted.** Its detectors
  re-derive only already-falsified claims, so recent cycles produce no new
  decisions. Progress from here needs *new* signal detectors or *new* data —
  not more cycles of the current ones. The system now escalates this stuck
  state on a recurring cadence rather than falling silent after one alert.

## 5. Honest bottom line

Atlas is a working falsification engine with a truthful promotion gate that has
so far refused to promote anything — which, given the data, is the correct
outcome, not a failure. Its value to date is a growing, machine-generated map
of what does **not** work, plus the discipline that will make any future
"this works" claim credible. The next measurable milestone is not "more
cycles"; it is a wider hypothesis supply (new detectors / data) that gives the
gate something it can honestly promote — or an explicit decision that the
current detector set is exhausted.
