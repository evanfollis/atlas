Reading additional input from stdin...
OpenAI Codex v0.120.0 (research preview)
--------
workdir: /opt/workspace/projects/atlas
model: gpt-5.4
provider: openai
approval: never
sandbox: read-only
reasoning effort: high
reasoning summaries: none
session id: 019dabcf-3b33-7932-aaf0-7fb8cd27d04b
--------
user
Adversarial review of /opt/workspace/projects/atlas/src/atlas/adapters/discovery.

You are a skeptical reviewer. Read the target file carefully. Then produce a review with exactly these three sections:

1. **Most dangerous assumption** — the claim that if wrong, produces the largest blast radius.
2. **Missing failure mode** — what the design does not account for that is likely to happen in practice.
3. **Boundary most likely to be collapsed in practice** — where the nominal separation will erode under real use.

Cite specific line numbers. Be terse and concrete. End with a 1-2 sentence overall verdict. Under 500 words total. Do not edit any files.
codex
I’m checking what `/opt/workspace/projects/atlas/src/atlas/adapters/discovery` resolves to and then I’ll read the relevant file(s) closely enough to ground the review in line-specific findings.
exec
/bin/bash -lc pwd in /opt/workspace/projects/atlas
 succeeded in 0ms:
/opt/workspace/projects/atlas

exec
/bin/bash -lc 'rg --files /opt/workspace/projects/atlas/src/atlas/adapters/discovery' in /opt/workspace/projects/atlas
 succeeded in 0ms:
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/emit.py
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/MAPPING.md

exec
/bin/bash -lc 'ls -ld /opt/workspace/projects/atlas/src/atlas/adapters/discovery' in /opt/workspace/projects/atlas
 succeeded in 0ms:
drwxr-xr-x 3 root root 4096 Apr 19 04:16 /opt/workspace/projects/atlas/src/atlas/adapters/discovery

codex
`discovery` is a package, not a single file. I’m reading the module entrypoint and the two implementation files so the review reflects the actual design surface rather than just the package stub.
exec
/bin/bash -lc 'wc -l /opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py /opt/workspace/projects/atlas/src/atlas/adapters/discovery/emit.py /opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py' in /opt/workspace/projects/atlas
 succeeded in 0ms:
   51 /opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py
  475 /opt/workspace/projects/atlas/src/atlas/adapters/discovery/emit.py
  253 /opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py
  779 total

exec
/bin/bash -lc 'nl -ba /opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py' in /opt/workspace/projects/atlas
 succeeded in 0ms:
     1	"""Canon adapter — emits discovery-framework canon envelopes from atlas state.
     2	
     3	The atlas research loop (src/atlas/) persists its own Pydantic state in .atlas/
     4	JSON files. This adapter maps each atlas record to a canon envelope conforming
     5	to the L1 spec at /opt/workspace/projects/context-repository/spec/discovery-
     6	framework/ (v0.1.0), producing a parallel .canon/ store that atlas's behavior
     7	does not otherwise depend on.
     8	
     9	The adapter is additive — it does NOT modify atlas's existing write path.
    10	The migrate.py entry point backfills historical records; the emit.py
    11	functions can be called in dual-write mode once atlas's runner is wired to
    12	call them alongside StateStore.save().
    13	
    14	Public API:
    15	    emit_claim(h, atlas_path)           -> canon Claim dict
    16	    emit_evidence(e, atlas_path)        -> canon Evidence dict
    17	    emit_decision(cycle, ..., atlas_path) -> canon Decision dict
    18	    emit_event_log(event, atlas_path)   -> canon EventLogEntry dict
    19	    emit_policy_tier_mapping()          -> canon Policy dict for the quality→tier map
    20	    canon_dir(atlas_path)               -> Path to the .canon/ store
    21	"""
    22	
    23	from .emit import (
    24	    emit_claim,
    25	    emit_evidence,
    26	    emit_decision,
    27	    emit_event_log,
    28	    emit_policy_tier_mapping,
    29	    canon_dir,
    30	    SPEC_VERSION,
    31	    EMITTER,
    32	    LAYER,
    33	    INSTANCE_ID,
    34	    TIER_POLICY_ID,
    35	    TIER_POLICY_VERSION,
    36	)
    37	
    38	__all__ = [
    39	    "emit_claim",
    40	    "emit_evidence",
    41	    "emit_decision",
    42	    "emit_event_log",
    43	    "emit_policy_tier_mapping",
    44	    "canon_dir",
    45	    "SPEC_VERSION",
    46	    "EMITTER",
    47	    "LAYER",
    48	    "INSTANCE_ID",
    49	    "TIER_POLICY_ID",
    50	    "TIER_POLICY_VERSION",
    51	]

exec
/bin/bash -lc 'nl -ba /opt/workspace/projects/atlas/src/atlas/adapters/discovery/emit.py' in /opt/workspace/projects/atlas
 succeeded in 0ms:
     1	"""Emit canon envelopes from atlas Pydantic records.
     2	
     3	Each emit_* function returns a dict conforming to its respective JSON Schema
     4	in /opt/workspace/projects/context-repository/spec/discovery-framework/schemas/.
     5	No I/O here — the caller is responsible for writing the dict to .canon/ and
     6	running the validator.
     7	
     8	Conventions:
     9	- `emitter`  = "L3:atlas"  — atlas operates at the domain-layer (L3).
    10	- `layer`    = "L3".
    11	- `binding`  = "binding" for domain research claims (NOT meta-layer outputs).
    12	- `sources`  = []          — atlas does not currently cite upstream canon.
    13	                              Left empty (valid per schema) so the
    14	                              influence-firewall check is trivially satisfied.
    15	
    16	The `tier` mapping from atlas's 3-tier EvidenceQuality to canon's 4-tier
    17	enum is documented in MAPPING.md in this directory AND expressed as a canon
    18	Policy via emit_policy_tier_mapping(). Future sessions reading canon
    19	envelopes see the mapping in Policy.provenance.
    20	"""
    21	
    22	from __future__ import annotations
    23	
    24	import hashlib
    25	import json
    26	from datetime import datetime, timezone
    27	from pathlib import Path
    28	from typing import Any, Iterable
    29	
    30	from atlas.models.evidence import Evidence, EvidenceDirection, EvidenceQuality
    31	from atlas.models.hypothesis import Hypothesis, HypothesisStatus
    32	
    33	
    34	SPEC_VERSION = "0.1.0"
    35	EMITTER = "L3:atlas"
    36	LAYER = "L3"
    37	INSTANCE_ID = "atlas"
    38	
    39	TIER_POLICY_ID = "atlas.evidence_quality_to_canon_tier"
    40	TIER_POLICY_VERSION = "1"
    41	
    42	
    43	# --------------------------------------------------------------------------
    44	# Helpers
    45	# --------------------------------------------------------------------------
    46	
    47	
    48	def canon_dir(atlas_path: Path) -> Path:
    49	    """Return the .canon/ directory under an atlas root, creating if missing."""
    50	    d = Path(atlas_path) / ".canon"
    51	    d.mkdir(parents=True, exist_ok=True)
    52	    for sub in ("claims", "evidence", "decisions", "event_log", "policies"):
    53	        (d / sub).mkdir(parents=True, exist_ok=True)
    54	    return d
    55	
    56	
    57	def _iso(dt: datetime | str) -> str:
    58	    """Convert datetime or isoformat-ish string to canon Timestamp (RFC 3339)."""
    59	    if isinstance(dt, str):
    60	        dt = datetime.fromisoformat(dt)
    61	    if dt.tzinfo is None:
    62	        dt = dt.replace(tzinfo=timezone.utc)
    63	    return dt.isoformat().replace("+00:00", "Z")
    64	
    65	
    66	def _sha256_file(path: Path) -> str:
    67	    h = hashlib.sha256()
    68	    with open(path, "rb") as f:
    69	        for chunk in iter(lambda: f.read(65536), b""):
    70	            h.update(chunk)
    71	    return f"sha256:{h.hexdigest()}"
    72	
    73	
    74	def _sha256_bytes(data: bytes) -> str:
    75	    return f"sha256:{hashlib.sha256(data).hexdigest()}"
    76	
    77	
    78	def _default_exposure() -> dict[str, Any]:
    79	    """Minimal exposure envelope for atlas research records.
    80	
    81	    Atlas research commits no capital and its outputs are internal to the
    82	    research loop until a promoted Primitive is fed downstream. Every field
    83	    is required by the canon Exposure schema.
    84	    """
    85	    return {
    86	        "capital_at_risk": 0,
    87	        "reversibility": "reversible",
    88	        "correlation_tags": [],
    89	        "time_to_realization": "P0D",
    90	        "blast_radius": "local",
    91	    }
    92	
    93	
    94	def _quality_to_tier(quality: EvidenceQuality, evidence_class: str) -> str:
    95	    """Lossy mapping from atlas.Evidence.quality to canon.Evidence.tier.
    96	
    97	    Atlas's quality measures statistical rigor (weak/moderate/strong). Canon's
    98	    tier measures bindingness to external reality
    99	    (internal_operational / external_conversation / external_commitment /
   100	    external_transaction). These axes are not identical; the mapping is
   101	    documented in MAPPING.md and codified as a Policy (see
   102	    emit_policy_tier_mapping).
   103	
   104	    Rule: STRONG evidence that came from live_observation is
   105	    external_transaction (actual market behavior). STRONG from OOS backtest is
   106	    external_commitment (committed to a real dataset, not in-sample cherry-
   107	    picking). MODERATE is external_conversation (moderate support, one test).
   108	    WEAK is internal_operational (in-sample only, pre-commitment).
   109	    """
   110	    if quality == EvidenceQuality.WEAK:
   111	        return "internal_operational"
   112	    if quality == EvidenceQuality.MODERATE:
   113	        return "external_conversation"
   114	    # STRONG
   115	    if evidence_class == "live_observation":
   116	        return "external_transaction"
   117	    return "external_commitment"
   118	
   119	
   120	def _direction_to_polarity(direction: EvidenceDirection) -> str:
   121	    return {
   122	        EvidenceDirection.SUPPORTS: "supports",
   123	        EvidenceDirection.CONTRADICTS: "contradicts",
   124	        EvidenceDirection.INCONCLUSIVE: "neutral",
   125	    }[direction]
   126	
   127	
   128	def _artifact_pointer(
   129	    uri: str, content_hash: str, version: str, anchor: str | None = None,
   130	    media_type: str | None = None,
   131	) -> dict[str, Any]:
   132	    ap: dict[str, Any] = {
   133	        "uri": uri,
   134	        "content_hash": content_hash,
   135	        "version": version,
   136	    }
   137	    if anchor:
   138	        ap["anchor"] = anchor
   139	    if media_type:
   140	        ap["media_type"] = media_type
   141	    return ap
   142	
   143	
   144	def _common_envelope(object_type: str, id_: str, emitted_at: str,
   145	                     role_declared_at: str | None = None,
   146	                     binding: str = "binding") -> dict[str, Any]:
   147	    """Shared envelope fields for all canon object types."""
   148	    return {
   149	        "id": id_,
   150	        "spec_version": SPEC_VERSION,
   151	        "object_type": object_type,
   152	        "emitted_at": emitted_at,
   153	        "emitter": EMITTER,
   154	        "layer": LAYER,
   155	        "roles": [object_type],
   156	        "role_declared_at": role_declared_at or emitted_at,
   157	        "binding": binding,
   158	        "sources": [],
   159	        "instance_id": INSTANCE_ID,
   160	    }
   161	
   162	
   163	# --------------------------------------------------------------------------
   164	# Claim
   165	# --------------------------------------------------------------------------
   166	
   167	
   168	def emit_claim(h: Hypothesis, atlas_path: Path | str) -> dict[str, Any]:
   169	    """Atlas Hypothesis → canon Claim envelope.
   170	
   171	    Mapping:
   172	      - Claim.id                     = Hypothesis.id (already sha256[:16] of canonical claim)
   173	      - Claim.statement              = Hypothesis.claim (immutable per canon)
   174	      - Claim.falsification_criteria = [Hypothesis.falsification_criteria]   (wrap str in list)
   175	      - Claim.thresholds             = {"alpha": Hypothesis.significance_threshold, ...}
   176	      - Claim.emitted_at             = Hypothesis.created_at (ISO 8601)
   177	      - Claim.artifact               = ArtifactPointer to the atlas hypothesis JSON file
   178	
   179	    The Hypothesis.status is NOT written into the Claim envelope (Claims are
   180	    immutable; status transitions are recorded as EventLogEntry(phase_transition)
   181	    events — see emit_event_log).
   182	    """
   183	    atlas_path = Path(atlas_path)
   184	    created = _iso(h.created_at)
   185	    envelope = _common_envelope("Claim", h.id, created, binding="binding")
   186	    envelope["statement"] = h.claim
   187	    envelope["falsification_criteria"] = [h.falsification_criteria]
   188	    envelope["thresholds"] = {
   189	        "alpha": h.significance_threshold,
   190	    }
   191	    envelope["exposure"] = _default_exposure()
   192	
   193	    # Point at the on-disk atlas hypothesis JSON if it exists, with content hash.
   194	    hyp_json = atlas_path / ".atlas" / "hypotheses" / f"{h.id}.json"
   195	    if hyp_json.exists():
   196	        envelope["artifact"] = _artifact_pointer(
   197	            uri=f"file://{hyp_json}",
   198	            content_hash=_sha256_file(hyp_json),
   199	            version=str(int(hyp_json.stat().st_mtime)),
   200	            media_type="application/json",
   201	        )
   202	    return envelope
   203	
   204	
   205	# --------------------------------------------------------------------------
   206	# Evidence
   207	# --------------------------------------------------------------------------
   208	
   209	
   210	def emit_evidence(e: Evidence, atlas_path: Path | str) -> dict[str, Any]:
   211	    """Atlas Evidence → canon Evidence envelope.
   212	
   213	    Mapping:
   214	      - Evidence.id              = Evidence.id                        (atlas deterministic)
   215	      - Evidence.claim_id        = Evidence.hypothesis_id
   216	      - Evidence.evidence_type   = Evidence.evidence_class.value      (domain-owned free-form string)
   217	      - Evidence.tier            = _quality_to_tier(...)              (Policy-documented lossy map)
   218	      - Evidence.polarity        = _direction_to_polarity(direction)  (inconclusive → neutral)
   219	      - Evidence.artifact        = ArtifactPointer to the atlas evidence JSON
   220	      - Evidence.observed_at     = Evidence.created_at
   221	    """
   222	    atlas_path = Path(atlas_path)
   223	    created = _iso(e.created_at)
   224	    envelope = _common_envelope(
   225	        "Evidence", e.id, created, binding="binding",
   226	    )
   227	    # Evidence schema REQUIRES binding + sources + claim_id + evidence_type +
   228	    # tier + polarity + artifact (beyond EnvelopeBase).
   229	    envelope["claim_id"] = e.hypothesis_id
   230	    envelope["evidence_type"] = e.evidence_class.value
   231	    envelope["tier"] = _quality_to_tier(e.quality, e.evidence_class.value)
   232	    envelope["polarity"] = _direction_to_polarity(e.direction)
   233	    envelope["observed_at"] = created
   234	
   235	    ev_json = atlas_path / ".atlas" / "evidence" / f"{e.id}.json"
   236	    if ev_json.exists():
   237	        envelope["artifact"] = _artifact_pointer(
   238	            uri=f"file://{ev_json}",
   239	            content_hash=_sha256_file(ev_json),
   240	            version=str(int(ev_json.stat().st_mtime)),
   241	            media_type="application/json",
   242	        )
   243	    else:
   244	        # Fallback: synthesize an artifact pointer from the evidence summary
   245	        # hash. The Evidence schema REQUIRES artifact, so this path keeps the
   246	        # envelope valid even when the source JSON is missing (rare).
   247	        payload = json.dumps(
   248	            {"summary": e.summary, "statistics": e.statistics,
   249	             "data_range": e.data_range},
   250	            sort_keys=True,
   251	        ).encode("utf-8")
   252	        envelope["artifact"] = _artifact_pointer(
   253	            uri=f"atlas-evidence:{e.id}",
   254	            content_hash=_sha256_bytes(payload),
   255	            version=created,
   256	        )
   257	    return envelope
   258	
   259	
   260	# --------------------------------------------------------------------------
   261	# Decision
   262	# --------------------------------------------------------------------------
   263	
   264	
   265	def emit_decision(
   266	    *,
   267	    decision_id: str,
   268	    kind: str,
   269	    hypothesis: Hypothesis,
   270	    evidence: Iterable[Evidence],
   271	    rationale: str,
   272	    emitted_at: str | datetime | None = None,
   273	    atlas_path: Path | str,
   274	    promotion_id: str | None = None,
   275	) -> dict[str, Any]:
   276	    """Emit a canon Decision for an atlas cycle outcome.
   277	
   278	    Atlas currently produces promote|kill|continue|pivot decisions at the
   279	    runner level. This function expects a caller (migrate.py or atlas's
   280	    runner in dual-write mode) to pass in the decision kind, the target
   281	    hypothesis, and the relevant evidence set.
   282	
   283	    Contention-integrity rules:
   284	    - candidate_claims == [hypothesis.id] (atlas evaluates one claim at a time;
   285	      no cross-hypothesis arbitration today)
   286	    - rejected_alternatives omitted (candidate_claims has 1 entry)
   287	    - arbitration omitted for the same reason
   288	
   289	    If kind=promote, a promotion_id MUST be provided.
   290	    """
   291	    if kind == "promote" and not promotion_id:
   292	        raise ValueError("promotion_id required when kind='promote'")
   293	    if kind not in {"promote", "kill", "continue", "pivot"}:
   294	        raise ValueError(f"atlas does not emit Decision.kind={kind!r}")
   295	
   296	    dt = emitted_at or datetime.now(timezone.utc)
   297	    emitted = _iso(dt) if not isinstance(dt, str) else dt
   298	
   299	    envelope = _common_envelope("Decision", decision_id, emitted, binding="binding")
   300	    envelope["kind"] = kind
   301	    envelope["candidate_claims"] = [hypothesis.id]
   302	    envelope["chosen_claim_id"] = hypothesis.id
   303	    envelope["cited_evidence"] = [e.id for e in evidence]
   304	
   305	    # contradictory evidence MUST be cited at decision time
   306	    contradictions = [e for e in evidence if e.direction == EvidenceDirection.CONTRADICTS]
   307	    if contradictions:
   308	        envelope["contradictions_addressed"] = [
   309	            {
   310	                "evidence_id": c.id,
   311	                "treatment": (
   312	                    "hard_gated" if kind == "kill" else "accepted_as_partial_constraint"
   313	                ),
   314	                "rationale": c.summary,
   315	            }
   316	            for c in contradictions
   317	        ]
   318	
   319	    envelope["rationale"] = rationale
   320	    envelope["policies_in_force"] = [
   321	        {
   322	            "policy_id": TIER_POLICY_ID,
   323	            "version": TIER_POLICY_VERSION,
   324	            "class": "operational",
   325	        }
   326	    ]
   327	    envelope["exposure"] = _default_exposure()
   328	
   329	    if promotion_id:
   330	        envelope["promotion_id"] = promotion_id
   331	    return envelope
   332	
   333	
   334	# --------------------------------------------------------------------------
   335	# EventLogEntry (phase transitions + methodology logs)
   336	# --------------------------------------------------------------------------
   337	
   338	
   339	PHASE_FOR_STATUS = {
   340	    HypothesisStatus.FORMULATED: "draft",
   341	    HypothesisStatus.TESTING: "probe",
   342	    HypothesisStatus.SUPPORTED: "promotion",
   343	    HypothesisStatus.FALSIFIED: "promotion",
   344	    HypothesisStatus.PROMOTED: "promotion",
   345	}
   346	
   347	
   348	def emit_event_log(
   349	    *,
   350	    event_id: str,
   351	    event_kind: str,
   352	    emitted_at: str | datetime,
   353	    claim_id: str | None = None,
   354	    from_phase: str | None = None,
   355	    to_phase: str | None = None,
   356	    triggering_decision_id: str | None = None,
   357	    methodology_artifact: dict[str, Any] | None = None,
   358	    methodology_summary: str | None = None,
   359	) -> dict[str, Any]:
   360	    """Emit a canon EventLogEntry.
   361	
   362	    Only two event_kinds are produced by the atlas adapter today:
   363	
   364	      - phase_transition: claim_id FORMULATED→TESTING, TESTING→PROMOTION, etc.
   365	      - methodology_log: a pointer to an atlas methodology record
   366	                        (artifact is a canon ArtifactPointer)
   367	
   368	    Other event_kinds (canon_violation, activation_change, cross_layer_read,
   369	    advisory_rejection, trigger_fired) are reserved for future work; this
   370	    adapter does not emit them.
   371	    """
   372	    if event_kind not in {"phase_transition", "methodology_log"}:
   373	        raise ValueError(
   374	            f"atlas adapter does not emit EventLogEntry.event_kind={event_kind!r}"
   375	        )
   376	
   377	    emitted = _iso(emitted_at) if not isinstance(emitted_at, str) else emitted_at
   378	    envelope = _common_envelope(
   379	        "EventLogEntry", event_id, emitted, binding="binding",
   380	    )
   381	    envelope["event_kind"] = event_kind
   382	
   383	    if event_kind == "phase_transition":
   384	        if not (claim_id and from_phase and to_phase):
   385	            raise ValueError("phase_transition requires claim_id, from_phase, to_phase")
   386	        pt: dict[str, Any] = {
   387	            "claim_id": claim_id,
   388	            "from_phase": from_phase,
   389	            "to_phase": to_phase,
   390	        }
   391	        if triggering_decision_id:
   392	            pt["triggering_decision_id"] = triggering_decision_id
   393	        envelope["phase_transition"] = pt
   394	        envelope["subject_id"] = claim_id
   395	    elif event_kind == "methodology_log":
   396	        if not methodology_artifact:
   397	            raise ValueError("methodology_log requires methodology_artifact")
   398	        ml: dict[str, Any] = {"artifact": methodology_artifact}
   399	        if methodology_summary:
   400	            ml["summary"] = methodology_summary
   401	        envelope["methodology_log"] = ml
   402	    return envelope
   403	
   404	
   405	# --------------------------------------------------------------------------
   406	# Policy — the tier mapping
   407	# --------------------------------------------------------------------------
   408	
   409	
   410	def emit_policy_tier_mapping(effective_from: str | datetime | None = None) -> dict[str, Any]:
   411	    """One-shot canon Policy declaring the quality→tier mapping for atlas.
   412	
   413	    Written once at migration time. Referenced by every Decision's
   414	    policies_in_force. Future updates go through the Policy amendment path
   415	    (Decision.kind=amend_policy).
   416	    """
   417	    ts = effective_from or datetime.now(timezone.utc)
   418	    emitted = _iso(ts) if not isinstance(ts, str) else ts
   419	
   420	    envelope = _common_envelope(
   421	        "Policy", TIER_POLICY_ID, emitted, binding="binding",
   422	    )
   423	    # Policy schema has additionalProperties:false and does not list
   424	    # instance_id; remove it so the envelope validates.
   425	    envelope.pop("instance_id", None)
   426	    envelope["class"] = "operational"
   427	    envelope["scope"] = f"L3:{INSTANCE_ID}"
   428	    envelope["field_path"] = "evidence.tier_mapping"
   429	    envelope["value"] = {
   430	        "source_enum": "atlas.EvidenceQuality",
   431	        "target_enum": "canon.tier",
   432	        "rules": [
   433	            {"when": {"quality": "weak"},
   434	             "then_tier": "internal_operational",
   435	             "rationale": "in-sample only, pre-external-commitment"},
   436	            {"when": {"quality": "moderate"},
   437	             "then_tier": "external_conversation",
   438	             "rationale": "significant but single test"},
   439	            {"when": {"quality": "strong", "evidence_class_not": "live_observation"},
   440	             "then_tier": "external_commitment",
   441	             "rationale": "OOS / multi-test significance — committed to dataset"},
   442	            {"when": {"quality": "strong", "evidence_class": "live_observation"},
   443	             "then_tier": "external_transaction",
   444	             "rationale": "actual market behavior observed"},
   445	        ],
   446	    }
   447	    envelope["version"] = TIER_POLICY_VERSION
   448	    envelope["issuer"] = EMITTER
   449	    envelope["amendment_authority"] = [EMITTER, "human:evan"]
   450	    envelope["ratification_rule"] = {
   451	        "kind": "principal_signoff",
   452	        "signatories": ["human:evan"],
   453	    }
   454	    envelope["rollback_rule"] = {
   455	        "rules": [
   456	            {
   457	                "id": "spec_version_bump",
   458	                "condition": (
   459	                    "canon.spec_version has advanced beyond this Policy's "
   460	                    "spec_version and the target_enum has changed"
   461	                ),
   462	                "restore_version": "previous",
   463	            },
   464	        ],
   465	        "precedence": ["spec_version_bump"],
   466	    }
   467	    envelope["provenance"] = [
   468	        {
   469	            "version": TIER_POLICY_VERSION,
   470	            "effective_from": emitted,
   471	        }
   472	    ]
   473	    envelope["effective_from"] = emitted
   474	    envelope["effective_until"] = None
   475	    return envelope

exec
/bin/bash -lc 'nl -ba /opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py' in /opt/workspace/projects/atlas
 succeeded in 0ms:
     1	"""One-shot backfill: atlas .atlas/* → canon .canon/*.
     2	
     3	Usage:
     4	    python -m atlas.adapters.discovery.migrate --atlas /opt/workspace/projects/atlas [--dry-run]
     5	
     6	Reads all atlas hypotheses + evidence, emits canon envelopes via emit.py,
     7	validates each against the JSON Schemas at
     8	/opt/workspace/projects/context-repository/spec/discovery-framework/schemas/,
     9	and writes to .canon/ (unless --dry-run, which validates but does not write).
    10	
    11	Phase-transition EventLogEntry records are synthesized from each
    12	Hypothesis's current status.
    13	
    14	The one-time tier Policy is written first (at .canon/policies/<id>.json)
    15	since every Decision envelope cites it.
    16	
    17	Exit codes:
    18	    0 — all envelopes emitted and validated
    19	    1 — some envelopes failed validation (details on stderr)
    20	    2 — adapter or schema loading failure
    21	"""
    22	
    23	from __future__ import annotations
    24	
    25	import argparse
    26	import json
    27	import sys
    28	import traceback
    29	from pathlib import Path
    30	
    31	from atlas.adapters.discovery.emit import (
    32	    EMITTER,
    33	    INSTANCE_ID,
    34	    PHASE_FOR_STATUS,
    35	    TIER_POLICY_ID,
    36	    _iso,
    37	    _sha256_bytes,
    38	    canon_dir,
    39	    emit_claim,
    40	    emit_event_log,
    41	    emit_evidence,
    42	    emit_policy_tier_mapping,
    43	)
    44	from atlas.models.evidence import Evidence
    45	from atlas.models.hypothesis import Hypothesis, HypothesisStatus
    46	
    47	
    48	DEFAULT_SCHEMA_DIR = Path(
    49	    "/opt/workspace/projects/context-repository/spec/discovery-framework/schemas"
    50	)
    51	
    52	
    53	def _load_schema_registry(schema_dir: Path):
    54	    """Load every *.schema.json and build a jsonschema Registry for $ref resolution."""
    55	    try:
    56	        from jsonschema import Draft202012Validator
    57	        from referencing import Registry, Resource
    58	    except Exception as exc:  # pragma: no cover
    59	        print(
    60	            f"FATAL: jsonschema + referencing required but missing: {exc}",
    61	            file=sys.stderr,
    62	        )
    63	        print(
    64	            "install via: .venv/bin/pip install 'jsonschema>=4.20' 'referencing>=0.30'",
    65	            file=sys.stderr,
    66	        )
    67	        raise
    68	
    69	    resources: list[tuple[str, Resource]] = []
    70	    schemas: dict[str, dict] = {}
    71	    for p in sorted(schema_dir.glob("*.schema.json")):
    72	        with open(p) as f:
    73	            body = json.load(f)
    74	        sid = body["$id"]
    75	        schemas[p.name] = body
    76	        resources.append((sid, Resource.from_contents(body)))
    77	
    78	    # Register schemas under both their full $id AND the bare filename they
    79	    # are $ref'd by (e.g. "common.schema.json"). Without the bare alias the
    80	    # relative $refs in claim.schema.json, etc., cannot be resolved by the
    81	    # referencing registry when a draft-2020-12 validator walks the tree.
    82	    extra: list[tuple[str, Resource]] = []
    83	    for fname, body in schemas.items():
    84	        extra.append((fname, Resource.from_contents(body)))
    85	
    86	    registry = Registry().with_resources(resources + extra)
    87	    validators = {
    88	        body["title"]: Draft202012Validator(body, registry=registry)
    89	        for _, body in schemas.items()
    90	        if "title" in body
    91	    }
    92	    return validators
    93	
    94	
    95	def _load_json(path: Path) -> dict:
    96	    with open(path) as f:
    97	        return json.load(f)
    98	
    99	
   100	def _validate(envelope: dict, validators: dict, object_type: str) -> list[str]:
   101	    v = validators.get(object_type)
   102	    if not v:
   103	        return [f"no validator for object_type={object_type!r}"]
   104	    errors = sorted(v.iter_errors(envelope), key=lambda e: e.path)
   105	    return [
   106	        f"{'/'.join(str(p) for p in err.absolute_path)}: {err.message}"
   107	        for err in errors
   108	    ]
   109	
   110	
   111	def _write_envelope(envelope: dict, dest: Path, dry_run: bool) -> None:
   112	    if dry_run:
   113	        return
   114	    dest.parent.mkdir(parents=True, exist_ok=True)
   115	    # Atomic write
   116	    tmp = dest.with_suffix(dest.suffix + ".tmp")
   117	    with open(tmp, "w") as f:
   118	        json.dump(envelope, f, indent=2, sort_keys=True)
   119	    tmp.replace(dest)
   120	
   121	
   122	def migrate(atlas_root: Path, schema_dir: Path, dry_run: bool) -> int:
   123	    atlas_root = Path(atlas_root)
   124	    if not (atlas_root / ".atlas").is_dir():
   125	        print(f"no .atlas/ under {atlas_root}", file=sys.stderr)
   126	        return 2
   127	
   128	    canon_root = canon_dir(atlas_root)
   129	    validators = _load_schema_registry(schema_dir)
   130	
   131	    hyp_ok = hyp_bad = 0
   132	    ev_ok = ev_bad = 0
   133	    event_ok = event_bad = 0
   134	    pol_ok = pol_bad = 0
   135	
   136	    # 1) Tier-mapping policy first (referenced by every Decision)
   137	    pol = emit_policy_tier_mapping()
   138	    errs = _validate(pol, validators, "Policy")
   139	    if errs:
   140	        pol_bad += 1
   141	        print(f"[POLICY] {TIER_POLICY_ID}: {errs}", file=sys.stderr)
   142	    else:
   143	        pol_ok += 1
   144	        _write_envelope(pol, canon_root / "policies" / f"{TIER_POLICY_ID}.json", dry_run)
   145	
   146	    # 2) Claims
   147	    hyp_dir = atlas_root / ".atlas" / "hypotheses"
   148	    for p in sorted(hyp_dir.glob("*.json")):
   149	        try:
   150	            h = Hypothesis.model_validate(_load_json(p))
   151	        except Exception as exc:
   152	            hyp_bad += 1
   153	            print(f"[PARSE] hypothesis {p.name}: {exc}", file=sys.stderr)
   154	            continue
   155	        claim_env = emit_claim(h, atlas_root)
   156	        errs = _validate(claim_env, validators, "Claim")
   157	        if errs:
   158	            hyp_bad += 1
   159	            print(f"[CLAIM] {h.id}: {errs}", file=sys.stderr)
   160	            continue
   161	        hyp_ok += 1
   162	        _write_envelope(
   163	            claim_env, canon_root / "claims" / f"{h.id}.json", dry_run,
   164	        )
   165	
   166	        # Synthesize phase-transition events from current status.
   167	        # Every hypothesis had to pass through draft on the way to current
   168	        # state, so we emit the transitions in order. We emit at most two
   169	        # events (draft→probe, probe→promotion) and use the hypothesis's
   170	        # created_at as emitted_at; it's the best timestamp available
   171	        # historically.
   172	        target_phase = PHASE_FOR_STATUS[h.status]
   173	        ordered_phases = ["draft", "probe", "promotion"]
   174	        current_idx = ordered_phases.index(target_phase)
   175	        prev_phase = "draft"
   176	        for i in range(1, current_idx + 1):
   177	            to_phase = ordered_phases[i]
   178	            ev_id = f"pt-{h.id}-{prev_phase}-{to_phase}"
   179	            try:
   180	                event = emit_event_log(
   181	                    event_id=ev_id,
   182	                    event_kind="phase_transition",
   183	                    emitted_at=h.created_at,
   184	                    claim_id=h.id,
   185	                    from_phase=prev_phase,
   186	                    to_phase=to_phase,
   187	                )
   188	            except Exception as exc:
   189	                event_bad += 1
   190	                print(f"[EVENT] {ev_id}: {exc}", file=sys.stderr)
   191	                continue
   192	            errs = _validate(event, validators, "EventLogEntry")
   193	            if errs:
   194	                event_bad += 1
   195	                print(f"[EVENT] {ev_id}: {errs}", file=sys.stderr)
   196	                continue
   197	            event_ok += 1
   198	            _write_envelope(
   199	                event, canon_root / "event_log" / f"{ev_id}.json", dry_run,
   200	            )
   201	            prev_phase = to_phase
   202	
   203	    # 3) Evidence
   204	    ev_dir = atlas_root / ".atlas" / "evidence"
   205	    for p in sorted(ev_dir.glob("*.json")):
   206	        try:
   207	            e = Evidence.model_validate(_load_json(p))
   208	        except Exception as exc:
   209	            ev_bad += 1
   210	            print(f"[PARSE] evidence {p.name}: {exc}", file=sys.stderr)
   211	            continue
   212	        ev_env = emit_evidence(e, atlas_root)
   213	        errs = _validate(ev_env, validators, "Evidence")
   214	        if errs:
   215	            ev_bad += 1
   216	            print(f"[EVIDENCE] {e.id}: {errs}", file=sys.stderr)
   217	            continue
   218	        ev_ok += 1
   219	        _write_envelope(
   220	            ev_env, canon_root / "evidence" / f"{e.id}.json", dry_run,
   221	        )
   222	
   223	    total_bad = hyp_bad + ev_bad + event_bad + pol_bad
   224	    mode = "dry-run" if dry_run else "write"
   225	    print(
   226	        f"[{mode}] "
   227	        f"claims: {hyp_ok} ok / {hyp_bad} bad, "
   228	        f"evidence: {ev_ok} ok / {ev_bad} bad, "
   229	        f"events: {event_ok} ok / {event_bad} bad, "
   230	        f"policies: {pol_ok} ok / {pol_bad} bad"
   231	    )
   232	    return 0 if total_bad == 0 else 1
   233	
   234	
   235	def main() -> int:
   236	    ap = argparse.ArgumentParser(description=__doc__)
   237	    ap.add_argument("--atlas", type=Path, default=Path.cwd(),
   238	                    help="atlas repo root (default: cwd)")
   239	    ap.add_argument("--schemas", type=Path, default=DEFAULT_SCHEMA_DIR,
   240	                    help=f"schema dir (default: {DEFAULT_SCHEMA_DIR})")
   241	    ap.add_argument("--dry-run", action="store_true",
   242	                    help="validate only; do not write .canon/")
   243	    args = ap.parse_args()
   244	
   245	    try:
   246	        return migrate(args.atlas, args.schemas, args.dry_run)
   247	    except Exception:
   248	        traceback.print_exc()
   249	        return 2
   250	
   251	
   252	if __name__ == "__main__":
   253	    sys.exit(main())

codex
I have the adapter code. I’m checking the source model definitions now so the review can distinguish between what the adapter enforces and what it merely assumes upstream will keep true.
exec
/bin/bash -lc "rg -n \"class Hypothesis|class Evidence|EvidenceQuality|EvidenceDirection|HypothesisStatus|evidence_class\" /opt/workspace/projects/atlas/src/atlas/models -g '*.py'" in /opt/workspace/projects/atlas
 succeeded in 0ms:
/opt/workspace/projects/atlas/src/atlas/models/evidence.py:11:class EvidenceClass(str, Enum):
/opt/workspace/projects/atlas/src/atlas/models/evidence.py:19:class EvidenceQuality(str, Enum):
/opt/workspace/projects/atlas/src/atlas/models/evidence.py:25:class EvidenceDirection(str, Enum):
/opt/workspace/projects/atlas/src/atlas/models/evidence.py:31:class Evidence(BaseModel):
/opt/workspace/projects/atlas/src/atlas/models/evidence.py:36:    evidence_class: EvidenceClass
/opt/workspace/projects/atlas/src/atlas/models/evidence.py:37:    quality: EvidenceQuality
/opt/workspace/projects/atlas/src/atlas/models/evidence.py:38:    direction: EvidenceDirection
/opt/workspace/projects/atlas/src/atlas/models/hypothesis.py:11:class HypothesisStatus(str, Enum):
/opt/workspace/projects/atlas/src/atlas/models/hypothesis.py:19:class Hypothesis(BaseModel):
/opt/workspace/projects/atlas/src/atlas/models/hypothesis.py:28:    status: HypothesisStatus = HypothesisStatus.FORMULATED

exec
/bin/bash -lc 'nl -ba /opt/workspace/projects/atlas/src/atlas/models/hypothesis.py' in /opt/workspace/projects/atlas
 succeeded in 0ms:
     1	"""Hypothesis — specialization of CriticalAssumption for research."""
     2	
     3	from datetime import datetime, timezone
     4	from enum import Enum
     5	from typing import Optional
     6	from uuid import uuid4
     7	
     8	from pydantic import BaseModel, Field
     9	
    10	
    11	class HypothesisStatus(str, Enum):
    12	    FORMULATED = "formulated"
    13	    TESTING = "testing"
    14	    SUPPORTED = "supported"
    15	    FALSIFIED = "falsified"
    16	    PROMOTED = "promoted"
    17	
    18	
    19	class Hypothesis(BaseModel):
    20	    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    21	    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    22	    claim: str  # The falsifiable statement
    23	    rationale: str  # Why we believe this might be true
    24	    falsification_criteria: str  # What would prove it wrong
    25	    significance_threshold: float = 0.05  # Pre-registered alpha
    26	    domain: str = "crypto"
    27	    tags: list[str] = Field(default_factory=list)
    28	    status: HypothesisStatus = HypothesisStatus.FORMULATED
    29	    parent_primitive_id: Optional[str] = None  # If derived from existing knowledge

exec
/bin/bash -lc 'nl -ba /opt/workspace/projects/atlas/src/atlas/models/evidence.py' in /opt/workspace/projects/atlas
 succeeded in 0ms:
     1	"""Evidence — typed observation from experiments."""
     2	
     3	from datetime import datetime, timezone
     4	from enum import Enum
     5	from typing import Any
     6	from uuid import uuid4
     7	
     8	from pydantic import BaseModel, Field
     9	
    10	
    11	class EvidenceClass(str, Enum):
    12	    BACKTEST_RESULT = "backtest_result"
    13	    OUT_OF_SAMPLE_TEST = "out_of_sample_test"
    14	    STATISTICAL_TEST = "statistical_test"
    15	    LIVE_OBSERVATION = "live_observation"
    16	    EXTERNAL_PUBLICATION = "external_publication"
    17	
    18	
    19	class EvidenceQuality(str, Enum):
    20	    WEAK = "weak"
    21	    MODERATE = "moderate"
    22	    STRONG = "strong"
    23	
    24	
    25	class EvidenceDirection(str, Enum):
    26	    SUPPORTS = "supports"
    27	    CONTRADICTS = "contradicts"
    28	    INCONCLUSIVE = "inconclusive"
    29	
    30	
    31	class Evidence(BaseModel):
    32	    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    33	    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    34	    experiment_id: str
    35	    hypothesis_id: str
    36	    evidence_class: EvidenceClass
    37	    quality: EvidenceQuality
    38	    direction: EvidenceDirection
    39	    summary: str  # Human-readable description of finding
    40	    statistics: dict[str, Any] = Field(default_factory=dict)  # p-value, sharpe, CI, etc.
    41	    data_range: str = ""  # e.g. "2023-01-01 to 2024-06-30"
    42	    source_hash: str = ""  # sha256[:16] of raw finding block at ingest time; detects post-ingest edits

codex
I’m checking how this adapter is supposed to be used from the rest of Atlas, because the biggest risks here depend on whether these functions are best-effort sidecars or treated as truth-bearing records.
exec
/bin/bash -lc "rg -n \"emit_claim|emit_evidence|emit_decision|emit_event_log|canon_dir|adapters.discovery\" /opt/workspace/projects/atlas/src -g '*.py'" in /opt/workspace/projects/atlas
 succeeded in 0ms:
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:15:    emit_claim(h, atlas_path)           -> canon Claim dict
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:16:    emit_evidence(e, atlas_path)        -> canon Evidence dict
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:17:    emit_decision(cycle, ..., atlas_path) -> canon Decision dict
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:18:    emit_event_log(event, atlas_path)   -> canon EventLogEntry dict
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:20:    canon_dir(atlas_path)               -> Path to the .canon/ store
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:24:    emit_claim,
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:25:    emit_evidence,
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:26:    emit_decision,
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:27:    emit_event_log,
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:29:    canon_dir,
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:39:    "emit_claim",
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:40:    "emit_evidence",
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:41:    "emit_decision",
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:42:    "emit_event_log",
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:44:    "canon_dir",
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py:4:    python -m atlas.adapters.discovery.migrate --atlas /opt/workspace/projects/atlas [--dry-run]
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py:31:from atlas.adapters.discovery.emit import (
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py:38:    canon_dir,
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py:39:    emit_claim,
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py:40:    emit_event_log,
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py:41:    emit_evidence,
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py:128:    canon_root = canon_dir(atlas_root)
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py:155:        claim_env = emit_claim(h, atlas_root)
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py:180:                event = emit_event_log(
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/migrate.py:212:        ev_env = emit_evidence(e, atlas_root)
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/emit.py:48:def canon_dir(atlas_path: Path) -> Path:
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/emit.py:168:def emit_claim(h: Hypothesis, atlas_path: Path | str) -> dict[str, Any]:
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/emit.py:181:    events — see emit_event_log).
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/emit.py:210:def emit_evidence(e: Evidence, atlas_path: Path | str) -> dict[str, Any]:
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/emit.py:265:def emit_decision(
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/emit.py:348:def emit_event_log(

exec
/bin/bash -lc "rg -n \"StateStore.save|save\\(\" /opt/workspace/projects/atlas/src/atlas -g '*.py'" in /opt/workspace/projects/atlas
 succeeded in 0ms:
/opt/workspace/projects/atlas/src/atlas/research/ingest.py:118:        store.save("hypotheses", hyp_id, json.loads(hyp.model_dump_json()))
/opt/workspace/projects/atlas/src/atlas/research/ingest.py:139:        store.save("experiments", exp_id, json.loads(exp.model_dump_json()))
/opt/workspace/projects/atlas/src/atlas/research/ingest.py:170:    store.save("evidence", ev.id, json.loads(ev.model_dump_json()))
/opt/workspace/projects/atlas/src/atlas/runner.py:60:        self.state.save(kind, obj_id, data)
/opt/workspace/projects/atlas/src/atlas/runner.py:752:            self.graph_store.save(graph)
/opt/workspace/projects/atlas/src/atlas/cli.py:35:    _store.save(kind, obj_id, data)
/opt/workspace/projects/atlas/src/atlas/cli.py:351:        gs.save(graph)
/opt/workspace/projects/atlas/src/atlas/adapters/discovery/__init__.py:12:call them alongside StateStore.save().
/opt/workspace/projects/atlas/src/atlas/storage/state_store.py:7:Atomicity: save() writes to a tmpfile in the same directory then renames
/opt/workspace/projects/atlas/src/atlas/storage/state_store.py:36:    def save(self, kind: str, obj_id: str, data: dict) -> None:
/opt/workspace/projects/atlas/src/atlas/storage/graph_store.py:15:    def save(self, graph: CausalGraph) -> None:

codex
The main risk is looking like provenance and lifecycle truth while actually being a best-effort projection. I’m reading `StateStore.save()` to confirm whether the adapter ever gets a real transactional boundary to lean on.
exec
/bin/bash -lc 'nl -ba /opt/workspace/projects/atlas/src/atlas/storage/state_store.py' in /opt/workspace/projects/atlas
 succeeded in 0ms:
     1	"""Shared state management with pre-registration immutability enforcement.
     2	
     3	Both the CLI and AutonomousRunner must use this module to persist domain
     4	objects.  The runner's previous _save_obj bypassed immutability guards —
     5	this module closes that gap.
     6	
     7	Atomicity: save() writes to a tmpfile in the same directory then renames
     8	it to the target path.  os.replace() is atomic on Linux (single filesystem),
     9	so readers never observe a partial write.  Two concurrent workers writing the
    10	same object will both succeed; last-write-wins.  For hypotheses and
    11	experiments this is benign (both writers have identical pre-registered
    12	content).  For evidence the deterministic ID in ingest.py makes the
    13	content logically equivalent (modulo created_at).
    14	"""
    15	
    16	import json
    17	import os
    18	import tempfile
    19	from pathlib import Path
    20	
    21	
    22	# Fields that must not change after initial creation (pre-registration integrity)
    23	IMMUTABLE_FIELDS: dict[str, set[str]] = {
    24	    "hypotheses": {"claim", "rationale", "falsification_criteria", "significance_threshold"},
    25	    "experiments": {"hypothesis_id", "description", "method", "success_criteria", "failure_criteria", "parameters"},
    26	}
    27	
    28	
    29	class StateStore:
    30	    """JSON-per-object storage with immutability guards on pre-registered fields."""
    31	
    32	    def __init__(self, base_dir: Path) -> None:
    33	        self.base_dir = base_dir
    34	        self.base_dir.mkdir(parents=True, exist_ok=True)
    35	
    36	    def save(self, kind: str, obj_id: str, data: dict) -> None:
    37	        d = self.base_dir / kind
    38	        d.mkdir(exist_ok=True)
    39	        path = d / f"{obj_id}.json"
    40	
    41	        if path.exists() and kind in IMMUTABLE_FIELDS:
    42	            with open(path) as f:
    43	                existing = json.load(f)
    44	            for field in IMMUTABLE_FIELDS[kind]:
    45	                if field in existing and field not in data:
    46	                    raise ValueError(
    47	                        f"Cannot omit pre-registered field '{field}' on {kind}/{obj_id}"
    48	                    )
    49	                if field in existing and field in data and str(existing[field]) != str(data[field]):
    50	                    raise ValueError(
    51	                        f"Cannot modify pre-registered field '{field}' on {kind}/{obj_id}"
    52	                    )
    53	
    54	        # Atomic write: tmpfile in same directory → os.replace (rename).
    55	        # Ensures readers never see a partial write.
    56	        tmp_fd, tmp_name = tempfile.mkstemp(dir=d, suffix=".tmp")
    57	        try:
    58	            with os.fdopen(tmp_fd, "w") as f:
    59	                json.dump(data, f, indent=2, default=str)
    60	            os.replace(tmp_name, path)
    61	        except Exception:
    62	            try:
    63	                os.unlink(tmp_name)
    64	            except OSError:
    65	                pass
    66	            raise
    67	
    68	    def load(self, kind: str, obj_id: str) -> dict | None:
    69	        p = self.base_dir / kind / f"{obj_id}.json"
    70	        if p.exists():
    71	            with open(p) as f:
    72	                return json.load(f)
    73	        return None
    74	
    75	    def list_all(self, kind: str) -> list[dict]:
    76	        d = self.base_dir / kind
    77	        if not d.exists():
    78	            return []
    79	        objs = []
    80	        for p in sorted(d.glob("*.json")):
    81	            if p.suffix == ".json":
    82	                with open(p) as f:
    83	                    objs.append(json.load(f))
    84	        return objs

codex
1. **Most dangerous assumption** — The adapter assumes `sources=[]` is safe because Atlas “does not currently cite upstream canon” and that this makes the influence-firewall “trivially satisfied” (`emit.py:11-15`), then hardcodes that empty provenance onto every envelope in `_common_envelope()` (`emit.py:146-160`). If that claim is wrong even occasionally, the module will emit transformed or externally informed records as first-party canon objects, poisoning lineage, trust, and downstream dedupe/contamination checks across the entire `.canon` store.

2. **Missing failure mode** — The advertised dual-write mode is not transactionally modeled. The package says these emitters can be called “alongside `StateStore.save()`” (`__init__.py:9-12`), but `emit_claim()` only attaches the required artifact if the `.atlas` JSON already exists (`emit.py:193-202`), while `StateStore.save()` only guarantees atomicity for the `.atlas` write itself (`state_store.py:7-13`, `state_store.py:54-60`). In practice, ordering slips, retries, or partial failures will happen; this design has no account of `.atlas`/`.canon` divergence, and claim emission is especially brittle because it lacks the fallback path evidence has (`emit.py:243-256`).

3. **Boundary most likely to be collapsed in practice** — The supposed separation between “pure adapter” and storage/runtime concerns is already eroded. The module says “No I/O here — the caller is responsible for writing the dict to `.canon/` and running the validator” (`emit.py:5-6`), but `canon_dir()` creates directories (`emit.py:48-54`), emitters read and hash on-disk Atlas files (`emit.py:66-71`, `emit.py:193-199`, `emit.py:235-240`), and `migrate.py` reaches into private helper internals (`migrate.py:31-37`). Under real use this will stop behaving like a projection layer and start behaving like a second storage implementation coupled to Atlas’s filesystem layout.

Overall verdict: the code is tidy, but it overstates how “additive” and “non-invasive” it is. The real design is a provenance-bearing shadow store without a transaction boundary, which is exactly where subtle integrity bugs become systemic.
tokens used
102,384
1. **Most dangerous assumption** — The adapter assumes `sources=[]` is safe because Atlas “does not currently cite upstream canon” and that this makes the influence-firewall “trivially satisfied” (`emit.py:11-15`), then hardcodes that empty provenance onto every envelope in `_common_envelope()` (`emit.py:146-160`). If that claim is wrong even occasionally, the module will emit transformed or externally informed records as first-party canon objects, poisoning lineage, trust, and downstream dedupe/contamination checks across the entire `.canon` store.

2. **Missing failure mode** — The advertised dual-write mode is not transactionally modeled. The package says these emitters can be called “alongside `StateStore.save()`” (`__init__.py:9-12`), but `emit_claim()` only attaches the required artifact if the `.atlas` JSON already exists (`emit.py:193-202`), while `StateStore.save()` only guarantees atomicity for the `.atlas` write itself (`state_store.py:7-13`, `state_store.py:54-60`). In practice, ordering slips, retries, or partial failures will happen; this design has no account of `.atlas`/`.canon` divergence, and claim emission is especially brittle because it lacks the fallback path evidence has (`emit.py:243-256`).

3. **Boundary most likely to be collapsed in practice** — The supposed separation between “pure adapter” and storage/runtime concerns is already eroded. The module says “No I/O here — the caller is responsible for writing the dict to `.canon/` and running the validator” (`emit.py:5-6`), but `canon_dir()` creates directories (`emit.py:48-54`), emitters read and hash on-disk Atlas files (`emit.py:66-71`, `emit.py:193-199`, `emit.py:235-240`), and `migrate.py` reaches into private helper internals (`migrate.py:31-37`). Under real use this will stop behaving like a projection layer and start behaving like a second storage implementation coupled to Atlas’s filesystem layout.

Overall verdict: the code is tidy, but it overstates how “additive” and “non-invasive” it is. The real design is a provenance-bearing shadow store without a transaction boundary, which is exactly where subtle integrity bugs become systemic.
