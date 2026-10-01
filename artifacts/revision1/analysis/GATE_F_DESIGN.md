# Gate F Design: Dynamic Feasible-Choice Sensitivity

**Date:** 2026-09-30
**Amended:** 2026-09-30 — hash construction and event_uid frozen; unit tests specified
**Status:** Approved for implementation

---

## 1. Estimand and scientific question

**Estimand:**

> For a job requiring *k* cohort nodes, how many currently feasible candidate nodes must the scheduler be able to see before thermal information provides useful placement value?

This is a **dynamic feasible-choice-set sensitivity** experiment. It is not an occupancy simulation and must not be described as one. The manipulated variable is the size of the **exogenous** shortlist from which every policy draws at each job arrival.

**M4 established:**
- FP beats Random (24/30 definite wins, dlo_med +1.89 pp).
- FP-spread beats FP (18/25 definite wins, dlo_med +1.76 pp).
- FP-spread and Location-only are **not consistently distinguishable** (11/25 definite FP-spread wins, 14 indistinguishable, 0 Location wins; dlo_med −0.81 pp, CI spanning zero).

**Gate F question:**
Does learned thermal information add placement value **beyond** physical-location information as scheduler choice becomes constrained? Specifically, is there a choice-ratio regime where FP or FP-spread separates from Location while both remain above Random?

**Three scientifically valid outcomes (all to be reported):**

1. FP/FP-spread and Location diverge from Random at low choice ratios, but FP-spread and Location track each other at every ratio → persistent thermal structure is highly predictable from physical placement; a location-aware scheduler captures most of it.

2. FP-spread separates from Location as choice is constrained → the learned fingerprint contains operational thermal information beyond topology; most valuable when choices are scarce.

3. All three beat Random similarly at all ratios → thermal scheduling benefit is robust to choice constraints; source of advantage is not disambiguated by this experiment.

Negative findings are first-class results. The paper framing depends on the outcome.

---

## 2. Frozen inputs

All policy logic and source artifacts are frozen at M4 v3. Nothing changes.

| Artifact | Role |
|----------|------|
| `m4_fair_baselines.json` (v5) | FP and FP-spread lambda_rows; scenario seeds; workload seeds |
| `m4_random_canonical.json` | Canonical Random lambda_rows |
| `m4_canonical_policies.json` | Canonical Location lambda_rows |
| `m4_canonical_comparisons_v3.json` | Authoritative M4 comparisons; defines correct interval logic |
| `M4_V3_FINAL_AUDIT.md` | Frozen crossing estimand definition |

**Frozen policies (no tuning):**

| Policy | Source | Selector logic |
|--------|--------|---------------|
| `full_random` | canonical | uniform random within eligible shortlist |
| `full_fp` | v5 | lowest `FA_2024` first within eligible shortlist |
| `full_loc` | canonical | lowest position-mean FA (chassis/slot/board/node_pos) within eligible shortlist |
| `full_fp_spread` | v5 | FP-spread rule within eligible shortlist |

No policy parameter is changed. The only manipulation is the external shortlist size.

---

## 3. Choice ratios

```
r ∈ {1.0, 1.25, 1.5, 2.0, 4.0, 8.0, unrestricted}
```

For a job requiring *k* cohort nodes, the external shortlist exposes at most:

```
m = min( ceil(r × k), n_available )
```

where `n_available` = policy-neutral cohort nodes not blocked by background load at that instant.

`unrestricted` sets m = n_available (no shortlist cap). This reproduces the M4 unrestricted replay exactly and is the preflight gate (§6).

**Notation:**
- *k* = job cohort node count (nodes required by the job)
- *m* = shortlist size = min(ceil(r × k), n_available)
- *actual choice ratio* = m / k (may be < r when n_available < ceil(r × k))

Report actual choice ratio (m/k) median alongside nominal r. A 2× nominal shortlist is only 2× actual if enough cohort nodes are available.

---

## 4. Candidate-set construction

### 4.1 Base eligibility (policy-neutral)

At each job arrival, identify cohort nodes that are:
- Not currently occupied by a base or synthetic job (hard constraint).
- Not blocked by fixed/non-cohort background load at that instant.

This is the **policy-neutral available pool** for that event. It does not depend on thermal fingerprint, location, power, residual, future workload, or any policy state.

### 4.2 Node priority: frozen BLAKE2b keyed hash

Every node receives a deterministic, policy-neutral priority for each scheduling event. The construction is frozen here and must not be altered by the implementer.

**Priority function (canonical definition):**

```
priority(scenario_seed, event_uid, hostname)
    = uint64_big_endian(
        BLAKE2b(
            key     = uint64_big_endian(scenario_seed),   # 8-byte key
            message = UTF8(event_uid) || 0x00 || UTF8(hostname),
            digest_size = 8
        )
      )
```

**Sort key** (ascending): `(priority, hostname)` — hostname is the deterministic tie-breaker for the vanishingly unlikely case of a 64-bit digest collision.

**Python reference implementation:**

```python
import hashlib

def choice_priority(
    scenario_seed: int,
    event_uid: str,
    hostname: str,
) -> tuple[int, str]:
    key = scenario_seed.to_bytes(8, "big", signed=False)
    msg = (
        event_uid.encode("utf-8")
        + b"\x00"
        + hostname.encode("utf-8")
    )
    digest = hashlib.blake2b(msg, key=key, digest_size=8).digest()
    return int.from_bytes(digest, "big"), hostname
```

The NUL byte `0x00` separates `event_uid` from `hostname`. This is safe as long as neither field contains a NUL character, which is enforced by the event_uid construction below and the hostnames used in this fleet. If either field could ever contain NUL, length-prefix both strings instead.

**Why a keyed hash, not a seeded RNG:**
- No Python set/list ordering dependence.
- No PRNG state dependence.
- No dependence on how many other candidate nodes exist at the time of the call.
- Removing one node does not reshuffle the priorities of any other node.
- Adding a candidate does not reshuffle existing nodes.
- The same (scenario, event, node) always produces the same priority, regardless of execution order.
- Nested shortlists (`C_{1.0} ⊆ C_{1.25} ⊆ ...`) follow automatically from taking longer prefixes.
- All four policies receive byte-for-byte identical external shortlists.
- Reproduction requires only three pieces of metadata: scenario_seed, event_uid, hostname.

### 4.3 Event UID: frozen definition

`event_uid` must be:
- **Globally unique** within a scenario (no two scheduling events share the same uid).
- **Deterministic**: generated from the scenario workload before any policy replay begins.
- **Policy-independent**: identical across all four policies and all choice ratios.
- **Stable**: does not change if the replay is rerun with the same seeds.

**Do not use `job_idx` alone for synthetic events.** Synthetic workload generation creates copies or descendants of historical base jobs. Two synthetic events that share a base parent would inherit the same `job_idx` and therefore get identical node priorities, breaking independence.

**Frozen uid scheme:**

| Job type | event_uid |
|----------|-----------|
| Base job | `base:<job_idx>` |
| Synthetic job | `syn:<scenario_seed>:<synthetic_ordinal>` |

where `synthetic_ordinal` is the zero-based index of the synthetic job in the deterministic sorted order of the complete synthetic workload for that scenario (sorted by start_time, then by stable synthetic identity). This ordering must be computed and locked before any policy replay begins.

### 4.4 Shortlist construction (per job arrival)

```python
import math

# available_nodes: policy-neutral pool for this event (§4.1)
ordered = sorted(
    available_nodes,
    key=lambda h: choice_priority(scenario_seed, event_uid, h),
)

m = min(len(ordered), math.ceil(choice_ratio * k))
candidate_shortlist = ordered[:m]
```

By construction, shortlists are nested across ratios for the same event:
```
C_{1.0} ⊆ C_{1.25} ⊆ C_{1.5} ⊆ C_{2.0} ⊆ C_{4.0} ⊆ C_{8.0} ⊆ C_{unrestricted}
```

The nesting is exact (not approximate): `ordered` is computed once per event from fixed priorities, and `C_r` is simply `ordered[:m_r]`.

### 4.5 Per-policy endogenous filtering and selection

Each policy receives the **same external shortlist** for ratio r at each job arrival. It then:

1. Intersects the shortlist with its own **endogenous eligibility** — utilization cap, current synthetic occupancy, any policy-specific state — to form its **eligible set**.
2. Applies its frozen selector (random / lowest-FP / lowest-location-score / FP-spread rule) to the eligible set.
3. If the eligible set has fewer than *k* nodes: the job is recorded as a **choice-constrained drop** and not admitted.

**Critical:** shortlist construction happens fresh at every job arrival from the current policy-neutral pool. Nodes are never permanently removed from consideration for the duration of a scenario as in the M4 static-pool test.

### 4.6 No-choice negative control

When m = k (r = 1.0, or when n_available ≤ k), every eligible node is the same for every policy (the shortlist has exactly k nodes, and all have the same endogenous eligibility by definition of the neutral pool). All four policies must select the same k nodes. Verify this assertion holds in the dev scenarios.

---

## 5. QoS and feasibility invariants

### Preserved invariant (identical to M4)
**No base job is delayed or under-served.** Base jobs use their historical node assignments. The look-ahead/QoS rules from M4 are preserved exactly.

### New drop category
Record separately:
- `n_drop_choice_constrained`: job dropped because the restricted shortlist contains fewer than *k* policy-eligible nodes (shortlist too small after endogenous filtering).
- `n_drop_cap`: existing utilization-cap drops.
- `n_drop_physical`, `n_drop_la`: existing categories.

At r = unrestricted, `n_drop_choice_constrained` must be zero for all policies (preflight check).

---

## 6. Preflight gate: reproduce M4 at r = unrestricted

Before running any restricted ratios or looking at held-out results, the implementation must pass all of the following at r = unrestricted on sc0–4:

| Check | Requirement |
|-------|-------------|
| Workload seeds | Identical to v5 / canonical sources |
| Residual draws | Identical (same PRNG sequence) |
| Raw lambda rows | Metric-for-metric identical to M4 source files for all policies |
| Reconstructed crossings | Capacity-order first-violation (v3 estimand) applied to new lambda_rows produces same C_lower and C_upper as `m4_canonical_comparisons_v3.json` scenario_rows |
| C_lower ≤ C_upper | 0 violations across all reconstructed crossings |
| Right-censored | 0 unexpected right-censored crossings |
| No-choice control | At r = 1.0, all four policies select identical node sets whenever shortlist has exactly k policy-neutral nodes |
| Choice-constrained drops | 0 at r = unrestricted for all policies |

If any check fails, stop. Fix the implementation before looking at sc5–29 or running restricted ratios.

---

## 7. Development / held-out protocol

```
sc0–4   (5 scenarios)  →  implementation, debugging, preflight gates only
sc5–29  (25 scenarios) →  authoritative evaluation; look at these ONLY after
                           sc0–4 pass all preflight checks
```

**Code freeze:** lock policy logic, shortlist construction, hash function, and crossing estimand before running sc5–29. Document the git SHA at that point.

**No post-hoc tuning:** do not change choice ratios, policy parameters, hash construction, or QoS rules after seeing held-out results. Any change requires discarding held-out runs and starting again.

---

## 8. Execution plan

### 8.1 Lambda sweep

Reuse the M4 lambda sweep: `[1.0, 1.06, 1.1, 1.15, 1.2, 1.3, 1.4, 1.5, 1.55, 1.6, 1.7, 1.8, 1.9, 2.0]` plus the extension `[2.25, 2.5, 3.0, 3.5, 4.0]` if needed for right-censoring avoidance. Same DELTA_CAP, u_max formula, and N_BINS as M4.

### 8.2 Scenario structure

For each scenario (sc), for each lambda, for each ratio r: run all four policies on the **same shortlist** (generated from the same priority draw for that (sc, lambda, r) triple). Each (sc, lambda, r, policy) produces one row of metrics.

### 8.3 Output structure

Per scenario, per ratio, per policy, per lambda:
- All fields in M4 lambda_rows (capacity_unlock_pct, B_primary_ratio, etc.)
- Additionally: `m_shortlist`, `m_eligible`, `actual_choice_ratio`, `n_drop_choice_constrained`

Per scenario, per ratio, per policy:
- Reconstructed crossing (C_lower_pct, C_upper_pct, status, first_binding) via v3 capacity-order first-violation estimand.

Per ratio, per policy:
- Aggregated metrics across scenarios.

Per ratio, per comparison pair:
- Interval comparison: delta_lo, delta_hi, verdict.
- Bootstrap CI: N_BOOTSTRAP = 5000, BOOTSTRAP_SEED = 9999 (same as M4).
- Report pct_definitely_A / indistinguishable / definitely_B.

---

## 9. Primary outcomes and metrics

### Per-lambda row (all ratios, all policies)

| Metric | Notes |
|--------|-------|
| `capacity_unlock_pct` | Identical definition to M4 |
| `B_primary_ratio`, `S_primary_ratio` | Thermal/exposure budget ratios |
| `B_cab_ratio` | Cabinet power ratio |
| `infeasible`, `first_binding` | Feasibility and binding constraint |
| `n_syn_admit` | Admitted synthetic jobs |
| `n_drop_cap`, `n_drop_physical`, `n_drop_la` | Existing drop categories |
| `n_drop_choice_constrained` | New: shortlist too small |
| `syn_node_hours` | Admitted synthetic node-hours |
| `m_shortlist_median` | Median shortlist size across jobs at this lambda |
| `actual_choice_ratio_median` | Median m/k across jobs |
| `mean_F_syn` | Mean thermal fingerprint of admitted synthetic nodes |
| `loc_score_median` | Median location score of selected nodes |
| `cab_span_median`, `cab_span_p90` | Cabinet span |

### Per-scenario reconstructed crossing (per ratio, per policy)

C_lower_pct, C_upper_pct, status, first_binding_constraint — computed from lambda_rows using v3 capacity-order first-violation estimand.

### Job-size stratification

Report all metrics separately for four job-size quartiles of k (cohort node count). A 2× shortlist for a k=4 job is 8 nodes absolute; for a k=512 job it is 1024 nodes absolute. The effective constraint regime differs substantially.

---

## 10. Paired comparisons and CI methodology

### 10.1 Interval comparison (identical to M4 v3)

For each scenario at each ratio:
```
delta_lo = C_lower_A - C_upper_B   (pessimistic: A better iff > 0)
delta_hi = C_upper_A - C_lower_B   (optimistic)
assert delta_lo <= delta_hi
```

Verdict: `definitely_A_better` if delta_lo > 0; `definitely_B_better` if delta_hi < 0; `indistinguishable` otherwise.

### 10.2 Bootstrap CI (paired, scenario-level)

Resample the vector of per-scenario delta_lo values with replacement (same paired bootstrap as M4). Report:
- median delta_lo, CI95
- median delta_hi, CI95
- n_definitely_A / n_indistinguishable / n_definitely_B

### 10.3 Comparison pairs (for each ratio r)

| Pair | n scenarios | Notes |
|------|------------|-------|
| FP vs Random | 25 (sc5–29) | Primary thermal vs. baseline |
| Location vs Random | 25 (sc5–29) | Topology vs. baseline |
| FP-spread vs Random | 25 (sc5–29) | Best policy vs. baseline |
| FP-spread vs FP | 25 (sc5–29) | Spreading benefit |
| FP-spread vs Location | 25 (sc5–29) | **Key question** |

At r = unrestricted these must reproduce the M4 v3 held-out results (sc5–29 subset).

---

## 11. Primary figure specification

**x-axis:** actual median feasible choice ratio (m/k), or equivalently nominal r, with r=1.0 at left and r=unrestricted at right.

**y-axis:** median conservative scheduling advantage, delta_lo (pp).

**Five curves:**
1. FP − Random (delta_lo)
2. Location − Random (delta_lo)
3. FP-spread − Random (delta_lo)
4. FP-spread − FP (delta_lo)
5. FP-spread − Location (delta_lo)

**Annotations:**
- Shaded 95% bootstrap CI band on each curve.
- Horizontal dashed line at delta_lo = 0.
- Vertical dashed line at r = 1.0 (no-choice control; all curves must converge to 0 or indistinguishable).
- Right endpoint reproduces M4 v3 held-out results.

**Secondary figure (optional):** same axes but y = n_definitely_A / n (fraction of definite wins), for the same 5 pairs.

---

## 12. What this experiment does NOT change

- Policy logic, selectors, or parameters.
- Scenario seeds or workload seeds.
- The M4 crossing estimand (v3 capacity-order first-violation).
- The bootstrap CI methodology (N=5000, seed=9999, paired scenario-level).
- The M4 v3 results. At r = unrestricted the held-out comparisons must reproduce M4 v3 exactly.
- The 30-scenario / sc5–29 held-out evaluation set.

---

## 13. Required unit tests (must pass before any scenario run)

The following six tests must exist in the test suite and pass before sc0–4 are run. They are not optional.

**Test 1 — Determinism:** Calling `choice_priority(seed, event_uid, hostname)` twice with identical arguments returns an identical `(int, str)` tuple.

**Test 2 — Input-order independence:** Given a set of hostnames passed in two different Python iteration orders (e.g., sorted ascending vs. sorted descending), `sorted(hostnames, key=lambda h: choice_priority(seed, uid, h))` produces the same ranked list both times.

**Test 3 — Single-node stability:** Given a shortlist `ordered` for event E, removing one node from `available_nodes` and recomputing leaves the relative order of all remaining nodes unchanged.

**Test 4 — Nesting:** For a fixed event with `n_available = 20` and `k = 4`, verify:
```
shortlist(r=1.0)  ⊆  shortlist(r=1.25)  ⊆  shortlist(r=1.5)
                  ⊆  shortlist(r=2.0)   ⊆  shortlist(r=4.0)
                  ⊆  shortlist(r=8.0)   ⊆  shortlist(r=unrestricted)
```
by set containment of the node lists at each ratio.

**Test 5 — Cross-policy shortlist identity:** At a fixed (sc, lambda, ratio, event), all four policies receive byte-for-byte identical `candidate_shortlist` lists before endogenous filtering.

**Test 6 — Synthetic uid uniqueness:** Generate a scenario's complete synthetic workload. Verify that no two synthetic events share the same `event_uid` (`syn:<scenario_seed>:<synthetic_ordinal>`), and that base and synthetic events never collide (`base:*` vs `syn:*` are disjoint namespaces by prefix).

---

## 14. Implementation checklist (pre-run)

- [ ] Unit tests 1–6 all pass (§13).
- [ ] Nesting property verified in sc0 dev run at lambda=1.06: `C_{1.0} ⊆ ... ⊆ C_unrestricted`.
- [ ] No-choice control assertion verified in sc0: at r=1.0, all four policies select same nodes.
- [ ] At r=unrestricted, lambda rows for sc0–4 match M4 source files (metric-for-metric).
- [ ] At r=unrestricted, reconstructed crossings for sc0–4 match M4 v3 scenario_rows.
- [ ] 0 choice-constrained drops at r=unrestricted.
- [ ] 0 C_lower > C_upper post-reconstruction.
- [ ] 0 unexpected right-censored crossings.
- [ ] Job-size quartile boundaries computed and frozen before held-out run.
- [ ] Git SHA committed before sc5–29 execution.
- [ ] No policy or ratio changes after held-out run begins.

---

## 15. Output files (to be produced)

| File | Contents |
|------|----------|
| `gate_f_lambda_rows.json` | Full lambda_rows for all (sc, ratio, policy, lambda) |
| `gate_f_crossings.json` | Reconstructed crossings for all (sc, ratio, policy) |
| `gate_f_comparisons.json` | Paired comparison tables for all ratios and pairs |
| `gate_f_preflight.json` | Preflight check record (sc0–4 vs M4 v3) |
| `gate_f_fig_delta_lo.pdf/.png` | Primary figure |

---

## 16. Relationship to paper framing

M4 finding (frozen): *"Topology-aware thermal scheduling clearly improves over Random. FP-spread improves over plain FP. However, FP-spread and a strong location-only baseline are not consistently distinguishable."*

Gate F will refine this into one of:

- **Spatial signal dominates**: location captures most of the benefit at all choice ratios → ThermalShift improves over Random, but much of its value is topology-recoverable.
- **Fingerprint adds operational value**: FP-spread separates from Location when choice is constrained → the learned fingerprint encodes actionable thermal heterogeneity beyond physical placement.
- **Robust equivalence**: all thermal-aware policies outperform Random similarly regardless of choice ratio → the finding is robust to choice constraints, but the source of FP-spread's Location equivalence is still unresolved.

All three are publishable. The experiment is designed to distinguish them.
