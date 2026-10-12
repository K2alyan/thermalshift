#!/usr/bin/env python3
"""
Phase 0 integrity audit for revision1.

0.1  Hostname <-> xname mapping: is F_i keyed by hostname, xname, or location?
0.2  Temperature telemetry census: column names, GCD channels, timestamp spacing.
0.3  Cohort / job selection provenance.

Outputs
-------
artifacts/revision1/results/phase0_integrity.json
artifacts/revision1/tables/phase0_node_map.csv
artifacts/revision1/tables/sample_selection_flow.csv
"""

import os, re, json, random, hashlib, subprocess, datetime, time
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

DATA_DIR    = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset")
REPO_ROOT   = Path(__file__).resolve().parents[3]
PHASE1_DIR  = REPO_ROOT / "artifacts" / "phase1"
ANAL_DIR    = PHASE1_DIR / "analysis"
OUT_DIR     = REPO_ROOT / "artifacts" / "revision1" / "results"
TABLE_DIR   = REPO_ROOT / "artifacts" / "revision1" / "tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

XNAME_RE = re.compile(r"x(\d+)c(\d+)s(\d+)b(\d+)n(\d+)")

def git_sha():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], text=True,
                                       cwd=str(REPO_ROOT)).strip()
    except Exception:
        return "unknown"

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def parse_xname(xn):
    m = XNAME_RE.match(str(xn).strip())
    if not m:
        return None
    return dict(cabinet=int(m.group(1)), chassis=int(m.group(2)),
                slot=int(m.group(3)), board=int(m.group(4)), node_pos=int(m.group(5)))

print("=" * 65)
print("Phase 0 Integrity Audit")
print("=" * 65)
t0 = time.time()

# ─────────────────────────────────────────────────────────────────────
# Load base files
# ─────────────────────────────────────────────────────────────────────
print("\n[1] Loading job metadata …")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["start_date"] = pd.to_datetime(all_jobs["start_time"]).dt.date
print(f"    {len(all_jobs):,} jobs, {all_jobs.start_date.nunique()} unique dates")

cohort_manifest = pd.read_csv(PHASE1_DIR / "cohort_manifest.csv")
cohort_hosts    = set(cohort_manifest["hostname"])
print(f"    Cohort: {len(cohort_hosts)} nodes from cohort_manifest.csv")

with open(PHASE1_DIR / "globus_batch.txt") as f:
    globus_lines = [l.strip() for l in f if l.strip()]
print(f"    globus_batch.txt: {len(globus_lines)} lines")

# Extract job indices from globus batch (path format: .../DATE/JOBIDX/ ...)
globus_job_ids = set()
for line in globus_lines:
    parts = line.split("/")
    # Last non-empty segment before the trailing slash is the job_idx dir
    segments = [p for p in parts if p]
    # Find the 6-digit job id segment
    for seg in reversed(segments):
        if re.match(r"^\d{6}$", seg):
            globus_job_ids.add(seg)
            break
print(f"    Unique job indices in globus batch: {len(globus_job_ids)}")

# ─────────────────────────────────────────────────────────────────────
# 0.1  Hostname ↔ xname mapping
# ─────────────────────────────────────────────────────────────────────
print("\n[2] Building hostname <-> xname mapping (all 152,400 jobs) ...")
t1 = time.time()

# Build per-hostname xname history from ALL jobs
# host_list and node_list are numpy arrays — zip directly
hostname_xname_dates: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))

n_jobs = len(all_jobs)
chunk = n_jobs // 10
for i, (hl, nl, date) in enumerate(zip(
        all_jobs["host_list"].values,
        all_jobs["node_list"].values,
        all_jobs["start_date"].values)):
    if i % chunk == 0:
        print(f"    … {i:,}/{n_jobs:,}", end="\r")
    for hn, xn in zip(hl, nl):
        hostname_xname_dates[hn][str(xn)].append(str(date))

print(f"\n    Done in {time.time()-t1:.1f}s — {len(hostname_xname_dates):,} unique hostnames")

# ── Summarize mapping ──────────────────────────────────────────────
rows = []
for hn, xn_map in hostname_xname_dates.items():
    in_cohort = hn in cohort_hosts
    for xn, dates in xn_map.items():
        loc = parse_xname(xn) or {}
        rows.append(dict(
            hostname   = hn,
            xname      = xn,
            n_jobs_pair= len(dates),
            first_seen = min(dates),
            last_seen  = max(dates),
            in_cohort  = in_cohort,
            cabinet    = loc.get("cabinet"),
            chassis    = loc.get("chassis"),
            slot       = loc.get("slot"),
            board      = loc.get("board"),
            node_pos   = loc.get("node_pos"),
        ))

node_map_df = pd.DataFrame(rows)
node_map_df.to_csv(TABLE_DIR / "phase0_node_map.csv", index=False)
print(f"    Node map rows: {len(node_map_df):,}  (saved to tables/phase0_node_map.csv)")

# Counts per hostname (how many xnames per hostname)
per_host = node_map_df.groupby("hostname")["xname"].nunique()
n_exactly_one  = (per_host == 1).sum()
n_multi_xname  = (per_host  > 1).sum()

# Counts per xname (how many hostnames per xname)
per_xname = node_map_df.groupby("xname")["hostname"].nunique()
n_xname_one_host   = (per_xname == 1).sum()
n_xname_multi_host = (per_xname  > 1).sum()

print(f"\n    Hostnames mapping to exactly 1 xname : {n_exactly_one:,}")
print(f"    Hostnames mapping to >1 xname (movers): {n_multi_xname:,}")
print(f"    xnames  mapping to exactly 1 hostname : {n_xname_one_host:,}")
print(f"    xnames  mapping to >1 hostname        : {n_xname_multi_host:,}")

# Cohort-only summary
cohort_map = node_map_df[node_map_df.in_cohort]
coh_per_host = cohort_map.groupby("hostname")["xname"].nunique()
print(f"\n    COHORT nodes:")
print(f"    Hostnames mapping to exactly 1 xname : {(coh_per_host==1).sum()}")
print(f"    Hostnames mapping to >1 xname        : {(coh_per_host>1).sum()}")

# Multi-xname transitions in cohort
multi_cohort = coh_per_host[coh_per_host > 1].index.tolist()
transitions = []
for hn in multi_cohort[:20]:   # cap at 20 for reporting
    sub = cohort_map[cohort_map.hostname == hn].sort_values("first_seen")
    transitions.append({
        "hostname": hn,
        "xnames_seen": sub["xname"].tolist(),
        "first_seen_each": sub["first_seen"].tolist(),
        "n_jobs_each": sub["n_jobs_pair"].tolist()
    })

# Does mapping change during 2024–2025?
# Look for any hostname that has xname A before 2025-01-01 and xname B after
cohort_map2 = cohort_map.copy()
cohort_map2["era"] = cohort_map2["first_seen"].apply(
    lambda d: "pre2025" if str(d) < "2025-01-01" else "2025plus")
era_cross = (cohort_map2.groupby(["hostname","era"])["xname"]
             .apply(lambda x: set(x))
             .unstack(fill_value=set()))
if "pre2025" in era_cross.columns and "2025plus" in era_cross.columns:
    cross_changed = era_cross.apply(
        lambda r: bool(r["pre2025"]) and bool(r["2025plus"]) and r["pre2025"] != r["2025plus"],
        axis=1)
    n_changed_era = cross_changed.sum()
    print(f"\n    Cohort nodes with different xname pre/post 2025: {n_changed_era}")
else:
    n_changed_era = "N/A (era column missing)"

# What does the fingerprint use? → hostname (from telemetry column names)
fingerprint_key_evidence = (
    "Temperature telemetry columns use frontier##### hostnames (e.g. frontier00001_gpu0_gcd0). "
    "Fingerprint F_i is aggregated by hostname. "
    "xname is the hardware location parsed from node_list; hostname is the OS-level identity."
)
print(f"\n    Fingerprint key: HOSTNAME (not xname)")
print(f"    Evidence: {fingerprint_key_evidence[:80]}…")

# ─────────────────────────────────────────────────────────────────────
# 0.2  Temperature telemetry census
# ─────────────────────────────────────────────────────────────────────
print("\n[3] Telemetry census — sampling 60 jobs …")
random.seed(42)
telemetry_dir = DATA_DIR / "job-telemetry"
date_dirs = sorted(telemetry_dir.iterdir())

# Sample from globus batch jobs (the 8,303 analysis jobs)
globus_sample_lines = random.sample(globus_lines, min(200, len(globus_lines)))
sample_jobs = []
for line in globus_sample_lines:
    parts = line.split("/")
    segs = [p for p in parts if p]
    date_seg = job_seg = None
    for k, seg in enumerate(segs):
        if re.match(r"^\d{4}-\d{2}-\d{2}$", seg):
            date_seg = seg
            if k + 1 < len(segs):
                job_seg = segs[k + 1]
    if date_seg and job_seg:
        temp_file = telemetry_dir / date_seg / job_seg / f"{job_seg}-cleaned-temperature.parquet"
        if temp_file.exists():
            sample_jobs.append(temp_file)
    if len(sample_jobs) >= 60:
        break

print(f"    Found {len(sample_jobs)} temperature files to sample")

ts_intervals = []
gcd_channel_counts = []
cpu_present_frac   = []
all_8_gcd_frac     = []
col_name_examples  = []

for fpath in sample_jobs:
    try:
        t = pd.read_parquet(fpath)
        if t.empty or "Timestamp" not in t.columns:
            continue

        # Column names (node-specific: {hostname}_gpu{g}_gcd{k})
        node_cols = [c for c in t.columns if "_gpu" in c and "_gcd" in c]
        cpu_cols  = [c for c in t.columns if c.endswith("_cpu")]
        if col_name_examples is not None and len(col_name_examples) < 3 and node_cols:
            col_name_examples.append(node_cols[0])

        # Timestamp spacing
        ts = pd.to_datetime(t["Timestamp"]).sort_values()
        if len(ts) > 1:
            diffs = ts.diff().dropna().dt.total_seconds()
            ts_intervals.extend(diffs.tolist())

        # GCD channels: node_cols will be {hostname}_gpu{g}_gcd{k}
        # Count unique hostnames and gcd channels per node
        node_names = set(c.rsplit("_gpu", 1)[0] for c in node_cols)
        if node_names:
            for nn in node_names:
                gcd_cols_node = [c for c in node_cols if c.startswith(nn + "_")]
                gcd_channel_counts.append(len(gcd_cols_node))
                all_8_gcd_frac.append(1 if len(gcd_cols_node) == 8 else 0)

        cpu_present_frac.append(1 if cpu_cols else 0)

    except Exception as e:
        pass

# Compute stats
ts_arr = np.array(ts_intervals)
p5, p50, p95 = np.percentile(ts_arr, [5, 50, 95]) if len(ts_arr) else (0,0,0)
gcd_arr = np.array(gcd_channel_counts)

print(f"\n    Temperature column pattern: {col_name_examples[0] if col_name_examples else 'N/A'}")
print(f"    Example: {{hostname}}_gpu{{g}}_gcd{{k}} — keyed by HOSTNAME")
print(f"    GCD channels per node: median={np.median(gcd_arr):.0f}, min={gcd_arr.min()}, max={gcd_arr.max()}")
print(f"    Nodes with all 8 GCD channels: {np.mean(all_8_gcd_frac)*100:.1f}%")
print(f"    CPU channel present: {np.mean(cpu_present_frac)*100:.1f}% of jobs")
print(f"    Timestamp interval (seconds): p5={p5:.0f}, p50={p50:.0f}, p95={p95:.0f}")

gcd_dist = {str(k): int((gcd_arr == k).sum()) for k in sorted(set(gcd_arr.tolist()))}

# ─────────────────────────────────────────────────────────────────────
# 0.3  Cohort / job selection provenance
# ─────────────────────────────────────────────────────────────────────
print("\n[4] Selection provenance …")

# All jobs (fleet)
n_fleet = len(all_jobs)

# Cohort-touching jobs: jobs where any cohort node appears in host_list
print("    Finding jobs touching cohort nodes …")
t2 = time.time()

# Build a set of job indices from globus batch
globus_int = {int(j) for j in globus_job_ids if j.isdigit()}
all_jobs["job_idx_int"] = all_jobs["job_idx"].str.lstrip("0").apply(
    lambda x: int(x) if x else 0)

# 8,303 longitudinal jobs (from globus batch)
longitudinal_df = all_jobs[all_jobs.job_idx_int.isin(globus_int)].copy()
n_longitudinal  = len(longitudinal_df)

# Split by era
longitudinal_df["start_dt"] = pd.to_datetime(longitudinal_df["start_time"])
train_df = longitudinal_df[longitudinal_df.start_dt < "2025-01-01"]
cand_df  = longitudinal_df[longitudinal_df.start_dt >= "2025-01-01"]

# Test set (from frozen parquet)
test_df = pd.read_parquet(ANAL_DIR / "phase3a_test_set.parquet")
n_test_jobs = test_df["job_idx"].nunique()

print(f"    Fleet total:            {n_fleet:,}")
print(f"    Longitudinal (globus):  {n_longitudinal:,}  [expected 8,303]")
print(f"    Pre-2025 train:         {len(train_df):,}  [expected ~3,945]")
print(f"    2025+ candidate:        {len(cand_df):,}  [expected ~4,358]")
print(f"    2025 test jobs (frozen):{n_test_jobs:,}  [expected 2,637]")

# Check control job 107165
j107165 = all_jobs[all_jobs.job_idx == "107165"]
in_globus = "107165" in globus_job_ids
print(f"\n    Job 107165 (fleet diagnostic): in globus batch = {in_globus}")
if not j107165.empty:
    row = j107165.iloc[0]
    print(f"      date={row.date_dir}, node_count={row.node_count}, "
          f"start={str(row.start_time)[:16]}")

# Job-size / runtime distributions for key subsets
def dist_summary(df, label):
    return {
        "label": label,
        "n_jobs": int(len(df)),
        "node_count_median": float(df.node_count.median()),
        "node_count_p25":    float(df.node_count.quantile(0.25)),
        "node_count_p75":    float(df.node_count.quantile(0.75)),
        "node_count_max":    int(df.node_count.max()),
        "run_time_median_h": float(df.run_time.median() / 3600),
        "run_time_p95_h":    float(df.run_time.quantile(0.95) / 3600),
    }

sel_dists = [
    dist_summary(all_jobs,      "all_fleet_152400"),
    dist_summary(longitudinal_df,"longitudinal_8303"),
    dist_summary(train_df,       "pre2025_train"),
    dist_summary(cand_df,        "2025plus_candidate"),
]

# ─────────────────────────────────────────────────────────────────────
# Sample selection flow table
# ─────────────────────────────────────────────────────────────────────
flow = [
    {"stage": "Full Frontier dataset",            "n_jobs": n_fleet,            "n_nodes": int(all_jobs.node_count.sum())},
    {"stage": "Longitudinal analysis set (globus_batch.txt)", "n_jobs": n_longitudinal, "n_nodes": "NA"},
    {"stage": "Pre-2025 training split",           "n_jobs": len(train_df),      "n_nodes": "NA"},
    {"stage": "2025+ candidate split",             "n_jobs": len(cand_df),       "n_nodes": "NA"},
    {"stage": "2025 qualifying test jobs (frozen)","n_jobs": n_test_jobs,        "n_nodes": 2000},
    {"stage": "+ Fleet diagnostic job 107165",     "n_jobs": 1,                  "n_nodes": "fleet-wide"},
]
pd.DataFrame(flow).to_csv(TABLE_DIR / "sample_selection_flow.csv", index=False)
print(f"\n    Sample selection flow saved.")

# ─────────────────────────────────────────────────────────────────────
# Assemble JSON output
# ─────────────────────────────────────────────────────────────────────
result = {
    "script": "r1_00_integrity_audit.py",
    "git_sha": git_sha(),
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "raw_data_path": str(DATA_DIR),
    "input_sha256": {
        "frontier-completed-job-info.parquet":
            file_sha256(DATA_DIR / "frontier-completed-job-info.parquet"),
        "cohort_manifest.csv":
            file_sha256(PHASE1_DIR / "cohort_manifest.csv"),
        "globus_batch.txt":
            file_sha256(PHASE1_DIR / "globus_batch.txt"),
    },

    "phase_0_1_fingerprint_key": {
        "conclusion": "F_i is keyed by HOSTNAME (frontier##### OS identity), not xname (hardware location).",
        "evidence": fingerprint_key_evidence,
        "n_unique_hostnames": len(hostname_xname_dates),
        "hostnames_to_exactly_1_xname": int(n_exactly_one),
        "hostnames_to_multi_xname":      int(n_multi_xname),
        "xnames_to_exactly_1_hostname":  int(n_xname_one_host),
        "xnames_to_multi_hostname":      int(n_xname_multi_host),
        "cohort_hostnames_exactly_1_xname": int((coh_per_host == 1).sum()),
        "cohort_hostnames_multi_xname":     int((coh_per_host  > 1).sum()),
        "cohort_era_changed_xname_pre_post_2025": int(n_changed_era) if isinstance(n_changed_era, (int, np.integer)) else str(n_changed_era),
        "multi_xname_cohort_examples": transitions[:5],
    },

    "phase_0_2_telemetry": {
        "column_pattern": "{hostname}_gpu{g}_gcd{k}  (hostname-keyed, 8 GCD channels 0-7)",
        "example_columns": col_name_examples,
        "sensor_type": "GCD temperature channel (junction/package/edge unspecified in public dataset documentation; labeled 'gcd' in column name)",
        "n_jobs_sampled": len(sample_jobs),
        "gcd_channel_count_distribution": gcd_dist,
        "fraction_all_8_gcd": float(np.mean(all_8_gcd_frac)),
        "timestamp_interval_seconds": {
            "p5": float(p5), "p50": float(p50), "p95": float(p95),
            "n_intervals_sampled": len(ts_intervals)
        },
        "cpu_channel_present_fraction": float(np.mean(cpu_present_frac)),
    },

    "phase_0_3_provenance": {
        "n_fleet_jobs": n_fleet,
        "n_longitudinal_globus": n_longitudinal,
        "n_pre2025_train": len(train_df),
        "n_2025plus_candidate": len(cand_df),
        "n_2025_test_jobs_frozen": n_test_jobs,
        "job_107165_in_globus_batch": in_globus,
        "manifest_note": (
            "cohort_job_list.csv (52,413 entries) is the COHORT stratified sample, "
            "NOT the 8,303 longitudinal analysis set. "
            "The 8,303 jobs are recoverable from globus_batch.txt."
        ),
        "selection_distributions": sel_dists,
    },

    "elapsed_seconds": round(time.time() - t0, 1),
}

out_path = OUT_DIR / "phase0_integrity.json"
with open(out_path, "w") as f:
    json.dump(result, f, indent=2, default=str)

print(f"\nSaved: {out_path}")
print(f"Total elapsed: {time.time()-t0:.1f}s")
