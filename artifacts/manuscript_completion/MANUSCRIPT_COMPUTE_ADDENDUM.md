# Manuscript Completion Compute Addendum

**Version:** 1.3
**Date authored:** 2026-10-06
**Amendment date:** 2026-10-07 (v1.3)
**Status:** ALL PREFLIGHT GATES PASSED — awaiting explicit authorization for C1/C2/C3 production runs

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
| C1 manuscript runner | `artifacts/manuscript_completion/runners/c1_gate_f_run.py` | `7cb51ebcf541d9c04b932ef879ce5095d34195452ef88151418d01ce844b41ba` |
| C2 manuscript runner (bug-fixed) | `artifacts/manuscript_completion/runners/c2_gate_f_run.py` | `e0de9d35a99715bc05c08177b08ad399bb25902fb492ef3487223135b7d3c44a` |
| C3 manuscript runner | `artifacts/manuscript_completion/runners/c3_gate_f_run.py` | `3b4e9825462a5f8b80bc6f76c6938bcf88d460d12f782210474b38573654e91c` |
| Exp 1 unr result (sc5-29) | `artifacts/revision1/results/gate_f_sc5-29_unr.json` | `3a119505e5f17b2e7d9abea1f640f5c2ed38a3eed1825e3fdd8bc0c6567f6356` |
| Exp 1 r=1.0 result (sc5-29) | `artifacts/revision1/results/gate_f_sc5-29_1p0.json` | `b409fe8504ef4822a51ca28ea1936d686c67b2aaa3328e94d2c82e80a2d4b535` |

**r1 runner provenance (C1):**
- Scientific freeze commit: `e2df32a883fff8f26d93511483dfdae63fe0b730` — SHA256 of `r1_gate_f_run.py` at this commit: `ce03becd7d8436768cde3d2090bf88dd99fe20d5777ecf57cb7f7f77941173eb`
- Checkpoint-enhanced commit: `709c78a0df967f63a590ed4740ea3c3c7796136c` — SHA256 of `r1_gate_f_run.py` at this commit: `50bbcb3be69519fc66dcf3bcae15909102177b52dd80da4ebdfb64fbbaa123f2`
- Diff: the 709c78a runner adds ONLY checkpoint/resume infrastructure (~40 lines: checkpoint load on startup, skip-if-completed per scenario, write-after-each-scenario, delete-on-completion). Zero changes to scenario seeds, workload draws, policy logic, thermal model, hash function, or any scientific computation.
- The unr and 1p0 runs were executed at e2df32a. The 5-ratio merged run was executed at 709c78a.
- Conclusion: runner bytes differ, but the difference is operational only. C1 runner may be derived from 709c78a bytes (operational improvement retained); provenance must record e2df32a as the scientific freeze.

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
- `status == "left_boundary"` (C_lower = 0, C_upper = 0): represent as interval [0, 0].
  Count as `n_base_infeasible`. Exclude from bracket-width summaries.
  Apply the universal delta formulas without special-casing:
    - A=[0,0], B=[x,y] with x>0: delta_hi = 0-x < 0 → definite B
    - A=[x,y] with x>0, B=[0,0]: delta_lo = x-0 > 0 → definite A
    - A=[0,0], B=[0,0]: delta_lo=0, delta_hi=0 → indistinguishable
  Do NOT default to indistinguishable whenever a left_boundary is present.
- `status == "exact_bracket", C_lower = 0, C_upper > 0`: represent as [0, C_upper].
  Count as `n_floor_at_zero`. Apply universal delta formulas as-is.

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
`scenario_results[*].scen_seed` and `wl_seed` (the 5-ratio file). Confirm that
the same seeds appear in the unr.json and 1p0.json files. Master SCENARIO_SEED = 42.

### Policies (exact frozen Experiment 1 set)
Source: `gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json` `gate_f_policies` field.

1. `full_random`
2. `full_fp`
3. `full_loc`
4. `full_fp_spread`

Run all four. Do not add or remove any policy. Do not add placebos or `position_template`
(those are Experiment 2 constructs).

### Ratios (exact frozen Experiment 1 set — seven ratios)
Source: `gate_f_heldout_analysis.json` `ratios` field (authoritative frozen design).

1.0, 1.25, 1.5, 2.0, 4.0, 8.0, unrestricted

Run ALL SEVEN ratios. Do not omit r=1.0 or unrestricted.
- r=1.0 is the hard no-choice negative control (no synthetic workload admitted).
- unrestricted reproduces the M4 endpoint under the corrected reference (baseline
  equivalent of the main capacity replay). Historical execution: `gate_f_sc5-29_unr.json`.
- r=1.0 historical execution: `gate_f_sc5-29_1p0.json`.

Note: the merged 5-ratio file (`gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json`) does not
list 1.0 or unrestricted in its `gate_f_ratios` field because those were run as
separate executions. The authoritative full-design artifact is `gate_f_heldout_analysis.json`
which lists all seven.

### Cabinet Reference
- Mode: `corrected_timeweighted_total_p99_local`
- Threshold source: `artifacts/revision3/f2_local_scheduling_reference.json`
  SHA256: `71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34`
- Denominator: `B_cab_hist_F2_replay_h` = 871.3691666666647 h
  from `artifacts/revision3/f2_replay_denominator.json`
  SHA256: `b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48`

### Runner
Create a NEW runner file:
`artifacts/manuscript_completion/runners/c1_gate_f_run.py`

Base it on `artifacts/revision1/analysis/r1_gate_f_run.py` at commit
`709c78a0df967f63a590ed4740ea3c3c7796136c`.
Scientific freeze commit is `e2df32a883fff8f26d93511483dfdae63fe0b730`; 709c78a adds
checkpoint/resume infrastructure only (see Section 0 for full diff characterization).
Do NOT modify the historical runner file.

**Permitted patches only:**
1. Load cabinet thresholds from `f2_local_scheduling_reference.json` (corrected reference)
   instead of the original job-contribution envelope source.
2. Load `B_cab_hist_F2_replay_h` = 871.3691666666647 h from `f2_replay_denominator.json`
   as the cabinet historical denominator instead of the original F1 value.
3. Update default output path to
   `artifacts/manuscript_completion/results/gate_f_sc5-29_correctedref_*.json`.

**Everything else is preserved unchanged:**
scenario seeds, workload draws, candidate exposure logic, all four policy logics
(full_random, full_fp, full_loc, full_fp_spread), utilization rules, thermal model
(B_ref_s, S_ref_s computation), all non-cabinet accounting.

Do NOT combine C1 and C2 in the same runner.

Freeze SHA256 of `c1_gate_f_run.py` before execution. Record in output file header.

**Preflight gates (all required before launch):**
1. `py_compile` clean on runner
2. `ruff --select F821` clean on runner
3. SHA256 of F2 cabinet reference matches frozen value
4. SHA256 of replay denominator matches frozen value
5. sc5 smoke: run scenario sc5 across all four policies at r=1.25. For every row where
   policy and lambda_val match a row in the frozen Experiment 1 result file, require
   exact equality (max abs diff <= 1e-9) for ALL fields that are invariant to the cabinet
   reference: scen_seed, wl_seed, B_ref_s, S_ref_s, B_primary_h, S_primary_Cdoth,
   B_secondary_h, syn_node_hours, n_syn_admit, n_drop_*, n_base_unserved, workload
   identifiers if serialized, and utilization quantities.
   ONLY B_cab_ratio (and capacity_unlock_pct, crossing_lambda, feasibility status) may
   differ. If any invariant field mismatches, STOP before running the 25-scenario run.

### Frozen Comparison Family (five pairs, all seven ratios)
Source: `gate_f_heldout_analysis.json` `comparisons_frozen` field.

1. FP_vs_Random
2. Loc_vs_Random
3. FPSpread_vs_Random
4. FPSpread_vs_FP
5. FPSpread_vs_Loc

Report each comparison at EVERY ratio (7 ratios × 5 pairs = 35 cells).
Use the same reporting structure as the frozen analysis:
- A/I/B counts (n_definitely_A, n_indistinguishable, n_definitely_B)
- Median delta_lo and delta_hi
- bootstrap 95% CI on delta_lo and delta_hi (seed=9999, n=5000)

**No Holm-Bonferroni correction for C1.** The frozen Experiment 1 analysis did not
specify a Holm family; adding one post-exposure would invent a new inferential framework.
Report bootstrap CIs only. Exploratory sign-test p-values may be listed separately,
labeled clearly as "exploratory, post-hoc" and not used for any primary claim.

### Additional Required Output
- Absolute capacity (C_lower, C_upper median and IQR) for each policy at each ratio
- First-binding constraint counts for each policy
- Left-boundary and right-censored counts for each policy at each ratio
- Seven-ratio, five-curve structure mirroring the frozen Experiment 1 analysis output

### Output File
`artifacts/manuscript_completion/results/gate_f_sc5-29_correctedref_all7r.json`

Do NOT overwrite any frozen revision1 result files.

### Label
"Experiment 1 (choice-ratio) under corrected concurrent-load cabinet reference.
Reference-sensitivity rerun. Post-exposure. 4 policies, 7 ratios."

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

### Policies (7 — all mandatory)
All seven policies are mandatory. The Holm multiplicity family is fixed at 8 comparisons
regardless of results.

1. `full_fp`
2. `full_random`
3. `fp_withincab_placebo` — within-cabinet fingerprint permutation (see Placebo Seed section)
4. `fp_global_placebo` — global fingerprint permutation (see Placebo Seed section)
5. `position_loo` — leave-one-out position score (see Position LOO section)
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

**Pre-scheduling diagnostic (required before ANY C2 scenario is run):**

Compute position_loo scores for all fp nodes WITHOUT scheduling. Report:
- N nodes assigned at each fallback level (1, 2, 3, 4/global)
- N nodes with NaN FA_2024 (if any, report and STOP before C2 execution)
- Spearman rank correlation between position_loo scores and original
  position_template scores across all 2,000 fp nodes (using only finite values)

Stop condition: If a material number of nodes require fallback beyond level 1 (same
exact position group), STOP and report to user before scheduling. Do not use this
diagnostic to change the fallback hierarchy — hierarchy is frozen here. The user
must rule on whether to proceed before any scheduling result is accepted.

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
Create a NEW runner file:
`artifacts/manuscript_completion/runners/c2_gate_f_run.py`

Base it on the FROZEN Experiment 2 challenge runner at git commit
`5733b73bd715157f479821d969aac99811eee0d7` (`artifacts/revision2/r2_gate_f_run.py`).
Do NOT modify the historical runner file.

**Port into the new runner:**
1. Corrected concurrent-load cabinet reference (`f2_local_scheduling_reference.json`)
   and replay-matched denominator (`B_cab_hist_F2_replay_h` = 871.3691666666647 h)
2. Per-scenario placebo seeds (SeedSequence derivation from R3_ROOT as specified above)
3. New `position_loo` policy with 4-level LOO fallback (as specified above)
4. Output path `artifacts/manuscript_completion/results/gate_f_sc30-54_1p25_correctedref_7pol.json`

Do NOT combine C1 and C2 in the same runner.

Freeze SHA256 of `c2_gate_f_run.py` before execution. Record in output file header.

**Preflight gates (all required before launch):**
1. `py_compile` and `ruff --select F821` clean
2. SHA256 of F2 reference and replay denominator match frozen values
3. Position LOO self-inclusion unit test passes (for every fp node, its own FA_2024
   is excluded from its LOO computation)
4. Placebo thermal-invariant unit test passes
5. sc30 smoke: for full_fp and full_random at sc30, ALL scientific fields that are
   invariant to policy logic must match the frozen `gate_f_sc30-54_1p25_r3f2local.json`
   sc30 rows exactly (max abs diff <= 1e-9), including scen_seed, wl_seed, B_ref_s,
   S_ref_s, B_primary_h, S_primary_Cdoth, B_secondary_h, B_cab_ratio, capacity_unlock_pct,
   and C_lower/C_upper. If any mismatches, STOP before the 25-scenario run.
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

**Multiplicity family:** Fixed at 8 comparisons. All seven policies are mandatory,
so all eight comparisons are required. Holm-Bonferroni correction over the family.

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
T_thr governs NODE-LEVEL thermal budgets only. At each threshold recompute:
- `B_ref_s` — historical node-level thermal exceedance-hours, using that T_thr
- `S_ref_s` — historical node-level severity-weighted thermal exposure, using that T_thr

Hold fixed across all three threshold runs:
- Cabinet Q_c thresholds from `f2_local_scheduling_reference.json`
- `B_cab_hist_F2_replay_h` = 871.3691666666647 h
- Cabinet topology and reference support window

These are electrical cabinet quantities. They do NOT depend on node thermal T_thr.

### P95 Center Point (existing result — no new simulation)
The accepted corrected-reference P95 result is:
`artifacts/revision3/results/gate_f_sc30-54_1p25_r3f2local.json`
SHA256: `5982264fcf719cc4746b23ae6ef0aaf9e22a9700e4b6ef3e19e49a98b5460dca`

Do NOT rerun the full 25-scenario P95 experiment. Use this file as the P95 center point.

**Before running P90 or P99:** verify that the new C3 runner reproduces sc30 at P95
exactly (max abs diff <= 1e-9 on all comparable scientific fields vs the accepted
P95 result). If the sc30 reproduction fails at P95, STOP — do not proceed to P90/P99.

**Full 25-scenario runs:** P90 only and P99 only. Two new runs total.

### Threshold Verification Artifact (required before C3 implementation)
The threshold values 61.875 / 63.625 / 66.6625 °C are stored in:
- `artifacts/revision1/results/m4_threshold_audit.json`
- SHA256: `2ece0a19f63e3e147ae7c5f19765a2ebcd4144470c852004ef4426c2178adbcc`
- Git commit: `2733d84`
- Source: `r1_m4_threshold_audit.py` on full population of 3,940 contributing pre-2025
  jobs (77,627 node-job pairs), timestamp 2026-09-29T16:30:03Z

Before C3 implementation, independently reproduce these three percentile values from
the canonical frozen pre-2025 calibration population using a NEW verification script.
Create and commit a dedicated threshold-verification artifact:
`artifacts/manuscript_completion/c3_threshold_verification.json`

This artifact must contain: source population definition, N jobs, N node-job pairs,
exact percentile method, reproduced P90/P95/P99 values, SHA256 of m4_threshold_audit.json.

If independently reproduced values differ from 61.875 / 63.625 / 66.6625 °C: STOP.

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

**Data availability assessment (verified 2026-10-07):**

The accepted corrected-reference two-policy result (`gate_f_sc30-54_1p25_r3f2local.json`)
serializes AGGREGATE lambda-row quantities only. Per-lambda-row fields include:
`syn_node_hours`, `n_syn_admit`, `mean_F_syn`, `cab_span_median`, and aggregate
selector-eligible-count percentiles. There are NO per-cabinet selection counts,
per-cabinet node-hours, or event-level placement records.

**C4 per-scenario metrics CANNOT be extracted from the existing two-policy raw result.**
C4 must wait for C2. Do not attempt C4 from the current two-policy result.

If C2 serializes per-cabinet selection counts (required; runner must emit cabinet-level
accounting for this to be possible), C4 can proceed after C2 completes. If C2 does NOT
serialize per-cabinet data, a separately governed diagnostic replay will be required.

**C2 runner requirement (added):** The C2 runner must serialize, for each scenario and
policy around the capacity-crossing lambda, a per-cabinet breakdown of:
- Selected synthetic node-hours by cabinet ID
- Selection event count by cabinet ID

Record this as a `cabinet_accounting` sub-field in each lambda row. This is the only
way to enable C4 from C2 output.

### Required Metrics (from C2 output, if per-cabinet data serialized)

For FP and Random at r=1.25 under corrected reference, around the capacity crossing:
- Fraction of selected synthetic cohort node-hours from cabinets 2600, 2601, 2602
- Fraction of selection events touching those cabinets
- Share of cohort nodes represented by those cabinets (78/2000 = 3.9%)
- Expected share under neutral allocation (3.9%)
- Enrichment ratio: (observed share) / (expected share)
- Distribution of enrichment across 25 scenarios

Additionally, from existing fingerprint data:
- FA_2024 mean/median/IQR for cabinets 2600, 2601, 2602 vs early cohort (74 cabinets)
- Training jobs per node: mean/min/max for late vs early cabinets
- First observed date in collection record
- Corrected concurrent-load threshold vs job-contribution threshold for each late cabinet

### Stopping Rule
After producing diagnostics: **STOP and present to user.**

No exclusion simulation is authorized. C4 is diagnostic only. Do not proceed to any
late-cabinet exclusion run until explicitly authorized after reviewing the diagnostic.

### Output File
`artifacts/manuscript_completion/late_cabinet_leverage_diagnostic.json`
`artifacts/manuscript_completion/LATE_CABINET_LEVERAGE_DIAGNOSTIC.md`

---

## C5 — Measurement Robustness: Calendar Stability of Fingerprint Predictions (Optional)

### Status
Do not block C1-C4. Only run if explicitly requested after C1-C4 are reviewed.

### Purpose
Verify that the frozen pre-2025 fingerprint (FA_2024) retains predictive validity
for thermal outcomes in prospective 2025 node-job observations. This is a PREDICTIVE
VALIDITY CHECK on the fingerprint itself — not a new scheduling experiment.

### What this is NOT
- Not a new scheduling simulation
- Not a new scenario replay
- Not a fingerprint refit or update

### Fixed Split
**2025-07-01 00:00:00 UTC** (hard-coded; do not derive from data centroids).
Before looking at any outcome Y values, freeze and commit a minimum per-node support
rule (minimum number of 2025 observations required for a node to be included in each
half). Record this threshold before examining results.

### Fingerprint
Use the frozen pre-2025 fingerprint FA_2024 unchanged. No refit.

### Outcome Construction (must match primary prospective measurement exactly)

For each qualifying 2025 node-job observation (i, j):

    DeltaT_p95_ij = T_p95_ij - T_p95_j

where T_p95_ij is node i's time-wise T_p95 from available GCD channels in job j,
and T_p95_j is the job-level mean T_p95 across all qualifying nodes in job j.

For each node within each calendar half, using only observations in that half:

    Y_i_half = MEDIAN_j( DeltaT_p95_ij )

Use the **median** across qualifying job-level values. Do NOT use the arithmetic mean.

This construction matches the primary prospective validation in the manuscript exactly.

### Eligible Nodes and Observations
- Use existing prospective 2025 node-job observations
- Partition strictly by job start time relative to 2025-07-01 00:00:00 UTC
- Early-2025 half: job start < 2025-07-01 00:00:00 UTC
- Late-2025 half: job start >= 2025-07-01 00:00:00 UTC
- BEFORE reading any Y values: freeze and commit minimum jobs-per-node threshold (one
  value applies to both halves)
- Apply the frozen support rule to each half independently

### Required Outputs (both halves independently; no pooling before reporting)
For each half separately:
- N eligible nodes (meeting minimum support threshold)
- Pearson r(FA_2024, Y_i_half) across eligible nodes
- Spearman rho(FA_2024, Y_i_half) across eligible nodes
- Frozen no-refit R²:

      R2_frozen = 1 - sum_i[(Y_i - F_i_2024)^2] / sum_i[(Y_i - mean(Y))^2]

  where the sum is over eligible nodes in that half, Y_i = Y_i_half, and F_i_2024
  is the frozen pre-2025 fingerprint. Do NOT fit a slope or intercept. Do NOT use
  regression coefficients from any existing model. This is a direct no-refit prediction.

Additionally, for nodes present in BOTH halves:
- Pearson r(Y_i_early, Y_i_late)
- Spearman rho(Y_i_early, Y_i_late)
- Median absolute difference |Y_i_early - Y_i_late| (descriptive only)

### Output File
`artifacts/manuscript_completion/c5_fingerprint_calendar_stability.json`

---

## Multiplicity and Interpretation Rules

### Primary comparison family (C2)
8 pre-specified comparisons (all seven policies mandatory, Holm family size = 8).
Holm-Bonferroni correction. Report raw and adjusted p-values for all sign tests.

### C1 comparison family
Five pre-specified comparison pairs (from frozen `gate_f_heldout_analysis.json`
`comparisons_frozen` field), reported at all seven ratios:
1. FP_vs_Random
2. Loc_vs_Random
3. FPSpread_vs_Random
4. FPSpread_vs_FP
5. FPSpread_vs_Loc

No Holm-Bonferroni correction. The frozen Experiment 1 design did not specify a
Holm family; adding one post-exposure would invent a new inferential procedure.
Report paired bootstrap CIs at each ratio. Exploratory sign-test p-values may be
included as clearly labeled supplementary information.

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
| C1 (Exp 1 corrected ref) | 25 (sc5-29) | 4 (frozen set) | 7 (frozen set) | 8-14 hours |
| C2 (Exp 2 corrected ref, 7-pol) | 25 (sc30-54) | 7 (all mandatory) | 1 | 8-14 hours |
| C3 (threshold sensitivity) | 25 (sc30-54) | 2 | P90 + P99 (P95 reused) | 4-6 hours |
| C4 (late-cabinet diagnostic) | 0 (from existing) | — | — | < 1 hour |
| C5 (optional) | 0 (prospective obs) | — | — | < 2 hours |

Estimates based on F2 two-policy sc30-54 elapsed time of ~9,562 seconds (~2.7 hours).
C2 adds 5 additional policies at r=1.25 only. C3 runs two 25-scenario runs (P90, P99);
P95 center point reused from accepted corrected-reference result.

**Total mandatory (C1+C2+C3, C4 from C2 output):** approximately 20-34 hours wall time.

Note: C1 increases from 5 to 7 ratios (+~3-5h). C4 now requires C2 to be complete
first (no longer available from existing two-policy result).

---

## Execution Order

Authorize and execute in this order:
1. C1 (corrected reference for Experiment 1; verify runner first)
2. C2 (corrected reference for Experiment 2, seven policies; must emit per-cabinet
   accounting for C4 to be possible from its output)
3. C4 (diagnostic from C2 output — requires C2 to complete first)
4. C3 (threshold sensitivity)
5. C5 only if explicitly requested

**DO NOT start C1, C2, C3, or C5 until explicitly authorized after reviewing this addendum.**

---

## Amendment Record (v1.0 → v1.1)

**Amendment date:** 2026-10-06

### A1 — challenge_analysis.json SHA canonicalization
**Change:** Corrected wrong SHA (`3a8bbd0...e8d388cdc...`) to canonical (`3a8bbd0...e8d383bb9...`)
in `corrected_reference_same_estimand.json` and `CORRECTED_REFERENCE_SAME_ESTIMAND.md`.
**Why:** Wrong SHA was introduced during Phase 1A draft; the addendum's artifact table
already carried the correct value. All revision2 audit files agree on the canonical SHA.
The file bytes are unchanged — committed at `f1c78a3`.

### A2 — Left-boundary rule: universal delta formulas
**Change:** Removed erroneous special-case "delta_lo = 0 (indistinguishable unless...)"
for left_boundary policies. Replaced with explicit application of universal formulas to
[0,0] × [x,y] and [x,y] × [0,0] cases, showing definite B and definite A outcomes.
**Why:** A=[0,0] vs B=[x,y] with x>0 yields delta_hi = -x < 0 (definite B), not
indistinguishable. The previous language was incorrect and inconsistent with the accepted
frozen challenge_analysis.json estimand. The corrected_reference_same_estimand.json
computation was verified to have used the correct universal formula (result 25/0/0 is
consistent with universal formula; wrong formula would yield 16/9/0).

### A3 — C1 runner: separate runner from frozen r1; exact policy and ratio set
**Change:** Replaced "TO BE DETERMINED" runner options with definitive ruling: create
`c1_gate_f_run.py` derived from frozen `r1_gate_f_run.py` at commit `709c78a`. Replace
"mandatory/preferred" policy and ratio language with exact frozen Experiment 1 sets:
policies = {full_random, full_fp, full_loc, full_fp_spread}; ratios = {1.25, 1.5, 2.0,
4.0, 8.0}. C1 and C2 must use separate runners.
**Why:** The frozen Experiment 1 artifact records these exact four policies and five ratios.
Using a subset or different base runner would invalidate invariant-field comparison.

### A4 — C1 smoke test: require exact invariant-field equality
**Change:** Strengthened sc5 smoke from "accept if thermal ratios are identical" to
require max abs diff <= 1e-9 on ALL non-cabinet invariant fields (B_ref_s, S_ref_s,
B_primary_h, S_primary_Cdoth, B_secondary_h, syn_node_hours, n_drop_*, workload IDs,
utilization quantities). Only B_cab_ratio and downstream feasibility/crossing fields
may differ.
**Why:** Cabinet-reference change should not perturb any upstream quantity. Weak smoke
test could miss silent accidental divergence in workload draws or thermal accounting.

### A5 — C2 spread policies: all 7 mandatory; Holm family fixed at 8
**Change:** Removed "preferred (include if marginal compute is reasonable)" qualifier
for full_fp_spread and random_spread. All seven policies are mandatory. Holm family
size is fixed at 8.
**Why:** Holm family size cannot be determined post-execution. Pre-specifying all 8
comparisons before launch is required for valid multiplicity correction.

### A6 — C2 runner: derived from frozen r2, not r3
**Change:** Specified `c2_gate_f_run.py` derived from frozen r2 challenge runner at
commit `5733b73b`. Do not modify the historical runner; do not use r3 as base.
**Why:** C2 must extend Experiment 2 science, not a two-policy sensitivity runner.
Deriving from r2 ensures the frozen scenario logic, policy implementations, and
accounting are preserved.

### A7 — C2 position LOO diagnostic: stop-and-report on material fallback or NaN
**Change:** Added explicit stop condition if NaN FA_2024 values exist or if a material
number of nodes require fallback beyond level 1. Diagnostic must be run without
scheduling; hierarchy is frozen and cannot be changed by diagnostic findings without
explicit user ruling.
**Why:** If the position group structure is sparse, the LOO hierarchy may silently fall
back to global means for many nodes, potentially eliminating the within-chassis signal
the comparison is designed to test.

### A8 — C3 denominator: cabinet reference quantities are independent of T_thr
**Change:** Corrected "recompute B_cab_hist" at each T_thr to: hold cabinet Q_c
thresholds and B_cab_hist_F2_replay_h fixed across all threshold runs. Only B_ref_s
and S_ref_s are recomputed per T_thr.
**Why:** B_cab_hist is an electrical cabinet measurement. It does not depend on the
node thermal exceedance threshold. Recomputing it per T_thr would be incorrect.

### A9 — C3 run strategy: P95 reused; only P90 and P99 get new full runs
**Change:** Added P95 center-point rule (reuse accepted `gate_f_sc30-54_1p25_r3f2local.json`).
New runner must reproduce sc30 at P95 exactly before P90/P99 runs. Full 25-scenario
runs only for P90 and P99. Added threshold-verification artifact requirement
(`c3_threshold_verification.json`) to be committed before C3 implementation.
**Why:** Eliminates one redundant 25-scenario run (~2-3 hours). Threshold values are
stored in tracked `m4_threshold_audit.json` (SHA `2ece0a19...`, commit `2733d84`) but
independent verification is required before scientific use.

### A10 — C4: remove counterfactual; diagnostic only
**Change:** Removed bullet "does removing late cabinets change the sign of delta_lo."
Updated stopping rule to read "No exclusion simulation is authorized."
**Why:** Whether removing late cabinets reverses the FP advantage cannot be identified
from realized selection data alone. The counterfactual requires a new simulation, which
is not authorized.

### A11 — C5: rewritten as calendar measurement robustness (v1.1)

---

## Amendment Record (v1.1 → v1.2)

**Amendment date:** 2026-10-07

### B1 — C1 frozen ratios restored to seven
**Change:** Added r=1.0 and r=unrestricted to C1 ratio set. Source changed from
`gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json gate_f_ratios` to `gate_f_heldout_analysis.json
ratios` (authoritative). Noted that unr and 1p0 were separate historical executions.
Added unr.json (SHA `3a119505...`) and 1p0.json (SHA `b409fe85...`) to Section 0 frozen
input table.
**Why:** The v1.1 ratio set was extracted from the merged 5-ratio file, which omits the
r=1.0 and unrestricted endpoints run separately. Dropping unrestricted recreates the
selective-reporting problem the corrected-reference rerun is meant to eliminate — the
original reviewer explicitly noted Location-only matched/exceeded FP at r=8 and
unrestricted.

### B2 — C1 comparison family restored to five pairs; Holm removed
**Change:** Replaced the invented 3-comparison Holm family with the exact five
comparison pairs from `gate_f_heldout_analysis.json comparisons_frozen`:
FP_vs_Random, Loc_vs_Random, FPSpread_vs_Random, FPSpread_vs_FP, FPSpread_vs_Loc.
Removed Holm-Bonferroni specification for C1. Report bootstrap CIs per the frozen design.
**Why:** The original Experiment 1 design did not specify a Holm family. Inventing one
post-exposure would create a new inferential framework not present in the published design.

### B3 — C1 runner provenance: scientific freeze is e2df32a; 709c78a is checkpoint addition
**Change:** Documented that runner bytes differ between e2df32a (SHA ce03becd...) and
709c78a (SHA 50bbcb3b...). Diff is checkpoint/resume infrastructure only (~40 lines).
Scientific freeze recorded as e2df32a. C1 runner may use 709c78a bytes (checkpoint
improvement included), but provenance must name e2df32a as the scientific freeze.
The unr.json and 1p0.json results were produced at e2df32a; the merged 5-ratio result
at 709c78a.
**Why:** Two commits record different runner bytes. The addendum must explicitly state
which is the scientific freeze and whether the difference is scientific or operational.

### B4 — C5 outcome construction corrected to median of DeltaT_p95_ij
**Change:** Replaced "mean outcome" with: DeltaT_p95_ij = T_p95_ij - T_p95_j; Y_i_half
= MEDIAN_j(DeltaT_p95_ij). Replaced "using existing frozen thermal model coefficients"
with the exact no-refit R² formula: 1 - sum[(Y_i - F_i_2024)^2] / sum[(Y_i - mean(Y))^2].
**Why:** The existing prospective measurement uses the job-mean-subtracted median, not the
arithmetic mean. The no-refit R² is a direct comparison of FA_2024 to Y, not a model
prediction. Using regression coefficients would constitute a partial refit.

### B5 — Left-boundary prose corrected: sc51 is S-only, not one of the eight
**Change:** Corrected wording in CORRECTED_REFERENCE_SAME_ESTIMAND.md to:
"eight of nine have B_ratio > 1.0; four of nine have S_ratio > 1.0 (sc41, sc51, sc52,
sc54); three of those four also have B_ratio > 1.0; sc51 is the only S-only case."
**Why:** The v1.1 wording said "4 of those 8 also have S_ratio > 1" which implies sc51
is in the group of eight B_ratio > 1. That is false. sc51 has B_ratio < 1 and is the
only S-only infeasible scenario.

### B6 — C4 data availability: per-cabinet data not in existing result; must wait for C2
**Change:** Replaced "extract from existing two-policy result" with explicit determination
that the accepted `gate_f_sc30-54_1p25_r3f2local.json` contains only aggregate lambda-row
quantities — no per-cabinet node-hours or event-touch counts. C4 must wait for C2.
Added requirement that C2 runner must emit `cabinet_accounting` per-cabinet data.
Updated execution order accordingly.
**Why:** Inspection of the raw JSON confirmed lambda rows contain only aggregate fields
(`syn_node_hours`, `n_syn_admit`, `mean_F_syn`, `cab_span_median`, percentile counts).
No per-cabinet breakdown is serialized. The original C4 premise ("no simulation required,
extract from existing output") was incorrect.
**Change:** Replaced scheduling-replay design (sc55-79 scenarios) with prospective 2025
measurement robustness analysis. Fixed split at 2025-07-01 00:00:00 UTC. Frozen FA_2024
fingerprint, no refit. Reports Pearson r, Spearman rho, no-refit R² for each half separately.
**Why:** The sc55-79 scenario design was not a valid calendar stability test — it would
replay synthetic workloads, not measure fingerprint validity against actual 2025 outcomes.
The prospective-observations design directly tests whether FA_2024 remains predictive.

---

## Amendment Record (v1.2 → v1.3)

**Amendment date:** 2026-10-07

### C1 — c2_gate_f_run.py pol_seed ordering bug fix

**Change:** Fixed one-line bug in `c2_gate_f_run.py` line 132:

```python
# BEFORE (buggy):
_COMPAT_POLICY_ORDER = (_COMPAT_POLICY_ORDER_ENV.split(",")
                        if _COMPAT_POLICY_ORDER_ENV else list(GATE_F_POLICIES))

# AFTER (fixed):
_COMPAT_POLICY_ORDER = (_COMPAT_POLICY_ORDER_ENV.split(",")
                        if _COMPAT_POLICY_ORDER_ENV else list(CHALLENGE_POLICY_IDS))
```

**How found:** Gate 2 smoke test (c2 sc30, full_fp+full_random, r=1.25) failed to reproduce
`gate_f_sc30-54_1p25_r3f2local.json`. The smoke matched after the fix. Root cause: when
`GATE_F_RESTRICT_POLICIES` is set (smoke test only), `GATE_F_POLICIES` becomes the restricted
2-policy list. Defaulting `_COMPAT_POLICY_ORDER` to that list caused pol_seeds for full_fp and
full_random to be drawn from the wrong stream positions, swapping their random state.

**Production impact:** None. In production runs without `GATE_F_RESTRICT_POLICIES`,
`GATE_F_POLICIES` equals `CHALLENGE_POLICY_IDS` (7 policies, same order), so the old and fixed
code produce identical behavior. The bug only manifested in restricted smoke invocations.

**This is the same fix already present in `r3_gate_f_run.py` (original two-policy run, commit
5733b73), confirming the fix is correct and consistent with accepted results.**

**Updated SHA:** c2_gate_f_run.py — was `a40e62ef...`, now `e0de9d35a99715bc05c08177b08ad399bb25902fb492ef3487223135b7d3c44a`
**Committed:** `86e0096` (also adds C3 runner, all preflight smoke outputs)

### C2 — c3_gate_f_run.py: new threshold sensitivity runner

**Change:** Added `artifacts/manuscript_completion/runners/c3_gate_f_run.py`.

Derived from `c2_gate_f_run.py` (v1.3 bug-fixed version). Changes:
1. Only `full_fp` and `full_random` policies (hard-coded; no 7-policy seed draw)
2. `T_THR_C3` env var (default 63.625) controls both `T_THR_PRIMARY` and the `thr` argument
   to `compute_B_S_ref_s`. B_ref_s and S_ref_s are recomputed at T_THR_C3 from test-job data.
3. Cabinet parameters fixed: same `f2_local_scheduling_reference.json` and `B_cab_hist_F2_replay_h`
4. Checkpoint READ prohibited.
5. Does not use per-scenario placebo seeds or position_loo (Exp 2 constructs).

**SHA:** `3b4e9825462a5f8b80bc6f76c6938bcf88d460d12f782210474b38573654e91c`

**Gate 3b (C3 P95 sc30 smoke):** At T_THR_C3=63.625, reproduces `gate_f_sc30-54_1p25_r3f2local.json`
sc30 crossings exactly: full_fp C=[15.918%, 16.177%], full_random C=[4.818%, 4.824%].
Max numeric diff = 0.0 on all comparable fields. PASS.

### C3 — c3_threshold_verification.json: updated to COMPLETED

**Change:** Updated status from "PENDING" to "COMPLETE". Added independent reproduction
artifact (`artifacts/manuscript_completion/preflight/c3_threshold_independent.json`) and
verification script (`artifacts/manuscript_completion/preflight/c3_threshold_verify.py`).
Reproduction loaded the cached `full_train_t95_distribution.parquet` (committed at 2733d84),
computed percentiles independently, and confirmed P90=61.875, P95=63.625, P99=66.6625 °C,
n_jobs=3940, n_pairs=77627. All match frozen audit values exactly.

---

## Preflight Gate Results (2026-10-07)

All four previously blocked smoke gates now PASS. Summary:

| Gate | Result | Key evidence |
|---|---|---|
| C1 old-ref r=1.0 compatibility | PASS | Max abs diff = 0.0 vs gate_f_sc5-29_1p0.json sc5 |
| C1 old-ref r=1.25 compatibility | PASS | Max abs diff = 0.0 vs gate_f_sc5-29_1p25...json sc5 |
| C1 old-ref unrestricted compatibility | PASS | Max abs diff = 0.0 vs gate_f_sc5-29_unr.json sc5 |
| C1 corrected-ref sc5 smoke | PASS | All non-cabinet fields identical to old-ref; B_cab_ratio differs as expected |
| C1 r=1.0 negative control | PASS | All 4 policies: identical C_lower, C_upper; all 5 pairwise effects indistinguishable |
| C2 sc30 FP/Random reproduction | PASS (after C1 bug fix) | full_fp C=[15.918%, 16.177%], full_random C=[4.818%, 4.824%]; exact match |
| Cabinet-accounting inertness | PASS | Accounting fields are additive; strip → exact equality with reference |
| Position-LOO diagnostic | STOP CONDITION TRIGGERED (7 global fallbacks) → HUMAN RULING: PROCEED WITH FROZEN SPECIFICATION | 7/2000 = 0.35% global; ρ=0.9823; ruling date 2026-10-07: frozen hierarchy unchanged |
| Position self-exclusion | PASS | Brute-force: 0 errors across all 2000 nodes |
| Placebo seed/invariant tests | PASS | All 6 canonical checks pass; see exact values below |
| Threshold independent reproduction | PASS | P90/P95/P99 and population counts match frozen audit exactly |
| C3 P95 sc30 reproduction | PASS | Crossings match r3f2local exactly; max diff = 0.0 |
| git status | CLEAN | After removing smoke outputs from results/ |

**Position-LOO level-1 group sizes** (for the 57 pos_key groups with ≥2 members, covering 1990 nodes):
- Group size min: 2, median: 19, max: 73
- LOO effective size (excluding self) min: 1, median: 18, max: 72
- Spearman ρ(position_loo, original LOC_FA): 0.9823

**Placebo seeds** (for manuscript):
- sc30 (i=0): global = 2 514 122 466, within-cab = 4 138 460 386
- sc31 (i=1): global = 239 530 002, within-cab = 2 821 695 500
- sc54 (i=24): global = 1 242 389 544, within-cab = 2 325 658 828

**Placebo invariant checks:** WithinCab stays within cabinet ✓; Global permutation is bijective ✓;
Placebo scores affect selection only, thermal calculation uses true FA_2024 ✓;
No placebo score reachable from thermal reconstruction ✓.

---

## Position-LOO Human Ruling (2026-10-07)

**Stop condition triggered:** 7/2000 fp nodes (0.35%) require global fallback (level 4).
Under the frozen addendum rule, global fallback triggers a stop-and-report for human ruling
before any C2 scheduling result is accepted.

**Ruling (authorized by k2alyan, 2026-10-07):**
Proceed with the already-frozen Position-LOO hierarchy exactly as implemented.

**Rationale:**
- 1990/2000 nodes (99.5%) use the intended exact-position LOO group (level 1).
- 0 NaN FA_2024 values; 0 level-2 fallbacks; 3 level-3 (slot); 7 level-4 (global).
- 7/2000 = 0.35% global fallback is not a material fraction under any plausible threshold.
- Spearman ρ(position_loo, LOC_FA) = 0.9823: the LOO template remains extremely close
  to the original structural template. The comparison signal is preserved.
- Changing the hierarchy now would create greater methodological risk than leaving
  the seven pre-specified fallback nodes intact with global scores.

**What is NOT authorized:**
- Modifying the fallback logic.
- Removing the seven nodes.
- Inventing a new fallback.
- Tuning the structural comparator.
- Re-running the diagnostic to select a different rule.

**This ruling is final for all C2 and C3 production runs.**
The seven nodes with global fallback receive their LOO score from the global cohort mean
(excluding themselves), exactly as the frozen hierarchy specifies.

---

## Production Authorization (2026-10-07)

**Authorized by:** k2alyan  
**Authorization date:** 2026-10-07  
**Governing commit:** `999c113` (addendum v1.3, all preflight gates recorded)

**Authorized runs in order:**

| Run | Authorized | Notes |
|---|---|---|
| C1 (sc5-29, 4 policies, 7 ratios) | YES | After SHA verification and clean git state |
| C2 (sc30-54, 7 policies, r=1.25) | YES, after C1 | Requires C1 to complete and be committed first |
| C4 (late-cabinet diagnostic from C2) | YES, after C2 | From C2 cabinet_accounting output only |
| C3 P90 (sc30-54, full_fp+full_random) | YES, after C2/C4 | P95 reused; only P90 and P99 new runs |
| C3 P99 (sc30-54, full_fp+full_random) | YES, after C2/C4 | Independent of P90 result |
| C5 (calendar stability) | NOT YET | Awaits C1-C4 completion and review |

**Frozen runner SHAs (must match before each run):**
- C1: `7cb51ebcf541d9c04b932ef879ce5095d34195452ef88151418d01ce844b41ba`
- C2: `e0de9d35a99715bc05c08177b08ad399bb25902fb492ef3487223135b7d3c44a`
- C3: `3b4e9825462a5f8b80bc6f76c6938bcf88d460d12f782210474b38573654e91c`

**Mandatory pre-run protocol (every run):**
1. Verify exact runner SHA against authorized value above.
2. Verify all frozen input artifact SHAs (corrected cabinet ref, replay denominator, r3f2local, m4_threshold_audit).
3. `git status --porcelain --untracked-files=all` must return empty.
4. Print git HEAD and THERMALSHIFT_DATA_DIR.
5. Confirm no production output file already exists at the target path.
6. Confirm no manuscript-completion checkpoint is being reloaded.

**Stop conditions during production runs:**
- Any input SHA mismatch: STOP.
- C1 r=1.0 negative control fails (any policy pair non-indistinguishable): STOP and invalidate C1.
- Any run interrupted: mark partial output invalid, do not silently resume, report before restarting.
- C4 shows pipeline/integrity problem: STOP and report before continuing to C3.
- Do not inspect partial scientific results to make design decisions.
