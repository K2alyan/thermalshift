#!/usr/bin/env python3
"""
Phase 0 supplement:
  (a) Exhaustive GCD channel census across all analysis jobs
  (b) 4,358 -> 2,637 exclusion waterfall

Inputs
------
  - globus_batch.txt  (8,304 jobs = 8,303 longitudinal + job 107165)
  - phase3a_fingerprint_2024.parquet  (authoritative fp node set)
  - phase3a_test_set.parquet  (2,637 qualifying test jobs)
  - frontier-completed-job-info.parquet  (date_dir lookup)
  - Frontier telemetry files

Outputs
-------
  artifacts/revision1/results/phase0c_gcd_waterfall.json
  artifacts/revision1/tables/waterfall_4358_to_2637.csv
"""

import re, json, hashlib, subprocess, datetime, time
import numpy as np
import pandas as pd
from pathlib import Path

DATA_DIR   = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset")
TELE_DIR   = DATA_DIR / "job-telemetry"
REPO_ROOT  = Path(__file__).resolve().parents[3]
PHASE1_DIR = REPO_ROOT / "artifacts" / "phase1"
ANAL_DIR   = PHASE1_DIR / "analysis"
OUT_DIR    = REPO_ROOT / "artifacts" / "revision1" / "results"
TABLE_DIR  = REPO_ROOT / "artifacts" / "revision1" / "tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

MIN_VALID_TS  = 5    # min valid timestamps per node-job (matches phase3a_validation.py)
MIN_FP_NODES  = 3    # min fingerprinted nodes per job

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

def temp_path(date_dir, job_idx):
    job_str = str(int(job_idx)).zfill(6)
    return TELE_DIR / str(date_dir) / job_str / f"{job_str}-cleaned-temperature.parquet"

print("=" * 65)
print("Phase 0C: GCD Census + 4358->2637 Waterfall")
print("=" * 65)
t0 = time.time()

# ── Load reference data ────────────────────────────────────────────
print("\n[0] Loading reference data ...")
fp_df   = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
test_df = pd.read_parquet(ANAL_DIR / "phase3a_test_set.parquet")
fp_nodes = set(fp_df.index)

all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].str.lstrip("0").apply(
    lambda x: int(x) if x else 0)
date_lookup = all_jobs.set_index("job_idx_int")["date_dir"].to_dict()

qualifying_job_ids = set(test_df["job_idx"].astype(int).unique())
print(f"    fp_nodes: {len(fp_nodes)}")
print(f"    qualifying test jobs: {len(qualifying_job_ids)}")

# ── Parse globus_batch.txt ─────────────────────────────────────────
print("\n[1] Parsing globus_batch.txt ...")
with open(PHASE1_DIR / "globus_batch.txt") as f:
    lines = [l.strip() for l in f if l.strip()]

# Extract (date_dir, job_idx) from each line
# Format: .../job-telemetry/YYYY-MM-DD/JOBIDX/ ...
date_re = re.compile(r"(\d{4}-\d{2}-\d{2})/(\d{6})")
globus_jobs = []
for line in lines:
    m = date_re.search(line)
    if m:
        globus_jobs.append({"date_dir": m.group(1), "job_idx": int(m.group(2))})

globus_df = pd.DataFrame(globus_jobs).drop_duplicates("job_idx")
print(f"    Total globus jobs: {len(globus_df)}")

train_df_g = globus_df[globus_df["date_dir"] < "2025"].copy()
cand_df_g  = globus_df[globus_df["date_dir"] >= "2025"].copy()

# Exclude fleet diagnostic job 107165 from candidate set
DIAG_JOB = 107165
cand_df_g = cand_df_g[cand_df_g["job_idx"] != DIAG_JOB].copy()

print(f"    Pre-2025 train jobs:  {len(train_df_g)}")
print(f"    2025+ candidate jobs: {len(cand_df_g)}  (excl. diagnostic 107165)")

# ── (b) 4,358 -> 2,637 waterfall ───────────────────────────────────
print(f"\n[2] Waterfall: {len(cand_df_g)} candidates -> 2,637 qualifying ...")

n_total = len(cand_df_g)
n_missing_file    = 0
n_no_fp_cols      = 0
n_lt_min_nodes    = 0
n_all_ts_short    = 0
n_qualified       = 0
waterfall_rows    = []

for i, row in cand_df_g.iterrows():
    jid      = row["job_idx"]
    date_dir = row["date_dir"]
    fpath    = temp_path(date_dir, jid)

    status = None
    if not fpath.exists():
        n_missing_file += 1
        status = "missing_telemetry"
    else:
        try:
            temp = pd.read_parquet(fpath)
            # Find GCD columns for fp nodes
            gcd_cols = [c for c in temp.columns
                        if c.startswith("frontier") and "_gcd" in c
                        and c.split("_")[0] in fp_nodes]
            if not gcd_cols:
                n_no_fp_cols += 1
                status = "no_fp_gcd_cols"
            else:
                # Group columns by node
                node_cols: dict[str, list] = {}
                for c in gcd_cols:
                    node_cols.setdefault(c.split("_")[0], []).append(c)

                if len(node_cols) < MIN_FP_NODES:
                    n_lt_min_nodes += 1
                    status = f"lt_{MIN_FP_NODES}_fp_nodes"
                else:
                    # Check if any node has >= MIN_VALID_TS valid timestamps
                    has_valid_node = False
                    for node, ncols in node_cols.items():
                        ts_means = np.nanmean(temp[ncols].values.astype(float), axis=1)
                        valid_ts = np.sum(np.isfinite(ts_means))
                        if valid_ts >= MIN_VALID_TS:
                            has_valid_node = True
                            break
                    if not has_valid_node:
                        n_all_ts_short += 1
                        status = "all_nodes_lt_5_valid_ts"
                    else:
                        n_qualified += 1
                        status = "qualified"
        except Exception as e:
            n_missing_file += 1
            status = f"read_error: {str(e)[:40]}"

    if i % 200 == 0:
        print(f"    ... {i - cand_df_g.index[0]} / {n_total} "
              f"(qual so far: {n_qualified})", end="\r")

    waterfall_rows.append({"job_idx": jid, "date_dir": date_dir,
                            "status": status,
                            "in_test_set": jid in qualifying_job_ids})

print(f"\n    Done. Qualified: {n_qualified}")

wf_df = pd.DataFrame(waterfall_rows)
wf_df.to_csv(TABLE_DIR / "waterfall_4358_to_2637.csv", index=False)

# Reconcile with frozen test_set
qual_found   = set(wf_df[wf_df.status == "qualified"]["job_idx"].astype(int))
in_test_not_qual = qualifying_job_ids - qual_found
qual_not_in_test = qual_found - qualifying_job_ids

print(f"\n    Waterfall reconciliation:")
print(f"      Waterfall says 'qualified': {len(qual_found)}")
print(f"      In frozen test_set:         {len(qualifying_job_ids)}")
print(f"      In test_set but not qualified by waterfall: {len(in_test_not_qual)}")
print(f"      Qualified by waterfall but not in test_set: {len(qual_not_in_test)}")

waterfall_summary = {
    "n_candidate_2025": n_total,
    "n_missing_telemetry":    n_missing_file,
    "n_no_fp_gcd_cols":       n_no_fp_cols,
    "n_lt_min_nodes":         n_lt_min_nodes,
    "n_all_ts_short":         n_all_ts_short,
    "n_qualified":            n_qualified,
    "n_frozen_test_set":      len(qualifying_job_ids),
    "reconciliation_gap":     abs(n_qualified - len(qualifying_job_ids)),
    "min_fp_nodes_threshold": MIN_FP_NODES,
    "min_valid_ts_threshold": MIN_VALID_TS,
}

for k, v in waterfall_summary.items():
    if k not in ("min_fp_nodes_threshold", "min_valid_ts_threshold", "reconciliation_gap"):
        print(f"    {k}: {v}")

# ── (a) Exhaustive GCD channel census ─────────────────────────────
print(f"\n[3] GCD channel census (train sample + all test jobs) ...")

# Sample 500 training jobs
rng = np.random.default_rng(42)
train_sample = train_df_g.sample(n=min(500, len(train_df_g)), random_state=42)

def census_file(fpath, fp_nodes):
    """Return list of (node, n_gcd_cols, n_valid_gcd_channels) per node."""
    rows = []
    try:
        temp = pd.read_parquet(fpath)
        node_cols: dict[str, list] = {}
        for c in temp.columns:
            if c.startswith("frontier") and "_gcd" in c:
                node = c.split("_")[0]
                if node in fp_nodes:
                    node_cols.setdefault(node, []).append(c)
        for node, ncols in node_cols.items():
            n_cols = len(ncols)
            # Count channels with at least one finite value
            n_valid_ch = sum(
                1 for c in ncols
                if np.any(np.isfinite(temp[c].values.astype(float)))
            )
            # Count channels meeting MIN_VALID_TS threshold
            n_valid_ts = sum(
                1 for c in ncols
                if np.sum(np.isfinite(temp[c].values.astype(float))) >= MIN_VALID_TS
            )
            rows.append(dict(node=node, n_gcd_cols=n_cols,
                             n_valid_channels=n_valid_ch,
                             n_channels_meeting_min_ts=n_valid_ts))
    except Exception:
        pass
    return rows

census_rows = []

# Train sample
n_train_sample = len(train_sample)
for k, (_, row) in enumerate(train_sample.iterrows()):
    if k % 100 == 0:
        print(f"    Train sample {k}/{n_train_sample}", end="\r")
    fpath = temp_path(row["date_dir"], row["job_idx"])
    if fpath.exists():
        for r in census_file(fpath, fp_nodes):
            r["split"] = "train"
            census_rows.append(r)

# All test jobs (from frozen test_set — we know the job/date info from all_jobs)
test_jobs_info = test_df[["job_idx","date_dir"]].drop_duplicates()
n_test = len(test_jobs_info)
for k, (_, row) in enumerate(test_jobs_info.iterrows()):
    if k % 200 == 0:
        print(f"    Test {k}/{n_test}", end="\r")
    fpath = temp_path(row["date_dir"], row["job_idx"])
    if fpath.exists():
        for r in census_file(fpath, fp_nodes):
            r["split"] = "test"
            census_rows.append(r)

print(f"\n    Census rows: {len(census_rows):,}")

census_df = pd.DataFrame(census_rows)
if not census_df.empty:
    for split in ["train", "test", "all"]:
        sub = census_df if split == "all" else census_df[census_df.split == split]
        if sub.empty:
            continue
        n = len(sub)
        dist_cols  = sub["n_gcd_cols"].value_counts().sort_index().to_dict()
        dist_valid = sub["n_valid_channels"].value_counts().sort_index().to_dict()
        dist_ts    = sub["n_channels_meeting_min_ts"].value_counts().sort_index().to_dict()
        pct_all8   = float((sub["n_gcd_cols"] == 8).mean() * 100)
        pct_valid8 = float((sub["n_valid_channels"] == 8).mean() * 100)
        pct_ts8    = float((sub["n_channels_meeting_min_ts"] == 8).mean() * 100)
        print(f"\n    [{split.upper()}] n={n:,}")
        print(f"      All 8 GCD cols present:        {pct_all8:.2f}%")
        print(f"      All 8 channels >=1 finite val: {pct_valid8:.2f}%")
        print(f"      All 8 channels >={MIN_VALID_TS} valid ts: {pct_ts8:.2f}%")
        print(f"      n_gcd_cols distribution:       {dict(sorted(dist_cols.items()))}")

    gcd_census_result = {
        "n_node_job_obs": int(len(census_df)),
        "train_sample_size": n_train_sample,
        "test_jobs_size": n_test,
        "by_split": {}
    }
    for split in ["train", "test"]:
        sub = census_df[census_df.split == split]
        if sub.empty:
            continue
        gcd_census_result["by_split"][split] = {
            "n": int(len(sub)),
            "pct_all_8_gcd_cols":          float((sub.n_gcd_cols == 8).mean() * 100),
            "pct_all_8_valid_channels":    float((sub.n_valid_channels == 8).mean() * 100),
            "pct_all_8_channels_min_ts":   float((sub.n_channels_meeting_min_ts == 8).mean() * 100),
            "n_gcd_cols_distribution":     {str(k): int(v) for k,v in
                                            sub.n_gcd_cols.value_counts().sort_index().items()},
        }
else:
    gcd_census_result = {"error": "No census rows collected"}

# ── Assemble JSON ──────────────────────────────────────────────────
result = {
    "script": "r1_00c_gcd_census_waterfall.py",
    "git_sha": git_sha(),
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "input_sha256": {
        "phase3a_fingerprint_2024.parquet": file_sha256(ANAL_DIR/"phase3a_fingerprint_2024.parquet"),
        "phase3a_test_set.parquet":         file_sha256(ANAL_DIR/"phase3a_test_set.parquet"),
        "globus_batch.txt":                 file_sha256(PHASE1_DIR/"globus_batch.txt"),
    },
    "waterfall_4358_to_2637": waterfall_summary,
    "gcd_channel_census": gcd_census_result,
    "m1_5_conclusion": (
        "If pct_all_8_channels_min_ts >= 99.0% in both train and test splits, "
        "the full-channel restriction analysis (M1.5) would be identical to "
        "the unrestricted FA_2024 fingerprint and is unnecessary."
    ),
}

out = OUT_DIR / "phase0c_gcd_waterfall.json"
with open(out, "w") as f:
    json.dump(result, f, indent=2)

print(f"\nSaved: {out}")
print(f"Total elapsed: {time.time()-t0:.1f}s")
