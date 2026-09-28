"""
Estimate GPU power -> temperature slope (beta_GPU) from high-power longitudinal jobs.

Method: for each selected job, read per-node GPU temp and node power, demean
both within the job (removes job fixed effect), then pool all (delta_P, delta_T)
pairs across jobs and fit: delta_T_GPU = beta * delta_P.

Also runs the GPU scheduling counterfactual using the fitted model and GPU fingerprints.

Outputs:
  phase2_gpu_slope.json  — slope estimate, model stats, scheduling counterfactual
"""
# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.



import os
import os
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import stats
import os
import os
from pathlib import Path

DATA_DIR   = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "job-telemetry"
COHORT_DIR = Path(__file__).parent.parent
OUT_DIR    = COHORT_DIR / "analysis"
JOB_INFO   = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "frontier-completed-job-info.parquet"

manifest     = pd.read_csv(COHORT_DIR / "cohort_manifest.csv")
cohort_nodes = set(manifest["hostname"])
longitudinal = pd.read_csv(COHORT_DIR / "cohort_job_list.csv")
longitudinal = longitudinal[longitudinal["selection_role"] == "longitudinal_cohort"].copy()

jinfo = pq.read_table(JOB_INFO, columns=["job_idx","mean_power","peak_power","node_count"]).to_pandas()
jinfo["job_idx_int"] = jinfo["job_idx"].astype(int)
longitudinal = longitudinal.merge(
    jinfo[["job_idx_int","mean_power","peak_power"]],
    left_on="job_idx", right_on="job_idx_int", how="left"
)
longitudinal["power_per_node"] = longitudinal["mean_power"] / longitudinal["node_count"]

# Select top 30 high-power large-node jobs
p90 = longitudinal["power_per_node"].quantile(0.90)
candidates = (
    longitudinal[(longitudinal["power_per_node"] >= p90) & (longitudinal["node_count"] >= 50)]
    .sort_values("power_per_node", ascending=False)
    .head(30)
)
print(f"Selected {len(candidates)} jobs for slope fitting")
print(f"  Power range: [{candidates['power_per_node'].min():.0f}, {candidates['power_per_node'].max():.0f}] W/node")
print(f"  Node count range: [{candidates['node_count'].min()}, {candidates['node_count'].max()}]")


def load_job(job_idx, date_dir):
    job_str = str(job_idx).zfill(6)
    jdir = DATA_DIR / date_dir / job_str
    temp  = pq.read_table(jdir / f"{job_str}-cleaned-temperature.parquet").to_pandas()
    power = pq.read_table(jdir / f"{job_str}-cleaned-power.parquet").to_pandas()
    return temp, power


def node_mean_gcd_temp(temp_df, nodes_subset=None):
    gcd_cols = [c for c in temp_df.columns if c.startswith("frontier") and "_gcd" in c]
    if nodes_subset:
        gcd_cols = [c for c in gcd_cols if c.split("_")[0] in nodes_subset]
    if not gcd_cols:
        return pd.Series(dtype=float)
    node_map = {}
    for col in gcd_cols:
        node_map.setdefault(col.split("_")[0], []).append(col)
    return pd.Series({n: float(temp_df[cols].values[np.isfinite(temp_df[cols].values)].mean())
                      for n, cols in node_map.items()})


def node_mean_power(power_df, nodes_subset=None):
    node_cols = [c for c in power_df.columns if c.startswith("frontier") and c.endswith("_node")]
    if nodes_subset:
        node_cols = [c for c in node_cols if c.replace("_node","") in nodes_subset]
    if not node_cols:
        return pd.Series(dtype=float)
    means = power_df[node_cols].mean(axis=0)
    means.index = [c.replace("_node","") for c in means.index]
    return means


# ── Fit slope across all selected jobs ────────────────────────────────────────
print("\nFitting GPU power->temp slope across high-power jobs...")
all_delta_P = []
all_delta_T = []
job_slopes  = []
job_summary = []

for i, (_, row) in enumerate(candidates.iterrows()):
    try:
        temp, power = load_job(row["job_idx"], row["date_dir"])
    except Exception as e:
        print(f"  Job {row['job_idx']}: load error ({e})")
        continue

    T = node_mean_gcd_temp(temp)   # ALL nodes in job (not just cohort)
    P = node_mean_power(power)

    common = T.index.intersection(P.index)
    if len(common) < 5:
        continue

    t, p = T[common].values, P[common].values
    mask = np.isfinite(t) & np.isfinite(p)
    t, p = t[mask], p[mask]
    if len(t) < 5 or np.ptp(p) < 10:
        continue

    # Demean within job (remove job fixed effect)
    dt = t - t.mean()
    dp = p - p.mean()
    slope, intercept, r, pv, se = stats.linregress(dp, dt)

    all_delta_P.extend(dp.tolist())
    all_delta_T.extend(dt.tolist())
    job_slopes.append(slope)
    job_summary.append({
        "job_idx": row["job_idx"],
        "date_dir": row["date_dir"],
        "node_count": int(row["node_count"]),
        "power_per_node": round(float(row["power_per_node"]), 1),
        "n_nodes_with_data": len(t),
        "mean_gpu_temp": round(float(t.mean()), 2),
        "power_range_W": round(float(np.ptp(p)), 1),
        "slope_C_per_W": round(float(slope), 6),
        "r": round(float(r), 4),
        "p_value": float(pv),
    })
    print(f"  Job {row['job_idx']}: n={len(t)}, T_mean={t.mean():.1f}°C, "
          f"P_range={np.ptp(p):.0f}W, slope={slope*1000:.4f}°C/kW, r={r:.3f}")

# Pooled OLS across all job-demeaned pairs
all_dp = np.array(all_delta_P)
all_dt = np.array(all_delta_T)
mask = np.isfinite(all_dp) & np.isfinite(all_dt)
all_dp, all_dt = all_dp[mask], all_dt[mask]

slope_pooled, intercept_pooled, r_pooled, pv_pooled, se_pooled = stats.linregress(all_dp, all_dt)
slope_median = float(np.median(job_slopes))
slope_mean   = float(np.mean(job_slopes))

print(f"\n=== GPU power->temperature slope estimates ===")
print(f"  Pooled OLS:    {slope_pooled*1000:.4f} °C/kW  (r={r_pooled:.4f}, n={len(all_dp):,} node-obs)")
print(f"  Median/job:    {slope_median*1000:.4f} °C/kW")
print(f"  Mean/job:      {slope_mean*1000:.4f} °C/kW")
print(f"  Jobs used:     {len(job_slopes)}")

# Use pooled slope as best estimate
beta_GPU = slope_pooled   # °C/W

# ── Mean GPU temperature at high power ────────────────────────────────────────
high_power_temps = [s["mean_gpu_temp"] for s in job_summary if s["power_per_node"] > 2000]
print(f"\n  Mean GPU (GCD avg) temp at >2000 W/node: {np.mean(high_power_temps):.1f}°C "
      f"(range [{min(high_power_temps):.1f}, {max(high_power_temps):.1f}])")


# ── Thermal model for GPU scheduling counterfactual ───────────────────────────
# T_gpu(P, F) = T_ref + beta_GPU * (P - P_ref) + gamma_F * F
# where T_ref and P_ref are fleet job reference values
T_REF_GPU  = 44.1    # °C — fleet job mean GCD temp (moderate load)
P_REF      = 892.0   # W/node — fleet job mean power
GAMMA_GPU  = 1.0008  # from fleet job regression
T_THROTTLE = 95.0    # °C — AMD MI250X approximate thermal throttle junction

def T_gpu_pred(P_node, F_node):
    return T_REF_GPU + beta_GPU * (P_node - P_REF) + GAMMA_GPU * F_node

print(f"\n=== Predicted GPU temps at key power levels ===")
for P_val, label in [(495, "p5 = 495W"), (892, "fleet = 892W"),
                     (1072, "mean = 1072W"), (1907, "p90 = 1907W"),
                     (2086, "p95 = 2086W"), (2243, "p99 = 2243W")]:
    T_cold = T_gpu_pred(P_val, -5.25)
    T_med  = T_gpu_pred(P_val,  0.0)
    T_hot  = T_gpu_pred(P_val, +3.43)
    print(f"  {label}: cold={T_cold:.1f}°C, median={T_med:.1f}°C, hot={T_hot:.1f}°C "
          f"(delta hot-cold={T_hot-T_cold:.1f}°C)")


# ── GPU scheduling counterfactual using full job history ─────────────────────
print("\n=== GPU scheduling counterfactual (152,400 jobs) ===")

gpu_fp   = pq.read_table(OUT_DIR / "gpu_fingerprints.parquet").to_pandas()
node_fp  = gpu_fp["FA_fleet"].dropna().to_dict()
jinfo_full = pq.read_table(JOB_INFO, columns=["job_idx","mean_power","node_count","host_list"]).to_pandas()
jinfo_full["job_idx_int"] = jinfo_full["job_idx"].astype(int)
jinfo_full["power_per_node"] = jinfo_full["mean_power"] / jinfo_full["node_count"]

import ast

def parse_hosts(s):
    if s is None: return []
    if isinstance(s, (list, np.ndarray)): return list(s)
    try: return ast.literal_eval(str(s))
    except: return []

jinfo_full["hosts"] = jinfo_full["host_list"].apply(parse_hosts)
jinfo_full["cohort_hosts"] = jinfo_full["hosts"].apply(
    lambda nl: [n for n in nl if n in node_fp]
)
jinfo_full["n_cohort"] = jinfo_full["cohort_hosts"].apply(len)

jobs_w_cohort = jinfo_full[jinfo_full["n_cohort"] >= 1].dropna(subset=["power_per_node"])
print(f"  Jobs with >=1 cohort GPU-fingerprinted node: {len(jobs_w_cohort):,}")

# Sorted pool for Policy A
sorted_nodes = sorted(node_fp.keys(), key=lambda n: node_fp[n])
fp_sorted    = np.array([node_fp[n] for n in sorted_nodes])

def max_fp_baseline(cohort_hosts):
    fps = [node_fp[n] for n in cohort_hosts]
    return max(fps) if fps else np.nan

def max_fp_policyA(n_needed):
    if n_needed <= 0 or n_needed > len(fp_sorted): return np.nan
    return float(fp_sorted[:n_needed].max())

jobs_w_cohort = jobs_w_cohort.copy()
jobs_w_cohort["max_F_baseline"] = jobs_w_cohort["cohort_hosts"].apply(max_fp_baseline)
jobs_w_cohort["max_F_policyA"]  = jobs_w_cohort["n_cohort"].apply(max_fp_policyA)

P = jobs_w_cohort["power_per_node"].values
jobs_w_cohort["T_max_baseline"] = T_REF_GPU + beta_GPU * (P - P_REF) + GAMMA_GPU * jobs_w_cohort["max_F_baseline"].values
jobs_w_cohort["T_max_policyA"]  = T_REF_GPU + beta_GPU * (P - P_REF) + GAMMA_GPU * jobs_w_cohort["max_F_policyA"].values

valid = jobs_w_cohort.dropna(subset=["T_max_baseline","T_max_policyA"])
delta_T = valid["T_max_baseline"] - valid["T_max_policyA"]

print(f"  Jobs analyzed: {len(valid):,}")
print(f"  Baseline mean max GPU T: {valid['T_max_baseline'].mean():.1f}°C")
print(f"  Policy A mean max GPU T: {valid['T_max_policyA'].mean():.1f}°C")
print(f"  Mean delta_T: {delta_T.mean():.2f}°C, p95 delta: {delta_T.quantile(0.95):.2f}°C")

for thresh in [85, 90, T_THROTTLE]:
    n_bl = (valid["T_max_baseline"] > thresh).sum()
    n_pa = (valid["T_max_policyA"]  > thresh).sum()
    pct_bl = n_bl / len(valid) * 100
    pct_pa = n_pa / len(valid) * 100
    red = (1 - n_pa / max(n_bl, 1)) * 100
    print(f"  T > {thresh:.0f}°C: baseline {n_bl:,} ({pct_bl:.1f}%), "
          f"policy A {n_pa:,} ({pct_pa:.1f}%) — {red:.1f}% reduction")


# ── Save results ──────────────────────────────────────────────────────────────
results = {
    "slope_estimation": {
        "n_jobs_used": len(job_slopes),
        "n_node_observations": int(len(all_dp)),
        "beta_GPU_pooled_C_per_W": round(float(beta_GPU), 6),
        "beta_GPU_pooled_C_per_kW": round(float(beta_GPU * 1000), 4),
        "beta_GPU_median_C_per_kW": round(float(slope_median * 1000), 4),
        "pooled_r": round(float(r_pooled), 4),
        "mean_gpu_temp_high_power_jobs": round(float(np.mean(high_power_temps)), 2),
        "job_details": job_summary,
    },
    "thermal_model": {
        "T_ref_GPU_C": T_REF_GPU,
        "P_ref_W": P_REF,
        "gamma_F": round(GAMMA_GPU, 4),
        "beta_GPU_C_per_W": round(float(beta_GPU), 6),
        "T_throttle_C": T_THROTTLE,
        "note": "T_gpu = T_ref + beta*(P - P_ref) + gamma*F_gpu",
    },
    "scheduling_counterfactual_GPU": {
        "jobs_analyzed": int(len(valid)),
        "mean_max_T_baseline_C": round(float(valid["T_max_baseline"].mean()), 2),
        "mean_max_T_policyA_C":  round(float(valid["T_max_policyA"].mean()), 2),
        "mean_delta_T_C": round(float(delta_T.mean()), 3),
        "p95_delta_T_C":  round(float(delta_T.quantile(0.95)), 3),
        "above_85C_baseline_pct": round(float((valid["T_max_baseline"] > 85).sum() / len(valid) * 100), 2),
        "above_85C_policyA_pct":  round(float((valid["T_max_policyA"]  > 85).sum() / len(valid) * 100), 2),
        "above_90C_baseline_pct": round(float((valid["T_max_baseline"] > 90).sum() / len(valid) * 100), 2),
        "above_90C_policyA_pct":  round(float((valid["T_max_policyA"]  > 90).sum() / len(valid) * 100), 2),
        "above_throttle_baseline_pct": round(float((valid["T_max_baseline"] > T_THROTTLE).sum() / len(valid) * 100), 2),
        "above_throttle_policyA_pct":  round(float((valid["T_max_policyA"]  > T_THROTTLE).sum() / len(valid) * 100), 2),
    },
}

with open(OUT_DIR / "phase2_gpu_slope.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\nSaved phase2_gpu_slope.json")
print("Done.")
