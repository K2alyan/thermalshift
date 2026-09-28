#!/usr/bin/env python3
"""
Phase 3B Monte Carlo: 30 scenarios, Random-feasible vs FP-cap-10.
Tier-cap-20 run as single cautionary scenario (s=0).

Common Random Numbers (CRN): within each scenario both policies share the
same synthetic workload draw and residual permutations; only node selection
differs by policy.

Outputs:
  phase3b_mc_results.json   — full per-scenario data
  phase3b_mc_summary.txt    — console-formatted summary table
"""

import os
import pandas as pd
import numpy as np
import json, time, re
from pathlib import Path
from collections import defaultdict

ANALYSIS_DIR = Path(__file__).parent
# Set THERMALSHIFT_DATA_DIR env var to your local Frontier dataset directory.
DATA_DIR     = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

BETA_F        = 0.9569
N_BINS        = 5
T_P95_THRESHOLD = 60.602770562770566
P50_PWR         = 896.4571428571429
P80_PWR         = 1496.4923809523812
P95_PWR         = 1955.5884126984126

N_SCENARIOS      = 30
MC_BASE_SEED     = 200          # distinct from baseline SCENARIO_SEED=42
MC_LAMBDA_SWEEP  = [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40, 1.50]
MC_LAMBDA_MAX    = max(MC_LAMBDA_SWEEP)
LARGE_NODE_THRESH = 512         # node_count threshold for "large job"

MC_POLICIES = [
    ("random", 1e6,  "Random-feasible"),
    ("fp",     0.10, "FP-cap-10"),
]
TIER_POLICY = ("tier20", 0.20, "Tier-cap-20")

# ============================================================
# Load
# ============================================================
print("=== Phase 3B Monte Carlo ===\n")
t_load = time.time()

fp_df      = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set = set(fp_df.index)
F_dict     = fp_df["FA_2024"].to_dict()
cohort_list = sorted(cohort_set)
n_cohort   = len(cohort_list)
print(f"Cohort: {n_cohort} nodes")

test_df  = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"Total jobs: {len(all_jobs):,}")

# ============================================================
# Cabinet map
# ============================================================
print("Building cabinet map...")
_xe2_re = re.compile(r"x(\d+)c")
node_to_cabinet: dict[str, int] = {}
for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    for hn, xn in zip(hl, str(nl).split()):
        xn = xn.strip("'[]\"")
        if hn not in node_to_cabinet:
            m = _xe2_re.match(xn)
            if m:
                node_to_cabinet[hn] = int(m.group(1))
all_cabinets = sorted(set(node_to_cabinet.values()))
print(f"  {len(node_to_cabinet):,} nodes, {len(all_cabinets)} cabinets")

# ============================================================
# Schedule arrays
# ============================================================
def _col_to_dt64ms(series):
    s = pd.to_datetime(series, utc=True)
    return s.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ms]")

def _to_dt64_ms(ts):
    t = pd.Timestamp(ts)
    if t.tzinfo is None: t = t.tz_localize("UTC")
    return np.datetime64(t.tz_convert("UTC").tz_localize(None), "ms")

def _dt64_to_h(a, b):
    return float((b - a).astype("int64")) / 3.6e6

print("Schedule arrays...")
cohort_per_job: dict[int, frozenset] = {}
for jid, hl in zip(all_jobs["job_idx_int"].values, all_jobs["host_list"].values):
    cn = frozenset(n for n in hl if n in cohort_set)
    if cn:
        cohort_per_job[jid] = cn

has_cohort = np.array([jid in cohort_per_job for jid in all_jobs["job_idx_int"].values])
sched_jids = all_jobs["job_idx_int"].values[has_cohort]
sched_st   = _col_to_dt64ms(all_jobs["start_time"])[has_cohort]
sched_et   = _col_to_dt64ms(all_jobs["end_time"])[has_cohort]
sched_cn   = np.array([cohort_per_job[jid] for jid in sched_jids], dtype=object)
print(f"  {len(sched_jids):,} entries")

# ============================================================
# Job-level summary
# ============================================================
print("Job summary and residuals...")
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
test_id_set  = set(job_agg["job_idx"].astype(int))
jobs_sorted  = job_agg.sort_values("start_time").reset_index(drop=True)
n_base       = len(jobs_sorted)

hist_node_hours = {n: 0.0 for n in cohort_list}
for _, jrow in jobs_sorted.iterrows():
    rt_h = float(jrow["run_time"]) / 3600.0
    for nd in jrow["hist_nodes"]:
        if nd in hist_node_hours:
            hist_node_hours[nd] += rt_h
hist_util_arr = np.array([hist_node_hours[n] for n in cohort_list])
hist_total_nh = float(hist_util_arr.sum())
hist_fleet_avg = hist_total_nh / n_cohort

rt_lookup   = jobs_sorted.set_index("job_idx")["run_time"].to_dict()
test_rt_h   = test_df["job_idx"].map(lambda j: rt_lookup.get(int(j), 0.0)) / 3600.0
node_excess = test_df["T_p95"] - T_P95_THRESHOLD
B_hist_node = float((test_rt_h * (node_excess > 0)).sum())
S_hist_node = float((test_rt_h * node_excess.clip(lower=0)).sum())

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

# bg_busy_per_job
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

hist_starts_dt64 = np.array([_to_dt64_ms(r["start_time"]) for _, r in jobs_sorted.iterrows()])
hist_ends_dt64   = np.array([_to_dt64_ms(r["end_time"])   for _, r in jobs_sorted.iterrows()])
hist_k_arr       = jobs_sorted["n_cohort"].values.astype(int)
hist_jids_arr    = jobs_sorted["job_idx"].values.astype(int)
print(f"  {n_base} base jobs  (elapsed {time.time()-t_load:.0f}s)")

# ============================================================
# Full-cabinet background
# ============================================================
print("\nPrecomputing full-cabinet background...")
t0 = time.time()

bg_records: list[dict] = []
cohort_hist_records: list[dict] = []

_all_jids = all_jobs["job_idx_int"].values
_all_Pj   = np.where(all_jobs["mean_power"].isna().values, 0.0,
                     all_jobs["mean_power"].values.astype(float))
_all_nc   = np.maximum(all_jobs["node_count"].values.astype(int), 1)
_all_hl   = all_jobs["host_list"].values
_all_st   = _col_to_dt64ms(all_jobs["start_time"])
_all_et   = _col_to_dt64ms(all_jobs["end_time"])

for jid, P_j, nc, hl, t_s, t_e in zip(_all_jids, _all_Pj, _all_nc, _all_hl, _all_st, _all_et):
    ppn = P_j / nc
    ncc: dict[int, int] = {}
    chc: dict[int, int] = {}
    for hn in hl:
        c = node_to_cabinet.get(hn, -1)
        if c < 0: continue
        if hn in cohort_set: chc[c] = chc.get(c, 0) + 1
        else:                ncc[c] = ncc.get(c, 0) + 1
    if ncc:
        bg_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": ncc})
    if int(jid) in test_id_set and chc:
        cohort_hist_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": chc})

print(f"  bg: {len(bg_records):,} jobs  cohort_hist: {len(cohort_hist_records):,}  ({time.time()-t0:.1f}s)")

def per_cabinet_p99(records):
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
                    if Pc > 1e-9: cab_ivals[c2].append((dt_h, Pc))
        P_cab[c] += sign * dp; t_prev = t
    result = {}
    for c, ivals in cab_ivals.items():
        total = sum(d for d, _ in ivals)
        s = sorted(ivals, key=lambda x: x[1])
        target = total * 0.99; cum = 0.0; result[c] = s[-1][1]
        for dt, pwr in s:
            cum += dt
            if cum >= target: result[c] = pwr; break
    return result

def sweep_cab_budget(records, cab_threshold):
    events = []
    for r in records:
        ppn = r["ppn"]
        for c, n in r["cab_counts"].items():
            events.append((r["t_s"], +1, c, ppn * n))
            events.append((r["t_e"], -1, c, ppn * n))
    events.sort(key=lambda x: (x[0], x[1]))
    P_cab: dict[int, float] = defaultdict(float)
    last_t: dict[int, object] = {}
    B_tot = 0.0
    for t, sign, c, dp in events:
        if c in last_t and t != last_t[c]:
            dt_h = _dt64_to_h(last_t[c], t)
            if dt_h > 0:
                exc = P_cab[c] - cab_threshold.get(c, 0.0)
                if exc > 0: B_tot += dt_h
        P_cab[c] += sign * dp; last_t[c] = t
    return B_tot

print("Computing full-cabinet p99...")
t0 = time.time()
combined_hist   = bg_records + cohort_hist_records
P_cab_p99_full  = per_cabinet_p99(combined_hist)
B_cab_hist_full = sweep_cab_budget(combined_hist, P_cab_p99_full)
print(f"  {len(P_cab_p99_full)} cabinets  B_cab_hist={B_cab_hist_full:.2f} h  ({time.time()-t0:.1f}s)")

# ============================================================
# Window-matched denominator
# ============================================================
_test_jids_str = set(test_df["job_idx"].astype(str))
_test_meta     = all_jobs[all_jobs["job_idx"].isin(_test_jids_str)]
D_replay       = set(_test_meta["date_dir"].dropna().unique())
_rmask         = all_jobs["date_dir"].isin(D_replay)
H_all_replay   = float(
    (all_jobs.loc[_rmask, "node_count"].astype(float) *
     all_jobs.loc[_rmask, "run_time"].astype(float) / 3600.0).sum()
)
print(f"\nH_all_replay = {H_all_replay:,.0f} nh  ({len(D_replay)} replay dates)")
print(f"H_cohort_base/H_all_replay = {hist_total_nh/H_all_replay:.4f} ({hist_total_nh/H_all_replay:.2%})")

# Coolest-10% node set (by fingerprint F, ascending)
_n_cool10 = max(1, int(0.10 * n_cohort))
_sorted_by_F = sorted(cohort_list, key=lambda n: F_dict[n])
_cool10_set  = set(_sorted_by_F[:_n_cool10])

# ============================================================
# Helpers
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
    if not overlap_mask.any(): return True
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

def _gini(vals):
    v = np.sort(np.array(vals, dtype=float))
    n = len(v); s = v.sum()
    if s <= 0 or n == 0: return 0.0
    idx = np.arange(1, n + 1, dtype=float)
    return float((2 * (idx * v).sum() - (n + 1) * s) / (n * s))

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
# capacity_replay_mc — thermal + cabinet + workload metrics
# ============================================================
def capacity_replay_mc(syn_subset, policy, delta_cap, lambda_val,
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
    n_syn_admit     = 0; n_drop_cap = 0; n_drop_phys = 0; n_drop_la = 0
    n_base_unserved = 0
    n_syn_large_admit = 0; n_syn_large_total = 0

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

        if is_syn and nc >= LARGE_NODE_THRESH:
            n_syn_large_total += 1

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
                if nc >= LARGE_NODE_THRESH:
                    n_syn_large_admit += 1
            cc: dict[int, int] = {}
            for nd in selected:
                c = node_to_cabinet.get(nd, -1)
                if c >= 0: cc[c] = cc.get(c, 0) + 1
            if cc:
                cohort_records.append({"t_s": t_j, "t_e": t_e, "ppn": ppn, "cab_counts": cc})

    if n_base_unserved > 0:
        raise AssertionError(f"Base-job invariant violated: {n_base_unserved}")

    unlock_pct = syn_node_hours / hist_total_nh * 100.0

    full_records = bg_records + cohort_records
    B_cb_full = sweep_cab_budget(full_records, P_cab_p99_full)
    B_cb_ratio = B_cb_full / max(B_cab_hist_full, 1e-9)

    util_vals = np.array(list(cf_util.values()))
    gini = _gini(util_vals)
    total_util = float(util_vals.sum())
    cool_util  = sum(cf_util.get(n, 0.0) for n in _cool10_set)
    coolest10_share = cool_util / total_util if total_util > 0 else 0.0
    large_frac = (n_syn_large_admit / max(n_syn_large_total, 1)
                  if n_syn_large_total > 0 else float("nan"))

    return {
        "lambda_val"          : lambda_val,
        "policy"              : policy,
        "capacity_unlock_pct" : unlock_pct,
        "syn_node_hours"      : syn_node_hours,
        "n_syn_admit"         : n_syn_admit,
        "n_drop_cap"          : n_drop_cap,
        "n_drop_physical"     : n_drop_phys,
        "n_drop_la"           : n_drop_la,
        "B_node_ratio"        : B_node / B_hist_node if B_hist_node > 0 else float("nan"),
        "S_node_ratio"        : S_node / S_hist_node if S_hist_node > 0 else float("nan"),
        "B_cab_ratio_full"    : B_cb_ratio,
        "gini_util"           : gini,
        "coolest10_share"     : coolest10_share,
        "large_job_frac"      : large_frac,
    }

def find_crossing(rows, key, target=1.0):
    valid = [r for r in rows
             if key in r and not (isinstance(r.get(key), float) and np.isnan(r[key]))]
    if not valid: return None
    xs = [r["capacity_unlock_pct"] for r in valid]
    ys = [r[key] for r in valid]
    for i in range(len(ys) - 1):
        if ys[i] <= target <= ys[i + 1]:
            frac = (target - ys[i]) / max(ys[i + 1] - ys[i], 1e-12)
            return float(xs[i] + frac * (xs[i + 1] - xs[i]))
        if i == 0 and ys[i] >= target:
            return 0.0
    return None

def fmt_pct(v):
    return f"{v:.2f}%" if v is not None else ">expl"

# ============================================================
# MC loop
# ============================================================
n_extra_max = int(np.ceil((MC_LAMBDA_MAX - 1.0) * n_base))
print(f"\nMax synthetic pool: {n_extra_max} jobs")
print(f"Lambda sweep: {MC_LAMBDA_SWEEP}")
print(f"Scenarios: {N_SCENARIOS}  (Tier-cap-20 at scenario 0 only)\n")

all_mc = []
CKPT_PATH = ANALYSIS_DIR / "phase3b_mc_checkpoint.json"

t_mc_start = time.time()
for s in range(N_SCENARIOS):
    scen_seed   = MC_BASE_SEED + s * 97          # independent per scenario
    wl_seed     = scen_seed + 50000              # workload draw seed
    perm_seed   = scen_seed                      # residual permutation seed
    t_scen = time.time()

    scen_rng = np.random.default_rng(perm_seed)
    syn_pool = sample_synthetic_pool(n_extra_max, wl_seed)
    job_perms = generate_job_perms(syn_pool, scen_rng)

    run_policies = list(MC_POLICIES)
    if s == 0:
        run_policies = run_policies + [TIER_POLICY]

    scen_data = {"scenario": s, "scen_seed": scen_seed}

    for pk, delta_cap, label in run_policies:
        rows = []
        for lam in MC_LAMBDA_SWEEP:
            n_syn = int(round((lam - 1.0) * n_base))
            syn_sub = syn_pool.iloc[:n_syn].copy() if n_syn > 0 else pd.DataFrame(
                columns=syn_pool.columns if len(syn_pool) > 0 else jobs_sorted.columns)
            res = capacity_replay_mc(
                syn_sub, pk, delta_cap, lam,
                policy_seed=scen_seed + abs(hash(pk)) % 10000,
                job_perms=job_perms,
            )
            rows.append(res)

        c_BT  = find_crossing(rows, "B_node_ratio")
        c_ST  = find_crossing(rows, "S_node_ratio")
        c_cab = find_crossing(rows, "B_cab_ratio_full")
        cands = [x for x in [c_BT, c_ST, c_cab] if x is not None]
        cfeas = min(cands) if cands else None

        H_syn    = cfeas / 100.0 * hist_total_nh if cfeas is not None else None
        c_sys    = H_syn / H_all_replay * 100.0  if H_syn is not None else None

        # Metrics at the lambda closest to cfeas (or last lambda)
        def _at_cfeas(key):
            if cfeas is None or not rows: return rows[-1].get(key) if rows else None
            best_row = min(rows, key=lambda r: abs(r["capacity_unlock_pct"] - cfeas))
            return best_row.get(key)

        scen_data[pk] = {
            "C_B_th"           : c_BT,
            "C_S_th"           : c_ST,
            "C_cab_full"       : c_cab,
            "C_feasible"       : cfeas,
            "C_system_replay"  : c_sys,
            "syn_node_hours"   : H_syn,
            "gini_util"        : _at_cfeas("gini_util"),
            "coolest10_share"  : _at_cfeas("coolest10_share"),
            "large_job_frac"   : _at_cfeas("large_job_frac"),
            "rows"             : rows,
        }

    cfeas_fp  = scen_data.get("fp",     {}).get("C_feasible")
    cfeas_rnd = scen_data.get("random", {}).get("C_feasible")
    scen_data["delta_C"] = ((cfeas_fp - cfeas_rnd)
                             if cfeas_fp is not None and cfeas_rnd is not None
                             else None)

    all_mc.append(scen_data)

    elapsed = time.time() - t_scen
    tier_note = ""
    if s == 0:
        tc = scen_data.get("tier20", {})
        tier_note = f"  Tier: {fmt_pct(tc.get('C_feasible'))}"
    print(f"  s={s:02d}  Random={fmt_pct(cfeas_rnd)}  FP={fmt_pct(cfeas_fp)}  "
          f"dC={fmt_pct(scen_data.get('delta_C'))}  ({elapsed:.0f}s){tier_note}")

    # Checkpoint
    try:
        with open(CKPT_PATH, "w") as f:
            json.dump(all_mc, f, indent=2, default=str)
    except Exception:
        pass

total_mc_h = (time.time() - t_mc_start) / 3600.0
print(f"\nMC complete: {N_SCENARIOS} scenarios in {total_mc_h:.2f} h")

# ============================================================
# Summary
# ============================================================
def mc_cfeas(pk):
    return [s[pk]["C_feasible"] for s in all_mc if pk in s and s[pk]["C_feasible"] is not None]

def mc_delta():
    return [s["delta_C"] for s in all_mc if s.get("delta_C") is not None]

def pctile(arr, p):
    return float(np.percentile(arr, p)) if arr else float("nan")

rnd_cf = mc_cfeas("random")
fp_cf  = mc_cfeas("fp")
dc     = mc_delta()

lines = []
lines.append("\n" + "="*65)
lines.append("MC SUMMARY")
lines.append("="*65)
lines.append(f"\n  Scenarios: {N_SCENARIOS}  |  H_all_replay: {H_all_replay:,.0f} nh")
lines.append(f"  H_cohort_base: {hist_total_nh:,.0f} nh  |  ratio: {hist_total_nh/H_all_replay:.4f}\n")

lines.append(f"  {'Metric':<28} {'Random-feasible':>16} {'FP-cap-10':>12}")
lines.append("  " + "-"*58)
for label, arr in [("C_feasible median (%)", [rnd_cf, fp_cf]),
                   ("C_feasible 5th pct (%)", [rnd_cf, fp_cf]),
                   ("C_feasible 95th pct (%)", [rnd_cf, fp_cf])]:
    p_val = {"median": 50, "5th": 5, "95th": 95}[label.split()[1].rstrip(" (%)")]
    vals  = [f"{pctile(a, p_val):>9.2f}%" for a in arr]
    lines.append(f"  {label:<28} {vals[0]:>16} {vals[1]:>12}")

lines.append("")
lines.append(f"  dC = C_FP - C_Random per scenario:")
lines.append(f"    median={pctile(dc,50):.2f} pp    5th={pctile(dc,5):.2f} pp    95th={pctile(dc,95):.2f} pp")

lines.append("\n  Per-scenario table:")
lines.append(f"  {'s':>3} {'Random C_feas':>14} {'FP C_feas':>10} {'dC':>8} "
             f"{'C_sys_rnd':>10} {'C_sys_fp':>9}")
lines.append("  " + "-"*58)
for sd in all_mc:
    rnd = sd.get("random", {}); fp = sd.get("fp", {})
    cf_r = rnd.get("C_feasible"); cf_f = fp.get("C_feasible")
    dc_s = sd.get("delta_C")
    cs_r = rnd.get("C_system_replay"); cs_f = fp.get("C_system_replay")
    def _f(v, d=2): return f"{v:.{d}f}%" if v is not None else " n/a"
    lines.append(f"  {sd['scenario']:>3} {_f(cf_r):>14} {_f(cf_f):>10} {_f(dc_s):>8} "
                 f"{_f(cs_r,3):>10} {_f(cs_f,3):>9}")

if "tier20" in all_mc[0]:
    tc = all_mc[0]["tier20"]
    lines.append(f"\n  Tier-cap-20 (scenario 0 only):")
    lines.append(f"    C_B={fmt_pct(tc.get('C_B_th'))}  C_S={fmt_pct(tc.get('C_S_th'))}"
                 f"  C_cab={fmt_pct(tc.get('C_cab_full'))}  C_feasible={fmt_pct(tc.get('C_feasible'))}")
    lines.append(f"    C_system_replay={fmt_pct(tc.get('C_system_replay'))}")

lines.append("="*65)
summary_text = "\n".join(lines)
print(summary_text)

# ============================================================
# Save
# ============================================================
out = {
    "N_scenarios"       : N_SCENARIOS,
    "MC_lambda_sweep"   : MC_LAMBDA_SWEEP,
    "H_all_replay_nh"   : H_all_replay,
    "H_cohort_hist_nh"  : hist_total_nh,
    "D_replay_n_dates"  : len(D_replay),
    "B_hist_node"       : B_hist_node,
    "S_hist_node"       : S_hist_node,
    "summary": {
        "random": {
            "C_feasible_median": pctile(rnd_cf, 50),
            "C_feasible_p05"   : pctile(rnd_cf, 5),
            "C_feasible_p95"   : pctile(rnd_cf, 95),
        },
        "fp": {
            "C_feasible_median": pctile(fp_cf, 50),
            "C_feasible_p05"   : pctile(fp_cf, 5),
            "C_feasible_p95"   : pctile(fp_cf, 95),
        },
        "delta_C": {
            "median": pctile(dc, 50),
            "p05"   : pctile(dc, 5),
            "p95"   : pctile(dc, 95),
        },
    },
    "scenarios": all_mc,
}
out_path = ANALYSIS_DIR / "phase3b_mc_results.json"
with open(out_path, "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\n  Saved {out_path}")

summary_path = ANALYSIS_DIR / "phase3b_mc_summary.txt"
with open(summary_path, "w") as f:
    f.write(summary_text + "\n")
print(f"  Saved {summary_path}")
print("\n=== Done ===")
