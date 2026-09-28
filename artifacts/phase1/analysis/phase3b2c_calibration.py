# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.2-C: Counterfactual calibration.

Goal: verify that random node reassignment with empirical residuals reproduces
historical thermal statistics in expectation.

Residual model
--------------
For each historical (job j, node i) observation in the Phase 3A test set:
  e_{ij} = T_obs_{p95,ij} - alpha_j - beta_F * F_i
  alpha_j = T_p95_hist_j - beta_F * F_hist_mean_j   (OLS job intercept; residuals sum to 0 within j)

Counterfactual temperature for node s_m assigned to job j:
  T_hat_{s_m, j} = alpha_j + beta_F * F_{s_m} + e_j[pi[m]]
  where pi is a random permutation of the job's empirical residual vector.

Common residual permutations (CRN principle): for a given scenario, generate ONE
permutation per job drawn from a scenario-level RNG.  All scheduling policies in
that scenario use the same permutations; differences in B/S are attributable to
node selection only.

Calibration target (Random-feasible at lambda=1, N=20 draws):
  E[B_random / B_hist_node] in [0.95, 1.05]
  E[S_random / S_hist_node] in [0.95, 1.05]
  Temperature quantiles and within-job SD match historical.
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json, time, re
from pathlib import Path

ANALYSIS_DIR  = Path(__file__).parent
DATA_DIR      = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

BETA_F          = 0.9569
N_CALIB         = 20
CALIB_BASE_SEED = 99991   # scenario i uses CALIB_BASE_SEED + i

T_P95_THRESHOLD = 60.602770562770566

CALIB_PASS_LO = 0.95
CALIB_PASS_HI = 1.05

print("=== Phase 3B.2-C: Counterfactual calibration ===")
print(f"  N_CALIB={N_CALIB}  target B/S ratio in [{CALIB_PASS_LO}, {CALIB_PASS_HI}]\n")

# ---------------------------------------------------------------------------
# Load data (same as capacity script)
# ---------------------------------------------------------------------------
print("Loading fingerprints...")
fp_df       = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set  = set(fp_df.index)
F_dict      = fp_df["FA_2024"].to_dict()
cohort_list = sorted(cohort_set)
n_cohort    = len(cohort_list)
print(f"  Cohort: {n_cohort:,} nodes")

print("Loading test set...")
test_df = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")

print("Loading full job schedule...")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"  {len(all_jobs):,} total jobs")

# ---------------------------------------------------------------------------
# Schedule arrays (background busy)
# ---------------------------------------------------------------------------
print("\nPrecomputing schedule arrays...")
t0 = time.time()
cohort_per_job: dict[int, frozenset] = {}
for jid, hl in zip(all_jobs["job_idx_int"].values, all_jobs["host_list"].values):
    cn = frozenset(n for n in hl if n in cohort_set)
    if cn:
        cohort_per_job[jid] = cn
has_cohort = np.array([jid in cohort_per_job for jid in all_jobs["job_idx_int"].values])
sched_jids = all_jobs["job_idx_int"].values[has_cohort]
sched_st   = all_jobs["start_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_et   = all_jobs["end_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_cn   = np.array([cohort_per_job[jid] for jid in sched_jids], dtype=object)
print(f"  {len(sched_jids):,} entries  ({time.time()-t0:.1f}s)")

# ---------------------------------------------------------------------------
# Job-level test summary
# ---------------------------------------------------------------------------
print("\nBuilding job-level test summary...")
job_agg = (
    test_df.groupby("job_idx")
    .agg(F_hist_mean=("F_2024", "mean"), n_cohort=("node", "count"),
         T_p95_hist=("T_p95", "mean"), T_median_hist=("T_p95", "median"),
         hist_nodes=("node", list))
    .reset_index()
)
meta = (
    all_jobs[["job_idx_int", "node_count", "start_time", "end_time", "mean_power", "run_time"]]
    .rename(columns={"job_idx_int": "job_idx"})
)
job_agg = job_agg.merge(meta, on="job_idx", how="left")
test_id_set = set(job_agg["job_idx"].astype(int))
jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)
n_base      = len(jobs_sorted)
print(f"  {n_base} base test jobs")

# Job-level alpha_j (OLS intercept with frozen beta_F)
# alpha_j = T_p95_hist_j - beta_F * F_hist_mean_j
# Residuals e_{ij} sum to zero within each job by construction.
jobs_sorted["alpha_j"] = (
    jobs_sorted["T_p95_hist"] - BETA_F * jobs_sorted["F_hist_mean"]
)

# ---------------------------------------------------------------------------
# Background busy
# ---------------------------------------------------------------------------
print("\nPrecomputing background busy...")
t0 = time.time()
is_test_sched = np.array([jid in test_id_set for jid in sched_jids])
bg_st = sched_st[~is_test_sched]
bg_et = sched_et[~is_test_sched]
bg_cn = sched_cn[~is_test_sched]

def to_dt64(ts) -> np.datetime64:
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

bg_busy_per_job: dict[int, frozenset] = {}
for _, jrow in jobs_sorted.iterrows():
    jid = int(jrow["job_idx"])
    t_j = to_dt64(jrow["start_time"])
    mask = (bg_st <= t_j) & (bg_et > t_j)
    bg_busy_per_job[jid] = frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()
print(f"  Done  ({time.time()-t0:.1f}s)")

# ---------------------------------------------------------------------------
# Empirical residuals
# ---------------------------------------------------------------------------
print("\nComputing empirical residuals...")
# e_{ij} = T_obs_{ij} - alpha_j - beta_F * F_i
alpha_map = jobs_sorted.set_index("job_idx")["alpha_j"].to_dict()

test_res = test_df.copy()
test_res["F_i"]      = test_res["node"].map(F_dict)
test_res["alpha_j"]  = test_res["job_idx"].map(lambda jid: alpha_map.get(int(jid), np.nan))
test_res["residual"] = (test_res["T_p95"]
                        - test_res["alpha_j"]
                        - BETA_F * test_res["F_i"])

# Per-job residual arrays (length = k_j = n_cohort for that job)
job_residuals: dict[int, np.ndarray] = {}
for jid, grp in test_res.groupby("job_idx"):
    job_residuals[int(jid)] = grp["residual"].values.copy()

res_flat = test_res["residual"].values
print(f"  Residuals: mean={res_flat.mean():.4f}  SD={res_flat.std():.4f}"
      f"  p5={np.percentile(res_flat, 5):.2f}  p95={np.percentile(res_flat, 95):.2f} degC")
print(f"  (Mean near 0 = OLS invariant satisfied)")

# ---------------------------------------------------------------------------
# Historical statistics (exact observed truth, computed once)
# ---------------------------------------------------------------------------
print("\nComputing historical node-level statistics (exact observed)...")
rt_lookup   = jobs_sorted.set_index("job_idx")["run_time"].to_dict()
test_rt_h   = test_res["job_idx"].map(lambda jid: rt_lookup.get(int(jid), 0.0)) / 3600.0
node_excess = test_res["T_p95"] - T_P95_THRESHOLD

B_hist_node = float((test_rt_h * (node_excess > 0)).sum())
S_hist_node = float((test_rt_h * node_excess.clip(lower=0)).sum())

T_obs_all       = test_res["T_p95"].values
hist_T_q         = np.quantile(T_obs_all, [0.25, 0.50, 0.75, 0.90, 0.95, 0.99])
hist_n_exceed    = int((node_excess > 0).sum())
hist_exceedance_rate = hist_n_exceed / len(node_excess)

# Within-job SD and IQR
hist_wj_sd = []
for jid, grp in test_res.groupby("job_idx"):
    if len(grp) > 1:
        hist_wj_sd.append(float(grp["T_p95"].std()))
hist_wj_sd = np.array(hist_wj_sd)

print(f"  B_hist_node = {B_hist_node:.1f} h    S_hist_node = {S_hist_node:.1f} degC-h")
print(f"  T: p50={hist_T_q[1]:.2f}  p90={hist_T_q[3]:.2f}  p95={hist_T_q[4]:.2f}"
      f"  p99={hist_T_q[5]:.2f}  degC")
print(f"  Within-job SD: mean={hist_wj_sd.mean():.3f}  median={np.median(hist_wj_sd):.3f}"
      f"  p95={np.percentile(hist_wj_sd, 95):.3f}  degC")
print(f"  Node-level exceedance rate: {hist_exceedance_rate:.4f}"
      f"  ({hist_n_exceed}/{len(node_excess)} node-job pairs)")

# ---------------------------------------------------------------------------
# Calibration replay: Random-feasible + permuted residuals
# ---------------------------------------------------------------------------
def calib_replay(scen_seed: int) -> dict:
    """
    Random node assignment with empirical residual permutation.
    No synthetic jobs (lambda=1).
    Returns per-job and aggregate statistics.
    """
    rng = np.random.default_rng(scen_seed)

    cf_busy: dict[str, np.datetime64] = {}

    all_T_hats    = []
    wj_sds        = []
    B_total       = 0.0
    S_total       = 0.0
    n_under       = 0

    for _, jrow in jobs_sorted.iterrows():
        t_j   = to_dt64(jrow["start_time"])
        t_e   = to_dt64(jrow["end_time"])
        rt_h  = float(jrow["run_time"]) / 3600.0
        k     = int(jrow["n_cohort"])
        jid   = int(jrow["job_idx"])
        alpha = float(jrow["alpha_j"])

        bg_busy     = bg_busy_per_job[jid]
        cf_busy_now = frozenset(n for n, te in cf_busy.items() if te > t_j)
        available   = [n for n in cohort_set if n not in bg_busy and n not in cf_busy_now]

        if len(available) < k:
            # Take all available; flag underserved (should be rare)
            selected = available
            n_under += 1
        else:
            idx      = rng.choice(len(available), size=k, replace=False)
            selected = [available[i] for i in idx]

        for n in selected:
            cf_busy[n] = t_e

        if not selected:
            continue

        # Empirical residuals for this job, randomly permuted
        res  = job_residuals[jid]          # length k, mean=0 by construction
        perm = rng.permutation(len(res))   # fresh permutation for this scenario

        F_sel = np.array([F_dict[n] for n in selected])

        # T_hat_{s_m,j} = alpha_j + beta_F * F_{s_m} + e_j[pi[m]]
        # len(res) == len(selected) == k for all base jobs
        T_hats_j = alpha + BETA_F * F_sel + res[perm]

        excesses = T_hats_j - T_P95_THRESHOLD
        B_total += rt_h * float((excesses > 0).sum())
        S_total += rt_h * float(excesses.clip(min=0).sum())

        all_T_hats.append(T_hats_j)
        if len(T_hats_j) > 1:
            wj_sds.append(float(T_hats_j.std()))

    T_arr = np.concatenate(all_T_hats) if all_T_hats else np.array([])
    T_q   = np.quantile(T_arr, [0.25, 0.50, 0.75, 0.90, 0.95, 0.99]) if len(T_arr) > 0 else np.full(6, np.nan)
    wj    = np.array(wj_sds)

    n_exceed = int(((T_arr - T_P95_THRESHOLD) > 0).sum()) if len(T_arr) > 0 else 0
    exceedance_rate = n_exceed / len(T_arr) if len(T_arr) > 0 else np.nan

    return {
        "B":              B_total,
        "S":              S_total,
        "B_ratio":        B_total / B_hist_node,
        "S_ratio":        S_total / S_hist_node,
        "T_q":            T_q,
        "wj_sd_mean":     float(wj.mean()) if len(wj) > 0 else np.nan,
        "wj_sd_median":   float(np.median(wj)) if len(wj) > 0 else np.nan,
        "wj_sd_p95":      float(np.percentile(wj, 95)) if len(wj) > 0 else np.nan,
        "exceedance_rate": exceedance_rate,
        "n_under":        n_under,
        "T_arr":          T_arr,   # kept for CDF figure; large but manageable
    }

# ---------------------------------------------------------------------------
# Run N_CALIB scenarios
# ---------------------------------------------------------------------------
print(f"\nRunning {N_CALIB} calibration scenarios (Random-feasible, lambda=1)...")
results = []
for s in range(N_CALIB):
    t0 = time.time()
    r  = calib_replay(CALIB_BASE_SEED + s)
    results.append(r)
    print(f"  Scen {s+1:2d}/{N_CALIB}:  B/Bh={r['B_ratio']:.4f}  S/Sh={r['S_ratio']:.4f}"
          f"  exc_rate={r['exceedance_rate']:.4f}  under={r['n_under']}"
          f"  ({time.time()-t0:.1f}s)")

# ---------------------------------------------------------------------------
# Calibration summary
# ---------------------------------------------------------------------------
print("\n" + "="*65)
print("CALIBRATION RESULTS — Random-feasible at lambda=1")
print("="*65)

B_ratios = np.array([r["B_ratio"] for r in results])
S_ratios = np.array([r["S_ratio"] for r in results])
B_vals   = np.array([r["B"]       for r in results])
S_vals   = np.array([r["S"]       for r in results])
T_qs     = np.vstack([r["T_q"]    for r in results])   # (N_CALIB, 6)
wj_means = np.array([r["wj_sd_mean"] for r in results])
exc_rates= np.array([r["exceedance_rate"] for r in results])

se = lambda a: a.std() / np.sqrt(len(a))  # standard error

print(f"\n  {'Metric':<35}  {'Historical':>12}  {'CF mean':>12}  {'CF SE':>10}  {'Ratio':>8}")
print("  " + "-"*82)

def row(name, hist_val, cf_arr, fmt=".3f"):
    m  = cf_arr.mean()
    s  = se(cf_arr)
    r  = m / hist_val if hist_val != 0 else np.nan
    print(f"  {name:<35}  {hist_val:>12{fmt}}  {m:>12{fmt}}  {s:>10{fmt}}  {r:>8.4f}")

row("B (exceedance node-hours)",  B_hist_node, B_vals,   ".1f")
row("S (degC-node-hours)",        S_hist_node, S_vals,   ".1f")
row("B ratio to historical",      1.0,         B_ratios, ".4f")
row("S ratio to historical",      1.0,         S_ratios, ".4f")

print()
# Temperature quantile comparison
q_labels = ["p25", "p50", "p75", "p90", "p95", "p99"]
for qi, ql in enumerate(q_labels):
    row(f"T {ql} (degC)", hist_T_q[qi], T_qs[:, qi], ".3f")

print()
row("Within-job SD mean (degC)", hist_wj_sd.mean(), wj_means, ".4f")
row("Node exceedance rate",      hist_exceedance_rate, exc_rates, ".4f")

print()
B_pass = CALIB_PASS_LO <= B_ratios.mean() <= CALIB_PASS_HI
S_pass = CALIB_PASS_LO <= S_ratios.mean() <= CALIB_PASS_HI
print(f"  E[B_ratio] = {B_ratios.mean():.4f} +/- {se(B_ratios):.4f}"
      f"   target [{CALIB_PASS_LO}, {CALIB_PASS_HI}]   {'PASS' if B_pass else 'FAIL ***'}")
print(f"  E[S_ratio] = {S_ratios.mean():.4f} +/- {se(S_ratios):.4f}"
      f"   target [{CALIB_PASS_LO}, {CALIB_PASS_HI}]   {'PASS' if S_pass else 'FAIL ***'}")

overall_pass = B_pass and S_pass
print(f"\n  === CALIBRATION {'PASS' if overall_pass else 'FAIL'} ==="
      + (" — node-level metric ready for capacity sweep" if overall_pass
         else " — residual model needs further investigation"))

# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
print("\nGenerating calibration figures...")
fig, axes = plt.subplots(1, 3, figsize=(16, 5))
fig.suptitle("Phase 3B.2-C: Counterfactual calibration — Random-feasible at lambda=1",
             fontsize=12, fontweight="bold")

# Panel A: B/S ratio distributions across N_CALIB scenarios
ax = axes[0]
ax.hist(B_ratios, bins=10, alpha=0.7, color="#3377cc", label=f"B ratio  (mean={B_ratios.mean():.3f})")
ax.hist(S_ratios, bins=10, alpha=0.7, color="#ee7722", label=f"S ratio  (mean={S_ratios.mean():.3f})")
ax.axvline(1.0, color="black", lw=1.5, ls="--", label="target=1.0")
ax.axvspan(CALIB_PASS_LO, CALIB_PASS_HI, alpha=0.08, color="green", label=f"pass band [{CALIB_PASS_LO},{CALIB_PASS_HI}]")
ax.set_xlabel("CF ratio to historical")
ax.set_ylabel("Count")
ax.set_title(f"A. B/S calibration ratios\n({N_CALIB} scenarios)")
ax.legend(fontsize=8)

# Panel B: Temperature CDF — historical vs CF runs
ax = axes[1]
T_grid = np.linspace(40, 80, 300)
hist_cdf = np.mean(T_obs_all[:, None] <= T_grid[None, :], axis=0)
ax.plot(T_grid, hist_cdf, "k-", lw=2, label="Historical (observed)")
cf_cdfs = []
for r in results:
    T_a = r["T_arr"]
    if len(T_a) > 0:
        cdf_i = np.mean(T_a[:, None] <= T_grid[None, :], axis=0)
        cf_cdfs.append(cdf_i)
        ax.plot(T_grid, cdf_i, color="#3377cc", lw=0.5, alpha=0.3)
if cf_cdfs:
    cf_mean_cdf = np.mean(cf_cdfs, axis=0)
    ax.plot(T_grid, cf_mean_cdf, color="#3377cc", lw=2, ls="--", label="CF mean (N=20)")
ax.axvline(T_P95_THRESHOLD, color="#cc3333", lw=1, ls=":", label=f"T_95={T_P95_THRESHOLD:.1f}C")
ax.set_xlabel("Node T_p95 (degC)")
ax.set_ylabel("CDF")
ax.set_title("B. Temperature CDF\nblack=historical; blue=CF scenarios")
ax.legend(fontsize=8)
ax.set_xlim(40, 75)

# Panel C: Within-job SD — historical vs CF
ax = axes[2]
ax.hist(hist_wj_sd, bins=30, alpha=0.6, density=True, color="black", label="Historical")
all_cf_wj_sd = []
for r in results:
    # Re-compute per-job SD from T_arr shape — not available directly, use wj_sd_mean proxy
    pass
# Use per-scenario wj_sd_mean as a single number; plot distribution across scenarios
ax.axvline(hist_wj_sd.mean(), color="black", lw=2, ls="-", label=f"Hist mean={hist_wj_sd.mean():.3f}")
ax.axvline(hist_wj_sd.median() if hasattr(hist_wj_sd, 'median') else np.median(hist_wj_sd),
           color="black", lw=1.5, ls="--", label=f"Hist median={np.median(hist_wj_sd):.3f}")
for r in results:
    ax.axvline(r["wj_sd_mean"], color="#3377cc", lw=0.8, alpha=0.4)
ax.axvline(wj_means.mean(), color="#3377cc", lw=2, ls="-",
           label=f"CF mean={wj_means.mean():.3f} +/- {se(wj_means):.3f}")
ax.set_xlabel("Within-job T SD (degC)")
ax.set_ylabel("Density")
ax.set_title("C. Within-job temperature spread\nblack=historical; blue lines=CF scenarios")
ax.legend(fontsize=8)

plt.tight_layout()
out_fig = ANALYSIS_DIR / "phase3b2c_calibration.png"
plt.savefig(out_fig, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved {out_fig}")

# ---------------------------------------------------------------------------
# Save JSON
# ---------------------------------------------------------------------------
out = {
    "experiment"       : "phase3b2c_calibration",
    "n_calib"          : N_CALIB,
    "T_p95_threshold"  : T_P95_THRESHOLD,
    "B_hist_node"      : B_hist_node,
    "S_hist_node"      : S_hist_node,
    "hist_T_quantiles" : dict(zip(q_labels, hist_T_q.tolist())),
    "hist_wj_sd_mean"  : float(hist_wj_sd.mean()),
    "hist_exceedance_rate": hist_exceedance_rate,
    "calibration_pass" : bool(overall_pass),
    "B_ratio_mean"     : float(B_ratios.mean()),
    "B_ratio_se"       : float(se(B_ratios)),
    "S_ratio_mean"     : float(S_ratios.mean()),
    "S_ratio_se"       : float(se(S_ratios)),
    "cf_T_quantiles_mean": dict(zip(q_labels, T_qs.mean(axis=0).tolist())),
    "cf_wj_sd_mean"    : float(wj_means.mean()),
    "cf_exceedance_rate_mean": float(exc_rates.mean()),
    "scenario_B_ratios": B_ratios.tolist(),
    "scenario_S_ratios": S_ratios.tolist(),
}
with open(ANALYSIS_DIR / "phase3b2c_results.json", "w") as f:
    json.dump(out, f, indent=2, default=float)
print("Saved phase3b2c_results.json")
print("\n=== Done ===")
