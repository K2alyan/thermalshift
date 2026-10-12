# M4 V3 Final Audit

**Date:** 2026-09-30
**Script:** `artifacts/revision1/analysis/r1_m4_v3_independent_audit.py`

## Status

**`m4_canonical_comparisons_v3.json` is the authoritative M4 output.**
All prior M4 comparison JSONs are superseded.

| File | Status |
|------|--------|
| `m4_canonical_comparisons.json` (original) | Superseded — stored crossings used lambda-order scan |
| `m4_canonical_comparisons_v2.json` | Superseded — corrected only 6 inverted brackets, not 102 non-inverted-but-wrong |
| `m4_canonical_comparisons_v3.json` | **Authoritative** — all 120 crossings reconstructed |

## Crossing reconstruction estimand

**Conservative first-violation estimand:**
1. Sort all evaluated (lambda, capacity_unlock_pct) points by `capacity_unlock_pct`.
2. `C_upper` = first point in that order with `infeasible=True`.
3. `C_lower` = largest `capacity_unlock_pct` among all feasible points strictly before `C_upper`.
4. Feasible re-entries after the first violation do not advance `C_lower`.
5. If the first point (lowest capacity) is infeasible → `left_boundary`.
6. If no point is infeasible → `right_censored` (does not occur in this dataset).

## `capacity_unlock_pct` definition

```
capacity_unlock_pct = (syn_node_hours / hist_total_nh) * 100
```

- `syn_node_hours`: admitted synthetic (incremental) node-hours at offered load λ.
- `hist_total_nh`: total node-hours of the historical base workload
  (= 78907.3775 node-hours, from `data_anchors`).
- Non-monotone in λ because discrete placement decisions under thermal/power/QoS constraints
  can admit fewer synthetic node-hours at higher λ than at lower λ.
  This non-monotonicity is the root cause of the crossing reconstruction bug.

## Root cause of crossing defects

The original summarizer scanned `lambda_rows` in **lambda order** to find the first
feasible→infeasible transition. Because `capacity_unlock_pct` is non-monotone in λ,
the lambda-order first transition does not correspond to the first violation in
capacity order. The stored `C_upper` was often a **feasible** evaluated point
(the `lambda_{k+1}` value after the last lambda-order feasible point),
not a violating point. Inverted brackets occurred when an infeasible point at
lower capacity appeared later in lambda order than a feasible point at higher capacity.

## Audit results

| Metric | Value |
|--------|-------|
| Total crossings audited | 120/120 (4 policies × 30 scenarios) |
| Exact match (stored = reconstructed) | 13/120 |
| Inverted stored bracket | 5/120 |
| Non-inverted but wrong | 102/120 |
| **Total defective** | **107/120** |
| Max ΔC_lower | 4.31 pp |
| Max ΔC_upper | 8.04 pp |
| Right-censored (stored) | 0/120 |
| Right-censored (reconstructed) | 0/120 |
| C_lower > C_upper (reconstructed) | 0/120 |

## Independent validation checks

All 7 checks passed in `r1_m4_v3_independent_audit.py`:

1. `capacity_unlock_pct = syn_node_hours / hist_total_nh * 100` verified for all rows.
2. 120/120 crossings reconstructed from source `lambda_rows`.
3. 0/120 right-censored reconstructions (asserted).
4. 0/120 C_lower > C_upper violations in reconstruction (asserted).
5. 115/115 crossing values in v3 `scenario_rows` match independent reconstruction
   (tolerance 1e-6 pp).
6. fp_spread sc0–4 (not in v3 comparisons) match `m4_crossing_audit.json` reconstruction.
7. All 5 bootstrap CIs reproduced from independent reconstruction to within 1e-4 pp.
   Bootstrap confirmed as paired scenario-level resampling of per-scenario delta values.

## Authoritative v3 comparison results

N_BOOTSTRAP = 5000, BOOTSTRAP_SEED = 9999.
Comparison rows: fp_vs_rand=30, loc_vs_rand=30, spread_vs_rand=25,
spread_vs_fp=25, spread_vs_loc=25 → **total 135** (not 150).

| Comparison | def_A / ind / def_B | dlo_med | CI95(dlo) | dhi_med | CI95(dhi) |
|------------|---------------------|---------|-----------|---------|-----------|
| FP vs Random (n=30) | 24/5/1 | +1.894 pp | [+1.091, +4.351] | +5.781 pp | [+4.892, +6.892] |
| Loc vs Random (n=30) | 24/6/0 | +3.218 pp | [+1.773, +5.186] | +6.727 pp | [+5.513, +8.317] |
| FP-spread vs Random (n=25) | 22/3/0 | +5.203 pp | [+4.027, +7.549] | +8.569 pp | [+6.718, +11.560] |
| FP-spread vs FP (n=25) | 18/6/1 | +1.764 pp | [+0.553, +2.375] | +3.796 pp | [+2.343, +5.436] |
| FP-spread vs Loc (n=25) | 11/14/0 | -0.807 pp | [-1.148, +1.067] | +2.913 pp | [+1.017, +5.105] |

## Scientific interpretation

- **FP vs Random**: 24/30 definite FP wins. Median conservative paired advantage
  +1.89 pp, CI95 [+1.09, +4.35] pp. Thermal fingerprinting clearly improves over random.
- **Location vs Random**: 24/30 definite Location wins. Median +3.22 pp.
  Location-only baseline is strong.
- **FP-spread vs Random**: 22/25 definite wins. Strongest policy vs baseline.
- **FP-spread vs FP**: 18/25 definite wins. FP-spread improves over plain FP.
  Median +1.76 pp, CI95 [+0.55, +2.38] pp.
- **FP-spread vs Location**: 11/25 definite FP-spread wins, 14/25 indistinguishable,
  0/25 definite Location wins. Median conservative difference −0.81 pp,
  CI95 [−1.15, +1.07] pp. **FP-spread and Location-only are not consistently
  distinguishable.** The thermal fingerprint provides value over random placement
  and over plain FP, but a strong location-only baseline captures a large fraction
  of the achievable scheduling benefit.

## Superseded claims

The original stored crossings (lambda-order scan) produced overstated advantages.
Key corrections:

| Metric | Original (stored) | V3 (reconstructed) |
|--------|-------------------|--------------------|
| FP vs Random: def_A | 27/30 | 24/30 |
| FP vs Random: dlo_med | +4.32 pp | +1.89 pp |
| FP-spread vs Location: def_A | 18/25 | 11/25 |
| FP-spread vs Location: dlo_med | +1.25 pp | −0.81 pp |

The 'FP ~4 pp gain' headline is superseded. The most defensible conservative
paired statistic for FP vs Random is +1.89 pp (v3 dlo_med).

---
*Generated by `r1_m4_v3_independent_audit.py`. No simulation was rerun.*