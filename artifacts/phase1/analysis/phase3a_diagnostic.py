"""
Phase 3A.1 diagnostic: resolve the training-support quartile reversal.

Loads the frozen fingerprint and test set produced by phase3a_validation.py,
does a targeted re-pass through pre-2025 jobs to get per-node fingerprint SE,
then runs six diagnostic analyses without modifying any Phase 3A primary output.

Outputs:
  phase3a_diagnostic.json        — all diagnostic metrics
  phase3a_monthly_calib.png      — monthly calibration slope / MAE / residual bias
  phase3a_support_vs_mag.png     — |F| by training-support quartile
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

DATA_DIR   = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "job-telemetry"
COHORT_DIR = Path(__file__).parent.parent
OUT_DIR    = COHORT_DIR / "analysis"

# ── Load frozen fingerprint and test set ──────────────────────────────────────
print("Loading artifacts...")
fp_df = pq.read_table(OUT_DIR / "phase3a_fingerprint_2024.parquet").to_pandas()
fp_df.index.name = "node"
fp_df = fp_df.reset_index()

test_df = pq.read_table(OUT_DIR / "phase3a_test_set.parquet").to_pandas()

# Within-job demeaning (test_set.parquet stores raw T; reconstruct deltas)
for col in ["T_p95", "T_hot_die_p95", "T_mean", "T_max", "P_mean"]:
    test_df[f"delta_{col}"] = (
        test_df[col] - test_df.groupby("job_idx")[col].transform("mean")
    )

# Load cohort job list for training jobs
cohort_jobs  = pd.read_csv(COHORT_DIR / "cohort_job_list.csv")
longitudinal = cohort_jobs[cohort_jobs["selection_role"] == "longitudinal_cohort"].copy()
train_jobs   = longitudinal[longitudinal["date_dir"] < "2025"].copy()
cohort_manifest = pd.read_csv(COHORT_DIR / "cohort_manifest.csv")
cohort_nodes = set(cohort_manifest["hostname"])

print(f"  fp_df: {len(fp_df)} nodes")
print(f"  test_df: {len(test_df):,} node-job records, "
      f"{test_df['job_idx'].nunique()} jobs, {test_df['node'].nunique()} nodes")
print(f"  train_jobs: {len(train_jobs)} pre-2025 longitudinal jobs")


# ── Helpers ───────────────────────────────────────────────────────────────────

def gcd_cols_for(temp_df, nodes_subset):
    cols = [c for c in temp_df.columns if c.startswith("frontier") and "_gcd" in c]
    return [c for c in cols if c.split("_")[0] in nodes_subset]

def node_map_from(cols):
    nm = {}
    for col in cols:
        nm.setdefault(col.split("_")[0], []).append(col)
    return nm

def node_scalar_mean(temp_df, nm):
    result = {}
    for node, cols in nm.items():
        vals = temp_df[cols].values.flatten().astype(float)
        valid = vals[np.isfinite(vals)]
        if len(valid):
            result[node] = float(valid.mean())
    return result

def quartile_metrics(sub, fp_col, dt_col, label):
    """Per-quartile metrics across F and dT vectors."""
    valid = sub[[fp_col, dt_col]].dropna()
    F  = valid[fp_col].values
    dT = valid[dt_col].values
    if len(F) < 10:
        return {"label": label, "n_obs": len(F), "note": "too few"}
    r,  _ = stats.pearsonr(F, dT)
    sr, _ = stats.spearmanr(F, dT)
    mae   = float(np.mean(np.abs(F - dT)))
    rmse  = float(np.sqrt(np.mean((F - dT)**2)))
    sa    = float(np.mean(np.sign(F) == np.sign(dT)))
    sl, ic, _, _, _ = stats.linregress(F, dT)
    ss_tot = float(np.sum((dT - dT.mean())**2))
    r2 = 1.0 - float(np.sum((dT - (ic + sl * F))**2)) / ss_tot if ss_tot > 0 else np.nan
    return {
        "label": label, "n_obs": int(len(F)),
        "pearson_r": round(float(r),  4),
        "spearman_r": round(float(sr), 4),
        "mae_C":  round(mae,  4),
        "rmse_C": round(rmse, 4),
        "sign_agreement": round(sa, 4),
        "calib_slope":    round(float(sl), 4),
        "r2": round(float(r2), 4),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1: Training-support quartile — fingerprint magnitude profile
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Section 1: Training-support quartile — fingerprint magnitude + prediction ===")

fp_df["abs_F"] = fp_df["FA_2024"].abs()
fp_df["support_Q"] = pd.qcut(
    fp_df["n_jobs_train"], 4,
    labels=["Q1","Q2","Q3","Q4"], duplicates="drop"
)

node_to_squart = fp_df.set_index("node")["support_Q"].to_dict()
test_df["support_Q"] = test_df["node"].map(node_to_squart)

print(f"\n  {'Quartile':8s}  {'n_nodes':>8}  {'med_njobs':>10}  {'med|F|':>8}  "
      f"{'SD(F)':>7}  {'P(|F|>1C)':>10}")

support_q_summary = {}
for q in ["Q1","Q2","Q3","Q4"]:
    sub_fp = fp_df[fp_df["support_Q"] == q]
    n_nodes  = len(sub_fp)
    med_nj   = sub_fp["n_jobs_train"].median()
    med_absF = sub_fp["abs_F"].median()
    sd_F     = sub_fp["FA_2024"].std()
    p_hot    = (sub_fp["abs_F"] > 1.0).mean()
    print(f"  {q:8s}  {n_nodes:>8}  {med_nj:>10.0f}  {med_absF:>8.3f}  "
          f"{sd_F:>7.3f}  {p_hot:>10.3f}")
    support_q_summary[q] = {
        "n_nodes": int(n_nodes), "med_n_jobs": float(med_nj),
        "median_abs_F_C": round(float(med_absF), 4),
        "sd_F_C": round(float(sd_F), 4),
        "p_abs_F_gt1C": round(float(p_hot), 4),
    }

print(f"\n  {'Quartile':8s}  {'n_obs':>8}  {'r':>6}  {'MAE':>6}  "
      f"{'RMSE':>6}  {'slope':>6}  {'sign_ag':>8}")
support_q_pred = {}
for q in ["Q1","Q2","Q3","Q4"]:
    sub = test_df[test_df["support_Q"] == q]
    m = quartile_metrics(sub, "F_2024", "delta_T_p95", q)
    support_q_summary[q].update(m)
    support_q_pred[q] = m
    print(f"  {q:8s}  {m['n_obs']:>8,}  {m['pearson_r']:>6.4f}  {m['mae_C']:>6.4f}  "
          f"{m['rmse_C']:>6.4f}  {m['calib_slope']:>6.4f}  {m['sign_agreement']:>8.4f}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 2: Re-pass through 2024 training jobs to compute per-node SE
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Section 2: Re-pass for per-node fingerprint SE ===")

FA_obs = {}  # node -> list of within-job residuals
n_train = len(train_jobs)

for i, (_, row) in enumerate(train_jobs.iterrows()):
    if i % 500 == 0:
        print(f"  SE pass: {i}/{n_train}", flush=True)
    try:
        job_str = str(row["job_idx"]).zfill(6)
        temp = pq.read_table(
            DATA_DIR / row["date_dir"] / job_str / f"{job_str}-cleaned-temperature.parquet"
        ).to_pandas()
    except Exception:
        continue

    cols = gcd_cols_for(temp, cohort_nodes)
    if not cols:
        continue
    nm = node_map_from(cols)
    means = node_scalar_mean(temp, nm)
    if len(means) < 2:
        continue

    jm = np.mean(list(means.values()))
    for node, val in means.items():
        FA_obs.setdefault(node, []).append(val - jm)

# Compute SD and SE per node
node_se = {}
node_sd = {}
for node, obs in FA_obs.items():
    if len(obs) >= 3:
        sd = float(np.std(obs, ddof=1))
        se = sd / np.sqrt(len(obs))
        node_sd[node] = sd
        node_se[node] = se

fp_df["F_sd"]  = fp_df["node"].map(node_sd)
fp_df["F_se"]  = fp_df["node"].map(node_se)
fp_df["unc_Q"] = pd.qcut(
    fp_df["F_se"].dropna(), 4,
    labels=["U1","U2","U3","U4"], duplicates="drop"
)
node_to_uncq = fp_df.set_index("node")["unc_Q"].to_dict()
test_df["unc_Q"] = test_df["node"].map(node_to_uncq)

print(f"\n  Nodes with SE estimate: {fp_df['F_se'].notna().sum()}")
print(f"  Median SE: {fp_df['F_se'].median():.4f} degC")
print(f"  SE range: [{fp_df['F_se'].min():.4f}, {fp_df['F_se'].max():.4f}] degC")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 3: Fingerprint uncertainty quartile analysis
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Section 3: Fingerprint uncertainty (SE) quartile analysis ===")
print("  U1 = lowest SE (most precisely estimated), U4 = highest SE")

print(f"\n  {'Quartile':8s}  {'n_nodes':>8}  {'med_SE':>8}  {'med|F|':>8}  "
      f"{'P(|F|>1C)':>10}")

unc_q_summary = {}
for q in ["U1","U2","U3","U4"]:
    sub_fp = fp_df[fp_df["unc_Q"] == q]
    n_nodes  = len(sub_fp)
    med_se   = sub_fp["F_se"].median()
    med_absF = sub_fp["abs_F"].median()
    p_hot    = (sub_fp["abs_F"] > 1.0).mean()
    print(f"  {q:8s}  {n_nodes:>8}  {med_se:>8.4f}  {med_absF:>8.3f}  {p_hot:>10.3f}")
    unc_q_summary[q] = {
        "n_nodes": int(n_nodes), "med_se_C": round(float(med_se), 5),
        "median_abs_F_C": round(float(med_absF), 4),
        "p_abs_F_gt1C": round(float(p_hot), 4),
    }

print(f"\n  {'Quartile':8s}  {'n_obs':>8}  {'r':>6}  {'MAE':>6}  "
      f"{'RMSE':>6}  {'slope':>6}  {'sign_ag':>8}")
unc_q_pred = {}
for q in ["U1","U2","U3","U4"]:
    sub = test_df[test_df["unc_Q"] == q]
    m = quartile_metrics(sub, "F_2024", "delta_T_p95", q)
    unc_q_summary[q].update(m)
    unc_q_pred[q] = m
    print(f"  {q:8s}  {m['n_obs']:>8,}  {m['pearson_r']:>6.4f}  {m['mae_C']:>6.4f}  "
          f"{m['rmse_C']:>6.4f}  {m['calib_slope']:>6.4f}  {m['sign_agreement']:>8.4f}")


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 4: Correlates of n_jobs_train
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Section 4: What does training support correlate with? ===")

# Mean power per node from test set
node_power = test_df.groupby("node")["P_mean"].mean().rename("mean_power_test")
fp_df = fp_df.merge(node_power.reset_index(), on="node", how="left")

# Date-range proxy: extract first 4 chars of date_dir as year, for longitudinal jobs
# Active span: from cohort_job_list.csv
node_dates = (
    longitudinal.groupby("job_idx")["date_dir"]
    # we need per-node date range from test_df
)
node_date_range = (
    test_df.groupby("node")["date_dir"]
    .agg(lambda x: (
        pd.to_datetime(x).max() - pd.to_datetime(x).min()
    ).days)
    .rename("active_span_days_test")
)
fp_df = fp_df.merge(node_date_range.reset_index(), on="node", how="left")

# Rack proxy from hostname: frontier{NNNNN} — group first 3 digits as rack proxy
def rack_proxy(hostname):
    try:
        n = int(''.join(filter(str.isdigit, hostname)))
        return n // 100   # groups of 100 nodes as rack proxy
    except Exception:
        return np.nan

fp_df["rack_proxy"] = fp_df["node"].apply(rack_proxy)

corr_targets = {
    "|F|":          fp_df["abs_F"],
    "SE":           fp_df["F_se"],
    "mean_power":   fp_df["mean_power_test"],
    "active_span":  fp_df["active_span_days_test"],
    "rack_proxy":   fp_df["rack_proxy"],
}

print(f"\n  Correlations with n_jobs_train:")
n_corr = {}
for name, col in corr_targets.items():
    sub = fp_df[["n_jobs_train", col.name if hasattr(col, 'name') else name]].copy()
    sub.columns = ["n", "x"]
    sub = sub.dropna()
    if len(sub) >= 10:
        r,  p  = stats.pearsonr(sub["n"], sub["x"])
        sr, sp = stats.spearmanr(sub["n"], sub["x"])
        print(f"    {name:15s}: Pearson r={r:+.4f} (p={p:.3g}), "
              f"Spearman r={sr:+.4f} (p={sp:.3g}), n={len(sub)}")
        n_corr[name] = {
            "pearson_r": round(float(r), 4), "pearson_p": float(p),
            "spearman_r": round(float(sr), 4), "spearman_p": float(sp),
            "n": int(len(sub)),
        }

# Does SE correlate with |F|? (diagnostic: high-|F| nodes should have noisier estimates)
sub_se_f = fp_df[["F_se", "abs_F"]].dropna()
if len(sub_se_f) >= 10:
    r_sef, p_sef = stats.pearsonr(sub_se_f["F_se"], sub_se_f["abs_F"])
    print(f"\n  r(SE, |F|) = {r_sef:+.4f} (p={p_sef:.3g}, n={len(sub_se_f)})")
    n_corr["SE_vs_absF"] = {
        "pearson_r": round(float(r_sef), 4), "pearson_p": float(p_sef),
        "n": int(len(sub_se_f)),
    }


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 5: Matched analysis — compare support quartiles within |F| bands
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Section 5: Support comparison within |F| magnitude bands ===")

fp_df["F_band"] = pd.cut(
    fp_df["abs_F"],
    bins=[0, 0.5, 1.0, 2.0, 99.0],
    labels=["<0.5C", "0.5-1C", "1-2C", ">2C"],
)
node_to_fband = fp_df.set_index("node")["F_band"].to_dict()
test_df["F_band"] = test_df["node"].map(node_to_fband)

print(f"\n  {'Band':8s}  {'Support':6s}  {'n_nodes':>8}  {'n_obs':>8}  "
      f"{'r':>6}  {'MAE':>6}  {'slope':>6}")

matched_results = {}
for band in ["<0.5C", "0.5-1C", "1-2C", ">2C"]:
    band_fp  = fp_df[fp_df["F_band"] == band]
    band_test = test_df[test_df["F_band"] == band]
    matched_results[band] = {}

    for q_label, q_mask in [("lo_supp", band_fp["support_Q"].isin(["Q1","Q2"])),
                             ("hi_supp", band_fp["support_Q"].isin(["Q3","Q4"]))]:
        q_nodes = set(band_fp[q_mask]["node"])
        sub = band_test[band_test["node"].isin(q_nodes)]
        m = quartile_metrics(sub, "F_2024", "delta_T_p95", f"{band}_{q_label}")
        n_nd = len(q_nodes & set(sub["node"].unique()))
        print(f"  {band:8s}  {q_label:6s}  {n_nd:>8}  {m['n_obs']:>8,}  "
              f"{m.get('pearson_r', float('nan')):>6.4f}  "
              f"{m.get('mae_C', float('nan')):>6.4f}  "
              f"{m.get('calib_slope', float('nan')):>6.4f}")
        matched_results[band][q_label] = m


# ─────────────────────────────────────────────────────────────────────────────
# SECTION 6: Monthly calibration slope / MAE / residual bias
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Section 6: Monthly calibration (2025 holdout) ===")

test_df["month"] = pd.to_datetime(test_df["date_dir"]).dt.to_period("M").astype(str)
test_df["resid"] = test_df["delta_T_p95"] - test_df["F_2024"]

monthly = []
for month, grp in test_df.groupby("month"):
    sub = grp[["F_2024", "delta_T_p95", "resid"]].dropna()
    if len(sub) < 50:
        continue
    r, _   = stats.pearsonr(sub["F_2024"], sub["delta_T_p95"])
    mae    = float(np.mean(np.abs(sub["F_2024"] - sub["delta_T_p95"])))
    sl, ic, _, _, _ = stats.linregress(sub["F_2024"], sub["delta_T_p95"])
    med_resid = float(sub["resid"].median())
    monthly.append({
        "month": month,
        "n_obs": int(len(sub)),
        "pearson_r": round(float(r), 4),
        "mae_C": round(mae, 4),
        "calib_slope": round(float(sl), 4),
        "median_residual_C": round(med_resid, 4),
    })

monthly_df = pd.DataFrame(monthly).sort_values("month")
print(f"\n  {'Month':8s}  {'n_obs':>7}  {'r':>6}  {'MAE':>6}  "
      f"{'slope':>6}  {'med_resid':>10}")
for _, row in monthly_df.iterrows():
    print(f"  {row['month']:8s}  {int(row['n_obs']):>7,}  {row['pearson_r']:>6.4f}  "
          f"{row['mae_C']:>6.4f}  {row['calib_slope']:>6.4f}  "
          f"{row['median_residual_C']:>10.4f}")

# Monthly calibration plot
fig, axes = plt.subplots(3, 1, figsize=(10, 9), sharex=True)
months = monthly_df["month"]
x = np.arange(len(months))

ax = axes[0]
ax.plot(x, monthly_df["calib_slope"], "o-", color="steelblue", lw=1.5)
ax.axhline(1.0, color="k", lw=0.8, ls="--", alpha=0.5, label="ideal slope=1")
ax.set_ylabel("Calibration slope", fontsize=10)
ax.set_ylim(0.5, 1.5)
ax.legend(fontsize=8)
ax.set_title("Monthly calibration: frozen 2024 fingerprint predicting 2025 thermal residuals",
             fontsize=10)

ax = axes[1]
ax.plot(x, monthly_df["mae_C"], "o-", color="darkorange", lw=1.5)
ax.set_ylabel("MAE (degC)", fontsize=10)
ax.set_ylim(0)

ax = axes[2]
ax.plot(x, monthly_df["median_residual_C"], "o-", color="seagreen", lw=1.5)
ax.axhline(0, color="k", lw=0.8, ls="--", alpha=0.5)
ax.set_ylabel("Median residual (degC)", fontsize=10)
ax.set_xlabel("Month", fontsize=10)

for ax in axes:
    ax.set_xticks(x)
    ax.set_xticklabels(months, rotation=45, ha="right", fontsize=8)
    ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig(OUT_DIR / "phase3a_monthly_calib.png", dpi=150, bbox_inches="tight")
plt.close()
print("\n  Saved phase3a_monthly_calib.png")

# Support-vs-magnitude figure
fig, axes = plt.subplots(1, 2, figsize=(11, 4.5))

ax = axes[0]
q_order = ["Q1","Q2","Q3","Q4"]
med_absF = [fp_df[fp_df["support_Q"] == q]["abs_F"].median() for q in q_order]
p_hot    = [fp_df[fp_df["support_Q"] == q]["abs_F"].gt(1).mean() for q in q_order]
r_vals   = [support_q_pred[q]["pearson_r"] for q in q_order]
mae_vals = [support_q_pred[q]["mae_C"] for q in q_order]

ax2 = ax.twinx()
ax.bar(q_order, med_absF, color="steelblue", alpha=0.6, label="median |F| (L)")
ax2.plot(q_order, r_vals, "ro-", lw=1.5, label="Pearson r (R)")
ax2.plot(q_order, mae_vals, "gs-", lw=1.5, label="MAE degC (R)")
ax.set_xlabel("Training-support quartile", fontsize=10)
ax.set_ylabel("Median |F| (degC)", fontsize=10, color="steelblue")
ax2.set_ylabel("r  /  MAE (degC)", fontsize=10)
ax.set_title("Fingerprint magnitude and prediction\nby training-support quartile", fontsize=10)
lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper right")

ax = axes[1]
u_order = ["U1","U2","U3","U4"]
med_se   = [fp_df[fp_df["unc_Q"] == q]["F_se"].median() for q in u_order]
r_unc    = [unc_q_pred[q]["pearson_r"] for q in u_order]
mae_unc  = [unc_q_pred[q]["mae_C"] for q in u_order]

ax3 = ax.twinx()
ax.bar(u_order, med_se, color="darkorange", alpha=0.6, label="median SE (L)")
ax3.plot(u_order, r_unc, "ro-", lw=1.5, label="Pearson r (R)")
ax3.plot(u_order, mae_unc, "gs-", lw=1.5, label="MAE degC (R)")
ax.set_xlabel("Fingerprint uncertainty quartile (U1=most precise)", fontsize=10)
ax.set_ylabel("Median SE (degC)", fontsize=10, color="darkorange")
ax3.set_ylabel("r  /  MAE (degC)", fontsize=10)
ax.set_title("Fingerprint SE and prediction\nby uncertainty quartile", fontsize=10)
lines1, labels1 = ax.get_legend_handles_labels()
lines2, labels2 = ax3.get_legend_handles_labels()
ax.legend(lines1 + lines2, labels1 + labels2, fontsize=8, loc="upper left")

plt.tight_layout()
plt.savefig(OUT_DIR / "phase3a_support_vs_mag.png", dpi=150, bbox_inches="tight")
plt.close()
print("  Saved phase3a_support_vs_mag.png")


# ── Save ──────────────────────────────────────────────────────────────────────
results = {
    "training_support_quartiles": support_q_summary,
    "fingerprint_uncertainty_quartiles": unc_q_summary,
    "training_support_correlates": n_corr,
    "matched_by_F_band": matched_results,
    "monthly_calibration": monthly_df.to_dict(orient="records"),
}

with open(OUT_DIR / "phase3a_diagnostic.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nSaved phase3a_diagnostic.json")
print("Done.")
