"""Hypothesis generation — convert signals and graph gaps into testable claims.

The generator uses two strategies:
1. Signal-driven: Convert detected market signals into falsifiable hypotheses
2. Graph-driven: Identify gaps, weak nodes, and unexplored edges in the causal graph
"""

from atlas.generation.signals import Signal
from atlas.models.graph import CausalGraph
from atlas.models.hypothesis import Hypothesis


def from_autocorrelation_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from autocorrelation signal."""
    lag = signal.metadata["lag"]
    ac = signal.metadata["autocorr"]
    direction = "positive" if ac > 0 else "negative"

    return Hypothesis(
        claim=f"{symbol} {timeframe} returns show {direction} autocorrelation at lag {lag}, "
              f"enabling a {'momentum' if ac > 0 else 'mean-reversion'} strategy",
        rationale=f"Detected significant autocorrelation r={ac:.3f} at lag {lag}. "
                  f"If persistent, this implies predictable return patterns.",
        falsification_criteria=f"Sharpe ratio of lag-{lag} {'momentum' if ac > 0 else 'contrarian'} "
                               f"strategy is not significantly different from zero (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe, "autocorrelation",
              "momentum" if ac > 0 else "mean_reversion"],
    )


def from_regime_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from volatility regime signal."""
    is_expansion = "n_expansions" in signal.metadata
    regime = "expansion" if is_expansion else "compression"
    window = signal.metadata["window"]

    return Hypothesis(
        claim=f"Volatility {regime} events in {symbol} {timeframe} predict directional price movement "
              f"in the following {window} periods",
        rationale=f"Detected recurrent volatility {regime} patterns. "
                  f"Regime changes often precede trending moves as market participants adjust positioning.",
        falsification_criteria=f"Returns following {regime} events do not differ significantly "
                               f"from unconditional returns (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe, "volatility", "regime"],
    )


def from_mean_reversion_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from structural mean-reversion signal."""
    window = signal.metadata["window"]
    reversion_rate = signal.metadata.get("reversion_rate", 0)
    n_extremes = signal.metadata.get("n_extremes", 0)

    return Hypothesis(
        claim=f"{symbol} reverts to {window}-period mean after extreme deviations "
              f"(|z| > 2.0) within {window // 2} periods",
        rationale=f"Observed {reversion_rate:.0%} reversion rate across {n_extremes} extreme events. "
                  f"If structural, a mean-reversion strategy should capture this.",
        falsification_criteria=f"Buy-the-dip (z < -2) / sell-the-spike (z > 2) strategy "
                               f"does not produce significant positive returns (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe, "mean_reversion", f"ma_{window}"],
    )


def from_volume_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from volume-return relationship signal."""
    n_spikes = signal.metadata.get("n_spikes", 0)
    ratio = signal.metadata.get("spike_abs_return", 0) / max(signal.metadata.get("normal_abs_return", 1), 1e-10)

    return Hypothesis(
        claim=f"Volume spikes in {symbol} {timeframe} predict {ratio:.1f}x larger price moves",
        rationale=f"Observed {n_spikes} volume spike events where subsequent absolute returns "
                  f"were significantly larger than normal. If structural, this can be traded.",
        falsification_criteria=f"Post-spike absolute returns do not differ significantly "
                               f"from normal-volume absolute returns (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe, "volume", "anomaly"],
    )


def from_momentum_persistence_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from momentum persistence signal."""
    lookback = signal.metadata["lookback"]
    hit_rate = signal.metadata["hit_rate"]
    direction = signal.metadata["direction"]

    strategy = "momentum" if direction == "momentum" else "contrarian"
    return Hypothesis(
        claim=f"{symbol} {timeframe} shows {lookback}-bar {direction} ({hit_rate:.0%} hit rate), "
              f"enabling a {strategy} strategy",
        rationale=f"Detected {hit_rate:.1%} directional persistence over {lookback}-bar windows. "
                  f"If structural, a {strategy} strategy following the {lookback}-bar trend should profit.",
        falsification_criteria=f"{strategy.capitalize()} strategy based on {lookback}-bar returns "
                               f"does not produce significant positive Sharpe (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe, direction,
              "momentum" if direction == "momentum" else "mean_reversion", f"lookback_{lookback}"],
    )


def from_return_skew_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from return skew signal."""
    skew = signal.metadata["skew"]
    direction = signal.metadata["direction"]

    if direction == "positive":
        strategy = "buy dips and hold for asymmetric upside"
    else:
        strategy = "fade rallies to exploit negative skew (crash risk premium)"

    return Hypothesis(
        claim=f"{symbol} {timeframe} returns exhibit significant {direction} skew ({skew:.2f}), "
              f"enabling a skew-harvesting strategy",
        rationale=f"Return distribution shows {direction} skew = {skew:.3f}. "
                  f"If persistent, this represents a structural edge: {strategy}.",
        falsification_criteria=f"Strategy exploiting {direction} skew does not produce "
                               f"significant positive Sharpe (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe, "skew", direction],
    )


def from_volatility_clustering_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from volatility clustering signal."""
    ac1 = signal.metadata["ac_lag1"]
    return Hypothesis(
        claim=f"{symbol} {timeframe} shows volatility clustering (|r| autocorr={ac1:.3f}), "
              f"enabling a vol-scaled position strategy",
        rationale=f"Absolute returns show strong autocorrelation ({ac1:.3f}), meaning high volatility "
                  f"periods persist. Reducing position size after vol spikes and increasing after calm "
                  f"periods should improve risk-adjusted returns.",
        falsification_criteria="Vol-scaled strategy does not produce significantly better "
                               "Sharpe than buy-and-hold (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe, "volatility_clustering", "vol_scaling"],
    )


def from_cross_asset_spread_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from cross-asset spread signal."""
    sym_a = signal.metadata["symbol_a"]
    sym_b = signal.metadata["symbol_b"]
    rate = signal.metadata["reversion_rate"]
    window = signal.metadata["window"]
    return Hypothesis(
        claim=f"{sym_a}/{sym_b} spread reverts to mean after extreme deviations "
              f"({rate:.0%} reversion rate, {window}-period window)",
        rationale=f"The price ratio of {sym_a} to {sym_b} mean-reverts because both assets "
                  f"share common market factors. Extremes reflect temporary dislocations.",
        falsification_criteria=f"Spread mean-reversion strategy (long underperformer, short outperformer "
                               f"at |z| > 1.5) does not produce significant positive Sharpe (p > alpha)",
        tags=[sym_a.replace("/", "_").lower(), sym_b.replace("/", "_").lower(),
              timeframe, "spread", "pairs_trading", f"window_{window}"],
    )


def from_lead_lag_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from lead-lag signal."""
    leader = signal.metadata["leader"]
    follower = signal.metadata["follower"]
    corr = signal.metadata["correlation"]
    return Hypothesis(
        claim=f"{leader} leads {follower} by 1 period at {timeframe} (corr={corr:.4f}), "
              f"enabling a cross-asset momentum strategy",
        rationale=f"Detected significant lead-lag: {leader} returns predict {follower} returns "
                  f"one period later (r={corr:.4f}). Likely due to differential liquidity or "
                  f"information processing speed.",
        falsification_criteria=f"Strategy trading {follower} based on {leader}'s prior return "
                               f"does not produce significant positive Sharpe (p > alpha)",
        tags=[leader.replace("/", "_").lower(), follower.replace("/", "_").lower(),
              timeframe, "lead_lag", "cross_asset_momentum"],
    )


_SIGNAL_GENERATORS = {
    "autocorrelation_scan": from_autocorrelation_signal,
    "rolling_vol_ratio": from_regime_signal,
    "zscore_mean_reversion": from_mean_reversion_signal,
    "volume_return_relationship": from_volume_signal,
    "momentum_persistence": from_momentum_persistence_signal,
    "return_skew": from_return_skew_signal,
    "volatility_clustering": from_volatility_clustering_signal,
    "cross_asset_spread": from_cross_asset_spread_signal,
    "lead_lag": from_lead_lag_signal,
}


def from_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis | None:
    """Convert a signal into a hypothesis using the appropriate generator."""
    gen = _SIGNAL_GENERATORS.get(signal.method)
    if gen:
        return gen(signal, symbol, timeframe)
    return None


def from_graph_gaps(graph: CausalGraph) -> list[Hypothesis]:
    """Identify testable gaps in the causal graph.

    Strategies:
    - Root nodes with no children: test whether the primitive predicts anything downstream
    - Leaf nodes: test whether they generalize to other symbols/timeframes
    - Missing cross-edges: test whether two related primitives have a causal relationship
    """
    hypotheses = []

    if graph.node_count == 0:
        return hypotheses

    # Isolated roots — can we extend them?
    for root_id in graph.roots():
        data = graph.get_primitive_data(root_id)
        if data and not list(graph.g.successors(root_id)):
            hypotheses.append(Hypothesis(
                claim=f"The validated primitive '{data['claim']}' has downstream predictive implications "
                      f"that can be tested with new experiments",
                rationale=f"Root node {root_id} has no children in the causal graph. "
                          f"If this primitive is true, it likely implies testable consequences.",
                falsification_criteria="No downstream hypothesis derived from this primitive "
                                       "produces significant evidence",
                tags=data.get("tags", []) + ["graph_gap", "extension"],
                parent_primitive_id=root_id,
            ))

    return hypotheses
