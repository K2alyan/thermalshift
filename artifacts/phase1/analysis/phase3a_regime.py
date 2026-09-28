"""
Phase 3A.2: Diagnose the May-June 2025 thermal regime change.

Do NOT modify the frozen fingerprint or any Phase 3A headline results.
Five prespecified analyses only:
  1. Monthly temperature/power distribution shift
  2. Workload composition: May-June vs other months
  3. Node/rack participation patterns
  4. Rack-level prediction degradation: global vs localized
  5. Prespecified interaction model: dT ~ dP + F + F*dP

Outputs:
  phase3a_regime.json             -- all diagnostic metrics
  phase3a_monthly_thermal.png     -- monthly T / P distributions
  phase3a_rack_degradation.png    -- per-rack MAE delta (May-Jun vs rest)
  phase3a_interaction_model.png   -- interaction model fit
"""
# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.



import os
import json, warnings
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import stats
import os
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")

COHORT_DIR = Path(__file__).parent.parent
OUT_DIR    = COHORT_DIR / "analysis"
JOB_INFO   = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "frontier-completed-job-info.parquet"

MAY_JUNE = {"2025-05", "2025-06"}

# ── Load test set ──────────────────────────────────────────────────────────────
print("Loading test set and fingerprints...")
test_df = pq.read_table(OUT_DIR / "phase3a_test_set.parquet").to_pandas()
fp_df   = pq.read_table(OUT_DIR / "phase3a_fingerprint_2024.parquet").to_pandas()
fp_df   = fp_df.reset_index() if "node" not in fp_df.columns else fp_df

# Within-job demeaning (test_set.parquet stores raw T/P)
for col in ["T_p95", "T_hot_die_p95", "T_mean", "T_max", "P_mean"]:
    test_df[f"delta_{col}"] = (
        test_df[col] - test_df.groupby("job_idx")[col].transform("mean")
    )

test_df["month"] = pd.to_datetime(test_df["date_dir"]).dt.to_period("M").astype(str)
test_df["period"] = test_df["month"].apply(
    lambda m: "May-Jun" if m in MAY_JUNE else "other"
)

def rack_proxy(hostname):
    try:
        return int(''.join(filter(str.isdigit, hostname))) // 100
    except Exception:
        return np.nan

test_df["rack"] = test_df["node"].apply(rack_proxy)
fp_df["rack"]   = fp_df["node"].apply(rack_proxy)

print(f"  test_df: {len(test_df):,} obs, {test_df['job_idx'].nunique()} jobs, "
      f"{test_df['node'].nunique()} nodes")
print(f"  May-Jun obs: {(test_df['period']=='May-Jun').sum():,}  |  "
      f"other obs: {(test_df['period']=='other').sum():,}")


# ── Load job metadata ──────────────────────────────────────────────────────────
print("Loading job metadata...")
JOB_COLS = ["job_idx", "node_count", "run_time", "mean_power", "peak_power",
            "queue", "job_mode", "gpu_enabled", "user_id", "project_id",
            "project_prefix", "completion_state"]
jinfo = pq.read_table(JOB_INFO, columns=JOB_COLS).to_pandas()
jinfo["job_idx_int"] = jinfo["job_idx"].astype(int)
test_df["job_idx_int"] = test_df["job_idx"].astype(int)
test_df = test_df.merge(
    jinfo.drop(columns="job_idx"),
    on="job_idx_int", how="left"
)
print(f"  Job metadata join: {test_df['queue'].notna().sum():,} / {len(test_df):,} rows matched")


# ─────────────────────────────────────────────────────────────────────────────
# PART 1: Monthly temperature/power distribution shift
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Part 1: Monthly temperature/power distributions ===")

monthly_dist = []
for month, grp in test_df.groupby("month"):
    valid_t = grp["T_p95"].dropna()
    valid_p = grp["P_mean"].dropna()
    rec = {
        "month":           month,
        "period":          "May-Jun" if month in MAY_JUNE else "other",
        "n_obs":           int(len(grp)),
        "n_jobs":          int(grp["job_idx"].nunique()),
        "median_T_p95_C":  round(float(valid_t.median()), 3) if len(valid_t) else np.nan,
        "p95_T_p95_C":     round(float(valid_t.quantile(0.95)), 3) if len(valid_t) else np.nan,
        "median_P_mean_W": round(float(valid_p.median()), 1) if len(valid_p) else np.nan,
        "p95_P_mean_W":    round(float(valid_p.quantile(0.95)), 1) if len(valid_p) else np.nan,
    }
    if rec["median_P_mean_W"] and rec["median_P_mean_W"] > 0:
        rec["median_T_per_kW"] = round(rec["median_T_p95_C"] / (rec["median_P_mean_W"] / 1000), 3)
    else:
        rec["median_T_per_kW"] = np.nan
    monthly_dist.append(rec)

monthly_dist_df = pd.DataFrame(monthly_dist).sort_values("month")
print(f"\n  {'Month':8s}  {'period':7s}  {'n_jobs':>7}  {'med_T':>7}  "
      f"{'p95_T':>7}  {'med_P':>7}  {'T/kW':>7}")
for _, r in monthly_dist_df.iterrows():
    print(f"  {r['month']:8s}  {r['period']:7s}  {int(r['n_jobs']):>7}  "
          f"{r['median_T_p95_C']:>7.2f}  {r['p95_T_p95_C']:>7.2f}  "
          f"{r['median_P_mean_W']:>7.0f}  {r['median_T_per_kW']:>7.2f}")

# Figure: monthly T and P distributions
fig, axes = plt.subplots(3, 1, figsize=(11, 9), sharex=True)
months = monthly_dist_df["month"]
x = np.arange(len(months))
colors = ["tomato" if m in MAY_JUNE else "steelblue" for m in months]

ax = axes[0]
ax.bar(x, monthly_dist_df["median_T_p95_C"], color=colors, alpha=0.75, label="other / May-Jun")
ax.set_ylabel("Median T_p95 (degC)", fontsize=10)
ax.set_title("Monthly GPU temperature and power distributions\n(red = May-Jun)", fontsize=10)

ax = axes[1]
ax.bar(x, monthly_dist_df["median_P_mean_W"], color=colors, alpha=0.75)
ax.set_ylabel("Median P_mean (W/node)", fontsize=10)

ax = axes[2]
ax.bar(x, monthly_dist_df["median_T_per_kW"], color=colors, alpha=0.75)
ax.set_ylabel("Median T/kW (degC/kW)", fontsize=10)
ax.set_xlabel("Month", fontsize=10)

for ax in axes:
    ax.set_xticks(x)
    ax.set_xticklabels(months, rotation=45, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig(OUT_DIR / "phase3a_monthly_thermal.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  Saved phase3a_monthly_thermal.png")


# ─────────────────────────────────────────────────────────────────────────────
# PART 2: Workload composition — May-June vs other months
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Part 2: Workload composition ===")

# Job-level (one row per job)
job_level = test_df.drop_duplicates("job_idx_int").copy()

def compare_periods(col, label, categorical=False):
    mj  = job_level[job_level["period"] == "May-Jun"][col].dropna()
    oth = job_level[job_level["period"] == "other"][col].dropna()
    if categorical:
        print(f"\n  {label} distribution:")
        all_vals = pd.concat([mj, oth]).value_counts(normalize=True).index[:8]
        for v in all_vals:
            p_mj  = (mj  == v).mean()
            p_oth = (oth == v).mean()
            print(f"    {str(v):30s}  May-Jun: {p_mj:.3f}  other: {p_oth:.3f}")
    else:
        stat, p = stats.mannwhitneyu(mj, oth, alternative="two-sided")
        print(f"  {label:25s}: May-Jun med={mj.median():.1f}, other med={oth.median():.1f}, "
              f"MWU p={p:.3g}")
        return {"label": label, "mayjun_median": round(float(mj.median()), 3),
                "other_median": round(float(oth.median()), 3), "mwu_p": float(p)}

workload_comp = {}

# Continuous
for col, label in [("node_count",  "node_count"),
                   ("run_time",    "run_time_s"),
                   ("mean_power",  "mean_power_W"),
                   ("peak_power",  "peak_power_W")]:
    res = compare_periods(col, label)
    if res:
        workload_comp[col] = res

# GPU power per node (derived)
job_level["power_per_node"] = job_level["mean_power"] / job_level["node_count"]
res = compare_periods("power_per_node", "power_per_node_W")
if res:
    workload_comp["power_per_node"] = res

# Categorical
print()
for col, label in [("queue",       "Queue"),
                   ("job_mode",    "Job mode"),
                   ("gpu_enabled", "GPU enabled"),
                   ("completion_state", "Completion state")]:
    compare_periods(col, label, categorical=True)

# Project/user diversity
mj_jobs  = job_level[job_level["period"] == "May-Jun"]
oth_jobs = job_level[job_level["period"] == "other"]
print(f"\n  Unique projects:  May-Jun={mj_jobs['project_id'].nunique()}, "
      f"other={oth_jobs['project_id'].nunique()}")
print(f"  Unique users:     May-Jun={mj_jobs['user_id'].nunique()}, "
      f"other={oth_jobs['user_id'].nunique()}")
print(f"  Unique jobs:      May-Jun={len(mj_jobs):,}, other={len(oth_jobs):,}")

# Are the same projects/users active in May-Jun as the rest?
mj_proj  = set(mj_jobs["project_id"].dropna())
oth_proj = set(oth_jobs["project_id"].dropna())
print(f"  Projects in May-Jun only: {len(mj_proj - oth_proj)}")
print(f"  Projects in other only:   {len(oth_proj - mj_proj)}")
print(f"  Projects in both:         {len(mj_proj & oth_proj)}")
workload_comp["project_diversity"] = {
    "mayjun_projects": len(mj_proj), "other_projects": len(oth_proj),
    "mayjun_only": len(mj_proj - oth_proj), "other_only": len(oth_proj - mj_proj),
    "shared": len(mj_proj & oth_proj),
}


# ─────────────────────────────────────────────────────────────────────────────
# PART 3: Node / rack participation patterns
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Part 3: Node/rack participation ===")

# Per-node: fraction of observations in May-Jun
node_mayjun_frac = (
    test_df.groupby("node")["period"]
    .apply(lambda x: (x == "May-Jun").mean())
    .rename("mayjun_frac")
    .reset_index()
)
node_mayjun_frac = node_mayjun_frac.merge(
    fp_df[["node", "FA_2024", "n_jobs_train"]].rename(columns={"FA_2024": "F_2024"}),
    on="node", how="left"
)
node_mayjun_frac["abs_F"] = node_mayjun_frac["F_2024"].abs()

# Does May-Jun use different thermal fingerprint nodes?
r_frac_F, p_frac_F = stats.pearsonr(
    node_mayjun_frac["mayjun_frac"].dropna(),
    node_mayjun_frac["F_2024"].dropna(),
)
r_frac_absF, p_frac_absF = stats.pearsonr(
    node_mayjun_frac["mayjun_frac"],
    node_mayjun_frac["abs_F"],
)
r_frac_supp, p_frac_supp = stats.pearsonr(
    node_mayjun_frac["mayjun_frac"].dropna(),
    node_mayjun_frac["n_jobs_train"].dropna(),
)
print(f"  r(mayjun_frac, F_2024)      = {r_frac_F:+.4f}  (p={p_frac_F:.3g})")
print(f"  r(mayjun_frac, |F_2024|)    = {r_frac_absF:+.4f}  (p={p_frac_absF:.3g})")
print(f"  r(mayjun_frac, n_train_jobs) = {r_frac_supp:+.4f}  (p={p_frac_supp:.3g})")

# Nodes absent from May-Jun entirely
nodes_in_mayjun = set(test_df[test_df["period"] == "May-Jun"]["node"])
nodes_in_other  = set(test_df[test_df["period"] == "other"]["node"])
print(f"\n  Nodes in May-Jun: {len(nodes_in_mayjun)}")
print(f"  Nodes in other months: {len(nodes_in_other)}")
print(f"  Nodes in May-Jun only: {len(nodes_in_mayjun - nodes_in_other)}")
print(f"  Nodes absent from May-Jun: {len(nodes_in_other - nodes_in_mayjun)}")

# Per-rack: fraction in May-Jun
rack_mayjun = (
    test_df.groupby("rack")["period"]
    .apply(lambda x: (x == "May-Jun").mean())
    .rename("mayjun_frac")
    .reset_index()
)
print(f"\n  Racks: mean May-Jun fraction = {rack_mayjun['mayjun_frac'].mean():.3f}, "
      f"SD = {rack_mayjun['mayjun_frac'].std():.3f}")
print(f"  (if uniform ~10%, deviation would suggest localized usage)")


# ─────────────────────────────────────────────────────────────────────────────
# PART 4: Rack-level prediction degradation — global vs localized
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Part 4: Rack-level prediction degradation ===")

def rack_mae(sub):
    v = sub[["F_2024", "delta_T_p95"]].dropna()
    if len(v) < 10:
        return np.nan
    return float(np.mean(np.abs(v["F_2024"] - v["delta_T_p95"])))

rack_metrics = []
for rack in sorted(test_df["rack"].dropna().unique()):
    sub_mj  = test_df[(test_df["rack"] == rack) & (test_df["period"] == "May-Jun")]
    sub_oth = test_df[(test_df["rack"] == rack) & (test_df["period"] == "other")]
    mae_mj  = rack_mae(sub_mj)
    mae_oth = rack_mae(sub_oth)
    if np.isfinite(mae_mj) and np.isfinite(mae_oth):
        rack_metrics.append({
            "rack": rack,
            "mae_mayjun": round(mae_mj, 4),
            "mae_other":  round(mae_oth, 4),
            "delta_mae":  round(mae_mj - mae_oth, 4),
            "n_obs_mayjun": int(len(sub_mj)),
            "n_obs_other":  int(len(sub_oth)),
        })

rack_df = pd.DataFrame(rack_metrics)
n_degrade = (rack_df["delta_mae"] > 0).sum()
n_improve  = (rack_df["delta_mae"] < 0).sum()
mean_delta = rack_df["delta_mae"].mean()
print(f"  Racks with both May-Jun and other obs: {len(rack_df)}")
print(f"  Racks with worse MAE in May-Jun (delta>0): {n_degrade} / {len(rack_df)} "
      f"({n_degrade/len(rack_df)*100:.1f}%)")
print(f"  Racks with better MAE in May-Jun (delta<0): {n_improve}")
print(f"  Mean delta_MAE: {mean_delta:+.4f} degC")
print(f"  Median delta_MAE: {rack_df['delta_mae'].median():+.4f} degC")
print(f"  delta_MAE range: [{rack_df['delta_mae'].min():.3f}, {rack_df['delta_mae'].max():.3f}]")

# Top degrading racks
print(f"\n  Top 10 most degraded racks (delta_MAE):")
top_racks = rack_df.nlargest(10, "delta_mae")
for _, r in top_racks.iterrows():
    print(f"    Rack {int(r['rack']):3d}: delta={r['delta_mae']:+.3f}, "
          f"mae_mj={r['mae_mayjun']:.3f}, mae_oth={r['mae_other']:.3f}, "
          f"n_mj={r['n_obs_mayjun']}, n_oth={r['n_obs_other']}")

# Rack degradation figure
fig, ax = plt.subplots(figsize=(12, 4))
sorted_rack = rack_df.sort_values("delta_mae", ascending=False)
colors = ["tomato" if d > 0 else "steelblue" for d in sorted_rack["delta_mae"]]
ax.bar(range(len(sorted_rack)), sorted_rack["delta_mae"], color=colors, alpha=0.75)
ax.axhline(0, color="k", lw=0.8)
ax.axhline(mean_delta, color="darkred", lw=1.5, ls="--",
           label=f"mean delta={mean_delta:+.3f} degC")
ax.set_xlabel("Rack (sorted by degradation)", fontsize=10)
ax.set_ylabel("MAE(May-Jun) - MAE(other) (degC)", fontsize=10)
ax.set_title(f"Per-rack prediction degradation in May-June 2025\n"
             f"{n_degrade}/{len(rack_df)} racks degrade ({n_degrade/len(rack_df)*100:.0f}%)",
             fontsize=10)
ax.legend(fontsize=9)
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig(OUT_DIR / "phase3a_rack_degradation.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  Saved phase3a_rack_degradation.png")


# ─────────────────────────────────────────────────────────────────────────────
# PART 5: Prespecified interaction model  dT ~ dP + F + F*dP
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Part 5: Interaction model dT ~ dP + F + F*dP ===")

def fit_interaction(sub, label=""):
    sub = sub[["F_2024", "delta_T_p95", "delta_P_mean"]].dropna()
    if len(sub) < 50:
        return None
    dT = sub["delta_T_p95"].values
    F  = sub["F_2024"].values
    dP = sub["delta_P_mean"].values
    FdP = F * dP

    # M2: dT ~ dP + F  (replicate Phase 3A M1)
    X2 = np.column_stack([np.ones(len(dT)), dP, F])
    b2, _, _, _ = np.linalg.lstsq(X2, dT, rcond=None)
    pred2 = X2 @ b2
    r2_m2 = 1 - np.sum((dT - pred2)**2) / np.sum((dT - dT.mean())**2)

    # M3: dT ~ dP + F + F*dP
    X3 = np.column_stack([np.ones(len(dT)), dP, F, FdP])
    b3, _, _, _ = np.linalg.lstsq(X3, dT, rcond=None)
    pred3 = X3 @ b3
    r2_m3 = 1 - np.sum((dT - pred3)**2) / np.sum((dT - dT.mean())**2)
    mae3  = float(np.mean(np.abs(dT - pred3)))

    # Bootstrap SE for b_FP
    rng = np.random.default_rng(42)
    n = len(dT)
    boot_bFP = []
    for _ in range(1000):
        idx = rng.integers(0, n, n)
        Xb = X3[idx]; yb = dT[idx]
        try:
            bb, _, _, _ = np.linalg.lstsq(Xb, yb, rcond=None)
            boot_bFP.append(bb[3])
        except Exception:
            pass
    bFP_ci = (float(np.percentile(boot_bFP, 2.5)),
              float(np.percentile(boot_bFP, 97.5)))

    print(f"\n  [{label}] n={len(sub):,}")
    print(f"    M2 (dT ~ dP + F):       R2={r2_m2:.4f}")
    print(f"    M3 (dT ~ dP + F + F*dP): R2={r2_m3:.4f}, MAE={mae3:.4f} degC")
    print(f"    Coefficients: intercept={b3[0]:.4f}, b_dP={b3[1]:.6f}, "
          f"b_F={b3[2]:.4f}, b_FP={b3[3]:.6f}")
    print(f"    b_FP bootstrap 95% CI: [{bFP_ci[0]:.6f}, {bFP_ci[1]:.6f}]")
    print(f"    delta_R2 (M3 vs M2): {r2_m3 - r2_m2:+.4f}")

    return {
        "label": label, "n_obs": int(len(sub)),
        "M2_R2": round(r2_m2, 4),
        "M3_R2": round(r2_m3, 4),
        "M3_MAE_C": round(mae3, 4),
        "b_intercept": round(float(b3[0]), 6),
        "b_dP": round(float(b3[1]), 6),
        "b_F":  round(float(b3[2]), 4),
        "b_FP": round(float(b3[3]), 6),
        "b_FP_ci_95": [round(bFP_ci[0], 6), round(bFP_ci[1], 6)],
        "delta_R2_M3_vs_M2": round(r2_m3 - r2_m2, 4),
    }

interaction_results = {}

# Full dataset
res_all = fit_interaction(test_df, "all months")
if res_all:
    interaction_results["all_months"] = res_all

# Other months only
res_oth = fit_interaction(test_df[test_df["period"] == "other"], "other months")
if res_oth:
    interaction_results["other_months"] = res_oth

# May-June only
res_mj = fit_interaction(test_df[test_df["period"] == "May-Jun"], "May-Jun")
if res_mj:
    interaction_results["may_jun"] = res_mj

# Interpretation
print("\n  Interpretation:")
if res_all:
    b = res_all["b_FP"]
    ci = res_all["b_FP_ci_95"]
    if ci[0] > 0:
        print(f"  b_FP = {b:.6f} [{ci[0]:.6f}, {ci[1]:.6f}]: significantly > 0.")
        print("  Hot nodes become disproportionately hotter as workload power rises.")
    elif ci[1] < 0:
        print(f"  b_FP = {b:.6f} [{ci[0]:.6f}, {ci[1]:.6f}]: significantly < 0.")
        print("  Unexpected sign — hot nodes may have different thermal coupling.")
    else:
        print(f"  b_FP = {b:.6f} [{ci[0]:.6f}, {ci[1]:.6f}]: CI spans zero.")
        print("  No strong evidence of multiplicative interaction between F and power.")

# Interaction figure: F * dP partial effect
fig, axes = plt.subplots(1, 3, figsize=(14, 4.5))
for ax, (sub, label) in zip(axes, [
    (test_df, "All months"),
    (test_df[test_df["period"] == "other"], "Other months"),
    (test_df[test_df["period"] == "May-Jun"], "May-Jun"),
]):
    sub_v = sub[["F_2024", "delta_T_p95", "delta_P_mean"]].dropna()
    if len(sub_v) < 50:
        ax.set_title(f"{label}\n(insufficient data)")
        continue
    FdP = (sub_v["F_2024"] * sub_v["delta_P_mean"]).values
    dT  = sub_v["delta_T_p95"].values

    # Partial regression: residualize dT and F*dP on dP and F
    X_ctrl = np.column_stack([np.ones(len(dT)),
                               sub_v["delta_P_mean"].values,
                               sub_v["F_2024"].values])
    def resid(y):
        b, _, _, _ = np.linalg.lstsq(X_ctrl, y, rcond=None)
        return y - X_ctrl @ b

    dT_r  = resid(dT)
    FdP_r = resid(FdP)

    # Bin F*dP for visualization
    bins = np.percentile(FdP_r, np.linspace(0, 100, 21))
    bin_x, bin_y = [], []
    for lo, hi in zip(bins[:-1], bins[1:]):
        mask = (FdP_r >= lo) & (FdP_r < hi)
        if mask.sum() >= 5:
            bin_x.append(float(np.median(FdP_r[mask])))
            bin_y.append(float(np.mean(dT_r[mask])))

    ax.scatter(FdP_r[::5], dT_r[::5], alpha=0.04, s=2, color="gray")
    ax.plot(bin_x, bin_y, "ro-", ms=4, lw=1.5)
    sl, ic, r, _, _ = stats.linregress(FdP_r, dT_r)
    ax.set_xlabel("F x dP (partial, after removing dP + F effects)", fontsize=8)
    ax.set_ylabel("dT_p95 (partial)" if ax == axes[0] else "", fontsize=8)
    ax.set_title(f"{label}\npartial slope={sl:.5f}, r={r:.3f}", fontsize=9)
    ax.axhline(0, color="k", lw=0.5, ls="--", alpha=0.5)
    ax.axvline(0, color="k", lw=0.5, ls="--", alpha=0.5)
    ax.grid(alpha=0.2)

plt.suptitle("Partial regression: interaction term F x dP", fontsize=10)
plt.tight_layout()
plt.savefig(OUT_DIR / "phase3a_interaction_model.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  Saved phase3a_interaction_model.png")


# ── Save results ──────────────────────────────────────────────────────────────
results = {
    "monthly_distributions": monthly_dist_df.to_dict(orient="records"),
    "workload_composition": workload_comp,
    "node_participation": {
        "r_mayjun_frac_vs_F":    round(float(r_frac_F), 4),
        "r_mayjun_frac_vs_absF": round(float(r_frac_absF), 4),
        "r_mayjun_frac_vs_supp": round(float(r_frac_supp), 4),
        "n_nodes_in_mayjun":     int(len(nodes_in_mayjun)),
        "n_nodes_absent_mayjun": int(len(nodes_in_other - nodes_in_mayjun)),
    },
    "rack_degradation": {
        "n_racks_analyzed":   int(len(rack_df)),
        "n_racks_degrade":    int(n_degrade),
        "frac_racks_degrade": round(float(n_degrade / len(rack_df)), 4),
        "mean_delta_mae_C":   round(float(mean_delta), 4),
        "median_delta_mae_C": round(float(rack_df["delta_mae"].median()), 4),
        "rack_detail":        rack_df.to_dict(orient="records"),
    },
    "interaction_model": interaction_results,
}

with open(OUT_DIR / "phase3a_regime.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nSaved phase3a_regime.json")
print("Done.")
