# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.2d: Capacity-unlock experiment -- residual-calibrated thermal model.

Temperature model (node-level, empirical residuals):
  T_hat_ij = alpha_j + beta_F * F_i + e_j[pi[i]]
  alpha_j  = T_p95_hist_j - beta_F * F_hist_mean_j   (OLS intercept)
  e_j      = empirical within-job residual vector from Phase 3A test set
  pi       = random permutation of e_j, shared across all policies (CRN)
  Synthetic jobs inherit parent base job residual vector; new permutation per job.

Thermal budget (node-level exact):
  B_hist = sum_j sum_{i in j} t_j * 1[T_obs_ij > T_95]
  B_policy = sum_j sum_{i in selected(j)} t_j * 1[T_hat_ij > T_95]

Capacity unlock:
  C_policy  = admitted synth NH / hist_total_NH (%) at B_policy = B_hist crossing
  C_random  = same for Random-feasible baseline
  delta_C   = C_policy - C_random  (incremental thermal intelligence value)

Design:
  - Single scenario (N=1): lambda sweep [1.00 ... 1.80], 4 policies
  - CRN: one workload pool, one residual permutation set, shared across all policies
  - Stateful chronological replay with look-ahead base-job protection
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
SCENARIO_SEED = 42
WORKLOAD_SEED = 77777
N_SCENARIOS   = 1
N_BINS        = 5   # F-rank bins for conditioned residual permutation

# 0% to 80% extra offered demand
LAMBDA_SWEEP  = [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.40, 1.50, 1.65, 1.80]
LAMBDA_MAX    = max(LAMBDA_SWEEP)

# Policies: (key, delta_cap, label, color, marker)
# delta_cap=1e6 means no per-node utilization cap
POLICY_DEFS = [
    ("random",  1e6,  "Random-feasible", "#888888", "o"),
    ("fp",      0.10, "FP-cap-10",       "#ee7722", "s"),
    ("tier20",  0.20, "Tier-cap-20",     "#22aa55", "D"),
    ("tiernc",  1e6,  "Tier-no-cap",     "#aa44cc", "^"),
]
POLICY_KEYS = [p[0] for p in POLICY_DEFS]

# Frozen constants from earlier phases
T_P95_THRESHOLD = 60.602770562770566
P50_PWR         = 896.4571428571429
P80_PWR         = 1496.4923809523812
P95_PWR         = 1955.5884126984126

print("=== Phase 3B.2d: Capacity-unlock (conditioned residuals, fixed LA, 0-80% sweep) ===")
print(f"  N_SCENARIOS={N_SCENARIOS}  lambda=[{LAMBDA_SWEEP[0]:.2f}..{LAMBDA_SWEEP[-1]:.2f}]"
      f"  ({len(LAMBDA_SWEEP)} points)\n")

# ============================================================
# Load
# ============================================================
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

print("Loading job schedule...")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"  {len(all_jobs):,} total jobs")

# ============================================================
# Topology
# ============================================================
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
has_cohort = np.array([jid in cohort_per_job for jid in all_jobs["job_idx_int"].values])
sched_jids = all_jobs["job_idx_int"].values[has_cohort]
sched_st   = all_jobs["start_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_et   = all_jobs["end_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_cn   = np.array([cohort_per_job[jid] for jid in sched_jids], dtype=object)
print(f"  {len(sched_jids):,} schedule entries  ({time.time()-t0:.1f}s)")

# ============================================================
# Job-level test summary
# ============================================================
print("\nBuilding job-level test summary...")
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
test_id_set = set(job_agg["job_idx"].astype(int))
jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)
n_base      = len(jobs_sorted)
print(f"  {n_base} base test jobs")

# Historical node-hours (utilization cap reference)
hist_node_hours = {n: 0.0 for n in cohort_list}
for _, jrow in jobs_sorted.iterrows():
    rt_h = float(jrow["run_time"]) / 3600.0
    for n in jrow["hist_nodes"]:
        if n in hist_node_hours:
            hist_node_hours[n] += rt_h
hist_util_arr  = np.array([hist_node_hours[n] for n in cohort_list])
hist_total_nh  = float(hist_util_arr.sum())
hist_fleet_avg = hist_total_nh / n_cohort
print(f"  Hist fleet avg: {hist_fleet_avg:.2f} h/node  total: {hist_total_nh:.0f} h")

# ============================================================
# Historical thermal budget (exact observed, node-level)
# ============================================================
rt_lookup   = jobs_sorted.set_index("job_idx")["run_time"].to_dict()
test_rt_h   = test_df["job_idx"].map(lambda j: rt_lookup.get(int(j), 0.0)) / 3600.0
node_excess = test_df["T_p95"] - T_P95_THRESHOLD
B_hist_node = float((test_rt_h * (node_excess > 0)).sum())
S_hist_node = float((test_rt_h * node_excess.clip(lower=0)).sum())
print(f"\n  B_hist_node = {B_hist_node:.1f} h    S_hist_node = {S_hist_node:.1f} degC-h")

# ============================================================
# Residual model
# ============================================================
print(f"\nComputing empirical residuals (conditioned, N_BINS={N_BINS})...")
jobs_sorted["alpha_j"] = jobs_sorted["T_p95_hist"] - BETA_F * jobs_sorted["F_hist_mean"]
alpha_map = jobs_sorted.set_index("job_idx")["alpha_j"].to_dict()

test_res = test_df.copy()
test_res["alpha_j"]  = test_res["job_idx"].map(lambda j: alpha_map.get(int(j), np.nan))
test_res["F_i"]      = test_res["node"].map(F_dict)
test_res["residual"] = (test_res["T_p95"]
                        - test_res["alpha_j"]
                        - BETA_F * test_res["F_i"])

job_residuals: dict[int, tuple] = {}   # (res_sorted_by_F, bin_labels)
for jid, grp in test_res.groupby("job_idx"):
    jid = int(jid)
    grp_s = grp.sort_values("F_i")
    res_arr = grp_s["residual"].values.copy()
    k = len(grp_s)
    if k >= N_BINS:
        try:
            bins = pd.qcut(grp_s["F_i"], q=N_BINS,
                           labels=False, duplicates="drop").values.astype(int)
        except Exception:
            bins = np.zeros(k, dtype=int)
    else:
        bins = np.zeros(k, dtype=int)
    job_residuals[jid] = (res_arr, bins)

res_flat = test_res["residual"].dropna().values
print(f"  mean={res_flat.mean():.4f}  SD={res_flat.std():.4f}"
      f"  p5={np.percentile(res_flat, 5):.2f}  p95={np.percentile(res_flat, 95):.2f} degC")

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
# Look-ahead arrays (base-job protection)
# ============================================================
def _to_dt64_ms(ts) -> np.datetime64:
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

hist_starts_dt64 = np.array([_to_dt64_ms(r["start_time"]) for _, r in jobs_sorted.iterrows()])
hist_ends_dt64   = np.array([_to_dt64_ms(r["end_time"])   for _, r in jobs_sorted.iterrows()])
hist_k_arr       = jobs_sorted["n_cohort"].values.astype(int)
hist_jids_arr    = jobs_sorted["job_idx"].values.astype(int)

# ============================================================
# Utility functions
# ============================================================
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
        return [available[order[i]] for i in range(cap_k)]
    else:
        return [available[order[i]] for i in range(cap_k)]

def look_ahead_safe(selected_nodes: list, t_s, e_s, cf_busy: dict) -> bool:
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
        # Include base jobs starting at EXACTLY t_h (co-starters) since they are
        # processed before this job in the sorted schedule and consume nodes first.
        # Exclude idx itself (it is the target being protected, not a consumer).
        future_base_mask = (
            (hist_starts_dt64 > t_s) &
            (hist_starts_dt64 <= t_h) &
            (hist_ends_dt64   > t_h)
        )
        future_base_mask = future_base_mask.copy()
        future_base_mask[idx] = False
        future_base_k = min(int(hist_k_arr[future_base_mask].sum()),
                            max(0, n_cohort - n_blocked))
        if n_cohort - n_blocked - future_base_k < k_h:
            return False
    return True

# ============================================================
# Synthetic pool generator
# ============================================================
def sample_synthetic_pool(n_extra: int, seed: int) -> pd.DataFrame:
    rng_s = np.random.default_rng(seed)
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
    syn["is_synthetic"]    = True
    syn["parent_job_idx"]  = syn["job_idx"].values.copy()
    syn["job_idx"]         = -(np.arange(len(syn), dtype=np.int64) + 1)
    # alpha_j from parent
    syn["alpha_j"]         = syn["parent_job_idx"].map(alpha_map)
    syn = syn.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)
    return syn

# ============================================================
# CRN residual permutation generator
# ============================================================
def generate_job_perms(syn_pool: pd.DataFrame,
                       scen_rng: np.random.Generator) -> dict[int, np.ndarray]:
    """Fingerprint-conditioned permutations: permute residuals within F-rank bins."""
    job_perms: dict[int, np.ndarray] = {}
    for jid in jobs_sorted["job_idx"].astype(int):
        res_s, bins = job_residuals[jid]
        k = len(res_s)
        perm = np.arange(k)
        for b in np.unique(bins):
            idx_b = np.where(bins == b)[0]
            perm[idx_b] = scen_rng.permutation(idx_b)
        job_perms[jid] = perm
    if len(syn_pool) > 0:
        for syn_jid, parent_jid in zip(syn_pool["job_idx"].astype(int),
                                        syn_pool["parent_job_idx"].astype(int)):
            res_s, bins = job_residuals[parent_jid]
            k = len(res_s)
            perm = np.arange(k)
            for b in np.unique(bins):
                idx_b = np.where(bins == b)[0]
                perm[idx_b] = scen_rng.permutation(idx_b)
            job_perms[syn_jid] = perm
    return job_perms

# ============================================================
# Admission-mix diagnostics (by job size, runtime, power)
# ============================================================
def compute_admission_mix(syn_records: list[dict]) -> dict:
    if not syn_records:
        return {}
    df = pd.DataFrame(syn_records)
    df["nh"] = df["k"] * df["rt_h"]
    result = {}
    for dim, col in [("k_q", "k"), ("rt_q", "rt_h"), ("power_q", "power_per_node")]:
        if col not in df.columns:
            continue
        valid = df[col].notna()
        if not valid.any():
            continue
        try:
            df.loc[valid, dim] = pd.qcut(df.loc[valid, col], q=4,
                                          labels=["Q1", "Q2", "Q3", "Q4"],
                                          duplicates="drop")
        except ValueError:
            continue
        grp = df.groupby(dim, observed=True)
        result[dim] = {
            str(q): {
                "n"          : int(g["admitted"].count()),
                "n_admit"    : int(g["admitted"].sum()),
                "admit_rate" : float(g["admitted"].mean()),
                "nh_admitted": float((g["nh"] * g["admitted"]).sum()),
                "nh_offered" : float(g["nh"].sum()),
            }
            for q, g in grp
        }
    return result

# ============================================================
# Single-policy capacity replay
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

    cf_busy : dict[str, np.datetime64] = {}
    cf_util : dict[str, float]         = {n: 0.0 for n in cohort_set}
    _rng = np.random.default_rng(policy_seed)

    B_node = 0.0
    S_node = 0.0
    syn_node_hours  = 0.0
    n_syn_admit     = 0
    n_drop_cap      = 0
    n_drop_phys     = 0
    n_drop_la       = 0
    n_base_unserved = 0

    syn_records: list[dict] = []
    base_cab_list: list[int] = []
    syn_cab_list:  list[int] = []

    for _, jrow in combined.iterrows():
        is_syn  = bool(jrow["is_synthetic"])
        t_j     = to_dt64(jrow["start_time"])
        t_e     = to_dt64(jrow["end_time"])
        rt_h    = float(jrow["run_time"]) / 3600.0
        k       = int(jrow["n_cohort"])
        jid     = int(jrow["job_idx"])
        ppn     = jrow.get("power_per_node", np.nan)
        P_j     = float(ppn) if not pd.isnull(ppn) else np.nan

        # Resolve parent for residual lookup
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
                    cause = "physical"
                else:
                    n_drop_cap += 1
                    cause = "cap"
                syn_records.append({"k": k, "rt_h": rt_h, "admitted": False,
                                    "drop_cause": cause, "power_per_node": P_j})
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
            selected = tier_select(available, k, P_j, _rng)
        else:  # random
            idx      = _rng.choice(n_avail, size=min(k, n_avail), replace=False)
            selected = [available[i] for i in idx]

        if is_syn and selected:
            if not look_ahead_safe(selected, t_j, t_e, cf_busy):
                n_drop_la += 1
                syn_records.append({"k": k, "rt_h": rt_h, "admitted": False,
                                    "drop_cause": "la", "power_per_node": P_j})
                continue

        if not is_syn and len(selected) < k:
            n_base_unserved += 1

        for n in selected:
            cf_busy[n] = t_e
            cf_util[n] += rt_h

        if selected:
            F_arr  = np.array([F_dict[n] for n in selected])
            nh_j   = len(selected) * rt_h

            # Conditioned residual temperature model: map each selected node to its
            # within-job F rank, then draw from the corresponding permuted bin slot.
            alpha    = float(jrow["alpha_j"])
            res_s, _ = job_residuals[parent_jid]
            perm     = job_perms[jid]
            rank     = np.argsort(np.argsort(F_arr))  # F rank in [0, n_sel-1]
            T_hats_j = alpha + BETA_F * F_arr + res_s[perm[rank]]

            excesses = T_hats_j - T_P95_THRESHOLD
            B_node  += rt_h * float((excesses > 0).sum())
            S_node  += rt_h * float(excesses.clip(min=0).sum())

            cab = n_cabinets(selected)
            if is_syn:
                n_syn_admit    += 1
                syn_node_hours += nh_j
                syn_cab_list.append(cab)
                syn_records.append({"k": k, "rt_h": rt_h, "admitted": True,
                                    "drop_cause": None, "power_per_node": P_j})
            else:
                base_cab_list.append(cab)

    if n_base_unserved > 0:
        raise AssertionError(
            f"Base-job invariant violated: {n_base_unserved} job(s) under-served "
            f"(lam={lambda_val}, policy={policy})"
        )

    util_v        = np.array([cf_util[n] for n in cohort_list])
    g             = gini(util_v)
    n10           = n_cohort // 10
    c10sh         = (util_v[F_cohort_sort_idx[:n10]].sum() / util_v.sum()
                     if util_v.sum() > 0 else np.nan)
    max_util_h    = float(util_v.max())
    unlock_pct    = syn_node_hours / hist_total_nh * 100.0
    mean_base_cab = float(np.mean(base_cab_list)) if base_cab_list else np.nan
    mean_syn_cab  = float(np.mean(syn_cab_list))  if syn_cab_list  else np.nan

    return {
        "lambda_val"         : lambda_val,
        "policy"             : policy,
        "n_syn_target"       : n_syn,
        "n_syn_admit"        : n_syn_admit,
        "n_drop_cap"         : n_drop_cap,
        "n_drop_physical"    : n_drop_phys,
        "n_drop_la"          : n_drop_la,
        "n_base_unserved"    : n_base_unserved,
        "syn_node_hours"     : syn_node_hours,
        "capacity_unlock_pct": unlock_pct,
        "B_node"             : B_node,
        "S_node"             : S_node,
        "B_node_ratio"       : B_node / B_hist_node if B_hist_node > 0 else np.nan,
        "S_node_ratio"       : S_node / S_hist_node if S_hist_node > 0 else np.nan,
        "gini"               : g,
        "coolest10_share"    : c10sh,
        "max_util_h"         : max_util_h,
        "mean_base_cab"      : mean_base_cab,
        "mean_syn_cab"       : mean_syn_cab,
        "admission_mix"      : compute_admission_mix(syn_records),
    }

# ============================================================
# Interpolation (crossing point)
# ============================================================
def find_crossing(rows: list[dict], ratio_key: str, target: float = 1.0) -> float | None:
    valid = [r for r in rows if ratio_key in r]
    xs = [r["capacity_unlock_pct"] for r in valid]
    ys = [r[ratio_key] for r in valid]
    for i in range(len(ys) - 1):
        if ys[i] <= target <= ys[i + 1]:
            frac = (target - ys[i]) / max(ys[i + 1] - ys[i], 1e-12)
            return float(xs[i] + frac * (xs[i + 1] - xs[i]))
        if i == 0 and ys[i] >= target:
            return 0.0
    return None

def c_qos(rows: list[dict]) -> float | None:
    """Capacity_unlock_pct at first invariant violation (C_QoS upper bound)."""
    for r in rows:
        if r.get("invariant_violated"):
            return r.get("capacity_unlock_pct", None)
    return None

# ============================================================
# Main sweep
# ============================================================
print("\n" + "="*72)
print("CAPACITY SWEEP  (single scenario, N=1)")
print("="*72)

all_results: dict[str, list[dict]] = {pk: [] for pk in POLICY_KEYS}

# --- Workload pool (CRN across policies and lambdas) ---
n_extra_max = int(np.ceil((LAMBDA_MAX - 1.0) * n_base))
print(f"\nGenerating synthetic pool: {n_extra_max} jobs "
      f"({(LAMBDA_MAX-1)*100:.0f}% of {n_base} base)...")
syn_pool = sample_synthetic_pool(n_extra_max, WORKLOAD_SEED)
print(f"  Pool: {len(syn_pool)} synthetic jobs")

# --- Residual permutations (CRN across policies) ---
print("Pre-generating residual permutations (CRN)...")
scen_rng  = np.random.default_rng(SCENARIO_SEED)
job_perms = generate_job_perms(syn_pool, scen_rng)
print(f"  {len(job_perms)} permutations generated\n")

# --- Lambda loop ---
for lam in LAMBDA_SWEEP:
    n_syn      = int(round((lam - 1.0) * n_base))
    syn_subset = syn_pool.iloc[:n_syn].copy() if n_syn > 0 else pd.DataFrame(
        columns=syn_pool.columns if len(syn_pool) > 0 else jobs_sorted.columns)

    added_pct  = (lam - 1.0) * 100.0
    print(f"--- lam={lam:.2f} (+{added_pct:.0f}% offered)  N_syn={n_syn} ---")
    hdr = (f"  {'Policy':<20} | {'NH%':>5} | {'B/Bh':>6} | {'S/Sh':>6} |"
           f" {'Gini':>5} | {'c10%':>5} | cab | phy/cap/la")
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

        drops   = f"{res['n_drop_physical']}/{res['n_drop_cap']}/{res['n_drop_la']}"
        cab_s   = f"{res['mean_syn_cab']:.1f}" if res['n_syn_admit'] > 0 else "  -- "
        unserv  = f" !{res['n_base_unserved']}" if res['n_base_unserved'] > 0 else ""
        print(f"  {label:<20} | {res['capacity_unlock_pct']:>5.1f} |"
              f" {res['B_node_ratio']:>6.4f} | {res['S_node_ratio']:>6.4f} |"
              f" {res['gini']:>5.3f} | {res['coolest10_share']:>5.3f} |"
              f" {cab_s} | {drops}{unserv}  ({elapsed:.0f}s)")

# ============================================================
# Crossing analysis
# ============================================================
print("\n" + "="*72)
print("CAPACITY UNLOCK CROSSING ANALYSIS  (B_ratio = 1.0)")
print("="*72)

crossings: dict[str, dict] = {}
print(f"\n  {'Policy':<20} | C_B (NH%) | C_S (NH%) | C_QoS note")
print("  " + "-"*62)
for pk, delta_cap, label, color, marker in POLICY_DEFS:
    rows = all_results[pk]
    c_B  = find_crossing(rows, "B_node_ratio")
    c_S  = find_crossing(rows, "S_node_ratio")
    qos_violated = any(r.get("invariant_violated") for r in rows)
    if qos_violated:
        last_ok = [r for r in rows if not r.get("invariant_violated")]
        last_ok_pct = last_ok[-1].get("capacity_unlock_pct", "?") if last_ok else "?"
        qos_s = f"violated (last OK: {last_ok_pct:.1f}%)" if isinstance(last_ok_pct, float) else f"violated"
    else:
        qos_s = "OK (no violation up to +80%)"
    crossings[pk] = {"C_B": c_B, "C_S": c_S, "label": label,
                     "qos_violated": qos_violated}
    cb_s = f"{c_B:.1f}%" if c_B is not None else ">80%"
    cs_s = f"{c_S:.1f}%" if c_S is not None else ">80%"
    print(f"  {label:<20} | {cb_s:>9} | {cs_s:>9} | {qos_s}")

# Incremental over Random
rand_pk  = "random"
c_B_rand = crossings[rand_pk]["C_B"]
c_S_rand = crossings[rand_pk]["C_S"]

print(f"\n  Incremental capacity vs Random-feasible:")
print(f"  {'Policy':<20} | dC_B (pp) | dC_S (pp)")
print("  " + "-"*47)
for pk, delta_cap, label, color, marker in POLICY_DEFS:
    if pk == rand_pk:
        continue
    c_B = crossings[pk]["C_B"]
    c_S = crossings[pk]["C_S"]
    dB  = (c_B - c_B_rand) if (c_B is not None and c_B_rand is not None) else None
    dS  = (c_S - c_S_rand) if (c_S is not None and c_S_rand is not None) else None
    dB_s = f"+{dB:.1f} pp" if dB is not None else "N/A"
    dS_s = f"+{dS:.1f} pp" if dS is not None else "N/A"
    print(f"  {label:<20} | {dB_s:>9} | {dS_s:>9}")

# ============================================================
# Figures
# ============================================================
print("\nGenerating figures...")
fig, axes = plt.subplots(1, 2, figsize=(13, 5))

for ax_idx, (ratio_key, ylabel, title) in enumerate([
    ("B_node_ratio", "B / B_hist", "Thermal-exposure budget (B)"),
    ("S_node_ratio", "S / S_hist", "Thermal-severity budget (S)"),
]):
    ax = axes[ax_idx]
    for pk, delta_cap, label, color, marker in POLICY_DEFS:
        rows = [r for r in all_results[pk] if ratio_key in r]
        xs = [r["capacity_unlock_pct"] for r in rows]
        ys = [r[ratio_key] for r in rows]
        ls  = "--" if pk == "random" else "-"
        lw  = 1.5 if pk == "random" else 2.0
        ax.plot(xs, ys, color=color, marker=marker, ls=ls, lw=lw, label=label)
    ax.axhline(1.0, color="black", lw=1.5, ls=":", label="Historical budget")
    ax.set_xlabel("Added workload (% of hist. node-hours)")
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.3)

plt.tight_layout()
outfig = ANALYSIS_DIR / "phase3b2d_capacity.png"
fig.savefig(outfig, dpi=150)
plt.close()
print(f"  Saved {outfig}")

# ============================================================
# Gini / utilization figure
# ============================================================
fig2, ax2 = plt.subplots(figsize=(7, 5))
for pk, delta_cap, label, color, marker in POLICY_DEFS:
    rows = [r for r in all_results[pk] if "gini" in r]
    xs = [r["capacity_unlock_pct"] for r in rows]
    ys = [r["gini"] for r in rows]
    ls = "--" if pk == "random" else "-"
    ax2.plot(xs, ys, color=color, marker=marker, ls=ls, lw=2, label=label)
ax2.axhline(0.279, color="black", lw=1.5, ls=":", label="Historical Gini=0.279")
ax2.set_xlabel("Added workload (% of hist. node-hours)")
ax2.set_ylabel("Gini (utilization inequality)")
ax2.set_title("Utilization balance vs. added workload")
ax2.legend(fontsize=9)
ax2.grid(True, alpha=0.3)
plt.tight_layout()
outfig2 = ANALYSIS_DIR / "phase3b2d_gini.png"
fig2.savefig(outfig2, dpi=150)
plt.close()
print(f"  Saved {outfig2}")

# ============================================================
# Save JSON
# ============================================================
out = {
    "B_hist_node"      : B_hist_node,
    "S_hist_node"      : S_hist_node,
    "hist_total_nh"    : hist_total_nh,
    "hist_fleet_avg_h" : hist_fleet_avg,
    "lambda_sweep"     : LAMBDA_SWEEP,
    "n_base"           : n_base,
    "crossings"        : crossings,
    "C_B_random"       : c_B_rand,
    "C_S_random"       : c_S_rand,
    "policy_results"   : {pk: rows for pk, rows in all_results.items()},
}
outpath = ANALYSIS_DIR / "phase3b2d_results.json"
with open(outpath, "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"  Saved {outpath}")

print("\n=== Done ===")
