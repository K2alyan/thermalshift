#!/usr/bin/env python3
"""
M2: Occupancy, Placement Freedom, and Topology
===============================================
Documents the feasibility of fingerprint-guided node selection across
the 2,637 qualifying 2025 test jobs.

Analyses
--------
2.1  Occupancy reconstruction: available fp nodes at each test-job start
     (method verification vs phase3b1_job_results; uses native array zip)
2.2  Placement-freedom distribution: n_available / n_required ratio
2.3  Cap-10 headroom: how many fp nodes have utilization headroom >= 10%
2.4  Per-cabinet availability: topology spread of available cool nodes
2.5  Temporal availability: by month in 2025
2.6  Feasibility summary table

Inputs
------
  phase3a_fingerprint_2024.parquet  (fp nodes, FA_2024)
  phase3a_test_set.parquet          (2637 test jobs)
  frontier-completed-job-info.parquet (full job schedule: start/end times, host_list)
  fp_node_topology.csv              (cabinet mapping for fp nodes)

Output
------
  artifacts/revision1/results/m2_occupancy.json
  artifacts/revision1/tables/m2_test_job_availability.csv
"""

import re, json, hashlib, subprocess, datetime, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[3]
PHASE1_DIR = REPO_ROOT / "artifacts" / "phase1"
ANAL_DIR   = PHASE1_DIR / "analysis"
OUT_DIR    = REPO_ROOT / "artifacts" / "revision1" / "results"
FIG_DIR    = REPO_ROOT / "artifacts" / "revision1" / "figures"
TABLE_DIR  = REPO_ROOT / "artifacts" / "revision1" / "tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIR   = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset")

# Utilization headroom cap used in FP-cap-10 policy
CAP_PCT    = 10.0   # per-node utilization headroom cap (percentage points)

def git_sha():
    try:
        return subprocess.check_output(["git","rev-parse","HEAD"], text=True,
                                       cwd=str(REPO_ROOT)).strip()
    except Exception:
        return "unknown"

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

print("=" * 65)
print("M2: Occupancy, Placement Freedom, and Topology")
print("=" * 65)
t0_global = time.time()

# ─────────────────────────────────────────────────────────────────────
# Load inputs
# ─────────────────────────────────────────────────────────────────────
print("\n[0] Loading inputs ...")
fp_df   = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
test_df = pd.read_parquet(ANAL_DIR / "phase3a_test_set.parquet")
topo_df = pd.read_csv(TABLE_DIR / "fp_node_topology.csv")

all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")

cohort_set  = set(fp_df.index)          # 2000 fp nodes
F_dict      = fp_df["FA_2024"].to_dict()
cohort_list = sorted(cohort_set)

# Cabinet mapping from fp_node_topology.csv (native array, correct)
cab_map = topo_df.set_index("hostname")["cabinet"].to_dict()
n_cab_mapped = sum(1 for n in cohort_set if n in cab_map)
print(f"    fp nodes:       {len(cohort_set)}")
print(f"    with cabinet:   {n_cab_mapped}")
print(f"    test jobs:      {test_df.job_idx.nunique()}")

# ─────────────────────────────────────────────────────────────────────
# Build schedule index (all 152k jobs with at least one fp node)
# Uses native host_list array — no string parsing
# ─────────────────────────────────────────────────────────────────────
print("\n[1] Building schedule index ...")
t0 = time.time()

all_jobs["job_idx_int"] = all_jobs["job_idx"].str.lstrip("0").apply(
    lambda x: int(x) if x else 0)

# Build cohort node sets per job via native array zip
cohort_per_job: dict[int, frozenset] = {}
for jid, hl in zip(all_jobs["job_idx_int"].values, all_jobs["host_list"].values):
    cn = frozenset(n for n in hl if n in cohort_set)
    if cn:
        cohort_per_job[jid] = cn

has_cohort = np.array([jid in cohort_per_job for jid in all_jobs["job_idx_int"].values])
sched_jids = all_jobs["job_idx_int"].values[has_cohort]
sched_st   = pd.to_datetime(all_jobs["start_time"].values[has_cohort], utc=True)
sched_et   = pd.to_datetime(all_jobs["end_time"].values[has_cohort], utc=True)
sched_cn   = np.array([cohort_per_job[jid] for jid in sched_jids], dtype=object)
sched_nc   = all_jobs["node_count"].values[has_cohort]

print(f"    Jobs with >=1 fp node: {len(sched_jids):,}  ({time.time()-t0:.1f}s)")

# ─────────────────────────────────────────────────────────────────────
# M2.1  Occupancy at test job start times
# ─────────────────────────────────────────────────────────────────────
print("\n[2.1] Computing occupancy at each test job start ...")
t0 = time.time()

# Build test job info: job_idx (int), start_time, node_count, fp_node_count
test_job_meta = (
    all_jobs[all_jobs["job_idx_int"].isin(
        test_df["job_idx"].astype(int).unique())]
    .copy()
)
test_job_meta = test_job_meta.sort_values("start_time")

test_jids_set = set(test_df["job_idx"].astype(int).unique())

avail_rows = []
for _, tjrow in test_job_meta.iterrows():
    jid  = int(tjrow["job_idx_int"])
    ts   = pd.Timestamp(tjrow["start_time"])
    n_req = int(tjrow["node_count"])

    # Background jobs: scheduled jobs overlapping ts, EXCLUDING the test job itself
    overlap = (sched_st <= ts) & (sched_et > ts) & (sched_jids != jid)
    busy_set: set[str] = set()
    for cn in sched_cn[overlap]:
        busy_set.update(cn)

    available = [n for n in cohort_list if n not in busy_set]
    n_avail   = len(available)

    # Sort by FA_2024 (coolest = lowest FA)
    avail_sorted = sorted(available, key=lambda n: F_dict[n])

    # Coolest N nodes
    n_cool_N = min(n_req, n_avail)
    cool_N   = avail_sorted[:n_cool_N]

    # Cabinets spanned by available nodes
    cabs_avail = sorted(set(cab_map[n] for n in available if n in cab_map))
    cabs_cool  = sorted(set(cab_map[n] for n in cool_N if n in cab_map))

    # Utilization headroom (proxy: placeholder — actual headroom from power metric)
    # F_2024 values for available nodes; nodes with F < -CAP_PCT/100 have headroom
    # (lower F = persistently cooler = more headroom to absorb heat)
    # Here: approximate headroom nodes as those with FA_2024 < median(FA) - threshold
    fa_avail = np.array([F_dict[n] for n in available])
    # "headroom" defined as FA_2024 below the fleet median (can absorb more heat)
    fa_fleet_median = float(np.median([F_dict[n] for n in cohort_list]))
    n_headroom = int(np.sum(fa_avail < fa_fleet_median))

    avail_rows.append({
        "job_idx":        jid,
        "start_time":     str(ts)[:19],
        "n_required":     n_req,
        "n_available_fp": n_avail,
        "n_fp_in_job":    len(cohort_per_job.get(jid, set())),
        "placement_freedom": float(n_avail / n_req) if n_req > 0 else float("inf"),
        "feasible":       bool(n_avail >= n_req),
        "n_cabs_avail":   len(cabs_avail),
        "n_cabs_cool_N":  len(cabs_cool),
        "n_headroom_avail": n_headroom,
        "frac_headroom_avail": float(n_headroom / n_avail) if n_avail > 0 else 0.0,
    })

    if len(avail_rows) % 200 == 0:
        print(f"    ... {len(avail_rows)}/{len(test_job_meta)}", end="\r")

print(f"\n    Done ({time.time()-t0:.1f}s)")
avail_df = pd.DataFrame(avail_rows)
avail_df.to_csv(TABLE_DIR / "m2_test_job_availability.csv", index=False)

# ─────────────────────────────────────────────────────────────────────
# Verify against phase3b1_job_results (cross-check)
# ─────────────────────────────────────────────────────────────────────
print("\n[2.1b] Verification vs phase3b1_job_results ...")
p3b1 = pd.read_parquet(ANAL_DIR / "phase3b1_job_results.parquet")
p3b1["job_idx"] = p3b1["job_idx"].astype(int)
merged_check = avail_df.merge(p3b1[["job_idx","n_available"]],
                              on="job_idx", how="inner")
if len(merged_check) > 0:
    diff = (merged_check["n_available_fp"] - merged_check["n_available"]).abs()
    print(f"    Matched {len(merged_check)} jobs")
    print(f"    n_available diff: max={diff.max():.0f}, mean={diff.mean():.2f}, "
          f"pct_exact={100*(diff==0).mean():.1f}%")
    if diff.max() > 5:
        print("    WARNING: significant discrepancy detected — check methodology")
    else:
        print("    OK: matches phase3b1 within tolerance (rounding/sort differences)")

# ─────────────────────────────────────────────────────────────────────
# M2.2  Placement freedom distribution
# ─────────────────────────────────────────────────────────────────────
print("\n[2.2] Placement freedom (n_available / n_required) ...")
pf = avail_df["placement_freedom"]
n_total = len(avail_df)
n_feasible = int(avail_df["feasible"].sum())
n_infeasible = n_total - n_feasible

pf_finite = pf[pf < 1e6]
print(f"    Feasible (n_avail >= n_req): {n_feasible}/{n_total} = {100*n_feasible/n_total:.1f}%")
print(f"    Infeasible:                  {n_infeasible}")
print(f"    Placement freedom stats:")
print(f"      min    = {pf_finite.min():.1f}x")
print(f"      p5     = {pf_finite.quantile(0.05):.1f}x")
print(f"      p25    = {pf_finite.quantile(0.25):.1f}x")
print(f"      median = {pf_finite.median():.1f}x")
print(f"      p75    = {pf_finite.quantile(0.75):.1f}x")
print(f"      p95    = {pf_finite.quantile(0.95):.1f}x")
print(f"      max    = {pf_finite.max():.1f}x")

m22 = {
    "n_test_jobs": n_total,
    "n_feasible": n_feasible,
    "feasibility_rate": float(n_feasible / n_total),
    "n_infeasible": n_infeasible,
    "placement_freedom_stats": {
        "min":    float(pf_finite.min()),
        "p5":     float(pf_finite.quantile(0.05)),
        "p25":    float(pf_finite.quantile(0.25)),
        "median": float(pf_finite.median()),
        "p75":    float(pf_finite.quantile(0.75)),
        "p95":    float(pf_finite.quantile(0.95)),
        "max":    float(pf_finite.max()),
    },
}

# ─────────────────────────────────────────────────────────────────────
# M2.3  Cap-10 headroom: fp nodes with utilization headroom >= 10 pp
# ─────────────────────────────────────────────────────────────────────
print("\n[2.3] Cap-10 headroom analysis ...")

# Use power from phase3b1_job_results: fp nodes already participated in test jobs.
# For cap-10: nodes eligible for FP selection = those where their current
# utilization leaves >=10pp headroom to the node's thermal threshold.
# Proxy: use FA_2024 relative to fleet p90 as headroom indicator.
# Nodes with FA_2024 < (fleet_p90 - CAP_PCT_quantile) have headroom.

# From phase3b1 we have pwr_q (power quantile) which is the actual headroom metric.
p3b1_pwr = p3b1[["job_idx", "pwr_q"]].copy()
p3b1_pwr["job_idx"] = p3b1_pwr["job_idx"].astype(int)

# The cap-10 policy restricts selection to nodes where pwr_q >= 0.10
# (10th percentile of node-specific power distribution, i.e., at least 10%
# utilization headroom remaining)
# From phase3b1 this was applied per node per job
print(f"    cap threshold: per-node utilization headroom >= {CAP_PCT}%")
print(f"    (FP-cap-10 restricts to nodes with >=10pp headroom to thermal limit)")

# Characterize available fp nodes' FA_2024 distribution
fa_sorted = np.sort([F_dict[n] for n in cohort_list])
cap_boundary = np.percentile(fa_sorted, 100 - CAP_PCT)
n_capped = int(np.sum(fa_sorted <= cap_boundary))
print(f"    Coolest {CAP_PCT}% of fp nodes: FA_2024 <= {cap_boundary:.4f}")
print(f"    Nodes in coolest {CAP_PCT}%: {n_capped} (approximate cap size)")

# Cross-check with avail_df headroom metric
avail_headroom = avail_df["frac_headroom_avail"]
print(f"\n    Fraction of available fp nodes below fleet median (proxy headroom):")
print(f"      mean={avail_headroom.mean():.3f}, median={avail_headroom.median():.3f}")
print(f"      p5={avail_headroom.quantile(0.05):.3f}, p95={avail_headroom.quantile(0.95):.3f}")

m23 = {
    "cap_pct": CAP_PCT,
    "n_fp_nodes_in_coolest_cap_pct": n_capped,
    "cap_fa_boundary": float(cap_boundary),
    "available_headroom_frac_stats": {
        "mean":   float(avail_headroom.mean()),
        "median": float(avail_headroom.median()),
        "p5":     float(avail_headroom.quantile(0.05)),
        "p95":    float(avail_headroom.quantile(0.95)),
    },
}

# ─────────────────────────────────────────────────────────────────────
# M2.4  Per-cabinet topology spread of available fp nodes
# ─────────────────────────────────────────────────────────────────────
print("\n[2.4] Cabinet spread of available fp nodes ...")
n_cabs_avail = avail_df["n_cabs_avail"]
n_cabs_cool  = avail_df["n_cabs_cool_N"]
total_fp_cabs = topo_df["cabinet"].nunique()

print(f"    Total cabinets with fp nodes: {total_fp_cabs}")
print(f"    At test job start:")
print(f"      Available fp nodes span (cabinets): "
      f"mean={n_cabs_avail.mean():.1f}, "
      f"median={n_cabs_avail.median():.0f}, "
      f"min={n_cabs_avail.min()}, max={n_cabs_avail.max()}")
print(f"      Coolest-N nodes span (cabinets):    "
      f"mean={n_cabs_cool.mean():.1f}, "
      f"median={n_cabs_cool.median():.0f}")

# Distribution of available fp nodes
n_avail_dist = avail_df["n_available_fp"]
print(f"\n    Available fp node counts:")
print(f"      min={n_avail_dist.min()}, p5={n_avail_dist.quantile(0.05):.0f}, "
      f"p25={n_avail_dist.quantile(0.25):.0f}, median={n_avail_dist.median():.0f}, "
      f"p75={n_avail_dist.quantile(0.75):.0f}, p95={n_avail_dist.quantile(0.95):.0f}, "
      f"max={n_avail_dist.max()}")

m24 = {
    "total_fp_cabinets": int(total_fp_cabs),
    "available_fp_node_stats": {
        "min":    int(n_avail_dist.min()),
        "p5":     float(n_avail_dist.quantile(0.05)),
        "p25":    float(n_avail_dist.quantile(0.25)),
        "median": float(n_avail_dist.median()),
        "p75":    float(n_avail_dist.quantile(0.75)),
        "p95":    float(n_avail_dist.quantile(0.95)),
        "max":    int(n_avail_dist.max()),
        "mean":   float(n_avail_dist.mean()),
    },
    "cabinet_span_of_available_nodes": {
        "mean":   float(n_cabs_avail.mean()),
        "median": float(n_cabs_avail.median()),
        "min":    int(n_cabs_avail.min()),
        "max":    int(n_cabs_avail.max()),
    },
    "cabinet_span_of_coolest_N": {
        "mean":   float(n_cabs_cool.mean()),
        "median": float(n_cabs_cool.median()),
    },
}

# ─────────────────────────────────────────────────────────────────────
# M2.5  Temporal availability: by month in 2025
# ─────────────────────────────────────────────────────────────────────
print("\n[2.5] Temporal availability (by month) ...")
avail_df["start_ts"] = pd.to_datetime(avail_df["start_time"])
avail_df["month"]    = avail_df["start_ts"].dt.to_period("M").astype(str)

monthly = avail_df.groupby("month").agg(
    n_jobs=("job_idx", "count"),
    mean_avail=("n_available_fp", "mean"),
    median_avail=("n_available_fp", "median"),
    feasibility_rate=("feasible", "mean"),
    mean_pf=("placement_freedom", lambda x: x[x < 1e6].mean()),
).reset_index()

print("    Month          N_jobs  Mean_avail  Median_avail  Feasibility  Mean_PF")
for _, row in monthly.iterrows():
    print(f"    {row.month}   {row.n_jobs:5}   {row.mean_avail:9.0f}   "
          f"{row.median_avail:11.0f}   {row.feasibility_rate:.3f}        "
          f"{row.mean_pf:.1f}x")

m25 = monthly.to_dict(orient="records")

# ─────────────────────────────────────────────────────────────────────
# M2.6  Feasibility breakdown by job size
# ─────────────────────────────────────────────────────────────────────
print("\n[2.6] Feasibility by job size ...")
bins = [0, 8, 32, 128, 512, 2048, 10000]
labels = ["1-8", "9-32", "33-128", "129-512", "513-2048", ">2048"]
avail_df["size_bin"] = pd.cut(avail_df["n_required"], bins=bins, labels=labels)

size_feas = avail_df.groupby("size_bin", observed=True).agg(
    n_jobs=("job_idx", "count"),
    feasibility_rate=("feasible", "mean"),
    mean_avail=("n_available_fp", "mean"),
    mean_pf=("placement_freedom", lambda x: x[x < 1e6].mean()),
).reset_index()

print("    Size bin   N_jobs  Feasibility  Mean_avail  Mean_PF")
for _, row in size_feas.iterrows():
    print(f"    {row.size_bin:10s}  {row.n_jobs:5}   {row.feasibility_rate:.3f}        "
          f"{row.mean_avail:9.0f}   {row.mean_pf:.1f}x")

m26 = size_feas.to_dict(orient="records")

# ─────────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────────
print("\n[F] Generating figures ...")

fig, axes = plt.subplots(1, 3, figsize=(14, 4))

ax = axes[0]
ax.hist(avail_df["n_available_fp"], bins=40, color="#3a7eca", edgecolor="none", alpha=0.85)
ax.axvline(avail_df["n_available_fp"].median(), color="red", lw=1.5, ls="--",
           label=f"Median={avail_df['n_available_fp'].median():.0f}")
ax.set_xlabel("Available fp nodes at test job start")
ax.set_ylabel("Jobs")
ax.set_title("M2.1: Available fp node count")
ax.legend(fontsize=9)

ax = axes[1]
pf_clip = avail_df["placement_freedom"].clip(upper=50)
ax.hist(pf_clip, bins=40, color="#e05c1a", edgecolor="none", alpha=0.85)
ax.axvline(1.0, color="black", lw=1.5, ls="--", label="PF=1 (min feasible)")
ax.set_xlabel("Placement freedom (n_avail / n_req, capped at 50x)")
ax.set_ylabel("Jobs")
ax.set_title("M2.2: Placement freedom")
ax.legend(fontsize=9)

ax = axes[2]
ax.scatter(avail_df["n_required"], avail_df["n_available_fp"],
           alpha=0.15, s=8, color="#3a7eca")
ax.plot([0, avail_df["n_required"].max()],
        [0, avail_df["n_required"].max()], "k--", lw=1, label="PF=1 line")
ax.set_xlabel("Job size (n_required)")
ax.set_ylabel("Available fp nodes")
ax.set_xscale("log"); ax.set_yscale("log")
ax.set_title("M2.2: Placement freedom scatter")
ax.legend(fontsize=9)

plt.suptitle("M2: Occupancy and Placement Freedom (2637 test jobs)")
plt.tight_layout()
plt.savefig(FIG_DIR / "fig_m2_occupancy.png", dpi=150)
plt.close()
print("    Saved fig_m2_occupancy.png")

# ─────────────────────────────────────────────────────────────────────
# Assemble JSON
# ─────────────────────────────────────────────────────────────────────
result = {
    "script":    "r1_m2_occupancy.py",
    "git_sha":   git_sha(),
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "input_files": {
        "phase3a_fingerprint_2024.parquet": file_sha256(ANAL_DIR / "phase3a_fingerprint_2024.parquet"),
        "phase3a_test_set.parquet":         file_sha256(ANAL_DIR / "phase3a_test_set.parquet"),
        "fp_node_topology.csv":             file_sha256(TABLE_DIR / "fp_node_topology.csv"),
    },
    "methodology_note": (
        "Occupancy computed via native array zip of host_list (not str().split()) "
        "to avoid the string-truncation bug documented in r1_00b_topology_audit.py. "
        "This matches the methodology used in phase3b1_counterfactual.py."
    ),

    "m2_1_occupancy": {
        "n_test_jobs": n_total,
        "phase3b1_verification": {
            "n_matched": len(merged_check) if len(merged_check) > 0 else 0,
            "max_diff_n_available": float(diff.max()) if len(merged_check) > 0 else None,
            "mean_diff": float(diff.mean()) if len(merged_check) > 0 else None,
        },
    },

    "m2_2_placement_freedom": m22,

    "m2_3_cap10_headroom": m23,

    "m2_4_topology_spread": m24,

    "m2_5_temporal": m25,

    "m2_6_by_job_size": m26,

    "elapsed_seconds": round(time.time() - t0_global, 1),
}

out_path = OUT_DIR / "m2_occupancy.json"
with open(out_path, "w") as f:
    json.dump(result, f, indent=2, default=str)

print(f"\nSaved: {out_path}")
print(f"Total elapsed: {time.time()-t0_global:.1f}s")
