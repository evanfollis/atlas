# Research Backlog — Atlas

Open tracks (from user mandate 2026-04-12 + codex review #5):

1. **Cross-venue funding dispersion** — BitMEX vs OKX vs KrakenFutures BTC perp. Do divergences predict forward return or vol? Zero new data needed. [IN PROGRESS]
2. **Regime-gated funding reversal** — use realized-vol or DVOL as gate on the funding→return hypothesis.
3. **Dune exchange net-flow** — flow → forward return via labelled CEX addresses (already cached 4957 labels).
4. **News data source** — free crypto news APIs / RSS aggregators; event-study framework.
5. **Events data source** — halvings, forks, protocol upgrades, regulatory announcements.
6. **Substack as signal source (NEW)** — user wants to follow Substack authors for (a) *ideas* for signals to test and (b) potentially treating author-published signals themselves as the signal (track-record, timestamped posts). Needs: ingestion path (RSS per author), idea-extraction vs. signal-extraction distinction, forward-return evaluation framework for claimed calls.
7. **DVOL rebuttal test** — freeze rule pre-2024, episode-level bootstrap, report OOS 2024-26.
8. **Rolling stationarity infra** — replace calendar-year bins with rolling-window + structural-break tests + regime labels (codex #3).
9. **Walk-forward fit-vs-test claim** — backtest.py docstring says training fits, code only tests. Either wire training state through or correct docstring + runner comment (codex #4).
10. **Causal graph integration across multi-source data** — combine news/events/on-chain/market signals into testable causal hypotheses, not just one-variable correlations.
11. **Dispersion narrow retest (codex #6 design)** — fix venue membership to BitMEX+KrakenFutures only (stable 1yr window), measure at 8h funding-settlement cadence not daily mean, residualize dispersion against mean funding, test as interaction term `mean_fund × z(disp)` not median gate.
12. **Fetch-layer gap audit report** — beyond post-fetch gap warnings, produce a persisted coverage report per venue/asset and refuse downstream analyses when gap density > threshold.
13. **Trainable signal class exploration (codex #6 streetlight)** — the current walk-forward only evaluates stateless rolling rules. "Microstructure reversal is exhausted" is only defensible *for that implementation class*. Test one fit-train-apply-test variant (e.g., rolling-window regression-β with coefficient carried forward) as a control to see whether it changes the negative pattern.
