# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.2b: Capacity-unlock experiment — absolute thermal-exposure budget.

Metric formulations
-------------------
Job-level (prior version, kept for comparison):
  B_hist_job = sum_j N_j * t_j * 1[mean(T_p95,ij) > T_95]
  B_policy_job = sum_j N_j * t_j * 1[T_hat_j > T_95]  (T_hat_j uses mean selected F)

Node-level (primary, this version):
  B_hist_node = sum_j sum_{i in j} t_j * 1[T_p95,ij > T_95]   (actual observed, exact)
  B_policy_node = sum_j sum_{i in selected(j)} t_j * 1[T_hat_ij > T_95]
                  where T_hat_ij = T_median_j + beta_F * F_i     (per-node counterfactual)

  S variants weight by degree above threshold instead of binary indicator.

Unchanged: stateful replay, nested workloads, base-job protection, actual node-hour
accounting for x-axis, all four policies.
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import re, json, time
from pathlib import Path

ANALYSIS_DIR  = Path(__file__).parent
DATA_DIR      = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

BETA_F        = 0.9569
SEED          = 42
WORKLOAD_SEED = 77777

N_SCENARIOS   = 1

LAMBDA_SWEEP  = [1.00, 1.01, 1.02, 1.03, 1.04, 1.05, 1.07, 1.10, 1.12, 1.15, 1.20, 1.25, 1.30]

RELATIVE_CAP  = True

# (policy_key, delta_cap, label, color, marker, policy_seed_offset)
POLICY_DEFS = [
    ("random",      1e6,  "Random-feasible", "#888888", "o", 0),
    ("fingerprint", 0.10, "FP-cap-10",       "#ee7722", "s", 1),
    ("tier",        1e6,  "Tier-no-cap",      "#aa44cc", "^", 2),
    ("tier",        0.20, "Tier-cap-20",      "#22aa55", "D", 3),
]

# From 3B.1-H (hard-coded; do not recompute)
T_P95_THRESHOLD     = 60.602770562770566
HIST_P95_EXCEEDANCE = 0.05005688282138794
P50_PWR = 896.4571428571429
P80_PWR = 1496.4923809523812
P95_PWR = 1955.5884126984126

print("=== Phase 3B.2b: Capacity-unlock (node-level absolute budget) ===")
print(f"  RELATIVE_CAP={RELATIVE_CAP}  N_SCENARIOS={N_SCENARIOS}\n")

# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
print("Loading fingerprints...")
fp_df        = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set   = set(fp_df.index)
F_dict       = fp_df["FA_2024"].to_dict()
cohort_list  = sorted(cohort_set)
F_cohort_arr      = np.array([F_dict[n] for n in cohort_list])
F_cohort_sort_idx = np.argsort(F_cohort_arr)
n_cohort          = len(cohort_list)
print(f"  Cohort: {n_cohort:,} nodes")

print("Loading test set...")
test_df = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")

print("Loading full job schedule...")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"  {len(all_jobs):,} total jobs")

# ---------------------------------------------------------------------------
# Topology
# ---------------------------------------------------------------------------
print("\nBuilding topology map...")
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
print(f"  Mapped {len(node_to_cabinet)}/{n_cohort}  ({time.time()-t0:.1f}s)")

# ---------------------------------------------------------------------------
# Schedule arrays
# ---------------------------------------------------------------------------
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
print(f"  {len(sched_jids):,} entries  ({time.time()-t0:.1f}s)")

# ---------------------------------------------------------------------------
# Job-level test summary
# ---------------------------------------------------------------------------
print("\nBuilding job-level test summary...")
job_agg = (
    test_df.groupby("job_idx")
    .agg(F_hist_mean=("F_2024", "mean"), n_cohort=("node", "count"),
         T_p95_hist=("T_p95", "mean"),
         T_median_hist=("T_p95", "median"),   # within-job thermal center for node-level model
         hist_nodes=("node", list))
    .reset_index()
)
meta = (
    all_jobs[["job_idx_int", "node_count", "start_time", "end_time", "mean_power", "run_time"]]
    .rename(columns={"job_idx_int": "job_idx"})
)
job_agg = job_agg.merge(meta, on="job_idx", how="left")
job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)
test_id_set = set(job_agg["job_idx"].astype(int))
jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)
n_base      = len(jobs_sorted)
print(f"  {n_base} base test jobs")

# Historical node-hours (reference for utilization cap)
hist_node_hours = {n: 0.0 for n in cohort_list}
for _, jrow in jobs_sorted.iterrows():
    rt_h = float(jrow["run_time"]) / 3600.0
    for n in jrow["hist_nodes"]:
        if n in hist_node_hours:
            hist_node_hours[n] += rt_h
hist_util_arr  = np.array([hist_node_hours[n] for n in cohort_list])
hist_total_nh  = hist_util_arr.sum()
hist_fleet_avg = hist_total_nh / n_cohort
print(f"  Hist fleet avg: {hist_fleet_avg:.2f} h/node  total: {hist_total_nh:.0f} h")
print(f"  p95 threshold: {T_P95_THRESHOLD:.3f} degC  hist exceedance rate: {HIST_P95_EXCEEDANCE:.4f}")

# ---------------------------------------------------------------------------
# Thermal-exposure budgets
# ---------------------------------------------------------------------------
# --- Job-level (prior metric; kept for comparison table) ---
# B_hist_job = sum_j N_j * t_j * 1[mean(T_p95,ij) > T_95]
B_hist_job = 0.0
S_hist_job = 0.0
for _, jrow in jobs_sorted.iterrows():
    rt_h   = float(jrow["run_time"]) / 3600.0
    n_j    = int(jrow["n_cohort"])
    T_j    = float(jrow["T_p95_hist"])
    nh_j   = n_j * rt_h
    excess = T_j - T_P95_THRESHOLD
    if excess > 0:
        B_hist_job += nh_j
        S_hist_job += nh_j * excess
print(f"\n  Job-level budget (approximation):")
print(f"    B_hist_job = {B_hist_job:.1f} h  S_hist_job = {S_hist_job:.1f} degC-h")
print(f"    B_hist_job / hist_total_nh = {B_hist_job/hist_total_nh:.4f}"
      f"  (job-count rate={HIST_P95_EXCEEDANCE:.4f}; hot jobs are larger)")

# --- Node-level (primary metric) ---
# B_hist_node = sum_j sum_{i in j} t_j * 1[T_p95,ij > T_95]   exact observed per-node temps
rt_lookup = jobs_sorted.set_index("job_idx")["run_time"].to_dict()
test_rt_h  = test_df["job_idx"].map(lambda jid: rt_lookup.get(int(jid), 0.0)) / 3600.0
node_excess = test_df["T_p95"] - T_P95_THRESHOLD
B_hist_node = float((test_rt_h * (node_excess > 0)).sum())
S_hist_node = float((test_rt_h * node_excess.clip(lower=0)).sum())
print(f"\n  Node-level budget (exact observed):")
print(f"    B_hist_node = {B_hist_node:.1f} h  S_hist_node = {S_hist_node:.1f} degC-h")
print(f"    B_hist_node / B_hist_job = {B_hist_node/B_hist_job:.3f}"
      f"  S_hist_node / S_hist_job = {S_hist_node/S_hist_job:.3f}")
print(f"    B_hist_node / hist_total_nh = {B_hist_node/hist_total_nh:.4f}")

# ---------------------------------------------------------------------------
# Background busy
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Look-ahead arrays
# ---------------------------------------------------------------------------
def _to_dt64_ms(ts) -> np.datetime64:
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

hist_starts_dt64 = np.array([_to_dt64_ms(r["start_time"]) for _, r in jobs_sorted.iterrows()])
hist_ends_dt64   = np.array([_to_dt64_ms(r["end_time"])   for _, r in jobs_sorted.iterrows()])
hist_k_arr       = jobs_sorted["n_cohort"].values.astype(int)
hist_jids_arr    = jobs_sorted["job_idx"].values.astype(int)

# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------
def to_dt64(ts) -> np.datetime64:
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

def bg_busy_at(t_np: np.datetime64) -> frozenset:
    mask = (bg_st <= t_np) & (bg_et > t_np)
    return frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

def gini(arr: np.ndarray) -> float:
    a = np.abs(np.sort(arr))
    n = len(a)
    if n == 0 or a.sum() == 0:
        return 0.0
    idx = np.arange(1, n + 1)
    return float((2 * (idx * a).sum() / (n * a.sum())) - (n + 1) / n)

def n_cabinets(nodes: list) -> int:
    return len({node_to_cabinet.get(nd, -1) for nd in nodes} - {-1})

def tier_select(available: list, k: int, P_j: float, rng_local) -> list:
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
    elif P_j < P95_PWR:
        pool_end = max(cap_k, int(n_avail * 0.50))
        return [available[order[i]] for i in range(cap_k)]
    else:
        pool_end = max(cap_k, int(n_avail * 0.25))
        return [available[order[i]] for i in range(cap_k)]

def look_ahead_safe(
    selected_nodes: list,
    t_s: np.datetime64,
    e_s: np.datetime64,
    cf_busy: dict,
) -> bool:
    """
    Reject synthetic job admission if it would leave any overlapping future
    historical job with fewer than k_h available cohort nodes.

    Conservative accounting adds future_base_k: sum of k for historical jobs
    starting in (t_s, t_h) with end times past t_h.  These are not yet in
    cf_busy but will consume nodes before h starts.
    """
    overlap_mask = (hist_starts_dt64 > t_s) & (hist_starts_dt64 < e_s)
    if not overlap_mask.any():
        return True

    s_nodes = frozenset(selected_nodes)

    for idx in np.where(overlap_mask)[0]:
        t_h   = hist_starts_dt64[idx]
        k_h   = int(hist_k_arr[idx])
        jid_h = int(hist_jids_arr[idx])

        bg_at_h  = bg_busy_per_job[jid_h]
        cf_at_h  = frozenset(n for n, te in cf_busy.items() if te > t_h)
        blocked  = bg_at_h | cf_at_h | s_nodes
        n_blocked = len(blocked)

        future_base_mask = (
            (hist_starts_dt64 > t_s) &
            (hist_starts_dt64 < t_h) &
            (hist_ends_dt64   > t_h)
        )
        future_base_k = int(hist_k_arr[future_base_mask].sum())
        future_base_k = min(future_base_k, max(0, n_cohort - n_blocked))

        n_free = n_cohort - n_blocked - future_base_k
        if n_free < k_h:
            return False

    return True

# ---------------------------------------------------------------------------
# Synthetic pool generator
# ---------------------------------------------------------------------------
def sample_synthetic_pool(n_extra: int, seed: int) -> pd.DataFrame:
    rng_s = np.random.default_rng(seed)

    base_months = jobs_sorted["start_time"].dt.month.values
    base_hours  = jobs_sorted["start_time"].dt.hour.values
    strat_keys  = list(zip(base_months.tolist(), base_hours.tolist()))

    strat_to_idxs: dict = {}
    for i, sk in enumerate(strat_keys):
        strat_to_idxs.setdefault(sk, []).append(i)

    unique_strata = sorted(strat_to_idxs.keys())
    counts        = np.array([len(strat_to_idxs[s]) for s in unique_strata])
    probs         = counts / counts.sum()

    n_per = np.round(probs * n_extra).astype(int)
    diff  = n_extra - n_per.sum()
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
        return pd.DataFrame(columns=jobs_sorted.columns)

    syn = pd.concat(chunks, ignore_index=True)

    jitter_s             = rng_s.uniform(-1800.0, 1800.0, size=len(syn))
    syn["start_time"]    = syn["start_time"] + pd.to_timedelta(jitter_s, unit="s")
    syn["end_time"]      = syn["start_time"] + pd.to_timedelta(syn["run_time"].values, unit="s")
    syn["is_synthetic"]  = True
    syn["parent_job_idx"]= syn["job_idx"].values.copy()
    syn["job_idx"]       = -(np.arange(len(syn), dtype=np.int64) + 1)

    syn = syn.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)
    return syn

# ---------------------------------------------------------------------------
# Admission-mix helper
# ---------------------------------------------------------------------------
def compute_admission_mix(syn_records: list[dict]) -> dict:
    if not syn_records:
        return {}

    df = pd.DataFrame(syn_records)
    df["nh"] = df["k"] * df["rt_h"]

    result = {}
    for dim, col in [("k_quartile", "k"), ("rt_quartile", "rt_h")]:
        try:
            df[dim] = pd.qcut(df[col], q=4, labels=["Q1", "Q2", "Q3", "Q4"],
                              duplicates="drop")
        except ValueError:
            continue
        grp = df.groupby(dim, observed=True)
        result[dim] = {
            str(q): {
                "n_target"    : int(g["admitted"].count()),
                "n_admitted"  : int(g["admitted"].sum()),
                "admit_rate"  : float(g["admitted"].mean()),
                "col_range"   : [float(g[col].min()), float(g[col].max())],
                "avg_nh"      : float(g["nh"].mean()),
                "nh_admitted" : float(g.loc[g["admitted"], "nh"].sum()
                                      if g["admitted"].any() else 0.0),
                "nh_offered"  : float(g["nh"].sum()),
            }
            for q, g in grp
        }

    result["nh_admit_fraction"] = (
        float(df.loc[df["admitted"], "nh"].sum() / df["nh"].sum())
        if df["nh"].sum() > 0 else np.nan
    )
    result["nh_offered_total"]  = float(df["nh"].sum())
    result["nh_admitted_total"] = float(df.loc[df["admitted"], "nh"].sum())
    return result


# ---------------------------------------------------------------------------
# Capacity replay
# ---------------------------------------------------------------------------
def capacity_replay(
    syn_subset: pd.DataFrame,
    policy: str,
    delta_cap: float,
    lambda_val: float,
    policy_rng_seed: int,
) -> dict:
    """
    Chronological stateful replay.

    Thermal-exposure budgets tracked for all admitted jobs (base + synthetic):

    Job-level (prior approximation, kept for comparison):
      B_job: N_j * t_j * 1[T_hat_j > T_95]  where T_hat_j uses mean selected F
      S_job: analogous severity-weighted

    Node-level (primary, this version):
      T_hat_ij = T_median_j + beta_F * F_i       (per-node counterfactual)
      B_node: sum_i t_j * 1[T_hat_ij > T_95]
      S_node: sum_i t_j * max(0, T_hat_ij - T_95)
    """
    if RELATIVE_CAP:
        cap_per_node = (1.0 + delta_cap) * lambda_val * hist_fleet_avg
    else:
        cap_per_node = (1.0 + delta_cap) * hist_fleet_avg

    n_syn = len(syn_subset)
    if n_syn > 0:
        base_copy                   = jobs_sorted.copy()
        base_copy["is_synthetic"]   = False
        base_copy["parent_job_idx"] = base_copy["job_idx"].values
        combined = pd.concat([base_copy, syn_subset], ignore_index=True)
    else:
        combined                    = jobs_sorted.copy()
        combined["is_synthetic"]    = False
        combined["parent_job_idx"]  = combined["job_idx"].values

    combined = combined.sort_values("start_time").reset_index(drop=True)

    cf_busy: dict[str, np.datetime64] = {}
    cf_util: dict[str, float]         = {n: 0.0 for n in cohort_set}
    _rng = np.random.default_rng(policy_rng_seed)

    T_hats              = []
    syn_node_hours      = 0.0
    n_syn_admit         = 0
    n_drop_cap          = 0
    n_drop_physical     = 0
    n_drop_la           = 0
    n_base_under_served = 0

    # Job-level budget (prior metric, kept for comparison)
    B_job = 0.0
    S_job = 0.0
    # Node-level budget (primary metric)
    B_node = 0.0
    S_node = 0.0

    syn_records: list[dict] = []
    base_cab_counts: list[int] = []
    syn_cab_counts:  list[int] = []

    for _, jrow in combined.iterrows():
        is_syn = bool(jrow["is_synthetic"])
        t_j    = to_dt64(jrow["start_time"])
        t_e    = to_dt64(jrow["end_time"])
        rt_h   = float(jrow["run_time"]) / 3600.0
        k      = int(jrow["n_cohort"])
        ppn    = jrow.get("power_per_node", np.nan)
        P_j    = float(ppn) if not pd.isnull(ppn) else np.nan

        bg_busy = (bg_busy_at(t_j) if is_syn
                   else bg_busy_per_job.get(int(jrow["parent_job_idx"]), frozenset()))

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
                    n_drop_physical += 1
                    cause = "physical"
                else:
                    n_drop_cap += 1
                    cause = "cap"
                syn_records.append({"k": k, "rt_h": rt_h, "admitted": False,
                                    "drop_cause": cause, "nh": k * rt_h})
                continue
            available = avail_capped
        else:
            if len(avail_capped) >= k:
                available = avail_capped
            else:
                avail_uncapped = [n for n in cohort_set
                                  if n not in bg_busy and n not in cf_busy_now]
                available = avail_uncapped

        n_avail = len(available)

        if n_avail == 0:
            selected = []
        elif policy == "fingerprint":
            avail_F  = np.array([F_dict[n] for n in available])
            order    = np.argsort(avail_F)
            selected = [available[i] for i in order[:min(k, n_avail)]]
        elif policy == "tier":
            selected = tier_select(available, k, P_j, _rng)
        else:
            idx      = _rng.choice(n_avail, size=min(k, n_avail), replace=False)
            selected = [available[i] for i in idx]

        if is_syn:
            if not look_ahead_safe(selected, t_j, t_e, cf_busy):
                n_drop_la += 1
                syn_records.append({"k": k, "rt_h": rt_h, "admitted": False,
                                    "drop_cause": "la", "nh": k * rt_h})
                continue

        if not is_syn and len(selected) < k:
            n_base_under_served += 1

        for n in selected:
            cf_busy[n] = t_e
            cf_util[n] += rt_h

        if selected:
            F_arr  = np.array([F_dict[n] for n in selected])
            F_mean = float(F_arr.mean())

            # Job-level T_hat (mean-F prediction, kept for rate diagnostic and job-level budget)
            T_hat_job = float(jrow["T_p95_hist"]) + BETA_F * (F_mean - float(jrow["F_hist_mean"]))
            T_hats.append(T_hat_job)

            # Job-level B/S accumulation
            nh_j      = len(selected) * rt_h
            excess_job = T_hat_job - T_P95_THRESHOLD
            if excess_job > 0:
                B_job += nh_j
                S_job += nh_j * excess_job

            # Node-level B/S: T_hat_ij = T_median_j + beta_F * F_i
            T_med         = float(jrow["T_median_hist"])
            T_hats_node_j = T_med + BETA_F * F_arr
            excesses_n    = T_hats_node_j - T_P95_THRESHOLD
            B_node += rt_h * float((excesses_n > 0).sum())
            S_node += rt_h * float(excesses_n.clip(min=0).sum())

            cab = n_cabinets(selected)
            if is_syn:
                n_syn_admit    += 1
                syn_node_hours += nh_j
                syn_cab_counts.append(cab)
                syn_records.append({"k": k, "rt_h": rt_h, "admitted": True,
                                    "drop_cause": None, "nh": nh_j})
            else:
                base_cab_counts.append(cab)

    if n_base_under_served > 0:
        raise AssertionError(
            f"INVARIANT VIOLATION: {n_base_under_served} base job(s) received fewer "
            f"than their requested k nodes. "
            f"(lambda={lambda_val}, policy={policy}, delta={delta_cap})"
        )

    T_arr      = np.array(T_hats)
    p95_exceed = float((T_arr > T_P95_THRESHOLD).mean()) if len(T_arr) > 0 else np.nan

    util_v         = np.array([cf_util[n] for n in cohort_list])
    g              = gini(util_v)
    n10            = n_cohort // 10
    c10sh          = (util_v[F_cohort_sort_idx[:n10]].sum() / util_v.sum()
                      if util_v.sum() > 0 else np.nan)
    u_realized_avg = util_v.sum() / n_cohort
    max_node_util  = float(util_v.max())
    cap_ratio      = max_node_util / u_realized_avg if u_realized_avg > 0 else np.nan

    unlock_pct = syn_node_hours / hist_total_nh * 100.0

    return {
        "lambda_val"          : lambda_val,
        "cap_per_node"        : cap_per_node,
        "n_syn_target"        : n_syn,
        "n_syn_admit"         : n_syn_admit,
        "n_drop_cap"          : n_drop_cap,
        "n_drop_physical"     : n_drop_physical,
        "n_drop_la"           : n_drop_la,
        "n_base_under_served" : 0,
        "syn_admit_rate"      : n_syn_admit / max(1, n_syn),
        "syn_node_hours"      : syn_node_hours,
        "capacity_unlock_pct" : unlock_pct,
        # Job-level budget (prior approximation)
        "B_job"               : B_job,
        "S_job"               : S_job,
        "B_job_ratio"         : B_job  / B_hist_job  if B_hist_job  > 0 else np.nan,
        "S_job_ratio"         : S_job  / S_hist_job  if S_hist_job  > 0 else np.nan,
        # Node-level budget (primary)
        "B_node"              : B_node,
        "S_node"              : S_node,
        "B_node_ratio"        : B_node / B_hist_node if B_hist_node > 0 else np.nan,
        "S_node_ratio"        : S_node / S_hist_node if S_hist_node > 0 else np.nan,
        # Rate diagnostic
        "p95_exceedance"      : p95_exceed,
        "p95_reduction"       : float(1 - p95_exceed / HIST_P95_EXCEEDANCE),
        # Utilization
        "gini"                : g,
        "coolest10_share"     : c10sh,
        "max_node_hours"      : max_node_util,
        "u_realized_avg"      : u_realized_avg,
        "cap_ratio"           : cap_ratio,
        # Topology
        "base_cab_mean"       : float(np.mean(base_cab_counts)) if base_cab_counts else np.nan,
        "base_cab_p95"        : float(np.percentile(base_cab_counts, 95)) if base_cab_counts else np.nan,
        "syn_cab_mean"        : float(np.mean(syn_cab_counts)) if syn_cab_counts else np.nan,
        "syn_cab_p95"         : float(np.percentile(syn_cab_counts, 95)) if syn_cab_counts else np.nan,
        "admission_mix"       : compute_admission_mix(syn_records),
    }

# ---------------------------------------------------------------------------
# Capacity-unlock interpolation (generalized)
# ---------------------------------------------------------------------------
def find_capacity_unlock(rows: list[dict], key: str, budget: float) -> float | None:
    """
    Linearly interpolate capacity_unlock_pct where rows[i][key] crosses budget.
    Returns None if the curve never exceeds budget (lower bound).
    Returns 0.0 if already at/above budget at lambda=1.0.
    """
    for i in range(len(rows) - 1):
        b0, b1 = rows[i][key], rows[i + 1][key]
        a0, a1 = rows[i]["capacity_unlock_pct"], rows[i + 1]["capacity_unlock_pct"]
        if i == 0 and b0 >= budget:
            return 0.0
        if b0 <= budget <= b1:
            frac = (budget - b0) / max(b1 - b0, 1e-12)
            return float(a0 + frac * (a1 - a0))
    return None  # never crossed; lower bound

# ---------------------------------------------------------------------------
# Main experiment
# ---------------------------------------------------------------------------
n_max_extra = round((max(LAMBDA_SWEEP) - 1.0) * n_base)
print(f"\nMax synthetic jobs per scenario: {n_max_extra}")
print(f"Runs: {N_SCENARIOS} scenario(s) x {len(POLICY_DEFS)} policies x {len(LAMBDA_SWEEP)} lambdas\n")

scenario_results: list[dict] = []

for scen_idx in range(N_SCENARIOS):
    print(f"=== Scenario {scen_idx + 1}/{N_SCENARIOS} ===")
    t_scen = time.time()

    pool_seed = WORKLOAD_SEED + scen_idx * 999983
    print(f"  Generating pool (n={n_max_extra}, seed={pool_seed})...", flush=True)
    pool = sample_synthetic_pool(n_max_extra, seed=pool_seed)

    policy_results: dict[str, list[dict]] = {}

    for policy_key, delta_cap, label, color, marker, p_seed_off in POLICY_DEFS:
        print(f"\n  Policy: {label}")
        pol_seed = SEED + p_seed_off * 9973 + scen_idx * 97
        lambda_rows: list[dict] = []

        for lam in LAMBDA_SWEEP:
            n_extra = round((lam - 1.0) * n_base)

            if n_extra > 0 and len(pool) >= n_extra:
                syn_subset = pool.iloc[:n_extra].copy().sort_values("start_time").reset_index(drop=True)
                syn_subset["job_idx"] = -(np.arange(n_extra, dtype=np.int64) + 1)
            else:
                syn_subset = pd.DataFrame(columns=pool.columns if len(pool) > 0 else jobs_sorted.columns)

            t0 = time.time()
            m  = capacity_replay(syn_subset, policy_key, delta_cap, lam, pol_seed)
            lambda_rows.append(m)

            n_tgt    = m["n_syn_target"]
            drop_str = (
                f"drop=cap:{m['n_drop_cap']}+phys:{m['n_drop_physical']}+la:{m['n_drop_la']}"
                if n_tgt > 0 else ""
            )
            Bj_flag = "OK" if m["B_job"]  <= B_hist_job  else "OVR"
            Bn_flag = "OK" if m["B_node"] <= B_hist_node else "OVR"
            print(
                f"    lam={lam:.2f}  unlock={m['capacity_unlock_pct']:5.2f}%"
                f"  Bj={m['B_job_ratio']:.3f}({Bj_flag})"
                f"  Bn={m['B_node_ratio']:.3f}({Bn_flag})"
                f"  Sj={m['S_job_ratio']:.3f}"
                f"  Sn={m['S_node_ratio']:.3f}"
                f"  syn={m['n_syn_admit']}/{n_tgt} {drop_str}"
                f"  ({time.time()-t0:.1f}s)"
            )

        # Detailed report at last lambda within node-level budget
        within = [r for r in lambda_rows if r["B_node"] <= B_hist_node]
        report_row = within[-1] if within else lambda_rows[0]

        print(f"\n  --- Detailed report at lam={report_row['lambda_val']:.2f} ---")
        print(f"    INVARIANT: base_under = {report_row['n_base_under_served']}  PASS")
        print(f"    Unlock:    {report_row['capacity_unlock_pct']:.2f}%  "
              f"(syn nh: {report_row['syn_node_hours']:.0f} / hist: {hist_total_nh:.0f})")
        print(f"    B_job:     {report_row['B_job']:.1f} / {B_hist_job:.1f}  ratio={report_row['B_job_ratio']:.4f}")
        print(f"    S_job:     {report_row['S_job']:.2f} / {S_hist_job:.2f}  ratio={report_row['S_job_ratio']:.4f}")
        print(f"    B_node:    {report_row['B_node']:.1f} / {B_hist_node:.1f}  ratio={report_row['B_node_ratio']:.4f}"
              f"  {'WITHIN' if report_row['B_node'] <= B_hist_node else 'OVER ***'}")
        print(f"    S_node:    {report_row['S_node']:.2f} / {S_hist_node:.2f}  ratio={report_row['S_node_ratio']:.4f}"
              f"  {'WITHIN' if report_row['S_node'] <= S_hist_node else 'OVER ***'}")
        print(f"    p95_rate:  {report_row['p95_exceedance']:.4f}  (hist={HIST_P95_EXCEEDANCE:.4f})")
        print(f"    Util:      gini={report_row['gini']:.3f}  "
              f"coolest-10%={report_row['coolest10_share']:.3f}  "
              f"max={report_row['max_node_hours']:.1f}h  avg={report_row['u_realized_avg']:.1f}h")
        mix = report_row.get("admission_mix", {})
        if mix:
            kq = mix.get("k_quartile", {})
            parts = []
            for q in ["Q1", "Q2", "Q3", "Q4"]:
                if q in kq:
                    d = kq[q]
                    parts.append(f"{q}[{d['col_range'][0]:.0f}-{d['col_range'][1]:.0f}]:"
                                 f"{d['n_admitted']}/{d['n_target']}")
            if parts:
                print(f"    AdmixK:    {' '.join(parts)}")

        policy_results[label] = lambda_rows

    scenario_results.append(policy_results)
    print(f"\n  Scenario {scen_idx+1} done  ({time.time()-t_scen:.1f}s)")

# ---------------------------------------------------------------------------
# Aggregate capacity-unlock summary
# ---------------------------------------------------------------------------
print("\n" + "="*70)
print("Capacity-unlock comparison: job-level vs node-level budget")
print("="*70)
print(f"\n  Budgets:")
print(f"    B_hist_job  = {B_hist_job:.1f} h    S_hist_job  = {S_hist_job:.1f} degC-h")
print(f"    B_hist_node = {B_hist_node:.1f} h    S_hist_node = {S_hist_node:.1f} degC-h")
print(f"    Node/Job ratio: B={B_hist_node/B_hist_job:.3f}  S={S_hist_node/S_hist_job:.3f}\n")

header = f"  {'Policy':<20}  {'B(lam=1)':<9}  {'Bj-cross':>9}  {'Bn-cross':>9}  {'Sj-cross':>9}  {'Sn-cross':>9}"
print(header)
print("  " + "-"*(len(header)-2))

unlock_summary: dict[str, dict] = {}
lb = (max(LAMBDA_SWEEP) - 1) * 100

for _, _, label, _, _, _ in POLICY_DEFS:
    rows_list = [
        find_capacity_unlock(scen[label], key, budget)
        for scen in scenario_results
        for key, budget in [
            ("B_job",  B_hist_job),
            ("B_node", B_hist_node),
            ("S_job",  S_hist_job),
            ("S_node", S_hist_node),
        ]
    ]
    # Recompute per key properly
    def summarise_key(key, budget):
        unlocks = [
            u for scen in scenario_results
            if (u := find_capacity_unlock(scen[label], key, budget)) is not None
        ]
        if unlocks:
            med = float(np.median(unlocks))
            lo  = float(np.percentile(unlocks, 2.5))
            hi  = float(np.percentile(unlocks, 97.5))
            return {"median": med, "p025": lo, "p975": hi, "values": unlocks}
        return {"median": None, "p025": None, "p975": None, "values": []}

    su_Bj = summarise_key("B_job",  B_hist_job)
    su_Bn = summarise_key("B_node", B_hist_node)
    su_Sj = summarise_key("S_job",  S_hist_job)
    su_Sn = summarise_key("S_node", S_hist_node)

    def fmt(su):
        if su["median"] is None:
            return f">={lb:.0f}%"
        ci = f"[{su['p025']:.1f},{su['p975']:.1f}]" if N_SCENARIOS > 1 else ""
        return f"+{su['median']:.1f}%{ci}"

    r0 = scenario_results[0][label][0]
    Bj0 = r0["B_job_ratio"]

    print(f"  {label:<20}  {Bj0:.3f}x    {fmt(su_Bj):>9}  {fmt(su_Bn):>9}  {fmt(su_Sj):>9}  {fmt(su_Sn):>9}")

    unlock_summary[label] = {
        "B_job_crossing":  su_Bj,
        "B_node_crossing": su_Bn,
        "S_job_crossing":  su_Sj,
        "S_node_crossing": su_Sn,
        "B_job_at_lam1":   Bj0,
        "B_node_at_lam1":  r0["B_node_ratio"],
        "S_job_at_lam1":   r0["S_job_ratio"],
        "S_node_at_lam1":  r0["S_node_ratio"],
    }

print()

# Also print per-policy lam=1 ratios for all four metrics
print("  Budget ratios at lam=1.0 (base jobs only, no synthetic load):")
print(f"  {'Policy':<20}  {'Bj/B_hist':>9}  {'Bn/B_hist':>9}  {'Sj/S_hist':>9}  {'Sn/S_hist':>9}")
print("  " + "-"*65)
for _, _, label, _, _, _ in POLICY_DEFS:
    r0 = scenario_results[0][label][0]
    print(f"  {label:<20}  {r0['B_job_ratio']:9.3f}  {r0['B_node_ratio']:9.3f}"
          f"  {r0['S_job_ratio']:9.3f}  {r0['S_node_ratio']:9.3f}")

# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
print("\nGenerating figures...")
plot_scen = scenario_results[0]

fig, axes = plt.subplots(1, 2, figsize=(14, 6))
fig.suptitle(
    f"Phase 3B.2b: Capacity-unlock — node-level budget (N={N_SCENARIOS} scenario)",
    fontsize=12, fontweight="bold",
)

# Panel A: additional node-hours (%) vs node-level B_node; reference line at B_hist_node
ax = axes[0]
ax.axhline(B_hist_node, color="#444444", lw=1.5, ls="--",
           label=f"B_hist_node = {B_hist_node:.0f} h (exact per-node)")
ax.axhline(B_hist_job,  color="#aaaaaa", lw=1.0, ls=":",
           label=f"B_hist_job  = {B_hist_job:.0f} h (job-avg approx)")

for _, _, label, color, marker, _ in POLICY_DEFS:
    rows = plot_scen[label]
    xs   = [r["capacity_unlock_pct"] for r in rows]
    ys_n = [r["B_node"]              for r in rows]
    ys_j = [r["B_job"]               for r in rows]
    ax.plot(xs, ys_n, "-",  color=color, lw=2,   label=f"{label} (node)")
    ax.plot(xs, ys_j, "--", color=color, lw=1.2, alpha=0.5)  # job-level dashed, same color
    ax.scatter(xs, ys_n, color=color, marker=marker, s=50, zorder=4)

    u_n = unlock_summary[label]["B_node_crossing"]["median"]
    if u_n is not None and u_n > 0:
        ax.axvline(u_n, color=color, lw=0.8, ls=":", alpha=0.6)
        ax.annotate(f"+{u_n:.1f}%", xy=(u_n, B_hist_node),
                    xytext=(u_n + 0.3, B_hist_node * 1.01),
                    fontsize=7, color=color)

ax.set_xlabel("Additional admitted cohort node-hours (% of historical total)")
ax.set_ylabel("Thermal exposure B  (node-hours above p95 threshold)")
ax.set_title("A. Node-level capacity unlock\nsolid = node-level B; dashed = job-level B (same color)")
ax.legend(fontsize=7, loc="upper left")
ax.set_ylim(bottom=0)

# Panel B: S_node vs unlock_pct; reference line at S_hist_node
ax = axes[1]
ax.axhline(S_hist_node, color="#444444", lw=1.5, ls="--",
           label=f"S_hist_node = {S_hist_node:.0f} degC-h")
ax.axhline(S_hist_job,  color="#aaaaaa", lw=1.0, ls=":",
           label=f"S_hist_job  = {S_hist_job:.0f} degC-h")

for _, _, label, color, marker, _ in POLICY_DEFS:
    rows = plot_scen[label]
    xs   = [r["capacity_unlock_pct"] for r in rows]
    ys_n = [r["S_node"]              for r in rows]
    ys_j = [r["S_job"]               for r in rows]
    ax.plot(xs, ys_n, "-",  color=color, lw=2,   label=f"{label} (node)")
    ax.plot(xs, ys_j, "--", color=color, lw=1.2, alpha=0.5)
    ax.scatter(xs, ys_n, color=color, marker=marker, s=50, zorder=4)

    u_n = unlock_summary[label]["S_node_crossing"]["median"]
    if u_n is not None and u_n > 0:
        ax.axvline(u_n, color=color, lw=0.8, ls=":", alpha=0.6)
        ax.annotate(f"+{u_n:.1f}%", xy=(u_n, S_hist_node),
                    xytext=(u_n + 0.3, S_hist_node * 1.01),
                    fontsize=7, color=color)

ax.set_xlabel("Additional admitted cohort node-hours (% of historical total)")
ax.set_ylabel("Thermal severity S  (degC-node-hours above threshold)")
ax.set_title("B. Node-level severity metric\nsolid = node-level S; dashed = job-level S")
ax.legend(fontsize=7, loc="upper left")
ax.set_ylim(bottom=0)

plt.tight_layout()
out_fig = ANALYSIS_DIR / "phase3b2b_capacity.png"
plt.savefig(out_fig, dpi=150, bbox_inches="tight")
plt.close()
print(f"Saved {out_fig}")

# ---------------------------------------------------------------------------
# Save JSON
# ---------------------------------------------------------------------------
out_json = {
    "experiment"        : "phase3b2b_capacity_unlock_node_level",
    "relative_cap"      : RELATIVE_CAP,
    "n_scenarios"       : N_SCENARIOS,
    "T_p95_threshold"   : T_P95_THRESHOLD,
    "hist_p95_exceedance_rate": HIST_P95_EXCEEDANCE,
    "hist_total_nh"     : hist_total_nh,
    "hist_fleet_avg_nh" : hist_fleet_avg,
    "B_hist_job"        : B_hist_job,
    "S_hist_job"        : S_hist_job,
    "B_hist_node"       : B_hist_node,
    "S_hist_node"       : S_hist_node,
    "n_base_jobs"       : n_base,
    "lambda_sweep"      : LAMBDA_SWEEP,
    "capacity_unlock_summary": unlock_summary,
    "scenario_results"  : [
        {label: rows for label, rows in scen.items()}
        for scen in scenario_results
    ],
}
with open(ANALYSIS_DIR / "phase3b2b_results.json", "w") as f:
    json.dump(out_json, f, indent=2, default=float)
print("Saved phase3b2b_results.json")
print("\n=== Done ===")
