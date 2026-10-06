#!/usr/bin/env python3
"""
Compute B_cab_hist_F2_replay: historical cabinet exceedance in the replay world
under F2 local-date thresholds. Uses the exact frozen replay-world event process
from r3_gate_f_run.py (bg_records + cohort_hist_records + sweep_cab_budget_fast).

Also reproduces B_cab_hist_F1 for acceptance validation.

The replay world differs from the full Task-D reference process:
  - Background: non-cohort node power from all jobs with any non-cohort node
  - Historical cohort: cohort node power from test-set jobs only
  - NO local-date clipping; uses raw observed timestamps
  - Time unit: milliseconds (datetime64[ms]), not nanoseconds

Output: artifacts/revision3/f2_replay_denominator.json
"""
import os, json, hashlib, heapq, sys, time
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
P1_DIR    = REPO_ROOT / "artifacts" / "phase1" / "analysis"
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
REV3_DIR  = REPO_ROOT / "artifacts" / "revision3"
TABLE_DIR = REV1_DIR / "tables"
DATA_DIR  = Path(os.environ.get("THERMALSHIFT_DATA_DIR",
    "C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset"))
OUT       = REV3_DIR / "f2_replay_denominator.json"

# ── Frozen reference for F1 acceptance test ──────────────────────────────────
# Acceptance: abs(diff) <= 1e-9 h.
F1_FROZEN_REFERENCE_H = 67917.76333331302

# ── Helpers (identical to r3_gate_f_run.py) ──────────────────────────────────
def _col_to_dt64ms(series):
    s = pd.to_datetime(series, utc=True)
    return s.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ms]")

def _rec_ts_ms(r):
    v = r["t_s"]
    return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))

def _rec_te_ms(r):
    v = r["t_e"]
    return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))

def sweep_cab_budget_fast(bg_events_sorted, cohort_records, thr):
    """Aggregate B and S across all cabinets. Identical logic to runner."""
    coh_ev = []
    for r in cohort_records:
        ppn = r["ppn"]; ts = _rec_ts_ms(r); te = _rec_te_ms(r)
        for c, n in r["cab_counts"].items():
            dp = ppn * n
            coh_ev.append((ts, +1, c, dp))
            coh_ev.append((te, -1, c, dp))
    coh_ev.sort()
    P_cab = defaultdict(float); last_t = {}
    B = 0.0; S = 0.0
    for t, sign, c, dp in heapq.merge(bg_events_sorted, coh_ev):
        if c in last_t and t != last_t[c]:
            dt_h = (t - last_t[c]) / 3_600_000.0
            if dt_h > 0:
                exc = P_cab[c] - thr.get(c, 0.0)
                if exc > 0:
                    B += dt_h
                    S += dt_h * exc
        P_cab[c] += sign * dp
        last_t[c] = t
    return B, S

def sweep_cab_budget_percab(bg_events_sorted, cohort_records, thr, all_cabinets):
    """Per-cabinet B and S. Same logic but accumulated per cabinet."""
    coh_ev = []
    for r in cohort_records:
        ppn = r["ppn"]; ts = _rec_ts_ms(r); te = _rec_te_ms(r)
        for c, n in r["cab_counts"].items():
            dp = ppn * n
            coh_ev.append((ts, +1, c, dp))
            coh_ev.append((te, -1, c, dp))
    coh_ev.sort()
    P_cab = defaultdict(float); last_t = {}
    B_cab = {c: 0.0 for c in all_cabinets}
    S_cab = {c: 0.0 for c in all_cabinets}
    for t, sign, c, dp in heapq.merge(bg_events_sorted, coh_ev):
        if c in last_t and t != last_t[c]:
            dt_h = (t - last_t[c]) / 3_600_000.0
            if dt_h > 0:
                exc = P_cab[c] - thr.get(c, 0.0)
                if exc > 0:
                    B_cab[c] = B_cab.get(c, 0.0) + dt_h
                    S_cab[c] = S_cab.get(c, 0.0) + dt_h * exc
        P_cab[c] += sign * dp
        last_t[c] = t
    return B_cab, S_cab

# ── Load data ─────────────────────────────────────────────────────────────────
print("Loading parquet data ...")
t0 = time.time()
fp_df   = pd.read_parquet(P1_DIR / "phase3a_fingerprint_2024.parquet")
test_df = pd.read_parquet(P1_DIR / "phase3a_test_set.parquet")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"  fp: {len(fp_df)} nodes  test: {len(test_df):,} rows  all_jobs: {len(all_jobs):,}  ({time.time()-t0:.1f}s)")

fp_df.index.name = "node"
cohort_set  = set(fp_df.index)
test_id_set = set(test_df["job_idx"].astype(int))
print(f"  cohort_set: {len(cohort_set)} nodes  test_id_set: {len(test_id_set):,} job IDs")

print("Loading topology ...")
fleet_topo  = pd.read_csv(TABLE_DIR / "fleet_node_topology.csv")
node_to_cab = dict(zip(fleet_topo["hostname"].values,
                       fleet_topo["cabinet"].values.astype(int)))
all_cabinets = sorted(set(node_to_cab.values()))
assert len(node_to_cab) == 9856, f"Expected 9856 nodes, got {len(node_to_cab)}"
assert len(all_cabinets) == 77,  f"Expected 77 cabinets, got {len(all_cabinets)}"

print("Loading thresholds ...")
with open(REV1_DIR / "results" / "cabinet_power_envelopes.json") as f:
    cab_env = json.load(f)
p99_med_F1 = float(np.median([v * 1e3 for v in cab_env["per_cabinet_p99_kW_correct"].values()]))
cab_p99_W_F1: dict[int, float] = {
    int(float(k)): v * 1e3 for k, v in cab_env["per_cabinet_p99_kW_correct"].items()
}
cab_p99_W_F1 = {c: cab_p99_W_F1.get(c, p99_med_F1) for c in all_cabinets}

with open(REV3_DIR / "f2_local_scheduling_reference.json") as f:
    f2_ref = json.load(f)
p99_med_F2 = float(np.median([x["Q_F2_local_W"] for x in f2_ref["per_cabinet"]]))
cab_p99_W_F2: dict[int, float] = {
    int(x["cabinet_id"]): float(x["Q_F2_local_W"]) for x in f2_ref["per_cabinet"]
}
cab_p99_W_F2 = {c: cab_p99_W_F2.get(c, p99_med_F2) for c in all_cabinets}
f2_ref_sha256 = hashlib.sha256(
    open(REV3_DIR / "f2_local_scheduling_reference.json", "rb").read()).hexdigest()

print(f"  F1 median threshold: {p99_med_F1/1000:.2f} kW")
print(f"  F2 median threshold: {p99_med_F2/1000:.2f} kW")

# ── Build replay records (exact runner logic from step [8]) ──────────────────
print("Building replay records ...")
t0 = time.time()
_all_jids = all_jobs["job_idx_int"].values
_all_Pj   = np.where(all_jobs["mean_power"].isna().values, 0.0,
                     all_jobs["mean_power"].values.astype(float))
_all_nc   = np.maximum(all_jobs["node_count"].values.astype(int), 1)
_all_hl   = all_jobs["host_list"].values
_all_st   = _col_to_dt64ms(all_jobs["start_time"])
_all_et   = _col_to_dt64ms(all_jobs["end_time"])

bg_records: list[dict] = []
cohort_hist_records: list[dict] = []

for jid, P_j, nc, hl, t_s, t_e in zip(_all_jids, _all_Pj, _all_nc, _all_hl, _all_st, _all_et):
    ppn = P_j / nc
    ncc: dict[int, int] = {}   # non-cohort cab counts
    chc: dict[int, int] = {}   # cohort cab counts
    for hn in hl:
        c = node_to_cab.get(hn, -1)
        if c < 0: continue
        if hn in cohort_set: chc[c] = chc.get(c, 0) + 1
        else:                ncc[c] = ncc.get(c, 0) + 1
    if ncc:
        bg_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": ncc})
    if int(jid) in test_id_set and chc:
        cohort_hist_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": chc})

print(f"  bg_records: {len(bg_records):,}  cohort_hist_records: {len(cohort_hist_records):,}"
      f"  ({time.time()-t0:.1f}s)")

# Count node-hour contributions
bg_node_contrib = sum(sum(r["cab_counts"].values()) for r in bg_records)
coh_node_contrib = sum(sum(r["cab_counts"].values()) for r in cohort_hist_records)
print(f"  bg node-cabinet contributions: {bg_node_contrib:,}")
print(f"  cohort node-cabinet contributions: {coh_node_contrib:,}")

# ── Build bg_events_sorted ────────────────────────────────────────────────────
print("Building bg_events_sorted ...")
t0 = time.time()
bg_events_sorted: list[tuple] = []
for _r in bg_records:
    _ppn = _r["ppn"]
    _ts  = int(_r["t_s"].astype("int64"))
    _te  = int(_r["t_e"].astype("int64"))
    for _c, _n in _r["cab_counts"].items():
        _dp = _ppn * _n
        bg_events_sorted.append((_ts, +1, _c, _dp))
        bg_events_sorted.append((_te, -1, _c, _dp))
bg_events_sorted.sort()
print(f"  {len(bg_events_sorted):,} bg events  ({time.time()-t0:.1f}s)")

# ── Compute denominators ──────────────────────────────────────────────────────
print("\nComputing B_cab_hist_F1_reproduced ...")
t0 = time.time()
B_F1, S_F1 = sweep_cab_budget_fast(bg_events_sorted, cohort_hist_records, cab_p99_W_F1)
print(f"  B_cab_hist_F1_reproduced = {B_F1:.10f} h  ({time.time()-t0:.1f}s)")

print("Computing B_cab_hist_F2_replay ...")
t0 = time.time()
B_F2, S_F2 = sweep_cab_budget_fast(bg_events_sorted, cohort_hist_records, cab_p99_W_F2)
print(f"  B_cab_hist_F2_replay = {B_F2:.10f} h  ({time.time()-t0:.1f}s)")

print("\nComputing per-cabinet breakdown (F1) ...")
t0 = time.time()
B_percab_F1, S_percab_F1 = sweep_cab_budget_percab(
    bg_events_sorted, cohort_hist_records, cab_p99_W_F1, all_cabinets)
print(f"  Done  ({time.time()-t0:.1f}s)")

print("Computing per-cabinet breakdown (F2) ...")
t0 = time.time()
B_percab_F2, S_percab_F2 = sweep_cab_budget_percab(
    bg_events_sorted, cohort_hist_records, cab_p99_W_F2, all_cabinets)
print(f"  Done  ({time.time()-t0:.1f}s)")

# ── Aggregate cross-checks ────────────────────────────────────────────────────
B_F1_check = sum(B_percab_F1.values())
B_F2_check = sum(B_percab_F2.values())
assert abs(B_F1 - B_F1_check) < 1e-6, f"F1 percab sum mismatch: {B_F1} vs {B_F1_check}"
assert abs(B_F2 - B_F2_check) < 1e-6, f"F2 percab sum mismatch: {B_F2} vs {B_F2_check}"
print(f"\nAggregate cross-check OK: F1 diff={abs(B_F1-B_F1_check):.2e}  F2 diff={abs(B_F2-B_F2_check):.2e}")

# ── F1 acceptance test ────────────────────────────────────────────────────────
if F1_FROZEN_REFERENCE_H is not None:
    diff = abs(B_F1 - F1_FROZEN_REFERENCE_H)
    status = "PASS" if diff <= 1e-9 else "FAIL"
    print(f"F1 reproduction acceptance [{status}]: |{B_F1:.10f} - {F1_FROZEN_REFERENCE_H:.10f}| = {diff:.2e}")
    if status == "FAIL":
        sys.exit(1)
else:
    print(f"F1_FROZEN_REFERENCE_H not set — skipping acceptance test.")
    print(f"Set F1_FROZEN_REFERENCE_H = {B_F1!r} in this script after first run.")

# ── Time range ────────────────────────────────────────────────────────────────
all_st_ms = _all_st.astype(np.int64)
all_et_ms = _all_et.astype(np.int64)
t_min_ms = int(all_st_ms.min())
t_max_ms = int(all_et_ms.max())
t_span_h = (t_max_ms - t_min_ms) / 3_600_000.0

# ── Build output ──────────────────────────────────────────────────────────────
output = {
    "provenance": {
        "script":                "compute_f2_replay_denominator.py",
        "runner_reference":      "r3_gate_f_run.py (step [8], sweep_cab_budget_fast)",
        "f2_ref_sha256":         str(f2_ref_sha256),
        "n_all_jobs":            int(len(all_jobs)),
        "n_test_set_jobs":       int(len(test_id_set)),
        "n_cohort_nodes":        int(len(cohort_set)),
    },
    "replay_world_structure": {
        "bg_records":              int(len(bg_records)),
        "cohort_hist_records":     int(len(cohort_hist_records)),
        "bg_events_sorted":        int(len(bg_events_sorted)),
        "bg_node_cab_contributions":  int(bg_node_contrib),
        "coh_node_cab_contributions": int(coh_node_contrib),
        "time_range_h":            float(t_span_h),
        "note": (
            "bg_records: jobs with >=1 non-cohort node. "
            "cohort_hist_records: test-set jobs with >=1 cohort node. "
            "NO local-date clipping. Timestamps in milliseconds (datetime64[ms])."
        ),
    },
    "aggregate": {
        "B_cab_hist_F1_h":       float(B_F1),
        "S_cab_hist_F1_Wh":      float(S_F1),
        "B_cab_hist_F2_replay_h": float(B_F2),
        "S_cab_hist_F2_replay_Wh": float(S_F2),
        "n_cabinets":            77,
    },
    "per_cabinet": [
        {
            "cabinet":          int(c),
            "Q_F1_W":           float(cab_p99_W_F1[c]),
            "Q_F2_local_W":     float(cab_p99_W_F2[c]),
            "B_F1_h":           float(B_percab_F1[c]),
            "S_F1_Wh":          float(S_percab_F1[c]),
            "B_F2_replay_h":    float(B_percab_F2[c]),
            "S_F2_replay_Wh":   float(S_percab_F2[c]),
        }
        for c in all_cabinets
    ],
}

with open(OUT, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nWritten: {OUT}")
print(f"\n=== SUMMARY ===")
print(f"B_cab_hist_F1_reproduced  = {B_F1:.10f} h")
print(f"B_cab_hist_F2_replay      = {B_F2:.10f} h")
print(f"F2/F1 ratio               = {B_F2/B_F1:.6f}")
print(f"bg_records                = {len(bg_records):,}")
print(f"cohort_hist_records       = {len(cohort_hist_records):,}")
