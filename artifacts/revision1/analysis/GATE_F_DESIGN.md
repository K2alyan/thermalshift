# Gate F Design: Dynamic Feasible-Choice Sensitivity

**Date:** 2026-09-30
**Status:** Design — requires sign-off before implementation

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

### 4.2 Pseudorandom priority (deterministic, policy-neutral)

Assign every node a deterministic priority number for each job arrival:

```
priority(node, job) = hash(scenario_seed ‖ job_event_id ‖ hostname)
```

The hash must be:
- **Deterministic**: same inputs always produce same priority.
- **Independent of all policy signals**: no thermal fingerprint, no location, no power, no current utilization, no residual, no future workload.
- **Consistent across ratios**: the same priority ordering is used at every ratio for the same job arrival. This enforces nesting.

Implementation note: a seeded PRG (e.g., `numpy.random.default_rng(hash(scenario_seed, event_id))`) sampling one value per hostname, where the hash is computed before drawing, is acceptable. Document the exact hash construction in the implementation.

### 4.3 Nested shortlists

Sort the policy-neutral available pool by ascending priority. The external shortlist for ratio r is the first m = min(ceil(r × k), n_available) nodes in this order.

By construction:
```
C_{1.0} ⊆ C_{1.25} ⊆ C_{1.5} ⊆ C_{2.0} ⊆ C_{4.0} ⊆ C_{8.0} ⊆ C_{unrestricted}
```

The nesting is exact (not approximate) because priorities are fixed per event.

### 4.4 Per-policy endogenous filtering and selection

Each policy receives the **same external shortlist** for ratio r at each job arrival. It then:

1. Intersects the shortlist with its own **endogenous eligibility** — utilization cap, current synthetic occupancy, any policy-specific state — to form its **eligible set**.
2. Applies its frozen selector (random / lowest-FP / lowest-location-score / FP-spread rule) to the eligible set.
3. If the eligible set has fewer than *k* nodes: the job is recorded as a **choice-constrained drop** and not admitted.

**Critical:** shortlist construction happens fresh at every job arrival from the current policy-neutral pool. Nodes are never permanently removed from consideration for the duration of a scenario as in the M4 static-pool test.

### 4.5 No-choice negative control

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

## 13. Implementation checklist (pre-run)

- [ ] Pseudorandom priority hash specified and documented (exact construction, no policy signals).
- [ ] Nesting property verified for sc0 at lambda=1.06: `C_{1.0} ⊆ C_{1.25} ⊆ ... ⊆ C_unrestricted`.
- [ ] No-choice control assertion verified: at r=1.0, all four policies select same nodes.
- [ ] At r=unrestricted, lambda rows for sc0–4 match M4 source files (metric-for-metric).
- [ ] At r=unrestricted, reconstructed crossings for sc0–4 match M4 v3 scenario_rows.
- [ ] 0 choice-constrained drops at r=unrestricted.
- [ ] 0 C_lower > C_upper post-reconstruction.
- [ ] 0 unexpected right-censored crossings.
- [ ] Job-size quartile boundaries computed and frozen before held-out run.
- [ ] Git SHA committed before sc5–29 execution.
- [ ] No policy or ratio changes after held-out run begins.

---

## 14. Output files (to be produced)

| File | Contents |
|------|----------|
| `gate_f_lambda_rows.json` | Full lambda_rows for all (sc, ratio, policy, lambda) |
| `gate_f_crossings.json` | Reconstructed crossings for all (sc, ratio, policy) |
| `gate_f_comparisons.json` | Paired comparison tables for all ratios and pairs |
| `gate_f_preflight.json` | Preflight check record (sc0–4 vs M4 v3) |
| `gate_f_fig_delta_lo.pdf/.png` | Primary figure |

---

## 15. Relationship to paper framing

M4 finding (frozen): *"Topology-aware thermal scheduling clearly improves over Random. FP-spread improves over plain FP. However, FP-spread and a strong location-only baseline are not consistently distinguishable."*

Gate F will refine this into one of:

- **Spatial signal dominates**: location captures most of the benefit at all choice ratios → ThermalShift improves over Random, but much of its value is topology-recoverable.
- **Fingerprint adds operational value**: FP-spread separates from Location when choice is constrained → the learned fingerprint encodes actionable thermal heterogeneity beyond physical placement.
- **Robust equivalence**: all thermal-aware policies outperform Random similarly regardless of choice ratio → the finding is robust to choice constraints, but the source of FP-spread's Location equivalence is still unresolved.

All three are publishable. The experiment is designed to distinguish them.
