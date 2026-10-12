# F2 Replay Denominator Audit

**Script:** compute_f2_replay_denominator.py
**Output artifact:** f2_replay_denominator.json
**Date:** 2026-10-06
**Runner reference:** r3_gate_f_run.py, step [8] + sweep_cab_budget_fast

---

## Purpose

Documents the construction and validation of `B_cab_hist_F2_replay`: the historical cabinet exceedance denominator used by the corrected F2 scheduling experiment. This quantity uses the exact frozen replay-world event process from `r3_gate_f_run.py`, evaluated under the F2 local-date power thresholds.

This replaces the previously invalidated denominator loaded from `f2_denominator.json` (Task-D full-public-sample process, archived under `invalidated_f2_denominator_scope_mismatch/`).

---

## Two Distinct Denominator Quantities

| Property | Task-D B_F2_taskD | Replay B_F2_replay (this doc) |
|---|---|---|
| Artifact | f2_denominator.json | f2_replay_denominator.json |
| Purpose | Validate Q_F2 is a true time-weighted P99 | Scheduler historical exposure denominator |
| Workload population | All 152,400 public jobs, all nodes | bg: non-cohort nodes; cohort: test-set jobs only |
| Time support | America/New_York local-date, 3,240 h, clipped | Raw observed timestamps, no clipping |
| Time unit | Nanoseconds (datetime64[ns]) | Milliseconds (datetime64[ms]) |
| Result | 2,454.57 h aggregate | 871.37 h aggregate |
| Exceedance fraction | ~0.98% (matches P99 definition) | ~1.28% of F1 denominator |

These quantities answer different questions and are not interchangeable. The error in the invalidated run was using B_F2_taskD as the scheduling denominator when the scheduler's numerator uses the replay-world event process.

---

## Replay World Structure

| Field | Value |
|---|---|
| Total jobs (all_jobs) | 152,400 |
| Test-set job IDs (test_id_set) | 24,869 |
| Cohort nodes | 2,000 |
| bg_records (jobs with >= 1 non-cohort node) | 141,363 |
| cohort_hist_records (test-set jobs with >= 1 cohort node) | 2,637 |
| bg_events_sorted (background event pairs) | ~4.7M |
| bg node-cabinet contributions | 14,602,402 |
| cohort node-cabinet contributions | 65,174 |

### Background component

For every job in all_jobs, nodes whose hostname is NOT in `cohort_set` are attributed as background. If a job has at least one non-cohort node with a known cabinet mapping, that job contributes a `bg_record` with `cab_counts` = {cabinet: n_noncohort_nodes_in_cab}. Power is `ppn = mean_power_W / node_count` applied uniformly across all nodes. Total: 141,363 background records → 14.6M node-cabinet events.

### Historical cohort component

Only jobs in `test_id_set` (the frozen test-set workload) that have at least one cohort node contribute a `cohort_hist_record` with `cab_counts` = {cabinet: n_cohort_nodes_in_cab}. Total: 2,637 records → 65,174 node-cabinet events.

### Why not all 152,400 jobs

The scheduling experiment counterfactually reallocates the test-set cohort workload (admitting more synthetic jobs, changing cohort node assignments). The non-test-set workload is pure background and enters only through bg_records. Only test-set cohort jobs appear in cohort_hist_records because only those jobs are modeled as the "base" workload that policy scenarios replicate and augment.

### Time support

No local-date clipping. All events use raw observed `start_time` / `end_time` from the parquet, converted to `datetime64[ms]` via the same `_col_to_dt64ms` helper as the runner. The full job dataset spans approximately 13,600 hours.

---

## Results

### Aggregate

| Quantity | Value |
|---|---|
| B_cab_hist_F1_reproduced | 67,917.76 h |
| B_cab_hist_F2_replay | 871.37 h |
| F2 / F1 ratio | 0.01283 |
| n_cabinets | 77 |
| Cabinets with positive F2 exceedance | 77 / 77 |

### Per-cabinet summary

| Statistic | F1 (kW legacy) | F2 replay |
|---|---|---|
| Min cabinet exceedance | 682.75 h | 1.51 h |
| Median cabinet exceedance | 822.32 h | 11.53 h |
| Max cabinet exceedance | 1,725.78 h | 15.02 h |

The large F1 aggregate (67,918 h) reflects the ~41% historical exceedance fraction noted in Task D: the F1 threshold (~80–95 kW) is much lower than the typical total concurrent cabinet power, so the replay world exceeds it almost continuously. The smaller F2 aggregate (871 h) reflects the higher F2 threshold (~160–225 kW), which the historical replay process exceeds only ~1.3% of the aggregate observation time.

### Interpretation of F2/F1 ratio

The ratio 0.01283 is not the exceedance fraction (which would be ~1.28% of the total fleet-hours). It is the ratio of total aggregate cabinet-hours above threshold across all 77 cabinets. Both quantities are aggregate sums across cabinets and therefore depend on the number of cabinets (77) and total time support.

---

## Validation

### Discarded invalid inference

An earlier attempt to infer the frozen F1 B_cab_hist value divided `B_primary_h` by `B_cab_ratio` from the sc30 smoke checkpoint, obtaining ~2053 h (full_fp) and ~2341 h (full_random). **This inference was invalid.** `B_primary_h` is the thermal-incidence quantity (job-level temperature exceedance budget), not cabinet exceedance-hours. Those ~2053/~2341 h figures are discarded and are not estimates of B_cab_hist.

### Pre-existing independent anchor

`B_cab_hist_h = 67917.76333331302` appears in `artifacts/revision1/results/m4_fair_baselines.json` under `.data_anchors.B_cab_hist_h`. That file has SHA256 `cfb4912b9a73bf8b4aaa4a20f16b25490b8110c4fc3b6aba2e2d300a0ec6badc` and was committed 2026-09-30, before any F2 work. It constitutes a genuine independent anchor.

### Self-reference note in compute_f2_replay_denominator.py

`compute_f2_replay_denominator.py` initially ran with `F1_FROZEN_REFERENCE_H = None`. The first run produced 67917.76333331302 h, and that value was subsequently hard-coded as `F1_FROZEN_REFERENCE_H` in the same script. This is self-consistency, not independent reproduction. The script's F1 acceptance test (diff = 0.00e+00) is therefore a floating-point identity check, not an independent validation. Independence is established instead by:

1. The pre-existing revision-1 anchor above.
2. `verify_frozen_f1_bcab_denominator.py` — a separate script using verbatim code blocks from frozen runner commit bfb658b (SHA256: `fa1b6549...`), which independently reproduces B_cab_hist_F1_h and validates it against the revision-1 anchor to ≤1e-9.

### Per-cabinet aggregate consistency

Sum of per-cabinet B_F1_h matches aggregate sweep within 2.09e-08 h; sum of per-cabinet B_F2_replay_h matches within 1.02e-12 h. Both within 1e-6 tolerance.

**All cabinets positive:** 77/77 show positive F2_replay exceedance, confirming the F2 threshold is not so high that no replay events exceed it.

---

## Provenance

- F2 local reference: `f2_local_scheduling_reference.json` (SHA256: 71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34)
- Output artifact: `f2_replay_denominator.json`
- Computation script: `compute_f2_replay_denominator.py`
- Independent F1 verification: `verify_frozen_f1_bcab_denominator.py` → `frozen_f1_bcab_denominator_verification.json`
- Pre-existing anchor: `artifacts/revision1/results/m4_fair_baselines.json` (SHA256: `cfb4912b...`, 2026-09-30)
- Task-D reference (diagnostic only, NOT scheduler denominator): `f2_denominator.json`
