Reading additional input from stdin...
OpenAI Codex v0.144.1
--------
workdir: /opt/workspace/projects/atlas
model: gpt-5.5
provider: openai
approval: on-request
sandbox: read-only
reasoning effort: high
reasoning summaries: none
session id: 019f535a-c977-7653-bcd1-0d7bea69ea0c
--------
user
Adversarial review of this exact file path:

/opt/workspace/projects/atlas/src/atlas/runner.py

You are a skeptical reviewer. Read the target file carefully. Then produce a review with exactly these three sections:

1. **Most dangerous assumption** — the claim that if wrong, produces the largest blast radius.
2. **Missing failure mode** — what the design does not account for that is likely to happen in practice.
3. **Boundary most likely to be collapsed in practice** — where the nominal separation will erode under real use.

Cite specific line numbers. Be terse and concrete. End with a 1-2 sentence overall verdict. Under 500 words total. Do not edit any files.
codex
I’ll read the target file with line numbers and focus the review on the three requested adversarial angles, without making edits.
exec
/bin/bash -lc 'nl -ba /opt/workspace/projects/atlas/src/atlas/runner.py' in /opt/workspace/projects/atlas
 succeeded in 0ms:
     1	"""Autonomous research loop — the production runtime for Atlas.
     2	
     3	Runs continuously: scan → generate → test → evaluate → decide → update graph → repeat.
     4	"""
     5	
     6	import json
     7	import logging
     8	import time
     9	from datetime import datetime, timedelta, timezone
    10	from pathlib import Path
    11	
    12	import pandas as pd
    13	
    14	from atlas.analysis.backtest import run_backtest, walk_forward_backtest
    15	from atlas.analysis.statistics import bootstrap_sharpe, mean_return_test, sharpe_significance
    16	from atlas.data.alternative import AlternativeData, align_to_price
    17	from atlas.data.market import MarketData
    18	from atlas.generation.calendar_signals import scan_calendar
    19	from atlas.generation.composite_hypotheses import COMPOSITE_GENERATORS
    20	from atlas.generation.composite_signals import scan_composite
    21	from atlas.generation.hypotheses import from_graph_gaps, from_signal
    22	from atlas.generation.signals import scan_all, detect_cross_asset_spread, detect_lead_lag
    23	from atlas.graph_backfill import backfill_falsified_claims
    24	from atlas.models.events import EventType, SessionEvent
    25	from atlas.models.evidence import Evidence, EvidenceClass, EvidenceDirection, EvidenceQuality
    26	from atlas.models.experiment import Experiment, ExperimentStatus
    27	from atlas.models.hypothesis import Hypothesis, HypothesisStatus
    28	from atlas.models.prediction import Prediction, prediction_id
    29	from atlas.models.primitive import ReasoningPrimitive
    30	from atlas.models.session import CycleOutcome, CycleStatus, ResearchCycle
    31	from atlas.storage.event_store import EventStore
    32	from atlas.storage.graph_store import GraphStore
    33	from atlas.storage.prediction_store import PredictionStore
    34	from atlas.storage.state_store import StateStore
    35	from atlas.utils import claim_hash as _claim_hash
    36	
    37	log = logging.getLogger("atlas.runner")
    38	
    39	# Pairs and timeframes to scan.
    40	# 1h gives ~4300 bars (6 months) which clears the 833-bar walk-forward minimum.
    41	# 4h yields only ~720 bars — below the gate, so every hypothesis stalls at "continue".
    42	DEFAULT_UNIVERSE = [
    43	    ("BTC/USDT", "1h"),
    44	    ("ETH/USDT", "1h"),
    45	    ("SOL/USDT", "1h"),
    46	]
    47	DEFAULT_UNIVERSE_SET: set[tuple[str, str]] = set(DEFAULT_UNIVERSE)
    48	
    49	# Forward-prediction ledger (CAUSAL_LOOP_AUDIT.md Q5). Horizon for the
    50	# non-overlapping forward windows that detected signals are scored against.
    51	PREDICTION_HORIZON_DAYS = 7.0
    52	FEE_BPS = 26  # matches run_experiment's backtest fee (Kraken taker)
    53	
    54	# Only register predictions whose strategy is fully encoded in the hypothesis
    55	# tags, so the 2b scorer can replay the frozen spec faithfully via
    56	# _build_signal_from_hypothesis from (symbol, timeframe, tags) alone. Excluded:
    57	# cross_asset_spread / lead_lag (their builder falls back to a single-symbol
    58	# proxy that does not represent the cross-asset claim) and the composite/
    59	# calendar generators (no tag-driven builder branch -> the generic-momentum
    60	# fallback, which is unrelated to e.g. a "weekend volatility" claim). Scoring a
    61	# proxy/fallback strategy would write meaningless live_observation evidence.
    62	# These are deferred until the Prediction spec captures what they need (e.g. the
    63	# partner series); see CAUSAL_LOOP_AUDIT.md §Implementation log.
    64	REPLAYABLE_METHODS = frozenset({
    65	    "autocorrelation_scan",
    66	    "rolling_vol_ratio",
    67	    "zscore_mean_reversion",
    68	    "volume_return_relationship",
    69	    "momentum_persistence",
    70	    "return_skew",
    71	    "volatility_clustering",
    72	})
    73	
    74	# Phase 2b scorer (CAUSAL_LOOP_AUDIT.md §Implementation log).
    75	# A single ~168-bar (7d/1h) window is mostly noise, so single-window live
    76	# evidence is deliberately capped at MODERATE — never STRONG — so two lucky
    77	# windows cannot clear the "≥2 distinct strong + ≥1 live_observation" promotion
    78	# gate. Calibration comes from aggregating many windows (2c), not one.
    79	SCORE_EDGE_SHARPE = 1.0    # annualized realized Sharpe above which a forward "edge" is flagged
    80	SCORE_MIN_BARS = 100       # a 7d/1h window is ~168 bars; below this the window is unresolvable
    81	
    82	# Tokens that mark a hypothesis as INFEASIBLE on this Hetzner server: the
    83	# named exchanges are either geo-blocked or only expose perp/funding feeds
    84	# we don't ingest. Match against lowercase claim+tags. See ADR-0014 and
    85	# CLAUDE.md §Default exchange.
    86	INFEASIBLE_EXCHANGE_TOKENS = (
    87	    "bitmex",
    88	    "kraken futures",
    89	    "krakenfutures",
    90	    "binance",
    91	    "bybit",
    92	)
    93	
    94	# Auto-top-up target: how many hypotheses we want under test per cycle.
    95	# Matches the cap in `generate_hypotheses` so the two paths converge on
    96	# the same Bonferroni budget.
    97	TOP_UP_TARGET = 5
    98	
    99	# Minimum bars a dataset must have before atlas will scan it for signals.
   100	# Set to the walk-forward minimum (833 bars) so any dataset we scan can also
   101	# sustain anchored-expanding walk-forward validation — otherwise we'd burn
   102	# Bonferroni budget on hypotheses that cannot clear the OOS gate regardless
   103	# of signal strength. Symbols below the floor are skipped and logged via
   104	# methodology so the skip is visible in telemetry instead of silent.
   105	MIN_BARS_FOR_RESEARCH = 833
   106	
   107	# Existing dataset evidence is only a cache while it is fresh. After this
   108	# window the same symbol/timeframe should be retested against newly available
   109	# market data instead of freezing the hypothesis forever.
   110	DATASET_RETEST_AFTER = timedelta(days=1)
   111	
   112	# Frozen-loop escalation: after this many consecutive cycle.completed events
   113	# whose decisions are all "continue", the runner emits a cycle.escalated event
   114	# and writes an URGENT handoff. Matches the workspace S3-P2 rule "self-monitoring
   115	# systems must self-report stuck states; threshold is 3 consecutive same-reason
   116	# skips" (CLAUDE.md §Architecture Governance).
   117	FROZEN_LOOP_ESCALATION_AFTER = 3
   118	
   119	
   120	def evaluate_promotion_gate(evidence: list[Evidence]) -> dict:
   121	    """Pure predicate: return promotion-gate metrics for one hypothesis.
   122	
   123	    Single source of truth shared by `evaluate_and_decide` (which acts on the
   124	    verdict) and `atlas strategy readiness` (which counts how many hypotheses
   125	    would pass). Adding a parallel implementation here would silently drift
   126	    from the runner.
   127	
   128	    Gate (per CLAUDE.md §Promotion Gate and atlas review #2):
   129	      - ≥2 strong supporting evidence records
   130	      - from ≥2 DISTINCT experiments
   131	      - ≥1 of those strong supports is OOS or LIVE
   132	      - 0 strong contradictory evidence records
   133	    """
   134	    strong_support = [e for e in evidence
   135	                      if e.quality == EvidenceQuality.STRONG
   136	                      and e.direction == EvidenceDirection.SUPPORTS]
   137	    strong_contradict = [e for e in evidence
   138	                         if e.quality == EvidenceQuality.STRONG
   139	                         and e.direction == EvidenceDirection.CONTRADICTS]
   140	    oos_support = [e for e in strong_support
   141	                   if e.evidence_class in (EvidenceClass.OUT_OF_SAMPLE_TEST,
   142	                                           EvidenceClass.LIVE_OBSERVATION)]
   143	    distinct_experiments = len({e.experiment_id for e in strong_support})
   144	
   145	    promotable = (
   146	        not strong_contradict
   147	        and distinct_experiments >= 2
   148	        and len(oos_support) >= 1
   149	    )
   150	
   151	    return {
   152	        "strong_support": strong_support,
   153	        "strong_contradict": strong_contradict,
   154	        "oos_support": oos_support,
   155	        "distinct_experiments": distinct_experiments,
   156	        "promotable": promotable,
   157	    }
   158	
   159	
   160	
   161	class AutonomousRunner:
   162	    """Runs the full research loop autonomously."""
   163	
   164	    def __init__(self, base_dir: Path, exchange_id: str = "bitstamp") -> None:
   165	        self.base_dir = base_dir
   166	        self.state = StateStore(base_dir / ".atlas")
   167	        self.market = MarketData(cache_dir=base_dir / "data", exchange_id=exchange_id)
   168	        self.alt_data = AlternativeData(cache_dir=base_dir / "data")
   169	        self.events = EventStore(base_dir / "sessions")
   170	        self.graph_store = GraphStore(base_dir / "graph")
   171	        self.predictions = PredictionStore(base_dir / "predictions.jsonl")
   172	        self.methodology_log = base_dir / "methodology.jsonl"
   173	
   174	    def _save_obj(self, kind: str, obj_id: str, data: dict) -> None:
   175	        self.state.save(kind, obj_id, data)
   176	
   177	    def _load_obj(self, kind: str, obj_id: str) -> dict | None:
   178	        return self.state.load(kind, obj_id)
   179	
   180	    def _list_objs(self, kind: str) -> list[dict]:
   181	        return self.state.list_all(kind)
   182	
   183	    def _log_methodology(self, entry: dict) -> None:
   184	        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
   185	        with open(self.methodology_log, "a") as f:
   186	            f.write(json.dumps(entry, default=str) + "\n")
   187	
   188	    def _emit_telemetry(self, event_type: str, level: str = "info", details: dict | None = None) -> None:
   189	        """Append one event to the shared workspace telemetry stream."""
   190	        import uuid
   191	        event = {
   192	            "project": "atlas",
   193	            "source": "atlas.runner",
   194	            "eventType": event_type,
   195	            "level": level,
   196	            "sourceType": "system",
   197	            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
   198	            "id": str(uuid.uuid4()),
   199	        }
   200	        if details:
   201	            event["details"] = details
   202	        telemetry_path = self.TELEMETRY_PATH
   203	        try:
   204	            telemetry_path.parent.mkdir(parents=True, exist_ok=True)
   205	            with open(telemetry_path, "a") as f:
   206	                f.write(json.dumps(event, default=str) + "\n")
   207	        except Exception as exc:
   208	            log.warning("Failed to emit telemetry event %s: %s", event_type, exc)
   209	
   210	    def _find_existing_hypothesis(self, claim: str) -> Hypothesis | None:
   211	        """Find an existing hypothesis with the same claim."""
   212	        target_hash = _claim_hash(claim)
   213	        data = self._load_obj("hypotheses", target_hash)
   214	        if data:
   215	            return Hypothesis.model_validate(data)
   216	        return None
   217	
   218	    @staticmethod
   219	    def _parse_dataset_from_hypothesis(h: Hypothesis) -> tuple[str, str] | None:
   220	        """Parse (symbol, timeframe) from hypothesis tags.
   221	
   222	        Tag convention from `from_signal` and composite generators:
   223	        `['btc_usdt', '1h', ...]`. Pair/lead-lag generators emit two
   224	        `_usdt` tags (`['btc_usdt', 'eth_usdt', '1h', ...]`); we pick the
   225	        FIRST seen to be deterministic — the cycle's dataset selection
   226	        will iterate DEFAULT_UNIVERSE for cross-validation regardless.
   227	
   228	        Returns None when symbol or timeframe cannot be identified.
   229	        """
   230	        sym: str | None = None
   231	        tf: str | None = None
   232	        for tag in h.tags:
   233	            tag_lc = tag.lower()
   234	            if sym is None and tag_lc.endswith("_usdt"):
   235	                sym = tag.replace("_", "/").upper()
   236	            elif tf is None and tag_lc in ("1h", "4h", "1d", "1w"):
   237	                tf = tag_lc
   238	        if sym and tf:
   239	            return (sym, tf)
   240	        return None
   241	
   242	    @staticmethod
   243	    def _claim_is_permanently_infeasible(h: Hypothesis) -> bool:
   244	        """A claim is permanently INFEASIBLE only when it names a data
   245	        source we will never have access to from this deployment (geo-
   246	        blocked exchanges, perp/funding feeds we don't ingest).
   247	
   248	        Distinguishing claim-level infeasibility from environment-level
   249	        infeasibility is the whole point: INFEASIBLE is a one-way door
   250	        and must only be opened for properties of the claim itself, not
   251	        for transient deployment state like "DEFAULT_UNIVERSE doesn't
   252	        currently include 4h" or "Bitstamp only has 832 bars of SOL
   253	        right now". Those should leave the hypothesis FORMULATED so the
   254	        next cycle can re-evaluate when conditions change.
   255	        """
   256	        blob = (h.claim + " " + " ".join(h.tags)).lower()
   257	        return any(token in blob for token in INFEASIBLE_EXCHANGE_TOKENS)
   258	
   259	    def _data_currently_available(self, h: Hypothesis) -> bool:
   260	        """Reversible feasibility check: does this hypothesis have a
   261	        parseable (symbol, timeframe) in `DEFAULT_UNIVERSE` whose fetch
   262	        currently returns ≥ MIN_BARS_FOR_RESEARCH bars?
   263	
   264	        Returns False on any of: unparseable tags, off-universe pair,
   265	        fetch error, insufficient history. Caller MUST NOT use this as
   266	        an INFEASIBLE signal — these are all reversible.
   267	        """
   268	        parsed = self._parse_dataset_from_hypothesis(h)
   269	        if parsed is None:
   270	            return False
   271	        if parsed not in DEFAULT_UNIVERSE_SET:
   272	            return False
   273	        try:
   274	            df = self.market.fetch_ohlcv(symbol=parsed[0], timeframe=parsed[1], limit=100000)
   275	        except Exception:
   276	            return False
   277	        return len(df) >= MIN_BARS_FOR_RESEARCH
   278	
   279	    def _has_productive_universe_dataset(
   280	        self,
   281	        fresh_tested: set[tuple[str, str]],
   282	    ) -> tuple[str, str] | None:
   283	        """Return the first DEFAULT_UNIVERSE pair that is BOTH unfresh
   284	        AND has ≥ `MIN_BARS_FOR_RESEARCH` bars currently. None if no
   285	        universe dataset can produce a new experiment this cycle.
   286	
   287	        Used by `_include_orphaned_testing` to avoid re-including a
   288	        hypothesis whose only "unfresh" dataset has insufficient bars
   289	        (the SOL/USDT 1h case observed 2026-05-02). Without this check,
   290	        `re_included_productive` telemetry would be misleading —
   291	        hypotheses would burn slots and produce zero experiments,
   292	        exactly the failure mode the reviewer flagged.
   293	        """
   294	        for sym, tf in DEFAULT_UNIVERSE:
   295	            if (sym, tf) in fresh_tested:
   296	                continue
   297	            try:
   298	                df = self.market.fetch_ohlcv(symbol=sym, timeframe=tf, limit=100000)
   299	            except Exception:
   300	                continue
   301	            if len(df) >= MIN_BARS_FOR_RESEARCH:
   302	                return (sym, tf)
   303	        return None
   304	
   305	    def _include_orphaned_testing(self, current: list[Hypothesis]) -> list[Hypothesis]:
   306	        """Re-include TESTING-status hypotheses that can produce at least
   307	        one new experiment this cycle (an unfresh DEFAULT_UNIVERSE pair
   308	        with ≥ MIN_BARS_FOR_RESEARCH bars).
   309	
   310	        Without this, hypotheses promoted by `_top_up_from_formulated_pool`
   311	        are orphaned after one cycle: signal scans won't re-pick them
   312	        (parameter drift changes claim hashes), and the top-up path
   313	        only touches FORMULATED entries. The result observed 2026-05-02:
   314	        seven hypotheses promoted, one productive cycle, then 14+
   315	        consecutive empty cycles.
   316	
   317	        Order: this MUST run before `_top_up_from_formulated_pool`.
   318	        Reversed, the top-up fills the slot budget first and TESTING
   319	        starves forever — the dispatch handoff
   320	        `atlas-testing-reeval-p1-2026-05-02T16-48Z.md` requires this
   321	        invariant.
   322	
   323	        Slot budget shared via `TOP_UP_TARGET` so Bonferroni stays
   324	        bounded; the recompute in `run_cycle` covers the addition.
   325	
   326	        Hygiene gates (added per adversarial review):
   327	          - claim-permanently-infeasible TESTING entries (e.g. ingested
   328	            from research/ingest with BitMEX in claim, never migrated)
   329	            are skipped, NOT auto-migrated — auto-migration is an
   330	            ingest-contract decision out of scope for re-eval.
   331	          - "unfresh dataset exists" is not enough; we require
   332	            "unfresh dataset with ≥ MIN_BARS_FOR_RESEARCH bars".
   333	            Otherwise `re_included_productive` would be misleading and
   334	            operators would see `cycle.completed hypotheses_evaluated=0`
   335	            after `cycle.testing_reeval re_included_productive=N` and
   336	            assume a bug.
   337	        """
   338	        if len(current) >= TOP_UP_TARGET:
   339	            return current
   340	
   341	        current_ids = {h.id for h in current}
   342	        candidates: list[Hypothesis] = []
   343	        for record in self._list_objs("hypotheses"):
   344	            if record.get("status") != HypothesisStatus.TESTING.value:
   345	                continue
   346	            if record.get("id") in current_ids:
   347	                continue
   348	            try:
   349	                candidates.append(Hypothesis.model_validate(record))
   350	            except Exception as exc:
   351	                log.warning("Skipping malformed hypothesis record: %s", exc)
   352	                continue
   353	
   354	        candidates.sort(key=lambda c: c.id)
   355	
   356	        re_included_ids: list[str] = []
   357	        skipped_freshness_ids: list[str] = []
   358	        skipped_claim_infeasible_ids: list[str] = []
   359	        for h in candidates:
   360	            if len(current) >= TOP_UP_TARGET:
   361	                break
   362	            if self._claim_is_permanently_infeasible(h):
   363	                skipped_claim_infeasible_ids.append(h.id)
   364	                continue
   365	            existing_evidence = [
   366	                Evidence.model_validate(d)
   367	                for d in self._list_objs("evidence")
   368	                if d.get("hypothesis_id") == h.id
   369	            ]
   370	            fresh = self._fresh_tested_datasets(existing_evidence)
   371	            if self._has_productive_universe_dataset(fresh) is None:
   372	                # Either every universe dataset is fresh OR every
   373	                # unfresh one has insufficient bars. Either way no new
   374	                # experiment can run — don't burn a slot.
   375	                skipped_freshness_ids.append(h.id)
   376	                continue
   377	            current.append(h)
   378	            re_included_ids.append(h.id)
   379	
   380	        if candidates:
   381	            self._log_methodology({
   382	                "phase": "testing_reeval",
   383	                "re_included_productive": re_included_ids,
   384	                "skipped_no_productive_dataset": skipped_freshness_ids,
   385	                "skipped_claim_infeasible": skipped_claim_infeasible_ids,
   386	                "pool_size": len(candidates),
   387	                "current_size": len(current),
   388	            })
   389	            self._emit_telemetry(
   390	                "cycle.testing_reeval",
   391	                details={
   392	                    "re_included_productive": len(re_included_ids),
   393	                    "skipped_no_productive_dataset": len(skipped_freshness_ids),
   394	                    "skipped_claim_infeasible": len(skipped_claim_infeasible_ids),
   395	                    "pool_size": len(candidates),
   396	                    "current_size": len(current),
   397	                },
   398	            )
   399	        return current
   400	
   401	    def _top_up_from_formulated_pool(self, current: list[Hypothesis]) -> list[Hypothesis]:
   402	        """Promote currently-feasible FORMULATED hypotheses into the
   403	        cycle's test set; mark claim-permanently-infeasible ones as
   404	        INFEASIBLE; leave environmentally-blocked ones FORMULATED.
   405	
   406	        Single code path serving both the principal's A (auto-promote when
   407	        pool is starved) and D2 (STRICT fallback on empty signal scan)
   408	        decisions — A and D2 are the same operation viewed from two
   409	        symptoms (pool empty vs. signals absent). Conflating them avoids
   410	        the drift problem two near-duplicate methods would create.
   411	
   412	        Three outcomes per candidate:
   413	          - PROMOTED → status=TESTING, added to `current`.
   414	          - INFEASIBLE → status=INFEASIBLE (claim names a permanently-
   415	            blocked data source like BitMEX). One-way door.
   416	          - SKIPPED_NOT_PROMOTABLE → status stays FORMULATED. Reason is
   417	            environmental (off-universe, insufficient bars, unparseable
   418	            tags) so the next cycle can re-evaluate when conditions
   419	            change. Counted in telemetry but never persisted as
   420	            INFEASIBLE — that distinction matters because INFEASIBLE
   421	            permanently locks a hypothesis out of the loop.
   422	
   423	        Bonferroni for the cycle is recomputed by the caller; do not
   424	        stamp `_bonferroni_n` here.
   425	        """
   426	        current_ids = {h.id for h in current}
   427	        candidates: list[Hypothesis] = []
   428	        for record in self._list_objs("hypotheses"):
   429	            if record.get("status") != HypothesisStatus.FORMULATED.value:
   430	                continue
   431	            if record.get("id") in current_ids:
   432	                continue
   433	            try:
   434	                candidates.append(Hypothesis.model_validate(record))
   435	            except Exception as exc:
   436	                log.warning("Skipping malformed hypothesis record: %s", exc)
   437	                continue
   438	
   439	        # Deterministic ordering — sort by id so behavior is reproducible
   440	        # across runs and the audit log is stable.
   441	        candidates.sort(key=lambda c: c.id)
   442	
   443	        promoted_ids: list[str] = []
   444	        infeasible_ids: list[str] = []
   445	        skipped_ids: list[str] = []
   446	        for h in candidates:
   447	            # Permanent infeasibility is a property of the claim — always
   448	            # mark, even if `current` is already at target, so the pool
   449	            # gets cleaned up over successive cycles instead of needing
   450	            # multiple top-up triggers to clear stuck entries.
   451	            if self._claim_is_permanently_infeasible(h):
   452	                h.status = HypothesisStatus.INFEASIBLE
   453	                self._save_obj("hypotheses", h.id, h.model_dump())
   454	                infeasible_ids.append(h.id)
   455	                continue
   456	
   457	            # Stop promoting once the test set is at target — but keep
   458	            # iterating in case more INFEASIBLE entries need cleanup.
   459	            if len(current) >= TOP_UP_TARGET:
   460	                continue
   461	
   462	            try:
   463	                available = self._data_currently_available(h)
   464	            except Exception as exc:
   465	                log.warning("Feasibility check failed for %s: %s", h.id, exc)
   466	                skipped_ids.append(h.id)
   467	                continue
   468	            if not available:
   469	                # Reversible reason — leave FORMULATED for re-evaluation
   470	                # next cycle. Telemetry still records the skip so the
   471	                # frozen-loop monitor isn't blind to a "pool full of
   472	                # off-universe entries" failure mode.
   473	                skipped_ids.append(h.id)
   474	                continue
   475	
   476	            h.status = HypothesisStatus.TESTING
   477	            self._save_obj("hypotheses", h.id, h.model_dump())
   478	            current.append(h)
   479	            promoted_ids.append(h.id)
   480	
   481	        if candidates:  # always emit when the pool was non-empty
   482	            self._log_methodology({
   483	                "phase": "auto_top_up",
   484	                "promoted_from_formulated": promoted_ids,
   485	                "marked_infeasible": infeasible_ids,
   486	                "skipped_not_promotable": skipped_ids,
   487	                "pool_size": len(candidates),
   488	                "current_size": len(current),
   489	            })
   490	            self._emit_telemetry(
   491	                "cycle.top_up",
   492	                details={
   493	                    "promoted": len(promoted_ids),
   494	                    "infeasible": len(infeasible_ids),
   495	                    "skipped_not_promotable": len(skipped_ids),
   496	                    "pool_size": len(candidates),
   497	                    "current_size": len(current),
   498	                },
   499	            )
   500	        return current
   501	
   502	    def _find_active_cycle(self, hypothesis_id: str) -> ResearchCycle | None:
   503	        """Find an active cycle for a hypothesis."""
   504	        for data in self._list_objs("cycles"):
   505	            cycle = ResearchCycle.model_validate(data)
   506	            if cycle.hypothesis_id == hypothesis_id and cycle.status == CycleStatus.ACTIVE:
   507	                return cycle
   508	        return None
   509	
   510	    def _fresh_tested_datasets(
   511	        self,
   512	        existing_evidence: list[Evidence],
   513	        now: datetime | None = None,
   514	    ) -> set[tuple[str, str]]:
   515	        """Return datasets with recent evidence for the hypothesis."""
   516	        now = now or datetime.now(timezone.utc)
   517	        fresh: set[tuple[str, str]] = set()
   518	        newest_by_dataset: dict[tuple[str, str], datetime] = {}
   519	
   520	        for evidence in existing_evidence:
   521	            exp_data = self._load_obj("experiments", evidence.experiment_id)
   522	            if not exp_data:
   523	                continue
   524	            params = exp_data.get("parameters", {})
   525	            key = (params.get("symbol", ""), params.get("timeframe", ""))
   526	            if not all(key):
   527	                continue
   528	            created_at = evidence.created_at
   529	            if created_at.tzinfo is None:
   530	                created_at = created_at.replace(tzinfo=timezone.utc)
   531	            if key not in newest_by_dataset or created_at > newest_by_dataset[key]:
   532	                newest_by_dataset[key] = created_at
   533	
   534	        for key, created_at in newest_by_dataset.items():
   535	            if now - created_at < DATASET_RETEST_AFTER:
   536	                fresh.add(key)
   537	
   538	        return fresh
   539	
   540	    def scan_signals(self, oos_cutoff: float = 0.7) -> list[tuple[str, str, list, pd.DataFrame]]:
   541	        """Phase 1: Scan in-sample data only for signals.
   542	
   543	        Returns (symbol, timeframe, signals, full_df) tuples.
   544	        Signals are detected on the first 70% of data to avoid OOS contamination.
   545	        """
   546	        results = []
   547	        skipped_short: set[tuple[str, str]] = set()
   548	        for symbol, timeframe in DEFAULT_UNIVERSE:
   549	            try:
   550	                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=100000)
   551	                if len(df) < MIN_BARS_FOR_RESEARCH:
   552	                    skipped_short.add((symbol, timeframe))
   553	                    log.warning(
   554	                        "Skipping %s %s: %d bars < MIN_BARS_FOR_RESEARCH=%d",
   555	                        symbol, timeframe, len(df), MIN_BARS_FOR_RESEARCH,
   556	                    )
   557	                    self._log_methodology({
   558	                        "phase": "signal_intake",
   559	                        "symbol": symbol,
   560	                        "timeframe": timeframe,
   561	                        "skipped": "insufficient_history",
   562	                        "bars": len(df),
   563	                        "min_required": MIN_BARS_FOR_RESEARCH,
   564	                    })
   565	                    continue
   566	                split_idx = int(len(df) * oos_cutoff)
   567	                is_df = df.iloc[:split_idx]
   568	
   569	                # Scan signals on in-sample data ONLY
   570	                signals = scan_all(is_df)
   571	                if signals:
   572	                    results.append((symbol, timeframe, signals, df))
   573	                    log.info("Found %d signals for %s %s (in-sample scan)",
   574	                             len(signals), symbol, timeframe)
   575	                    self._log_methodology({
   576	                        "phase": "signal_intake",
   577	                        "symbol": symbol,
   578	                        "timeframe": timeframe,
   579	                        "n_signals": len(signals),
   580	                        "methods": list({s.method for s in signals}),
   581	                        "is_bars": split_idx,
   582	                        "total_bars": len(df),
   583	                    })
   584	            except Exception as e:
   585	                log.warning("Failed to scan %s %s: %s", symbol, timeframe, e)
   586	
   587	        # Cross-asset detectors: compare pairs at the same timeframe
   588	        is_data: dict[tuple[str, str], pd.DataFrame] = {}
   589	        for symbol, timeframe, _, df in results:
   590	            split_idx = int(len(df) * oos_cutoff)
   591	            is_data[(symbol, timeframe)] = df.iloc[:split_idx]
   592	
   593	        # Also load pairs not yet in results. Honor the min-bars gate here
   594	        # so cross-asset detectors don't pair a short dataset against a
   595	        # long one (would produce signals atlas then can't walk-forward).
   596	        for symbol, timeframe in DEFAULT_UNIVERSE:
   597	            if (symbol, timeframe) in is_data or (symbol, timeframe) in skipped_short:
   598	                continue
   599	            try:
   600	                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=100000)
   601	                if len(df) < MIN_BARS_FOR_RESEARCH:
   602	                    skipped_short.add((symbol, timeframe))
   603	                    continue
   604	                is_data[(symbol, timeframe)] = df.iloc[:int(len(df) * oos_cutoff)]
   605	            except Exception:
   606	                pass
   607	
   608	        timeframes_seen = set()
   609	        for (sym, tf) in is_data:
   610	            timeframes_seen.add(tf)
   611	
   612	        cross_signals = []
   613	        for tf in timeframes_seen:
   614	            pairs_at_tf = [(sym, df) for (sym, t), df in is_data.items() if t == tf]
   615	            for i, (sym_a, df_a) in enumerate(pairs_at_tf):
   616	                for sym_b, df_b in pairs_at_tf[i + 1:]:
   617	                    cross_signals.extend(detect_cross_asset_spread(
   618	                        df_a["close"], df_b["close"], sym_a, sym_b,
   619	                    ))
   620	                    ret_a = df_a["close"].pct_change().dropna()
   621	                    ret_b = df_b["close"].pct_change().dropna()
   622	                    cross_signals.extend(detect_lead_lag(ret_a, ret_b, sym_a, sym_b))
   623	                    cross_signals.extend(detect_lead_lag(ret_b, ret_a, sym_b, sym_a))
   624	
   625	        # Composite signals: multi-source (sentiment, on-chain, mining + price)
   626	        composite_signals = []
   627	        try:
   628	            alt_sources = self.alt_data.fetch_all()
   629	            if alt_sources:
   630	                for symbol, timeframe, _, df in results:
   631	                    split_idx = int(len(df) * oos_cutoff)
   632	                    is_prices = df["close"].iloc[:split_idx]
   633	                    csigs = scan_composite(is_prices, alt_sources)
   634	                    for s in csigs:
   635	                        s.symbol = symbol
   636	                        s.timeframe = timeframe
   637	                    composite_signals.extend(csigs)
   638	                log.info("Found %d composite signals from %d alt sources",
   639	                         len(composite_signals), len(alt_sources))
   640	        except Exception as e:
   641	            log.warning("Composite signal scan failed: %s", e)
   642	
   643	        # Calendar signals: temporal patterns (EOM, weekend, US session)
   644	        calendar_signals = []
   645	        for symbol, timeframe, _, df in results:
   646	            split_idx = int(len(df) * oos_cutoff)
   647	            is_prices = df["close"].iloc[:split_idx]
   648	            csigs = scan_calendar(is_prices)
   649	            for s in csigs:
   650	                s.symbol = symbol
   651	                s.timeframe = timeframe
   652	            calendar_signals.extend(csigs)
   653	        if calendar_signals:
   654	            log.info("Found %d calendar signals", len(calendar_signals))
   655	        composite_signals.extend(calendar_signals)
   656	
   657	        extra_signals = cross_signals + composite_signals
   658	        if extra_signals:
   659	            # Attach extra signals to the BTC/USDT 1h anchor
   660	            anchor = ("BTC/USDT", "1h")
   661	            anchor_found = False
   662	            for idx, (sym, tf, sigs, df) in enumerate(results):
   663	                if (sym, tf) == anchor:
   664	                    results[idx] = (sym, tf, sigs + extra_signals, df)
   665	                    anchor_found = True
   666	                    break
   667	            if not anchor_found and results:
   668	                sym, tf, sigs, df = results[0]
   669	                results[0] = (sym, tf, sigs + extra_signals, df)
   670	            log.info("Found %d cross-asset + %d composite signals",
   671	                     len(cross_signals), len(composite_signals))
   672	
   673	        return results
   674	
   675	    def generate_hypotheses(self, signal_results: list[tuple[str, str, list, pd.DataFrame]]) -> list[Hypothesis]:
   676	        """Phase 2: Convert signals into hypotheses. Reuse existing hypothesis IDs."""
   677	        candidates: list[tuple[Hypothesis, str]] = []  # (hypothesis, source_method)
   678	
   679	        for symbol, timeframe, signals, _ in signal_results:
   680	            for signal in signals:
   681	                # Try composite generators first, then single-source
   682	                gen = COMPOSITE_GENERATORS.get(signal.method)
   683	                if gen:
   684	                    sym = signal.symbol or symbol
   685	                    tf = signal.timeframe or timeframe
   686	                    candidates.append((gen(signal, sym, tf), signal.method))
   687	                else:
   688	                    h = from_signal(signal, symbol, timeframe)
   689	                    if h:
   690	                        candidates.append((h, signal.method))
   691	
   692	        # Graph-driven generation
   693	        graph = self.graph_store.load()
   694	        gap_hypotheses = from_graph_gaps(graph)
   695	        candidates.extend([(h, "graph_gaps") for h in gap_hypotheses])
   696	
   697	        # Deduplicate and resolve to durable IDs
   698	        seen_claims: set[str] = set()
   699	        unique: list[tuple[Hypothesis, str]] = []
   700	        for h, method in candidates:
   701	            if h.claim in seen_claims:
   702	                continue
   703	            seen_claims.add(h.claim)
   704	
   705	            # Check for existing hypothesis with same claim
   706	            existing = self._find_existing_hypothesis(h.claim)
   707	            if existing:
   708	                if existing.status in (HypothesisStatus.PROMOTED, HypothesisStatus.FALSIFIED):
   709	                    log.debug("Skipping already-resolved hypothesis: %s", existing.id)
   710	                    continue
   711	                unique.append((existing, method))
   712	            else:
   713	                # Assign stable ID from claim hash
   714	                h.id = _claim_hash(h.claim)
   715	                unique.append((h, method))
   716	
   717	        # Prioritize: calendar > composite > single-source, break ties by method promotion weight
   718	        method_weights = self.compute_method_weights()
   719	
   720	        def _score(item: tuple[Hypothesis, str]) -> float:
   721	            h, method = item
   722	            base = 0.0
   723	            if "calendar" in h.tags:
   724	                base = 2.0
   725	            elif "composite" in h.tags:
   726	                base = 1.0
   727	            return base + method_weights.get(method, 0.5)
   728	
   729	        prioritized = sorted(unique, key=_score, reverse=True)
   730	        selected_pairs = prioritized[:5]
   731	        selected = [h for h, _ in selected_pairs]
   732	
   733	        # Apply Bonferroni correction: compute adjusted alpha per cycle
   734	        # but do NOT mutate h.significance_threshold (pre-registered, immutable)
   735	        # Store on each hypothesis object for this cycle (not persisted on model)
   736	        n_tests = max(1, len(selected))
   737	        for h in selected:
   738	            h._bonferroni_n = n_tests  # type: ignore[attr-defined]
   739	
   740	        # Log method → hypothesis_id attribution for future weight computation
   741	        method_hypothesis_ids: dict[str, list[str]] = {}
   742	        for h, method in selected_pairs:
   743	            method_hypothesis_ids.setdefault(method, []).append(h.id)
   744	
   745	        self._log_methodology({
   746	            "phase": "hypothesis_generation",
   747	            "total_generated": len(candidates),
   748	            "unique": len(unique),
   749	            "selected": len(selected),
   750	            "bonferroni_n": n_tests,
   751	            "adjusted_alpha": (selected[0].significance_threshold / n_tests) if selected else None,
   752	        })
   753	        self._log_methodology({
   754	            "phase": "hypothesis_sources",
   755	            "method_hypothesis_ids": method_hypothesis_ids,
   756	        })
   757	
   758	        return selected
   759	
   760	    def compute_method_weights(self) -> dict[str, float]:
   761	        """Read methodology.jsonl to compute per-method promotion rate.
   762	
   763	        Uses Laplace smoothing: (promotions + 1) / (promotions + kills + 2).
   764	        Methods with no history get 0.5 (neutral). Reads hypothesis_sources
   765	        records to map method → hypothesis_id, then decision records for outcomes.
   766	        """
   767	        if not self.methodology_log.exists():
   768	            return {}
   769	
   770	        method_to_hyps: dict[str, set[str]] = {}
   771	        hyp_outcomes: dict[str, str] = {}
   772	
   773	        with open(self.methodology_log) as f:
   774	            for line in f:
   775	                line = line.strip()
   776	                if not line:
   777	                    continue
   778	                try:
   779	                    rec = json.loads(line)
   780	                except json.JSONDecodeError:
   781	                    continue
   782	                phase = rec.get("phase", "")
   783	                if phase == "hypothesis_sources":
   784	                    for method, ids in rec.get("method_hypothesis_ids", {}).items():
   785	                        method_to_hyps.setdefault(method, set()).update(ids)
   786	                elif phase == "decision":
   787	                    hid = rec.get("hypothesis_id")
   788	                    action = rec.get("action")
   789	                    if hid and action:
   790	                        hyp_outcomes[hid] = action
   791	
   792	        weights: dict[str, float] = {}
   793	        for method, hyp_ids in method_to_hyps.items():
   794	            promotes = sum(1 for hid in hyp_ids if hyp_outcomes.get(hid) == "promote")
   795	            kills = sum(1 for hid in hyp_ids if hyp_outcomes.get(hid) == "kill")
   796	            weights[method] = (promotes + 1) / (promotes + kills + 2)
   797	
   798	        return weights
   799	
   800	    def _build_composite_signal(self, h: Hypothesis, is_df: pd.DataFrame) -> pd.Series | None:
   801	        """Build regime-holding signal from composite hypothesis.
   802	
   803	        Returns None if required alt data is unavailable.
   804	        These signals trade rarely — enter on trigger, hold for N bars, then flat.
   805	        """
   806	        prices = is_df["close"]
   807	        holding = 20
   808	        for tag in h.tags:
   809	            if tag.startswith("hold_"):
   810	                holding = int(tag.split("_")[1])
   811	
   812	        try:
   813	            alt_sources = self.alt_data.fetch_all()
   814	        except Exception:
   815	            return None
   816	
   817	        signals = pd.Series(0, index=prices.index)
   818	
   819	        if "fear_capitulation" in h.tags:
   820	            fg = alt_sources.get("fear_greed")
   821	            if fg is None or "fear_greed" not in fg.columns:
   822	                return None
   823	            fg_aligned = fg["fear_greed"].reindex(prices.index, method="ffill").fillna(50)
   824	            rolling_high = prices.rolling(60).max()
   825	            drawdown = (prices - rolling_high) / rolling_high
   826	            trigger = (fg_aligned < 25) & (drawdown < -0.10)
   827	            signals = self._apply_regime_hold(trigger, holding, direction=1)
   828	
   829	        elif "greed_euphoria" in h.tags:
   830	            fg = alt_sources.get("fear_greed")
   831	            if fg is None or "fear_greed" not in fg.columns:
   832	                return None
   833	            fg_aligned = fg["fear_greed"].reindex(prices.index, method="ffill").fillna(50)
   834	            rolling_low = prices.rolling(60).min()
   835	            rally = (prices - rolling_low) / rolling_low
   836	            trigger = (fg_aligned > 75) & (rally > 0.15)
   837	            signals = self._apply_regime_hold(trigger, holding, direction=-1)
   838	
   839	        elif "onchain_divergence" in h.tags:
   840	            ov = alt_sources.get("onchain_volume")
   841	            if ov is None or "onchain_volume_usd" not in ov.columns:
   842	                return None
   843	            ov_aligned = ov["onchain_volume_usd"].reindex(prices.index, method="ffill")
   844	            px_trend = prices.pct_change(20)
   845	            ov_trend = ov_aligned.pct_change(20)
   846	            if "bullish" in h.tags:
   847	                trigger = (px_trend < -0.10) & (ov_trend > 0.10)
   848	                signals = self._apply_regime_hold(trigger, holding, direction=1)
   849	            else:
   850	                trigger = (px_trend > 0.10) & (ov_trend < -0.10)
   851	                signals = self._apply_regime_hold(trigger, holding, direction=-1)
   852	
   853	        elif "miner_capitulation" in h.tags:
   854	            hr = alt_sources.get("hashrate")
   855	            if hr is None or "hashrate" not in hr.columns:
   856	                return None
   857	            hr_aligned = hr["hashrate"].reindex(prices.index, method="ffill")
   858	            hr_peak = hr_aligned.rolling(30).max()
   859	            hr_dd = (hr_aligned - hr_peak) / hr_peak
   860	            was_down = hr_dd.rolling(30).min() < -0.10
   861	            recovering = hr_dd > -0.03
   862	            trigger = was_down & recovering & (~(was_down & recovering).shift(1).fillna(False))
   863	            signals = self._apply_regime_hold(trigger, holding, direction=1)
   864	
   865	        elif "end_of_month" in h.tags:
   866	            # Short last 3 days of month if negative drift, long if positive
   867	            dom = prices.index.day
   868	            eom_mask = pd.Series(dom >= 29, index=prices.index)
   869	            direction = -1 if "negative" in h.tags else 1
   870	            signals = pd.Series(0, index=prices.index)
   871	            signals.loc[eom_mask] = direction
   872	            return signals
   873	
   874	        elif "weekend_skip" in h.tags:
   875	            # Long only on weekdays, flat on weekends
   876	            dow = prices.index.dayofweek
   877	            weekday_mask = pd.Series(dow < 5, index=prices.index)
   878	            signals = pd.Series(0, index=prices.index)
   879	            signals.loc[weekday_mask] = 1
   880	            return signals
   881	
   882	        elif "us_session" in h.tags:
   883	            # Long only during US session (13:00-21:00 UTC)
   884	            hour = prices.index.hour
   885	            us_mask = pd.Series((hour >= 13) & (hour < 21), index=prices.index)
   886	            signals = pd.Series(0, index=prices.index)
   887	            signals.loc[us_mask] = 1
   888	            return signals
   889	
   890	        elif "regime_confluence" in h.tags:
   891	            fg = alt_sources.get("fear_greed")
   892	            ov = alt_sources.get("onchain_volume")
   893	            if fg is None or ov is None:
   894	                return None
   895	            fg_aligned = fg["fear_greed"].reindex(prices.index, method="ffill").fillna(50)
   896	            ov_aligned = ov["onchain_volume_usd"].reindex(prices.index, method="ffill")
   897	            ov_trend = ov_aligned.pct_change(20)
   898	            if "bullish" in h.tags:
   899	                px_low = prices.rolling(60).min()
   900	                trigger = (fg_aligned < 25) & (ov_trend > 0.05) & (prices <= px_low * 1.05)
   901	                signals = self._apply_regime_hold(trigger, holding, direction=1)
   902	            else:
   903	                px_high = prices.rolling(60).max()
   904	                trigger = (fg_aligned > 75) & (ov_trend < -0.05) & (prices >= px_high * 0.95)
   905	                signals = self._apply_regime_hold(trigger, holding, direction=-1)
   906	        else:
   907	            return None
   908	
   909	        return signals.reindex(prices.index).fillna(0)
   910	
   911	    @staticmethod
   912	    def _apply_regime_hold(trigger: pd.Series, holding_period: int, direction: int) -> pd.Series:
   913	        """Convert trigger events into held positions.
   914	
   915	        Enter on trigger, hold for holding_period bars, then go flat.
   916	        If a new trigger fires during a hold, extend the hold.
   917	        This produces sparse signals — only a few trades per year.
   918	        """
   919	        signals = pd.Series(0, index=trigger.index)
   920	        bars_remaining = 0
   921	        for i in range(len(trigger)):
   922	            if trigger.iloc[i]:
   923	                bars_remaining = holding_period
   924	            if bars_remaining > 0:
   925	                signals.iloc[i] = direction
   926	                bars_remaining -= 1
   927	        return signals
   928	
   929	    def _build_signal_from_hypothesis(self, h: Hypothesis, is_df: pd.DataFrame) -> pd.Series:
   930	        """Build a trading signal series using in-sample data only."""
   931	        # Try composite signal builder first
   932	        if "composite" in h.tags:
   933	            composite = self._build_composite_signal(h, is_df)
   934	            if composite is not None:
   935	                return composite
   936	
   937	        prices = is_df["close"]
   938	        returns = prices.pct_change().dropna()
   939	
   940	        if "autocorrelation" in h.tags:
   941	            lag = 1
   942	            for tag in h.tags:
   943	                if tag.startswith("lag_"):
   944	                    lag = int(tag.split("_")[1])
   945	            if "momentum" in h.tags:
   946	                signals = (returns.rolling(lag).mean() > 0).astype(int).replace(0, -1)
   947	            else:
   948	                signals = (returns.rolling(lag).mean() < 0).astype(int).replace(0, -1)
   949	        elif "momentum" in h.tags and any(t.startswith("lookback_") for t in h.tags):
   950	            lookback = 20
   951	            for tag in h.tags:
   952	                if tag.startswith("lookback_"):
   953	                    lookback = int(tag.split("_")[1])
   954	            rolling_ret = returns.rolling(lookback).sum()
   955	            if "reversal" in h.tags:
   956	                signals = -(rolling_ret > 0).astype(int).replace(0, -1)
   957	            else:
   958	                signals = (rolling_ret > 0).astype(int).replace(0, -1)
   959	        elif "vol_scaling" in h.tags:
   960	            # Volatility-scaled strategy: reduce position in high-vol, increase in low-vol
   961	            vol = returns.abs().rolling(20).mean()
   962	            vol_ma = vol.rolling(50).mean()
   963	            vol_ratio = (vol / vol_ma).reindex(prices.index).fillna(1.0)
   964	            signals = pd.Series(1, index=prices.index)  # default long
   965	            signals.loc[vol_ratio > 1.5] = 0    # step out in high vol
   966	            signals.loc[vol_ratio < 0.7] = 1    # full position in low vol
   967	        elif "pairs_trading" in h.tags:
   968	            # Pairs trading: use price z-score as proxy for spread dislocation
   969	            ma = prices.rolling(50).mean()
   970	            std = prices.rolling(50).std()
   971	            z = ((prices - ma) / std).reindex(prices.index).fillna(0)
   972	            signals = pd.Series(0, index=prices.index)
   973	            signals.loc[z < -1.5] = 1   # buy when spread is low
   974	            signals.loc[z > 1.5] = -1   # sell when spread is high
   975	        elif "lead_lag" in h.tags:
   976	            # Lead-lag: trade the follower based on the leader's return
   977	            # Since we only have the follower's data here, use its own lagged returns
   978	            # as a proxy (the signal builder gets the follower's data)
   979	            lag_ret = returns.shift(1).reindex(prices.index).fillna(0)
   980	            signals = pd.Series(0, index=prices.index)
   981	            signals.loc[lag_ret > 0] = 1
   982	            signals.loc[lag_ret < 0] = -1
   983	        elif "skew" in h.tags:
   984	            # Skew strategy: positive skew → buy dips, negative skew → fade rallies
   985	            ma = prices.rolling(20).mean()
   986	            std = prices.rolling(20).std()
   987	            z = (prices - ma) / std
   988	            signals = pd.Series(0, index=prices.index)
   989	            if "positive" in h.tags:
   990	                # Buy when below MA (dips), expecting asymmetric upside
   991	                signals[z < -1.0] = 1
   992	            else:
   993	                # Sell when above MA (rallies), expecting mean reversion / crash
   994	                signals[z > 1.0] = -1
   995	        elif "mean_reversion" in h.tags:
   996	            window = 20
   997	            for tag in h.tags:
   998	                if tag.startswith("ma_"):
   999	                    window = int(tag.split("_")[1])
  1000	            ma = prices.rolling(window).mean()
  1001	            std = prices.rolling(window).std()
  1002	            z = (prices - ma) / std
  1003	            signals = pd.Series(0, index=prices.index)
  1004	            signals[z < -2.0] = 1
  1005	            signals[z > 2.0] = -1
  1006	        elif "volatility" in h.tags or "regime" in h.tags:
  1007	            vol = returns.rolling(20).std()
  1008	            vol_ma = vol.rolling(50).mean()
  1009	            signals = pd.Series(0, index=prices.index)
  1010	            signals[vol < vol_ma * 0.7] = 1
  1011	            signals[vol > vol_ma * 1.5] = -1
  1012	        elif "volume" in h.tags:
  1013	            if "volume" in is_df.columns:
  1014	                vol_z = (is_df["volume"] - is_df["volume"].rolling(20).mean()) / is_df["volume"].rolling(20).std()
  1015	                ret_dir = returns.rolling(3).mean()
  1016	                signals = pd.Series(0, index=prices.index)
  1017	                mask = vol_z > 3.0
  1018	                signals[mask & (ret_dir > 0)] = 1
  1019	                signals[mask & (ret_dir < 0)] = -1
  1020	            else:
  1021	                signals = pd.Series(0, index=prices.index)
  1022	        else:
  1023	            signals = (prices.pct_change(20) > 0).astype(int).replace(0, -1)
  1024	
  1025	        return signals
  1026	
  1027	    def run_experiment(self, h: Hypothesis, df: pd.DataFrame, symbol: str, timeframe: str) -> tuple[Experiment, Evidence | None]:
  1028	        """Phase 3: Design, execute, and evaluate an experiment.
  1029	
  1030	        Walk-forward evaluation only: the harness does NOT fit state on the
  1031	        training window (see walk_forward_backtest docstring). All current
  1032	        signal builders are stateless rolling indicators whose no-lookahead
  1033	        guarantee comes from past-anchored windows, not from train/test
  1034	        separation. Trainable signals would require extending the harness.
  1035	        """
  1036	        tf_periods = {"1h": 365 * 24, "4h": 365 * 6, "1d": 365, "1w": 52}
  1037	        periods_per_year = tf_periods.get(timeframe, 365 * 6)
  1038	
  1039	        # Bonferroni-adjusted alpha: persisted on the experiment so it survives restarts
  1040	        bonferroni_n = getattr(h, "_bonferroni_n", 1)
  1041	        adjusted_alpha = h.significance_threshold / bonferroni_n
  1042	
  1043	        exp = Experiment(
  1044	            hypothesis_id=h.id,
  1045	            description=f"Backtest {h.claim[:80]} on {symbol} {timeframe}",
  1046	            method="backtest",
  1047	            parameters={
  1048	                "symbol": symbol, "timeframe": timeframe, "lookback": len(df),
  1049	                "bonferroni_n": bonferroni_n, "adjusted_alpha": adjusted_alpha,
  1050	            },
  1051	            success_criteria=f"OOS Sharpe > 0 with p < {adjusted_alpha:.4f} (Bonferroni-adjusted)",
  1052	            failure_criteria=f"OOS Sharpe not significantly different from zero (p >= {adjusted_alpha:.4f})",
  1053	        )
  1054	        self._save_obj("experiments", exp.id, exp.model_dump())
  1055	
  1056	        try:
  1057	            # Walk-forward validation: expanding train window with 5 OOS folds
  1058	            signal_builder = lambda sub_df: self._build_signal_from_hypothesis(h, sub_df)
  1059	            wf = walk_forward_backtest(
  1060	                df, signal_builder,
  1061	                n_folds=5, train_ratio=0.7,
  1062	                periods_per_year=periods_per_year, fee_bps=26,
  1063	            )
  1064	
  1065	            # Statistical tests on concatenated OOS returns with Bonferroni-adjusted alpha
  1066	            alpha = adjusted_alpha
  1067	            oos_sharpe = sharpe_significance(wf.oos_returns, periods_per_year=periods_per_year, alpha=alpha)
  1068	            oos_mean = mean_return_test(wf.oos_returns, alpha=alpha)
  1069	            oos_boot = bootstrap_sharpe(wf.oos_returns, periods_per_year=periods_per_year, alpha=alpha)
  1070	
  1071	            exp.status = ExperimentStatus.COMPLETED
  1072	            exp.results = {
  1073	                "walk_forward": {
  1074	                    "n_folds": wf.n_folds,
  1075	                    "mean_oos_sharpe": wf.aggregate_oos_sharpe,
  1076	                    "folds": wf.folds,
  1077	                },
  1078	                "out_of_sample": {
  1079	                    "sharpe": wf.aggregate_oos_sharpe,
  1080	                    "total_return": float((1 + wf.oos_returns).prod() - 1),
  1081	                    "sharpe_p": oos_sharpe.p_value,
  1082	                    "mean_p": oos_mean.p_value,
  1083	                    "bootstrap_ci": [oos_boot.ci_lower, oos_boot.ci_upper],
  1084	                    "bonferroni_alpha": alpha,
  1085	                },
  1086	            }
  1087	            self._save_obj("experiments", exp.id, exp.model_dump())
  1088	
  1089	            # Evaluate evidence quality
  1090	            oos = exp.results["out_of_sample"]
  1091	            # Require BOTH sharpe and bootstrap to agree for strong
  1092	            both_significant = oos_sharpe.significant and oos_boot.significant
  1093	            is_positive = wf.aggregate_oos_sharpe > 0
  1094	
  1095	            if both_significant and is_positive:
  1096	                quality = EvidenceQuality.STRONG
  1097	                direction = EvidenceDirection.SUPPORTS
  1098	            elif is_positive and (oos_sharpe.significant or oos_boot.significant):
  1099	                quality = EvidenceQuality.MODERATE
  1100	                direction = EvidenceDirection.SUPPORTS
  1101	            elif wf.aggregate_oos_sharpe < -0.5 and both_significant:
  1102	                quality = EvidenceQuality.STRONG
  1103	                direction = EvidenceDirection.CONTRADICTS
  1104	            elif not is_positive and (oos_sharpe.p_value < 0.15 or oos_boot.p_value < 0.15):
  1105	                quality = EvidenceQuality.MODERATE
  1106	                direction = EvidenceDirection.CONTRADICTS
  1107	            else:
  1108	                quality = EvidenceQuality.WEAK
  1109	                direction = EvidenceDirection.INCONCLUSIVE
  1110	
  1111	            ev = Evidence(
  1112	                experiment_id=exp.id,
  1113	                hypothesis_id=h.id,
  1114	                evidence_class=EvidenceClass.OUT_OF_SAMPLE_TEST,
  1115	                quality=quality,
  1116	                direction=direction,
  1117	                summary=f"Walk-forward OOS Sharpe={wf.aggregate_oos_sharpe:.2f} ({wf.n_folds} folds, "
  1118	                        f"p={oos_sharpe.p_value:.3f}, α={alpha:.4f}). "
  1119	                        f"Bootstrap CI=[{oos_boot.ci_lower:.2f}, {oos_boot.ci_upper:.2f}]",
  1120	                statistics=oos,
  1121	            )
  1122	            self._save_obj("evidence", ev.id, ev.model_dump())
  1123	
  1124	            log.info("Experiment %s: WF OOS Sharpe=%.2f (%d folds) p=%.3f (α=%.4f) → %s %s",
  1125	                     exp.id, wf.aggregate_oos_sharpe, wf.n_folds, oos_sharpe.p_value, alpha,
  1126	                     quality.value, direction.value)
  1127	
  1128	            return exp, ev
  1129	
  1130	        except Exception as e:
  1131	            log.error("Experiment %s failed: %s", exp.id, e)
  1132	            exp.status = ExperimentStatus.FAILED
  1133	            exp.results = {"error": str(e)}
  1134	            self._save_obj("experiments", exp.id, exp.model_dump())
  1135	            return exp, None
  1136	
  1137	    def evaluate_and_decide(self, h: Hypothesis, cycle: ResearchCycle) -> str:
  1138	        """Phase 4-5: Evaluate accumulated evidence and decide.
  1139	
  1140	        Promotion requires:
  1141	        - ≥2 strong supporting evidence from DISTINCT experiments
  1142	        - ≥1 must be OOS or live
  1143	        - No unaddressed strong contradictory evidence
  1144	        """
  1145	        evidence = [Evidence.model_validate(d) for d in self._list_objs("evidence")
  1146	                    if d.get("hypothesis_id") == h.id]
  1147	
  1148	        if not evidence:
  1149	            return "continue"
  1150	
  1151	        gate = evaluate_promotion_gate(evidence)
  1152	        strong_support = gate["strong_support"]
  1153	        strong_contradict = gate["strong_contradict"]
  1154	        oos_support = gate["oos_support"]
  1155	        distinct_experiments = gate["distinct_experiments"]
  1156	
  1157	        # Kill if strong contradictory evidence
  1158	        if len(strong_contradict) >= 2:
  1159	            h.status = HypothesisStatus.FALSIFIED
  1160	            self._save_obj("hypotheses", h.id, h.model_dump())
  1161	            self._add_refuted_claim_to_graph(h, evidence)
  1162	            cycle.status = CycleStatus.CLOSED
  1163	            cycle.outcome = CycleOutcome.KILLED
  1164	            cycle.decision_rationale = f"Falsified: {len(strong_contradict)} strong contradictory evidence records"
  1165	            self._save_obj("cycles", cycle.id, cycle.model_dump())
  1166	            self.events.append(SessionEvent(
  1167	                session_id=cycle.id,
  1168	                event_type=EventType.DECISION_MADE,
  1169	                details={"action": "kill", "reason": cycle.decision_rationale},
  1170	            ))
  1171	            return "kill"
  1172	
  1173	        # Block promotion if ANY strong contradictory evidence exists
  1174	        if strong_contradict:
  1175	            log.info("Hypothesis %s has %d strong contradictions — cannot promote",
  1176	                     h.id, len(strong_contradict))
  1177	            return "continue"
  1178	
  1179	        # Promote if gate is met with distinct experiments
  1180	        if distinct_experiments >= 2 and len(oos_support) >= 1:
  1181	            primitive = ReasoningPrimitive(
  1182	                claim=h.claim,
  1183	                hypothesis_id=h.id,
  1184	                evidence_ids=[e.id for e in strong_support],
  1185	                confidence=min(0.95, 0.5 + 0.15 * distinct_experiments),
  1186	                tags=h.tags,
  1187	                causal_parents=[h.parent_primitive_id] if h.parent_primitive_id else [],
  1188	            )
  1189	            self._save_obj("primitives", primitive.id, primitive.model_dump())
  1190	
  1191	            graph = self.graph_store.load()
  1192	            try:
  1193	                graph.add_primitive(primitive)
  1194	            except ValueError as e:
  1195	                log.warning("Could not link parent: %s — adding as root", e)
  1196	                primitive.causal_parents = []
  1197	                graph.add_primitive(primitive)
  1198	            self.graph_store.save(graph)
  1199	
  1200	            h.status = HypothesisStatus.PROMOTED
  1201	            self._save_obj("hypotheses", h.id, h.model_dump())
  1202	            cycle.status = CycleStatus.CLOSED
  1203	            cycle.outcome = CycleOutcome.PROMOTED
  1204	            cycle.decision_rationale = (
  1205	                f"Promoted: {distinct_experiments} distinct strong experiments, "
  1206	                f"{len(oos_support)} OOS. Graph: {graph.node_count} nodes."
  1207	            )
  1208	            self._save_obj("cycles", cycle.id, cycle.model_dump())
  1209	            self.events.append(SessionEvent(
  1210	                session_id=cycle.id,
  1211	                event_type=EventType.PRIMITIVE_PROMOTED,
  1212	                details={"primitive_id": primitive.id, "claim": h.claim},
  1213	            ))
  1214	            self._log_methodology({
  1215	                "phase": "decision", "hypothesis_id": h.id, "action": "promote",
  1216	                "primitive_id": primitive.id, "graph_nodes": graph.node_count,
  1217	            })
  1218	            return "promote"
  1219	
  1220	        # Kill if all evidence is weak/contradictory after enough attempts
  1221	        all_weak_or_negative = all(
  1222	            e.direction != EvidenceDirection.SUPPORTS or e.quality == EvidenceQuality.WEAK
  1223	            for e in evidence
  1224	        )
  1225	        if all_weak_or_negative and len(evidence) >= 3:
  1226	            h.status = HypothesisStatus.FALSIFIED
  1227	            self._save_obj("hypotheses", h.id, h.model_dump())
  1228	            self._add_refuted_claim_to_graph(h, evidence)
  1229	            cycle.status = CycleStatus.CLOSED
  1230	            cycle.outcome = CycleOutcome.KILLED
  1231	            cycle.decision_rationale = f"Killed: {len(evidence)} evidence records, none strong/supporting"
  1232	            self._save_obj("cycles", cycle.id, cycle.model_dump())
  1233	            self.events.append(SessionEvent(
  1234	                session_id=cycle.id,
  1235	                event_type=EventType.DECISION_MADE,
  1236	                details={"action": "kill", "reason": cycle.decision_rationale},
  1237	            ))
  1238	            return "kill"
  1239	
  1240	        return "continue"
  1241	
  1242	    def _add_refuted_claim_to_graph(self, h: Hypothesis, evidence: list[Evidence]) -> None:
  1243	        """Project a killed hypothesis into the causal map as tested negative knowledge."""
  1244	        graph = self.graph_store.load()
  1245	        contradiction_count = sum(
  1246	            1
  1247	            for e in evidence
  1248	            if e.quality == EvidenceQuality.STRONG
  1249	            and e.direction == EvidenceDirection.CONTRADICTS
  1250	        )
  1251	        graph.add_refuted_hypothesis(
  1252	            h,
  1253	            [e.id for e in evidence],
  1254	            contradiction_count=contradiction_count,
  1255	        )
  1256	        self.graph_store.save(graph)
  1257	
  1258	    def register_predictions(self, signal_results, now: datetime | None = None) -> dict:
  1259	        """Register dated forward predictions for currently-detected signals.
  1260	
  1261	        Each detected pattern implies a forward forecast: net of fees, does it
  1262	        predict forward returns? One prediction per (claim, horizon bucket) keeps
  1263	        the hourly cycle idempotent and the windows non-overlapping; the scorer
  1264	        (2b) resolves them against realized data once the window closes. This is
  1265	        the un-exhaustible evidence path (CAUSAL_LOOP_AUDIT.md Q5) — it runs every
  1266	        cycle regardless of whether the backtest hypothesis space is exhausted.
  1267	        """
  1268	        now = now or datetime.now(timezone.utc)
  1269	        bucket, window_start, resolve = Prediction.forward_bucket(now, PREDICTION_HORIZON_DAYS)
  1270	        existing = {p.id for p in self.predictions.all()}
  1271	        registered = 0
  1272	        skipped_unreplayable = 0
  1273	        seen: set[str] = set()
  1274	        for symbol, timeframe, signals, _ in signal_results:
  1275	            for signal in signals:
  1276	                # Only forward-score strategies that reconstruct faithfully from
  1277	                # the frozen (symbol, timeframe, tags) spec. Proxy/fallback types
  1278	                # would produce meaningless live_observation evidence.
  1279	                if signal.method not in REPLAYABLE_METHODS:
  1280	                    skipped_unreplayable += 1
  1281	                    continue
  1282	                h = from_signal(signal, symbol, timeframe)
  1283	                if not h:
  1284	                    continue
  1285	                hid = _claim_hash(h.claim)
  1286	                pid = prediction_id(hid, PREDICTION_HORIZON_DAYS, bucket)
  1287	                if pid in seen or pid in existing:
  1288	                    seen.add(pid)
  1289	                    continue
  1290	                seen.add(pid)
  1291	                pred = Prediction(
  1292	                    id=pid,
  1293	                    hypothesis_id=hid,
  1294	                    claim=h.claim,
  1295	                    symbol=signal.symbol or symbol,
  1296	                    timeframe=signal.timeframe or timeframe,
  1297	                    strategy_tags=h.tags,
  1298	                    horizon_days=PREDICTION_HORIZON_DAYS,
  1299	                    bucket=bucket,
  1300	                    window_start_ts=window_start,
  1301	                    resolve_ts=resolve,
  1302	                    asof_ts=now,
  1303	                    statement=(
  1304	                        f"Net of {FEE_BPS}bps, a strategy implied by '{h.claim[:70]}' shows "
  1305	                        f"no significant edge over the {PREDICTION_HORIZON_DAYS:.0f}d forward "
  1306	                        f"window {window_start:%Y-%m-%d}..{resolve:%Y-%m-%d}"
  1307	                    ),
  1308	                )
  1309	                self.predictions.append(pred)
  1310	                registered += 1
  1311	        result = {
  1312	            "registered": registered,
  1313	            "skipped_unreplayable": skipped_unreplayable,
  1314	            "bucket": bucket,
  1315	            "window_start": window_start.isoformat(),
  1316	            "resolve": resolve.isoformat(),
  1317	            "open_total": self.predictions.count_open(),
  1318	        }
  1319	        if registered:
  1320	            self._log_methodology({"phase": "prediction_registration", **result})
  1321	        self._emit_telemetry("prediction.registered", details=result)
  1322	        return result
  1323	
  1324	    def score_due_predictions(self, now: datetime | None = None) -> dict:
  1325	        """Phase 2b: resolve predictions whose forward window has closed.
  1326	
  1327	        For each due prediction, replay the FROZEN strategy spec on realized data
  1328	        for the forward window only, write a conservative `live_observation`
  1329	        evidence record, and fill the prediction's resolution fields (append-only
  1330	        — the forecast fields are never touched). Runs every cycle so scoring is
  1331	        autonomous. The un-exhaustible evidence path: forward time keeps closing
  1332	        windows regardless of whether the backtest hypothesis space is exhausted.
  1333	        """
  1334	        now = now or datetime.now(timezone.utc)
  1335	        due = self.predictions.list_due(now)
  1336	        scored = 0
  1337	        unresolvable = 0
  1338	        outcomes: dict[str, int] = {}
  1339	        for p in due:
  1340	            try:
  1341	                resolved = self._score_one_prediction(p, now)
  1342	            except Exception as exc:
  1343	                log.warning("Scoring prediction %s failed: %s", p.id, exc)
  1344	                continue
  1345	            self.predictions.update(resolved)
  1346	            if resolved.status == "resolved":
  1347	                scored += 1
  1348	                outcomes[resolved.outcome] = outcomes.get(resolved.outcome, 0) + 1
  1349	            else:
  1350	                unresolvable += 1
  1351	        result = {
  1352	            "scored": scored,
  1353	            "unresolvable": unresolvable,
  1354	            "outcomes": outcomes,
  1355	            "open_remaining": self.predictions.count_open(),
  1356	        }
  1357	        if scored or unresolvable:
  1358	            self._log_methodology({"phase": "prediction_scoring", **result})
  1359	            self._emit_telemetry("prediction.resolved", details=result)
  1360	        return result
  1361	
  1362	    def _score_one_prediction(self, p: Prediction, now: datetime):
  1363	        """Score one due prediction; return the resolved (or unresolvable) copy.
  1364	
  1365	        Guardrails: (1) reconstruct from the frozen tags only — never re-detect;
  1366	        (2) score returns inside [window_start, resolve_ts] only, using an earlier
  1367	        warm-up prefix solely to prime rolling indicators; (3) set only resolution
  1368	        fields (append-only).
  1369	        """
  1370	        warmup = timedelta(days=p.horizon_days)  # generous prefix for rolling indicators
  1371	        since = (p.window_start_ts - warmup).strftime("%Y-%m-%d")
  1372	        # `since` forces a cache-miss on a fresh (window-covering) fetch, bypassing
  1373	        # the indefinitely-cached main scan CSV (which lags the forward window).
  1374	        df = self.market.fetch_ohlcv(symbol=p.symbol, timeframe=p.timeframe, since=since, limit=100000)
  1375	
  1376	        window_mask = (df.index >= p.window_start_ts) & (df.index <= p.resolve_ts)
  1377	        window = df.loc[window_mask]
  1378	        if len(window) < SCORE_MIN_BARS:
  1379	            return p.model_copy(update={
  1380	                "status": "unresolvable",
  1381	                "outcome": "insufficient_data",
  1382	                "resolved_at": now,
  1383	            })
  1384	
  1385	        # Build the signal on [window_start - warmup, resolve_ts] so rolling
  1386	        # indicators are primed, then score ONLY the window's returns.
  1387	        full = df.loc[(df.index >= p.window_start_ts - warmup) & (df.index <= p.resolve_ts)]
  1388	        frozen_h = Hypothesis(
  1389	            claim=p.claim,
  1390	            tags=list(p.strategy_tags),
  1391	            rationale="frozen forward-prediction spec (replay only)",
  1392	            falsification_criteria="frozen",
  1393	        )
  1394	        signals = self._build_signal_from_hypothesis(frozen_h, full)
  1395	
  1396	        tf_periods = {"1h": 365 * 24, "4h": 365 * 6, "1d": 365, "1w": 52}
  1397	        periods_per_year = tf_periods.get(p.timeframe, 365 * 6)
  1398	        # Pass window prices + full signals; run_backtest reindexes signals to the
  1399	        # window returns (the values were computed with warm-up) and applies fees.
  1400	        bt = run_backtest(window["close"], signals, periods_per_year=periods_per_year, fee_bps=FEE_BPS)
  1401	        realized_sharpe = float(bt.sharpe_ratio)
  1402	        realized_return = float(bt.total_return)
  1403	        realized_up = 1.0 if realized_return > 0 else 0.0
  1404	        brier = (p.predicted_prob_up - realized_up) ** 2
  1405	
  1406	        if realized_sharpe >= SCORE_EDGE_SHARPE and realized_return > 0:
  1407	            realized_label, outcome, direction = "edge", "edge_appeared", EvidenceDirection.SUPPORTS
  1408	        elif realized_sharpe <= 0 or realized_return <= 0:
  1409	            realized_label, outcome, direction = "no_edge", "confirmed_null", EvidenceDirection.CONTRADICTS
  1410	        else:
  1411	            realized_label, outcome, direction = "marginal", "inconclusive", EvidenceDirection.INCONCLUSIVE
  1412	
  1413	        # Single window is noisy: cap at MODERATE (never STRONG) so the ledger
  1414	        # cannot manufacture a promotion on the current feature space.
  1415	        quality = EvidenceQuality.WEAK if outcome == "inconclusive" else EvidenceQuality.MODERATE
  1416	
  1417	        ev = Evidence(
  1418	            experiment_id=p.id,  # the prediction is its own distinct experiment
  1419	            hypothesis_id=p.hypothesis_id,
  1420	            evidence_class=EvidenceClass.LIVE_OBSERVATION,
  1421	            quality=quality,
  1422	            direction=direction,
  1423	            summary=(
  1424	                f"Forward window {p.window_start_ts:%Y-%m-%d}..{p.resolve_ts:%Y-%m-%d}: "
  1425	                f"realized Sharpe {realized_sharpe:.2f}, return {realized_return * 100:.1f}% "
  1426	                f"net {FEE_BPS}bps over {len(window)} bars → {outcome}"
  1427	            ),
  1428	            statistics={
  1429	                "realized_sharpe": realized_sharpe,
  1430	                "realized_return": realized_return,
  1431	                "brier_score": brier,
  1432	                "n_bars": len(window),
  1433	                "prediction_id": p.id,
  1434	                "bucket": p.bucket,
  1435	            },
  1436	            data_range=f"{p.window_start_ts:%Y-%m-%d} to {p.resolve_ts:%Y-%m-%d}",
  1437	        )
  1438	        self._save_obj("evidence", ev.id, ev.model_dump())
  1439	
  1440	        return p.model_copy(update={
  1441	            "status": "resolved",
  1442	            "realized_return": realized_return,
  1443	            "realized_sharpe": realized_sharpe,
  1444	            "realized_label": realized_label,
  1445	            "brier_score": brier,
  1446	            "outcome": outcome,
  1447	            "resolved_at": now,
  1448	        })
  1449	
  1450	    def run_cycle(self) -> dict:
  1451	        """Execute one complete research cycle."""
  1452	        log.info("=== Starting research cycle ===")
  1453	        self._emit_telemetry("cycle.started")
  1454	        cycle_report = {"timestamp": datetime.now(timezone.utc).isoformat(), "hypotheses": []}
  1455	
  1456	        # Phase 1: Scan in-sample data for signals
  1457	        signal_results = self.scan_signals()
  1458	        cycle_report["signals_found"] = sum(len(s) for _, _, s, _ in signal_results)
  1459	
  1460	        # Forward-prediction ledger: register dated forward forecasts for the
  1461	        # detected signals (idempotent per horizon bucket). Independent of the
  1462	        # backtest path so it produces fresh evidence even when the hypothesis
  1463	        # space is exhausted. Defensive try/except: a ledger bug must not break
  1464	        # the research cycle.
  1465	        try:
  1466	            cycle_report["predictions"] = self.register_predictions(signal_results)
  1467	        except Exception as exc:
  1468	            log.warning("Prediction registration failed: %s", exc)
  1469	
  1470	        # Phase 2b: score any predictions whose forward window has closed. Runs
  1471	        # every cycle so calibration accrues autonomously. Defensive: a scorer
  1472	        # bug must not break the research cycle.
  1473	        try:
  1474	            cycle_report["prediction_scoring"] = self.score_due_predictions()
  1475	        except Exception as exc:
  1476	            log.warning("Prediction scoring failed: %s", exc)
  1477	
  1478	        # Phase 2: Generate hypotheses (with durable IDs and Bonferroni correction)
  1479	        hypotheses = self.generate_hypotheses(signal_results)
  1480	
  1481	        # Phase 2a: Re-include orphaned TESTING hypotheses that have an
  1482	        # unfresh DEFAULT_UNIVERSE dataset. P1 dispatch handoff
  1483	        # (atlas-testing-reeval-p1-2026-05-02T16-48Z.md). Without this,
  1484	        # A+C+D2 promotes hypotheses but they orphan after one cycle —
  1485	        # observed 2026-05-02 as 14 consecutive empty cycles.
  1486	        # MUST run before top-up so re-evaluating active TESTING work is
  1487	        # preferred over promoting from the cold FORMULATED pool.
  1488	        hypotheses = self._include_orphaned_testing(hypotheses)
  1489	
  1490	        # Phase 2b: Top up from FORMULATED pool when signal-driven generation
  1491	        # under-fills the cycle. Per principal decision A+C+D2 (handoff
  1492	        # atlas-pool-rotation-decision.md, 2026-05-01): keep the loop from
  1493	        # silently starving when current signal scans don't re-fire prior
  1494	        # hypotheses. STRICT-D2 marks data-unavailable hypotheses INFEASIBLE
  1495	        # so they don't repeatedly block the auto-top-up.
  1496	        hypotheses = self._top_up_from_formulated_pool(hypotheses)
  1497	
  1498	        # Recompute Bonferroni adjustment now that the cycle's test set is
  1499	        # finalized — generate_hypotheses stamped its own n_tests, but the
  1500	        # top-up may have added more, which would understate the
  1501	        # multiple-testing burden.
  1502	        n_tests = max(1, len(hypotheses))
  1503	        for h in hypotheses:
  1504	            h._bonferroni_n = n_tests  # type: ignore[attr-defined]
  1505	
  1506	        cycle_report["hypotheses_generated"] = len(hypotheses)
  1507	
  1508	        if not hypotheses:
  1509	            log.info("No hypotheses generated this cycle")
  1510	            backfill_stats = backfill_falsified_claims(self.state, self.graph_store)
  1511	            graph = self.graph_store.load()
  1512	            cycle_report["graph_nodes"] = graph.node_count
  1513	            cycle_report["graph_edges"] = graph.edge_count
  1514	            cycle_report["no_action"] = {
  1515	                "reason": "hypothesis_space_exhausted",
  1516	                "signals_found": cycle_report.get("signals_found", 0),
  1517	                "hypotheses_generated": 0,
  1518	                "backfill": backfill_stats,
  1519	            }
  1520	            # Emit cycle.completed even on the empty-hypothesis path so the
  1521	            # S3-P2 gate is not blind to "loop is starving" failures
  1522	            # (regression: 04-30 14:18Z URGENT — runner ran 14h producing
  1523	            # nothing while the gate saw no events to count).
  1524	            self._emit_telemetry(
  1525	                "cycle.completed",
  1526	                details={
  1527	                    "hypotheses_evaluated": 0,
  1528	                    "total_evidence_store_size": len(self.state.list_all("evidence")),
  1529	                    "signals_found": cycle_report.get("signals_found", 0),
  1530	                    "graph_nodes": graph.node_count,
  1531	                    "graph_edges": graph.edge_count,
  1532	                    "decisions_by_kind": {},
  1533	                    "no_action_reason": "hypothesis_space_exhausted",
  1534	                    "refuted_nodes": graph.status_counts().get("refuted", 0),
  1535	                    "backfill": backfill_stats,
  1536	                },
  1537	            )
  1538	            try:
  1539	                self._update_streak_counter({})
  1540	            except Exception as exc:
  1541	                log.warning("Streak counter update failed: %s", exc)
  1542	            try:
  1543	                self._maybe_escalate_frozen_loop()
  1544	            except Exception as exc:
  1545	                log.warning("Frozen-loop escalation check failed: %s", exc)
  1546	            return cycle_report
  1547	
  1548	        # Build a lookup from hypothesis claim to the full df
  1549	        claim_to_data: dict[str, tuple[str, str, pd.DataFrame]] = {}
  1550	        for symbol, timeframe, signals, df in signal_results:
  1551	            for signal in signals:
  1552	                h_candidate = from_signal(signal, symbol, timeframe)
  1553	                if h_candidate:
  1554	                    claim_to_data[h_candidate.claim] = (symbol, timeframe, df)
  1555	
  1556	        # Phase 3-5: For each hypothesis, run experiments and decide
  1557	        for h in hypotheses:
  1558	            # Persist hypothesis (or it already exists with same ID)
  1559	            if not self._load_obj("hypotheses", h.id):
  1560	                self._save_obj("hypotheses", h.id, h.model_dump())
  1561	
  1562	            h_report = {"id": h.id, "claim": h.claim, "experiments": []}
  1563	            is_graph_gap = "graph_gap" in h.tags
  1564	
  1565	            # Determine which datasets to test on. Primary from signal source,
  1566	            # plus additional datasets for cross-validation (distinct experiments).
  1567	            existing_evidence = [Evidence.model_validate(d) for d in self._list_objs("evidence")
  1568	                                 if d.get("hypothesis_id") == h.id]
  1569	            fresh_tested_datasets = self._fresh_tested_datasets(existing_evidence)
  1570	
  1571	            # Build candidate datasets: primary first, then cross-validation pairs
  1572	            datasets = []
  1573	            if h.claim in claim_to_data:
  1574	                sym, tf, df = claim_to_data[h.claim]
  1575	                datasets.append((sym, tf, df))
  1576	            elif is_graph_gap:
  1577	                parsed = self._parse_dataset_from_hypothesis(h)
  1578	                if parsed and parsed in DEFAULT_UNIVERSE_SET:
  1579	                    try:
  1580	                        df = self.market.fetch_ohlcv(symbol=parsed[0], timeframe=parsed[1], limit=100000)
  1581	                        if len(df) >= MIN_BARS_FOR_RESEARCH:
  1582	                            datasets.append((parsed[0], parsed[1], df))
  1583	                    except Exception as exc:
  1584	                        log.info("Graph-gap dataset fetch failed for %s: %s", h.id, exc)
  1585	
  1586	            # Extract the base asset from tags for cross-validation
  1587	            base_asset = None
  1588	            for tag in h.tags:
  1589	                if "usdt" in tag:
  1590	                    base_asset = tag.replace("_", "/").upper()
  1591	                    break
  1592	
  1593	            # Add cross-validation datasets (same strategy, different data)
  1594	            if not is_graph_gap:
  1595	                for sym, tf in DEFAULT_UNIVERSE:
  1596	                    if (sym, tf) not in fresh_tested_datasets and (not datasets or (sym, tf) != (datasets[0][0], datasets[0][1])):
  1597	                        try:
  1598	                            xdf = self.market.fetch_ohlcv(symbol=sym, timeframe=tf, limit=100000)
  1599	                            if len(xdf) >= 200:
  1600	                                datasets.append((sym, tf, xdf))
  1601	                        except Exception:
  1602	                            continue
  1603	                    if len(datasets) >= 3:
  1604	                        break
  1605	
  1606	            if not datasets:
  1607	                if is_graph_gap:
  1608	                    h_report["skip_reason"] = "no_claim_faithful_dataset"
  1609	                    h_report["decision"] = "continue"
  1610	                    self._log_methodology({
  1611	                        "phase": "experiment_selection",
  1612	                        "hypothesis_id": h.id,
  1613	                        "skipped": "no_claim_faithful_dataset",
  1614	                        "tags": h.tags,
  1615	                    })
  1616	                    cycle_report["hypotheses"].append(h_report)
  1617	                    self._emit_telemetry(
  1618	                        "hypothesis.decided",
  1619	                        details={
  1620	                            "hypothesis_id": h.id,
  1621	                            "decision": "continue",
  1622	                            "skip_reason": "no_claim_faithful_dataset",
  1623	                            "total_evidence_store_size": len(self.state.list_all("evidence")),
  1624	                        },
  1625	                    )
  1626	                    continue
  1627	                symbol, timeframe = "BTC/USDT", "1h"
  1628	                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=100000)
  1629	                datasets.append((symbol, timeframe, df))
  1630	
  1631	            # Find or create a cycle only after we know the hypothesis has a
  1632	            # claim-faithful dataset to test. Otherwise skipped graph-gap
  1633	            # followups create permanent active-cycle clutter.
  1634	            cycle = self._find_active_cycle(h.id)
  1635	            if not cycle:
  1636	                cycle = ResearchCycle(hypothesis_id=h.id)
  1637	                self._save_obj("cycles", cycle.id, cycle.model_dump())
  1638	                self.events.append(SessionEvent(
  1639	                    session_id=cycle.id,
  1640	                    event_type=EventType.HYPOTHESIS_FORMULATED,
  1641	                    details={"hypothesis_id": h.id, "claim": h.claim},
  1642	                ))
  1643	
  1644	            # Test on each dataset (distinct experiments for promotion gate)
  1645	            n_folds = 5
  1646	            min_bars = n_folds * 50 / 0.3  # each OOS fold needs ≥50 bars
  1647	            for symbol, timeframe, df in datasets:
  1648	                if (symbol, timeframe) in fresh_tested_datasets:
  1649	                    continue
  1650	                if len(df) < min_bars:
  1651	                    log.info("Skipping %s %s: %d bars too short for %d-fold walk-forward (need %d)",
  1652	                             symbol, timeframe, len(df), n_folds, int(min_bars))
  1653	                    continue
  1654	                exp, ev = self.run_experiment(h, df, symbol, timeframe)
  1655	                if ev:
  1656	                    cycle.experiment_ids.append(exp.id)
  1657	                    cycle.evidence_ids.append(ev.id)
  1658	                    self._save_obj("cycles", cycle.id, cycle.model_dump())
  1659	                    h_report["experiments"].append({
  1660	                        "id": exp.id,
  1661	                        "evidence_quality": ev.quality.value,
  1662	                        "evidence_direction": ev.direction.value,
  1663	                    })
  1664	
  1665	            # Decide
  1666	            decision = self.evaluate_and_decide(h, cycle)
  1667	            h_report["decision"] = decision
  1668	            cycle_report["hypotheses"].append(h_report)
  1669	
  1670	            log.info("Hypothesis %s: %s → %s", h.id, h.claim[:60], decision)
  1671	            self._emit_telemetry(
  1672	                "hypothesis.decided",
  1673	                level="info" if decision != "error" else "error",
  1674	                details={
  1675	                    "hypothesis_id": h.id,
  1676	                    "decision": decision,
  1677	                    "total_evidence_store_size": len(self.state.list_all("evidence")),
  1678	                },
  1679	            )
  1680	
  1681	        # Phase 6: Report graph state
  1682	        graph = self.graph_store.load()
  1683	        cycle_report["graph_nodes"] = graph.node_count
  1684	        cycle_report["graph_edges"] = graph.edge_count
  1685	
  1686	        log.info("=== Cycle complete: %d hypotheses tested, graph has %d nodes ===",
  1687	                 len(hypotheses), graph.node_count)
  1688	
  1689	        # Decision breakdown: how many hypotheses landed in each terminal state
  1690	        # this cycle. A cycle where every decision is "continue" produces no new
  1691	        # epistemic state — surfacing this explicitly is how meta-scan detects
  1692	        # the frozen-loop failure mode (Pattern 2 of the 2026-04-24 synthesis).
  1693	        decisions_by_kind: dict[str, int] = {}
  1694	        for hrep in cycle_report["hypotheses"]:
  1695	            kind = hrep.get("decision", "unknown")
  1696	            decisions_by_kind[kind] = decisions_by_kind.get(kind, 0) + 1
  1697	
  1698	        self._emit_telemetry(
  1699	            "cycle.completed",
  1700	            details={
  1701	                "hypotheses_evaluated": len(cycle_report["hypotheses"]),
  1702	                "total_evidence_store_size": len(self.state.list_all("evidence")),
  1703	                "signals_found": cycle_report.get("signals_found", 0),
  1704	                "graph_nodes": graph.node_count,
  1705	                "graph_edges": graph.edge_count,
  1706	                "decisions_by_kind": decisions_by_kind,
  1707	            },
  1708	        )
  1709	
  1710	        # S3-P2 frozen-loop escalation: if the last N completed cycles were
  1711	        # all-continue (no kills, promotions, or pivots), the loop is producing
  1712	        # no epistemic state and the silent-monitor failure mode applies.
  1713	        try:
  1714	            self._update_streak_counter(decisions_by_kind)
  1715	        except Exception as exc:
  1716	            log.warning("Streak counter update failed: %s", exc)
  1717	        try:
  1718	            self._maybe_escalate_frozen_loop()
  1719	        except Exception as exc:  # never let escalation crash a cycle
  1720	            log.warning("Frozen-loop escalation check failed: %s", exc)
  1721	
  1722	        return cycle_report
  1723	
  1724	    # --------------------------------------------------------------------
  1725	    # S3-P2 frozen-loop escalation
  1726	    # --------------------------------------------------------------------
  1727	
  1728	    TELEMETRY_PATH = Path("/opt/workspace/runtime/.telemetry/events.jsonl")
  1729	    SUPERVISOR_HANDOFF_DIR = Path("/opt/workspace/supervisor/handoffs/INBOX")
  1730	
  1731	    def _escalation_state_path(self) -> Path:
  1732	        """Authoritative dedup state for the frozen-loop gate. Lives under
  1733	        .atlas/ so it survives both runner restart and telemetry rotation.
  1734	
  1735	        The previous design read prior `cycle.escalated` events back from
  1736	        `events.jsonl`, which broke at midnight UTC when the workspace
  1737	        telemetry collector rotated yesterday's events to a `.gz` archive
  1738	        the gate did not read.
  1739	        """
  1740	        return self.base_dir / ".atlas" / "escalation_state.json"
  1741	
  1742	    def _load_escalation_state(self) -> dict:
  1743	        """Return the persistent streak state, validated.
  1744	
  1745	        Recognized fields:
  1746	          consecutive_empty_count  int    — live streak length; null/bad → fail-open
  1747	          streak_start_ts          int|None — when the current streak started
  1748	          emitted_for_current_streak bool — True once the gate has fired this streak
  1749	          last_emitted_ts          int    — epoch-ms of the last emission (display only)
  1750	
  1751	        A malformed file is treated as empty (fail-open = counter resets to 0,
  1752	        not-emitted) so the gate re-arms after 3 new cycles rather than going
  1753	        silently dark.
  1754	        """
  1755	        path = self._escalation_state_path()
  1756	        if not path.exists():
  1757	            return {}
  1758	        try:
  1759	            raw = json.loads(path.read_text())
  1760	        except Exception as exc:
  1761	            log.warning("Failed to read escalation state %s: %s", path, exc)
  1762	            return {}
  1763	        if not isinstance(raw, dict):
  1764	            log.warning("Escalation state %s is not a dict; ignoring", path)
  1765	            return {}
  1766	        out: dict = {}
  1767	        # consecutive_empty_count: int; null or non-int → fail-open
  1768	        if "consecutive_empty_count" in raw:
  1769	            val = raw["consecutive_empty_count"]
  1770	            try:
  1771	                out["consecutive_empty_count"] = int(val)
  1772	            except (TypeError, ValueError):
  1773	                log.warning(
  1774	                    "Escalation state %s has non-int consecutive_empty_count=%r; ignoring",
  1775	                    path, val,
  1776	                )
  1777	                return {}
  1778	        # streak_start_ts: int or None (null = counter is at 0 / not started)
  1779	        if "streak_start_ts" in raw:
  1780	            val = raw["streak_start_ts"]
  1781	            if val is None:
  1782	                out["streak_start_ts"] = None
  1783	            else:
  1784	                try:
  1785	                    out["streak_start_ts"] = int(val)
  1786	                except (TypeError, ValueError):
  1787	                    log.warning(
  1788	                        "Escalation state %s has non-int streak_start_ts=%r; ignoring",
  1789	                        path, val,
  1790	                    )
  1791	                    return {}
  1792	        # emitted_for_current_streak: bool; corrupt value → default False
  1793	        if "emitted_for_current_streak" in raw:
  1794	            val = raw["emitted_for_current_streak"]
  1795	            if isinstance(val, bool):
  1796	                out["emitted_for_current_streak"] = val
  1797	            elif val in (0, 1):
  1798	                out["emitted_for_current_streak"] = bool(val)
  1799	            else:
  1800	                out["emitted_for_current_streak"] = False
  1801	        return out
  1802	
  1803	    def _persist_escalation_state(self, state: dict) -> None:
  1804	        """Atomic write of the escalation state dict."""
  1805	        path = self._escalation_state_path()
  1806	        try:
  1807	            path.parent.mkdir(parents=True, exist_ok=True)
  1808	            tmp = path.with_suffix(path.suffix + ".tmp")
  1809	            tmp.write_text(json.dumps(state))
  1810	            tmp.replace(path)
  1811	        except Exception as exc:
  1812	            log.warning("Failed to write escalation state %s: %s", path, exc)
  1813	
  1814	    def _save_escalation_state(self, streak_start_ts: int, emitted_ts: int) -> None:
  1815	        """Mark the current streak as emitted. Preserves the existing counter."""
  1816	        state = self._load_escalation_state()
  1817	        state.update({
  1818	            "emitted_for_current_streak": True,
  1819	            "last_emitted_ts": emitted_ts,
  1820	            "streak_start_ts": streak_start_ts,
  1821	        })
  1822	        self._persist_escalation_state(state)
  1823	
  1824	    def _update_streak_counter(self, decisions_by_kind: dict) -> None:
  1825	        """Update the persistent consecutive-empty counter from one cycle's outcome.
  1826	
  1827	        Increments on empty cycles (decisions_by_kind == {}) and all-continue
  1828	        cycles (only "continue" keys). Resets to 0 on any decisive outcome
  1829	        (kill / promote / pivot). Called by run_cycle before
  1830	        _maybe_escalate_frozen_loop.
  1831	        """
  1832	        STUCK_KINDS = frozenset({"continue"})
  1833	        kind_set = set(decisions_by_kind.keys())
  1834	        has_decisive = bool(kind_set - STUCK_KINDS)
  1835	
  1836	        state = self._load_escalation_state()
  1837	
  1838	        if has_decisive:
  1839	            new_state: dict = {
  1840	                "consecutive_empty_count": 0,
  1841	                "streak_start_ts": None,
  1842	                "emitted_for_current_streak": False,
  1843	            }
  1844	            if "last_emitted_ts" in state:
  1845	                new_state["last_emitted_ts"] = state["last_emitted_ts"]
  1846	        else:
  1847	            count = state.get("consecutive_empty_count", 0) + 1
  1848	            streak_start_ts = (
  1849	                state.get("streak_start_ts")
  1850	                or int(datetime.now(timezone.utc).timestamp() * 1000)
  1851	            )
  1852	            new_state = {
  1853	                "consecutive_empty_count": count,
  1854	                "streak_start_ts": streak_start_ts,
  1855	                "emitted_for_current_streak": state.get("emitted_for_current_streak", False),
  1856	            }
  1857	            if "last_emitted_ts" in state:
  1858	                new_state["last_emitted_ts"] = state["last_emitted_ts"]
  1859	
  1860	        self._persist_escalation_state(new_state)
  1861	
  1862	    def _maybe_escalate_frozen_loop(self) -> None:
  1863	        """Emit a `cycle.escalated` event and write an URGENT handoff when
  1864	        the persistent consecutive-empty counter reaches FROZEN_LOOP_ESCALATION_AFTER
  1865	        and the current streak has not yet been reported.
  1866	
  1867	        The counter is maintained by `_update_streak_counter`, called from
  1868	        `run_cycle` before this method. Resets to 0 on any kill/promote/pivot.
  1869	        Idempotency is governed by `emitted_for_current_streak` in the state
  1870	        file — rotation-proof because it never reads events.jsonl.
  1871	        """
  1872	        state = self._load_escalation_state()
  1873	        count = state.get("consecutive_empty_count", 0)
  1874	
  1875	        if count < FROZEN_LOOP_ESCALATION_AFTER:
  1876	            return
  1877	
  1878	        if state.get("emitted_for_current_streak", False):
  1879	            return
  1880	
  1881	        streak_start_ts = state.get("streak_start_ts") or 0
  1882	        emitted_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
  1883	        self._emit_telemetry(
  1884	            "cycle.escalated",
  1885	            level="warning",
  1886	            details={
  1887	                "reason": "frozen_loop_all_continue",
  1888	                "consecutive_cycles": count,
  1889	                "streak_start_ts": streak_start_ts,
  1890	                "total_evidence_store_size": len(self.state.list_all("evidence")),
  1891	            },
  1892	        )
  1893	        self._save_escalation_state(streak_start_ts, emitted_ts)
  1894	        self._write_frozen_loop_handoff(count, streak_start_ts)
  1895	
  1896	    def _write_frozen_loop_handoff(self, consecutive_cycles: int, streak_start_ts: int) -> None:
  1897	        """Drop one URGENT handoff to general/atlas describing the streak.
  1898	        Dedup by glob — if any URGENT-atlas-frozen-loop-*.md exists, skip."""
  1899	        try:
  1900	            self.SUPERVISOR_HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
  1901	            existing = list(self.SUPERVISOR_HANDOFF_DIR.glob("URGENT-atlas-frozen-loop-*.md"))
  1902	            if existing:
  1903	                return
  1904	            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%MZ")
  1905	            path = self.SUPERVISOR_HANDOFF_DIR / f"URGENT-atlas-frozen-loop-{now_iso}.md"
  1906	            evidence_size = len(self.state.list_all("evidence"))
  1907	            body = (
  1908	                "---\n"
  1909	                f"priority: critical\n"
  1910	                f"created: {datetime.now(timezone.utc).isoformat()}\n"
  1911	                "from: atlas.runner (self-emitted via S3-P2 escalation gate)\n"
  1912	                "to: atlas / general\n"
  1913	                "---\n\n"
  1914	                "# atlas — frozen loop (auto-escalated)\n\n"
  1915	                f"The autonomous loop has produced {consecutive_cycles} consecutive\n"
  1916	                "all-continue cycles with no kill/promote/pivot decisions.\n"
  1917	                f"Evidence store size: {evidence_size}.\n\n"
  1918	                "## Likely causes\n\n"
  1919	                "- Dataset retest cache is too aggressive (DATASET_RETEST_AFTER) —\n"
  1920	                "  hypothesis is being re-evaluated against the same evidence.\n"
  1921	                "- All available data has been exhausted under the current signal\n"
  1922	                "  detectors; new detectors or new data sources needed.\n"
  1923	                "- A bug is silently dropping experiment runs.\n\n"
  1924	                "## Diagnostic\n\n"
  1925	                "  grep '\"eventType\": \"cycle.completed\"' \\\n"
  1926	                "    /opt/workspace/runtime/.telemetry/events.jsonl | tail -10\n"
  1927	                "  .venv/bin/atlas strategy readiness\n\n"
  1928	                "Delete this file once the root cause is addressed; the gate is\n"
  1929	                "idempotent and will re-fire only on a new streak.\n"
  1930	            )
  1931	            path.write_text(body)
  1932	            log.warning("Wrote frozen-loop URGENT handoff to %s", path)
  1933	        except Exception as exc:
  1934	            log.warning("Failed to write frozen-loop handoff: %s", exc)
  1935	
  1936	    def run_continuous(self, interval_seconds: int = 3600) -> None:
  1937	        """Run the research loop continuously."""
  1938	        log.info("Starting continuous research loop (interval=%ds)", interval_seconds)
  1939	        while True:
  1940	            try:
  1941	                report = self.run_cycle()
  1942	                reports_dir = self.base_dir / "reports"
  1943	                reports_dir.mkdir(exist_ok=True)
  1944	                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  1945	                with open(reports_dir / f"cycle_{ts}.json", "w") as f:
  1946	                    json.dump(report, f, indent=2, default=str)
  1947	            except Exception as e:
  1948	                log.error("Cycle failed: %s", e, exc_info=True)
  1949	                self._log_methodology({
  1950	                    "phase": "cycle_failure",
  1951	                    "error": str(e),
  1952	                })
  1953	                self._emit_telemetry("cycle.failed", level="error", details={"error": str(e)})
  1954	
  1955	            log.info("Sleeping %ds until next cycle", interval_seconds)
  1956	            time.sleep(interval_seconds)

codex
The file is large, so I’m reading it in focused numbered chunks around the runner phases, experiment execution, decisions, and persistence boundaries.
exec
/bin/bash -lc "sed -n '120,520p' /opt/workspace/projects/atlas/src/atlas/runner.py | nl -ba -v120" in /opt/workspace/projects/atlas
 succeeded in 0ms:
   120	def evaluate_promotion_gate(evidence: list[Evidence]) -> dict:
   121	    """Pure predicate: return promotion-gate metrics for one hypothesis.
   122	
   123	    Single source of truth shared by `evaluate_and_decide` (which acts on the
   124	    verdict) and `atlas strategy readiness` (which counts how many hypotheses
   125	    would pass). Adding a parallel implementation here would silently drift
   126	    from the runner.
   127	
   128	    Gate (per CLAUDE.md §Promotion Gate and atlas review #2):
   129	      - ≥2 strong supporting evidence records
   130	      - from ≥2 DISTINCT experiments
   131	      - ≥1 of those strong supports is OOS or LIVE
   132	      - 0 strong contradictory evidence records
   133	    """
   134	    strong_support = [e for e in evidence
   135	                      if e.quality == EvidenceQuality.STRONG
   136	                      and e.direction == EvidenceDirection.SUPPORTS]
   137	    strong_contradict = [e for e in evidence
   138	                         if e.quality == EvidenceQuality.STRONG
   139	                         and e.direction == EvidenceDirection.CONTRADICTS]
   140	    oos_support = [e for e in strong_support
   141	                   if e.evidence_class in (EvidenceClass.OUT_OF_SAMPLE_TEST,
   142	                                           EvidenceClass.LIVE_OBSERVATION)]
   143	    distinct_experiments = len({e.experiment_id for e in strong_support})
   144	
   145	    promotable = (
   146	        not strong_contradict
   147	        and distinct_experiments >= 2
   148	        and len(oos_support) >= 1
   149	    )
   150	
   151	    return {
   152	        "strong_support": strong_support,
   153	        "strong_contradict": strong_contradict,
   154	        "oos_support": oos_support,
   155	        "distinct_experiments": distinct_experiments,
   156	        "promotable": promotable,
   157	    }
   158	
   159	
   160	
   161	class AutonomousRunner:
   162	    """Runs the full research loop autonomously."""
   163	
   164	    def __init__(self, base_dir: Path, exchange_id: str = "bitstamp") -> None:
   165	        self.base_dir = base_dir
   166	        self.state = StateStore(base_dir / ".atlas")
   167	        self.market = MarketData(cache_dir=base_dir / "data", exchange_id=exchange_id)
   168	        self.alt_data = AlternativeData(cache_dir=base_dir / "data")
   169	        self.events = EventStore(base_dir / "sessions")
   170	        self.graph_store = GraphStore(base_dir / "graph")
   171	        self.predictions = PredictionStore(base_dir / "predictions.jsonl")
   172	        self.methodology_log = base_dir / "methodology.jsonl"
   173	
   174	    def _save_obj(self, kind: str, obj_id: str, data: dict) -> None:
   175	        self.state.save(kind, obj_id, data)
   176	
   177	    def _load_obj(self, kind: str, obj_id: str) -> dict | None:
   178	        return self.state.load(kind, obj_id)
   179	
   180	    def _list_objs(self, kind: str) -> list[dict]:
   181	        return self.state.list_all(kind)
   182	
   183	    def _log_methodology(self, entry: dict) -> None:
   184	        entry["timestamp"] = datetime.now(timezone.utc).isoformat()
   185	        with open(self.methodology_log, "a") as f:
   186	            f.write(json.dumps(entry, default=str) + "\n")
   187	
   188	    def _emit_telemetry(self, event_type: str, level: str = "info", details: dict | None = None) -> None:
   189	        """Append one event to the shared workspace telemetry stream."""
   190	        import uuid
   191	        event = {
   192	            "project": "atlas",
   193	            "source": "atlas.runner",
   194	            "eventType": event_type,
   195	            "level": level,
   196	            "sourceType": "system",
   197	            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
   198	            "id": str(uuid.uuid4()),
   199	        }
   200	        if details:
   201	            event["details"] = details
   202	        telemetry_path = self.TELEMETRY_PATH
   203	        try:
   204	            telemetry_path.parent.mkdir(parents=True, exist_ok=True)
   205	            with open(telemetry_path, "a") as f:
   206	                f.write(json.dumps(event, default=str) + "\n")
   207	        except Exception as exc:
   208	            log.warning("Failed to emit telemetry event %s: %s", event_type, exc)
   209	
   210	    def _find_existing_hypothesis(self, claim: str) -> Hypothesis | None:
   211	        """Find an existing hypothesis with the same claim."""
   212	        target_hash = _claim_hash(claim)
   213	        data = self._load_obj("hypotheses", target_hash)
   214	        if data:
   215	            return Hypothesis.model_validate(data)
   216	        return None
   217	
   218	    @staticmethod
   219	    def _parse_dataset_from_hypothesis(h: Hypothesis) -> tuple[str, str] | None:
   220	        """Parse (symbol, timeframe) from hypothesis tags.
   221	
   222	        Tag convention from `from_signal` and composite generators:
   223	        `['btc_usdt', '1h', ...]`. Pair/lead-lag generators emit two
   224	        `_usdt` tags (`['btc_usdt', 'eth_usdt', '1h', ...]`); we pick the
   225	        FIRST seen to be deterministic — the cycle's dataset selection
   226	        will iterate DEFAULT_UNIVERSE for cross-validation regardless.
   227	
   228	        Returns None when symbol or timeframe cannot be identified.
   229	        """
   230	        sym: str | None = None
   231	        tf: str | None = None
   232	        for tag in h.tags:
   233	            tag_lc = tag.lower()
   234	            if sym is None and tag_lc.endswith("_usdt"):
   235	                sym = tag.replace("_", "/").upper()
   236	            elif tf is None and tag_lc in ("1h", "4h", "1d", "1w"):
   237	                tf = tag_lc
   238	        if sym and tf:
   239	            return (sym, tf)
   240	        return None
   241	
   242	    @staticmethod
   243	    def _claim_is_permanently_infeasible(h: Hypothesis) -> bool:
   244	        """A claim is permanently INFEASIBLE only when it names a data
   245	        source we will never have access to from this deployment (geo-
   246	        blocked exchanges, perp/funding feeds we don't ingest).
   247	
   248	        Distinguishing claim-level infeasibility from environment-level
   249	        infeasibility is the whole point: INFEASIBLE is a one-way door
   250	        and must only be opened for properties of the claim itself, not
   251	        for transient deployment state like "DEFAULT_UNIVERSE doesn't
   252	        currently include 4h" or "Bitstamp only has 832 bars of SOL
   253	        right now". Those should leave the hypothesis FORMULATED so the
   254	        next cycle can re-evaluate when conditions change.
   255	        """
   256	        blob = (h.claim + " " + " ".join(h.tags)).lower()
   257	        return any(token in blob for token in INFEASIBLE_EXCHANGE_TOKENS)
   258	
   259	    def _data_currently_available(self, h: Hypothesis) -> bool:
   260	        """Reversible feasibility check: does this hypothesis have a
   261	        parseable (symbol, timeframe) in `DEFAULT_UNIVERSE` whose fetch
   262	        currently returns ≥ MIN_BARS_FOR_RESEARCH bars?
   263	
   264	        Returns False on any of: unparseable tags, off-universe pair,
   265	        fetch error, insufficient history. Caller MUST NOT use this as
   266	        an INFEASIBLE signal — these are all reversible.
   267	        """
   268	        parsed = self._parse_dataset_from_hypothesis(h)
   269	        if parsed is None:
   270	            return False
   271	        if parsed not in DEFAULT_UNIVERSE_SET:
   272	            return False
   273	        try:
   274	            df = self.market.fetch_ohlcv(symbol=parsed[0], timeframe=parsed[1], limit=100000)
   275	        except Exception:
   276	            return False
   277	        return len(df) >= MIN_BARS_FOR_RESEARCH
   278	
   279	    def _has_productive_universe_dataset(
   280	        self,
   281	        fresh_tested: set[tuple[str, str]],
   282	    ) -> tuple[str, str] | None:
   283	        """Return the first DEFAULT_UNIVERSE pair that is BOTH unfresh
   284	        AND has ≥ `MIN_BARS_FOR_RESEARCH` bars currently. None if no
   285	        universe dataset can produce a new experiment this cycle.
   286	
   287	        Used by `_include_orphaned_testing` to avoid re-including a
   288	        hypothesis whose only "unfresh" dataset has insufficient bars
   289	        (the SOL/USDT 1h case observed 2026-05-02). Without this check,
   290	        `re_included_productive` telemetry would be misleading —
   291	        hypotheses would burn slots and produce zero experiments,
   292	        exactly the failure mode the reviewer flagged.
   293	        """
   294	        for sym, tf in DEFAULT_UNIVERSE:
   295	            if (sym, tf) in fresh_tested:
   296	                continue
   297	            try:
   298	                df = self.market.fetch_ohlcv(symbol=sym, timeframe=tf, limit=100000)
   299	            except Exception:
   300	                continue
   301	            if len(df) >= MIN_BARS_FOR_RESEARCH:
   302	                return (sym, tf)
   303	        return None
   304	
   305	    def _include_orphaned_testing(self, current: list[Hypothesis]) -> list[Hypothesis]:
   306	        """Re-include TESTING-status hypotheses that can produce at least
   307	        one new experiment this cycle (an unfresh DEFAULT_UNIVERSE pair
   308	        with ≥ MIN_BARS_FOR_RESEARCH bars).
   309	
   310	        Without this, hypotheses promoted by `_top_up_from_formulated_pool`
   311	        are orphaned after one cycle: signal scans won't re-pick them
   312	        (parameter drift changes claim hashes), and the top-up path
   313	        only touches FORMULATED entries. The result observed 2026-05-02:
   314	        seven hypotheses promoted, one productive cycle, then 14+
   315	        consecutive empty cycles.
   316	
   317	        Order: this MUST run before `_top_up_from_formulated_pool`.
   318	        Reversed, the top-up fills the slot budget first and TESTING
   319	        starves forever — the dispatch handoff
   320	        `atlas-testing-reeval-p1-2026-05-02T16-48Z.md` requires this
   321	        invariant.
   322	
   323	        Slot budget shared via `TOP_UP_TARGET` so Bonferroni stays
   324	        bounded; the recompute in `run_cycle` covers the addition.
   325	
   326	        Hygiene gates (added per adversarial review):
   327	          - claim-permanently-infeasible TESTING entries (e.g. ingested
   328	            from research/ingest with BitMEX in claim, never migrated)
   329	            are skipped, NOT auto-migrated — auto-migration is an
   330	            ingest-contract decision out of scope for re-eval.
   331	          - "unfresh dataset exists" is not enough; we require
   332	            "unfresh dataset with ≥ MIN_BARS_FOR_RESEARCH bars".
   333	            Otherwise `re_included_productive` would be misleading and
   334	            operators would see `cycle.completed hypotheses_evaluated=0`
   335	            after `cycle.testing_reeval re_included_productive=N` and
   336	            assume a bug.
   337	        """
   338	        if len(current) >= TOP_UP_TARGET:
   339	            return current
   340	
   341	        current_ids = {h.id for h in current}
   342	        candidates: list[Hypothesis] = []
   343	        for record in self._list_objs("hypotheses"):
   344	            if record.get("status") != HypothesisStatus.TESTING.value:
   345	                continue
   346	            if record.get("id") in current_ids:
   347	                continue
   348	            try:
   349	                candidates.append(Hypothesis.model_validate(record))
   350	            except Exception as exc:
   351	                log.warning("Skipping malformed hypothesis record: %s", exc)
   352	                continue
   353	
   354	        candidates.sort(key=lambda c: c.id)
   355	
   356	        re_included_ids: list[str] = []
   357	        skipped_freshness_ids: list[str] = []
   358	        skipped_claim_infeasible_ids: list[str] = []
   359	        for h in candidates:
   360	            if len(current) >= TOP_UP_TARGET:
   361	                break
   362	            if self._claim_is_permanently_infeasible(h):
   363	                skipped_claim_infeasible_ids.append(h.id)
   364	                continue
   365	            existing_evidence = [
   366	                Evidence.model_validate(d)
   367	                for d in self._list_objs("evidence")
   368	                if d.get("hypothesis_id") == h.id
   369	            ]
   370	            fresh = self._fresh_tested_datasets(existing_evidence)
   371	            if self._has_productive_universe_dataset(fresh) is None:
   372	                # Either every universe dataset is fresh OR every
   373	                # unfresh one has insufficient bars. Either way no new
   374	                # experiment can run — don't burn a slot.
   375	                skipped_freshness_ids.append(h.id)
   376	                continue
   377	            current.append(h)
   378	            re_included_ids.append(h.id)
   379	
   380	        if candidates:
   381	            self._log_methodology({
   382	                "phase": "testing_reeval",
   383	                "re_included_productive": re_included_ids,
   384	                "skipped_no_productive_dataset": skipped_freshness_ids,
   385	                "skipped_claim_infeasible": skipped_claim_infeasible_ids,
   386	                "pool_size": len(candidates),
   387	                "current_size": len(current),
   388	            })
   389	            self._emit_telemetry(
   390	                "cycle.testing_reeval",
   391	                details={
   392	                    "re_included_productive": len(re_included_ids),
   393	                    "skipped_no_productive_dataset": len(skipped_freshness_ids),
   394	                    "skipped_claim_infeasible": len(skipped_claim_infeasible_ids),
   395	                    "pool_size": len(candidates),
   396	                    "current_size": len(current),
   397	                },
   398	            )
   399	        return current
   400	
   401	    def _top_up_from_formulated_pool(self, current: list[Hypothesis]) -> list[Hypothesis]:
   402	        """Promote currently-feasible FORMULATED hypotheses into the
   403	        cycle's test set; mark claim-permanently-infeasible ones as
   404	        INFEASIBLE; leave environmentally-blocked ones FORMULATED.
   405	
   406	        Single code path serving both the principal's A (auto-promote when
   407	        pool is starved) and D2 (STRICT fallback on empty signal scan)
   408	        decisions — A and D2 are the same operation viewed from two
   409	        symptoms (pool empty vs. signals absent). Conflating them avoids
   410	        the drift problem two near-duplicate methods would create.
   411	
   412	        Three outcomes per candidate:
   413	          - PROMOTED → status=TESTING, added to `current`.
   414	          - INFEASIBLE → status=INFEASIBLE (claim names a permanently-
   415	            blocked data source like BitMEX). One-way door.
   416	          - SKIPPED_NOT_PROMOTABLE → status stays FORMULATED. Reason is
   417	            environmental (off-universe, insufficient bars, unparseable
   418	            tags) so the next cycle can re-evaluate when conditions
   419	            change. Counted in telemetry but never persisted as
   420	            INFEASIBLE — that distinction matters because INFEASIBLE
   421	            permanently locks a hypothesis out of the loop.
   422	
   423	        Bonferroni for the cycle is recomputed by the caller; do not
   424	        stamp `_bonferroni_n` here.
   425	        """
   426	        current_ids = {h.id for h in current}
   427	        candidates: list[Hypothesis] = []
   428	        for record in self._list_objs("hypotheses"):
   429	            if record.get("status") != HypothesisStatus.FORMULATED.value:
   430	                continue
   431	            if record.get("id") in current_ids:
   432	                continue
   433	            try:
   434	                candidates.append(Hypothesis.model_validate(record))
   435	            except Exception as exc:
   436	                log.warning("Skipping malformed hypothesis record: %s", exc)
   437	                continue
   438	
   439	        # Deterministic ordering — sort by id so behavior is reproducible
   440	        # across runs and the audit log is stable.
   441	        candidates.sort(key=lambda c: c.id)
   442	
   443	        promoted_ids: list[str] = []
   444	        infeasible_ids: list[str] = []
   445	        skipped_ids: list[str] = []
   446	        for h in candidates:
   447	            # Permanent infeasibility is a property of the claim — always
   448	            # mark, even if `current` is already at target, so the pool
   449	            # gets cleaned up over successive cycles instead of needing
   450	            # multiple top-up triggers to clear stuck entries.
   451	            if self._claim_is_permanently_infeasible(h):
   452	                h.status = HypothesisStatus.INFEASIBLE
   453	                self._save_obj("hypotheses", h.id, h.model_dump())
   454	                infeasible_ids.append(h.id)
   455	                continue
   456	
   457	            # Stop promoting once the test set is at target — but keep
   458	            # iterating in case more INFEASIBLE entries need cleanup.
   459	            if len(current) >= TOP_UP_TARGET:
   460	                continue
   461	
   462	            try:
   463	                available = self._data_currently_available(h)
   464	            except Exception as exc:
   465	                log.warning("Feasibility check failed for %s: %s", h.id, exc)
   466	                skipped_ids.append(h.id)
   467	                continue
   468	            if not available:
   469	                # Reversible reason — leave FORMULATED for re-evaluation
   470	                # next cycle. Telemetry still records the skip so the
   471	                # frozen-loop monitor isn't blind to a "pool full of
   472	                # off-universe entries" failure mode.
   473	                skipped_ids.append(h.id)
   474	                continue
   475	
   476	            h.status = HypothesisStatus.TESTING
   477	            self._save_obj("hypotheses", h.id, h.model_dump())
   478	            current.append(h)
   479	            promoted_ids.append(h.id)
   480	
   481	        if candidates:  # always emit when the pool was non-empty
   482	            self._log_methodology({
   483	                "phase": "auto_top_up",
   484	                "promoted_from_formulated": promoted_ids,
   485	                "marked_infeasible": infeasible_ids,
   486	                "skipped_not_promotable": skipped_ids,
   487	                "pool_size": len(candidates),
   488	                "current_size": len(current),
   489	            })
   490	            self._emit_telemetry(
   491	                "cycle.top_up",
   492	                details={
   493	                    "promoted": len(promoted_ids),
   494	                    "infeasible": len(infeasible_ids),
   495	                    "skipped_not_promotable": len(skipped_ids),
   496	                    "pool_size": len(candidates),
   497	                    "current_size": len(current),
   498	                },
   499	            )
   500	        return current
   501	
   502	    def _find_active_cycle(self, hypothesis_id: str) -> ResearchCycle | None:
   503	        """Find an active cycle for a hypothesis."""
   504	        for data in self._list_objs("cycles"):
   505	            cycle = ResearchCycle.model_validate(data)
   506	            if cycle.hypothesis_id == hypothesis_id and cycle.status == CycleStatus.ACTIVE:
   507	                return cycle
   508	        return None
   509	
   510	    def _fresh_tested_datasets(
   511	        self,
   512	        existing_evidence: list[Evidence],
   513	        now: datetime | None = None,
   514	    ) -> set[tuple[str, str]]:
   515	        """Return datasets with recent evidence for the hypothesis."""
   516	        now = now or datetime.now(timezone.utc)
   517	        fresh: set[tuple[str, str]] = set()
   518	        newest_by_dataset: dict[tuple[str, str], datetime] = {}
   519	
   520	        for evidence in existing_evidence:

exec
/bin/bash -lc "sed -n '520,980p' /opt/workspace/projects/atlas/src/atlas/runner.py | nl -ba -v520" in /opt/workspace/projects/atlas
 succeeded in 0ms:
   520	        for evidence in existing_evidence:
   521	            exp_data = self._load_obj("experiments", evidence.experiment_id)
   522	            if not exp_data:
   523	                continue
   524	            params = exp_data.get("parameters", {})
   525	            key = (params.get("symbol", ""), params.get("timeframe", ""))
   526	            if not all(key):
   527	                continue
   528	            created_at = evidence.created_at
   529	            if created_at.tzinfo is None:
   530	                created_at = created_at.replace(tzinfo=timezone.utc)
   531	            if key not in newest_by_dataset or created_at > newest_by_dataset[key]:
   532	                newest_by_dataset[key] = created_at
   533	
   534	        for key, created_at in newest_by_dataset.items():
   535	            if now - created_at < DATASET_RETEST_AFTER:
   536	                fresh.add(key)
   537	
   538	        return fresh
   539	
   540	    def scan_signals(self, oos_cutoff: float = 0.7) -> list[tuple[str, str, list, pd.DataFrame]]:
   541	        """Phase 1: Scan in-sample data only for signals.
   542	
   543	        Returns (symbol, timeframe, signals, full_df) tuples.
   544	        Signals are detected on the first 70% of data to avoid OOS contamination.
   545	        """
   546	        results = []
   547	        skipped_short: set[tuple[str, str]] = set()
   548	        for symbol, timeframe in DEFAULT_UNIVERSE:
   549	            try:
   550	                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=100000)
   551	                if len(df) < MIN_BARS_FOR_RESEARCH:
   552	                    skipped_short.add((symbol, timeframe))
   553	                    log.warning(
   554	                        "Skipping %s %s: %d bars < MIN_BARS_FOR_RESEARCH=%d",
   555	                        symbol, timeframe, len(df), MIN_BARS_FOR_RESEARCH,
   556	                    )
   557	                    self._log_methodology({
   558	                        "phase": "signal_intake",
   559	                        "symbol": symbol,
   560	                        "timeframe": timeframe,
   561	                        "skipped": "insufficient_history",
   562	                        "bars": len(df),
   563	                        "min_required": MIN_BARS_FOR_RESEARCH,
   564	                    })
   565	                    continue
   566	                split_idx = int(len(df) * oos_cutoff)
   567	                is_df = df.iloc[:split_idx]
   568	
   569	                # Scan signals on in-sample data ONLY
   570	                signals = scan_all(is_df)
   571	                if signals:
   572	                    results.append((symbol, timeframe, signals, df))
   573	                    log.info("Found %d signals for %s %s (in-sample scan)",
   574	                             len(signals), symbol, timeframe)
   575	                    self._log_methodology({
   576	                        "phase": "signal_intake",
   577	                        "symbol": symbol,
   578	                        "timeframe": timeframe,
   579	                        "n_signals": len(signals),
   580	                        "methods": list({s.method for s in signals}),
   581	                        "is_bars": split_idx,
   582	                        "total_bars": len(df),
   583	                    })
   584	            except Exception as e:
   585	                log.warning("Failed to scan %s %s: %s", symbol, timeframe, e)
   586	
   587	        # Cross-asset detectors: compare pairs at the same timeframe
   588	        is_data: dict[tuple[str, str], pd.DataFrame] = {}
   589	        for symbol, timeframe, _, df in results:
   590	            split_idx = int(len(df) * oos_cutoff)
   591	            is_data[(symbol, timeframe)] = df.iloc[:split_idx]
   592	
   593	        # Also load pairs not yet in results. Honor the min-bars gate here
   594	        # so cross-asset detectors don't pair a short dataset against a
   595	        # long one (would produce signals atlas then can't walk-forward).
   596	        for symbol, timeframe in DEFAULT_UNIVERSE:
   597	            if (symbol, timeframe) in is_data or (symbol, timeframe) in skipped_short:
   598	                continue
   599	            try:
   600	                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=100000)
   601	                if len(df) < MIN_BARS_FOR_RESEARCH:
   602	                    skipped_short.add((symbol, timeframe))
   603	                    continue
   604	                is_data[(symbol, timeframe)] = df.iloc[:int(len(df) * oos_cutoff)]
   605	            except Exception:
   606	                pass
   607	
   608	        timeframes_seen = set()
   609	        for (sym, tf) in is_data:
   610	            timeframes_seen.add(tf)
   611	
   612	        cross_signals = []
   613	        for tf in timeframes_seen:
   614	            pairs_at_tf = [(sym, df) for (sym, t), df in is_data.items() if t == tf]
   615	            for i, (sym_a, df_a) in enumerate(pairs_at_tf):
   616	                for sym_b, df_b in pairs_at_tf[i + 1:]:
   617	                    cross_signals.extend(detect_cross_asset_spread(
   618	                        df_a["close"], df_b["close"], sym_a, sym_b,
   619	                    ))
   620	                    ret_a = df_a["close"].pct_change().dropna()
   621	                    ret_b = df_b["close"].pct_change().dropna()
   622	                    cross_signals.extend(detect_lead_lag(ret_a, ret_b, sym_a, sym_b))
   623	                    cross_signals.extend(detect_lead_lag(ret_b, ret_a, sym_b, sym_a))
   624	
   625	        # Composite signals: multi-source (sentiment, on-chain, mining + price)
   626	        composite_signals = []
   627	        try:
   628	            alt_sources = self.alt_data.fetch_all()
   629	            if alt_sources:
   630	                for symbol, timeframe, _, df in results:
   631	                    split_idx = int(len(df) * oos_cutoff)
   632	                    is_prices = df["close"].iloc[:split_idx]
   633	                    csigs = scan_composite(is_prices, alt_sources)
   634	                    for s in csigs:
   635	                        s.symbol = symbol
   636	                        s.timeframe = timeframe
   637	                    composite_signals.extend(csigs)
   638	                log.info("Found %d composite signals from %d alt sources",
   639	                         len(composite_signals), len(alt_sources))
   640	        except Exception as e:
   641	            log.warning("Composite signal scan failed: %s", e)
   642	
   643	        # Calendar signals: temporal patterns (EOM, weekend, US session)
   644	        calendar_signals = []
   645	        for symbol, timeframe, _, df in results:
   646	            split_idx = int(len(df) * oos_cutoff)
   647	            is_prices = df["close"].iloc[:split_idx]
   648	            csigs = scan_calendar(is_prices)
   649	            for s in csigs:
   650	                s.symbol = symbol
   651	                s.timeframe = timeframe
   652	            calendar_signals.extend(csigs)
   653	        if calendar_signals:
   654	            log.info("Found %d calendar signals", len(calendar_signals))
   655	        composite_signals.extend(calendar_signals)
   656	
   657	        extra_signals = cross_signals + composite_signals
   658	        if extra_signals:
   659	            # Attach extra signals to the BTC/USDT 1h anchor
   660	            anchor = ("BTC/USDT", "1h")
   661	            anchor_found = False
   662	            for idx, (sym, tf, sigs, df) in enumerate(results):
   663	                if (sym, tf) == anchor:
   664	                    results[idx] = (sym, tf, sigs + extra_signals, df)
   665	                    anchor_found = True
   666	                    break
   667	            if not anchor_found and results:
   668	                sym, tf, sigs, df = results[0]
   669	                results[0] = (sym, tf, sigs + extra_signals, df)
   670	            log.info("Found %d cross-asset + %d composite signals",
   671	                     len(cross_signals), len(composite_signals))
   672	
   673	        return results
   674	
   675	    def generate_hypotheses(self, signal_results: list[tuple[str, str, list, pd.DataFrame]]) -> list[Hypothesis]:
   676	        """Phase 2: Convert signals into hypotheses. Reuse existing hypothesis IDs."""
   677	        candidates: list[tuple[Hypothesis, str]] = []  # (hypothesis, source_method)
   678	
   679	        for symbol, timeframe, signals, _ in signal_results:
   680	            for signal in signals:
   681	                # Try composite generators first, then single-source
   682	                gen = COMPOSITE_GENERATORS.get(signal.method)
   683	                if gen:
   684	                    sym = signal.symbol or symbol
   685	                    tf = signal.timeframe or timeframe
   686	                    candidates.append((gen(signal, sym, tf), signal.method))
   687	                else:
   688	                    h = from_signal(signal, symbol, timeframe)
   689	                    if h:
   690	                        candidates.append((h, signal.method))
   691	
   692	        # Graph-driven generation
   693	        graph = self.graph_store.load()
   694	        gap_hypotheses = from_graph_gaps(graph)
   695	        candidates.extend([(h, "graph_gaps") for h in gap_hypotheses])
   696	
   697	        # Deduplicate and resolve to durable IDs
   698	        seen_claims: set[str] = set()
   699	        unique: list[tuple[Hypothesis, str]] = []
   700	        for h, method in candidates:
   701	            if h.claim in seen_claims:
   702	                continue
   703	            seen_claims.add(h.claim)
   704	
   705	            # Check for existing hypothesis with same claim
   706	            existing = self._find_existing_hypothesis(h.claim)
   707	            if existing:
   708	                if existing.status in (HypothesisStatus.PROMOTED, HypothesisStatus.FALSIFIED):
   709	                    log.debug("Skipping already-resolved hypothesis: %s", existing.id)
   710	                    continue
   711	                unique.append((existing, method))
   712	            else:
   713	                # Assign stable ID from claim hash
   714	                h.id = _claim_hash(h.claim)
   715	                unique.append((h, method))
   716	
   717	        # Prioritize: calendar > composite > single-source, break ties by method promotion weight
   718	        method_weights = self.compute_method_weights()
   719	
   720	        def _score(item: tuple[Hypothesis, str]) -> float:
   721	            h, method = item
   722	            base = 0.0
   723	            if "calendar" in h.tags:
   724	                base = 2.0
   725	            elif "composite" in h.tags:
   726	                base = 1.0
   727	            return base + method_weights.get(method, 0.5)
   728	
   729	        prioritized = sorted(unique, key=_score, reverse=True)
   730	        selected_pairs = prioritized[:5]
   731	        selected = [h for h, _ in selected_pairs]
   732	
   733	        # Apply Bonferroni correction: compute adjusted alpha per cycle
   734	        # but do NOT mutate h.significance_threshold (pre-registered, immutable)
   735	        # Store on each hypothesis object for this cycle (not persisted on model)
   736	        n_tests = max(1, len(selected))
   737	        for h in selected:
   738	            h._bonferroni_n = n_tests  # type: ignore[attr-defined]
   739	
   740	        # Log method → hypothesis_id attribution for future weight computation
   741	        method_hypothesis_ids: dict[str, list[str]] = {}
   742	        for h, method in selected_pairs:
   743	            method_hypothesis_ids.setdefault(method, []).append(h.id)
   744	
   745	        self._log_methodology({
   746	            "phase": "hypothesis_generation",
   747	            "total_generated": len(candidates),
   748	            "unique": len(unique),
   749	            "selected": len(selected),
   750	            "bonferroni_n": n_tests,
   751	            "adjusted_alpha": (selected[0].significance_threshold / n_tests) if selected else None,
   752	        })
   753	        self._log_methodology({
   754	            "phase": "hypothesis_sources",
   755	            "method_hypothesis_ids": method_hypothesis_ids,
   756	        })
   757	
   758	        return selected
   759	
   760	    def compute_method_weights(self) -> dict[str, float]:
   761	        """Read methodology.jsonl to compute per-method promotion rate.
   762	
   763	        Uses Laplace smoothing: (promotions + 1) / (promotions + kills + 2).
   764	        Methods with no history get 0.5 (neutral). Reads hypothesis_sources
   765	        records to map method → hypothesis_id, then decision records for outcomes.
   766	        """
   767	        if not self.methodology_log.exists():
   768	            return {}
   769	
   770	        method_to_hyps: dict[str, set[str]] = {}
   771	        hyp_outcomes: dict[str, str] = {}
   772	
   773	        with open(self.methodology_log) as f:
   774	            for line in f:
   775	                line = line.strip()
   776	                if not line:
   777	                    continue
   778	                try:
   779	                    rec = json.loads(line)
   780	                except json.JSONDecodeError:
   781	                    continue
   782	                phase = rec.get("phase", "")
   783	                if phase == "hypothesis_sources":
   784	                    for method, ids in rec.get("method_hypothesis_ids", {}).items():
   785	                        method_to_hyps.setdefault(method, set()).update(ids)
   786	                elif phase == "decision":
   787	                    hid = rec.get("hypothesis_id")
   788	                    action = rec.get("action")
   789	                    if hid and action:
   790	                        hyp_outcomes[hid] = action
   791	
   792	        weights: dict[str, float] = {}
   793	        for method, hyp_ids in method_to_hyps.items():
   794	            promotes = sum(1 for hid in hyp_ids if hyp_outcomes.get(hid) == "promote")
   795	            kills = sum(1 for hid in hyp_ids if hyp_outcomes.get(hid) == "kill")
   796	            weights[method] = (promotes + 1) / (promotes + kills + 2)
   797	
   798	        return weights
   799	
   800	    def _build_composite_signal(self, h: Hypothesis, is_df: pd.DataFrame) -> pd.Series | None:
   801	        """Build regime-holding signal from composite hypothesis.
   802	
   803	        Returns None if required alt data is unavailable.
   804	        These signals trade rarely — enter on trigger, hold for N bars, then flat.
   805	        """
   806	        prices = is_df["close"]
   807	        holding = 20
   808	        for tag in h.tags:
   809	            if tag.startswith("hold_"):
   810	                holding = int(tag.split("_")[1])
   811	
   812	        try:
   813	            alt_sources = self.alt_data.fetch_all()
   814	        except Exception:
   815	            return None
   816	
   817	        signals = pd.Series(0, index=prices.index)
   818	
   819	        if "fear_capitulation" in h.tags:
   820	            fg = alt_sources.get("fear_greed")
   821	            if fg is None or "fear_greed" not in fg.columns:
   822	                return None
   823	            fg_aligned = fg["fear_greed"].reindex(prices.index, method="ffill").fillna(50)
   824	            rolling_high = prices.rolling(60).max()
   825	            drawdown = (prices - rolling_high) / rolling_high
   826	            trigger = (fg_aligned < 25) & (drawdown < -0.10)
   827	            signals = self._apply_regime_hold(trigger, holding, direction=1)
   828	
   829	        elif "greed_euphoria" in h.tags:
   830	            fg = alt_sources.get("fear_greed")
   831	            if fg is None or "fear_greed" not in fg.columns:
   832	                return None
   833	            fg_aligned = fg["fear_greed"].reindex(prices.index, method="ffill").fillna(50)
   834	            rolling_low = prices.rolling(60).min()
   835	            rally = (prices - rolling_low) / rolling_low
   836	            trigger = (fg_aligned > 75) & (rally > 0.15)
   837	            signals = self._apply_regime_hold(trigger, holding, direction=-1)
   838	
   839	        elif "onchain_divergence" in h.tags:
   840	            ov = alt_sources.get("onchain_volume")
   841	            if ov is None or "onchain_volume_usd" not in ov.columns:
   842	                return None
   843	            ov_aligned = ov["onchain_volume_usd"].reindex(prices.index, method="ffill")
   844	            px_trend = prices.pct_change(20)
   845	            ov_trend = ov_aligned.pct_change(20)
   846	            if "bullish" in h.tags:
   847	                trigger = (px_trend < -0.10) & (ov_trend > 0.10)
   848	                signals = self._apply_regime_hold(trigger, holding, direction=1)
   849	            else:
   850	                trigger = (px_trend > 0.10) & (ov_trend < -0.10)
   851	                signals = self._apply_regime_hold(trigger, holding, direction=-1)
   852	
   853	        elif "miner_capitulation" in h.tags:
   854	            hr = alt_sources.get("hashrate")
   855	            if hr is None or "hashrate" not in hr.columns:
   856	                return None
   857	            hr_aligned = hr["hashrate"].reindex(prices.index, method="ffill")
   858	            hr_peak = hr_aligned.rolling(30).max()
   859	            hr_dd = (hr_aligned - hr_peak) / hr_peak
   860	            was_down = hr_dd.rolling(30).min() < -0.10
   861	            recovering = hr_dd > -0.03
   862	            trigger = was_down & recovering & (~(was_down & recovering).shift(1).fillna(False))
   863	            signals = self._apply_regime_hold(trigger, holding, direction=1)
   864	
   865	        elif "end_of_month" in h.tags:
   866	            # Short last 3 days of month if negative drift, long if positive
   867	            dom = prices.index.day
   868	            eom_mask = pd.Series(dom >= 29, index=prices.index)
   869	            direction = -1 if "negative" in h.tags else 1
   870	            signals = pd.Series(0, index=prices.index)
   871	            signals.loc[eom_mask] = direction
   872	            return signals
   873	
   874	        elif "weekend_skip" in h.tags:
   875	            # Long only on weekdays, flat on weekends
   876	            dow = prices.index.dayofweek
   877	            weekday_mask = pd.Series(dow < 5, index=prices.index)
   878	            signals = pd.Series(0, index=prices.index)
   879	            signals.loc[weekday_mask] = 1
   880	            return signals
   881	
   882	        elif "us_session" in h.tags:
   883	            # Long only during US session (13:00-21:00 UTC)
   884	            hour = prices.index.hour
   885	            us_mask = pd.Series((hour >= 13) & (hour < 21), index=prices.index)
   886	            signals = pd.Series(0, index=prices.index)
   887	            signals.loc[us_mask] = 1
   888	            return signals
   889	
   890	        elif "regime_confluence" in h.tags:
   891	            fg = alt_sources.get("fear_greed")
   892	            ov = alt_sources.get("onchain_volume")
   893	            if fg is None or ov is None:
   894	                return None
   895	            fg_aligned = fg["fear_greed"].reindex(prices.index, method="ffill").fillna(50)
   896	            ov_aligned = ov["onchain_volume_usd"].reindex(prices.index, method="ffill")
   897	            ov_trend = ov_aligned.pct_change(20)
   898	            if "bullish" in h.tags:
   899	                px_low = prices.rolling(60).min()
   900	                trigger = (fg_aligned < 25) & (ov_trend > 0.05) & (prices <= px_low * 1.05)
   901	                signals = self._apply_regime_hold(trigger, holding, direction=1)
   902	            else:
   903	                px_high = prices.rolling(60).max()
   904	                trigger = (fg_aligned > 75) & (ov_trend < -0.05) & (prices >= px_high * 0.95)
   905	                signals = self._apply_regime_hold(trigger, holding, direction=-1)
   906	        else:
   907	            return None
   908	
   909	        return signals.reindex(prices.index).fillna(0)
   910	
   911	    @staticmethod
   912	    def _apply_regime_hold(trigger: pd.Series, holding_period: int, direction: int) -> pd.Series:
   913	        """Convert trigger events into held positions.
   914	
   915	        Enter on trigger, hold for holding_period bars, then go flat.
   916	        If a new trigger fires during a hold, extend the hold.
   917	        This produces sparse signals — only a few trades per year.
   918	        """
   919	        signals = pd.Series(0, index=trigger.index)
   920	        bars_remaining = 0
   921	        for i in range(len(trigger)):
   922	            if trigger.iloc[i]:
   923	                bars_remaining = holding_period
   924	            if bars_remaining > 0:
   925	                signals.iloc[i] = direction
   926	                bars_remaining -= 1
   927	        return signals
   928	
   929	    def _build_signal_from_hypothesis(self, h: Hypothesis, is_df: pd.DataFrame) -> pd.Series:
   930	        """Build a trading signal series using in-sample data only."""
   931	        # Try composite signal builder first
   932	        if "composite" in h.tags:
   933	            composite = self._build_composite_signal(h, is_df)
   934	            if composite is not None:
   935	                return composite
   936	
   937	        prices = is_df["close"]
   938	        returns = prices.pct_change().dropna()
   939	
   940	        if "autocorrelation" in h.tags:
   941	            lag = 1
   942	            for tag in h.tags:
   943	                if tag.startswith("lag_"):
   944	                    lag = int(tag.split("_")[1])
   945	            if "momentum" in h.tags:
   946	                signals = (returns.rolling(lag).mean() > 0).astype(int).replace(0, -1)
   947	            else:
   948	                signals = (returns.rolling(lag).mean() < 0).astype(int).replace(0, -1)
   949	        elif "momentum" in h.tags and any(t.startswith("lookback_") for t in h.tags):
   950	            lookback = 20
   951	            for tag in h.tags:
   952	                if tag.startswith("lookback_"):
   953	                    lookback = int(tag.split("_")[1])
   954	            rolling_ret = returns.rolling(lookback).sum()
   955	            if "reversal" in h.tags:
   956	                signals = -(rolling_ret > 0).astype(int).replace(0, -1)
   957	            else:
   958	                signals = (rolling_ret > 0).astype(int).replace(0, -1)
   959	        elif "vol_scaling" in h.tags:
   960	            # Volatility-scaled strategy: reduce position in high-vol, increase in low-vol
   961	            vol = returns.abs().rolling(20).mean()
   962	            vol_ma = vol.rolling(50).mean()
   963	            vol_ratio = (vol / vol_ma).reindex(prices.index).fillna(1.0)
   964	            signals = pd.Series(1, index=prices.index)  # default long
   965	            signals.loc[vol_ratio > 1.5] = 0    # step out in high vol
   966	            signals.loc[vol_ratio < 0.7] = 1    # full position in low vol
   967	        elif "pairs_trading" in h.tags:
   968	            # Pairs trading: use price z-score as proxy for spread dislocation
   969	            ma = prices.rolling(50).mean()
   970	            std = prices.rolling(50).std()
   971	            z = ((prices - ma) / std).reindex(prices.index).fillna(0)
   972	            signals = pd.Series(0, index=prices.index)
   973	            signals.loc[z < -1.5] = 1   # buy when spread is low
   974	            signals.loc[z > 1.5] = -1   # sell when spread is high
   975	        elif "lead_lag" in h.tags:
   976	            # Lead-lag: trade the follower based on the leader's return
   977	            # Since we only have the follower's data here, use its own lagged returns
   978	            # as a proxy (the signal builder gets the follower's data)
   979	            lag_ret = returns.shift(1).reindex(prices.index).fillna(0)
   980	            signals = pd.Series(0, index=prices.index)

exec
/bin/bash -lc "sed -n '980,1460p' /opt/workspace/projects/atlas/src/atlas/runner.py | nl -ba -v980" in /opt/workspace/projects/atlas
 succeeded in 0ms:
   980	            signals = pd.Series(0, index=prices.index)
   981	            signals.loc[lag_ret > 0] = 1
   982	            signals.loc[lag_ret < 0] = -1
   983	        elif "skew" in h.tags:
   984	            # Skew strategy: positive skew → buy dips, negative skew → fade rallies
   985	            ma = prices.rolling(20).mean()
   986	            std = prices.rolling(20).std()
   987	            z = (prices - ma) / std
   988	            signals = pd.Series(0, index=prices.index)
   989	            if "positive" in h.tags:
   990	                # Buy when below MA (dips), expecting asymmetric upside
   991	                signals[z < -1.0] = 1
   992	            else:
   993	                # Sell when above MA (rallies), expecting mean reversion / crash
   994	                signals[z > 1.0] = -1
   995	        elif "mean_reversion" in h.tags:
   996	            window = 20
   997	            for tag in h.tags:
   998	                if tag.startswith("ma_"):
   999	                    window = int(tag.split("_")[1])
  1000	            ma = prices.rolling(window).mean()
  1001	            std = prices.rolling(window).std()
  1002	            z = (prices - ma) / std
  1003	            signals = pd.Series(0, index=prices.index)
  1004	            signals[z < -2.0] = 1
  1005	            signals[z > 2.0] = -1
  1006	        elif "volatility" in h.tags or "regime" in h.tags:
  1007	            vol = returns.rolling(20).std()
  1008	            vol_ma = vol.rolling(50).mean()
  1009	            signals = pd.Series(0, index=prices.index)
  1010	            signals[vol < vol_ma * 0.7] = 1
  1011	            signals[vol > vol_ma * 1.5] = -1
  1012	        elif "volume" in h.tags:
  1013	            if "volume" in is_df.columns:
  1014	                vol_z = (is_df["volume"] - is_df["volume"].rolling(20).mean()) / is_df["volume"].rolling(20).std()
  1015	                ret_dir = returns.rolling(3).mean()
  1016	                signals = pd.Series(0, index=prices.index)
  1017	                mask = vol_z > 3.0
  1018	                signals[mask & (ret_dir > 0)] = 1
  1019	                signals[mask & (ret_dir < 0)] = -1
  1020	            else:
  1021	                signals = pd.Series(0, index=prices.index)
  1022	        else:
  1023	            signals = (prices.pct_change(20) > 0).astype(int).replace(0, -1)
  1024	
  1025	        return signals
  1026	
  1027	    def run_experiment(self, h: Hypothesis, df: pd.DataFrame, symbol: str, timeframe: str) -> tuple[Experiment, Evidence | None]:
  1028	        """Phase 3: Design, execute, and evaluate an experiment.
  1029	
  1030	        Walk-forward evaluation only: the harness does NOT fit state on the
  1031	        training window (see walk_forward_backtest docstring). All current
  1032	        signal builders are stateless rolling indicators whose no-lookahead
  1033	        guarantee comes from past-anchored windows, not from train/test
  1034	        separation. Trainable signals would require extending the harness.
  1035	        """
  1036	        tf_periods = {"1h": 365 * 24, "4h": 365 * 6, "1d": 365, "1w": 52}
  1037	        periods_per_year = tf_periods.get(timeframe, 365 * 6)
  1038	
  1039	        # Bonferroni-adjusted alpha: persisted on the experiment so it survives restarts
  1040	        bonferroni_n = getattr(h, "_bonferroni_n", 1)
  1041	        adjusted_alpha = h.significance_threshold / bonferroni_n
  1042	
  1043	        exp = Experiment(
  1044	            hypothesis_id=h.id,
  1045	            description=f"Backtest {h.claim[:80]} on {symbol} {timeframe}",
  1046	            method="backtest",
  1047	            parameters={
  1048	                "symbol": symbol, "timeframe": timeframe, "lookback": len(df),
  1049	                "bonferroni_n": bonferroni_n, "adjusted_alpha": adjusted_alpha,
  1050	            },
  1051	            success_criteria=f"OOS Sharpe > 0 with p < {adjusted_alpha:.4f} (Bonferroni-adjusted)",
  1052	            failure_criteria=f"OOS Sharpe not significantly different from zero (p >= {adjusted_alpha:.4f})",
  1053	        )
  1054	        self._save_obj("experiments", exp.id, exp.model_dump())
  1055	
  1056	        try:
  1057	            # Walk-forward validation: expanding train window with 5 OOS folds
  1058	            signal_builder = lambda sub_df: self._build_signal_from_hypothesis(h, sub_df)
  1059	            wf = walk_forward_backtest(
  1060	                df, signal_builder,
  1061	                n_folds=5, train_ratio=0.7,
  1062	                periods_per_year=periods_per_year, fee_bps=26,
  1063	            )
  1064	
  1065	            # Statistical tests on concatenated OOS returns with Bonferroni-adjusted alpha
  1066	            alpha = adjusted_alpha
  1067	            oos_sharpe = sharpe_significance(wf.oos_returns, periods_per_year=periods_per_year, alpha=alpha)
  1068	            oos_mean = mean_return_test(wf.oos_returns, alpha=alpha)
  1069	            oos_boot = bootstrap_sharpe(wf.oos_returns, periods_per_year=periods_per_year, alpha=alpha)
  1070	
  1071	            exp.status = ExperimentStatus.COMPLETED
  1072	            exp.results = {
  1073	                "walk_forward": {
  1074	                    "n_folds": wf.n_folds,
  1075	                    "mean_oos_sharpe": wf.aggregate_oos_sharpe,
  1076	                    "folds": wf.folds,
  1077	                },
  1078	                "out_of_sample": {
  1079	                    "sharpe": wf.aggregate_oos_sharpe,
  1080	                    "total_return": float((1 + wf.oos_returns).prod() - 1),
  1081	                    "sharpe_p": oos_sharpe.p_value,
  1082	                    "mean_p": oos_mean.p_value,
  1083	                    "bootstrap_ci": [oos_boot.ci_lower, oos_boot.ci_upper],
  1084	                    "bonferroni_alpha": alpha,
  1085	                },
  1086	            }
  1087	            self._save_obj("experiments", exp.id, exp.model_dump())
  1088	
  1089	            # Evaluate evidence quality
  1090	            oos = exp.results["out_of_sample"]
  1091	            # Require BOTH sharpe and bootstrap to agree for strong
  1092	            both_significant = oos_sharpe.significant and oos_boot.significant
  1093	            is_positive = wf.aggregate_oos_sharpe > 0
  1094	
  1095	            if both_significant and is_positive:
  1096	                quality = EvidenceQuality.STRONG
  1097	                direction = EvidenceDirection.SUPPORTS
  1098	            elif is_positive and (oos_sharpe.significant or oos_boot.significant):
  1099	                quality = EvidenceQuality.MODERATE
  1100	                direction = EvidenceDirection.SUPPORTS
  1101	            elif wf.aggregate_oos_sharpe < -0.5 and both_significant:
  1102	                quality = EvidenceQuality.STRONG
  1103	                direction = EvidenceDirection.CONTRADICTS
  1104	            elif not is_positive and (oos_sharpe.p_value < 0.15 or oos_boot.p_value < 0.15):
  1105	                quality = EvidenceQuality.MODERATE
  1106	                direction = EvidenceDirection.CONTRADICTS
  1107	            else:
  1108	                quality = EvidenceQuality.WEAK
  1109	                direction = EvidenceDirection.INCONCLUSIVE
  1110	
  1111	            ev = Evidence(
  1112	                experiment_id=exp.id,
  1113	                hypothesis_id=h.id,
  1114	                evidence_class=EvidenceClass.OUT_OF_SAMPLE_TEST,
  1115	                quality=quality,
  1116	                direction=direction,
  1117	                summary=f"Walk-forward OOS Sharpe={wf.aggregate_oos_sharpe:.2f} ({wf.n_folds} folds, "
  1118	                        f"p={oos_sharpe.p_value:.3f}, α={alpha:.4f}). "
  1119	                        f"Bootstrap CI=[{oos_boot.ci_lower:.2f}, {oos_boot.ci_upper:.2f}]",
  1120	                statistics=oos,
  1121	            )
  1122	            self._save_obj("evidence", ev.id, ev.model_dump())
  1123	
  1124	            log.info("Experiment %s: WF OOS Sharpe=%.2f (%d folds) p=%.3f (α=%.4f) → %s %s",
  1125	                     exp.id, wf.aggregate_oos_sharpe, wf.n_folds, oos_sharpe.p_value, alpha,
  1126	                     quality.value, direction.value)
  1127	
  1128	            return exp, ev
  1129	
  1130	        except Exception as e:
  1131	            log.error("Experiment %s failed: %s", exp.id, e)
  1132	            exp.status = ExperimentStatus.FAILED
  1133	            exp.results = {"error": str(e)}
  1134	            self._save_obj("experiments", exp.id, exp.model_dump())
  1135	            return exp, None
  1136	
  1137	    def evaluate_and_decide(self, h: Hypothesis, cycle: ResearchCycle) -> str:
  1138	        """Phase 4-5: Evaluate accumulated evidence and decide.
  1139	
  1140	        Promotion requires:
  1141	        - ≥2 strong supporting evidence from DISTINCT experiments
  1142	        - ≥1 must be OOS or live
  1143	        - No unaddressed strong contradictory evidence
  1144	        """
  1145	        evidence = [Evidence.model_validate(d) for d in self._list_objs("evidence")
  1146	                    if d.get("hypothesis_id") == h.id]
  1147	
  1148	        if not evidence:
  1149	            return "continue"
  1150	
  1151	        gate = evaluate_promotion_gate(evidence)
  1152	        strong_support = gate["strong_support"]
  1153	        strong_contradict = gate["strong_contradict"]
  1154	        oos_support = gate["oos_support"]
  1155	        distinct_experiments = gate["distinct_experiments"]
  1156	
  1157	        # Kill if strong contradictory evidence
  1158	        if len(strong_contradict) >= 2:
  1159	            h.status = HypothesisStatus.FALSIFIED
  1160	            self._save_obj("hypotheses", h.id, h.model_dump())
  1161	            self._add_refuted_claim_to_graph(h, evidence)
  1162	            cycle.status = CycleStatus.CLOSED
  1163	            cycle.outcome = CycleOutcome.KILLED
  1164	            cycle.decision_rationale = f"Falsified: {len(strong_contradict)} strong contradictory evidence records"
  1165	            self._save_obj("cycles", cycle.id, cycle.model_dump())
  1166	            self.events.append(SessionEvent(
  1167	                session_id=cycle.id,
  1168	                event_type=EventType.DECISION_MADE,
  1169	                details={"action": "kill", "reason": cycle.decision_rationale},
  1170	            ))
  1171	            return "kill"
  1172	
  1173	        # Block promotion if ANY strong contradictory evidence exists
  1174	        if strong_contradict:
  1175	            log.info("Hypothesis %s has %d strong contradictions — cannot promote",
  1176	                     h.id, len(strong_contradict))
  1177	            return "continue"
  1178	
  1179	        # Promote if gate is met with distinct experiments
  1180	        if distinct_experiments >= 2 and len(oos_support) >= 1:
  1181	            primitive = ReasoningPrimitive(
  1182	                claim=h.claim,
  1183	                hypothesis_id=h.id,
  1184	                evidence_ids=[e.id for e in strong_support],
  1185	                confidence=min(0.95, 0.5 + 0.15 * distinct_experiments),
  1186	                tags=h.tags,
  1187	                causal_parents=[h.parent_primitive_id] if h.parent_primitive_id else [],
  1188	            )
  1189	            self._save_obj("primitives", primitive.id, primitive.model_dump())
  1190	
  1191	            graph = self.graph_store.load()
  1192	            try:
  1193	                graph.add_primitive(primitive)
  1194	            except ValueError as e:
  1195	                log.warning("Could not link parent: %s — adding as root", e)
  1196	                primitive.causal_parents = []
  1197	                graph.add_primitive(primitive)
  1198	            self.graph_store.save(graph)
  1199	
  1200	            h.status = HypothesisStatus.PROMOTED
  1201	            self._save_obj("hypotheses", h.id, h.model_dump())
  1202	            cycle.status = CycleStatus.CLOSED
  1203	            cycle.outcome = CycleOutcome.PROMOTED
  1204	            cycle.decision_rationale = (
  1205	                f"Promoted: {distinct_experiments} distinct strong experiments, "
  1206	                f"{len(oos_support)} OOS. Graph: {graph.node_count} nodes."
  1207	            )
  1208	            self._save_obj("cycles", cycle.id, cycle.model_dump())
  1209	            self.events.append(SessionEvent(
  1210	                session_id=cycle.id,
  1211	                event_type=EventType.PRIMITIVE_PROMOTED,
  1212	                details={"primitive_id": primitive.id, "claim": h.claim},
  1213	            ))
  1214	            self._log_methodology({
  1215	                "phase": "decision", "hypothesis_id": h.id, "action": "promote",
  1216	                "primitive_id": primitive.id, "graph_nodes": graph.node_count,
  1217	            })
  1218	            return "promote"
  1219	
  1220	        # Kill if all evidence is weak/contradictory after enough attempts
  1221	        all_weak_or_negative = all(
  1222	            e.direction != EvidenceDirection.SUPPORTS or e.quality == EvidenceQuality.WEAK
  1223	            for e in evidence
  1224	        )
  1225	        if all_weak_or_negative and len(evidence) >= 3:
  1226	            h.status = HypothesisStatus.FALSIFIED
  1227	            self._save_obj("hypotheses", h.id, h.model_dump())
  1228	            self._add_refuted_claim_to_graph(h, evidence)
  1229	            cycle.status = CycleStatus.CLOSED
  1230	            cycle.outcome = CycleOutcome.KILLED
  1231	            cycle.decision_rationale = f"Killed: {len(evidence)} evidence records, none strong/supporting"
  1232	            self._save_obj("cycles", cycle.id, cycle.model_dump())
  1233	            self.events.append(SessionEvent(
  1234	                session_id=cycle.id,
  1235	                event_type=EventType.DECISION_MADE,
  1236	                details={"action": "kill", "reason": cycle.decision_rationale},
  1237	            ))
  1238	            return "kill"
  1239	
  1240	        return "continue"
  1241	
  1242	    def _add_refuted_claim_to_graph(self, h: Hypothesis, evidence: list[Evidence]) -> None:
  1243	        """Project a killed hypothesis into the causal map as tested negative knowledge."""
  1244	        graph = self.graph_store.load()
  1245	        contradiction_count = sum(
  1246	            1
  1247	            for e in evidence
  1248	            if e.quality == EvidenceQuality.STRONG
  1249	            and e.direction == EvidenceDirection.CONTRADICTS
  1250	        )
  1251	        graph.add_refuted_hypothesis(
  1252	            h,
  1253	            [e.id for e in evidence],
  1254	            contradiction_count=contradiction_count,
  1255	        )
  1256	        self.graph_store.save(graph)
  1257	
  1258	    def register_predictions(self, signal_results, now: datetime | None = None) -> dict:
  1259	        """Register dated forward predictions for currently-detected signals.
  1260	
  1261	        Each detected pattern implies a forward forecast: net of fees, does it
  1262	        predict forward returns? One prediction per (claim, horizon bucket) keeps
  1263	        the hourly cycle idempotent and the windows non-overlapping; the scorer
  1264	        (2b) resolves them against realized data once the window closes. This is
  1265	        the un-exhaustible evidence path (CAUSAL_LOOP_AUDIT.md Q5) — it runs every
  1266	        cycle regardless of whether the backtest hypothesis space is exhausted.
  1267	        """
  1268	        now = now or datetime.now(timezone.utc)
  1269	        bucket, window_start, resolve = Prediction.forward_bucket(now, PREDICTION_HORIZON_DAYS)
  1270	        existing = {p.id for p in self.predictions.all()}
  1271	        registered = 0
  1272	        skipped_unreplayable = 0
  1273	        seen: set[str] = set()
  1274	        for symbol, timeframe, signals, _ in signal_results:
  1275	            for signal in signals:
  1276	                # Only forward-score strategies that reconstruct faithfully from
  1277	                # the frozen (symbol, timeframe, tags) spec. Proxy/fallback types
  1278	                # would produce meaningless live_observation evidence.
  1279	                if signal.method not in REPLAYABLE_METHODS:
  1280	                    skipped_unreplayable += 1
  1281	                    continue
  1282	                h = from_signal(signal, symbol, timeframe)
  1283	                if not h:
  1284	                    continue
  1285	                hid = _claim_hash(h.claim)
  1286	                pid = prediction_id(hid, PREDICTION_HORIZON_DAYS, bucket)
  1287	                if pid in seen or pid in existing:
  1288	                    seen.add(pid)
  1289	                    continue
  1290	                seen.add(pid)
  1291	                pred = Prediction(
  1292	                    id=pid,
  1293	                    hypothesis_id=hid,
  1294	                    claim=h.claim,
  1295	                    symbol=signal.symbol or symbol,
  1296	                    timeframe=signal.timeframe or timeframe,
  1297	                    strategy_tags=h.tags,
  1298	                    horizon_days=PREDICTION_HORIZON_DAYS,
  1299	                    bucket=bucket,
  1300	                    window_start_ts=window_start,
  1301	                    resolve_ts=resolve,
  1302	                    asof_ts=now,
  1303	                    statement=(
  1304	                        f"Net of {FEE_BPS}bps, a strategy implied by '{h.claim[:70]}' shows "
  1305	                        f"no significant edge over the {PREDICTION_HORIZON_DAYS:.0f}d forward "
  1306	                        f"window {window_start:%Y-%m-%d}..{resolve:%Y-%m-%d}"
  1307	                    ),
  1308	                )
  1309	                self.predictions.append(pred)
  1310	                registered += 1
  1311	        result = {
  1312	            "registered": registered,
  1313	            "skipped_unreplayable": skipped_unreplayable,
  1314	            "bucket": bucket,
  1315	            "window_start": window_start.isoformat(),
  1316	            "resolve": resolve.isoformat(),
  1317	            "open_total": self.predictions.count_open(),
  1318	        }
  1319	        if registered:
  1320	            self._log_methodology({"phase": "prediction_registration", **result})
  1321	        self._emit_telemetry("prediction.registered", details=result)
  1322	        return result
  1323	
  1324	    def score_due_predictions(self, now: datetime | None = None) -> dict:
  1325	        """Phase 2b: resolve predictions whose forward window has closed.
  1326	
  1327	        For each due prediction, replay the FROZEN strategy spec on realized data
  1328	        for the forward window only, write a conservative `live_observation`
  1329	        evidence record, and fill the prediction's resolution fields (append-only
  1330	        — the forecast fields are never touched). Runs every cycle so scoring is
  1331	        autonomous. The un-exhaustible evidence path: forward time keeps closing
  1332	        windows regardless of whether the backtest hypothesis space is exhausted.
  1333	        """
  1334	        now = now or datetime.now(timezone.utc)
  1335	        due = self.predictions.list_due(now)
  1336	        scored = 0
  1337	        unresolvable = 0
  1338	        outcomes: dict[str, int] = {}
  1339	        for p in due:
  1340	            try:
  1341	                resolved = self._score_one_prediction(p, now)
  1342	            except Exception as exc:
  1343	                log.warning("Scoring prediction %s failed: %s", p.id, exc)
  1344	                continue
  1345	            self.predictions.update(resolved)
  1346	            if resolved.status == "resolved":
  1347	                scored += 1
  1348	                outcomes[resolved.outcome] = outcomes.get(resolved.outcome, 0) + 1
  1349	            else:
  1350	                unresolvable += 1
  1351	        result = {
  1352	            "scored": scored,
  1353	            "unresolvable": unresolvable,
  1354	            "outcomes": outcomes,
  1355	            "open_remaining": self.predictions.count_open(),
  1356	        }
  1357	        if scored or unresolvable:
  1358	            self._log_methodology({"phase": "prediction_scoring", **result})
  1359	            self._emit_telemetry("prediction.resolved", details=result)
  1360	        return result
  1361	
  1362	    def _score_one_prediction(self, p: Prediction, now: datetime):
  1363	        """Score one due prediction; return the resolved (or unresolvable) copy.
  1364	
  1365	        Guardrails: (1) reconstruct from the frozen tags only — never re-detect;
  1366	        (2) score returns inside [window_start, resolve_ts] only, using an earlier
  1367	        warm-up prefix solely to prime rolling indicators; (3) set only resolution
  1368	        fields (append-only).
  1369	        """
  1370	        warmup = timedelta(days=p.horizon_days)  # generous prefix for rolling indicators
  1371	        since = (p.window_start_ts - warmup).strftime("%Y-%m-%d")
  1372	        # `since` forces a cache-miss on a fresh (window-covering) fetch, bypassing
  1373	        # the indefinitely-cached main scan CSV (which lags the forward window).
  1374	        df = self.market.fetch_ohlcv(symbol=p.symbol, timeframe=p.timeframe, since=since, limit=100000)
  1375	
  1376	        window_mask = (df.index >= p.window_start_ts) & (df.index <= p.resolve_ts)
  1377	        window = df.loc[window_mask]
  1378	        if len(window) < SCORE_MIN_BARS:
  1379	            return p.model_copy(update={
  1380	                "status": "unresolvable",
  1381	                "outcome": "insufficient_data",
  1382	                "resolved_at": now,
  1383	            })
  1384	
  1385	        # Build the signal on [window_start - warmup, resolve_ts] so rolling
  1386	        # indicators are primed, then score ONLY the window's returns.
  1387	        full = df.loc[(df.index >= p.window_start_ts - warmup) & (df.index <= p.resolve_ts)]
  1388	        frozen_h = Hypothesis(
  1389	            claim=p.claim,
  1390	            tags=list(p.strategy_tags),
  1391	            rationale="frozen forward-prediction spec (replay only)",
  1392	            falsification_criteria="frozen",
  1393	        )
  1394	        signals = self._build_signal_from_hypothesis(frozen_h, full)
  1395	
  1396	        tf_periods = {"1h": 365 * 24, "4h": 365 * 6, "1d": 365, "1w": 52}
  1397	        periods_per_year = tf_periods.get(p.timeframe, 365 * 6)
  1398	        # Pass window prices + full signals; run_backtest reindexes signals to the
  1399	        # window returns (the values were computed with warm-up) and applies fees.
  1400	        bt = run_backtest(window["close"], signals, periods_per_year=periods_per_year, fee_bps=FEE_BPS)
  1401	        realized_sharpe = float(bt.sharpe_ratio)
  1402	        realized_return = float(bt.total_return)
  1403	        realized_up = 1.0 if realized_return > 0 else 0.0
  1404	        brier = (p.predicted_prob_up - realized_up) ** 2
  1405	
  1406	        if realized_sharpe >= SCORE_EDGE_SHARPE and realized_return > 0:
  1407	            realized_label, outcome, direction = "edge", "edge_appeared", EvidenceDirection.SUPPORTS
  1408	        elif realized_sharpe <= 0 or realized_return <= 0:
  1409	            realized_label, outcome, direction = "no_edge", "confirmed_null", EvidenceDirection.CONTRADICTS
  1410	        else:
  1411	            realized_label, outcome, direction = "marginal", "inconclusive", EvidenceDirection.INCONCLUSIVE
  1412	
  1413	        # Single window is noisy: cap at MODERATE (never STRONG) so the ledger
  1414	        # cannot manufacture a promotion on the current feature space.
  1415	        quality = EvidenceQuality.WEAK if outcome == "inconclusive" else EvidenceQuality.MODERATE
  1416	
  1417	        ev = Evidence(
  1418	            experiment_id=p.id,  # the prediction is its own distinct experiment
  1419	            hypothesis_id=p.hypothesis_id,
  1420	            evidence_class=EvidenceClass.LIVE_OBSERVATION,
  1421	            quality=quality,
  1422	            direction=direction,
  1423	            summary=(
  1424	                f"Forward window {p.window_start_ts:%Y-%m-%d}..{p.resolve_ts:%Y-%m-%d}: "
  1425	                f"realized Sharpe {realized_sharpe:.2f}, return {realized_return * 100:.1f}% "
  1426	                f"net {FEE_BPS}bps over {len(window)} bars → {outcome}"
  1427	            ),
  1428	            statistics={
  1429	                "realized_sharpe": realized_sharpe,
  1430	                "realized_return": realized_return,
  1431	                "brier_score": brier,
  1432	                "n_bars": len(window),
  1433	                "prediction_id": p.id,
  1434	                "bucket": p.bucket,
  1435	            },
  1436	            data_range=f"{p.window_start_ts:%Y-%m-%d} to {p.resolve_ts:%Y-%m-%d}",
  1437	        )
  1438	        self._save_obj("evidence", ev.id, ev.model_dump())
  1439	
  1440	        return p.model_copy(update={
  1441	            "status": "resolved",
  1442	            "realized_return": realized_return,
  1443	            "realized_sharpe": realized_sharpe,
  1444	            "realized_label": realized_label,
  1445	            "brier_score": brier,
  1446	            "outcome": outcome,
  1447	            "resolved_at": now,
  1448	        })
  1449	
  1450	    def run_cycle(self) -> dict:
  1451	        """Execute one complete research cycle."""
  1452	        log.info("=== Starting research cycle ===")
  1453	        self._emit_telemetry("cycle.started")
  1454	        cycle_report = {"timestamp": datetime.now(timezone.utc).isoformat(), "hypotheses": []}
  1455	
  1456	        # Phase 1: Scan in-sample data for signals
  1457	        signal_results = self.scan_signals()
  1458	        cycle_report["signals_found"] = sum(len(s) for _, _, s, _ in signal_results)
  1459	
  1460	        # Forward-prediction ledger: register dated forward forecasts for the

exec
/bin/bash -lc "sed -n '1460,1956p' /opt/workspace/projects/atlas/src/atlas/runner.py | nl -ba -v1460" in /opt/workspace/projects/atlas
 succeeded in 0ms:
  1460	        # Forward-prediction ledger: register dated forward forecasts for the
  1461	        # detected signals (idempotent per horizon bucket). Independent of the
  1462	        # backtest path so it produces fresh evidence even when the hypothesis
  1463	        # space is exhausted. Defensive try/except: a ledger bug must not break
  1464	        # the research cycle.
  1465	        try:
  1466	            cycle_report["predictions"] = self.register_predictions(signal_results)
  1467	        except Exception as exc:
  1468	            log.warning("Prediction registration failed: %s", exc)
  1469	
  1470	        # Phase 2b: score any predictions whose forward window has closed. Runs
  1471	        # every cycle so calibration accrues autonomously. Defensive: a scorer
  1472	        # bug must not break the research cycle.
  1473	        try:
  1474	            cycle_report["prediction_scoring"] = self.score_due_predictions()
  1475	        except Exception as exc:
  1476	            log.warning("Prediction scoring failed: %s", exc)
  1477	
  1478	        # Phase 2: Generate hypotheses (with durable IDs and Bonferroni correction)
  1479	        hypotheses = self.generate_hypotheses(signal_results)
  1480	
  1481	        # Phase 2a: Re-include orphaned TESTING hypotheses that have an
  1482	        # unfresh DEFAULT_UNIVERSE dataset. P1 dispatch handoff
  1483	        # (atlas-testing-reeval-p1-2026-05-02T16-48Z.md). Without this,
  1484	        # A+C+D2 promotes hypotheses but they orphan after one cycle —
  1485	        # observed 2026-05-02 as 14 consecutive empty cycles.
  1486	        # MUST run before top-up so re-evaluating active TESTING work is
  1487	        # preferred over promoting from the cold FORMULATED pool.
  1488	        hypotheses = self._include_orphaned_testing(hypotheses)
  1489	
  1490	        # Phase 2b: Top up from FORMULATED pool when signal-driven generation
  1491	        # under-fills the cycle. Per principal decision A+C+D2 (handoff
  1492	        # atlas-pool-rotation-decision.md, 2026-05-01): keep the loop from
  1493	        # silently starving when current signal scans don't re-fire prior
  1494	        # hypotheses. STRICT-D2 marks data-unavailable hypotheses INFEASIBLE
  1495	        # so they don't repeatedly block the auto-top-up.
  1496	        hypotheses = self._top_up_from_formulated_pool(hypotheses)
  1497	
  1498	        # Recompute Bonferroni adjustment now that the cycle's test set is
  1499	        # finalized — generate_hypotheses stamped its own n_tests, but the
  1500	        # top-up may have added more, which would understate the
  1501	        # multiple-testing burden.
  1502	        n_tests = max(1, len(hypotheses))
  1503	        for h in hypotheses:
  1504	            h._bonferroni_n = n_tests  # type: ignore[attr-defined]
  1505	
  1506	        cycle_report["hypotheses_generated"] = len(hypotheses)
  1507	
  1508	        if not hypotheses:
  1509	            log.info("No hypotheses generated this cycle")
  1510	            backfill_stats = backfill_falsified_claims(self.state, self.graph_store)
  1511	            graph = self.graph_store.load()
  1512	            cycle_report["graph_nodes"] = graph.node_count
  1513	            cycle_report["graph_edges"] = graph.edge_count
  1514	            cycle_report["no_action"] = {
  1515	                "reason": "hypothesis_space_exhausted",
  1516	                "signals_found": cycle_report.get("signals_found", 0),
  1517	                "hypotheses_generated": 0,
  1518	                "backfill": backfill_stats,
  1519	            }
  1520	            # Emit cycle.completed even on the empty-hypothesis path so the
  1521	            # S3-P2 gate is not blind to "loop is starving" failures
  1522	            # (regression: 04-30 14:18Z URGENT — runner ran 14h producing
  1523	            # nothing while the gate saw no events to count).
  1524	            self._emit_telemetry(
  1525	                "cycle.completed",
  1526	                details={
  1527	                    "hypotheses_evaluated": 0,
  1528	                    "total_evidence_store_size": len(self.state.list_all("evidence")),
  1529	                    "signals_found": cycle_report.get("signals_found", 0),
  1530	                    "graph_nodes": graph.node_count,
  1531	                    "graph_edges": graph.edge_count,
  1532	                    "decisions_by_kind": {},
  1533	                    "no_action_reason": "hypothesis_space_exhausted",
  1534	                    "refuted_nodes": graph.status_counts().get("refuted", 0),
  1535	                    "backfill": backfill_stats,
  1536	                },
  1537	            )
  1538	            try:
  1539	                self._update_streak_counter({})
  1540	            except Exception as exc:
  1541	                log.warning("Streak counter update failed: %s", exc)
  1542	            try:
  1543	                self._maybe_escalate_frozen_loop()
  1544	            except Exception as exc:
  1545	                log.warning("Frozen-loop escalation check failed: %s", exc)
  1546	            return cycle_report
  1547	
  1548	        # Build a lookup from hypothesis claim to the full df
  1549	        claim_to_data: dict[str, tuple[str, str, pd.DataFrame]] = {}
  1550	        for symbol, timeframe, signals, df in signal_results:
  1551	            for signal in signals:
  1552	                h_candidate = from_signal(signal, symbol, timeframe)
  1553	                if h_candidate:
  1554	                    claim_to_data[h_candidate.claim] = (symbol, timeframe, df)
  1555	
  1556	        # Phase 3-5: For each hypothesis, run experiments and decide
  1557	        for h in hypotheses:
  1558	            # Persist hypothesis (or it already exists with same ID)
  1559	            if not self._load_obj("hypotheses", h.id):
  1560	                self._save_obj("hypotheses", h.id, h.model_dump())
  1561	
  1562	            h_report = {"id": h.id, "claim": h.claim, "experiments": []}
  1563	            is_graph_gap = "graph_gap" in h.tags
  1564	
  1565	            # Determine which datasets to test on. Primary from signal source,
  1566	            # plus additional datasets for cross-validation (distinct experiments).
  1567	            existing_evidence = [Evidence.model_validate(d) for d in self._list_objs("evidence")
  1568	                                 if d.get("hypothesis_id") == h.id]
  1569	            fresh_tested_datasets = self._fresh_tested_datasets(existing_evidence)
  1570	
  1571	            # Build candidate datasets: primary first, then cross-validation pairs
  1572	            datasets = []
  1573	            if h.claim in claim_to_data:
  1574	                sym, tf, df = claim_to_data[h.claim]
  1575	                datasets.append((sym, tf, df))
  1576	            elif is_graph_gap:
  1577	                parsed = self._parse_dataset_from_hypothesis(h)
  1578	                if parsed and parsed in DEFAULT_UNIVERSE_SET:
  1579	                    try:
  1580	                        df = self.market.fetch_ohlcv(symbol=parsed[0], timeframe=parsed[1], limit=100000)
  1581	                        if len(df) >= MIN_BARS_FOR_RESEARCH:
  1582	                            datasets.append((parsed[0], parsed[1], df))
  1583	                    except Exception as exc:
  1584	                        log.info("Graph-gap dataset fetch failed for %s: %s", h.id, exc)
  1585	
  1586	            # Extract the base asset from tags for cross-validation
  1587	            base_asset = None
  1588	            for tag in h.tags:
  1589	                if "usdt" in tag:
  1590	                    base_asset = tag.replace("_", "/").upper()
  1591	                    break
  1592	
  1593	            # Add cross-validation datasets (same strategy, different data)
  1594	            if not is_graph_gap:
  1595	                for sym, tf in DEFAULT_UNIVERSE:
  1596	                    if (sym, tf) not in fresh_tested_datasets and (not datasets or (sym, tf) != (datasets[0][0], datasets[0][1])):
  1597	                        try:
  1598	                            xdf = self.market.fetch_ohlcv(symbol=sym, timeframe=tf, limit=100000)
  1599	                            if len(xdf) >= 200:
  1600	                                datasets.append((sym, tf, xdf))
  1601	                        except Exception:
  1602	                            continue
  1603	                    if len(datasets) >= 3:
  1604	                        break
  1605	
  1606	            if not datasets:
  1607	                if is_graph_gap:
  1608	                    h_report["skip_reason"] = "no_claim_faithful_dataset"
  1609	                    h_report["decision"] = "continue"
  1610	                    self._log_methodology({
  1611	                        "phase": "experiment_selection",
  1612	                        "hypothesis_id": h.id,
  1613	                        "skipped": "no_claim_faithful_dataset",
  1614	                        "tags": h.tags,
  1615	                    })
  1616	                    cycle_report["hypotheses"].append(h_report)
  1617	                    self._emit_telemetry(
  1618	                        "hypothesis.decided",
  1619	                        details={
  1620	                            "hypothesis_id": h.id,
  1621	                            "decision": "continue",
  1622	                            "skip_reason": "no_claim_faithful_dataset",
  1623	                            "total_evidence_store_size": len(self.state.list_all("evidence")),
  1624	                        },
  1625	                    )
  1626	                    continue
  1627	                symbol, timeframe = "BTC/USDT", "1h"
  1628	                df = self.market.fetch_ohlcv(symbol=symbol, timeframe=timeframe, limit=100000)
  1629	                datasets.append((symbol, timeframe, df))
  1630	
  1631	            # Find or create a cycle only after we know the hypothesis has a
  1632	            # claim-faithful dataset to test. Otherwise skipped graph-gap
  1633	            # followups create permanent active-cycle clutter.
  1634	            cycle = self._find_active_cycle(h.id)
  1635	            if not cycle:
  1636	                cycle = ResearchCycle(hypothesis_id=h.id)
  1637	                self._save_obj("cycles", cycle.id, cycle.model_dump())
  1638	                self.events.append(SessionEvent(
  1639	                    session_id=cycle.id,
  1640	                    event_type=EventType.HYPOTHESIS_FORMULATED,
  1641	                    details={"hypothesis_id": h.id, "claim": h.claim},
  1642	                ))
  1643	
  1644	            # Test on each dataset (distinct experiments for promotion gate)
  1645	            n_folds = 5
  1646	            min_bars = n_folds * 50 / 0.3  # each OOS fold needs ≥50 bars
  1647	            for symbol, timeframe, df in datasets:
  1648	                if (symbol, timeframe) in fresh_tested_datasets:
  1649	                    continue
  1650	                if len(df) < min_bars:
  1651	                    log.info("Skipping %s %s: %d bars too short for %d-fold walk-forward (need %d)",
  1652	                             symbol, timeframe, len(df), n_folds, int(min_bars))
  1653	                    continue
  1654	                exp, ev = self.run_experiment(h, df, symbol, timeframe)
  1655	                if ev:
  1656	                    cycle.experiment_ids.append(exp.id)
  1657	                    cycle.evidence_ids.append(ev.id)
  1658	                    self._save_obj("cycles", cycle.id, cycle.model_dump())
  1659	                    h_report["experiments"].append({
  1660	                        "id": exp.id,
  1661	                        "evidence_quality": ev.quality.value,
  1662	                        "evidence_direction": ev.direction.value,
  1663	                    })
  1664	
  1665	            # Decide
  1666	            decision = self.evaluate_and_decide(h, cycle)
  1667	            h_report["decision"] = decision
  1668	            cycle_report["hypotheses"].append(h_report)
  1669	
  1670	            log.info("Hypothesis %s: %s → %s", h.id, h.claim[:60], decision)
  1671	            self._emit_telemetry(
  1672	                "hypothesis.decided",
  1673	                level="info" if decision != "error" else "error",
  1674	                details={
  1675	                    "hypothesis_id": h.id,
  1676	                    "decision": decision,
  1677	                    "total_evidence_store_size": len(self.state.list_all("evidence")),
  1678	                },
  1679	            )
  1680	
  1681	        # Phase 6: Report graph state
  1682	        graph = self.graph_store.load()
  1683	        cycle_report["graph_nodes"] = graph.node_count
  1684	        cycle_report["graph_edges"] = graph.edge_count
  1685	
  1686	        log.info("=== Cycle complete: %d hypotheses tested, graph has %d nodes ===",
  1687	                 len(hypotheses), graph.node_count)
  1688	
  1689	        # Decision breakdown: how many hypotheses landed in each terminal state
  1690	        # this cycle. A cycle where every decision is "continue" produces no new
  1691	        # epistemic state — surfacing this explicitly is how meta-scan detects
  1692	        # the frozen-loop failure mode (Pattern 2 of the 2026-04-24 synthesis).
  1693	        decisions_by_kind: dict[str, int] = {}
  1694	        for hrep in cycle_report["hypotheses"]:
  1695	            kind = hrep.get("decision", "unknown")
  1696	            decisions_by_kind[kind] = decisions_by_kind.get(kind, 0) + 1
  1697	
  1698	        self._emit_telemetry(
  1699	            "cycle.completed",
  1700	            details={
  1701	                "hypotheses_evaluated": len(cycle_report["hypotheses"]),
  1702	                "total_evidence_store_size": len(self.state.list_all("evidence")),
  1703	                "signals_found": cycle_report.get("signals_found", 0),
  1704	                "graph_nodes": graph.node_count,
  1705	                "graph_edges": graph.edge_count,
  1706	                "decisions_by_kind": decisions_by_kind,
  1707	            },
  1708	        )
  1709	
  1710	        # S3-P2 frozen-loop escalation: if the last N completed cycles were
  1711	        # all-continue (no kills, promotions, or pivots), the loop is producing
  1712	        # no epistemic state and the silent-monitor failure mode applies.
  1713	        try:
  1714	            self._update_streak_counter(decisions_by_kind)
  1715	        except Exception as exc:
  1716	            log.warning("Streak counter update failed: %s", exc)
  1717	        try:
  1718	            self._maybe_escalate_frozen_loop()
  1719	        except Exception as exc:  # never let escalation crash a cycle
  1720	            log.warning("Frozen-loop escalation check failed: %s", exc)
  1721	
  1722	        return cycle_report
  1723	
  1724	    # --------------------------------------------------------------------
  1725	    # S3-P2 frozen-loop escalation
  1726	    # --------------------------------------------------------------------
  1727	
  1728	    TELEMETRY_PATH = Path("/opt/workspace/runtime/.telemetry/events.jsonl")
  1729	    SUPERVISOR_HANDOFF_DIR = Path("/opt/workspace/supervisor/handoffs/INBOX")
  1730	
  1731	    def _escalation_state_path(self) -> Path:
  1732	        """Authoritative dedup state for the frozen-loop gate. Lives under
  1733	        .atlas/ so it survives both runner restart and telemetry rotation.
  1734	
  1735	        The previous design read prior `cycle.escalated` events back from
  1736	        `events.jsonl`, which broke at midnight UTC when the workspace
  1737	        telemetry collector rotated yesterday's events to a `.gz` archive
  1738	        the gate did not read.
  1739	        """
  1740	        return self.base_dir / ".atlas" / "escalation_state.json"
  1741	
  1742	    def _load_escalation_state(self) -> dict:
  1743	        """Return the persistent streak state, validated.
  1744	
  1745	        Recognized fields:
  1746	          consecutive_empty_count  int    — live streak length; null/bad → fail-open
  1747	          streak_start_ts          int|None — when the current streak started
  1748	          emitted_for_current_streak bool — True once the gate has fired this streak
  1749	          last_emitted_ts          int    — epoch-ms of the last emission (display only)
  1750	
  1751	        A malformed file is treated as empty (fail-open = counter resets to 0,
  1752	        not-emitted) so the gate re-arms after 3 new cycles rather than going
  1753	        silently dark.
  1754	        """
  1755	        path = self._escalation_state_path()
  1756	        if not path.exists():
  1757	            return {}
  1758	        try:
  1759	            raw = json.loads(path.read_text())
  1760	        except Exception as exc:
  1761	            log.warning("Failed to read escalation state %s: %s", path, exc)
  1762	            return {}
  1763	        if not isinstance(raw, dict):
  1764	            log.warning("Escalation state %s is not a dict; ignoring", path)
  1765	            return {}
  1766	        out: dict = {}
  1767	        # consecutive_empty_count: int; null or non-int → fail-open
  1768	        if "consecutive_empty_count" in raw:
  1769	            val = raw["consecutive_empty_count"]
  1770	            try:
  1771	                out["consecutive_empty_count"] = int(val)
  1772	            except (TypeError, ValueError):
  1773	                log.warning(
  1774	                    "Escalation state %s has non-int consecutive_empty_count=%r; ignoring",
  1775	                    path, val,
  1776	                )
  1777	                return {}
  1778	        # streak_start_ts: int or None (null = counter is at 0 / not started)
  1779	        if "streak_start_ts" in raw:
  1780	            val = raw["streak_start_ts"]
  1781	            if val is None:
  1782	                out["streak_start_ts"] = None
  1783	            else:
  1784	                try:
  1785	                    out["streak_start_ts"] = int(val)
  1786	                except (TypeError, ValueError):
  1787	                    log.warning(
  1788	                        "Escalation state %s has non-int streak_start_ts=%r; ignoring",
  1789	                        path, val,
  1790	                    )
  1791	                    return {}
  1792	        # emitted_for_current_streak: bool; corrupt value → default False
  1793	        if "emitted_for_current_streak" in raw:
  1794	            val = raw["emitted_for_current_streak"]
  1795	            if isinstance(val, bool):
  1796	                out["emitted_for_current_streak"] = val
  1797	            elif val in (0, 1):
  1798	                out["emitted_for_current_streak"] = bool(val)
  1799	            else:
  1800	                out["emitted_for_current_streak"] = False
  1801	        return out
  1802	
  1803	    def _persist_escalation_state(self, state: dict) -> None:
  1804	        """Atomic write of the escalation state dict."""
  1805	        path = self._escalation_state_path()
  1806	        try:
  1807	            path.parent.mkdir(parents=True, exist_ok=True)
  1808	            tmp = path.with_suffix(path.suffix + ".tmp")
  1809	            tmp.write_text(json.dumps(state))
  1810	            tmp.replace(path)
  1811	        except Exception as exc:
  1812	            log.warning("Failed to write escalation state %s: %s", path, exc)
  1813	
  1814	    def _save_escalation_state(self, streak_start_ts: int, emitted_ts: int) -> None:
  1815	        """Mark the current streak as emitted. Preserves the existing counter."""
  1816	        state = self._load_escalation_state()
  1817	        state.update({
  1818	            "emitted_for_current_streak": True,
  1819	            "last_emitted_ts": emitted_ts,
  1820	            "streak_start_ts": streak_start_ts,
  1821	        })
  1822	        self._persist_escalation_state(state)
  1823	
  1824	    def _update_streak_counter(self, decisions_by_kind: dict) -> None:
  1825	        """Update the persistent consecutive-empty counter from one cycle's outcome.
  1826	
  1827	        Increments on empty cycles (decisions_by_kind == {}) and all-continue
  1828	        cycles (only "continue" keys). Resets to 0 on any decisive outcome
  1829	        (kill / promote / pivot). Called by run_cycle before
  1830	        _maybe_escalate_frozen_loop.
  1831	        """
  1832	        STUCK_KINDS = frozenset({"continue"})
  1833	        kind_set = set(decisions_by_kind.keys())
  1834	        has_decisive = bool(kind_set - STUCK_KINDS)
  1835	
  1836	        state = self._load_escalation_state()
  1837	
  1838	        if has_decisive:
  1839	            new_state: dict = {
  1840	                "consecutive_empty_count": 0,
  1841	                "streak_start_ts": None,
  1842	                "emitted_for_current_streak": False,
  1843	            }
  1844	            if "last_emitted_ts" in state:
  1845	                new_state["last_emitted_ts"] = state["last_emitted_ts"]
  1846	        else:
  1847	            count = state.get("consecutive_empty_count", 0) + 1
  1848	            streak_start_ts = (
  1849	                state.get("streak_start_ts")
  1850	                or int(datetime.now(timezone.utc).timestamp() * 1000)
  1851	            )
  1852	            new_state = {
  1853	                "consecutive_empty_count": count,
  1854	                "streak_start_ts": streak_start_ts,
  1855	                "emitted_for_current_streak": state.get("emitted_for_current_streak", False),
  1856	            }
  1857	            if "last_emitted_ts" in state:
  1858	                new_state["last_emitted_ts"] = state["last_emitted_ts"]
  1859	
  1860	        self._persist_escalation_state(new_state)
  1861	
  1862	    def _maybe_escalate_frozen_loop(self) -> None:
  1863	        """Emit a `cycle.escalated` event and write an URGENT handoff when
  1864	        the persistent consecutive-empty counter reaches FROZEN_LOOP_ESCALATION_AFTER
  1865	        and the current streak has not yet been reported.
  1866	
  1867	        The counter is maintained by `_update_streak_counter`, called from
  1868	        `run_cycle` before this method. Resets to 0 on any kill/promote/pivot.
  1869	        Idempotency is governed by `emitted_for_current_streak` in the state
  1870	        file — rotation-proof because it never reads events.jsonl.
  1871	        """
  1872	        state = self._load_escalation_state()
  1873	        count = state.get("consecutive_empty_count", 0)
  1874	
  1875	        if count < FROZEN_LOOP_ESCALATION_AFTER:
  1876	            return
  1877	
  1878	        if state.get("emitted_for_current_streak", False):
  1879	            return
  1880	
  1881	        streak_start_ts = state.get("streak_start_ts") or 0
  1882	        emitted_ts = int(datetime.now(timezone.utc).timestamp() * 1000)
  1883	        self._emit_telemetry(
  1884	            "cycle.escalated",
  1885	            level="warning",
  1886	            details={
  1887	                "reason": "frozen_loop_all_continue",
  1888	                "consecutive_cycles": count,
  1889	                "streak_start_ts": streak_start_ts,
  1890	                "total_evidence_store_size": len(self.state.list_all("evidence")),
  1891	            },
  1892	        )
  1893	        self._save_escalation_state(streak_start_ts, emitted_ts)
  1894	        self._write_frozen_loop_handoff(count, streak_start_ts)
  1895	
  1896	    def _write_frozen_loop_handoff(self, consecutive_cycles: int, streak_start_ts: int) -> None:
  1897	        """Drop one URGENT handoff to general/atlas describing the streak.
  1898	        Dedup by glob — if any URGENT-atlas-frozen-loop-*.md exists, skip."""
  1899	        try:
  1900	            self.SUPERVISOR_HANDOFF_DIR.mkdir(parents=True, exist_ok=True)
  1901	            existing = list(self.SUPERVISOR_HANDOFF_DIR.glob("URGENT-atlas-frozen-loop-*.md"))
  1902	            if existing:
  1903	                return
  1904	            now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%MZ")
  1905	            path = self.SUPERVISOR_HANDOFF_DIR / f"URGENT-atlas-frozen-loop-{now_iso}.md"
  1906	            evidence_size = len(self.state.list_all("evidence"))
  1907	            body = (
  1908	                "---\n"
  1909	                f"priority: critical\n"
  1910	                f"created: {datetime.now(timezone.utc).isoformat()}\n"
  1911	                "from: atlas.runner (self-emitted via S3-P2 escalation gate)\n"
  1912	                "to: atlas / general\n"
  1913	                "---\n\n"
  1914	                "# atlas — frozen loop (auto-escalated)\n\n"
  1915	                f"The autonomous loop has produced {consecutive_cycles} consecutive\n"
  1916	                "all-continue cycles with no kill/promote/pivot decisions.\n"
  1917	                f"Evidence store size: {evidence_size}.\n\n"
  1918	                "## Likely causes\n\n"
  1919	                "- Dataset retest cache is too aggressive (DATASET_RETEST_AFTER) —\n"
  1920	                "  hypothesis is being re-evaluated against the same evidence.\n"
  1921	                "- All available data has been exhausted under the current signal\n"
  1922	                "  detectors; new detectors or new data sources needed.\n"
  1923	                "- A bug is silently dropping experiment runs.\n\n"
  1924	                "## Diagnostic\n\n"
  1925	                "  grep '\"eventType\": \"cycle.completed\"' \\\n"
  1926	                "    /opt/workspace/runtime/.telemetry/events.jsonl | tail -10\n"
  1927	                "  .venv/bin/atlas strategy readiness\n\n"
  1928	                "Delete this file once the root cause is addressed; the gate is\n"
  1929	                "idempotent and will re-fire only on a new streak.\n"
  1930	            )
  1931	            path.write_text(body)
  1932	            log.warning("Wrote frozen-loop URGENT handoff to %s", path)
  1933	        except Exception as exc:
  1934	            log.warning("Failed to write frozen-loop handoff: %s", exc)
  1935	
  1936	    def run_continuous(self, interval_seconds: int = 3600) -> None:
  1937	        """Run the research loop continuously."""
  1938	        log.info("Starting continuous research loop (interval=%ds)", interval_seconds)
  1939	        while True:
  1940	            try:
  1941	                report = self.run_cycle()
  1942	                reports_dir = self.base_dir / "reports"
  1943	                reports_dir.mkdir(exist_ok=True)
  1944	                ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  1945	                with open(reports_dir / f"cycle_{ts}.json", "w") as f:
  1946	                    json.dump(report, f, indent=2, default=str)
  1947	            except Exception as e:
  1948	                log.error("Cycle failed: %s", e, exc_info=True)
  1949	                self._log_methodology({
  1950	                    "phase": "cycle_failure",
  1951	                    "error": str(e),
  1952	                })
  1953	                self._emit_telemetry("cycle.failed", level="error", details={"error": str(e)})
  1954	
  1955	            log.info("Sleeping %ds until next cycle", interval_seconds)
  1956	            time.sleep(interval_seconds)

codex
1. **Most dangerous assumption** — “Distinct experiment” is treated as independent support. The gate only counts unique `experiment_id`s (`runner.py:143`, `runner.py:1180`), while the runner manufactures those by replaying the same tag-derived strategy across default symbols (`runner.py:1593`-`runner.py:1604`). If that cross-asset reuse is not epistemically independent, promotion can turn correlated backtest artifacts into graph primitives.

2. **Missing failure mode** — Strong-but-insufficient contradiction creates limbo. Two strong contradictions kill (`runner.py:1157`-`runner.py:1171`), but one strong contradiction blocks promotion forever (`runner.py:1173`-`runner.py:1177`) and otherwise falls through to `continue` (`runner.py:1240`). There is no explicit “conflicted” state, remediation path, or escalation keyed to this condition.

3. **Boundary most likely to be collapsed in practice** — Claim-faithful testing vs runnable proxy. Dataset choice starts claim-derived (`runner.py:1548`-`runner.py:1555`), then expands to generic universe cross-validation (`runner.py:1593`-`runner.py:1604`), and finally falls back to BTC/USDT when no dataset exists (`runner.py:1627`-`runner.py:1629`). The signal builder also proxies pairs/lead-lag claims (`runner.py:967`-`runner.py:982`) and defaults unknown tags to momentum (`runner.py:1022`-`runner.py:1023`).

Overall verdict: the runner is operationally robust but epistemically loose. Its biggest risk is converting “something executable” into “evidence for the claim.”
tokens used
50,164
1. **Most dangerous assumption** — “Distinct experiment” is treated as independent support. The gate only counts unique `experiment_id`s (`runner.py:143`, `runner.py:1180`), while the runner manufactures those by replaying the same tag-derived strategy across default symbols (`runner.py:1593`-`runner.py:1604`). If that cross-asset reuse is not epistemically independent, promotion can turn correlated backtest artifacts into graph primitives.

2. **Missing failure mode** — Strong-but-insufficient contradiction creates limbo. Two strong contradictions kill (`runner.py:1157`-`runner.py:1171`), but one strong contradiction blocks promotion forever (`runner.py:1173`-`runner.py:1177`) and otherwise falls through to `continue` (`runner.py:1240`). There is no explicit “conflicted” state, remediation path, or escalation keyed to this condition.

3. **Boundary most likely to be collapsed in practice** — Claim-faithful testing vs runnable proxy. Dataset choice starts claim-derived (`runner.py:1548`-`runner.py:1555`), then expands to generic universe cross-validation (`runner.py:1593`-`runner.py:1604`), and finally falls back to BTC/USDT when no dataset exists (`runner.py:1627`-`runner.py:1629`). The signal builder also proxies pairs/lead-lag claims (`runner.py:967`-`runner.py:982`) and defaults unknown tags to momentum (`runner.py:1022`-`runner.py:1023`).

Overall verdict: the runner is operationally robust but epistemically loose. Its biggest risk is converting “something executable” into “evidence for the claim.”
