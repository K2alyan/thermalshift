# Gate F Design: Dynamic Feasible-Choice Sensitivity

**Date:** 2026-09-30
**Amended:** 2026-09-30 — hash construction and event_uid frozen; unit tests specified
**Amended:** 2026-09-30 — §4.6 no-choice control corrected; generation_ordinal frozen; terminology clarified
**Amended:** 2026-09-30 — §4.1 external pool corrected (exogenous blockers only); §5 base-job placement corrected; §6 preflight strengthened
**Amended:** 2026-09-30 — drop-cause semantics frozen (E_full/E_r); terminology finalized; §8.2 priority description corrected; §11 r=1 annotation fixed; realized-choice diagnostics added.
**Amended:** 2026-09-30 — Estimand/intervention corrected. Intervention now follows M4 feasibility. Gate F restricts how many currently feasible nodes the selector may inspect, not external candidate visibility. Design frozen.
**Amended:** 2026-09-30 — Consistency cleanup only. §3 formula corrected to per-policy m_p,r; n_available removed. §4.2 nesting and cross-policy-identity bullets qualified. §4.4 nesting claim qualified (fixed E_full,p only). §8.2 CRN claim qualified. Tests 3–4 use full_eligible/E_full,p. §14 checklist: runtime nesting assertion removed.
**Amended:** 2026-09-30 — Pre-implementation inspection. M4 call graph confirmed (r1_m4_fair_baselines.py): look_ahead_safe() is allocation-level, post-selection, synthetic-only. E_full,p renamed A_full,p (pre-selector eligible set, not post-look-ahead). full_feasible_count renamed full_selector_eligible_count. Gate F wrapper order corrected to preserve post-selection look-ahead unchanged.
**Amended:** 2026-09-30 — Base-job Stage 1 path inspected and documented. bg_busy source differs by job type (fleet-wide for synthetic, per-job for base). Base jobs fall back to uncapped set when capped set < k (no drop); synthetic jobs drop. Marginal-mode base jobs bypass selector; Gate F does not apply. exposed_feasible_count -> exposed_selector_eligible_count; realized_feasible_choice_multiplier -> realized_selector_choice_multiplier.
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

For policy p and a job requiring *k* cohort nodes, the Gate F shortlist is drawn from A_full,p (§4.0, §4.1) and has size:

```
m_p,r = min( ceil(r × k), |A_full,p| )
```

`A_full,p` is the per-policy pre-selector eligible set (M4 `avail_capped_set` — see §4.0). The shortlist and its size are therefore policy-specific once replay states diverge.

**Frozen shortlist definitions:**
- `C_p,r` = first `m_p,r` nodes from hash-ranked A_full,p (§4.2, §4.4)
- `C_p,unrestricted` = A_full,p (no prefix restriction; full pre-selector eligible set exposed)

`unrestricted` exposes the full A_full,p to the selector. Combined with the unchanged post-selection look-ahead check, this reproduces the M4 unrestricted replay exactly and is the preflight gate (§6).

**Terminology (frozen):**

| Term | Symbol | Definition |
|------|--------|-----------|
| *k* | — | Job cohort node count (nodes required) |
| `nominal_choice_ratio` | r | The experimental treatment variable. Set by the design; identical across all policies. |
| `full_selector_eligible_count` | \|A_full,p\| | Per-policy: number of pre-selector eligible nodes (M4 avail_capped_set — nodes passing the node-level occupancy/cap filter, before policy selection and before look-ahead). Policy-specific; can differ across policies at the same event once replay states diverge. |
| `exposed_selector_eligible_count` | \|C_p,r\| | Per-policy: shortlist size after Gate F restriction. = min(ceil(r × k), \|A_full,p\|). Always ≥ k when \|A_full,p\| ≥ k and r ≥ 1. These are pre-selector-eligible candidates; allocation-level look-ahead runs after selection. |
| `realized_selector_choice_multiplier` | \|C_p,r\| / k | Per-policy: the number of pre-selector-eligible candidates exposed to the selector, as a multiple of the job size. This is what the estimand measures. |

The primary x-axis is `nominal_choice_ratio` r (the manipulated variable). Because Gate F intervenes after the M4 node-level eligibility filter but before policy selection and before look-ahead, `realized_selector_choice_multiplier` records how many pre-selector-eligible candidates the selector inspected per required node, with look-ahead running unchanged on the resulting allocation.

---

## 4. Candidate-set construction

### 4.0 M4 placement call graph: pre-implementation inspection

**File:** `artifacts/revision1/analysis/r1_m4_fair_baselines.py`

The M4 per-event loop (`capacity_replay_m4()`) has a strict two-stage structure:

**Stage 1 — Node-level eligibility filter (pre-selector, job-type-specific):**

The `bg_busy` source and the behavior when `n_avail_capped < k` differ by job type.

*Synthetic jobs (is_syn=True):*
```python
bg_busy          = bg_busy_at_ms(t_j_ms)                          # line 923 — fleet-wide bg conflicts
avail_capped_set = available_set.difference(bg_busy)               # line 928
if n_avail_capped < k:                                             # line 932
    # check avail_unc_set; drop n_drop_cap or n_drop_phys; continue
available = list(avail_capped_set)                                 # line 949 — A_full,p for synthetic
```
Synthetic jobs drop (`n_drop_cap` or `n_drop_phys`) if the capped set is insufficient; there is no fallback.

*Base jobs, full-replacement mode (is_syn=False, not marginal):*
```python
bg_busy          = bg_busy_per_job.get(parent_jid, frozenset())   # line 925 — per-job bg conflicts
avail_capped_set = available_set.difference(bg_busy)               # line 928 (shared)
if n_avail_capped >= k:
    available = list(avail_capped_set)                             # line 992 — capped set
else:
    avail_unc_set = eligible_set.difference(cf_busy_active, bg_busy)
    available = list(avail_unc_set)                                # line 995 — uncapped fallback, no drop
```
Base jobs fall back to the uncapped eligible set when the capped set is insufficient; there is no drop and no `n_drop_cap` increment.

*Base jobs, marginal mode (is_syn=False, marginal=True):*
Uses historical node assignment directly; skips the policy selector entirely (`continue` at line 988). Gate F does not apply to marginal-mode base jobs.

**A_full,p is therefore job-type-specific.** The Gate F wrapper must read the `available` list from the frozen M4 branch actually used for that job type — do not force all events through the synthetic branch.

**Stage 2 — Policy selection (on A_full,p):**
```python
selected = select_fp(available, k)     # line 1003 — or select_loc / select_random / select_fp_spread
```
The policy selector receives `available` (= A_full,p) and returns exactly k nodes.

**Stage 3 — Allocation-level admission check (post-selection, synthetic jobs only):**
```python
if is_syn and selected:                                                    # line 1013
    if not look_ahead_safe(selected, t_j_ms, t_e_ms, cf_busy_ms):        # line 1014
        n_drop_la += 1
        continue
```
`look_ahead_safe()` (line 590) receives the **complete k-node selected set** (`s_nodes = frozenset(selected_nodes)`, line 595) and evaluates whether admitting all k nodes simultaneously leaves sufficient future capacity for upcoming base jobs. It is not a per-node filter; it is an atomic check on the k-node allocation. Base jobs do not call `look_ahead_safe` regardless of mode.

**Gate F correct wrapper order:**
```
Stage 1:   A_full,p = job-type-specific M4 candidate list (§4.1)
           synthetic: drop if capped set < k (n_drop_cap / n_drop_phys)
           base (full-replacement): uncapped fallback if capped set < k; no drop
           base (marginal): historical assignment; Gate F does not apply
Stage 1½:  BLAKE2b hash-rank A_full,p; take prefix C_p,r of size m_p,r  (Gate F — §4.2, §4.4)
Stage 2:   selected = frozen_policy_selector(C_p_r, k, policy=p)         (policy — §4.5)
Stage 3:   if is_syn: look_ahead_safe(selected, ...)  →  admit or n_drop_la
           base jobs: no look_ahead_safe; commit directly
```

**What A_full,p is NOT:** nodes in `A_full,p` have passed only the node-level occupancy/cap filter. `look_ahead_safe` evaluates the entire k-node allocation after selection. A node may be in A_full,p and still contribute to a look-ahead failure when combined with specific other nodes. Gate F restricts how many pre-selector-eligible nodes the selector may inspect; look-ahead runs unchanged on whatever k nodes the selector chooses.

**Do not:** call `frozen_m4_candidate_set()` as if it were a single reusable function — it does not exist. Replicate the inline Stage 1 filter exactly, preserving the job-type-specific branch. **Do not** move `look_ahead_safe` upstream.

### 4.1 Pre-selector eligibility step (per policy)

For each scheduling event and each policy, replicate the exact job-type-specific M4 Stage 1 filter (§4.0) to build `A_full,p`. The construction is not a single helper call; it is the M4 inline candidate-list branch for that job type:

- **Synthetic job:** `A_full,p = avail_capped_set` (capped, fleet-wide bg_busy). If n_avail_capped < k: existing drop (`n_drop_cap` / `n_drop_phys`); Gate F does not apply.
- **Base job, full-replacement mode:** `A_full,p = avail_capped_set` if n_avail_capped ≥ k; else `A_full,p = avail_unc_set` (uncapped fallback, no drop).
- **Base job, marginal mode:** historical assignment; Gate F does not apply.

Do not reimplement from a new formula. Replicate the frozen M4 v3 inline branch exactly.

`A_full,p` is **per-policy** and will diverge across policies once their replay states differ. This is expected.

**Full per-event pipeline (Gate F wrapper):**

```
Stage 1:   A_full,p = job-type-specific M4 candidate list (see §4.0 for branches)
Stage 1½:  BLAKE2b hash-rank A_full,p  (§4.2)
           C_p,r = first min(ceil(r×k), |A_full,p|) nodes  (§4.4)
           (only reached if |A_full,p| >= k, else existing M4 drop / marginal skip)
Stage 2:   selected = frozen_policy_selector(C_p_r, k, policy=p)  (§4.5)
Stage 3:   if is_syn: look_ahead_safe(selected, ...)               (§4.5, unchanged)
           base jobs: commit directly, no look_ahead_safe
```

At r ≥ 1 and |A_full,p| ≥ k, C_p,r always contains at least k pre-selector-eligible nodes, so Gate F Stage 1½ never prevents Stage 2 from receiving a full shortlist.

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
- For a fixed A_full,p at a given event, longer-prefix shortlists are nested: `C_p,{1.0} ⊆ C_p,{1.25} ⊆ ... ⊆ A_full,p`. This prefix property holds within one replay at a fixed event state; it does not extend across independently evolved ratio replays where earlier placements may have changed A_full,p.
- If two policies have identical A_full sets for an event (as they do at r=1 before any state divergence), the policy-neutral hash produces identical rankings and identical shortlists at the same r. Once policy states diverge, A_full,p may differ and shortlist identities may therefore differ across policies.
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

Called only when |A_full,p| ≥ k (§4.1). Applies to the per-policy pre-selector eligible set.

```python
import math

# full_eligible: A_full,p from M4 node-level eligibility filter (§4.0, §4.1)
# Nodes pass occupancy/cap filter. Look-ahead runs after selection — not here.

ordered_p = sorted(
    full_eligible,
    key=lambda h: choice_priority(scenario_seed, event_uid, h),
)

m_p_r = min(len(ordered_p), math.ceil(r * k))
# Since len(ordered_p) = |A_full,p| >= k and r >= 1.0, m_p_r >= k always.

C_p_r = ordered_p[:m_p_r]  # Gate F shortlist: m_p_r pre-selector-eligible nodes

selected = frozen_selector(C_p_r, k, policy=p)
# look_ahead_safe(selected, ...) runs after this in Stage 3 (§4.5)
```

**Prefix nesting (fixed A_full,p):** for a fixed A_full,p at a given event, shortlists at increasing r are nested prefixes of the same hash ordering:

```
C_p,{1.0} ⊆ C_p,{1.25} ⊆ C_p,{1.5} ⊆ C_p,{2.0} ⊆ C_p,{4.0} ⊆ C_p,{8.0} ⊆ C_p,{unr}
```

This property holds mathematically for any fixed A_full,p. Across independently evolved ratio replays, earlier placements under different r values change occupancy state and therefore A_full,p at subsequent events; runtime shortlists from separate ratio replays are not required to be nested.

**Candidate identities may differ across policies** at the same event once replay states diverge (because A_full,p is policy-specific). This is correct behavior. Fairness is provided by identical workload and residual draws, identical nominal r, and the same policy-blind hash function applied to each policy's own eligible set.

### 4.5 Frozen policy selector

Every node in C_p,r has passed the M4 node-level eligibility filter (§4.0, §4.1). The frozen policy selector receives C_p,r and chooses k nodes:

| Policy | Selector rule |
|--------|--------------|
| `full_random` | uniform random draw of k from C_p,r |
| `full_fp` | lowest FA_2024 first; take top k |
| `full_loc` | lowest position-mean FA (chassis/slot/board/node_pos); take top k |
| `full_fp_spread` | FP-spread rule; take k |

Selector logic is identical to M4 v3 — frozen, no tuning.

Since |C_p,r| ≥ k always holds when |A_full,p| ≥ k and r ≥ 1, the selector always has at least k candidates.

**Stage 3 — Post-selection look-ahead (unchanged from M4):** after the selector returns `selected`, run `look_ahead_safe(selected, t_j_ms, t_e_ms, cf_busy_ms)` exactly as in M4 (line 1014, synthetic jobs only). Admit on pass; increment `n_drop_la` and continue on failure. Do not move this check to shortlist construction or to the node-level eligibility filter.

Gate F restricts which pre-selector-eligible candidates the selector may inspect, but it does not alter what happens to the selected allocation. The look-ahead outcome may vary across r values because different C_p,r shortlists lead to different selections and thus different look-ahead inputs; this is the intended sensitivity signal.

**Shortlist construction happens fresh at every job arrival** from the current per-policy eligible set. Nodes are never permanently removed for the duration of a scenario.

### 4.6 r=1 negative control (strong)

At r = 1.0 and |A_full,p| ≥ k for all policies: each policy's Gate F shortlist C_p,{1.0} contains exactly k pre-selector-eligible nodes. The selector has no choice discretion — it must place exactly those k nodes. Since A_full,p is built from identical state and all four policies start from identical state before any placements, the following holds **by induction**:

**Base case:** at the first job event, all four policies have identical replay state. Their A_full,p sets are therefore identical. All four receive the same k-node C_p,{1.0} and make the same k placements.

**Inductive step:** if all four policies have identical replay state before event t, they produce identical A_full,p at event t, receive the same k-node shortlist, make the same k placements, and `look_ahead_safe(selected, ...)` evaluates the same k-node allocation for all four — producing the same admit/drop outcome. All four arrive at identical state after event t.

**Conclusion:** throughout an r = 1.0 replay, as long as each job is pre-selector eligible (|A_full,p| ≥ k), all four policies select identical nodes at every event, their replay states evolve identically, and all post-selection outcomes (including look-ahead) are identical.

**Assert on sc0–4 at r = 1.0:**
- Identical selected node sets across all four policies at every eligible event.
- Identical look-ahead outcomes (admit / n_drop_la) across policies at every event.
- Identical evolving synthetic occupancy and utilization state across policies.
- Identical raw lambda-row metrics (capacity_unlock_pct, B/B_ref, S/S_ref, B_cab, drop counts).
- Identical reconstructed crossings.

If the inductive argument holds, this is a hard assertion, not an empirical check. A violation indicates an implementation bug (state divergence before the expected event, or policy-specific selection when |C_p,r| = k).

**Unrestricted is the opposite endpoint:** C_p,{unr} = A_full,p — full pre-selector eligible set exposed to the selector — which, combined with the unchanged look-ahead check, must reproduce M4 v3 exactly.

---

## 5. QoS and feasibility invariants

### Preserved invariant (identical to M4 full-policy replay)

Historical base jobs retain their original start times, durations, and requested cohort-node counts, but their **cohort-node placements are counterfactually replayed under each policy**, exactly as in M4. No base job may be delayed or under-served. The existing M4 look-ahead/QoS invariant is preserved exactly.

This is the M4 **full-policy** replay model. It is not the marginal-policy model in which base jobs keep their historical node assignments. If implemented as marginal-policy, the unrestricted preflight cannot reproduce M4 v3.

### Drop classification (Gate F)

Existing M4 drop categories (`n_drop_cap`, `n_drop_physical`, `n_drop_la`) are preserved and retain their M4 semantics.

**Gate F introduces no new drop categories.**

Gate F inserts at Stage 1½ (§4.0): between the M4 node-level eligibility filter and the policy selector. Every node in C_p,r has passed the node-level occupancy/cap filter. Because |C_p,r| ≥ k whenever |A_full,p| ≥ k and r ≥ 1.0, the selector always receives at least k pre-selector-eligible candidates and Gate F cannot prevent Stage 2 or Stage 3 from running.

If |A_full,p| < k at any policy and event, that is an existing M4 failure condition (`n_drop_cap` / `n_drop_phys`), not a Gate F failure. Apply the existing M4 drop semantics exactly and record under the existing M4 category. Report `full_selector_eligible_count` (|A_full,p|) as a per-event diagnostic field to confirm that shortfall is not Gate F-caused.

`n_drop_la` continues to fire post-selection on the look-ahead check, exactly as in M4. Gate F does not alter this; it only changes which k-node allocation the selector produces.

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

For each scenario (sc), for each lambda, for each ratio r: run all four policies with the same nominal choice ratio r. Each (sc, lambda, r, policy) produces one row of metrics. Each policy operates on its own A_full,p (which may diverge across policies once occupancy states differ), but applies the same hash function and the same r to construct C_p,r from its own eligible set.

The node priority for each (event, hostname) pair is fixed by `(scenario_seed, event_uid, hostname)` — it does not depend on lambda or choice ratio. Within a single replay run, the hash ordering at any event is stable across lambda values. However, because different r values lead to different placements at earlier events, A_full,p at a later event may differ across independently evolved ratio replays; runtime shortlists from separate ratio replays are not guaranteed to be nested. The priority function nonetheless provides common-random-number structure within each replay by keeping node ranks stable across lambda values.

### 8.3 Output structure

Per scenario, per ratio, per policy, per lambda:
- All fields in M4 lambda_rows (capacity_unlock_pct, B_primary_ratio, etc.)
- Additionally: `nominal_choice_ratio` (= r), `full_selector_eligible_count` (= |A_full,p|, per-policy), `exposed_selector_eligible_count` (= |C_p,r|, per-policy), `realized_selector_choice_multiplier` (= |C_p,r|/k, per-policy)

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
| `full_selector_eligible_count_p10/p50/p90` | Per-policy distribution of |A_full,p| (pre-selector eligible nodes before Gate F shortlist, not yet look-ahead-admitted) across jobs at this lambda |
| `exposed_selector_eligible_count_p10/p50/p90` | Per-policy distribution of |C_p,r| (pre-selector-eligible nodes in the Gate F shortlist; look-ahead runs after selection) |
| `realized_selector_choice_multiplier_p10/p50/p90` | Per-policy distribution of |C_p,r|/k (pre-selector-eligible candidates per required node, as seen by the selector) |
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

**x-axis:** `nominal_choice_ratio` r (the manipulated variable), with r=1.0 at left and r=unrestricted at right. Label ticks with nominal r values. Do not label the axis as "realized feasible-choice ratio" or use `realized_selector_choice_multiplier` as the primary axis; those are per-policy diagnostic observations, not the experimental treatment.

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

**Test 4 — Prefix nesting (fixed A_full):** Given one fixed `full_eligible` set with `|full_eligible| = 20` and `k = 4`, verify that shortlists computed at increasing r from the same `full_eligible` are nested prefixes of the same hash ordering:
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
- [ ] Fixed-A_full prefix-nesting unit test (Test 4) passes. Runtime ratio replays are allowed to have different A_full,p sets after their states diverge; runtime nesting across separately evolved ratio replays is not asserted.
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
