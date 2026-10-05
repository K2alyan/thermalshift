# Existing-Output Diagnostics — Round-3 (Task B)

**Post-exposure:** post-exposure reviewer-requested; designed and executed after sc30-sc54 primary results observed
**Source:** `artifacts\revision2\challenge_analysis.json`

---

## B1. Absolute Capacity Levels at r=1.25

| Policy | Median C_lower (%) | Median C_upper (%) | Bracket width | n_right_censored |
|---|---|---|---|---|
| full_fp | 7.3318 | 7.3756 | 0.0438 | 0 |
| full_random | 0.1028 | 0.5752 | 0.4724 | 0 |
| full_fp_spread | 4.9611 | 5.5389 | 0.5778 | 0 |
| random_spread | 0.1199 | 0.8340 | 0.7141 | 0 |
| fp_withincab_placebo | 2.8848 | 3.9942 | 1.1095 | 0 |
| fp_global_placebo | 0.7558 | 1.3018 | 0.5460 | 0 |
| position_template | 4.5745 | 5.7800 | 1.2055 | 0 |

## B2. Binding Constraint Diagnostic (legacy cabinet reference)

| Comparison | A/I/B | Median δ_lo (pp) | Bootstrap 95% CI |
|---|---|---|---|
| FP_vs_Random | 22/1/2 | +6.706 | [+3.920, +8.725] |
| FP_vs_WithinCabPlacebo | 20/5/0 | +3.538 | [+0.558, +4.435] |
| FP_vs_GlobalPlacebo | 22/1/2 | +4.548 | [+2.945, +7.817] |
| RandomSpread_vs_Random | 8/14/3 | +0.000 | [-0.256, +0.030] |
| FPSpread_vs_RandomSpread | 20/5/0 | +2.152 | [+0.525, +4.249] |
| FPSpread_vs_FP | 4/3/18 | -2.640 | [-4.489, -2.004] |
| FP_vs_PositionTemplate | 16/5/4 | +0.741 | [-0.816, +1.504] |
| FPSpread_vs_PositionTemplate | 6/11/8 | -1.159 | [-2.294, -0.254] |

## B3. FPSpread vs FP — crossover

Crossover point: **8.0**

| Ratio | FPSpread_vs_FP median δ_lo | A/I/B |
|---|---|---|
| 1.0 | -0.2302 | 0/25/0 |
| 1.25 | -2.6403 | 4/3/18 |
| 1.5 | -2.8761 | 1/4/20 |
| 2.0 | -2.9506 | 4/4/17 |
| 4.0 | -0.4638 | 12/3/10 |
| 8.0 | +0.7215 | 17/3/5 |
| unrestricted | +2.0117 | 21/3/1 |

## B4. Sign Tests with Holm-Bonferroni Correction (r=1.25)

| Comparison | A/I/B | p_raw | p_Holm | Reject H0 |
|---|---|---|---|---|
| FP_vs_Random | 22/1/2 | 0.0001 | 0.0006 | YES |
| FP_vs_WithinCabPlacebo | 20/5/0 | 0.0020 | 0.0122 | YES |
| FP_vs_GlobalPlacebo | 22/1/2 | 0.0001 | 0.0005 | YES |
| RandomSpread_vs_Random | 8/14/3 | 0.9784 | 1.0000 | no |
| FPSpread_vs_RandomSpread | 20/5/0 | 0.0020 | 0.0102 | YES |
| FPSpread_vs_FP | 4/3/18 | 0.9999 | 0.9999 | no |
| FP_vs_PositionTemplate | 16/5/4 | 0.1148 | 0.4590 | no |
| FPSpread_vs_PositionTemplate | 6/11/8 | 0.9980 | 1.0000 | no |

## B5. Decomposition Contrasts (exploratory)

| Contrast | Median δ_lo (pp) | Interpretation |
|---|---|---|
| global_score_advantage | +4.5475 | Advantage from knowing global thermal ordering vs random permutation |
| node_vs_cabinet_specificity | +3.5378 | Node-level fingerprint advantage beyond cabinet-level composition |
| cabinet_composition_advantage | +2.1588 | Advantage attributable to cabinet-level thermal composition (approximate decomposition) |
| spreading_cost_constrained | -2.6403 | Cost of cabinet-spreading at r=1.25 (FPSpread loses to FP) |

## B6. Order-Statistic Median CI (n=25)

OS_8 and OS_18; actual coverage = 0.9567

| Comparison | Median δ_lo | OS CI | Bootstrap 95% CI |
|---|---|---|---|
| FP_vs_Random | +6.706 | [+3.920, +8.725] | [+3.920, +8.725] |
| FP_vs_WithinCabPlacebo | +3.538 | [+0.558, +4.435] | [+0.558, +4.435] |
| FP_vs_GlobalPlacebo | +4.548 | [+2.945, +7.817] | [+2.945, +7.817] |
| RandomSpread_vs_Random | +0.000 | [-0.256, +0.030] | [-0.256, +0.030] |
| FPSpread_vs_RandomSpread | +2.152 | [+0.525, +4.249] | [+0.525, +4.249] |
| FPSpread_vs_FP | -2.640 | [-4.489, -2.004] | [-4.489, -2.004] |
| FP_vs_PositionTemplate | +0.741 | [-0.816, +1.504] | [-0.816, +1.504] |
| FPSpread_vs_PositionTemplate | -1.159 | [-2.294, -0.254] | [-2.294, -0.254] |

## B7. sc5–sc29 Evaluation (revision1 design, exploratory context)

n_scenarios: 25

| Comparison | n | Median δ_approx | Bootstrap 95% | n+/0/− |
|---|---|---|---|---|
| FP_vs_Random | 25 | -0.4370 | [-0.6604, -0.1729] | 5/0/20 |
| FP_vs_Loc | 25 | +0.1222 | [-0.1267, +0.9401] | 14/0/11 |
| FPSpread_vs_FP | 25 | +0.3168 | [+0.2341, +0.5049] | 21/0/4 |

---

*Post-exposure reviewer-requested analysis.*
