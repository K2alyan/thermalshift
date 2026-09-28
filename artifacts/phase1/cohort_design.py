"""
Phase 1 cohort design — revised.
Strategy: 2,000 nodes (stratified across all 77 racks) with a
stratified job sample (3 jobs per quarter per node), preferring
small-to-medium jobs. This avoids pulling multi-thousand-node jobs
that would dominate download size while delivering nothing extra for
the fingerprint analysis.
Outputs: cohort_manifest.csv, cohort_job_list.csv (overwrites prior versions)
"""
# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.



import os
import pyarrow.parquet as pq
import pandas as pd
import numpy as np
import re, json
from pathlib import Path

JOB_INFO = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "frontier-completed-job-info.parquet"
OUT_DIR  = Path(__file__).parent

np.random.seed(42)

# ── 1. Load job-info ──────────────────────────────────────────────────────────
print("Loading job-info...", flush=True)
ji = pq.read_table(JOB_INFO).to_pandas()
for col in ["start_time", "end_time"]:
    ji[col] = pd.to_datetime(ji[col], utc=True, errors="coerce")
ji["quarter"] = ji["start_time"].dt.to_period("Q").astype(str)  # e.g. "2024Q1"
print(f"  {len(ji):,} jobs loaded", flush=True)

# ── 2. Build node-job index efficiently ───────────────────────────────────────
print("Building node->job index...", flush=True)

def to_py_list(val):
    if val is None: return []
    if isinstance(val, (list, np.ndarray)): return list(val)
    try:
        import ast; return ast.literal_eval(str(val))
    except: return []

# Lightweight explode: just host→job_idx, quarter, node_count, run_time,
# project_prefix, completion_state, start_time, xname
meta_cols = ["job_idx", "quarter", "node_count", "run_time",
             "project_prefix", "completion_state", "start_time"]
ji_meta = ji[meta_cols].copy()

ji["_pairs"] = ji.apply(
    lambda r: list(zip(to_py_list(r["host_list"]), to_py_list(r["node_list"])))
              if len(to_py_list(r["host_list"])) == len(to_py_list(r["node_list"]))
              else [(h, None) for h in to_py_list(r["host_list"])],
    axis=1
)

pairs_exp = ji[meta_cols + ["_pairs"]].copy()
pairs_exp = pairs_exp[pairs_exp["_pairs"].apply(len) > 0].explode("_pairs")
pairs_exp["hostname"] = pairs_exp["_pairs"].apply(lambda p: p[0])
pairs_exp["xname"]    = pairs_exp["_pairs"].apply(lambda p: p[1])
pairs_exp = pairs_exp.drop(columns=["_pairs"]).reset_index(drop=True)

print(f"  {len(pairs_exp):,} node-job pairs", flush=True)
print(f"  {pairs_exp['hostname'].nunique():,} unique nodes", flush=True)

# ── 3. Parse topology for all nodes ───────────────────────────────────────────
def parse_xname(xname):
    if not xname or not isinstance(xname, str): return {}
    m = re.match(r"x(\d+)c(\d+)s(\d+)b(\d+)n(\d+)", xname)
    if not m: return {}
    r, c, s, b, n = [int(x) for x in m.groups()]
    return {"rack": r, "chassis": c, "slot": s, "board": b}

node_xname = pairs_exp.groupby("hostname")["xname"].first().reset_index()
topo = node_xname["xname"].apply(parse_xname)
node_xname["rack"]    = topo.apply(lambda d: d.get("rack"))
node_xname["chassis"] = topo.apply(lambda d: d.get("chassis"))
node_xname["slot"]    = topo.apply(lambda d: d.get("slot"))
node_xname["board"]   = topo.apply(lambda d: d.get("board"))

# Per-node summary for selection scoring
per_node = pairs_exp.groupby("hostname").agg(
    n_jobs=("job_idx", "nunique"),
    n_projects=("project_prefix", "nunique"),
    first_start=("start_time", "min"),
    last_end=("start_time", "max"),
).reset_index()
per_node = per_node.merge(node_xname, on="hostname", how="left")
per_node["span_days"] = (per_node["last_end"] - per_node["first_start"]).dt.total_seconds() / 86400
per_node = per_node.dropna(subset=["rack"])

print(f"  Nodes with parsed xname: {len(per_node):,}", flush=True)
print(f"  Racks: {per_node['rack'].nunique()}", flush=True)

# ── 4. Select 2,000 nodes stratified by rack ─────────────────────────────────
TARGET_NODES  = 2000
N_RACKS       = int(per_node["rack"].nunique())
nodes_per_rack = max(1, -(-TARGET_NODES // N_RACKS))  # ceiling division

# Within each rack, pick nodes by job count (all are high, so pick top)
per_node_sorted = per_node.sort_values("n_jobs", ascending=False)
cohort_nodes_list = (
    per_node_sorted
    .groupby("rack", group_keys=False)
    .apply(lambda g: g.head(nodes_per_rack), include_groups=True)
)
# Trim to target
cohort_nodes = cohort_nodes_list.head(TARGET_NODES).copy()
cohort_hostnames = set(cohort_nodes["hostname"])
print(f"\nCohort nodes selected: {len(cohort_nodes):,}", flush=True)
print(f"  Racks covered: {cohort_nodes['rack'].nunique()}", flush=True)
print(f"  Chassis covered: {cohort_nodes['chassis'].nunique()}", flush=True)

# ── 5. Stratified job sample per node ────────────────────────────────────────
# For each cohort node, sample up to N_PER_QUARTER jobs from each quarter.
# Prefer: COMPLETED, then diverse project_prefix, then small node_count.
N_PER_QUARTER = 4        # slight increase to compensate for short-job filter
MAX_NODE_COUNT = 256     # skip jobs larger than this to control file size
MIN_RUN_TIME_S = 600     # at least 10 temperature readings at 60s bins

print("\nBuilding stratified job sample per node...", flush=True)

# Add run_time from ji into pairs_exp (join once)
pairs_exp = pairs_exp.merge(
    ji[["job_idx", "run_time", "date_dir"]].rename(columns={"run_time": "run_time_s"}),
    on="job_idx", how="left"
)

# Filter pairs to cohort nodes, reasonable-size and sufficient-length jobs
cohort_pairs = pairs_exp[
    pairs_exp["hostname"].isin(cohort_hostnames) &
    (pairs_exp["node_count"].fillna(9999) <= MAX_NODE_COUNT) &
    (pairs_exp["run_time_s"].fillna(0) >= MIN_RUN_TIME_S)
].copy()

# Rank jobs within each (node, quarter) by priority:
# 1. COMPLETED first
# 2. Shortest run_time >= MIN_RUN_TIME (control file size while ensuring enough readings)
# 3. Then by node_count ASC
cohort_pairs["completed"] = (cohort_pairs["completion_state"] == "COMPLETED").astype(int)
cohort_pairs = cohort_pairs.sort_values(
    ["hostname", "quarter", "completed", "run_time_s", "node_count"],
    ascending=[True, True, False, True, True]   # completed DESC, run_time ASC, nc ASC
)

# Sample N_PER_QUARTER per (node, quarter)
sampled = (
    cohort_pairs
    .groupby(["hostname", "quarter"], group_keys=False)
    .apply(lambda g: g.head(N_PER_QUARTER), include_groups=True)
)

unique_jobs = sampled["job_idx"].unique()
print(f"  Node-quarter-job triples: {len(sampled):,}", flush=True)
print(f"  Unique jobs (after dedup): {len(unique_jobs):,}", flush=True)

# Jobs per node in the sample
jobs_per_node_sample = sampled.groupby("hostname")["job_idx"].nunique()
print(f"  Jobs/node in sample: min={jobs_per_node_sample.min()}, "
      f"median={jobs_per_node_sample.median():.0f}, max={jobs_per_node_sample.max()}", flush=True)

# ── 6. Estimate download size ─────────────────────────────────────────────────
# Calibration from 100-job sample: 64.1 MB / 12,056,400 node-seconds = 5.32 bytes/node-second
BYTES_PER_NODE_SECOND = 64.1e6 / (3349 * 3600)

# For each unique job, get its actual node_count and run_time
job_meta = ji.set_index("job_idx")[["node_count", "run_time"]]
selected_job_meta = job_meta.loc[unique_jobs].copy()
selected_job_meta["node_count"] = selected_job_meta["node_count"].fillna(4)
selected_job_meta["run_time"]   = selected_job_meta["run_time"].fillna(3600)
node_seconds = (selected_job_meta["node_count"] * selected_job_meta["run_time"]).sum()
est_gb = node_seconds * BYTES_PER_NODE_SECOND / 1e9

print(f"\n=== Download size estimate ===", flush=True)
print(f"  Unique jobs: {len(unique_jobs):,}", flush=True)
print(f"  Total node-hours: {node_seconds/3600:,.0f}", flush=True)
print(f"  Estimated download (cleaned temp+power): {est_gb:.1f} GB", flush=True)

# Node_count distribution of selected jobs
nc_selected = selected_job_meta["node_count"]
print(f"  Selected job node_count: median={nc_selected.median():.0f}, "
      f"p90={np.percentile(nc_selected, 90):.0f}, max={nc_selected.max():.0f}", flush=True)

# ── 7. Coverage checks ────────────────────────────────────────────────────────
print("\n=== Cohort coverage ===", flush=True)

quarters_available = sorted(sampled["quarter"].unique())
print(f"  Quarters covered: {len(quarters_available)} ({quarters_available[0]} to {quarters_available[-1]})", flush=True)

proj_per_node = sampled.groupby("hostname")["project_prefix"].nunique()
print(f"  Project_prefix per node in sample: min={proj_per_node.min()}, "
      f"median={proj_per_node.median():.0f}, max={proj_per_node.max()}", flush=True)

# Fraction of cohort nodes with >=3 quarters covered
quarters_per_node = sampled.groupby("hostname")["quarter"].nunique()
print(f"  Nodes with >=4 quarters: {(quarters_per_node>=4).sum():,}", flush=True)
print(f"  Nodes with >=6 quarters: {(quarters_per_node>=6).sum():,}", flush=True)
print(f"  Nodes with >=8 quarters: {(quarters_per_node>=8).sum():,}", flush=True)

# ── 8. Save cohort manifest ───────────────────────────────────────────────────
manifest = cohort_nodes[[
    "hostname", "xname", "rack", "chassis", "slot", "board",
    "n_jobs", "n_projects", "first_start", "last_end", "span_days"
]].copy().sort_values("n_jobs", ascending=False).reset_index(drop=True)

manifest.to_csv(OUT_DIR / "cohort_manifest.csv", index=False)
print(f"\nSaved cohort_manifest.csv  ({len(manifest):,} nodes)", flush=True)

# Job list: job_idx + date_dir (for Globus path construction) + size metadata
ji_jobmeta = ji.set_index("job_idx")[["date_dir", "node_count", "run_time"]]
job_list = ji_jobmeta.loc[unique_jobs].copy().reset_index()
job_list = job_list.rename(columns={"run_time": "run_time_s"})
job_list["globus_path"] = (
    "/gen101/world-shared/doi-data/OLCF/202609/10.13139_OLCF_3013979/"
    "frontier-job-centric-telemetry-dataset/job-telemetry/"
    + job_list["date_dir"].astype(str) + "/" + job_list["job_idx"].astype(str) + "/"
)
job_list.to_csv(OUT_DIR / "cohort_job_list.csv", index=False)
print(f"Saved cohort_job_list.csv  ({len(job_list):,} jobs)", flush=True)

# ── 9. Save updated stats ─────────────────────────────────────────────────────
with open(OUT_DIR / "fleet_stats.json") as f:
    fs = json.load(f)

fs["cohort"] = {
    "strategy": "stratified_job_sample",
    "n_nodes": len(manifest),
    "n_jobs": len(unique_jobs),
    "n_per_quarter_per_node": N_PER_QUARTER,
    "max_node_count_per_job": MAX_NODE_COUNT,
    "min_run_time_s": MIN_RUN_TIME_S,
    "min_jobs_per_node_in_sample": int(jobs_per_node_sample.min()),
    "median_jobs_per_node_in_sample": float(jobs_per_node_sample.median()),
    "max_jobs_per_node_in_sample": int(jobs_per_node_sample.max()),
    "quarters_covered": len(quarters_available),
    "n_racks": int(cohort_nodes["rack"].nunique()),
    "estimated_download_gb": round(est_gb, 2),
}
with open(OUT_DIR / "fleet_stats.json", "w") as f:
    json.dump(fs, f, indent=2)
print("Updated fleet_stats.json", flush=True)

print("\n=== DONE ===", flush=True)
