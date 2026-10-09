# Figure Data Index

**Date:** 2026-10-09  
**Purpose:** For every possible figure/table concept, this file records the exact
source file, the fields/columns needed, and the canonical values. It does NOT
decide whether each belongs in the main paper, does NOT design the figure, and
does NOT generate prose.

---

## Figure/Table Concepts

### Figure 1 — Node-Level Thermal Fingerprint: Distribution and Temporal Stability

| Field | Value |
|-------|-------|
| **Concept** | Show that individual nodes have persistent thermal positions across years. Two panels likely: (A) distribution of fingerprint scores across 2,000 nodes; (B) scatter of 2024 training fingerprint vs 2025 test mean thermal position. |
| **Source file** | `fingerprint/phase3a_results.json` |
| **Fields needed** | `node_level_companion.pearson_r`=0.9259; `node_level_companion.spearman_r`=0.9358; `node_level_companion.mae_C`=0.2645; `node_level_companion.n_obs`=2000 |
| **Supplementary source** | `fingerprint/m1_sensitivity_summary.json` → `key_stats.r2_frozen_individual_F`=0.8482 |
| **Canonical values** | r=0.926, rho=0.936, R²=0.848 (no-refit direct), 2,000 nodes |
| **Existing image** | `figures/existing/phase1_analysis_phase3a_node_level.png` (node-level scatter); `phase1_analysis_phase3a_monthly_thermal.png` (monthly breakdown) |
| **Note** | The existing phase3a_node_level.png is likely the closest existing approximation. Axes, title, and annotation must use publication-facing terminology (no internal names). |

---

### Figure 2 — Capacity Yield Crossing Illustration

| Field | Value |
|-------|-------|
| **Concept** | Illustrate the conservative interval estimand. Show lambda sweep for one scenario and policy pair: how C_lower(lambda) and C_upper(lambda) evolve, where they cross zero, and how delta_lo = C_lower(A) - C_upper(B) is measured. |
| **Source file** | `raw_merged/gate_f_sc30-54_1p25_c2manuscript_C2_P95.json` (one scenario, e.g. sc30) OR `corrected_reference/c2_correctedref_analysis.json` → `comparisons.FP_vs_Random.delta_lo_per_scenario` |
| **Fields needed** | For a representative scenario (sc46 recommended: median delta_lo=12.16 pp): `lambda_rows` array inside `scenario_results[scenario_idx=46].ratios["1.25"].full_fp`; similarly for `full_random`. Each lambda_row has `lambda`, `C_lower_pct`, `C_upper_pct`. |
| **Canonical values** | FP vs Random delta_lo median = 12.48 pp; delta_hi median = 12.94 pp across 25 scenarios. |
| **Existing image** | None. Must be generated. |

---

### Figure 3 — Forest Plot: All 8 Comparisons at r=1.25 (Corrected Reference)

| Field | Value |
|-------|-------|
| **Concept** | One row per comparison. x-axis: median delta_lo (pp). Whiskers: bootstrap 95% CI. Color/fill: significant (Holm p < 0.05) vs not. |
| **Source file** | `corrected_reference/c2_correctedref_analysis.json` → `comparisons` dict |
| **Fields needed (all 8 rows)** | |

| Comparison key | policy_A | policy_B | n_A/n_I/n_B | median_delta_lo_pp | CI_lo | CI_hi | holm_p | significant |
|---|---|---|---|---|---|---|---|---|
| FP_vs_Random | full_fp | full_random | 25/0/0 | 12.475543 | 11.094795 | 19.038500 | 4.77e-7 | True |
| FP_vs_WithinCab | full_fp | full_fp_withincab_placebo | 24/1/0 | 10.876... | 5.96... | 17.40... | 4.77e-7 | True |
| FP_vs_Global | full_fp | fp_global_placebo | 25/0/0 | 12.309... | 10.88... | 17.40... | 4.77e-7 | True |
| FP_vs_PositionLOO | full_fp | position_loo | 25/0/0 | 13.950... | 12.23... | 21.98... | 4.77e-7 | True |
| FPSpread_vs_RandSpread | full_fp_spread | random_spread | 23/2/0 | 4.420... | 2.14... | 5.42... | 4.77e-7 | True |
| FPSpread_vs_FP | full_fp_spread | full_fp | 0/0/25 | -9.175... | -17.91... | -6.60... | 4.77e-7 | True |
| RandSpread_vs_Random | random_spread | full_random | 5/14/6 | -0.192... | -0.58... | 0.00... | 1.000 | False |
| FPSpread_vs_PositionLOO | full_fp_spread | position_loo | 24/1/0 | 4.960... | 2.26... | 8.34... | 4.77e-7 | True |

| **Canonical values** | See Quick Reference table in WRITER_HANDOFF_INDEX.md |
| **Existing image** | `figures/existing/revision2_fig_r2_factorial_r125.{pdf,png}` — SUPERSEDED, uses job-contribution-reference values. Layout/style reference only; all values must be replaced. |
| **Note** | The existing fig_r2_factorial_r125 figure uses the old values (+6.71 pp etc.). It should inform layout only. The FPSpread_vs_FP row is −9.18 pp (corrected) vs positive values seen in old figures. |

---

### Figure 4 — Absolute Capacity Distributions: FP vs Random at r=1.25

| Field | Value |
|-------|-------|
| **Concept** | Show the distribution of C_lower across 25 scenarios for FP and Random, illustrating the systematic separation. |
| **Source file** | `corrected_reference/c2_correctedref_analysis.json` → `capacity_table` OR `comparisons.FP_vs_Random.delta_lo_per_scenario` |
| **Fields needed** | Per-scenario `delta_lo_per_scenario` for FP_vs_Random (25 values); or per-scenario C_lower values for full_fp and full_random from the raw merged data. |
| **Canonical values** | delta_lo range: sc42=20.90 pp (max), sc38=4.90 pp (min); all 25 positive. Median = 12.48 pp. |
| **Existing image** | `figures/existing/revision2_fig_r2_policy_matrix.{pdf,png}` — SUPERSEDED. |

---

### Figure 5 (optional/robustness) — Threshold Sensitivity: P90/P95/P99

| Field | Value |
|-------|-------|
| **Concept** | Show FP vs Random delta_lo and CI at each of the three threshold definitions. Could be a small forest plot or bar chart. |
| **Source file** | `threshold_sensitivity/c3_threshold_analysis.json` → `thresholds` dict |
| **Fields needed** | |

| Threshold | temp_C | n_A/n_I/n_B | median_delta_lo_pp | CI_lo | CI_hi | random_lb |
|---|---|---|---|---|---|---|
| P90 | 61.875 | 24/1/0 | 8.896892 | 4.947107 | 14.497655 | 3 |
| P95 | 63.625 | 25/0/0 | 12.475543 | 11.094795 | 19.038500 | 9 |
| P99 | 66.6625 | 25/0/0 | 21.332228 | 16.392728 | 25.364214 | 19 |

| **Canonical values** | Direction preserved at all three; P99 floor-limited (19/25 Random at left boundary). |
| **Existing image** | None specifically for threshold sensitivity. |
| **Note** | Table 2 in thermalops_manuscript.tex already encodes this. A figure may be redundant depending on layout. |

---

### Figure/Diagnostic — F1 vs F2 Reference Comparison (Revision3 D-series)

| Field | Value |
|-------|-------|
| **Concept** | Illustrate the difference between job-contribution (F1) and concurrent-load (F2) references. May belong in supplementary material rather than main paper. |
| **Source file** | `figures/existing/revision3_D1_f1_vs_f2_scatter.png` through `revision3_D5_concurrent_power_timeseries.png` |
| **Canonical values** | See `corrected_reference/F1_VS_F2_CABINET_REFERENCE_AUDIT.md` for quantitative comparison |
| **Existing image** | revision3_D1 through D5 PNGs — canonical for F1 vs F2 comparison |

---

## Table Concepts

### Table 1 — Experiment 2 Node-Specificity Challenge Results (Main Paper)

This table is partially constructed in `thermalops_manuscript.tex` (Section 6.3, `\label{tab:exp2}`).

| Field | Value |
|-------|-------|
| **Source file** | `corrected_reference/c2_correctedref_analysis.json` → `comparisons` |
| **Columns needed** | Comparison label; n_A/n_I/n_B; Med. delta_lo (pp); 95% CI; Holm p; Significant |
| **All 8 rows** | See Figure 3 table above for all exact values |
| **Note** | Bootstrap note: 5,000 paired draws, seed 9999, percentile 95% CI. Holm-Bonferroni: 8 comparisons, alpha=0.05. |

---

### Table 1B (optional) — Experiment 1 Choice-Ratio Sweep

| Field | Value |
|-------|-------|
| **Concept** | Show FP vs Random verdict summary and median delta_lo across all 7 choice ratios (r=1.0, 1.25, 1.5, 2.0, 4.0, 8.0, unrestricted) under corrected reference. |
| **Source file** | `corrected_reference/c1_correctedref_analysis.json` → `comparisons.FP_vs_Random` |
| **Fields needed** | For each ratio: n_A, n_I, n_B, median_delta_lo_pp, CI |
| **Existing placeholder** | Table 1 placeholder in manuscript (Section 6.2) is currently a comment: `% [TABLE 1: Experiment 1...]` |
| **Note** | r=1.0 should show 25 indeterminate (negative control). Values at r=1.25 match E2 table exactly. |

---

### Table 2 — Threshold Sensitivity (Already in Manuscript)

| Field | Value |
|-------|-------|
| **Concept** | P90/P95/P99 results: verdicts, median delta_lo, CI, Random left-boundary count. |
| **Source file** | `threshold_sensitivity/c3_threshold_analysis.json` → `thresholds` |
| **Status** | Already fully populated in `thermalops_manuscript.tex` (Section 7.1, `\label{tab:thresh}`). |
| **Values** | P90: 24/1/0, +8.90 pp, [+4.95, +14.50], 3/25 lb; P95: 25/0/0, +12.48 pp, [+11.09, +19.04], 9/25 lb; P99: 25/0/0, +21.33 pp, [+16.39, +25.36], 19/25 lb |

---

### Table — Binding Constraint Summary

| Field | Value |
|-------|-------|
| **Concept** | For each threshold, which binding constraint (B_ratio vs S_ratio) drives FP crossings. |
| **Source file** | `threshold_sensitivity/c3_threshold_analysis.json` → `thresholds.P90.binding_constraints.full_fp` |
| **Canonical values** | P90 FP: B_ratio=25/25 crossings (100%). P95 FP: B_ratio=25/25 (100%). P99 FP: S_ratio=20, B_ratio=5 (80% S_ratio). |
| **Note** | This may work better as a paragraph in Appendix C than a standalone table. Already described in manuscript prose (Section 7.1, Appendix C). |

---

## Data Not Available for Figures (Raw Telemetry Excluded)

The following data types are NOT included in this handoff package:
- Raw Frontier job metadata parquet files (multi-gigabyte Frontier dataset; access via DOI 10.13139/OLCF/3013979)
- Per-node GPU temperature time series from Frontier OLCF telemetry
- Full per-scenario worker output logs

All numbers needed for paper figures can be derived from the JSON files included in this package.
