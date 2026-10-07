#!/usr/bin/env python3
"""
Gate 3a: Independent threshold verification script.
Loads full_train_t95_distribution.parquet and independently computes percentiles.
Compares against frozen values from m4_threshold_audit.json.
"""
import sys, json, hashlib
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[3]
CACHE_PATH = REPO_ROOT / "artifacts" / "revision1" / "results" / "full_train_t95_distribution.parquet"
AUDIT_PATH = REPO_ROOT / "artifacts" / "revision1" / "results" / "m4_threshold_audit.json"
OUT_PATH   = Path(__file__).parent / "c3_threshold_independent.json"

FROZEN_AUDIT_SHA = "2ece0a19f63e3e147ae7c5f19765a2ebcd4144470c852004ef4426c2178adbcc"
FROZEN_P90 = 61.875
FROZEN_P95 = 63.625
FROZEN_P99 = 66.6625
FROZEN_N_CONTRIBUTING_JOBS = 3940
FROZEN_N_NODE_JOB_PAIRS    = 77627

print("Gate 3a: Threshold Independent Verification")
print("=" * 60)

# Step 1: Verify m4_threshold_audit.json SHA256
print(f"\n[1] Verifying m4_threshold_audit.json SHA256 ...")
actual_sha = hashlib.sha256(open(AUDIT_PATH, "rb").read()).hexdigest()
sha_match = (actual_sha == FROZEN_AUDIT_SHA)
print(f"    Expected: {FROZEN_AUDIT_SHA}")
print(f"    Actual:   {actual_sha}")
print(f"    Match:    {sha_match}")
if not sha_match:
    print("GATE 3 FAIL: threshold audit SHA256 mismatch")
    sys.exit(1)

# Step 2: Load cache parquet
print(f"\n[2] Loading cache parquet: {CACHE_PATH.name} ...")
df = pd.read_parquet(CACHE_PATH)
print(f"    Shape: {df.shape}")
print(f"    Columns: {list(df.columns)}")

# Step 3: Independently compute percentiles on T_p95 column
print(f"\n[3] Computing percentiles on T_p95 column ...")
# Column may be lowercase or uppercase
_col = "T_p95" if "T_p95" in df.columns else "t_p95"
t_p95_vals = df[_col].values
pctiles = np.percentile(t_p95_vals, [90, 95, 99])
p90, p95, p99 = float(pctiles[0]), float(pctiles[1]), float(pctiles[2])
print(f"    P90 = {p90}  (frozen: {FROZEN_P90})")
print(f"    P95 = {p95}  (frozen: {FROZEN_P95})")
print(f"    P99 = {p99}  (frozen: {FROZEN_P99})")

p90_ok = abs(p90 - FROZEN_P90) < 1e-9
p95_ok = abs(p95 - FROZEN_P95) < 1e-9
p99_ok = abs(p99 - FROZEN_P99) < 1e-9

# Step 4: Verify n_contributing_jobs and n_node_job_pairs
print(f"\n[4] Verifying population counts ...")
# n_contributing_jobs = unique job_idx values
n_contributing_jobs = int(df["job_idx"].nunique()) if "job_idx" in df.columns else int(df.index.nunique())
# n_node_job_pairs = total rows
n_node_job_pairs = int(len(df))
print(f"    n_contributing_jobs: {n_contributing_jobs}  (frozen: {FROZEN_N_CONTRIBUTING_JOBS})")
print(f"    n_node_job_pairs:    {n_node_job_pairs}  (frozen: {FROZEN_N_NODE_JOB_PAIRS})")
jobs_ok = (n_contributing_jobs == FROZEN_N_CONTRIBUTING_JOBS)
pairs_ok = (n_node_job_pairs == FROZEN_N_NODE_JOB_PAIRS)

# Summary
all_pass = all([p90_ok, p95_ok, p99_ok, jobs_ok, pairs_ok, sha_match])
print(f"\n[5] Summary:")
print(f"    SHA256 match:          {'PASS' if sha_match else 'FAIL'}")
print(f"    P90 match:             {'PASS' if p90_ok else 'FAIL'} ({p90} vs {FROZEN_P90})")
print(f"    P95 match:             {'PASS' if p95_ok else 'FAIL'} ({p95} vs {FROZEN_P95})")
print(f"    P99 match:             {'PASS' if p99_ok else 'FAIL'} ({p99} vs {FROZEN_P99})")
print(f"    n_contributing_jobs:   {'PASS' if jobs_ok else 'FAIL'} ({n_contributing_jobs} vs {FROZEN_N_CONTRIBUTING_JOBS})")
print(f"    n_node_job_pairs:      {'PASS' if pairs_ok else 'FAIL'} ({n_node_job_pairs} vs {FROZEN_N_NODE_JOB_PAIRS})")
print(f"    OVERALL:               {'PASS' if all_pass else 'FAIL'}")

result = {
    "description"               : "Gate 3a: Independent threshold verification",
    "cache_parquet"             : str(CACHE_PATH),
    "audit_path"                : str(AUDIT_PATH),
    "audit_sha256_frozen"       : FROZEN_AUDIT_SHA,
    "audit_sha256_actual"       : actual_sha,
    "audit_sha256_match"        : sha_match,
    "n_contributing_jobs_frozen": FROZEN_N_CONTRIBUTING_JOBS,
    "n_contributing_jobs_actual": n_contributing_jobs,
    "n_contributing_jobs_match" : jobs_ok,
    "n_node_job_pairs_frozen"   : FROZEN_N_NODE_JOB_PAIRS,
    "n_node_job_pairs_actual"   : n_node_job_pairs,
    "n_node_job_pairs_match"    : pairs_ok,
    "percentiles_computed"      : {"P90": p90, "P95": p95, "P99": p99},
    "percentiles_frozen"        : {"P90": FROZEN_P90, "P95": FROZEN_P95, "P99": FROZEN_P99},
    "P90_match"                 : p90_ok,
    "P95_match"                 : p95_ok,
    "P99_match"                 : p99_ok,
    "overall_pass"              : all_pass,
}
OUT_PATH.write_text(json.dumps(result, indent=2))
print(f"\nWritten: {OUT_PATH}")

if not all_pass:
    print("GATE 3 FAIL: threshold mismatch")
    sys.exit(1)
else:
    print("Gate 3a: PASS")
