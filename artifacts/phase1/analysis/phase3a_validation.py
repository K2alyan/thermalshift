"""
Phase 3A: Prospective node-level validation.

Freeze GPU thermal fingerprints from pre-2025 longitudinal production jobs,
then test whether those fingerprints predict relative GPU temperature in
held-out 2025 jobs — no recalibration.

Outputs:
  phase3a_fingerprint_2024.parquet  — F^A_2024 per node with obs counts
  phase3a_test_set.parquet          — per node-job T statistics from 2025 holdout
  phase3a_results.json              — all metrics
  phase3a_node_level.png            — F^A_2024 vs Y_i^2025 scatter
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

# ── Load cohort metadata ───────────────────────────────────────────────────────
print("Loading cohort metadata...")
cohort_manifest = pd.read_csv(COHORT_DIR / "cohort_manifest.csv")
cohort_nodes    = set(cohort_manifest["hostname"])
cohort_jobs     = pd.read_csv(COHORT_DIR / "cohort_job_list.csv")
longitudinal    = cohort_jobs[cohort_jobs["selection_role"] == "longitudinal_cohort"].copy()

train_jobs = longitudinal[longitudinal["date_dir"] < "2025"].copy()
test_jobs  = longitudinal[longitudinal["date_dir"] >= "2025"].copy()

print(f"  Longitudinal jobs total: {len(longitudinal)}")
print(f"  Pre-2025 (train):        {len(train_jobs)}")
print(f"  2025+    (test):         {len(test_jobs)}")


# ── helpers ───────────────────────────────────────────────────────────────────

def load_temp(job_idx, date_dir):
    job_str = str(job_idx).zfill(6)
    return pq.read_table(
        DATA_DIR / date_dir / job_str / f"{job_str}-cleaned-temperature.parquet"
    ).to_pandas()

def load_power(job_idx, date_dir):
    job_str = str(job_idx).zfill(6)
    return pq.read_table(
        DATA_DIR / date_dir / job_str / f"{job_str}-cleaned-power.parquet"
    ).to_pandas()

def _gcd_idx(col):
    try:
        return int(col.split("_gcd")[1])
    except Exception:
        return -1

def gcd_cols_for(temp_df, nodes_subset=None, gcd_parity=None):
    cols = [c for c in temp_df.columns if c.startswith("frontier") and "_gcd" in c]
    if nodes_subset is not None:
        cols = [c for c in cols if c.split("_")[0] in nodes_subset]
    if gcd_parity == "even":
        cols = [c for c in cols if _gcd_idx(c) % 2 == 0]
    elif gcd_parity == "odd":
        cols = [c for c in cols if _gcd_idx(c) % 2 == 1]
    return cols

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


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1: Freeze F^A_2024 from pre-2025 longitudinal jobs only
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 1: Freezing F^A_2024 (pre-2025 longitudinal jobs) ===")

FA_acc  = {}  # node -> list of within-job residuals
FC_acc  = {}
FE_acc  = {}  # even GCDs (sensor bias test)
FO_acc  = {}  # odd GCDs

n_train = len(train_jobs)
for i, (_, row) in enumerate(train_jobs.iterrows()):
    if i % 500 == 0:
        print(f"  Fingerprint pass: {i}/{n_train}", flush=True)
    try:
        temp = load_temp(row["job_idx"], row["date_dir"])
    except Exception:
        continue

    # F^A — all GCDs, all cohort nodes
    cols = gcd_cols_for(temp, cohort_nodes)
    if not cols:
        continue
    nm = node_map_from(cols)
    means = node_scalar_mean(temp, nm)
    if len(means) < 2:
        continue

    jm = np.mean(list(means.values()))
    for node, val in means.items():
        FA_acc.setdefault(node, []).append(val - jm)

    # F^C — timestamp-level median subtraction
    node_ts = {n: temp[c].mean(axis=1) for n, c in nm.items()}
    nts = pd.DataFrame(node_ts)
    med = nts.median(axis=1)
    fc_vals = nts.subtract(med, axis=0).mean(axis=0)
    for node, val in fc_vals.items():
        FC_acc.setdefault(node, []).append(float(val))

    # Even GCDs (sensor bias)
    ecols = gcd_cols_for(temp, cohort_nodes, gcd_parity="even")
    if ecols:
        enm = node_map_from(ecols)
        em = node_scalar_mean(temp, enm)
        if len(em) >= 2:
            emj = np.mean(list(em.values()))
            for node, val in em.items():
                FE_acc.setdefault(node, []).append(val - emj)

    # Odd GCDs (sensor bias)
    ocols = gcd_cols_for(temp, cohort_nodes, gcd_parity="odd")
    if ocols:
        onm = node_map_from(ocols)
        om = node_scalar_mean(temp, onm)
        if len(om) >= 2:
            omj = np.mean(list(om.values()))
            for node, val in om.items():
                FO_acc.setdefault(node, []).append(val - omj)

FA_2024   = pd.Series({n: np.mean(v) for n, v in FA_acc.items()},  name="FA_2024")
FC_2024   = pd.Series({n: np.mean(v) for n, v in FC_acc.items()},  name="FC_2024")
FA_even_s = pd.Series({n: np.mean(v) for n, v in FE_acc.items()},  name="FA_even")
FA_odd_s  = pd.Series({n: np.mean(v) for n, v in FO_acc.items()},  name="FA_odd")
n_train_s = pd.Series({n: len(v)     for n, v in FA_acc.items()},  name="n_jobs_train")

fp_2024 = pd.DataFrame({
    "FA_2024": FA_2024, "FC_2024": FC_2024,
    "FA_even": FA_even_s, "FA_odd": FA_odd_s,
    "n_jobs_train": n_train_s,
})
fp_2024.index.name = "node"
fp_2024.to_parquet(OUT_DIR / "phase3a_fingerprint_2024.parquet")
print(f"  Saved phase3a_fingerprint_2024.parquet")

node_fp = FA_2024.dropna().to_dict()
fc_map  = FC_2024.dropna().to_dict()
print(f"  F^A_2024: {FA_2024.notna().sum()} nodes, "
      f"range [{FA_2024.min():.2f}, {FA_2024.max():.2f}]degC")
print(f"  Median train jobs/node: {n_train_s.median():.0f}")


# ─────────────────────────────────────────────────────────────────────────────
# STEPS 2-3: Build 2025 held-out test set + cohort-size check
# ─────────────────────────────────────────────────────────────────────────────

print(f"\n=== Steps 2-3: Building 2025 held-out test set ({len(test_jobs)} candidate jobs) ===")
print(f"  Frozen fingerprint nodes available: {len(node_fp)}")

records = []
n_ok, n_fail = 0, 0
n_test = len(test_jobs)

for i, (_, row) in enumerate(test_jobs.iterrows()):
    if i % 100 == 0:
        print(f"  Test pass: {i}/{n_test} (records so far: {len(records):,})", flush=True)
    try:
        temp = load_temp(row["job_idx"], row["date_dir"])
    except Exception:
        n_fail += 1
        continue

    cols = gcd_cols_for(temp, set(node_fp.keys()))
    if not cols:
        n_fail += 1
        continue
    nm = node_map_from(cols)
    if len(nm) < 3:
        continue

    # Load power (optional — not always present)
    pwr = None
    try:
        pwr = load_power(row["job_idx"], row["date_dir"])
    except Exception:
        pass

    for node, ncols in nm.items():
        ts_vals = temp[ncols].values.astype(float)  # (n_time, n_gcds)

        # mean_g per timestamp: p95 over time is T_p95
        mean_g = np.nanmean(ts_vals, axis=1)
        valid_mean = mean_g[np.isfinite(mean_g)]
        if len(valid_mean) < 5:
            continue

        T_p95    = float(np.percentile(valid_mean, 95))
        T_mean_v = float(np.mean(valid_mean))
        T_max_v  = float(np.max(valid_mean))

        # max_g per timestamp: hot-die p95
        max_g = np.nanmax(ts_vals, axis=1)
        valid_max = max_g[np.isfinite(max_g)]
        T_hot_p95 = float(np.percentile(valid_max, 95)) if len(valid_max) >= 5 else np.nan

        # Node power
        P_mean_v = np.nan
        if pwr is not None:
            pc = [c for c in pwr.columns if c == f"{node}_node"]
            if pc:
                pvals = pwr[pc[0]].values.astype(float)
                pvals = pvals[np.isfinite(pvals)]
                if len(pvals):
                    P_mean_v = float(pvals.mean())

        records.append({
            "job_idx":       int(row["job_idx"]),
            "date_dir":      row["date_dir"],
            "node":          node,
            "F_2024":        node_fp[node],
            "T_p95":         T_p95,
            "T_hot_die_p95": T_hot_p95,
            "T_mean":        T_mean_v,
            "T_max":         T_max_v,
            "P_mean":        P_mean_v,
        })
    n_ok += 1

print(f"\n  Jobs processed: {n_ok}, failed/skipped: {n_fail}")
print(f"  Total node-job records: {len(records):,}")

test_df = pd.DataFrame(records)
test_df.to_parquet(OUT_DIR / "phase3a_test_set.parquet")
print(f"  Saved phase3a_test_set.parquet")

# Within-job demeaning
for col in ["T_p95", "T_hot_die_p95", "T_mean", "T_max", "P_mean"]:
    test_df[f"delta_{col}"] = (
        test_df[col] - test_df.groupby("job_idx")[col].transform("mean")
    )

test_df["FC_2024"]     = test_df["node"].map(fc_map)
test_df["n_jobs_train"] = test_df["node"].map(n_train_s.to_dict())

# Cohort-size diagnostic (Step 2)
print(f"\n=== Cohort-size check ===")
print(f"  2025 qualifying jobs:                {test_df['job_idx'].nunique()}")
print(f"  Unique fingerprinted nodes in test:  {test_df['node'].nunique()}")
print(f"  Node-job observations:               {len(test_df):,}")
print(f"  Median obs/node:                     {test_df.groupby('node').size().median():.0f} jobs")
print(f"  Median cohort nodes/job:             {test_df.groupby('job_idx').size().median():.0f}")
frac_nodes = test_df["node"].nunique() / len(cohort_nodes) * 100
print(f"  Fraction of cohort nodes represented: {frac_nodes:.1f}%")


# ─────────────────────────────────────────────────────────────────────────────
# Analysis helpers
# ─────────────────────────────────────────────────────────────────────────────

def compute_metrics(fp, dt, label=""):
    valid = np.isfinite(fp) & np.isfinite(dt)
    fp, dt = fp[valid], dt[valid]
    if len(fp) < 10:
        return {"label": label, "n_obs": int(len(fp)), "note": "too few obs"}
    r,  _ = stats.pearsonr(fp, dt)
    sr, _ = stats.spearmanr(fp, dt)
    mae   = float(np.mean(np.abs(fp - dt)))
    rmse  = float(np.sqrt(np.mean((fp - dt)**2)))
    sa    = float(np.mean(np.sign(fp) == np.sign(dt)))
    sl, ic, _, _, _ = stats.linregress(fp, dt)
    ss_tot = float(np.sum((dt - dt.mean())**2))
    ss_res = float(np.sum((dt - (ic + sl * fp))**2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else np.nan
    return {
        "label": label, "n_obs": int(len(fp)),
        "pearson_r":   round(float(r),  4),
        "spearman_r":  round(float(sr), 4),
        "mae_C":       round(mae,  4),
        "rmse_C":      round(rmse, 4),
        "sign_agreement": round(sa, 4),
        "calib_slope":    round(float(sl), 4),
        "calib_intercept": round(float(ic), 4),
        "r2":          round(float(r2), 4),
    }


def boot_r_twoway(jobs, nodes, fp, dt, n_boot=1000, seed=42):
    """
    Two-way clustered bootstrap CI for Pearson r.
    Resamples jobs with replacement; within each resampled job, resamples
    node observations with replacement.
    """
    rng = np.random.default_rng(seed)
    uj = np.unique(jobs)
    boot = []
    for _ in range(n_boot):
        sj = rng.choice(uj, size=len(uj), replace=True)
        bF, bdT = [], []
        for j in sj:
            mask = jobs == j
            jF, jdT = fp[mask], dt[mask]
            if len(jF) == 0:
                continue
            idx = rng.integers(0, len(jF), len(jF))
            bF.append(jF[idx])
            bdT.append(jdT[idx])
        if not bF:
            continue
        bF  = np.concatenate(bF)
        bdT = np.concatenate(bdT)
        if np.ptp(bF) > 0 and np.ptp(bdT) > 0 and len(bF) > 2:
            boot.append(stats.pearsonr(bF, bdT)[0])
    boot = np.array(boot)
    boot = boot[np.isfinite(boot)]
    if len(boot) < 10:
        return np.nan, np.nan
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def ols_fit(X_list, y):
    """OLS; returns (beta, MAE, RMSE, R²)."""
    X = np.column_stack([np.ones(len(y))] + X_list)
    beta, _, _, _ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    mae  = float(np.mean(np.abs(y - pred)))
    rmse = float(np.sqrt(np.mean((y - pred)**2)))
    ss_tot = float(np.sum((y - y.mean())**2))
    r2 = 1 - float(np.sum((y - pred)**2)) / ss_tot if ss_tot > 0 else np.nan
    return beta, mae, rmse, float(r2)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4: Direct prospective test — F^A_2024 -> delta_T_p95
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 4: Direct prospective test — F^A_2024 -> delta_T_p95 ===")

sub4 = test_df[["job_idx", "node", "F_2024", "delta_T_p95"]].dropna()
F4   = sub4["F_2024"].values
dT4  = sub4["delta_T_p95"].values

m4 = compute_metrics(F4, dT4, "FA2024_vs_dTp95")
print(f"  Pearson r        = {m4['pearson_r']:.4f}")
print(f"  Spearman r       = {m4['spearman_r']:.4f}")
print(f"  MAE              = {m4['mae_C']:.3f} degC")
print(f"  RMSE             = {m4['rmse_C']:.3f} degC")
print(f"  Sign agreement   = {m4['sign_agreement']:.4f}")
print(f"  Calib slope      = {m4['calib_slope']:.4f}  (ideal: 1.0)")
print(f"  R2               = {m4['r2']:.4f}")
print(f"  n                = {m4['n_obs']:,}")

print("  Two-way clustered CI (n=1000 bootstrap)...", flush=True)
r_lo, r_hi = boot_r_twoway(
    sub4["job_idx"].values, sub4["node"].values, F4, dT4
)
m4["pearson_r_ci_twoway"] = [round(r_lo, 4) if np.isfinite(r_lo) else None,
                              round(r_hi, 4) if np.isfinite(r_hi) else None]
print(f"  Pearson r = {m4['pearson_r']:.4f} [{r_lo:.4f}, {r_hi:.4f}] (two-way clustered 95% CI)")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 5: Node-level companion — Y_i = median_j(delta_T_p95_ij)
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 5: Node-level companion ===")

node_summ = (
    test_df.groupby("node")
    .agg(
        Y_p95  = ("delta_T_p95",          "median"),
        Y_hot  = ("delta_T_hot_die_p95",  "median"),
        Y_mean = ("delta_T_mean",          "median"),
        F_2024 = ("F_2024",                "first"),
        n_jobs = ("job_idx",               "nunique"),
    )
    .reset_index()
    .query("n_jobs >= 3")
    .dropna(subset=["F_2024", "Y_p95"])
)

m5 = compute_metrics(
    node_summ["F_2024"].values, node_summ["Y_p95"].values, "node_level"
)
print(f"  Nodes with >=3 test jobs: {len(node_summ)}")
print(f"  Pearson r      = {m5['pearson_r']:.4f}")
print(f"  Spearman r     = {m5['spearman_r']:.4f}")
print(f"  MAE            = {m5['mae_C']:.3f} degC")
print(f"  Calib slope    = {m5['calib_slope']:.4f}  (ideal: 1.0)")
print(f"  R2             = {m5['r2']:.4f}")

# Node-level scatter plot
fig, ax = plt.subplots(figsize=(7, 6))
sc = ax.scatter(
    node_summ["F_2024"], node_summ["Y_p95"],
    c=node_summ["n_jobs"], cmap="viridis",
    alpha=0.65, s=30, edgecolors="none"
)
plt.colorbar(sc, ax=ax, label="n test jobs per node")
xl = np.linspace(node_summ["F_2024"].min(), node_summ["F_2024"].max(), 100)
ax.plot(xl, m5["calib_intercept"] + m5["calib_slope"] * xl,
        "r-", lw=1.5,
        label=f"slope={m5['calib_slope']:.2f}, r={m5['pearson_r']:.3f}")
ax.axhline(0, color="k", lw=0.5, ls="--", alpha=0.5)
ax.axvline(0, color="k", lw=0.5, ls="--", alpha=0.5)
ax.set_xlabel("F_A_2024 (frozen pre-2025 fingerprint, degC)", fontsize=11)
ax.set_ylabel("Y_i_2025 = median_j(delta_T_p95_ij) (degC)", fontsize=11)
ax.set_title(
    f"Node-level prospective validation\n"
    f"n={len(node_summ)} nodes, Pearson r={m5['pearson_r']:.3f}, "
    f"Spearman r={m5['spearman_r']:.3f}",
    fontsize=10
)
ax.legend(fontsize=9)
plt.tight_layout()
plt.savefig(OUT_DIR / "phase3a_node_level.png", dpi=150, bbox_inches="tight")
plt.close()
print("  Saved phase3a_node_level.png")


# ─────────────────────────────────────────────────────────────────────────────
# STEP 6: Incremental model M0 vs M1
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 6: Incremental model M0 vs M1 ===")

sub6 = test_df[["F_2024", "delta_T_p95", "delta_P_mean"]].dropna()
dT6 = sub6["delta_T_p95"].values
F6  = sub6["F_2024"].values
dP6 = sub6["delta_P_mean"].values

_, mae0, rmse0, r2_0 = ols_fit([dP6], dT6)
beta1, mae1, rmse1, r2_1 = ols_fit([dP6, F6], dT6)

print(f"  M0 (dT ~ dP):      MAE={mae0:.4f} degC, RMSE={rmse0:.4f} degC, R2={r2_0:.4f}")
print(f"  M1 (dT ~ dP + F):  MAE={mae1:.4f} degC, RMSE={rmse1:.4f} degC, R2={r2_1:.4f}")
print(f"  Improvement:       dMAE={mae0-mae1:.4f}, dRMSE={rmse0-rmse1:.4f}, dR2={r2_1-r2_0:.4f}")
print(f"  F^A coefficient in M1: {beta1[2]:.4f}  (ideal: 1.0)")
print(f"  (n={len(dT6):,} obs with both power and T data)")

m6 = {
    "n_obs": int(len(dT6)),
    "M0": {"mae_C": round(mae0,4), "rmse_C": round(rmse0,4), "r2": round(r2_0,4)},
    "M1": {"mae_C": round(mae1,4), "rmse_C": round(rmse1,4), "r2": round(r2_1,4),
           "FA_coefficient": round(float(beta1[2]), 4)},
    "delta_MAE_C":  round(mae0 - mae1, 4),
    "delta_RMSE_C": round(rmse0 - rmse1, 4),
    "delta_R2":     round(r2_1 - r2_0, 4),
}


# ─────────────────────────────────────────────────────────────────────────────
# STEP 7: Robustness checks
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 7: Robustness checks ===")
robustness = {}

# 7a. F^C variant
sub_fc = test_df[["FC_2024", "delta_T_p95"]].dropna()
m_fc = compute_metrics(sub_fc["FC_2024"].values, sub_fc["delta_T_p95"].values, "FC_2024")
print(f"  F^C variant:     r={m_fc['pearson_r']:.4f}, MAE={m_fc['mae_C']:.3f}, n={m_fc['n_obs']:,}")
robustness["FC_2024"] = m_fc

# 7b. High vs low power jobs (median split on per-job mean power)
pj_mean = test_df.groupby("job_idx")["P_mean"].transform("mean")
p_med = pj_mean.quantile(0.5)
for label, mask in [("high_power", pj_mean >= p_med), ("low_power", pj_mean < p_med)]:
    sub = test_df[mask][["F_2024", "delta_T_p95"]].dropna()
    m = compute_metrics(sub["F_2024"].values, sub["delta_T_p95"].values, label)
    print(f"  {label}:   r={m['pearson_r']:.4f}, n={m['n_obs']:,}")
    robustness[label] = m

# 7c. Fingerprint confidence quartiles (by number of training jobs per node)
try:
    quartile_labels = pd.qcut(
        test_df["n_jobs_train"].dropna(), 4,
        labels=["Q1","Q2","Q3","Q4"], duplicates="drop"
    )
    test_df.loc[quartile_labels.index, "fp_quartile"] = quartile_labels.values
    for q in ["Q1","Q2","Q3","Q4"]:
        sub = test_df[test_df["fp_quartile"] == q][["F_2024","delta_T_p95"]].dropna()
        m = compute_metrics(sub["F_2024"].values, sub["delta_T_p95"].values, f"confidence_{q}")
        n_med = test_df[test_df["fp_quartile"] == q]["n_jobs_train"].median()
        print(f"  Confidence {q} (med train_jobs={n_med:.0f}): r={m['pearson_r']:.4f}, n={m['n_obs']:,}")
        robustness[f"confidence_{q}"] = m
except Exception as e:
    print(f"  Confidence quartile check failed: {e}")

# 7d. T_hot_die_p95 (secondary metric: hot-die p95)
sub_hot = test_df[["F_2024", "delta_T_hot_die_p95"]].dropna()
m_hot = compute_metrics(sub_hot["F_2024"].values, sub_hot["delta_T_hot_die_p95"].values, "T_hot_die_p95")
print(f"  T_hot_die_p95:   r={m_hot['pearson_r']:.4f}, MAE={m_hot['mae_C']:.3f}, n={m_hot['n_obs']:,}")
robustness["T_hot_die_p95"] = m_hot

# 7e. T_mean
sub_mean = test_df[["F_2024", "delta_T_mean"]].dropna()
m_mean = compute_metrics(sub_mean["F_2024"].values, sub_mean["delta_T_mean"].values, "T_mean")
print(f"  T_mean:          r={m_mean['pearson_r']:.4f}, MAE={m_mean['mae_C']:.3f}, n={m_mean['n_obs']:,}")
robustness["T_mean"] = m_mean

# 7f. T_max
sub_max = test_df[["F_2024", "delta_T_max"]].dropna()
m_max = compute_metrics(sub_max["F_2024"].values, sub_max["delta_T_max"].values, "T_max")
print(f"  T_max:           r={m_max['pearson_r']:.4f}, MAE={m_max['mae_C']:.3f}, n={m_max['n_obs']:,}")
robustness["T_max"] = m_max


# ─────────────────────────────────────────────────────────────────────────────
# STEP 8: Sensor bias test — even vs odd GCDs
# ─────────────────────────────────────────────────────────────────────────────

print("\n=== Step 8: Sensor bias test (even vs odd GCDs) ===")

common = FA_even_s.index.intersection(FA_odd_s.index)
eo = pd.DataFrame({
    "FA_even": FA_even_s[common],
    "FA_odd":  FA_odd_s[common],
}).dropna()

if len(eo) >= 10:
    r_eo,  _ = stats.pearsonr(eo["FA_even"], eo["FA_odd"])
    sr_eo, _ = stats.spearmanr(eo["FA_even"], eo["FA_odd"])
    mae_eo   = float(np.mean(np.abs(eo["FA_even"] - eo["FA_odd"])))
    print(f"  Nodes with both even/odd fingerprints: {len(eo)}")
    print(f"  r(F^even, F^odd) = {r_eo:.4f}  (Spearman = {sr_eo:.4f}, MAE = {mae_eo:.3f} degC)")
    print(f"  High r argues against result being driven by a single temperature channel")
    sensor_bias = {
        "n_nodes": int(len(eo)),
        "pearson_r": round(float(r_eo), 4),
        "spearman_r": round(float(sr_eo), 4),
        "mae_C": round(mae_eo, 4),
    }
else:
    print(f"  Insufficient data for sensor bias test (n={len(eo)})")
    sensor_bias = {"n_nodes": int(len(eo)), "note": "insufficient data"}


# ─────────────────────────────────────────────────────────────────────────────
# Save results
# ─────────────────────────────────────────────────────────────────────────────

results = {
    "fingerprint_freeze": {
        "n_train_jobs": int(len(train_jobs)),
        "n_test_jobs":  int(test_df["job_idx"].nunique()),
        "n_fp_nodes":   int(FA_2024.notna().sum()),
        "n_test_nodes": int(test_df["node"].nunique()),
        "n_node_job_obs": int(len(test_df)),
        "fp_range_C": [round(float(FA_2024.min()), 3), round(float(FA_2024.max()), 3)],
        "fp_median_train_jobs_per_node": float(n_train_s.median()),
        "median_obs_per_node_test": float(test_df.groupby("node").size().median()),
        "median_nodes_per_job_test": float(test_df.groupby("job_idx").size().median()),
    },
    "direct_prospective_test": m4,
    "node_level_companion": m5,
    "incremental_model": m6,
    "robustness": robustness,
    "sensor_bias_test": sensor_bias,
}

with open(OUT_DIR / "phase3a_results.json", "w") as f:
    json.dump(results, f, indent=2)

print("\nSaved phase3a_results.json")
print("Done.")
