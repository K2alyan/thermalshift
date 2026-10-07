# Invalidated C1 Launch — Accidental sc0–4 Dev-Scenario Execution

**Status:** INVALIDATED — no manuscript use  
**Record date:** 2026-10-07 (updated 2026-10-07 after concurrent-execution discovery)  
**Governing commit at launch:** `e44fedd`

---

## What Happened

During the first production launch of the C1 runner, the environment variables
`GATE_F_N_FIRST` and `GATE_F_N_DEV` were omitted. The runner defaulted to
`N_FIRST=0, N_DEV=5`, selecting the **dev scenario block sc0–4** instead of the
authorized held-out block **sc5–29**.

This was caught at the 1-hour progress check when the task output showed scenario
indices 0 and 1 (dev scenarios) rather than 5+ (held-out scenarios). A `pkill -f
c1_gate_f_run.py` was issued, believed to have terminated the process, and the
correct sc5–29 run (task `bpdjphtc0`, PID 115441) was launched.

**Subsequent discovery (2026-10-07 ~16:19):** The pkill did NOT terminate the sc0–4
process. PID 115132 continued running concurrently with the sc5–29 run (PID 115441)
for approximately 118 minutes (14:21–16:19 PDT). This was confirmed at the
second wakeup check by `ps aux` showing two python3 processes. PID 115132 was then
killed with a targeted `kill 115132` command.

**Concurrent execution impact on sc5–29:** The sc0–4 and sc5–29 runs shared CPU and
I/O resources during the first two scenarios of the correct run (sc5, which completed
at 15:29 in 4089 s, and the opening of sc6). Both processes read from the same
read-only THERMALSHIFT_DATA_DIR and wrote to different output files; no file-level
conflict occurred. Correctness of the sc5–29 scheduling results is unaffected by
the concurrent process (identical random seeds, deterministic computation). Timing
may be slower than expected for sc5 and the beginning of sc6.

---

## Sequence of Events

| Time (PDT approx.) | Event |
|---|---|
| 2026-10-07 ~13:16 | `artifacts/manuscript_completion/results/` directory created (had been absent after `git rm` of smoke files) |
| 2026-10-07 ~13:16 | **Invalid launch** — task ID `b1iuu7ed9`, PID 115132; command: `python3 artifacts/manuscript_completion/runners/c1_gate_f_run.py` with no GATE_F_N_FIRST or GATE_F_N_DEV set |
| 2026-10-07 ~14:18 | Wakeup check fired; task output inspected; sc0–4 execution confirmed |
| 2026-10-07 ~14:20 | `pkill -f c1_gate_f_run.py` issued — INEFFECTIVE; PID 115132 continued running |
| 2026-10-07 ~14:20 | First checkpoint (`gate_f_sc0-4_all_checkpoint.json`) deleted from `results/` |
| 2026-10-07 ~14:21 | **Correct sc5–29 run launched** — task `bpdjphtc0`, PID 115441 |
| 2026-10-07 15:22 | sc0–4 run (PID 115132) wrote updated checkpoint (confirmed by file timestamp); ran concurrently ~118 min |
| 2026-10-07 15:29 | sc5–29 run wrote checkpoint after sc5 completed (4089 s, 68 min) |
| 2026-10-07 ~16:19 | Second wakeup check; `ps aux` revealed PID 115132 still alive alongside PID 115441 |
| 2026-10-07 ~16:19 | `kill 115132` issued; PID 115132 terminated (confirmed by `ps aux`) |
| 2026-10-07 ~16:19 | sc0–4 checkpoint (SHA `08b273da401a6577d3fd1e99d759a549139cad44f30384ec6f1698344ef6196f`, timestamp 15:22:47) deleted |
| 2026-10-07 ~16:19 | `results/` confirmed clean: only `gate_f_sc5-29_all_checkpoint.json` remains |
| 2026-10-07 ~14:21 | **Correct launch** — task ID `bpdjphtc0`; command: `GATE_F_N_FIRST=5 GATE_F_N_DEV=25 python3 artifacts/manuscript_completion/runners/c1_gate_f_run.py` |

---

## Invalid Run Provenance

| Field | Value |
|---|---|
| Task ID | `b1iuu7ed9` |
| git HEAD at launch | `e44fedd` |
| C1 runner SHA256 | `7cb51ebcf541d9c04b932ef879ce5095d34195452ef88151418d01ce844b41ba` |
| THERMALSHIFT_DATA_DIR | `C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset` |
| GATE_F_N_FIRST | not set (defaulted to 0) |
| GATE_F_N_DEV | not set (defaulted to 5) |
| Effective scenario range | sc0–4 (dev scenarios) |
| Authorized scenario range | sc5–29 (held-out) |
| GATE_F_RATIOS_ONLY | not set (all 7 ratios) |
| Cabinet reference | corrected concurrent-load (f2_local_scheduling_reference.json) |

---

## What Executed Before Kill

| Dev scenario | Status |
|---|---|
| sc0 (Scenario index 0) | **Completed** — 3287 s; checkpoint written ("1/5 saved") |
| sc1 (Scenario index 1) | **Partial** — r=1.0 and r=1.5 partly underway; killed mid-ratio |
| sc2, sc3, sc4 | Never reached |

Checkpoint file written: `artifacts/manuscript_completion/results/gate_f_sc0-4_all_checkpoint.json`  
Checkpoint deleted: yes, before the correct run launched.  
Final result file (`gate_f_sc0-4_all.json`): never written (run killed before completion).

---

## Exposure of Held-Out Data

**None.** The invalid run operated exclusively on dev scenarios sc0–4. No sc5–29
scenario seeds, workloads, or outcomes were executed or inspected. The held-out
block is uncontaminated.

---

## Stdout/Stderr Availability

The full task stdout is preserved in the ephemeral background-task output file:

```
C:\Users\kalya\AppData\Local\Temp\claude\C--users-kalya-thermalops\
  31aed3a6-030e-4804-af8a-6d84deacb6b2\tasks\b1iuu7ed9.output
```

This file is session-scoped and will not persist beyond the current terminal session.
Its terminal content was inspected only to identify scenario indices (0 and 1) and
confirm that sc5–29 data was not accessed. No scientific values from sc0–4 were
read, recorded, or used for any design decision.

---

## Correct Run

| Field | Value |
|---|---|
| Task ID | `bpdjphtc0` |
| git HEAD at launch | `e44fedd` |
| C1 runner SHA256 | `7cb51ebcf541d9c04b932ef879ce5095d34195452ef88151418d01ce844b41ba` |
| GATE_F_N_FIRST | 5 |
| GATE_F_N_DEV | 25 |
| Effective scenario range | sc5–29 (authorized held-out block) |
| Status at record time | Running |

---

## Root Cause and Mitigation

**Root cause:** The c1 runner inherits its default `N_FIRST=0, N_DEV=5` from
`r1_gate_f_run.py`, which was designed for dev-scenario runs (sc0–4). The manuscript
production invocation requires explicit overrides, but no launcher enforced them.

**Mitigation:** A hardened launcher script
(`artifacts/manuscript_completion/runners/c1_launch.sh`) has been written that
refuses to run unless `GATE_F_N_FIRST` and `GATE_F_N_DEV` are supplied explicitly.
It also verifies the runner SHA and emits the full pre-run protocol header before
delegating to the Python runner. This script will be used for any future C1 restart
or re-run. The Python runner itself is **not modified**.
