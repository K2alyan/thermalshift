# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.1-H: Balanced Thermal Scheduling — utilization-constrained Pareto sweep.

Policy A: utilization-capped fingerprint.
  Greedy-coolest, but exclude nodes whose accumulated CF node-hours exceed
  (1+delta) x historical_fleet_average.  Sweep delta in {0.05, 0.10, 0.20, 0.30, 0.50, 1.00}.

Policy B: power-tiered selection (delta=20% cap enforced).
  Tier by job power percentile:
    < p50   : random from available  (low thermal risk)
    p50-p80 : exclude hottest 25% by fingerprint
    p80-p95 : select from coolest 50%
    > p95   : select from coolest 25%

Pareto output:
  x-axis: utilization Gini  (lower = more balanced)
  y-axis: historical-p95 threshold exceedance rate  (lower = better)
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import re, json, time
import os
from pathlib import Path

ANALYSIS_DIR = Path(__file__).parent
DATA_DIR     = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

BETA_F       = 0.9569
F_HOT_THRESH = 1.0
SEED         = 42
rng          = np.random.default_rng(SEED)

DELTA_SWEEP  = [0.05, 0.10, 0.20, 0.30, 0.50, 1.00]

print("=== Phase 3B.1-H: Balanced Thermal Scheduling ===\n")

# --------------------------------------------------------------------------
# Load data
# --------------------------------------------------------------------------
print("Loading fingerprints...")
fp_df        = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set   = set(fp_df.index)
F_dict       = fp_df["FA_2024"].to_dict()
F_vals       = fp_df["FA_2024"].values
cohort_list  = sorted(cohort_set)
# Indices that sort cohort by F ascending (coolest first)
F_sorted_cohort_idx = np.argsort([F_dict[n] for n in cohort_list])
print(f"  Cohort: {len(cohort_set):,} nodes")

print("Loading test set...")
test_df = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")

print("Loading full job schedule...")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"  {len(all_jobs):,} total jobs")

# --------------------------------------------------------------------------
# Section 0: Topology mapping (fixed break condition)
# --------------------------------------------------------------------------
print("\nSection 0: Building topology map (frontierNNNNN -> XE2 cabinet)...")
t0 = time.time()
_xe2_re = re.compile(r"x(\d+)c")
node_to_cabinet: dict[str, int] = {}

# Fix: only add cohort nodes; break when all cohort nodes are mapped
for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    for hn, xn in zip(hl, nl):
        if hn in cohort_set and hn not in node_to_cabinet:
            m = _xe2_re.match(xn)
            if m:
                node_to_cabinet[hn] = int(m.group(1))
    if len(node_to_cabinet) >= len(cohort_set):
        break

n_mapped = len(node_to_cabinet)
print(f"  Mapped {n_mapped}/{len(cohort_set)} cohort nodes  ({time.time()-t0:.1f}s)")
if n_mapped > 0:
    cabs = sorted(set(node_to_cabinet.values()))
    print(f"  Distinct cabinets: {len(cabs)}, range {min(cabs)}-{max(cabs)}")

# --------------------------------------------------------------------------
# Precompute schedule arrays (reuse logic from previous scripts)
# --------------------------------------------------------------------------
print("\nPrecomputing schedule arrays...")
t0 = time.time()
cohort_per_job: dict[int, frozenset] = {}
for jid, hl in zip(all_jobs["job_idx_int"].values, all_jobs["host_list"].values):
    cn = frozenset(n for n in hl if n in cohort_set)
    if cn:
        cohort_per_job[jid] = cn

has_cohort = np.array([jid in cohort_per_job for jid in all_jobs["job_idx_int"].values])
sched_jids = all_jobs["job_idx_int"].values[has_cohort]
sched_st   = all_jobs["start_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_et   = all_jobs["end_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_cn   = np.array([cohort_per_job[jid] for jid in sched_jids], dtype=object)
print(f"  {len(sched_jids):,} schedule entries  ({time.time()-t0:.1f}s)")

# --------------------------------------------------------------------------
# Build per-job test summary
# --------------------------------------------------------------------------
print("\nBuilding job-level test summary...")
job_agg = (
    test_df.groupby("job_idx")
    .agg(
        F_hist_mean=("F_2024", "mean"),
        n_cohort   =("node", "count"),
        T_p95_hist =("T_p95", "mean"),
        hist_nodes =("node", list),
    )
    .reset_index()
)
meta = (
    all_jobs[["job_idx_int", "node_count", "start_time", "end_time",
               "mean_power", "run_time"]]
    .rename(columns={"job_idx_int": "job_idx"})
)
job_agg = job_agg.merge(meta, on="job_idx", how="left")
job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)

# Power percentile thresholds for Policy B
p50_pwr, p80_pwr, p95_pwr = np.nanpercentile(job_agg["power_per_node"], [50, 80, 95])
print(f"  Power/node: p50={p50_pwr:.0f} W  p80={p80_pwr:.0f} W  p95={p95_pwr:.0f} W")

test_id_set = set(job_agg["job_idx"].astype(int))
jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)

# Historical utilization reference
hist_node_hours = {n: 0.0 for n in cohort_list}
for _, jrow in jobs_sorted.iterrows():
    rt_h = float(jrow["run_time"]) / 3600.0
    for n in jrow["hist_nodes"]:
        if n in hist_node_hours:
            hist_node_hours[n] += rt_h
hist_util_arr = np.array([hist_node_hours[n] for n in cohort_list])
hist_total_nh = hist_util_arr.sum()
hist_fleet_avg = hist_total_nh / len(cohort_list)
print(f"  Historical total node-hours: {hist_total_nh:.0f}")
print(f"  Historical fleet average:    {hist_fleet_avg:.2f} h/node")

# Empirical p95 threshold (from realism audit)
T_p95_threshold = float(np.percentile(jobs_sorted["T_p95_hist"].values, 95))
hist_p95_exceedance = float(
    (jobs_sorted["T_p95_hist"].values > T_p95_threshold).mean()
)
print(f"  Empirical p95 threshold: {T_p95_threshold:.2f} degC  "
      f"(hist exceedance = {hist_p95_exceedance:.3f})")

# Background busy precompute
print("\nPrecomputing background_busy...")
t0 = time.time()
is_test_sched = np.array([jid in test_id_set for jid in sched_jids])
bg_st  = sched_st[~is_test_sched]
bg_et  = sched_et[~is_test_sched]
bg_cn  = sched_cn[~is_test_sched]

bg_busy_per_job: dict[int, frozenset] = {}
for _, jrow in jobs_sorted.iterrows():
    jid = int(jrow["job_idx"])
    t_j = np.datetime64(
        pd.Timestamp(jrow["start_time"]).tz_convert("UTC").tz_localize(None), "ms"
    )
    mask = (bg_st <= t_j) & (bg_et > t_j)
    bg_busy_per_job[jid] = frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()
print(f"  Done  ({time.time()-t0:.1f}s)")

# --------------------------------------------------------------------------
# Utility functions
# --------------------------------------------------------------------------
def to_dt64(ts):
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

def gini(arr: np.ndarray) -> float:
    a = np.abs(np.sort(arr))
    n = len(a)
    if n == 0 or a.sum() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return (2 * (idx * a).sum() / (n * a.sum())) - (n + 1) / n

F_cohort_arr      = np.array([F_dict[n] for n in cohort_list])
F_cohort_sort_idx = np.argsort(F_cohort_arr)   # ascending (coolest first)

def tier_select(available: list, k: int, P_j: float, rng_local) -> list:
    """Power-tier node selection within the available pool (already cap-filtered)."""
    n_avail  = len(available)
    cap_k    = min(k, n_avail)
    avail_F  = np.array([F_dict[n] for n in available], dtype=float)
    order    = np.argsort(avail_F)       # coolest-first

    if np.isnan(P_j) or P_j < p50_pwr:
        # Random from full available pool
        idx = rng_local.choice(n_avail, size=cap_k, replace=False)
        return [available[i] for i in idx]
    elif P_j < p80_pwr:
        # Exclude hottest 25%; random from remaining 75%
        pool_end = max(cap_k, int(n_avail * 0.75))
        pool = order[:pool_end]
        pick = rng_local.choice(len(pool), size=cap_k, replace=False)
        return [available[pool[i]] for i in pick]
    elif P_j < p95_pwr:
        # Greedy-coolest from coolest 50%
        pool_end = max(cap_k, int(n_avail * 0.50))
        pool = order[:pool_end]
        return [available[pool[i]] for i in range(cap_k)]
    else:
        # Greedy-coolest from coolest 25%
        pool_end = max(cap_k, int(n_avail * 0.25))
        pool = order[:pool_end]
        return [available[pool[i]] for i in range(cap_k)]

def compute_metrics(job_results: list[dict], label: str) -> dict:
    """Aggregate per-job results into fleet-level metrics."""
    F_means  = [r["F_mean"] for r in job_results if not np.isnan(r["F_mean"])]
    F_hists  = [r["hist_F_mean"] for r in job_results if not np.isnan(r["F_mean"])]
    T_hists  = [r["T_p95_hist"] for r in job_results if not np.isnan(r["F_mean"])]
    util_arr = np.array([r.get("util_arr_snapshot", np.nan) for r in job_results
                         if "util_final" in r], dtype=object)

    # Get final utilization from the result dict
    util_final = job_results[-1]["util_final"]
    util_v     = np.array([util_final[n] for n in cohort_list])

    T_hat_arr      = np.array(T_hists) + BETA_F * (np.array(F_means) - np.array(F_hists))
    p95_exceed     = float((T_hat_arr > T_p95_threshold).mean())
    dT_pred        = float(BETA_F * (np.mean(F_hists) - np.mean(F_means)))
    g              = gini(util_v)
    n10            = len(cohort_list) // 10
    n20            = len(cohort_list) // 5
    cool10_share   = util_v[F_cohort_sort_idx[:n10]].sum() / util_v.sum() if util_v.sum() > 0 else np.nan
    n_infeas       = sum(1 for r in job_results if not r["feasible"])
    n_zero         = int((util_v == 0).sum())

    return {
        "label"           : label,
        "n_jobs"          : len(job_results),
        "mean_F_mean"     : float(np.mean(F_means)),
        "dT_pred_degC"    : dT_pred,
        "p95_exceedance"  : p95_exceed,
        "p95_exceedance_reduction": float(1 - p95_exceed / hist_p95_exceedance),
        "gini"            : g,
        "coolest10_share" : cool10_share,
        "max_node_hours"  : float(util_v.max()),
        "zero_work_nodes" : n_zero,
        "n_infeasible"    : n_infeas,
    }

# --------------------------------------------------------------------------
# Core stateful replay
# --------------------------------------------------------------------------
def stateful_replay(
    delta_cap: float,
    policy: str = "fingerprint",   # "fingerprint" | "random" | "tier"
    seed_offset: int = 0,
) -> list[dict]:
    """
    Stateful chronological replay with utilization cap.
    Cap per node = (1 + delta_cap) * hist_fleet_avg  [node-hours].
    Infeasible under cap -> fall back to uncapped available pool.
    """
    cap_per_node = (1 + delta_cap) * hist_fleet_avg
    cf_busy: dict[str, np.datetime64] = {}
    cf_util: dict[str, float] = {n: 0.0 for n in cohort_set}
    _rng = np.random.default_rng(SEED + seed_offset)
    results = []

    for _, jrow in jobs_sorted.iterrows():
        jid = int(jrow["job_idx"])
        t_j = to_dt64(jrow["start_time"])
        t_e = to_dt64(jrow["end_time"])
        rt_h = float(jrow["run_time"]) / 3600.0
        k    = int(jrow["n_cohort"])
        P_j  = float(jrow["power_per_node"]) if not pd.isnull(jrow["power_per_node"]) else np.nan

        bg_busy     = bg_busy_per_job[jid]
        cf_busy_now = frozenset(n for n, te in cf_busy.items() if te > t_j)

        # Available under cap
        avail_capped = [
            n for n in cohort_set
            if n not in bg_busy
            and n not in cf_busy_now
            and cf_util[n] < cap_per_node
        ]
        # Fallback if cap makes it infeasible
        if len(avail_capped) < k:
            avail_uncapped = [n for n in cohort_set
                              if n not in bg_busy and n not in cf_busy_now]
            available = avail_uncapped if len(avail_uncapped) >= k else avail_capped
            cap_active = False
        else:
            available = avail_capped
            cap_active = True

        n_avail  = len(available)
        feasible = n_avail >= k

        if n_avail == 0:
            selected = []
        elif policy == "fingerprint":
            avail_F = np.array([F_dict[n] for n in available])
            order   = np.argsort(avail_F)
            selected = [available[i] for i in order[:min(k, n_avail)]]
        elif policy == "tier":
            selected = tier_select(available, k, P_j, _rng)
        else:  # random
            cap_k = min(k, n_avail)
            idx   = _rng.choice(n_avail, size=cap_k, replace=False)
            selected = [available[i] for i in idx]

        for n in selected:
            cf_busy[n] = t_e
            cf_util[n] += rt_h

        F_sel = np.array([F_dict[n] for n in selected], dtype=float) if selected else np.array([np.nan])
        results.append({
            "job_idx"      : jid,
            "n_available"  : n_avail,
            "feasible"     : feasible,
            "cap_active"   : cap_active if selected else False,
            "F_mean"       : float(np.nanmean(F_sel)),
            "hist_F_mean"  : float(jrow["F_hist_mean"]),
            "T_p95_hist"   : float(jrow["T_p95_hist"]),
            "selected"     : list(selected),
            "util_final"   : dict(cf_util),  # snapshot for metrics (overwritten each iter)
        })

    return results

# --------------------------------------------------------------------------
# Reference baselines
# --------------------------------------------------------------------------
print("\nRunning reference baselines...")

# Historical (no replay needed — compute metrics directly)
hist_util_v = np.array([hist_node_hours[n] for n in cohort_list])
hist_p95_exceed_check = float(
    (jobs_sorted["T_p95_hist"].values > T_p95_threshold).mean()
)
n10 = len(cohort_list) // 10
hist_cool10 = hist_util_v[F_cohort_sort_idx[:n10]].sum() / hist_util_v.sum()
baseline_hist = {
    "label": "Historical",
    "dT_pred_degC": 0.0,
    "p95_exceedance": hist_p95_exceedance,
    "p95_exceedance_reduction": 0.0,
    "gini": gini(hist_util_v),
    "coolest10_share": hist_cool10,
    "max_node_hours": float(hist_util_v.max()),
    "zero_work_nodes": int((hist_util_v == 0).sum()),
    "n_infeasible": 0,
}
print(f"  Historical: Gini={baseline_hist['gini']:.3f}  "
      f"p95_exceed={baseline_hist['p95_exceedance']:.3f}  "
      f"cool10={baseline_hist['coolest10_share']:.3f}")

# Stateful fingerprint (no cap — delta=inf)
print("  Running stateful Fingerprint (no cap)...")
t0 = time.time()
fp_nocap_res = stateful_replay(delta_cap=1e6, policy="fingerprint")
fp_nocap_m   = compute_metrics(fp_nocap_res, "Fingerprint (no cap)")
print(f"  Fingerprint (no cap): dT={fp_nocap_m['dT_pred_degC']:+.3f}  "
      f"Gini={fp_nocap_m['gini']:.3f}  "
      f"p95_exceed={fp_nocap_m['p95_exceedance']:.3f}  ({time.time()-t0:.1f}s)")

# Stateful random (no cap)
print("  Running stateful Random (no cap)...")
t0 = time.time()
rnd_nocap_res = stateful_replay(delta_cap=1e6, policy="random", seed_offset=1)
rnd_nocap_m   = compute_metrics(rnd_nocap_res, "Random (no cap)")
print(f"  Random (no cap): dT={rnd_nocap_m['dT_pred_degC']:+.3f}  "
      f"Gini={rnd_nocap_m['gini']:.3f}  "
      f"p95_exceed={rnd_nocap_m['p95_exceedance']:.3f}  ({time.time()-t0:.1f}s)")

# --------------------------------------------------------------------------
# Policy A: utilization-capped fingerprint sweep
# --------------------------------------------------------------------------
print(f"\nPolicy A: utilization-capped fingerprint (delta sweep = {DELTA_SWEEP})...")
policy_a_metrics = []
for delta in DELTA_SWEEP:
    t0 = time.time()
    res = stateful_replay(delta_cap=delta, policy="fingerprint")
    m   = compute_metrics(res, f"FP-cap-{int(delta*100)}pct")
    policy_a_metrics.append(m)
    print(f"  delta={delta:.2f}: dT={m['dT_pred_degC']:+.3f}  Gini={m['gini']:.3f}  "
          f"p95_exceed={m['p95_exceedance']:.3f}  cool10={m['coolest10_share']:.3f}  "
          f"max_util={m['max_node_hours']:.1f}h  zero={m['zero_work_nodes']}  "
          f"infeas={m['n_infeasible']}  ({time.time()-t0:.1f}s)")

# --------------------------------------------------------------------------
# Policy B: power-tiered with delta=20% cap
# --------------------------------------------------------------------------
print("\nPolicy B: power-tiered (delta=20%)...")
t0 = time.time()
tier_res = stateful_replay(delta_cap=0.20, policy="tier")
tier_m   = compute_metrics(tier_res, "Power-tiered (delta=20%)")
print(f"  Tier (delta=20%): dT={tier_m['dT_pred_degC']:+.3f}  Gini={tier_m['gini']:.3f}  "
      f"p95_exceed={tier_m['p95_exceedance']:.3f}  cool10={tier_m['coolest10_share']:.3f}  "
      f"max_util={tier_m['max_node_hours']:.1f}h  zero={tier_m['zero_work_nodes']}  "
      f"({time.time()-t0:.1f}s)")

# Also run Policy B without cap (to see pure tier effect)
print("\nPolicy B no-cap:")
t0 = time.time()
tier_nc_res = stateful_replay(delta_cap=1e6, policy="tier", seed_offset=2)
tier_nc_m   = compute_metrics(tier_nc_res, "Power-tiered (no cap)")
print(f"  Tier (no cap):    dT={tier_nc_m['dT_pred_degC']:+.3f}  Gini={tier_nc_m['gini']:.3f}  "
      f"p95_exceed={tier_nc_m['p95_exceedance']:.3f}  cool10={tier_nc_m['coolest10_share']:.3f}  "
      f"({time.time()-t0:.1f}s)")

# --------------------------------------------------------------------------
# Summary table
# --------------------------------------------------------------------------
print("\n=== Summary table ===\n")
all_metrics = (
    [baseline_hist, rnd_nocap_m]
    + policy_a_metrics
    + [fp_nocap_m, tier_nc_m, tier_m]
)
hdr = (f"  {'Policy':<28}  {'dT_pred':>8}  {'p95_exceed':>10}  {'Gini':>6}  "
       f"{'cool10%':>8}  {'max_h':>7}  {'zero_n':>7}  {'infeas':>7}")
print(hdr)
print("  " + "-" * (len(hdr) - 2))
for m in all_metrics:
    label  = m["label"][:28]
    dT     = m.get("dT_pred_degC", 0.0)
    p95e   = m["p95_exceedance"]
    g      = m["gini"]
    c10    = m.get("coolest10_share", np.nan)
    maxh   = m.get("max_node_hours", np.nan)
    zerow  = m.get("zero_work_nodes", 0)
    infeas = m.get("n_infeasible", 0)
    print(f"  {label:<28}  {dT:+8.3f}  {p95e:10.3f}  {g:6.3f}  "
          f"{c10:8.3f}  {maxh:7.1f}  {zerow:7d}  {infeas:7d}")

# --------------------------------------------------------------------------
# Topology: cabinet count per job under each policy
# --------------------------------------------------------------------------
if n_mapped >= len(cohort_set) * 0.90:
    print("\n=== Topology: distinct cabinets per job ===\n")

    def n_cabinets(nodes):
        cabs = {node_to_cabinet.get(n, -1) for n in nodes}
        return len(cabs - {-1})

    fp20_res = [r for r in stateful_replay(delta_cap=0.20, policy="fingerprint")]
    fp20_m   = compute_metrics(fp20_res, "FP-cap-20%")

    hist_cabs_arr = np.array([n_cabinets(jrow["hist_nodes"])
                               for _, jrow in jobs_sorted.iterrows()])
    fp20_cabs_arr = np.array([n_cabinets(fp20_res[i]["selected"])
                               for i in range(len(jobs_sorted))])

    delta_cabs = fp20_cabs_arr - hist_cabs_arr
    print(f"  Historical:             mean={hist_cabs_arr.mean():.1f}  "
          f"p50={np.percentile(hist_cabs_arr,50):.1f}  "
          f"p95={np.percentile(hist_cabs_arr,95):.1f}  max={hist_cabs_arr.max()}")
    print(f"  Fingerprint-cap-20%:    mean={fp20_cabs_arr.mean():.1f}  "
          f"p50={np.percentile(fp20_cabs_arr,50):.1f}  "
          f"p95={np.percentile(fp20_cabs_arr,95):.1f}  max={fp20_cabs_arr.max()}")
    print(f"  Mean change:  {delta_cabs.mean():+.1f}  "
          f"more cabs: {(delta_cabs>0).mean():.1%}  "
          f"fewer: {(delta_cabs<0).mean():.1%}  "
          f"same: {(delta_cabs==0).mean():.1%}")

    # Add fp20 topology-restricted variant
    print("\n  Note: topology-constrained rerun deferred pending full network model.")
else:
    print(f"\n  Topology mapping incomplete ({n_mapped}/{len(cohort_set)} nodes).")
    print("  Cabinet analysis skipped.")

# --------------------------------------------------------------------------
# Pareto plot
# --------------------------------------------------------------------------
fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle("Phase 3B.1-H: Balanced thermal scheduling — Pareto frontier",
             fontsize=12, fontweight="bold")

# Pareto data points
pareto_points = [
    (baseline_hist["gini"],    baseline_hist["p95_exceedance"],    "Historical",         "#888888", "o", 10),
    (rnd_nocap_m["gini"],      rnd_nocap_m["p95_exceedance"],      "Random",             "#4488cc", "s", 8),
    (fp_nocap_m["gini"],       fp_nocap_m["p95_exceedance"],       "FP unconstrained",   "#dd4444", "D", 8),
    (tier_nc_m["gini"],        tier_nc_m["p95_exceedance"],        "Tier (no cap)",      "#aa44cc", "^", 8),
    (tier_m["gini"],           tier_m["p95_exceedance"],           "Tier (cap 20%)",     "#22aa55", "^", 10),
]
for i, m in enumerate(policy_a_metrics):
    d = DELTA_SWEEP[i]
    pareto_points.append(
        (m["gini"], m["p95_exceedance"], f"FP cap {int(d*100)}%", "#ee7722", "o", 6)
    )

ax = axes[0]
# Draw Policy A curve
a_ginis  = [m["gini"]         for m in policy_a_metrics]
a_p95s   = [m["p95_exceedance"] for m in policy_a_metrics]
ax.plot(a_ginis, a_p95s, "--", color="#ee7722", lw=1.2, alpha=0.7, zorder=1)

for g, p, label, color, marker, ms in pareto_points:
    ax.scatter(g, p, color=color, marker=marker, s=ms**2, zorder=3,
               label=label if "cap" not in label or "%" not in label or label in
               ["FP cap 10%", "FP cap 50%"] else None)
    if "Historical" in label or "unconstrained" in label or "Tier (cap" in label:
        ax.annotate(label, (g, p), textcoords="offset points",
                    xytext=(5, 4), fontsize=7)

# Annotate delta values along Policy A curve
for i, m in enumerate(policy_a_metrics):
    ax.annotate(f"{int(DELTA_SWEEP[i]*100)}%",
                (m["gini"], m["p95_exceedance"]),
                textcoords="offset points", xytext=(3, -9), fontsize=7,
                color="#ee7722")

ax.set_xlabel("Utilization Gini (lower = more balanced)")
ax.set_ylabel(f"p95 threshold exceedance rate\n(p95={T_p95_threshold:.1f} degC; lower = better)")
ax.set_title("A. Pareto: thermal benefit vs utilization balance")
ax.legend(fontsize=7, loc="upper left")
ax.axhline(baseline_hist["p95_exceedance"], color="#888888", lw=0.8, ls=":")
ax.axvline(baseline_hist["gini"], color="#888888", lw=0.8, ls=":")

# Panel B: thermal improvement vs Gini (delta sweep + tier)
ax = axes[1]
ax.plot([baseline_hist["gini"]] + a_ginis + [fp_nocap_m["gini"]],
        [0.0] + [m["dT_pred_degC"] for m in policy_a_metrics] + [fp_nocap_m["dT_pred_degC"]],
        "-o", color="#ee7722", label="Policy A (FP cap)", lw=2, markersize=5)

ax.scatter(tier_m["gini"], tier_m["dT_pred_degC"], color="#22aa55", marker="^",
           s=100, zorder=5, label="Tier (cap 20%)")
ax.scatter(tier_nc_m["gini"], tier_nc_m["dT_pred_degC"], color="#aa44cc", marker="^",
           s=80, zorder=5, label="Tier (no cap)")
ax.scatter(rnd_nocap_m["gini"], rnd_nocap_m["dT_pred_degC"], color="#4488cc",
           marker="s", s=64, zorder=5, label="Random")
ax.scatter(baseline_hist["gini"], 0, color="#888888", marker="o", s=100, zorder=5,
           label="Historical")

for i, m in enumerate(policy_a_metrics):
    ax.annotate(f"d={int(DELTA_SWEEP[i]*100)}%",
                (m["gini"], m["dT_pred_degC"]),
                textcoords="offset points", xytext=(4, 3), fontsize=7, color="#ee7722")

ax.set_xlabel("Utilization Gini (lower = more balanced)")
ax.set_ylabel("Mean predicted thermal improvement (degC)")
ax.set_title("B. Thermal gain vs utilization balance")
ax.legend(fontsize=8)
ax.axvline(baseline_hist["gini"], color="#888888", lw=0.8, ls=":")
ax.axhline(0, color="black", lw=0.6)

plt.tight_layout()
plt.savefig(ANALYSIS_DIR / "phase3b1h_pareto.png", dpi=150, bbox_inches="tight")
plt.close()
print("\nSaved phase3b1h_pareto.png")

# --------------------------------------------------------------------------
# Save outputs
# --------------------------------------------------------------------------
output_json = {
    "topology_mapped": n_mapped,
    "topology_cohort_total": len(cohort_set),
    "T_p95_threshold": T_p95_threshold,
    "hist_p95_exceedance": hist_p95_exceedance,
    "historical": baseline_hist,
    "random_nocap": rnd_nocap_m,
    "fingerprint_nocap": fp_nocap_m,
    "policy_A_sweep": policy_a_metrics,
    "policy_B_tier_nocap": tier_nc_m,
    "policy_B_tier_cap20": tier_m,
    "power_thresholds_W": {"p50": p50_pwr, "p80": p80_pwr, "p95": p95_pwr},
    "delta_sweep": DELTA_SWEEP,
    "hist_fleet_avg_node_hours": hist_fleet_avg,
}
with open(ANALYSIS_DIR / "phase3b1h_results.json", "w") as f:
    json.dump(output_json, f, indent=2, default=float)

print("Saved phase3b1h_results.json")
print("\nDone.")
