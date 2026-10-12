#!/usr/bin/env python3
"""
Compute F2 historical B_cab denominator (fast vectorized version).
Uses 152,400 observed jobs, local-date (America/New_York) support, F2_local thresholds.
All timestamps converted to int64 nanoseconds for fast comparison.
"""
import os, json, hashlib, datetime, sys, bisect
from pathlib import Path
import numpy as np
import pandas as pd
import pytz

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("THERMALSHIFT_DATA_DIR",
    "C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset"))
PARQUET   = DATA_DIR / "frontier-completed-job-info.parquet"
TOPO_CSV  = REPO_ROOT / "artifacts/revision1/tables/fleet_node_topology.csv"
F2_REF    = REPO_ROOT / "artifacts/revision3/f2_local_scheduling_reference.json"
OUT       = REPO_ROOT / "artifacts/revision3/f2_denominator.json"

eastern = pytz.timezone("America/New_York")
utc     = pytz.utc

# ── Load data ────────────────────────────────────────────────────────────────
print("Loading parquet ...")
df = pd.read_parquet(PARQUET, columns=[
    "job_idx","date_dir","start_time","end_time","mean_power","node_count","host_list"])
print(f"  {len(df):,} rows")

print("Loading topology ...")
topo = pd.read_csv(TOPO_CSV)
node_to_cab: dict[str, int] = dict(zip(topo["hostname"], topo["cabinet"]))

print("Loading F2 thresholds ...")
with open(F2_REF) as f:
    ref = json.load(f)
f2_thr_kW: dict[int, float] = {int(x["cabinet_id"]): x["Q_F2_local_kW"]
                                 for x in ref["per_cabinet"]}
cabinets = sorted(f2_thr_kW.keys())

# ── Filter qualifying jobs ───────────────────────────────────────────────────
mask = (df["mean_power"].notna() & (df["mean_power"] > 0) &
        (df["node_count"] > 0) & df["start_time"].notna() & df["end_time"].notna())
df_q = df[mask].copy()
print(f"  Qualifying: {len(df_q):,} / {len(df):,}")

# ── Convert timestamps to UTC int64 nanoseconds ─────────────────────────────
print("Converting timestamps to int64 ns ...")
# pandas may store timestamps in ms resolution (datetime64[ms, UTC]);
# use .dt.tz_convert("UTC") then cast to datetime64[ns] to ensure nanoseconds.
st_ns = df_q["start_time"].dt.tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)
et_ns = df_q["end_time"].dt.tz_convert("UTC").values.astype("datetime64[ns]").astype(np.int64)
print(f"  Timestamp resolution check: st_ns[0]={st_ns[0]} ({pd.Timestamp(st_ns[0])})")

# Power per node in kW (mean_power is in W)
pw_per_node_kW = (df_q["mean_power"].values.astype(float) / 1000.0 /
                  np.maximum(df_q["node_count"].values.astype(float), 1))
host_lists = df_q["host_list"].values
n_jobs = len(df_q)

# ── Build local-date support blocks as int64 ns ──────────────────────────────
print("Building local-date support blocks ...")
date_strs = sorted(df_q["date_dir"].unique())
block_starts_ns = []
block_ends_ns   = []
for d in date_strs:
    dt = datetime.datetime.strptime(str(d), "%Y-%m-%d")
    s_loc = eastern.localize(datetime.datetime(dt.year, dt.month, dt.day))
    e_loc = s_loc + datetime.timedelta(days=1)
    s_utc = s_loc.astimezone(utc)
    e_utc = e_loc.astimezone(utc)
    # Convert to int64 ns
    s_ns = int(s_utc.timestamp() * 1e9)
    e_ns = int(e_utc.timestamp() * 1e9)
    block_starts_ns.append(s_ns)
    block_ends_ns.append(e_ns)

# Merge adjacent
raw = sorted(zip(block_starts_ns, block_ends_ns))
merged = []
for s, e in raw:
    if merged and s <= merged[-1][1]:
        merged[-1] = (merged[-1][0], max(merged[-1][1], e))
    else:
        merged.append([s, e])
blk_s = np.array([x[0] for x in merged], dtype=np.int64)
blk_e = np.array([x[1] for x in merged], dtype=np.int64)
n_blocks = len(blk_s)
total_support_ns = int(np.sum(blk_e - blk_s))
total_support_s  = total_support_ns / 1e9
print(f"  {len(date_strs)} dates -> {n_blocks} blocks, {total_support_s/3600:.1f}h support")

# Precompute sorted block starts for bisect
blk_s_list = blk_s.tolist()

def in_support(mid_ns: int) -> bool:
    """O(log n) support membership test using bisect."""
    i = bisect.bisect_right(blk_s_list, mid_ns) - 1
    if i < 0:
        return False
    return mid_ns < blk_e[i]

# ── Build per-cabinet contribution lookup ────────────────────────────────────
# For each job, parse host_list and accumulate per-cabinet (power_kW, start_ns, end_ns)
print(f"Building per-cabinet contributions (n_jobs={n_jobs:,}) ...")
cab_jobs: dict[int, list] = {c: [] for c in cabinets}

NS_PER_S = np.int64(1_000_000_000)

for i in range(n_jobs):
    if i % 10000 == 0:
        print(f"  job {i:,}/{n_jobs:,}", end="\r", flush=True)
    hl = host_lists[i]
    if hl is None:
        continue
    ppn = float(pw_per_node_kW[i])
    js  = int(st_ns[i])
    je  = int(et_ns[i])
    if js >= je:
        continue
    # Count nodes per cabinet for this job
    cab_counts: dict[int, int] = {}
    for h in hl:
        c = node_to_cab.get(h)
        if c is not None:
            cab_counts[c] = cab_counts.get(c, 0) + 1
    for c, n in cab_counts.items():
        if c in cab_jobs:
            cab_jobs[c].append((ppn * n, js, je))

print(f"\n  Done. Total job-cabinet contributions: {sum(len(v) for v in cab_jobs.values()):,}")

# ── Per-cabinet F2 exceedance sweep ─────────────────────────────────────────
print("Sweeping per-cabinet exceedance ...")
results = {}

for cab_idx, cab in enumerate(cabinets):
    thr_kW = f2_thr_kW[cab]
    jobs   = cab_jobs[cab]

    if not jobs:
        results[cab] = {"exceedance_h": 0.0, "exceedance_fraction": 0.0,
                        "calendar_support_h": total_support_s / 3600.0}
        continue

    # Build event list: clip each job to each support block
    events = []  # (timestamp_ns, delta_kW)
    for pwr, js, je in jobs:
        for bi in range(n_blocks):
            eff_s = max(js, int(blk_s[bi]))
            eff_e = min(je, int(blk_e[bi]))
            if eff_s >= eff_e:
                continue
            events.append((eff_s,  pwr))
            events.append((eff_e, -pwr))

    # Add block boundary sentinels
    for bi in range(n_blocks):
        events.append((int(blk_s[bi]), 0.0))
        events.append((int(blk_e[bi]), 0.0))

    # Sort by timestamp; Python tuple sort is fast
    events.sort()

    # Piecewise-constant sweep
    exc_ns   = 0
    cur_kW   = 0.0
    prev_t   = None

    for t, delta in events:
        if prev_t is not None and t > prev_t:
            dt_ns = t - prev_t
            if dt_ns > 0:
                mid_ns = prev_t + dt_ns // 2
                if in_support(mid_ns):
                    if cur_kW > thr_kW:
                        exc_ns += dt_ns
        cur_kW += delta
        prev_t = t

    exc_s    = exc_ns / 1e9
    exc_frac = exc_s / total_support_s if total_support_s > 0 else 0.0
    results[cab] = {
        "exceedance_h":        exc_s / 3600.0,
        "exceedance_fraction": exc_frac,
        "calendar_support_h":  total_support_s / 3600.0,
    }
    if (cab_idx + 1) % 10 == 0 or cab_idx == 0:
        print(f"  {cab_idx+1:3d}/77  cab={cab}  exc={exc_frac:.4%}")

# ── Aggregate and validate ───────────────────────────────────────────────────
B_h   = sum(v["exceedance_h"] for v in results.values())
agg_f = B_h / (total_support_s / 3600.0 * len(cabinets))

fracs = [v["exceedance_fraction"] for v in results.values()]
n_ok  = sum(1 for f in fracs if 0.005 <= f <= 0.015)

print(f"\nB_cab_hist_F2 = {B_h:.4f} h")
print(f"Aggregate exceedance fraction = {agg_f:.4%}")
print(f"Cabinets exc in [0.5%,1.5%]: {n_ok}/77")
print(f"Per-cabinet exc: min={min(fracs):.4%} median={np.median(fracs):.4%} max={max(fracs):.4%}")

# ── Write output ─────────────────────────────────────────────────────────────
f2_ref_sha256 = hashlib.sha256(open(F2_REF, "rb").read()).hexdigest()
output = {
    "provenance": {
        "task_d2_commit":      "ab3119c",
        "f2_local_ref_sha256": f2_ref_sha256,
        "n_qualifying_jobs":   int(mask.sum()),
        "n_date_strs":         len(date_strs),
        "n_blocks":            n_blocks,
        "total_support_h":     total_support_s / 3600.0,
        "support_convention":  "America/New_York local calendar end-date, converted to UTC",
    },
    "aggregate": {
        "B_cab_hist_F2_h":             B_h,
        "aggregate_exceedance_fraction": agg_f,
        "n_cabinets":                  len(cabinets),
    },
    "per_cabinet_stats": {
        "exc_frac_min":    float(min(fracs)),
        "exc_frac_median": float(np.median(fracs)),
        "exc_frac_p90":    float(np.percentile(fracs, 90)),
        "exc_frac_max":    float(max(fracs)),
    },
    "per_cabinet": [
        {
            "cabinet":              cab,
            "B_cab_hist_F2_h":      results[cab]["exceedance_h"],
            "exceedance_fraction":  results[cab]["exceedance_fraction"],
            "calendar_support_h":   results[cab]["calendar_support_h"],
            "Q_F2_local_kW":        f2_thr_kW[cab],
        }
        for cab in cabinets
    ],
    "validation": {
        "n_cabinets_exc_in_0p5_to_1p5pct": n_ok,
        "n_cabinets_total":                77,
        "all_exceedance_positive":         all(v["exceedance_h"] > 0 for v in results.values()),
    },
}
with open(OUT, "w") as f:
    json.dump(output, f, indent=2)
print(f"\nWritten: {OUT}")
