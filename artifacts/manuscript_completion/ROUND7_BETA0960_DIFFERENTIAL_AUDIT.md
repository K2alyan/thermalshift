# Round-7 Beta=0.960 Differential Audit

Generated: 2026-10-10  
Branch: revision1/major-revision-analyses

## Purpose

Verify that beta_F = 0.960 is the only scientific change relative to the
canonical-beta run (beta_F = 1.11416358). All quantities set before beta is
applied must be identical across the two runs.

## Files audited

| File | SHA256 |
|---|---|
| gate_f_sc30-54_1p0_1p25_c7primary.json (canonical) | 7bca547c732f8ce2b299a5fadf337fdc2a5bf50de06b184a9d0144515b1514ea |
| gate_f_sc30-54_1p0_1p25_c7beta0p960.json (sensitivity) | 3c1f38babca9ec69b4604684621ab03d87daef7d3b659f167bf249356d6cfa3f |

## Upstream field classification

**Must be identical (set before beta is applied):**
- scen_seed, wl_seed — scenario and workload random seeds
- syn_node_hours — synthetic load (physical, not budget-dependent)
- mean_F_syn, cab_span_median — physical characteristics
- n_syn_admit, n_drop_physical, n_drop_la, n_base_unserved — physical counts
- invariant_violated — physical invariant
- full_selector / exposed_selector / realized_selector percentile fields —
  candidate-set statistics, computed before budget application

**Expected to differ (downstream of beta_F):**
- B_ref_s, S_ref_s — reference budget and service level (beta-multiplied)
- B_primary_h, S_primary_Cdoth, B_secondary_h, B_cab_ratio
- capacity_unlock_pct, lambda_val grid
- n_drop_cap — capacity-constrained drops
- infeasible, first_binding — feasibility at given lambda
- B_primary_ratio, S_primary_ratio
- C_lower_pct, C_upper_pct, crossing status

## Audit result

Upstream fields checked: 1,750 (across 25 scenarios × 4 policies, lam=1.0 rows)  
Upstream failures: 0

**PASS — beta_F is the only scientific change confirmed.**

## Effect-attenuation table

| Comparison | b=1.114 A/I/B | b=0.960 A/I/B | b=1.114 med_lo | b=0.960 med_lo | abs chg | rel% | Direction? |
|---|---|---|---|---|---|---|---|
| FP vs Random | 25/0/0 | 25/0/0 | +12.476 pp | +10.477 pp | −1.998 pp | −16.0% | YES |
| FP vs WithinCab | 24/1/0 | 24/1/0 | +10.883 pp | +6.893 pp | −3.990 pp | −36.7% | YES |
| FP vs PositionGroupHash | 24/1/0 | 23/2/0 | +7.265 pp | +5.120 pp | −2.145 pp | −29.5% | YES |
| PositionGroupHash vs Random | 21/4/0 | 23/2/0 | +4.582 pp | +3.428 pp | −1.154 pp | −25.2% | YES |

All four comparisons preserve direction. No B verdicts in either run.

## Scientific questions answered

1. Does FP remain directionally ahead of Random? **YES** (25/0/0 at both betas)
2. Does FP remain ahead of WithinCab? **YES** (24/1/0 at both betas)
3. Does FP remain ahead of PositionGroupHash? **YES** (24→23 A-wins; one scenario moves to I)
4. Does PositionGroupHash remain better than Random? **YES** (21→23 A-wins; straddlers reduce)

## Absolute capacity changes

All policies attenuate slightly under tighter budget (expected):

| Policy | b=1.114 C_lower | b=0.960 C_lower | change |
|---|---|---|---|
| full_fp | 15.35% | 14.72% | −0.63 pp |
| position_group_hash | 8.45% | 7.83% | −0.62 pp |
| fp_withincab_placebo | 4.04% | 2.35% | −1.69 pp |
| full_random | 0.10% | ~0.00% | ~−0.10 pp |

## Censoring changes

Left-boundary (zero-capacity floor) increases for weaker policies under tighter budget:
- full_random: 9→11 left-boundary scenarios
- fp_withincab_placebo: 2→4 left-boundary scenarios
- full_fp: unchanged (0)
- position_group_hash: unchanged (0)

No right-censoring in any policy at either beta.

## Binding constraint changes

| Policy | b=1.114 binding | b=0.960 binding |
|---|---|---|
| full_fp | B_ratio: 25 | B_ratio: 25 |
| position_group_hash | B_ratio: 23, S_ratio: 2 | B_ratio: 21, S_ratio: 4 |
| fp_withincab_placebo | B_ratio: 22, S_ratio: 3 | B_ratio: 21, S_ratio: 4 |
| full_random | B_ratio: 22, S_ratio: 3 | B_ratio: 23, S_ratio: 2 |

At lower beta, S_ratio binds more frequently for structured policies
(tighter budget means supply constraint is reached sooner relative to demand).
FP remains exclusively B_ratio constrained at both betas.

## Interpretation

The beta=0.960 sensitivity confirms that the structural hierarchy
Random < PositionGroupHash < FP is robust to the independently-motivated
prospective coefficient. Magnitudes attenuate by 16–37%, consistent with a
tighter budget reducing overall scheduling headroom. No comparison reverses
direction; no new B verdicts appear. The corrected structural baseline story
survives the sensitivity intact.
