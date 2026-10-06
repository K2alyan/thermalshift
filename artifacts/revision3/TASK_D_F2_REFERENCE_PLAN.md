# Task D — F2 Concurrent Cabinet Power Reference Plan

**Version:** 1.0
**Plan commit:** c674209
**R3-0 evidence commit:** a80d51f
**Date:** 2026-10-06
**Status:** Pre-computation freeze

---

## Purpose

The purpose of Task D is to construct a cabinet-power reference whose statistical object matches the quantity used by the replay cabinet constraint: total concurrent reconstructed cabinet power. No scheduling-policy comparison is executed in Task D.

F1 remains the cabinet-reference definition used in all frozen sc0–sc54 results. F2 is a post-exposure reviewer-requested alternative definition. Task D does not replace or rewrite frozen F1 results.

---

## Definitions

### F1 (frozen legacy reference)
`Q_F1,c = percentile_99({P_job,c for all qualifying jobs j})`

where `P_job,c = (mean_power_j / node_count_j) * n_nodes_in_c_for_job_j`

This is the event-weighted (job-count-weighted) P99 of individual job-cabinet power contributions. One observation per qualifying job regardless of duration. Used in all sc0–sc54 results.

### F2 (corrected time-weighted total P99)
`Q_F2,c = time-weighted P99 of P_c(t)`

where `P_c(t) = Σ_j P_job,c(t)` — the total concurrent reconstructed cabinet power at time t.

Computed using an exact piecewise-constant event-driven process over selected-date calendar support. Weights are exact interval durations. Zero observed load during a supported calendar interval is an observed state and is included.

### F3 (corrected event-weighted total P99 — diagnostic only)
`Q_F3,c = P99 of post-event power states at unique event timestamps`

Event timestamps are all unique job-start and job-end times inside supported intervals. The post-event power state is sampled once per unique timestamp. Ordinary (unweighted) P99. No scheduling simulation.

---

## Data Source

`THERMALSHIFT_DATA_DIR/frontier-completed-job-info.parquet`

Required fields: `job_idx`, `date_dir`, `start_time`, `end_time`, `mean_power`, `node_count`, `host_list`

Topology: `artifacts/revision1/tables/fleet_node_topology.csv` (frozen, same as r2_gate_f_run.py)

---

## Support Definition (v1)

### Collection dates
All unique `date_dir` values in the parquet. 135 dates expected.

### Support intervals
Each date d → `[d 00:00:00 UTC, d+1 00:00:00 UTC)`. Adjacent dates merged into contiguous blocks.

### Caveat
Because the public dataset is constructed around selected collection dates / job records rather than a complete scheduler log, reconstructed concurrent cabinet power represents observed reconstructed concurrent load on supported intervals. Jobs absent from the public dataset can cause undercounting of true physical cabinet load. We therefore do not call this complete facility cabinet power.

Required terminology: **observed reconstructed concurrent cabinet power**

Do not call it: measured/actual/physical/facility-meter cabinet power.

### Job clipping
`observed_interval = [start_time, end_time) ∩ support_union`

Jobs are clipped to support intervals. Unsupported gaps contribute zero duration.

### Zero states
Zero observed load during an actually selected support interval is an observed state and is included in the F2 time-weighted distribution.

### Weighted-quantile convention
For sorted power states (P_k, duration_k):
- Normalize by total calendar support duration
- F2 P99 = smallest P such that cumulative time weight at or below P is ≥ 0.99 of total supported duration

---

## Stop Conditions

- F1 cannot be reproduced within 1e-6 tolerance
- Cabinet count ≠ 77
- Weighted-quantile tests fail
- Negative/invalid concurrent power appears
- Support integration inconsistent
- Any scheduling-policy code is called

---

## Authorized Outputs

1. `task_d_f1_reproduction.json`
2. `f2_timeweighted_cabinet_reference.json`
3. `f3_eventweighted_cabinet_reference.json`
4. `cabinet_support_audit_v2.json`
5. `CABINET_SUPPORT_AUDIT_V2.md`
6. `task_d_validation.json`
7. `f1_vs_f2_cabinet_reference_audit.json`
8. `F1_VS_F2_CABINET_REFERENCE_AUDIT.md`
9. `figures/D1_f1_vs_f2_scatter.png`
10. `figures/D2_f2_f1_ratio_ecdf.png`
11. `figures/D3_exceedance_fractions.png`
12. `figures/D4_sorted_thresholds.png`
13. `figures/D5_concurrent_power_timeseries.png`

---

## What Task D Does NOT Do

- Does not run any scheduling-policy simulation
- Does not modify frozen F1 results
- Does not produce F2 simulation output
- Does not authorize F2 FP-vs-Random comparison
- Does not edit the paper
