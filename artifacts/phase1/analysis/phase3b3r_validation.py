# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.3-R: Validation, cabinet diagnostic, pooled envelope, Tier-cab policy.

1. Cabinet identity check: historical nodes -> B_cab_ratio ~= 1.0
2. q_c = P_cab_p99[c] / N_c diagnostic (distribution, correlations)
3. Pooled normalized envelope: q_pooled = p99(q_c), P_limit_c = q_pooled * N_c
4. Fleet power note: crossing at 0% by construction; report growth rate
5. Tier-cab policy: tier routing + real-time per-cabinet power cap
6. Sparse sweep: random, fp, tier20, tiercab -- both cabinet envelope variants
"""

import os
import pandas as pd
import numpy as np
import json, time, re
from pathlib import Path
from collections import defaultdict

ANALYSIS_DIR  = Path(__file__).parent
DATA_DIR      = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

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

print("=== Phase 3B.3-R: Validation + Cabinet diagnostic + Tier-cab ===\n")

# ============================================================
# Load
# ============================================================
fp_df        = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set   = set(fp_df.index)
F_dict       = fp_df["FA_2024"].to_dict()
cohort_list  = sorted(cohort_set)
n_cohort     = len(cohort_list)
print(f"Cohort: {n_cohort} nodes")

test_df = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")

all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"Total jobs: {len(all_jobs):,}")

print("Building cabinet map...")
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
all_cabinets = sorted(set(node_to_cabinet.values()))
print(f"  {len(node_to_cabinet)}/{n_cohort} nodes, {len(all_cabinets)} cabinets  ({time.time()-t0:.1f}s)")

print("Schedule arrays...")
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

print("Background busy...")
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

def _to_dt64_ms(ts):
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

hist_starts_dt64 = np.array([_to_dt64_ms(r["start_time"]) for _, r in jobs_sorted.iterrows()])
hist_ends_dt64   = np.array([_to_dt64_ms(r["end_time"])   for _, r in jobs_sorted.iterrows()])
hist_k_arr       = jobs_sorted["n_cohort"].values.astype(int)
hist_jids_arr    = jobs_sorted["job_idx"].values.astype(int)

def _dt64_to_h(a, b):
    return float((b - a).astype("int64")) / 3.6e6

# ============================================================
# Load phase3b3 power baseline results
# ============================================================
with open(ANALYSIS_DIR / "phase3b3_results.json") as f:
    p3b3 = json.load(f)

P_fleet_p99_hist = p3b3["P_fleet_p99_hist_W"]
P_fleet_max_hist = p3b3["P_fleet_max_hist_W"]
B_fleet_hist     = p3b3["B_fleet_hist_h"]
B_cab_hist       = p3b3["B_cab_hist_h"]
total_test_h     = p3b3["total_test_period_h"]

# Reload per-cabinet p99 (recompute since not stored in JSON)
print("\nRecomputing cabinet p99 from phase3b3 approach...")

def _build_hist_records():
    recs = []
    for _, jrow in jobs_sorted.iterrows():
        P_j = float(jrow["mean_power"]) if not pd.isna(jrow["mean_power"]) else 0.0
        nc  = max(1, int(jrow["node_count"]))
        ppn = P_j / nc
        t_s = _to_dt64_ms(jrow["start_time"])
        t_e = _to_dt64_ms(jrow["end_time"])
        cc  = defaultdict(int)
        for nd in jrow["hist_nodes"]:
            c = node_to_cabinet.get(nd, -1)
            if c >= 0:
                cc[c] += 1
        recs.append({"t_s":t_s,"t_e":t_e,"P_fleet":P_j,"ppn":ppn,"cab_counts":dict(cc)})
    return recs

hist_records = _build_hist_records()

def per_cabinet_p99(records):
    events = []
    for r in records:
        ppn = r["ppn"]
        for c, n in r["cab_counts"].items():
            dp = ppn * n
            events.append((r["t_s"], +1, c, dp))
            events.append((r["t_e"], -1, c, dp))
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
        total = sum(d for d,_ in ivals)
        s = sorted(ivals, key=lambda x: x[1])
        target = total * 0.99; cum = 0.0
        result[c] = s[-1][1]
        for dt, pwr in s:
            cum += dt
            if cum >= target:
                result[c] = pwr; break
    return result

P_cab_p99_hist = per_cabinet_p99(hist_records)
print(f"  {len(P_cab_p99_hist)} cabinet thresholds recomputed")

def sweep_line_power(records, fleet_thr, cab_thr):
    events = []
    for r in records:
        ppn = r["ppn"]
        cdp = {c: ppn*n for c, n in r["cab_counts"].items()}
        events.append((r["t_s"], +1, r["P_fleet"], cdp))
        neg = {c: -v for c, v in cdp.items()}
        events.append((r["t_e"], -1, r["P_fleet"], neg))
    events.sort(key=lambda x: (x[0], x[1]))
    P_fl = 0.0; P_cab = defaultdict(float); t_prev = None
    B_fl = 0.0; S_fl = 0.0; B_cb = 0.0; S_cb = 0.0
    for t, sign, dP_f, dP_c in events:
        if t_prev is not None and t != t_prev:
            dt_h = _dt64_to_h(t_prev, t)
            if dt_h > 0:
                exc_f = P_fl - fleet_thr
                if exc_f > 0: B_fl += dt_h; S_fl += dt_h*exc_f
                if cab_thr:
                    for c, Pc in P_cab.items():
                        exc_c = Pc - cab_thr.get(c, 0.0)
                        if exc_c > 0: B_cb += dt_h; S_cb += dt_h*exc_c
        P_fl += sign * dP_f
        for c, dp in dP_c.items(): P_cab[c] += dp
        t_prev = t
    return B_fl, S_fl, B_cb, S_cb

# ============================================================
# Part 1: Cabinet identity check
# ============================================================
print("\n" + "="*60)
print("PART 1: Cabinet identity check")
print("="*60)
# hist_records already uses historical nodes -> this IS the identity check
B_fl_id, S_fl_id, B_cb_id, S_cb_id = sweep_line_power(
    hist_records, P_fleet_p99_hist, P_cab_p99_hist)
print(f"  B_fleet_ratio (identity) = {B_fl_id/B_fleet_hist:.4f}  (expect 1.0000)")
print(f"  B_cab_ratio   (identity) = {B_cb_id/B_cab_hist:.4f}  (expect 1.0000)")
print(f"  S_cab_ratio   (identity) = {S_cb_id/p3b3.get('S_cab_hist_h', S_cb_id):.4f}"
      if "S_cab_hist_h" in p3b3 else f"  S_cab (abs)   = {S_cb_id:.2f} W*h")

# ============================================================
# Part 2: Cabinet threshold diagnostic
# ============================================================
print("\n" + "="*60)
print("PART 2: Cabinet threshold diagnostic  q_c = P_p99_c / N_c")
print("="*60)

# Per-cabinet: node count, utilization, high-power fraction, mean fingerprint
cab_node_count: dict[int, int]   = defaultdict(int)
cab_util_total: dict[int, float] = defaultdict(float)
cab_F_sum:      dict[int, float] = defaultdict(float)

for nd in cohort_list:
    c = node_to_cabinet.get(nd, -1)
    if c >= 0:
        cab_node_count[c]  += 1
        cab_util_total[c]  += hist_node_hours[nd]
        cab_F_sum[c]       += F_dict.get(nd, 0.0)

# High-power fraction: fraction of job-node-hours in high-power jobs (P_j > P95_PWR)
cab_hipwr_nh: dict[int, float] = defaultdict(float)
cab_total_nh: dict[int, float] = defaultdict(float)
for _, jrow in jobs_sorted.iterrows():
    is_hi = (not pd.isna(jrow["mean_power"])) and float(jrow["mean_power"]) >= P95_PWR
    rt_h  = float(jrow["run_time"]) / 3600.0
    for nd in jrow["hist_nodes"]:
        c = node_to_cabinet.get(nd, -1)
        if c >= 0:
            nh = rt_h
            cab_total_nh[c] += nh
            if is_hi:
                cab_hipwr_nh[c] += nh

cabs = sorted(P_cab_p99_hist.keys())
N_c       = np.array([cab_node_count[c]   for c in cabs], dtype=float)
P_p99_c   = np.array([P_cab_p99_hist[c]   for c in cabs], dtype=float)
q_c       = P_p99_c / N_c
util_pn_c = np.array([cab_util_total[c] / max(1, cab_node_count[c]) for c in cabs])
hipwr_frac= np.array([cab_hipwr_nh[c]   / max(1e-9, cab_total_nh[c]) for c in cabs])
mean_F_c  = np.array([cab_F_sum[c]       / max(1, cab_node_count[c]) for c in cabs])

print(f"\n  q_c = P_p99_c / N_c  (per-node p99 power in Watts):")
print(f"    mean={q_c.mean():.1f}  SD={q_c.std():.1f}  min={q_c.min():.1f}"
      f"  median={np.median(q_c):.1f}  max={q_c.max():.1f}")
print(f"    ratio max/min = {q_c.max()/max(q_c.min(),1e-9):.2f}x  (1.0 = uniform)")

# Spearman correlations
def spearm(a, b):
    ra = pd.Series(a).rank(); rb = pd.Series(b).rank()
    return float(np.corrcoef(ra, rb)[0,1])

print(f"\n  Spearman correlations with q_c:")
print(f"    vs N_c (node count):         r={spearm(q_c, N_c):+.3f}")
print(f"    vs util/node (h):            r={spearm(q_c, util_pn_c):+.3f}")
print(f"    vs high-power frac:          r={spearm(q_c, hipwr_frac):+.3f}")
print(f"    vs mean fingerprint F_mean:  r={spearm(q_c, mean_F_c):+.3f}")

# Quartiles of q_c
q_c_sorted = np.sort(q_c)
n_cabs = len(q_c_sorted)
print(f"\n  q_c distribution (W/node) -- {n_cabs} cabinets:")
for pct in [10, 25, 50, 75, 90, 99]:
    print(f"    p{pct:02d} = {np.percentile(q_c, pct):.1f} W/node")

# Interpretation: is q_c driven by utilization or by physical capacity?
r_util  = spearm(q_c, util_pn_c)
r_hipwr = spearm(q_c, hipwr_frac)
if abs(r_util) > 0.4 or abs(r_hipwr) > 0.4:
    print(f"\n  >> q_c correlates with workload exposure (r_util={r_util:+.2f},"
          f" r_hipwr={r_hipwr:+.2f}).")
    print( "     Cabinet-specific historical thresholds partly reflect routing history,")
    print( "     not only physical capacity. Pooled envelope is relevant.")
else:
    print(f"\n  >> q_c is not strongly driven by workload (r_util={r_util:+.2f}).")
    print( "     Cabinet-specific thresholds are a reasonable physical-capacity proxy.")

# ============================================================
# Part 3: Pooled normalized envelope
# ============================================================
print("\n" + "="*60)
print("PART 3: Pooled normalized cabinet envelope")
print("="*60)

q_pooled = float(np.percentile(q_c, 99))
P_cab_limit_pooled: dict[int, float] = {c: q_pooled * cab_node_count[c]
                                         for c in all_cabinets}
print(f"  q_pooled (p99 of q_c distribution) = {q_pooled:.1f} W/node")
print(f"  P_limit range (pooled): "
      f"{min(P_cab_limit_pooled.values()):.0f} - {max(P_cab_limit_pooled.values()):.0f} W")
print(f"  Comparison: historical-specific range "
      f"{P_p99_c.min():.0f} - {P_p99_c.max():.0f} W")

# Also compute B_cab_hist under pooled thresholds (new baseline for pooled ratio)
B_fl_pool, S_fl_pool, B_cb_pool_hist, S_cb_pool_hist = sweep_line_power(
    hist_records, P_fleet_p99_hist, P_cab_limit_pooled)
print(f"  B_cab_hist (pooled thresholds) = {B_cb_pool_hist:.2f} h"
      f"  (vs {B_cab_hist:.2f} h specific)")

# ============================================================
# Part 4: Fleet power note
# ============================================================
print("\n" + "="*60)
print("PART 4: Fleet power analysis")
print("="*60)
print(f"  P_fleet_p99_hist (test jobs only) = {P_fleet_p99_hist/1e6:.3f} MW")
print(f"  P_fleet_max_hist (test jobs only) = {P_fleet_max_hist/1e6:.3f} MW")
print(f"  B_fleet_hist = {B_fleet_hist:.2f} h  (= 1% of {total_test_h:.0f} h test period)")
print()
print("  Fleet power is policy-independent: P_fleet(t) = sum P_j regardless of")
print("  node assignment. At lam=1.0 the replay is identical to historical -> ratio=1.0.")
print("  C_fleet = 0.0% by definition for all policies (historical system at p99 load).")
print()
print("  Fleet power B_fleet_ratio growth from phase3b3:")
for pk in ["random", "fp", "tier20"]:
    rows = p3b3["policy_results"][pk]
    print(f"    {pk:<10} lam=1.10 B_flt={[r for r in rows if r['lambda_val']==1.1][0].get('B_fleet_ratio','?'):.4f}"
          f"  lam=1.40 B_flt={[r for r in rows if r['lambda_val']==1.4][0].get('B_fleet_ratio','?'):.4f}"
          f"  lam=1.80 B_flt={[r for r in rows if r['lambda_val']==1.8][0].get('B_fleet_ratio','?'):.4f}")
print()
print("  Fleet power max exceedance: first new historical maximum at lam=1.10 (~32s).")
print("  Without nameplate electrical capacity, fleet power cannot yield a hard ceiling.")
print("  Cabinet power (policy-dependent) is the operative constraint.")

# ============================================================
# Helpers (same as phase3b2d / phase3b3)
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
        return pd.DataFrame(columns=list(jobs_sorted.columns)+["is_synthetic","parent_job_idx"])
    syn = pd.concat(chunks, ignore_index=True)
    jitter = rng_s.uniform(-1800., 1800., size=len(syn))
    syn["start_time"]     = syn["start_time"] + pd.to_timedelta(jitter, unit="s")
    syn["end_time"]       = syn["start_time"] + pd.to_timedelta(syn["run_time"].values, unit="s")
    syn["is_synthetic"]   = True
    syn["parent_job_idx"] = syn["job_idx"].values.copy()
    syn["job_idx"]        = -(np.arange(len(syn), dtype=np.int64) + 1)
    syn["alpha_j"]        = syn["parent_job_idx"].map(alpha_map)
    syn = syn.sample(frac=1, random_state=int(rng_s.integers(0,2**31))).reset_index(drop=True)
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
# Replay with cabinet power tracking and optional cab cap
# ============================================================
def capacity_replay(
    syn_subset, policy, delta_cap, lambda_val, policy_seed, job_perms,
    P_cab_limit=None,   # dict[cab->W] for tiercab; None = no cap
    identity_mode=False,# use historical nodes for base jobs
):
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
    cf_node_ppn: dict[str, float]     = {}   # node -> ppn for active jobs
    _rng = np.random.default_rng(policy_seed)

    B_node = 0.0; S_node = 0.0
    syn_node_hours  = 0.0
    n_syn_admit     = 0
    n_drop_cap      = 0
    n_drop_phys     = 0
    n_drop_la       = 0
    n_drop_cabcap   = 0
    n_base_unserved = 0
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
        try: parent_jid = int(pjid_raw)
        except (TypeError, ValueError): parent_jid = jid

        bg_busy = (bg_busy_at(t_j) if is_syn
                   else bg_busy_per_job.get(parent_jid, frozenset()))
        cf_busy_now = frozenset(n for n, te in cf_busy.items() if te > t_j)

        avail_capped = [
            n for n in cohort_set
            if n not in bg_busy and n not in cf_busy_now and cf_util[n] < cap_per_node
        ]

        # --- Identity mode for base jobs ---
        if identity_mode and not is_syn:
            selected = list(jrow["hist_nodes"])
            for n in selected:
                cf_busy[n] = t_e
                cf_util[n] += rt_h
                cf_node_ppn[n] = ppn
            F_arr = np.array([F_dict[n] for n in selected])
            alpha = float(jrow["alpha_j"])
            res_s, _ = job_residuals[parent_jid]
            perm = job_perms[jid]
            rank = np.argsort(np.argsort(F_arr))
            T_hats_j = alpha + BETA_F * F_arr + res_s[perm[rank]]
            excesses = T_hats_j - T_P95_THRESHOLD
            B_node += rt_h * float((excesses > 0).sum())
            S_node += rt_h * float(excesses.clip(min=0).sum())
            cc = defaultdict(int)
            for nd in selected:
                c = node_to_cabinet.get(nd,-1)
                if c >= 0: cc[c] += 1
            power_records.append({"t_s":t_j,"t_e":t_e,"P_fleet":P_j,"ppn":ppn,"cab_counts":dict(cc)})
            continue

        if is_syn:
            if len(avail_capped) < k:
                avail_uncapped = [n for n in cohort_set if n not in bg_busy and n not in cf_busy_now]
                n_drop_phys += 1 if len(avail_uncapped) < k else 0
                n_drop_cap  += 1 if len(avail_uncapped) >= k else 0
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
        elif policy in ("tier20", "tiercab"):
            if policy == "tiercab" and P_cab_limit is not None and is_syn:
                # compute current per-cabinet active power
                cab_pw_cur: dict[int, float] = defaultdict(float)
                for nd, te in cf_busy.items():
                    if te > t_j and nd in cf_node_ppn:
                        c = node_to_cabinet.get(nd, -1)
                        if c >= 0:
                            cab_pw_cur[c] += cf_node_ppn[nd]
                # filter: exclude nodes whose cabinet would exceed limit
                avail_cabcap = [
                    n for n in available
                    if cab_pw_cur.get(node_to_cabinet.get(n,-1), 0.0) + ppn
                       <= P_cab_limit.get(node_to_cabinet.get(n,-1), float("inf"))
                ]
                if len(avail_cabcap) < k:
                    n_drop_cabcap += 1
                    continue
                selected = tier_select(avail_cabcap, k, ppn_cf, _rng)
            else:
                selected = tier_select(available, k, ppn_cf, _rng)
        else:
            idx = _rng.choice(n_avail, size=min(k, n_avail), replace=False)
            selected = [available[i] for i in idx]

        if is_syn and selected:
            if not look_ahead_safe(selected, t_j, t_e, cf_busy):
                n_drop_la += 1; continue

        if not is_syn and len(selected) < k:
            n_base_unserved += 1

        for n in selected:
            cf_busy[n] = t_e
            cf_util[n] += rt_h
            cf_node_ppn[n] = ppn

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
            cc = defaultdict(int)
            for nd in selected:
                c = node_to_cabinet.get(nd,-1)
                if c >= 0: cc[c] += 1
            power_records.append({"t_s":t_j,"t_e":t_e,"P_fleet":P_j,"ppn":ppn,"cab_counts":dict(cc)})

    if n_base_unserved > 0:
        raise AssertionError(
            f"Base-job invariant violated: {n_base_unserved} job(s) "
            f"(lam={lambda_val}, policy={policy})")

    unlock_pct = syn_node_hours / hist_total_nh * 100.0

    B_fl_r, S_fl_r, B_cb_r_spec, S_cb_r_spec = sweep_line_power(
        power_records, P_fleet_p99_hist, P_cab_p99_hist)
    _, _, B_cb_r_pool, S_cb_r_pool = sweep_line_power(
        power_records, P_fleet_p99_hist, P_cab_limit_pooled)

    return {
        "lambda_val"           : lambda_val,
        "policy"               : policy,
        "n_syn_admit"          : n_syn_admit,
        "n_drop_cap"           : n_drop_cap,
        "n_drop_physical"      : n_drop_phys,
        "n_drop_la"            : n_drop_la,
        "n_drop_cabcap"        : n_drop_cabcap,
        "n_base_unserved"      : n_base_unserved,
        "syn_node_hours"       : syn_node_hours,
        "capacity_unlock_pct"  : unlock_pct,
        "B_node_ratio"         : B_node / B_hist_node if B_hist_node > 0 else np.nan,
        "S_node_ratio"         : S_node / S_hist_node if S_hist_node > 0 else np.nan,
        "B_fleet_ratio"        : B_fl_r / B_fleet_hist if B_fleet_hist > 0 else np.nan,
        "B_cab_ratio_spec"     : B_cb_r_spec / B_cab_hist if B_cab_hist > 0 else np.nan,
        "B_cab_ratio_pool"     : B_cb_r_pool / B_cb_pool_hist if B_cb_pool_hist > 0 else np.nan,
    }

def find_crossing(rows, ratio_key, target=1.0):
    valid = [r for r in rows if ratio_key in r and not np.isnan(r.get(ratio_key, float("nan")))]
    if not valid: return None
    xs = [r["capacity_unlock_pct"] for r in valid]
    ys = [r[ratio_key] for r in valid]
    for i in range(len(ys)-1):
        if ys[i] <= target <= ys[i+1]:
            frac = (target - ys[i]) / max(ys[i+1] - ys[i], 1e-12)
            return float(xs[i] + frac*(xs[i+1]-xs[i]))
        if i == 0 and ys[i] >= target:
            return 0.0
    return None

# ============================================================
# Part 5: Sweep
# ============================================================
print("\n" + "="*60)
print("PART 5: Sparse sweep -- all policies, both cabinet envelopes")
print("="*60)

POLICY_DEFS = [
    ("random",   1e6,  "Random-feasible",  None),
    ("fp",       0.10, "FP-cap-10",        None),
    ("tier20",   0.20, "Tier-cap-20",      None),
    ("tiercab",  0.20, "Tier-cab-spec",    P_cab_p99_hist),     # specific historical
    ("tiercab2", 0.20, "Tier-cab-pool",    P_cab_limit_pooled), # pooled normalized
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
        columns=syn_pool.columns if len(syn_pool)>0 else jobs_sorted.columns)
    print(f"--- lam={lam:.2f} N_syn={n_syn} ---")
    hdr = f"  {'Policy':<20} | {'NH%':>5} | {'B/Bh':>6} | {'Bcab_s':>7} | {'Bcab_p':>7} | drops"
    print(hdr); print("  " + "-"*(len(hdr)-2))
    for pk, delta_cap, label, P_cab_lim in POLICY_DEFS:
        t0 = time.time()
        try:
            res = capacity_replay(syn_subset, pk if pk!="tiercab2" else "tiercab",
                                  delta_cap, lam,
                                  policy_seed=SCENARIO_SEED + abs(hash(pk)) % 1000,
                                  job_perms=job_perms,
                                  P_cab_limit=P_cab_lim)
            res["policy"] = pk
        except AssertionError as exc:
            print(f"  {label:<20} | INVARIANT VIOLATED -- {exc}")
            all_results[pk].append({"lambda_val":lam,"policy":pk,"invariant_violated":True})
            continue
        elapsed = time.time() - t0
        all_results[pk].append(res)
        bs  = res.get("B_cab_ratio_spec", float("nan"))
        bp  = res.get("B_cab_ratio_pool", float("nan"))
        dcc = res.get("n_drop_cabcap", 0)
        drops = f"{res['n_drop_physical']}/{res['n_drop_cap']}/{res['n_drop_la']}" + \
                (f"/cc{dcc}" if dcc > 0 else "")
        print(f"  {label:<20} | {res['capacity_unlock_pct']:>5.1f} |"
              f" {res['B_node_ratio']:>6.4f} | {bs:>7.4f} | {bp:>7.4f} |"
              f" {drops}  ({elapsed:.0f}s)")

# ============================================================
# Part 6: Crossing analysis and C_feasible
# ============================================================
print("\n" + "="*60)
print("CROSSING ANALYSIS AND FINAL C_feasible")
print("="*60)

# Load thermal crossings
with open(ANALYSIS_DIR / "phase3b2d_results.json") as f:
    therm = json.load(f)["crossings"]

def fmt(v): return f"{v:.1f}%" if v is not None else ">explored"

print(f"\n  {'Policy':<22} | {'C_B_th':>7} | {'C_S_th':>7} | "
      f"{'C_cab_spec':>10} | {'C_cab_pool':>10} | {'C_feasible':>11}")
print("  " + "-"*85)

rand_cfeas_spec = None; rand_cfeas_pool = None

for pk, delta_cap, label, P_cab_lim in POLICY_DEFS:
    rows = all_results[pk]
    tc   = therm.get(pk if pk not in ("tiercab","tiercab2") else "tier20", {})
    c_BT = tc.get("C_B"); c_ST = tc.get("C_S")
    c_cs = find_crossing(rows, "B_cab_ratio_spec")
    c_cp = find_crossing(rows, "B_cab_ratio_pool")

    cands_spec = [x for x in [c_BT, c_ST, c_cs] if x is not None]
    cands_pool = [x for x in [c_BT, c_ST, c_cp] if x is not None]
    cfeas_spec = min(cands_spec) if cands_spec else None
    cfeas_pool = min(cands_pool) if cands_pool else None

    if pk == "random":
        rand_cfeas_spec = cfeas_spec; rand_cfeas_pool = cfeas_pool

    delta_spec = (cfeas_spec - rand_cfeas_spec) if (cfeas_spec and rand_cfeas_spec) else None
    ds = f"+{delta_spec:.1f}pp" if delta_spec is not None else "N/A"

    print(f"  {label:<22} | {fmt(c_BT):>7} | {fmt(c_ST):>7} | "
          f"{fmt(c_cs):>10} | {fmt(c_cp):>10} | "
          f"{fmt(cfeas_spec):>9} ({ds})")

# Save
out = {
    "q_c_mean": float(q_c.mean()), "q_c_sd": float(q_c.std()),
    "q_c_min": float(q_c.min()), "q_c_max": float(q_c.max()),
    "q_pooled": q_pooled,
    "spearman_qc_vs_util": float(spearm(q_c, util_pn_c)),
    "spearman_qc_vs_hipwr": float(spearm(q_c, hipwr_frac)),
    "spearman_qc_vs_N": float(spearm(q_c, N_c)),
    "B_cab_hist_pooled": B_cb_pool_hist,
    "policy_results": {pk: all_results[pk] for pk, *_ in POLICY_DEFS},
}
outpath = ANALYSIS_DIR / "phase3b3r_results.json"
with open(outpath, "w") as f:
    json.dump(out, f, indent=2, default=str)
print(f"\n  Saved {outpath}")
print("\n=== Done ===")
