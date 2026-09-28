"""
Shared-job structure analysis and matched-job cohort evaluation.
Reports shared-job coverage, node-pair co-occurrence, and recommends
whether/how to modify the cohort to improve matched-comparison density.
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
import re
from pathlib import Path
from collections import Counter, defaultdict
from itertools import combinations

JOB_INFO = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "frontier-completed-job-info.parquet"
OUT_DIR  = Path(__file__).parent

np.random.seed(42)

# ── 1. Load job-info and current cohort ───────────────────────────────────────
print("Loading job-info...", flush=True)
ji = pq.read_table(JOB_INFO).to_pandas()
for col in ["start_time", "end_time"]:
    ji[col] = pd.to_datetime(ji[col], utc=True, errors="coerce")
ji["quarter"] = ji["start_time"].dt.to_period("Q").astype(str)
ji_idx = ji.set_index("job_idx")

cohort_manifest = pd.read_csv(OUT_DIR / "cohort_manifest.csv")
cohort_job_list = pd.read_csv(OUT_DIR / "cohort_job_list.csv")

cohort_hostnames  = set(cohort_manifest["hostname"])
cohort_job_ids    = set(cohort_job_list["job_idx"].astype(str))
n_cohort_nodes    = len(cohort_hostnames)
n_cohort_jobs     = len(cohort_job_ids)
print(f"  {n_cohort_nodes:,} cohort nodes, {n_cohort_jobs:,} cohort jobs", flush=True)

# ── 2. Build cohort-node list for each selected job ───────────────────────────
print("\nBuilding job->cohort_nodes index...", flush=True)

def to_py_list(val):
    if val is None: return []
    if isinstance(val, (list, np.ndarray)): return list(val)
    try:
        import ast; return ast.literal_eval(str(val))
    except: return []

# For each selected job, count how many cohort nodes it contains
job_to_cohort_nodes = {}  # job_idx -> list of cohort hostnames
for _, row in ji[ji["job_idx"].astype(str).isin(cohort_job_ids)].iterrows():
    hosts = to_py_list(row["host_list"])
    cohort_in_job = [h for h in hosts if h in cohort_hostnames]
    job_to_cohort_nodes[str(row["job_idx"])] = cohort_in_job

# Cohort-nodes-per-job distribution
cohort_nodes_per_job = np.array([len(v) for v in job_to_cohort_nodes.values()])
print(f"  Jobs processed: {len(job_to_cohort_nodes):,}", flush=True)

# ── 3. Shared-job structure statistics ────────────────────────────────────────
print("\n=== Shared-job structure ===", flush=True)

thresholds = [2, 4, 8, 16, 32, 64, 128]
for t in thresholds:
    cnt  = (cohort_nodes_per_job >= t).sum()
    frac = cnt / n_cohort_jobs
    print(f"  Jobs with >= {t:3d} cohort nodes: {cnt:5,}  ({100*frac:.1f}%)")

print(f"\n  Distribution of cohort nodes per selected job:")
for p, v in zip([0, 5, 10, 25, 50, 75, 90, 95, 99, 100],
                np.percentile(cohort_nodes_per_job, [0,5,10,25,50,75,90,95,99,100])):
    print(f"    p{p:3d}: {v:.0f}")
print(f"    mean: {cohort_nodes_per_job.mean():.1f}")

# Fraction of observations (node×timestep) in shared jobs
# Approx: each node contributes run_time/60 timesteps × 8 GCDs per job
jl_meta = cohort_job_list.set_index("job_idx")

total_obs     = 0.0
shared_obs    = 0.0
for jid, cohort_nodes in job_to_cohort_nodes.items():
    k     = len(cohort_nodes)
    if jid in jl_meta.index:
        rt = jl_meta.loc[jid, "run_time_s"]
        rt = rt if pd.notna(rt) else 3600
    else:
        rt = 3600
    timesteps = max(1, rt / 60)
    obs = k * timesteps * 8          # per-node: 8 GCDs × timesteps
    total_obs  += obs
    if k >= 2:
        shared_obs += obs

print(f"\n  Approx fraction of GCD-obs in shared jobs (>=2 cohort nodes): "
      f"{100*shared_obs/max(1,total_obs):.1f}%", flush=True)

# ── 4. Node-pair co-occurrence (efficient sparse approach) ────────────────────
print("\n=== Node-pair co-occurrence ===", flush=True)
print("  Computing pair counts (sparse)...", flush=True)

pair_job_count = Counter()
for jid, cohort_nodes in job_to_cohort_nodes.items():
    k = len(cohort_nodes)
    if k < 2:
        continue
    nodes = sorted(cohort_nodes)
    for pair in combinations(nodes, 2):
        pair_job_count[pair] += 1

n_unique_pairs = len(pair_job_count)
pair_counts_arr = np.array(list(pair_job_count.values()), dtype=np.int32)
print(f"  Unique node pairs with >= 1 shared job: {n_unique_pairs:,}", flush=True)
print(f"  Max theoretical pairs from {n_cohort_nodes} nodes: "
      f"{n_cohort_nodes*(n_cohort_nodes-1)//2:,}", flush=True)

pair_thresholds = [2, 5, 10, 20, 50]
for t in pair_thresholds:
    cnt = (pair_counts_arr >= t).sum()
    print(f"  Pairs with >= {t:2d} shared jobs: {cnt:8,}  "
          f"({100*cnt/max(1,n_unique_pairs):.1f}% of observed pairs)")

print(f"\n  Shared-jobs-per-pair distribution:")
for p, v in zip([0, 5, 10, 25, 50, 75, 90, 95, 99, 100],
                np.percentile(pair_counts_arr, [0,5,10,25,50,75,90,95,99,100])):
    print(f"    p{p:3d}: {v:.0f}")
print(f"    mean: {pair_counts_arr.mean():.1f}")

# Per-node: how many unique co-nodes does each cohort node share a job with?
node_cooccurrence = defaultdict(set)
for (a, b), cnt in pair_job_count.items():
    if cnt >= 2:     # only count meaningful co-occurrence
        node_cooccurrence[a].add(b)
        node_cooccurrence[b].add(a)

n_cooccurrence = np.array([len(v) for v in node_cooccurrence.values()])
nodes_with_any = len(node_cooccurrence)
print(f"\n  Nodes with >= 1 matched-pair partner (>=2 shared jobs): "
      f"{nodes_with_any:,} of {n_cohort_nodes:,}")
if len(n_cooccurrence):
    print(f"  Co-occurrence partners per node: "
          f"median={np.median(n_cooccurrence):.0f}, "
          f"p10={np.percentile(n_cooccurrence,10):.0f}, "
          f"p90={np.percentile(n_cooccurrence,90):.0f}, "
          f"max={n_cooccurrence.max()}")

# ── 5. Adequacy assessment ────────────────────────────────────────────────────
print("\n=== Adequacy assessment ===", flush=True)

# Thresholds for "adequate" matched-comparison coverage:
# - A matched-job fingerprint needs nodes to appear together in >= 5 jobs
# - Ideally most nodes have >= 10 co-occurrence partners
pairs_ge5  = (pair_counts_arr >= 5).sum()
pairs_ge10 = (pair_counts_arr >= 10).sum()
nodes_ge5_partners = sum(1 for v in node_cooccurrence.values() if len(v) >= 5)

print(f"  Pairs with >= 5 shared jobs: {pairs_ge5:,}")
print(f"  Pairs with >= 10 shared jobs: {pairs_ge10:,}")
print(f"  Nodes with >= 5 co-occurrence partners (>=2 shared): "
      f"{nodes_ge5_partners:,} of {n_cohort_nodes:,}")

# Key question: are there large jobs not currently selected that would
# dramatically improve shared-job coverage?
# A job with K cohort nodes adds K*(K-1)/2 new pairs.
# Find fleet jobs NOT in cohort with largest cohort-node overlap.

print("\nSearching for high-value large jobs not yet in cohort...", flush=True)

# Iterate jobs outside cohort, compute cohort overlap
top_large_jobs = []
for _, row in ji[~ji["job_idx"].astype(str).isin(cohort_job_ids)].iterrows():
    nc = row.get("node_count", 0)
    if pd.isna(nc) or nc < 128:    # only bother with large jobs
        continue
    hosts = to_py_list(row["host_list"])
    cohort_in_job = [h for h in hosts if h in cohort_hostnames]
    k = len(cohort_in_job)
    if k < 16:
        continue
    rt = row.get("run_time", 0)
    rt = rt if pd.notna(rt) else 0
    top_large_jobs.append({
        "job_idx": str(row["job_idx"]),
        "date_dir": row.get("date_dir", ""),
        "node_count": int(nc),
        "run_time_s": rt,
        "cohort_nodes_in_job": k,
        "pairs_added": k * (k - 1) // 2,
        "quarter": row.get("quarter", ""),
        "completion_state": row.get("completion_state", ""),
        "project_prefix": row.get("project_prefix", ""),
    })

top_large_jobs.sort(key=lambda x: -x["pairs_added"])
print(f"  Large non-cohort jobs with >=16 cohort nodes: {len(top_large_jobs):,}", flush=True)
if top_large_jobs:
    print(f"  Top 5 by pairs-added:")
    for j in top_large_jobs[:5]:
        print(f"    {j['job_idx']}  nc={j['node_count']}  "
              f"cohort_nodes={j['cohort_nodes_in_job']}  "
              f"pairs={j['pairs_added']}  "
              f"rt={j['run_time_s']:.0f}s  "
              f"state={j['completion_state']}  "
              f"prefix={j['project_prefix']}")

# ── 6. Decision: modify cohort? ───────────────────────────────────────────────
print("\n=== Cohort modification decision ===", flush=True)

BYTES_PER_NODE_SECOND = 64.1e6 / (3349 * 3600)
current_gb = (cohort_job_list["node_count"].fillna(4) *
              cohort_job_list["run_time_s"].fillna(3600)).sum() * BYTES_PER_NODE_SECOND / 1e9
budget_gb  = 15.0
headroom   = budget_gb - current_gb
print(f"  Current cohort: {current_gb:.1f} GB")
print(f"  Budget: {budget_gb:.1f} GB  ->  headroom: {headroom:.1f} GB")

# Decide: add top large jobs if pairs_ge5 < 50000 OR nodes_ge5_partners < 1500
NEED_MODIFICATION = (pairs_ge5 < 50_000) or (nodes_ge5_partners < 1_500)
print(f"  Modification needed: {NEED_MODIFICATION}")

added_jobs = []
if NEED_MODIFICATION and top_large_jobs:
    print("  Adding large matched jobs within budget...", flush=True)

    # Add top N large jobs (sorted by pairs_added) that fit in budget
    # Prefer COMPLETED jobs, then spread across quarters
    quarters_covered = set()
    for j in sorted(top_large_jobs,
                    key=lambda x: (x["completion_state"] != "COMPLETED",
                                   -x["pairs_added"])):
        est_gb = j["node_count"] * j["run_time_s"] * BYTES_PER_NODE_SECOND / 1e9
        if headroom - est_gb < 0:
            continue
        added_jobs.append(j)
        headroom -= est_gb
        quarters_covered.add(j["quarter"])
        if headroom < 0.2:
            break

    new_pairs = sum(j["pairs_added"] for j in added_jobs)
    new_gb    = sum(j["node_count"] * j["run_time_s"] * BYTES_PER_NODE_SECOND / 1e9
                    for j in added_jobs)
    print(f"  Adding {len(added_jobs)} large jobs: "
          f"+{new_pairs:,} pairs, +{new_gb:.2f} GB", flush=True)

elif not NEED_MODIFICATION:
    print("  Current cohort is adequate for matched-job analysis.", flush=True)
    print(f"    pairs_ge5={pairs_ge5:,}  nodes_ge5_partners={nodes_ge5_partners:,}")
else:
    print("  No large jobs available to add.", flush=True)

# ── 7. Regenerate manifests if modified ───────────────────────────────────────
if added_jobs:
    print("\nRegenerating cohort job list with added large jobs...", flush=True)

    added_df = pd.DataFrame(added_jobs)[["job_idx", "date_dir", "node_count", "run_time_s"]]
    added_df["globus_path"] = (
        "/gen101/world-shared/doi-data/OLCF/202609/10.13139_OLCF_3013979/"
        "frontier-job-centric-telemetry-dataset/job-telemetry/"
        + added_df["date_dir"].astype(str) + "/"
        + added_df["job_idx"].astype(str) + "/"
    )

    new_job_list = pd.concat([cohort_job_list, added_df], ignore_index=True)
    new_job_list = new_job_list.drop_duplicates(subset="job_idx")
    new_job_list.to_csv(OUT_DIR / "cohort_job_list.csv", index=False)
    print(f"  Updated cohort_job_list.csv: {len(new_job_list):,} jobs", flush=True)

    total_gb = (new_job_list["node_count"].fillna(4) *
                new_job_list["run_time_s"].fillna(3600)).sum() * BYTES_PER_NODE_SECOND / 1e9
    print(f"  Revised estimated download: {total_gb:.1f} GB", flush=True)
    final_jobs = len(new_job_list)
    final_gb   = total_gb
else:
    final_jobs = n_cohort_jobs
    final_gb   = current_gb

# ── 8. Generate Globus batch file ─────────────────────────────────────────────
jl_final = pd.read_csv(OUT_DIR / "cohort_job_list.csv")
batch_lines = []
LOCAL_ROOT  = "/Users/kalya/Downloads/frontier_phase1"
for _, r in jl_final.iterrows():
    src = str(r["globus_path"])
    dst = f"{LOCAL_ROOT}/job-telemetry/{r['date_dir']}/{r['job_idx']}/"
    batch_lines.append(f"{src} {dst} --recursive")

batch_path = OUT_DIR / "globus_batch.txt"
with open(batch_path, "w") as f:
    f.write("\n".join(batch_lines))
print(f"\nSaved globus_batch.txt ({len(batch_lines):,} transfer lines)", flush=True)

# ── 9. Save summary stats ─────────────────────────────────────────────────────
with open(OUT_DIR / "fleet_stats.json") as f:
    fs = json.load(f)

fs["shared_job_analysis"] = {
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
    "nodes_with_ge5_partners": int(nodes_ge5_partners),
    "large_jobs_added": len(added_jobs),
    "final_n_jobs":  final_jobs,
    "final_est_gb":  round(final_gb, 2),
    "modification_made": bool(added_jobs),
}

with open(OUT_DIR / "fleet_stats.json", "w") as f:
    json.dump(fs, f, indent=2)
print("Updated fleet_stats.json", flush=True)

# ── 10. Final summary ─────────────────────────────────────────────────────────
print(f"\n{'='*60}", flush=True)
print(f"FINAL COHORT SUMMARY", flush=True)
print(f"{'='*60}", flush=True)
print(f"  Nodes:              {n_cohort_nodes:,}", flush=True)
print(f"  Jobs (total):       {final_jobs:,}", flush=True)
print(f"  Estimated download: {final_gb:.1f} GB", flush=True)
print(f"  Cohort modified:    {bool(added_jobs)}", flush=True)
print(f"\nMatched-job coverage:", flush=True)
print(f"  Jobs w/ >=2 cohort nodes: {(cohort_nodes_per_job>=2).sum():,}", flush=True)
print(f"  Jobs w/ >=16 cohort nodes: {(cohort_nodes_per_job>=16).sum():,}", flush=True)
print(f"  Unique node pairs (>=1 shared): {n_unique_pairs:,}", flush=True)
print(f"  Pairs with >=5 shared jobs: {pairs_ge5:,}", flush=True)
print(f"  Pairs with >=10 shared jobs: {pairs_ge10:,}", flush=True)
print(f"\nGlobus transfer command:", flush=True)
print(f"  globus transfer \\", flush=True)
print(f"    57618e0a-2c99-45ff-9694-24141b92fa17 \\", flush=True)
print(f"    <YOUR-LOCAL-ENDPOINT-ID> \\", flush=True)
print(f"    --batch {batch_path} \\", flush=True)
print(f"    --label 'ThermalOps Phase 1 cohort'", flush=True)
print(f"\n=== DONE ===", flush=True)
