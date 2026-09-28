# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.2-F: look_ahead_safe failure trace.

Runs tiernc policy at lam=1.15 with full admission instrumentation.
On the first base-job invariant violation, prints:
  - failing base job details
  - all synthetic jobs running at that moment (in cf_busy)
  - for each: what look_ahead_safe returned when it was admitted, and
              what the check would return for THIS base job
  - the per-base-job occupancy picture to show how depletion accumulated
Then exits.
"""

import os
import pandas as pd
import numpy as np
import re, time
from pathlib import Path

ANALYSIS_DIR  = Path(__file__).parent
DATA_DIR      = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

BETA_F        = 0.9569
SCENARIO_SEED = 42
WORKLOAD_SEED = 77777
LAM           = 1.15
POLICY        = "tiernc"
T_P95_THRESHOLD = 60.602770562770566
P50_PWR         = 896.4571428571429
P80_PWR         = 1496.4923809523812
P95_PWR         = 1955.5884126984126

print("=== Phase 3B.2-F: look_ahead_safe failure diagnostic ===")
print(f"  Policy={POLICY}  lam={LAM}\n")

# ============================================================
# Load (identical to phase3b2d_capacity.py)
# ============================================================
print("Loading fingerprints...")
fp_df       = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set  = set(fp_df.index)
F_dict      = fp_df["FA_2024"].to_dict()
cohort_list = sorted(cohort_set)
n_cohort    = len(cohort_list)
F_cohort_arr = np.array([F_dict[n] for n in cohort_list])
print(f"  {n_cohort:,} nodes")

print("Loading test set...")
test_df = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")

print("Loading job schedule...")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"  {len(all_jobs):,} total jobs")

print("Building topology map...")
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

print("Building schedule arrays...")
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

print("Building job summaries...")
job_agg = (
    test_df.groupby("job_idx")
    .agg(F_hist_mean=("F_2024", "mean"), n_cohort=("node", "count"),
         T_p95_hist=("T_p95", "mean"), hist_nodes=("node", list))
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
jobs_sorted["alpha_j"] = jobs_sorted["T_p95_hist"] - BETA_F * jobs_sorted["F_hist_mean"]
alpha_map = jobs_sorted.set_index("job_idx")["alpha_j"].to_dict()
print(f"  {n_base} base jobs")

hist_node_hours = {n: 0.0 for n in cohort_list}
for _, jrow in jobs_sorted.iterrows():
    rt_h = float(jrow["run_time"]) / 3600.0
    for n in jrow["hist_nodes"]:
        if n in hist_node_hours:
            hist_node_hours[n] += rt_h
hist_util_arr = np.array([hist_node_hours[n] for n in cohort_list])
hist_total_nh = float(hist_util_arr.sum())
hist_fleet_avg = hist_total_nh / n_cohort

test_res = test_df.copy()
test_res["alpha_j"]  = test_res["job_idx"].map(lambda j: alpha_map.get(int(j), np.nan))
test_res["F_i"]      = test_res["node"].map(F_dict)
test_res["residual"] = test_res["T_p95"] - test_res["alpha_j"] - BETA_F * test_res["F_i"]
job_residuals: dict[int, np.ndarray] = {}
for jid, grp in test_res.groupby("job_idx"):
    job_residuals[int(jid)] = grp["residual"].values.copy()

print("Precomputing background busy...")
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

def _to_dt64_ms(ts) -> np.datetime64:
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

hist_starts_dt64 = np.array([_to_dt64_ms(r["start_time"]) for _, r in jobs_sorted.iterrows()])
hist_ends_dt64   = np.array([_to_dt64_ms(r["end_time"])   for _, r in jobs_sorted.iterrows()])
hist_k_arr       = jobs_sorted["n_cohort"].values.astype(int)
hist_jids_arr    = jobs_sorted["job_idx"].values.astype(int)

print("Done loading.\n")

# ============================================================
# Helper
# ============================================================
def to_dt64(ts) -> np.datetime64:
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

def bg_busy_at(t_np: np.datetime64) -> frozenset:
    mask = (bg_st <= t_np) & (bg_et > t_np)
    return frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

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
    else:
        return [available[order[i]] for i in range(cap_k)]

# Instrumented look_ahead_safe: returns (decision, list of per-check diagnostics)
def look_ahead_safe_diag(selected_nodes, t_s, e_s, cf_busy):
    overlap_mask = (hist_starts_dt64 > t_s) & (hist_starts_dt64 < e_s)
    if not overlap_mask.any():
        return True, []
    s_nodes = frozenset(selected_nodes)
    n_sel   = len(selected_nodes)
    checks  = []
    for idx in np.where(overlap_mask)[0]:
        t_h   = hist_starts_dt64[idx]
        k_h   = int(hist_k_arr[idx])
        jid_h = int(hist_jids_arr[idx])
        bg_at_h  = bg_busy_per_job[jid_h]
        cf_at_h  = frozenset(n for n, te in cf_busy.items() if te > t_h)
        blocked  = bg_at_h | cf_at_h | s_nodes
        n_blocked = len(blocked)
        future_base_mask = (
            (hist_starts_dt64 > t_s) & (hist_starts_dt64 < t_h) & (hist_ends_dt64 > t_h)
        )
        future_base_k = min(int(hist_k_arr[future_base_mask].sum()), max(0, n_cohort - n_blocked))
        free = n_cohort - n_blocked - future_base_k
        ok   = free >= k_h
        checks.append({
            "h_idx": int(idx), "jid_h": jid_h, "t_h": t_h, "k_h": k_h,
            "n_bg": len(bg_at_h), "n_cf_at_h": len(cf_at_h), "n_sel": n_sel,
            "n_future_base": future_base_k, "free": free, "ok": ok,
        })
        if not ok:
            return False, checks
    return True, checks

# ============================================================
# Synthetic pool
# ============================================================
n_extra_max = int(np.ceil((1.80 - 1.0) * n_base))
rng_s = np.random.default_rng(WORKLOAD_SEED)
base_months = jobs_sorted["start_time"].dt.month.values
base_hours  = jobs_sorted["start_time"].dt.hour.values
strat_keys  = list(zip(base_months.tolist(), base_hours.tolist()))
strat_to_idxs: dict = {}
for i, sk in enumerate(strat_keys):
    strat_to_idxs.setdefault(sk, []).append(i)
unique_strata = sorted(strat_to_idxs.keys())
counts  = np.array([len(strat_to_idxs[s]) for s in unique_strata])
probs   = counts / counts.sum()
n_per   = np.round(probs * n_extra_max).astype(int)
diff    = n_extra_max - n_per.sum()
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
syn_pool = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
jitter_s           = rng_s.uniform(-1800.0, 1800.0, size=len(syn_pool))
syn_pool["start_time"]  = syn_pool["start_time"] + pd.to_timedelta(jitter_s, unit="s")
syn_pool["end_time"]    = syn_pool["start_time"] + pd.to_timedelta(syn_pool["run_time"].values, unit="s")
syn_pool["is_synthetic"]    = True
syn_pool["parent_job_idx"]  = syn_pool["job_idx"].values.copy()
syn_pool["job_idx"]         = -(np.arange(len(syn_pool), dtype=np.int64) + 1)
syn_pool["alpha_j"]         = syn_pool["parent_job_idx"].map(alpha_map)
syn_pool = syn_pool.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)

# CRN permutations
scen_rng  = np.random.default_rng(SCENARIO_SEED)
job_perms: dict[int, np.ndarray] = {}
for jid in jobs_sorted["job_idx"].astype(int):
    k = len(job_residuals[jid])
    job_perms[jid] = scen_rng.permutation(k)
if len(syn_pool) > 0:
    for syn_jid, parent_jid in zip(syn_pool["job_idx"].astype(int),
                                    syn_pool["parent_job_idx"].astype(int)):
        k = len(job_residuals[parent_jid])
        job_perms[syn_jid] = scen_rng.permutation(k)

n_syn_target = int(round((LAM - 1.0) * n_base))
syn_subset   = syn_pool.iloc[:n_syn_target].copy()
print(f"Synthetic jobs for lam={LAM}: {n_syn_target}")

# ============================================================
# Build combined schedule
# ============================================================
cap_per_node = (1.0 + 1e6) * LAM * hist_fleet_avg  # tiernc: no cap
base_copy = jobs_sorted.copy()
base_copy["is_synthetic"]   = False
base_copy["parent_job_idx"] = base_copy["job_idx"].values.copy()
combined = pd.concat([base_copy, syn_subset], ignore_index=True)
combined = combined.sort_values("start_time").reset_index(drop=True)

# ============================================================
# Instrumented replay
# ============================================================
cf_busy : dict[str, np.datetime64] = {}
cf_util : dict[str, float]         = {n: 0.0 for n in cohort_set}
_rng = np.random.default_rng(SCENARIO_SEED + abs(hash("tiernc")) % 1000)

# Admission history for trace
# Each entry: {jid, t_admit, t_end, k, is_base, la_checks}
admission_log: list[dict] = []

n_base_unserved = 0

print("Running instrumented replay...\n")

for row_idx, jrow in combined.iterrows():
    is_syn  = bool(jrow["is_synthetic"])
    t_j     = to_dt64(jrow["start_time"])
    t_e     = to_dt64(jrow["end_time"])
    rt_h    = float(jrow["run_time"]) / 3600.0
    k       = int(jrow["n_cohort"])
    jid     = int(jrow["job_idx"])

    pjid_raw = jrow["parent_job_idx"]
    try:
        parent_jid = int(pjid_raw)
    except (TypeError, ValueError):
        parent_jid = jid

    ppn = jrow.get("power_per_node", np.nan)
    P_j = float(ppn) if not pd.isnull(ppn) else np.nan

    bg_busy = (bg_busy_at(t_j) if is_syn
               else bg_busy_per_job.get(parent_jid, frozenset()))
    cf_busy_now = frozenset(n for n, te in cf_busy.items() if te > t_j)

    avail_capped = [
        n for n in cohort_set
        if n not in bg_busy and n not in cf_busy_now and cf_util[n] < cap_per_node
    ]

    if is_syn:
        if len(avail_capped) < k:
            continue  # drop
        available = avail_capped
    else:
        available = avail_capped if len(avail_capped) >= k else [
            n for n in cohort_set if n not in bg_busy and n not in cf_busy_now
        ]

    n_avail = len(available)
    if n_avail == 0:
        selected = []
    else:
        selected = tier_select(available, k, P_j, _rng)

    if is_syn and selected:
        ok, checks = look_ahead_safe_diag(selected, t_j, t_e, cf_busy)
        if not ok:
            continue  # rejected
        admission_log.append({
            "jid": jid, "parent_jid": parent_jid, "is_base": False,
            "t_admit": t_j, "t_end": t_e, "k": k,
            "nodes": frozenset(selected), "la_checks": checks,
        })
    elif not is_syn:
        if len(selected) < k:
            n_base_unserved += 1
            # =============================================
            # FAILURE TRACE
            # =============================================
            print("=" * 70)
            print("FIRST BASE-JOB INVARIANT VIOLATION")
            print("=" * 70)
            print(f"  Base job: jid={jid}  k_needed={k}  k_served={len(selected)}")
            print(f"  Start time (UTC): {jrow['start_time']}")
            print(f"  run_time: {rt_h:.2f} h")
            print(f"  n_avail at failure: {n_avail}  (need {k})")
            print(f"  |bg_busy| = {len(bg_busy)}")
            print(f"  |cf_busy_now| = {len(cf_busy_now)}")
            print(f"  n_cohort - |bg| - |cf_now| = {n_cohort - len(bg_busy) - len(cf_busy_now)}")

            # Synthetic jobs running right now (at t_j)
            syn_running = [
                e for e in admission_log
                if not e["is_base"] and e["t_admit"] <= t_j and e["t_end"] > t_j
            ]
            print(f"\n  Synthetic jobs running at t_fail ({len(syn_running)} of {len(admission_log)} admitted):")
            for i, e in enumerate(syn_running):
                # How many of this synthetic's nodes are in cf_busy_now
                n_overlap = len(e["nodes"] & cf_busy_now)
                print(f"    [{i+1}] jid={e['jid']}  parent={e['parent_jid']}  k={e['k']}")
                print(f"          admitted_at={e['t_admit']}  end={e['t_end']}")
                print(f"          nodes_in_cf_now={n_overlap}")
                # Re-check what look_ahead_safe would have predicted for THIS base job
                # at the time this synthetic was admitted
                s_in_overlap = (hist_starts_dt64 > e["t_admit"]) & (hist_starts_dt64 < e["t_end"])
                # Find this base job's index in jobs_sorted
                b_idx = np.where(hist_jids_arr == jid)[0]
                if len(b_idx) > 0:
                    b_idx = b_idx[0]
                    if s_in_overlap[b_idx]:
                        # This base job was in the look_ahead window of the synthetic
                        print(f"          --> base job WAS in look_ahead window of this synthetic")
                        # Was it checked?
                        checked = [c for c in e["la_checks"] if c["h_idx"] == b_idx]
                        if checked:
                            c = checked[0]
                            print(f"          --> check: n_bg={c['n_bg']}  n_cf_at_h={c['n_cf_at_h']}")
                            print(f"                     n_sel={c['n_sel']}  n_future_base={c['n_future_base']}")
                            print(f"                     free={c['free']}  k_h={c['k_h']}  ok={c['ok']}")
                        else:
                            print(f"          --> base job was NOT checked (loop exited early?)")
                    else:
                        print(f"          --> base job NOT in look_ahead window (started outside synthetic window)")

            # Show accumulated cf_busy at t_j: breakdown by base vs synthetic
            base_running = [
                e for e in admission_log
                if e["is_base"] and e["t_admit"] <= t_j and e["t_end"] > t_j
            ]
            print(f"\n  Base jobs in cf_busy at t_fail: {len(base_running)}")
            total_base_nodes  = sum(e["k"] for e in base_running)
            total_synth_nodes = sum(e["k"] for e in syn_running)
            print(f"  Total base nodes at t_fail: {total_base_nodes}")
            print(f"  Total synth nodes at t_fail: {total_synth_nodes}")
            print(f"  Total cf occupied: {len(cf_busy_now)}")
            print(f"  bg occupied: {len(bg_busy)}")
            print(f"  Unaccounted discrepancy: {len(cf_busy_now) - total_base_nodes - total_synth_nodes}")

            # Chronological accumulation of synthetic admissions that overlap t_j
            print(f"\n  Chronological synthetic admissions overlapping t_fail:")
            print(f"  {'#':>3}  {'t_admit':>12}  {'k':>5}  {'cf_size_at_admit':>16}  {'la_ok':>6}")
            cf_size_snapshots = []
            for j, e in enumerate([e2 for e2 in admission_log if not e2["is_base"]]):
                if e["t_end"] > t_j and e["t_admit"] <= t_j:
                    # Find cf_busy size at the time this synthetic was admitted
                    # (We can't recover exact cf_busy at that time from the log,
                    #  but we can compute from all admissions before this one)
                    admitted_before = [
                        e3 for e3 in admission_log
                        if e3["t_admit"] < e["t_admit"] and e3["t_end"] > e["t_admit"]
                    ]
                    cf_at_admit = sum(e3["k"] for e3 in admitted_before)
                    print(f"  {j+1:>3}  {str(e['t_admit']):>30}  {e['k']:>5}  {cf_at_admit:>16}  {'YES':>6}")

            print(f"\nTotal synthetic admissions: {len([e for e in admission_log if not e['is_base']])}")
            print("Exiting after first failure trace.")
            import sys
            sys.exit(0)
        else:
            admission_log.append({
                "jid": jid, "parent_jid": parent_jid, "is_base": True,
                "t_admit": t_j, "t_end": t_e, "k": k,
                "nodes": frozenset(selected), "la_checks": [],
            })

    for n in selected:
        cf_busy[n] = t_e
        cf_util[n] += rt_h

print("No base-job violations observed at this lambda -- check the policy/lambda.")
