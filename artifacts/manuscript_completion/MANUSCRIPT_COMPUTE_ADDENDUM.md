# Manuscript Completion Compute Addendum

**Version:** 1.0
**Date authored:** 2026-10-06
**Status:** FROZEN BEFORE ANY NEW SIMULATION — commit before executing C1, C2, C3, C4, or C5

**Governance:** This document must be committed at its current state before any new simulation run begins. If code must change after this freeze, stop, amend this document explicitly, commit the amendment, rerun all affected gates, and wait for explicit re-authorization.

---

## 0. Frozen Input Artifacts

All simulations below depend exclusively on the following frozen artifacts. No simulation
may proceed if any SHA256 does not match.

| Artifact | Path | SHA256 (full 64 hex) |
|---|---|---|
| Corrected cabinet reference | `artifacts/revision3/f2_local_scheduling_reference.json` | `71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34` |
| Replay denominator | `artifacts/revision3/f2_replay_denominator.json` | `b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48` |
| r2 challenge merged (Exp 2 primary) | `artifacts/revision2/results/gate_f_sc30-54_all_r2challenge_merged.json` | `181161082cbf79e32fb138779af20327fd026d5383d70a942e7373a64d635a71` |
| Exp 1 merged (sc5-29) | `artifacts/revision1/results/gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json` | `1ec4eba733df43fb6ecf18fabdc354760f0ebbc4decb5858c53f3e06ef1f34f9` |
| Corrected-ref F2 raw result | `artifacts/revision3/results/gate_f_sc30-54_1p25_r3f2local.json` | `5982264fcf719cc4746b23ae6ef0aaf9e22a9700e4b6ef3e19e49a98b5460dca` |
| Exp 2 challenge analysis | `artifacts/revision2/challenge_analysis.json` | `3a8bbd0aba95209e8d383bb94f9b57b93df98a37d8cfa7423d8db0db115edac4` |
| Round-3 plan | `artifacts/revision3/third_review_plan.json` | `7a194fad3dde6a739189f8bf5957279601fc0ac793692e521c2793dc3a7f8550` |
| r3 runner (F2 two-policy run) | `artifacts/revision3/r3_gate_f_run.py` | `3bc8bcb07defd342d925e3eed2e5258be5424a7d596201c0246ba41d0613a6e1` |
| r2 runner commit | — | git commit `5733b73bd715157f479821d969aac99811eee0d7` |
| r1 runner commit | — | git commit `709c78a0df967f63a590ed4740ea3c3c7796136c` |

**Replay denominator key values:**
- `B_cab_hist_F2_replay_h` = 871.3691666666647 h (scheduling denominator for corrected reference)
- `B_cab_hist_F1_h` = 67917.76333331302 h

**Corrected reference thresholds:**
- Per-cabinet Q_F2_local_kW from `f2_local_scheduling_reference.json`
- Fleet median Q_F2_local = 211.6 kW vs fleet median Q_F1 = 92.5 kW (ratio ~2.29x)
- Late cabinets (2600, 2601, 2602): F1 = 71.2 / 74.0 / 68.7 kW; F2 = 161.8 / 173.5 / 163.1 kW

---

## Common Estimand Definition (all runs)

    delta_lo(A, B) = C_lower(A) - C_upper(B)   [conservative lower bound of advantage]
    delta_hi(A, B) = C_upper(A) - C_lower(B)   [conservative upper bound of advantage]

    verdict per scenario:
      "A" if delta_lo > 0   (A definitively outperforms B)
      "B" if delta_hi < 0   (B definitively outperforms A)
      "I" otherwise         (intervals overlap; indistinguishable)

**Left-boundary rule:**
- `status == "left_boundary"` (C_lower = 0, C_upper = 0): policy cannot schedule any
  synthetic workload at this ratio. Include as [0, 0]. Count as `n_base_infeasible`.
  Exclude from bracket-width summaries. delta_lo = 0 - 0 = 0 (indistinguishable unless
  the other policy also has C_lower = 0).
- `status == "exact_bracket", C_lower = 0, C_upper > 0`: include in delta_lo as
  0 - C_upper_B (correctly negative or zero). Count as `n_floor_at_zero`.

**Bootstrap configuration (all runs):** 5,000 draws, seed 9999, percentile method,
95% CI. Paired bootstrap over scenarios for median delta_lo.

**Censoring:** Report `n_right_censored` per policy. Right-censored scenarios are
excluded from pairwise comparisons.

---

## C1 — Experiment 1 Under Corrected Concurrent-Load Reference

### Purpose
Test whether the choice-ratio experiment's conclusions survive correction of the cabinet
reference. Experiment 1 (sc5-sc29) used the job-contribution cabinet reference in all
frozen results. This run uses the corrected concurrent-load reference with replay-matched
denominator, keeping all other parameters identical.

### Scenarios
**Exactly sc5-sc29** (25 scenarios). Same scenario seeds as frozen revision1 run:
sourced from `artifacts/revision1/results/gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json`
`scenario_results[*].scen_seed` and `wl_seed`. Master SCENARIO_SEED = 42.

### Policies
Mandatory:
- `full_fp`
- `full_random`
- `full_loc` (location-only: mean FA_2024 over nodes sharing the same structural
  position key `chassis + '_' + slot + '_' + board + '_' + node_pos`)

Preferred (include if the frozen Experiment 1 runner already supports without modification):
- `full_fp_spread`

Do NOT add policies not in the frozen Experiment 1 runner. Do NOT add placebos or
position_template — those are Experiment 2 constructs.

### Ratios
Mandatory: r = 1.25
Preferred (include if marginal compute is negligible): r = 1.5, 2.0, 4.0, 8.0

### Cabinet Reference
- Mode: `corrected_timeweighted_total_p99_local`
- Threshold source: `artifacts/revision3/f2_local_scheduling_reference.json`
  SHA256: `71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34`
- Denominator: `B_cab_hist_F2_replay_h` = 871.3691666666647 h
  from `artifacts/revision3/f2_replay_denominator.json`
  SHA256: `b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48`

### Runner
**TO BE DETERMINED BEFORE IMPLEMENTATION.** Options:
(a) Modify `r1_gate_f_run.py` (709c78a) to support `corrected_timeweighted_total_p99_local`
    mode, loading from `f2_local_scheduling_reference.json` and `f2_replay_denominator.json`.
(b) Modify `r3_gate_f_run.py` (4fa1b50) to support sc5-sc29 scenarios and
    `full_loc` policy.

Freeze runner SHA256 before execution. Record in output file header.

**Preflight gates (all required before launch):**
1. `py_compile` clean on runner
2. `ruff --select F821` clean on runner
3. SHA256 of F2 cabinet reference matches frozen value
4. SHA256 of replay denominator matches frozen value
5. sc5 smoke: run scenario sc5, full_fp, r=1.25 — compare C_lower/C_upper against
   revision1 frozen result to confirm difference is entirely attributable to cabinet
   reference (not seed/workload change). Accept if thermal ratios (B_primary_ratio,
   S_primary_ratio) are identical and only B_cab_ratio differs.

### Primary Required Output
- A/I/B, median delta_lo, bootstrap CI for FP vs Random at r=1.25
- A/I/B, median delta_lo, bootstrap CI for Loc vs Random at r=1.25
- A/I/B, median delta_lo, bootstrap CI for FP vs Loc at r=1.25 (if Loc present)
- Absolute capacity (C_lower, C_upper median and IQR) for each policy
- First-binding constraint counts for each policy
- Left-boundary and right-censored counts for each policy

### Output File
`artifacts/manuscript_completion/results/gate_f_sc5-29_1p25_r_correctedref.json`
(include all preferred ratios in filename if run beyond r=1.25)

Do NOT overwrite any frozen revision1 result files.

### Label
"Experiment 1 (choice-ratio) under corrected concurrent-load cabinet reference.
Reference-sensitivity rerun. Post-exposure."

---

## C2 — Experiment 2 Under Corrected Reference (Seven-Policy Full Challenge)

### Purpose
Determine whether the node-specificity conclusions survive once the cabinet reference
is corrected. This is the highest-value new run.

The existing corrected-reference run (`gate_f_sc30-54_1p25_r3f2local.json`) covers only
FP and Random. C2 runs all seven policies under the corrected reference on the same
frozen Experiment 2 scenarios.

### Scenarios
**Exactly sc30-sc54** (25 scenarios). Use the frozen scenario seeds from revision2:
sourced from `gate_f_sc30-54_all_r2challenge_merged.json scenario_results[*].scen_seed`
and `wl_seed`. Challenge seed: 2042.

### Ratio
**r = 1.25 only** (mandatory).

### Policies (7)
Mandatory:
1. `full_fp`
2. `full_random`
3. `fp_withincab_placebo` — within-cabinet fingerprint permutation (see Placebo Seed section)
4. `fp_global_placebo` — global fingerprint permutation (see Placebo Seed section)
5. `position_loo` — leave-one-out position score (see Position LOO section)

Preferred (include if marginal compute is reasonable):
6. `full_fp_spread`
7. `random_spread`

Do NOT run the original `position_template` (which includes each node's own fingerprint
in its template mean) as the structural comparator. Use `position_loo` instead.

### Position LOO Definition (frozen)

For each target node i, compute its position score using FA_2024 values of OTHER nodes
sharing the same structural position, excluding node i itself.

**Scheduling key:** `pos_key = chassis + '_' + slot + '_' + board + '_' + node_pos`

**Fallback hierarchy (all levels within-chassis):**

| Level | Scope | Rule |
|---|---|---|
| 1 (primary) | same (chassis, slot, board, node_pos) | mean FA_2024 excluding target node |
| 2 | same (chassis, slot, board) | mean FA_2024 excluding target node |
| 3 | same (chassis, slot) | mean FA_2024 excluding target node |
| 4 (last resort) | global cohort | mean FA_2024 excluding target node |

Apply first level with group size >= 2 (including target). Cross-chassis fallback is
NOT permitted at levels 1-3.

**Self-inclusion guard:** Before full scenario runs, assert for every fp node that its
own FA_2024 value is absent from its LOO score computation. This requires a unit test
run before any scheduling result is accepted.

**Missing-value handling:** If a node has NaN FA_2024, assign the global cohort mean
FA_2024. Apply this BEFORE the LOO exclusion.

**Score normalization:** None. Use raw LOO mean FA_2024 as the selection score.

**Validation requirement (before scheduling run):**
- Compute Spearman rank correlation between position_loo scores and original
  position_template scores across all 2,000 fp nodes.
- Report count of nodes at each fallback level.
- Report. Do not gate on any threshold — proceed regardless. The validation is a
  diagnostic, not a pass/fail gate.

### Placebo Seeds (per-scenario, deterministic)

**CRITICAL: Use per-scenario placebo seeds derived from the Round-3 plan.**
Do NOT reuse the fixed seeds from the frozen sc30-54 challenge
(`placebo_global_perm_seed = 218767960`, `placebo_withincab_perm_seed = 365514213`).

**Seed derivation (from third_review_plan.json, frozen):**
```python
from numpy.random import SeedSequence
R3_ROOT          = 847291653
placebo_global_id    = 1
placebo_withincab_id = 2

# For scenario with array_index i (0-based; sc30=i0, sc31=i1, ..., sc54=i24):
placebo_global_seed_i    = int(SeedSequence([R3_ROOT, i, placebo_global_id]).generate_state(1)[0])
placebo_withincab_seed_i = int(SeedSequence([R3_ROOT, i, placebo_withincab_id]).generate_state(1)[0])
```

**WithinCab placebo:** permute FA_2024 scores independently within each cabinet using
`placebo_withincab_seed_i`. Nodes assigned to permuted score from the same cabinet.

**Global placebo:** permute FA_2024 scores across the entire eligible cohort using
`placebo_global_seed_i`. Nodes assigned to permuted score from anywhere in the cohort.

### CRITICAL INVARIANT (placebo)
Placebo scores affect NODE SELECTION ONLY. Temperature prediction uses the selected
node's TRUE FA_2024 value (from `FA_dict`), not its placebo-permuted score. The
thermal exceedance computation is NEVER passed `placebo_fa_dict`.

**Required unit test before first scenario:** Assert that `placebo_fa_dict` (or
equivalent) is not reachable from any code path in the thermal exceedance computation.
This test must pass before any scenario result is accepted.

### Cabinet Reference
Same as C1 (corrected concurrent-load):
- `f2_local_scheduling_reference.json` SHA256 = `71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34`
- `B_cab_hist_F2_replay_h` = 871.3691666666647 h
  SHA256 = `b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48`

### Runner
Freeze SHA256 before execution. Must be based on `r3_gate_f_run.py` or a new runner
extending it to support all 7 policies and the position_loo and per-scenario placebo
logic. Record runner SHA256 in output file header.

**Preflight gates (all required before launch):**
1. `py_compile` and `ruff --select F821` clean
2. SHA256 of F2 reference and replay denominator match frozen values
3. Position LOO self-inclusion unit test passes (for every fp node, its own FA_2024
   is excluded from its LOO computation)
4. Placebo thermal-invariant unit test passes
5. sc30 smoke: FP and Random results must match the frozen
   `gate_f_sc30-54_1p25_r3f2local.json` sc30 values exactly (max abs diff <= 1e-9)
6. Seed canonical check: reproduce placebo_global_seed for i=0 (sc30) using derivation
   above; expected value = **2514122466**. Reproduce placebo_withincab_seed for i=0;
   expected value = **4138460386**. Abort if either mismatches.

### Eight Required Comparisons
Primary:
1. FP_vs_Random

Secondary (node-specificity):
2. FP_vs_WithinCabPlacebo
3. FP_vs_GlobalPlacebo
4. FP_vs_PositionLOO

Spread (if spread policies run):
5. FPSpread_vs_RandomSpread
6. FPSpread_vs_FP
7. RandomSpread_vs_Random

Additional:
8. FPSpread_vs_PositionLOO (if spread policies run)

**Multiplicity family:** All 8 comparisons (or 4 mandatory comparisons if spread
policies not executed). Holm-Bonferroni correction over the family.

For each comparison report:
- A/I/B counts
- n_both_base_infeasible
- Median delta_lo and delta_hi
- Bootstrap 95% CI (seed=9999, n=5000)
- Sign test p (two-sided, decisive scenarios only, H0: P(A|decisive)=0.5)
- Holm-adjusted p over the comparison family
- Absolute capacity (median C_lower, C_upper, IQR) per policy
- First-binding constraint counts per policy
- Left-boundary counts per policy

### Output File
`artifacts/manuscript_completion/results/gate_f_sc30-54_1p25_r_correctedref_7pol.json`

Do NOT overwrite frozen revision2 or revision3 result files.

### Label
"Experiment 2 (node-specificity challenge) under corrected concurrent-load cabinet
reference, full seven-policy run. Post-exposure reviewer-requested robustness check."

---

## C3 — Thermal Threshold Sensitivity

### Purpose
Test sensitivity to T_thr now that the corrected-reference FP is thermally constrained
(B_ratio binds first in 25/25 scenarios). Uses Experiment 2 scenarios.

### Scenarios
Exactly sc30-sc54 (25 scenarios), same frozen seeds as C2.

### Ratio
r = 1.25 (mandatory).

### Policies
- `full_fp`
- `full_random`

### Threshold Grid (frozen; verify against authoritative artifact before implementation)

Source: `artifacts/revision1/results/m4_threshold_audit.json` (or equivalent)
Population: 3,940 contributing pre-2025 jobs (full population, not 462-job subset)

| Label | T_thr (°C) | Source |
|---|---|---|
| T_p90 | **61.875** | p90 of contributing pre-2025 jobs |
| T_p95 (primary) | **63.625** | p95 of contributing pre-2025 jobs |
| T_p99 | **66.6625** | p99 of contributing pre-2025 jobs |

**STOP AND REPORT if the artifact returns different values.** Do not silently substitute.

### Denominator Recomputation Rule (mandatory)
At EACH threshold T_thr, recompute:
- `B_ref_s` (historical node-level thermal exceedance-hours) using that T_thr
- `S_ref_s` (historical node-level severity-weighted thermal exposure) using that T_thr
- `B_cab_hist` (historical cabinet exceedance) using the corrected concurrent-load
  reference thresholds AND that T_thr for the node-level thermal budget

Do NOT reuse the primary T_p95 denominators while changing only T_thr. All thermal
budget denominators must be recomputed at each threshold.

Cabinet reference (Q_c thresholds) remains the corrected concurrent-load reference
(`f2_local_scheduling_reference.json`) for all three threshold runs.

### Output
For each T_thr: A/I/B, median delta_lo, bootstrap CI, absolute capacity, first-binding
constraints, left-boundary counts.

Report each threshold result independently before any cross-threshold summary.

### Output File
`artifacts/manuscript_completion/results/gate_f_sc30-54_1p25_r_correctedref_thrsens.json`

### Label
"Exploratory threshold sensitivity. T_thr grid = {p90, p95, p99}. Post-exposure.
Primary T_thr = p95 = 63.625 deg-C."

---

## C4 — Late-Cabinet Leverage Diagnostic

### Purpose
Determine whether cabinets 2600, 2601, 2602 (commissioned 2024-07-18 through
2024-11-22) disproportionately drive the FP capacity advantage under the corrected
reference.

**No new simulation required for the initial diagnostic.** Extract from existing
corrected-reference C2 output (or the existing F2 two-policy result if C2 is not yet
complete).

### Required Metrics (per scenario, from existing outputs)

For FP and Random at r=1.25 under corrected reference, around the capacity crossing:
- Fraction of selected synthetic cohort node-hours from cabinets 2600, 2601, 2602
- Fraction of selection events touching those cabinets
- Share of cohort nodes represented by those cabinets (78/2000 = 3.9%)
- Expected share under neutral allocation (3.9%)
- Enrichment ratio: (observed share) / (expected share)
- Distribution of enrichment across 25 scenarios
- Whether those cabinets are disproportionately responsible for FP's capacity gain
  (defined as: does removing them from the eligible set change the sign of delta_lo
  for any scenario? — answer from data, not from new simulation)

Additionally, from existing fingerprint data:
- FA_2024 mean/median/IQR for cabinets 2600, 2601, 2602 vs early cohort (74 cabinets)
- Training jobs per node: mean/min/max for late vs early cabinets
- First observed date in collection record
- Corrected concurrent-load threshold vs job-contribution threshold for each late cabinet

### Stopping Rule
After producing diagnostics: **STOP and present to user.**

Do not run any exclusion rerun. The methodological decision (whether to exclude late
cabinets, and if so whether to recompute reference denominators for the reduced cohort
or hold them fixed) must be made explicitly before any exclusion run.

### Output File
`artifacts/manuscript_completion/late_cabinet_leverage_diagnostic.json`
`artifacts/manuscript_completion/LATE_CABINET_LEVERAGE_DIAGNOSTIC.md`

---

## C5 — Calendar Stability (Optional)

### Status
Do not block C1-C4. Only run if explicitly requested after C1-C4 are reviewed.

### If run: parameters
- Split boundary: median `start_time` of the 2,637 frozen base-cohort test-set jobs.
  Compute and record the exact timestamp BEFORE any run.
- New scenarios: sc55-sc79 (seeds from `third_review_plan.json placebo_and_seed_plan`)
- Use corrected concurrent-load cabinet reference
- Policies: `full_fp`, `full_random`
- Ratio: r=1.25
- Minimum per-node support for inclusion: to be defined before looking at results
- Report each half separately; no pooling before reporting both

---

## Multiplicity and Interpretation Rules

### Primary comparison family (C2)
8 pre-specified comparisons (or 4 mandatory if spread policies absent).
Holm-Bonferroni correction. Report raw and adjusted p-values for all sign tests.

### C1 comparison family
3 comparisons: FP vs Random, Loc vs Random, FP vs Loc.
Holm-Bonferroni correction over this family.

### C3 interpretation
Label all results "exploratory threshold sensitivity." Do not select a "robust range"
that excludes threshold-threshold disagreements. Report all three independently.

### Outcome-independent rules
- If C2 corrected-reference FP_vs_Random result reverses direction vs frozen
  job-contribution result: mandatory disclosure in abstract.
- If C4 shows late-cabinet exclusion reverses FP_vs_Random: stop, report, await ruling.
- These rules apply regardless of what the results show.

---

## Required Per-Run Procedure

Before each run:
1. Start from clean git status (`git status` must show nothing uncommitted)
2. Print and record git HEAD
3. Print and record runner SHA256
4. Print and record all input artifact SHA256 values

After each run:
1. Compute SHA256 of raw output JSON
2. Commit raw output before any derived analysis
3. Run analysis from raw output in a separate script
4. Commit derived analysis separately

If interrupted: record and invalidate partial output before restart. Do not resume
from checkpoint unless this addendum explicitly permits it (none of C1-C5 permit
checkpoint reuse by default).

If any preflight fails: STOP. Report before restarting.

---

## Quality Gates (before committing this addendum)

- [ ] All scenario sets are explicit
- [ ] All policies are explicit
- [ ] All ratios are explicit
- [ ] All thresholds are explicit
- [ ] All random seeds and derivations are explicit
- [ ] All primary/secondary contrasts are explicit
- [ ] Multiplicity families are explicit
- [ ] Censoring/floor rules are explicit
- [ ] Bootstrap method and seed are explicit
- [ ] Corrected cabinet reference SHA is explicit
- [ ] Replay denominator SHA is explicit
- [ ] Runner commit/hash is marked TO-BE-FROZEN or frozen
- [ ] No result-dependent decision is left open
- [ ] `py_compile` clean on all new Python (TO BE VERIFIED before implementation)
- [ ] `ruff --select F821` clean (TO BE VERIFIED before implementation)
- [ ] Existing unit and regression tests pass (TO BE VERIFIED before implementation)

---

## Estimated Runtimes

| Run | Scenarios | Policies | Ratios | Estimate |
|---|---|---|---|---|
| C1 (Exp 1 corrected ref) | 25 (sc5-29) | 3-4 | 1-5 | 4-8 hours |
| C2 (Exp 2 corrected ref, 7-pol) | 25 (sc30-54) | 5-7 | 1 | 8-14 hours |
| C3 (threshold sensitivity) | 25 (sc30-54) | 2 | 1 per threshold (x3) | 6-9 hours |
| C4 (late-cabinet diagnostic) | 0 (from existing) | — | — | < 1 hour |
| C5 (optional) | 25 (sc55-79) | 2 | 1 | 3-5 hours |

Estimates based on F2 two-policy sc30-54 elapsed time of ~9,562 seconds (~2.7 hours).
C2 adds 5+ policies at r=1.25 only; C3 runs 3x the F2 setup with recalculated denominators.

**Total mandatory (C1+C2+C3+C4):** approximately 18-32 hours wall time.

---

## Execution Order

Authorize and execute in this order:
1. C4 (no simulation — extract from existing F2 output; present diagnostic)
2. C1 (corrected reference for Experiment 1; verify runner first)
3. C2 (corrected reference for Experiment 2, seven policies)
4. C3 (threshold sensitivity)
5. C5 only if explicitly requested

**DO NOT start C1, C2, C3, or C5 until explicitly authorized after reviewing this addendum.**
