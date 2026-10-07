# Corrected Concurrent-Load Reference — Conservative Estimand Re-analysis

**Date:** 2026-10-06
**Source:** `artifacts/revision3/results/gate_f_sc30-54_1p25_r3f2local.json`
**Source SHA256:** `5982264fcf719cc4746b23ae6ef0aaf9e22a9700e4b6ef3e19e49a98b5460dca`

---

## Purpose

The frozen Experiment 2 challenge uses the conservative interval-aware estimand:

    delta_lo = C_lower(A) - C_upper(B)
    delta_hi = C_upper(A) - C_lower(B)

The earlier corrected-reference analysis (`f2_primary_result.json`) used the non-conservative form:

    delta_lo = C_lower(FP) - C_lower(Random)

This file re-expresses the corrected concurrent-load reference result on the same conservative estimand so that F1 and F2 are directly comparable.

---

## Result (Conservative Estimand)

| Metric | Corrected reference (concurrent-load) | Job-contribution reference (frozen challenge) |
|---|---|---|
| Estimand | delta_lo = C_lower(FP) - C_upper(Random) | Same |
| A / I / B | **25 / 0 / 0** | 22 / 1 / 2 |
| Median delta_lo | **+12.48 pp** | +6.71 pp |
| Bootstrap 95% CI | **[+11.09, +19.04] pp** | [+3.92, +8.72] pp |
| Bootstrap seed | 9999, n=5000 | 9999, n=5000 |
| Interpretation | SUPPORTS_FP | SUPPORTS_FP |
| Directional agreement | YES | — |

---

## Effect of Estimand Choice on Corrected-Reference Result

| Estimand | Median delta_lo | 95% CI | A/I/B |
|---|---|---|---|
| Conservative: C_lower(FP) - C_upper(Random) | +12.48 pp | [+11.09, +19.04] pp | 25/0/0 |
| Non-conservative: C_lower(FP) - C_lower(Random) | +12.76 pp | [+11.10, +19.35] pp | 25/0/0 |
| Difference | 0.28 pp | ~0.02 / 0.31 pp | identical |

The A/I/B counts are identical under both estimands because FP's C_lower exceeds Random's C_upper in all 25 scenarios (FP's advantage is large enough to clear the full Random bracket). The 0.28 pp difference in median reflects the narrow FP bracket width (median ~0.19 pp) combined with modest Random bracket widths.

---

## Left-Boundary and Censoring

| | Corrected reference | Job-contribution reference |
|---|---|---|
| FP left_boundary | 0/25 | 0/25 |
| Random left_boundary | 9/25 | 9/25 |
| FP right_censored | 0/25 | 0/25 |
| Random right_censored | 0/25 | 0/25 |

The 9 Random left_boundary scenarios are identical under both cabinet references. In all 9, B_cab_ratio < 1.0 under both references. Of the 9: 8 have B_ratio > 1.0 (cumulative thermal exceedance budget); 4 of those 8 also have S_ratio > 1.0 (severity-weighted thermal exposure budget, deg-C x node-hours above threshold): sc41, sc51, sc52, sc54. sc51 is the only scenario where S_ratio alone causes infeasibility (B_ratio = 0.987 < 1.0). The cabinet reference does not affect left_boundary status.

For these 9 scenarios, the universal delta formulas apply as normal: FP has C_lower > 0 in all 9 (n_left_boundary_fp = 0), so delta_lo = C_lower(FP) - C_upper(Random) = C_lower(FP) - 0 > 0 in each, yielding definite A. All 25 scenarios are therefore A under the conservative estimand.

---

## Frozen Challenge Reference Artifact

- **Job-contribution reference raw result:** `artifacts/revision3/results/gate_f_sc30-54_1p25_r3legacy.json`
- **SHA256:** `0f2736058fca95117d5a03cb43e08eab93145c3d5ea7c82054ecc4cb08ddea97`
- **Analysis:** `artifacts/revision2/challenge_analysis.json`
- **Analysis SHA256:** `3a8bbd0aba95209e8d383bb94f9b57b93df98a37d8cfa7423d8db0db115edac4`
- **Runner commit:** `5733b73bd715157f479821d969aac99811eee0d7`

---

## Manuscript Wording (defensible)

Under the corrected concurrent-load cabinet reference and replay-matched historical denominator, fingerprint-guided placement (FP) outperforms random placement in all 25 scenarios (25/0/0), with a median conservative paired lower-bound advantage of +12.48 percentage points (bootstrap 95% CI [+11.09, +19.04] pp, 5,000 draws, seed 9999). The result is consistent in direction with the frozen job-contribution reference result (22/1/2, +6.71 pp, CI [+3.92, +8.72] pp) and larger in magnitude.
