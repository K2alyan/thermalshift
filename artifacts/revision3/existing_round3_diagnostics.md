# Existing-Output Diagnostics — Round-3 (Task B)

**Amendment:** 2  **Plan version:** 2.1
**Post-exposure:** post-exposure reviewer-requested; designed and executed after sc30-sc54 primary results observed
**Source:** `artifacts\revision2\challenge_analysis.json`

---

## B1. Absolute Capacity Levels at r=1.25

| Policy | Median C_lower (%) | Median C_upper (%) | Bracket width (excl infeasible) | n_base_infeasible | n_floor_at_zero | n_right_censored |
|---|---|---|---|---|---|---|
| full_fp | 7.3318 | 7.3756 | 0.1855 | 0 | 0 | 0 |
| full_random | 0.1028 | 0.5752 | 0.2430 | 9 | 3 | 0 |
| full_fp_spread | 4.9611 | 5.5389 | 0.3196 | 0 | 0 | 0 |
| random_spread | 0.1199 | 0.8340 | 0.2811 | 10 | 1 | 0 |
| fp_withincab_placebo | 2.8848 | 3.9942 | 0.4456 | 2 | 0 | 0 |
| fp_global_placebo | 0.7558 | 1.3018 | 0.3123 | 7 | 1 | 0 |
| position_template | 4.5745 | 5.7800 | 0.4278 | 0 | 0 | 0 |

## B2. Binding Constraint Diagnostic (legacy cabinet reference)

| Comparison | A/I/B | n_both_infeasible | Median delta_lo (pp) | Bootstrap 95% CI |
|---|---|---|---|---|
| FP_vs_Random | 22/1/2 | 0 | +6.706 | [+3.920, +8.725] |
| FP_vs_WithinCabPlacebo | 20/5/0 | 0 | +3.538 | [+0.558, +4.435] |
| FP_vs_GlobalPlacebo | 22/1/2 | 0 | +4.548 | [+2.945, +7.817] |
| RandomSpread_vs_Random | 8/14/3 | 6 | +0.000 | [-0.256, +0.030] |
| FPSpread_vs_RandomSpread | 20/5/0 | 0 | +2.152 | [+0.525, +4.249] |
| FPSpread_vs_FP | 4/3/18 | 0 | -2.640 | [-4.489, -2.004] |
| FP_vs_PositionTemplate | 16/5/4 | 0 | +0.741 | [-0.816, +1.504] |
| FPSpread_vs_PositionTemplate | 6/11/8 | 0 | -1.159 | [-2.294, -0.254] |

## B3. FPSpread vs FP — Both Directions

FPSpread_vs_FP: delta_lo = C_lower(FPSpread) - C_upper(FP).
FP-over-FPSpread reverse: uses identity delta_lo(FP,FPSpread) = -delta_hi(FPSpread,FP).
NEVER negate delta_lo for the reverse direction.

Crossover point (FPSpread_vs_FP median delta_lo flips +): **8.0**

| Ratio | FPSpread_vs_FP median delta_lo | A/I/B | FP_over_FPSpread median (-delta_hi) |
|---|---|---|---|
| 1.0 | -0.2302 | 0/25/0 | -0.2302 |
| 1.25 | -2.6403 | 4/3/18 | +2.1482 |
| 1.5 | -2.8761 | 1/4/20 | +1.0733 |
| 2.0 | -2.9506 | 4/4/17 | +1.8552 |
| 4.0 | -0.4638 | 12/3/10 | -1.3969 |
| 8.0 | +0.7215 | 17/3/5 | -2.6316 |
| unrestricted | +2.0117 | 21/3/1 | -3.2506 |

## B4. Sign Tests with Holm-Bonferroni Correction (r=1.25)

Two-sided exact binomial on decisive scenarios only (indistinguishable excluded from n_decisive).
Holm correction: cumulative-maximum step applied before capping at 1.0 (Amendment 2 fix).

| Comparison | A/I/B | n_decisive | p_raw (two-sided) | p_Holm | Reject H0 |
|---|---|---|---|---|---|
| FP_vs_Random | 22/1/2 | 24 | 0.000036 | 0.000215 | YES |
| FP_vs_WithinCabPlacebo | 20/5/0 | 20 | 0.000002 | 0.000015 | YES |
| FP_vs_GlobalPlacebo | 22/1/2 | 24 | 0.000036 | 0.000215 | YES |
| RandomSpread_vs_Random | 8/14/3 | 11 | 0.226562 | 0.453125 | no |
| FPSpread_vs_RandomSpread | 20/5/0 | 20 | 0.000002 | 0.000015 | YES |
| FPSpread_vs_FP | 4/3/18 | 22 | 0.004344 | 0.017374 | YES |
| FP_vs_PositionTemplate | 16/5/4 | 20 | 0.011818 | 0.035454 | YES |
| FPSpread_vs_PositionTemplate | 6/11/8 | 14 | 0.790527 | 0.790527 | no |

## B5. Direct Paired Decomposition Contrasts (post-exposure exploratory)

Direct per-scenario bracket contrasts: delta_lo(A,B) = C_lower(A) - C_upper(B);
delta_hi(A,B) = C_upper(A) - C_lower(B). Algebraic median subtraction NOT used.
Both-infeasible scenarios: treated as [0,0] -> indistinguishable.

| Contrast | A/I/B | n_both_infeasible | Median delta_lo | Median delta_hi | Boot95 delta_lo | p (sign test) |
|---|---|---|---|---|---|---|
| GlobalPlacebo_vs_Random | 8/13/4 | 5 | +0.0000 | +0.2541 | [-0.3728, +0.5088] | 0.387695 |
| WithinCabPlacebo_vs_GlobalPlacebo | 14/7/4 | 2 | +0.0141 | +0.9560 | [-0.3435, +1.4484] | 0.030884 |
| FP_vs_WithinCabPlacebo | 20/5/0 | 0 | +3.5378 | +3.9417 | [+0.5581, +4.4353] | 0.000002 |

## B6. Order-Statistic Median CI (n=25)

OS_8 and OS_18; actual coverage = 0.9567

| Comparison | Median delta_lo | OS CI | Bootstrap 95% CI |
|---|---|---|---|
| FP_vs_Random | +6.706 | [+3.920, +8.725] | [+3.920, +8.725] |
| FP_vs_WithinCabPlacebo | +3.538 | [+0.558, +4.435] | [+0.558, +4.435] |
| FP_vs_GlobalPlacebo | +4.548 | [+2.945, +7.817] | [+2.945, +7.817] |
| RandomSpread_vs_Random | +0.000 | [-0.256, +0.030] | [-0.256, +0.030] |
| FPSpread_vs_RandomSpread | +2.152 | [+0.525, +4.249] | [+0.525, +4.249] |
| FPSpread_vs_FP | -2.640 | [-4.489, -2.004] | [-4.489, -2.004] |
| FP_vs_PositionTemplate | +0.741 | [-0.816, +1.504] | [-0.816, +1.504] |
| FPSpread_vs_PositionTemplate | -1.159 | [-2.294, -0.254] | [-2.294, -0.254] |

## B7. sc5-sc29 Evaluation (revision1 design, development-era, exploratory context)

**Authoritative source:** `artifacts\revision1\results\gate_f_heldout_analysis.json`
**Note:** Values read directly from gate_f_heldout_analysis.json (NOT gate_f_sc5-29 file).
n_scenarios: 25

| Comparison | A/I/B | Median delta_lo | Bootstrap95 delta_lo |
|---|---|---|---|
| FP_vs_Random | 25/0/0 | 4.771026 | [2.585024, 6.063253] |
| Loc_vs_Random | 22/3/0 | 2.620803 | [1.100455, 5.149012] |
| FPSpread_vs_Random | 21/4/0 | 1.611426 | [0.438159, 2.908751] |
| FPSpread_vs_FP | 3/3/19 | -3.362997 | [-4.935221, -1.879605] |
| FPSpread_vs_Loc | 2/11/12 | -1.170622 | [-3.295356, -0.486615] |

---

*Post-exposure reviewer-requested analysis. Amendment 2 corrected.*
