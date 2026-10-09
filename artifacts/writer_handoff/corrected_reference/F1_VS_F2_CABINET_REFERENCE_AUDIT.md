# F1 vs F2 Cabinet Reference Audit

**Plan commit:** c674209
**R3 evidence commit:** a80d51f
**Script SHA256:** 0269f981b11fd4aa475461146ad0b62c03a3b516e6d88e7c54039d041e675adb
**Date:** 2026-10-06

---

## Purpose

Compares F1 (frozen legacy event-weighted P99) and F2 (corrected time-weighted total P99) per-cabinet power thresholds across all 77 cabinets. No scheduling simulation is performed or implied.

---

## Definitions

**F1:** `Q_F1,c = P99({P_job,c for all qualifying jobs j})` where `P_job,c = (mean_power_j / node_count_j) * n_nodes_in_c`. One observation per job regardless of duration (event-weighted). Used in all sc0–sc54 frozen results.

**F2:** `Q_F2,c = time-weighted P99 of P_c(t)` where `P_c(t) = Σ_j P_job,c(t)` is total concurrent reconstructed observed cabinet power. Weights are exact interval durations over selected-date calendar support. Zero observed load is included.

---

## F1 Reproduction Check

| Field | Value |
|---|---|
| Cabinets checked | 77 |
| Cabinets within 1e-9 tolerance | 77 |
| Mismatch flag | False |
| Fleet median F1 P99 | 92.49 kW |

F1 reference reproduced exactly (within floating-point tolerance) before any F2 computation.

---

## F2 vs F1 Summary

| Metric | Value |
|---|---|
| Cabinets where F2 > F1 | 77 / 77 |
| Cabinets where F2 ≈ F1 | 0 |
| Cabinets where F2 < F1 | 0 |
| Delta (F2 − F1) mean | 118.4 kW |
| Delta median | 120.1 kW |
| Delta IQR | 6.4 kW |
| Delta P10 | 108.0 kW |
| Delta P90 | 127.3 kW |
| Delta min | 90.9 kW (cab 2600) |
| Delta max | 132.0 kW (cab 2301) |
| F2/F1 ratio mean | 2.313 |
| F2/F1 ratio median | 2.310 |
| F2/F1 ratio IQR | 0.093 |
| F2/F1 ratio P10 | 2.162 |
| F2/F1 ratio P90 | 2.403 |
| F2/F1 ratio min | 2.096 (cab 2600) |
| F2/F1 ratio max | 2.829 (cab 2610) |
| Pearson r (F1, F2) | 0.730 (p = 5.2e-14) |
| Spearman r (F1, F2) | 0.484 (p = 8.4e-6) |

F2 exceeds F1 for every cabinet. The median ratio is approximately 2.31. The difference arises because F2 measures total concurrent power across all simultaneously active jobs, while F1 measures the per-job contribution of the single highest-contributing job.

---

## Top 10 Largest Absolute Deltas (F2 − F1)

| Rank | Cabinet | F1 (kW) | F2 (kW) | Delta (kW) |
|---|---|---|---|---|
| 1 | 2301 | 91.9 | 223.9 | 132.0 |
| 2 | 2610 | 71.4 | 201.9 | 130.6 |
| 3 | 2302 | 90.7 | 220.9 | 130.2 |
| 4 | 2609 | 78.4 | 208.2 | 129.8 |
| 5 | 2611 | 80.7 | 208.8 | 128.1 |
| 6 | 2211 | 93.9 | 221.7 | 127.8 |
| 7 | 2103 | 95.4 | 223.1 | 127.7 |
| 8 | 2210 | 92.7 | 220.3 | 127.6 |
| 9 | 2300 | 94.0 | 221.1 | 127.1 |
| 10 | 2204 | 92.5 | 219.2 | 126.7 |

---

## Late-Commissioned Cabinets (2600–2602)

These cabinets joined the facility later in the collection period. They have fewer active jobs contributing to concurrent load and show the smallest F2 − F1 deltas (91–99 kW).

| Cabinet | F1 (kW) | F2 (kW) | Delta (kW) |
|---|---|---|---|
| 2600 | 71.2 | 162.0 | 90.9 |
| 2601 | 74.0 | 173.1 | 99.1 |
| 2602 | 68.7 | 163.1 | 94.4 |

---

## Interpretation

F2 is the total concurrent observed reconstructed cabinet power, not a per-job contribution. The factor-of-~2.3 elevation reflects that the P99 of concurrent total load significantly exceeds the P99 of single-job contributions. Neither definition is wrong; they measure different quantities. F1 is the definition used in all frozen sc0–sc54 results. F2 is a reviewer-requested alternative construction. Task D does not authorize any F2-based scheduling simulation.

---

## Figures

| Figure | Description |
|---|---|
| D1 | F1 vs F2 scatter (77 cabinets) |
| D2 | F2/F1 ratio ECDF |
| D3 | Exceedance fractions |
| D4 | F1 and F2 sorted thresholds |
| D5 | Concurrent power timeseries (representative cabinet) |

---

## Provenance

Machine-readable audit: `f1_vs_f2_cabinet_reference_audit.json`
