# Cabinet Support Audit V2

**Plan commit:** c674209
**R3 evidence commit:** a80d51f
**Script SHA256:** 0269f981b11fd4aa475461146ad0b62c03a3b516e6d88e7c54039d041e675adb
**Support definition version:** v1
**Date:** 2026-10-06

---

## Purpose

Audits the calendar support structure used in Task D F2 computation: unique collection dates from `date_dir`, merged into contiguous blocks, over which concurrent cabinet power is reconstructed.

---

## Dataset Summary

| Field | Value |
|---|---|
| Total rows | 152,400 |
| Missing/NaN mean_power | 0 |
| Non-positive mean_power | 0 |
| Missing start or end time | 0 |
| Non-positive node_count | 0 |
| host_list length != node_count | 0 |
| Zero topology hits | 0 |

No data quality issues detected.

---

## Calendar Support Structure

| Field | Value |
|---|---|
| Unique collection dates (date_dir) | 135 |
| Contiguous date blocks | 106 |
| Total calendar support | 3,240.0 hours |
| Block duration min | 24.0 h |
| Block duration median | 24.0 h |
| Block duration P90 | 48.0 h |
| Block duration max | 120.0 h |

Most dates are isolated (block duration 24 h). The longest contiguous run is 5 consecutive days (120 h).

---

## Support Definition (v1)

Each unique `date_dir` value maps to the calendar interval `[d 00:00:00 UTC, d+1 00:00:00 UTC)`. Adjacent dates are merged into contiguous blocks. The support union is the union of all such intervals.

**Unsupported gaps:** Intervals between non-adjacent date blocks are not part of the support. Jobs are clipped to the support union: `observed_interval = [start_time, end_time) ∩ support_union`. Unsupported gaps contribute zero duration to the piecewise-constant process.

**Zero observed load:** A calendar support interval during which no qualifying job is active in a given cabinet is an observed idle state. It is included in the F2 time-weighted distribution with its full duration weight.

---

## Per-Cabinet Summary

All 77 cabinets received 3,240.0 hours of calendar support (identical, as support is dataset-level). Active fraction ranged from approximately 0.987 to 0.999 across cabinets.

---

## Provenance

Machine-readable audit: `cabinet_support_audit_v2.json`
