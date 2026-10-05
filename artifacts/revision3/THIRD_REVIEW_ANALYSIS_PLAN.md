# Round-3 Analysis Plan: Reviewer-Requested Robustness and Exploratory Analyses

**Exposure status:** post-exposure — all Round-3 work was designed and will be executed after the sc30–sc54 primary challenge results (commit f1c78a3) were observed.

**Critical invariant:** The frozen sc30–sc54 challenge (preregistered at commit 5733b73, evidence-frozen at commit f1c78a3) is unchanged and remains the original pre-specified result. Round-3 results do not supersede or modify it.

**Plan freeze:** This document and `third_review_plan.json` must be committed before any new policy simulation is run.

**Machine-readable companion:** `artifacts/revision3/third_review_plan.json`

---

## A. Plan Documents

This file (`THIRD_REVIEW_ANALYSIS_PLAN.md`) and `third_review_plan.json` constitute the frozen Round-3 plan. All analysis definitions, seed derivations, output filenames, interpretation rules, floor handling, cabinet-reference definitions, threshold grid, LOO Position fallback hierarchy, late-cabinet exclusion set, and calendar-split boundary rule are frozen here before any new simulation.

---

## B. Existing-Output Diagnostics (no new simulation)

**Script:** `artifacts/revision3/analyze_existing_round3_requests.py`
**Outputs:** `existing_round3_diagnostics.json`, `existing_round3_diagnostics.md`
**Source data:** `artifacts/revision2/challenge_analysis.json` only (frozen sc30–sc54 outputs)

### B1. Absolute Capacity Levels at r=1.25

For each of the 7 policies, extract from `challenge_analysis.json policy_summaries[policy]["1.25"]`:

| Field | Definition |
|---|---|
| `median_C_lower_pct` | Median lower-bracket capacity across 25 scenarios (%) |
| `median_C_upper_pct` | Median upper-bracket capacity across 25 scenarios (%) |
| bracket_width | `C_upper - C_lower` per scenario; report median and IQR |
| `n_right_censored` | Count of right-censored scenarios |
| n_floor_at_zero | Scenarios with `C_lower = 0`, `C_upper > 0` |
| n_base_infeasible | Scenarios with `C_lower = 0`, `C_upper = 0` |

Floor/left-censor rule (frozen):
- **Base-infeasible** `[0, 0]`: report as-is; exclude from bracket-width summaries; count separately.
- **Floor-at-zero** `C_lower=0`, `C_upper>0`: include in delta_lo as `delta_lo = 0 − C_upper_B` (conservative); report count.
- Bracket-width summaries (`mean`, `median`, `IQR`) exclude `[0, 0]` cells. N of excluded cells reported alongside.

### B2. Binding-Constraint Diagnostic (legacy_cabinet_reference_binding_diagnostic)

For each scenario and policy at r=1.25, identify which constraint bound the crossing lambda:
- **B** (thermal, node-level): `B_primary_h` reaches the crossing
- **S** (thermal severity): `S_primary_Cdoth` drives the result
- **B_cab** (cabinet-power): `B_cab_ratio` ≥ 1.0 triggers cabinet-power drop

Label all results: `legacy_cabinet_reference_binding_diagnostic` — the cabinet reference is the legacy job-contribution P99 from `cabinet_power_envelopes.json`.

### B3. FPSpread vs FP Both Directions

Report `FPSpread_vs_FP` results from `challenge_analysis.json` at all ratios [1.25, 1.5, 2.0, 4.0, 8.0, unrestricted] with bootstrap 95% CI (n_bootstrap=5000, seed=9999). Report both the stored direction and the reverse implied by sign flip. Document the crossover point.

### B4. Exact Sign Tests with Holm-Bonferroni Correction

For each of the 8 preregistered comparisons at r=1.25:
- **Test:** Exact binomial sign test: H₀: P(δ_lo > 0) = 0.5; one-sided (direction pre-specified by comparison name).
- **Ties** (indistinguishable verdicts): counted as 0.5 wins/losses; reported separately.
- **Correction:** Holm-Bonferroni over 8 comparisons.
- Source: `verdicts` arrays in `challenge_analysis.json results[comparison]["ratios"]["1.25"]`.

### B5. Exploratory Decomposition Contrasts

| Contrast | Computation | Interpretation |
|---|---|---|
| Global-score advantage | FP_vs_GlobalPlacebo | Knowing global thermal ordering |
| Node-vs-cabinet specificity | FP_vs_WithinCabPlacebo | Node-level identity beyond cabinet composition |
| Cabinet-composition advantage | FP_vs_Random − FP_vs_GlobalPlacebo (algebraic) | Advantage from cabinet-level thermal composition |
| Spreading cost at r=1.25 | FPSpread_vs_FP (negative) | Cost of cabinet-spreading at constrained ratios |

Label: exploratory — not preregistered. Medians only; bootstrap CIs from stored values.

### B6. Order-Statistic Median Intervals (n=25)

For each comparison at r=1.25, compute the exact order-statistic 95% CI on the median of `delta_lo_per_scenario` (n=25): use OS₈ and OS₁₈ (exact binomial 95% CI on n=25 median, Conover 1999). Report alongside the bootstrap CI as a non-parametric confirmation.

### B7. Earlier Held-Out sc5–sc29 Evaluation

Source: `artifacts/revision1/results/gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json`

Compute the same bootstrap analysis (n_bootstrap=5000, seed=9999) for sc5–sc29 at r=1.25 on the revision1 comparisons (FP_vs_Random, FP_vs_Loc, FPSpread_vs_FP). Label: exploratory context, revision1 design — different selectors from revision2 challenge. Report n_scenarios=25, scenario indices 5–29.

---

## C. Cabinet Reference Audit

**Output:** `artifacts/revision3/CABINET_REFERENCE_AUDIT.md`, `cabinet_reference_audit.json`

Document the exact construction of the legacy cabinet power envelope:

**Formula (from `cabinet_power_envelopes.json`):**
```
P_cab_j = (mean_power_j / node_count_j) × n_nodes_in_cabinet_j
```
where `n_nodes_in_cabinet_j` uses the CORRECT topology (corrected from an earlier bug). Applied to all 152,400 jobs with reported `mean_power > 0`. The per-cabinet P99 is taken over all qualifying job contributions.

**Key distinction (verbatim, to appear in all outputs):**
> The legacy cabinet envelope (P99 of per-job contributions) is not the same statistical object as the P99 of observed concurrent cabinet power over time. These are different estimators. The former is used in all sc0–sc54 results; the latter is what Round-3 corrected-mode analyses will test.

**Also document:**
- E1 cabinet-scale behavior: `CAB_SCALE` multiplies each cabinet's P99 uniformly. The historical `B_cab` denominator scales proportionally. E1 is a cabinet-reference-scale sensitivity, not a fixed-budget test, and not equivalent to T_thr sensitivity.
- Late-cabinet P99 values: 2600 = 71.171 kW, 2601 = 74.009 kW, 2602 = 68.741 kW (vs fleet median 92.487 kW).

---

## D. Cabinet Support Audit

**Script:** `artifacts/revision3/cabinet_support_audit.py`
**Output:** `artifacts/revision3/cabinet_support_audit.json`

Determine the exact support over which historical concurrent cabinet power can be reconstructed:
- All collection dates with usable power telemetry
- Contiguous blocks (hours)
- Total support hours per cabinet
- Distribution of concurrent job counts and concurrent node counts per 15-min (or hourly) bin
- Fraction of bins with ≥1 concurrent job across all 77 cabinets

**Phrase required in all outputs:** "observed reconstructed concurrent cabinet power"

---

## E. Legacy Exceedance Fraction

Using support from D, compute for each cabinet:

```
legacy_exceedance_fraction_i = (hours where reconstructed_P_concurrent_i > P99_legacy_i) / support_hours_i
```

Report: per-cabinet values, aggregate (fleet-level), median, IQR, p90, max, min. This is diagnostic only — not a feasibility criterion.

---

## F. Corrected Cabinet Reference Definitions

Three modes frozen here; no policy simulations until D is complete and Q equivalence check passes.

**F1 — legacy_job_contribution_p99 (current):** P99 of per-job cabinet power contributions over 152,400 jobs. Source: `cabinet_power_envelopes.json`. Used in all sc0–sc54.

**F2 — corrected_timeweighted_total_p99:** Concurrent cabinet power sum at each time point; P99 over the support period (from D). Uses uniform node-power approximation applied simultaneously across all overlapping jobs.

**F3 — corrected_eventweighted_total_p99:** Same concurrent sum, but P99 is taken over job-start-event-weighted samples (one sample per job start, concurrent power at that instant). Alternative to F2.

---

## G. S_cab Severity Diagnostic Code

Prepare code (diagnostic only, not a feasibility criterion):

```
S_cab_kWh_i = sum_{t in bins} max(0, P_reconstructed_i(t) - P_reference_i) * bin_duration_h
```

Report aggregate `S_cab_kWh` across fleet, per-cabinet distribution, and fraction of cabinets with S_cab_kWh > 0.

---

## H. Concurrent Power Validation Script

**Script:** `artifacts/revision3/validate_concurrent_cabinet_power.py`

Validate the concurrent cabinet power computation by filtering to scenarios where all concurrent jobs have complete usable telemetry (no missing nodes). Compare reconstructed concurrent cabinet power against individual job-level approximations as a cross-check.

---

## I. Legacy-vs-Corrected Reporting Rule (verbatim freeze)

> If corrected cabinet reference (F2 or F3) changes any comparison verdict direction from the legacy reference (F1), both results must be reported. The discrepancy is a finding requiring explicit disclosure. The original preregistered sc30–sc54 result (legacy F1) remains the primary result and is not superseded.

---

## J. E1 Cabinet-Scale Behavior Documentation

Exact E1 behavior (from `sensitivity_cabinet_scale.json`):
- `CAB_SCALE ∈ {0.90, 0.95, 1.00, 1.05, 1.10}` multiplies each cabinet's P99 uniformly.
- The historical `B_cab` denominator at each scale equals `B_cab_reference × scale_factor`.
- E1 tests sensitivity to uniform mis-estimation of cabinet capacity, not to a fixed physical budget.
- E1 is **not** equivalent to T_thr sensitivity (T_thr controls which nodes contribute to thermal exceedance; scale controls the cabinet power ceiling).

---

## K. Threshold Population Audit

**Output:** `artifacts/revision3/threshold_population_audit.json`

Source: `artifacts/revision1/results/m4_threshold_audit.json`

| Population | N jobs | p90 (°C) | p95 (°C) | p99 (°C) |
|---|---|---|---|---|
| Nominal pre-2025 | 3,945 | — | — | — |
| Contributing (≥1 fp node, ≥8 GCD, ≥5 timestamps) | 3,940 | 61.875 | 63.625 | 66.6625 |
| 462-job training subset (LOO beta) | 462 | 61.801 | 63.625 | 66.264 |

Frozen primary threshold grid: p90=61.875°C, p95=63.625°C (primary T_thr), p99=66.6625°C

**Determine exact 5 excluded job IDs** with machine-readable exclusion reason (from training data filtering in `r1_m3_thermal_model.py` or equivalent). Document: "nominal 3,945 becomes 3,940 contributing because [exact reason per job]."

Legacy T_thr secondary: 60.602770562770566°C (from BETA_F calibration; provenance to be confirmed).

---

## L. Floor/Left-Censor Rule (frozen)

**Base-infeasible** `[C_lower=0, C_upper=0]`: the policy cannot schedule any synthetic jobs in this scenario at this ratio. Report as `[0, 0]`. Exclude from bracket-width summary statistics. Count separately as `n_base_infeasible`.

**Floor-at-zero** `[C_lower=0, C_upper>0]`: the policy can schedule some jobs but with zero lower-bracket capacity. Report `C_lower=0` and correct `C_upper`. Include in delta_lo as `delta_lo = 0 − C_upper_B`. Count separately as `n_floor_at_zero`.

**Bracket-width summaries:** Exclude `[0, 0]` cells. Report `n` (non-infeasible), `n_base_infeasible`, separately for each policy-ratio cell.

---

## M. Position Template Audit

**Output:** `artifacts/revision3/position_template_audit.json`

**Scheduling key:** `pos_key = chassis + '_' + slot + '_' + board + '_' + node_pos`

**Grouping columns:** `chassis`, `slot`, `board`, `node_pos`

**LOC_FA construction:** Mean FA_2024 over all fp nodes sharing the same `pos_key`. NaN filled with global mean. Source: `r2_gate_f_run.py` lines 236–246.

**From selector audit (`m4_selector_audit.json`):** 67 unique position scores; 1,933 nodes share a score with at least one other; max multiplicity = 73; hash tie-breaking does not apply (score ties resolved by hostname sort, which is deterministic but not thermally informed).

**LOO Position score (frozen fallback hierarchy):**
1. Mean FA_2024 over same `pos_key`, excluding the target node (primary LOO)
2. Mean FA_2024 over all nodes with same `slot_board_nodepos` across all chassis (cross-chassis mean)
3. Mean FA_2024 over all nodes with same `slot_board` across all chassis
4. Global mean FA_2024

Apply the first level that has ≥2 members (after excluding the target node). Compute Spearman rank correlation between LOO variant scores and original LOC_FA for validation.

---

## N. Placebo Scope and Seeds

**Placebo scope (frozen):** The placebo FA permutation affects the selector score only. The thermal model (FA_2024, beta estimator) is unchanged. The constraint checker uses actual job power telemetry (not permuted scores). Unit test required: assert that `placebo_fa_dict` is never passed to the thermal exceedance computation in `r3_gate_f_run.py`.

**Round-3 root seed:** 847291653
**Seed derivation:**
```python
rng = np.random.default_rng(847291653)
scen_seeds = [int(rng.integers(0, 2**31)) for _ in range(25)]
wl_seeds   = [int(rng.integers(0, 2**31)) for _ in range(25)]
```
**Scenario indices:** sc55–sc79 (sc30–sc54 were the revision2 challenge)

**Frozen seed table:**

| Scenario | seed_index | scen_seed | wl_seed |
|---|---|---|---|
| sc55 | 0 | 1904386450 | 977279263 |
| sc56 | 1 | 313800891 | 498745018 |
| sc57 | 2 | 2025222357 | 1950300279 |
| sc58 | 3 | 477937402 | 1029216890 |
| sc59 | 4 | 638036904 | 1599240198 |
| sc60 | 5 | 1896999442 | 541016197 |
| sc61 | 6 | 1227074784 | 99709171 |
| sc62 | 7 | 1831068730 | 1303540434 |
| sc63 | 8 | 692298778 | 1171597058 |
| sc64 | 9 | 1866114391 | 512454599 |
| sc65 | 10 | 597289215 | 777856846 |
| sc66 | 11 | 1310291338 | 867962360 |
| sc67 | 12 | 281306444 | 1760341653 |
| sc68 | 13 | 765916616 | 1376942482 |
| sc69 | 14 | 2073810169 | 225153310 |
| sc70 | 15 | 648527551 | 1811153282 |
| sc71 | 16 | 1221674886 | 1180004610 |
| sc72 | 17 | 44859 | 583818257 |
| sc73 | 18 | 1780201749 | 481639077 |
| sc74 | 19 | 868128083 | 1101340298 |
| sc75 | 20 | 527967842 | 698767369 |
| sc76 | 21 | 1428443707 | 946098883 |
| sc77 | 22 | 1520695285 | 1637364493 |
| sc78 | 23 | 209700599 | 529424009 |
| sc79 | 24 | 960876882 | 1885369134 |

All 25 scen_seeds unique: confirmed. All 25 wl_seeds unique: confirmed.

---

## O. Late-Cabinet Exclusion

**Exclusion set (frozen):** cabinets 2600, 2601, 2602

**Rationale:** These three cabinets were commissioned 2024-07-18 to 2024-11-22 (after study start 2024-01-17). Their FA_2024 estimates are based on fewer training jobs (mean 6–24 vs 39 for early cabinets). They are the coolest in the fleet (FA mean −1.24 to −2.22 vs fleet mean −0.037). The FP selector preferentially picks them, which may overstate the FP advantage if their FA estimates are noisy.

**Diagnostic:** Run FP vs Random with and without late-cabinet nodes in the candidate pool. Label: post-exposure exploratory. If the sign of FP_vs_Random reverses without late-cabinet nodes, this is a material finding requiring disclosure.

**Output:** `artifacts/revision3/late_cabinet_diagnostic.json`

---

## P. Calendar-Split Plan

**Split boundary rule (frozen):** median `start_time` of the 2,637 frozen test-set jobs. Compute and record the exact timestamp before execution. Store in `calendar_split_plan.json`.

**Two halves:** jobs with `start_time < boundary` (first half) and `start_time ≥ boundary` (second half). Run FP vs Random on each half separately at r=1.25. Label: post-exposure exploratory temporal stability check.

**Seed rule:** Use the same frozen seed table (sc55–sc79) for both halves; the scenario seed determines which jobs from the relevant half are used.

**Output:** `artifacts/revision3/calendar_split_plan.json`

---

## Q. Round-3 Runner Preparation

**Legacy mode:** Identical to revision2 runner (`r2_gate_f_run.py`); uses F1 cabinet reference. Used for equivalence check only.

**Corrected mode:** Uses F2 or F3 cabinet reference. **Do NOT run until:** D (support audit) complete; F reference definitions frozen and reviewed; Q equivalence check passes; this plan committed.

**Equivalence check script:** `artifacts/revision3/check_r3_legacy_equivalence.py`
Purpose: verify that the Round-3 legacy-mode runner produces results matching the sc30–sc54 results on shared scenarios (tolerance 1e-9), before any Round-3-specific scenarios are run.

---

## R. Interpretation Rules (frozen)

1. **Primary challenge unchanged:** sc30–sc54 is the pre-specified result; Round-3 is post-exposure context.
2. **Legacy vs corrected:** Report both if verdict changes; discrepancy is a finding, not a correction.
3. **Late-cabinet:** If sign reverses without late-cabinet nodes: material finding, explicit disclosure.
4. **LOO Position:** Non-separation finding (16/5/4, CI spanning zero) stands regardless of LOO variant; LOO variant results are robustness context.
5. **Placebos:** Reported as preregistered secondary; primary endpoint interpretation unchanged.
6. **Threshold grid:** p90/p95/p99 results labeled exploratory threshold sensitivity.
7. **Calendar split:** If second-half sign reverses: disclose as temporal instability finding.
8. **Required disclosure text for all Round-3 outputs:**
   > Post-exposure: This analysis was designed and executed after the sc30–sc54 primary results were observed. The design was not changed after primary results were available, but this work is post-exposure reviewer-requested robustness/exploratory analysis.

---

## S. Commit

Commit message: `Freeze Round-3 reviewer-requested analysis plan`

**STOP:** Do not inspect any new policy result before this plan is committed. Do not run corrected-mode policy simulations until D, F, and Q are complete.
