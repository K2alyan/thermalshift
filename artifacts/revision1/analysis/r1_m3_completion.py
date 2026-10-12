#!/usr/bin/env python3
"""
M3 Completion Analysis (Gate D)
================================
D.1+D.2: 2024 T_p95 thresholds from training telemetry (p90/p95/p99)
D.3+D.4: Identity replay B/S -- model-identity vs observed
D.5:     Residual bin sensitivity K=1,3,5,10 + parametric heteroscedastic
D.6:     Non-monotonicity of B/S crossing curves
D.7:     Conservative first-violation crossing brackets
D.8:     Scenario 27 extension to lambda=2.0

Output:
  artifacts/revision1/results/m3_completion.json
"""

import json, hashlib, subprocess, datetime, time, re
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict
from scipy import stats as scipy_stats

REPO_ROOT  = Path(__file__).resolve().parents[3]
PHASE1_DIR = REPO_ROOT / "artifacts" / "phase1"
ANAL_DIR   = PHASE1_DIR / "analysis"
REV1_DIR   = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR    = REV1_DIR / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIR = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset")
TELE_DIR = DATA_DIR / "job-telemetry"

BETA_F_FROZEN   = 1.12484352   # from M3 (2024 training median)
BETA_F_MC       = 0.9569       # value used in original phase3b MC -- used for D.8 consistency
N_BINS_MC       = 5            # original MC binning
T_P95_THRESHOLD = 60.602770562770566
MC_BASE_SEED    = 200
SCEN27_IDX      = 27
SCEN27_SEED     = MC_BASE_SEED + SCEN27_IDX * 97   # = 2819
GCD_REQUIRED    = 8
MIN_VALID_TS    = 5

def git_sha():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=str(REPO_ROOT)).strip()
    except Exception:
        return "unknown"

def jf(v):
    if v is None:
        return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

t_script = time.time()
print("=" * 65)
print("Gate D: M3 Completion Analysis")
print("=" * 65)

# ── Shared data load ────────────────────────────────────────────
print("\n[0] Loading shared data ...")
fp_df    = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
fp_nodes = set(fp_df.index.tolist())
FA_dict  = fp_df["FA_2024"].to_dict()
test_df  = pd.read_parquet(ANAL_DIR / "phase3a_test_set.parquet")
tb       = pd.read_parquet(OUT_DIR / "m3_train_betas.parquet")
tres_df  = pd.read_parquet(OUT_DIR / "m3_test_residuals.parquet")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)

with open(ANAL_DIR / "phase3b_mc_results.json") as f:
    mc_results = json.load(f)
with open(ANAL_DIR / "phase3b_mc_analysis.json") as f:
    mc_enriched = json.load(f)

print(f"    fp nodes: {len(fp_nodes)}")
print(f"    test rows: {len(test_df)}")
print(f"    train betas: {len(tb)}")
print(f"    all jobs: {len(all_jobs):,}")

# ── D.1+D.2: 2024 training T_p95 distribution ──────────────────
print("\n[D.1+D.2] 2024 training T_p95 thresholds ...")
t0 = time.time()

TRAIN_T_CACHE = OUT_DIR / "d2_train_t95_distribution.parquet"
if TRAIN_T_CACHE.exists():
    t95_cache = pd.read_parquet(TRAIN_T_CACHE)
    train_t95_all = t95_cache["t_p95"].values
    print(f"    Loaded from cache ({len(train_t95_all):,} node-job pairs)")
else:
    train_t95_rows = []
    n_jobs_ok = 0
    for _, row in tb.iterrows():
        date_dir = str(row["date_dir"])
        job_idx  = int(row["job_idx"])
        job_dir  = TELE_DIR / date_dir / f"{job_idx:06d}"
        tfile    = job_dir / f"{job_idx:06d}-cleaned-temperature.parquet"
        if not tfile.exists():
            continue
        try:
            tmp = pd.read_parquet(tfile)
        except Exception:
            continue
        gcd_cols  = [c for c in tmp.columns if "_gcd" in c and "frontier" in c]
        node_names = sorted(set(c.split("_gpu")[0] for c in gcd_cols))
        for node in node_names:
            if node not in fp_nodes:
                continue
            gcols = [c for c in gcd_cols if c.startswith(node + "_")]
            if len(gcols) < GCD_REQUIRED:
                continue
            t_mat  = tmp[gcols].values.astype(float)
            if t_mat.shape[1] < GCD_REQUIRED:
                continue
            t_ts   = np.nanmean(t_mat, axis=1)
            finite = t_ts[np.isfinite(t_ts)]
            if len(finite) < MIN_VALID_TS:
                continue
            train_t95_rows.append({"job_idx": job_idx, "node": node,
                                   "t_p95": float(np.percentile(finite, 95))})
        n_jobs_ok += 1
        if n_jobs_ok % 50 == 0:
            print(f"    ... {n_jobs_ok}/{len(tb)} training jobs", end="\r")

    t95_cache = pd.DataFrame(train_t95_rows)
    t95_cache.to_parquet(TRAIN_T_CACHE, index=False)
    train_t95_all = t95_cache["t_p95"].values
    print(f"\n    Jobs processed: {n_jobs_ok}/{len(tb)}")
    print(f"    Node-job pairs: {len(train_t95_all):,}")

thr_p90_2024 = float(np.percentile(train_t95_all, 90))
thr_p95_2024 = float(np.percentile(train_t95_all, 95))
thr_p99_2024 = float(np.percentile(train_t95_all, 99))
thr_mean_2024 = float(np.mean(train_t95_all))

print(f"    2024 T_p95 distribution ({len(train_t95_all):,} node-job pairs):")
print(f"      mean={thr_mean_2024:.3f}  p90={thr_p90_2024:.3f}  "
      f"p95={thr_p95_2024:.3f}  p99={thr_p99_2024:.3f}")
print(f"    Reference: fixed threshold=60.60, test-set p95={np.percentile(test_df.T_p95, 95):.3f}")
print(f"    Elapsed: {time.time()-t0:.1f}s")

d12_result = {
    "n_node_job_pairs_training": int(len(train_t95_all)),
    "n_training_jobs":           int(len(tb)),
    "t_p95_mean_2024":  jf(thr_mean_2024),
    "t_p95_p90_2024":   jf(thr_p90_2024),
    "t_p95_p95_2024":   jf(thr_p95_2024),
    "t_p95_p99_2024":   jf(thr_p99_2024),
    "fixed_threshold":  jf(T_P95_THRESHOLD),
    "test_set_p95":     jf(float(np.percentile(test_df.T_p95, 95))),
    "note": (
        "Thresholds derived from 2024 training telemetry (same jobs that generated "
        "BETA_F_frozen=1.1248). Node-job pairs: fp nodes in qualifying training jobs "
        "with all 8 GCD channels and >=5 valid timestamps."
    ),
}

# ── D.3+D.4: Identity replay B/S ───────────────────────────────
print("\n[D.3+D.4] Identity replay B/S ...")
t0 = time.time()

# Build per-job alpha_j = observed job mean T_p95 (from test set)
# T_pred_ij = alpha_j + BETA_F_frozen * FA_2024_i = alpha_j + pred_frozen_model_ij
job_mean = test_df.groupby("job_idx")["T_p95"].mean()

# Merge predicted temperatures
tres = tres_df.copy()
tres["alpha_j"] = tres["job_idx"].map(job_mean)
tres["T_pred"]  = tres["alpha_j"] + tres["pred_frozen_model"]
# pred_frozen_model = BETA_F_frozen * FA_2024 (no job mean offset included)
# So T_pred = alpha_j + BETA_F_frozen * FA_2024 = job mean + scaled fingerprint

# Merge with observed T_p95
obs = test_df[["job_idx", "node", "T_p95"]].rename(columns={"T_p95": "T_obs"})
tres = tres.merge(obs, on=["job_idx", "node"], how="left")

# Run times per job
rt_map = all_jobs.set_index("job_idx_int")["run_time"].to_dict()
tres["rt_h"] = tres["job_idx"].map(lambda j: rt_map.get(int(j), 0.0)) / 3600.0

thresholds = {
    "fixed_60_60":  T_P95_THRESHOLD,
    "p90_2024":     thr_p90_2024,
    "p95_2024":     thr_p95_2024,
    "p99_2024":     thr_p99_2024,
}

# Historical B/S reference (using fixed threshold, matching published paper)
# This is the same B_hist_node as in phase3b_mc.py
B_hist_ref  = float((tres["rt_h"] * (tres["T_obs"] > T_P95_THRESHOLD)).sum())
S_hist_ref  = float((tres["rt_h"] * (tres["T_obs"] - T_P95_THRESHOLD).clip(lower=0)).sum())

d34_by_thr = {}
for thr_name, thr_val in thresholds.items():
    B_obs   = float((tres["rt_h"] * (tres["T_obs"]  > thr_val)).sum())
    S_obs   = float((tres["rt_h"] * (tres["T_obs"]  - thr_val).clip(lower=0)).sum())
    B_model = float((tres["rt_h"] * (tres["T_pred"] > thr_val)).sum())
    S_model = float((tres["rt_h"] * (tres["T_pred"] - thr_val).clip(lower=0)).sum())
    d34_by_thr[thr_name] = {
        "threshold_C":       jf(thr_val),
        "B_obs_h":           jf(B_obs),
        "S_obs_Cdoth":       jf(S_obs),
        "B_model_id_h":      jf(B_model),
        "S_model_id_Cdoth":  jf(S_model),
        "B_obs_ratio":       jf(B_obs   / max(B_hist_ref, 1e-9)),
        "S_obs_ratio":       jf(S_obs   / max(S_hist_ref, 1e-9)),
        "B_model_ratio":     jf(B_model / max(B_hist_ref, 1e-9)),
        "S_model_ratio":     jf(S_model / max(S_hist_ref, 1e-9)),
    }
    print(f"    {thr_name} (T>{thr_val:.2f}C): "
          f"B_obs/B_hist={B_obs/max(B_hist_ref,1e-9):.4f}  "
          f"B_model/B_hist={B_model/max(B_hist_ref,1e-9):.4f}")

# Correlation of per-node-job observed vs model-predicted exceedance
tres["exc_obs"]   = (tres["T_obs"]  - T_P95_THRESHOLD).clip(lower=0)
tres["exc_model"] = (tres["T_pred"] - T_P95_THRESHOLD).clip(lower=0)
r_exc, _ = scipy_stats.pearsonr(tres["exc_obs"], tres["exc_model"])
print(f"    Pearson r(exc_obs, exc_model): {r_exc:.4f}")

# Model bias: mean(T_pred - T_obs)
bias = float((tres["T_pred"] - tres["T_obs"]).mean())
rmse = float(np.sqrt(((tres["T_pred"] - tres["T_obs"])**2).mean()))
print(f"    Identity bias(pred-obs): {bias:+.4f}C  RMSE: {rmse:.4f}C")
print(f"    Elapsed: {time.time()-t0:.1f}s")

d34_result = {
    "beta_F_frozen":   BETA_F_FROZEN,
    "B_hist_ref_h":    jf(B_hist_ref),
    "S_hist_ref_Cdoth": jf(S_hist_ref),
    "identity_model_bias_C": jf(bias),
    "identity_model_rmse_C": jf(rmse),
    "r_exceedance_obs_vs_model": jf(r_exc),
    "note": (
        "T_pred_ij = alpha_j + BETA_F_frozen * FA_2024_i, where alpha_j = "
        "mean(T_p95_obs) across fp nodes in job j (test set). "
        "Model-identity B/S uses T_pred; observed B/S uses T_obs. "
        "Ratios normalised against B_hist/S_hist at the fixed 60.60C threshold."
    ),
    "by_threshold": d34_by_thr,
}

# ── D.5: Residual bin sensitivity K=1,3,5,10 ───────────────────
print("\n[D.5] Residual bin sensitivity ...")
t0 = time.time()

# test_res: per-(job,node) residuals from frozen model
# resid_frozen_model = T_obs - (alpha_j + BETA_F_frozen * FA_2024_i)
# = T_obs - T_pred
# We re-use tres (which already has T_obs, T_pred, FA_2024 via tres_df.FA_2024)
test_res_bins = tres_df.copy()
test_res_bins["FA_2024"]  = test_res_bins["FA_2024"]
test_res_bins["residual"] = test_res_bins["resid_frozen_model"]

K_values = [1, 3, 5, 10]
bin_stats = {}

for K in K_values:
    within_ss = 0.0
    total_ss  = 0.0
    bin_means_list = []
    n_jobs_with_K_bins = 0
    n_jobs_underbinned = 0

    for jid, grp in test_res_bins.groupby("job_idx"):
        grp_s = grp.sort_values("FA_2024")
        res_arr = grp_s["residual"].values
        k = len(grp_s)
        total_ss += float(np.sum((res_arr - res_arr.mean())**2))
        if k >= K and K > 1:
            try:
                bins = pd.qcut(grp_s["FA_2024"], q=K, labels=False,
                               duplicates="drop").values.astype(int)
            except Exception:
                bins = np.zeros(k, dtype=int)
            n_bins_actual = len(np.unique(bins))
            if n_bins_actual < K:
                n_jobs_underbinned += 1
        else:
            bins = np.zeros(k, dtype=int)
            if K > 1:
                n_jobs_underbinned += 1
        # Within-bin SS
        for b in np.unique(bins):
            mask = bins == b
            r_b  = res_arr[mask]
            bin_means_list.append(float(r_b.mean()))
            within_ss += float(np.sum((r_b - r_b.mean())**2))
        n_jobs_with_K_bins += 1

    r2_bins = 1.0 - within_ss / max(total_ss, 1e-12)
    bin_means_arr = np.array(bin_means_list)
    print(f"    K={K:2d}: R2_bins={r2_bins:.5f}  "
          f"within_var_frac={within_ss/max(total_ss,1e-12):.5f}  "
          f"underbinned_jobs={n_jobs_underbinned}/{n_jobs_with_K_bins}")
    bin_stats[f"K{K}"] = {
        "K": K,
        "r2_bins_explain": jf(r2_bins),
        "within_var_fraction": jf(within_ss / max(total_ss, 1e-12)),
        "n_jobs_underbinned": n_jobs_underbinned,
        "n_jobs_total": n_jobs_with_K_bins,
    }

# Parametric heteroscedastic: fit residual std ~ f(FA_2024)
# Model: sigma_ij = exp(a + b * FA_2024_i)  [log-linear in FA]
fa_vals   = test_res_bins["FA_2024"].values
res_vals  = test_res_bins["residual"].values
abs_res   = np.abs(res_vals)
log_abs_nz = np.log(abs_res[abs_res > 1e-6])
fa_nz      = fa_vals[abs_res > 1e-6]
if len(fa_nz) > 100:
    slope_het, intercept_het, r_het, _, _ = scipy_stats.linregress(fa_nz, log_abs_nz)
    print(f"    Parametric heteroscedastic: log|resid| ~ FA: "
          f"slope={slope_het:.4f}  r={r_het:.4f}")
else:
    slope_het, intercept_het, r_het = None, None, None

print(f"    Elapsed: {time.time()-t0:.1f}s")

d5_result = {
    "residual_source": "resid_frozen_model from m3_test_residuals.parquet (= T_obs - T_pred_frozen)",
    "binning_variable": "FA_2024 quantile within each test job",
    "by_K": bin_stats,
    "parametric_heteroscedastic": {
        "model": "log|residual| ~ a + b * FA_2024",
        "slope_b": jf(slope_het),
        "intercept_a": jf(intercept_het),
        "pearson_r": jf(r_het),
        "note": (
            "Negative slope means cooler nodes (low FA_2024) have larger absolute residuals, "
            "consistent with larger relative variance at the thermal floor. "
            "Small |r| suggests the heteroscedasticity is modest."
        ),
    },
}

# ── D.6: Non-monotonicity of crossing curves ────────────────────
print("\n[D.6] Non-monotonicity analysis ...")

lam_sweep = mc_results["MC_lambda_sweep"]
n_scen = len(mc_results["scenarios"])

nonmono = {"fp": [], "random": []}
magnitude = {"fp": [], "random": []}

for scen in mc_results["scenarios"]:
    for pol in ["fp", "random"]:
        rows = scen[pol]["rows"]
        b_vals = [r["B_node_ratio"] for r in rows if r.get("B_node_ratio") is not None]
        s_vals = [r["S_node_ratio"] for r in rows if r.get("S_node_ratio") is not None]
        # Check B monotonicity
        b_nonmono = any(b_vals[i] > b_vals[i+1] for i in range(len(b_vals)-1))
        s_nonmono = any(s_vals[i] > s_vals[i+1] for i in range(len(s_vals)-1))
        nonmono[pol].append({"B": b_nonmono, "S": s_nonmono})
        # Magnitude of max drop
        if len(b_vals) > 1:
            b_drops = [b_vals[i] - b_vals[i+1]
                       for i in range(len(b_vals)-1) if b_vals[i] > b_vals[i+1]]
            magnitude[pol].append(max(b_drops) if b_drops else 0.0)

for pol in ["fp", "random"]:
    n_B = sum(1 for x in nonmono[pol] if x["B"])
    n_S = sum(1 for x in nonmono[pol] if x["S"])
    mags = [m for m in magnitude[pol] if m > 0]
    print(f"    {pol}: B non-mono={n_B}/{n_scen}, S non-mono={n_S}/{n_scen}"
          + (f"  B-drop max={max(mags):.4f} med={np.median(mags):.4f}" if mags else ""))

d6_result = {
    "n_scenarios": n_scen,
    "lambda_sweep": lam_sweep,
    "note": (
        "Non-monotonicity occurs when B_node_ratio or S_node_ratio decreases at a "
        "higher lambda due to MC stochasticity (different job assignment draws). "
        "S is more volatile because exceedance severity is a continuous quantity "
        "sensitive to which specific thermal extremes are assigned."
    ),
    "by_policy": {},
}
for pol in ["fp", "random"]:
    n_B = sum(1 for x in nonmono[pol] if x["B"])
    n_S = sum(1 for x in nonmono[pol] if x["S"])
    mags = np.array([m for m in magnitude[pol] if m > 0])
    d6_result["by_policy"][pol] = {
        "n_B_nonmonotonic": n_B,
        "n_S_nonmonotonic": n_S,
        "B_nonmono_rate":   jf(n_B / n_scen),
        "S_nonmono_rate":   jf(n_S / n_scen),
        "B_max_drop_magnitude": jf(float(mags.max())) if len(mags) > 0 else None,
        "B_median_drop_magnitude": jf(float(np.median(mags))) if len(mags) > 0 else None,
    }

# ── D.7: Conservative first-violation brackets ──────────────────
print("\n[D.7] Conservative crossing brackets ...")

bracket_lo_vals = []
interp_vals     = []
bracket_gaps    = []
n_censored = 0
n_bracket_available = 0

for e in mc_enriched["enriched"]:
    fp = e["fp"]
    c_lo   = fp.get("C_bracket_lo")     # capacity_unlock_pct at last lambda before B>1
    c_hi   = fp.get("C_bracket_hi")     # capacity_unlock_pct at first lambda where B>1
    c_feas = fp.get("C_feasible")       # interpolated crossing (same units as c_lo)
    c_sys  = fp.get("C_system_replay")  # fleet-scale fraction (different units)
    if c_feas is None:
        n_censored += 1
        continue
    n_bracket_available += 1
    bracket_lo_vals.append(float(c_lo) if c_lo is not None else float(c_feas))
    interp_vals.append(float(c_feas))   # both in capacity_unlock_pct
    if c_lo is not None and c_hi is not None:
        bracket_gaps.append(float(c_hi) - float(c_lo))

blo = np.array(bracket_lo_vals)
cv  = np.array(interp_vals)
bg  = np.array(bracket_gaps)

print(f"    Scenarios with binding constraint: {n_bracket_available}")
print(f"    Right-censored (no binding): {n_censored}")
print(f"    Bracket lo (conservative):    median={np.median(blo):.2f}%  "
      f"p5={np.percentile(blo,5):.2f}%  p95={np.percentile(blo,95):.2f}%")
print(f"    Interpolated (C_feasible):    median={np.median(cv):.2f}%   "
      f"p5={np.percentile(cv,5):.2f}%   p95={np.percentile(cv,95):.2f}%")
if len(bg) > 0:
    print(f"    Lambda interval width:       median={np.median(bg):.2f}%  "
          f"max={np.max(bg):.2f}%")

d7_result = {
    "n_binding_scenarios": n_bracket_available,
    "n_censored": n_censored,
    "units": "capacity_unlock_pct (extra cohort node-hours / hist cohort node-hours * 100)",
    "conservative_bracket_lo": {
        "median_pct":  jf(float(np.median(blo))),
        "p5_pct":      jf(float(np.percentile(blo, 5))),
        "p95_pct":     jf(float(np.percentile(blo, 95))),
    },
    "interpolated_c_feasible": {
        "median_pct":  jf(float(np.median(cv))),
        "p5_pct":      jf(float(np.percentile(cv, 5))),
        "p95_pct":     jf(float(np.percentile(cv, 95))),
    },
    "lambda_interval_width_pct": {
        "median": jf(float(np.median(bg))) if len(bg) > 0 else None,
        "max":    jf(float(np.max(bg)))    if len(bg) > 0 else None,
    },
    "note": (
        "C_bracket_lo = capacity_unlock_pct at the last lambda below the B_node_ratio=1.0 "
        "crossing (conservative lower bound on safe capacity unlock). C_bracket_hi = "
        "first lambda where B_node_ratio >= 1.0. C_feasible = interpolated crossing "
        "estimate. All in capacity_unlock_pct units (same scale). "
        "C_system_replay (fleet-wide fraction) is a separate derived metric in the "
        "enriched analysis and is ~100x smaller than capacity_unlock_pct."
    ),
}

# ── D.8: Scenario 27 extension to lambda=2.0 ───────────────────
print("\n[D.8] Scenario 27 extension to lambda=2.0 ...")
print("      Setting up MC infrastructure (this may take 2-5 min) ...")
t0 = time.time()

# Use same setup as phase3b_mc.py but load correct topology map (corrected xnames)
# for B_node_ratio only (no cabinet power).
# BETA_F = 0.9569 for consistency with existing scenario 27 results.

BETA_F_D8 = BETA_F_MC   # 0.9569

# ── Cabinet map (buggy, consistent with original MC) ──
_xe2_re_d8 = re.compile(r"x(\d+)c")
node_to_cabinet_d8: dict[str, int] = {}
for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    for hn, xn in zip(hl, str(nl).split()):
        xn = xn.strip("'[]\"")
        if hn not in node_to_cabinet_d8:
            m = _xe2_re_d8.match(xn)
            if m:
                node_to_cabinet_d8[hn] = int(m.group(1))

# Cohort
cohort_set_d8  = set(fp_df.index)
cohort_list_d8 = sorted(cohort_set_d8)
F_dict_d8      = fp_df["FA_2024"].to_dict()

def _col_to_dt64ms(series):
    s = pd.to_datetime(series, utc=True)
    return s.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ms]")

def _to_dt64_ms(ts):
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return np.datetime64(t.tz_convert("UTC").tz_localize(None), "ms")

def _dt64_to_h(a, b):
    return float((b - a).astype("int64")) / 3.6e6

# Schedule arrays
cohort_per_job_d8: dict[int, frozenset] = {}
for jid, hl in zip(all_jobs["job_idx_int"].values, all_jobs["host_list"].values):
    cn = frozenset(n for n in hl if n in cohort_set_d8)
    if cn:
        cohort_per_job_d8[jid] = cn

has_cohort_d8 = np.array([jid in cohort_per_job_d8 for jid in all_jobs["job_idx_int"].values])
sched_jids_d8 = all_jobs["job_idx_int"].values[has_cohort_d8]
sched_st_d8   = _col_to_dt64ms(all_jobs["start_time"])[has_cohort_d8]
sched_et_d8   = _col_to_dt64ms(all_jobs["end_time"])[has_cohort_d8]
sched_cn_d8   = np.array([cohort_per_job_d8[jid] for jid in sched_jids_d8], dtype=object)

# Job-level aggregate (matching phase3b_mc.py exactly)
job_agg_d8 = (
    test_df.groupby("job_idx")
    .agg(F_hist_mean=("F_2024", "mean"), n_cohort=("node", "count"),
         T_p95_hist=("T_p95", "mean"), hist_nodes=("node", list))
    .reset_index()
)
meta_d8 = (
    all_jobs[["job_idx_int", "node_count", "start_time", "end_time", "mean_power", "run_time"]]
    .rename(columns={"job_idx_int": "job_idx"})
)
job_agg_d8 = job_agg_d8.merge(meta_d8, on="job_idx", how="left")
job_agg_d8["power_per_node"] = job_agg_d8["mean_power"] / job_agg_d8["node_count"].clip(lower=1)
test_id_set_d8 = set(job_agg_d8["job_idx"].astype(int))
jobs_sorted_d8 = job_agg_d8.sort_values("start_time").reset_index(drop=True)
n_base_d8      = len(jobs_sorted_d8)

hist_node_hours_d8 = {n: 0.0 for n in cohort_list_d8}
for _, jrow in jobs_sorted_d8.iterrows():
    rt_h = float(jrow["run_time"]) / 3600.0
    for nd in jrow["hist_nodes"]:
        if nd in hist_node_hours_d8:
            hist_node_hours_d8[nd] += rt_h
hist_util_arr_d8  = np.array([hist_node_hours_d8[n] for n in cohort_list_d8])
hist_total_nh_d8  = float(hist_util_arr_d8.sum())
hist_fleet_avg_d8 = hist_total_nh_d8 / len(cohort_list_d8)

rt_lookup_d8   = jobs_sorted_d8.set_index("job_idx")["run_time"].to_dict()
test_rt_h_d8   = test_df["job_idx"].map(lambda j: rt_lookup_d8.get(int(j), 0.0)) / 3600.0
node_excess_d8 = test_df["T_p95"] - T_P95_THRESHOLD
B_hist_node_d8 = float((test_rt_h_d8 * (node_excess_d8 > 0)).sum())
S_hist_node_d8 = float((test_rt_h_d8 * node_excess_d8.clip(lower=0)).sum())

# Residuals with N_BINS_MC=5 and BETA_F_D8=0.9569 (exact match to original MC)
jobs_sorted_d8["alpha_j"] = jobs_sorted_d8["T_p95_hist"] - BETA_F_D8 * jobs_sorted_d8["F_hist_mean"]
alpha_map_d8 = jobs_sorted_d8.set_index("job_idx")["alpha_j"].to_dict()
test_res_d8 = test_df.copy()
test_res_d8["alpha_j"]  = test_res_d8["job_idx"].map(lambda j: alpha_map_d8.get(int(j), np.nan))
test_res_d8["F_i"]      = test_res_d8["node"].map(F_dict_d8)
test_res_d8["residual"] = test_res_d8["T_p95"] - test_res_d8["alpha_j"] - BETA_F_D8 * test_res_d8["F_i"]
job_residuals_d8: dict[int, tuple] = {}
for jid, grp in test_res_d8.groupby("job_idx"):
    jid = int(jid)
    grp_s = grp.sort_values("F_i")
    res_arr = grp_s["residual"].values.copy()
    k = len(grp_s)
    if k >= N_BINS_MC:
        try:
            bins = pd.qcut(grp_s["F_i"], q=N_BINS_MC, labels=False,
                           duplicates="drop").values.astype(int)
        except Exception:
            bins = np.zeros(k, dtype=int)
    else:
        bins = np.zeros(k, dtype=int)
    job_residuals_d8[jid] = (res_arr, bins)

# bg_busy_per_job
is_test_sched_d8 = np.array([jid in test_id_set_d8 for jid in sched_jids_d8])
bg_st_d8 = sched_st_d8[~is_test_sched_d8]
bg_et_d8 = sched_et_d8[~is_test_sched_d8]
bg_cn_d8 = sched_cn_d8[~is_test_sched_d8]
bg_busy_per_job_d8: dict[int, frozenset] = {}
for _, jrow in jobs_sorted_d8.iterrows():
    jid = int(jrow["job_idx"])
    t_j = np.datetime64(pd.Timestamp(jrow["start_time"]).tz_convert("UTC").tz_localize(None), "ms")
    mask = (bg_st_d8 <= t_j) & (bg_et_d8 > t_j)
    bg_busy_per_job_d8[jid] = (frozenset().union(*bg_cn_d8[mask])
                                if mask.any() else frozenset())

hist_starts_dt64_d8 = np.array([_to_dt64_ms(r["start_time"])
                                 for _, r in jobs_sorted_d8.iterrows()])
hist_ends_dt64_d8   = np.array([_to_dt64_ms(r["end_time"])
                                 for _, r in jobs_sorted_d8.iterrows()])
hist_k_arr_d8    = jobs_sorted_d8["n_cohort"].values.astype(int)
hist_jids_arr_d8 = jobs_sorted_d8["job_idx"].values.astype(int)
print(f"    Setup complete ({time.time()-t0:.1f}s)")

# Look-ahead and pool helpers
def look_ahead_safe_d8(selected_nodes, t_s, t_e, cf_busy):
    overlap_mask = (hist_starts_dt64_d8 > t_s) & (hist_starts_dt64_d8 < t_e)
    if not overlap_mask.any():
        return True
    s_nodes = frozenset(selected_nodes)
    for idx in np.where(overlap_mask)[0]:
        t_h   = hist_starts_dt64_d8[idx]
        k_h   = int(hist_k_arr_d8[idx])
        jid_h = int(hist_jids_arr_d8[idx])
        bg_at_h = bg_busy_per_job_d8[jid_h]
        cf_at_h = frozenset(n for n, te in cf_busy.items() if te > t_h)
        blocked = bg_at_h | cf_at_h | s_nodes
        fb_mask = ((hist_starts_dt64_d8 > t_s) & (hist_starts_dt64_d8 <= t_h)
                   & (hist_ends_dt64_d8 > t_h))
        fb_mask = fb_mask.copy(); fb_mask[idx] = False
        future_base_k = min(int(hist_k_arr_d8[fb_mask].sum()),
                            max(0, len(cohort_list_d8) - len(blocked)))
        if len(cohort_list_d8) - len(blocked) - future_base_k < k_h:
            return False
    return True

def sample_pool_d8(n_extra, seed):
    rng_s = np.random.default_rng(seed)
    base_months = jobs_sorted_d8["start_time"].dt.month.values
    base_hours  = jobs_sorted_d8["start_time"].dt.hour.values
    strat_keys  = list(zip(base_months.tolist(), base_hours.tolist()))
    strat_to_idxs: dict = {}
    for i, sk in enumerate(strat_keys):
        strat_to_idxs.setdefault(sk, []).append(i)
    unique_strata = sorted(strat_to_idxs.keys())
    counts = np.array([len(strat_to_idxs[s]) for s in unique_strata])
    probs  = counts / counts.sum()
    n_per  = np.round(probs * n_extra).astype(int)
    diff   = n_extra - n_per.sum()
    if diff > 0: n_per[np.argsort(-probs)[:diff]] += 1
    elif diff < 0: n_per[np.argsort(n_per)[:(-diff)]] -= 1
    chunks = []
    for sk, n_s in zip(unique_strata, n_per):
        if n_s <= 0: continue
        idxs = rng_s.choice(strat_to_idxs[sk], size=int(n_s), replace=True)
        chunks.append(jobs_sorted_d8.iloc[idxs])
    if not chunks:
        return pd.DataFrame(columns=list(jobs_sorted_d8.columns) + ["is_synthetic", "parent_job_idx"])
    syn = pd.concat(chunks, ignore_index=True)
    jitter = rng_s.uniform(-1800., 1800., size=len(syn))
    syn["start_time"]     = syn["start_time"] + pd.to_timedelta(jitter, unit="s")
    syn["end_time"]       = syn["start_time"] + pd.to_timedelta(syn["run_time"].values, unit="s")
    syn["is_synthetic"]   = True
    syn["parent_job_idx"] = syn["job_idx"].values.copy()
    syn["job_idx"]        = -(np.arange(len(syn), dtype=np.int64) + 1)
    syn["alpha_j"]        = syn["parent_job_idx"].map(alpha_map_d8)
    syn = syn.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)
    return syn

def gen_perms_d8(syn_pool, scen_rng):
    job_perms = {}
    for jid in jobs_sorted_d8["job_idx"].astype(int):
        res_s, bins = job_residuals_d8[jid]
        k = len(res_s); perm = np.arange(k)
        for b in np.unique(bins):
            idx_b = np.where(bins == b)[0]
            perm[idx_b] = scen_rng.permutation(idx_b)
        job_perms[jid] = perm
    if len(syn_pool) > 0:
        for syn_jid, parent_jid in zip(syn_pool["job_idx"].astype(int),
                                        syn_pool["parent_job_idx"].astype(int)):
            res_s, bins = job_residuals_d8[parent_jid]
            k = len(res_s); perm = np.arange(k)
            for b in np.unique(bins):
                idx_b = np.where(bins == b)[0]
                perm[idx_b] = scen_rng.permutation(idx_b)
            job_perms[syn_jid] = perm
    return job_perms

def capacity_replay_d8(syn_subset, policy, delta_cap, lambda_val, policy_seed, job_perms):
    cap_per_node = (1.0 + delta_cap) * lambda_val * hist_fleet_avg_d8
    if len(syn_subset) > 0:
        base_copy = jobs_sorted_d8.copy()
        base_copy["is_synthetic"]   = False
        base_copy["parent_job_idx"] = base_copy["job_idx"].values.copy()
        combined = pd.concat([base_copy, syn_subset], ignore_index=True)
    else:
        combined = jobs_sorted_d8.copy()
        combined["is_synthetic"]   = False
        combined["parent_job_idx"] = combined["job_idx"].values.copy()
    combined = combined.sort_values("start_time").reset_index(drop=True)

    cf_busy: dict[str, np.datetime64] = {}
    cf_util: dict[str, float] = {n: 0.0 for n in cohort_set_d8}
    _rng = np.random.default_rng(policy_seed)

    B_node = 0.0; S_node = 0.0
    syn_node_hours = 0.0; n_syn_admit = 0

    for _, jrow in combined.iterrows():
        is_syn = bool(jrow["is_synthetic"])
        t_j    = _to_dt64_ms(jrow["start_time"])
        t_e    = _to_dt64_ms(jrow["end_time"])
        rt_h   = float(jrow["run_time"]) / 3600.0
        k      = int(jrow["n_cohort"])
        jid    = int(jrow["job_idx"])
        try:
            parent_jid = int(jrow["parent_job_idx"])
        except (TypeError, ValueError):
            parent_jid = jid

        if is_syn:
            mask_bg = (bg_st_d8 <= t_j) & (bg_et_d8 > t_j)
            bg_busy = (frozenset().union(*bg_cn_d8[mask_bg])
                       if mask_bg.any() else frozenset())
        else:
            bg_busy = bg_busy_per_job_d8.get(parent_jid, frozenset())
        cf_busy_now = frozenset(n for n, te in cf_busy.items() if te > t_j)

        avail_capped = [n for n in cohort_list_d8
                        if n not in bg_busy and n not in cf_busy_now
                        and cf_util[n] < cap_per_node]

        if is_syn:
            if len(avail_capped) < k:
                continue
            available = avail_capped
        else:
            available = (avail_capped if len(avail_capped) >= k
                         else [n for n in cohort_list_d8
                               if n not in bg_busy and n not in cf_busy_now])

        n_avail = len(available)
        if n_avail == 0:
            selected = []
        elif policy == "fp":
            avail_F = np.array([F_dict_d8[n] for n in available])
            order   = np.argsort(avail_F)
            selected = [available[i] for i in order[:min(k, n_avail)]]
        else:
            idx = _rng.choice(n_avail, size=min(k, n_avail), replace=False)
            selected = [available[i] for i in idx]

        if is_syn and selected:
            if not look_ahead_safe_d8(selected, t_j, t_e, cf_busy):
                continue

        for n in selected:
            cf_busy[n] = t_e
            cf_util[n] += rt_h

        if selected:
            F_arr    = np.array([F_dict_d8[n] for n in selected])
            alpha    = float(jrow["alpha_j"])
            res_s, _ = job_residuals_d8[parent_jid]
            perm     = job_perms[jid]
            rank     = np.argsort(np.argsort(F_arr))
            T_hats_j = alpha + BETA_F_D8 * F_arr + res_s[perm[rank]]
            excesses = T_hats_j - T_P95_THRESHOLD
            B_node  += rt_h * float((excesses > 0).sum())
            S_node  += rt_h * float(excesses.clip(min=0).sum())
            if is_syn:
                n_syn_admit    += 1
                syn_node_hours += len(selected) * rt_h

    unlock_pct = syn_node_hours / hist_total_nh_d8 * 100.0
    return {
        "lambda_val":          lambda_val,
        "policy":              policy,
        "n_syn_admit":         n_syn_admit,
        "syn_node_hours":      syn_node_hours,
        "capacity_unlock_pct": unlock_pct,
        "B_node_ratio":        B_node / B_hist_node_d8 if B_hist_node_d8 > 0 else float("nan"),
        "S_node_ratio":        S_node / S_hist_node_d8 if S_hist_node_d8 > 0 else float("nan"),
    }

# Run scenario 27 full trajectory [1.0..2.0] with consistent pool.
# Pool must be sized for LAMBDA_MAX=2.0; different from original 1.50-capped MC pool.
# The lambda<=1.50 values may differ slightly from original MC (different pool composition),
# but the full trajectory is internally consistent with same scen_seed and wl_seed.
LAMBDA_FULL_D8 = [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40, 1.50, 1.55, 1.60, 1.70, 1.80, 1.90, 2.00]
LAMBDA_MAX_D8  = 2.00

scen27_seed = SCEN27_SEED
wl_seed_27  = scen27_seed + 50000

n_extra_max = int(np.ceil((LAMBDA_MAX_D8 - 1.0) * n_base_d8))
print(f"    Synthetic pool: {n_extra_max} jobs ...")
syn_pool_27 = sample_pool_d8(n_extra_max, wl_seed_27)
print(f"    Generating permutations ...")
scen_rng_27  = np.random.default_rng(scen27_seed)
job_perms_27 = gen_perms_d8(syn_pool_27, scen_rng_27)

print(f"    Running FP-cap-10 full sweep (lambda=1.0..2.0) ...")
full_rows_27 = []
fp_delta_cap = 0.10
first_bind_lam = None

for lam in LAMBDA_FULL_D8:
    n_syn = int(round((lam - 1.0) * n_base_d8))
    syn_sub = syn_pool_27.iloc[:n_syn].copy() if n_syn > 0 else pd.DataFrame(
        columns=list(jobs_sorted_d8.columns) + ["is_synthetic", "parent_job_idx"])
    t_lam = time.time()
    res = capacity_replay_d8(syn_sub, "fp", fp_delta_cap, lam,
                              scen27_seed + abs(hash("fp")) % 10000, job_perms_27)
    full_rows_27.append(res)
    print(f"      lam={lam:.2f}  B_ratio={res['B_node_ratio']:.4f}  "
          f"S_ratio={res['S_node_ratio']:.4f}  "
          f"unlock={res['capacity_unlock_pct']:.1f}%  ({time.time()-t_lam:.1f}s)")
    if first_bind_lam is None and res["B_node_ratio"] >= 1.0:
        first_bind_lam = lam

# Also keep original MC lambda<=1.50 rows for comparison
original_rows_27 = mc_results["scenarios"][SCEN27_IDX]["fp"]["rows"]

print(f"    First binding lambda (extended pool): "
      f"{first_bind_lam if first_bind_lam is not None else '>2.00'}")

# Conservative bracket from the consistent full trajectory
b_ratios_27 = [r["B_node_ratio"] for r in full_rows_27 if r.get("B_node_ratio") is not None]
lams_27     = [r["lambda_val"]   for r in full_rows_27 if r.get("B_node_ratio") is not None]

bracket_lo_27 = bracket_hi_27 = interp_27 = None
for i in range(len(b_ratios_27) - 1):
    if b_ratios_27[i] < 1.0 and b_ratios_27[i+1] >= 1.0:
        bracket_lo_27 = lams_27[i]
        bracket_hi_27 = lams_27[i+1]
        frac = (1.0 - b_ratios_27[i]) / max(b_ratios_27[i+1] - b_ratios_27[i], 1e-12)
        interp_27 = lams_27[i] + frac * (lams_27[i+1] - lams_27[i])
        print(f"    Bracket: [{bracket_lo_27:.2f}, {bracket_hi_27:.2f}]  "
              f"Interpolated lambda*={interp_27:.3f}")
        break

d8_result = {
    "scenario_idx":        SCEN27_IDX,
    "scenario_seed":       scen27_seed,
    "beta_F":              BETA_F_D8,
    "n_bins":              N_BINS_MC,
    "original_max_lambda": max(mc_results["MC_lambda_sweep"]),
    "full_lambda_sweep":   LAMBDA_FULL_D8,
    "first_binding_lambda": first_bind_lam,
    "bracket_lo_lambda":   bracket_lo_27,
    "bracket_hi_lambda":   bracket_hi_27,
    "interpolated_lambda_star": jf(interp_27),
    "extended_rows": [
        {k: jf(v) if isinstance(v, float) else v for k, v in r.items()}
        for r in full_rows_27
    ],
    "original_mc_rows_lambda_le_150": [
        {k: jf(v) if isinstance(v, float) else v for k, v in r.items()}
        for r in original_rows_27
    ],
    "note": (
        "Full trajectory [1.0..2.0] for scenario 27 (the right-censored scenario in the "
        "30-scenario MC). Uses same scen_seed=2819 and wl_seed=52819, but pool sized for "
        f"LAMBDA_MAX=2.0 (n_extra={n_extra_max} vs original 1318). Lambda<=1.50 values "
        "may differ slightly from original MC due to different pool composition. "
        f"BETA_F={BETA_F_D8} (original unfrozen value, for consistency with existing results). "
        "B_node_ratio = B_node_h / B_hist_node_h."
    ),
}

# ── Assemble and save ───────────────────────────────────────────
print("\n[7] Saving results ...")

result = {
    "script":    "r1_m3_completion.py",
    "git_sha":   git_sha(),
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "input_files": {
        "phase3a_fingerprint_2024.parquet": file_sha256(ANAL_DIR / "phase3a_fingerprint_2024.parquet"),
        "phase3a_test_set.parquet":         file_sha256(ANAL_DIR / "phase3a_test_set.parquet"),
        "m3_test_residuals.parquet":        file_sha256(OUT_DIR  / "m3_test_residuals.parquet"),
        "m3_train_betas.parquet":           file_sha256(OUT_DIR  / "m3_train_betas.parquet"),
        "phase3b_mc_results.json":          file_sha256(ANAL_DIR / "phase3b_mc_results.json"),
        "phase3b_mc_analysis.json":         file_sha256(ANAL_DIR / "phase3b_mc_analysis.json"),
    },
    "D1_D2_training_thresholds": d12_result,
    "D3_D4_identity_replay":     d34_result,
    "D5_residual_bin_sensitivity": d5_result,
    "D6_nonmonotonicity":          d6_result,
    "D7_conservative_brackets":    d7_result,
    "D8_scenario27_extension":     d8_result,
    "elapsed_seconds": round(time.time() - t_script, 1),
}

out_path = OUT_DIR / "m3_completion.json"
with open(out_path, "w") as f:
    json.dump(result, f, indent=2)

print(f"\nSaved: {out_path}")
print(f"Total elapsed: {time.time()-t_script:.1f}s")
