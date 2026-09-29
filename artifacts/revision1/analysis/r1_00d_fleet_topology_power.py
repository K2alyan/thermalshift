#!/usr/bin/env python3
"""
Gate C: Full-Fleet Topology Correction + Cabinet Power Rebuild
=============================================================
The existing r1_00b_topology_audit.py quantified the string-truncation bug
only for the 2,000 fp analysis nodes. This script:

A. Quantifies the full-fleet bug across ALL 9,856 fleet nodes.
B. Saves a canonical fleet_node_topology.csv (correct cabinet for each node).
C. Computes per-cabinet node counts before/after correction.
D. Builds per-cabinet historical power distribution from job metadata
   (uniform node-power approximation: P_cab_j = n_nodes_cab_j * ppn_j).
E. Computes per-cabinet p99 power envelopes and exposure budget.
F. Runs 60-job power validation (20 small + 20 medium + 20 large)
   comparing uniform vs actual per-node power telemetry with CORRECT topology.

Outputs
-------
  artifacts/revision1/results/fleet_topology.json     (Gate C main result)
  artifacts/revision1/tables/fleet_node_topology.csv  (all nodes, correct map)
  artifacts/revision1/tables/cabinet_before_after.csv (per-cabinet comparison)
  artifacts/revision1/results/cabinet_power_envelopes.json (p99 per cabinet)
  artifacts/revision1/results/power_validation_60job.json  (60-job validation)
"""

import re, json, hashlib, subprocess, datetime, time
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

DATA_DIR   = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset")
TELE_DIR   = DATA_DIR / "job-telemetry"
REPO_ROOT  = Path(__file__).resolve().parents[3]
PHASE1_DIR = REPO_ROOT / "artifacts" / "phase1"
ANAL_DIR   = PHASE1_DIR / "analysis"
REV1_DIR   = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR    = REV1_DIR / "results"
TABLE_DIR  = REV1_DIR / "tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

XNAME_RE       = re.compile(r"x(\d+)c(\d+)s(\d+)b(\d+)n(\d+)")
CAB_RE         = re.compile(r"x(\d+)c")
NODE_POWER_RE  = re.compile(r"^(frontier\d+)_node$")
SMALL_MAX      = 64
MEDIUM_MAX     = 512
N_PER_TIER     = 20      # 20 each = 60 jobs total
NUMPY_THRESH   = 1000

def git_sha():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=str(REPO_ROOT)).strip()
    except Exception:
        return "unknown"

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def jf(v):
    if v is None:
        return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f

print("=" * 65)
print("Gate C: Full-Fleet Topology + Cabinet Power Rebuild")
print("=" * 65)
t0 = time.time()

# ── Load metadata ──────────────────────────────────────────────────
print("\n[0] Loading job metadata ...")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
n_jobs   = len(all_jobs)
n_truncated = int((all_jobs["node_count"] > NUMPY_THRESH).sum())
print(f"    Total jobs:           {n_jobs:,}")
print(f"    Truncated (nc>{NUMPY_THRESH}): {n_truncated:,} ({100*n_truncated/n_jobs:.1f}%)")

fp_df   = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
fp_nodes = set(fp_df.index)
print(f"    fp analysis nodes:    {len(fp_nodes)}")

# ── A. Correct full-fleet node→cabinet map (set-based, matches r1_00b) ──────
print("\n[A] Building CORRECT full-fleet node->cabinet map ...")
t1 = time.time()
correct_xnames_set: dict[str, set] = defaultdict(set)  # accumulate all xnames
n_len_mismatch = 0

for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    if len(hl) != len(nl):
        n_len_mismatch += 1
        continue
    for hn, xn in zip(hl, nl):
        correct_xnames_set[str(hn)].add(str(xn))

# Derive cabinet from set (correct map should be 1:1; set has one element per node)
correct_xname: dict[str, str] = {}
correct_cab:   dict[str, int] = {}
for hn, xns in correct_xnames_set.items():
    for xn in xns:
        m_full = XNAME_RE.match(xn)
        m_cab  = CAB_RE.match(xn)
        if m_full:
            correct_xname[hn] = xn
            correct_cab[hn]   = int(m_full.group(1))
            break
        elif m_cab:
            correct_cab[hn] = int(m_cab.group(1))
            break

print(f"    Done in {time.time()-t1:.1f}s")
print(f"    Unique hostnames (correct): {len(correct_cab):,}")
print(f"    Multi-xname nodes (correct): {sum(1 for xns in correct_xnames_set.values() if len(xns)>1)}")
print(f"    len-mismatch jobs: {n_len_mismatch}")
correct_cabinets = sorted(set(correct_cab.values()))
print(f"    Unique cabinets:   {len(correct_cabinets)}")

# ── B. Buggy map (set-based, matches r1_00b approach) ─────────────
print("\n[B] Building BUGGY node->cabinet map ...")
t2 = time.time()
buggy_xnames_set: dict[str, set] = defaultdict(set)
n_ellipsis = 0

for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    xn_list = str(nl).split()
    for hn, xn_raw in zip(hl, xn_list):
        xn = xn_raw.strip("'[]\"")
        if xn == "...":
            n_ellipsis += 1
            continue
        buggy_xnames_set[str(hn)].add(xn)

buggy_cab: dict[str, int] = {}
for hn, xns in buggy_xnames_set.items():
    for xn in xns:
        m = CAB_RE.match(xn)
        if m:
            buggy_cab[hn] = int(m.group(1))
            break

buggy_multi_count = sum(1 for xns in buggy_xnames_set.values() if len(xns) > 1)
print(f"    Done in {time.time()-t2:.1f}s")
print(f"    Unique hostnames (buggy): {len(buggy_cab):,}")
print(f"    Multi-xname nodes (buggy, false): {buggy_multi_count:,}")
print(f"    Ellipsis hits:            {n_ellipsis:,}")

# ── C. Before/after comparison ─────────────────────────────────────
print("\n[C] Full-fleet before/after comparison ...")

n_correct_only  = 0
n_buggy_only    = 0
n_wrong_cab     = 0
n_correct_cab   = 0

for hn in correct_cab:
    if hn not in buggy_cab:
        n_correct_only += 1
    elif correct_cab[hn] != buggy_cab[hn]:
        n_wrong_cab += 1
    else:
        n_correct_cab += 1
for hn in buggy_cab:
    if hn not in correct_cab:
        n_buggy_only += 1

print(f"    Fleet nodes in correct map:     {len(correct_cab):,}")
print(f"    Fleet nodes in buggy map:       {len(buggy_cab):,}")
print(f"    Cabinet correct in both:        {n_correct_cab:,}")
print(f"    Cabinet WRONG in buggy:         {n_wrong_cab:,}  ({100*n_wrong_cab/max(1,len(correct_cab)):.1f}%)")
print(f"    Missing from buggy (correct-only): {n_correct_only:,}")
print(f"    Spurious in buggy (buggy-only):    {n_buggy_only:,}")

# FP analysis nodes specifically
fp_wrong = sum(1 for hn in fp_nodes
               if hn in correct_cab and hn in buggy_cab
               and correct_cab[hn] != buggy_cab[hn])
fp_missing = sum(1 for hn in fp_nodes
                 if hn in correct_cab and hn not in buggy_cab)
print(f"\n    FP analysis nodes (2000):")
print(f"      Cabinet WRONG in buggy:  {fp_wrong}")
print(f"      Missing from buggy:      {fp_missing}")

# Per-cabinet node count comparison
per_cab_correct = defaultdict(int)
per_cab_buggy   = defaultdict(int)
for hn, c in correct_cab.items():
    per_cab_correct[c] += 1
for hn, c in buggy_cab.items():
    per_cab_buggy[c]   += 1

cab_rows = []
for c in correct_cabinets:
    n_corr  = per_cab_correct[c]
    n_bug   = per_cab_buggy.get(c, 0)
    cab_rows.append({
        "cabinet":    c,
        "n_correct":  n_corr,
        "n_buggy":    n_bug,
        "delta":      n_corr - n_bug,
    })
cab_df = pd.DataFrame(cab_rows)
cab_df_path = TABLE_DIR / "cabinet_before_after.csv"
cab_df.to_csv(cab_df_path, index=False)

cab_count_correct = np.array([r["n_correct"] for r in cab_rows])
cab_count_buggy   = np.array([r["n_buggy"]   for r in cab_rows])
print(f"\n    Per-cabinet node count (correct): "
      f"min={cab_count_correct.min()}  median={int(np.median(cab_count_correct))}  "
      f"max={cab_count_correct.max()}")
print(f"    Per-cabinet node count (buggy):   "
      f"min={cab_count_buggy.min()}  median={int(np.median(cab_count_buggy))}  "
      f"max={cab_count_buggy.max()}")
delta_arr = np.abs(cab_count_correct - cab_count_buggy)
print(f"    |delta| per cabinet: mean={delta_arr.mean():.1f}  max={delta_arr.max()}")
print(f"    Saved: {cab_df_path.name}")

# ── D. Per-cabinet power distribution from job metadata ───────────
print("\n[D] Per-cabinet power distribution from job metadata ...")
# Use uniform approximation: P_cab_j = ppn_j * n_nodes_in_cab_j
# where ppn_j = mean_power_j / node_count_j

jobs_with_power = all_jobs.dropna(subset=["mean_power"]).copy()
jobs_with_power = jobs_with_power[jobs_with_power["mean_power"].astype(float) > 0].copy()
jobs_with_power["mean_power_f"] = jobs_with_power["mean_power"].astype(float)
jobs_with_power["node_count_i"] = jobs_with_power["node_count"].astype(int)
print(f"    Jobs with mean_power: {len(jobs_with_power):,}")

# For each job, count fp-node occupancy per cabinet (correct topology)
# Accumulate: for each cabinet, list of (P_cab_j, run_time_h) pairs
cab_power_correct: dict[int, list] = defaultdict(list)
cab_power_buggy:   dict[int, list] = defaultdict(list)

t3 = time.time()
n_proc = 0
for _, jrow in jobs_with_power.iterrows():
    ppn = float(jrow["mean_power_f"]) / max(1, int(jrow["node_count_i"]))
    rt_h = float(jrow.get("run_time", 0)) / 3600.0

    hl = jrow["host_list"]

    # Correct
    cnt_c: dict[int, int] = defaultdict(int)
    for hn in hl:
        c = correct_cab.get(str(hn), -1)
        if c >= 0:
            cnt_c[c] += 1
    for c, n in cnt_c.items():
        cab_power_correct[c].append((ppn * n, rt_h))

    # Buggy (replicated buggy map)
    cnt_b: dict[int, int] = defaultdict(int)
    for hn in hl:
        c = buggy_cab.get(str(hn), -1)
        if c >= 0:
            cnt_b[c] += 1
    for c, n in cnt_b.items():
        cab_power_buggy[c].append((ppn * n, rt_h))

    n_proc += 1
    if n_proc % 10000 == 0:
        print(f"    ... {n_proc:,}/{len(jobs_with_power):,}", end="\r")

print(f"\n    Done in {time.time()-t3:.1f}s")

# ── E. Per-cabinet p99 power envelopes + exposure budget ──────────
print("\n[E] Per-cabinet p99 power envelopes + exposure budget ...")

# Exposure budget: fraction of total job-weighted time where P_cab > threshold
# We use the median observed single-node power * 128 nodes as the "full-cabinet" threshold
# The published ~148 kW full-cabinet power corresponds to 128 nodes at ~1157 W/node
# Use per-cabinet p99 from correct map as the policy constraint.
# We do NOT apply a fixed threshold here; instead report p99 per cabinet.

env_rows = []
for c in correct_cabinets:
    pw_corr = cab_power_correct.get(c, [])
    pw_bug  = cab_power_buggy.get(c, [])

    vals_c  = np.array([v for v, _ in pw_corr]) if pw_corr else np.array([])
    vals_b  = np.array([v for v, _ in pw_bug])  if pw_bug  else np.array([])
    rt_c    = np.array([h for _, h in pw_corr]) if pw_corr else np.array([])

    p99_c   = float(np.percentile(vals_c,  99)) if len(vals_c)  >= 10 else np.nan
    p99_b   = float(np.percentile(vals_b,  99)) if len(vals_b)  >= 10 else np.nan
    p50_c   = float(np.percentile(vals_c,  50)) if len(vals_c)  >= 10 else np.nan
    max_c   = float(vals_c.max())                if len(vals_c)   > 0 else np.nan

    env_rows.append({
        "cabinet":        c,
        "n_obs_correct":  len(vals_c),
        "n_obs_buggy":    len(vals_b),
        "p50_kW_correct": jf(p50_c / 1000) if not np.isnan(p50_c) else None,
        "p99_kW_correct": jf(p99_c / 1000) if not np.isnan(p99_c) else None,
        "max_kW_correct": jf(max_c / 1000) if not np.isnan(max_c) else None,
        "p99_kW_buggy":   jf(p99_b / 1000) if not np.isnan(p99_b) else None,
        "delta_p99_kW":   jf((p99_c - p99_b) / 1000) if not np.isnan(p99_c) and not np.isnan(p99_b) else None,
    })

env_df = pd.DataFrame(env_rows)
valid_p99 = env_df["p99_kW_correct"].dropna()
delta_p99 = env_df["delta_p99_kW"].dropna()

print(f"    Per-cabinet p99 power (correct, kW):")
print(f"      min={valid_p99.min():.1f}  median={valid_p99.median():.1f}  "
      f"p95={valid_p99.quantile(0.95):.1f}  max={valid_p99.max():.1f}")
print(f"    Delta p99 (correct - buggy, kW):")
print(f"      mean={delta_p99.mean():+.1f}  max={delta_p99.max():+.1f}  "
      f"min={delta_p99.min():+.1f}  |delta|>50kW: {(delta_p99.abs()>50).sum()}")

# ── F. 60-job power validation (correct topology) ─────────────────
print("\n[F] 60-job power validation (correct topology) ...")

if "date_dir" not in jobs_with_power.columns:
    jobs_with_power["date_dir"] = (
        pd.to_datetime(jobs_with_power["start_time"], utc=True)
        .dt.strftime("%Y-%m-%d"))

def tele_path(date_dir, job_idx):
    jid = str(int(job_idx)).zfill(6)
    return TELE_DIR / str(date_dir) / jid / f"{jid}-cleaned-power.parquet"

def classify_size(nc):
    if nc <= SMALL_MAX:  return "small"
    if nc <= MEDIUM_MAX: return "medium"
    return "large"

jobs_with_power["size_tier"] = jobs_with_power["node_count_i"].apply(classify_size)

selected = []
for tier in ["small", "medium", "large"]:
    tier_jobs = (jobs_with_power[jobs_with_power["size_tier"] == tier]
                 .sort_values("mean_power_f", ascending=False)
                 .reset_index(drop=True))
    count = 0
    for _, jrow in tier_jobs.iterrows():
        if count >= N_PER_TIER:
            break
        p = tele_path(jrow["date_dir"], jrow["job_idx"])
        if p.exists():
            selected.append(jrow)
            count += 1
    print(f"    {tier:6s}: {count} jobs selected")

print(f"    Total selected: {len(selected)}")

tier_stats: dict[str, dict] = {t: {"abs": [], "rel": [], "rho": []} for t in ["small", "medium", "large"]}
all_abs: list[float] = []
all_rel: list[float] = []
all_rho: list[float] = []
n_val_ok = 0
n_val_correct_diff = 0   # jobs where correction changes result

for jrow in selected:
    tier = classify_size(int(jrow["node_count_i"]))
    p = tele_path(jrow["date_dir"], jrow["job_idx"])
    try:
        telem = pd.read_parquet(p)
    except Exception as e:
        print(f"    WARNING: {p.name}: {e}")
        continue

    # Per-cabinet actual power with CORRECT topology
    col_to_cab_correct: dict[str, int] = {}
    col_to_cab_buggy:   dict[str, int] = {}
    for col in telem.columns:
        m = NODE_POWER_RE.match(col)
        if m:
            hn = m.group(1)
            cc = correct_cab.get(hn, -1)
            cb = buggy_cab.get(hn, -1)
            if cc >= 0: col_to_cab_correct[col] = cc
            if cb >= 0: col_to_cab_buggy[col]   = cb

    if not col_to_cab_correct:
        continue

    cab_actual_correct: dict[int, float] = defaultdict(float)
    for col, c in col_to_cab_correct.items():
        vals = telem[col].dropna().values.astype(float)
        if len(vals) > 0:
            cab_actual_correct[c] += float(np.mean(vals))

    # Uniform approximation with correct topology
    P_j   = float(jrow["mean_power_f"])
    N_j   = max(1, int(jrow["node_count_i"]))
    ppn   = P_j / N_j
    cnt_c: dict[int, int] = defaultdict(int)
    for hn in jrow["host_list"]:
        c = correct_cab.get(str(hn), -1)
        if c >= 0:
            cnt_c[c] += 1
    cab_uniform_correct = {c: ppn * n for c, n in cnt_c.items()}

    common = sorted(set(cab_actual_correct) & set(cab_uniform_correct))
    if not common:
        continue

    acts = np.array([cab_actual_correct[c]  for c in common])
    unis = np.array([cab_uniform_correct[c] for c in common])
    ae   = np.abs(unis - acts)
    re_  = ae / np.maximum(acts, 1.0)

    tier_stats[tier]["abs"].extend(ae.tolist())
    tier_stats[tier]["rel"].extend(re_.tolist())
    all_abs.extend(ae.tolist())
    all_rel.extend(re_.tolist())

    if len(common) >= 2:
        rx = np.empty(len(acts), dtype=float)
        rx[np.argsort(acts)] = np.arange(len(acts), dtype=float)
        ry = np.empty(len(unis), dtype=float)
        ry[np.argsort(unis)] = np.arange(len(unis), dtype=float)
        mx, my = rx.mean(), ry.mean()
        num = ((rx - mx) * (ry - my)).sum()
        den = np.sqrt(((rx - mx)**2).sum() * ((ry - my)**2).sum())
        rho = float(num / den) if den > 0 else float("nan")
        if not np.isnan(rho):
            tier_stats[tier]["rho"].append(rho)
            all_rho.append(rho)

    n_val_ok += 1

print(f"\n    Validated {n_val_ok} jobs")

def pct(vals, p):
    return float(np.percentile(vals, p)) if len(vals) > 0 else np.nan

val_summary_by_tier = {}
for tier in ["small", "medium", "large"]:
    d = tier_stats[tier]
    ae, re_, rho_l = np.array(d["abs"]), np.array(d["rel"]), np.array(d.get("rho", []))
    if len(ae) == 0:
        continue
    print(f"\n    {tier.upper()} ({len(ae)} cab-job pairs):")
    print(f"      MAE={np.mean(ae)/1e3:.2f} kW  MRE={np.mean(re_):.1%}  "
          f"p95_abs={pct(ae,95)/1e3:.2f} kW  "
          f"rho_med={np.median(rho_l):.3f}" if len(rho_l) else "")
    val_summary_by_tier[tier] = {
        "n_cab_job_pairs": len(ae),
        "mae_kW":       jf(np.mean(ae) / 1e3),
        "mean_rel_err": jf(np.mean(re_)),
        "p95_abs_kW":   jf(pct(ae, 95) / 1e3),
        "spearman_rho_median": jf(float(np.median(rho_l))) if len(rho_l) else None,
        "pct_rho_ge_09": jf(float(np.mean(rho_l >= 0.9))) if len(rho_l) else None,
    }

all_ae  = np.array(all_abs)
all_re  = np.array(all_rel)
all_rho_arr = np.array(all_rho)
print(f"\n    OVERALL ({len(all_ae)} cab-job pairs):")
print(f"      MAE={np.mean(all_ae)/1e3:.2f} kW  MRE={np.mean(all_re):.1%}  "
      f"p95_abs={pct(all_ae,95)/1e3:.2f} kW")
if len(all_rho_arr) > 0:
    print(f"      Spearman rho: mean={np.mean(all_rho_arr):.3f}  "
          f"median={np.median(all_rho_arr):.3f}  "
          f"p10={pct(all_rho_arr,10):.3f}  "
          f">=0.9: {np.mean(all_rho_arr>=0.9):.0%}")

# ── Assemble results ────────────────────────────────────────────────
fleet_topology_summary = {
    "n_fleet_nodes_correct": len(correct_cab),
    "n_fleet_nodes_buggy":   len(buggy_cab),
    "n_cabinets":            len(correct_cabinets),
    "n_correct_cab_in_both": n_correct_cab,
    "n_wrong_cab_in_buggy":  n_wrong_cab,
    "pct_wrong_cab":         jf(100 * n_wrong_cab / max(1, len(correct_cab))),
    "n_missing_from_buggy":  n_correct_only,
    "ellipsis_hits":         n_ellipsis,
    "fp_analysis_nodes_2000": {
        "n_wrong_cabinet_in_buggy":  fp_wrong,
        "n_missing_in_buggy":        fp_missing,
    },
}

print(f"\n[G] Saving fleet_node_topology.csv ...")
fleet_topo_rows = []
for hn in sorted(correct_cab.keys()):
    xn  = correct_xname.get(hn, "")
    m   = XNAME_RE.match(xn) if xn else None
    cab = correct_cab[hn]
    chassis = int(m.group(2)) if m else None
    slot    = int(m.group(3)) if m else None
    board   = int(m.group(4)) if m else None
    node_pos= int(m.group(5)) if m else None
    fleet_topo_rows.append({
        "hostname":       hn,
        "xname":          xn or None,
        "cabinet":        cab,
        "chassis":        chassis,
        "slot":           slot,
        "board":          board,
        "node_pos":       node_pos,
        "cabinet_buggy":  buggy_cab.get(hn),
        "cabinet_matches":  (correct_cab.get(hn) == buggy_cab.get(hn)),
        "is_fp_node":     (hn in fp_nodes),
    })
fleet_topo_df = pd.DataFrame(fleet_topo_rows)
fleet_topo_df.to_csv(TABLE_DIR / "fleet_node_topology.csv", index=False)
print(f"    Saved {len(fleet_topo_df):,} rows -> fleet_node_topology.csv")
print(f"    Nodes with full xname:  {fleet_topo_df['xname'].notna().sum():,}")
print(f"    fp nodes covered:       {fleet_topo_df['is_fp_node'].sum():,}")

# JSON outputs
power_env_json = {
    "method": (
        "Uniform node-power approximation: P_cab_j = (mean_power_j / node_count_j) "
        "* n_nodes_in_cab_j, where n_nodes_in_cab_j uses the CORRECT topology. "
        "Applied to all jobs with reported mean_power > 0."
    ),
    "n_jobs_used": len(jobs_with_power),
    "per_cabinet_p99_kW_correct": {
        str(r["cabinet"]): r["p99_kW_correct"]
        for _, r in env_df.iterrows()
        if r["p99_kW_correct"] is not None
    },
    "fleet_p99_kW": jf(valid_p99.max()),
    "summary_correct": {
        "median_cab_p99_kW": jf(float(valid_p99.median())),
        "max_cab_p99_kW":    jf(float(valid_p99.max())),
        "min_cab_p99_kW":    jf(float(valid_p99.min())),
    },
    "summary_delta_vs_buggy": {
        "mean_delta_p99_kW": jf(float(delta_p99.mean())) if len(delta_p99) else None,
        "max_delta_p99_kW":  jf(float(delta_p99.max()))  if len(delta_p99) else None,
        "min_delta_p99_kW":  jf(float(delta_p99.min()))  if len(delta_p99) else None,
        "cabinets_with_abs_delta_gt_50kW": int((delta_p99.abs() > 50).sum()),
    },
}

val_json = {
    "n_jobs_selected": len(selected),
    "n_jobs_ok": n_val_ok,
    "jobs_per_tier": N_PER_TIER,
    "topology": "CORRECT (native array zip)",
    "by_tier": val_summary_by_tier,
    "overall": {
        "n_cab_job_pairs": len(all_ae),
        "mae_kW":          jf(float(np.mean(all_ae)) / 1e3) if len(all_ae) else None,
        "mean_rel_err":    jf(float(np.mean(all_re)))       if len(all_re) else None,
        "p95_abs_kW":      jf(pct(all_ae, 95) / 1e3)        if len(all_ae) else None,
        "spearman_rho_mean":   jf(float(np.mean(all_rho_arr)))   if len(all_rho_arr) else None,
        "spearman_rho_median": jf(float(np.median(all_rho_arr))) if len(all_rho_arr) else None,
        "pct_rho_ge_09":       jf(float(np.mean(all_rho_arr >= 0.9))) if len(all_rho_arr) else None,
    },
}

result = {
    "script":    "r1_00d_fleet_topology_power.py",
    "git_sha":   git_sha(),
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "input_sha256": {
        "frontier-completed-job-info.parquet":
            file_sha256(DATA_DIR / "frontier-completed-job-info.parquet"),
        "phase3a_fingerprint_2024.parquet":
            file_sha256(ANAL_DIR / "phase3a_fingerprint_2024.parquet"),
    },
    "full_fleet_topology": fleet_topology_summary,
    "cabinet_before_after_note": (
        "cabinet_before_after.csv shows per-cabinet node counts under correct "
        "vs buggy topology. Large |delta| values indicate cabinets whose power "
        "budget and thermal headroom estimates were most corrupted by the bug."
    ),
    "cabinet_power_envelopes": power_env_json,
    "power_validation_60job": val_json,
    "elapsed_seconds": round(time.time() - t0, 1),
}

out_a = OUT_DIR / "fleet_topology.json"
out_b = OUT_DIR / "cabinet_power_envelopes.json"
out_c = OUT_DIR / "power_validation_60job.json"

with open(out_a, "w") as f:
    json.dump(result, f, indent=2)
with open(out_b, "w") as f:
    json.dump(power_env_json, f, indent=2)
with open(out_c, "w") as f:
    json.dump(val_json, f, indent=2)

print(f"\nSaved: {out_a.name}, {out_b.name}, {out_c.name}")
print(f"Total elapsed: {time.time()-t0:.1f}s")
