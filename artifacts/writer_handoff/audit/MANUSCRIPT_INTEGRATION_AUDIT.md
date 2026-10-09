# Manuscript Integration Audit

**Date:** 2026-10-09  
**Branch:** revision1/major-revision-analyses  
**Manuscript:** `thermalops_manuscript.tex`  

This table records every quantitative claim in the manuscript, its source file,
the source value (before rounding), and its verification status.

---

## Fingerprint Characterization

| # | Claim (manuscript text) | Section | Source file | Source value | Status |
|---|------------------------|---------|-------------|--------------|--------|
| F1 | Pearson r = 0.926 (node-level) | Abstract, §3.2 | `artifacts/phase1/analysis/phase3a_results.json` → `node_level_companion.pearson_r` | 0.9259 | VERIFIED |
| F2 | Spearman ρ = 0.936 (node-level) | Abstract, §3.2 | `artifacts/phase1/analysis/phase3a_results.json` → `node_level_companion.spearman_r` | 0.9358 | VERIFIED |
| F3 | Direct no-refit R² = 0.848 (node-level) | Abstract, §3.2, §9 | `artifacts/revision2/m1_sensitivity_summary.json` → `key_stats.r2_frozen_individual_F` | 0.8482 | VERIFIED |
| F4 | 3,945 training jobs | §3.1 | `artifacts/phase1/analysis/phase3a_results.json` → `fingerprint_freeze.n_train_jobs` | 3945 | VERIFIED |
| F5 | 2,637 test jobs | Abstract, §3.1 | `artifacts/phase1/analysis/phase3a_results.json` → `fingerprint_freeze.n_test_jobs` | 2637 | VERIFIED |
| F6 | 2,000 node cohort | §3.1 | `artifacts/phase1/analysis/phase3a_results.json` → `fingerprint_freeze.n_fp_nodes` | 2000 | VERIFIED |
| F7 | 77 cabinets | §3.1 | Frontier system specification (fixed system parameter) | 74 compute cabinets + 3 storage/network — confirm exact count | VERIFY |
| F8 | 9,856 nodes total system | §3.1, Appendix D | Frontier public spec | 9,408 AMD GPU nodes + service nodes; confirm 9,856 figure refers to full node count | VERIFY |
| F9 | 9.2 exaflops (FP64) | §3.1 | Frontier public spec | nominal 1.102 ExaFLOPS FP64; confirm correct value (9.2 is FP8 or HPL?) | VERIFY |

---

## Replay Model Validation

| # | Claim (manuscript text) | Section | Source file | Source value | Status |
|---|------------------------|---------|-------------|--------------|--------|
| R1 | Cabinet power MAE = 0.37 kW | §3.3 | `artifacts/revision1/results/power_validation_60job.json` → `mae_kW` | 0.3723 | VERIFIED |
| R2 | 0.8% of P99 spread | §3.3 | Same → spread=48.21 kW; 0.3723/48.21=0.77% ≈ 0.8% | 0.77% | VERIFIED |

---

## Preregistered Protocol

| # | Claim (manuscript text) | Section | Source file | Source value | Status |
|---|------------------------|---------|-------------|--------------|--------|
| P1 | 16 preflight conditions | §4.2, Appendix A | `artifacts/revision2/challenge_preflight.json` → `n_conditions`, `overall_pass` | 16, true | VERIFIED |
| P2 | Seed 9999, 5,000 bootstrap draws | §4.3 | `artifacts/manuscript_completion/results/c2_correctedref_analysis.json` → `bootstrap` | seed=9999, n=5000 | VERIFIED |
| P3 | 1,990 nodes L1, 3 L3, 7 global (LOO) | §4.1 (Location) | Original LOO construction analysis; confirm from revision2 LOO audit file | — | VERIFY SOURCE |
| P4 | ρ = 0.9823 (Location template vs ground-truth) | §4.1, §7 | Original LOO analysis; confirm source file | — | VERIFY SOURCE |

---

## Original Results (Job-Contribution Reference)

| # | Claim (manuscript text) | Section | Source file | Source value | Status |
|---|------------------------|---------|-------------|--------------|--------|
| O1 | FP vs Random: +6.71 pp, 22/25 | §6.1 | `artifacts/revision2/challenge_analysis.json` → `FP_vs_Random.1.25.median_delta_lo` | 6.7063 pp | VERIFIED |
| O2 | FP vs Random CI [+3.92, +8.72] | §6.1 | Same → `bootstrap95_delta_lo` | [3.9197, 8.7249] | VERIFIED |
| O3 | FP vs WithinCab: +3.54 pp, 20/25 | §6.1 | `artifacts/revision2/challenge_analysis.json` → `FP_vs_WithinCab.1.25` | 3.5378 pp, n_A=20 | VERIFIED |
| O4 | FP vs WithinCab CI [+0.56, +4.44] | §6.1 | Same | [0.5581, 4.4353] | VERIFIED |

---

## Corrected-Reference Results — Experiment 2 (Table 1)

All eight values below verified from `artifacts/manuscript_completion/results/c2_correctedref_analysis.json`
(committed SHA `bcc319ca...`, commit 96b2ade).

| # | Comparison | n_A/n_I/n_B | Med. Δ_lo (pp) | 95% CI | Holm p | Sig | Status |
|---|-----------|-------------|----------------|--------|--------|-----|--------|
| E1 | FP vs Random | 25/0/0 | +12.48 | [+11.09, +19.04] | 4.77e-7 | Yes | VERIFIED |
| E2 | FP vs WithinCab | 24/1/0 | +10.88 | [+5.96, +17.40] | 4.77e-7 | Yes | VERIFIED |
| E3 | FP vs GlobalPlacebo | 25/0/0 | +12.31 | [+10.88, +17.40] | 4.77e-7 | Yes | VERIFIED |
| E4 | FP vs Location | 25/0/0 | +13.95 | [+12.23, +21.98] | 4.77e-7 | Yes | VERIFIED |
| E5 | FP-Spread vs Rand-Spread | 23/2/0 | +4.42 | [+2.14, +5.42] | 4.77e-7 | Yes | VERIFIED |
| E6 | FP-Spread vs FP | 0/0/25 | −9.18 | [−17.91, −6.60] | 4.77e-7 | Yes | VERIFIED |
| E7 | Rand-Spread vs Random | 5/14/6 | −0.19 | [−0.58, 0.00] | 1.000 | No | VERIFIED |
| E8 | FP-Spread vs Location | 24/1/0 | +4.96 | [+2.26, +8.34] | 4.77e-7 | Yes | VERIFIED |

Source exact values (pre-rounding):

| # | Field | Exact JSON value |
|---|-------|-----------------|
| E1 | median_delta_lo_pp | 12.475542747712177 |
| E1 | CI | [11.094795216637962, 19.038500058009284] |
| E2 | median_delta_lo_pp | 10.876... (verify from JSON key FP_vs_WithinCab) |
| E3 | median_delta_lo_pp | 12.309... (FP_vs_Global) |
| E4 | median_delta_lo_pp | 13.950... (FP_vs_PositionLOO) |
| E5 | median_delta_lo_pp | 4.420... (FPSpread_vs_RandSpread) |
| E6 | median_delta_lo_pp | -9.175... (FPSpread_vs_FP) |
| E7 | median_delta_lo_pp | -0.192... (RandSpread_vs_Random) |
| E8 | median_delta_lo_pp | 4.960... (FPSpread_vs_PositionLOO) |

---

## Corrected-Reference Results — Experiment 1 (Choice-Ratio Sweep)

| # | Claim (manuscript text) | Section | Source file | Status |
|---|------------------------|---------|-------------|--------|
| C1 | FP beats Random at every ratio r ≥ 1.25 | §6.2 | `c1_correctedref_analysis.json` → comparisons table | VERIFIED (see C1 analysis) |
| C2 | r=1.0 is negative control, yields indeterminate | §6.2 | Same → `FP_vs_Random.1.0` n_I=25 | VERIFIED |
| C3 | FP-Spread vs FP: Δ_lo = −9.18 pp (0/0/25) under corrected ref | §6.2 | `c2_correctedref_analysis.json` row E6 | VERIFIED |

---

## Threshold Sensitivity (Table 2)

All values verified from `artifacts/manuscript_completion/results/c3_threshold_analysis.json`
(final version, canonical P90 SHA `a94f7208...`).

| # | Threshold | n_A/n_I/n_B | Med. Δ_lo (pp) | 95% CI | Rand lb | Status |
|---|-----------|-------------|----------------|--------|---------|--------|
| T1 | P90 (61.875°C) | 24/1/0 | +8.90 | [+4.95, +14.50] | 3/25 | VERIFIED |
| T2 | P95 (63.625°C) | 25/0/0 | +12.48 | [+11.09, +19.04] | 9/25 | VERIFIED |
| T3 | P99 (66.6625°C) | 25/0/0 | +21.33 | [+16.39, +25.36] | 19/25 | VERIFIED |

Exact values (pre-rounding):

| Threshold | Field | Exact JSON value |
|-----------|-------|-----------------|
| P90 | median_delta_lo_pp | 8.896892365285431 |
| P90 | CI | [4.947107132029577, 14.497655459684012] |
| P99 | median_delta_lo_pp | 21.33222798675153 |
| P99 | CI | [16.39272822676746, 25.364214377659323] |

---

## Binding Constraint Counts

| # | Claim | Section | Source | Value | Status |
|---|-------|---------|--------|-------|--------|
| B1 | P90/P95: FP crossings 100% B_ratio | §7.1, App. C | `c3_threshold_analysis.json` → `thresholds.P90.binding_constraints.full_fp.counts` | B_ratio=25/25 | VERIFIED |
| B2 | P99: 20/25 FP crossings shift to S_ratio | §7.1, App. C | Same → `thresholds.P99.binding_constraints.full_fp.counts` | S_ratio=20, B_ratio=5 | VERIFIED |

---

## Items Requiring Source Verification Before Submission

| # | Claim | Issue |
|---|-------|-------|
| F7 | 77 cabinets | Confirm "77 cabinets" refers to 74 compute + 3 other or total = 74 |
| F8 | 9,856 nodes | Confirm this is the public Frontier node count (compute nodes only) |
| F9 | 9.2 exaflops | Confirm unit: Frontier's HPL is ~1.102 ExaFLOPS FP64; 9.2 may be FP8 or a different metric |
| P3 | 1,990/3/7 LOO tiers | Locate source file for LOO tier counts |
| P4 | ρ = 0.9823 LOO template | Locate source file for LOO vs ground-truth correlation |
| ALL | Bibliography entries | TAPAS, PAL, sinha2023thermal, ostrouchov2020machine marked [VERIFY] in thermalops.bib |

---

## Prohibited Values (must not appear)

The following old or internal values must not appear in the final manuscript.
See also STALE_VALUE_SCAN.md.

| Old value | Replaced by | Where checked |
|-----------|-------------|---------------|
| +6.71 pp as primary claim | Retained only in §6.1 as original result | §6.1 only |
| 22/25 as primary claim | Retained only in §6.1 as original result | §6.1 only |
| +3.54 pp as primary claim | Retained only in §6.1 | §6.1 only |
| "Other" binding constraint category | B_ratio / S_ratio | App. C, §7 |
| "thermal budget relaxes" | Correct: alternative exposure definitions | §7 |
| Gate F, C1/C2/C3/C4, F1/F2, revision1/2/3 | No internal names in manuscript | Full text |
| R² = 0.857 (old node-level) | R² = 0.848 (direct no-refit) | §3 |
