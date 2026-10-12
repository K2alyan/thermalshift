# INVALID FOR SCIENTIFIC EVIDENCE

**Terminated:** 2026-10-06, after 8/25 scenarios completed (sc30–sc37)
**Reason:** Denominator scope mismatch — numerator and denominator used different workload populations and time support

---

## What went wrong

F2 thresholds (Q_F2_local_kW, from f2_local_scheduling_reference.json) were correct.

The scheduling denominator was not. The runner was patched to load:

```
B_cab_hist = f2_denominator.json["aggregate"]["B_cab_hist_F2_h"]  # 2454.57 h
```

That artifact was computed from the **full observed public-job reconstruction** (all 152,400 jobs, all nodes, clipped to America/New_York local-date support). Its purpose is to validate that Q_F2 is a true time-weighted P99 of the process from which it was derived (Task D/D2 reference definition).

The policy numerator `B_cab_h` is computed by `sweep_cab_budget_fast` over the **replay-world event process**: background events from non-cohort nodes plus counterfactual cohort/base/synthetic placements.

In the frozen F1 model, the historical denominator was produced by the same replay-world sweep:
```
sweep_cab_budget_fast(cohort_hist_records, cab_p99_W)
```

The F2 patch replaced that with an external Task-D denominator, creating a ratio of the form:

```
counterfactual replay-world cabinet exceedance
------------------------------------------------
full-public-sample local-support cabinet exceedance
```

rather than the intended:

```
counterfactual replay-world cabinet exceedance
------------------------------------------------
historical replay-world cabinet exceedance
```

This violates the one-change-at-a-time comparison. The ratio B_cab_ratio in the 8 completed scenarios is not interpretable as a scheduling feasibility metric.

---

## What remains valid

- F2 thresholds (f2_local_scheduling_reference.json) — unchanged, still the primary corrected reference
- Task-D/D2 audit results — unchanged
- Task-D denominator (f2_denominator.json, ~2454.57 h / 0.9839%) — valid as a reference-process diagnostic; not the scheduler denominator

---

## Contents of this directory

- `gate_f_sc30-54_1p25_r3f2local_checkpoint.json` — partial run, 8/25 scenarios (sc30–sc37). DO NOT ANALYZE.
- `F2_EXECUTION_MANIFEST.json` — original manifest (now superseded by V2)

---

## Resolution

The correct F2 scheduling denominator is `B_cab_hist_F2_replay`: historical replay-world cabinet exceedance evaluated under the same frozen replay event process as F1, but using Q_F2_local thresholds. Computed independently in `compute_f2_replay_denominator.py` and frozen before the corrected run.
