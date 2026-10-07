# F2 Primary Result

**Date:** 2026-10-06
**Manifest:** F2_EXECUTION_MANIFEST_V2.json (commit 59e1d7c)
**Runner commit:** 4fa1b50
**Result file:** results/gate_f_sc30-54_1p25_r3f2local.json
**Result SHA256:** 5982264fcf719cc4746b23ae6ef0aaf9e22a9700e4b6ef3e19e49a98b5460dca

---

## Experiment

Scenarios sc30–sc54 (25 held-out scenarios), `full_fp` vs `full_random`, r=1.25, using the corrected time-weighted total P99 local-date cabinet thresholds (F2) and the replay-matched historical exceedance denominator (B_cab_hist_F2_replay = 871.37 h). No checkpoint reuse.

---

## Primary Result

| Metric | F2 (this experiment) | F1 (frozen reference) |
|---|---|---|
| Scenarios | 25 | 25 |
| A / I / B | **25 / 0 / 0** | 22 / 0 / 3 |
| Median delta_lo | **+12.76 pp** | +6.78 pp |
| 95% CI on median delta_lo | **[+11.10, +19.35] pp** | [+4.07, +8.82] pp |
| Interpretation | **SUPPORTS_FP** | SUPPORTS_FP |
| Directional agreement | **YES** | — |

Bootstrap: 5000 draws, seed=9999.

---

## Capacity Summary

C_lower_pct = lower bound of the synthetic-capacity interval at the first-binding crossing, expressed as % of baseline node-hours. This is an absolute policy capacity measure, not delta_lo. delta_lo = FP C_lower − Random C_lower per scenario; median delta_lo = +12.76 pp is kept separate.

| Policy | F2 median C_lower | F2 IQR | F1 median C_lower | F1 IQR |
|---|---|---|---|---|
| full_fp | 15.35% | [12.23%, 22.83%] | 7.33% | [4.90%, 9.36%] |
| full_random | 0.10% | [0.00%, 3.48%] | 0.10% | [0.00%, 2.79%] |

---

## Censoring

| | F2 | F1 |
|---|---|---|
| FP left_boundary | 0 / 25 | 0 / 25 |
| Random left_boundary | **9 / 25** | **9 / 25** |
| FP right_censored | 0 / 25 | 0 / 25 |
| Random right_censored | 0 / 25 | 0 / 25 |

The 9 Random left_boundary scenarios are identical in F1 and F2 (absolute scenarios sc36, sc38, sc41, sc44, sc45, sc47, sc51, sc52, sc54). In all 9 cases under both references, B_cab_ratio < 1.0 at lambda=1.0 — the cabinet constraint is not binding. Eight of the nine have B_ratio > 1.0 at lambda=1.0 (cumulative thermal exceedance budget exceeded). Four also have S_ratio > 1.0 (severity-weighted thermal exposure budget, degree-C × node-hours above threshold): sc41, sc51, sc52, sc54. sc51 is the only case where S_ratio alone makes the baseline infeasible (B_ratio = 0.987 < 1.0). All nine are therefore infeasible because of the thermal B and/or severity-weighted S budgets; B_cab_ratio remains below 1.0 under both F1 and F2. The B_ratio and S_ratio values at lambda=1.0 are identical between F1 and F2 for all 9 scenarios; the F2 correction does not change their left_boundary status.

---

## First-Binding Constraints

| Policy | F2 | F1 |
|---|---|---|
| full_fp | B_ratio: 25/25 | B_cab_ratio: 23/25, B_ratio: 2/25 |
| full_random | B_ratio: 22/25, S_ratio: 3/25 | B_ratio: 19/25, B_cab_ratio: 4/25, S_ratio: 2/25 |

**Key structural shift:** Under F1, the cabinet budget constraint was first-binding for FP in 23/25 scenarios, capping achievable capacity. Under the corrected F2 cabinet reference and replay-matched historical denominator, cabinet power is no longer the first-binding constraint for FP in any of the 25 scenarios; the thermal budget (B_ratio) binds first in all 25. The transition is 23/25 B_cab_ratio → B_ratio, 2/25 B_ratio → B_ratio (sc36 and sc38 were already thermal-constrained under F1). This allows higher unlocked capacity (FP median C_lower 15.35% under F2 vs 7.33% under F1).

---

## F1 vs F2 Comparison

Both experiments support FP over Random at r=1.25 (directional agreement = YES). The F2 result is stronger:

- A count: 25/25 vs 22/25
- Median delta_lo: +12.76 pp vs +6.78 pp (shift: +5.98 pp)
- CI lower bound: +11.10 pp vs +4.07 pp (shift: +7.03 pp)
- CI entirely above zero in both cases

Under the corrected F2 cabinet reference and replay-matched historical denominator, cabinet power is no longer the first-binding constraint for FP in any of the 25 scenarios; B_ratio (thermal) binds first in all 25. Under F1, 23/25 FP scenarios were cabinet-constrained, capping achievable capacity. The 23 scenarios that transition from B_cab_ratio → B_ratio account for the increase in FP median C_lower from 7.33% to 15.35%.

Random left_boundary: 9/25 in both F1 and F2, identical set of scenarios. The cabinet constraint is not binding for Random in any of these cases under either reference. Eight of the nine have B_ratio > 1.0 at lambda=1.0; four also have S_ratio > 1.0 (severity-weighted thermal exposure budget); sc51 is the only scenario where S_ratio alone makes the baseline infeasible. All nine are infeasible because of thermal B and/or severity-weighted S budgets, unchanged between F1 and F2.

---

## Frozen Interpretation

Rule: CI entirely above zero → SUPPORTS_FP; CI includes zero → INCONCLUSIVE.

- F2: CI = [+11.10, +19.35] pp → **SUPPORTS_FP**
- F1: CI = [+4.07, +8.82] pp → **SUPPORTS_FP**
- Agreement: **YES**

**Conclusion:** The corrected local-date F2 cabinet reference (time-weighted P99 with replay-matched historical denominator) is consistent in direction with the frozen F1 legacy reference. The original ThermalShift conclusion — that fingerprint-guided placement (FP) unlocks more feasible additional capacity than random placement at r=1.25 — is replicated and strengthened under the corrected cabinet reference definition. The correction does not reverse or attenuate the original finding.

---

## Provenance

| Artifact | SHA256 |
|---|---|
| F2 threshold reference | 71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34 |
| F2 replay denominator | b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48 |
| Runner (r3_gate_f_run.py) | 3bc8bcb07defd342d925e3eed2e5258be5424a7d596201c0246ba41d0613a6e1 |
| F2 result file | 5982264fcf719cc4746b23ae6ef0aaf9e22a9700e4b6ef3e19e49a98b5460dca |
| F1 result file | 0f2736058fca95117d5a03cb43e08eab93145c3d5ea7c82054ecc4cb08ddea97 |
