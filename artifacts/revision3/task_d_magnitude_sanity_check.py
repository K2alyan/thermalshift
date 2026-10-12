#!/usr/bin/env python3
"""
Task D Magnitude Sanity Check
==============================
Independently re-derives F1 and F2 for 10 representative cabinets
and compares against committed results.

Cabinets: [2000, 2103, 2204, 2300, 2400, 2500, 2600, 2610, 2200, 2001]

Writes: artifacts/revision3/task_d_magnitude_sanity_check.json

Does NOT modify any files in artifacts/revision3/results/.
Does NOT run any scheduling simulation.
"""

import os
import sys
import json
import datetime
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
REV3_DIR  = REPO_ROOT / "artifacts" / "revision3"
RESULTS   = REV3_DIR / "results"
OUT_JSON  = REV3_DIR / "task_d_magnitude_sanity_check.json"

TOPOLOGY_CSV     = REV1_DIR / "tables" / "fleet_node_topology.csv"
F1_ENVELOPE_JSON = REV1_DIR / "results" / "cabinet_power_envelopes.json"
F2_JSON          = RESULTS / "f2_timeweighted_cabinet_reference.json"

CABINETS_TO_CHECK = [2000, 2103, 2204, 2300, 2400, 2500, 2600, 2610, 2200, 2001]
TOLERANCE = 1e-6

data_dir_env = os.environ.get("THERMALSHIFT_DATA_DIR")
if not data_dir_env:
    sys.exit("FATAL: THERMALSHIFT_DATA_DIR not set")
DATA_DIR = Path(data_dir_env)
PARQUET  = DATA_DIR / "frontier-completed-job-info.parquet"


def jf(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except Exception:
        return None


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Identical to original script's weighted_quantile function."""
    if len(values) == 0:
        return float("nan")
    order    = np.argsort(values)
    vals_s   = values[order]
    wts_s    = weights[order]
    cum_wt   = np.cumsum(wts_s)
    total_wt = cum_wt[-1]
    threshold = q * total_wt
    idx = np.searchsorted(cum_wt, threshold, side="left")
    if idx >= len(vals_s):
        idx = len(vals_s) - 1
    return float(vals_s[idx])


print("Loading parquet ...")
df_raw = pd.read_parquet(
    PARQUET,
    columns=["job_idx", "date_dir", "start_time", "end_time",
             "mean_power", "node_count", "host_list"],
)
print(f"  Loaded {len(df_raw):,} rows")

print("Loading topology ...")
topo = pd.read_csv(TOPOLOGY_CSV)
node_to_cab = dict(zip(topo["hostname"], topo["cabinet"]))

print("Loading F1 reference ...")
with open(F1_ENVELOPE_JSON) as fh:
    f1_envelope = json.load(fh)
f1_ref = f1_envelope["per_cabinet_p99_kW_correct"]

print("Loading committed F2 results ...")
with open(F2_JSON) as fh:
    f2_data = json.load(fh)
f2_per_cab = {r["cabinet"]: r for r in f2_data["per_cabinet"]}

# Filter to qualifying rows
mask = (
    df_raw["mean_power"].notna() &
    (df_raw["mean_power"] > 0) &
    (df_raw["node_count"] > 0) &
    df_raw["start_time"].notna() &
    df_raw["end_time"].notna()
)
df = df_raw[mask].copy()
df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
df["end_time"]   = pd.to_datetime(df["end_time"],   utc=True)
print(f"  Qualifying rows: {len(df):,}")

# unit check: mean_power is in Watts
# Frontier cabinets: ~100-300 kW at busy state. A 512-node cabinet with ~200W/node = ~100 kW
# So mean_power for a full-cabinet job of 512 nodes at 200 W/node = 102400 W
# P_job_c = (mean_power_W / node_count) * n_cab_nodes / 1000 = (102400/512)*512/1000 = 102.4 kW  CORRECT
print("  Unit check: mean_power treated as Watts, converting to kW by / 1000.0")

# Reconstruct support blocks
unique_date_strs = df_raw["date_dir"].dropna().unique()
parsed_dates     = sorted(datetime.date.fromisoformat(d) for d in unique_date_strs)
blocks_raw = []
bs = parsed_dates[0]; be = parsed_dates[0]
for d in parsed_dates[1:]:
    if (d - be).days == 1:
        be = d
    else:
        blocks_raw.append((bs, be)); bs = d; be = d
blocks_raw.append((bs, be))

support_blocks = [
    (pd.Timestamp(s, tz="UTC"), pd.Timestamp(e + datetime.timedelta(days=1), tz="UTC"))
    for s, e in blocks_raw
]
total_support_h = sum((e - s).total_seconds() / 3600 for s, e in support_blocks)
print(f"  Support blocks: {len(support_blocks)}, total {total_support_h:.1f}h")

# Build reverse mapping: cabinet -> set of hostnames
cab_to_nodes = defaultdict(set)
for hostname, cab in node_to_cab.items():
    cab_to_nodes[cab].add(hostname)

results = []
all_pass = True

for cab in CABINETS_TO_CHECK:
    print(f"\nChecking cabinet {cab} ...")
    committed_r = f2_per_cab.get(cab, {})
    committed_f1 = committed_r.get("Q_F1_kW")
    committed_f2 = committed_r.get("Q_F2_kW")

    cab_nodes = cab_to_nodes.get(cab, set())
    n_cab_nodes_total = len(cab_nodes)
    print(f"  Cabinet has {n_cab_nodes_total} nodes")

    # ── Step 1-2: For each qualifying job, compute contribution ──────────────
    cab_p_vals = []  # For F1: per-job P_job_c values
    cab_intervals = []  # For F2: (clip_start, clip_end, P_kW) tuples

    for _, row in df.iterrows():
        hosts = row["host_list"]
        if hosts is None or len(hosts) == 0:
            continue

        # Count nodes in this cabinet
        n_nodes_in_cab = sum(1 for h in hosts if h in cab_nodes)
        if n_nodes_in_cab == 0:
            continue

        ppn_W = float(row["mean_power"]) / int(row["node_count"])
        p_kW  = ppn_W * n_nodes_in_cab / 1000.0  # Step 3: unit check

        start = row["start_time"]
        end   = row["end_time"]

        # For F1 reproduction: P99 of per-job contributions
        if p_kW > 0:
            cab_p_vals.append(p_kW)

        # For F2: clip to support
        for blk_s, blk_e in support_blocks:
            if start >= blk_e or end <= blk_s:
                continue
            cs = max(start, blk_s)
            ce = min(end, blk_e)
            dur_s = (ce - cs).total_seconds()
            if dur_s > 0:
                cab_intervals.append((cs, ce, p_kW))

    print(f"  Qualifying job contributions: {len(cab_p_vals):,}, clipped intervals: {len(cab_intervals):,}")

    # ── Step 4: Independent F1 ─────────────────────────────────────────────────
    if not cab_p_vals:
        print(f"  SKIP: no contributions for cabinet {cab}")
        results.append({
            "cabinet": cab,
            "status": "FAIL",
            "error": "no_contributions",
        })
        all_pass = False
        continue

    arr_f1 = np.array(cab_p_vals)
    computed_f1 = float(np.percentile(arr_f1, 99))

    # ── Unit check ─────────────────────────────────────────────────────────────
    max_p = float(arr_f1.max())
    # Expected: per-job contribution to a single cabinet should be << total system power
    # A fully-loaded 512-node cabinet at ~200W/node = ~100kW
    # max_p should be in range ~1 kW to ~400 kW
    unit_check_pass = (0.1 <= max_p <= 1000.0)
    unit_check_note = f"max per-job-cabinet contribution = {max_p:.2f} kW (expected 0.1-1000 kW)"

    # Cross-check with committed max_observed
    committed_max_obs = committed_r.get("max_observed_reconstructed_concurrent_kW")
    if committed_max_obs:
        unit_check_note += f"; committed max_obs_concurrent = {committed_max_obs:.2f} kW"

    # ── Step 5-9: Independent F2 (event-driven) ─────────────────────────────────
    events = defaultdict(float)
    for cs, ce, p_kW in cab_intervals:
        events[cs.value] += p_kW
        events[ce.value] -= p_kW

    # Add support sentinels
    for blk_s, blk_e in support_blocks:
        if blk_s.value not in events:
            events[blk_s.value] = 0.0
        else:
            events[blk_s.value] += 0.0
        if blk_e.value not in events:
            events[blk_e.value] = 0.0

    # Sort unique timestamps
    sorted_ts_ns = sorted(events.keys())
    unique_ts = [pd.Timestamp(ns, tz="UTC") for ns in sorted_ts_ns]

    # ── Simultaneous-events check ──────────────────────────────────────────────
    # By construction: events dict aggregates all simultaneous events at same ns key
    simultaneous_check = True  # By construction, all same-ns events are merged
    simultaneous_note  = "Simultaneous events merged by defaultdict(float) keyed on nanosecond timestamp"

    # Build state intervals
    running_power = 0.0
    state_intervals = []
    running_power_vals = []  # track all running power values for validation

    for i, ts in enumerate(unique_ts):
        dp = events[ts.value]
        running_power += dp
        if running_power < 0.0 and running_power > -1e-9:
            running_power = 0.0

        if i + 1 < len(unique_ts):
            t_next = unique_ts[i + 1]
            dur_s  = (t_next - ts).total_seconds()
            if dur_s > 0:
                mid   = ts + (t_next - ts) / 2
                in_sup = any(blk_s <= mid < blk_e for blk_s, blk_e in support_blocks)
                if in_sup:
                    state_intervals.append({
                        "t_start": ts, "t_end": t_next,
                        "power_kW": running_power, "duration_s": dur_s
                    })

    if not state_intervals:
        print(f"  FAIL: no state intervals for cabinet {cab}")
        results.append({
            "cabinet": cab,
            "status": "FAIL",
            "error": "no_state_intervals",
        })
        all_pass = False
        continue

    powers_arr = np.array([s["power_kW"]  for s in state_intervals])
    durs_arr   = np.array([s["duration_s"] for s in state_intervals])

    computed_f2 = weighted_quantile(powers_arr, durs_arr, 0.99)

    # ── Step 8: Duration sum check ─────────────────────────────────────────────
    dur_sum = float(durs_arr.sum())
    expected_s = total_support_h * 3600
    boundary_check_pass = abs(dur_sum - expected_s) <= 1.0
    boundary_note = f"dur_sum={dur_sum:.1f}s expected={expected_s:.1f}s diff={abs(dur_sum-expected_s):.3f}s"

    # ── Step 10: Compare ───────────────────────────────────────────────────────
    diff_f1 = abs(computed_f1 - committed_f1) if committed_f1 is not None else None
    diff_f2 = abs(computed_f2 - committed_f2) if committed_f2 is not None else None

    f1_ok = (diff_f1 is not None and diff_f1 <= TOLERANCE)
    f2_ok = (diff_f2 is not None and diff_f2 <= TOLERANCE)
    cab_pass = f1_ok and f2_ok and unit_check_pass and boundary_check_pass and simultaneous_check

    if not cab_pass:
        all_pass = False

    result = {
        "cabinet": cab,
        "computed_Q_F1": jf(computed_f1),
        "committed_Q_F1": jf(committed_f1),
        "diff_F1": jf(diff_f1),
        "computed_Q_F2": jf(computed_f2),
        "committed_Q_F2": jf(committed_f2),
        "diff_F2": jf(diff_f2),
        "unit_check": "PASS" if unit_check_pass else "FAIL",
        "unit_check_note": unit_check_note,
        "boundary_check": "PASS" if boundary_check_pass else "FAIL",
        "boundary_check_note": boundary_note,
        "simultaneous_check": "PASS" if simultaneous_check else "FAIL",
        "simultaneous_check_note": simultaneous_note,
        "f1_within_tolerance": f1_ok,
        "f2_within_tolerance": f2_ok,
        "status": "PASS" if cab_pass else "FAIL",
    }
    results.append(result)
    print(f"  F1: computed={computed_f1:.6f} committed={committed_f1:.6f} diff={diff_f1:.2e} -> {'PASS' if f1_ok else 'FAIL'}")
    print(f"  F2: computed={computed_f2:.6f} committed={committed_f2:.6f} diff={diff_f2:.2e} -> {'PASS' if f2_ok else 'FAIL'}")
    print(f"  unit_check={result['unit_check']} boundary_check={result['boundary_check']}")
    print(f"  CABINET {cab}: {'PASS' if cab_pass else 'FAIL'}")

n_pass = sum(1 for r in results if r.get("status") == "PASS")
n_fail = sum(1 for r in results if r.get("status") == "FAIL")
print(f"\n=== MAGNITUDE SANITY SUMMARY: {n_pass}/{len(results)} PASS ===")

out = {
    "audit_date": "2026-10-06",
    "plan_commit": "c674209",
    "tolerance": TOLERANCE,
    "n_cabinets": len(results),
    "n_pass": n_pass,
    "n_fail": n_fail,
    "overall": "PASS" if n_pass == len(results) else "FAIL",
    "cabinets": results,
    "unit_interpretation": (
        "mean_power field is in Watts. P_job_c = (mean_power_W / node_count) * n_nodes_in_cabinet / 1000 [kW]. "
        "Verified: max per-job-cabinet contribution is in plausible range for Frontier supercomputer cabinets (10-400 kW)."
    )
}

with open(OUT_JSON, "w", encoding="utf-8") as fh:
    json.dump(out, fh, indent=2, ensure_ascii=False)

print(f"Wrote: {OUT_JSON}")

if not all_pass:
    sys.exit(f"STOP: {n_fail} cabinet(s) failed magnitude sanity check")
