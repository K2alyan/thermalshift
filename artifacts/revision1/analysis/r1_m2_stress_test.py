#!/usr/bin/env python3
"""
M2 Availability Stress Test
============================
The 152,400-job metadata are selected jobs; observed schedule occupancy is a
LOWER BOUND on true production occupancy. This synthetic stress test asks:
how does the FP-cap-10 advantage over Random-cap-10 hold as available fraction
of fp nodes drops from 60% to 10%?

Design
------
For each available fraction f in {10, 20, 30, 40, 50, 60}%:
  For N_SCENARIOS random draws of which nodes are available (CRN across policies):
    1. Mark round(f * 2000) randomly chosen fp nodes as "available"
    2. For each of the 2,637 test jobs (known n_required from M2):
       a. Feasible iff n_available >= n_required
       b. FP-cap-10   selection: n_required lowest-FA nodes from available set
       c. Random-cap-10 selection: n_required randomly drawn from available set
                         (per-job seed = scenario * 10000 + job_ordinal)
    3. Record per-job: feasible, fa_fp, fa_random, delta_fa, avail_req_ratio
  Summarise over jobs x scenarios:
    - pct_feasible (overall and by n_required quartile)
    - drop_rate by n_required quartile
    - mean_delta_fa (paired FP advantage in thermal fingerprint units)
    - avail_req_ratio distribution

Output
------
  artifacts/revision1/results/m2_stress_test.json
  artifacts/revision1/tables/m2_stress_summary.csv
"""

import json, hashlib, subprocess, datetime, time
import numpy as np
import pandas as pd
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[3]
PHASE1_DIR = REPO_ROOT / "artifacts" / "phase1"
ANAL_DIR   = PHASE1_DIR / "analysis"
REV1_DIR   = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR    = REV1_DIR / "results"
TABLE_DIR  = REV1_DIR / "tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

N_SCENARIOS        = 30    # consistent with phase3b
AVAIL_FRACTIONS    = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
RNG_SEED_BASE      = 42    # base seed; scenario-specific seeds derived from this
N_FP               = 2000  # total fingerprinted nodes in cohort

def git_sha():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=str(REPO_ROOT)).strip()
    except Exception:
        return "unknown"

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def jf(v):
    if v is None:
        return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f

print("=" * 65)
print("M2: Availability Stress Test")
print("=" * 65)
t0 = time.time()

# ── Load inputs ────────────────────────────────────────────────────
print("\n[0] Loading inputs ...")
fp_df   = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
avail_df = pd.read_csv(TABLE_DIR / "m2_test_job_availability.csv")

# Ordered fp node array with FA scores
fp_nodes   = fp_df.index.tolist()
FA_arr     = fp_df["FA_2024"].values.astype(float)
FA_argsort = np.argsort(FA_arr)   # ascending: index of coolest first

# Test jobs: n_required and quartile assignment
n_req_arr = avail_df["n_required"].values.astype(int)
job_ids   = avail_df["job_idx"].values
n_jobs    = len(avail_df)

q_cuts = np.percentile(n_req_arr, [25, 50, 75])
job_quartile = np.digitize(n_req_arr, q_cuts) + 1   # 1=smallest, 4=largest

print(f"    fp nodes:   {len(fp_nodes)}")
print(f"    test jobs:  {n_jobs}")
print(f"    n_required  p25={q_cuts[0]:.0f}  p50={q_cuts[1]:.0f}  p75={q_cuts[2]:.0f}")
print(f"    job size quartile counts: {np.bincount(job_quartile)[1:]}")

# ── Stress test loop ───────────────────────────────────────────────
print(f"\n[1] Running {N_SCENARIOS} scenarios x {len(AVAIL_FRACTIONS)} fractions ...")

# For efficiency: within each scenario/fraction, we pick available node set
# once (CRN across policies). Then for each job:
#   - FP: deterministic (lowest FA from available)
#   - Random: seeded per (scenario, job_ordinal) for CRN across fractions
#
# CRN across fractions: same "blocker" permutation reused; just change threshold.

all_rows = []   # one row per (scenario, fraction, job)

for scen_idx in range(N_SCENARIOS):
    scen_rng = np.random.default_rng(RNG_SEED_BASE + scen_idx)

    # Draw a single permutation of fp node indices; available = first n_avail
    perm = scen_rng.permutation(N_FP)   # perm[0..n_avail-1] = available nodes

    for f in AVAIL_FRACTIONS:
        n_avail = max(1, round(f * N_FP))
        avail_idx = set(perm[:n_avail])          # set of fp-array indices available
        avail_list = np.array(sorted(avail_idx)) # for indexing

        # FA values and sorted (coolest first) within available set
        FA_avail   = FA_arr[avail_list]
        fp_sort_in_avail = np.argsort(FA_avail)  # ascending within available

        for job_ord in range(n_jobs):
            n_req = n_req_arr[job_ord]
            feasible = (n_avail >= n_req)

            avail_req_ratio = n_avail / n_req

            if not feasible:
                all_rows.append({
                    "scenario":   scen_idx,
                    "f":          f,
                    "job_ord":    job_ord,
                    "quartile":   int(job_quartile[job_ord]),
                    "n_required": int(n_req),
                    "n_avail":    n_avail,
                    "feasible":   False,
                    "fa_fp":      np.nan,
                    "fa_random":  np.nan,
                    "delta_fa":   np.nan,
                    "avail_req_ratio": avail_req_ratio,
                })
                continue

            # FP-cap-10: select n_req coolest available nodes
            fp_sel_local = fp_sort_in_avail[:n_req]
            fa_fp = float(FA_avail[fp_sel_local].mean())

            # Random-cap-10: random selection; CRN seed per (scenario, job, fraction)
            # Use scen_idx + a stable per-job hash to make it reproducible
            job_rng = np.random.default_rng(
                (RNG_SEED_BASE + scen_idx) * 100003 + job_ord)
            rand_sel_local = job_rng.choice(n_avail, size=n_req, replace=False)
            fa_random = float(FA_avail[rand_sel_local].mean())

            delta_fa = fa_fp - fa_random   # negative = FP selects cooler nodes

            all_rows.append({
                "scenario":   scen_idx,
                "f":          f,
                "job_ord":    job_ord,
                "quartile":   int(job_quartile[job_ord]),
                "n_required": int(n_req),
                "n_avail":    n_avail,
                "feasible":   True,
                "fa_fp":      fa_fp,
                "fa_random":  fa_random,
                "delta_fa":   delta_fa,
                "avail_req_ratio": avail_req_ratio,
            })

    if (scen_idx + 1) % 5 == 0:
        print(f"    ... scenario {scen_idx+1}/{N_SCENARIOS}", end="\r")

print(f"\n    Loop done. Total rows: {len(all_rows):,}")

df = pd.DataFrame(all_rows)

# ── Aggregate summary ───────────────────────────────────────────────
print("\n[2] Aggregating results ...")

summary_rows = []
for f in AVAIL_FRACTIONS:
    sub = df[df["f"] == f]
    n_avail = max(1, round(f * N_FP))

    feasible_mask = sub["feasible"]
    feas = sub[feasible_mask]
    infeas = sub[~feasible_mask]

    pct_feasible   = float(feasible_mask.mean() * 100)
    drop_rate      = float((~feasible_mask).mean() * 100)
    mean_delta_fa  = float(feas["delta_fa"].mean()) if len(feas) > 0 else np.nan
    pct_fp_cooler  = float((feas["delta_fa"] < 0).mean() * 100) if len(feas) > 0 else np.nan
    median_arr     = float(feas["avail_req_ratio"].median()) if len(feas) > 0 else np.nan
    fa_fp_mean     = float(feas["fa_fp"].mean()) if len(feas) > 0 else np.nan
    fa_random_mean = float(feas["fa_random"].mean()) if len(feas) > 0 else np.nan

    print(f"    f={f:.0%}: feasible={pct_feasible:.1f}%  "
          f"delta_FA={mean_delta_fa:+.4f}  "
          f"FP_cooler={pct_fp_cooler:.1f}%")

    row = {
        "avail_frac":      f,
        "n_avail":         n_avail,
        "pct_feasible":    pct_feasible,
        "drop_rate_pct":   drop_rate,
        "mean_delta_fa_fp_vs_random": jf(mean_delta_fa),
        "pct_jobs_fp_cooler": jf(pct_fp_cooler),
        "mean_fa_fp":       jf(fa_fp_mean),
        "mean_fa_random":   jf(fa_random_mean),
        "median_avail_req_ratio": jf(median_arr),
    }

    # By quartile
    for q in range(1, 5):
        subq = sub[sub["quartile"] == q]
        feasq = subq[subq["feasible"]]
        row[f"q{q}_pct_feasible"] = float((subq["feasible"]).mean() * 100)
        row[f"q{q}_drop_rate_pct"] = float((~subq["feasible"]).mean() * 100)
        row[f"q{q}_mean_delta_fa"] = float(feasq["delta_fa"].mean()) if len(feasq) > 0 else np.nan
        row[f"q{q}_n_jobs_per_scen"] = int(len(subq) / N_SCENARIOS)

    summary_rows.append(row)

summary_df = pd.DataFrame(summary_rows)
summary_df.to_csv(TABLE_DIR / "m2_stress_summary.csv", index=False)
print(f"\n    Summary table saved.")

# ── By-quartile drop table ─────────────────────────────────────────
print("\n[3] Drop rate by job-size quartile ...")
q_boundaries = [int(n_req_arr.min())] + [int(q_cuts[i]) for i in range(3)] + [int(n_req_arr.max())]
print(f"    Quartile boundaries (n_required): {q_boundaries}")
print(f"    {'Fraction':>10}  {'Q1':>10}  {'Q2':>10}  {'Q3':>10}  {'Q4':>10}")
print(f"    {'':>10}  {'(<='+str(q_boundaries[1])+')':>10}  "
      f"{'(<='+str(q_boundaries[2])+')':>10}  "
      f"{'(<='+str(q_boundaries[3])+')':>10}  "
      f"{'(<='+str(q_boundaries[4])+')':>10}")
for _, r in summary_df.iterrows():
    print(f"    {r['avail_frac']:.0%}:        "
          f"  {r['q1_drop_rate_pct']:7.1f}%   "
          f"{r['q2_drop_rate_pct']:7.1f}%   "
          f"{r['q3_drop_rate_pct']:7.1f}%   "
          f"{r['q4_drop_rate_pct']:7.1f}%")

# ── Assemble JSON ───────────────────────────────────────────────────
n_req_quartile_boundaries = {
    "q1_max": int(q_cuts[0]),
    "q2_max": int(q_cuts[1]),
    "q3_max": int(q_cuts[2]),
    "q4_max": int(n_req_arr.max()),
}

by_fraction = []
for _, r in summary_df.iterrows():
    by_fraction.append({
        "avail_frac":     r["avail_frac"],
        "n_avail_nodes":  int(r["n_avail"]),
        "pct_feasible":   jf(r["pct_feasible"]),
        "drop_rate_pct":  jf(r["drop_rate_pct"]),
        "paired_fa_advantage": {
            "mean_delta_fa_fp_minus_random": jf(r["mean_delta_fa_fp_vs_random"]),
            "pct_jobs_fp_cooler": jf(r["pct_jobs_fp_cooler"]),
            "mean_fa_fp":    jf(r["mean_fa_fp"]),
            "mean_fa_random":jf(r["mean_fa_random"]),
        },
        "median_avail_req_ratio": jf(r["median_avail_req_ratio"]),
        "by_quartile": {
            f"q{q}": {
                "drop_rate_pct":   jf(r[f"q{q}_drop_rate_pct"]),
                "pct_feasible":    jf(r[f"q{q}_pct_feasible"]),
                "mean_delta_fa":   jf(r[f"q{q}_mean_delta_fa"]),
                "n_jobs_per_scen": int(r[f"q{q}_n_jobs_per_scen"]),
            }
            for q in range(1, 5)
        },
    })

result = {
    "script":    "r1_m2_stress_test.py",
    "git_sha":   git_sha(),
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "input_files": {
        "phase3a_fingerprint_2024.parquet": file_sha256(ANAL_DIR / "phase3a_fingerprint_2024.parquet"),
        "m2_test_job_availability.csv":     file_sha256(TABLE_DIR / "m2_test_job_availability.csv"),
    },
    "design": {
        "n_fp_nodes":        N_FP,
        "n_test_jobs":       n_jobs,
        "n_scenarios":       N_SCENARIOS,
        "avail_fractions":   AVAIL_FRACTIONS,
        "rng_seed_base":     RNG_SEED_BASE,
        "crn_note": (
            "Common random numbers: same available-node draw per (scenario, fraction) "
            "for both policies. Within available set, Random-cap-10 uses a per-(scenario, job) "
            "seed. FP-cap-10 always selects n_required nodes with lowest FA_2024 "
            "(deterministic given available set)."
        ),
        "fp_cap_10_note": (
            "FP-cap-10: select n_required nodes with lowest FA_2024 from available "
            "set. FA_2024 is the 2024-training frozen fingerprint. Lower FA = "
            "historically cooler node = more thermal headroom."
        ),
        "observed_occupancy_note": (
            "The 2025 test-job dataset captures jobs that ran, not true production "
            "occupancy at each instant. Observed n_available_fp (M2 base) is a "
            "LOWER BOUND on true occupancy. This stress test evaluates FP advantage "
            "at controlled synthetic occupancy levels (90% to 40%)."
        ),
        "n_required_quartile_boundaries": n_req_quartile_boundaries,
    },
    "by_available_fraction": by_fraction,
    "elapsed_seconds": round(time.time() - t0, 1),
}

out_path = OUT_DIR / "m2_stress_test.json"
with open(out_path, "w") as f:
    json.dump(result, f, indent=2)

print(f"\nSaved: {out_path}")
print(f"Total elapsed: {time.time()-t0:.1f}s")
