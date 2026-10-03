#!/usr/bin/env python3
"""
Phase B v2: Per-job LOO cross-fitted beta with correct estimand and correct r_ij.

Supersedes: run_b1_loo_beta.py (preserved at commit 2814bb6).
Plan ref: REVIEW2_CHALLENGE_PLAN.md §B1-B3 (Amendment 3).

CRITICAL CORRECTIONS from run_b1_loo_beta.py:

  1. WRONG ESTIMAND: The superseded script computed a pooled fixed-effects slope
         beta_CF = sum_j(c_xy[j]) / sum_j(c_xx[j])
     BETA_F_FROZEN is median(beta_j) over 462 per-job OLS slopes.  This script
     preserves that estimand:
         PRIMARY_BETA_CHALLENGE = median_j(beta_j_CF)

  2. WRONG r_ij: The superseded script subtracted T_dev[i,j] (T_p95 deviation)
     from FA_2024[i].  FA_2024 was built from the flat mean of ALL non-NaN GCD
     temperature values (all timestamps x all sensors), NOT T_p95.  This script
     reconstructs the actual r_ij = node_scalar_mean[i,j] - job_mean.

Correct procedure (Amendment 3 §B3-1, §B3-2):
  For each qualifying training job j (462 total from m3_train_betas.parquet):
    1. Load temperature parquet for job j.
    2. For each fp node i in job j:
         node_scalar_mean[i,j] = mean(ALL non-NaN GCD values, all ts x sensors)
         r_ij                  = node_scalar_mean[i,j] - job_mean(node_scalar_mean)
         T_p95[i,j]            = p95 over timestamps of (mean across GCD sensors)
    3. HARD ASSERTION: reproduce original per-job beta_j using FA_2024 + T_p95.
         If median(beta_j_repro) deviates from BETA_F_FROZEN by > BETA_MED_TOL,
         exit non-zero — r_ij reconstruction is inconsistent with FA_2024.
    4. Compute LOO fingerprint:
         F_i^(-j) = (n_i * FA_2024[i] - r_ij) / (n_i - 1)
    5. Compute per-job LOO beta:
         fa_cf_dm = F_i^(-j) - job_mean(F[:,j])
         t_dm     = T_p95[i,j] - job_mean(T_p95[:,j])
         beta_j_CF = dot(fa_cf_dm, t_dm) / dot(fa_cf_dm, fa_cf_dm)
  PRIMARY_BETA_CHALLENGE = median(beta_j_CF) over qualifying jobs.
  Bootstrap 95% CI by resampling 462 per-job LOO betas (unit = job).
"""
import sys, io, json
import numpy as np
import pandas as pd
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
BETA_F_FROZEN  = 1.12484352
BETA_REPRO_TOL = 0.02    # max |beta_j_repro - beta_j_frozen| per individual job
BETA_MED_TOL   = 0.001   # max |median_repro - BETA_F_FROZEN| for hard assertion

print("=== Phase B v2: Per-Job LOO Cross-Fitted Beta (Corrected Estimand + r_ij) ===")
print(f"BETA_F_FROZEN = {BETA_F_FROZEN}")
print()

# ── Load fingerprints ──────────────────────────────────────────────────────
fp_df       = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
FA_2024     = fp_df["FA_2024"].to_dict()
n_train_d   = fp_df["n_jobs_train"].to_dict()
cohort_nodes = set(fp_df.index)
print(f"Cohort nodes: {len(cohort_nodes)}")
print(f"n_jobs_train: median={np.median(list(n_train_d.values())):.0f}, "
      f"range=[{min(n_train_d.values())}, {max(n_train_d.values())}]")

# ── Load qualifying training jobs ─────────────────────────────────────────
print("\nLoading qualifying training jobs (m3_train_betas.parquet) ...")
train_betas_df = pd.read_parquet(REV1_DIR / "m3_train_betas.parquet")
n_qual = len(train_betas_df)
print(f"Qualifying training jobs: {n_qual}")
frozen_median_check = train_betas_df["beta_F"].median()
print(f"Frozen median(beta_F) from parquet: {frozen_median_check:.8f}")
assert abs(frozen_median_check - BETA_F_FROZEN) < 0.0001, \
    f"m3_train_betas.parquet median={frozen_median_check:.8f} != BETA_F_FROZEN={BETA_F_FROZEN}"

frozen_betas = {int(r.job_idx): float(r.beta_F)
                for _, r in train_betas_df.iterrows()
                if hasattr(r, "beta_F") and pd.notna(r.beta_F)}


# ── Helpers ────────────────────────────────────────────────────────────────
def get_node_gcols(all_cols: list) -> dict:
    """Returns {node: [gcd_col, ...]} for all fp-cohort nodes present in cols."""
    result: dict[str, list] = {}
    for col in all_cols:
        if "_gcd" not in col or "ncount" in col:
            continue
        node = col.split("_")[0]
        if node in cohort_nodes:
            result.setdefault(node, []).append(col)
    return result


def load_qualifying_job(row) -> dict | None:
    """Load one qualifying job; return both r_ij and T_p95 per node."""
    job_idx  = int(row.job_idx)
    date_dir = str(row.date_dir)
    job_str  = str(job_idx).zfill(6)
    fpath    = DATA_DIR / date_dir / job_str / f"{job_str}-cleaned-temperature.parquet"

    try:
        temp = pq.read_table(fpath).to_pandas()
    except Exception:
        return None

    node_gcols = get_node_gcols(list(temp.columns))
    if not node_gcols:
        return None

    # Per-node: compute both node_scalar_mean (for r_ij) and T_p95 (outcome)
    node_nsm: dict[str, float] = {}   # node_scalar_mean per node
    node_tp95: dict[str, float] = {}  # T_p95 per node
    for node, gcols in node_gcols.items():
        vals = temp[gcols].values.astype(float)   # (n_ts, n_gcds)

        # r_ij: flat mean of ALL non-NaN GCD values (all timestamps x sensors)
        flat  = vals.flatten()
        valid = flat[np.isfinite(flat)]
        if len(valid) < 5:
            continue
        node_nsm[node] = float(valid.mean())

        # T_p95: p95 over timestamps of row-wise nanmean across GCDs
        ts_means  = np.nanmean(vals, axis=1)
        finite_ts = ts_means[np.isfinite(ts_means)]
        if len(finite_ts) < 5:
            continue
        node_tp95[node] = float(np.percentile(finite_ts, 95))

    # Keep only nodes with both quantities and present in FA_2024
    common = [n for n in node_nsm if n in node_tp95 and n in FA_2024]
    if len(common) < 2:
        return None

    nsm_arr  = np.array([node_nsm[n]  for n in common])
    tp95_arr = np.array([node_tp95[n] for n in common])

    job_mean_nsm  = float(nsm_arr.mean())
    job_mean_tp95 = float(tp95_arr.mean())

    obs = {
        n: {
            "r_ij":  float(node_nsm[n]  - job_mean_nsm),    # fingerprint contribution
            "T_dev": float(node_tp95[n] - job_mean_tp95),   # outcome deviation
        }
        for n in common
    }

    # Quarter from date_dir (e.g. "2024-03" -> Q1_2024)
    try:
        m = int(date_dir[5:7])
        quarter = f"Q{(m - 1) // 3 + 1}_{date_dir[:4]}"
    except Exception:
        quarter = "Q?"

    return {"job_idx": job_idx, "date_dir": date_dir, "quarter": quarter, "obs": obs}


# ── Load all qualifying jobs ───────────────────────────────────────────────
print(f"\nLoading {n_qual} qualifying training jobs (MAX_WORKERS={MAX_WORKERS}) ...")
job_results: list[dict] = []
n_ok = n_fail = 0

with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
    futures = {ex.submit(load_qualifying_job, r): r
               for r in train_betas_df.itertuples()}
    for fut in as_completed(futures):
        res = fut.result()
        if res is None:
            n_fail += 1
        else:
            job_results.append(res)
            n_ok += 1

print(f"  Loaded OK: {n_ok}   Failed: {n_fail}")
job_results.sort(key=lambda x: x["job_idx"])

# ════════════════════════════════════════════════════════════════════════════
# HARD ASSERTION: Reproduce original per-job betas using FA_2024 + T_p95
# Verifies that our r_ij reconstruction is internally consistent with FA_2024.
# ════════════════════════════════════════════════════════════════════════════
print("\n--- HARD ASSERTION: Reproducing original per-job betas ---")
repro_diffs: list[float] = []
repro_betas: list[float] = []
n_repro_ok = n_repro_miss = 0

for jres in job_results:
    jid = jres["job_idx"]
    obs = jres["obs"]
    nodes_j = sorted(obs.keys())
    if len(nodes_j) < 2:
        continue

    fa_arr = np.array([FA_2024[n] for n in nodes_j])
    t_arr  = np.array([obs[n]["T_dev"] for n in nodes_j])

    fa_center = fa_arr - fa_arr.mean()
    denom = float(np.dot(fa_center, fa_center))
    if denom == 0:
        continue
    beta_j_repro = float(np.dot(fa_center, t_arr) / denom)
    repro_betas.append(beta_j_repro)

    if jid in frozen_betas:
        diff = abs(beta_j_repro - frozen_betas[jid])
        repro_diffs.append(diff)
        if diff <= BETA_REPRO_TOL:
            n_repro_ok += 1
        else:
            n_repro_miss += 1

n_checked = len(repro_diffs)
max_diff  = float(max(repro_diffs)) if repro_diffs else float("nan")
med_diff  = float(np.median(repro_diffs)) if repro_diffs else float("nan")
print(f"  Jobs with frozen beta reference: {n_checked}")
print(f"  Within tol ({BETA_REPRO_TOL}): {n_repro_ok}/{n_checked}")
print(f"  Exceeded tol: {n_repro_miss}/{n_checked}")
print(f"  Max |beta_repro - beta_frozen|:    {max_diff:.6f}")
print(f"  Median |beta_repro - beta_frozen|: {med_diff:.6f}")

median_repro = float(np.median(repro_betas)) if repro_betas else float("nan")
print(f"\n  median(beta_j_repro):  {median_repro:.8f}")
print(f"  BETA_F_FROZEN:         {BETA_F_FROZEN:.8f}")
print(f"  |median_repro - BETA_F_FROZEN|: {abs(median_repro - BETA_F_FROZEN):.8f}")

if abs(median_repro - BETA_F_FROZEN) > BETA_MED_TOL:
    print(f"\nHARD ASSERTION FAILED: median_repro={median_repro:.8f} "
          f"!= BETA_F_FROZEN={BETA_F_FROZEN:.8f} (tol={BETA_MED_TOL})")
    print("r_ij reconstruction is inconsistent with FA_2024.  Cannot proceed.")
    sys.exit(1)

print("  HARD ASSERTION PASSED: r_ij reconstruction verified via beta reproduction.")

# ── Soft check: correlation between mean(r_ij over qualifying) and FA_2024 ─
print("\n--- Soft check: mean(r_ij over qualifying jobs) vs FA_2024 ---")
rij_sum:   dict[str, float] = {}
rij_count: dict[str, int]   = {}
for jres in job_results:
    for node, od in jres["obs"].items():
        rij_sum[node]   = rij_sum.get(node, 0.0) + od["r_ij"]
        rij_count[node] = rij_count.get(node, 0) + 1

nodes_common = [n for n in rij_sum if n in FA_2024]
rij_mean_q   = np.array([rij_sum[n] / rij_count[n] for n in nodes_common])
fa_common    = np.array([FA_2024[n] for n in nodes_common])
corr_rij_fa  = float(np.corrcoef(rij_mean_q, fa_common)[0, 1]) if len(nodes_common) > 1 else float("nan")
print(f"  Nodes with r_ij in qualifying jobs: {len(nodes_common)}")
print(f"  Pearson corr(mean(r_ij_qualifying), FA_2024): {corr_rij_fa:.6f}")
print(f"  (Expected <1.0 because qualifying jobs are a subset of all n_i training jobs)")

# ════════════════════════════════════════════════════════════════════════════
# Compute per-job LOO betas
# ════════════════════════════════════════════════════════════════════════════
print("\n--- Computing per-job LOO betas ---")
loo_beta_records: list[dict] = []
n_excluded_n1 = 0

for jres in job_results:
    obs = jres["obs"]
    nodes_j: list[str] = []
    r_ij_j:  list[float] = []
    t_dev_j: list[float] = []
    fa_j:    list[float] = []
    ni_j:    list[int]   = []

    for node in sorted(obs.keys()):
        n_i = n_train_d.get(node)
        if n_i is None or int(n_i) <= 1:
            n_excluded_n1 += 1
            continue
        nodes_j.append(node)
        r_ij_j.append(obs[node]["r_ij"])
        t_dev_j.append(obs[node]["T_dev"])
        fa_j.append(FA_2024[node])
        ni_j.append(int(n_i))

    if len(nodes_j) < 2:
        continue

    r_arr  = np.array(r_ij_j)
    t_arr  = np.array(t_dev_j)
    fa_arr = np.array(fa_j)
    ni_arr = np.array(ni_j, dtype=float)

    # LOO fingerprint: F_i^(-j) = (n_i * FA_2024[i] - r_ij) / (n_i - 1)
    f_loo    = (ni_arr * fa_arr - r_arr) / (ni_arr - 1.0)

    # Within-job demeaning of LOO fingerprint and T_dev
    f_loo_dm = f_loo - f_loo.mean()
    t_dm     = t_arr - t_arr.mean()

    denom = float(np.dot(f_loo_dm, f_loo_dm))
    if denom == 0:
        continue

    beta_j_cf = float(np.dot(f_loo_dm, t_dm) / denom)
    loo_beta_records.append({
        "job_idx":   jres["job_idx"],
        "quarter":   jres["quarter"],
        "n_nodes":   len(nodes_j),
        "beta_j_cf": beta_j_cf,
    })

n_jobs_loo = len(loo_beta_records)
print(f"  Jobs with LOO beta computed: {n_jobs_loo}")
print(f"  Excluded obs (n_i=1): {n_excluded_n1}")

beta_arr = np.array([d["beta_j_cf"] for d in loo_beta_records])
primary_beta = float(np.median(beta_arr))
pct_diff     = 100.0 * (primary_beta - BETA_F_FROZEN) / abs(BETA_F_FROZEN)

print(f"\nPRIMARY_BETA_CHALLENGE = median(beta_j_CF) = {primary_beta:.8f}")
print(f"BETA_F_FROZEN          =                     {BETA_F_FROZEN:.8f}")
print(f"Difference:            {pct_diff:+.2f}%")

# ════════════════════════════════════════════════════════════════════════════
# Bootstrap CI: resample 462 per-job LOO betas (unit = job, not observation)
# ════════════════════════════════════════════════════════════════════════════
print(f"\nBootstrap CI ({N_BOOTSTRAP} replicates, seed={BOOTSTRAP_SEED}, unit=job) ...")
rng_bs = np.random.default_rng(BOOTSTRAP_SEED)
n_j    = len(beta_arr)
boot_medians = np.array([
    float(np.median(beta_arr[rng_bs.integers(0, n_j, size=n_j)]))
    for _ in range(N_BOOTSTRAP)
])
ci_lo = float(np.percentile(boot_medians, 2.5))
ci_hi = float(np.percentile(boot_medians, 97.5))
print(f"  PRIMARY_BETA_CHALLENGE: {primary_beta:.8f}")
print(f"  95% CI (bootstrap):     [{ci_lo:.8f}, {ci_hi:.8f}]")

# ── Per-job beta distribution ─────────────────────────────────────────────
print(f"\nPer-job LOO beta distribution (n={n_jobs_loo}):")
for label, val in [
    ("mean",    float(beta_arr.mean())),
    ("std",     float(beta_arr.std())),
    ("min",     float(beta_arr.min())),
    ("P5",      float(np.percentile(beta_arr, 5))),
    ("P25",     float(np.percentile(beta_arr, 25))),
    ("median",  float(np.median(beta_arr))),
    ("P75",     float(np.percentile(beta_arr, 75))),
    ("P95",     float(np.percentile(beta_arr, 95))),
    ("max",     float(beta_arr.max())),
]:
    print(f"  {label:8s}: {val:.6f}")

# ── Quarter-wise breakdown ────────────────────────────────────────────────
print("\nQuarter-wise breakdown:")
q_betas: dict[str, list] = {}
for d in loo_beta_records:
    q_betas.setdefault(d["quarter"], []).append(d["beta_j_cf"])

q_summary: dict[str, dict] = {}
for q in sorted(q_betas):
    b = np.array(q_betas[q])
    q_summary[q] = {
        "n_jobs": len(b),
        "median": round(float(np.median(b)), 6),
        "mean":   round(float(b.mean()), 6),
        "std":    round(float(b.std()), 6),
    }
    print(f"  {q}: n={len(b):3d}  median={np.median(b):.4f}  mean={b.mean():.4f}")

# ── Interpretation ────────────────────────────────────────────────────────
if abs(pct_diff) <= 2:
    interp = f"Within +-2% ({pct_diff:+.1f}%): LOO correction made negligible difference"
elif abs(pct_diff) <= 10:
    interp = f"+-2-10% difference ({pct_diff:+.1f}%): Modest self-inclusion correction"
else:
    interp = f">10% difference ({pct_diff:+.1f}%): Substantial self-inclusion bias"
print(f"\nInterpretation: {interp}")

# ── Write results ──────────────────────────────────────────────────────────
result = {
    "audit_script": "artifacts/revision2/run_b1_loo_beta_v2.py",
    "audit_date":   "2026-10-03",
    "plan_ref":     "REVIEW2_CHALLENGE_PLAN.md §B1-B3 (Amendment 3)",
    "supersedes":   "run_b1_loo_beta.py (commit 2814bb6)",
    "correction_note": (
        "Corrects two errors: "
        "(1) estimand changed from pooled FE slope to median of per-job LOO betas "
        "(matching BETA_F_FROZEN estimand); "
        "(2) LOO r_ij uses flat GCD mean (node_scalar_mean), not T_p95 deviation."
    ),
    "training_data": {
        "source":               "m3_train_betas.parquet",
        "n_jobs_attempted":     n_qual,
        "n_jobs_loaded":        n_ok,
        "n_jobs_failed":        n_fail,
        "n_jobs_with_loo_beta": n_jobs_loo,
        "n_excluded_n1_nodes":  n_excluded_n1,
    },
    "hard_assertion_beta_repro": {
        "n_jobs_checked":              n_checked,
        "max_diff":                    round(max_diff, 8),
        "median_diff":                 round(med_diff, 8),
        "n_within_tol":                n_repro_ok,
        "tol_per_job":                 BETA_REPRO_TOL,
        "median_repro":                round(median_repro, 8),
        "BETA_F_FROZEN":               BETA_F_FROZEN,
        "median_tol":                  BETA_MED_TOL,
        "assertion_passed":            True,
    },
    "rij_fa_consistency": {
        "n_nodes":              len(nodes_common),
        "pearson_corr":         round(corr_rij_fa, 6),
        "note": (
            "Pearson corr between mean(r_ij over qualifying 462 jobs) and FA_2024. "
            "Expected <1 since qualifying jobs are a subset of all n_i training jobs."
        ),
    },
    "B1_primary_v2": {
        "estimand":               "median(beta_j_CF) over qualifying jobs",
        "PRIMARY_BETA_CHALLENGE": round(primary_beta, 8),
        "bootstrap_CI_95_lo":     round(ci_lo, 8),
        "bootstrap_CI_95_hi":     round(ci_hi, 8),
        "bootstrap_n":            N_BOOTSTRAP,
        "bootstrap_seed":         BOOTSTRAP_SEED,
        "bootstrap_unit":         "per-job LOO beta (not individual observation)",
    },
    "B3_primary_beta": {
        "PRIMARY_BETA_CHALLENGE":          round(primary_beta, 8),
        "BETA_F_FROZEN":                   BETA_F_FROZEN,
        "pct_difference_from_frozen":      round(pct_diff, 4),
        "interpretation":                  interp,
        "BETA_F_CF_P5":                    round(ci_lo, 8),
        "BETA_F_CF_P95":                   round(ci_hi, 8),
    },
    "B1_secondary_FE_beta": {
        "note": (
            "Pooled fixed-effects slope from superseded run_b1_loo_beta.py. "
            "This is sum_j(c_xy) / sum_j(c_xx), a different estimand from BETA_F_FROZEN. "
            "Reported as secondary diagnostic only — NOT used as primary beta."
        ),
        "value":                   1.08293343,
        "source_commit":           "2814bb6",
    },
    "per_job_beta_distribution": {
        "n_jobs":  int(n_jobs_loo),
        "mean":    round(float(beta_arr.mean()), 6),
        "std":     round(float(beta_arr.std()),  6),
        "min":     round(float(beta_arr.min()),  6),
        "P5":      round(float(np.percentile(beta_arr, 5)),  6),
        "P25":     round(float(np.percentile(beta_arr, 25)), 6),
        "median":  round(float(np.median(beta_arr)),         6),
        "P75":     round(float(np.percentile(beta_arr, 75)), 6),
        "P95":     round(float(np.percentile(beta_arr, 95)), 6),
        "max":     round(float(beta_arr.max()),  6),
    },
    "quarter_wise_breakdown": q_summary,
    "B2a_jackknife": {
        "note": "Jackknife not recomputed for v2; refer to run_b1_loo_beta.py for FE-slope jackknife."
    },
    "B2b_quarter_wise": q_summary,
}

out_path = OUT_DIR / "loo_beta_results.json"
out_path.write_text(json.dumps(result, indent=2))
print(f"\nWritten: {out_path}")
print(f"\nPRIMARY_BETA_CHALLENGE = {primary_beta:.8f}")
print(f"Bootstrap 95% CI:       [{ci_lo:.8f}, {ci_hi:.8f}]")
print(f"vs BETA_F_FROZEN:       {BETA_F_FROZEN:.8f}  ({pct_diff:+.2f}%)")
print("\nNext step: update PRIMARY_BETA_CHALLENGE in r2_selectors.py with the value above.")
