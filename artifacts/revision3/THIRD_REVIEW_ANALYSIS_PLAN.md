# Round-3 Analysis Plan v2.0: Reviewer-Requested Robustness and Exploratory Analyses

**Version:** 2.0 (supersedes v1.0 committed at 17c2e91)

**Exposure status:** post-exposure — all Round-3 work was designed and will be executed after the sc30–sc54 primary challenge results (evidence-frozen at commit f1c78a3) were observed.

**Critical invariant:** The frozen sc30–sc54 challenge (pre-specified at commit 5733b73, evidence-frozen at commit f1c78a3) is unchanged and remains the original pre-specified result. Round-3 results are post-exposure reviewer-requested additions that do not supersede or modify it.

**Plan freeze:** This document and `third_review_plan.json` must be committed before any new policy simulation is run.

**Machine-readable companion:** `artifacts/revision3/third_review_plan.json`

---

## A. Plan Documents

This file (`THIRD_REVIEW_ANALYSIS_PLAN.md`) and `third_review_plan.json` constitute the frozen Round-3 plan. All analysis definitions, seed derivations, output filenames, interpretation rules, floor handling, cabinet-reference definitions, threshold grid, LOO Position fallback hierarchy, late-cabinet exclusion set, and calendar-split boundary rule are frozen here before any new simulation.

---

## B. Existing-Output Diagnostics (no new simulation)

**Script:** `artifacts/revision3/analyze_existing_round3_requests.py`
**Outputs:** `existing_round3_diagnostics.json`, `existing_round3_diagnostics.md`
**Source data:** `artifacts/revision2/challenge_analysis.json` and `artifacts/revision2/results/gate_f_sc30-54_all_r2challenge_merged.json` (frozen sc30–sc54 outputs only — no new simulation)

### B1. Absolute Capacity Levels at r=1.25

For each of the 7 policies, extract from per-scenario crossing data (merged file) and `challenge_analysis.json policy_summaries`:

| Field | Definition |
|---|---|
| `median_C_lower_pct` | Median lower-bracket capacity across 25 scenarios (%) |
| `median_C_upper_pct` | Median upper-bracket capacity across 25 scenarios (%) |
| `median_bracket_width_excl_infeasible` | Median of `C_upper − C_lower` excluding [0,0] cells |
| `n_base_infeasible` | Scenarios with `crossing.status == "left_boundary"` ([0,0]) |
| `n_floor_at_zero` | Scenarios with `status == "exact_bracket"` AND `C_lower_pct == 0`, `C_upper_pct > 0` |
| `n_right_censored` | Scenarios with `right_censored == True` |

**Verified floor counts from frozen sc30–sc54 data:**

| Policy | n_base_infeasible | n_floor_at_zero | n_total_C_lower_0 |
|---|---|---|---|
| full_fp | 0 | 0 | 0 |
| full_random | 9 | 3 | 12 |
| full_fp_spread | 0 | 0 | 0 |
| random_spread | 10 | 1 | 11 |
| fp_withincab_placebo | 2 | 0 | 2 |
| fp_global_placebo | 7 | 1 | 8 |
| position_template | 0 | 0 | 0 |

**For full_random base-infeasible scenarios:** first_binding_constraint at left_boundary: B_ratio=8, S_ratio=1.

**Floor/left-censor rule (frozen):**
- **Base-infeasible** `[0, 0]` (`status=="left_boundary"`): report as-is; exclude from bracket-width summaries; count separately as `n_base_infeasible`.
- **Floor-at-zero** `C_lower=0`, `C_upper>0` (`status=="exact_bracket"`): include in delta_lo as `delta_lo = 0 − C_upper_B` (conservative, correctly negative or zero); count separately as `n_floor_at_zero`.
- Bracket-width summaries (`median`) exclude `[0, 0]` cells only. `n_base_infeasible` reported alongside.

### B2. Binding-Constraint Diagnostic

Label: `legacy_cabinet_reference_binding_diagnostic` — the cabinet reference is the legacy job-contribution P99 (event-weighted) from `cabinet_power_envelopes.json`.

For each comparison at r=1.25, report:
- n_definitely_A, n_indistinguishable, n_definitely_B
- `n_both_base_infeasible`: scenarios where BOTH policies are left_boundary (neither can schedule synthetic jobs at this ratio)

**Verified n_both_base_infeasible from frozen data:**

| Comparison | n_both_base_infeasible | Note |
|---|---|---|
| FP_vs_Random | 0 | FP never infeasible at r=1.25 |
| FP_vs_WithinCabPlacebo | 0 | |
| FP_vs_GlobalPlacebo | 0 | |
| RandomSpread_vs_Random | 6 | Not measured zero-difference ties |
| FPSpread_vs_RandomSpread | 0 | |
| FPSpread_vs_FP | 0 | |
| FP_vs_PositionTemplate | 0 | |
| FPSpread_vs_PositionTemplate | 0 | |

**First-binding constraint at crossing for non-infeasible scenarios:**
- full_fp: B_cab_ratio=23, B_ratio=2
- full_random (non-infeasible): B_ratio=11, B_cab_ratio=4, S_ratio=1

### B3. FPSpread vs FP Both Directions

Report `FPSpread_vs_FP` results from `challenge_analysis.json` at all ratios [1.25, 1.5, 2.0, 4.0, 8.0, unrestricted] with bootstrap 95% CI (n_bootstrap=5000, seed=9999). Report both the stored direction and the reverse implied by sign flip. Document the crossover point (FPSpread underperforms at constrained ratios, outperforms at large ratios).

**Pre-specified crossover:** FPSpread underperforms FP at r=1.25–2.0; crossover at r≥8.0 or unrestricted. This was pre-specified before sc30–sc54 execution and is replicated exactly.

### B4. Sign Tests with Holm-Bonferroni Correction

For each of the 8 pre-specified comparisons at r=1.25:
- **Test:** Two-sided exact binomial sign test on **decisive scenarios only**.
  - H₀: P(A better | decisive) = 0.5
  - N = n_definitely_A + n_definitely_B (indistinguishable excluded from test N)
  - p_two_sided = 2 × min(P(X ≤ min(n_A, n_B)), P(X ≥ max(n_A, n_B))) under Binom(N, 0.5), capped at 1.0
- **Correction:** Holm-Bonferroni over 8 comparisons.
- Source: `verdicts` arrays in `challenge_analysis.json results[comparison]["ratios"]["1.25"]`.

**Note on FP_vs_PositionTemplate:** The pre-specified interpretation of "not statistically separated" is based on the bootstrap CI on delta_lo spanning zero (CI [−0.82, +1.50] pp). The sign test is an additional exploratory measure. These are complementary; the delta_lo CI result stands as the primary characterization.

### B5. Exploratory Decomposition Contrasts

| Contrast | Computation | Interpretation |
|---|---|---|
| Global-score advantage | FP_vs_GlobalPlacebo median delta_lo | Knowing global thermal ordering vs random permutation |
| Node-vs-cabinet specificity | FP_vs_WithinCabPlacebo median delta_lo | Node-level identity beyond cabinet composition |
| Cabinet-composition advantage | FP_vs_Random − FP_vs_GlobalPlacebo (algebraic) | Advantage from cabinet-level thermal composition (approximate) |
| Spreading cost at r=1.25 | FPSpread_vs_FP median delta_lo (negative = FPSpread loses) | Cost of cabinet-spreading at constrained ratios |

Label: exploratory — not preregistered. Medians only; bootstrap CIs from stored values.

### B6. Order-Statistic Median Intervals (n=25)

For each comparison at r=1.25, compute the exact order-statistic 95% CI on the median of `delta_lo_per_scenario` (n=25): use OS₈ and OS₁₈ (k_lo=8, k_hi=18; actual coverage ≈ 0.9567, Conover 1999). Report alongside bootstrap CI as a non-parametric confirmation.

### B7. sc5–sc29 Development-Era Evaluation

Source: `artifacts/revision1/results/gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json`

Label: **"development-era evaluation on the same underlying base dataset"** — NOT a held-out evaluation. Scenarios sc5–sc29 were run during revision1 development (before the sc30–sc54 held-out challenge was designed). They share the same base job set. Report bootstrap analysis at r=1.25 for revision1 comparisons (FP_vs_Random, FP_vs_Loc, FPSpread_vs_FP). This is qualitative context only; revision1 uses different selectors from revision2.

---

## C. Cabinet Reference Audit

**Outputs:** `artifacts/revision3/CABINET_REFERENCE_AUDIT.md`, `cabinet_reference_audit.json`

**Legacy formula (from `cabinet_power_envelopes.json`):**
```
P_cab_j = (mean_power_j / node_count_j) × n_nodes_in_cabinet_j
```
Applied to all 152,400 jobs with reported `mean_power > 0`. Per-cabinet P99 taken over all qualifying job contributions.

**Weighting: EVENT-WEIGHTED (job-weighted), NOT time-weighted.** Each job contributes one observation regardless of job duration. P99 is computed over the count of qualifying job observations per cabinet.

**Key distinction (verbatim, to appear in all cabinet-reference outputs):**
> The legacy P99 reference and the replayed concurrent cabinet quantity are not the same statistical object. The legacy reference is a marginal P99 over individual job contributions — each job contributes one observation, so it is EVENT-WEIGHTED (job-weighted), not time-weighted. The replayed concurrent quantity P_c_total(t) = sum_j P_job,c(t) over overlapping jobs is a time-varying sum; taking its P99 over time gives a TIME-WEIGHTED estimator of the concurrent power ceiling. These are different estimators and will generally differ. The legacy estimator is used in all sc0–sc54 results.

**Fleet summary:** fleet median P99 = 92.487 kW; n_cabinets = 77.

**Late-cabinet P99:** 2600 = 71.171 kW, 2601 = 74.009 kW, 2602 = 68.741 kW (all below fleet median).

---

## D. Cabinet Support Audit

**Script:** `artifacts/revision3/cabinet_support_audit.py`
**Output:** `artifacts/revision3/cabinet_support_audit.json`

Determine the exact support over which historical concurrent cabinet power can be reconstructed:
- All collection dates with usable power telemetry
- Contiguous blocks (hours)
- Total support hours per cabinet
- Distribution of concurrent job counts and concurrent node counts per 15-min or hourly bin
- Fraction of bins with ≥1 concurrent job across all 77 cabinets

**Phrase required in all outputs:** "observed reconstructed concurrent cabinet power"

---

## E. Legacy Exceedance Fraction

Using support from D, for each cabinet:
```
legacy_exceedance_fraction_i = (hours where P_c_total_reconstructed_i(t) > P99_legacy_i) / support_hours_i
```

Report: per-cabinet, aggregate (fleet-level), median, IQR, p90, max, min. Diagnostic only — not a feasibility criterion.

**E1 Cabinet-Scale Behavior (B_cab approximate hours):**

`CAB_SCALE ∈ {0.90, 0.95, 1.00, 1.05, 1.10}` multiplies each cabinet's P99 uniformly. Both the counterfactual exposure envelope and the historical B_cab denominator scale proportionally. Approximate B_cab hours (from `sensitivity_cabinet_scale.json`) at each scale:

| CAB_SCALE | Approx B_cab denominator (hours) |
|---|---|
| 0.90 | 89,264 |
| 0.95 | 77,950 |
| 1.00 | 67,918 |
| 1.05 | 58,851 |
| 1.10 | 50,288 |

Label: "cabinet-reference scale sensitivity" — E1 tests uniform mis-estimation of cabinet P99 ceiling, not T_thr or physical power budget. E1 is NOT equivalent to T_thr sensitivity.

---

## F. Corrected Cabinet Reference Definitions

Three modes frozen here; no policy simulations until D is complete and Q equivalence check passes.

**F1 — legacy_job_contribution_p99 (current):**
P99 of per-job cabinet power contributions over 152,400 jobs (EVENT-WEIGHTED). Source: `cabinet_power_envelopes.json`. Used in all sc0–sc54.

**F2 — corrected_timeweighted_total_p99 (PRIMARY corrected mode):**
P99 of P_c_total(t) = sum_j P_job,c(t) over the historical support period (from D), computed using uniform node-power approximation applied simultaneously across all overlapping jobs. TIME-WEIGHTED.

**F3 — corrected_eventweighted_total_p99 (SENSITIVITY):**
P99 of P_c_total(t) at job-start-event timestamps (one sample per job start event). Alternative to F2.

**Event set:** Freeze the set of support bins (for F2) and job-start events (for F3) BEFORE implementing the corrected-mode runner. No post-implementation changes to the event set.

---

## G. S_cab Severity Diagnostic

Prepare code (diagnostic only — NOT an additional feasibility constraint):
```
S_cab_kWh_i = sum_{t in bins} max(0, P_c_total_reconstructed_i(t) − P_reference_i) × bin_duration_h
```

Report: aggregate S_cab_kWh across fleet, per-cabinet distribution, fraction of cabinets with S_cab_kWh > 0.

**S_cab is a secondary diagnostic only.** It does NOT enter the capacity-crossing feasibility check as an additional constraint.

---

## H. Concurrent Power Validation

**Script:** `artifacts/revision3/validate_concurrent_cabinet_power.py`

Validate the concurrent cabinet power reconstruction by filtering to scenarios where all concurrent jobs have complete usable telemetry (no missing nodes). Compare reconstructed concurrent cabinet power against individual job-level approximations as a cross-check.

---

## I. Legacy-vs-Corrected Reporting Rule (verbatim freeze)

> The legacy result (F1, sc0–sc54) remains the frozen pre-specified primary result. The corrected-mode result (F2 or F3) is a post-exposure reviewer-requested robustness check using the same pre-specified protocol structure but a different cabinet reference definition. Use the corrected reference (F2) as the reported result for all Round-3 new simulations regardless of whether it agrees with or differs from F1. If the corrected result changes any comparison verdict direction from the legacy result, BOTH results must be reported and the discrepancy is a mandatory disclosure — the abstract must contain an explicit limitation statement noting that the choice of cabinet reference definition affects the result direction.

---

## J. E1 Cabinet-Scale Behavior Documentation

Exact E1 behavior:
- `CAB_SCALE ∈ {0.90, 0.95, 1.00, 1.05, 1.10}` multiplies each cabinet's P99 uniformly.
- The historical `B_cab` denominator at each scale scales proportionally (see E1 table above).
- E1 tests sensitivity to uniform mis-estimation of cabinet capacity, not to a fixed physical budget.
- E1 is **not** equivalent to T_thr sensitivity.
- E1 is labeled "cabinet-reference scale sensitivity" in all outputs.

---

## K. Threshold Population Audit

**Output:** `artifacts/revision3/threshold_population_audit.json`
**Source:** `artifacts/revision1/results/m4_threshold_audit.json`

| Population | N jobs | p90 (°C) | p95 (°C) | p99 (°C) |
|---|---|---|---|---|
| Nominal pre-2025 | 3,945 | — | — | — |
| Contributing (≥1 fp node, ≥8 GCD, ≥5 timestamps) | 3,940 | 61.875 | 63.625 | 66.6625 |
| 462-job training subset (LOO beta) | 462 | 61.801 | 63.625 | 66.264 |

**Frozen primary threshold grid:** p90 = 61.875°C, p95 = 63.625°C (primary T_thr), p99 = 66.6625°C.
**Source population:** full_population (n=3,940).

**Threshold consistency:** Full-population p95 = 63.625°C = subset p95 = 63.625°C (delta = 0.000°C). Difference < 0.5°C: subset threshold is a reliable estimate of the full-population threshold.

**Exact 5 excluded job IDs:** Status PENDING — to be extracted by diffing the 3,945 nominal job IDs against the 3,940 contributing job IDs in the thermal model calibration scripts. Exclusion reason: fails the criterion "at least one fp node with ≥8 GCD channels and ≥5 valid T_p95 timestamps."

**Legacy T_thr secondary:** 60.602770562770566°C (frozen in BETA_F calibration; provenance to be confirmed by reading calibration script).

**Floor rule with exact_bracket_at_floor:** For Round-3 scenarios, if a crossing yields `C_lower=0` with `status=="exact_bracket"`, classify as `floor_at_zero` and apply the floor rule (include in delta_lo as 0 − C_upper_B).

---

## L. Floor/Left-Censor Rule (frozen)

**Base-infeasible** `[C_lower=0, C_upper=0]` (`status=="left_boundary"`): the policy cannot schedule any synthetic jobs in this scenario at this ratio. Report as `[0, 0]`. Exclude from bracket-width summary statistics. Count as `n_base_infeasible`. The constraint that triggers `left_boundary` is recorded as `first_binding_constraint`.

**Floor-at-zero** `[C_lower=0, C_upper>0]` (`status=="exact_bracket"`, `C_lower_pct==0`): the policy can schedule some synthetic jobs but with zero lower-bracket capacity. Include in delta_lo as `delta_lo = 0 − C_upper_B`. Count as `n_floor_at_zero`.

**Bracket-width summaries:** Exclude `[0, 0]` cells. Report `n_non_infeasible`, `n_base_infeasible`, separately for each policy-ratio cell.

---

## M. Position Template Audit

**Output:** `artifacts/revision3/position_template_audit.json`

**Scheduling key:** `pos_key = chassis + '_' + slot + '_' + board + '_' + node_pos`
**Grouping columns:** `chassis`, `slot`, `board`, `node_pos`
**LOC_FA construction:** Mean FA_2024 over all fp nodes sharing the same `pos_key`. NaN filled with global mean. Source: `r2_gate_f_run.py` lines 236–246.
**From selector audit:** 67 unique position scores; 1,933 nodes share a score with ≥1 other node; max multiplicity = 73.

**LOO Position score — corrected fallback hierarchy (within-chassis at all levels):**

| Level | Scope | Rule |
|---|---|---|
| 1 (primary LOO) | (chassis, slot, board, node_pos) | Mean FA_2024 over same pos_key, EXCLUDING the target node |
| 2 | (chassis, slot, board) | Mean FA_2024 over all nodes with same (chassis, slot, board) EXCLUDING target |
| 3 | (chassis, slot) | Mean FA_2024 over all nodes with same (chassis, slot) EXCLUDING target |
| 4 (fallback) | global cohort | Mean FA_2024 over all fp nodes |

Apply the first level that has ≥2 members after excluding the target node. Levels 2 and 3 remain WITHIN the same chassis — no cross-chassis averaging. Level 4 (global cohort mean) is the last resort.

**Validation:** Compute Spearman rank correlation between LOO variant scores and original LOC_FA. Report count of nodes at each fallback level used.

**Status:** PENDING — requires fp_node_topology.csv and FA_2024 values.

---

## N. Placebo Scope and Seeds

**Placebo scope (frozen):** The placebo FA permutation affects the selector score only. The thermal model (FA_2024, beta estimator, B_primary_h / S_primary computation) is unchanged. The constraint checker uses actual job power telemetry (not permuted scores). Unit test required: assert that `placebo_fa_dict` is never passed to the thermal exceedance computation in `r3_gate_f_run.py`.

**Round-3 root seed:** 847291653
**Scenario/workload seed derivation:**
```python
rng = np.random.default_rng(847291653)
scen_seeds = [int(rng.integers(0, 2**31)) for _ in range(25)]
wl_seeds   = [int(rng.integers(0, 2**31)) for _ in range(25)]
```

**Placebo seed derivation (SeedSequence):**
```python
from numpy.random import SeedSequence
R3_ROOT = 847291653
placebo_global_id    = 1
placebo_withincab_id = 2

# For scenario at seed_index i (0-based):
placebo_global_seed_i    = int(SeedSequence([R3_ROOT, i, placebo_global_id]).generate_state(1)[0])
placebo_withincab_seed_i = int(SeedSequence([R3_ROOT, i, placebo_withincab_id]).generate_state(1)[0])
```

**Scenario indices:** sc55–sc79 (sc30–sc54 were the revision2 challenge).

**Frozen seed table (all 25 scenarios):**

| Scenario | seed_index | scen_seed | wl_seed | placebo_global_seed | placebo_withincab_seed |
|---|---|---|---|---|---|
| sc55 | 0 | 1904386450 | 977279263 | 2514122466 | 4138460386 |
| sc56 | 1 | 313800891 | 498745018 | 239530002 | 2821695500 |
| sc57 | 2 | 2025222357 | 1950300279 | 3621860046 | 2637602780 |
| sc58 | 3 | 477937402 | 1029216890 | 545698191 | 4163530149 |
| sc59 | 4 | 638036904 | 1599240198 | 190970408 | 1026495243 |
| sc60 | 5 | 1896999442 | 541016197 | 3116675064 | 3324370430 |
| sc61 | 6 | 1227074784 | 99709171 | 2485654332 | 635301088 |
| sc62 | 7 | 1831068730 | 1303540434 | 1342144885 | 1003500168 |
| sc63 | 8 | 692298778 | 1171597058 | 2673015118 | 1148566559 |
| sc64 | 9 | 1866114391 | 512454599 | 2922433317 | 3151530878 |
| sc65 | 10 | 597289215 | 777856846 | 2063110589 | 896152315 |
| sc66 | 11 | 1310291338 | 867962360 | 4022789993 | 1775581892 |
| sc67 | 12 | 281306444 | 1760341653 | 2236687990 | 3332431586 |
| sc68 | 13 | 765916616 | 1376942482 | 2194622976 | 436439489 |
| sc69 | 14 | 2073810169 | 225153310 | 340492901 | 3132632523 |
| sc70 | 15 | 648527551 | 1811153282 | 4109598880 | 3507870418 |
| sc71 | 16 | 1221674886 | 1180004610 | 1995312588 | 3821245189 |
| sc72 | 17 | 44859 | 583818257 | 2665193087 | 1241988281 |
| sc73 | 18 | 1780201749 | 481639077 | 462462717 | 883960542 |
| sc74 | 19 | 868128083 | 1101340298 | 3965125396 | 314023354 |
| sc75 | 20 | 527967842 | 698767369 | 1002510123 | 3224669518 |
| sc76 | 21 | 1428443707 | 946098883 | 2867200991 | 3961623455 |
| sc77 | 22 | 1520695285 | 1637364493 | 2702104386 | 3362594012 |
| sc78 | 23 | 209700599 | 529424009 | 2848031429 | 1745551056 |
| sc79 | 24 | 960876882 | 1885369134 | 1242389544 | 2325658828 |

All 25 scen_seeds unique: confirmed. All 25 wl_seeds unique: confirmed.

---

## O. Late-Cabinet Exclusion

**Exclusion set (frozen):** cabinets 2600, 2601, 2602

**Rationale:** Commissioned 2024-07-18 to 2024-11-22 (after study start 2024-01-17). FA_2024 estimates based on 6–24 training jobs (vs ~39 for early cabinets). These are the coolest cabinets (FA mean −1.24 to −2.22 vs fleet mean −0.037). FP preferentially picks them; their FA estimates may be noisy.

**Exclusion rule (frozen):** Exclude late-cabinet nodes from BOTH FP and Random candidate pools. Apply the corrected time-weighted cabinet reference (F2) regardless of R3-0 legacy-equivalence outcome.

**Diagnostic:** Run FP vs Random with and without late-cabinet nodes in the candidate pool. If the sign of FP_vs_Random reverses without late-cabinet nodes: mandatory material finding disclosure.

**Output:** `artifacts/revision3/late_cabinet_diagnostic.json`

---

## P. Calendar-Split Plan

**Split boundary rule (frozen):** median `start_time` of the 2,637 frozen test-set jobs. Compute and record the EXACT timestamp before any simulation. Store in `calendar_split_plan.json`. The timestamp must appear in the plan file before any calendar-split scenario is run.

**Two halves:** jobs with `start_time < boundary` (first half) and `start_time ≥ boundary` (second half). Run FP vs Random on each half separately at r=1.25. Label: post-exposure exploratory temporal stability check.

**Seed rule:** Use the corrected time-weighted cabinet reference (F2). Same frozen seed table (sc55–sc79) for both halves.

**Output:** `artifacts/revision3/calendar_split_plan.json`

---

## Q. Round-3 Runner Preparation and R3-0 Plan

**Legacy mode (R3-0):** Identical to revision2 runner (`r2_gate_f_run.py`); uses F1 (event-weighted job-contribution P99) cabinet reference. Purpose: equivalence check only.

**R3-0 equivalence criterion:** Run sc55 (first Round-3 scenario) in legacy mode. Compare results against sc30–sc54 on shared internal quantities (B_primary_h, S_primary_Cdoth, B_cab_ratio at each lambda). Accept if max absolute difference ≤ 1e-9. STOP after R3-0 passes; report equivalence result before proceeding to corrected modes.

**Corrected mode:** Uses F2 or F3 cabinet reference. Do NOT run until:
1. D (support audit) complete
2. F (corrected reference definitions) frozen, reviewed, and committed
3. Q equivalence check (R3-0) passes
4. This plan committed (already required above)

**Equivalence check script:** `artifacts/revision3/check_r3_legacy_equivalence.py`
Purpose: verify that the Round-3 legacy-mode runner produces results matching sc30–sc54 on shared scenarios (tolerance ≤ 1e-9), before any Round-3-specific scenarios run.

---

## R. Interpretation Rules (frozen)

1. **Primary challenge unchanged:** sc30–sc54 is the pre-specified result; Round-3 is post-exposure reviewer-requested context.

2. **Legacy vs corrected cabinet reference:** Use F2 (corrected time-weighted) as the reported reference for all Round-3 new simulations. If F2 changes any comparison verdict direction from F1, BOTH must be reported and the abstract must carry an explicit limitation statement.

3. **Late-cabinet exclusion:** If FP_vs_Random sign reverses without late-cabinet nodes: mandatory material finding, explicit disclosure.

4. **LOO Position:** The non-separation finding (16/5/4, CI [−0.82, +1.50] pp spanning zero) stands regardless of LOO variant. LOO variant results are robustness context only; they do not reopen the non-separation verdict.

5. **Placebos (GlobalPlacebo, WithinCabPlacebo):** Pre-specified secondary comparisons. Primary endpoint interpretation unchanged by placebo pattern.

6. **Threshold grid (p90/p95/p99):** Label all results "exploratory threshold sensitivity." Primary T_thr = p95 = 63.625°C.

7. **Calendar split:** If second-half FP_vs_Random sign reverses from first-half: disclose as temporal instability finding. Applies corrected F2 reference.

8. **S_cab:** Secondary diagnostic only. A positive S_cab_kWh for a policy does NOT constitute infeasibility; it is a descriptive measure of how far above the reference the policy runs.

9. **Required disclosure text for all Round-3 outputs:**
   > Post-exposure: This analysis was designed and executed after the sc30–sc54 primary results were observed. The design was not changed after primary results were available, but this work is post-exposure reviewer-requested robustness and exploratory analysis.

10. **Outcome-independent rules:** These interpretation rules apply regardless of what the Round-3 results show. No rule is conditional on observing a favorable or unfavorable result.

---

## S. Freeze Checklist

Before any new simulation:

1. `git diff --check` — verify no whitespace errors
2. Compute SHA256 of `THIRD_REVIEW_ANALYSIS_PLAN.md` and `third_review_plan.json`
3. Commit all mechanical paper fixes, existing-output analyses, support audit code, and Round-3 plan with message: `Freeze Round-3 reviewer-requested analysis plan v2`
4. Report commit SHA
5. Report exact R3 run matrix (policies × ratios × scenarios × modes)
6. Show legacy-equivalence acceptance criterion (≤ 1e-9 on all shared quantities)
7. **STOP.** Do not execute R3-0 or any Round-3 simulation until this checklist is reviewed.
