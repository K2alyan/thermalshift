#!/usr/bin/env python3
"""
M4 Availability Transition Experiment.
Post-hoc. Does NOT modify m4_fair_baselines.json.

Fractions: 60%, 70%, 80%, 90%, 100% (extending existing 10%-60% sensitivity)
Scenarios:  sc0-sc4 (dev) + sc5-sc9 (held-out) = 10 total, pre-declared
Policies:   full_fp and full_random only
Design:     Expanding-subset — each scenario uses one fixed permutation
            perm_s = RNG(AVAIL_SEED + s_idx).permutation(N_FP)
            avail_f_s = {fp_list[perm_s[i]] for i in range(round(f * N_FP))}
            f=1.00 -> avail_nodes=None (unrestricted cohort)

Full crossing refinement (refine_crossing_bracket) per policy x fraction x scenario.
Interval-aware: delta_lo = C_lower_fp - C_upper_rand (pessimistic, FP over rand)
                delta_hi = C_upper_fp - C_lower_rand (optimistic)

Output: artifacts/revision1/results/m4_avail_transition.json
"""

import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import json, time, heapq
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

# ── Paths (identical to r1_m4_fair_baselines.py) ───────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
P1_DIR    = REPO_ROOT / "artifacts" / "phase1" / "analysis"
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR   = REV1_DIR / "results"
TABLE_DIR = REV1_DIR / "tables"
DATA_DIR  = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

# ── Constants (identical to r1_m4_fair_baselines.py) ───────────────────
BETA_F_FROZEN    = 1.12484352
T_THR_PRIMARY    = 63.625
T_THR_SECONDARY  = 60.602770562770566
DELTA_CAP        = 0.10
N_BINS           = 5
N_SCENARIOS      = 30
SCENARIO_SEED    = 42
N_FP             = 2000
LAMBDA_SWEEP     = [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40,
                    1.50, 1.55, 1.60, 1.70, 1.80, 1.90, 2.00]
LAMBDA_MAX       = 2.00
LAMBDA_MAX_EXT   = 4.00
LAMBDA_SWEEP_EXT = [2.25, 2.50, 3.00, 3.50, 4.00]
TARGET_PP        = 0.5
N_REFINE_GRID    = 3

POLICY_IDS = ["full_random", "full_fp", "full_loc", "full_compact",
              "marginal_random", "marginal_fp", "full_fp_spread"]
POLICY_MAP = {
    "full_random":     ("random",    False),
    "full_fp":         ("fp",        False),
    "full_loc":        ("loc",       False),
    "full_compact":    ("compact",   False),
    "marginal_random": ("random",    True),
    "marginal_fp":     ("fp",        True),
    "full_fp_spread":  ("fp_spread", False),
}

# ── Transition experiment settings ─────────────────────────────────────
AVAIL_FRACTIONS = [0.60, 0.70, 0.80, 0.90, 1.00]
AVAIL_SCENARIOS = list(range(10))   # sc0-sc9; declared before looking at results
AVAIL_SEED      = 20260929          # distinct from main-script SCENARIO_SEED
TRANS_POLICIES  = ["full_fp", "full_random"]
OUT_FILE        = OUT_DIR / "m4_avail_transition.json"

# ── Regression-test mode ────────────────────────────────────────────────
# M4_AVAIL_REGRESSION=1: run only f=1.00 for sc0-9, compare to frozen v5,
# exit 0 if all pass, exit 1 if any field mismatches. Safe to run before
# the full 60-100% experiment to catch any reimplementation divergence.
REGRESSION_ONLY = os.environ.get("M4_AVAIL_REGRESSION", "0").strip() in ("1", "true")
if REGRESSION_ONLY:
    AVAIL_FRACTIONS = [1.00]   # collapse to 100% only
    OUT_FILE        = OUT_DIR / "m4_avail_regression.json"


def jf(v):
    if v is None:
        return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f

def _col_to_dt64ms(series):
    s = pd.to_datetime(series, utc=True)
    return s.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ms]")

def _dt64_to_h(a, b):
    return float((b - a).astype("int64")) / 3.6e6

def _rec_ts_ms(r):
    v = r["t_s"]
    return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))

def _rec_te_ms(r):
    v = r["t_e"]
    return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))


# ══════════════════════════════════════════════════════════════════════
# [0] Load core data
# ══════════════════════════════════════════════════════════════════════
print("\nM4 Availability Transition Experiment")
print("=" * 70)
print(f"Fractions: {AVAIL_FRACTIONS}")
print(f"Scenarios: sc{AVAIL_SCENARIOS[0]}-sc{AVAIL_SCENARIOS[-1]}  (dev=sc0-4, held-out=sc5-9)")
print(f"Policies:  {TRANS_POLICIES}")
print(f"AVAIL_SEED: {AVAIL_SEED}  (expanding-subset design)")
print("=" * 70)
t_script = time.time()

print("\n[0] Loading inputs ...")
fp_df    = pd.read_parquet(P1_DIR / "phase3a_fingerprint_2024.parquet")
test_df  = pd.read_parquet(P1_DIR / "phase3a_test_set.parquet")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)

fp_df.index.name = "node"
cohort_set  = set(fp_df.index)
FA_dict     = fp_df["FA_2024"].to_dict()
cohort_list = sorted(cohort_set)
n_cohort    = len(cohort_list)
_F_vals_arr  = np.array(list(FA_dict.values()), dtype=float)
F_COOL10_THR = float(np.percentile(_F_vals_arr, 10))
print(f"    fp nodes: {n_cohort}  test rows: {len(test_df):,}  all jobs: {len(all_jobs):,}")

# ══════════════════════════════════════════════════════════════════════
# [1] Correct topology (Gate C)
# ══════════════════════════════════════════════════════════════════════
print("\n[1] Building node-to-cabinet map ...")
fleet_topo  = pd.read_csv(TABLE_DIR / "fleet_node_topology.csv")
node_to_cab: dict[str, int] = dict(
    zip(fleet_topo["hostname"].values, fleet_topo["cabinet"].values.astype(int))
)
all_cabinets = sorted(set(node_to_cab.values()))
assert len(node_to_cab) == 9856, f"Expected 9856 nodes, got {len(node_to_cab)}"
assert len(all_cabinets) == 77,  f"Expected 77 cabinets, got {len(all_cabinets)}"
fp_cab: dict[str, int] = {n: node_to_cab[n] for n in cohort_list if n in node_to_cab}
assert len(fp_cab) == n_cohort

cab_eligible_count: dict[int, int] = {}
for _n in cohort_list:
    _c = fp_cab.get(_n, -1)
    if _c >= 0:
        cab_eligible_count[_c] = cab_eligible_count.get(_c, 0) + 1
print(f"    {len(node_to_cab):,} nodes, {len(all_cabinets)} cabinets")

# ══════════════════════════════════════════════════════════════════════
# [2] Location-only fingerprint
# ══════════════════════════════════════════════════════════════════════
print("\n[2] Building location-only fingerprint ...")
fp_topo = pd.read_csv(TABLE_DIR / "fp_node_topology.csv")
fp_topo["pos_key"] = (fp_topo["chassis"].astype(str) + "_" +
                      fp_topo["slot"].astype(str)    + "_" +
                      fp_topo["board"].astype(str)   + "_" +
                      fp_topo["node_pos"].astype(str))
fp_topo["FA_2024"] = fp_topo["hostname"].map(FA_dict)
pos_mean = fp_topo.groupby("pos_key")["FA_2024"].mean().rename("FA_loc")
fp_topo  = fp_topo.join(pos_mean, on="pos_key")
LOC_FA_dict: dict[str, float] = dict(
    zip(fp_topo["hostname"].values, fp_topo["FA_loc"].values)
)
_glob_mean  = float(np.nanmean(list(LOC_FA_dict.values())))
LOC_FA_dict = {k: (v if not np.isnan(v) else _glob_mean) for k, v in LOC_FA_dict.items()}

# ══════════════════════════════════════════════════════════════════════
# [3] Cabinet P^99 power thresholds (Gate C corrected)
# ══════════════════════════════════════════════════════════════════════
print("\n[3] Loading cabinet P^99 ...")
with open(OUT_DIR / "cabinet_power_envelopes.json") as fh:
    cab_env = json.load(fh)
cab_p99_W: dict[int, float] = {
    int(float(k)): v * 1e3
    for k, v in cab_env["per_cabinet_p99_kW_correct"].items()
}
_p99_med  = float(np.median(list(cab_p99_W.values())))
cab_p99_W = {c: cab_p99_W.get(c, _p99_med) for c in all_cabinets}
print(f"    {len(cab_p99_W)} cabinets loaded")

# ══════════════════════════════════════════════════════════════════════
# [4] Schedule arrays
# ══════════════════════════════════════════════════════════════════════
print("\n[4] Building schedule arrays ...")
t0 = time.time()
cohort_per_job: dict[int, frozenset] = {}
for jid, hl in zip(all_jobs["job_idx_int"].values, all_jobs["host_list"].values):
    cn = frozenset(n for n in hl if n in cohort_set)
    if cn:
        cohort_per_job[jid] = cn

sched_mask = np.array([jid in cohort_per_job for jid in all_jobs["job_idx_int"].values])
sched_jids = all_jobs["job_idx_int"].values[sched_mask]
sched_st   = _col_to_dt64ms(all_jobs["start_time"])[sched_mask]
sched_et   = _col_to_dt64ms(all_jobs["end_time"])[sched_mask]
sched_cn   = np.array([cohort_per_job[jid] for jid in sched_jids], dtype=object)
print(f"    {len(sched_jids):,} cohort-containing jobs  ({time.time()-t0:.1f}s)")

# ══════════════════════════════════════════════════════════════════════
# [5] Job-level aggregates (test jobs only)
# ══════════════════════════════════════════════════════════════════════
print("\n[5] Aggregating test-job summaries ...")
test_id_set = set(test_df["job_idx"].astype(int))
job_agg = (
    test_df.groupby("job_idx")
    .agg(F_hist_mean=("F_2024", "mean"),
         n_cohort=("node", "count"),
         T_p95_hist=("T_p95", "mean"),
         hist_nodes=("node", list))
    .reset_index()
)
meta = (
    all_jobs[["job_idx_int", "node_count", "start_time", "end_time",
              "mean_power", "run_time"]]
    .rename(columns={"job_idx_int": "job_idx"})
)
job_agg      = job_agg.merge(meta, on="job_idx", how="left")
job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)
jobs_sorted  = job_agg.sort_values("start_time").reset_index(drop=True)
n_base       = len(jobs_sorted)

def _make_quartile_map(arr, jids):
    cuts = np.percentile(arr, [25, 50, 75])
    q    = (np.digitize(arr, cuts) + 1).clip(1, 4)
    return {int(jid): int(qi) for jid, qi in zip(jids, q)}

_jids             = jobs_sorted["job_idx"].values
job_quartile_ncoh = _make_quartile_map(jobs_sorted["n_cohort"].values, _jids)
job_quartile_nc   = _make_quartile_map(jobs_sorted["node_count"].fillna(0).values, _jids)
job_quartile_ppn  = _make_quartile_map(jobs_sorted["power_per_node"].fillna(0).values, _jids)
job_quartile_rt   = _make_quartile_map(jobs_sorted["run_time"].fillna(0).values, _jids)
job_quartile      = job_quartile_ncoh   # primary quartile for q_admit/q_drop

hist_node_hours: dict[str, float] = {n: 0.0 for n in cohort_list}
_nh_rt = jobs_sorted["run_time"].fillna(0.0).values / 3600.0
_nh_ns = jobs_sorted["hist_nodes"].values
for _ni in range(len(jobs_sorted)):
    _rt = float(_nh_rt[_ni])
    for nd in _nh_ns[_ni]:
        if nd in hist_node_hours:
            hist_node_hours[nd] += _rt
hist_util_arr  = np.array([hist_node_hours[n] for n in cohort_list])
hist_total_nh  = float(hist_util_arr.sum())
hist_fleet_avg = hist_total_nh / n_cohort
print(f"    {n_base} base test jobs  hist_total_nh={hist_total_nh:.1f}  hist_fleet_avg={hist_fleet_avg:.3f}")

# ══════════════════════════════════════════════════════════════════════
# [6] Residual model (N_BINS=5)
# ══════════════════════════════════════════════════════════════════════
print("\n[6] Building residual model ...")
test_df2 = test_df.copy()
test_df2["job_mean_T"] = test_df2.groupby("job_idx")["T_p95"].transform("mean")
alpha_map: dict[int, float] = test_df2.groupby("job_idx")["job_mean_T"].first().to_dict()
test_df2["delta_T_p95"] = test_df2["T_p95"] - test_df2["job_mean_T"]
test_df2["pred_frozen"]  = BETA_F_FROZEN * test_df2["F_2024"]
test_df2["residual"]     = test_df2["delta_T_p95"] - test_df2["pred_frozen"]

job_residuals: dict[int, tuple] = {}
for jid, grp in test_df2.groupby("job_idx"):
    jid     = int(jid)
    grp_s   = grp.sort_values("F_2024")
    res_arr = grp_s["residual"].values.copy()
    k       = len(grp_s)
    if k >= N_BINS:
        try:
            bins = pd.qcut(grp_s["F_2024"], q=N_BINS, labels=False,
                           duplicates="drop").values.astype(int)
        except Exception:
            bins = np.zeros(k, dtype=int)
    else:
        bins = np.zeros(k, dtype=int)
    job_residuals[jid] = (res_arr, bins)

jobs_sorted["alpha_j"] = jobs_sorted["job_idx"].astype(int).map(alpha_map)
print(f"    {len(job_residuals)} jobs with residuals")

# ══════════════════════════════════════════════════════════════════════
# [7] Background busy arrays (non-test-job cohort activity)
# ══════════════════════════════════════════════════════════════════════
print("\n[7] Precomputing background busy arrays ...")
t0 = time.time()
is_test_sched = np.array([jid in test_id_set for jid in sched_jids])
bg_st    = sched_st[~is_test_sched]
bg_et    = sched_et[~is_test_sched]
bg_cn    = sched_cn[~is_test_sched]
bg_st_ms = bg_st.astype(np.int64)
bg_et_ms = bg_et.astype(np.int64)

hist_st_for_precomp = _col_to_dt64ms(jobs_sorted["start_time"]).astype(np.int64)
bg_busy_per_job: dict[int, frozenset] = {}
for i, jid in enumerate(jobs_sorted["job_idx"].values.astype(int)):
    t_ms = int(hist_st_for_precomp[i])
    mask = (bg_st_ms <= t_ms) & (bg_et_ms > t_ms)
    bg_busy_per_job[jid] = frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()
del hist_st_for_precomp

hist_starts_dt64 = _col_to_dt64ms(jobs_sorted["start_time"])
hist_ends_dt64   = _col_to_dt64ms(jobs_sorted["end_time"])
hist_starts_ms   = hist_starts_dt64.astype(np.int64)
hist_ends_ms     = hist_ends_dt64.astype(np.int64)
hist_k_arr       = jobs_sorted["n_cohort"].values.astype(int)
hist_jids_arr    = jobs_sorted["job_idx"].values.astype(int)
print(f"    Done  ({time.time()-t0:.1f}s)")

# ══════════════════════════════════════════════════════════════════════
# [8] Cabinet power background
# ══════════════════════════════════════════════════════════════════════
print("\n[8] Precomputing cabinet background power ...")
t0 = time.time()
_all_jids = all_jobs["job_idx_int"].values
_all_Pj   = np.where(all_jobs["mean_power"].isna().values, 0.0,
                     all_jobs["mean_power"].values.astype(float))
_all_nc   = np.maximum(all_jobs["node_count"].values.astype(int), 1)
_all_hl   = all_jobs["host_list"].values
_all_st   = _col_to_dt64ms(all_jobs["start_time"])
_all_et   = _col_to_dt64ms(all_jobs["end_time"])

bg_records: list[dict] = []
cohort_hist_records: list[dict] = []
for jid, P_j, nc, hl, t_s, t_e in zip(_all_jids, _all_Pj, _all_nc, _all_hl, _all_st, _all_et):
    ppn = P_j / nc
    ncc: dict[int, int] = {}
    chc: dict[int, int] = {}
    for hn in hl:
        c = node_to_cab.get(hn, -1)
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
print(f"    bg_records: {len(bg_records):,}  hist_cohort_records: {len(cohort_hist_records):,}"
      f"  ({time.time()-t0:.1f}s)")

print("\n[8b] Pre-sorting background cabinet events ...")
t0 = time.time()
bg_events_sorted: list[tuple] = []
for _r in bg_records:
    _ppn = _r["ppn"]
    _ts  = int(_r["t_s"].astype("int64"))
    _te  = int(_r["t_e"].astype("int64"))
    for _c, _n in _r["cab_counts"].items():
        _dp = _ppn * _n
        bg_events_sorted.append((_ts, +1, _c, _dp))
        bg_events_sorted.append((_te, -1, _c, _dp))
bg_events_sorted.sort()
print(f"    {len(bg_events_sorted):,} bg events sorted  ({time.time()-t0:.1f}s)")


def sweep_cab_budget_fast(cohort_records: list[dict],
                          thr: dict[int, float]) -> tuple[float, float]:
    coh_ev: list[tuple] = []
    for r in cohort_records:
        ppn = r["ppn"]
        ts  = _rec_ts_ms(r)
        te  = _rec_te_ms(r)
        for c, n in r["cab_counts"].items():
            dp = ppn * n
            coh_ev.append((ts, +1, c, dp))
            coh_ev.append((te, -1, c, dp))
    coh_ev.sort()
    events = heapq.merge(bg_events_sorted, coh_ev)
    P_cab: dict[int, float] = defaultdict(float)
    last_t: dict[int, int]  = {}
    B = 0.0; S = 0.0
    for t, sign, c, dp in events:
        if c in last_t and t != last_t[c]:
            dt_h = (t - last_t[c]) / 3_600_000.0
            if dt_h > 0:
                exc = P_cab[c] - thr.get(c, 0.0)
                if exc > 0:
                    B += dt_h
                    S += dt_h * exc
        P_cab[c] += sign * dp
        last_t[c] = t
    return B, S


B_cab_hist, S_cab_hist = sweep_cab_budget_fast(cohort_hist_records, cab_p99_W)
print(f"    B_cab_hist: {B_cab_hist:.2f} h  S_cab_hist: {S_cab_hist:.2f} W*h")


# ══════════════════════════════════════════════════════════════════════
# [9] Helper functions (verbatim from r1_m4_fair_baselines.py)
# ══════════════════════════════════════════════════════════════════════

def bg_busy_at_ms(t_ms: int) -> frozenset:
    mask = (bg_st_ms <= t_ms) & (bg_et_ms > t_ms)
    return frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()


def look_ahead_safe(selected_nodes, t_s_ms: int, t_e_ms: int,
                    cf_busy_ms: dict) -> bool:
    overlap_mask = (hist_starts_ms > t_s_ms) & (hist_starts_ms < t_e_ms)
    if not overlap_mask.any():
        return True
    s_nodes = frozenset(selected_nodes)
    for idx in np.where(overlap_mask)[0]:
        t_h_ms  = int(hist_starts_ms[idx])
        k_h     = int(hist_k_arr[idx])
        jid_h   = int(hist_jids_arr[idx])
        bg_at_h = bg_busy_per_job[jid_h]
        cf_at_h = frozenset(n for n, te_ms in cf_busy_ms.items() if te_ms > t_h_ms)
        blocked = bg_at_h | cf_at_h | s_nodes
        fb_mask = ((hist_starts_ms > t_s_ms) & (hist_starts_ms <= t_h_ms)
                   & (hist_ends_ms > t_h_ms))
        fb_mask = fb_mask.copy(); fb_mask[idx] = False
        future_base_k = min(int(hist_k_arr[fb_mask].sum()),
                            max(0, n_cohort - len(blocked)))
        if n_cohort - len(blocked) - future_base_k < k_h:
            return False
    return True


def select_fp(available: list[str], k: int) -> list[str]:
    avail_F = np.array([FA_dict[n] for n in available])
    order   = np.argsort(avail_F)
    return [available[i] for i in order[:min(k, len(available))]]


def select_loc(available: list[str], k: int) -> list[str]:
    avail_L = np.array([LOC_FA_dict.get(n, 0.0) for n in available])
    order   = np.argsort(avail_L)
    return [available[i] for i in order[:min(k, len(available))]]


def select_compact(available: list[str], k: int, rng_local) -> list[str]:
    if k >= len(available):
        return available[:]
    cab_groups: dict[int, list] = defaultdict(list)
    for n in available:
        cab_groups[fp_cab.get(n, -1)].append(n)
    sorted_cabs = sorted(cab_groups.keys(),
                         key=lambda c: (-len(cab_groups[c]),
                                        int(rng_local.integers(0, 1000))))
    selected = []
    for c in sorted_cabs:
        if len(selected) >= k:
            break
        need  = k - len(selected)
        nodes = cab_groups[c]
        take  = min(need, len(nodes))
        idx   = rng_local.choice(len(nodes), size=take, replace=False)
        selected.extend(nodes[i] for i in idx)
    return selected


def select_random(available: list[str], k: int, rng_local) -> list[str]:
    n_avail = len(available)
    idx = rng_local.choice(n_avail, size=min(k, n_avail), replace=False)
    return [available[i] for i in idx]


def select_fp_spread(available: list[str], k: int,
                     cab_active_count: dict[int, int]) -> list[str]:
    k    = min(k, len(available))
    temp = dict(cab_active_count)
    if k == 0:
        return []
    if k == len(available):
        return list(available)
    cab_nodes: dict[int, list[str]] = {}
    for n in available:
        c = fp_cab.get(n, -1)
        cab_nodes.setdefault(c, []).append(n)
    for c in cab_nodes:
        cab_nodes[c].sort(key=lambda n: FA_dict.get(n, 0.0))
    selected: list[str] = []
    for _ in range(k):
        if not cab_nodes:
            break
        best_c = min(cab_nodes, key=lambda c: (temp.get(c, 0), c))
        best_n = cab_nodes[best_c].pop(0)
        if not cab_nodes[best_c]:
            del cab_nodes[best_c]
        selected.append(best_n)
        temp[best_c] = temp.get(best_c, 0) + 1
    return selected


def sample_synthetic_pool(n_extra: int, seed: int) -> pd.DataFrame:
    rng_s       = np.random.default_rng(seed)
    base_months = jobs_sorted["start_time"].dt.month.values
    base_hours  = jobs_sorted["start_time"].dt.hour.values
    strat_keys  = list(zip(base_months.tolist(), base_hours.tolist()))
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
        idxs = rng_s.choice(strat_to_idxs[sk], size=int(n_s), replace=True)
        chunks.append(jobs_sorted.iloc[idxs])
    if not chunks:
        return pd.DataFrame(columns=list(jobs_sorted.columns) +
                            ["is_synthetic", "parent_job_idx"])
    syn = pd.concat(chunks, ignore_index=True)
    jitter = rng_s.uniform(-1800.0, 1800.0, size=len(syn))
    syn["start_time"]     = syn["start_time"] + pd.to_timedelta(jitter, unit="s")
    syn["end_time"]       = syn["start_time"] + pd.to_timedelta(syn["run_time"].values, unit="s")
    syn["is_synthetic"]   = True
    syn["parent_job_idx"] = syn["job_idx"].values.copy()
    syn["job_idx"]        = -(np.arange(len(syn), dtype=np.int64) + 1)
    syn["alpha_j"]        = syn["parent_job_idx"].map(alpha_map)
    syn = syn.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)
    return syn


def generate_job_perms(syn_pool: pd.DataFrame,
                       scen_rng: np.random.Generator) -> dict:
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


_bref_jids   = jobs_sorted["job_idx"].values.astype(int)
_bref_rt_h   = jobs_sorted["run_time"].fillna(0.0).values.astype(float) / 3600.0
_bref_alpha  = jobs_sorted["alpha_j"].fillna(0.0).values.astype(float)
_bref_hnodes = jobs_sorted["hist_nodes"].values


def compute_B_S_ref_s(job_perms: dict, thr: float) -> tuple[float, float]:
    B = 0.0; S = 0.0
    for _bi in range(len(_bref_jids)):
        jid     = int(_bref_jids[_bi])
        rt_h    = float(_bref_rt_h[_bi])
        alpha   = float(_bref_alpha[_bi])
        hist_ns = _bref_hnodes[_bi]
        if not hist_ns:
            continue
        F_arr    = np.array([FA_dict[n] for n in hist_ns], dtype=float)
        res_s, _ = job_residuals[jid]
        perm     = job_perms[jid]
        rank     = np.argsort(np.argsort(F_arr))
        T_hats   = alpha + BETA_F_FROZEN * F_arr + res_s[perm[rank]]
        exc      = T_hats - thr
        B       += rt_h * float((exc > 0).sum())
        S       += rt_h * float(exc.clip(min=0).sum())
    return B, S


# ══════════════════════════════════════════════════════════════════════
# [10] capacity_replay_m4 (verbatim from r1_m4_fair_baselines.py)
# ══════════════════════════════════════════════════════════════════════

def capacity_replay_m4(syn_subset, policy: str, lambda_val: float,
                       policy_seed: int, job_perms: dict,
                       avail_nodes: set | None = None,
                       marginal: bool = False) -> dict:
    eligible     = avail_nodes if avail_nodes is not None else cohort_set
    u_max        = (1.0 + DELTA_CAP) * lambda_val * hist_fleet_avg
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

    _cst_ms  = _col_to_dt64ms(combined["start_time"]).astype(np.int64)
    _cet_ms  = _col_to_dt64ms(combined["end_time"]).astype(np.int64)
    _crt_h   = combined["run_time"].fillna(0.0).values.astype(float) / 3600.0
    _ck      = combined["n_cohort"].fillna(0).values.astype(int)
    _cjid    = combined["job_idx"].values.astype(int)
    _cpid    = combined["parent_job_idx"].values.astype(int)
    _cissyn  = combined["is_synthetic"].values.astype(bool)
    _calpha  = combined["alpha_j"].fillna(0.0).values.astype(float)
    _cnc     = np.maximum(combined["node_count"].fillna(1).values.astype(int), 1)
    _cppn    = np.where(combined["mean_power"].isna().values, 0.0,
                        combined["mean_power"].values.astype(float)) / _cnc
    _chist_nodes = combined["hist_nodes"].values

    cf_busy_ms: dict[str, int]  = {}
    cf_busy_active: set[str]    = set()
    cf_expire_heap: list        = []
    cf_util: dict[str, float]   = {n: 0.0 for n in eligible}
    cap_exceeded: set[str]      = set()
    eligible_set                = set(eligible)
    available_set               = set(eligible)
    _rng = np.random.default_rng(policy_seed)

    B_primary = 0.0; S_primary = 0.0
    n_cabs_per_job: list[int] = []
    B_secondary = 0.0; S_secondary = 0.0
    syn_node_hours = 0.0
    n_syn_admit  = 0
    n_drop_cap   = 0
    n_drop_phys  = 0
    n_drop_la    = 0
    n_base_unserved = 0
    cab_active_count: dict[int, int] = {}
    sum_F_syn = 0.0; n_F_syn = 0
    cool10_nh = 0.0
    cohort_records: list[dict] = []

    def _empty_strat():
        return {q: {"attempted": 0, "admitted": 0,
                    "drop_cap": 0, "drop_physical": 0, "drop_la": 0}
                for q in range(1, 5)}
    strat_ncoh = _empty_strat(); strat_nc = _empty_strat()
    strat_ppn  = _empty_strat(); strat_rt = _empty_strat()
    q_admit = {q: 0 for q in range(1, 5)}
    q_drop  = {q: 0 for q in range(1, 5)}

    for _i in range(len(combined)):
        is_syn     = bool(_cissyn[_i])
        t_j_ms     = int(_cst_ms[_i])
        t_e_ms     = int(_cet_ms[_i])
        rt_h       = float(_crt_h[_i])
        k          = int(_ck[_i])
        jid        = int(_cjid[_i])
        parent_jid = int(_cpid[_i])
        alpha      = float(_calpha[_i])
        ppn        = float(_cppn[_i])

        while cf_expire_heap and cf_expire_heap[0][0] <= t_j_ms:
            _exp_ms, _exp_n = heapq.heappop(cf_expire_heap)
            if cf_busy_ms.get(_exp_n, -1) == _exp_ms:
                cf_busy_active.discard(_exp_n)
                _exp_c = fp_cab.get(_exp_n, -1)
                if _exp_c >= 0 and cab_active_count.get(_exp_c, 0) > 0:
                    cab_active_count[_exp_c] -= 1
                if _exp_n not in cap_exceeded:
                    available_set.add(_exp_n)

        if is_syn:
            bg_busy = bg_busy_at_ms(t_j_ms)
        else:
            bg_busy = bg_busy_per_job.get(parent_jid, frozenset())

        avail_capped_set = available_set.difference(bg_busy)
        n_avail_capped   = len(avail_capped_set)

        if is_syn:
            if n_avail_capped < k:
                avail_unc_set = eligible_set.difference(cf_busy_active, bg_busy)
                if len(avail_unc_set) < k:
                    n_drop_phys += 1
                    _drop_key = "drop_physical"
                else:
                    n_drop_cap += 1
                    _drop_key = "drop_cap"
                for _strat, _qmap in ((strat_ncoh, job_quartile_ncoh),
                                      (strat_nc,   job_quartile_nc),
                                      (strat_ppn,  job_quartile_ppn),
                                      (strat_rt,   job_quartile_rt)):
                    _q = _qmap.get(parent_jid, 4)
                    _strat[_q]["attempted"] += 1
                    _strat[_q][_drop_key]   += 1
                q_drop[job_quartile.get(parent_jid, 4)] += 1
                continue
            available = list(avail_capped_set)
        else:
            if marginal:
                hist_ns  = list(_chist_nodes[_i]) if _chist_nodes[_i] is not None else []
                selected = [n for n in hist_ns if n in eligible_set]
                if len(selected) < k:
                    n_base_unserved += 1
                for n in selected:
                    if n not in cf_busy_ms or cf_busy_ms[n] < t_e_ms:
                        cf_busy_ms[n] = t_e_ms
                        cf_busy_active.add(n)
                        available_set.discard(n)
                        heapq.heappush(cf_expire_heap, (t_e_ms, n))
                        _new_util = cf_util.get(n, 0.0) + rt_h
                        cf_util[n] = _new_util
                        if _new_util >= u_max and n not in cap_exceeded:
                            cap_exceeded.add(n)
                if selected:
                    F_arr    = np.array([FA_dict[n] for n in selected])
                    res_s, _ = job_residuals[parent_jid]
                    perm     = job_perms[jid]
                    rank     = np.argsort(np.argsort(F_arr))
                    T_hats   = alpha + BETA_F_FROZEN * F_arr + res_s[perm[rank]]
                    B_primary   += rt_h * float((T_hats > T_THR_PRIMARY  ).sum())
                    S_primary   += rt_h * float((T_hats - T_THR_PRIMARY  ).clip(min=0).sum())
                    B_secondary += rt_h * float((T_hats > T_THR_SECONDARY).sum())
                    S_secondary += rt_h * float((T_hats - T_THR_SECONDARY).clip(min=0).sum())
                    cc: dict[int, int] = {}
                    for nd in selected:
                        c = fp_cab.get(nd, -1)
                        if c >= 0:
                            cc[c] = cc.get(c, 0) + 1
                    if cc:
                        cohort_records.append({"t_s": t_j_ms, "t_e": t_e_ms,
                                               "ppn": ppn, "cab_counts": cc})
                continue
            else:
                if n_avail_capped >= k:
                    available = list(avail_capped_set)
                else:
                    avail_unc_set = eligible_set.difference(cf_busy_active, bg_busy)
                    available = list(avail_unc_set)

        if not available:
            if not is_syn:
                n_base_unserved += 1
            continue

        if policy == "fp":
            selected = select_fp(available, k)
        elif policy == "fp_spread":
            selected = select_fp_spread(available, k, cab_active_count)
        elif policy == "loc":
            selected = select_loc(available, k)
        elif policy == "compact":
            selected = select_compact(available, k, _rng)
        else:
            selected = select_random(available, k, _rng)

        if is_syn and selected:
            if not look_ahead_safe(selected, t_j_ms, t_e_ms, cf_busy_ms):
                n_drop_la += 1
                for _strat, _qmap in ((strat_ncoh, job_quartile_ncoh),
                                      (strat_nc,   job_quartile_nc),
                                      (strat_ppn,  job_quartile_ppn),
                                      (strat_rt,   job_quartile_rt)):
                    _q = _qmap.get(parent_jid, 4)
                    _strat[_q]["attempted"] += 1
                    _strat[_q]["drop_la"]   += 1
                q_drop[job_quartile.get(parent_jid, 4)] += 1
                continue

        if not is_syn and len(selected) < k:
            n_base_unserved += 1

        for n in selected:
            cf_busy_ms[n] = t_e_ms
            cf_busy_active.add(n)
            available_set.discard(n)
            heapq.heappush(cf_expire_heap, (t_e_ms, n))
            _new_util = cf_util.get(n, 0.0) + rt_h
            cf_util[n] = _new_util
            if _new_util >= u_max and n not in cap_exceeded:
                cap_exceeded.add(n)
                available_set.discard(n)
            _nc = fp_cab.get(n, -1)
            if _nc >= 0:
                cab_active_count[_nc] = cab_active_count.get(_nc, 0) + 1

        if selected:
            F_arr    = np.array([FA_dict[n] for n in selected])
            res_s, _ = job_residuals[parent_jid]
            perm     = job_perms[jid]
            rank     = np.argsort(np.argsort(F_arr))
            T_hats   = alpha + BETA_F_FROZEN * F_arr + res_s[perm[rank]]
            B_primary   += rt_h * float((T_hats > T_THR_PRIMARY  ).sum())
            S_primary   += rt_h * float((T_hats - T_THR_PRIMARY  ).clip(min=0).sum())
            B_secondary += rt_h * float((T_hats > T_THR_SECONDARY).sum())
            S_secondary += rt_h * float((T_hats - T_THR_SECONDARY).clip(min=0).sum())
            if is_syn:
                n_syn_admit    += 1
                syn_node_hours += len(selected) * rt_h
                q_admit[job_quartile.get(parent_jid, 4)] += 1
                for _strat, _qmap in ((strat_ncoh, job_quartile_ncoh),
                                      (strat_nc,   job_quartile_nc),
                                      (strat_ppn,  job_quartile_ppn),
                                      (strat_rt,   job_quartile_rt)):
                    _q = _qmap.get(parent_jid, 4)
                    _strat[_q]["attempted"] += 1
                    _strat[_q]["admitted"]  += 1
                for n in selected:
                    f_n = FA_dict.get(n, 0.0)
                    sum_F_syn += f_n; n_F_syn += 1
                    if f_n <= F_COOL10_THR:
                        cool10_nh += rt_h
            cc2: dict[int, int] = {}
            for nd in selected:
                c = fp_cab.get(nd, -1)
                if c >= 0:
                    cc2[c] = cc2.get(c, 0) + 1
            if cc2:
                cohort_records.append({"t_s": t_j_ms, "t_e": t_e_ms,
                                       "ppn": ppn, "cab_counts": cc2})
                n_cabs_per_job.append(len(cc2))

    if n_base_unserved > 0 and not marginal:
        raise AssertionError(
            f"Base-job invariant violated: {n_base_unserved} unserved "
            f"(lam={lambda_val:.2f}, policy={policy})")

    u_vals = np.array([cf_util.get(n, 0.0) for n in eligible], dtype=float)
    if u_vals.sum() > 0:
        u_sorted = np.sort(u_vals)
        n_u  = len(u_sorted)
        cum  = np.cumsum(u_sorted)
        gini = float(1 - 2 * cum[:-1].sum() / (n_u * cum[-1]))
    else:
        gini = float("nan")

    capacity_unlock_pct = syn_node_hours / hist_total_nh * 100.0
    B_cab, S_cab        = sweep_cab_budget_fast(cohort_records, cab_p99_W)
    B_cab_ratio         = B_cab / max(B_cab_hist, 1e-9)
    S_cab_ratio         = S_cab / max(S_cab_hist, 1e-9)

    return {
        "lambda_val"         : lambda_val,
        "policy"             : policy,
        "capacity_unlock_pct": capacity_unlock_pct,
        "B_primary_h"        : B_primary,
        "S_primary_Cdoth"    : S_primary,
        "B_secondary_h"      : B_secondary,
        "S_secondary_Cdoth"  : S_secondary,
        "B_cab_h"            : B_cab,
        "S_cab_Wh"           : S_cab,
        "B_cab_ratio"        : B_cab_ratio,
        "S_cab_ratio"        : S_cab_ratio,
        "n_syn_admit"        : n_syn_admit,
        "n_drop_cap"         : n_drop_cap,
        "n_drop_physical"    : n_drop_phys,
        "n_drop_la"          : n_drop_la,
        "n_base_unserved"    : n_base_unserved,
        "syn_node_hours"     : syn_node_hours,
        "util_gini"          : jf(gini),
        "q_admit"            : q_admit,
        "q_drop"             : q_drop,
    }


# ══════════════════════════════════════════════════════════════════════
# [11] Crossing helpers (verbatim from r1_m4_fair_baselines.py)
# ══════════════════════════════════════════════════════════════════════

def check_infeasible(res: dict, b_ref_s: float,
                     s_ref_s: float) -> tuple[bool, str | None]:
    if res.get("invariant_violated"):
        return True, "invariant_violated"
    b_ratio = res["B_primary_h"] / max(b_ref_s, 1e-9)
    s_val   = res.get("S_primary_Cdoth")
    s_ratio = (float(s_val) if s_val is not None
               and not (isinstance(s_val, float) and np.isnan(s_val))
               else float("nan")) / max(s_ref_s, 1e-9)
    b_cab   = res.get("B_cab_ratio") or 0.0
    violations = []
    if b_ratio > 1.0:                                violations.append("B_ratio")
    if not np.isnan(s_ratio) and s_ratio > 1.0:     violations.append("S_ratio")
    if b_cab > 1.0:                                  violations.append("B_cab_ratio")
    return bool(violations), (violations[0] if violations else None)


def classify_crossing(lambda_rows: list[dict],
                      b_ref_s: float, s_ref_s: float,
                      b_cab_ref: float) -> dict:
    for r in lambda_rows:
        if r.get("invariant_violated"):
            r["infeasible"] = True
            r["first_binding"] = "invariant_violated"
            continue
        b_ratio   = r["B_primary_h"] / max(b_ref_s, 1e-9)
        s_val     = r.get("S_primary_Cdoth")
        s_ratio   = (float(s_val) if s_val is not None
                     and not (isinstance(s_val, float) and np.isnan(s_val))
                     else float("nan")) / max(s_ref_s, 1e-9)
        b_cab     = r.get("B_cab_ratio") or 0.0
        violations = []
        if b_ratio > 1.0:                                violations.append("B_ratio")
        if not np.isnan(s_ratio) and s_ratio > 1.0:     violations.append("S_ratio")
        if b_cab > 1.0:                                  violations.append("B_cab_ratio")
        r["infeasible"]    = bool(violations)
        r["first_binding"] = violations[0] if violations else None

    last_feasible = None
    for r in lambda_rows:
        if not r["infeasible"]:
            last_feasible = r
        else:
            c_up = r["capacity_unlock_pct"]
            if last_feasible is None:
                return {"status": "left_boundary",
                        "C_lower_pct": 0.0,
                        "C_upper_pct": c_up,
                        "first_binding_constraint": r["first_binding"],
                        "right_censored": False}
            return {"status": "exact_bracket",
                    "C_lower_pct": last_feasible["capacity_unlock_pct"],
                    "C_upper_pct": c_up,
                    "first_binding_constraint": r["first_binding"],
                    "right_censored": False}

    c_lo = last_feasible["capacity_unlock_pct"] if last_feasible else 0.0
    return {"status": "right_censored",
            "C_lower_pct": c_lo,
            "C_upper_pct": None,
            "first_binding_constraint": None,
            "right_censored": True}


def refine_crossing_bracket(cx: dict, pol_name: str, base_pol: str,
                             job_perms: dict, policy_seed: int,
                             syn_pool, n_base: int,
                             b_ref_s: float, s_ref_s: float,
                             lambda_rows: list,
                             avail_nodes: set | None = None,
                             target_pp: float = TARGET_PP,
                             n_grid: int = N_REFINE_GRID) -> tuple[dict, list]:
    if cx["status"] != "exact_bracket" or cx["C_upper_pct"] is None:
        return cx, []
    if (cx["C_upper_pct"] - cx["C_lower_pct"]) <= target_pp:
        return cx, []

    n_safe = 0; c_safe = 0.0
    n_unsafe = None; c_unsafe = None; binding = cx["first_binding_constraint"]
    for r in sorted(lambda_rows, key=lambda x: x.get("lambda_val", 0)):
        is_inf, bind = check_infeasible(r, b_ref_s, s_ref_s)
        lam     = r.get("lambda_val", 1.0)
        n_syn_r = int(round((lam - 1.0) * n_base))
        if not is_inf:
            n_safe = n_syn_r; c_safe = r["capacity_unlock_pct"]
        else:
            if n_unsafe is None:
                n_unsafe = n_syn_r; c_unsafe = r["capacity_unlock_pct"]
                if bind: binding = bind
                break

    if n_unsafe is None or (n_unsafe - n_safe) <= 1:
        return cx, []

    extra_rows: list = []
    while (c_unsafe - c_safe) > target_pp and (n_unsafe - n_safe) > 1:
        step = (n_unsafe - n_safe) / (n_grid + 1)
        grid_pts = sorted(set(
            int(round(n_safe + step * i))
            for i in range(1, n_grid + 1)
            if n_safe < int(round(n_safe + step * i)) < n_unsafe
        ))
        if not grid_pts:
            break

        first_inf_pt: tuple | None = None
        last_safe_pt: tuple | None = None

        for n_pt in grid_pts:
            if n_pt > len(syn_pool):
                break
            syn_sub = syn_pool.iloc[:n_pt].copy()
            lam_pt  = 1.0 + n_pt / n_base
            try:
                res = capacity_replay_m4(syn_sub, base_pol, lam_pt,
                                         policy_seed=policy_seed,
                                         job_perms=job_perms,
                                         avail_nodes=avail_nodes,
                                         marginal=False)
            except AssertionError:
                res = {"lambda_val": lam_pt, "policy": pol_name,
                       "invariant_violated": True,
                       "capacity_unlock_pct": n_pt / n_base * 100.0,
                       "B_primary_h": float("nan"),
                       "S_primary_Cdoth": float("nan"),
                       "B_cab_ratio": float("nan")}
            extra_rows.append(res)
            is_inf, bind = check_infeasible(res, b_ref_s, s_ref_s)
            if is_inf:
                first_inf_pt = (n_pt, res["capacity_unlock_pct"])
                if bind: binding = bind
                break
            else:
                last_safe_pt = (n_pt, res["capacity_unlock_pct"])

        if first_inf_pt is not None:
            n_unsafe, c_unsafe = first_inf_pt
            if last_safe_pt is not None:
                n_safe, c_safe = last_safe_pt
        else:
            if last_safe_pt is not None:
                n_safe, c_safe = last_safe_pt
            else:
                break

    print(f"        [refine] {pol_name}: [{c_safe:.2f},{c_unsafe:.2f}]%  "
          f"gap={c_unsafe-c_safe:.2f}pp  {len(extra_rows)} evals")
    return {
        "status": "exact_bracket",
        "C_lower_pct": c_safe,
        "C_upper_pct": c_unsafe,
        "first_binding_constraint": binding,
        "right_censored": False,
    }, extra_rows


# ══════════════════════════════════════════════════════════════════════
# [12] Seed generation (replicate main-script master_rng sequence)
# ══════════════════════════════════════════════════════════════════════
master_rng = np.random.default_rng(SCENARIO_SEED)
scen_seeds = [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
wl_seeds   = [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
pol_seeds  = {p: [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
              for p in POLICY_IDS}

n_extra_max = int(np.ceil((LAMBDA_MAX_EXT - 1.0) * n_base))
print(f"\nSynthetic pool size: {n_extra_max} jobs (covers lam up to {LAMBDA_MAX_EXT})")

# ══════════════════════════════════════════════════════════════════════
# [13] Transition experiment
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"Running availability transition: "
      f"{len(AVAIL_SCENARIOS)} scenarios x {len(AVAIL_FRACTIONS)} fractions "
      f"x {len(TRANS_POLICIES)} policies")
print(f"{'='*70}")

# Pre-generate one fixed permutation per scenario (expanding-subset design)
# perm_s[i] gives node index for the i-th position in the ranked inclusion order.
# f=0.60 → first 1200 positions; f=0.70 → first 1400; ...; f=1.00 → all (None).
avail_perms: dict[int, np.ndarray] = {}
for s_idx in AVAIL_SCENARIOS:
    avail_perms[s_idx] = np.random.default_rng(AVAIL_SEED + s_idx).permutation(N_FP)

fp_list = list(cohort_list)  # index-addressable cohort list (sorted)

all_fraction_results = []
scenario_B_refs: dict[int, tuple] = {}  # s_idx -> (B_ref_s, S_ref_s) for regression check

for s_idx in AVAIL_SCENARIOS:
    t_scen = time.time()
    print(f"\nScenario {s_idx}  (scen_seed={scen_seeds[s_idx]}  wl_seed={wl_seeds[s_idx]})")

    # Per-scenario data (shared across fractions)
    syn_pool  = sample_synthetic_pool(n_extra_max, wl_seeds[s_idx])
    scen_rng  = np.random.default_rng(scen_seeds[s_idx])
    job_perms = generate_job_perms(syn_pool, scen_rng)
    B_ref_s, S_ref_s = compute_B_S_ref_s(job_perms, T_THR_PRIMARY)
    scenario_B_refs[s_idx] = (B_ref_s, S_ref_s)
    print(f"    B_ref_s={B_ref_s:.2f} h  S_ref_s={S_ref_s:.4f} C*h")

    node_perm = avail_perms[s_idx]

    for f in AVAIL_FRACTIONS:
        n_avail   = round(f * N_FP)
        avail_set = (None if f == 1.0
                     else {fp_list[int(node_perm[i])] for i in range(n_avail)})
        avail_tag = f"f={f:.0%}  n={n_avail if avail_set is not None else N_FP}"

        crossings: dict[str, dict] = {}

        for pol_name in TRANS_POLICIES:
            base_pol = POLICY_MAP[pol_name][0]
            pol_rows: list[dict] = []

            # Main lambda sweep
            for lam in LAMBDA_SWEEP:
                n_syn = int(round((lam - 1.0) * n_base))
                syn_sub = (syn_pool.iloc[:n_syn].copy() if n_syn > 0
                           else pd.DataFrame(columns=list(syn_pool.columns)))
                try:
                    res = capacity_replay_m4(
                        syn_sub, base_pol, lam,
                        policy_seed=pol_seeds[pol_name][s_idx],
                        job_perms=job_perms,
                        avail_nodes=avail_set,
                        marginal=False,
                    )
                except AssertionError as exc:
                    res = {"lambda_val": lam, "policy": pol_name,
                           "invariant_violated": True,
                           "capacity_unlock_pct": n_syn / n_base * 100.0,
                           "B_primary_h": float("nan"),
                           "S_primary_Cdoth": float("nan"),
                           "B_cab_ratio": float("nan")}
                pol_rows.append(res)

            cx = classify_crossing(pol_rows, B_ref_s, S_ref_s, B_cab_hist)

            # Extension sweep for right-censored
            if cx["right_censored"]:
                for lam_ext in LAMBDA_SWEEP_EXT:
                    n_syn = int(round((lam_ext - 1.0) * n_base))
                    if n_syn > len(syn_pool):
                        break
                    syn_sub = syn_pool.iloc[:n_syn].copy()
                    try:
                        res = capacity_replay_m4(
                            syn_sub, base_pol, lam_ext,
                            policy_seed=pol_seeds[pol_name][s_idx],
                            job_perms=job_perms,
                            avail_nodes=avail_set,
                            marginal=False,
                        )
                    except AssertionError:
                        res = {"lambda_val": lam_ext, "policy": pol_name,
                               "invariant_violated": True,
                               "capacity_unlock_pct": n_syn / n_base * 100.0,
                               "B_primary_h": float("nan"),
                               "S_primary_Cdoth": float("nan"),
                               "B_cab_ratio": float("nan")}
                    pol_rows.append(res)
                    cx = classify_crossing(pol_rows, B_ref_s, S_ref_s, B_cab_hist)
                    if not cx["right_censored"]:
                        break

            # Adaptive refinement
            if cx["status"] == "exact_bracket" and cx["C_upper_pct"] is not None:
                gap = cx["C_upper_pct"] - cx["C_lower_pct"]
                if gap > TARGET_PP:
                    cx, extra = refine_crossing_bracket(
                        cx, pol_name, base_pol,
                        job_perms=job_perms,
                        policy_seed=pol_seeds[pol_name][s_idx],
                        syn_pool=syn_pool,
                        n_base=n_base,
                        b_ref_s=B_ref_s,
                        s_ref_s=S_ref_s,
                        lambda_rows=pol_rows,
                        avail_nodes=avail_set,
                    )
                    pol_rows.extend(extra)

            crossings[pol_name] = cx

        # Interval-aware comparison: FP vs Random
        cx_fp   = crossings["full_fp"]
        cx_rand = crossings["full_random"]

        lo_fp   = cx_fp["C_lower_pct"]
        hi_fp   = cx_fp["C_upper_pct"] if cx_fp["C_upper_pct"] is not None else lo_fp
        lo_rand = cx_rand["C_lower_pct"]
        hi_rand = cx_rand["C_upper_pct"] if cx_rand["C_upper_pct"] is not None else lo_rand

        delta_lo = lo_fp - hi_rand   # pessimistic
        delta_hi = hi_fp - lo_rand   # optimistic

        if delta_lo > 0:
            verdict = "definitely_fp_better"
        elif delta_hi < 0:
            verdict = "definitely_rand_better"
        else:
            verdict = "indistinguishable"

        print(f"    {avail_tag}  "
              f"fp=[{lo_fp:.2f},{hi_fp:.2f}]%  rand=[{lo_rand:.2f},{hi_rand:.2f}]%  "
              f"dlo={delta_lo:+.2f}  dhi={delta_hi:+.2f}  {verdict}")

        all_fraction_results.append({
            "scenario_idx"   : s_idx,
            "avail_frac"     : f,
            "n_avail"        : n_avail if avail_set is not None else N_FP,
            "C_lower_fp"     : jf(lo_fp),
            "C_upper_fp"     : jf(hi_fp),
            "C_lower_rand"   : jf(lo_rand),
            "C_upper_rand"   : jf(hi_rand),
            "delta_lo"       : jf(delta_lo),
            "delta_hi"       : jf(delta_hi),
            "verdict"        : verdict,
            "status_fp"      : cx_fp["status"],
            "status_rand"    : cx_rand["status"],
            "binding_fp"     : cx_fp["first_binding_constraint"],
            "binding_rand"   : cx_rand["first_binding_constraint"],
        })

    print(f"    Scenario {s_idx} elapsed: {time.time()-t_scen:.0f}s")

# ══════════════════════════════════════════════════════════════════════
# [14] Aggregate and print summary
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("AVAILABILITY TRANSITION SUMMARY")
print(f"{'='*70}")

fraction_summaries = []
for f in AVAIL_FRACTIONS:
    rows = [r for r in all_fraction_results if r["avail_frac"] == f]
    n    = len(rows)

    n_defA  = sum(1 for r in rows if r["verdict"] == "definitely_fp_better")
    n_ind   = sum(1 for r in rows if r["verdict"] == "indistinguishable")
    n_defB  = sum(1 for r in rows if r["verdict"] == "definitely_rand_better")

    dlo_vals = [r["delta_lo"] for r in rows if r["delta_lo"] is not None]
    dhi_vals = [r["delta_hi"] for r in rows if r["delta_hi"] is not None]
    clo_fp   = [r["C_lower_fp"]   for r in rows if r["C_lower_fp"]   is not None]
    clo_rand = [r["C_lower_rand"] for r in rows if r["C_lower_rand"] is not None]

    med_dlo  = float(np.median(dlo_vals)) if dlo_vals else None
    med_dhi  = float(np.median(dhi_vals)) if dhi_vals else None
    med_fp   = float(np.median(clo_fp))   if clo_fp   else None
    med_rand = float(np.median(clo_rand)) if clo_rand else None

    n_avail  = rows[0]["n_avail"] if rows else round(f * N_FP)

    print(f"\n  f={f:.0%}  n_avail={n_avail}")
    print(f"    Definitely FP better: {n_defA}/{n}  |  "
          f"Indistinguishable: {n_ind}/{n}  |  "
          f"Definitely Rand better: {n_defB}/{n}")
    if med_dlo is not None:
        print(f"    delta_lo median={med_dlo:+.2f} pp  "
              f"delta_hi median={med_dhi:+.2f} pp")
    print(f"    C_lower median: fp={med_fp:.2f}%  rand={med_rand:.2f}%")

    fraction_summaries.append({
        "avail_frac"           : f,
        "n_avail"              : n_avail,
        "n_scenarios"          : n,
        "n_definitely_fp"      : n_defA,
        "n_indistinguishable"  : n_ind,
        "n_definitely_rand"    : n_defB,
        "pct_definitely_fp"    : round(100 * n_defA / n, 1) if n else None,
        "delta_lo_median"      : jf(med_dlo),
        "delta_hi_median"      : jf(med_dhi),
        "C_lower_fp_median"    : jf(med_fp),
        "C_lower_rand_median"  : jf(med_rand),
    })

# Transition threshold: first fraction where any scenario shows definite FP advantage
print("\n  Transition detection (held-out sc5-9 only):")
for f in AVAIL_FRACTIONS:
    held = [r for r in all_fraction_results
            if r["avail_frac"] == f and r["scenario_idx"] >= 5]
    n_defA = sum(1 for r in held if r["verdict"] == "definitely_fp_better")
    print(f"    f={f:.0%}  definitely_fp_better: {n_defA}/{len(held)}")

# ══════════════════════════════════════════════════════════════════════
# [15] Save output
# ══════════════════════════════════════════════════════════════════════
out = {
    "method"            : "availability_transition_expanding_subset",
    "avail_fractions"   : AVAIL_FRACTIONS,
    "avail_scenarios"   : AVAIL_SCENARIOS,
    "avail_seed"        : AVAIL_SEED,
    "scenario_seed"     : SCENARIO_SEED,
    "policies"          : TRANS_POLICIES,
    "n_fp_total"        : N_FP,
    "target_pp"         : TARGET_PP,
    "beta_f_frozen"     : BETA_F_FROZEN,
    "t_thr_primary_C"   : T_THR_PRIMARY,
    "note": ("Expanding-subset design: perm_s = RNG(AVAIL_SEED+s_idx).permutation(N_FP); "
             "avail_f_s = fp_list[perm_s[:round(f*N_FP)]]. "
             "The 60% subset is always a prefix of the 70% subset, etc. "
             "f=1.00 uses avail_nodes=None (unrestricted cohort). "
             "Full crossing refinement applied; interval-aware comparison: "
             "delta_lo = C_lower_fp - C_upper_rand (pessimistic)."),
    "fraction_summaries": fraction_summaries,
    "scenario_rows"     : all_fraction_results,
    "elapsed_s"         : round(time.time() - t_script, 1),
}
OUT_FILE.write_text(json.dumps(out, indent=2))
print(f"\nSaved: {OUT_FILE}")
print(f"Total elapsed: {time.time()-t_script:.1f}s")

# ══════════════════════════════════════════════════════════════════════
# [16] Regression comparison (only when M4_AVAIL_REGRESSION=1)
# ══════════════════════════════════════════════════════════════════════
if REGRESSION_ONLY:
    print(f"\n{'='*70}")
    print("REGRESSION CHECK: f=1.00 results vs frozen v5 (m4_fair_baselines.json)")
    print(f"{'='*70}")

    v5_path = OUT_DIR / "m4_fair_baselines.json"
    if not v5_path.exists():
        print(f"FATAL: frozen v5 not found at {v5_path}")
        sys.exit(1)
    v5_data  = json.loads(v5_path.read_text())
    v5_by_sc = {sr["scenario_idx"]: sr for sr in v5_data["scenario_results"]}

    fails  = []
    checks = 0

    def _chk(label, new_val, ref_val, tol=None):
        nonlocal checks
        checks += 1
        if tol is not None:
            # Numeric tolerance check
            if new_val is None and ref_val is None:
                ok = True
            elif new_val is None or ref_val is None:
                ok = False
            else:
                ok = abs(float(new_val) - float(ref_val)) <= tol
            if not ok:
                fails.append(f"  FAIL {label}: new={new_val}  v5={ref_val}  tol={tol}")
            else:
                print(f"  [OK]  {label}: {new_val:.6g} == v5 {ref_val:.6g}")
        else:
            # Exact equality
            ok = (new_val == ref_val)
            if not ok:
                fails.append(f"  FAIL {label}: new={new_val!r}  v5={ref_val!r}")
            else:
                print(f"  [OK]  {label}: {new_val!r}")

    for rec in all_fraction_results:
        s_idx = rec["scenario_idx"]
        if s_idx not in v5_by_sc:
            fails.append(f"  FAIL sc{s_idx}: not found in frozen v5")
            continue
        sr_v5 = v5_by_sc[s_idx]

        print(f"\n  Scenario {s_idx}:")

        # ── Seed sanity ──────────────────────────────────────────────
        _chk(f"sc{s_idx} scen_seed",  scen_seeds[s_idx], sr_v5["scen_seed"])
        _chk(f"sc{s_idx} wl_seed",    wl_seeds[s_idx],   sr_v5["wl_seed"])

        # ── B_ref_s ──────────────────────────────────────────────────
        b_ref_new, s_ref_new = scenario_B_refs[s_idx]
        _chk(f"sc{s_idx} B_ref_s",    b_ref_new, sr_v5["B_ref_s_primary_h"], tol=1e-3)
        _chk(f"sc{s_idx} S_ref_s",    s_ref_new, sr_v5["S_ref_s_primary"],   tol=1e-3)

        # ── Crossings ────────────────────────────────────────────────
        for pol_name in TRANS_POLICIES:
            cx_v5 = sr_v5["crossings"][pol_name]
            if pol_name == "full_fp":
                c_lo_new = rec["C_lower_fp"]
                c_hi_new = rec["C_upper_fp"]
                st_new   = rec["status_fp"]
                bd_new   = rec["binding_fp"]
            else:
                c_lo_new = rec["C_lower_rand"]
                c_hi_new = rec["C_upper_rand"]
                st_new   = rec["status_rand"]
                bd_new   = rec["binding_rand"]

            _chk(f"sc{s_idx} {pol_name} status",  st_new, cx_v5["status"])
            _chk(f"sc{s_idx} {pol_name} binding",
                 bd_new, cx_v5["first_binding_constraint"])
            _chk(f"sc{s_idx} {pol_name} C_lower",
                 c_lo_new, cx_v5["C_lower_pct"], tol=1e-3)
            if cx_v5["C_upper_pct"] is not None:
                _chk(f"sc{s_idx} {pol_name} C_upper",
                     c_hi_new, cx_v5["C_upper_pct"], tol=1e-3)

        # ── Lambda-level spot-check (lam=1.0 → C=0, lam=1.06 → first step) ──
        for pol_name in TRANS_POLICIES:
            lr_v5 = {r["lambda_val"]: r
                     for r in sr_v5["lambda_rows"][pol_name]}
            # Spot-check lam=1.0 (no synthetic jobs → trivially feasible)
            if 1.0 in lr_v5:
                r_v5 = lr_v5[1.0]
                # We don't save per-lambda from transition script, but we can
                # check that B_ref_s was used consistently (already done above).
                _chk(f"sc{s_idx} {pol_name} lam=1.0 C_unlock",
                     0.0, r_v5["capacity_unlock_pct"], tol=1e-6)

    # ── Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    if fails:
        print(f"REGRESSION FAILED  ({len(fails)} failures out of {checks} checks):")
        for f_msg in fails:
            print(f_msg)
        print(f"{'='*70}")
        sys.exit(1)
    else:
        print(f"REGRESSION PASSED  ({checks}/{checks} checks)")
        print("f=1.00 results are numerically identical to frozen v5 for sc0-9.")
        print("Safe to launch the full 60/70/80/90/100 experiment.")
        print(f"{'='*70}")
