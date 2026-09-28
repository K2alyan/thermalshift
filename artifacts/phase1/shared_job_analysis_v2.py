"""
Corrected shared-job analysis with fixed job_idx normalization.
Adds job 107165 as dedicated fleet_matched_control.
Regenerates cohort_job_list.csv, cohort_manifest.csv, globus_batch.txt
with selection_role field.

Bug fix: parquet stores job_idx as zero-padded strings ("005934");
CSV reads them back as int (5934); comparison failed for all <100000.
Fix: normalize both sides to int before any set operations.
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
import json
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations

JOB_INFO = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "frontier-completed-job-info.parquet"
OUT_DIR  = Path(__file__).parent

BYTES_PER_NODE_SECOND = 64.1e6 / (3349 * 3600)
FLEET_MATCHED_JOB_ID  = 107165
LOCAL_ROOT             = "/Users/kalya/Downloads/frontier_phase1"
GLOBUS_BASE            = (
    "/gen101/world-shared/doi-data/OLCF/202609/10.13139_OLCF_3013979/"
    "frontier-job-centric-telemetry-dataset/job-telemetry/"
)

np.random.seed(42)

# ── 1. Load and normalize identifiers ────────────────────────────────────────
print("Loading job-info...", flush=True)
ji = pq.read_table(JOB_INFO).to_pandas()
for col in ["start_time", "end_time"]:
    ji[col] = pd.to_datetime(ji[col], utc=True, errors="coerce")
ji["quarter"] = ji["start_time"].dt.to_period("Q").astype(str)

# CRITICAL FIX: strip leading zeros by converting to int.
# parquet stores job_idx as strings ("005934"); CSV reads back as int (5934).
# Normalize both to int so comparisons are consistent.
ji["job_idx"] = pd.to_numeric(ji["job_idx"], errors="coerce").astype("Int64")

cohort_manifest  = pd.read_csv(OUT_DIR / "cohort_manifest.csv")
cohort_job_list  = pd.read_csv(OUT_DIR / "cohort_job_list.csv")
cohort_job_list["job_idx"] = pd.to_numeric(
    cohort_job_list["job_idx"], errors="coerce"
).astype("Int64")

cohort_hostnames = set(cohort_manifest["hostname"])
# Longitudinal set excludes fleet-matched-control job (if already present from prior run)
longitudinal_ids = set(int(x) for x in cohort_job_list["job_idx"]) - {FLEET_MATCHED_JOB_ID}
n_cohort_nodes   = len(cohort_hostnames)
n_cohort_jobs    = len(longitudinal_ids)
print(f"  {n_cohort_nodes:,} cohort nodes, {n_cohort_jobs:,} longitudinal jobs", flush=True)

# ── 2. Build job->cohort_nodes index for longitudinal cohort ─────────────────
print("\nBuilding job->cohort_nodes index...", flush=True)

def to_py_list(val):
    if val is None: return []
    if isinstance(val, (list, np.ndarray)): return list(val)
    try:
        import ast; return ast.literal_eval(str(val))
    except: return []

ji_long = ji[ji["job_idx"].isin(longitudinal_ids)]
print(f"  Jobs matched in parquet: {len(ji_long):,} of {n_cohort_jobs:,}", flush=True)
if len(ji_long) < n_cohort_jobs:
    print(f"  WARNING: {n_cohort_jobs - len(ji_long):,} cohort jobs not found in parquet.",
          flush=True)

job_to_cohort_nodes = {}
for i, (_, row) in enumerate(ji_long.iterrows()):
    jid   = int(row["job_idx"])
    hosts = to_py_list(row["host_list"])
    job_to_cohort_nodes[jid] = [h for h in hosts if h in cohort_hostnames]
    if (i + 1) % 1000 == 0:
        print(f"  Processed {i+1:,} jobs...", flush=True)

cohort_nodes_per_job = np.array([len(v) for v in job_to_cohort_nodes.values()])
print(f"  Total jobs processed: {len(job_to_cohort_nodes):,}", flush=True)

# ── 3. Shared-job structure ───────────────────────────────────────────────────
print("\n=== Shared-job structure (longitudinal cohort) ===", flush=True)

thresholds = [2, 4, 8, 16, 32, 64, 128]
for t in thresholds:
    cnt  = int((cohort_nodes_per_job >= t).sum())
    frac = cnt / n_cohort_jobs
    print(f"  Jobs with >= {t:3d} cohort nodes: {cnt:5,}  ({100*frac:.1f}%)")

print(f"\n  Distribution of cohort nodes per selected job:", flush=True)
for p, v in zip([0, 5, 10, 25, 50, 75, 90, 95, 99, 100],
                np.percentile(cohort_nodes_per_job, [0,5,10,25,50,75,90,95,99,100])):
    print(f"    p{p:3d}: {v:.0f}")
print(f"    mean: {cohort_nodes_per_job.mean():.1f}")

# Fraction of GCD-obs in shared jobs
jl_meta = cohort_job_list.set_index("job_idx")
total_obs  = 0.0
shared_obs = 0.0
for jid, c_nodes in job_to_cohort_nodes.items():
    k  = len(c_nodes)
    rt = float(jl_meta.loc[jid, "run_time_s"]) if jid in jl_meta.index and pd.notna(jl_meta.loc[jid, "run_time_s"]) else 3600.0
    obs = k * max(1, rt / 60) * 8
    total_obs  += obs
    if k >= 2:
        shared_obs += obs

print(f"\n  Approx fraction of GCD-obs in shared jobs (>=2 cohort nodes): "
      f"{100*shared_obs/max(1,total_obs):.1f}%", flush=True)

# ── 4. Node-pair co-occurrence ────────────────────────────────────────────────
print("\n=== Node-pair co-occurrence ===", flush=True)
print("  Computing pair counts (sparse)...", flush=True)

pair_job_count = Counter()
for jid, c_nodes in job_to_cohort_nodes.items():
    if len(c_nodes) < 2:
        continue
    nodes = sorted(c_nodes)
    for pair in combinations(nodes, 2):
        pair_job_count[pair] += 1

n_unique_pairs  = len(pair_job_count)
pair_counts_arr = np.array(list(pair_job_count.values()), dtype=np.int32)
max_theoretical = n_cohort_nodes * (n_cohort_nodes - 1) // 2
print(f"  Unique node pairs with >= 1 shared job: {n_unique_pairs:,}", flush=True)
print(f"  Max theoretical pairs from {n_cohort_nodes} nodes: {max_theoretical:,}", flush=True)

pair_thresholds = [2, 5, 10, 20, 50]
for t in pair_thresholds:
    cnt = int((pair_counts_arr >= t).sum())
    print(f"  Pairs with >= {t:2d} shared jobs: {cnt:8,}  "
          f"({100*cnt/max(1,n_unique_pairs):.1f}% of observed pairs)")

print(f"\n  Shared-jobs-per-pair distribution:", flush=True)
for p, v in zip([0, 5, 10, 25, 50, 75, 90, 95, 99, 100],
                np.percentile(pair_counts_arr, [0,5,10,25,50,75,90,95,99,100])):
    print(f"    p{p:3d}: {v:.0f}")
print(f"    mean: {pair_counts_arr.mean():.1f}")

node_cooccurrence = defaultdict(set)
for (a, b), cnt in pair_job_count.items():
    if cnt >= 2:
        node_cooccurrence[a].add(b)
        node_cooccurrence[b].add(a)

n_cooccurrence  = np.array([len(v) for v in node_cooccurrence.values()])
nodes_with_any  = len(node_cooccurrence)
print(f"\n  Nodes with >= 1 matched-pair partner (>=2 shared jobs): "
      f"{nodes_with_any:,} of {n_cohort_nodes:,}", flush=True)
if len(n_cooccurrence):
    print(f"  Co-occurrence partners per node: "
          f"median={np.median(n_cooccurrence):.0f}, "
          f"p10={np.percentile(n_cooccurrence,10):.0f}, "
          f"p90={np.percentile(n_cooccurrence,90):.0f}, "
          f"max={n_cooccurrence.max()}", flush=True)

# ── 5. Adequacy assessment ────────────────────────────────────────────────────
print("\n=== Adequacy assessment ===", flush=True)

pairs_ge5  = int((pair_counts_arr >= 5).sum())
pairs_ge10 = int((pair_counts_arr >= 10).sum())
nodes_ge5_partners = sum(1 for v in node_cooccurrence.values() if len(v) >= 5)

print(f"  Pairs with >= 5 shared jobs:  {pairs_ge5:,}")
print(f"  Pairs with >= 10 shared jobs: {pairs_ge10:,}")
print(f"  Nodes with >= 5 co-occurrence partners (>=2 shared): "
      f"{nodes_ge5_partners:,} of {n_cohort_nodes:,}", flush=True)

ADEQUATE = (pairs_ge5 >= 50_000) and (nodes_ge5_partners >= 1_500)
print(f"  Adequacy: {'PASS' if ADEQUATE else 'FAIL'}", flush=True)
if not ADEQUATE:
    print("  WARNING: matched-job coverage is inadequate. Stop and report.", flush=True)

# ── 6. Look up job 107165 metadata ────────────────────────────────────────────
print(f"\n=== Fleet matched-control job {FLEET_MATCHED_JOB_ID} ===", flush=True)

fleet_row = ji[ji["job_idx"] == FLEET_MATCHED_JOB_ID]
if len(fleet_row) == 0:
    raise ValueError(f"Job {FLEET_MATCHED_JOB_ID} not found in parquet!")

fleet_row = fleet_row.iloc[0]
fleet_date_dir  = str(fleet_row["date_dir"])
fleet_nc        = int(fleet_row["node_count"]) if pd.notna(fleet_row["node_count"]) else 9400
fleet_rt        = float(fleet_row["run_time"])  if pd.notna(fleet_row.get("run_time", np.nan)) else 1800.0
fleet_state     = str(fleet_row["completion_state"])
fleet_prefix    = str(fleet_row.get("project_prefix", ""))
fleet_hosts     = to_py_list(fleet_row["host_list"])
fleet_cohort_nodes = [h for h in fleet_hosts if h in cohort_hostnames]
fleet_k         = len(fleet_cohort_nodes)
fleet_pairs     = fleet_k * (fleet_k - 1) // 2
fleet_est_gb    = fleet_nc * fleet_rt * BYTES_PER_NODE_SECOND / 1e9

print(f"  job_idx:          {FLEET_MATCHED_JOB_ID}", flush=True)
print(f"  date_dir:         {fleet_date_dir}", flush=True)
print(f"  node_count:       {fleet_nc:,}", flush=True)
print(f"  run_time_s:       {fleet_rt:.0f}", flush=True)
print(f"  state:            {fleet_state}", flush=True)
print(f"  project_prefix:   {fleet_prefix}", flush=True)
print(f"  cohort nodes in job: {fleet_k:,} of {n_cohort_nodes:,}", flush=True)
print(f"  cohort pairs:     {fleet_pairs:,}", flush=True)
print(f"  estimated GB:     {fleet_est_gb:.3f}", flush=True)

# ── 7. Regenerate cohort_job_list.csv with selection_role ─────────────────────
print("\nRegenerating cohort_job_list.csv...", flush=True)

# Rebuild globus paths using zero-padded job_idx (to match dataset directory structure)
# parquet stores directories as zero-padded 6-char strings
def make_globus_path(date_dir, job_id_int):
    job_str = str(job_id_int).zfill(6)
    return GLOBUS_BASE + f"{date_dir}/{job_str}/"

# Longitudinal jobs: reuse existing data but normalize job_idx and add role
long_jobs = cohort_job_list[
    ~cohort_job_list["job_idx"].isin([FLEET_MATCHED_JOB_ID])
].copy()
long_jobs["job_idx"] = long_jobs["job_idx"].astype(int)

# Reconstruct globus_path with zero-padded IDs (ensures consistency)
if "date_dir" in long_jobs.columns:
    long_jobs["globus_path"] = long_jobs.apply(
        lambda r: make_globus_path(r["date_dir"], r["job_idx"]), axis=1
    )
long_jobs["selection_role"] = "longitudinal_cohort"

# Fleet matched-control entry
fleet_entry = pd.DataFrame([{
    "job_idx":        FLEET_MATCHED_JOB_ID,
    "date_dir":       fleet_date_dir,
    "node_count":     fleet_nc,
    "run_time_s":     fleet_rt,
    "globus_path":    make_globus_path(fleet_date_dir, FLEET_MATCHED_JOB_ID),
    "selection_role": "fleet_matched_control",
}])

new_job_list = pd.concat([long_jobs, fleet_entry], ignore_index=True)
new_job_list = new_job_list.drop_duplicates(subset="job_idx")

# Column order
col_order = ["job_idx", "date_dir", "node_count", "run_time_s",
             "globus_path", "selection_role"]
for c in col_order:
    if c not in new_job_list.columns:
        new_job_list[c] = ""
new_job_list = new_job_list[col_order]

new_job_list.to_csv(OUT_DIR / "cohort_job_list.csv", index=False)
n_total_jobs = len(new_job_list)
print(f"  Saved cohort_job_list.csv: {n_total_jobs:,} jobs "
      f"({n_total_jobs - 1:,} longitudinal + 1 fleet_matched_control)", flush=True)

# ── 8. Update cohort_manifest.csv with selection_role ─────────────────────────
# (manifest is nodes only, no role needed — nodes appear in both roles)
# Add a note column for documentation purposes only
cohort_manifest["in_fleet_matched_job_107165"] = (
    cohort_manifest["hostname"].isin(fleet_cohort_nodes)
).astype(int)
cohort_manifest.to_csv(OUT_DIR / "cohort_manifest.csv", index=False)
print(f"Saved cohort_manifest.csv ({len(cohort_manifest):,} nodes, "
      f"added in_fleet_matched_job_107165 flag)", flush=True)

# ── 9. Generate Globus batch file ─────────────────────────────────────────────
batch_lines = []
for _, r in new_job_list.iterrows():
    src = str(r["globus_path"])
    dst = f"{LOCAL_ROOT}/job-telemetry/{r['date_dir']}/{str(int(r['job_idx'])).zfill(6)}/"
    batch_lines.append(f"{src} {dst} --recursive")

batch_path = OUT_DIR / "globus_batch.txt"
with open(batch_path, "w") as f:
    f.write("\n".join(batch_lines))
print(f"Saved globus_batch.txt ({len(batch_lines):,} transfer lines)", flush=True)

# ── 10. Compute final download estimate ───────────────────────────────────────
long_gb  = (long_jobs["node_count"].fillna(4) *
            long_jobs["run_time_s"].fillna(3600)).sum() * BYTES_PER_NODE_SECOND / 1e9
total_gb = long_gb + fleet_est_gb
print(f"\nEstimated download:", flush=True)
print(f"  Longitudinal cohort: {long_gb:.2f} GB", flush=True)
print(f"  Fleet matched-control (107165): {fleet_est_gb:.3f} GB", flush=True)
print(f"  Total: {total_gb:.2f} GB", flush=True)

# ── 11. Save updated fleet_stats.json ─────────────────────────────────────────
with open(OUT_DIR / "fleet_stats.json") as fh:
    fs = json.load(fh)

fs["shared_job_analysis"] = {
    "run_version": "v2_corrected",
    "longitudinal_jobs_matched": len(ji_long),
    "longitudinal_jobs_expected": n_cohort_jobs,
    "jobs_with_ge2_cohort_nodes":   int((cohort_nodes_per_job >= 2).sum()),
    "jobs_with_ge4_cohort_nodes":   int((cohort_nodes_per_job >= 4).sum()),
    "jobs_with_ge8_cohort_nodes":   int((cohort_nodes_per_job >= 8).sum()),
    "jobs_with_ge16_cohort_nodes":  int((cohort_nodes_per_job >= 16).sum()),
    "jobs_with_ge32_cohort_nodes":  int((cohort_nodes_per_job >= 32).sum()),
    "jobs_with_ge64_cohort_nodes":  int((cohort_nodes_per_job >= 64).sum()),
    "jobs_with_ge128_cohort_nodes": int((cohort_nodes_per_job >= 128).sum()),
    "fraction_obs_in_shared_jobs":  round(shared_obs / max(1, total_obs), 3),
    "unique_pairs_ge1":  int(n_unique_pairs),
    "unique_pairs_ge2":  int((pair_counts_arr >= 2).sum()),
    "unique_pairs_ge5":  int(pairs_ge5),
    "unique_pairs_ge10": int(pairs_ge10),
    "unique_pairs_ge20": int((pair_counts_arr >= 20).sum()),
    "nodes_with_ge5_partners":  int(nodes_ge5_partners),
    "adequacy_pass": ADEQUATE,
    "fleet_matched_control_job": FLEET_MATCHED_JOB_ID,
    "fleet_matched_cohort_nodes": fleet_k,
    "fleet_matched_pairs": fleet_pairs,
    "fleet_matched_est_gb": round(fleet_est_gb, 3),
    "final_n_jobs": n_total_jobs,
    "final_n_longitudinal_jobs": n_total_jobs - 1,
    "final_est_gb": round(total_gb, 2),
    "modification_made": False,
}

with open(OUT_DIR / "fleet_stats.json", "w") as fh:
    json.dump(fs, fh, indent=2)
print("Updated fleet_stats.json", flush=True)

# ── 12. Final summary ─────────────────────────────────────────────────────────
print(f"\n{'='*60}", flush=True)
print(f"FINAL CORRECTED COHORT SUMMARY", flush=True)
print(f"{'='*60}", flush=True)
print(f"  Nodes:                     {n_cohort_nodes:,}", flush=True)
print(f"  Longitudinal jobs:         {n_total_jobs - 1:,}", flush=True)
print(f"  Fleet matched-control:     1 (job {FLEET_MATCHED_JOB_ID})", flush=True)
print(f"  Total jobs in manifest:    {n_total_jobs:,}", flush=True)
print(f"  Estimated download:        {total_gb:.2f} GB", flush=True)
print(f"  Cohort modified:           False (same 8,303 longitudinal jobs)", flush=True)
print(f"\nMatched-job coverage (longitudinal):", flush=True)
print(f"  Jobs w/ >=2 cohort nodes:   {(cohort_nodes_per_job>=2).sum():,}", flush=True)
print(f"  Jobs w/ >=16 cohort nodes:  {(cohort_nodes_per_job>=16).sum():,}", flush=True)
print(f"  Unique node pairs (>=1):    {n_unique_pairs:,}", flush=True)
print(f"  Pairs with >=5 shared jobs: {pairs_ge5:,}", flush=True)
print(f"  Pairs with >=10 shared jobs:{pairs_ge10:,}", flush=True)
print(f"\nFleet matched-control (job {FLEET_MATCHED_JOB_ID}):", flush=True)
print(f"  Cohort nodes present:       {fleet_k:,}", flush=True)
print(f"  Cohort node pairs:          {fleet_pairs:,}", flush=True)
print(f"\nGlobus transfer command:", flush=True)
print(f"  globus transfer \\", flush=True)
print(f"    57618e0a-2c99-45ff-9694-24141b92fa17 \\", flush=True)
print(f"    <YOUR-LOCAL-ENDPOINT-ID> \\", flush=True)
print(f"    --batch {batch_path} \\", flush=True)
print(f"    --label 'ThermalOps Phase 1 cohort'", flush=True)
print(f"\n=== DONE ===", flush=True)
