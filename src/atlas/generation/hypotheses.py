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
    ratio = signal.metadata["vol_ratio"]
    regime = "expansion" if ratio > 1.0 else "compression"

    return Hypothesis(
        claim=f"Volatility {regime} in {symbol} {timeframe} predicts directional price movement "
              f"in the following {signal.metadata['window']} periods",
        rationale=f"Vol ratio = {ratio:.2f}. Regime changes often precede trending moves "
                  f"as market participants adjust positioning.",
        falsification_criteria=f"Returns following {regime} events do not differ significantly "
                               f"from unconditional returns (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe, "volatility", "regime"],
    )


def from_mean_reversion_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from mean-reversion signal."""
    z = signal.metadata["zscore"]
    window = signal.metadata["window"]
    direction = "below" if z < 0 else "above"

    return Hypothesis(
        claim=f"{symbol} reverts to {window}-period mean after extreme deviations "
              f"(|z| > 2.0) within {window // 2} periods",
        rationale=f"Current z-score = {z:.1f}σ {direction} MA. "
                  f"If mean-reversion holds, expect price convergence.",
        falsification_criteria=f"Buy-the-dip (z < -2) / sell-the-spike (z > 2) strategy "
                               f"does not produce significant positive returns (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe, "mean_reversion", f"ma_{window}"],
    )


def from_volume_signal(signal: Signal, symbol: str, timeframe: str) -> Hypothesis:
    """Generate hypothesis from volume anomaly signal."""
    z = signal.metadata["volume_zscore"]
    window = signal.metadata["window"]

    return Hypothesis(
        claim=f"Volume spikes (>{window}-period average + 3σ) in {symbol} {timeframe} "
              f"predict increased volatility and directional movement",
        rationale=f"Volume z-score = {z:.1f}. Unusual volume often signals informed trading "
                  f"or structural breaks.",
        falsification_criteria=f"Post-spike absolute returns do not differ significantly "
                               f"from normal-volume absolute returns (p > alpha)",
        tags=[symbol.replace("/", "_").lower(), timeframe, "volume", "anomaly"],
    )


_SIGNAL_GENERATORS = {
    "autocorrelation_scan": from_autocorrelation_signal,
    "rolling_vol_ratio": from_regime_signal,
    "zscore_mean_reversion": from_mean_reversion_signal,
    "volume_zscore": from_volume_signal,
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
