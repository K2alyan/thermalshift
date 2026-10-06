# Round-3 Plan Amendment 2

**Amendment number:** 2
**Plan version produced:** 2.1 (supersedes v2.0)
**Date:** 2026-10-05
**Exposure status at time of amendment:** pre-execution — no new Round-3 policy simulation results were observed before or during this amendment. The only policy results in existence are the frozen sc30–sc54 revision2 challenge (commit 5733b73 / f1c78a3) and the revision1 development results.
**Initial freeze commit:** 17c2e91
**First correction commit:** bf4d2a3
**This amendment corrects:** methodological errors identified in the bf4d2a3 plan and scripts by auditing the actual committed files. All corrections are pre-execution.

---

## Summary of Corrections

This amendment corrects fifteen material errors found in the v2.0 plan (bf4d2a3), scripts, and audit files. None of the corrections change any frozen policy result; all concern how the plan, scripts, or audit documents describe or will implement the analysis.

---

## Correction 1 — R3-0 Design: sc30–sc54 (not sc55)

**File:** `THIRD_REVIEW_ANALYSIS_PLAN.md §Q`, `third_review_plan.json r3_0_plan`

**Error:** v2.0 §Q stated "Run sc55 (first Round-3 scenario) in legacy mode. Compare results against sc30–sc54." This is wrong. R3-0 tests whether the Round-3 legacy-mode runner implementation is equivalent to the revision2 runner. To test this, R3-0 must replay the same scenarios that were run in revision2 — sc30–sc54 — and compare against the frozen revision2 outputs. Running sc55 (a new scenario) cannot establish equivalence against frozen revision2 results.

**Correction:** R3-0 replays sc30–sc54 (all 25 frozen revision2 held-out scenarios) using the Round-3 legacy-mode runner and compares against the frozen revision2 challenge outputs. Partial scenario sets fail immediately. Subset equivalence never passes.

---

## Correction 2 — Position LOO Peer Requirement: ≥1 (not ≥2)

**File:** `THIRD_REVIEW_ANALYSIS_PLAN.md §M`, `third_review_plan.json position_template_audit`

**Error:** v2.0 stated "Apply the first level that has ≥2 members after excluding the target node." This incorrectly requires 2 peers. The correct criterion is ≥1 peer (i.e., the group has ≥2 nodes including the target).

**Correction:** Apply the first level that has ≥1 member after excluding the target node (group size ≥ 2 including target). Levels 2 and 3 remain within the same chassis.

---

## Correction 3 — E1 B_ref_s Does Not Scale Proportionally

**File:** `THIRD_REVIEW_ANALYSIS_PLAN.md §E, §J`, `third_review_plan.json e1_reinterpretation`

**Error:** v2.0 stated "Both the counterfactual exposure envelope and the historical B_cab denominator scale proportionally." This was false. B_ref_s (the historical exceedance-hours denominator) is computed at the FIXED base threshold (CAB_SCALE=1.0) and is identical across all 5 CAB_SCALE values.

**Verification:** B_ref_s = 2449.93 s at all 5 CAB_SCALE values for sc30, confirmed from `artifacts/revision2/results/gate_f_sc30-54_1p25_r2sensitivity_sc*_bprimary.json`.

**Correction:** B_ref_s is fixed at the base threshold. Only B_primary_h (counterfactual exceedance) changes nonlinearly: higher CAB_SCALE → higher threshold → less exceedance → lower B_primary_h → lower B_cab_ratio. The prior statement is retracted in §E and §J.

---

## Correction 4 — Cabinet Reference Audit: Replay Summing Is Not the Issue

**File:** `cabinet_reference_audit.json` (v1, superseded), `CABINET_REFERENCE_AUDIT.md` (v1, superseded)

**Error:** An earlier audit version incorrectly implied that replay job-cabinet contributions are NOT summed. This was false. `sweep_cab_budget_fast()` explicitly maintains a running sum P_cab[c] per cabinet and adds/removes each job's contribution at start/end events. The concurrent total IS summed.

**Correction:** The mismatch between the legacy cabinet reference and the replay quantity concerns how the reference threshold Q_c is estimated, not whether replay power is summed. The legacy Q_c is a marginal P99 over individual job contributions (event-weighted); the concurrent total P_c_total(t) = Σ_j P_job_c(t) is summed in the replay. The distinction is that Q_c estimated from per-job marginals (F1) is a different statistical object from Q_c estimated from the concurrent total power distribution (F2/F3). Correction documented in `cabinet_reference_audit_v3.json`.

---

## Correction 5 — Holm-Bonferroni Missing Cumulative-Maximum Step

**File:** `analyze_existing_round3_requests.py`

**Error:** The original `holm_bonferroni()` implementation tracked `prev_reject` to set a rejection floor but did not apply the standard cumulative-maximum (running-max) step required by the Holm procedure. This produced incorrect adjusted p-values.

**Correction:** Implementation rewritten with: (1) sort ascending by p-value; (2) compute (m − rank) × p for each; (3) apply running maximum; (4) cap at 1.0; (5) map back to original order. All 8 expected Holm-adjusted p-values verified via `_verify_holm_values()` assertion.

---

## Correction 6 — FP↔FPSpread Reverse Direction

**File:** `analyze_existing_round3_requests.py b3_fpspread_vs_fp()`

**Error:** The reverse direction used `[-x for x in delta_lo_per_scenario]` (negating delta_lo). This is wrong because delta_lo(B,A) ≠ −delta_lo(A,B). The correct identity is delta_lo(B,A) = −delta_hi(A,B).

**Correction:** Reverse uses `dlo_reverse = [-x for x in dhi_stored]` where `dhi_stored = delta_hi_per_scenario` from the stored FPSpread_vs_FP comparison. Verified against exact expected values.

---

## Correction 7 — B5 Decomposition: Direct Paired Contrasts

**File:** `analyze_existing_round3_requests.py b5_decomposition()`

**Error:** Old implementation subtracted medians (algebraic: FP_vs_Random median − FP_vs_GlobalPlacebo median). This does not produce the correct per-scenario bracket contrasts for verdict counting.

**Correction:** Use direct per-scenario crossing brackets from the merged file. For each scenario, compute delta_lo = C_lower_A − C_upper_B and delta_hi = C_upper_A − C_lower_B directly from crossing data. Verdict: definitely_A if delta_lo > 0, definitely_B if delta_hi < 0, else indistinguishable.

---

## Correction 8 — sc5–sc29 Source: gate_f_heldout_analysis.json

**File:** `analyze_existing_round3_requests.py b7_sc5_sc29()`

**Error:** Old code attempted to parse capacity_unlock_pct from lambda_rows of the raw sc5-29 output file. This returned incorrect values (reported −0.437 pp instead of the stored analysis result).

**Correction:** Read `gate_f_heldout_analysis.json` directly as the authoritative source for sc5–sc29 analysis results. Return stored values without recomputation.

---

## Correction 9 — check_r3_legacy_equivalence.py: Enforce Full sc30–54

**File:** `check_r3_legacy_equivalence.py`

**Error:** Old implementation used intersection of scenario keys, accepting partial sets. Checked all policies rather than only the equivalent policies (full_fp, full_random). Did not check all required fields.

**Correction:** Added `REQUIRED_SCENARIOS = set(range(30, 55))`, `EQUIV_POLICIES = ["full_fp", "full_random"]`, `EQUIV_RATIO = "1.25"`, and explicit field lists `LAMBDA_ROW_FIELDS` and `CROSSING_FIELDS`. Missing scenarios cause immediate hard failure with exit code 2. Subset equivalence never passes.

---

## Correction 10 — Seed Table Scope Clarification

**File:** `THIRD_REVIEW_ANALYSIS_PLAN.md §N`

**Error:** v2.0 §N listed only sc55–sc79 seeds and stated "sc30–sc54 were the revision2 challenge" without clarifying that sc30–sc54 placebo seeds are also pre-specified (for R3-0 CRN and placebo robustness runs on those scenarios).

**Correction:** §N now clarifies two seed roles: sc30–sc54 as CRN for R3-0 and placebo robustness (documented in `placebo_seeds_r2_crn.json`); sc55–sc79 for new Round-3 scenarios including calendar-split temporal replication.

---

## Correction 11 — Threshold 5-Job IDs: Status Resolved

**File:** `THIRD_REVIEW_ANALYSIS_PLAN.md §K`, `threshold_population_audit.json` (superseded)

**Error:** v2.0 §K listed excluded job IDs as "PENDING."

**Resolution:** IDs resolved by diffing globus_batch.txt (3,945) against full_train_t95_distribution.parquet (3,940). Excluded: 035490, 035492, 057113, 057851, 058085. Documented in `threshold_population_audit_v2.json`.

---

## Correction 12 — T_thr Secondary Provenance: Resolved

**File:** `THIRD_REVIEW_ANALYSIS_PLAN.md §K`

**Error:** v2.0 listed legacy T_thr secondary provenance as "to be confirmed."

**Resolution:** 60.60277°C is the empirical p95 of node-job GCD temperatures from the 462-job training subset, stored in `phase3b1_realism.json` as `empirical_thresholds.T_p95`. This is the B_secondary/S_secondary threshold, not the primary T_thr.

---

## Correction 13 — Cabinet Reference Audit V3

**File:** `cabinet_reference_audit_v3.json` (new)

**Action:** Supersedes v1 audit. Corrects the description of replay mechanics (replay DOES sum concurrent contributions), clarifies E1 B_ref_s behavior (fixed at base threshold), and defines F1/F2/F3 modes with correct weighting descriptions.

---

## Correction 14 — Position LOO Diagnostic

**File:** `position_loo_diagnostic.json` (new)

**Computed:** n_unique_pos_keys=67, n_singleton_groups=10, Spearman rho(LOC_FA, LOO_Position)=0.982344. L1=1990, L2=0, L3=3, L4=7 nodes. Status: COMPUTED; scheduling run requires R3-0 clearance.

---

## Correction 15 — Paper Revert

**Files:** `paper/` directory

**Error:** bf4d2a3 included edits to `paper/` files. The paper is owned separately and must not be modified by the plan amendment commit.

**Correction:** `git restore --source=17c2e91 -- paper/` was executed to revert all paper files to the pre-bf4d2a3 state.

---

## Files Written or Updated in This Amendment

| File | Action | Notes |
|---|---|---|
| `THIRD_REVIEW_ANALYSIS_PLAN.md` | Updated to v2.1 | Corrections 1–3, 10–12 |
| `third_review_plan.json` | Updated to v2.1 | Governance metadata; E1 and LOO corrections |
| `ROUND3_PLAN_AMENDMENT_2.md` | New | This document |
| `check_r3_legacy_equivalence.py` | Rewritten | Correction 9 |
| `analyze_existing_round3_requests.py` | Rewritten | Corrections 5–8 |
| `cabinet_reference_audit_v3.json` | New | Correction 4, 13 |
| `threshold_population_audit_v2.json` | New | Correction 11–12 |
| `position_loo_diagnostic.json` | New | Correction 14 |
| `placebo_seeds_r2_crn.json` | New | Correction 10 |
| `paper/` | Reverted to 17c2e91 | Correction 15 |

---

## Stop Condition

STOP. Do not execute any policy simulation. The only computations authorized before committing this amendment are:
- Non-policy diagnostics already run (B-tasks, LOO audit, threshold audit, seed generation)
- `git diff --check` and SHA256 computation
- The commit itself

Do not run R3-0, any corrected-mode simulation, or any new scenario until this amendment is committed and reviewed.
