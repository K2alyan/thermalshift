#!/usr/bin/env python3
"""Phase B: LOO cross-fitted beta + jackknife + quarter-wise sensitivity.

Plan ref: REVIEW2_CHALLENGE_PLAN.md §B1-B3 (amendment 6b45030).

BETA_F_FROZEN = 1.12484352 = median of per-job slopes across 462 qualifying
training jobs (m3_train_betas.parquet).  The LOO cross-fit operates on the
same 462 jobs and their fp-node observations.

For each qualifying training observation (node i, job j):
  F_CF[i,j] = (FA_2024[i] * n_i - T_dev[i,j]) / (n_i - 1)
Fit ONE model:
  T_dev[i,j] = alpha_j + beta_CF * F_CF[i,j]   (within-job FE, demeaned form)
Bootstrap 95% CI by job-cluster resampling (5000 replicates).

Fast jackknife uses job-level aggregates:
  c_xy[j] = sum(F_CF_dm * T_dev_dm) for obs in job j
  beta = sum(c_xy) / sum(c_xx)
  beta_{-j} = (sum_c_xy - c_xy[j]) / (sum_c_xx - c_xx[j])
"""
import sys, io, json, numpy as np, pandas as pd
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import pyarrow.parquet as pq

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

DATA_DIR   = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset/job-telemetry")
REPO_ROOT  = Path("C:/users/kalya/thermalops")
ANAL_DIR   = REPO_ROOT / "artifacts/phase1/analysis"
REV1_DIR   = REPO_ROOT / "artifacts/revision1/results"
OUT_DIR    = REPO_ROOT / "artifacts/revision2"

N_BOOTSTRAP    = 5000
BOOTSTRAP_SEED = 9999
MAX_WORKERS    = 8
BETA_F_FROZEN  = 1.12484352   # frozen: median of 462 per-job slopes, Gate D

print("=== Phase B: LOO Cross-Fitted Beta ===")
print(f"BETA_F_FROZEN = {BETA_F_FROZEN}")
print()

# ── Load fingerprints ──────────────────────────────────────────────────────
fp_df       = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
FA_2024     = fp_df["FA_2024"].to_dict()
n_train_d   = fp_df["n_jobs_train"].to_dict()
cohort_nodes= set(fp_df.index)
print(f"Cohort nodes: {len(cohort_nodes)}")
print(f"n_jobs_train: mean={np.mean(list(n_train_d.values())):.1f}, "
      f"median={np.median(list(n_train_d.values())):.0f}")

# ── Load qualifying training jobs (same jobs that determined BETA_F_FROZEN) ──
print("\nLoading qualifying training jobs (m3_train_betas.parquet) ...")
train_betas_df = pd.read_parquet(REV1_DIR / "m3_train_betas.parquet")
print(f"Qualifying training jobs: {len(train_betas_df)}")
print(f"BETA_F_FROZEN check: median beta_F = {train_betas_df['beta_F'].median():.8f}")

# ── Helpers ────────────────────────────────────────────────────────────────
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

def load_train_job(row):
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
    # Compute T_p95 per node (matches M3 model: nanmean across GCDs -> p95 across timestamps)
    node_data = {}
    for node, gcols in nm.items():
        ts_means = np.nanmean(temp[gcols].values.astype(float), axis=1)
        finite   = ts_means[np.isfinite(ts_means)]
        if len(finite) < 5:
            continue
        node_data[node] = float(np.percentile(finite, 95))
    if len(node_data) < 2:
        return None
    # Within-job T_dev = T_p95[i] - job_mean(T_p95)
    jm  = np.mean(list(node_data.values()))
    obs = [(node, float(val - jm)) for node, val in node_data.items()
           if node in FA_2024]
    if len(obs) < 2:
        return None
    return (job_idx, date_dir, obs)

# ── Load all qualifying training jobs ─────────────────────────────────────
print(f"\nLoading {len(train_betas_df)} qualifying training jobs (MAX_WORKERS={MAX_WORKERS}) ...")
rows = [row for _, row in train_betas_df.iterrows()]
job_obs_list = []
n_ok = n_fail = 0

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futures = {ex.submit(load_train_job, r): r for r in rows}
    for fut in as_completed(futures):
        res = fut.result()
        if res is None:
            n_fail += 1
        else:
            job_obs_list.append(res)
            n_ok += 1

print(f"  Loaded: {n_ok}  Failed: {n_fail}")

# ── Build flat observation DataFrame ──────────────────────────────────────
print("Building observation DataFrame ...")
records = []
for job_idx, date_dir, obs in job_obs_list:
    q_num = (int(date_dir[5:7]) - 1) // 3 + 1
    quarter = f"Q{q_num}_{date_dir[:4]}"
    for node, t_dev in obs:
        records.append({
            "job_idx":  job_idx,
            "date_dir": date_dir,
            "quarter":  quarter,
            "node":     node,
            "T_dev":    t_dev,
        })

obs_df = pd.DataFrame(records)
print(f"Total training observations: {len(obs_df):,}")
print(f"Unique jobs:   {obs_df['job_idx'].nunique()}")
print(f"Unique nodes:  {obs_df['node'].nunique()}")

# ── Compute F_CF[i,j] ─────────────────────────────────────────────────────
print("Computing F_CF ...")
obs_df["FA"] = obs_df["node"].map(FA_2024)
obs_df["n_i"] = obs_df["node"].map(n_train_d)
obs_df = obs_df.dropna(subset=["FA", "n_i"]).copy()
obs_df["n_i"] = obs_df["n_i"].astype(int)

n_excluded_n1 = int((obs_df["n_i"] == 1).sum())
print(f"  Excluded (n_i=1, can't LOO): {n_excluded_n1}")
obs_df = obs_df[obs_df["n_i"] > 1].copy()

# LOO formula: remove job j's contribution from FA_2024[i]
obs_df["F_CF"] = (obs_df["FA"] * obs_df["n_i"] - obs_df["T_dev"]) / (obs_df["n_i"] - 1)

print(f"  Eligible observations: {len(obs_df):,}")
print(f"  FA_2024 range:  [{obs_df['FA'].min():.3f}, {obs_df['FA'].max():.3f}]")
print(f"  F_CF range:     [{obs_df['F_CF'].min():.3f}, {obs_df['F_CF'].max():.3f}]")
print(f"  Mean |FA - F_CF|: {(obs_df['FA'] - obs_df['F_CF']).abs().mean():.4f}")

# ── Within-job demeaning ───────────────────────────────────────────────────
jm_FCF = obs_df.groupby("job_idx")["F_CF"].transform("mean")
jm_T   = obs_df.groupby("job_idx")["T_dev"].transform("mean")
obs_df["F_CF_dm"]  = obs_df["F_CF"]  - jm_FCF
obs_df["T_dev_dm"] = obs_df["T_dev"] - jm_T

# ── Job-level aggregates for fast inference ────────────────────────────────
print("Computing job-level aggregates ...")
obs_df["cross_xy"] = obs_df["F_CF_dm"] * obs_df["T_dev_dm"]
obs_df["cross_xx"] = obs_df["F_CF_dm"] ** 2

job_agg = obs_df.groupby("job_idx").agg(
    c_xy=("cross_xy", "sum"),
    c_xx=("cross_xx", "sum"),
    n_obs=("T_dev", "count"),
    quarter=("quarter", "first"),
).reset_index()

SS_xy    = float(job_agg["c_xy"].sum())
SS_xx    = float(job_agg["c_xx"].sum())
beta_CF  = SS_xy / SS_xx
pct_diff = 100.0 * (beta_CF - BETA_F_FROZEN) / abs(BETA_F_FROZEN)

print(f"\nbeta_CF (LOO cross-fit):  {beta_CF:.6f}")
print(f"BETA_F_FROZEN (median):   {BETA_F_FROZEN:.6f}")
print(f"Difference:               {pct_diff:+.2f}%")

# ── Bootstrap CI ──────────────────────────────────────────────────────────
print(f"\nBootstrap CI ({N_BOOTSTRAP} replicates, seed={BOOTSTRAP_SEED}) ...")
c_xy_arr = job_agg["c_xy"].values
c_xx_arr = job_agg["c_xx"].values
n_jobs_v = len(c_xy_arr)
rng = np.random.default_rng(BOOTSTRAP_SEED)

boot_betas = np.empty(N_BOOTSTRAP)
for b in range(N_BOOTSTRAP):
    idx = rng.integers(0, n_jobs_v, size=n_jobs_v)
    boot_betas[b] = c_xy_arr[idx].sum() / c_xx_arr[idx].sum()

ci_lo, ci_hi = np.percentile(boot_betas, [2.5, 97.5])
print(f"  beta_CF: {beta_CF:.6f}")
print(f"  95% CI:  [{ci_lo:.6f}, {ci_hi:.6f}]")

# ── B2a: Jackknife sensitivity (fast) ─────────────────────────────────────
print(f"\nB2a: Jackknife ({len(job_agg)} leave-one-job-out betas) ...")
jack_xy    = SS_xy - c_xy_arr
jack_xx    = SS_xx - c_xx_arr
jack_betas = jack_xy / jack_xx
print(f"  Mean:  {jack_betas.mean():.6f}")
print(f"  Std:   {jack_betas.std():.6f}")
print(f"  Min:   {jack_betas.min():.6f}")
print(f"  Max:   {jack_betas.max():.6f}")
print(f"  P5:    {np.percentile(jack_betas, 5):.6f}")
print(f"  P95:   {np.percentile(jack_betas, 95):.6f}")

# ── B2b: Quarter-wise cross-fit sensitivity ───────────────────────────────
print("\nB2b: Quarter-wise cross-fit ...")
quarters = sorted(obs_df["quarter"].unique())
print(f"  Quarters: {quarters}")

quarter_betas = {}
for q_held in quarters:
    train_q = obs_df[obs_df["quarter"] != q_held].copy()
    held_q  = obs_df[obs_df["quarter"] == q_held].copy()
    if len(held_q) < 30:
        quarter_betas[q_held] = {"note": "too few obs", "n_held": int(len(held_q))}
        continue
    # Recompute FA from train_q and LOO for held_q
    fa_q  = train_q.groupby("node")["T_dev"].mean().to_dict()
    n_q   = train_q.groupby("node")["T_dev"].count().to_dict()
    held_q = held_q.copy()
    held_q["FA_q"] = held_q["node"].map(fa_q)
    held_q = held_q.dropna(subset=["FA_q"])
    jm_T_q   = held_q.groupby("job_idx")["T_dev"].transform("mean")
    jm_FA_q  = held_q.groupby("job_idx")["FA_q"].transform("mean")
    held_q["T_dm"]  = held_q["T_dev"] - jm_T_q
    held_q["FA_dm"] = held_q["FA_q"] - jm_FA_q
    ss_xy_q = float((held_q["FA_dm"] * held_q["T_dm"]).sum())
    ss_xx_q = float((held_q["FA_dm"] ** 2).sum())
    beta_q  = float(ss_xy_q / ss_xx_q) if ss_xx_q != 0 else float("nan")
    quarter_betas[q_held] = {
        "n_train_obs": int(len(train_q)),
        "n_held_obs":  int(len(held_q)),
        "n_fa_nodes":  int(len(fa_q)),
        "beta_q":      round(float(beta_q), 6),
    }
    print(f"  Hold {q_held}: n_held={len(held_q):,}  beta_q={beta_q:.4f}")

# ── Interpretation per §H7 ────────────────────────────────────────────────
if abs(pct_diff) <= 2:
    interp = "Within ±2%: LOO cross-fit correction made negligible difference to beta"
elif abs(pct_diff) <= 10:
    interp = f"±2-10% difference ({pct_diff:+.1f}%): Modest self-inclusion correction; direction noted"
else:
    interp = f">10% difference ({pct_diff:+.1f}%): Substantial self-inclusion bias; direction noted explicitly"

print(f"\nInterpretation: {interp}")

# ── Write results ─────────────────────────────────────────────────────────
result = {
    "audit_script": "artifacts/revision2/run_b1_loo_beta.py",
    "audit_date":   "2026-10-02",
    "plan_ref":     "REVIEW2_CHALLENGE_PLAN.md §B1-B3 (amendment 6b45030)",
    "training_data": {
        "source":                 "m3_train_betas.parquet (462 qualifying jobs, same as BETA_F_FROZEN)",
        "n_jobs_loaded":          int(n_ok),
        "n_jobs_failed":          int(n_fail),
        "n_eligible_observations": int(len(obs_df)),
        "n_excluded_n1_obs":      int(n_excluded_n1),
        "n_unique_nodes":         int(obs_df["node"].nunique()),
        "n_unique_jobs":          int(obs_df["job_idx"].nunique()),
        "mean_abs_FA_minus_FCF":  round(float((obs_df["FA"] - obs_df["F_CF"]).abs().mean()), 6),
    },
    "B1_primary": {
        "beta_CF":            round(float(beta_CF), 8),
        "bootstrap_CI_95_lo": round(float(ci_lo), 8),
        "bootstrap_CI_95_hi": round(float(ci_hi), 8),
        "bootstrap_n":        N_BOOTSTRAP,
        "bootstrap_seed":     BOOTSTRAP_SEED,
        "beta_CF_se":         round(float((ci_hi - ci_lo) / 3.92), 8),
    },
    "B3_primary_beta": {
        "PRIMARY_BETA_CHALLENGE": round(float(beta_CF), 8),
        "BETA_F_FROZEN":          BETA_F_FROZEN,
        "pct_difference_from_frozen": round(float(pct_diff), 4),
        "interpretation":         interp,
        "BETA_F_CF_P5":           round(float(ci_lo), 8),
        "BETA_F_CF_P95":          round(float(ci_hi), 8),
    },
    "B2a_jackknife": {
        "n_jobs":               int(len(jack_betas)),
        "BETA_F_JACKKNIFE_MEAN": round(float(jack_betas.mean()), 8),
        "std":                  round(float(jack_betas.std()), 8),
        "min":                  round(float(jack_betas.min()), 8),
        "max":                  round(float(jack_betas.max()), 8),
        "P5":                   round(float(np.percentile(jack_betas, 5)), 8),
        "P95":                  round(float(np.percentile(jack_betas, 95)), 8),
    },
    "B2b_quarter_wise": quarter_betas,
}

out = OUT_DIR / "loo_beta_results.json"
out.write_text(json.dumps(result, indent=2))
print(f"\nWritten: {out}")
print(f"\nPRIMARY_BETA_CHALLENGE = beta_CF = {beta_CF:.6f}")
print(f"Bootstrap 95% CI: [{ci_lo:.6f}, {ci_hi:.6f}]")
print(f"vs BETA_F_FROZEN ({BETA_F_FROZEN}): {pct_diff:+.2f}%")
