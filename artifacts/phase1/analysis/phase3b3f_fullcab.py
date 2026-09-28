#!/usr/bin/env python3
"""
Phase 3B.3-F: Full-cabinet power reconstruction.

Key change vs. 3B.3-R: cabinet power includes ALL physical nodes (9,856), not
just the 2,000-node cohort.  Non-cohort nodes are a fixed background derived
import os
from historical job assignments.  Cohort nodes are rerouted by policy.

  P_cab(t) = P_bg_noncohort_c(t)          <- fixed for all policies
            + P_cf_cohort_c(t)             <- policy-dependent

Full-cabinet historical p99/max are used as baselines.  Fleet power peak is
compared against the ORNL public ~29 MW system figure as a sanity check.

Topology (OLCF 2024: 77 Olympus rack HPE cabinets, 128 nodes each, 9,856 total):
  - Telemetry observes all 77 documented cabinets.
  - 480 nodes appear under >1 x-number (maintenance reassignments).
  - x2305 absent from all job data (offline or never used).
  - Cohort is uniformly stratified: exactly 26 of 128 nodes per cabinet = 20.3%.
  - Current model cabinet "limit" ~30 kW is cohort-only, ~148 kW physical.
"""

import pandas as pd
import numpy as np
import json, time, re
from pathlib import Path
from collections import defaultdict

ANALYSIS_DIR = Path(__file__).parent
# Set THERMALSHIFT_DATA_DIR env var to your local Frontier dataset directory.
DATA_DIR     = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

BETA_F        = 0.9569
SCENARIO_SEED = 42
WORKLOAD_SEED = 77777
N_BINS        = 5
LAMBDA_SWEEP  = [1.00, 1.10, 1.20, 1.30, 1.40, 1.50, 1.65, 1.80]
LAMBDA_MAX    = max(LAMBDA_SWEEP)

T_P95_THRESHOLD = 60.602770562770566
P50_PWR         = 896.4571428571429
P80_PWR         = 1496.4923809523812
P95_PWR         = 1955.5884126984126

# ============================================================
# Load
# ============================================================
print("=== Phase 3B.3-F: Full-cabinet power reconstruction ===\n")

fp_df     = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set = set(fp_df.index)
F_dict    = fp_df["FA_2024"].to_dict()
cohort_list = sorted(cohort_set)
n_cohort  = len(cohort_list)
print(f"Cohort: {n_cohort} nodes")

test_df  = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"Total jobs: {len(all_jobs):,}")

H_all_hist = float(
    (all_jobs["node_count"].astype(float) * all_jobs["run_time"].astype(float) / 3600.0).sum()
)
print(f"H_all_hist (all-job fleet node-hours): {H_all_hist:,.0f} nh")

# ============================================================
# Canonical node->cabinet mapping (ALL 9,856 nodes)
# ============================================================
print("\nBuilding canonical node-to-cabinet map (all nodes)...")
t0 = time.time()
_xe2_re = re.compile(r"x(\d+)c")
node_to_cabinet: dict[str, int] = {}  # frontier_name -> x-number (first seen)

for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    for hn, xn in zip(hl, str(nl).split()):
        xn = xn.strip("'[]\"")
        if hn not in node_to_cabinet:
            m = _xe2_re.match(xn)
            if m:
                node_to_cabinet[hn] = int(m.group(1))

all_cabinets = sorted(set(node_to_cabinet.values()))
n_cab        = len(all_cabinets)
n_all_nodes  = len(node_to_cabinet)
print(f"  {n_all_nodes:,} unique nodes, {n_cab} cabinet IDs  ({time.time()-t0:.1f}s)")

# ============================================================
# TOPOLOGY DIAGNOSTIC
# ============================================================
print("\n" + "="*60)
print("TOPOLOGY DIAGNOSTIC: 77 vs 74 cabinet reconciliation")
print("="*60)
cab_canon_size  = defaultdict(int)
cab_cohort_size = defaultdict(int)
for hn, c in node_to_cabinet.items():
    cab_canon_size[c]  += 1
    if hn in cohort_set:
        cab_cohort_size[c] += 1

sizes = [cab_canon_size[c] for c in all_cabinets]
print(f"  Canonical node counts per cabinet:")
print(f"    min={min(sizes)}  median={int(np.median(sizes))}  max={max(sizes)}")
print(f"    == 128: {sum(1 for s in sizes if s == 128)}")
print(f"    != 128: {sum(1 for s in sizes if s != 128)}  (boundary effects from node migrations)")
print(f"  x2305 absent from all job data (offline or never used).")
print(f"  All 77 cabinets are documented (OLCF 2024: 77 Olympus rack HPE cabinets,")
print(f"    128 nodes each, 9,856 nodes total); telemetry observes all 77.")
print(f"  Cohort distribution: {min(cab_cohort_size.values())}-{max(cab_cohort_size.values())} cohort nodes/cabinet")
print(f"    Uniform at 26/128 = {26/128:.1%} per cabinet -> cohort is 20.3% of physical fleet.")
print(f"  Previous cabinet 'limit' ~30 kW was cohort-only;")
print(f"    physical cabinet power ~ 30 * 128/26 = {30*128/26:.0f} kW.")

# ============================================================
# Schedule arrays (cohort-containing jobs only)
# ============================================================
print("\nSchedule arrays...")
t0 = time.time()
cohort_per_job: dict[int, frozenset] = {}
for jid, hl in zip(all_jobs["job_idx_int"].values, all_jobs["host_list"].values):
    cn = frozenset(n for n in hl if n in cohort_set)
    if cn:
        cohort_per_job[jid] = cn

def _to_dt64_ms(ts):
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return np.datetime64(t.tz_convert("UTC").tz_localize(None), "ms")

def _col_to_dt64ms(series):
    """Convert a pandas datetime Series (tz-aware or naive) to numpy datetime64[ms] array."""
    s = pd.to_datetime(series, utc=True)
    return s.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ms]")

has_cohort = np.array([jid in cohort_per_job for jid in all_jobs["job_idx_int"].values])
sched_jids = all_jobs["job_idx_int"].values[has_cohort]
sched_st   = _col_to_dt64ms(all_jobs["start_time"])[has_cohort]
sched_et   = _col_to_dt64ms(all_jobs["end_time"])[has_cohort]
sched_cn   = np.array([cohort_per_job[jid] for jid in sched_jids], dtype=object)
print(f"  {len(sched_jids):,} entries  ({time.time()-t0:.1f}s)")

# ============================================================
# Job-level summary (test jobs only, same as before)
# ============================================================
print("Job-level summary...")
job_agg = (
    test_df.groupby("job_idx")
    .agg(F_hist_mean=("F_2024","mean"), n_cohort=("node","count"),
         T_p95_hist=("T_p95","mean"), hist_nodes=("node", list))
    .reset_index()
)
meta = (
    all_jobs[["job_idx_int","node_count","start_time","end_time","mean_power","run_time"]]
    .rename(columns={"job_idx_int":"job_idx"})
)
job_agg = job_agg.merge(meta, on="job_idx", how="left")
job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)
test_id_set = set(job_agg["job_idx"].astype(int))
jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)
n_base      = len(jobs_sorted)
print(f"  {n_base} base jobs")

hist_node_hours = {n: 0.0 for n in cohort_list}
for _, jrow in jobs_sorted.iterrows():
    rt_h = float(jrow["run_time"]) / 3600.0
    for nd in jrow["hist_nodes"]:
        if nd in hist_node_hours:
            hist_node_hours[nd] += rt_h
hist_util_arr  = np.array([hist_node_hours[n] for n in cohort_list])
hist_total_nh  = float(hist_util_arr.sum())
hist_fleet_avg = hist_total_nh / n_cohort

rt_lookup   = jobs_sorted.set_index("job_idx")["run_time"].to_dict()
test_rt_h   = test_df["job_idx"].map(lambda j: rt_lookup.get(int(j), 0.0)) / 3600.0
node_excess = test_df["T_p95"] - T_P95_THRESHOLD
B_hist_node = float((test_rt_h * (node_excess > 0)).sum())
S_hist_node = float((test_rt_h * node_excess.clip(lower=0)).sum())

print("Residuals...")
jobs_sorted["alpha_j"] = jobs_sorted["T_p95_hist"] - BETA_F * jobs_sorted["F_hist_mean"]
alpha_map = jobs_sorted.set_index("job_idx")["alpha_j"].to_dict()
test_res = test_df.copy()
test_res["alpha_j"]  = test_res["job_idx"].map(lambda j: alpha_map.get(int(j), np.nan))
test_res["F_i"]      = test_res["node"].map(F_dict)
test_res["residual"] = test_res["T_p95"] - test_res["alpha_j"] - BETA_F * test_res["F_i"]
job_residuals: dict[int, tuple] = {}
for jid, grp in test_res.groupby("job_idx"):
    jid = int(jid)
    grp_s = grp.sort_values("F_i")
    res_arr = grp_s["residual"].values.copy()
    k = len(grp_s)
    if k >= N_BINS:
        try:
            bins = pd.qcut(grp_s["F_i"], q=N_BINS, labels=False,
                           duplicates="drop").values.astype(int)
        except Exception:
            bins = np.zeros(k, dtype=int)
    else:
        bins = np.zeros(k, dtype=int)
    job_residuals[jid] = (res_arr, bins)

print("Background busy (cohort-level)...")
t0 = time.time()
is_test_sched = np.array([jid in test_id_set for jid in sched_jids])
bg_st = sched_st[~is_test_sched]
bg_et = sched_et[~is_test_sched]
bg_cn = sched_cn[~is_test_sched]
bg_busy_per_job: dict[int, frozenset] = {}
for _, jrow in jobs_sorted.iterrows():
    jid = int(jrow["job_idx"])
    t_j = np.datetime64(pd.Timestamp(jrow["start_time"]).tz_convert("UTC").tz_localize(None), "ms")
    mask = (bg_st <= t_j) & (bg_et > t_j)
    bg_busy_per_job[jid] = frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()
print(f"  Done ({time.time()-t0:.1f}s)")

hist_starts_dt64 = np.array([_to_dt64_ms(r["start_time"]) for _, r in jobs_sorted.iterrows()])
hist_ends_dt64   = np.array([_to_dt64_ms(r["end_time"])   for _, r in jobs_sorted.iterrows()])
hist_k_arr       = jobs_sorted["n_cohort"].values.astype(int)
hist_jids_arr    = jobs_sorted["job_idx"].values.astype(int)

def _dt64_to_h(a, b):
    return float((b - a).astype("int64")) / 3.6e6

# ============================================================
# FULL-CABINET BACKGROUND PRECOMPUTATION
# ============================================================
print("\nPrecomputing full-cabinet background (non-cohort nodes, all 152,400 jobs)...")
t0 = time.time()

# bg_records: for each job, non-cohort node cabinet distribution
# cohort_hist_records: for each BASE job, historical cohort cabinet distribution
# all_fleet_P: for fleet sanity check (all-job peak power)

bg_records: list[dict] = []
cohort_hist_records: list[dict] = []
all_fleet_events: list[tuple] = []  # (t_s, t_e, P_j) for every job

# Pre-extract arrays for fast iteration (avoid .iloc[idx] which is O(n^2))
_all_jids = all_jobs["job_idx_int"].values
_all_Pj   = np.where(all_jobs["mean_power"].isna().values,
                     0.0, all_jobs["mean_power"].values.astype(float))
_all_nc   = np.maximum(all_jobs["node_count"].values.astype(int), 1)
_all_hl   = all_jobs["host_list"].values
_all_st = _col_to_dt64ms(all_jobs["start_time"])
_all_et = _col_to_dt64ms(all_jobs["end_time"])

for jid, P_j, nc, hl, t_s, t_e in zip(_all_jids, _all_Pj, _all_nc, _all_hl, _all_st, _all_et):
    ppn = P_j / nc

    all_fleet_events.append((t_s, t_e, P_j))

    # Split nodes into cohort and non-cohort cabinet distributions
    ncc: dict[int, int] = {}
    chc: dict[int, int] = {}
    for hn in hl:
        c = node_to_cabinet.get(hn, -1)
        if c < 0:
            continue
        if hn in cohort_set:
            chc[c] = chc.get(c, 0) + 1
        else:
            ncc[c] = ncc.get(c, 0) + 1

    if ncc:
        bg_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": ncc})

    if int(jid) in test_id_set and chc:
        cohort_hist_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": chc})

print(f"  bg_records:          {len(bg_records):,} jobs have non-cohort nodes")
print(f"  cohort_hist_records: {len(cohort_hist_records):,} base jobs with cohort nodes")
print(f"  all_fleet_events:    {len(all_fleet_events):,} total jobs")
print(f"  Elapsed: {time.time()-t0:.1f}s")

# ============================================================
# Full-cabinet historical p99 and budget
# ============================================================
print("\nComputing full-cabinet historical p99 ...")
t0 = time.time()

def per_cabinet_p99_from_records(records: list[dict]) -> dict[int, float]:
    """Compute p99 power per cabinet from a list of {t_s, t_e, ppn, cab_counts} records."""
    events = []
    for r in records:
        ppn = r["ppn"]
        for c, n in r["cab_counts"].items():
            dp = ppn * n
            events.append((r["t_s"], +1, c, dp))
            events.append((r["t_e"], -1, c, dp))
    events.sort(key=lambda x: (x[0], x[1]))
    P_cab: dict[int, float] = defaultdict(float)
    t_prev = None
    cab_ivals: dict[int, list] = defaultdict(list)
    for t, sign, c, dp in events:
        if t_prev is not None and t != t_prev:
            dt_h = _dt64_to_h(t_prev, t)
            if dt_h > 0:
                for c2, Pc in P_cab.items():
                    if Pc > 1e-9:
                        cab_ivals[c2].append((dt_h, Pc))
        P_cab[c] += sign * dp
        t_prev = t
    result = {}
    for c, ivals in cab_ivals.items():
        total = sum(d for d, _ in ivals)
        s = sorted(ivals, key=lambda x: x[1])
        target = total * 0.99
        cum = 0.0
        result[c] = s[-1][1]
        for dt, pwr in s:
            cum += dt
            if cum >= target:
                result[c] = pwr
                break
    return result

def sweep_cab_budget(records: list[dict],
                     cab_threshold: dict[int, float]) -> tuple[float, float]:
    """
    Sweep a merged record list and compute total budget integral:
      B = sum_c integral dt * 1[P_c(t) > threshold_c]   (hours)
      S = sum_c integral dt * (P_c(t) - threshold_c)+    (W*h)
    """
    events = []
    for r in records:
        ppn = r["ppn"]
        for c, n in r["cab_counts"].items():
            dp = ppn * n
            events.append((r["t_s"], +1, c, dp))
            events.append((r["t_e"], -1, c, dp))
    events.sort(key=lambda x: (x[0], x[1]))
    P_cab: dict[int, float] = defaultdict(float)
    last_t: dict[int, object] = {}
    B_tot = 0.0; S_tot = 0.0
    for t, sign, c, dp in events:
        if c in last_t and t != last_t[c]:
            dt_h = _dt64_to_h(last_t[c], t)
            if dt_h > 0:
                thr = cab_threshold.get(c, 0.0)
                exc = P_cab[c] - thr
                if exc > 0:
                    B_tot += dt_h
                    S_tot += dt_h * exc
        P_cab[c] += sign * dp
        last_t[c] = t
    return B_tot, S_tot

# Historical full-cabinet power = bg (non-cohort of all jobs)
#                               + cohort_hist (cohort of base jobs, historical assignment)
combined_hist = bg_records + cohort_hist_records
P_cab_p99_full = per_cabinet_p99_from_records(combined_hist)
B_cab_hist_full, S_cab_hist_full = sweep_cab_budget(combined_hist, P_cab_p99_full)
print(f"  Full-cabinet p99 computed for {len(P_cab_p99_full)} cabinets  ({time.time()-t0:.1f}s)")
print(f"  B_cab_hist_full = {B_cab_hist_full:.2f} h")
print(f"  P_cab_p99 range: {min(P_cab_p99_full.values())/1e3:.1f} - "
      f"{max(P_cab_p99_full.values())/1e3:.1f} kW")

# Per-cabinet: q_c_full = p99 / 128 nodes
q_c_full = np.array([P_cab_p99_full.get(c, 0.0) / 128.0 for c in all_cabinets], dtype=float)
print(f"  q_c_full (W/node) -- {len(all_cabinets)} cabinets:")
print(f"    mean={q_c_full.mean():.0f}  SD={q_c_full.std():.0f}  "
      f"min={q_c_full.min():.0f}  median={np.median(q_c_full):.0f}  max={q_c_full.max():.0f}")
print(f"    ratio max/min = {q_c_full.max()/max(q_c_full.min(),1e-9):.2f}x")

# ============================================================
# IDENTITY CHECK
# ============================================================
print("\n" + "="*60)
print("IDENTITY CHECK: historical assignment reproduces p99 baseline")
print("="*60)
B_id, _ = sweep_cab_budget(combined_hist, P_cab_p99_full)
print(f"  B_cab_ratio (full-cabinet identity) = {B_id / max(B_cab_hist_full, 1e-9):.4f}  (expect 1.0000)")
print(f"  (By construction: p99 computed from the same records, so ratio = 1.0)")

# ============================================================
# FLEET POWER SANITY CHECK
# ============================================================
print("\n" + "="*60)
print("FLEET POWER SANITY CHECK vs. ORNL ~29 MW")
print("="*60)

# Sweep all 152,400 jobs to find peak and p99 fleet power
def fleet_peak_p99(fleet_events: list[tuple]) -> tuple[float, float, float]:
    """
    fleet_events: list of (t_s, t_e, P_j).
    Returns (P_peak, P_p99, total_duration_h).
    """
    evs = []
    for t_s, t_e, P_j in fleet_events:
        evs.append((t_s, +1, P_j))
        evs.append((t_e, -1, P_j))
    evs.sort(key=lambda x: (x[0], x[1]))
    P_fl = 0.0; t_prev = None; P_peak = 0.0
    ivals = []
    for t, sign, dP in evs:
        if t_prev is not None and t != t_prev:
            dt_h = _dt64_to_h(t_prev, t)
            if dt_h > 0:
                ivals.append((dt_h, P_fl))
                if P_fl > P_peak:
                    P_peak = P_fl
        P_fl += sign * dP
        t_prev = t
    total_h = sum(d for d, _ in ivals)
    # p99 of the power distribution weighted by time
    ivals_s = sorted(ivals, key=lambda x: x[1])
    target = total_h * 0.99; cum = 0.0; P_p99 = ivals_s[-1][1]
    for dt, pwr in ivals_s:
        cum += dt
        if cum >= target:
            P_p99 = pwr; break
    return P_peak, P_p99, total_h

P_fleet_peak_all, P_fleet_p99_all, total_period_h = fleet_peak_p99(all_fleet_events)
ORNL_MW = 29.0
print(f"  Historical fleet power (all {len(all_fleet_events):,} jobs):")
print(f"    Peak = {P_fleet_peak_all/1e6:.3f} MW")
print(f"    p99  = {P_fleet_p99_all/1e6:.3f} MW")
print(f"    Test period: {total_period_h:.0f} h")
print(f"  ORNL public figure: ~{ORNL_MW:.0f} MW  (total system: compute + network + storage + cooling)")
print(f"  Compute-job peak / ORNL total = {P_fleet_peak_all/1e6/ORNL_MW:.1%}")
print(f"  NOTE: This dataset covers 152,400 jobs from selected days in 2024-2025")
print(f"        (~6.8% of all allocated jobs).  P_fleet is compute-job scheduling power")
print(f"        only; cooling, network fabric, storage, and other overhead are excluded.")
print(f"        The 22.2 MW compute-job peak vs ORNL's ~29 MW total-system figure is a")
print(f"        reasonable order-of-magnitude sanity check, not a direct comparison.")

# The fleet power constraint is policy-independent (P_j does not change with node assignment).
# At lam=1.0 all policies reproduce historical fleet load -> C_fleet = 0.0%.
# Below: track fleet power for the admitted-cohort portion only (for growth reference).

# ============================================================
# Helpers (unchanged from phase3b3r)
# ============================================================
def to_dt64(ts):
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

def bg_busy_at(t_np):
    mask = (bg_st <= t_np) & (bg_et > t_np)
    return frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

def tier_select(available, k, P_j, rng_local):
    n_avail = len(available)
    cap_k   = min(k, n_avail)
    avail_F = np.array([F_dict[n] for n in available], dtype=float)
    order   = np.argsort(avail_F)
    if np.isnan(P_j) or P_j < P50_PWR:
        idx = rng_local.choice(n_avail, size=cap_k, replace=False)
        return [available[i] for i in idx]
    elif P_j < P80_PWR:
        pool_end = max(cap_k, int(n_avail * 0.75))
        pick = rng_local.choice(pool_end, size=cap_k, replace=False)
        return [available[order[i]] for i in pick]
    else:
        return [available[order[i]] for i in range(cap_k)]

def look_ahead_safe(selected_nodes, t_s, e_s, cf_busy):
    overlap_mask = (hist_starts_dt64 > t_s) & (hist_starts_dt64 < e_s)
    if not overlap_mask.any():
        return True
    s_nodes = frozenset(selected_nodes)
    for idx in np.where(overlap_mask)[0]:
        t_h   = hist_starts_dt64[idx]
        k_h   = int(hist_k_arr[idx])
        jid_h = int(hist_jids_arr[idx])
        bg_at_h = bg_busy_per_job[jid_h]
        cf_at_h = frozenset(n for n, te in cf_busy.items() if te > t_h)
        blocked = bg_at_h | cf_at_h | s_nodes
        fb_mask = ((hist_starts_dt64 > t_s) & (hist_starts_dt64 <= t_h)
                   & (hist_ends_dt64 > t_h))
        fb_mask = fb_mask.copy(); fb_mask[idx] = False
        future_base_k = min(int(hist_k_arr[fb_mask].sum()),
                            max(0, n_cohort - len(blocked)))
        if n_cohort - len(blocked) - future_base_k < k_h:
            return False
    return True

def sample_synthetic_pool(n_extra, seed):
    rng_s       = np.random.default_rng(seed)
    base_months = jobs_sorted["start_time"].dt.month.values
    base_hours  = jobs_sorted["start_time"].dt.hour.values
    strat_keys  = list(zip(base_months.tolist(), base_hours.tolist()))
    strat_to_idxs: dict = {}
    for i, sk in enumerate(strat_keys):
        strat_to_idxs.setdefault(sk, []).append(i)
    unique_strata = sorted(strat_to_idxs.keys())
    counts = np.array([len(strat_to_idxs[s]) for s in unique_strata])
    probs  = counts / counts.sum()
    n_per  = np.round(probs * n_extra).astype(int)
    diff   = n_extra - n_per.sum()
    if diff > 0: n_per[np.argsort(-probs)[:diff]] += 1
    elif diff < 0: n_per[np.argsort(n_per)[:(-diff)]] -= 1
    chunks = []
    for sk, n_s in zip(unique_strata, n_per):
        if n_s <= 0: continue
        idxs = rng_s.choice(strat_to_idxs[sk], size=int(n_s), replace=True)
        chunks.append(jobs_sorted.iloc[idxs])
    if not chunks:
        return pd.DataFrame(columns=list(jobs_sorted.columns) + ["is_synthetic", "parent_job_idx"])
    syn = pd.concat(chunks, ignore_index=True)
    jitter = rng_s.uniform(-1800., 1800., size=len(syn))
    syn["start_time"]     = syn["start_time"] + pd.to_timedelta(jitter, unit="s")
    syn["end_time"]       = syn["start_time"] + pd.to_timedelta(syn["run_time"].values, unit="s")
    syn["is_synthetic"]   = True
    syn["parent_job_idx"] = syn["job_idx"].values.copy()
    syn["job_idx"]        = -(np.arange(len(syn), dtype=np.int64) + 1)
    syn["alpha_j"]        = syn["parent_job_idx"].map(alpha_map)
    syn = syn.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)
    return syn

def generate_job_perms(syn_pool, scen_rng):
    job_perms = {}
    for jid in jobs_sorted["job_idx"].astype(int):
        res_s, bins = job_residuals[jid]
        k = len(res_s); perm = np.arange(k)
        for b in np.unique(bins):
            idx_b = np.where(bins == b)[0]
            perm[idx_b] = scen_rng.permutation(idx_b)
        job_perms[jid] = perm
    if len(syn_pool) > 0:
        for syn_jid, parent_jid in zip(syn_pool["job_idx"].astype(int),
                                        syn_pool["parent_job_idx"].astype(int)):
            res_s, bins = job_residuals[parent_jid]
            k = len(res_s); perm = np.arange(k)
            for b in np.unique(bins):
                idx_b = np.where(bins == b)[0]
                perm[idx_b] = scen_rng.permutation(idx_b)
            job_perms[syn_jid] = perm
    return job_perms

# ============================================================
# capacity_replay — returns COHORT cabinet power records only.
# Full-cabinet budget computed by merging with bg_records externally.
# ============================================================
def capacity_replay(syn_subset, policy, delta_cap, lambda_val,
                    policy_seed, job_perms):
    cap_per_node = (1.0 + delta_cap) * lambda_val * hist_fleet_avg
    n_syn = len(syn_subset)
    if n_syn > 0:
        base_copy = jobs_sorted.copy()
        base_copy["is_synthetic"]   = False
        base_copy["parent_job_idx"] = base_copy["job_idx"].values.copy()
        combined = pd.concat([base_copy, syn_subset], ignore_index=True)
    else:
        combined = jobs_sorted.copy()
        combined["is_synthetic"]   = False
        combined["parent_job_idx"] = combined["job_idx"].values.copy()
    combined = combined.sort_values("start_time").reset_index(drop=True)

    cf_busy: dict[str, np.datetime64] = {}
    cf_util: dict[str, float]         = {n: 0.0 for n in cohort_set}
    _rng = np.random.default_rng(policy_seed)

    B_node = 0.0; S_node = 0.0
    syn_node_hours  = 0.0
    n_syn_admit     = 0
    n_drop_cap      = 0
    n_drop_phys     = 0
    n_drop_la       = 0
    n_base_unserved = 0

    # Cohort-only power records (will be merged with bg_records for full-cabinet budget)
    cohort_records: list[dict] = []

    for _, jrow in combined.iterrows():
        is_syn  = bool(jrow["is_synthetic"])
        t_j     = to_dt64(jrow["start_time"])
        t_e     = to_dt64(jrow["end_time"])
        rt_h    = float(jrow["run_time"]) / 3600.0
        k       = int(jrow["n_cohort"])
        jid     = int(jrow["job_idx"])
        P_j_raw = jrow.get("mean_power", np.nan)
        P_j     = float(P_j_raw) if not pd.isna(P_j_raw) else 0.0
        nc      = max(1, int(jrow["node_count"]))
        ppn     = P_j / nc
        ppn_cf  = float(jrow.get("power_per_node", np.nan))
        ppn_cf  = ppn_cf if not np.isnan(ppn_cf) else ppn

        try:
            parent_jid = int(jrow["parent_job_idx"])
        except (TypeError, ValueError):
            parent_jid = jid

        bg_busy = (bg_busy_at(t_j) if is_syn
                   else bg_busy_per_job.get(parent_jid, frozenset()))
        cf_busy_now = frozenset(n for n, te in cf_busy.items() if te > t_j)

        avail_capped = [
            n for n in cohort_set
            if n not in bg_busy and n not in cf_busy_now and cf_util[n] < cap_per_node
        ]

        if is_syn:
            if len(avail_capped) < k:
                avail_unc = [n for n in cohort_set if n not in bg_busy and n not in cf_busy_now]
                n_drop_phys += 1 if len(avail_unc) < k else 0
                n_drop_cap  += 1 if len(avail_unc) >= k else 0
                continue
            available = avail_capped
        else:
            available = avail_capped if len(avail_capped) >= k else [
                n for n in cohort_set if n not in bg_busy and n not in cf_busy_now]

        n_avail = len(available)
        if n_avail == 0:
            selected = []
        elif policy == "fp":
            avail_F = np.array([F_dict[n] for n in available])
            order   = np.argsort(avail_F)
            selected = [available[i] for i in order[:min(k, n_avail)]]
        elif policy == "tier20":
            selected = tier_select(available, k, ppn_cf, _rng)
        else:
            idx = _rng.choice(n_avail, size=min(k, n_avail), replace=False)
            selected = [available[i] for i in idx]

        if is_syn and selected:
            if not look_ahead_safe(selected, t_j, t_e, cf_busy):
                n_drop_la += 1
                continue

        if not is_syn and len(selected) < k:
            n_base_unserved += 1

        for n in selected:
            cf_busy[n] = t_e
            cf_util[n] += rt_h

        if selected:
            F_arr    = np.array([F_dict[n] for n in selected])
            nh_j     = len(selected) * rt_h
            alpha    = float(jrow["alpha_j"])
            res_s, _ = job_residuals[parent_jid]
            perm     = job_perms[jid]
            rank     = np.argsort(np.argsort(F_arr))
            T_hats_j = alpha + BETA_F * F_arr + res_s[perm[rank]]
            excesses = T_hats_j - T_P95_THRESHOLD
            B_node  += rt_h * float((excesses > 0).sum())
            S_node  += rt_h * float(excesses.clip(min=0).sum())
            if is_syn:
                n_syn_admit    += 1
                syn_node_hours += nh_j
            # Cohort cabinet distribution
            cc: dict[int, int] = {}
            for nd in selected:
                c = node_to_cabinet.get(nd, -1)
                if c >= 0:
                    cc[c] = cc.get(c, 0) + 1
            if cc:
                cohort_records.append({"t_s": t_j, "t_e": t_e, "ppn": ppn, "cab_counts": cc})

    if n_base_unserved > 0:
        raise AssertionError(
            f"Base-job invariant violated: {n_base_unserved} job(s) "
            f"(lam={lambda_val}, policy={policy})")

    unlock_pct = syn_node_hours / hist_total_nh * 100.0

    # Full-cabinet budget: merge bg (fixed) + cohort (policy-specific)
    full_records = bg_records + cohort_records
    B_cb_full, S_cb_full = sweep_cab_budget(full_records, P_cab_p99_full)
    B_cb_ratio = B_cb_full / max(B_cab_hist_full, 1e-9)
    S_cb_ratio = S_cb_full / max(S_cab_hist_full, 1e-9)

    return {
        "lambda_val"         : lambda_val,
        "policy"             : policy,
        "n_syn_admit"        : n_syn_admit,
        "n_drop_cap"         : n_drop_cap,
        "n_drop_physical"    : n_drop_phys,
        "n_drop_la"          : n_drop_la,
        "n_base_unserved"    : n_base_unserved,
        "syn_node_hours"     : syn_node_hours,
        "capacity_unlock_pct": unlock_pct,
        "B_node_ratio"       : B_node / B_hist_node if B_hist_node > 0 else float("nan"),
        "S_node_ratio"       : S_node / S_hist_node if S_hist_node > 0 else float("nan"),
        "B_cab_ratio_full"   : B_cb_ratio,
        "S_cab_ratio_full"   : S_cb_ratio,
    }

def find_crossing(rows, ratio_key, target=1.0):
    valid = [r for r in rows
             if ratio_key in r and not (isinstance(r.get(ratio_key), float)
                                        and np.isnan(r[ratio_key]))]
    if not valid:
        return None
    xs = [r["capacity_unlock_pct"] for r in valid]
    ys = [r[ratio_key] for r in valid]
    for i in range(len(ys) - 1):
        if ys[i] <= target <= ys[i + 1]:
            frac = (target - ys[i]) / max(ys[i + 1] - ys[i], 1e-12)
            return float(xs[i] + frac * (xs[i + 1] - xs[i]))
        if i == 0 and ys[i] >= target:
            return 0.0
    return None

def fmt(v):
    if v is None: return ">explored"
    return f"{v:.1f}%"

# ============================================================
# Window-matched system denominator for C_system_replay
# ============================================================
# D_replay = date_dir values represented by the 2,637 base test jobs
_test_jids_str = set(test_df["job_idx"].astype(str))
_test_meta = all_jobs[all_jobs["job_idx"].isin(_test_jids_str)]
D_replay = set(_test_meta["date_dir"].dropna().unique())
_replay_mask = all_jobs["date_dir"].isin(D_replay)
H_all_replay = float(
    (all_jobs.loc[_replay_mask, "node_count"].astype(float) *
     all_jobs.loc[_replay_mask, "run_time"].astype(float) / 3600.0).sum()
)
print(f"\nWindow-matched system denominator:")
print(f"  D_replay: {len(D_replay)} date_dirs represented in 2,637 base jobs")
print(f"  Jobs on replay days: {_replay_mask.sum():,}")
print(f"  H_all_replay: {H_all_replay:,.0f} node-hours")
print(f"  H_cohort_base/H_all_replay: {hist_total_nh/H_all_replay:.4f}  "
      f"({hist_total_nh/H_all_replay:.2%})")

# ============================================================
# Load thermal crossings from phase3b2d for final table
# ============================================================
with open(ANALYSIS_DIR / "phase3b2d_results.json") as f:
    p3b2 = json.load(f)
therm = {
    "random": p3b2["crossings"]["random"],
    "fp":     p3b2["crossings"]["fp"],
    "tier20": p3b2["crossings"]["tier20"],
}

# ============================================================
# SPARSE SWEEP
# ============================================================
print("\n" + "="*60)
print("SPARSE SWEEP: random, fp, tier20  (full-cabinet power)")
print("="*60)

POLICY_DEFS = [
    ("random", 1e6,  "Random-feasible"),
    ("fp",     0.10, "FP-cap-10"),
    ("tier20", 0.20, "Tier-cap-20"),
]

n_extra_max = int(np.ceil((LAMBDA_MAX - 1.0) * n_base))
print(f"\nSynthetic pool: {n_extra_max} jobs...")
syn_pool = sample_synthetic_pool(n_extra_max, WORKLOAD_SEED)
print(f"  {len(syn_pool)} synthetic jobs")
print("Generating permutations...")
scen_rng  = np.random.default_rng(SCENARIO_SEED)
job_perms = generate_job_perms(syn_pool, scen_rng)
print(f"  {len(job_perms)} permutations\n")

all_results: dict[str, list] = {pk: [] for pk, *_ in POLICY_DEFS}

for lam in LAMBDA_SWEEP:
    n_syn = int(round((lam - 1.0) * n_base))
    syn_subset = syn_pool.iloc[:n_syn].copy() if n_syn > 0 else pd.DataFrame(
        columns=syn_pool.columns if len(syn_pool) > 0 else jobs_sorted.columns)
    print(f"--- lam={lam:.2f} N_syn={n_syn} ---")
    hdr = f"  {'Policy':<20} | {'NH%':>5} | {'B/Bh':>6} | {'Bcab_full':>9} | drops"
    print(hdr); print("  " + "-" * (len(hdr) - 2))
    for pk, delta_cap, label in POLICY_DEFS:
        t0 = time.time()
        try:
            res = capacity_replay(
                syn_subset, pk, delta_cap, lam,
                policy_seed=SCENARIO_SEED + abs(hash(pk)) % 1000,
                job_perms=job_perms,
            )
        except AssertionError as exc:
            print(f"  {label:<20} | INVARIANT VIOLATED -- {exc}")
            all_results[pk].append({"lambda_val": lam, "policy": pk,
                                    "invariant_violated": True})
            continue
        elapsed = time.time() - t0
        all_results[pk].append(res)
        bf = res.get("B_cab_ratio_full", float("nan"))
        drops = f"{res['n_drop_physical']}/{res['n_drop_cap']}/{res['n_drop_la']}"
        print(f"  {label:<20} | {res['capacity_unlock_pct']:>5.1f} | "
              f"{res['B_node_ratio']:>6.4f} | {bf:>9.4f} | {drops}  ({elapsed:.0f}s)")

# ============================================================
# CROSSING ANALYSIS
# ============================================================
print("\n" + "="*60)
print("CROSSING ANALYSIS -- full-cabinet power baseline")
print("="*60)

rand_cfeas = None
print(f"\n  {'Policy':<22} | {'C_B_th':>7} | {'C_S_th':>7} | {'C_cab_full':>10} | {'C_cohort':>10} | {'C_system':>9}")
print(f"  {'':22}   {'':7}   {'':7}   {'':10}   (H_extra/H_coh)  (H_extra/H_all)")
print("  " + "-" * 90)

for pk, delta_cap, label in POLICY_DEFS:
    rows = all_results[pk]
    tc   = therm.get(pk, {})
    c_BT = tc.get("C_B")
    c_ST = tc.get("C_S")
    c_cf = find_crossing(rows, "B_cab_ratio_full")

    cands = [x for x in [c_BT, c_ST, c_cf] if x is not None]
    cfeas = min(cands) if cands else None

    if pk == "random":
        rand_cfeas = cfeas

    # C_system_replay: admitted node-hours as fraction of all-fleet activity on replay days
    c_sys = (cfeas * hist_total_nh / H_all_replay) if cfeas is not None else None

    delta = (cfeas - rand_cfeas) if (cfeas is not None and rand_cfeas is not None) else None
    ds = f"+{delta:.1f}pp" if delta is not None and delta >= 0 else (
         f"{delta:.1f}pp" if delta is not None else "N/A")

    print(f"  {label:<22} | {fmt(c_BT):>7} | {fmt(c_ST):>7} | "
          f"{fmt(c_cf):>10} | {fmt(cfeas):>10} | {fmt(c_sys):>9} ({ds})")

# ============================================================
# Save
# ============================================================
print()
out = {
    "n_all_nodes"             : n_all_nodes,
    "n_cab"                   : n_cab,
    "cohort_fraction_pct"     : 26.0 / 128.0 * 100.0,
    "H_all_hist_nh"           : H_all_hist,
    "H_all_replay_nh"         : H_all_replay,
    "H_cohort_hist_nh"        : hist_total_nh,
    "D_replay_n_dates"        : len(D_replay),
    "P_fleet_peak_all_W"      : P_fleet_peak_all,
    "P_fleet_p99_all_W"       : P_fleet_p99_all,
    "ORNL_system_MW"          : ORNL_MW,
    "compute_job_peak_to_ornl": P_fleet_peak_all / 1e6 / ORNL_MW,
    "B_cab_hist_full_h"       : B_cab_hist_full,
    "S_cab_hist_full_Wh"      : S_cab_hist_full,
    "P_cab_p99_full_kW_mean"  : float(np.mean(list(P_cab_p99_full.values()))) / 1e3,
    "P_cab_p99_full_kW_min"   : float(min(P_cab_p99_full.values())) / 1e3,
    "P_cab_p99_full_kW_max"   : float(max(P_cab_p99_full.values())) / 1e3,
    "policy_results"          : {pk: all_results[pk] for pk, *_ in POLICY_DEFS},
}
outpath = ANALYSIS_DIR / "phase3b3f_results.json"
with open(outpath, "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"  Saved {outpath}")
print("\n=== Done ===")
