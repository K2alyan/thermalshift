#!/usr/bin/env python3
"""
M3: 2024-Only Prospective Thermal Model
========================================
Builds and validates a thermal prediction model using ONLY 2024 training data.

Problem: phase3a_validation.py's incremental model (FA_coefficient=0.9566) was
fitted on the 2025 test set (phase3a_validation.py:354, sub4 = test_df[...]).
A truly prospective model requires the slope to be frozen from 2024 training jobs.

Analyses
--------
3.1  Per-job slope estimation from 2024 training telemetry (sample-based)
     For each qualifying training job j:
       delta_T_p95_ij = beta_j * FA_2024_i + noise_ij
     BETA_F_frozen = median(beta_j across training jobs)

3.2  Validate frozen BETA_F on 2025 test data
     Residuals: e_ij = delta_T_p95_ij - BETA_F_frozen * FA_2024_i
     Compare R2_frozen vs R2_refitted

3.3  Per-job slope stability: distribution of beta_j in training vs test
     Confirms the 2024 model generalizes to 2025

3.4  Residual table for 2025 test jobs (for M4 input)
     Saves artifacts/revision1/results/m3_test_residuals.parquet

Inputs
------
  phase3a_fingerprint_2024.parquet
  phase3a_test_set.parquet
  Training job telemetry (1000-job sample, same seed as M1.6 F^P)

Output
------
  artifacts/revision1/results/m3_thermal_model.json
  artifacts/revision1/results/m3_train_betas.parquet
  artifacts/revision1/results/m3_test_residuals.parquet
"""

import re, json, hashlib, subprocess, datetime, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats
from numpy.linalg import lstsq

REPO_ROOT  = Path(__file__).resolve().parents[3]
PHASE1_DIR = REPO_ROOT / "artifacts" / "phase1"
ANAL_DIR   = PHASE1_DIR / "analysis"
OUT_DIR    = REPO_ROOT / "artifacts" / "revision1" / "results"
FIG_DIR    = REPO_ROOT / "artifacts" / "revision1" / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIR   = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset")
TELE_DIR   = DATA_DIR / "job-telemetry"

TRAIN_SAMPLE_N  = 1000   # training jobs to sample (seed matches M1.6)
MIN_FP_PER_JOB  = 8      # min fp nodes with valid T_p95 per job for slope estimation

BETA_CACHE    = OUT_DIR / "m3_train_betas.parquet"
RESID_CACHE   = OUT_DIR / "m3_test_residuals.parquet"

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

print("=" * 65)
print("M3: 2024-Only Prospective Thermal Model")
print("=" * 65)
t0_global = time.time()

# ─────────────────────────────────────────────────────────────────────
# Load frozen inputs
# ─────────────────────────────────────────────────────────────────────
print("\n[0] Loading inputs ...")
fp_df   = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
test_df = pd.read_parquet(ANAL_DIR / "phase3a_test_set.parquet")

fp_hostname_set = set(fp_df.index)
F_dict = fp_df["FA_2024"].to_dict()

# Compute delta_T_p95 = T_p95 - job_mean(T_p95) in test set
test_df["job_mean_T"]  = test_df.groupby("job_idx")["T_p95"].transform("mean")
test_df["delta_T_p95"] = test_df["T_p95"] - test_df["job_mean_T"]

print(f"    fp nodes:  {len(fp_hostname_set)}")
print(f"    test obs:  {len(test_df):,}  across {test_df.job_idx.nunique()} jobs")

# ─────────────────────────────────────────────────────────────────────
# M3.1  Per-job slope from 2024 training telemetry
# ─────────────────────────────────────────────────────────────────────
print("\n[3.1] Estimating per-job slopes from 2024 training telemetry ...")

if BETA_CACHE.exists():
    print(f"    Loading cached training betas from {BETA_CACHE}")
    betas_df = pd.read_parquet(BETA_CACHE)
    n_qualifying = len(betas_df)
    print(f"    Loaded {n_qualifying} training job betas")
else:
    print(f"    Computing per-job betas from training telemetry ...")
    print(f"    (sample={TRAIN_SAMPLE_N} jobs, seed=42, same as M1.6)")

    # Get training job list (pre-2025)
    with open(PHASE1_DIR / "globus_batch.txt") as _bf:
        _blines = [l.strip() for l in _bf if l.strip()]
    _bpat = re.compile(r"(\d{4}-\d{2}-\d{2})/(\d{6})")
    train_job_list = []
    for _bl in _blines:
        _bm = _bpat.search(_bl)
        if _bm and _bm.group(1) < "2025":
            train_job_list.append({"date_dir": _bm.group(1), "job_idx": int(_bm.group(2))})
    train_job_df = pd.DataFrame(train_job_list).drop_duplicates("job_idx")

    if TRAIN_SAMPLE_N and len(train_job_df) > TRAIN_SAMPLE_N:
        train_job_df = train_job_df.sample(n=TRAIN_SAMPLE_N, random_state=42)
    print(f"    Training jobs to process: {len(train_job_df)}")

    beta_rows = []
    jobs_used = 0

    for ki, (_, tj) in enumerate(train_job_df.iterrows()):
        if ki % 50 == 0:
            print(f"    ... {ki}/{len(train_job_df)} (qualifying: {jobs_used})", end="\r")

        jid   = str(int(tj["job_idx"])).zfill(6)
        ddir  = tj["date_dir"]
        tpath = TELE_DIR / ddir / jid / f"{jid}-cleaned-temperature.parquet"

        if not tpath.exists():
            continue
        try:
            tmp = pd.read_parquet(tpath)
        except Exception:
            continue

        # Find GCD temperature columns for fp nodes
        node_gcd_map: dict[str, list] = {}
        for c in tmp.columns:
            if c.startswith("frontier") and "_gcd" in c and "ncount" not in c:
                node = c.split("_")[0]
                if node in fp_hostname_set:
                    node_gcd_map.setdefault(node, []).append(c)

        if len(node_gcd_map) < MIN_FP_PER_JOB:
            continue

        # Compute T_p95 per fp node per job
        nodes, t_p95s, fa_vals = [], [], []
        for node, gcols in node_gcd_map.items():
            t_ts  = np.nanmean(tmp[gcols].values.astype(float), axis=1)
            finite_t = t_ts[np.isfinite(t_ts)]
            if len(finite_t) < 5:
                continue
            t_p95 = float(np.percentile(finite_t, 95))
            fa    = F_dict.get(node)
            if fa is None:
                continue
            nodes.append(node)
            t_p95s.append(t_p95)
            fa_vals.append(fa)

        if len(nodes) < MIN_FP_PER_JOB:
            continue

        T_arr  = np.array(t_p95s)
        FA_arr = np.array(fa_vals)

        # Within-job deviation
        dT = T_arr - T_arr.mean()

        # Regress dT ~ beta * FA (no intercept — dT is already mean-centered)
        # Use scalar formula: beta = cov(FA, dT) / var(FA)
        fa_center = FA_arr - FA_arr.mean()
        denom = float(np.dot(fa_center, fa_center))
        if denom < 1e-12:
            continue
        beta_j = float(np.dot(fa_center, dT) / denom)

        # R2 for this job
        sst_j = float(np.dot(dT, dT))
        pred_j = beta_j * fa_center
        sse_j  = float(np.dot(dT - pred_j, dT - pred_j))
        r2_j   = 1.0 - sse_j / sst_j if sst_j > 1e-12 else float("nan")

        beta_rows.append({
            "job_idx":     int(tj["job_idx"]),
            "date_dir":    ddir,
            "n_fp_nodes":  len(nodes),
            "beta_F":      beta_j,
            "r2_job":      r2_j,
            "T_p95_mean":  float(T_arr.mean()),
            "T_p95_std":   float(T_arr.std()),
            "FA_std":      float(FA_arr.std()),
        })
        jobs_used += 1

    print(f"\n    Done: {jobs_used} qualifying training jobs")
    betas_df = pd.DataFrame(beta_rows)
    betas_df.to_parquet(BETA_CACHE, index=False)
    print(f"    Saved: {BETA_CACHE}")
    n_qualifying = len(betas_df)

print(f"\n    Training job slope summary (n={n_qualifying}):")
b = betas_df["beta_F"]
print(f"      min={b.min():.4f}  p5={b.quantile(0.05):.4f}  p25={b.quantile(0.25):.4f}")
print(f"      median={b.median():.4f}  mean={b.mean():.4f}")
print(f"      p75={b.quantile(0.75):.4f}  p95={b.quantile(0.95):.4f}  max={b.max():.4f}")
print(f"      std={b.std():.4f}")

BETA_F_FROZEN  = float(b.median())
BETA_F_MEAN    = float(b.mean())
BETA_F_REF     = 0.9566   # published value (fitted on 2025 test data — for comparison)
print(f"\n    BETA_F_frozen (2024 training median):  {BETA_F_FROZEN:.4f}")
print(f"    BETA_F_mean   (2024 training mean):    {BETA_F_MEAN:.4f}")
print(f"    BETA_F_ref    (phase3a test-data fit):  {BETA_F_REF}")
print(f"    Difference (frozen - ref):              {BETA_F_FROZEN - BETA_F_REF:.4f}")

m31 = {
    "n_qualifying_jobs": int(n_qualifying),
    "training_sample_size": TRAIN_SAMPLE_N,
    "min_fp_per_job": MIN_FP_PER_JOB,
    "beta_F_frozen": float(BETA_F_FROZEN),
    "beta_F_mean_training": float(BETA_F_MEAN),
    "beta_F_ref_test_fit": float(BETA_F_REF),
    "beta_F_diff_frozen_minus_ref": float(BETA_F_FROZEN - BETA_F_REF),
    "beta_training_stats": {
        "min":    float(b.min()),
        "p5":     float(b.quantile(0.05)),
        "p25":    float(b.quantile(0.25)),
        "median": float(b.median()),
        "mean":   float(b.mean()),
        "p75":    float(b.quantile(0.75)),
        "p95":    float(b.quantile(0.95)),
        "max":    float(b.max()),
        "std":    float(b.std()),
    },
}

# ─────────────────────────────────────────────────────────────────────
# M3.2  Validate frozen BETA_F on 2025 test data
# ─────────────────────────────────────────────────────────────────────
print("\n[3.2] Validating frozen BETA_F on 2025 test data ...")

# Predictions using frozen model: pred_ij = BETA_F_frozen * FA_2024_i
# Residuals: e_ij = delta_T_p95_ij - pred_ij
sub = test_df[["job_idx","node","F_2024","delta_T_p95"]].dropna().copy()
sub["pred_frozen"]  = BETA_F_FROZEN * sub["F_2024"]
sub["pred_ref"]     = BETA_F_REF    * sub["F_2024"]
sub["resid_frozen"] = sub["delta_T_p95"] - sub["pred_frozen"]
sub["resid_ref"]    = sub["delta_T_p95"] - sub["pred_ref"]

def r2_ss(y, yhat):
    sst = ((y - y.mean())**2).sum()
    sse = ((y - yhat)**2).sum()
    return float(1 - sse/sst)

y    = sub["delta_T_p95"].values
yfz  = sub["pred_frozen"].values
yfr  = sub["pred_ref"].values

r2_frozen = r2_ss(y, yfz)
r2_ref    = r2_ss(y, yfr)
mae_frozen = float(np.abs(sub["resid_frozen"]).mean())
mae_ref    = float(np.abs(sub["resid_ref"]).mean())
rmse_frozen = float(np.sqrt((sub["resid_frozen"]**2).mean()))
rmse_ref    = float(np.sqrt((sub["resid_ref"]**2).mean()))

# Refitted slope on 2025 test data (in-sample — for comparison only)
fa_c = sub["F_2024"].values - sub["F_2024"].values.mean()
dt_c = y - y.mean()
beta_test = float(np.dot(fa_c, dt_c) / np.dot(fa_c, fa_c))
y_test_fit = beta_test * fa_c + y.mean()
r2_test_fit = r2_ss(y, y_test_fit)

print(f"    n_obs = {len(sub):,}")
print(f"    Frozen BETA_F = {BETA_F_FROZEN:.4f}")
print(f"    Ref   BETA_F  = {BETA_F_REF}")
print(f"    Test-fit beta = {beta_test:.4f}  (IN-SAMPLE on 2025 — reference only)")
print(f"\n    R2_frozen  (2024-trained beta): {r2_frozen:.4f}")
print(f"    R2_ref     (test-data  beta):   {r2_ref:.4f}")
print(f"    R2_in-sample (refitted to 2025): {r2_test_fit:.4f}")
print(f"\n    MAE_frozen:   {mae_frozen:.4f}")
print(f"    MAE_ref:      {mae_ref:.4f}")
print(f"    RMSE_frozen:  {rmse_frozen:.4f}")
print(f"    RMSE_ref:     {rmse_ref:.4f}")

m32 = {
    "n_obs": int(len(sub)),
    "beta_F_frozen": float(BETA_F_FROZEN),
    "beta_F_ref_test": float(BETA_F_REF),
    "beta_F_in_sample_2025": float(beta_test),
    "frozen_model": {
        "r2":   r2_frozen,
        "mae":  mae_frozen,
        "rmse": rmse_frozen,
    },
    "ref_model": {
        "r2":   r2_ref,
        "mae":  mae_ref,
        "rmse": rmse_ref,
    },
    "in_sample_2025": {
        "r2":   r2_test_fit,
        "note": "refitted to 2025 test data — NOT a valid prospective model",
    },
}

# ─────────────────────────────────────────────────────────────────────
# M3.3  Per-job slope stability: training vs test
# ─────────────────────────────────────────────────────────────────────
print("\n[3.3] Per-job slope stability: test data vs training distribution ...")

# Compute per-job beta in 2025 test data
test_job_betas = []
for jid, grp in sub.groupby("job_idx"):
    if len(grp) < 4:
        continue
    fa   = grp["F_2024"].values
    dt   = grp["delta_T_p95"].values
    fa_c2 = fa - fa.mean()
    denom2 = float(np.dot(fa_c2, fa_c2))
    if denom2 < 1e-12:
        continue
    bj = float(np.dot(fa_c2, dt) / denom2)
    test_job_betas.append({"job_idx": jid, "beta_F": bj, "n_nodes": len(grp)})

test_betas_df = pd.DataFrame(test_job_betas)
b_test = test_betas_df["beta_F"]
print(f"    2025 test job betas (n={len(b_test)}):")
print(f"      median={b_test.median():.4f}  mean={b_test.mean():.4f}  std={b_test.std():.4f}")
print(f"      p5={b_test.quantile(0.05):.4f}  p95={b_test.quantile(0.95):.4f}")

print(f"\n    2024 training betas (n={len(betas_df)}):")
print(f"      median={b.median():.4f}  mean={b.mean():.4f}  std={b.std():.4f}")

# Kolmogorov-Smirnov test: are training and test slope distributions similar?
ks_stat, ks_p = stats.ks_2samp(b.values, b_test.values)
print(f"\n    KS test (train vs test beta distribution): stat={ks_stat:.4f}, p={ks_p:.4f}")

m33 = {
    "training_betas": {
        "n": int(len(betas_df)),
        "median": float(b.median()),
        "mean": float(b.mean()),
        "std": float(b.std()),
        "p5": float(b.quantile(0.05)),
        "p95": float(b.quantile(0.95)),
    },
    "test_betas": {
        "n": int(len(b_test)),
        "median": float(b_test.median()),
        "mean": float(b_test.mean()),
        "std": float(b_test.std()),
        "p5": float(b_test.quantile(0.05)),
        "p95": float(b_test.quantile(0.95)),
    },
    "ks_test_stat": float(ks_stat),
    "ks_test_p": float(ks_p),
    "interpretation": (
        "Low KS p -> training and test beta distributions are significantly different. "
        "High KS p -> distributions are compatible (frozen model generalizes well)."
    ),
}

# ─────────────────────────────────────────────────────────────────────
# M3.4  Residual table for 2025 test jobs
# ─────────────────────────────────────────────────────────────────────
print("\n[3.4] Building test residual table ...")
resid_df = sub[["job_idx","node","F_2024","delta_T_p95","pred_frozen","resid_frozen"]].copy()
resid_df.rename(columns={
    "F_2024":       "FA_2024",
    "pred_frozen":  "pred_frozen_model",
    "resid_frozen": "resid_frozen_model",
}, inplace=True)
resid_df["beta_F_frozen"] = BETA_F_FROZEN
resid_df.to_parquet(RESID_CACHE, index=False)
print(f"    Saved: {RESID_CACHE}  ({len(resid_df):,} rows)")

m34 = {
    "output_file": str(RESID_CACHE),
    "n_rows": int(len(resid_df)),
    "columns": list(resid_df.columns),
    "beta_F_frozen_used": float(BETA_F_FROZEN),
    "note": (
        "resid_frozen_model = delta_T_p95 - BETA_F_frozen * FA_2024. "
        "This is the unexplained thermal deviation after removing the fingerprint "
        "signal with the prospectively frozen slope. "
        "Input for M4 capacity-unlock analysis."
    ),
}

# ─────────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────────
print("\n[F] Generating figures ...")

fig, axes = plt.subplots(1, 3, figsize=(14, 4))

# Fig 1: Distribution of per-job betas (training vs test)
ax = axes[0]
ax.hist(b.clip(-1, 3), bins=50, alpha=0.6, color="#3a7eca",
        density=True, label=f"Train (n={len(b)}, med={b.median():.3f})")
ax.hist(b_test.clip(-1, 3), bins=50, alpha=0.6, color="#e05c1a",
        density=True, label=f"Test  (n={len(b_test)}, med={b_test.median():.3f})")
ax.axvline(BETA_F_FROZEN, color="blue", lw=2, ls="--",
           label=f"BETA_F_frozen={BETA_F_FROZEN:.3f}")
ax.axvline(BETA_F_REF, color="red", lw=2, ls=":",
           label=f"BETA_F_ref={BETA_F_REF}")
ax.set_xlabel("Per-job slope beta_F")
ax.set_ylabel("Density")
ax.set_title("M3.1/3.3: Per-job slope distribution")
ax.legend(fontsize=7)

# Fig 2: Frozen model predictions vs actual (node-job level)
ax = axes[1]
idx_s = np.random.default_rng(0).choice(len(sub), size=min(5000, len(sub)), replace=False)
ax.scatter(sub["pred_frozen"].iloc[idx_s], sub["delta_T_p95"].iloc[idx_s],
           alpha=0.15, s=4, color="#3a7eca")
lim_min = min(sub["pred_frozen"].quantile(0.01), sub["delta_T_p95"].quantile(0.01))
lim_max = max(sub["pred_frozen"].quantile(0.99), sub["delta_T_p95"].quantile(0.99))
ax.plot([lim_min, lim_max], [lim_min, lim_max], "k--", lw=1)
ax.set_xlabel(f"Frozen model prediction (BETA_F={BETA_F_FROZEN:.3f} * FA)")
ax.set_ylabel("Actual delta_T_p95 (2025 test)")
ax.set_title(f"M3.2: Frozen model vs actual\nR2={r2_frozen:.4f}  MAE={mae_frozen:.3f}")

# Fig 3: Residual distribution
ax = axes[2]
ax.hist(sub["resid_frozen"].clip(-5, 5), bins=60, color="#3a7eca",
        edgecolor="none", alpha=0.85)
ax.axvline(0, color="red", lw=1, ls="--")
ax.set_xlabel("Frozen-model residual (delta_T - pred)")
ax.set_ylabel("Node-job obs")
ax.set_title(f"M3.4: Residuals (frozen model)\n"
             f"mean={sub['resid_frozen'].mean():.3f}  std={sub['resid_frozen'].std():.3f}")

plt.suptitle("M3: 2024-Only Prospective Thermal Model")
plt.tight_layout()
plt.savefig(FIG_DIR / "fig_m3_thermal_model.png", dpi=150)
plt.close()
print("    Saved fig_m3_thermal_model.png")

# ─────────────────────────────────────────────────────────────────────
# Assemble JSON
# ─────────────────────────────────────────────────────────────────────
result = {
    "script":    "r1_m3_thermal_model.py",
    "git_sha":   git_sha(),
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "input_files": {
        "phase3a_fingerprint_2024.parquet": file_sha256(ANAL_DIR / "phase3a_fingerprint_2024.parquet"),
        "phase3a_test_set.parquet":         file_sha256(ANAL_DIR / "phase3a_test_set.parquet"),
    },
    "methodology_note": (
        "BETA_F_frozen is the median per-job slope from 2024 training telemetry. "
        "Per-job slope = cov(FA_2024, delta_T_p95) / var(FA_2024) within each training job. "
        "The published ref value (0.9566) was fitted on 2025 test data (phase3a_validation.py "
        "line 354) and is NOT a frozen prospective parameter. "
        "M3 provides the prospectively frozen slope and validates it on 2025."
    ),

    "m3_1_training_slopes": m31,
    "m3_2_frozen_validation": m32,
    "m3_3_slope_stability": m33,
    "m3_4_residual_table": m34,

    "elapsed_seconds": round(time.time() - t0_global, 1),
}

out_path = OUT_DIR / "m3_thermal_model.json"
with open(out_path, "w") as f:
    json.dump(result, f, indent=2)

print(f"\nSaved: {out_path}")
print(f"Total elapsed: {time.time()-t0_global:.1f}s")
