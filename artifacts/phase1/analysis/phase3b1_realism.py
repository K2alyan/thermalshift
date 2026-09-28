# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.1-R: Realism audit for same-start-time counterfactual.

Addresses five issues identified after the initial non-stateful run:
  1. Counterfactual state propagation (no double-booking across overlapping jobs)
  2. Utilization/wear concentration (Gini, p95/p50, coolest-N% fraction)
  3. Topology dispersion (distinct cabinets per job)
  4. Availability-pressure stratification (benefit vs A_j = n_avail / n_required)
  5. Empirical tail thresholds (replace fixed 60 degC with historical p90/p95/p99)

The key correction: Available^CF(t_j) = cohort - background_busy(t_j) - cf_test_busy(t_j)
where cf_test_busy tracks nodes already assigned to earlier overlapping test jobs
under the counterfactual policy.
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
BETA_P       = 0.014731
F_HOT_THRESH = 1.0
SEED         = 42
rng          = np.random.default_rng(SEED)

print("=== Phase 3B.1-R: Realism audit ===\n")

# --------------------------------------------------------------------------
# Load data
# --------------------------------------------------------------------------
print("Loading fingerprints...")
fp_df      = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set = set(fp_df.index)
F_dict     = fp_df["FA_2024"].to_dict()
F_vals     = fp_df["FA_2024"].values
cohort_list = sorted(cohort_set)
print(f"  Cohort: {len(cohort_set):,} nodes")

print("Loading test set...")
test_df  = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")
print(f"  {len(test_df):,} obs, {test_df['job_idx'].nunique():,} jobs")

print("Loading full job schedule...")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"  {len(all_jobs):,} total jobs")

print("Loading non-stateful results...")
ns_df = pd.read_parquet(ANALYSIS_DIR / "phase3b1_job_results.parquet")
print(f"  {len(ns_df):,} rows")

# --------------------------------------------------------------------------
# Build node -> cabinet mapping (XE2: x{cabinet}c{chassis}s{slot}b{board}n{node})
# --------------------------------------------------------------------------
print("\nBuilding topology map (frontierNNNNN -> XE2 cabinet)...")
t0 = time.time()
node_to_cabinet: dict[str, int] = {}
_xe2_re = re.compile(r"x(\d+)c")
for _, row in all_jobs.iterrows():
    hl = row["host_list"]
    nl = row["node_list"]
    if len(hl) != len(nl):
        continue
    for hn, xn in zip(hl, nl):
        if hn not in node_to_cabinet:
            m = _xe2_re.match(xn)
            if m:
                node_to_cabinet[hn] = int(m.group(1))
    if len(node_to_cabinet) >= len(cohort_set) * 1.1:
        break
n_mapped = sum(1 for n in cohort_set if n in node_to_cabinet)
print(f"  Cohort nodes with cabinet mapping: {n_mapped}/{len(cohort_set)}  ({time.time()-t0:.1f}s)")

# --------------------------------------------------------------------------
# Precompute cohort sets per job + schedule arrays
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
sched_rt   = all_jobs["run_time"].values[has_cohort]  # seconds
print(f"  Schedule entries: {len(sched_jids):,}  ({time.time()-t0:.1f}s)")

# --------------------------------------------------------------------------
# Build per-job test summary (same as phase3b1_counterfactual)
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
    all_jobs[["job_idx_int", "node_count", "start_time", "end_time", "mean_power", "run_time"]]
    .rename(columns={"job_idx_int": "job_idx"})
)
job_agg = job_agg.merge(meta, on="job_idx", how="left")
job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)
p25, p50_pwr, p75 = np.nanpercentile(job_agg["power_per_node"], [25, 50, 75])
fleet_P_med = p50_pwr
job_agg["pwr_q"] = pd.cut(
    job_agg["power_per_node"],
    bins=[-np.inf, p25, p50_pwr, p75, np.inf],
    labels=["Q1_low", "Q2", "Q3", "Q4_high"],
)
test_id_set = set(job_agg["job_idx"].astype(int))
print(f"  {len(job_agg):,} jobs")

# --------------------------------------------------------------------------
# Section 0: Test-job overlap diagnostic
# --------------------------------------------------------------------------
print("\n=== Section 0: Test-job overlap ===\n")
jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)
st_all = jobs_sorted["start_time"].values
et_all = jobs_sorted["end_time"].values
n_overlap_arr = np.zeros(len(jobs_sorted), dtype=int)
for i in range(len(jobs_sorted)):
    mask = (st_all < et_all[i]) & (et_all > st_all[i])
    mask[i] = False
    n_overlap_arr[i] = mask.sum()
print(f"  Test jobs with 0 overlapping test jobs: {(n_overlap_arr==0).sum():,} "
      f"({(n_overlap_arr==0).mean():.1%})")
print(f"  Test jobs with 1+ overlapping:          {(n_overlap_arr>0).sum():,} "
      f"({(n_overlap_arr>0).mean():.1%})")
print(f"  Test jobs with 5+ overlapping:          {(n_overlap_arr>=5).sum():,}")
print(f"  Max simultaneous test jobs:             {n_overlap_arr.max()}")
print(f"  --> Non-stateful result is an oracle artifact; stateful replay required.")

# --------------------------------------------------------------------------
# Section 1: Stateful replay setup
# Split schedule into background (non-test) and test-job entries
# --------------------------------------------------------------------------
print("\nSplitting schedule into background / test entries...")
is_test_sched = np.array([jid in test_id_set for jid in sched_jids])
bg_jids = sched_jids[~is_test_sched]
bg_st   = sched_st[~is_test_sched]
bg_et   = sched_et[~is_test_sched]
bg_cn   = sched_cn[~is_test_sched]
print(f"  Background schedule entries: {len(bg_jids):,}")
print(f"  Test-job schedule entries:   {is_test_sched.sum():,}")

# Precompute background_busy for each test job (fixed regardless of policy)
print("Precomputing background_busy per test job...")
t0 = time.time()
bg_busy_per_job: dict[int, frozenset] = {}
for _, jrow in jobs_sorted.iterrows():
    jid = int(jrow["job_idx"])
    t_j = np.datetime64(
        pd.Timestamp(jrow["start_time"]).tz_convert("UTC").tz_localize(None), "ms"
    )
    mask = (bg_st <= t_j) & (bg_et > t_j)
    bg_busy_per_job[jid] = frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()
print(f"  Done  ({time.time()-t0:.1f}s)")

def to_dt64(ts):
    """Convert pandas Timestamp (possibly tz-aware) to numpy datetime64[ms]."""
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

# --------------------------------------------------------------------------
# Stateful replay function
# --------------------------------------------------------------------------
def stateful_replay(policy: str, n_rand_jobs: int = 1) -> list[dict]:
    """
    Chronological stateful replay of one policy over test jobs.
    Returns list of per-job result dicts.
    policy: 'fingerprint' or 'random'
    """
    cf_busy: dict[str, np.datetime64] = {}  # {node: cf_end_time}
    results = []
    _rng = np.random.default_rng(SEED)

    for _, jrow in jobs_sorted.iterrows():
        jid  = int(jrow["job_idx"])
        t_j  = to_dt64(jrow["start_time"])
        t_e  = to_dt64(jrow["end_time"])
        k    = int(jrow["n_cohort"])

        bg_busy = bg_busy_per_job[jid]
        # CF busy: nodes assigned to earlier CF test jobs still running
        cf_busy_now = frozenset(n for n, te in cf_busy.items() if te > t_j)

        available = [n for n in cohort_set if n not in bg_busy and n not in cf_busy_now]
        n_avail   = len(available)
        feasible  = n_avail >= k

        if n_avail == 0:
            selected = []
        elif policy == "fingerprint":
            avail_F  = np.array([F_dict[n] for n in available])
            order    = np.argsort(avail_F)
            cap      = min(k, n_avail)
            selected = [available[i] for i in order[:cap]]
        elif policy == "random":
            cap      = min(k, n_avail)
            idx      = _rng.choice(n_avail, size=cap, replace=False)
            selected = [available[i] for i in idx]
        else:
            raise ValueError(policy)

        # Reserve nodes for the duration of this job
        for n in selected:
            cf_busy[n] = t_e

        F_sel = np.array([F_dict[n] for n in selected], dtype=float) if selected else np.array([np.nan])

        results.append({
            "job_idx"      : jid,
            "n_available"  : n_avail,
            "n_selected"   : len(selected),
            "feasible"     : feasible,
            "F_mean"       : float(np.nanmean(F_sel)),
            "F_p95"        : float(np.nanpercentile(F_sel, 95)),
            "F_max"        : float(np.nanmax(F_sel)),
            "hot_rate"     : float(np.nanmean(F_sel > F_HOT_THRESH)),
            "selected"     : selected,
        })
    return results

print("\nRunning stateful Fingerprint replay...")
t0 = time.time()
fp_stat_results = stateful_replay("fingerprint")
print(f"  Done  ({time.time()-t0:.1f}s)")

print("Running stateful Random replay...")
t0 = time.time()
rnd_stat_results = stateful_replay("random")
print(f"  Done  ({time.time()-t0:.1f}s)")

fp_stat_df  = pd.DataFrame(fp_stat_results).set_index("job_idx")
rnd_stat_df = pd.DataFrame(rnd_stat_results).set_index("job_idx")

# --------------------------------------------------------------------------
# Section 2: Stateful vs non-stateful comparison
# --------------------------------------------------------------------------
print("\n=== Section 1: Stateful vs non-stateful comparison ===\n")

# Merge non-stateful Fingerprint results
ns = ns_df.set_index("job_idx")
compare = pd.DataFrame({
    "fp_ns_F_mean"   : ns["fp_F_mean"],
    "fp_stat_F_mean" : fp_stat_df["F_mean"],
    "hist_F_mean"    : ns["hist_F_mean"],
    "n_avail_ns"     : ns["n_available"],
    "n_avail_stat"   : fp_stat_df["n_available"],
}).dropna()

dT_ns   = BETA_F * (compare["hist_F_mean"] - compare["fp_ns_F_mean"])
dT_stat = BETA_F * (compare["hist_F_mean"] - compare["fp_stat_F_mean"])

print(f"  Non-stateful Fingerprint: mean delta_T_pred = {dT_ns.mean():+.3f} degC")
print(f"  Stateful    Fingerprint:  mean delta_T_pred = {dT_stat.mean():+.3f} degC")
print(f"  Overestimate (NS - stateful): {(dT_ns - dT_stat).mean():+.3f} degC")
print()
print("  Available pool comparison:")
print(f"    Non-stateful available (mean): {compare['n_avail_ns'].mean():.0f} "
      f"(historical idle)")
print(f"    Stateful    available (mean):  {compare['n_avail_stat'].mean():.0f} "
      f"(after CF reservations)")
print()

# Hot-node rate
hn_ns   = (ns["fp_F_max"] > F_HOT_THRESH).mean()
hn_stat = (fp_stat_df["F_max"] > F_HOT_THRESH).mean()
print(f"  Hot-node job rate (F_max > {F_HOT_THRESH} degC):")
print(f"    Non-stateful Fingerprint: {hn_ns:.3f}")
print(f"    Stateful    Fingerprint:  {hn_stat:.3f}")
print(f"    Historical:               {(ns['hist_F_max'] > F_HOT_THRESH).mean():.3f}")

# Infeasibility in stateful
n_infeas_stat = (~fp_stat_df["feasible"]).sum()
print(f"\n  Stateful infeasibility: {n_infeas_stat:,} jobs "
      f"({n_infeas_stat/len(fp_stat_df):.1%})")

# --------------------------------------------------------------------------
# Section 3: Utilization / wear concentration
# --------------------------------------------------------------------------
print("\n=== Section 2: Utilization concentration ===\n")

def node_utilization(assignment_list: list[tuple[list[str], float]]) -> np.ndarray:
    """
    assignment_list: list of (selected_nodes, run_time_s) per job.
    Returns array of node-hours per cohort node (ordered by cohort_list).
    """
    node_h = {n: 0.0 for n in cohort_list}
    for nodes, rt in assignment_list:
        hrs = rt / 3600.0
        for n in nodes:
            if n in node_h:
                node_h[n] += hrs
    return np.array([node_h[n] for n in cohort_list])

def gini(arr: np.ndarray) -> float:
    a = np.abs(np.sort(arr))
    n = len(a)
    if n == 0 or a.sum() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return (2 * (idx * a).sum() / (n * a.sum())) - (n + 1) / n

# Historical utilization: from test_df
hist_assign = []
for _, jrow in jobs_sorted.iterrows():
    jid  = int(jrow["job_idx"])
    rt   = float(jrow["run_time"])
    hn   = list(frozenset(jrow["hist_nodes"]))
    hist_assign.append((hn, rt))

hist_util = node_utilization(hist_assign)

# Fingerprint stateful utilization
fp_assign = []
for _, jrow in jobs_sorted.iterrows():
    jid = int(jrow["job_idx"])
    rt  = float(jrow["run_time"])
    sel = fp_stat_df.loc[jid, "selected"] if jid in fp_stat_df.index else []
    fp_assign.append((sel, rt))

fp_util = node_utilization(fp_assign)

# Sort cohort by F_i (coldest first)
F_sorted_idx = np.argsort(F_vals)  # fp_df sorted by FA_2024 ascending
hist_util_fsort = hist_util[F_sorted_idx]
fp_util_fsort   = fp_util[F_sorted_idx]

def util_stats(util_arr, label):
    total = util_arr.sum()
    n     = len(util_arr)
    n_used = (util_arr > 0).sum()
    p50, p95 = np.percentile(util_arr, [50, 95])
    g = gini(util_arr)
    # Fraction assigned to coolest 10% / 20%
    n10 = max(1, n // 10)
    n20 = max(1, n // 5)
    frac10 = util_arr[F_sorted_idx[:n10]].sum() / total if total > 0 else np.nan
    frac20 = util_arr[F_sorted_idx[:n20]].sum() / total if total > 0 else np.nan
    print(f"  {label}:")
    print(f"    Total node-hours assigned: {total:.0f}")
    print(f"    Nodes used (>0 hours):     {n_used}/{n}")
    print(f"    Max node-hours:            {util_arr.max():.1f}")
    print(f"    p50 / p95 node-hours:      {p50:.1f} / {p95:.1f}")
    print(f"    Gini coefficient:          {g:.3f}  (0=perfectly equal, 1=fully concentrated)")
    print(f"    Coolest-10%% share of work: {frac10:.3f}  (expected {0.10:.3f} if uniform)")
    print(f"    Coolest-20%% share of work: {frac20:.3f}  (expected {0.20:.3f} if uniform)")
    return g, frac10, frac20

g_hist, f10_hist, f20_hist = util_stats(hist_util, "Historical")
print()
g_fp, f10_fp, f20_fp = util_stats(fp_util, "Fingerprint (stateful)")

# --------------------------------------------------------------------------
# Section 4: Topology dispersion
# --------------------------------------------------------------------------
print("\n=== Section 3: Topology dispersion ===\n")

def n_cabinets(nodes: list[str]) -> int:
    cabs = set(node_to_cabinet.get(n, -1) for n in nodes)
    return len(cabs - {-1})

hist_cabs = np.array([n_cabinets(jrow["hist_nodes"]) for _, jrow in jobs_sorted.iterrows()])
fp_cabs   = np.array([n_cabinets(fp_stat_df.loc[int(jrow["job_idx"]), "selected"])
                      for _, jrow in jobs_sorted.iterrows()])

print(f"  {'Policy':<28}  {'mean cabs':>9}  {'p50':>6}  {'p95':>6}  {'max':>5}")
print(f"  {'-'*54}")
for arr, label in [(hist_cabs, "Historical"), (fp_cabs, "Fingerprint (stateful)")]:
    m = arr.mean(); p5 = np.percentile(arr, 50); p9 = np.percentile(arr, 95)
    print(f"  {label:<28}  {m:9.1f}  {p5:6.1f}  {p9:6.1f}  {arr.max():5d}")

delta_cabs = fp_cabs - hist_cabs
print(f"\n  Mean cabinet-count change (FP - Hist): {delta_cabs.mean():+.1f}")
print(f"  Fraction of jobs with more cabinets:   {(delta_cabs > 0).mean():.3f}")
print(f"  Fraction of jobs with fewer cabinets:  {(delta_cabs < 0).mean():.3f}")
print(f"  Fraction unchanged:                    {(delta_cabs == 0).mean():.3f}")

# --------------------------------------------------------------------------
# Section 5: Availability-pressure stratification
# --------------------------------------------------------------------------
print("\n=== Section 4: Availability-pressure stratification ===\n")

stat_df = fp_stat_df.copy().reset_index()
stat_df = stat_df.merge(jobs_sorted[["job_idx", "n_cohort", "F_hist_mean"]], on="job_idx")
stat_df["A_j"] = stat_df["n_available"] / stat_df["n_cohort"].clip(lower=1)
stat_df["dT_stat"] = BETA_F * (stat_df["F_hist_mean"] - stat_df["F_mean"])

bins   = [0, 1.5, 3.0, 10.0, np.inf]
labels = ["<1.5 (very constrained)", "1.5-3 (constrained)", "3-10 (moderate)", ">10 (abundant)"]
stat_df["pressure_bin"] = pd.cut(stat_df["A_j"], bins=bins, labels=labels)

print(f"  {'Availability pressure':28}  {'n_jobs':>7}  {'n_avail med':>11}  "
      f"{'dT_pred mean':>12}  {'infeasible':>10}")
for lbl in labels:
    sub = stat_df[stat_df["pressure_bin"] == lbl]
    n_inf = (~sub["feasible"]).sum()
    if len(sub) == 0:
        continue
    print(f"  {lbl:<28}  {len(sub):7d}  {sub['n_available'].median():11.0f}  "
          f"{sub['dT_stat'].mean():+12.3f}  {n_inf:10d}")

# --------------------------------------------------------------------------
# Section 6: Empirical tail thresholds (replace fixed 60 degC)
# --------------------------------------------------------------------------
print("\n=== Section 5: Empirical analysis thresholds ===\n")

T_obs = jobs_sorted["T_p95_hist"].values
T_p90 = float(np.percentile(T_obs, 90))
T_p95 = float(np.percentile(T_obs, 95))
T_p99 = float(np.percentile(T_obs, 99))

print(f"  Historical T_p95 distribution:")
print(f"    p50={np.percentile(T_obs,50):.2f}  p90={T_p90:.2f}  p95={T_p95:.2f}  p99={T_p99:.2f} degC")
print()

# For each threshold, compute exceedance rates under Historical and Fingerprint (stateful)
# Fingerprint T_hat: T_p95_hist + beta_F*(F_fp - F_hist)
T_hat_fp = (jobs_sorted["T_p95_hist"].values
            + BETA_F * (fp_stat_df["F_mean"].values - jobs_sorted["F_hist_mean"].values))

print(f"  {'Threshold':>10}  {'Hist exceed':>13}  {'FP exceed':>13}  {'Reduction':>12}")
print(f"  {'-'*52}")
for thresh, label in [(T_p90, f"p90={T_p90:.1f}C"), (T_p95, f"p95={T_p95:.1f}C"),
                       (T_p99, f"p99={T_p99:.1f}C")]:
    e_hist = float((T_obs > thresh).mean())
    e_fp   = float((T_hat_fp > thresh).mean())
    red    = 1 - e_fp / e_hist if e_hist > 0 else np.nan
    print(f"  {label:>10}  {e_hist:13.3f}  {e_fp:13.3f}  {red:11.1%}")

# --------------------------------------------------------------------------
# Key summary table
# --------------------------------------------------------------------------
print("\n=== Summary: Stateful results vs Historical ===\n")
hist_Fm  = ns["hist_F_mean"].mean()
rnd_Fm   = rnd_stat_df["F_mean"].mean()
fp_Fm    = fp_stat_df["F_mean"].mean()
hist_hr  = (ns["hist_F_max"] > F_HOT_THRESH).mean()
rnd_hr   = (rnd_stat_df["F_max"] > F_HOT_THRESH).mean()
fp_hr    = (fp_stat_df["F_max"] > F_HOT_THRESH).mean()
dT_rnd   = BETA_F * (ns["hist_F_mean"].values - rnd_stat_df["F_mean"].values)
dT_fp    = BETA_F * (ns["hist_F_mean"].values - fp_stat_df["F_mean"].values)

print(f"  {'Policy':<28}  {'F_mean':>8}  {'hot_rate':>9}  {'dT_pred':>8}")
print(f"  {'-'*58}")
print(f"  {'Historical':<28}  {hist_Fm:+8.3f}  {hist_hr:9.3f}  {'---':>8}")
print(f"  {'Random (stateful)':<28}  {rnd_Fm:+8.3f}  {rnd_hr:9.3f}  {dT_rnd.mean():+8.3f} degC")
print(f"  {'Fingerprint (stateful)':<28}  {fp_Fm:+8.3f}  {fp_hr:9.3f}  {dT_fp.mean():+8.3f} degC")
print()
print(f"  Non-stateful Fingerprint had dT_pred = {dT_ns.mean():+.3f} degC "
      f"(oracle overestimate: {(dT_ns - dT_stat).mean():+.3f} degC)")

# --------------------------------------------------------------------------
# Plots
# --------------------------------------------------------------------------
fig, axes = plt.subplots(2, 3, figsize=(16, 10))
fig.suptitle("Phase 3B.1-R: Realism audit", fontsize=13, fontweight="bold")

# Panel A: Stateful vs non-stateful dT per job
ax = axes[0, 0]
ax.scatter(dT_ns.values, dT_stat.values, alpha=0.3, s=8, color="#2255aa")
lim = max(dT_ns.max(), dT_stat.max()) * 1.05
ax.plot([0, lim], [0, lim], "k--", lw=1, label="y = x (no overestimate)")
ax.set_xlabel("Non-stateful delta_T_pred per job (degC)")
ax.set_ylabel("Stateful delta_T_pred per job (degC)")
ax.set_title("A. Stateful vs non-stateful (Fingerprint)")
ax.legend(fontsize=8)

# Panel B: Node utilization CDF (Fingerprint vs Historical)
ax = axes[0, 1]
for arr, label, color in [
    (hist_util, "Historical", "#666666"),
    (fp_util,   "Fingerprint (stateful)", "#ee7722"),
]:
    s   = np.sort(arr)
    cdf = np.arange(1, len(s)+1) / len(s)
    ax.plot(s, cdf, label=label, color=color, lw=1.8)
ax.set_xlabel("Node-hours assigned in 2025 test period")
ax.set_ylabel("CDF over cohort nodes")
ax.set_title("B. Utilization CDF by policy")
ax.legend(fontsize=8)

# Panel C: Lorenz curve (coolest -> hottest node cumulative share of work)
ax = axes[0, 2]
for arr_fsort, label, color in [
    (hist_util_fsort, "Historical", "#666666"),
    (fp_util_fsort,   "Fingerprint (stateful)", "#ee7722"),
]:
    cumshare = np.cumsum(arr_fsort) / (arr_fsort.sum() + 1e-12)
    x = np.linspace(0, 1, len(cumshare))
    ax.plot(x, cumshare, label=label, color=color, lw=1.8)
ax.plot([0, 1], [0, 1], "k--", lw=1, label="Perfect equality")
ax.set_xlabel("Fraction of nodes (coolest -> hottest F_i)")
ax.set_ylabel("Cumulative fraction of node-hours")
ax.set_title("C. Lorenz curve (ordered by F_i, cool-to-hot)")
ax.legend(fontsize=8)

# Panel D: dT vs availability pressure scatter
ax = axes[1, 0]
ax.scatter(stat_df["A_j"].clip(upper=30), stat_df["dT_stat"],
           alpha=0.3, s=8, color="#22aa55")
ax.axhline(0, color="red", lw=1, ls="--")
ax.set_xlabel("Availability ratio A_j = n_available / n_required")
ax.set_ylabel("Stateful delta_T_pred (degC)")
ax.set_title("D. Thermal benefit vs availability pressure")
ax.set_xlim(left=0)

# Panel E: Cabinet count change histogram
ax = axes[1, 1]
ax.hist(delta_cabs, bins=range(delta_cabs.min()-1, delta_cabs.max()+2), color="#4488cc", alpha=0.8)
ax.axvline(0, color="red", lw=1.5, ls="--", label="No change")
ax.set_xlabel("Cabinet count change: Fingerprint - Historical")
ax.set_ylabel("Number of jobs")
ax.set_title("E. Topology dispersion (cabinet count delta)")
ax.legend(fontsize=8)

# Panel F: Empirical threshold exceedance rates
ax = axes[1, 2]
thresholds = np.linspace(T_obs.min(), T_obs.max(), 60)
e_hist_arr = [(T_obs > t).mean() for t in thresholds]
e_fp_arr   = [(T_hat_fp > t).mean() for t in thresholds]
ax.plot(thresholds, e_hist_arr, label="Historical", color="#666666", lw=2)
ax.plot(thresholds, e_fp_arr,   label="Fingerprint (stateful)", color="#ee7722", lw=2)
for tv, lbl in [(T_p90, "p90"), (T_p95, "p95"), (T_p99, "p99")]:
    ax.axvline(tv, color="gray", lw=0.8, ls=":")
    ax.text(tv + 0.1, 0.5, lbl, fontsize=7, color="gray")
ax.set_xlabel("Temperature threshold (degC)")
ax.set_ylabel("Fraction of jobs exceeding threshold")
ax.set_title("F. Empirical threshold exceedance rates")
ax.legend(fontsize=8)

plt.tight_layout()
plt.savefig(ANALYSIS_DIR / "phase3b1_realism.png", dpi=150, bbox_inches="tight")
plt.close()
print("\nSaved phase3b1_realism.png")

# --------------------------------------------------------------------------
# Save outputs
# --------------------------------------------------------------------------
stat_out = fp_stat_df.drop(columns=["selected"], errors="ignore").reset_index()
stat_out.to_parquet(ANALYSIS_DIR / "phase3b1_fingerprint_stateful.parquet", index=False)

output_json = {
    "stateful_vs_nonstateful": {
        "dT_pred_nonstateful": float(dT_ns.mean()),
        "dT_pred_stateful":    float(dT_stat.mean()),
        "oracle_overestimate": float((dT_ns - dT_stat).mean()),
    },
    "test_job_overlap": {
        "n_jobs_no_overlap":   int((n_overlap_arr == 0).sum()),
        "n_jobs_some_overlap": int((n_overlap_arr > 0).sum()),
        "max_simultaneous":    int(n_overlap_arr.max()),
    },
    "stateful_summary": {
        "Historical_F_mean":   float(hist_Fm),
        "Random_F_mean":       float(rnd_Fm),
        "Fingerprint_F_mean":  float(fp_Fm),
        "Historical_hot_rate": float(hist_hr),
        "Random_hot_rate":     float(rnd_hr),
        "Fingerprint_hot_rate": float(fp_hr),
        "dT_pred_Random_degC":      float(dT_rnd.mean()),
        "dT_pred_Fingerprint_degC": float(dT_fp.mean()),
    },
    "utilization": {
        "Historical_Gini":  float(g_hist),
        "Fingerprint_Gini": float(g_fp),
        "Historical_coolest10pct_share":  float(f10_hist),
        "Fingerprint_coolest10pct_share": float(f10_fp),
        "Historical_coolest20pct_share":  float(f20_hist),
        "Fingerprint_coolest20pct_share": float(f20_fp),
    },
    "topology": {
        "hist_mean_cabinets":    float(hist_cabs.mean()),
        "fp_stat_mean_cabinets": float(fp_cabs.mean()),
        "mean_cabinet_delta":    float(delta_cabs.mean()),
        "frac_jobs_more_cabs":   float((delta_cabs > 0).mean()),
    },
    "empirical_thresholds": {
        "T_p90": T_p90, "T_p95": T_p95, "T_p99": T_p99,
        "exceedance_hist_p90": float((T_obs > T_p90).mean()),
        "exceedance_fp_p90":   float((T_hat_fp > T_p90).mean()),
        "exceedance_hist_p95": float((T_obs > T_p95).mean()),
        "exceedance_fp_p95":   float((T_hat_fp > T_p95).mean()),
        "exceedance_hist_p99": float((T_obs > T_p99).mean()),
        "exceedance_fp_p99":   float((T_hat_fp > T_p99).mean()),
    },
    "n_jobs_infeasible_stateful": int(n_infeas_stat),
}
with open(ANALYSIS_DIR / "phase3b1_realism.json", "w") as f:
    json.dump(output_json, f, indent=2, default=float)

print("Saved phase3b1_realism.json, phase3b1_fingerprint_stateful.parquet")
print("\nDone.")
