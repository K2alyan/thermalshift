# Gate F Design: Dynamic Feasible-Choice Sensitivity

**Date:** 2026-09-30
**Amended:** 2026-09-30 — hash construction and event_uid frozen; unit tests specified
**Amended:** 2026-09-30 — §4.6 no-choice control corrected; generation_ordinal frozen; terminology clarified
**Amended:** 2026-09-30 — §4.1 external pool corrected (exogenous blockers only); §5 base-job placement corrected; §6 preflight strengthened
**Amended:** 2026-09-30 — drop-cause semantics frozen (E_full/E_r); terminology finalized; §8.2 priority description corrected; §11 r=1 annotation fixed; realized-choice diagnostics added.
**Amended:** 2026-09-30 — Estimand/intervention corrected. Intervention now follows M4 feasibility. Gate F restricts how many currently feasible nodes the selector may inspect, not external candidate visibility. Design frozen.
**Amended:** 2026-09-30 — Consistency cleanup only. §3 formula corrected to per-policy m_p,r; n_available removed. §4.2 nesting and cross-policy-identity bullets qualified. §4.4 nesting claim qualified (fixed E_full,p only). §8.2 CRN claim qualified. Tests 3–4 use full_eligible/E_full,p. §14 checklist: runtime nesting assertion removed.
**Status:** Approved for implementation

---

## 1. Estimand and scientific question

**Estimand:**

> For a job requiring *k* cohort nodes, how many currently feasible candidate nodes must the scheduler be able to see before thermal information provides useful placement value?

This is a **dynamic feasible-choice-set sensitivity** experiment. It is not an occupancy simulation and must not be described as one. The manipulated variable is the number of currently feasible candidate nodes the selector may inspect at each job arrival.

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

No policy parameter is changed. The only manipulation is the number of currently feasible candidates exposed to the selector (the feasible-choice shortlist size).

---

## 3. Choice ratios

```
r ∈ {1.0, 1.25, 1.5, 2.0, 4.0, 8.0, unrestricted}
```

For policy p and a job requiring *k* cohort nodes, the Gate F shortlist is drawn from E_full,p (§4.1) and has size:

```
m_p,r = min( ceil(r × k), |E_full,p| )
```

`E_full,p` is the per-policy set of currently feasible candidates returned by the frozen M4 candidate-generation logic. The shortlist and its size are therefore policy-specific once replay states diverge.

**Frozen shortlist definitions:**
- `C_p,r` = first `m_p,r` nodes from hash-ranked E_full,p (§4.2, §4.4)
- `C_p,unrestricted` = E_full,p (no prefix restriction; full feasible set exposed)

`unrestricted` exposes the full E_full,p to the selector. This reproduces the M4 unrestricted replay exactly and is the preflight gate (§6).

**Terminology (frozen):**

| Term | Symbol | Definition |
|------|--------|-----------|
| *k* | — | Job cohort node count (nodes required) |
| `nominal_choice_ratio` | r | The experimental treatment variable. Set by the design; identical across all policies. |
| `full_feasible_count` | \|E_full,p\| | Per-policy: number of currently feasible candidate nodes produced by the frozen M4 candidate-generation logic. Policy-specific; can differ across policies at the same event once replay states diverge. |
| `exposed_feasible_count` | \|C_p,r\| | Per-policy: shortlist size after Gate F restriction. = min(ceil(r × k), \|E_full,p\|). Always ≥ k when \|E_full,p\| ≥ k and r ≥ 1. |
| `realized_feasible_choice_multiplier` | \|C_p,r\| / k | Per-policy: the number of currently feasible choices actually exposed, as a multiple of the job size. This is what the estimand measures. |

The primary x-axis is `nominal_choice_ratio` r (the manipulated variable). Because Gate F intervenes after M4 feasibility, `realized_feasible_choice_multiplier` now truly means what it says: the scheduler has |C_p,r| / k times as many currently feasible candidates as the job requires.

---

## 4. Candidate-set construction

### 4.1 Frozen M4 feasibility step (per policy)

For each scheduling event and each policy, first obtain the complete set of currently feasible candidate nodes using the **exact frozen M4 full-policy candidate-generation logic**, including all job-type-specific occupancy rules, utilization-cap handling, look-ahead/QoS constraints, and base-job fallback semantics:

```
E_full,p  =  frozen_m4_candidate_set(policy=p, event=e, state=state_p)
```

Do not reimplement M4 eligibility from a new formula. Call or reuse the existing M4 candidate-generation path directly. The logic is frozen at M4 v3 and must not be altered for Gate F.

`E_full,p` is **per-policy** and will diverge across policies once their replay states differ — because counterfactual base-job occupancy and synthetic occupancy are policy-specific. This is expected and must not be forced to be identical.

**If |E_full,p| < k**: the job is not feasible under the current policy state with any choice ratio. Apply the existing M4 failure/drop/invariant semantics exactly. Gate F is not the cause; this is an ordinary M4 outcome.

**If |E_full,p| ≥ k**: proceed to Gate F shortlist (§4.4).

**Construction pipeline for each scheduling event:**

```
Frozen M4 candidate generation  (§4.1 — per policy, full feasibility)
    → E_full,p  (currently feasible nodes; policy-specific)
    ↓ if |E_full,p| < k: existing M4 failure semantics
    ↓ else:
    BLAKE2b hash priority on E_full,p  (§4.2)
    → C_p,r = first min(ceil(r×k), |E_full,p|) feasible nodes  (§4.4)
    → Frozen policy selector  (§4.5)
```

This ordering ensures that Gate F restricts how many currently feasible nodes the selector may inspect, not external candidate visibility. At r ≥ 1 and |E_full,p| ≥ k, C_p,r always contains at least k feasible nodes, so Gate F never directly prevents a feasible job from being placed.

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
- For a fixed E_full,p at a given event, longer-prefix shortlists are nested: `C_p,{1.0} ⊆ C_p,{1.25} ⊆ ... ⊆ E_full,p`. This prefix property holds within one replay at a fixed event state; it does not extend across independently evolved ratio replays where earlier placements may have changed E_full,p.
- If two policies have identical E_full sets for an event (as they do at r=1 before any state divergence), the policy-neutral hash produces identical rankings and identical shortlists at the same r. Once policy states diverge, E_full,p may differ and shortlist identities may therefore differ across policies.
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
| Synthetic job | `syn:<scenario_seed>:<generation_ordinal>` |

`generation_ordinal` is the zero-based index assigned to each synthetic event **at the moment the scenario's synthetic workload is generated**, in generation order, before any sorting by start_time or any policy replay. It is an immutable column on the synthetic workload table. Once assigned it does not change regardless of how the workload is later sorted, filtered, or replayed.

Sorting the workload by start_time for scheduling purposes does not renumber the `generation_ordinal`. The uid is derived from the generation sequence, not from the scheduling sequence.

### 4.4 Gate F shortlist construction (per policy, per job arrival)

Called only when |E_full,p| ≥ k (§4.1). Applies to the per-policy feasible set.

```python
import math

# full_eligible: E_full,p from frozen M4 candidate generation (§4.1)
# Already filtered for all occupancy, caps, QoS — every node here is feasible.

ordered_p = sorted(
    full_eligible,
    key=lambda h: choice_priority(scenario_seed, event_uid, h),
)

m_p_r = min(len(ordered_p), math.ceil(r * k))
# Since len(ordered_p) = |E_full,p| >= k and r >= 1.0, m_p_r >= k always.

C_p_r = ordered_p[:m_p_r]  # Gate F shortlist: m_p_r currently-feasible nodes

selected = frozen_selector(C_p_r, k, policy=p)
```

**Prefix nesting (fixed E_full,p):** for a fixed E_full,p at a given event, shortlists at increasing r are nested prefixes of the same hash ordering:

```
C_p,{1.0} ⊆ C_p,{1.25} ⊆ C_p,{1.5} ⊆ C_p,{2.0} ⊆ C_p,{4.0} ⊆ C_p,{8.0} ⊆ C_p,{unr}
```

This property holds mathematically for any fixed E_full,p. Across independently evolved ratio replays, earlier placements under different r values change occupancy state and therefore E_full,p at subsequent events; runtime shortlists from separate ratio replays are not required to be nested.

**Candidate identities may differ across policies** at the same event once replay states diverge (because E_full,p is policy-specific). This is correct behavior. Fairness is provided by identical workload and residual draws, identical nominal r, and the same policy-blind hash function applied to each policy's own feasible set.

### 4.5 Frozen policy selector

Every node in C_p,r is already feasible (produced by §4.1). There is no separate endogenous filtering step. The frozen policy selector receives C_p,r directly and chooses k nodes:

| Policy | Selector rule |
|--------|--------------|
| `full_random` | uniform random draw of k from C_p,r |
| `full_fp` | lowest FA_2024 first; take top k |
| `full_loc` | lowest position-mean FA (chassis/slot/board/node_pos); take top k |
| `full_fp_spread` | FP-spread rule; take k |

Selector logic is identical to M4 v3 — frozen, no tuning.

Since |C_p,r| ≥ k always holds when |E_full,p| ≥ k and r ≥ 1, the selector always has at least k candidates. Gate F does not introduce a new category of infeasible placements; it restricts which feasible candidates are visible to the selector, which changes placement quality and downstream thermal/power headroom.

**Shortlist construction happens fresh at every job arrival** from the current per-policy feasible set. Nodes are never permanently removed for the duration of a scenario.

### 4.6 r=1 negative control (strong)

At r = 1.0 and |E_full,p| ≥ k for all policies: each policy's Gate F shortlist C_p,{1.0} contains exactly k feasible nodes. The selector has no choice discretion — it must place exactly those k nodes. Since E_full,p is produced by the M4 full-policy candidate-generation logic and all four policies start from identical state before any placements, the following holds **by induction**:

**Base case:** at the first job event, all four policies have identical replay state. Their E_full,p sets are therefore identical. All four receive the same k-node C_p,{1.0} and make the same k placements.

**Inductive step:** if all four policies have identical replay state before event t, they produce identical E_full,p at event t, receive the same k-node shortlist, make the same k placements, and arrive at identical state after event t.

**Conclusion:** throughout an r = 1.0 replay, as long as each job is feasible (|E_full,p| ≥ k), all four policies select identical nodes at every event, their replay states evolve identically, and their raw lambda-row metrics are identical.

**Assert on sc0–4 at r = 1.0:**
- Identical selected node sets across all four policies at every feasible event.
- Identical evolving synthetic occupancy and utilization state across policies.
- Identical raw lambda-row metrics (capacity_unlock_pct, B/B_ref, S/S_ref, B_cab, drop counts).
- Identical reconstructed crossings.

If the inductive argument holds, this is a hard assertion, not an empirical check. A violation indicates an implementation bug (state divergence before the expected event, or policy-specific selection when |C_p,r| = k).

**Unrestricted is the opposite endpoint:** C_p,{unr} = E_full,p — full feasible set exposed — which must reproduce M4 v3 exactly.

---

## 5. QoS and feasibility invariants

### Preserved invariant (identical to M4 full-policy replay)

Historical base jobs retain their original start times, durations, and requested cohort-node counts, but their **cohort-node placements are counterfactually replayed under each policy**, exactly as in M4. No base job may be delayed or under-served. The existing M4 look-ahead/QoS invariant is preserved exactly.

This is the M4 **full-policy** replay model. It is not the marginal-policy model in which base jobs keep their historical node assignments. If implemented as marginal-policy, the unrestricted preflight cannot reproduce M4 v3.

### Drop classification (Gate F)

Existing M4 drop categories (`n_drop_cap`, `n_drop_physical`, `n_drop_la`) are preserved and retain their M4 semantics.

**Gate F introduces no new drop categories.**

Gate F intervenes after M4 feasibility (§4.1): every node in C_p,r is already feasible. Because |C_p,r| ≥ k whenever |E_full,p| ≥ k and r ≥ 1.0, the selector always receives at least k feasible candidates and Gate F cannot prevent a feasible placement.

If |E_full,p| < k at any policy and event, that is an existing M4 failure condition, not a Gate F failure. Apply the existing M4 failure/drop/invariant semantics exactly and record the drop under the existing M4 category. Report `full_feasible_count` (|E_full,p|) as a per-event diagnostic field to confirm that shortfall is not Gate F-caused.

---

## 6. Preflight gate: reproduce M4 at r = unrestricted

Before running any restricted ratios or looking at held-out results, the implementation must pass all of the following at r = unrestricted on sc0–4:

| Check | Requirement |
|-------|-------------|
| Workload seeds | Identical to v5 / canonical sources |
| Residual draws | Identical (same PRNG sequence) |
| Base-job placement behavior | Counterfactual base-job node selections under each policy match M4 frozen source (metric-for-metric per policy) |
| Synthetic placement behavior | Synthetic node selections match M4 frozen source (metric-for-metric per policy) |
| Raw lambda rows | All per-lambda metrics (capacity_unlock_pct, B_primary_ratio, B_cab_ratio, S_primary_ratio, syn_node_hours, infeasible, first_binding, drop counts) identical to M4 source files for all policies |
| Reconstructed crossings | Capacity-order first-violation (v3 estimand) applied to new lambda_rows produces same C_lower and C_upper as `m4_canonical_comparisons_v3.json` scenario_rows |
| C_lower ≤ C_upper | 0 violations across all reconstructed crossings |
| Right-censored | 0 unexpected right-censored crossings |
| r=1 inductive negative-control assertion | At r = 1.0 on sc0–4: all four policies must select identical node sets at every feasible event, maintain identical evolving replay state, and produce identical lambda-row metrics and reconstructed crossings throughout the replay. Any deviation is an implementation bug (see §4.6). |

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

For each scenario (sc), for each lambda, for each ratio r: run all four policies with the same nominal choice ratio r. Each (sc, lambda, r, policy) produces one row of metrics. Each policy operates on its own E_full,p (which may diverge across policies once occupancy states differ), but applies the same hash function and the same r to construct C_p,r from its own feasible set.

The node priority for each (event, hostname) pair is fixed by `(scenario_seed, event_uid, hostname)` — it does not depend on lambda or choice ratio. Within a single replay run, the hash ordering at any event is stable across lambda values. However, because different r values lead to different placements at earlier events, E_full,p at a later event may differ across independently evolved ratio replays; runtime shortlists from separate ratio replays are not guaranteed to be nested. The priority function nonetheless provides common-random-number structure within each replay by keeping node ranks stable across lambda values.

### 8.3 Output structure

Per scenario, per ratio, per policy, per lambda:
- All fields in M4 lambda_rows (capacity_unlock_pct, B_primary_ratio, etc.)
- Additionally: `nominal_choice_ratio` (= r), `full_feasible_count` (= |E_full,p|, per-policy), `exposed_feasible_count` (= |C_p,r|, per-policy), `realized_feasible_choice_multiplier` (= |C_p,r|/k, per-policy)

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
| `n_drop_cap`, `n_drop_physical`, `n_drop_la` | Existing drop categories (unchanged from M4) |
| `syn_node_hours` | Admitted synthetic node-hours |
| `full_feasible_count_p10/p50/p90` | Per-policy distribution of |E_full,p| (feasible nodes before Gate F restriction) across jobs at this lambda |
| `exposed_feasible_count_p10/p50/p90` | Per-policy distribution of |C_p,r| (feasible nodes exposed to selector) |
| `realized_feasible_choice_multiplier_p10/p50/p90` | Per-policy distribution of |C_p,r|/k (true feasible-choice multiplier seen by the selector) |
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

**x-axis:** `nominal_choice_ratio` r (the manipulated variable), with r=1.0 at left and r=unrestricted at right. Label ticks with nominal r values. Do not label the axis as "realized feasible-choice ratio" or use `realized_feasible_choice_multiplier` as the primary axis; those are per-policy diagnostic observations, not the experimental treatment.

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
- Vertical dashed line at r = 1.0 with annotation "hard negative-control assertion (§4.6): all policies identical". As established in §4.6, at r = 1.0 all four policies select identical nodes throughout the replay (by induction); all five comparison curves must collapse to zero at r = 1.0. Any non-zero deviation at r = 1.0 is a hard assertion failure indicating an implementation bug, not a scientific finding.
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

**Test 3 — Single-node stability:** Given a fixed `full_eligible` set for event E, removing one node from `full_eligible` and recomputing leaves the relative hash-rank order of all remaining nodes unchanged.

**Test 4 — Prefix nesting (fixed E_full):** Given one fixed `full_eligible` set with `|full_eligible| = 20` and `k = 4`, verify that shortlists computed at increasing r from the same `full_eligible` are nested prefixes of the same hash ordering:
```
C_p_r(r=1.0)  ⊆  C_p_r(r=1.25)  ⊆  C_p_r(r=1.5)
              ⊆  C_p_r(r=2.0)   ⊆  C_p_r(r=4.0)
              ⊆  C_p_r(r=8.0)   ⊆  C_p_r(r=unrestricted)
```
by set containment. The same `full_eligible` must be passed at every ratio call. This verifies the mathematical prefix property, not that independently evolved ratio replays remain nested.

**Test 5 — Hash policy-neutrality:** The hash priority function takes no policy parameter. Given an identical `full_eligible` set and identical `(scenario_seed, event_uid)`, all four policies produce the same `ordered_p` ranking and the same `C_p_r`. Verify by passing the same `full_eligible` set to the shortlist construction for all four policies at a synthetic event and asserting `C_p_r` is byte-for-byte identical across policies.

**Test 6 — Global event_uid uniqueness:** Generate a scenario's complete workload (base + synthetic). Assert:
```python
assert len(set(all_event_uids)) == len(all_event_uids)
```
This catches duplicate base IDs, duplicate synthetic generation ordinals, and any base/synthetic collision in a single check. The `base:` / `syn:` prefix namespaces make inter-type collisions impossible by construction, but the assertion is required regardless.

---

## 14. Implementation checklist (pre-run)

- [ ] Unit tests 1–6 all pass (§13).
- [ ] Fixed-E_full prefix-nesting unit test (Test 4) passes. Runtime ratio replays are allowed to have different E_full,p sets after their states diverge; runtime nesting across separately evolved ratio replays is not asserted.
- [ ] r=1 inductive negative-control assertion verified on sc0–4: all four policies select identical node sets at every feasible event, maintain identical evolving replay state, produce identical lambda-row metrics and reconstructed crossings. All five comparison curves are zero at r=1. Any deviation is treated as an implementation bug (§4.6).
- [ ] At r=unrestricted, lambda rows for sc0–4 match M4 source files (metric-for-metric).
- [ ] At r=unrestricted, reconstructed crossings for sc0–4 match M4 v3 scenario_rows.
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
