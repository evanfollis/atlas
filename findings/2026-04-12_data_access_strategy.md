# Data Access Strategy — 2026-04-12

## Paid tier evaluation

### Glassnode
- Studio Advanced $49/mo: Studio display only, **no API**
- Studio Professional $999/mo billed yearly: per-exchange flows + entity-adjusted + cohort metrics, but **API is a paid add-on (sales call)**
- Realistic cost to get API-accessible on-chain flows: **$999/mo base + add-on ≈ $1500-2000/mo range**
- Verdict: overpriced for research phase. Priced for funds.

### CryptoQuant
- Advanced $29/mo: API gives price-OHLCV only (useless — we already have this)
- **Professional $99/mo billed yearly**: API with "All" data coverage, 20 req/min, 1 year history, daily resolution. **Minimum viable tier.**
- Premium $799/mo: full history + 1-min resolution + business license
- Verdict: Professional is 10× cheaper than Glassnode equivalent for comparable research access. The right paid option *when* we reach the point of spending.

## Free-first strategy (current approach)

80-90% of what paid on-chain services provide is buildable from free sources. Cost is engineering time, not dollars. For a research phase where we're eliminating hypothesis classes faster than promoting them, free > paid on expected-value basis.

### Free sources mapped to data needs

| Need | Free source | Status |
|---|---|---|
| Funding rates (deep history) | BitMEX via ccxt | **Plumbed** — 10 yr of BTC funding retrieved |
| Funding (other venues) | OKX, Kraken Futures via ccxt | Confirmed public, not yet plumbed |
| Open interest + liquidations | Coinglass public API | Not yet plumbed |
| Long/short ratio | Coinglass | Not yet plumbed |
| Options IV / skew / term | Deribit via ccxt | Public, not yet plumbed |
| Exchange flows | Dune Analytics free tier (SQL) | Not yet plumbed |
| Whale-tier labels | Arkham Intelligence (manual export) + Dune | Not yet plumbed |
| Miner flows | Dune (labeled miner addresses) | Not yet plumbed |

### Forbidden venues (CLAUDE.md geo-restriction)
- Binance (futures + spot) — blocked on Hetzner US server
- Bybit — blocked

## Prioritized free-data roadmap

1. **Coinglass** (no key) — unlocks aggregated funding/OI/liquidations across venues in one place. Largest one-step unlock.
2. **Cross-venue funding dispersion** — we already have BitMEX + OKX + Kraken Futures funding free. Zero new infrastructure needed. Untested hypothesis: funding *dispersion* between venues → arbitrage-resistance signal. Potentially novel because single-venue funding research is saturated, cross-venue isn't.
3. **Deribit options via ccxt** — free IV and skew. Options-implied vol predicts realized vol; skew predicts direction. Classical signals never tested in Atlas.
4. **Dune exchange flow queries** — rate-limited but sufficient for daily refresh. Closes the biggest remaining gap (on-chain flow composition).

## Trigger for paid subscription

Upgrade to CryptoQuant Professional ($99/mo) if and only if all of:
- A primitive has been validated on walk-forward + stationarity + bootstrap
- The primitive is blocked from further development by a specific missing metric that Dune cannot replicate economically
- The metric is listed on CryptoQuant Professional's API data coverage

Otherwise: stay free-tier.

## Connection to current Atlas state

The lag-6 decay finding (findings/2026-04-12_lag6_decay.md) concluded that the alpha frontier has moved beyond public-spot-price lag patterns. The funding-regime finding (findings/2026-04-12_funding_regime.md) showed regime-conditional derivatives signals are the next viable frontier. Both point to the same next-step: **plumb free derivatives-market data (Coinglass + Deribit) and test regime-conditional hypotheses on it.**
