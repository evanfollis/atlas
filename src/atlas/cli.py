"""Atlas CLI — scientific research workflow for causal reasoning."""

import json
from pathlib import Path

import click

from atlas.models.events import EventType, SessionEvent
from atlas.models.evidence import Evidence, EvidenceClass, EvidenceDirection, EvidenceQuality
from atlas.models.experiment import Experiment, ExperimentStatus
from atlas.models.hypothesis import Hypothesis, HypothesisStatus
from atlas.models.primitive import ReasoningPrimitive
from atlas.models.session import CycleOutcome, CycleStatus, ResearchCycle
from atlas.storage.event_store import EventStore
from atlas.storage.graph_store import GraphStore
from atlas.storage.state_store import StateStore

BASE_DIR = Path.cwd()
SESSIONS_DIR = BASE_DIR / "sessions"
GRAPH_DIR = BASE_DIR / "graph"
STATE_DIR = BASE_DIR / ".atlas"

_store = StateStore(STATE_DIR)


def get_event_store() -> EventStore:
    return EventStore(SESSIONS_DIR)


def get_graph_store() -> GraphStore:
    return GraphStore(GRAPH_DIR)


def _save_obj(kind: str, obj_id: str, data: dict) -> None:
    _store.save(kind, obj_id, data)


def _load_obj(kind: str, obj_id: str) -> dict | None:
    return _store.load(kind, obj_id)


def _list_objs(kind: str) -> list[dict]:
    return _store.list_all(kind)


def _active_cycle() -> ResearchCycle | None:
    """Return the active cycle, but only if exactly one exists."""
    active = []
    for data in _list_objs("cycles"):
        cycle = ResearchCycle.model_validate(data)
        if cycle.status == CycleStatus.ACTIVE:
            active.append(cycle)
    if len(active) == 1:
        return active[0]
    if len(active) > 1:
        click.echo(f"Warning: {len(active)} active cycles. Use --cycle to specify.", err=True)
    return None


@click.group()
def cli() -> None:
    """Atlas — scientific causal reasoning engine."""
    pass


# --- Hypothesis ---

@cli.group()
def hypothesis() -> None:
    """Manage hypotheses."""
    pass


@hypothesis.command("create")
@click.option("--claim", prompt=True, help="The falsifiable claim")
@click.option("--rationale", prompt=True, help="Why this might be true")
@click.option("--falsification", prompt="Falsification criteria", help="What would prove it wrong")
@click.option("--alpha", default=0.05, help="Significance threshold")
@click.option("--tags", default="", help="Comma-separated tags")
@click.option("--parent", default=None, help="Parent primitive ID if derived")
def hypothesis_create(claim: str, rationale: str, falsification: str, alpha: float, tags: str, parent: str | None) -> None:
    """Formulate a new hypothesis and start a research cycle."""
    h = Hypothesis(
        claim=claim,
        rationale=rationale,
        falsification_criteria=falsification,
        significance_threshold=alpha,
        tags=[t.strip() for t in tags.split(",") if t.strip()],
        parent_primitive_id=parent,
    )
    _save_obj("hypotheses", h.id, h.model_dump())

    cycle = ResearchCycle(hypothesis_id=h.id)
    _save_obj("cycles", cycle.id, cycle.model_dump())

    store = get_event_store()
    store.append(SessionEvent(
        session_id=cycle.id,
        event_type=EventType.HYPOTHESIS_FORMULATED,
        details={"hypothesis_id": h.id, "claim": claim},
    ))

    click.echo(f"Hypothesis {h.id}: {claim}")
    click.echo(f"Research cycle {cycle.id} started.")


@hypothesis.command("list")
def hypothesis_list() -> None:
    """List all hypotheses."""
    for data in _list_objs("hypotheses"):
        h = Hypothesis.model_validate(data)
        click.echo(f"[{h.status.value:>10}] {h.id}: {h.claim}")


# --- Experiment ---

@cli.group()
def experiment() -> None:
    """Manage experiments."""
    pass


@experiment.command("design")
@click.option("--hypothesis-id", prompt=True, help="Hypothesis to test")
@click.option("--description", prompt=True, help="What we're doing")
@click.option("--method", prompt=True, type=click.Choice(["backtest", "statistical_test", "observation"]), help="Method")
@click.option("--success", prompt="Success criteria", help="What constitutes support")
@click.option("--failure", prompt="Failure criteria", help="What constitutes falsification")
@click.option("--params", default="{}", help="JSON parameters")
def experiment_design(hypothesis_id: str, description: str, method: str, success: str, failure: str, params: str) -> None:
    """Design an experiment for a hypothesis."""
    h_data = _load_obj("hypotheses", hypothesis_id)
    if not h_data:
        click.echo(f"Hypothesis {hypothesis_id} not found.")
        return

    exp = Experiment(
        hypothesis_id=hypothesis_id,
        description=description,
        method=method,
        parameters=json.loads(params),
        success_criteria=success,
        failure_criteria=failure,
    )
    _save_obj("experiments", exp.id, exp.model_dump())

    cycle = _active_cycle()
    if cycle and cycle.hypothesis_id == hypothesis_id:
        cycle.experiment_ids.append(exp.id)
        _save_obj("cycles", cycle.id, cycle.model_dump())
        store = get_event_store()
        store.append(SessionEvent(
            session_id=cycle.id,
            event_type=EventType.EXPERIMENT_DESIGNED,
            details={"experiment_id": exp.id, "method": method},
        ))

    click.echo(f"Experiment {exp.id}: {description}")


@experiment.command("run")
@click.argument("experiment_id")
@click.option("--symbol", default="BTC/USDT", help="Trading pair")
@click.option("--timeframe", default="4h", help="Candle timeframe")
@click.option("--since", default=None, help="Start date (ISO format)")
@click.option("--limit", default=1000, help="Number of candles")
def experiment_run(experiment_id: str, symbol: str, timeframe: str, since: str | None, limit: int) -> None:
    """Run a backtest experiment. Fetches data, runs backtest, outputs stats."""
    from atlas.analysis.backtest import run_backtest
    from atlas.analysis.statistics import bootstrap_sharpe, mean_return_test, sharpe_significance
    from atlas.data.market import MarketData

    exp_data = _load_obj("experiments", experiment_id)
    if not exp_data:
        click.echo(f"Experiment {experiment_id} not found.")
        return

    exp = Experiment.model_validate(exp_data)
    h_data = _load_obj("hypotheses", exp.hypothesis_id)
    alpha = h_data.get("significance_threshold", 0.05) if h_data else 0.05

    click.echo(f"Fetching {symbol} {timeframe} data...")
    md = MarketData(cache_dir=BASE_DIR / "data")
    prices_df = md.fetch_ohlcv(symbol=symbol, timeframe=timeframe, since=since, limit=limit)
    prices = prices_df["close"]

    # For now: simple momentum signal as placeholder
    # Real signals will be defined per-experiment via parameters
    lookback = exp.parameters.get("lookback", 20)
    signals = (prices.pct_change(lookback) > 0).astype(int).replace(0, -1)

    click.echo("Running backtest...")
    result = run_backtest(prices, signals)

    click.echo(f"\n--- Backtest Results ---")
    click.echo(f"Total return:      {result.total_return:>10.2%}")
    click.echo(f"Annualized return: {result.annualized_return:>10.2%}")
    click.echo(f"Sharpe ratio:      {result.sharpe_ratio:>10.2f}")
    click.echo(f"Max drawdown:      {result.max_drawdown:>10.2%}")
    click.echo(f"Win rate:          {result.win_rate:>10.2%}")
    click.echo(f"N trades:          {result.n_trades:>10d}")

    click.echo(f"\n--- Statistical Tests (α={alpha}) ---")
    sharpe_test = sharpe_significance(result.returns, alpha=alpha)
    click.echo(f"Sharpe significance: t={sharpe_test.statistic:.3f}, p={sharpe_test.p_value:.4f}, "
               f"{'✓' if sharpe_test.significant else '✗'} CI=[{sharpe_test.ci_lower:.2f}, {sharpe_test.ci_upper:.2f}]")

    mean_test = mean_return_test(result.returns, alpha=alpha)
    click.echo(f"Mean return t-test:  t={mean_test.statistic:.3f}, p={mean_test.p_value:.4f}, "
               f"{'✓' if mean_test.significant else '✗'} CI=[{mean_test.ci_lower:.6f}, {mean_test.ci_upper:.6f}]")

    boot = bootstrap_sharpe(result.returns, alpha=alpha)
    click.echo(f"Bootstrap Sharpe:    S={boot.statistic:.2f}, p={boot.p_value:.4f}, "
               f"{'✓' if boot.significant else '✗'} CI=[{boot.ci_lower:.2f}, {boot.ci_upper:.2f}]")

    # Update experiment
    exp.status = ExperimentStatus.COMPLETED
    exp.results = {
        "total_return": result.total_return,
        "sharpe": result.sharpe_ratio,
        "max_drawdown": result.max_drawdown,
        "sharpe_p_value": sharpe_test.p_value,
        "mean_p_value": mean_test.p_value,
        "bootstrap_ci": [boot.ci_lower, boot.ci_upper],
    }
    _save_obj("experiments", exp.id, exp.model_dump())

    cycle = _active_cycle()
    if cycle:
        store = get_event_store()
        store.append(SessionEvent(
            session_id=cycle.id,
            event_type=EventType.EXPERIMENT_EXECUTED,
            details={"experiment_id": exp.id, "sharpe": result.sharpe_ratio, "p_value": sharpe_test.p_value},
        ))


# --- Evidence ---

@cli.group()
def evidence() -> None:
    """Record evidence from experiments."""
    pass


@evidence.command("record")
@click.option("--experiment-id", prompt=True, help="Experiment this evidence is from")
@click.option("--evidence-class", "ev_class", prompt=True,
              type=click.Choice([e.value for e in EvidenceClass]), help="Type of evidence")
@click.option("--quality", prompt=True, type=click.Choice([q.value for q in EvidenceQuality]))
@click.option("--direction", prompt=True, type=click.Choice([d.value for d in EvidenceDirection]))
@click.option("--summary", prompt=True, help="Description of finding")
@click.option("--data-range", default="", help="Data range covered")
def evidence_record(experiment_id: str, ev_class: str, quality: str, direction: str, summary: str, data_range: str) -> None:
    """Record evidence from an experiment."""
    exp_data = _load_obj("experiments", experiment_id)
    if not exp_data:
        click.echo(f"Experiment {experiment_id} not found.")
        return

    exp = Experiment.model_validate(exp_data)
    stats = exp.results or {}

    ev = Evidence(
        experiment_id=experiment_id,
        hypothesis_id=exp.hypothesis_id,
        evidence_class=EvidenceClass(ev_class),
        quality=EvidenceQuality(quality),
        direction=EvidenceDirection(direction),
        summary=summary,
        statistics=stats,
        data_range=data_range,
    )
    _save_obj("evidence", ev.id, ev.model_dump())

    cycle = _active_cycle()
    if cycle:
        cycle.evidence_ids.append(ev.id)
        _save_obj("cycles", cycle.id, cycle.model_dump())
        store = get_event_store()
        store.append(SessionEvent(
            session_id=cycle.id,
            event_type=EventType.EVIDENCE_RECORDED,
            details={"evidence_id": ev.id, "quality": quality, "direction": direction},
        ))

    click.echo(f"Evidence {ev.id} recorded: {quality} {direction}")


@evidence.command("list")
@click.option("--hypothesis-id", default=None, help="Filter by hypothesis")
def evidence_list(hypothesis_id: str | None) -> None:
    """List recorded evidence."""
    for data in _list_objs("evidence"):
        ev = Evidence.model_validate(data)
        if hypothesis_id and ev.hypothesis_id != hypothesis_id:
            continue
        click.echo(f"[{ev.quality.value:>8} {ev.direction.value:>12}] {ev.id}: {ev.summary}")


# --- Decide ---

@cli.command()
@click.argument("action", type=click.Choice(["promote", "kill", "continue", "pivot"]))
@click.option("--rationale", prompt=True, help="Why this decision")
@click.option("--confidence", default=0.8, help="Confidence level for promotion")
@click.option("--causal-parents", default="", help="Comma-separated parent primitive IDs")
def decide(action: str, rationale: str, confidence: float, causal_parents: str) -> None:
    """Make a decision on the current research cycle."""
    cycle = _active_cycle()
    if not cycle:
        click.echo("No active research cycle.")
        return

    h_data = _load_obj("hypotheses", cycle.hypothesis_id)
    if not h_data:
        click.echo("Hypothesis not found.")
        return

    h = Hypothesis.model_validate(h_data)
    store = get_event_store()

    if action == "promote":
        # Check promotion gate
        evidence_objs = [Evidence.model_validate(d) for d in _list_objs("evidence") if d.get("hypothesis_id") == h.id]
        strong = [e for e in evidence_objs if e.quality == EvidenceQuality.STRONG and e.direction == EvidenceDirection.SUPPORTS]
        oos_or_live = [e for e in strong if e.evidence_class in (EvidenceClass.OUT_OF_SAMPLE_TEST, EvidenceClass.LIVE_OBSERVATION)]

        if len(strong) < 2:
            click.echo(f"Promotion gate: need ≥2 strong supporting evidence, have {len(strong)}. Use 'continue' to gather more.")
            return
        if len(oos_or_live) < 1:
            click.echo("Promotion gate: need ≥1 out-of-sample or live observation among strong evidence.")
            return

        parents = [p.strip() for p in causal_parents.split(",") if p.strip()]
        primitive = ReasoningPrimitive(
            claim=h.claim,
            hypothesis_id=h.id,
            evidence_ids=[e.id for e in strong],
            confidence=confidence,
            tags=h.tags,
            causal_parents=parents,
        )
        _save_obj("primitives", primitive.id, primitive.model_dump())

        # Update graph
        gs = get_graph_store()
        graph = gs.load()
        graph.add_primitive(primitive)
        gs.save(graph)

        h.status = HypothesisStatus.PROMOTED
        _save_obj("hypotheses", h.id, h.model_dump())
        cycle.status = CycleStatus.CLOSED
        cycle.outcome = CycleOutcome.PROMOTED
        cycle.decision_rationale = rationale
        _save_obj("cycles", cycle.id, cycle.model_dump())

        store.append(SessionEvent(
            session_id=cycle.id,
            event_type=EventType.PRIMITIVE_PROMOTED,
            details={"primitive_id": primitive.id, "claim": h.claim},
        ))
        store.append(SessionEvent(
            session_id=cycle.id,
            event_type=EventType.DECISION_MADE,
            details={"action": "promote", "rationale": rationale},
        ))

        click.echo(f"Primitive {primitive.id} promoted: {h.claim}")
        click.echo(f"Graph now has {graph.node_count} nodes, {graph.edge_count} edges.")

    elif action == "kill":
        h.status = HypothesisStatus.FALSIFIED
        _save_obj("hypotheses", h.id, h.model_dump())
        cycle.status = CycleStatus.CLOSED
        cycle.outcome = CycleOutcome.KILLED
        cycle.decision_rationale = rationale
        _save_obj("cycles", cycle.id, cycle.model_dump())

        store.append(SessionEvent(
            session_id=cycle.id,
            event_type=EventType.DECISION_MADE,
            details={"action": "kill", "rationale": rationale},
        ))
        click.echo(f"Hypothesis {h.id} killed: {rationale}")

    elif action == "pivot":
        cycle.status = CycleStatus.CLOSED
        cycle.outcome = CycleOutcome.PIVOTED
        cycle.decision_rationale = rationale
        _save_obj("cycles", cycle.id, cycle.model_dump())

        store.append(SessionEvent(
            session_id=cycle.id,
            event_type=EventType.DECISION_MADE,
            details={"action": "pivot", "rationale": rationale},
        ))
        click.echo(f"Research cycle pivoted: {rationale}")
        click.echo("Create a new hypothesis to continue.")

    else:  # continue
        store.append(SessionEvent(
            session_id=cycle.id,
            event_type=EventType.DECISION_MADE,
            details={"action": "continue", "rationale": rationale},
        ))
        click.echo(f"Continuing research: {rationale}")


# --- Graph ---

@cli.group()
def graph() -> None:
    """Inspect the causal graph."""
    pass


@graph.command("show")
def graph_show() -> None:
    """Display the current causal graph."""
    gs = get_graph_store()
    g = gs.load()
    click.echo(g.display())


@graph.command("primitive")
@click.argument("primitive_id")
def graph_primitive(primitive_id: str) -> None:
    """Show details for a specific primitive."""
    data = _load_obj("primitives", primitive_id)
    if not data:
        click.echo(f"Primitive {primitive_id} not found.")
        return
    p = ReasoningPrimitive.model_validate(data)
    click.echo(f"ID:         {p.id}")
    click.echo(f"Claim:      {p.claim}")
    click.echo(f"Confidence: {p.confidence}")
    click.echo(f"Evidence:   {', '.join(p.evidence_ids)}")
    click.echo(f"Parents:    {', '.join(p.causal_parents) or 'none (root)'}")
    click.echo(f"Children:   {', '.join(p.causal_children) or 'none (leaf)'}")


# --- Status ---

@cli.command()
def status() -> None:
    """Show current research state."""
    cycle = _active_cycle()
    if not cycle:
        click.echo("No active research cycle.")
    else:
        h_data = _load_obj("hypotheses", cycle.hypothesis_id)
        claim = h_data.get("claim", "?") if h_data else "?"
        click.echo(f"Active cycle:  {cycle.id}")
        click.echo(f"Hypothesis:    {cycle.hypothesis_id}: {claim}")
        click.echo(f"Experiments:   {len(cycle.experiment_ids)}")
        click.echo(f"Evidence:      {len(cycle.evidence_ids)}")

    gs = get_graph_store()
    g = gs.load()
    click.echo(f"\nCausal graph:  {g.node_count} primitives, {g.edge_count} edges")

    hypotheses = _list_objs("hypotheses")
    by_status = {}
    for h in hypotheses:
        s = h.get("status", "unknown")
        by_status[s] = by_status.get(s, 0) + 1
    if by_status:
        click.echo(f"Hypotheses:    {', '.join(f'{v} {k}' for k, v in by_status.items())}")


# --- Autonomous Runner ---

@cli.command("run")
@click.option("--once", is_flag=True, help="Run one cycle and exit")
@click.option("--interval", default=3600, help="Seconds between cycles (continuous mode)")
@click.option("--exchange", default="bitstamp", help="Exchange to use (bitstamp for deep history)")
def run_autonomous(once: bool, interval: int, exchange: str) -> None:
    """Run the autonomous research loop."""
    import logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

    from atlas.runner import AutonomousRunner
    runner = AutonomousRunner(base_dir=BASE_DIR, exchange_id=exchange)

    if once:
        report = runner.run_cycle()
        click.echo(json.dumps(report, indent=2, default=str))
    else:
        runner.run_continuous(interval_seconds=interval)


@cli.command("scan")
@click.option("--symbol", default="BTC/USDT", help="Trading pair")
@click.option("--timeframe", default="4h", help="Candle timeframe")
def scan_signals(symbol: str, timeframe: str) -> None:
    """Scan for signals in market data (debug/inspect)."""
    from atlas.data.market import MarketData
    from atlas.generation.signals import scan_all

    md = MarketData(cache_dir=BASE_DIR / "data")
    df = md.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=500)
    signals = scan_all(df)

    if not signals:
        click.echo("No signals detected.")
        return

    for s in signals:
        click.echo(f"[{s.strength:.2f}] {s.method}: {s.description}")


METHODOLOGY_LOG = BASE_DIR / "methodology.jsonl"
REVAL_QUEUE = BASE_DIR / "pending_revalidation.jsonl"


@cli.command("ingest-finding")
@click.argument("finding_path", type=click.Path(exists=True, path_type=Path))
def ingest_finding_cmd(finding_path: Path) -> None:
    """Parse a finding markdown and emit Hypothesis/Experiment/Evidence records."""
    from atlas.research.ingest import ingest_finding
    ids = ingest_finding(finding_path, STATE_DIR, METHODOLOGY_LOG, REVAL_QUEUE)
    click.echo(f"hypothesis={ids['hypothesis_id']} experiment={ids['experiment_id']} evidence={ids['evidence_id']}")


@cli.command("revalidations-due")
def revalidations_due_cmd() -> None:
    """List findings whose revalidation window has elapsed."""
    from atlas.research.ingest import due_revalidations
    rows = due_revalidations(REVAL_QUEUE)
    if not rows:
        click.echo("No revalidations due.")
        return
    for r in rows:
        click.echo(f"{r['experiment_id']}  due={r['due_at']}  script={r['script']}")
