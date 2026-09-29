#!/usr/bin/env python3
"""
M4 Threshold Provenance Audit
==============================
Verifies whether the 63.625 C primary threshold (derived from 462 power-model
training jobs, a 1000-job sample of 3,945 pre-2025 training jobs) is a reliable
estimate of the full thermal-eligible 2024 training population threshold.

Compares:
  A) Current: T_p95 from 462 power-model qualifying jobs (m3_train_betas.parquet)
  B) Full:    T_p95 from all 3,945 pre-2025 training jobs (any fp node, >= 8 GCDs,
              >= 5 valid ts, no minimum-per-job fp count requirement)

Saves: artifacts/revision1/results/m4_threshold_audit.json
       artifacts/revision1/results/full_train_t95_distribution.parquet
"""

import json, datetime, time, re
import numpy as np
import pandas as pd
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[3]
P1_ANAL    = REPO_ROOT / "artifacts" / "phase1" / "analysis"
REV1       = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR    = REV1 / "results"

DATA_DIR   = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset")
TELE_DIR   = DATA_DIR / "job-telemetry"
BATCH_FILE = REPO_ROOT / "artifacts" / "phase1" / "globus_batch.txt"

GCD_REQUIRED  = 8
MIN_VALID_TS  = 5
FULL_CACHE    = OUT_DIR / "full_train_t95_distribution.parquet"

t0 = time.time()
print("=" * 65)
print("M4 Threshold Provenance Audit")
print("=" * 65)

# ── Load existing 462-job subset ────────────────────────────────────
fp_df    = pd.read_parquet(P1_ANAL / "phase3a_fingerprint_2024.parquet")
fp_nodes = set(fp_df.index.tolist())

existing = pd.read_parquet(OUT_DIR / "d2_train_t95_distribution.parquet")
print(f"\n[A] Existing (462 power-model jobs subset):")
print(f"    n_node_job_pairs: {len(existing):,}")
print(f"    n_unique_jobs:    {existing['job_idx'].nunique()}")
a_vals = existing["t_p95"].values
print(f"    p90={np.percentile(a_vals,90):.4f}  p95={np.percentile(a_vals,95):.4f}  "
      f"p99={np.percentile(a_vals,99):.4f}")

# ── Load full pre-2025 job list from globus_batch.txt ───────────────
pat = re.compile(r"(\d{4}-\d{2}-\d{2})/(\d{6})")
all_pre2025 = []
with open(BATCH_FILE) as f:
    for line in f:
        m = pat.search(line)
        if m and m.group(1) < "2025":
            all_pre2025.append({"date_dir": m.group(1), "job_idx": int(m.group(2))})

pre2025_df = pd.DataFrame(all_pre2025).drop_duplicates("job_idx")
n_total = len(pre2025_df)
print(f"\n[B] Full pre-2025 training population: {n_total:,} jobs")

# ── Load from cache or recompute ────────────────────────────────────
if FULL_CACHE.exists():
    full_cache = pd.read_parquet(FULL_CACHE)
    print(f"\n    Loaded full-population cache ({len(full_cache):,} node-job pairs)")
else:
    print(f"\n    Computing from telemetry ({n_total:,} jobs)...")
    print("    Criteria: fp node in job, >= 8 GCD channels, >= 5 valid timestamps")
    print("    (No minimum fp-nodes-per-job cut)")

    rows = []
    n_jobs_ok = 0
    n_jobs_missing = 0
    n_jobs_nofp = 0
    waterfall = {"total_pre2025": n_total, "missing_tele": 0,
                 "no_eligible_fp_node": 0, "contributing": 0}

    for ki, (_, row) in enumerate(pre2025_df.iterrows()):
        if ki % 200 == 0:
            elapsed = time.time() - t0
            eta = (elapsed / max(ki, 1)) * (n_total - ki)
            print(f"    {ki}/{n_total}  ({elapsed:.0f}s elapsed, ~{eta:.0f}s remaining)", end="\r")

        jid      = int(row["job_idx"])
        date_dir = str(row["date_dir"])
        jid_str  = f"{jid:06d}"
        tpath    = TELE_DIR / date_dir / jid_str / f"{jid_str}-cleaned-temperature.parquet"

        if not tpath.exists():
            n_jobs_missing += 1
            waterfall["missing_tele"] += 1
            continue

        try:
            tmp = pd.read_parquet(tpath)
        except Exception:
            n_jobs_missing += 1
            waterfall["missing_tele"] += 1
            continue

        # Find GCD temperature columns for fp nodes
        node_gcd_map: dict[str, list] = {}
        for c in tmp.columns:
            if c.startswith("frontier") and "_gcd" in c and "ncount" not in c:
                node = c.split("_")[0]
                if node in fp_nodes:
                    node_gcd_map.setdefault(node, []).append(c)

        contributed = 0
        for node, gcols in node_gcd_map.items():
            if len(gcols) < GCD_REQUIRED:
                continue
            t_ts  = np.nanmean(tmp[gcols].values.astype(float), axis=1)
            finite = t_ts[np.isfinite(t_ts)]
            if len(finite) < MIN_VALID_TS:
                continue
            rows.append({"job_idx": jid, "date_dir": date_dir, "node": node,
                         "t_p95": float(np.percentile(finite, 95)),
                         "n_fp_in_job": len(node_gcd_map)})
            contributed += 1

        if contributed > 0:
            n_jobs_ok += 1
            waterfall["contributing"] += 1
        else:
            n_jobs_nofp += 1
            waterfall["no_eligible_fp_node"] += 1

    print(f"\n    Done: {n_jobs_ok} contributing jobs, "
          f"{n_jobs_nofp} no eligible fp node, {n_jobs_missing} missing telemetry")

    full_cache = pd.DataFrame(rows)
    full_cache.to_parquet(FULL_CACHE, index=False)
    print(f"    Saved: {FULL_CACHE}")
    print(f"    Total node-job pairs: {len(full_cache):,}")

# ── Compare distributions ────────────────────────────────────────────
b_vals = full_cache["t_p95"].values
n_contributing_jobs_b = full_cache["job_idx"].nunique()

print(f"\n{'='*65}")
print("THRESHOLD PROVENANCE COMPARISON")
print(f"{'='*65}")
print(f"\n  {'Statistic':<15}  {'A (462-job subset)':>20}  {'B (full population)':>20}")
print(f"  {'-'*55}")
print(f"  {'n_jobs':<15}  {existing['job_idx'].nunique():>20,}  {n_contributing_jobs_b:>20,}")
print(f"  {'n_node_jobs':<15}  {len(existing):>20,}  {len(full_cache):>20,}")
print(f"  {'p90 (C)':<15}  {np.percentile(a_vals,90):>20.4f}  {np.percentile(b_vals,90):>20.4f}")
print(f"  {'p95 (C)':<15}  {np.percentile(a_vals,95):>20.4f}  {np.percentile(b_vals,95):>20.4f}")
print(f"  {'p99 (C)':<15}  {np.percentile(a_vals,99):>20.4f}  {np.percentile(b_vals,99):>20.4f}")
print(f"  {'mean (C)':<15}  {np.mean(a_vals):>20.4f}  {np.mean(b_vals):>20.4f}")
print(f"  {'median (C)':<15}  {np.median(a_vals):>20.4f}  {np.median(b_vals):>20.4f}")

delta_p95 = np.percentile(b_vals, 95) - np.percentile(a_vals, 95)
print(f"\n  Delta p95 (full - subset): {delta_p95:+.4f} C")

# Jobs contributing to full but excluded from subset
full_jobs   = set(full_cache["job_idx"].unique())
subset_jobs = set(existing["job_idx"].unique())
extra_jobs  = full_jobs - subset_jobs
print(f"\n  Jobs in full but not in subset: {len(extra_jobs):,}")
print(f"  Jobs in subset:  {len(subset_jobs):,}")
print(f"  Jobs in full:    {len(full_jobs):,}")

# Distribution of n_fp_in_job for excluded vs included jobs
if "n_fp_in_job" in full_cache.columns:
    full_cache_j = full_cache.groupby("job_idx")["n_fp_in_job"].first()
    extra_sizes  = full_cache_j[full_cache_j.index.isin(extra_jobs)].values
    sub_sizes    = full_cache_j[full_cache_j.index.isin(subset_jobs)].values
    print(f"\n  n_fp_in_job (jobs in full but not subset): "
          f"median={np.median(extra_sizes) if len(extra_sizes) else 'N/A'}")
    print(f"  n_fp_in_job (jobs in subset): "
          f"median={np.median(sub_sizes) if len(sub_sizes) else 'N/A'}")
    # T_p95 statistics for extra jobs only
    extra_t95 = full_cache[full_cache["job_idx"].isin(extra_jobs)]["t_p95"].values
    if len(extra_t95) > 0:
        print(f"\n  T_p95 for excluded-job observations:")
        print(f"    n={len(extra_t95):,}  p90={np.percentile(extra_t95,90):.4f}  "
              f"p95={np.percentile(extra_t95,95):.4f}  p99={np.percentile(extra_t95,99):.4f}")

# ── Save result ──────────────────────────────────────────────────────
def jf(v):
    if v is None: return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f

result = {
    "script"    : "r1_m4_threshold_audit.py",
    "timestamp" : datetime.datetime.utcnow().isoformat() + "Z",
    "subset_462_jobs": {
        "n_jobs"          : int(existing["job_idx"].nunique()),
        "n_node_job_pairs": int(len(existing)),
        "selection_rule"  : "Jobs from 1000-job random sample of 3,945 pre-2025 training jobs that "
                            "qualified for power-model slope estimation (>= 8 fp nodes per job, "
                            "each with >= 8 GCD channels and >= 5 valid timestamps). "
                            "TRAIN_SAMPLE_N=1000, seed=42 in r1_m3_thermal_model.py.",
        "p90_C"  : jf(float(np.percentile(a_vals, 90))),
        "p95_C"  : jf(float(np.percentile(a_vals, 95))),
        "p99_C"  : jf(float(np.percentile(a_vals, 99))),
        "mean_C" : jf(float(np.mean(a_vals))),
    },
    "full_population": {
        "n_pre2025_jobs_in_batch": int(n_total),
        "n_contributing_jobs"    : int(n_contributing_jobs_b),
        "n_node_job_pairs"       : int(len(full_cache)),
        "selection_rule"         : "All pre-2025 jobs in globus_batch.txt with at least one "
                                   "fp node having >= 8 GCD channels and >= 5 valid timestamps. "
                                   "No minimum fp-nodes-per-job requirement.",
        "p90_C"  : jf(float(np.percentile(b_vals, 90))),
        "p95_C"  : jf(float(np.percentile(b_vals, 95))),
        "p99_C"  : jf(float(np.percentile(b_vals, 99))),
        "mean_C" : jf(float(np.mean(b_vals))),
    },
    "delta_p95_full_minus_subset_C": jf(delta_p95),
    "verdict": (
        f"Full-population p95={np.percentile(b_vals,95):.4f} C vs subset p95={np.percentile(a_vals,95):.4f} C "
        f"(delta={delta_p95:+.4f} C). "
        + ("Difference < 0.5 C: subset threshold is a reliable estimate."
           if abs(delta_p95) < 0.5
           else "Difference >= 0.5 C: use full-population p95 as M4 primary threshold.")
    ),
    "recommended_primary_threshold_C": jf(float(np.percentile(b_vals, 95))),
    "elapsed_seconds": round(time.time() - t0, 1),
}

out_path = OUT_DIR / "m4_threshold_audit.json"
with open(out_path, "w") as fh:
    json.dump(result, fh, indent=2)
print(f"\nSaved: {out_path}")
print(f"Total elapsed: {time.time()-t0:.1f}s")
