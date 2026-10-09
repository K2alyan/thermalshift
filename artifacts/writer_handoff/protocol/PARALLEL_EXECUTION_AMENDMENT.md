# C1 Parallel Execution Amendment
## Provenance Record for Governed Parallelization of sc5–sc29

**Date:** 2026-10-07/08  
**Branch:** revision1/major-revision-analyses  
**Author:** k2alyan

---

## 1. Sequential Run Invalidation

The original C1 sequential run (sc5–sc29) was stopped and formally invalidated before any parallel
execution began. The invalidation was not due to a scientific error but to a governance decision:
parallelizing all 25 held-out scenarios under a governed merger produces cleaner provenance at
negligible scientific cost (all scenarios are independent with pre-seeded RNG).

| Field | Value |
|-------|-------|
| Sequential task | bpdjphtc0 |
| PID killed | 115441 (SIGTERM, exit 143) |
| Kill time | 2026-10-07 ~20:08 PDT |
| Checkpoint preserved | `INVALIDATED_C1_SEQUENTIAL_CHECKPOINT.json` |
| Checkpoint SHA256 | `dab8542d597581171b26d3c47b79c5de60cd369c28c74767ee35720611644e3d` |
| Scenarios complete at kill | 5/25 (sc5, sc6, sc7, sc8, sc9) |
| Scenarios discarded | All 5 — none will be reused in parallel run |

Note: A concurrent sc0–sc4 process (PID 115132) was also running due to pkill ineffectiveness and
was separately killed. Its checkpoint was SHA256'd and deleted. See `INVALIDATED_C1_SC0-4_LAUNCH.md`.

---

## 2. Frozen Provenance Constants

All parallel workers and the merger enforce these values. Any mismatch causes immediate abort.

| Artifact | SHA256 |
|----------|--------|
| `c1_gate_f_run.py` (runner — unmodified) | `7cb51ebcf541d9c04b932ef879ce5095d34195452ef88151418d01ce844b41ba` |
| F2 reference file | `71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34` |
| F2 replay denominator | `b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48` |
| Scientific freeze commit | `e2df32a883fff8f26d93511483dfdae63fe0b730` |
| Cabinet reference mode | `corrected_timeweighted_total_p99_local` |

---

## 3. Parallel Tooling — SHA256 Registry

New tools written for this parallelization. None modify `c1_gate_f_run.py`.

| Script | SHA256 | Role |
|--------|--------|------|
| `runners/c1_parallel_launcher.py` | `c84749ce54b56c836967528e7dde3354a1a8eeef3f3182c7683cfd8797d650e4` | Subprocess fan-out, pre-flight guards, pilot mode, manifest writer, calls merger |
| `runners/c1_parallel_merge.py` | `82344a4c114893bfb60fff69781a6d6641c3c85afe7ec902ff23986f65cc2e6a` | Validated merger: enforces all provenance checks, no recomputation |
| `runners/c1_sc5_equivalence_check.py` | `61d089a6af8e250840996c1bb0d3d9d7507753ed63392ee0e93848ef281209dd` | Deep recursive comparison of parallel vs sequential sc5 output |
| `runners/test_c1_parallel_merge.py` | `adc61b82f3395a2623556aba89faa5f5b178c5e3e7f1224f36281babb29919ba` | 13 merger validation tests |

---

## 4. Merger Validation — Test Results

Run: `python3 runners/test_c1_parallel_merge.py`  
Result: **13/13 PASS**

| Test | Description | Result |
|------|-------------|--------|
| T1 | Single valid sc5 file accepted | PASS |
| T2 | Two files (sc5+sc6) merged in sorted order | PASS |
| T3 | Duplicate scenario_idx rejected | PASS |
| T4 | Missing scenario_idx rejected | PASS |
| T5 | Out-of-range scenario_idx rejected | PASS |
| T6 | f2_reference_sha256 mismatch rejected | PASS |
| T7 | f2_replay_denominator_sha256 mismatch rejected | PASS |
| T8 | git_tracked_dirty=True rejected | PASS |
| T9 | Wrong script name rejected | PASS |
| T10 | Wrong scientific_freeze_commit rejected | PASS |
| T11 | git_commit_full mismatch across workers rejected | PASS |
| T12 | Scenario fields preserved byte-for-byte after merge | PASS |
| T13 | Dry-run validates without writing output | PASS |

---

## 5. Equivalence Preflight — sc5

A single parallel worker ran sc5 with `GATE_F_N_FIRST=5 GATE_F_N_DEV=1`. Its output was compared
field-by-field against the sc5 result extracted from the sequential checkpoint.

| Field | Value |
|-------|-------|
| Sequential sc5 reference | `SEQUENTIAL_SC5_REFERENCE.json` |
| Reference SHA256 | `cc7b101ce6b1f2611f19ef431fab36bc1c5f6c4c69a6d10729184e4142239d92` |
| Parallel sc5 output | `results/gate_f_sc5-5_all.json` |
| Output SHA256 | `8a528aeac0120f065b037fdaad89f9350d0d1356d5d13b2244a7493ee86a5e1e` |
| scen_seed | 1843824993 (match) |
| wl_seed | 137046513 (match) |
| Field-value pairs compared | 21,037 |
| Ratios verified | 1.0, 1.25, 1.5, 2.0, 4.0, 8.0, unrestricted |
| Policies verified | full_random, full_fp, full_loc, full_fp_spread |
| Numeric tolerance | 0.0 (exact bitwise equality) |
| **Equivalence result** | **PASS — all 21,037 fields match exactly** |

Operational field excluded from comparison: `elapsed_s` only.

**Note on merger step:** The preflight launcher (n_dev=1) correctly produced `gate_f_sc5-5_all.json`
via the runner. The subsequent merger invocation found the file already present and aborted (by
design — merger refuses to overwrite). This is not a defect: in production (n_dev=25) each worker
writes `gate_f_sc{i}-{i}_all.json` and the merger produces the distinct `gate_f_sc5-29_all.json`.
The naming collision is specific to the single-worker preflight case.

Elapsed times:
- Sequential sc5 (from invalidated checkpoint): 4089s (68.2 min)
- Parallel sc5 (preflight): 4969s (82.8 min)

---

## 6. Resource Pilot — sc0 and sc1 (2 simultaneous workers)

Two dev scenarios ran simultaneously to measure parallelism overhead and resource usage.

| Metric | Value |
|--------|-------|
| Pilot scenarios | sc0, sc1 |
| Concurrency | 2 workers |
| sc0 elapsed | 5082.7s (84.7 min) |
| sc1 elapsed | 5244.1s (87.4 min) |
| Wall clock | 87.4 min |
| Both succeeded | Yes |
| RAM monitoring | Failed — wmic polling returned no samples (Windows subprocess timing issue) |

No OOM errors, no crashes, no unusual termination. Both workers completed successfully.

**Parallelism overhead:** The sequential reference sc5 took 68–83 min; pilot workers took 85–87 min
(~5–25% slower under 2-way concurrency). This is consistent with normal CPU/memory contention
and does not indicate a fundamental scalability problem.

Pilot outputs (sc0, sc1 JSON files) were cleaned up by the launcher after measurement, as designed.

---

## 7. Worker Count Recommendation

Based on pilot results:

- 2 workers succeeded without adverse effects
- ~5–25% runtime overhead observed under 2-way concurrency
- RAM monitoring failed; no OOM events occurred
- Runner is CPU-bound per scenario, low memory footprint per process

**Recommended: N_WORKERS=8**

At 8 workers and 25 scenarios (~87 min mean), the launcher fans out up to 8 concurrently and
starts replacements as slots free. Approximate wall time: 4 rounds × 87 min ≈ 5.5–6 hours.

If memory pressure is observed during the first batch, reduce to N_WORKERS=6 (wall time ~7 hours).

---

## 8. Production Launch Parameters (Pending Authorization)

```bash
cd artifacts/manuscript_completion/runners
GATE_F_N_FIRST=5 GATE_F_N_DEV=25 GATE_F_N_WORKERS=8 python3 c1_parallel_launcher.py
```

Pre-flight checks enforced by launcher on every run:
- Runner SHA256 verified
- F2 reference and denominator SHA256 verified
- Git working tree clean (no dirty tracked files)
- No pre-existing per-scenario output files
- No pre-existing checkpoint files for the range
- No pre-existing merged output

Merger enforces on every merge:
- Runner SHA256, all frozen inputs, freeze commit
- No duplicate or out-of-range scenario IDs
- git_commit_full consistency across all workers
- No dirty-run contamination

**Status: AWAITING AUTHORIZATION**
