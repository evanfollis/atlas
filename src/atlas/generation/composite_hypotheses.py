"""Hypothesis generators for composite (multi-source) signals.

Each hypothesis encodes a causal mechanism, not just a correlation.
The falsification criteria test the mechanism's predictions, not just
whether the backtest is profitable.
"""

from atlas.generation.signals import Signal
from atlas.models.hypothesis import Hypothesis


def from_fear_capitulation(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    n = signal.metadata["n_events"]
    wr = signal.metadata["win_rate"]
    hp = signal.metadata["holding_period"]
    return Hypothesis(
        claim=f"Extreme fear (FNG<{signal.metadata['fear_threshold']}) during drawdown in {symbol} "
              f"marks capitulation — buying and holding {hp} bars yields positive returns "
              f"({wr:.0%} win rate across {n} events)",
        rationale="Extreme fear reflects retail panic. Combined with significant drawdown, "
                  "it signals forced sellers are exhausted. Remaining supply is in stronger hands, "
                  "creating asymmetric upside. The holding period avoids whipsaws from continued "
                  "fear oscillation.",
        falsification_criteria=f"Buy-at-fear strategy with {hp}-bar holding period does not "
                               f"produce significant positive returns (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe,
              "composite", "fear_capitulation", "sentiment", f"hold_{hp}"],
    )


def from_greed_euphoria(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    n = signal.metadata["n_events"]
    rr = signal.metadata["reversal_rate"]
    hp = signal.metadata["holding_period"]
    return Hypothesis(
        claim=f"Extreme greed (FNG>{signal.metadata['greed_threshold']}) during rally in {symbol} "
              f"marks euphoria — selling and holding {hp} bars captures reversal "
              f"({rr:.0%} reversal rate across {n} events)",
        rationale="Extreme greed during extended rally reflects overleveraged positioning. "
                  "Marginal buyers exhausted, liquidation cascades become likely. "
                  "Short exposure profits from the inevitable deleveraging.",
        falsification_criteria=f"Sell-at-greed strategy with {hp}-bar holding period does not "
                               f"produce significant negative returns for the asset (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe,
              "composite", "greed_euphoria", "sentiment", f"hold_{hp}"],
    )


def from_onchain_divergence(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    direction = signal.metadata["direction"]
    n = signal.metadata["n_events"]
    hp = signal.metadata["holding_period"]
    if direction == "bullish":
        claim = (f"Bullish on-chain divergence in {symbol}: price falling but on-chain volume "
                 f"rising signals accumulation by large holders ({n} events)")
        rationale = ("Declining price + rising on-chain volume means real BTC is moving to new "
                     "wallets despite negative sentiment. This pattern reflects informed accumulation — "
                     "large holders buying from panicking retail. Price follows on-chain activity.")
    else:
        claim = (f"Bearish on-chain divergence in {symbol}: price rising but on-chain volume "
                 f"declining signals speculative rally without real activity ({n} events)")
        rationale = ("Rising price without corresponding on-chain activity means the rally is driven "
                     "by derivatives/leverage, not actual BTC movement. These rallies are fragile — "
                     "there's no real demand backing the price increase.")

    return Hypothesis(
        claim=claim,
        rationale=rationale,
        falsification_criteria=f"{'Long' if direction == 'bullish' else 'Short'} position on "
                               f"on-chain divergence with {hp}-bar hold does not produce "
                               f"significant returns (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe,
              "composite", "onchain_divergence", direction, f"hold_{hp}"],
    )


def from_miner_capitulation(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    n = signal.metadata["n_events"]
    wr = signal.metadata["win_rate"]
    hp = signal.metadata["holding_period"]
    return Hypothesis(
        claim=f"Miner capitulation recovery in {symbol}: hashrate recovering after >10% drop "
              f"signals forced selling exhausted ({wr:.0%} win rate, {n} events)",
        rationale="When hashrate drops significantly, unprofitable miners shut down and must sell "
                  "BTC reserves to cover fixed costs (facilities, loans). This creates selling pressure. "
                  "When hashrate recovers, the forced selling is over — a structural price floor forms. "
                  "Buy signal is recovery, not the drop.",
        falsification_criteria=f"Long position on hashrate recovery with {hp}-bar hold does not "
                               f"produce significant positive returns (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe,
              "composite", "miner_capitulation", "onchain", f"hold_{hp}"],
    )


def from_sentiment_regime_confluence(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    direction = signal.metadata["direction"]
    n = signal.metadata["n_events"]
    hp = signal.metadata["holding_period"]
    components = signal.metadata["components"]

    if direction == "bullish":
        claim = (f"Bullish multi-source confluence in {symbol}: fear + accumulation + drawdown "
                 f"marks structural buying opportunity ({n} events)")
        rationale = ("Three independent causal channels converge: (1) retail sentiment extreme fear "
                     "→ capitulation selling exhausted, (2) on-chain volume rising → large holders "
                     "accumulating despite fear, (3) price at recent lows → maximum pain. "
                     "Each source tells a different part of the same story. Together they identify "
                     "moments where forced selling is exhausted and informed money is positioned.")
    else:
        claim = (f"Bearish multi-source confluence in {symbol}: greed + distribution + rally "
                 f"marks structural top ({n} events)")
        rationale = ("Three independent causal channels converge: (1) retail greed → overleveraged, "
                     "(2) on-chain volume falling → real activity doesn't support the price, "
                     "(3) price at recent highs → maximum euphoria. The rally is built on leverage "
                     "and sentiment, not real demand. Liquidation cascade is the likely resolution.")

    return Hypothesis(
        claim=claim,
        rationale=rationale,
        falsification_criteria=f"{'Long' if direction == 'bullish' else 'Short'} position on "
                               f"multi-source confluence with {hp}-bar hold does not produce "
                               f"significant returns (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe,
              "composite", "regime_confluence", direction, f"hold_{hp}"],
    )


COMPOSITE_GENERATORS = {
    "fear_capitulation": from_fear_capitulation,
    "greed_euphoria": from_greed_euphoria,
    "onchain_divergence": from_onchain_divergence,
    "miner_capitulation": from_miner_capitulation,
    "sentiment_regime_confluence": from_sentiment_regime_confluence,
}
