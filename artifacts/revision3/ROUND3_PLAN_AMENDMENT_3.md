# Round-3 Plan Amendment 3

**Amendment number:** 3
**Plan version produced:** 2.2 (supersedes v2.1)
**Date:** 2026-10-05
**Exposure status at time of amendment:** pre-execution — no Round-3 policy simulation results observed. The only policy results are the frozen sc30–sc54 revision2 challenge (5733b73 / f1c78a3) and revision1 development results.
**Initial freeze commit:** 17c2e91
**Amendment 1 checkpoint:** bf4d2a3
**Amendment 2 checkpoint:** 6339587
**No scientific result motivated these changes.**

---

## Purpose

Three execution blockers in the Amendment 2 plan (6339587) prevent running R3-0:
1. Equivalence checker could falsely pass on missing or wrong fields
2. The F2 scientific run matrix was too broad (sc55–79, multiple policies, many ratios)
3. E1 B-vs-Bcab terminology was incorrect (B_ref_s ≠ cabinet denominator)

This amendment fixes all three. No paper files are touched.

---

## Correction A — Equivalence Checker: Hard-Fail on Missing/Wrong Fields

**File:** `check_r3_legacy_equivalence.py`

**Error 1 — None-vs-None false pass:** The prior `_check_numeric` helper returned `checks_passed + 1` when both values were `None`, regardless of whether the key was present. This meant that if a field was absent from both r2 and r3 files, it passed silently as if it had been checked. A sentinel object `_ABSENT` now distinguishes "key absent" from "key present with JSON null."

**Error 2 — Missing field is a hard failure, not a skip:** Every field in `SCENARIO_FIELDS`, `LAMBDA_ROW_NUMERIC`, etc., must exist on both sides. If either side is missing a required key, the check records `MISSING_KEY` and fails — not a silent pass.

**Error 3 — `first_binding` was misclassified as nullable numeric:** The `first_binding` field in lambda rows can be a string (e.g. `"B_cab_ratio"`) or `None`. Classifying it as nullable numeric caused a `TYPE_ERROR` when both values were the same non-None string, falsely failing the identity test. Fixed: moved to a new `LAMBDA_ROW_NULLABLE_CATEGORICAL` group with a `_cmp_nullable_categorical` helper that uses exact equality when both are non-None strings.

**Error 4 — Extra scenarios not rejected:** Prior version only checked for missing scenarios; scenarios beyond `{30,...,54}` in the r3 output were silently accepted. Now: extra scenarios also cause immediate hard failure.

**Error 5 — Duplicate scenario IDs not detected:** Now validated for both r2 and r3 files.

**Schema source:** `r2_equivalence_schema.json` — extracted directly from `gate_f_sc30-54_all_r2challenge_merged.json`. All field names verified against the actual frozen data. The original `SCENARIO_FIELDS` list (`scenario_array_i`, `B_ref_s`, `S_ref_s`) was correct — these fields DO exist in the frozen file.

**Self-tests added:** 10 negative/positive self-tests (`--self-test` flag). All 10 pass. See `equivalence_checker_selftest.json`.

---

## Correction B — Initial F2 Run Matrix

**Files:** `THIRD_REVIEW_ANALYSIS_PLAN.md §Q`, `third_review_plan.json r3_0_plan`

**Error:** The Amendment 2 freeze report described the post-R3-0 F2 run matrix as "sc55–79 × 5+ policies × nearly all ratios." This was wrong. Moving immediately to sc55–79, multiple policies, and every ratio loses the clean model-definition comparison (F1→F2 with everything else fixed).

**Correction:** After R3-0 passes, the FIRST and ONLY corrected scientific run is:

| Parameter | Value |
|---|---|
| Reference | F2 (`corrected_timeweighted_total_p99`) |
| Scenarios | sc30–sc54 (the 25 frozen revision2 scenarios) |
| Policies | `full_fp`, `full_random` only |
| Ratio | 1.25 only |
| Seeds / CRN | Identical frozen revision2 seeds |
| Purpose | Isolate cabinet-reference-definition change; one thing changes (Q_c) |

After this result: STOP AND REPORT. Do NOT auto-proceed to F3, other policies, other ratios, sc55–sc79, late-cabinet exclusion, LOO scheduling, scenario-specific placebos, threshold grid, calendar split, or corrected E1 without explicit review.

sc55–sc79 remain reserved for later calendar/data-level replication — not the initial F2 comparison.

**F2 gate conditions (all four required):**
1. THERMALSHIFT_DATA_DIR available
2. Task D (support audit) complete and reviewed
3. F2 per-cabinet thresholds generated from Task D
4. R3-0 legacy equivalence check passed

Legacy R3-0 equivalence testing does NOT require Task D. Only F2 and F3 require it.

---

## Correction C — E1 B-vs-Bcab Terminology

**Files:** `THIRD_REVIEW_ANALYSIS_PLAN.md §E, §J`, `third_review_plan.json e1_reinterpretation`, `e1_cabinet_denominator_audit.json` (new)

**Error:** Amendment 2 stated "B_ref_s (the historical exceedance-hours denominator) is FIXED at the base threshold." This was a false identification of `B_ref_s` as the cabinet exceedance denominator. Auditing `r2_sensitivity_run.py` line by line reveals:

- `B_ref_s`: node-level **thermal** incidence reference, computed from `compute_B_S_ref_s(job_perms, T_THR_PRIMARY=63.625°C)` (line 1105). Varies per scenario (e.g. sc30=2449.93, sc31=2456.55). NOT related to `cab_p99_W`. NOT the cabinet denominator. Invariant to `CAB_SCALE` because it does not use `cab_p99_W`.

- `B_cab_hist`: the actual cabinet exceedance **denominator**, computed as `sweep_cab_budget_fast(cohort_hist_records, cab_p99_W)` (line 428). Depends on `cab_p99_W`. `cab_p99_W` is scaled by `CAB_SCALE` at lines 262-263 BEFORE `B_cab_hist` is computed. Therefore `B_cab_hist` changes with `CAB_SCALE`.

- Both `B_cab_hist` and `B_cab_h` (numerator) change with `CAB_SCALE`. The ratio `B_cab_ratio = B_cab_h / B_cab_hist` is nonlinear and cannot be asserted without simulation output.

The prior observation that `B_ref_s = 2449.93` is constant for sc30 across all CAB_SCALE values (from sensitivity run files) is trivially true but was incorrectly labeled as evidence about the cabinet denominator. It is not.

**Correction:** All plan language now explicitly distinguishes thermal B (B_ref_s, B_primary_h, B_primary_ratio) from cabinet B (B_cab_hist, B_cab_h, B_cab_ratio). No assertion is made about whether the cabinet denominator is fixed or recomputed until simulation output is available. Full audit in `e1_cabinet_denominator_audit.json`.

---

## New Files Written

| File | Purpose |
|---|---|
| `ROUND3_PLAN_AMENDMENT_3.md` | This document |
| `r2_equivalence_schema.json` | Authoritative field schema extracted from frozen r2 merged file |
| `e1_cabinet_denominator_audit.json` | Line-by-line audit of B_cab_ratio denominator in r2_sensitivity_run.py |
| `equivalence_checker_selftest.json` | 10/10 self-test results for check_r3_legacy_equivalence.py |

## Files Updated

| File | Changes |
|---|---|
| `check_r3_legacy_equivalence.py` | Absent-key hard fail; nullable categorical fix; extra-scenario rejection; duplicate detection; 10 self-tests |
| `THIRD_REVIEW_ANALYSIS_PLAN.md` | v2.1→v2.2; §E/§J E1 terminology; §Q F2 initial matrix; §D support gate; §B7 held-out terminology |
| `third_review_plan.json` | v2.1→v2.2; e1_reinterpretation corrected; initial_f2_run_matrix added; amendment_3_status |

---

## Stop Condition

STOP. Do not execute R3-0 yet. This amendment must be committed and reviewed before any policy simulation.

After this commit is accepted:
1. R3-0 (legacy equivalence on sc30–sc54) may be authorized
2. R3-0 is a software-equivalence test, not a scientific result
3. F2 (first scientifically informative run) requires Task D first
