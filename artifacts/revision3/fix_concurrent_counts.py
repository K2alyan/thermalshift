#!/usr/bin/env python3
"""
Fix the concurrent job/node counts in task_d_supplementary_audit.json.
The original computation had a bug in sampling timestamps — it was
sampling pd.Timestamp objects from a Python list, which produced
index integers instead of timestamps.

This script recomputes correctly and patches the JSON in place.
"""
import os, json
import numpy as np
import pandas as pd
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REV3_DIR  = REPO_ROOT / "artifacts" / "revision3"
OUT_JSON  = REV3_DIR / "task_d_supplementary_audit.json"

PARQUET = Path(os.environ["THERMALSHIFT_DATA_DIR"]) / "frontier-completed-job-info.parquet"

print("Loading parquet (start/end/node_count columns only)...")
df = pd.read_parquet(
    PARQUET,
    columns=["start_time", "end_time", "node_count", "mean_power"]
)
df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
df["end_time"]   = pd.to_datetime(df["end_time"],   utc=True)

mask = (
    df["mean_power"].notna() & (df["mean_power"] > 0) &
    (df["node_count"] > 0) &
    df["start_time"].notna() & df["end_time"].notna()
)
df = df[mask]
print(f"  Qualifying rows: {len(df):,}")

# Collect all unique event timestamps (mix of starts and ends)
ts_all = np.concatenate([
    df["start_time"].values.astype("int64"),
    df["end_time"].values.astype("int64")
])
ts_unique = np.unique(ts_all)
print(f"  Total unique event timestamps: {len(ts_unique):,}")

# Sample 5000 uniformly
rng = np.random.default_rng(42)
n_sample = min(5000, len(ts_unique))
idx = rng.choice(len(ts_unique), n_sample, replace=False)
sample_ts_ns = ts_unique[idx]

starts_ns = df["start_time"].values.astype("int64")
ends_ns   = df["end_time"].values.astype("int64")
ncs       = df["node_count"].values.astype("int64")

concurrent_jobs  = []
concurrent_nodes = []
for ts_ns in sample_ts_ns:
    act = (starts_ns <= ts_ns) & (ends_ns > ts_ns)
    concurrent_jobs.append(int(act.sum()))
    concurrent_nodes.append(int(ncs[act].sum()))

cj = np.array(concurrent_jobs)
cn = np.array(concurrent_nodes)

print(f"  Concurrent jobs:  median={float(np.median(cj)):.1f} p90={float(np.percentile(cj,90)):.1f} p99={float(np.percentile(cj,99)):.1f} max={int(cj.max())}")
print(f"  Concurrent nodes: median={float(np.median(cn)):.1f} p90={float(np.percentile(cn,90)):.1f} p99={float(np.percentile(cn,99)):.1f} max={int(cn.max())}")

# Patch the JSON
with open(OUT_JSON) as fh:
    data = json.load(fh)

data["support"]["concurrent_observed_jobs_at_event_ts"] = {
    "n_sample": n_sample,
    "median":   float(np.median(cj)),
    "p90":      float(np.percentile(cj, 90)),
    "p99":      float(np.percentile(cj, 99)),
    "max":      int(cj.max()),
    "note": "Computed from unique event timestamps (start/end of qualifying jobs) sampled uniformly"
}
data["support"]["concurrent_observed_nodes_at_event_ts"] = {
    "n_sample": n_sample,
    "median":   float(np.median(cn)),
    "p90":      float(np.percentile(cn, 90)),
    "p99":      float(np.percentile(cn, 99)),
    "max":      int(cn.max()),
    "note": "Computed from unique event timestamps (start/end of qualifying jobs) sampled uniformly"
}

with open(OUT_JSON, "w", encoding="utf-8") as fh:
    json.dump(data, fh, indent=2, ensure_ascii=False)

print(f"Patched: {OUT_JSON}")
