#!/usr/bin/env python3
"""
Recovery of BETA_F_JACKKNIFE_MEAN from the Phase B v1 (run_b1_loo_beta.py) implementation.

Context: run_b1_loo_beta_v2.py (the corrected primary estimator) did not recompute the
jackknife; its B2a field states "refer to run_b1_loo_beta.py for FE-slope jackknife."
The v1 output file was overwritten by v2.  This script re-derives BETA_F_JACKKNIFE_MEAN
from the same v1 formulas and the same frozen telemetry data without overwriting any
existing artifact.

V1 FORMULAS USED (line-identical to run_b1_loo_beta.py §B2a):
  - r_ij = T_dev[i,j] (T_p95 deviation from job mean) — v1's formula, NOT v2's flat GCD mean
  - F_CF[i,j] = (FA_2024[i]*n_i - T_dev[i,j]) / (n_i - 1)   (v1 LOO formula)
  - Within-job demeaning of F_CF and T_dev
  - c_xy[j] = sum(F_CF_dm * T_dev_dm) for obs in job j
  - c_xx[j] = sum(F_CF_dm^2) for obs in job j
  - beta_FE = SS_xy / SS_xx  (v1 primary, which v2 labels B1_secondary_FE_beta)
  - jack_betas[j] = (SS_xy - c_xy[j]) / (SS_xx - c_xx[j])
  - BETA_F_JACKKNIFE_MEAN = mean(jack_betas)

CROSS-CHECKS:
  - beta_FE must equal 1.08293343 (stored in v2 as B1_secondary_FE_beta, source 2814bb6)
  - Tolerance: |computed - 1.08293343| <= 1e-6

Output: artifacts/revision2/beta_jackknife_recovery.json
Does NOT overwrite: loo_beta_results.json or any other existing artifact.
"""
import sys, io, json, numpy as np, pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pyarrow.parquet as pq

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

DATA_DIR  = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset/job-telemetry")
REPO_ROOT = Path("C:/users/kalya/thermalops")
ANAL_DIR  = REPO_ROOT / "artifacts/phase1/analysis"
REV1_DIR  = REPO_ROOT / "artifacts/revision1/results"
OUT_DIR   = REPO_ROOT / "artifacts/revision2"

MAX_WORKERS = 8

# Cross-check target: v1 FE-slope beta stored in v2 results as B1_secondary_FE_beta
EXPECTED_BETA_FE = 1.08293343
CROSS_CHECK_TOL  = 1e-6

print("=== BETA_F_JACKKNIFE_MEAN Recovery (v1 FE-slope formula) ===")
print(f"Cross-check target: beta_FE = {EXPECTED_BETA_FE}")
print()

# Load fingerprints
fp_df       = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
FA_2024     = fp_df["FA_2024"].to_dict()
n_train_d   = fp_df["n_jobs_train"].to_dict()
cohort_nodes = set(fp_df.index)
print(f"Cohort nodes: {len(cohort_nodes)}")

# Load qualifying training jobs (same 462 jobs as v1/v2)
train_betas_df = pd.read_parquet(REV1_DIR / "m3_train_betas.parquet")
n_qual = len(train_betas_df)
print(f"Qualifying training jobs: {n_qual}")

# Helper: same as v1 (uses T_p95 from GCD columns, NOT flat mean)
def gcd_cols_for_nodes(cols_all, nodes):
    return [c for c in cols_all
            if c.startswith("frontier") and "_gcd" in c
            and "ncount" not in c
            and c.split("_")[0] in nodes]

def node_map_from(cols):
    nm = {}
    for col in cols:
        nm.setdefault(col.split("_")[0], []).append(col)
    return nm

def load_train_job_v1(row):
    """V1 formula: r_ij = T_p95 deviation from job mean (NOT flat GCD mean)."""
    job_idx  = int(row["job_idx"])
    date_dir = str(row["date_dir"])
    job_str  = str(job_idx).zfill(6)
    fpath    = DATA_DIR / date_dir / job_str / f"{job_str}-cleaned-temperature.parquet"
    try:
        temp = pq.read_table(fpath).to_pandas()
    except Exception:
        return None
    cols = gcd_cols_for_nodes(list(temp.columns), cohort_nodes)
    if not cols:
        return None
    nm = node_map_from(cols)
    node_data = {}
    for node, gcols in nm.items():
        ts_means = np.nanmean(temp[gcols].values.astype(float), axis=1)
        finite   = ts_means[np.isfinite(ts_means)]
        if len(finite) < 5:
            continue
        node_data[node] = float(np.percentile(finite, 95))  # T_p95: v1 formula
    if len(node_data) < 2:
        return None
    jm  = np.mean(list(node_data.values()))
    obs = [(node, float(val - jm)) for node, val in node_data.items()
           if node in FA_2024]
    if len(obs) < 2:
        return None
    return (job_idx, date_dir, obs)

print(f"\nLoading {n_qual} qualifying training jobs (MAX_WORKERS={MAX_WORKERS}) ...")
rows = [row for _, row in train_betas_df.iterrows()]
job_obs_list = []
n_ok = n_fail = 0

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futures = {ex.submit(load_train_job_v1, r): r for r in rows}
    for fut in as_completed(futures):
        res = fut.result()
        if res is None:
            n_fail += 1
        else:
            job_obs_list.append(res)
            n_ok += 1

print(f"  Loaded: {n_ok}  Failed: {n_fail}")
if n_fail > 0:
    print(f"  WARNING: {n_fail} jobs failed to load")

# Build observation DataFrame (same as v1)
records = []
for job_idx, date_dir, obs in job_obs_list:
    for node, t_dev in obs:
        records.append({"job_idx": job_idx, "node": node, "T_dev": t_dev})

obs_df = pd.DataFrame(records)
obs_df["FA"] = obs_df["node"].map(FA_2024)
obs_df["n_i"] = obs_df["node"].map(n_train_d)
obs_df = obs_df.dropna(subset=["FA", "n_i"]).copy()
obs_df["n_i"] = obs_df["n_i"].astype(int)
obs_df = obs_df[obs_df["n_i"] > 1].copy()

# V1 LOO formula: F_CF[i,j] = (FA_2024[i]*n_i - T_dev[i,j]) / (n_i - 1)
obs_df["F_CF"] = (obs_df["FA"] * obs_df["n_i"] - obs_df["T_dev"]) / (obs_df["n_i"] - 1)

# Within-job demeaning (same as v1)
jm_FCF = obs_df.groupby("job_idx")["F_CF"].transform("mean")
jm_T   = obs_df.groupby("job_idx")["T_dev"].transform("mean")
obs_df["F_CF_dm"]  = obs_df["F_CF"]  - jm_FCF
obs_df["T_dev_dm"] = obs_df["T_dev"] - jm_T

# Job-level aggregates (same as v1)
obs_df["cross_xy"] = obs_df["F_CF_dm"] * obs_df["T_dev_dm"]
obs_df["cross_xx"] = obs_df["F_CF_dm"] ** 2

job_agg = obs_df.groupby("job_idx").agg(
    c_xy=("cross_xy", "sum"),
    c_xx=("cross_xx", "sum"),
    n_obs=("T_dev", "count"),
).reset_index()

n_jobs   = len(job_agg)
SS_xy    = float(job_agg["c_xy"].sum())
SS_xx    = float(job_agg["c_xx"].sum())
beta_FE  = SS_xy / SS_xx

print(f"\nComputed beta_FE (v1 FE slope): {beta_FE:.8f}")
print(f"Expected beta_FE (stored v2 B1_secondary_FE_beta): {EXPECTED_BETA_FE:.8f}")
cross_check_diff = abs(beta_FE - EXPECTED_BETA_FE)
print(f"Difference: {cross_check_diff:.2e}")

cross_check_pass = cross_check_diff <= CROSS_CHECK_TOL
if not cross_check_pass:
    print(f"\nFATAL: Cross-check FAILED — beta_FE differs from stored value by {cross_check_diff:.6f}")
    print("This means the v1 formulas were not reproduced exactly.")
    print("Do NOT use the jackknife value. Investigate the discrepancy.")
    sys.exit(1)
print(f"Cross-check: PASS (diff={cross_check_diff:.2e} <= {CROSS_CHECK_TOL:.0e})")

# V1 jackknife (leave-one-job-out of FE slope)
c_xy_arr = job_agg["c_xy"].values
c_xx_arr = job_agg["c_xx"].values

jack_xy    = SS_xy - c_xy_arr
jack_xx    = SS_xx - c_xx_arr
jack_betas = jack_xy / jack_xx

BETA_F_JACKKNIFE_MEAN = float(jack_betas.mean())
jack_std = float(jack_betas.std())
jack_min = float(jack_betas.min())
jack_max = float(jack_betas.max())
jack_p5  = float(np.percentile(jack_betas, 5))
jack_p95 = float(np.percentile(jack_betas, 95))

print(f"\nBETA_F_JACKKNIFE_MEAN: {BETA_F_JACKKNIFE_MEAN:.8f}")
print(f"  std:  {jack_std:.6f}")
print(f"  min:  {jack_min:.6f}")
print(f"  max:  {jack_max:.6f}")
print(f"  P5:   {jack_p5:.6f}")
print(f"  P95:  {jack_p95:.6f}")
print(f"  n_jobs: {n_jobs}")

result = {
    "script": "artifacts/revision2/beta_jackknife_recovery.py",
    "purpose": "Recovery of BETA_F_JACKKNIFE_MEAN from v1 (run_b1_loo_beta.py) formula",
    "estimand": "Leave-one-job-out of pooled FE slope (sum_c_xy/sum_c_xx); v1 r_ij=T_p95 formula",
    "plan_ref": "REVIEW2_CHALLENGE_PLAN.md §B2a (v1 implementation at commit 2814bb6)",
    "provenance_note": (
        "run_b1_loo_beta_v2.py B2a field: 'Jackknife not recomputed for v2; "
        "refer to run_b1_loo_beta.py for FE-slope jackknife.' "
        "This script reproduces that computation from the same frozen telemetry data "
        "without overwriting loo_beta_results.json."
    ),
    "training_data": {
        "n_jobs_loaded": n_ok,
        "n_jobs_failed": n_fail,
        "n_unique_jobs_in_aggregates": n_jobs,
    },
    "cross_check": {
        "expected_beta_FE": EXPECTED_BETA_FE,
        "computed_beta_FE": round(beta_FE, 8),
        "diff": round(cross_check_diff, 10),
        "tol": CROSS_CHECK_TOL,
        "pass": cross_check_pass,
    },
    "BETA_F_JACKKNIFE_MEAN": round(BETA_F_JACKKNIFE_MEAN, 8),
    "jackknife_distribution": {
        "n_jobs": n_jobs,
        "mean":  round(BETA_F_JACKKNIFE_MEAN, 8),
        "std":   round(jack_std, 8),
        "min":   round(jack_min, 8),
        "max":   round(jack_max, 8),
        "P5":    round(jack_p5, 8),
        "P95":   round(jack_p95, 8),
    },
}

out_path = OUT_DIR / "beta_jackknife_recovery.json"
out_path.write_text(json.dumps(result, indent=2))
print(f"\nWritten: {out_path}")
print(f"\nBETA_F_JACKKNIFE_MEAN = {BETA_F_JACKKNIFE_MEAN:.8f}")
print("Cross-check: PASS")
