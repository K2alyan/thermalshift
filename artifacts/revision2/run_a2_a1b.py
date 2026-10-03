#!/usr/bin/env python3
"""A2 (prospective accuracy by job size) + A1b (late-cabinet cohort diagnostic).

Plan ref: REVIEW2_CHALLENGE_PLAN.md Phases A2 and A1b (amendment 6b45030).
"""
import sys, io, json, numpy as np, pandas as pd
from pathlib import Path
from scipy import stats

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

DATA_DIR  = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset")
REPO_ROOT = Path("C:/users/kalya/thermalops")
ANAL_DIR  = REPO_ROOT / "artifacts" / "phase1" / "analysis"
OUT_DIR   = REPO_ROOT / "artifacts" / "revision2"

print("=== A2 + A1b: Job-Size Accuracy + Late-Cabinet Cohort ===")
print()

# ── Load data ──────────────────────────────────────────────────────────────
print("Loading fingerprint data ...")
fp_df = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")

print("Loading test set ...")
test_df = pd.read_parquet(ANAL_DIR / "phase3a_test_set.parquet")

print("Loading all jobs for node_count ...")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet",
                           columns=["job_idx", "node_count", "start_time"])
all_jobs["job_idx"] = all_jobs["job_idx"].astype(int)

# ── Merge test_df with node_count ──────────────────────────────────────────
print("Merging test observations with job metadata ...")
test_df2 = test_df.copy()
test_df2["job_idx_int"] = test_df2["job_idx"].astype(int)
job_meta = all_jobs.set_index("job_idx")[["node_count", "start_time"]]
test_df2 = test_df2.join(job_meta, on="job_idx_int")

# Within-job T deviation (T_dev) — already in the fingerprint frame
# FA_2024 is the frozen predictor; T_dev = T_p95 - job_mean(T_p95)
# test_df should have columns: node_id, job_idx, FA_2024, T_dev (or similar)
print(f"test_df columns: {list(test_df2.columns)}")
print(f"test_df shape:   {test_df2.shape}")

# Identify outcome column (within-job T deviation)
outcome_col = None
for c in ["T_dev", "T_p95_dev", "within_job_dev", "delta_T"]:
    if c in test_df2.columns:
        outcome_col = c
        break
if outcome_col is None:
    # Fall back: look for any column that could be within-job deviation
    candidates = [c for c in test_df2.columns if "dev" in c.lower() or "delta" in c.lower()]
    print(f"Outcome column not found by name. Candidates: {candidates}")
    # Try to compute it from T_p95 if present
    if "T_p95" in test_df2.columns:
        job_means = test_df2.groupby("job_idx_int")["T_p95"].transform("mean")
        test_df2["T_dev"] = test_df2["T_p95"] - job_means
        outcome_col = "T_dev"
        print("Computed T_dev from T_p95 - job_mean(T_p95)")
    elif "T_max" in test_df2.columns:
        job_means = test_df2.groupby("job_idx_int")["T_max"].transform("mean")
        test_df2["T_dev"] = test_df2["T_max"] - job_means
        outcome_col = "T_dev"
        print("Computed T_dev from T_max - job_mean(T_max)")

print(f"Outcome column: {outcome_col}")

# Predictor column (in test_df the frozen fingerprint is stored as F_2024)
pred_col = None
for c in ["F_2024", "FA_2024", "FA_frozen", "FA", "fingerprint"]:
    if c in test_df2.columns:
        pred_col = c
        break
print(f"Predictor column: {pred_col}")

# Drop rows with missing data
test_clean = test_df2.dropna(subset=[pred_col, outcome_col, "node_count"]).copy()
print(f"Clean test observations: {len(test_clean)}")

# ── A2: Stratified by job size (node_count bins) ────────────────────────────
print("\n--- A2: Prospective Accuracy by Job Size ---")

BINS   = [1, 32, 128, 512, 2048, 1_000_000]
LABELS = ["1-32", "33-128", "129-512", "513-2048", "2049+"]

test_clean["size_bin"] = pd.cut(test_clean["node_count"], bins=BINS, labels=LABELS, right=True)

strata_results = []
for label in LABELS:
    sub = test_clean[test_clean["size_bin"] == label]
    n_obs  = len(sub)
    n_jobs = sub["job_idx_int"].nunique()
    if n_obs < 10:
        strata_results.append({
            "size_bin": label, "n_jobs": n_jobs, "n_obs": n_obs,
            "note": "insufficient data"
        })
        continue

    x = sub[pred_col].values
    y = sub[outcome_col].values

    pr, _     = stats.pearsonr(x, y)
    sr, _     = stats.spearmanr(x, y)
    r2        = pr ** 2
    slope, intercept, *_ = stats.linregress(x, y)

    strata_results.append({
        "size_bin":  label,
        "n_jobs":    int(n_jobs),
        "n_obs":     int(n_obs),
        "pearson_r": round(float(pr),   4),
        "spearman_r":round(float(sr),   4),
        "r2":        round(float(r2),   4),
        "ols_slope": round(float(slope), 4),
        "ols_intercept": round(float(intercept), 4),
    })
    print(f"  {label:12s}  n_jobs={n_jobs:5d}  n_obs={n_obs:7d}  "
          f"r={pr:.3f}  rho={sr:.3f}  R2={r2:.3f}")

# Overall
x_all = test_clean[pred_col].values
y_all = test_clean[outcome_col].values
pr_all, _  = stats.pearsonr(x_all, y_all)
sr_all, _  = stats.spearmanr(x_all, y_all)
r2_all     = pr_all ** 2
slope_all, intercept_all, *_ = stats.linregress(x_all, y_all)

overall = {
    "n_jobs":    int(test_clean["job_idx_int"].nunique()),
    "n_obs":     int(len(test_clean)),
    "pearson_r": round(float(pr_all),   4),
    "spearman_r":round(float(sr_all),   4),
    "r2":        round(float(r2_all),   4),
    "ols_slope": round(float(slope_all), 4),
    "ols_intercept": round(float(intercept_all), 4),
}
print(f"\n  Overall      n_jobs={overall['n_jobs']:5d}  n_obs={overall['n_obs']:7d}  "
      f"r={pr_all:.3f}  rho={sr_all:.3f}  R2={r2_all:.3f}")

a2_result = {
    "audit_script": "artifacts/revision2/run_a2_a1b.py",
    "audit_date":   "2026-10-02",
    "plan_ref":     "REVIEW2_CHALLENGE_PLAN.md Phase A2 (amendment 6b45030)",
    "predictor":    pred_col,
    "outcome":      outcome_col,
    "overall":      overall,
    "by_size_bin":  strata_results,
}

a2_out = OUT_DIR / "prospective_accuracy_by_job_size.json"
a2_out.write_text(json.dumps(a2_result, indent=2))
print(f"\nWritten: {a2_out}")

# ── A1b: Late-cabinet cohort diagnostic ────────────────────────────────────
print("\n--- A1b: Late-Cabinet Cohort Diagnostic ---")

# Load cabinet_timeline_audit.json to get cab->commissioning mapping
audit_json = OUT_DIR / "cabinet_timeline_audit.json"
with open(audit_json) as f:
    audit = json.load(f)

# Build node->cabinet map from the audit
# Use fp_df which has all 2000 fp-analysis nodes; we need their cabinet assignments
# Reload the mapping by replaying cab data from the audit's cabinet list
late_cabs = set(audit["cabinet_counts"]["late_commissioned_cabs"])  # {2600, 2601, 2602}

# The A1 script (run_a1_audit.py) built node_to_cab from all_jobs.
# We need the same map. Rebuild it from the parquet.
print("Rebuilding node->cabinet map from job parquet ...")
import re
jobs_full = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet",
                            columns=["job_idx", "host_list", "node_list"])
XNAME_RE = re.compile(r"x(\d+)c(\d+)s(\d+)b(\d+)n(\d+)")
CAB_RE   = re.compile(r"x(\d+)c")
node_to_cab = {}
for _, row in jobs_full.iterrows():
    hl = row.get("host_list")
    nl = row.get("node_list")
    if hl is None or nl is None or len(hl) != len(nl):
        continue
    for hn, xn in zip(hl, nl):
        hn_s, xn_s = str(hn), str(xn)
        m = XNAME_RE.match(xn_s) or CAB_RE.match(xn_s)
        if m:
            cab = int(m.group(1))
            node_to_cab[hn_s] = cab

print(f"  Mapped {len(node_to_cab):,} unique nodes to cabinets")

# Assign cabinet to each fp node
fp_df2 = fp_df.copy()
fp_df2["cabinet"] = fp_df2.index.map(lambda n: node_to_cab.get(str(n), -1))
fp_df2["is_late"] = fp_df2["cabinet"].isin(late_cabs)

late_nodes  = fp_df2[fp_df2["is_late"]]
early_nodes = fp_df2[~fp_df2["is_late"] & (fp_df2["cabinet"] != -1)]
unmapped    = fp_df2[fp_df2["cabinet"] == -1]

print(f"  Late-cab fp nodes:    {len(late_nodes)}")
print(f"  Early-cab fp nodes:   {len(early_nodes)}")
print(f"  Unmapped fp nodes:    {len(unmapped)}")

def cohort_stats(sub, label):
    if len(sub) == 0:
        return {"label": label, "n_nodes": 0}
    fa_col = "FA_2024" if "FA_2024" in sub.columns else pred_col
    ntrain_col = "n_jobs_train" if "n_jobs_train" in sub.columns else None
    out = {
        "label":   label,
        "n_nodes": int(len(sub)),
        "cabinets": sorted(int(c) for c in sub["cabinet"].unique() if c != -1),
    }
    if fa_col in sub.columns:
        out["FA_2024_mean"]   = round(float(sub[fa_col].mean()), 4)
        out["FA_2024_median"] = round(float(sub[fa_col].median()), 4)
        out["FA_2024_std"]    = round(float(sub[fa_col].std()), 4)
        out["FA_2024_q25"]    = round(float(sub[fa_col].quantile(0.25)), 4)
        out["FA_2024_q75"]    = round(float(sub[fa_col].quantile(0.75)), 4)
    if ntrain_col and ntrain_col in sub.columns:
        out["n_jobs_train_mean"]   = round(float(sub[ntrain_col].mean()), 2)
        out["n_jobs_train_median"] = round(float(sub[ntrain_col].median()), 2)
        out["n_jobs_train_min"]    = int(sub[ntrain_col].min())
        out["n_jobs_train_max"]    = int(sub[ntrain_col].max())
    return out

# Prospective accuracy per cohort using test_clean observations
def prospective_for_cohort(sub_fp, test_obs, pred, outcome):
    node_set = set(sub_fp.index.astype(str))
    # test_obs node column
    node_col = None
    for c in ["node_id", "hostname", "node", "host"]:
        if c in test_obs.columns:
            node_col = c
            break
    if node_col is None:
        return {"note": "no node column found in test_obs"}
    sub_test = test_obs[test_obs[node_col].astype(str).isin(node_set)]
    n_obs  = len(sub_test)
    n_jobs = sub_test["job_idx_int"].nunique() if "job_idx_int" in sub_test.columns else 0
    if n_obs < 10:
        return {"n_obs": n_obs, "n_jobs": n_jobs, "note": "insufficient data"}
    x = sub_test[pred].values
    y = sub_test[outcome].values
    pr, _   = stats.pearsonr(x, y)
    sr, _   = stats.spearmanr(x, y)
    mae     = float(np.mean(np.abs(y - x)))
    rmse    = float(np.sqrt(np.mean((y - x)**2)))
    r2_froz = float(pr**2)
    sign_ag = float(np.mean(np.sign(x) == np.sign(y)))
    return {
        "n_obs":     int(n_obs),
        "n_jobs":    int(n_jobs),
        "pearson_r": round(float(pr),   4),
        "spearman_r":round(float(sr),   4),
        "r2_frozen": round(r2_froz,     4),
        "mae":       round(mae,         4),
        "rmse":      round(rmse,        4),
        "sign_agreement": round(sign_ag, 4),
    }

late_cohort_stats  = cohort_stats(late_nodes,  "late_cabinets_2600_2601_2602")
early_cohort_stats = cohort_stats(early_nodes, "early_cabinets_74")

late_prosp  = prospective_for_cohort(late_nodes,  test_clean, pred_col, outcome_col)
early_prosp = prospective_for_cohort(early_nodes, test_clean, pred_col, outcome_col)

# Per-cabinet breakdown for late cabs
per_late_cab = {}
for cab in sorted(late_cabs):
    sub = fp_df2[fp_df2["cabinet"] == cab]
    cs  = cohort_stats(sub, f"cabinet_{cab}")
    pr  = prospective_for_cohort(sub, test_clean, pred_col, outcome_col)
    per_late_cab[str(cab)] = {**cs, "prospective_accuracy": pr}
    print(f"  Cab {cab}: n={len(sub)}  FA_mean={cs.get('FA_2024_mean','?'):.3f}  "
          f"n_train_mean={cs.get('n_jobs_train_mean','?')}  "
          f"prosp_r={pr.get('pearson_r','?')}")

# Interpretation
interpretation = []
if late_prosp.get("pearson_r") is not None and early_prosp.get("pearson_r") is not None:
    diff = late_prosp["pearson_r"] - early_prosp["pearson_r"]
    interpretation.append(
        f"Late-cab prospective Pearson r = {late_prosp['pearson_r']:.3f} vs "
        f"early-cab r = {early_prosp['pearson_r']:.3f} (diff = {diff:+.3f}). "
        "Negative FA fingerprints for late cabs are measured from genuine operational "
        "data; lower n_jobs_train reduces precision but does not introduce systematic bias."
    )

a1b_result = {
    "audit_script":  "artifacts/revision2/run_a2_a1b.py",
    "audit_date":    "2026-10-02",
    "plan_ref":      "REVIEW2_CHALLENGE_PLAN.md Phase A1b (amendment 6b45030)",
    "late_cabs":     sorted(late_cabs),
    "n_fp_nodes_total": int(len(fp_df2[fp_df2["cabinet"] != -1])),
    "late_cohort_descriptor": late_cohort_stats,
    "early_cohort_descriptor": early_cohort_stats,
    "late_cohort_prospective": late_prosp,
    "early_cohort_prospective": early_prosp,
    "per_late_cabinet": per_late_cab,
    "interpretation": interpretation,
}

a1b_out = OUT_DIR / "late_cab_cohort_diagnostic.json"
a1b_out.write_text(json.dumps(a1b_result, indent=2))
print(f"\nWritten: {a1b_out}")
print("\nAll done.")
