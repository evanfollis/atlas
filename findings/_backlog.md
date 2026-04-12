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
