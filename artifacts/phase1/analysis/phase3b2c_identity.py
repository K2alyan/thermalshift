# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.2-C identity check: historical-assignment residual reconstruction.

Separates two effects:
  (A) Model calibration error -- residual model wrong even at historical nodes
  (B) Reassignment effect    -- random node reassignment changes true exposure

Protocol: use actual historical node assignments (not Random), permute empirical
residuals within each job. Should give E[B/B_hist] ~ 1, E[S/S_hist] ~ 1.

If (A) is small and (B) accounts for the ~4% Random gap, then the model is
well-calibrated and the difference seen in calibration is a real physical effect
of fingerprint composition, not a modelling artefact.
"""

import os
import json
import numpy as np
import pandas as pd
import time
from pathlib import Path

ANALYSIS_DIR    = Path(__file__).parent
DATA_DIR        = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))
BETA_F          = 0.9569
T_P95_THRESHOLD = 60.602770562770566
N_IDENT         = 20
IDENT_SEED_BASE = 55551

print("=== Phase 3B.2-C: Historical-assignment identity check ===")
print(f"  N_IDENT={N_IDENT}  using actual historical node assignments, permuted residuals\n")

# -----------------------------------------------------------------------
# Load
# -----------------------------------------------------------------------
fp_df      = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set = set(fp_df.index)
F_dict     = fp_df["FA_2024"].to_dict()
print(f"  Cohort: {len(cohort_set):,} nodes")

test_df = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")
print(f"  Test set: {len(test_df):,} node-job pairs, {test_df['job_idx'].nunique()} jobs")

print("  Loading run_time from job schedule...")
t0 = time.time()
sched = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet",
                        columns=["job_idx", "run_time"])
sched["job_idx_int"] = sched["job_idx"].astype(int)
rt_from_jobs = dict(zip(sched["job_idx_int"], sched["run_time"]))
print(f"  Done ({time.time()-t0:.1f}s)")

# -----------------------------------------------------------------------
# Job-level summary
# -----------------------------------------------------------------------
job_agg = (
    test_df.groupby("job_idx")
    .agg(
        F_hist_mean = ("F_2024", "mean"),
        T_p95_hist  = ("T_p95",  "mean"),
        hist_nodes  = ("node",   list),
        n_cohort    = ("node",   "count"),
    )
    .reset_index()
)
job_agg["run_time"] = job_agg["job_idx"].astype(int).map(rt_from_jobs)
job_agg["alpha_j"]  = job_agg["T_p95_hist"] - BETA_F * job_agg["F_hist_mean"]
print(f"  {len(job_agg)} base jobs")

# -----------------------------------------------------------------------
# Empirical residuals
# -----------------------------------------------------------------------
alpha_map        = job_agg.set_index("job_idx")["alpha_j"].to_dict()
test_res         = test_df.copy()
test_res["alpha_j"]  = test_res["job_idx"].map(lambda j: alpha_map.get(int(j), np.nan))
test_res["F_i"]      = test_res["node"].map(F_dict)
test_res["residual"] = (test_res["T_p95"]
                        - test_res["alpha_j"]
                        - BETA_F * test_res["F_i"])

job_residuals: dict[int, np.ndarray] = {}
for jid, grp in test_res.groupby("job_idx"):
    job_residuals[int(jid)] = grp["residual"].values.copy()

res_flat = test_res["residual"].dropna().values
print(f"  Residuals: mean={res_flat.mean():.4f}  SD={res_flat.std():.4f} degC")

# -----------------------------------------------------------------------
# Historical B and S (exact observed)
# -----------------------------------------------------------------------
rt_h_map     = {int(j): float(rt) / 3600.0
                for j, rt in zip(job_agg["job_idx"], job_agg["run_time"])}
test_res_rth = test_res["job_idx"].map(lambda j: rt_h_map.get(int(j), 0.0))
node_excess  = test_res["T_p95"] - T_P95_THRESHOLD
B_hist_node  = float((test_res_rth * (node_excess > 0)).sum())
S_hist_node  = float((test_res_rth * node_excess.clip(lower=0)).sum())
print(f"  B_hist_node = {B_hist_node:.1f} h    S_hist_node = {S_hist_node:.1f} degC-h\n")

# -----------------------------------------------------------------------
# Identity replay: historical nodes, permuted residuals
# -----------------------------------------------------------------------
print(f"Running {N_IDENT} identity scenarios (historical node assignments)...")
B_ratios: list[float] = []
S_ratios: list[float] = []

for scen in range(N_IDENT):
    rng   = np.random.default_rng(IDENT_SEED_BASE + scen)
    B_tot = 0.0
    S_tot = 0.0

    for _, jrow in job_agg.iterrows():
        jid        = int(jrow["job_idx"])
        rt_h       = float(jrow["run_time"]) / 3600.0
        alpha      = float(jrow["alpha_j"])
        hist_nodes = jrow["hist_nodes"]
        k          = len(hist_nodes)
        if k == 0 or not np.isfinite(rt_h):
            continue

        res  = job_residuals.get(jid, np.zeros(k))
        perm = rng.permutation(len(res))
        F_sel  = np.array([F_dict.get(n, 0.0) for n in hist_nodes])
        T_hats = alpha + BETA_F * F_sel + res[perm[:k]]

        excesses = T_hats - T_P95_THRESHOLD
        B_tot   += rt_h * float((excesses > 0).sum())
        S_tot   += rt_h * float(excesses.clip(min=0).sum())

    Br = B_tot / B_hist_node
    Sr = S_tot / S_hist_node
    B_ratios.append(Br)
    S_ratios.append(Sr)
    print(f"  Scen {scen+1:2d}/{N_IDENT}: B/Bh={Br:.4f}  S/Sh={Sr:.4f}")

B_mean = float(np.mean(B_ratios))
B_se   = float(np.std(B_ratios) / np.sqrt(N_IDENT))
S_mean = float(np.mean(S_ratios))
S_se   = float(np.std(S_ratios) / np.sqrt(N_IDENT))

print(f"\n  E[B_ratio] = {B_mean:.4f} +/- {B_se:.4f}  (target: ~1.0)")
print(f"  E[S_ratio] = {S_mean:.4f} +/- {S_se:.4f}  (target: ~1.0)")

if 0.97 <= B_mean <= 1.03 and 0.97 <= S_mean <= 1.03:
    verdict = "PASS (within 3%)"
elif 0.95 <= B_mean <= 1.05 and 0.95 <= S_mean <= 1.05:
    verdict = "PASS (within 5%)"
else:
    verdict = "FAIL -- investigate before proceeding"
print(f"\n  Identity check: {verdict}")

# -----------------------------------------------------------------------
# Attribution breakdown
# -----------------------------------------------------------------------
rand_B = 0.9632   # from phase3b2c calibration
rand_S = 0.9586
print(f"\n  Attribution summary:")
print(f"  Historical-assignment (identity):  E[B]={B_mean:.4f}  E[S]={S_mean:.4f}")
print(f"  Random-feasible (calibration):     E[B]={rand_B:.4f}  E[S]={rand_S:.4f}")
model_gap_B = 1.0 - B_mean
model_gap_S = 1.0 - S_mean
reassign_gap_B = B_mean - rand_B
reassign_gap_S = S_mean - rand_S
print(f"  Total gap vs hist (Random):        B={1-rand_B:.4f}  S={1-rand_S:.4f}")
print(f"  Of which model calibration error:  B={model_gap_B:.4f}  S={model_gap_S:.4f}")
print(f"  Of which reassignment effect:      B={reassign_gap_B:.4f}  S={reassign_gap_S:.4f}")

# -----------------------------------------------------------------------
# Save
# -----------------------------------------------------------------------
results = {
    "B_hist_node"        : B_hist_node,
    "S_hist_node"        : S_hist_node,
    "E_B_ratio"          : B_mean,
    "B_se"               : B_se,
    "E_S_ratio"          : S_mean,
    "S_se"               : S_se,
    "B_ratios"           : B_ratios,
    "S_ratios"           : S_ratios,
    "verdict"            : verdict,
    "random_B_ratio"     : rand_B,
    "random_S_ratio"     : rand_S,
    "model_calibration_gap_B" : model_gap_B,
    "model_calibration_gap_S" : model_gap_S,
    "reassignment_gap_B" : reassign_gap_B,
    "reassignment_gap_S" : reassign_gap_S,
}
outpath = ANALYSIS_DIR / "phase3b2c_identity.json"
with open(outpath, "w") as f:
    json.dump(results, f, indent=2)
print(f"\n  Saved {outpath}")
print("=== Done ===")
