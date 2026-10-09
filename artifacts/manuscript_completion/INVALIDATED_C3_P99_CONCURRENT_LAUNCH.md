# INVALIDATED: C3 P99 Concurrent Launch

**Status:** INVALIDATED — operational resource-concurrency violation  
**Date:** 2026-10-09  

---

## What happened

P90 (T=61.875°C) and P99 (T=66.6625°C) were launched simultaneously with
N_WORKERS=3 each, creating 6 concurrent heavy workers. This violates the
established machine resource gate: the prior 5-worker test left only 6.4%
physical RAM free, and the authorized safe concurrency level is N_WORKERS=3
machine-wide, not per threshold run.

## Terminated execution record

| Field | Value |
|---|---|
| Task ID | bx0m624ki |
| Threshold | 66.6625 °C (P99) |
| Runner | c3_gate_f_run.py |
| Runner SHA256 | 3b4e9825462a5f8b80bc6f76c6938bcf88d460d12f782210474b38573654e91c |
| Launcher SHA256 | d4df5a158c6e6157f7ad6ca7e83164db0c28bc7c6a3d8226cdb0653f369ce957 |
| Launch time (UTC approx) | 2026-10-09T08:50Z |
| Workers attempted | 3 (sc30, sc31, sc32 started before termination) |
| Completed scenario JSONs | 0 (none written before termination) |
| Checkpoint files | 0 (none written) |
| Termination method | TaskStop (bx0m624ki) |
| Partial logs deleted | sc30/31/32 c3_t66p6625 worker logs — deleted before any scientific result was written |

## No scientific result was inspected or retained

No per-scenario JSON output was produced for any P99 scenario before
termination. No scientific value (C_lower_pct, C_upper_pct, crossing status,
binding constraint) was read, interpreted, or compared. The invalidation is
purely operational.

## P90 status at time of P99 termination

P90 (T=61.875°C, task bect6fp1g) was NOT stopped. It continued running
and completed sc30, sc31, sc32 normally before P99 was terminated.
P90 sc33, sc34, sc35 were running as the second batch at termination time.
The brief period of 6-worker concurrency (from launch until P99 kill) may
have slowed P90 workers but does not affect the deterministic scenario seeds
or calculations.

## Frozen scientific design

The C3 scientific design (runner SHA, scenario range, ratio, policies,
thresholds, analysis estimand) is unchanged by this operational event.
c3_threshold_analysis.py (commit 5f050eb) remains the frozen analysis script.

## Remediation plan

1. Allow P90 to complete all 25 scenarios.
2. SHA and commit raw P90 merged result.
3. Relaunch P99 from scratch with N_WORKERS=3 (sole active threshold run).
4. SHA and commit raw P99 merged result separately.
5. Run the frozen c3_threshold_analysis.py on both raw results plus the
   accepted P95 C2 result.
6. Commit analysis separately from raw results.
