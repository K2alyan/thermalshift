#!/usr/bin/env python3
"""
M1: Machine Identity vs Physical Location
==========================================
Is F_i genuinely node-specific information beyond cabinet/chassis/slot location?

Analyses
--------
1.1  Parse hierarchy from fp_node_topology.csv
1.2  Variance decomposition of FA_2024 by location level
1.3  Location-only LOO prediction of Y_2025 vs individual F_2024
     (a) cabinet LOO, (b) chassis LOO, (c) slot LOO, (d) combined location,
     (e) repeated-position (chassis/slot/board/node_pos across cabinets),
     (f) individual F_2024 — all reported as frozen/no-refit R2
1.4  Permutation null (2000 draws each: global / within-cabinet / within-chassis)
1.5  Full-channel restriction note (Phase 0 showed >99% all-8-GCD; no analysis needed)
1.6  Power-adjusted fingerprint F^P (T ~ a_j + b_j*P per 2024 training job, frozen)
1.7  Hardware-move natural experiment: NOT FEASIBLE (hostname=xname 1:1 throughout)
1.8  Allocation-list-position analysis

Primary output: artifacts/revision1/results/m1_location_identity.json
Figures:        artifacts/revision1/figures/fig_m1_*.png
"""

import os, re, json, hashlib, subprocess, datetime, time
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path
from scipy import stats

REPO_ROOT  = Path(__file__).resolve().parents[3]
PHASE1_DIR = REPO_ROOT / "artifacts" / "phase1"
ANAL_DIR   = PHASE1_DIR / "analysis"
OUT_DIR    = REPO_ROOT / "artifacts" / "revision1" / "results"
FIG_DIR    = REPO_ROOT / "artifacts" / "revision1" / "figures"
TABLE_DIR  = REPO_ROOT / "artifacts" / "revision1" / "tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)
FIG_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIR   = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset")
TELE_DIR   = DATA_DIR / "job-telemetry"

N_PERM     = 2000
PERM_SEED  = 7
XNAME_RE   = re.compile(r"x(\d+)c(\d+)s(\d+)b(\d+)n(\d+)")

# F^P computation parameters
FP_CACHE        = OUT_DIR / "fp_power_adjusted.parquet"
FP_SAMPLE_N     = 1000   # training jobs to sample (all ~3945 would work but take ~30min)
FP_MIN_NODES    = 4      # min fp nodes with T and P data per job to use that job
FP_MIN_JOBS_NODE = 5     # min qualifying jobs per node to report F^P

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

def pearson_r(a, b):
    return float(np.corrcoef(a, b)[0, 1])

def spearman_r(a, b):
    return float(stats.spearmanr(a, b).statistic)

def frozen_r2(y_true, y_pred):
    """R2 = 1 - SSE/SST, no refitting."""
    sst = float(((y_true - y_true.mean()) ** 2).sum())
    sse = float(((y_true - y_pred) ** 2).sum())
    return 1.0 - sse / sst if sst > 0 else float("nan")

def mae(y_true, y_pred):
    return float(np.abs(y_true - y_pred).mean())

def rmse(y_true, y_pred):
    return float(np.sqrt(((y_true - y_pred) ** 2).mean()))

def jf(v):
    """Float for JSON: converts NaN/inf to None."""
    if v is None:
        return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f

print("=" * 65)
print("M1: Location vs Node Identity")
print("=" * 65)
t0 = time.time()

# ─────────────────────────────────────────────────────────────────────
# Load inputs
# ─────────────────────────────────────────────────────────────────────
print("\n[0] Loading inputs ...")
fp_df      = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
test_df    = pd.read_parquet(ANAL_DIR / "phase3a_test_set.parquet")

fp_hostname_set = set(fp_df.index)   # 2000 fp node hostnames

print(f"    Fingerprint: {len(fp_df)} nodes")
print(f"    Test set:    {len(test_df)} node-job rows, {test_df.job_idx.nunique()} jobs")
print(f"    NOTE: using fp_node_topology.csv (correct) not cohort_manifest.csv")

# Build node-level dataset: FA_2024 + location + Y_2025
test_df["job_mean_T"]  = test_df.groupby("job_idx")["T_p95"].transform("mean")
test_df["delta_T_p95"] = test_df["T_p95"] - test_df["job_mean_T"]

# Y_2025: median delta_T_p95 per node across test jobs (matches original validation)
y2025 = test_df.groupby("node").agg(
    Y_2025=("delta_T_p95", "median"),
    n_test_jobs=("job_idx", "nunique"),
).reset_index().rename(columns={"node": "hostname"})

# Merge with fingerprint
fp_reset = fp_df.reset_index().rename(columns={"node": "hostname"})

# IMPORTANT: cohort_manifest.csv (2000 nodes) does NOT match the fp analysis
# nodes. Use fp_node_topology.csv built by r1_00b_topology_audit.py.
topo_path = TABLE_DIR / "fp_node_topology.csv"
if not topo_path.exists():
    raise FileNotFoundError(
        "fp_node_topology.csv not found. Run r1_00b_topology_audit.py first.")
topo_df = pd.read_csv(topo_path)
print(f"    Topology table: {len(topo_df)} nodes, columns: {list(topo_df.columns)}")

node_df = (fp_reset
    .merge(topo_df[["hostname","cabinet","chassis","slot","board","node_pos"]],
           on="hostname", how="inner")
    .merge(y2025, on="hostname", how="inner"))

print(f"    Node-level merged: {len(node_df)} nodes")
assert len(node_df) == 2000, f"Expected 2000 nodes, got {len(node_df)}"

# Composite group keys (nested — for within-cabinet location)
node_df["cab_str"]     = node_df["cabinet"].astype(str)
node_df["chassis_str"] = (node_df["cabinet"].astype(str) + "_" +
                          node_df["chassis"].astype(str))
node_df["slot_str"]    = (node_df["cabinet"].astype(str) + "_" +
                          node_df["chassis"].astype(str) + "_" +
                          node_df["slot"].astype(str))
node_df["board_str"]   = node_df["slot_str"] + "_" + node_df["board"].astype(str)
node_df["pos_str"]     = node_df["board_str"] + "_" + node_df["node_pos"].astype(str)

# Position key WITHOUT cabinet: tests whether pattern repeats at same physical
# position (chassis/slot/board/node_pos) across all cabinets
node_df["pos_key"] = (node_df["chassis"].astype(str) + "_" +
                      node_df["slot"].astype(str) + "_" +
                      node_df["board"].astype(str) + "_" +
                      node_df["node_pos"].astype(str))

print(f"    Unique cabinets: {node_df.cabinet.nunique()}")
print(f"    Unique chassis:  {node_df.chassis_str.nunique()}")
print(f"    Unique slots:    {node_df.slot_str.nunique()}")

# ─────────────────────────────────────────────────────────────────────
# M1.1  Hierarchy topology summary
# ─────────────────────────────────────────────────────────────────────
topo = {
    "n_nodes": int(len(node_df)),
    "n_cabinets": int(node_df.cabinet.nunique()),
    "n_chassis_unique": int(node_df.chassis_str.nunique()),
    "n_slots_unique": int(node_df.slot_str.nunique()),
    "nodes_per_cabinet_median": float(node_df.groupby("cab_str").size().median()),
    "nodes_per_cabinet_min":    int(node_df.groupby("cab_str").size().min()),
    "nodes_per_cabinet_max":    int(node_df.groupby("cab_str").size().max()),
}
print(f"\n[1.1] Topology: {topo['n_cabinets']} cabinets, "
      f"{topo['n_chassis_unique']} chassis, {topo['n_slots_unique']} slots")

# ─────────────────────────────────────────────────────────────────────
# M1.2  Variance decomposition of FA_2024 by location level
# ─────────────────────────────────────────────────────────────────────
print("\n[1.2] Variance decomposition ...")

F = node_df["FA_2024"].values
Y = node_df["Y_2025"].values
n = len(F)

def group_mean_loo(df, group_col, val_col):
    """Leave-one-out group mean: mean of others in the same group."""
    df = df.copy()
    g_sum   = df.groupby(group_col)[val_col].transform("sum")
    g_count = df.groupby(group_col)[val_col].transform("count")
    return (g_sum - df[val_col]) / (g_count - 1)

def explained_var_frac(y, group_col, df):
    """Fraction of total variance of y explained by group means."""
    group_means = df.groupby(group_col)["FA_2024"].transform("mean").values
    sst = ((y - y.mean()) ** 2).sum()
    sse = ((y - group_means) ** 2).sum()
    return 1 - sse / sst

levels = ["cab_str", "chassis_str", "slot_str", "board_str"]
level_labels = ["cabinet", "cabinet:chassis", "cabinet:chassis:slot",
                "cabinet:chassis:slot:board"]
var_decomp = {}
for lev, lab in zip(levels, level_labels):
    r2_lev = explained_var_frac(F, lev, node_df)
    var_decomp[lab] = float(r2_lev)
    print(f"    FA_2024 variance explained by {lab}: {r2_lev:.4f}")

total_loc_r2 = var_decomp["cabinet:chassis:slot:board"]
node_residual_frac = 1.0 - total_loc_r2
print(f"    Residual (node-specific) fraction: {node_residual_frac:.4f}")
print(f"    NOTE: board-level R2=1.0 is a topology artifact. In Frontier's xname")
print(f"    hierarchy, (cabinet,chassis,slot,board) uniquely identifies each cohort")
print(f"    node, so 'board-level residual'=0 by construction. The meaningful test")
print(f"    for node-specific signal is prediction-based (M1.3).")

# Bootstrap CI on residual fraction (cluster by cabinet)
rng = np.random.default_rng(PERM_SEED)
cab_ids = node_df["cab_str"].values
unique_cabs = np.unique(cab_ids)
boot_resid = []
for _ in range(1000):
    boot_cabs = rng.choice(unique_cabs, size=len(unique_cabs), replace=True)
    idx = np.concatenate([np.where(cab_ids == c)[0] for c in boot_cabs])
    sub = node_df.iloc[idx].reset_index(drop=True)
    r2b = explained_var_frac(sub["FA_2024"].values, "board_str", sub)
    boot_resid.append(1.0 - r2b)
boot_resid = np.array(boot_resid)
resid_ci = (float(np.percentile(boot_resid, 2.5)),
            float(np.percentile(boot_resid, 97.5)))
print(f"    Bootstrap 95% CI on node-residual fraction: [{resid_ci[0]:.4f}, {resid_ci[1]:.4f}]")

# ─────────────────────────────────────────────────────────────────────
# M1.3  Location-only LOO prediction of Y_2025 — FROZEN / no-refit R2
# ─────────────────────────────────────────────────────────────────────
print("\n[1.3] Location-only LOO prediction of Y_2025 ...")
print("    All R2 values are frozen (predictor built from 2024 FA only;")
print("    no slope or intercept fitted to 2025 Y data).")

# Within-cabinet LOO means
node_df["FA_loo_cab"]     = group_mean_loo(node_df, "cab_str",     "FA_2024")
node_df["FA_loo_chassis"] = group_mean_loo(node_df, "chassis_str", "FA_2024")
node_df["FA_loo_slot"]    = group_mean_loo(node_df, "slot_str",    "FA_2024")

# Combined location: chassis LOO (finest available); fall back to cabinet LOO
# where chassis group size = 1
node_df["chassis_count"] = node_df.groupby("chassis_str")["hostname"].transform("count")
node_df["FA_loo_combined"] = np.where(
    node_df["chassis_count"] > 1,
    node_df["FA_loo_chassis"],
    node_df["FA_loo_cab"]
)

# Repeated-position: LOO mean by (chassis, slot, board, node_pos) WITHOUT cabinet.
# Tests whether the thermal pattern repeats at the same physical position across
# all ~77 cabinets. Group size median is ~3-5 nodes per position.
node_df["FA_loo_pos"] = group_mean_loo(node_df, "pos_key", "FA_2024")
pos_sizes = node_df.groupby("pos_key").size()
n_pos_singleton = int((pos_sizes == 1).sum())
print(f"    Repeated-position groups: {node_df.pos_key.nunique()} unique, "
      f"size median={pos_sizes.median():.1f}, "
      f"singletons={n_pos_singleton} (LOO=NaN for singletons)")

predictors = {
    "A_cabinet_loo":       "FA_loo_cab",
    "B_chassis_loo":       "FA_loo_chassis",
    "C_slot_loo":          "FA_loo_slot",
    "D_combined_loc":      "FA_loo_combined",
    "E_repeated_position": "FA_loo_pos",
    "F_individual_F":      "FA_2024",
}

loc_results = {}
Y_s = pd.Series(Y, index=node_df.index)
for name, col in predictors.items():
    yhat = node_df[col].values
    valid = ~np.isnan(yhat)
    if valid.sum() < 50:
        print(f"    {name:26s}: SKIPPED (n={valid.sum()} valid)")
        continue
    r  = pearson_r(Y[valid], yhat[valid])
    sp = spearman_r(Y[valid], yhat[valid])
    r2 = frozen_r2(Y_s[valid].values, yhat[valid])
    m  = mae(Y[valid], yhat[valid])
    rm = rmse(Y[valid], yhat[valid])
    loc_results[name] = dict(n=int(valid.sum()), pearson_r=r, spearman_r=sp,
                              r2_frozen=r2, mae=m, rmse=rm)
    print(f"    {name:26s}: r={r:.4f}  sp={sp:.4f}  R2_frozen={r2:.4f}  MAE={m:.4f}")

# Frozen incremental R2 of F after location
r2_frozen_loc  = loc_results["D_combined_loc"]["r2_frozen"]
r2_frozen_pos  = loc_results.get("E_repeated_position", {}).get("r2_frozen", float("nan"))
r2_frozen_F    = loc_results["F_individual_F"]["r2_frozen"]
delta_r2_frozen = r2_frozen_F - r2_frozen_loc

print(f"\n    [Frozen / no-refit R2 summary]")
print(f"    Location-only (combined LOO):    {r2_frozen_loc:.4f}")
print(f"    Repeated-position (cross-cab):   {r2_frozen_pos:.4f}")
print(f"    Individual F_2024:               {r2_frozen_F:.4f}")
print(f"    Incremental R2 from F:           {delta_r2_frozen:.4f}")

# Calibrated OLS — reference only, clearly labeled
# (slope+intercept fitted to 2025 Y data — NOT the primary comparison)
from numpy.linalg import lstsq
X_loc  = node_df["FA_loo_combined"].values.reshape(-1, 1)
X_both = np.column_stack([node_df["FA_loo_combined"].values, node_df["FA_2024"].values])
valid  = ~np.isnan(X_loc[:, 0])
Y_v    = Y[valid]

coef_loc, _, _, _ = lstsq(np.column_stack([np.ones(valid.sum()), X_loc[valid]]), Y_v, rcond=None)
y_hat_loc_cal = np.column_stack([np.ones(valid.sum()), X_loc[valid]]) @ coef_loc
r2_loc_calib = float(1 - ((Y_v - y_hat_loc_cal)**2).sum() / ((Y_v - Y_v.mean())**2).sum())

coef_both, _, _, _ = lstsq(np.column_stack([np.ones(valid.sum()), X_both[valid]]), Y_v, rcond=None)
y_hat_both_cal = np.column_stack([np.ones(valid.sum()), X_both[valid]]) @ coef_both
r2_both_calib = float(1 - ((Y_v - y_hat_both_cal)**2).sum() / ((Y_v - Y_v.mean())**2).sum())

print(f"\n    [Calibrated OLS R2 — slope+intercept fitted to 2025, reference only]")
print(f"    Location-only OLS R2:  {r2_loc_calib:.4f}")
print(f"    Location + F OLS R2:   {r2_both_calib:.4f}")

# ─────────────────────────────────────────────────────────────────────
# M1.4  Permutation null (2,000 draws x 3 shuffle strategies)
# ─────────────────────────────────────────────────────────────────────
print(f"\n[1.4] Permutation null ({N_PERM} draws each) ...")
p_threshold_str = f"p < 1/{N_PERM+1} ≈ {1/(N_PERM+1):.4f}"
rng2 = np.random.default_rng(PERM_SEED + 1)
F_vals = node_df["FA_2024"].values.copy()
Y_vals = Y.copy()
cab_arr = node_df["cab_str"].values
cha_arr = node_df["chassis_str"].values

observed_r = pearson_r(F_vals, Y_vals)
print(f"    Observed Pearson r(F,Y): {observed_r:.4f}")

null_results = {}
for null_name, strat in [
        ("A_global",        "global"),
        ("B_within_cabinet","cabinet"),
        ("C_within_chassis","chassis"),
]:
    null_rs = []
    for _ in range(N_PERM):
        F_perm = F_vals.copy()
        if strat == "global":
            rng2.shuffle(F_perm)
        elif strat == "cabinet":
            for cab in np.unique(cab_arr):
                idx = np.where(cab_arr == cab)[0]
                F_perm[idx] = rng2.permutation(F_perm[idx])
        elif strat == "chassis":
            for cha in np.unique(cha_arr):
                idx = np.where(cha_arr == cha)[0]
                F_perm[idx] = rng2.permutation(F_perm[idx])
        null_rs.append(pearson_r(F_perm, Y_vals))
    null_rs = np.array(null_rs)
    p_emp = float((null_rs >= observed_r).mean())
    # p=0 means no permutation exceeded observed; report as upper bound
    p_str = (p_threshold_str if p_emp == 0.0
             else f"p = {p_emp:.4f}")
    null_results[null_name] = {
        "strategy": strat,
        "n_perm": N_PERM,
        "observed_r": float(observed_r),
        "null_mean": float(null_rs.mean()),
        "null_p95":  float(np.percentile(null_rs, 95)),
        "null_p99":  float(np.percentile(null_rs, 99)),
        "empirical_p": p_emp,
        "p_display": p_str,
    }
    print(f"    {null_name}: null_mean={null_rs.mean():.4f}, "
          f"p95={np.percentile(null_rs,95):.4f}, {p_str}")

# ─────────────────────────────────────────────────────────────────────
# M1.5  Full-channel restriction note (Phase 0C showed >99% all-8-GCD)
# ─────────────────────────────────────────────────────────────────────
m15_note = (
    "Phase 0C GCD census (500 train sample + 2637 test jobs) found >99% of "
    "node-job observations have all 8 GCD channels present with >=5 valid "
    "timestamps. Restricting the fingerprint to jobs where all 8 GCD channels "
    "are valid would exclude <1% of training observations and produce an "
    "FA_restricted that is indistinguishable from the unrestricted FA_2024. "
    "A separate restricted-channel fingerprint is therefore not informative."
)
print(f"\n[1.5] {m15_note[:90]}...")

# ─────────────────────────────────────────────────────────────────────
# M1.6  Power-adjusted fingerprint F^P
# For each qualifying 2024 training job j:
#   T_ij = a_j + b_j * P_ij + e_ij   (OLS fit across fp nodes in job j)
#   F^P_i = mean_j(e_ij)              (frozen on 2024, tested on Y_2025)
# ─────────────────────────────────────────────────────────────────────
print("\n[1.6] Power-adjusted fingerprint F^P ...")

if FP_CACHE.exists():
    print(f"    Loading cached F^P from {FP_CACHE}")
    fp_pa = pd.read_parquet(FP_CACHE)
    n_fp_jobs_used = int(fp_pa["n_jobs"].max()) if "n_jobs" in fp_pa.columns else -1
else:
    print(f"    Computing F^P from training telemetry (sample up to {FP_SAMPLE_N} jobs)...")

    # Get training job list (pre-2025 from globus_batch.txt)
    with open(PHASE1_DIR / "globus_batch.txt") as _bf:
        _blines = [l.strip() for l in _bf if l.strip()]
    _bpat = re.compile(r"(\d{4}-\d{2}-\d{2})/(\d{6})")
    train_job_list = []
    for _bl in _blines:
        _bm = _bpat.search(_bl)
        if _bm and _bm.group(1) < "2025":
            train_job_list.append({"date_dir": _bm.group(1), "job_idx": int(_bm.group(2))})
    train_job_df = pd.DataFrame(train_job_list).drop_duplicates("job_idx")

    if FP_SAMPLE_N and len(train_job_df) > FP_SAMPLE_N:
        train_job_df = train_job_df.sample(n=FP_SAMPLE_N, random_state=42)
    print(f"    Training jobs to process: {len(train_job_df)}")

    resid_acc: dict[str, list] = {}
    jobs_used = 0

    for ki, (_, tj) in enumerate(train_job_df.iterrows()):
        if ki % 50 == 0:
            print(f"    ... {ki}/{len(train_job_df)} jobs (qualifying: {jobs_used})", end="\r")

        jid   = str(int(tj["job_idx"])).zfill(6)
        ddir  = tj["date_dir"]
        tpath = TELE_DIR / ddir / jid / f"{jid}-cleaned-temperature.parquet"
        ppath = TELE_DIR / ddir / jid / f"{jid}-cleaned-power.parquet"

        if not tpath.exists() or not ppath.exists():
            continue
        try:
            tmp = pd.read_parquet(tpath)
            pwr = pd.read_parquet(ppath)
        except Exception:
            continue

        # Map fp nodes -> their GCD temperature columns
        node_gcd_map: dict[str, list] = {}
        for c in tmp.columns:
            if c.startswith("frontier") and "_gcd" in c and "ncount" not in c:
                node = c.split("_")[0]
                if node in fp_hostname_set:
                    node_gcd_map.setdefault(node, []).append(c)

        # Map fp nodes -> their node-level power column
        node_pwr_map: dict[str, str] = {}
        for c in pwr.columns:
            if c.startswith("frontier") and c.endswith("_node"):
                node = c[:-5]
                if node in fp_hostname_set:
                    node_pwr_map[node] = c

        shared_nodes = [nd for nd in node_gcd_map if nd in node_pwr_map]
        if len(shared_nodes) < FP_MIN_NODES:
            continue

        T_list, P_list, node_list = [], [], []
        for node in shared_nodes:
            gcols = node_gcd_map[node]
            pcol  = node_pwr_map[node]
            t_ts  = np.nanmean(tmp[gcols].values.astype(float), axis=1)
            finite_t = t_ts[np.isfinite(t_ts)]
            if len(finite_t) < 5:
                continue
            t_p95 = float(np.percentile(finite_t, 95))
            p_ts  = pwr[pcol].values.astype(float)
            finite_p = p_ts[np.isfinite(p_ts)]
            if len(finite_p) < 5:
                continue
            p_mean = float(np.nanmean(finite_p))
            T_list.append(t_p95)
            P_list.append(p_mean)
            node_list.append(node)

        if len(node_list) < FP_MIN_NODES:
            continue

        T_arr = np.array(T_list)
        P_arr = np.array(P_list)
        X_job = np.column_stack([np.ones(len(T_arr)), P_arr])
        try:
            coefs, _, _, _ = lstsq(X_job, T_arr, rcond=None)
        except Exception:
            continue

        resids = T_arr - X_job @ coefs
        for node, r in zip(node_list, resids):
            resid_acc.setdefault(node, []).append(float(r))
        jobs_used += 1

    print(f"\n    Done: {jobs_used} qualifying jobs used")

    fp_rows = []
    for node, resids in resid_acc.items():
        if len(resids) >= FP_MIN_JOBS_NODE:
            fp_rows.append({
                "hostname":    node,
                "F_power":     float(np.mean(resids)),
                "n_jobs":      len(resids),
                "F_power_std": float(np.std(resids)),
            })
    fp_pa = pd.DataFrame(fp_rows)
    n_fp_jobs_used = jobs_used
    print(f"    F^P computed for {len(fp_pa)} of {len(fp_hostname_set)} fp nodes "
          f"(min {FP_MIN_JOBS_NODE} jobs each)")
    fp_pa.to_parquet(FP_CACHE, index=False)
    print(f"    Saved cache: {FP_CACHE}")

# Test F^P on Y_2025
fp_power_map = fp_pa.set_index("hostname")["F_power"].to_dict()
node_df["F_power"] = node_df["hostname"].map(fp_power_map)
fp_valid = node_df["F_power"].notna() & node_df["Y_2025"].notna() & node_df["FA_2024"].notna()

if fp_valid.sum() >= 100:
    F_p  = node_df.loc[fp_valid, "F_power"].values
    Y_p  = node_df.loc[fp_valid, "Y_2025"].values
    FA_p = node_df.loc[fp_valid, "FA_2024"].values

    r_fp    = pearson_r(F_p,  Y_p)
    r2_fp   = frozen_r2(Y_p,  F_p)
    mae_fp  = mae(Y_p,  F_p)
    rmse_fp = rmse(Y_p, F_p)
    r_fa    = pearson_r(FA_p, Y_p)
    r2_fa   = frozen_r2(Y_p,  FA_p)
    r_fa_fp = pearson_r(FA_p, F_p)

    print(f"    F^P vs Y_2025 (n={fp_valid.sum()} nodes):")
    print(f"      r(F^P, Y):  {r_fp:.4f}   R2_frozen={r2_fp:.4f}   MAE={mae_fp:.4f}")
    print(f"      r(FA,  Y):  {r_fa:.4f}   R2_frozen={r2_fa:.4f}   (same nodes)")
    print(f"      r(FA, F^P): {r_fa_fp:.4f}   (correlation between fingerprints)")

    m16 = {
        "n_nodes": int(fp_valid.sum()),
        "n_training_jobs_used": n_fp_jobs_used,
        "training_sample_size": FP_SAMPLE_N,
        "min_jobs_per_node": FP_MIN_JOBS_NODE,
        "F_power_vs_Y2025": {
            "pearson_r": float(r_fp),
            "r2_frozen": float(r2_fp),
            "mae":       float(mae_fp),
            "rmse":      float(rmse_fp),
        },
        "FA_2024_vs_Y2025_same_nodes": {
            "pearson_r": float(r_fa),
            "r2_frozen": float(r2_fa),
        },
        "r_FA_vs_FP": float(r_fa_fp),
        "note": (
            "F^P_i = mean_j(e_ij) where e_ij = T_p95_ij - (a_j + b_j*P_ij), "
            "OLS fit per 2024 training job j across fingerprinted nodes. "
            "T_p95=p95 of mean(GCD temperature channels) per node-job; "
            "P=mean(node-level power) per node-job. "
            "Frozen on 2024 training jobs, tested prospectively on 2025 Y_2025."
        ),
    }
    # Also test even/odd split-half on FA for reference
    if "FA_even" in node_df.columns and "FA_odd" in node_df.columns:
        r_even_odd = pearson_r(node_df["FA_even"].dropna().values,
                               node_df["FA_odd"].dropna().values)
        sb = 2 * r_even_odd / (1 + r_even_odd)
        m16["fa_split_half_r_even_odd"] = float(r_even_odd)
        m16["fa_spearman_brown_full_year"] = float(sb)
        print(f"      FA even/odd split-half r: {r_even_odd:.4f}  SB: {sb:.4f}")
else:
    print(f"    WARNING: only {fp_valid.sum()} nodes with F^P data.")
    m16 = {"status": "insufficient_data", "n_valid": int(fp_valid.sum())}

# ─────────────────────────────────────────────────────────────────────
# M1.8  Allocation-list-position analysis
# Slurm allocates nodes in xname lexicographic order. A node's typical
# ordinal rank in that list (its "allocation-list position") could
# correlate with thermal fingerprint if, e.g., rank-0 nodes are I/O
# aggregators and run hotter. The dataset records host_list order but
# does NOT expose MPI task rank, I/O aggregator role, or communication
# topology metadata — so we can test position correlation but cannot
# attribute it to specific roles.
# ─────────────────────────────────────────────────────────────────────
print("\n[1.8] Allocation-list-position analysis ...")
print("    NOTE: host_list gives Slurm allocation order, not MPI rank.")
print("    The dataset does not expose MPI task rank, I/O aggregator role,")
print("    or communication topology metadata.")

all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")

with open(PHASE1_DIR / "globus_batch.txt") as _f:
    _lines = [l.strip() for l in _f if l.strip()]
_date_re = re.compile(r"(\d{4}-\d{2}-\d{2})/(\d{6})")
train_job_ids = set()
for line in _lines:
    m = _date_re.search(line)
    if m and m.group(1) < "2025":
        train_job_ids.add(int(m.group(2)))

print(f"    Training job IDs: {len(train_job_ids)}")

pos_acc: dict[str, list] = {}
first_acc: dict[str, int] = {}
count_acc: dict[str, int] = {}

train_jobs_df = all_jobs[all_jobs["job_idx"].str.lstrip("0").apply(
    lambda x: int(x) if x else 0).isin(train_job_ids)].copy()
print(f"    Training jobs found in metadata: {len(train_jobs_df)}")

for hl in train_jobs_df["host_list"].values:
    n_hl = len(hl)
    if n_hl < 2:
        continue
    for pos, hn in enumerate(hl):
        hn = str(hn)
        if hn not in fp_hostname_set:
            continue
        q = pos / (n_hl - 1)
        pos_acc.setdefault(hn, []).append(q)
        count_acc[hn] = count_acc.get(hn, 0) + 1
        if pos == 0:
            first_acc[hn] = first_acc.get(hn, 0) + 1

print(f"    fp nodes with position data: {len(pos_acc)}")

alloc_rows = []
for hn in sorted(fp_hostname_set):
    if hn not in pos_acc:
        continue
    ps = np.array(pos_acc[hn])
    n_appear = count_acc.get(hn, 0)
    n_first  = first_acc.get(hn, 0)
    alloc_rows.append(dict(
        hostname=hn,
        mean_norm_pos=float(ps.mean()),
        median_norm_pos=float(np.median(ps)),
        frac_first=float(n_first / n_appear) if n_appear else np.nan,
        frac_top10pct=float((ps <= 0.10).mean()),
        frac_bot10pct=float((ps >= 0.90).mean()),
        n_train_jobs=n_appear,
    ))

alloc_df = pd.DataFrame(alloc_rows)
alloc_df = alloc_df.merge(
    fp_reset[["hostname","FA_2024"]], on="hostname", how="inner"
).merge(
    y2025[["hostname","Y_2025"]], on="hostname", how="inner"
)
print(f"    Nodes with full data: {len(alloc_df)}")

def safe_r(a, b):
    v = np.isfinite(a) & np.isfinite(b)
    if v.sum() < 10:
        return float("nan")
    return float(np.corrcoef(a[v], b[v])[0, 1])

r_pos_F  = safe_r(alloc_df.mean_norm_pos.values, alloc_df.FA_2024.values)
r_pos_Y  = safe_r(alloc_df.mean_norm_pos.values, alloc_df.Y_2025.values)
r_first_F = safe_r(alloc_df.frac_first.values, alloc_df.FA_2024.values)
r_first_Y = safe_r(alloc_df.frac_first.values, alloc_df.Y_2025.values)

print(f"    r(mean_norm_pos, F):       {r_pos_F:.4f}")
print(f"    r(mean_norm_pos, Y_2025):  {r_pos_Y:.4f}")
print(f"    r(frac_first, F):          {r_first_F:.4f}")
print(f"    r(frac_first, Y_2025):     {r_first_Y:.4f}")

valid = (alloc_df[["mean_norm_pos","FA_2024","Y_2025"]].notna().all(axis=1)).values
Yp = alloc_df.loc[valid, "Y_2025"].values
Fp = alloc_df.loc[valid, "FA_2024"].values
Pp = alloc_df.loc[valid, "mean_norm_pos"].values
loc_pred = node_df.set_index("hostname").loc[
    alloc_df.loc[valid, "hostname"], "FA_loo_combined"].values

def ols_r2(X, y):
    Xd = np.column_stack([np.ones(len(y)), X])
    beta, _, _, _ = lstsq(Xd, y, rcond=None)
    yhat = Xd @ beta
    sst = ((y - y.mean())**2).sum()
    sse = ((y - yhat)**2).sum()
    return 1 - sse/sst

alloc_valid2 = np.isfinite(loc_pred) & np.isfinite(Yp) & np.isfinite(Fp) & np.isfinite(Pp)
Yp2, Fp2, Pp2, Lp2 = Yp[alloc_valid2], Fp[alloc_valid2], Pp[alloc_valid2], loc_pred[alloc_valid2]

r2_loc_only_alloc  = ols_r2(np.column_stack([Lp2]), Yp2)
r2_loc_alloc       = ols_r2(np.column_stack([Lp2, Pp2]), Yp2)
r2_loc_alloc_F     = ols_r2(np.column_stack([Lp2, Pp2, Fp2]), Yp2)

print(f"\n    R2 (Y ~ location):                  {r2_loc_only_alloc:.4f}")
print(f"    R2 (Y ~ location + alloc_pos):      {r2_loc_alloc:.4f}")
print(f"    R2 (Y ~ location + alloc_pos + F):  {r2_loc_alloc_F:.4f}")
print(f"    Incremental R2 of F after both:     {r2_loc_alloc_F - r2_loc_alloc:.4f}")

m18 = {
    "section": "allocation-list-position analysis",
    "note": (
        "Tests whether a node's typical ordinal position in the Slurm allocation "
        "list (host_list order) correlates with its thermal fingerprint. "
        "The dataset records allocation-list order but does NOT expose MPI task rank, "
        "I/O aggregator role, or communication topology metadata."
    ),
    "n_nodes": int(len(alloc_df)),
    "n_training_jobs_used": len(train_job_ids),
    "correlations": {
        "r_mean_norm_pos_vs_F":      float(r_pos_F),
        "r_mean_norm_pos_vs_Y2025":  float(r_pos_Y),
        "r_frac_first_vs_F":         float(r_first_F),
        "r_frac_first_vs_Y2025":     float(r_first_Y),
    },
    "incremental_analysis": {
        "note": "OLS calibrated to Y_2025; reported for reference",
        "r2_location_only":            float(r2_loc_only_alloc),
        "r2_location_plus_alloc_pos":  float(r2_loc_alloc),
        "r2_loc_alloc_pos_plus_F":     float(r2_loc_alloc_F),
        "incremental_R2_F_after_both": float(r2_loc_alloc_F - r2_loc_alloc),
    },
}

# ─────────────────────────────────────────────────────────────────────
# M1.7  Hardware-move experiment: not feasible
# ─────────────────────────────────────────────────────────────────────
m17_note = (
    "Phase 0.1 showed hostname <-> xname mapping is perfectly 1:1 across "
    "all 152,400 jobs (0 hostnames with >1 xname, 0 xnames with >1 hostname). "
    "No hardware relocations are detectable in this dataset. "
    "The thermal fingerprint cannot be attributed to hardware vs permanent slot: "
    "both explanations are observationally equivalent. "
    "This analysis is NOT FEASIBLE with available data."
)
print(f"\n[1.7] Hardware-move experiment: NOT FEASIBLE")
print(f"    {m17_note[:90]}...")

# ─────────────────────────────────────────────────────────────────────
# Classify M1 verdict
# ─────────────────────────────────────────────────────────────────────
print("\n--- M1 VERDICT ---")
perm_p_within_chassis = null_results["C_within_chassis"]["empirical_p"]
r_indiv = loc_results["F_individual_F"]["pearson_r"]
r_loc   = loc_results["D_combined_loc"]["pearson_r"]

print(f"    Frozen R2 — location-only (combined LOO):  {r2_frozen_loc:.4f}")
print(f"    Frozen R2 — repeated-position (cross-cab): {r2_frozen_pos:.4f}")
print(f"    Frozen R2 — individual F_2024:             {r2_frozen_F:.4f}")
print(f"    Incremental frozen R2 from F:              {delta_r2_frozen:.4f}")
print(f"    Within-chassis permutation:                {null_results['C_within_chassis']['p_display']}")
print(f"    Individual F Pearson r(Y_2025):            {r_indiv:.4f}")
print(f"    Combined-location Pearson r(Y_2025):       {r_loc:.4f}")
print(f"    NOTE: board-level variance decomp R2=1.0 is topology artifact; see M1.2.")

if delta_r2_frozen > 0.50 and perm_p_within_chassis < 0.01 and r_indiv > 0.80:
    m1_verdict = "RESOLVED IN FAVOUR OF NODE-SPECIFIC SIGNAL"
    m1_verdict_note = (
        "Location group means (cabinet/chassis LOO) predict Y_2025 with "
        f"frozen R2={r2_frozen_loc:.3f}. Repeated-position model (cross-cabinet) "
        f"predicts with frozen R2={r2_frozen_pos:.3f}. "
        f"Individual F_2024 predicts Y_2025 with frozen R2={r2_frozen_F:.3f}. "
        f"Incremental frozen R2 from F beyond location = {delta_r2_frozen:.3f}. "
        f"Within-chassis permutation {null_results['C_within_chassis']['p_display']}. "
        "These results support a persistent node-slot thermal fingerprint that is not "
        "reducible to cabinet or chassis location effects. "
        "Whether the fingerprint follows the physical hardware or the permanent rack slot "
        "cannot be resolved because hostname and xname are in 1:1 correspondence throughout."
    )
elif delta_r2_frozen > 0.20 and perm_p_within_chassis < 0.05:
    m1_verdict = "PARTIALLY RESOLVED"
    m1_verdict_note = "Incremental frozen R2 moderate; permutation significant."
elif r_loc > 0.80:
    m1_verdict = "LOCATION DOMINATES"
    m1_verdict_note = "Location LOO predictor nearly as good as individual F."
else:
    m1_verdict = "AMBIGUOUS — review figures"
    m1_verdict_note = ""
print(f"\n    Classification: {m1_verdict}")

# ─────────────────────────────────────────────────────────────────────
# Figures
# ─────────────────────────────────────────────────────────────────────
print("\n[F] Generating figures ...")

# Fig 1: Variance decomposition bar chart
fig, ax = plt.subplots(figsize=(8, 4))
labels = list(var_decomp.keys()) + ["node-specific residual"]
vals   = list(var_decomp.values()) + [node_residual_frac]
increments = [vals[0]] + [vals[i] - vals[i-1] for i in range(1, len(vals)-1)] + [vals[-1]]
ax.bar(range(len(increments)), increments,
       color=["#3a7eca","#3a7eca","#3a7eca","#3a7eca","#e05c1a"])
ax.set_xticks(range(len(labels)))
ax.set_xticklabels(["Cabinet", "Chassis", "Slot", "Board", "Node residual"],
                   rotation=25, ha="right")
ax.set_ylabel("Incremental fraction of FA variance")
ax.set_title("M1: Variance of FA_2024 attributed to hierarchy level\n"
             "(board R2=1.0 is a topology artifact — see text)")
ax.axhline(0, color="black", lw=0.5)
plt.tight_layout()
plt.savefig(FIG_DIR / "fig_m1_variance_decomposition.png", dpi=150)
plt.close()

# Fig 2: Location vs identity prediction scatter
fig, axes = plt.subplots(1, 2, figsize=(10, 4))
ax = axes[0]
ax.scatter(node_df["FA_loo_combined"], Y, alpha=0.3, s=10, color="#3a7eca")
ax.set_xlabel("Location-only predictor (chassis LOO mean FA)")
ax.set_ylabel("Y_2025 (median delta_T_p95)")
r_loc_lab = loc_results["D_combined_loc"]["pearson_r"]
ax.set_title(f"Location-only: r={r_loc_lab:.3f}  R2_frozen={r2_frozen_loc:.3f}")
ax = axes[1]
ax.scatter(node_df["FA_2024"], Y, alpha=0.3, s=10, color="#e05c1a")
ax.set_xlabel("Individual FA_2024")
ax.set_ylabel("Y_2025 (median delta_T_p95)")
ax.set_title(f"Individual FA_2024: r={r_indiv:.3f}  R2_frozen={r2_frozen_F:.3f}")
plt.tight_layout()
plt.savefig(FIG_DIR / "fig_m1_location_vs_identity_prediction.png", dpi=150)
plt.close()

# Fig 3: Spatial permutation null distributions (summary bars only)
fig, axes = plt.subplots(1, 3, figsize=(12, 4))
for i, (null_name, res) in enumerate(null_results.items()):
    ax = axes[i]
    ax.set_title(f"Null {null_name[:1]}: {res['strategy']}")
    ax.axvline(res["observed_r"], color="red", lw=2,
               label=f"Observed r={res['observed_r']:.3f}")
    ax.axvline(res["null_p99"], color="gray", lw=1, ls="--",
               label=f"p99={res['null_p99']:.3f}")
    ax.set_xlabel("Permuted Pearson r")
    ax.set_title(ax.get_title() + f"\n{res['p_display']}")
    ax.legend(fontsize=8)
plt.suptitle("M1: Spatial permutation null distributions")
plt.tight_layout()
plt.savefig(FIG_DIR / "fig_m1_spatial_permutation_null.png", dpi=150)
plt.close()

print("    Figures saved.")

# ─────────────────────────────────────────────────────────────────────
# Assemble JSON output
# ─────────────────────────────────────────────────────────────────────
result = {
    "script":    "r1_m1_location_identity.py",
    "git_sha":   git_sha(),
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "input_files": {
        "phase3a_fingerprint_2024.parquet": file_sha256(ANAL_DIR / "phase3a_fingerprint_2024.parquet"),
        "phase3a_test_set.parquet":         file_sha256(ANAL_DIR / "phase3a_test_set.parquet"),
        "fp_node_topology.csv":             file_sha256(TABLE_DIR / "fp_node_topology.csv"),
    },
    "random_seed":    PERM_SEED,
    "n_permutations": N_PERM,

    "m1_1_topology": topo,

    "m1_2_variance_decomposition": {
        "target": "FA_2024",
        "method": "OLS R2 with nested location group means",
        "cumulative_R2_by_level": var_decomp,
        "node_specific_residual_fraction": float(node_residual_frac),
        "bootstrap_95ci_residual": {"lo": resid_ci[0], "hi": resid_ci[1]},
        "bootstrap_n": 1000,
        "bootstrap_cluster": "cabinet",
        "topology_artifact_note": (
            "board_level_R2=1.0 because (cabinet,chassis,slot,board) uniquely "
            "identifies each fp analysis node in Frontier's xname hierarchy. "
            "The 'node-specific residual' fraction is 0 by construction. "
            "This does NOT mean location explains the thermal signal — it means "
            "the finest location descriptor IS the node identifier. "
            "Primary evidence for node-specific signal comes from M1.3 prediction R2."
        ),
    },

    "m1_3_location_prediction": {
        "target": "Y_2025 (node-level median delta_T_p95 across 2025 test jobs)",
        "note_frozen_r2": (
            "All R2 values are frozen/no-refit: the predictor is built from 2024 FA "
            "LOO means only; no slope or intercept is fitted to 2025 Y data. "
            "Calibrated OLS values (slope+intercept fitted to 2025) are provided "
            "separately for reference."
        ),
        "predictors_frozen": loc_results,
        "frozen_incremental": {
            "r2_frozen_location_combined": jf(r2_frozen_loc),
            "r2_frozen_repeated_position": jf(r2_frozen_pos),
            "r2_frozen_individual_F":      jf(r2_frozen_F),
            "delta_r2_F_minus_location":   jf(delta_r2_frozen),
        },
        "calibrated_ols_reference": {
            "note": "slope+intercept fitted to 2025 Y — NOT the primary comparison",
            "location_only_ols_R2":    float(r2_loc_calib),
            "location_plus_F_ols_R2":  float(r2_both_calib),
        },
        "pos_key_stats": {
            "n_unique_positions": int(node_df.pos_key.nunique()),
            "median_group_size":  float(pos_sizes.median()),
            "n_singleton_groups": int(n_pos_singleton),
        },
    },

    "m1_4_permutation_null": null_results,

    "m1_5_full_channel_restriction": {
        "status": "NOT RUN — not informative",
        "reason": m15_note,
    },

    "m1_6_power_adjusted_fingerprint": m16,

    "m1_7_hardware_move": {
        "status": "NOT FEASIBLE",
        "reason": m17_note,
    },

    "m1_8_allocation_list_position": m18,

    "m1_verdict": {
        "classification": m1_verdict,
        "note": m1_verdict_note,
        "key_stats": {
            "r2_frozen_location_only":       jf(r2_frozen_loc),
            "r2_frozen_repeated_position":   jf(r2_frozen_pos),
            "r2_frozen_individual_F":        jf(r2_frozen_F),
            "incremental_frozen_R2_from_F":  jf(delta_r2_frozen),
            "within_chassis_permutation":    null_results["C_within_chassis"]["p_display"],
            "individual_F_pearson_r":        float(r_indiv),
            "combined_location_pearson_r":   float(r_loc),
            "topology_artifact_note": (
                "board_level_variance_decomp_R2=1.0 is structural (each fp node is "
                "uniquely identified at the board level in Frontier's xname hierarchy). "
                "Primary evidence for node-specific signal is prediction-based (M1.3)."
            ),
        },
    },

    "elapsed_seconds": round(time.time() - t0, 1),
}

out_path = OUT_DIR / "m1_location_identity.json"
with open(out_path, "w") as f:
    json.dump(result, f, indent=2)

print(f"\nSaved: {out_path}")
print(f"Total elapsed: {time.time()-t0:.1f}s")
