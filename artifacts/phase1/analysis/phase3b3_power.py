# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.3: Power-envelope audit.

Uses the identical stateful replay from Phase 3B.2d (conditioned residuals,
fixed look-ahead, hard historical-service invariant). Three policies only:
Random-feasible, FP-cap-10, Tier-cap-20.

Power metrics:
  P_fleet(t) = sum_{j active at t} mean_power_j        (concurrent mean-power proxy)
  P_c(t)     = sum_{j active at t} (mean_power_j / node_count_j) * N_{jc}

Budget framework (mirrors thermal exactly):
  B_fleet = integral dt * 1[P_fleet(t) > P_fleet_p99_hist]
  S_fleet = integral dt * max(0, P_fleet(t) - P_fleet_p99_hist)
  B_cab   = sum_c integral dt * 1[P_c(t) > P_c_p99_hist[c]]
  S_cab   = sum_c integral dt * max(0, P_c(t) - P_c_p99_hist[c])

Sensitivity: same budgets at P_fleet_max threshold.

Final C_feasible = min(C_B_thermal, C_S_thermal, C_fleet_power, C_cab_power)
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import json, time, re
from pathlib import Path
from collections import defaultdict

ANALYSIS_DIR  = Path(__file__).parent
DATA_DIR      = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

BETA_F        = 0.9569
SCENARIO_SEED = 42
WORKLOAD_SEED = 77777
N_BINS        = 5

# Sparse sweep — locate crossings before committing to 30-scenario MC
LAMBDA_SWEEP = [1.00, 1.10, 1.20, 1.30, 1.40, 1.50, 1.65, 1.80]
LAMBDA_MAX   = max(LAMBDA_SWEEP)

# Three policies only; Tier-no-cap excluded (shows upper bound, skip MC)
POLICY_DEFS = [
    ("random",  1e6,  "Random-feasible", "#888888", "o"),
    ("fp",      0.10, "FP-cap-10",       "#ee7722", "s"),
    ("tier20",  0.20, "Tier-cap-20",     "#22aa55", "D"),
]
POLICY_KEYS = [p[0] for p in POLICY_DEFS]

T_P95_THRESHOLD = 60.602770562770566
P50_PWR         = 896.4571428571429
P80_PWR         = 1496.4923809523812
P95_PWR         = 1955.5884126984126

print("=== Phase 3B.3: Power-envelope audit (single scenario) ===")
print(f"  Policies: {[p[2] for p in POLICY_DEFS]}")
print(f"  Lambda sweep: {LAMBDA_SWEEP}\n")

# ============================================================
# Load (identical to phase3b2d)
# ============================================================
print("Loading fingerprints...")
fp_df        = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set   = set(fp_df.index)
F_dict       = fp_df["FA_2024"].to_dict()
cohort_list  = sorted(cohort_set)
n_cohort     = len(cohort_list)
F_cohort_arr = np.array([F_dict[n] for n in cohort_list])
F_sort_idx   = np.argsort(F_cohort_arr)
print(f"  Cohort: {n_cohort:,} nodes")

print("Loading test set...")
test_df = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")

print("Loading job schedule...")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"  {len(all_jobs):,} total jobs")

# ============================================================
# Cabinet mapping
# ============================================================
print("\nBuilding cabinet map...")
t0 = time.time()
_xe2_re = re.compile(r"x(\d+)c")
node_to_cabinet: dict[str, int] = {}
for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    for hn, xn in zip(hl, nl):
        if hn in cohort_set and hn not in node_to_cabinet:
            m = _xe2_re.match(xn)
            if m:
                node_to_cabinet[hn] = int(m.group(1))
    if len(node_to_cabinet) >= n_cohort:
        break
n_mapped = len(node_to_cabinet)
all_cabinets = sorted(set(node_to_cabinet.values()))
print(f"  Mapped {n_mapped}/{n_cohort} nodes -> {len(all_cabinets)} cabinets  ({time.time()-t0:.1f}s)")

# ============================================================
# Schedule arrays
# ============================================================
print("\nPrecomputing schedule arrays...")
t0 = time.time()
cohort_per_job: dict[int, frozenset] = {}
for jid, hl in zip(all_jobs["job_idx_int"].values, all_jobs["host_list"].values):
    cn = frozenset(n for n in hl if n in cohort_set)
    if cn:
        cohort_per_job[jid] = cn
has_cohort  = np.array([jid in cohort_per_job for jid in all_jobs["job_idx_int"].values])
sched_jids  = all_jobs["job_idx_int"].values[has_cohort]
sched_st    = all_jobs["start_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_et    = all_jobs["end_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_cn    = np.array([cohort_per_job[jid] for jid in sched_jids], dtype=object)
print(f"  {len(sched_jids):,} schedule entries  ({time.time()-t0:.1f}s)")

# ============================================================
# Job-level summary
# ============================================================
print("\nBuilding job-level summary...")
job_agg = (
    test_df.groupby("job_idx")
    .agg(F_hist_mean=("F_2024", "mean"), n_cohort=("node", "count"),
         T_p95_hist=("T_p95", "mean"),
         hist_nodes=("node", list))
    .reset_index()
)
meta = (
    all_jobs[["job_idx_int", "node_count", "start_time", "end_time", "mean_power", "run_time"]]
    .rename(columns={"job_idx_int": "job_idx"})
)
job_agg = job_agg.merge(meta, on="job_idx", how="left")
job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)
test_id_set  = set(job_agg["job_idx"].astype(int))
jobs_sorted  = job_agg.sort_values("start_time").reset_index(drop=True)
n_base       = len(jobs_sorted)
print(f"  {n_base} base test jobs")

hist_node_hours = {n: 0.0 for n in cohort_list}
for _, jrow in jobs_sorted.iterrows():
    rt_h = float(jrow["run_time"]) / 3600.0
    for n in jrow["hist_nodes"]:
        if n in hist_node_hours:
            hist_node_hours[n] += rt_h
hist_util_arr  = np.array([hist_node_hours[n] for n in cohort_list])
hist_total_nh  = float(hist_util_arr.sum())
hist_fleet_avg = hist_total_nh / n_cohort
print(f"  hist_total_nh={hist_total_nh:.0f} h  fleet_avg={hist_fleet_avg:.2f} h/node")

# ============================================================
# Thermal budgets (from phase3b2d, for final C_feasible table)
# ============================================================
rt_lookup   = jobs_sorted.set_index("job_idx")["run_time"].to_dict()
test_rt_h   = test_df["job_idx"].map(lambda j: rt_lookup.get(int(j), 0.0)) / 3600.0
node_excess = test_df["T_p95"] - T_P95_THRESHOLD
B_hist_node = float((test_rt_h * (node_excess > 0)).sum())
S_hist_node = float((test_rt_h * node_excess.clip(lower=0)).sum())
print(f"  B_hist_node={B_hist_node:.1f} h  S_hist_node={S_hist_node:.1f} degC-h")

# ============================================================
# Residual model (conditioned, N_BINS=5)
# ============================================================
print(f"\nComputing empirical residuals (N_BINS={N_BINS})...")
jobs_sorted["alpha_j"] = jobs_sorted["T_p95_hist"] - BETA_F * jobs_sorted["F_hist_mean"]
alpha_map = jobs_sorted.set_index("job_idx")["alpha_j"].to_dict()

test_res = test_df.copy()
test_res["alpha_j"]  = test_res["job_idx"].map(lambda j: alpha_map.get(int(j), np.nan))
test_res["F_i"]      = test_res["node"].map(F_dict)
test_res["residual"] = test_res["T_p95"] - test_res["alpha_j"] - BETA_F * test_res["F_i"]

job_residuals: dict[int, tuple] = {}
for jid, grp in test_res.groupby("job_idx"):
    jid = int(jid)
    grp_s   = grp.sort_values("F_i")
    res_arr = grp_s["residual"].values.copy()
    k       = len(grp_s)
    if k >= N_BINS:
        try:
            bins = pd.qcut(grp_s["F_i"], q=N_BINS,
                           labels=False, duplicates="drop").values.astype(int)
        except Exception:
            bins = np.zeros(k, dtype=int)
    else:
        bins = np.zeros(k, dtype=int)
    job_residuals[jid] = (res_arr, bins)
print(f"  {len(job_residuals)} job residual vectors")

# ============================================================
# Background busy
# ============================================================
print("\nPrecomputing background busy...")
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
print(f"  Done  ({time.time()-t0:.1f}s)")

# ============================================================
# Look-ahead arrays (fixed: co-start bug closed)
# ============================================================
def _to_dt64_ms(ts) -> np.datetime64:
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

hist_starts_dt64 = np.array([_to_dt64_ms(r["start_time"]) for _, r in jobs_sorted.iterrows()])
hist_ends_dt64   = np.array([_to_dt64_ms(r["end_time"])   for _, r in jobs_sorted.iterrows()])
hist_k_arr       = jobs_sorted["n_cohort"].values.astype(int)
hist_jids_arr    = jobs_sorted["job_idx"].values.astype(int)

# ============================================================
# Historical concurrent power baseline
# ============================================================
print("\nComputing historical power baseline...")
t0 = time.time()

def _dt64_to_h(a: np.datetime64, b: np.datetime64) -> float:
    return float((b - a).astype("int64")) / 3.6e6  # ms → hours

def build_power_records(rows_df, node_col="hist_nodes", assigned_nodes=None):
    """
    Build per-job power records for sweep-line computation.
    node_col: column in rows_df containing list of assigned nodes.
    assigned_nodes: if provided, overrides node_col (list-of-lists, same order as rows_df).
    """
    records = []
    for idx, (_, jrow) in enumerate(rows_df.iterrows()):
        P_j  = float(jrow["mean_power"]) if not pd.isna(jrow["mean_power"]) else 0.0
        nc   = max(1, int(jrow["node_count"]))
        ppn  = P_j / nc
        t_s  = _to_dt64_ms(jrow["start_time"])
        t_e  = _to_dt64_ms(jrow["end_time"])
        nodes = assigned_nodes[idx] if assigned_nodes is not None else jrow[node_col]
        cab_counts: dict[int, int] = defaultdict(int)
        for nd in nodes:
            c = node_to_cabinet.get(nd, -1)
            if c >= 0:
                cab_counts[c] += 1
        records.append({
            "t_s": t_s, "t_e": t_e,
            "P_fleet": P_j,
            "ppn": ppn,
            "cab_counts": dict(cab_counts),
        })
    return records

def sweep_line_power(records, fleet_thr: float,
                     cab_thr: dict) -> tuple[float, float, float, float]:
    """
    Sweep-line over all power records.
    Returns (B_fleet_h, S_fleet_Wh, B_cab_h, S_cab_Wh)
    where B_fleet_h = total hours P_fleet > fleet_thr, etc.
    """
    events = []
    for r in records:
        ppn = r["ppn"]
        cdp = {c: ppn * n for c, n in r["cab_counts"].items()}
        events.append((r["t_s"],  +1, r["P_fleet"],  cdp))
        neg = {c: -v for c, v in cdp.items()}
        events.append((r["t_e"],  -1, r["P_fleet"],  neg))
    # sort: earlier time first; at same time, ends (-1) before starts (+1)
    events.sort(key=lambda x: (x[0], x[1]))

    P_fleet = 0.0
    P_cab   = defaultdict(float)
    t_prev  = None
    B_fleet = 0.0; S_fleet = 0.0
    B_cab   = 0.0; S_cab   = 0.0

    for t, sign, dP_f, dP_c in events:
        if t_prev is not None and t != t_prev:
            dt_h = _dt64_to_h(t_prev, t)
            if dt_h > 0:
                exc_f = P_fleet - fleet_thr
                if exc_f > 0:
                    B_fleet += dt_h
                    S_fleet += dt_h * exc_f
                if cab_thr:
                    for c, Pc in P_cab.items():
                        thr_c = cab_thr.get(c, 0.0)
                        exc_c = Pc - thr_c
                        if exc_c > 0:
                            B_cab += dt_h
                            S_cab += dt_h * exc_c
        P_fleet += sign * dP_f
        for c, dp in dP_c.items():
            P_cab[c] += dp
        t_prev = t
    return B_fleet, S_fleet, B_cab, S_cab

def time_weighted_percentile(records, percentile: float = 99.0):
    """Fleet power time-weighted percentile and maximum."""
    events = []
    for r in records:
        events.append((r["t_s"], +1, r["P_fleet"]))
        events.append((r["t_e"], -1, r["P_fleet"]))
    events.sort(key=lambda x: (x[0], x[1]))
    P = 0.0; P_max = 0.0; t_prev = None
    intervals = []
    for t, sign, dP in events:
        if t_prev is not None and t != t_prev:
            dt_h = _dt64_to_h(t_prev, t)
            if dt_h > 0:
                intervals.append((dt_h, P))
        P += sign * dP
        if P > P_max:
            P_max = P
        t_prev = t
    total_h = sum(d for d, _ in intervals)
    intervals_s = sorted(intervals, key=lambda x: x[1])
    target = total_h * (percentile / 100.0)
    cum = 0.0
    p_val = intervals_s[-1][1] if intervals_s else 0.0
    for dt, pwr in intervals_s:
        cum += dt
        if cum >= target:
            p_val = pwr
            break
    return p_val, P_max, total_h

def per_cabinet_p99(records):
    """Per-cabinet time-weighted p99 power."""
    events = []
    for r in records:
        ppn = r["ppn"]
        for c, n in r["cab_counts"].items():
            dp = ppn * n
            events.append((r["t_s"],  +1, c, dp))
            events.append((r["t_e"],  -1, c, dp))
    events.sort(key=lambda x: (x[0], x[1]))

    P_cab = defaultdict(float)
    t_prev = None
    cab_ivals = defaultdict(list)

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

# Build historical records from test jobs' historical node assignments
hist_records = build_power_records(jobs_sorted, node_col="hist_nodes")

P_fleet_p99_hist, P_fleet_max_hist, total_test_h = time_weighted_percentile(hist_records, 99.0)
P_cab_p99_hist = per_cabinet_p99(hist_records)

B_fleet_hist, S_fleet_hist, B_cab_hist, S_cab_hist = sweep_line_power(
    hist_records, P_fleet_p99_hist, P_cab_p99_hist)

n_pwr_missing = sum(1 for _, r in jobs_sorted.iterrows() if pd.isna(r["mean_power"]))
print(f"  P_fleet_p99_hist = {P_fleet_p99_hist/1e6:.3f} MW")
print(f"  P_fleet_max_hist = {P_fleet_max_hist/1e6:.3f} MW")
print(f"  Total test period = {total_test_h:.1f} h")
print(f"  B_fleet_hist (h above p99)  = {B_fleet_hist:.2f} h")
print(f"  B_cab_hist   (h above p99)  = {B_cab_hist:.2f} h")
print(f"  Cabinet p99 computed for {len(P_cab_p99_hist)} / {len(all_cabinets)} cabinets")
print(f"  Jobs with missing mean_power: {n_pwr_missing}")
print(f"  ({time.time()-t0:.1f}s)")

# ============================================================
# Utility helpers
# ============================================================
def to_dt64(ts) -> np.datetime64:
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

def bg_busy_at(t_np: np.datetime64) -> frozenset:
    mask = (bg_st <= t_np) & (bg_et > t_np)
    return frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

def tier_select(available: list, k: int, P_j: float, rng_local) -> list:
    n_avail  = len(available)
    cap_k    = min(k, n_avail)
    avail_F  = np.array([F_dict[n] for n in available], dtype=float)
    order    = np.argsort(avail_F)
    if np.isnan(P_j) or P_j < P50_PWR:
        idx = rng_local.choice(n_avail, size=cap_k, replace=False)
        return [available[i] for i in idx]
    elif P_j < P80_PWR:
        pool_end = max(cap_k, int(n_avail * 0.75))
        pick = rng_local.choice(pool_end, size=cap_k, replace=False)
        return [available[order[i]] for i in pick]
    else:
        return [available[order[i]] for i in range(cap_k)]

def look_ahead_safe(selected_nodes: list, t_s, e_s, cf_busy: dict) -> bool:
    overlap_mask = (hist_starts_dt64 > t_s) & (hist_starts_dt64 < e_s)
    if not overlap_mask.any():
        return True
    s_nodes = frozenset(selected_nodes)
    for idx in np.where(overlap_mask)[0]:
        t_h      = hist_starts_dt64[idx]
        k_h      = int(hist_k_arr[idx])
        jid_h    = int(hist_jids_arr[idx])
        bg_at_h  = bg_busy_per_job[jid_h]
        cf_at_h  = frozenset(n for n, te in cf_busy.items() if te > t_h)
        blocked  = bg_at_h | cf_at_h | s_nodes
        # Include co-starters (same timestamp, sorted before idx in combined schedule)
        future_base_mask = (
            (hist_starts_dt64 > t_s) &
            (hist_starts_dt64 <= t_h) &
            (hist_ends_dt64   > t_h)
        )
        future_base_mask = future_base_mask.copy()
        future_base_mask[idx] = False
        future_base_k = min(int(hist_k_arr[future_base_mask].sum()),
                            max(0, n_cohort - len(blocked)))
        if n_cohort - len(blocked) - future_base_k < k_h:
            return False
    return True

# ============================================================
# Synthetic pool generator
# ============================================================
def sample_synthetic_pool(n_extra: int, seed: int) -> pd.DataFrame:
    rng_s        = np.random.default_rng(seed)
    base_months  = jobs_sorted["start_time"].dt.month.values
    base_hours   = jobs_sorted["start_time"].dt.hour.values
    strat_keys   = list(zip(base_months.tolist(), base_hours.tolist()))
    strat_to_idxs: dict = {}
    for i, sk in enumerate(strat_keys):
        strat_to_idxs.setdefault(sk, []).append(i)
    unique_strata = sorted(strat_to_idxs.keys())
    counts  = np.array([len(strat_to_idxs[s]) for s in unique_strata])
    probs   = counts / counts.sum()
    n_per   = np.round(probs * n_extra).astype(int)
    diff    = n_extra - n_per.sum()
    if diff > 0:
        n_per[np.argsort(-probs)[:diff]] += 1
    elif diff < 0:
        n_per[np.argsort(n_per)[:(-diff)]] -= 1
    chunks = []
    for sk, n_s in zip(unique_strata, n_per):
        if n_s <= 0:
            continue
        pool = strat_to_idxs[sk]
        idxs = rng_s.choice(pool, size=int(n_s), replace=True)
        chunks.append(jobs_sorted.iloc[idxs])
    if not chunks:
        return pd.DataFrame(columns=list(jobs_sorted.columns) + ["is_synthetic", "parent_job_idx"])
    syn = pd.concat(chunks, ignore_index=True)
    jitter_s           = rng_s.uniform(-1800.0, 1800.0, size=len(syn))
    syn["start_time"]  = syn["start_time"] + pd.to_timedelta(jitter_s, unit="s")
    syn["end_time"]    = syn["start_time"] + pd.to_timedelta(syn["run_time"].values, unit="s")
    syn["is_synthetic"]   = True
    syn["parent_job_idx"] = syn["job_idx"].values.copy()
    syn["job_idx"]        = -(np.arange(len(syn), dtype=np.int64) + 1)
    syn["alpha_j"]        = syn["parent_job_idx"].map(alpha_map)
    syn = syn.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)
    return syn

def generate_job_perms(syn_pool: pd.DataFrame,
                       scen_rng: np.random.Generator) -> dict[int, np.ndarray]:
    job_perms: dict[int, np.ndarray] = {}
    for jid in jobs_sorted["job_idx"].astype(int):
        res_s, bins = job_residuals[jid]
        k    = len(res_s)
        perm = np.arange(k)
        for b in np.unique(bins):
            idx_b      = np.where(bins == b)[0]
            perm[idx_b] = scen_rng.permutation(idx_b)
        job_perms[jid] = perm
    if len(syn_pool) > 0:
        for syn_jid, parent_jid in zip(syn_pool["job_idx"].astype(int),
                                        syn_pool["parent_job_idx"].astype(int)):
            res_s, bins = job_residuals[parent_jid]
            k    = len(res_s)
            perm = np.arange(k)
            for b in np.unique(bins):
                idx_b      = np.where(bins == b)[0]
                perm[idx_b] = scen_rng.permutation(idx_b)
            job_perms[syn_jid] = perm
    return job_perms

# ============================================================
# Capacity replay (with power record collection)
# ============================================================
def capacity_replay(
    syn_subset  : pd.DataFrame,
    policy      : str,
    delta_cap   : float,
    lambda_val  : float,
    policy_seed : int,
    job_perms   : dict[int, np.ndarray],
) -> dict:

    cap_per_node = (1.0 + delta_cap) * lambda_val * hist_fleet_avg
    n_syn        = len(syn_subset)

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

    cf_busy : dict[str, np.datetime64] = {}
    cf_util : dict[str, float]         = {n: 0.0 for n in cohort_set}
    _rng = np.random.default_rng(policy_seed)

    B_node = 0.0; S_node = 0.0
    syn_node_hours  = 0.0
    n_syn_admit     = 0
    n_drop_cap      = 0
    n_drop_phys     = 0
    n_drop_la       = 0
    n_base_unserved = 0

    # Power record: one entry per admitted job (base + synthetic)
    power_records: list[dict] = []

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

        pjid_raw = jrow["parent_job_idx"]
        try:
            parent_jid = int(pjid_raw)
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
                avail_uncapped = [n for n in cohort_set
                                  if n not in bg_busy and n not in cf_busy_now]
                if len(avail_uncapped) < k:
                    n_drop_phys += 1
                else:
                    n_drop_cap += 1
                continue
            available = avail_capped
        else:
            available = avail_capped if len(avail_capped) >= k else [
                n for n in cohort_set if n not in bg_busy and n not in cf_busy_now
            ]

        n_avail = len(available)
        if n_avail == 0:
            selected = []
        elif policy == "fp":
            avail_F  = np.array([F_dict[n] for n in available])
            order    = np.argsort(avail_F)
            selected = [available[i] for i in order[:min(k, n_avail)]]
        elif policy in ("tier20", "tiernc"):
            selected = tier_select(available, k, ppn_cf, _rng)
        else:
            idx      = _rng.choice(n_avail, size=min(k, n_avail), replace=False)
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

            # Collect power record for this admitted job
            cab_counts: dict[int, int] = defaultdict(int)
            for nd in selected:
                c = node_to_cabinet.get(nd, -1)
                if c >= 0:
                    cab_counts[c] += 1
            power_records.append({
                "t_s": t_j, "t_e": t_e,
                "P_fleet": P_j,
                "ppn": ppn,
                "cab_counts": dict(cab_counts),
            })

    if n_base_unserved > 0:
        raise AssertionError(
            f"Base-job invariant violated: {n_base_unserved} job(s) under-served "
            f"(lam={lambda_val}, policy={policy})"
        )

    unlock_pct = syn_node_hours / hist_total_nh * 100.0

    # --- Power budgets ---
    B_fleet_r, S_fleet_r, B_cab_r, S_cab_r = sweep_line_power(
        power_records, P_fleet_p99_hist, P_cab_p99_hist)
    # Sensitivity: max threshold
    B_fleet_max_r, _, _, _ = sweep_line_power(
        power_records, P_fleet_max_hist, {})

    return {
        "lambda_val"          : lambda_val,
        "policy"              : policy,
        "n_syn_admit"         : n_syn_admit,
        "n_drop_cap"          : n_drop_cap,
        "n_drop_physical"     : n_drop_phys,
        "n_drop_la"           : n_drop_la,
        "n_base_unserved"     : n_base_unserved,
        "syn_node_hours"      : syn_node_hours,
        "capacity_unlock_pct" : unlock_pct,
        "B_node_ratio"        : B_node / B_hist_node if B_hist_node > 0 else np.nan,
        "S_node_ratio"        : S_node / S_hist_node if S_hist_node > 0 else np.nan,
        # Fleet power
        "B_fleet_h"           : B_fleet_r,
        "S_fleet_Wh"          : S_fleet_r,
        "B_fleet_ratio"       : B_fleet_r / B_fleet_hist if B_fleet_hist > 0 else np.nan,
        "S_fleet_ratio"       : S_fleet_r / S_fleet_hist if S_fleet_hist > 0 else np.nan,
        # Cabinet power
        "B_cab_h"             : B_cab_r,
        "S_cab_Wh"            : S_cab_r,
        "B_cab_ratio"         : B_cab_r / B_cab_hist if B_cab_hist > 0 else np.nan,
        "S_cab_ratio"         : S_cab_r / S_cab_hist if S_cab_hist > 0 else np.nan,
        # Sensitivity (max threshold)
        "B_fleet_max_h"       : B_fleet_max_r,
    }

# ============================================================
# Crossing helper
# ============================================================
def find_crossing(rows: list[dict], ratio_key: str, target: float = 1.0) -> float | None:
    valid = [r for r in rows if ratio_key in r and not np.isnan(r[ratio_key])]
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

# ============================================================
# Main sweep
# ============================================================
print("\n" + "=" * 72)
print("POWER SWEEP  (single scenario, 3 policies)")
print("=" * 72)

n_extra_max = int(np.ceil((LAMBDA_MAX - 1.0) * n_base))
print(f"\nGenerating synthetic pool: {n_extra_max} jobs ...")
syn_pool = sample_synthetic_pool(n_extra_max, WORKLOAD_SEED)
print(f"  Pool: {len(syn_pool)} synthetic jobs")

print("Pre-generating residual permutations (CRN)...")
scen_rng  = np.random.default_rng(SCENARIO_SEED)
job_perms = generate_job_perms(syn_pool, scen_rng)
print(f"  {len(job_perms)} permutations generated\n")

all_results: dict[str, list[dict]] = {pk: [] for pk in POLICY_KEYS}

for lam in LAMBDA_SWEEP:
    n_syn      = int(round((lam - 1.0) * n_base))
    syn_subset = syn_pool.iloc[:n_syn].copy() if n_syn > 0 else pd.DataFrame(
        columns=syn_pool.columns if len(syn_pool) > 0 else jobs_sorted.columns)

    added_pct = (lam - 1.0) * 100.0
    print(f"--- lam={lam:.2f} (+{added_pct:.0f}% offered)  N_syn={n_syn} ---")
    hdr = (f"  {'Policy':<20} | {'NH%':>5} | {'B/Bh':>6} | {'B_flt':>6} | "
           f"{'B_cab':>6} | {'B_flt_max':>9} | drops")
    print(hdr)
    print("  " + "-" * (len(hdr) - 2))

    for pk, delta_cap, label, color, marker in POLICY_DEFS:
        t0  = time.time()
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

        drops = f"{res['n_drop_physical']}/{res['n_drop_cap']}/{res['n_drop_la']}"
        bf_r  = res.get("B_fleet_ratio", float("nan"))
        bc_r  = res.get("B_cab_ratio",   float("nan"))
        bfm_h = res.get("B_fleet_max_h", float("nan"))
        bf_s  = f"{bf_r:.4f}" if not np.isnan(bf_r) else "  nan "
        bc_s  = f"{bc_r:.4f}" if not np.isnan(bc_r) else "  nan "
        bfm_s = f"{bfm_h:.3f}h" if not np.isnan(bfm_h) else "  nan "
        print(f"  {label:<20} | {res['capacity_unlock_pct']:>5.1f} |"
              f" {res['B_node_ratio']:>6.4f} | {bf_s} | {bc_s} | {bfm_s:>9} |"
              f" {drops}  ({elapsed:.0f}s)")

# ============================================================
# Crossing analysis
# ============================================================
print("\n" + "=" * 72)
print("POWER-ENVELOPE CROSSING ANALYSIS")
print("=" * 72)

# Load thermal crossings from phase3b2d
try:
    with open(ANALYSIS_DIR / "phase3b2d_results.json") as f:
        thermal_data = json.load(f)
    thermal_cross = thermal_data["crossings"]
except Exception as e:
    print(f"  WARNING: could not load thermal crossings: {e}")
    thermal_cross = {}

power_crossings: dict[str, dict] = {}
for pk, delta_cap, label, color, marker in POLICY_DEFS:
    rows  = all_results[pk]
    c_Bf  = find_crossing(rows, "B_fleet_ratio")
    c_Sf  = find_crossing(rows, "S_fleet_ratio")
    c_Bc  = find_crossing(rows, "B_cab_ratio")
    c_Sc  = find_crossing(rows, "S_cab_ratio")
    power_crossings[pk] = {
        "C_fleet_B": c_Bf, "C_fleet_S": c_Sf,
        "C_cab_B": c_Bc,   "C_cab_S": c_Sc,
        "label": label,
    }

def fmt(v):
    return f"{v:.1f}%" if v is not None else ">explored"

print(f"\n  Power crossings (NH% at budget-ratio = 1.0):")
print(f"  {'Policy':<20} | {'C_fleet_B':>10} | {'C_fleet_S':>10} | "
      f"{'C_cab_B':>10} | {'C_cab_S':>10}")
print("  " + "-" * 70)
for pk, delta_cap, label, color, marker in POLICY_DEFS:
    pc = power_crossings[pk]
    print(f"  {label:<20} | {fmt(pc['C_fleet_B']):>10} | {fmt(pc['C_fleet_S']):>10} | "
          f"{fmt(pc['C_cab_B']):>10} | {fmt(pc['C_cab_S']):>10}")

print(f"\n  Max-threshold sensitivity (B_fleet_max_h > 0 means new power peak):")
print(f"  {'Policy':<20} | {'lam':>5} | {'B_fleet_max_h':>14} | note")
print("  " + "-" * 60)
for pk, delta_cap, label, color, marker in POLICY_DEFS:
    for r in all_results[pk]:
        bfm = r.get("B_fleet_max_h", 0.0)
        if bfm is not None and bfm > 0:
            print(f"  {label:<20} | {r['lambda_val']:>5.2f} | {bfm:>14.3f} h | first exceedance")
            break
    else:
        print(f"  {label:<20} | {'---':>5} | {'0.000':>14} h | never exceeded hist max")

# ============================================================
# Final C_feasible table
# ============================================================
print(f"\n{'=' * 72}")
print("FINAL C_feasible = min(C_B_thermal, C_S_thermal, C_fleet_power, C_cabinet_power)")
print(f"{'=' * 72}")

print(f"\n  {'Policy':<20} | {'C_B_therm':>10} | {'C_S_therm':>10} | "
      f"{'C_flt_B':>10} | {'C_cab_B':>10} | {'C_feasible':>12} | {'delta':>10}")
print("  " + "-" * 90)

rand_cfeas = None
for pk, delta_cap, label, color, marker in POLICY_DEFS:
    tc = thermal_cross.get(pk, {})
    c_BT = tc.get("C_B")
    c_ST = tc.get("C_S")
    pc   = power_crossings[pk]
    c_Bf = pc["C_fleet_B"]
    c_Bc = pc["C_cab_B"]

    candidates = [x for x in [c_BT, c_ST, c_Bf, c_Bc] if x is not None]
    cfeas = min(candidates) if candidates else None

    if pk == "random":
        rand_cfeas = cfeas

    delta = (cfeas - rand_cfeas) if (cfeas is not None and rand_cfeas is not None) else None
    delta_s = f"+{delta:.1f} pp" if delta is not None else "N/A"

    cfeas_s = f"{cfeas:.1f}%" if cfeas is not None else ">explored"
    print(f"  {label:<20} | {fmt(c_BT):>10} | {fmt(c_ST):>10} | "
          f"{fmt(c_Bf):>10} | {fmt(c_Bc):>10} | {cfeas_s:>12} | {delta_s:>10}")

# ============================================================
# Figure
# ============================================================
print("\nGenerating power-envelope figure...")
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

for ax_idx, (ratio_key, ylabel, title) in enumerate([
    ("B_fleet_ratio", "B_fleet / B_fleet_hist", "Fleet power exposure budget (B)"),
    ("B_cab_ratio",   "B_cab / B_cab_hist",     "Cabinet power exposure budget (B)"),
]):
    ax = axes[ax_idx]
    for pk, delta_cap, label, color, marker in POLICY_DEFS:
        rows = [r for r in all_results[pk] if ratio_key in r and not np.isnan(r.get(ratio_key, float("nan")))]
        xs = [r["capacity_unlock_pct"] for r in rows]
        ys = [r[ratio_key] for r in rows]
        ls = "--" if pk == "random" else "-"
        ax.plot(xs, ys, color=color, marker=marker, ls=ls, lw=2, label=label)
    ax.axhline(1.0, color="black", lw=1.5, ls=":", label="Historical budget")
    ax.set_xlabel("Added workload (% of hist. node-hours)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

plt.tight_layout()
outfig = ANALYSIS_DIR / "phase3b3_power.png"
fig.savefig(outfig, dpi=150)
plt.close()
print(f"  Saved {outfig}")

# ============================================================
# Save JSON
# ============================================================
out = {
    "P_fleet_p99_hist_W" : P_fleet_p99_hist,
    "P_fleet_max_hist_W" : P_fleet_max_hist,
    "B_fleet_hist_h"     : B_fleet_hist,
    "B_cab_hist_h"       : B_cab_hist,
    "total_test_period_h": total_test_h,
    "lambda_sweep"       : LAMBDA_SWEEP,
    "power_crossings"    : power_crossings,
    "policy_results"     : {pk: rows for pk, rows in all_results.items()},
}
outpath = ANALYSIS_DIR / "phase3b3_results.json"
with open(outpath, "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"  Saved {outpath}")

print("\n=== Done ===")
