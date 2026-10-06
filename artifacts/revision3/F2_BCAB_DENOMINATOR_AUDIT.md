# F2 B_cab Historical Denominator Audit

**Task D2 commit:** ab3119c
**F2 local reference SHA256:** 71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34
**Script:** compute_f2_denominator.py
**Date:** 2026-10-06

---

## Purpose

Documents the computation and validation of B_cab_hist_F2, the historical exceedance denominator used in the F2 local-date scheduling experiment (sc30–54). Replaces the F1 denominator (B_cab_hist computed via sweep_cab_budget_fast) for the F2 cabinet reference mode.

---

## Definition

B_cab_hist_F2 is the aggregate per-cabinet exceedance of the F2_local threshold over the local-date calendar support:

```
B_cab_hist_F2 = Σ_{c=1..77} B_c   where
B_c = ∫_{support} 1[P_c(t) > Q_{F2,c}] dt
P_c(t) = Σ_j (mean_power_j / node_count_j) × n_{j,c}(t)   [total concurrent kW in cabinet c]
Q_{F2,c} = time-weighted P99 threshold from f2_local_scheduling_reference.json
support  = union of Eastern local-date intervals [00:00 ET, 24:00 ET) for each date_dir, converted to UTC
```

This matches the F2 definition exactly: B_c measures the fraction of observed calendar time during which total concurrent cabinet power exceeded the F2 threshold. The aggregate is the sum across all 77 cabinets.

---

## Dataset

| Field | Value |
|---|---|
| Total qualifying jobs | 152,400 |
| Date strings (date_dir) | 135 |
| Merged contiguous blocks | 106 |
| Total calendar support | 3,240.0 h |
| Support convention | America/New_York local calendar end-date, converted to UTC |

All 152,400 jobs have non-null mean_power > 0, node_count > 0, non-null start/end times (per CABINET_SUPPORT_AUDIT_V2.md).

---

## Implementation Notes

**Timestamp handling:** Parquet stores timestamps as `datetime64[ms, UTC]`. The conversion `.dt.tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)` is used to force nanosecond resolution before the int64 cast. The intermediate `astype("datetime64[ns]")` step is required; without it, `.astype(np.int64)` returns millisecond-epoch values (~10^12), while block boundaries are nanosecond-epoch values (~10^18), causing all jobs to be skipped.

**Block boundaries:** Computed via `int(s_utc.timestamp() * 1e9)` giving nanoseconds since epoch. Adjacent dates merged into contiguous intervals.

**Exceedance sweep:** For each cabinet, jobs are clipped to support blocks, sorted into a piecewise-constant event list, and swept. The `bisect.bisect_right` O(log n) membership test uses block midpoints to attribute intervals to the correct block.

---

## Results

| Field | Value |
|---|---|
| B_cab_hist_F2_h | 2454.5711 h |
| Aggregate exceedance fraction | 0.9839% |
| n_cabinets | 77 |
| Exceedance fraction min | 0.7861% (cab with fewest data) |
| Exceedance fraction median | 0.9980% |
| Exceedance fraction P90 | 1.0076% |
| Exceedance fraction max | 1.0844% |
| Cabinets in [0.5%, 1.5%] | 77 / 77 |
| All cabinets positive | True |

---

## Validation

**77/77 in [0.5%, 1.5%]:** The F2 threshold is by construction the time-weighted P99, so the historical exceedance fraction should be close to 1% for each cabinet. All 77 cabinets fall within [0.5%, 1.5%], confirming that: (a) the threshold computation and denominator computation use the same support; (b) the timestamp unit conversion is correct; (c) no cabinets were skipped.

**All positive:** All 77 cabinets show positive exceedance hours, confirming all cabinets had active jobs contributing to concurrent power above threshold.

**Aggregate fraction 0.9839%:** Consistent with P99 definition applied to the union of all cabinet-time. The small departure from exactly 1.0% reflects per-cabinet variation in active job density.

---

## Comparison: F1 vs F2 Denominators

| Property | F1 B_cab_hist | F2 B_cab_hist_F2 |
|---|---|---|
| Threshold definition | Event-weighted P99 (per-job contribution) | Time-weighted P99 (total concurrent power) |
| Threshold magnitude | ~80–95 kW per cabinet | ~160–225 kW per cabinet |
| Denominator | Computed per-scenario via sweep_cab_budget_fast | Frozen artifact (this document) |
| Exceedance fraction | ~41% (F1 threshold is low relative to concurrent power) | ~0.98% (F2 threshold is at true P99 of concurrent power) |

The large F1 exceedance fraction (~41%) arises because the F1 threshold measures a per-job contribution, while the denominator sweep measures total concurrent power (which is much higher). The F2 definition is internally consistent: threshold and denominator both measure total concurrent power, yielding ~1% exceedance.

---

## Provenance

- F2 local reference: `f2_local_scheduling_reference.json` (SHA256 above)
- Denominator artifact: `f2_denominator.json`
- Computation script: `compute_f2_denominator.py` (Task D2 commit ab3119c)
