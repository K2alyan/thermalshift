# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.1  -  Same-start-time capacity-constrained counterfactual
Question: At each job's actual start time, could we have assigned thermally
cooler cohort nodes from those already idle, at zero scheduling delay?

Four policies applied to each 2025 test job:
  Historical        -  actual node assignment (observed)
  Random feasible   -  uniform random draw from Available(t_j)  &  cohort
  Fingerprint-only  -  coolest n_k nodes from Available by F_i
  ThermalShift      -  coolest n_k nodes by T^_i = beta_F·F_i + beta_P·(P_j - P_bar_fleet)
                     (reduces to F_i ranking under uniform within-job power)

Model coefficients from Phase 3A M2 (all months):
  beta_F = 0.9569,  beta_P = 0.014731 °C/W
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats
import json, time
import os
from pathlib import Path

ANALYSIS_DIR = Path(__file__).parent
DATA_DIR     = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

BETA_F        = 0.9569
BETA_P        = 0.014731
F_HOT_THRESH  = 1.0    # °C  -  "hot node"
T_RISK        = 60.0   # °C  -  headroom reference temperature
N_RAND_TRIALS = 100    # draws per job for Random policy (averaged)
SEED          = 42
rng           = np.random.default_rng(SEED)

print("=== Phase 3B.1: Same-start-time counterfactual ===\n")

# --------------------------------------------------------------------------
# Load data
# --------------------------------------------------------------------------
print("Loading fingerprints...")
fp_df      = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set = set(fp_df.index)
F_dict     = fp_df["FA_2024"].to_dict()
F_vals     = fp_df["FA_2024"].values
cohort_arr = np.array(list(fp_df.index))
fleet_F_p50 = float(np.median(F_vals))
print(f"  Cohort: {len(cohort_set):,} nodes, F in [{F_vals.min():.2f}, {F_vals.max():.2f}]"
      f"  median={fleet_F_p50:+.3f} degC")

print("Loading test set...")
test_df   = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")
n_tj      = test_df["job_idx"].nunique()
print(f"  {len(test_df):,} obs, {n_tj:,} jobs")

print("Loading full job schedule...")
all_jobs  = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"  {len(all_jobs):,} total jobs")

# --------------------------------------------------------------------------
# Precompute cohort node sets per job (single pass)
# --------------------------------------------------------------------------
print("\nPrecomputing cohort membership per job...")
t0 = time.time()
cohort_per_job: dict[int, frozenset] = {}
for jid, hl in zip(all_jobs["job_idx_int"].values, all_jobs["host_list"].values):
    cn = frozenset(n for n in hl if n in cohort_set)
    if cn:
        cohort_per_job[jid] = cn
print(f"  Jobs with >=1 cohort node: {len(cohort_per_job):,}  ({time.time()-t0:.1f}s)")

# Build compact schedule arrays (only jobs with cohort nodes)
has_cohort  = np.array([jid in cohort_per_job for jid in all_jobs["job_idx_int"].values])
sched_jids  = all_jobs["job_idx_int"].values[has_cohort]
# Strip tz and keep as datetime64[ms] for correct numpy comparisons
sched_st    = all_jobs["start_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_et    = all_jobs["end_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_cn    = np.array([cohort_per_job[jid] for jid in sched_jids], dtype=object)
print(f"  Schedule entries for time queries: {len(sched_jids):,}")

# --------------------------------------------------------------------------
# Build per-job test summary
# --------------------------------------------------------------------------
print("\nBuilding job-level test summary...")

job_agg = (
    test_df.groupby("job_idx")
    .agg(
        F_hist_mean=("F_2024", "mean"),
        F_hist_p95 =("F_2024", lambda x: float(np.percentile(x, 95))),
        F_hist_max =("F_2024", "max"),
        n_cohort   =("node", "count"),
        T_p95_hist =("T_p95", "mean"),
        hist_nodes =("node", list),
    )
    .reset_index()
)

# Join job metadata (node_count, start/end, power)
meta = (
    all_jobs[["job_idx_int", "node_count", "start_time", "end_time", "mean_power"]]
    .rename(columns={"job_idx_int": "job_idx"})
)
job_agg = job_agg.merge(meta, on="job_idx", how="left")
job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)

# Power quartile boundaries
p25, p50_pwr, p75 = np.nanpercentile(job_agg["power_per_node"], [25, 50, 75])
fleet_P_med       = p50_pwr
job_agg["pwr_q"]  = pd.cut(
    job_agg["power_per_node"],
    bins=[-np.inf, p25, p50_pwr, p75, np.inf],
    labels=["Q1_low", "Q2", "Q3", "Q4_high"],
)
print(f"  Power/node quartile boundaries: {p25:.0f} / {p50_pwr:.0f} / {p75:.0f} W")
print(f"  Jobs ready: {len(job_agg):,}")

# --------------------------------------------------------------------------
# Counterfactual main loop
# --------------------------------------------------------------------------
print("\nRunning counterfactual policies...")
t0  = time.time()
records = []
n_skip = n_infeasible = 0

for _, jrow in job_agg.iterrows():
    job_idx    = int(jrow["job_idx"])
    t_j        = jrow["start_time"]
    n_cohort   = int(jrow["n_cohort"])

    if n_cohort == 0 or pd.isnull(t_j):
        n_skip += 1
        continue

    hist_nodes = frozenset(jrow["hist_nodes"])
    F_hist_arr = np.array([F_dict[n] for n in hist_nodes if n in F_dict], dtype=float)
    if len(F_hist_arr) == 0:
        n_skip += 1
        continue

    # Strip tz from t_j for comparison with sched_st / sched_et (both datetime64[ms])
    t_j_dt = np.datetime64(pd.Timestamp(t_j).tz_convert("UTC").tz_localize(None), "ms")

    # Reconstruct Available(t_j): cohort nodes idle at t_j, from all other jobs
    concurrent = (sched_st <= t_j_dt) & (sched_et > t_j_dt) & (sched_jids != job_idx)
    if concurrent.any():
        busy_cohort = frozenset().union(*sched_cn[concurrent])
    else:
        busy_cohort = frozenset()

    # Available cohort = cohort - busy_by_other_jobs
    available = list(cohort_set - busy_cohort)
    n_avail   = len(available)
    k         = n_cohort   # number of cohort slots to fill

    rec = {
        "job_idx"       : job_idx,
        "n_cohort_hist" : n_cohort,
        "n_available"   : n_avail,
        "feasible"      : n_avail >= k,
        "power_per_node": float(jrow["power_per_node"]) if not pd.isnull(jrow["power_per_node"]) else np.nan,
        "pwr_q"         : str(jrow["pwr_q"]),
        "T_p95_hist"    : float(jrow["T_p95_hist"]),
        # Historical
        "hist_F_mean"   : float(np.mean(F_hist_arr)),
        "hist_F_p95"    : float(np.percentile(F_hist_arr, 95)),
        "hist_F_max"    : float(np.max(F_hist_arr)),
        "hist_hot_rate" : float(np.mean(F_hist_arr > F_HOT_THRESH)),
    }

    if n_avail < k:
        n_infeasible += 1
        for pol in ("rand", "fp", "ts"):
            for stat in ("F_mean", "F_p95", "F_max", "hot_rate"):
                rec[f"{pol}_{stat}"] = np.nan
    else:
        avail_F = np.array([F_dict[n] for n in available], dtype=float)
        P_j     = float(jrow["power_per_node"]) if not pd.isnull(jrow["power_per_node"]) else fleet_P_med

        # Random policy: average N_RAND_TRIALS draws
        rand_means, rand_p95s, rand_maxs, rand_hot = [], [], [], []
        for _ in range(N_RAND_TRIALS):
            idx = rng.choice(len(avail_F), size=k, replace=False)
            fv  = avail_F[idx]
            rand_means.append(np.mean(fv))
            rand_p95s.append(np.percentile(fv, 95))
            rand_maxs.append(np.max(fv))
            rand_hot.append(np.mean(fv > F_HOT_THRESH))
        rec["rand_F_mean"]   = float(np.mean(rand_means))
        rec["rand_F_p95"]    = float(np.mean(rand_p95s))
        rec["rand_F_max"]    = float(np.mean(rand_maxs))
        rec["rand_hot_rate"] = float(np.mean(rand_hot))

        # Fingerprint-only: k coolest nodes by F_i
        order_fp = np.argsort(avail_F)
        fp_F     = avail_F[order_fp[:k]]
        rec["fp_F_mean"]   = float(np.mean(fp_F))
        rec["fp_F_p95"]    = float(np.percentile(fp_F, 95))
        rec["fp_F_max"]    = float(np.max(fp_F))
        rec["fp_hot_rate"] = float(np.mean(fp_F > F_HOT_THRESH))

        # ThermalShift: k coolest by T^_i = beta_F·F_i + beta_P·(P_j - P_bar_fleet)
        T_hat    = BETA_F * avail_F + BETA_P * (P_j - fleet_P_med)
        order_ts = np.argsort(T_hat)
        ts_F     = avail_F[order_ts[:k]]
        rec["ts_F_mean"]   = float(np.mean(ts_F))
        rec["ts_F_p95"]    = float(np.percentile(ts_F, 95))
        rec["ts_F_max"]    = float(np.max(ts_F))
        rec["ts_hot_rate"] = float(np.mean(ts_F > F_HOT_THRESH))

    records.append(rec)

print(f"  Processed: {len(records):,} jobs  ({time.time()-t0:.1f}s)")
print(f"  Feasibility failures (available < needed): {n_infeasible:,}")
print(f"  Skipped (no cohort/metadata): {n_skip:,}")

res_df    = pd.DataFrame(records)
feas_df   = res_df[res_df["feasible"]].copy()
print(f"  Feasible jobs retained: {len(feas_df):,}")

# --------------------------------------------------------------------------
# Headroom: H_j_k = T_risk - T^_j_k
# T^_j_hist  = T_p95_hist (observed)
# T^_j_k     = T_p95_hist + beta_F·(F_k_mean - F_hist_mean)
# H_j_k      = T_risk - T^_j_k
# --------------------------------------------------------------------------
for pol, col in [("hist", "hist"), ("rand", "rand"), ("fp", "fp"), ("ts", "ts")]:
    feas_df[f"{pol}_T_hat"] = (
        feas_df["T_p95_hist"] + BETA_F * (feas_df[f"{col}_F_mean"] - feas_df["hist_F_mean"])
    )
    feas_df[f"{pol}_headroom"] = T_RISK - feas_df[f"{pol}_T_hat"]

# --------------------------------------------------------------------------
# Part 1  -  Fleet-level summary
# --------------------------------------------------------------------------
print("\n=== Part 1: Fleet-level summary ===\n")

policies = [
    ("hist", "Historical"),
    ("rand", "Random feasible"),
    ("fp",   "Fingerprint-only"),
    ("ts",   "ThermalShift"),
]

summary_rows = []
hdr = f"  {'Policy':<22}  {'F_mean':>7}  {'F_p95':>7}  {'hot_rate':>9}  {'deltaT_vs_hist':>11}  {'headroom':>9}"
print(hdr)
print("  " + "-" * (len(hdr) - 2))

for prefix, label in policies:
    sub  = feas_df[feas_df[f"{prefix}_F_mean"].notna()]
    fm   = float(sub[f"{prefix}_F_mean"].mean())
    fp95 = float(sub[f"{prefix}_F_p95"].mean())
    hr   = float(sub[f"{prefix}_hot_rate"].mean())
    hdm  = float(sub[f"{prefix}_headroom"].mean())
    if prefix == "hist":
        dt = 0.0
    else:
        dF = sub["hist_F_mean"] - sub[f"{prefix}_F_mean"]
        dt = float(BETA_F * dF.mean())
    s = {
        "label": label, "n_jobs": len(sub),
        "mean_F_mean": fm, "mean_F_p95": fp95,
        "hot_node_rate": hr, "dT_vs_hist": dt, "mean_headroom": hdm,
    }
    summary_rows.append(s)
    print(f"  {label:<22}  {fm:+7.3f}°C  {fp95:+7.3f}°C  {hr:9.3f}  {dt:+11.3f}°C  {hdm:9.3f}°C")

# --------------------------------------------------------------------------
# Part 2  -  Stratified by job power quartile
# --------------------------------------------------------------------------
print("\n=== Part 2: Thermal improvement by job power quartile ===\n")
print(f"  deltaT^ = beta_F × (F_hist_mean - F_policy_mean)  [°C, positive = cooling benefit]\n")

q_order = ["Q1_low", "Q2", "Q3", "Q4_high"]
q_rows  = {}
for prefix, label in [("rand", "Random"), ("fp", "Fingerprint"), ("ts", "ThermalShift")]:
    sub = feas_df[feas_df[f"{prefix}_F_mean"].notna()].copy()
    sub["dT"] = BETA_F * (sub["hist_F_mean"] - sub[f"{prefix}_F_mean"])
    grp = sub.groupby("pwr_q", observed=True)["dT"].agg(["mean", "median", "std"]).reindex(q_order)
    q_rows[label] = grp
    vals = "  ".join([f"{q}={grp.loc[q,'mean']:+.3f}°C" if q in grp.index else f"{q}=n/a"
                      for q in q_order])
    print(f"  {label:<14}: {vals}")

print()
print("  Job count per power quartile:")
qc = feas_df["pwr_q"].value_counts().reindex(q_order)
for q, c in qc.items():
    print(f"    {q}: {c}")

# --------------------------------------------------------------------------
# Part 3  -  Hot-node avoidance
# --------------------------------------------------------------------------
print(f"\n=== Part 3: Hot-node avoidance (F_max > {F_HOT_THRESH}°C) ===\n")
for prefix, label in policies:
    col = f"{prefix}_F_max"
    sub = feas_df[feas_df[col].notna()]
    rate_job = float((sub[col] > F_HOT_THRESH).mean())
    print(f"  {label:<22}: jobs with at least one hot node = {rate_job:.3f}")

print()
for prefix, label in [("rand", "Random"), ("fp", "Fingerprint"), ("ts", "ThermalShift")]:
    col  = f"{prefix}_hot_rate"
    sub  = feas_df[feas_df[col].notna()]
    reduction = float(
        (sub["hist_hot_rate"] - sub[col]).mean()
    )
    print(f"  {label:<14}: mean hot-node-rate reduction vs Historical = {reduction:+.3f}")

# --------------------------------------------------------------------------
# Part 4  -  Headroom distribution
# --------------------------------------------------------------------------
print(f"\n=== Part 4: Headroom H = {T_RISK}°C - T^ ===\n")
for prefix, label in policies:
    col = f"{prefix}_headroom"
    sub = feas_df[feas_df[col].notna()]
    hm  = float(sub[col].mean())
    hp5 = float(sub[col].quantile(0.05))
    print(f"  {label:<22}: mean headroom={hm:+.2f}°C  p5={hp5:+.2f}°C (p5 = worst-case jobs)")

# --------------------------------------------------------------------------
# Part 5  -  Fingerprint vs ThermalShift convergence
# --------------------------------------------------------------------------
print("\n=== Part 5: Fingerprint vs ThermalShift node-selection agreement ===\n")
diff = (feas_df["fp_F_mean"] - feas_df["ts_F_mean"]).abs().dropna()
print(f"  |F_fp_mean - F_ts_mean|: mean={diff.mean():.5f}°C, max={diff.max():.5f}°C")
print(f"  Near-zero confirms ranking equivalence under uniform within-job power.")
frac_same = float((diff < 0.001).mean())
print(f"  Fraction of jobs where policies select identical nodes: {frac_same:.3f}")

# --------------------------------------------------------------------------
# Part 6  -  Available-pool descriptives
# --------------------------------------------------------------------------
print("\n=== Part 6: Available pool and utilization ===\n")
print(f"  Mean available cohort nodes at job start: {feas_df['n_available'].mean():.0f}")
print(f"  Min / median / max: {feas_df['n_available'].min()} / "
      f"{feas_df['n_available'].median():.0f} / {feas_df['n_available'].max()}")
print(f"  Fraction of cohort idle (mean): {feas_df['n_available'].mean() / len(cohort_set):.3f}")

# --------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------
fig, axes = plt.subplots(2, 2, figsize=(12, 9))
fig.suptitle("Phase 3B.1  -  Same-start-time counterfactual", fontsize=13, fontweight="bold")

colors = {"Historical": "#666666", "Random feasible": "#4488cc",
          "Fingerprint-only": "#ee7722", "ThermalShift": "#22aa55"}

# Panel A: distribution of mean(F) per job, by policy
ax = axes[0, 0]
for prefix, label in policies:
    col = f"{prefix}_F_mean"
    sub = feas_df[col].dropna()
    ax.hist(sub, bins=40, alpha=0.55, label=label, color=colors[label], density=True)
ax.axvline(F_HOT_THRESH, color="red", lw=1.2, ls="--", label=f"F_hot={F_HOT_THRESH}°C")
ax.set_xlabel("Mean fingerprint of assigned cohort nodes (°C)")
ax.set_ylabel("Density")
ax.set_title("A. Distribution of mean(F) per job")
ax.legend(fontsize=8)

# Panel B: deltaT^ vs Historical by power quartile (Fingerprint and ThermalShift)
ax = axes[0, 1]
x   = np.arange(len(q_order))
w   = 0.32
for i, (prefix, label) in enumerate([("rand", "Random"), ("fp", "Fingerprint"), ("ts", "ThermalShift")]):
    sub = feas_df[feas_df[f"{prefix}_F_mean"].notna()].copy()
    sub["dT"] = BETA_F * (sub["hist_F_mean"] - sub[f"{prefix}_F_mean"])
    grp = sub.groupby("pwr_q", observed=True)["dT"].mean().reindex(q_order)
    ax.bar(x + (i - 1) * w, grp.values, width=w, label=label,
           color=list(colors.values())[i + 1], alpha=0.85)
ax.axhline(0, color="black", lw=0.8)
ax.set_xticks(x)
ax.set_xticklabels(q_order, fontsize=9)
ax.set_xlabel("Job power quartile")
ax.set_ylabel("Mean deltaT^ vs Historical (°C)")
ax.set_title("B. Cooling benefit by job power quartile")
ax.legend(fontsize=8)

# Panel C: Headroom CDF by policy
ax = axes[1, 0]
for prefix, label in policies:
    col = f"{prefix}_headroom"
    sub = feas_df[col].dropna().sort_values()
    cdf = np.arange(1, len(sub) + 1) / len(sub)
    ax.plot(sub.values, cdf, label=label, color=colors[label], lw=1.8)
ax.axvline(0, color="red", lw=1.2, ls="--", label="H = 0 (at T_risk)")
ax.set_xlabel(f"Headroom H = {T_RISK}°C - T^_j (°C)")
ax.set_ylabel("Cumulative fraction of jobs")
ax.set_title("C. Headroom CDF by policy")
ax.legend(fontsize=8)

# Panel D: Hot-node rate by power quartile (Hist vs Fingerprint)
ax = axes[1, 1]
for prefix, label in [("hist", "Historical"), ("fp", "Fingerprint-only"), ("ts", "ThermalShift")]:
    col = f"{prefix}_hot_rate"
    sub = feas_df[feas_df[col].notna()]
    grp = sub.groupby("pwr_q", observed=True)[col].mean().reindex(q_order)
    ax.plot(q_order, grp.values, marker="o", label=label, color=colors[label], lw=2)
ax.set_xlabel("Job power quartile")
ax.set_ylabel(f"Mean fraction of nodes with F > {F_HOT_THRESH}°C")
ax.set_title("D. Hot-node rate by power quartile")
ax.legend(fontsize=8)

plt.tight_layout()
plt.savefig(ANALYSIS_DIR / "phase3b1_counterfactual.png", dpi=150, bbox_inches="tight")
plt.close()
print("\nSaved phase3b1_counterfactual.png")

# --------------------------------------------------------------------------
# Save outputs
# --------------------------------------------------------------------------
output_json = {
    "policy_summary"     : summary_rows,
    "n_jobs_total"       : len(res_df),
    "n_jobs_feasible"    : len(feas_df),
    "n_jobs_infeasible"  : n_infeasible,
    "n_jobs_skipped"     : n_skip,
    "model_params"       : {"beta_F": BETA_F, "beta_P": BETA_P},
    "thresholds"         : {"F_hot": F_HOT_THRESH, "T_risk": T_RISK},
    "power_quartile_boundaries_W": {"p25": p25, "p50": p50_pwr, "p75": p75},
    "rand_policy_trials" : N_RAND_TRIALS,
}
with open(ANALYSIS_DIR / "phase3b1_results.json", "w") as f:
    json.dump(output_json, f, indent=2, default=float)

res_df.to_parquet(ANALYSIS_DIR / "phase3b1_job_results.parquet", index=False)
print("Saved phase3b1_results.json, phase3b1_job_results.parquet")
print("\nDone.")
