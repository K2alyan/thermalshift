# Writer Handoff Index

**Date:** 2026-10-09  
**Purpose:** Index for ChatGPT or any independent writer to write the final
SIGMETRICS/POMACS submission. This file is an index only. It does not draft
any paper prose.

---

## Quick Reference: Canonical Numbers

| Claim | Value | Source |
|-------|-------|--------|
| Node-level Pearson r | 0.926 | `fingerprint/m1_sensitivity_summary.json` → `key_stats.individual_F_pearson_r` = 0.9259 |
| Node-level Spearman rho | 0.936 | `fingerprint/phase3a_results.json` → `node_level_companion.spearman_r` = 0.9358 |
| Node-level direct no-refit R² | 0.848 | `fingerprint/m1_sensitivity_summary.json` → `key_stats.r2_frozen_individual_F` = 0.8482 |
| Training jobs | 3,945 | `fingerprint/phase3a_results.json` → `fingerprint_freeze.n_train_jobs` |
| Test jobs | 2,637 | `fingerprint/phase3a_results.json` → `fingerprint_freeze.n_test_jobs` |
| Nodes in cohort | 2,000 | `fingerprint/phase3a_results.json` → `fingerprint_freeze.n_fp_nodes` |
| Cabinet MAE | 0.37 kW (0.8%) | `replay_model/power_validation_60job.json` → `mae_kW` = 0.3723 |
| FP vs Random (corrected ref) | +12.48 pp, 25/0/0, [+11.09, +19.04] | `corrected_reference/c2_correctedref_analysis.json` → `comparisons.FP_vs_Random` |
| FP vs WithinCab | +10.88 pp, 24/1/0, [+5.96, +17.40] | Same → `FP_vs_WithinCab` |
| FP vs GlobalPlacebo | +12.31 pp, 25/0/0, [+10.88, +17.40] | Same → `FP_vs_Global` |
| FP vs Location (LOO) | +13.95 pp, 25/0/0, [+12.23, +21.98] | Same → `FP_vs_PositionLOO` |
| FP-Spread vs Rand-Spread | +4.42 pp, 23/2/0, [+2.14, +5.42] | Same → `FPSpread_vs_RandSpread` |
| FP-Spread vs FP | −9.18 pp, 0/0/25, [−17.91, −6.60] | Same → `FPSpread_vs_FP` |
| Rand-Spread vs Random | −0.19 pp, 5/14/6, [−0.58, 0.00] | Same → `RandSpread_vs_Random` |
| FP-Spread vs Location | +4.96 pp, 24/1/0, [+2.26, +8.34] | Same → `FPSpread_vs_PositionLOO` |
| All Holm p (except Rand-Spread) | 4.77e-7 | Same |
| Rand-Spread Holm p | 1.000 | Same |
| P90 FP vs Random | +8.90 pp, 24/1/0, [+4.95, +14.50], lb=3/25 | `threshold_sensitivity/c3_threshold_analysis.json` → `thresholds.P90` |
| P95 FP vs Random | +12.48 pp, 25/0/0, [+11.09, +19.04], lb=9/25 | Same → `thresholds.P95` |
| P99 FP vs Random | +21.33 pp, 25/0/0, [+16.39, +25.36], lb=19/25 | Same → `thresholds.P99` |
| P90/P95 binding constraint (FP) | 100% B_ratio | `c3_threshold_analysis.json` → `binding_constraints.full_fp` |
| P99 binding constraint shift (FP) | 20/25 S_ratio | Same |
| Original E2 FP vs Random | +6.71 pp, 22/25, [+3.92, +8.72] | `original_experiments/challenge_analysis_E2.json` |
| Original E2 FP vs WithinCab | +3.54 pp, 20/25, [+0.56, +4.44] | Same |

---

## File Index

### manuscript/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `thermalops_manuscript.tex` | Full SIGMETRICS/POMACS single-column anonymous LaTeX draft (9 sections + 4 appendices). Compiled with `\documentclass[acmsmall,screen,review,anonymous]{acmart}`. | YES — latest integrated draft | All corrected-reference values from committed JSONs; correct B_ratio/S_ratio terminology; P99 floor limitation disclosed; 4 figure placeholders; 1 table placeholder (Exp 1 choice-ratio sweep) | All earlier prose drafts |
| `thermalops.bib` | BibTeX bibliography for all 10 cite keys used in the manuscript. Entries marked [VERIFY]: tapas, pal, sinha2023thermal, ostrouchov2020machine, exadigit. | YES | fan2007power, mytkowicz2009producing, inadomi2015hpc, frontier_userguide, frontier_olcf_dataset confirmed. | — |
| `SIGMETRICS_OUTLINE_revision2.md` | Detailed paper outline from fifth-round review phase (revision2). Contains section-by-section structure, key arguments, earlier numerical values (some superseded). | NO — structural reference only | Old abstract values (+6.71 pp, 22/25) appear here as historical record | — |
| `reviewer_response_r2.md` | Fifth-round reviewer response document. Records reviewer concerns and response commitments that shaped the corrected-reference analyses. | Reference | Lists the reviewer-raised reference circularity issue and the commitments that led to the corrected-reference work | — |

---

### audit/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `FINAL_SCIENTIFIC_CLAIMS_AUDIT.md` | 14-claim audit table with allowed/prohibited wording for every scientific claim. Established after full scientific review. | YES | Complete claim-by-claim evidence citations; prohibited characterizations; Holm correction summary | All earlier claims lists |
| `PROVENANCE_MANIFEST.md` | SHA256 checksums for every runner, reference file, and canonical output artifact. Runner freeze commit 5733b73b. | YES | All SHA256 values for auditing any artifact | — |
| `MANUSCRIPT_INTEGRATION_AUDIT.md` | Per-claim table: manuscript location → source file → exact JSON value → verification status. Created at manuscript-integration time. | YES | All quantitative claims with pre-rounding source values | — |
| `STALE_VALUE_SCAN.md` | Scan of thermalops_manuscript.tex for forbidden internal names and stale values. All CLEAN. | YES | Scan verdict: CLEAN for all forbidden strings | — |
| `FINAL_NUMERICAL_CLAIM_AUDIT_revision2.md` | Comprehensive numerical audit from revision2 (fifth-round review). Uses job-contribution reference values throughout. | PARTIALLY — use for original-experiment numbers only | V8: +6.71 pp (FP_vs_Random r=1.25); V12: +3.54 pp; O7: R²=0.848; O8: MAE 0.37 kW | Superseded by MANUSCRIPT_INTEGRATION_AUDIT.md for corrected-reference claims |
| `FINAL_REVIEWER_COVERAGE_MATRIX.md` | Matrix of reviewer concerns mapped to analysis responses. Revision2 vintage. | Reference | Documents what each reviewer raised and how each was addressed | — |
| `POST_EXPOSURE_SENSITIVITY_RECOVERY.md` | Decision record for the post-exposure sensitivity recovery strategy (corrected-reference reanalysis). | Reference | Explains why corrected-reference analyses were performed and how they relate to preregistered work | — |

---

### fingerprint/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `phase3a_results.json` | Phase 3A fingerprint characterization results: node-level and job-level predictive accuracy stats. | YES | `node_level_companion.pearson_r`=0.9259; `.spearman_r`=0.9358; `n_train_jobs`=3945; `n_test_jobs`=2637; `n_fp_nodes`=2000 | — |
| `m1_sensitivity_summary.json` | M1 sensitivity summary from revision2. Contains no-refit R², within-chassis permutation test. | YES | `key_stats.r2_frozen_individual_F`=0.8482; `key_stats.individual_F_pearson_r`=0.9259 | — |
| `prospective_accuracy_by_job_size.json` | Prospective accuracy broken down by job size. | Supporting | Job-size stratified stats | — |
| `figures/` | Phase1 analysis and figure PNG files. See FIGURE_DATA_INDEX.md. | Supporting | `phase3a_node_level.png` is the key fingerprint scatter figure | — |

---

### replay_model/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `power_validation_60job.json` | Cabinet power estimation validation against 60 jobs. | YES | `mae_kW`=0.3723; spread=48.21 kW; 0.77%≈0.8% | — |
| `fleet_topology.json` | Fleet topology: node→cabinet mapping, hostname→slot mapping. | YES | Used by replay model for cabinet load calculation | — |
| `cabinet_power_envelopes.json` | Per-cabinet thermal operating envelopes (thresholds). | YES | B_ref and S_ref denominator structure | — |
| `cabinet_timeline_audit.json` | Timeline of cabinet availability (identifies late-added cabinets 2600/2601/2602). | YES | Cabinet installation dates, late-cabinet identification | — |

---

### protocol/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `GATE_F_DESIGN.md` | Full design document for the preregistered challenge protocol (Gate F). Covers estimand, policies, bootstrap settings, interpretation rules. | YES — frozen preregistration document | Canonical definition of delta_lo/delta_hi estimand; 7 policies; seed 9999; 5000 draws | — |
| `MANUSCRIPT_COMPUTE_ADDENDUM.md` | Comprehensive governance log of all corrected-reference computation: C1/C2/C3/C4 runs, preflight records, equivalence gates, operational incidents. | YES | Full operational record from corrected-reference compute phase | — |
| `PARALLEL_EXECUTION_AMENDMENT.md` | Amendment documenting the shift from sequential to parallel execution. | Reference | Explains the execution architecture change | — |
| `C2_POSTRUN_COMPATIBILITY_NOTE.md` | Documents post-run compatibility fixes (print encoding, scipy API). Verifies zero scientific change. | YES | Zero-scientific-change verification for C2 post-run fixes | — |
| `CORRECTED_REFERENCE_SAME_ESTIMAND.md` | Analysis showing the corrected (concurrent-load) reference uses the same estimand as the original. | YES | Confirms estimand continuity across reference definitions | — |
| `corrected_reference_same_estimand.json` | Supporting JSON for same-estimand analysis. | YES | Numerical evidence for estimand continuity | — |

---

### original_experiments/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `challenge_analysis_E2.json` | Original Experiment 2 analysis under job-contribution reference. The primary preregistered analysis. | YES — for original E2 results | FP_vs_Random r=1.25: median_delta_lo=6.7063 pp, n_A=22, n_I=1, n_B=2; FP_vs_WithinCabPlacebo: 3.5378 pp, 20/25 | Superseded by corrected-reference as primary scientific claim; retained as original preregistered result |
| `challenge_preflight.json` | Preflight gate record for the original preregistered run. 16/16 conditions passed. | YES | n_conditions=16, overall_pass=True; records Position-LOO 7-global-fallback pre-run ruling | — |
| `gate_f_heldout_analysis.json` | Original Experiment 1 analysis (all ratios, job-contribution reference). | YES — for original E1 results | FP_vs_Random across 7 choice ratios; r=1.25 gives 25/0/0 median_delta_lo=4.77 (note: this is the E1 value; E2 analysis at r=1.25 gives +6.71 pp in challenge_analysis_E2.json) | Superseded by corrected-reference for primary claims |
| `gate_f_manuscript_tables.json` | Summary tables from the revision2 manuscript analysis. Job-contribution reference values. | Reference | Contains formatted comparison tables for original experiments | Superseded by c2_correctedref_analysis.json for corrected-reference tables |
| `r2_vs_r1_equivalence.json` | Equivalence check between revision2 and revision1 raw results. | Reference | Confirms revision2 results reproduce revision1 within tolerance | — |
| `loo_beta_results.json` | Position-LOO beta sensitivity results. | Supporting | LOO template stability across beta parameter choices | — |
| `sensitivity_loo_beta.json` | Beta sensitivity analysis for LOO template. | Supporting | Sensitivity of LOO template to beta parameter | — |

---

### corrected_reference/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `C1_CORRECTEDREF_ANALYSIS.md` | Narrative analysis of C1 (corrected reference, sc5-29, all ratios). | YES | Choice-ratio sweep under corrected reference; sensitivity_vs_original_e1 comparison | — |
| `c1_correctedref_analysis.json` | C1 analysis output: FP vs Random across all 7 ratios under concurrent-load reference. | YES | All 7 ratio results; sensitivity table comparing original vs corrected; negative control r=1.0 (25 indeterminate) | Original E1 analysis for corrected-reference claims |
| `C2_CORRECTEDREF_ANALYSIS.md` | Narrative analysis of C2 (corrected reference, sc30-54, r=1.25, 8-policy). | YES | 8-comparison results narrative | — |
| `c2_correctedref_analysis.json` | C2 canonical analysis: all 8 comparisons at r=1.25, corrected reference. PRIMARY SCIENTIFIC RESULT FILE. | YES — CANONICAL | All 8 comparison rows with exact values; Holm p-values; binding constraint table | Original E2 analysis for corrected-reference claims |
| `c2_loo_diagnostic.json` | LOO diagnostic for C2 analysis. | Supporting | LOO stability check | — |
| `C4_CABINET_DIAGNOSTIC.md` | Late-cabinet diagnostic narrative (cabinets 2600/2601/2602). | YES | No late-cabinet dominance; proportional structural share | — |
| `c4_cabinet_diagnostic.json` | Late-cabinet diagnostic data. | YES | Node-hours, event-touches, FP/Random enrichment for late cabinets | — |
| `late_cab_cohort_diagnostic.json` | Earlier late-cabinet cohort analysis from revision2. | Supporting | Background for late-cabinet section | — |
| `F2_PRIMARY_RESULT.md` | Record of the corrected (F2) reference primary result. | Reference | Documents the F2 concurrent-load reference approach and validation | — |
| `TASK_D_PROVENANCE_CORRECTION.md` | Provenance record for the Task D reference correction. | Reference | Documents why and how the reference correction was made | — |
| `F1_VS_F2_CABINET_REFERENCE_AUDIT.md` | Audit comparing F1 (job-contribution) vs F2 (concurrent-load) cabinet reference. | YES | Quantifies circularity in F1 reference; validates F2 correction | — |

---

### raw_merged/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `gate_f_sc5-29_all_C1.json` | C1 raw merged result: 25 scenarios sc5-29, all ratios, corrected reference. SHA: `8d66349fb1...` | YES | Per-scenario crossing data for C1 analysis; all 7 ratios | — |
| `gate_f_sc30-54_1p25_c2manuscript_C2_P95.json` | C2 raw merged result: 25 scenarios sc30-54, r=1.25, corrected reference. Also used as P95 threshold source. SHA: `b4dbc4bc0f...` | YES | Per-scenario data for all 7 policies; source for both C2 and P95 threshold | — |
| `gate_f_sc30-54_1p25_t61p875_c3canonical_P90.json` | P90 canonical raw merged: 25 scenarios sc30-54, T=61.875°C. Single git HEAD 3a7bd3c for all workers. SHA: `a94f72084d...` | YES — canonical P90 | P90 threshold raw data; use this for P90 analysis | Mixed-commit P90 (next row) |
| `gate_f_sc30-54_1p25_t61p875_c3manuscript_P90_MIXEDCOMMIT.json` | P90 original raw merged: scientifically valid but has mixed git_commit_full execution metadata. SHA: `0cd2371a71...` | SUPERSEDED for provenance; scientifically valid | Identical science to canonical; kept for auditability | Superseded by canonical above for submission |
| `gate_f_sc30-54_1p25_t66p6625_c3manuscript_P99.json` | P99 raw merged: 25 scenarios sc30-54, T=66.6625°C. Clean single-commit run. SHA: `2fef4c4950...` | YES | P99 threshold raw data | — |
| `gate_f_sc30-54_all_r2challenge_merged_E2original.json` | Original Experiment 2 raw merged result under job-contribution reference. | YES — for original E2 raw data | Per-scenario data for original challenge; used with challenge_analysis_E2.json | — |

---

### threshold_sensitivity/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `C3_THRESHOLD_ANALYSIS.md` | Narrative of C3 threshold sensitivity analysis (P90/P95/P99). | YES | Directional robustness conclusion; P99 floor limitation; binding constraint shift | — |
| `c3_threshold_analysis.json` | C3 threshold analysis: FP vs Random at P90, P95, P99. | YES | `thresholds.P90/P95/P99` with verdicts, CI, left-boundary counts, binding constraints | Earlier C3 analysis with incorrect binding constraint labels |
| `INVALIDATED_C3_P99_CONCURRENT_LAUNCH.md` | Record of the invalidated P99 concurrent launch (6-worker resource gate violation). | Operational record | Documents why the first P99 run was invalidated | — |

---

### figures/existing/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `revision2_fig_r2_factorial_r125.{pdf,png}` | Forest plot of factorial comparisons at r=1.25 — UNDER JOB-CONTRIBUTION REFERENCE | NOT CANONICAL — must be regenerated | Old values (+6.71 pp, +3.54 pp etc.); style reference only | Superseded by corrected-reference values |
| `revision2_fig_r2_robustness.{pdf,png}` | Robustness/sensitivity analysis figure — UNDER JOB-CONTRIBUTION REFERENCE | NOT CANONICAL — must be regenerated | Old sensitivity results; layout reference only | Superseded |
| `revision2_fig_r2_fpspread_crossover.{pdf,png}` | FP-Spread vs FP crossover figure — OLD REFERENCE | NOT CANONICAL | Old values; layout reference only | Superseded |
| `revision2_fig_r2_policy_matrix.{pdf,png}` | Policy comparison matrix — OLD REFERENCE | NOT CANONICAL | Old values; layout reference only | Superseded |
| `revision3_D1_f1_vs_f2_scatter.png` | F1 vs F2 reference scatter diagnostic | Supporting | Shows relationship between job-contribution and concurrent-load references | — |
| `revision3_D2_f2_f1_ratio_ecdf.png` | ECDF of F2/F1 ratio | Supporting | Distribution of reference correction magnitude | — |
| `revision3_D3_exceedance_fractions.png` | Exceedance fractions diagnostic | Supporting | Threshold exceedance analysis | — |
| `revision3_D4_sorted_thresholds.png` | Sorted thresholds diagnostic | Supporting | Per-node threshold distribution | — |
| `revision3_D5_concurrent_power_timeseries.png` | Concurrent power time series | Supporting | Temporal structure of concurrent-load reference | — |
| `phase1_analysis_phase3a_node_level.png` | Node-level fingerprint characterization scatter (temporal stability) | Supporting — likely closest to Fig 1 for manuscript | Prospective fingerprint vs test set | — |
| `phase1_analysis_phase3a_monthly_thermal.png` | Monthly thermal breakdown | Supporting | Monthly fingerprint stability | — |
| `phase1_analysis_phase3a_monthly_calib.png` | Monthly calibration | Supporting | Calibration by month | — |
| `phase1_analysis_phase3b2_capacity.png` | Phase 3B capacity figure (early model) | SUPERSEDED | Early capacity estimates; not from final replay model | Superseded by corrected-reference analyses |

---

### figures/scripts/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `fig_r2_main.py` | Figure generation script from revision2. Reads revision2 challenge_analysis.json. | NOT CANONICAL for corrected-reference figs | Script must be updated to read c2_correctedref_analysis.json | — |
| `fig_r2_robustness.py` | Robustness figure script from revision2. | NOT CANONICAL | Must be updated to use corrected-reference data | — |

---

### analysis_scripts/

| File | What it contains | Canonical? | Key values / results inside | Supersedes |
|------|-----------------|------------|-----------------------------|------------|
| `c1_correctedref_analysis.py` | Frozen C1 analysis script. | YES | Produces c1_correctedref_analysis.json | — |
| `c2_correctedref_analysis.py` | Frozen C2 analysis script (8 comparisons, Holm correction). | YES | Produces c2_correctedref_analysis.json | — |
| `c3_threshold_analysis.py` | Frozen C3 analysis script (P90/P95/P99 sensitivity). | YES | Produces c3_threshold_analysis.json | — |
| `c4_cabinet_diagnostic.py` | Frozen C4 late-cabinet diagnostic script. | YES | Produces c4_cabinet_diagnostic.json | — |
| `c3_p90_equivalence_gate.py` | Equivalence gate verifying canonical P90 vs original P90. | YES | PASS; max_abs_diff=0.0; confirms canonical P90 scientifically identical to original | — |

---

## DO NOT USE / SUPERSEDED RESULTS

These artifacts exist in the repository but must NOT be used as primary evidence
in the manuscript. They are listed here for auditability only.

| Item | Why superseded | Canonical replacement |
|------|---------------|----------------------|
| **+15.5 pp development headline** | From early development analysis (dev scenarios sc0-4); not from the held-out set. Dev results are not the scientific claim. | Held-out result: +12.48 pp (corrected reference) |
| **+12.76 pp lower-vs-lower diagnostic** | This was a non-conservative diagnostic (C_lower(A) − C_lower(B)) used during development. The conservative estimand is delta_lo = C_lower(A) − C_upper(B). | Use delta_lo values from c2_correctedref_analysis.json |
| **R² = 0.857 or 0.8572** | This is the node-level R² from the fitted linear model. The correct value is the no-refit direct R² = 0.848 (m1_sensitivity_summary.json). | R² = 0.848 (direct no-refit) |
| **R² = 0.2067 (job-level)** | The job-level correlation is not the node-level fingerprint predictive accuracy. Must not be presented as the primary predictive R². | R² = 0.848 (node-level, no-refit) |
| **Self-inclusive Position result** | Early LOO analysis did not exclude the evaluated job from its own position's history. The correct result excludes the evaluated job (leave-one-out). | Position-LOO result from challenge_analysis_E2.json / c2_correctedref_analysis.json |
| **Original incorrect cabinet reference (+6.71 pp as primary)** | Original analysis had a structural circularity: the evaluated job's thermal contribution partially overlapped with the reference collection window. | Corrected-reference result: +12.48 pp (c2_correctedref_analysis.json). The +6.71 pp value is a valid historical record of the original preregistered experiment and should be reported for completeness in a "Original Results" section — but is not the primary claim. |
| **Mixed-commit P90 artifact** (`gate_f_sc30-54_1p25_t61p875_c3manuscript_P90_MIXEDCOMMIT.json`) | Workers recorded two different git_commit_full values because a documentation commit happened during execution. Science is identical to canonical; but provenance is mixed. | Canonical P90: `gate_f_sc30-54_1p25_t61p875_c3canonical_P90.json` (equivalence gate PASS, max_abs_diff=0.0) |
| **Revision3 gate_f task_d figures (D1-D5 from invalidated runs)** | These were from Task D intermediate runs before the final corrected reference was established. | Use revision3 figures only for the F1-vs-F2 reference comparison narrative; not as primary results |
| **FP-Spread advantage at high choice ratios (original reference)** | Under the job-contribution reference, FP-Spread appeared to beat FP at r≥4. This reverses under the corrected reference: FP-Spread vs FP is 0/0/25 (−9.18 pp). | Corrected reference result in c2_correctedref_analysis.json |
| **"Other" binding constraint category** | Earlier C3 analysis used B_thermal/B_cab/Other columns. "Other" was actually S_ratio (thermal severity). This terminology was incorrect. | B_ratio (thermal incidence) and S_ratio (thermal severity) as defined in Appendix C of the manuscript |
| **Threshold sensitivity as dose-response** | P90→P95→P99 are alternative exposure definitions, not monotonically relaxing thermal budgets. B_ref_s and S_ref_s are recomputed at each threshold. | Directional robustness framing only; P99 magnitude is floor-limited |

---

## Experimental Hierarchy

The manuscript reports three layers of results. This hierarchy must be preserved:

1. **Original preregistered experiments** (Sections 6.1): Under the job-contribution cabinet reference.
   - Experiment 1 (choice-ratio sweep): `original_experiments/gate_f_heldout_analysis_E1.json`
   - Experiment 2 (node-specificity challenge): `original_experiments/challenge_analysis_E2.json`
   - Values: FP vs Random +6.71 pp (22/25); FP vs WithinCab +3.54 pp (20/25)
   - These are valid preregistered results; they are NOT the primary claims.

2. **Corrected-reference analyses** (Sections 6.2–6.3, primary claims): Under concurrent-load reference.
   - C1 choice-ratio sweep: `corrected_reference/c1_correctedref_analysis.json`
   - C2 node-specificity challenge: `corrected_reference/c2_correctedref_analysis.json`
   - These are post-exposure analyses motivated by reference correction. They are not retroactively preregistered primary experiments.

3. **Threshold sensitivity** (Section 7): Post-exposure sensitivity probes.
   - C3: `threshold_sensitivity/c3_threshold_analysis.json`
   - Directional robustness evidence only; P99 floor-limited.
