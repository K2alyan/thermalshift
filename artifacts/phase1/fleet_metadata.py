"""
Phase 1, Section 2: Full fleet metadata analysis.
Computes exact node reuse, temporal coverage, cohort statistics,
and designs the Phase 1 telemetry cohort.
Saves: artifacts/phase1/fleet_stats.json, cohort_manifest.csv, figures/fig1_fleet_metadata.png
"""

import pyarrow.parquet as pq
import pandas as pd
import numpy as np
import json
import re
import os
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

# Set THERMALSHIFT_DATA_DIR env var to your local Frontier dataset directory.
JOB_INFO = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "frontier-completed-job-info.parquet"
OUT_DIR  = Path(__file__).parent
FIG_DIR  = OUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

# ── 1. Load job-info ──────────────────────────────────────────────────────────
print("Loading full job-info...", flush=True)
ji = pq.read_table(JOB_INFO).to_pandas()
print(f"  Loaded: {len(ji):,} jobs, {ji.shape[1]} columns", flush=True)

# Parse timestamps
for col in ["submit_time", "start_time", "end_time"]:
    if col in ji.columns:
        ji[col] = pd.to_datetime(ji[col], utc=True, errors="coerce")

# ── 2. Top-level scalar statistics ───────────────────────────────────────────
print("\n=== Fleet-level statistics ===", flush=True)

n_jobs = len(ji)
date_start = ji["start_time"].min()
date_end   = ji["end_time"].max()
span_days  = (date_end - date_start).days

print(f"  Total jobs       : {n_jobs:,}")
print(f"  Collection start : {date_start}")
print(f"  Collection end   : {date_end}")
print(f"  Span             : {span_days} days ({span_days/365:.2f} years)")

# ── 3. Completion / queue / gpu distributions ─────────────────────────────────
print("\n=== completion_state ===", flush=True)
for k, v in ji["completion_state"].value_counts(dropna=False).items():
    print(f"  {k}: {v:,}  ({100*v/n_jobs:.1f}%)")

print("\n=== queue ===", flush=True)
for k, v in ji["queue"].value_counts(dropna=False).head(10).items():
    print(f"  {k}: {v:,}  ({100*v/n_jobs:.1f}%)")

print("\n=== gpu_enabled ===", flush=True)
for k, v in ji["gpu_enabled"].value_counts(dropna=False).items():
    print(f"  {k}: {v:,}  ({100*v/n_jobs:.1f}%)")

# ── 4. node_count distribution ────────────────────────────────────────────────
print("\n=== node_count ===", flush=True)
nc = ji["node_count"].dropna()
for p, v in zip([0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100],
                np.percentile(nc, [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100])):
    print(f"  p{p:3d}: {v:.0f}")
print(f"  mean  : {nc.mean():.1f}")
print(f"  median: {nc.median():.0f}")

# ── 5. run_time distribution ──────────────────────────────────────────────────
print("\n=== run_time (seconds) ===", flush=True)
rt = ji["run_time"].dropna()
for p, v in zip([0, 5, 25, 50, 75, 90, 95, 99, 100],
                np.percentile(rt, [0, 5, 25, 50, 75, 90, 95, 99, 100])):
    print(f"  p{p:3d}: {v:.0f} s  ({v/3600:.2f} h)")
print(f"  mean  : {rt.mean():.0f} s  ({rt.mean()/3600:.2f} h)")

# ── 6. project_prefix ─────────────────────────────────────────────────────────
print("\n=== project_prefix (top 20) ===", flush=True)
pp = ji["project_prefix"].value_counts(dropna=False)
n_unique_pp = len(pp)
print(f"  Unique project_prefix values: {n_unique_pp}")
for k, v in pp.head(20).items():
    print(f"  {k}: {v:,}  ({100*v/n_jobs:.1f}%)")

# ── 7. Explode host_list → per-node statistics ────────────────────────────────
print("\nExploding host_list...", flush=True)

# Columns to carry through to exploded table
meta_cols = ["job_idx", "start_time", "end_time", "run_time",
             "project_prefix", "node_count", "completion_state", "gpu_enabled"]

# host_list is stored as numpy.ndarray per row; use pandas explode
# Build a paired host+xname list per job first
def to_py_list(val):
    """Convert ndarray / list / None to plain Python list."""
    if val is None:
        return []
    if isinstance(val, (list, np.ndarray)):
        return list(val)
    try:
        import ast
        return ast.literal_eval(str(val))
    except Exception:
        return []

ji["_hosts"] = ji["host_list"].apply(to_py_list)
ji["_nodes"] = ji["node_list"].apply(to_py_list)

# Explode hosts
host_exp = ji[meta_cols + ["_hosts", "_nodes"]].copy()
host_exp = host_exp[host_exp["_hosts"].apply(len) > 0]
host_exp = host_exp.explode("_hosts")
host_exp = host_exp.rename(columns={"_hosts": "hostname"})

# Attach matching xname: explode nodes and align by position
# Simpler: pair (host, xname) as list of tuples, then explode
def make_pairs(row):
    hosts = row["_hosts_orig"]
    nodes = row["_nodes_orig"]
    if len(nodes) == len(hosts):
        return list(zip(hosts, nodes))
    return [(h, None) for h in hosts]

ji["_pairs"] = ji.apply(lambda r: make_pairs({"_hosts_orig": to_py_list(r["host_list"]),
                                               "_nodes_orig": to_py_list(r["node_list"])}), axis=1)
pairs_exp = ji[meta_cols + ["_pairs"]].copy()
pairs_exp = pairs_exp[pairs_exp["_pairs"].apply(len) > 0].explode("_pairs")
pairs_exp["hostname"] = pairs_exp["_pairs"].apply(lambda p: p[0])
pairs_exp["xname"]    = pairs_exp["_pairs"].apply(lambda p: p[1])
node_df = pairs_exp.drop(columns=["_pairs"]).reset_index(drop=True)

print(f"  Node-job pairs: {len(node_df):,}", flush=True)
print(f"  Unique hostnames: {node_df['hostname'].nunique():,}", flush=True)

# ── 8. Per-node statistics ────────────────────────────────────────────────────
print("\n=== Per-node statistics ===", flush=True)

per_node = node_df.groupby("hostname").agg(
    n_jobs=("job_idx", "nunique"),
    n_projects=("project_prefix", "nunique"),
    first_start=("start_time", "min"),
    last_end=("end_time", "max"),
    n_unique_dates=("start_time", lambda x: x.dt.date.nunique()),
    total_runtime_h=("run_time", lambda x: x.sum() / 3600 if x.notna().any() else 0),
).reset_index()

per_node["temporal_span_days"] = (per_node["last_end"] - per_node["first_start"]).dt.total_seconds() / 86400

# xname for each node (first occurrence)
node_xnames = node_df.dropna(subset=["xname"]).groupby("hostname")["xname"].first()
per_node["xname"] = per_node["hostname"].map(node_xnames)

n_unique_nodes = len(per_node)
print(f"  Unique nodes: {n_unique_nodes:,}")

# Jobs per node full percentile distribution
jobs_per_node = per_node["n_jobs"].values
print(f"\n  Jobs-per-node distribution:")
for p, v in zip([0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100],
                np.percentile(jobs_per_node, [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100])):
    print(f"    p{p:3d}: {v:.0f}")
print(f"    mean  : {jobs_per_node.mean():.1f}")
print(f"    median: {np.median(jobs_per_node):.0f}")

print(f"\n  Node reuse counts:")
thresholds = [2, 5, 10, 20, 50, 100, 250, 500]
for t in thresholds:
    cnt = (jobs_per_node >= t).sum()
    frac = cnt / n_unique_nodes
    print(f"    >= {t:4d} jobs: {cnt:6,}  ({100*frac:.1f}%)")

# Temporal span per node
ts = per_node["temporal_span_days"].dropna()
print(f"\n  Temporal span per node (days):")
for p, v in zip([0, 5, 25, 50, 75, 90, 95, 99, 100],
                np.percentile(ts, [0, 5, 25, 50, 75, 90, 95, 99, 100])):
    print(f"    p{p:3d}: {v:.1f} d")

# Distinct dates per node
nd = per_node["n_unique_dates"].values
print(f"\n  Distinct job-days per node:")
for p, v in zip([50, 75, 90, 95, 99, 100],
                np.percentile(nd, [50, 75, 90, 95, 99, 100])):
    print(f"    p{p:3d}: {v:.0f}")

# Unique project_prefix per node
np_ = per_node["n_projects"].values
print(f"\n  Unique project_prefix per node:")
for p, v in zip([50, 75, 90, 95, 99, 100],
                np.percentile(np_, [50, 75, 90, 95, 99, 100])):
    print(f"    p{p:3d}: {v:.0f}")
print(f"  Nodes with >=2 projects: {(np_>=2).sum():,}  ({100*(np_>=2).mean():.1f}%)")
print(f"  Nodes with >=3 projects: {(np_>=3).sum():,}  ({100*(np_>=3).mean():.1f}%)")
print(f"  Nodes with >=5 projects: {(np_>=5).sum():,}  ({100*(np_>=5).mean():.1f}%)")

# ── 9. Parse xname topology ───────────────────────────────────────────────────
def parse_xname(xname):
    if not xname or not isinstance(xname, str):
        return {}
    m = re.match(r"x(\d+)c(\d+)s(\d+)b(\d+)n(\d+)", xname)
    if not m:
        return {}
    r, c, s, b, n = [int(x) for x in m.groups()]
    return {"rack": r, "chassis": c, "slot": s, "board": b, "node_pos": n}

topo = per_node["xname"].apply(parse_xname)
per_node["rack"]      = topo.apply(lambda d: d.get("rack"))
per_node["chassis"]   = topo.apply(lambda d: d.get("chassis"))
per_node["slot"]      = topo.apply(lambda d: d.get("slot"))
per_node["board"]     = topo.apply(lambda d: d.get("board"))
per_node["node_pos"]  = topo.apply(lambda d: d.get("node_pos"))

n_with_topo = per_node["rack"].notna().sum()
print(f"\n  Nodes with parsed xname: {n_with_topo:,}")
print(f"  Unique racks:   {per_node['rack'].nunique()}")
print(f"  Unique chassis: {per_node['chassis'].nunique()}")
print(f"  Unique slots:   {per_node['slot'].nunique()}")

# ── 10. Cohort design ─────────────────────────────────────────────────────────
print("\n=== Phase 1 Cohort Design ===", flush=True)

# Criteria:
# - At least 10 independent jobs
# - Temporal span >= 30 days (ensures non-trivial stability window)
# - xname parsed (needed for spatial analysis)
# - Workload diversity: prefer >=2 project_prefix values

MIN_JOBS          = 10
MIN_SPAN_DAYS     = 30
TARGET_NODES      = 2000
MAX_NODES         = 4000

cohort_pool = per_node[
    (per_node["n_jobs"] >= MIN_JOBS) &
    (per_node["temporal_span_days"] >= MIN_SPAN_DAYS) &
    (per_node["rack"].notna())
].copy()

print(f"  Pool (>={MIN_JOBS} jobs, >={MIN_SPAN_DAYS} day span, xname parsed): {len(cohort_pool):,} nodes")

# Score nodes for selection priority:
#   - more jobs = better fingerprint estimation
#   - more projects = workload diversity
#   - longer span = stability over time
#   - normalize each to [0,1] and combine
def norm01(s):
    mn, mx = s.min(), s.max()
    if mx == mn:
        return s * 0
    return (s - mn) / (mx - mn)

cohort_pool["score"] = (
    0.40 * norm01(np.log1p(cohort_pool["n_jobs"])) +
    0.30 * norm01(cohort_pool["temporal_span_days"]) +
    0.20 * norm01(cohort_pool["n_projects"]) +
    0.10 * norm01(cohort_pool["n_unique_dates"])
)

# Ensure spatial coverage: within each rack, select by score
cohort_pool = cohort_pool.sort_values("score", ascending=False)

if len(cohort_pool) <= MAX_NODES:
    cohort = cohort_pool.copy()
    print(f"  Pool is within MAX_NODES limit — taking all {len(cohort):,} nodes")
else:
    # Stratified: take top-scored within each rack, capping at MAX_NODES total
    # First take all nodes with >= 50 jobs unconditionally
    high_reuse = cohort_pool[cohort_pool["n_jobs"] >= 50]
    remaining  = cohort_pool[cohort_pool["n_jobs"] < 50]
    n_remaining = max(0, TARGET_NODES - len(high_reuse))
    # From remaining, stratify by rack to ensure spatial coverage
    rack_quota = max(1, n_remaining // max(1, remaining["rack"].nunique()))
    stratified = (
        remaining.groupby("rack", group_keys=False)
        .apply(lambda g: g.head(rack_quota))
    )
    # Top up to TARGET_NODES
    still_need = TARGET_NODES - len(high_reuse) - len(stratified)
    if still_need > 0:
        used = set(high_reuse.index) | set(stratified.index)
        fill = cohort_pool[~cohort_pool.index.isin(used)].head(still_need)
        cohort = pd.concat([high_reuse, stratified, fill]).drop_duplicates()
    else:
        cohort = pd.concat([high_reuse, stratified]).drop_duplicates().head(TARGET_NODES)
    print(f"  Selected {len(cohort):,} nodes (target {TARGET_NODES:,})")

print(f"  Cohort n_jobs: min={cohort['n_jobs'].min()}, median={cohort['n_jobs'].median():.0f}, max={cohort['n_jobs'].max()}")
print(f"  Cohort temporal span: median={cohort['temporal_span_days'].median():.0f} days, max={cohort['temporal_span_days'].max():.0f} days")
print(f"  Cohort racks covered: {cohort['rack'].nunique()}")
print(f"  Cohort chassis covered: {cohort['chassis'].nunique()}")
print(f"  Nodes with >=2 projects: {(cohort['n_projects']>=2).sum():,}")
print(f"  Nodes with >=5 projects: {(cohort['n_projects']>=5).sum():,}")

# ── 11. Estimate download size ────────────────────────────────────────────────
print("\n=== Download size estimate ===", flush=True)

# Get all jobs for cohort nodes
cohort_hostnames = set(cohort["hostname"])
cohort_job_rows = node_df[node_df["hostname"].isin(cohort_hostnames)]
cohort_jobs = cohort_job_rows["job_idx"].unique()

# Cross-ref with original ji to get node_count for each job
ji_idx = ji.set_index("job_idx")

total_node_seconds = 0
total_jobs = len(cohort_jobs)
missing = 0
for jid in cohort_jobs:
    if jid not in ji_idx.index:
        missing += 1
        continue
    row = ji_idx.loc[jid]
    nc_j = row["node_count"] if pd.notna(row["node_count"]) else 1
    rt_j = row["run_time"]   if pd.notna(row["run_time"])   else 3600
    total_node_seconds += nc_j * rt_j

# Empirical estimate from sample:
# Sample: 95 jobs, mean 4613/95 ≈ 49 nodes/job, 1,620,918 obs (8 GCDs × timesteps)
# Each obs ≈ temperature + power merged → ~2 parquet files per job
# From sample: 95 jobs → ~56 MB compressed (only temperature+power cleaned files)
# Per job per node: temperature file at 60s = ~6 rows/min; power resampled similarly
# Rough: size ∝ node_seconds
sample_node_seconds = 0
sample_ji = pq.read_table(Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "frontier-completed-job-info-SAMPLE.parquet").to_pandas()
for _, r in sample_ji.iterrows():
    nc_s = r["node_count"] if pd.notna(r["node_count"]) else 1
    rt_s = r["run_time"]   if pd.notna(r["run_time"])   else 3600
    sample_node_seconds += nc_s * rt_s

# Sample parquet directory size: cleaned temp+power only
import os, glob
sample_dir = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "job-telemetry"
sample_bytes = sum(
    os.path.getsize(f)
    for f in glob.glob(str(sample_dir / "**" / "*-cleaned-*.parquet"), recursive=True)
)
print(f"  Sample cleaned-parquet size: {sample_bytes/1e6:.1f} MB over {int(sample_node_seconds/3600):,} node-hours")

if sample_node_seconds > 0:
    bytes_per_node_second = sample_bytes / sample_node_seconds
    est_bytes = bytes_per_node_second * total_node_seconds
    print(f"  Cohort node-hours: {int(total_node_seconds/3600):,}")
    print(f"  Estimated download (cleaned temp+power only): {est_bytes/1e9:.1f} GB")
    print(f"  Jobs to download: {total_jobs:,}  (missing from ji: {missing})")
else:
    print("  Could not estimate size (sample_node_seconds=0)")

# ── 12. Cohort manifest ───────────────────────────────────────────────────────
# Save per-node cohort, plus all jobs associated with cohort nodes
manifest = cohort[[
    "hostname", "xname", "rack", "chassis", "slot", "board", "node_pos",
    "n_jobs", "n_projects", "first_start", "last_end",
    "temporal_span_days", "n_unique_dates", "total_runtime_h", "score"
]].copy()
manifest = manifest.sort_values("n_jobs", ascending=False).reset_index(drop=True)

manifest_path = OUT_DIR / "cohort_manifest.csv"
manifest.to_csv(manifest_path, index=False)
print(f"\nSaved cohort_manifest.csv  ({len(manifest):,} nodes)", flush=True)

# Also save the list of job_idx files to download
cohort_job_list = pd.DataFrame({"job_idx": cohort_jobs})
cohort_job_list.to_csv(OUT_DIR / "cohort_job_list.csv", index=False)
print(f"Saved cohort_job_list.csv  ({len(cohort_jobs):,} jobs)", flush=True)

# ── 13. Figure 1: Fleet metadata (4-panel) ────────────────────────────────────
print("\nGenerating Figure 1...", flush=True)

fig = plt.figure(figsize=(16, 10))
gs  = gridspec.GridSpec(2, 3, figure=fig, hspace=0.40, wspace=0.35)

# Panel A: Jobs-per-node histogram (log scale)
ax = fig.add_subplot(gs[0, 0])
bins = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 5000]
ax.hist(per_node["n_jobs"], bins=bins, color="steelblue", alpha=0.8, edgecolor="white")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xlabel("Jobs per node")
ax.set_ylabel("Node count")
ax.set_title(f"A: Jobs per node (N={n_unique_nodes:,} nodes)")
ax.axvline(10, color="red", linestyle="--", linewidth=1, label=">=10 threshold")
ax.legend(fontsize=8)

# Panel B: Node reuse CDF
ax = fig.add_subplot(gs[0, 1])
sorted_jobs = np.sort(per_node["n_jobs"].values)
cdf = np.arange(1, len(sorted_jobs)+1) / len(sorted_jobs)
ax.plot(sorted_jobs, 1 - cdf, color="steelblue", linewidth=1.5)
ax.set_xscale("log")
ax.set_xlabel("Jobs per node (log)")
ax.set_ylabel("Fraction of nodes with >= x jobs")
ax.set_title(f"B: Node reuse CCDF")
ax.axvline(10, color="red", linestyle="--", linewidth=1)
ax.grid(True, alpha=0.3)

# Panel C: Temporal span per node
ax = fig.add_subplot(gs[0, 2])
ax.hist(per_node["temporal_span_days"].dropna(), bins=50, color="darkorange", alpha=0.8, edgecolor="white")
ax.set_xlabel("Temporal span (days)")
ax.set_ylabel("Node count")
ax.set_title("C: Temporal span per node")
ax.axvline(30, color="red", linestyle="--", linewidth=1, label="30-day min")
ax.axvline(365, color="green", linestyle="--", linewidth=1, label=">1 year")
ax.legend(fontsize=8)

# Panel D: node_count distribution (job size)
ax = fig.add_subplot(gs[1, 0])
nc_vals = ji["node_count"].dropna().values
ax.hist(np.log10(np.maximum(nc_vals, 1)), bins=40, color="mediumpurple", alpha=0.8, edgecolor="white")
ax.set_xlabel("Node count per job (log scale)")
ax.set_ylabel("Job count")
ax.set_title("D: Job size distribution")
xticks = [1, 2, 5, 10, 50, 100, 500, 2000]
ax.set_xticks(np.log10(xticks))
ax.set_xticklabels([str(x) for x in xticks], fontsize=7)

# Panel E: project_prefix distribution (top 20)
ax = fig.add_subplot(gs[1, 1])
top_pp = pp.head(20)
ax.barh(range(len(top_pp)), top_pp.values[::-1], color="steelblue", alpha=0.8)
ax.set_yticks(range(len(top_pp)))
ax.set_yticklabels(list(top_pp.index[::-1]), fontsize=7)
ax.set_xlabel("Job count")
ax.set_title(f"E: project_prefix distribution\n({n_unique_pp} unique prefixes)")

# Panel F: Cohort vs pool summary
ax = fig.add_subplot(gs[1, 2])
labels = ["Total\nnodes", "Pool\n(>=10 jobs,\n>=30d span)", "Cohort\nselected",
          "Nodes with\n>=2 projects", "Nodes with\n>=5 projects"]
vals = [n_unique_nodes,
        len(cohort_pool),
        len(cohort),
        int((cohort["n_projects"] >= 2).sum()),
        int((cohort["n_projects"] >= 5).sum())]
colors = ["#aec7e8", "#ffbb78", "#98df8a", "#c5b0d5", "#f7b6d2"]
ax.bar(range(len(labels)), vals, color=colors, edgecolor="white", alpha=0.9)
ax.set_xticks(range(len(labels)))
ax.set_xticklabels(labels, fontsize=7)
ax.set_ylabel("Node count")
ax.set_title("F: Cohort selection funnel")
for i, v in enumerate(vals):
    ax.text(i, v + max(vals)*0.01, f"{v:,}", ha="center", fontsize=7)

fig.suptitle(
    f"Frontier Fleet Metadata | {n_jobs:,} jobs | {n_unique_nodes:,} nodes | "
    f"{date_start.date()} to {date_end.date()}",
    fontsize=12, fontweight="bold"
)
p = FIG_DIR / "fig1_fleet_metadata.png"
fig.savefig(p, dpi=130, bbox_inches="tight")
plt.close(fig)
print(f"  Saved {p.name}", flush=True)

# ── 14. Save stats JSON ───────────────────────────────────────────────────────
def to_json_safe(x):
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.floating,)): return None if not np.isfinite(float(x)) else float(x)
    if isinstance(x, dict): return {str(k): to_json_safe(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)): return [to_json_safe(i) for i in x]
    if isinstance(x, pd.Timestamp): return str(x)
    return x

reuse_counts = {f">={t}": int((per_node["n_jobs"] >= t).sum()) for t in thresholds}
reuse_fracs  = {f">={t}_frac": float((per_node["n_jobs"] >= t).mean()) for t in thresholds}

fleet_stats = {
    "n_jobs": n_jobs,
    "n_unique_nodes": n_unique_nodes,
    "collection_start": str(date_start),
    "collection_end": str(date_end),
    "span_days": span_days,
    "n_unique_project_prefix": int(n_unique_pp),
    "completion_state": {k: int(v) for k, v in ji["completion_state"].value_counts(dropna=False).items()},
    "gpu_enabled": {str(k): int(v) for k, v in ji["gpu_enabled"].value_counts(dropna=False).items()},
    "queue": {k: int(v) for k, v in ji["queue"].value_counts(dropna=False).head(10).items()},
    "jobs_per_node_percentiles": {
        f"p{p}": float(np.percentile(jobs_per_node, p))
        for p in [0, 1, 5, 10, 25, 50, 75, 90, 95, 99, 100]
    },
    "jobs_per_node_mean": float(jobs_per_node.mean()),
    "node_reuse_counts": reuse_counts,
    "node_reuse_fractions": reuse_fracs,
    "temporal_span_per_node_days": {
        f"p{p}": to_json_safe(np.percentile(ts, p))
        for p in [0, 5, 25, 50, 75, 90, 95, 99, 100]
    },
    "n_unique_dates_per_node": {
        f"p{p}": to_json_safe(np.percentile(nd, p))
        for p in [50, 75, 90, 95, 99, 100]
    },
    "projects_per_node": {
        "pct_with_2plus": float((np_>=2).mean()),
        "pct_with_3plus": float((np_>=3).mean()),
        "pct_with_5plus": float((np_>=5).mean()),
    },
    "topology": {
        "n_racks": int(per_node["rack"].nunique()),
        "n_chassis": int(per_node["chassis"].nunique()),
        "n_slots": int(per_node["slot"].nunique()),
    },
    "cohort": {
        "n_nodes": len(cohort),
        "n_jobs": int(total_jobs),
        "min_jobs_per_node": int(cohort["n_jobs"].min()),
        "median_jobs_per_node": float(cohort["n_jobs"].median()),
        "max_jobs_per_node": int(cohort["n_jobs"].max()),
        "median_span_days": float(cohort["temporal_span_days"].median()),
        "max_span_days": float(cohort["temporal_span_days"].max()),
        "n_racks": int(cohort["rack"].nunique()),
        "n_with_2plus_projects": int((cohort["n_projects"]>=2).sum()),
        "n_with_5plus_projects": int((cohort["n_projects"]>=5).sum()),
        "estimated_download_gb": to_json_safe(est_bytes/1e9 if sample_node_seconds > 0 else None),
    }
}

with open(OUT_DIR / "fleet_stats.json", "w") as f:
    json.dump(fleet_stats, f, indent=2)
print("\nSaved fleet_stats.json", flush=True)

print("\n=== DONE ===", flush=True)
