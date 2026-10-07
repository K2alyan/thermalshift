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

| Policy | F2 median C_lower | F2 IQR | F1 median C_lower | F1 IQR |
|---|---|---|---|---|
| full_fp | 15.35% | [12.23%, 22.83%] | 7.33% | [4.90%, 9.36%] |
| full_random | 0.10% | [0.00%, 3.48%] | 0.10% | [0.00%, 2.79%] |

---

## Censoring

| | F2 | F1 |
|---|---|---|
| FP left_boundary | 0 / 25 | 0 / 25 |
| Random left_boundary | **9 / 25** | 6 / 25 |
| FP right_censored | 0 / 25 | 0 / 25 |
| Random right_censored | 0 / 25 | 0 / 25 |

In all 9 F2 left_boundary Random scenarios, B_cab_ratio < 1.0 at lambda=1.0 — the cabinet constraint is not binding. The thermal constraint (B_ratio) is infeasible at the baseline counterfactual placement, because Random selects nodes that are thermally hotter than what FP would choose. FP avoids this in all 25 scenarios.

---

## First-Binding Constraints

| Policy | F2 | F1 |
|---|---|---|
| full_fp | B_ratio: 25/25 | B_cab_ratio: 23/25, B_ratio: 2/25 |
| full_random | B_ratio: 22/25, S_ratio: 3/25 | B_ratio: 19/25, B_cab_ratio: 4/25, S_ratio: 2/25 |

**Key structural shift:** Under F1, the cabinet budget constraint was first-binding for FP in 23/25 scenarios, capping achievable capacity. Under F2, the higher cabinet threshold relaxes the cabinet constraint entirely — the thermal budget (B_ratio) becomes the sole binding constraint. This exposes FP's full thermal advantage: FP selects thermally cooler nodes, which allows higher unlocked capacity (median 15.35% vs 7.33% under F1) before the thermal budget binds.

---

## F1 vs F2 Comparison

Both experiments support FP over Random at r=1.25 (directional agreement = YES). The F2 result is stronger:

- A count: 25/25 vs 22/25
- Median delta_lo: +12.76 pp vs +6.78 pp (shift: +5.98 pp)
- CI lower bound: +11.10 pp vs +4.07 pp (shift: +7.03 pp)
- CI entirely above zero in both cases

The stronger F2 result is structurally explained: the corrected concurrent-load P99 threshold (~2.3× higher than the event-weighted F1 threshold) relaxes the cabinet constraint that previously capped FP's capacity expansion. The thermal constraint, where FP has its principal advantage, now drives the result throughout. Under F1, the cabinet constraint was partially masking the thermal signal for FP.

Random's left_boundary count increases from 6 to 9 under F2, consistent with the same mechanism: the changed denominator structure shifts which constraint binds first for Random's thermally suboptimal placements.

---

## Frozen Interpretation

Rule: CI entirely above zero → SUPPORTS_FP; CI includes zero → INCONCLUSIVE.

- F2: CI = [+11.10, +19.35] pp → **SUPPORTS_FP**
- F1: CI = [+4.07, +8.82] pp → **SUPPORTS_FP**
- Agreement: **YES**

**Conclusion:** The corrected time-weighted total P99 local-date cabinet reference (F2) is consistent in direction with the frozen F1 legacy reference. The original ThermalShift conclusion — that fingerprint-guided placement (FP) unlocks more feasible additional capacity than random placement at r=1.25 — is replicated and strengthened under the corrected threshold definition. The correction does not reverse or attenuate the original finding.

---

## Provenance

| Artifact | SHA256 |
|---|---|
| F2 threshold reference | 71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34 |
| F2 replay denominator | b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48 |
| Runner (r3_gate_f_run.py) | 3bc8bcb07defd342d925e3eed2e5258be5424a7d596201c0246ba41d0613a6e1 |
| F2 result file | 5982264fcf719cc4746b23ae6ef0aaf9e22a9700e4b6ef3e19e49a98b5460dca |
| F1 result file | 0f2736058fca95117d5a03cb43e08eab93145c3d5ea7c82054ecc4cb08ddea97 |
