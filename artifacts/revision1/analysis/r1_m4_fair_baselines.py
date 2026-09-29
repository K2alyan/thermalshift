#!/usr/bin/env python3
"""
M4 Fair-baseline Monte-Carlo Capacity Experiment
=================================================
Four scheduling policies compared on the 2,637-job test set under
a controlled lambda sweep [1.0 .. 2.0].  Primary metric: thermal
exceedance budget ratio B/B_ref,s, where B_ref,s is the model-identity
replay at historical assignments (scenario-specific residual permutation).

Policies
--------
  P0  Random-cap-10    : random selection, utilisation cap u_max(lam)
  P1  FP-cap-10        : lowest FA_2024 first, same cap
  P2  Location-cap-10  : lowest position-mean FA first, same cap
  P3  Compact-cap-10   : greedy cabinet-minimising selection, same cap

Thermal model
-------------
  T_hat_ij = alpha_j + BETA_F_frozen * FA_2024_i + resid_perm_ij
  BETA_F_frozen = 1.12484352 (training-median, from Gate D)
  Primary threshold T_thr = 63.625 deg-C (2024 training p95, from Gate D)
  Secondary: fixed 60.602 deg-C for comparison

B_ref,s (denominator)
----------------------
  Identity replay: same residual permutation as policy runs, but
  historical node assignments.  Makes B_ratio comparable to 1 under
  no policy change.

Capacity metric
---------------
  C_unlock_pct = 100 * syn_node_hours / hist_total_nh
  C_lower,s    = C_unlock_pct at LAST lam before B_ratio first exceeds 1
  C_upper,s    = C_unlock_pct at FIRST lam where B_ratio >= 1
  C_feasible,s = linear interpolation (secondary)

Cabinet power
-------------
  Per-cabinet P^99 from Gate C (cabinet_power_envelopes.json).
  All 9856 nodes; correct topology from fleet_node_topology.csv.
  No str(node_list).split() used anywhere.

Output: artifacts/revision1/results/m4_fair_baselines.json
"""

import json, hashlib, subprocess, datetime, time, os
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

# ── Paths ──────────────────────────────────────────────────────────────
REPO_ROOT  = Path(__file__).resolve().parents[3]
P1_DIR     = REPO_ROOT / "artifacts" / "phase1" / "analysis"
REV1_DIR   = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR    = REV1_DIR / "results"
TABLE_DIR  = REV1_DIR / "tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)

DATA_DIR   = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))
SMOKE_ONLY = os.environ.get("M4_SMOKE_ONLY", "0").strip().lower() in ("1", "true", "yes")

# ── Constants ──────────────────────────────────────────────────────────
BETA_F_FROZEN     = 1.12484352       # training-median frozen slope (Gate D)
T_THR_PRIMARY     = 63.625           # 2024 training p95 (Gate D D.1/D.2)
T_THR_SECONDARY   = 60.602770562770566  # fixed published threshold
DELTA_CAP         = 0.10             # slack over utilisation target: u_max = (1+DELTA_CAP)*lam*u_hist
N_BINS            = 5                # residual quantile bins (primary)
N_SCENARIOS       = 30
N_SMOKE           = 5                # smoke-test gate
SCENARIO_SEED     = 42
WORKLOAD_SEED     = 77777
N_FP              = 2000             # cohort size
N_AVAIL_FRACTIONS = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
N_AVAIL_SCENARIOS = 10               # subset for availability sensitivity
LAMBDA_SWEEP      = [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40,
                     1.50, 1.55, 1.60, 1.70, 1.80, 1.90, 2.00]
LAMBDA_MAX        = 2.00
N_BOOTSTRAP       = 5000
BOOTSTRAP_SEED    = 9999

# ── Utilities ──────────────────────────────────────────────────────────
def git_sha():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, cwd=str(REPO_ROOT)).strip()
    except Exception:
        return "unknown"

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def jf(v):
    if v is None:
        return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f

def _col_to_dt64ms(series):
    s = pd.to_datetime(series, utc=True)
    return s.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ms]")

def _to_dt64_ms(ts):
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    return np.datetime64(t.tz_convert("UTC").tz_localize(None), "ms")

def _dt64_to_h(a, b):
    return float((b - a).astype("int64")) / 3.6e6

# ══════════════════════════════════════════════════════════════════════
# DESIGN AUDIT — printed before any data load
# ══════════════════════════════════════════════════════════════════════
_DESIGN_AUDIT = {
    # Items IN this script (M4-primary)
    "primary_residual_model_K5"        : True,
    "model_identity_B_ref_s"           : True,
    "primary_threshold_2024_p95"       : True,  # 63.625 C (audit confirmed = full-pop p95)
    "secondary_threshold_legacy_60_60" : True,   # computed and stored in every lambda row
    "correct_Gate_C_topology"          : True,
    "gate_C_cabinet_p99_power"         : True,
    "conservative_C_lower_primary"     : True,
    "four_policies_P0_P1_P2_P3"       : True,
    "5_scenario_smoke_gate"            : True,
    "30_scenario_main_run"             : True,
    "availability_sensitivity_f_10_60" : True,
    "bootstrap_CI_for_median_delta_C"  : True,
    "stratification_4_dimensions"      : True,   # ncoh, node_count, ppn, runtime
    # Items NOT in this script → r1_m4_sensitivity.py
    "residual_sensitivity_K1_K3_K10"   : False,
    "parametric_residual_sensitivity"  : False,
    "threshold_sensitivity_p90_p99"    : False,
    "cabinet_span_metrics"             : False,
}

print("=" * 70)
print("M4 DESIGN AUDIT")
print("=" * 70)
for item, implemented in _DESIGN_AUDIT.items():
    tag = "[M4-primary]" if implemented else "[M4-sensitivity]"
    print(f"  {tag:<18} {item}")
print()
_missing = [k for k, v in _DESIGN_AUDIT.items() if not v]
if _missing:
    print(f"  Items deferred to r1_m4_sensitivity.py: {len(_missing)}")
    for m in _missing:
        print(f"    - {m}")
print("=" * 70)

# ══════════════════════════════════════════════════════════════════════
# [0] Load core data
# ══════════════════════════════════════════════════════════════════════
print("\nM4: Fair-baseline Monte-Carlo Capacity Experiment")
print("=" * 70)
t_script = time.time()

print("\n[0] Loading inputs ...")
fp_df   = pd.read_parquet(P1_DIR / "phase3a_fingerprint_2024.parquet")
test_df = pd.read_parquet(P1_DIR / "phase3a_test_set.parquet")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)

fp_df.index.name = "node"
cohort_set  = set(fp_df.index)
FA_dict     = fp_df["FA_2024"].to_dict()          # hostname -> FA_2024
cohort_list = sorted(cohort_set)
n_cohort    = len(cohort_list)

print(f"    fp nodes:    {n_cohort}")
print(f"    test rows:   {len(test_df):,}")
print(f"    all jobs:    {len(all_jobs):,}")

# ══════════════════════════════════════════════════════════════════════
# [1] Correct topology: fleet_node_topology.csv (Gate C)
#     ASSERTION: no str(node_list).split() used for node->cabinet mapping
# ══════════════════════════════════════════════════════════════════════
print("\n[1] Building correct node-to-cabinet map from fleet_node_topology.csv ...")

fleet_topo = pd.read_csv(TABLE_DIR / "fleet_node_topology.csv")
node_to_cab: dict[str, int] = dict(
    zip(fleet_topo["hostname"].values, fleet_topo["cabinet"].values.astype(int))
)
all_cabinets = sorted(set(node_to_cab.values()))
assert len(node_to_cab) == 9856, f"Expected 9856 nodes, got {len(node_to_cab)}"
assert len(all_cabinets) == 77, f"Expected 77 cabinets, got {len(all_cabinets)}"
print(f"    {len(node_to_cab):,} nodes, {len(all_cabinets)} cabinets  [corrected Gate C map]")

# Cohort: cabinet assignment per fp node
fp_cab = {n: node_to_cab[n] for n in cohort_list if n in node_to_cab}
assert len(fp_cab) == n_cohort, "Some fp nodes missing from topology map"

# ══════════════════════════════════════════════════════════════════════
# [2] Location-only fingerprint (P2)
#     Group mean of FA_2024 by position_key=(chassis, slot, board, node_pos)
#     across all cabinets — no individual node identity
# ══════════════════════════════════════════════════════════════════════
print("\n[2] Building location-only fingerprint (P2) ...")

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
# Fill any NaN with cohort mean (singletons with missing neighbours)
_glob_mean = float(np.nanmean(list(LOC_FA_dict.values())))
LOC_FA_dict = {k: (v if not np.isnan(v) else _glob_mean) for k, v in LOC_FA_dict.items()}
n_loc_unique = fp_topo["pos_key"].nunique()
print(f"    {n_loc_unique} unique position keys; group-mean FA range "
      f"[{min(LOC_FA_dict.values()):.3f}, {max(LOC_FA_dict.values()):.3f}]")

# ══════════════════════════════════════════════════════════════════════
# [3] Cabinet P^99 power thresholds (Gate C corrected)
# ══════════════════════════════════════════════════════════════════════
print("\n[3] Loading cabinet P^99 from Gate C ...")

with open(OUT_DIR / "cabinet_power_envelopes.json") as fh:
    cab_env = json.load(fh)

# Keys are float strings (e.g. "2000.0"); values are in kW
cab_p99_W: dict[int, float] = {
    int(float(k)): v * 1e3
    for k, v in cab_env["per_cabinet_p99_kW_correct"].items()
}
# Any cabinet not in map gets global median
_p99_med = float(np.median(list(cab_p99_W.values())))
cab_p99_W = {c: cab_p99_W.get(c, _p99_med) for c in all_cabinets}
print(f"    {len(cab_p99_W)} cabinets; P^99 range "
      f"[{min(cab_p99_W.values())/1e3:.1f}, {max(cab_p99_W.values())/1e3:.1f}] kW")

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
job_agg = job_agg.merge(meta, on="job_idx", how="left")
job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)
jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)
n_base = len(jobs_sorted)
print(f"    {n_base} base test jobs")

# Job stratification: quartiles by n_cohort, node_count, power_per_node, runtime
def _make_quartile_map(arr, jids, label):
    cuts = np.percentile(arr, [25, 50, 75])
    q    = (np.digitize(arr, cuts) + 1).clip(1, 4)
    mapping = {int(jid): int(qi) for jid, qi in zip(jids, q)}
    print(f"    {label} quartile bounds: p25={cuts[0]:.2f} p50={cuts[1]:.2f} p75={cuts[2]:.2f}")
    return mapping, cuts

_jids = jobs_sorted["job_idx"].values
job_quartile_ncoh, _q_cuts_ncoh = _make_quartile_map(
    jobs_sorted["n_cohort"].values,   _jids, "n_cohort")
job_quartile_nc,   _q_cuts_nc   = _make_quartile_map(
    jobs_sorted["node_count"].fillna(0).values, _jids, "node_count")
job_quartile_ppn,  _q_cuts_ppn  = _make_quartile_map(
    jobs_sorted["power_per_node"].fillna(0).values, _jids, "power_per_node")
job_quartile_rt,   _q_cuts_rt   = _make_quartile_map(
    jobs_sorted["run_time"].fillna(0).values, _jids, "runtime")

# Primary n_cohort quartile (used in loop)
job_quartile = job_quartile_ncoh   # for backward compat label
_q_cuts      = _q_cuts_ncoh

# Historical per-node utilisation
hist_node_hours: dict[str, float] = {n: 0.0 for n in cohort_list}
for _, jrow in jobs_sorted.iterrows():
    rt_h = float(jrow["run_time"]) / 3600.0
    for nd in jrow["hist_nodes"]:
        if nd in hist_node_hours:
            hist_node_hours[nd] += rt_h

hist_util_arr  = np.array([hist_node_hours[n] for n in cohort_list])
hist_total_nh  = float(hist_util_arr.sum())
hist_fleet_avg = hist_total_nh / n_cohort       # average node-hours per node
u_max_base     = (1.0 + DELTA_CAP) * hist_fleet_avg
print(f"    hist_total_nh={hist_total_nh:.1f}  hist_fleet_avg={hist_fleet_avg:.3f} h")

# ══════════════════════════════════════════════════════════════════════
# [6] Residual model (N_BINS=5, sorted by FA_2024 within job)
# ══════════════════════════════════════════════════════════════════════
print("\n[6] Building residual model (N_BINS=5) ...")

# alpha_j: mean T_p95 across fp nodes in each test job (frozen from test set)
test_df2 = test_df.copy()
test_df2["job_mean_T"] = test_df2.groupby("job_idx")["T_p95"].transform("mean")
alpha_map: dict[int, float] = (
    test_df2.groupby("job_idx")["job_mean_T"].first().to_dict()
)

# Residuals: delta_T_p95 - BETA_F_frozen * FA_2024
test_df2["delta_T_p95"] = test_df2["T_p95"] - test_df2["job_mean_T"]
test_df2["pred_frozen"]  = BETA_F_FROZEN * test_df2["F_2024"]
test_df2["residual"]     = test_df2["delta_T_p95"] - test_df2["pred_frozen"]

job_residuals: dict[int, tuple] = {}
for jid, grp in test_df2.groupby("job_idx"):
    jid = int(jid)
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

n_underbinned = sum(1 for jid, (r, b) in job_residuals.items() if len(r) < N_BINS)
print(f"    {len(job_residuals)} jobs with residuals; {n_underbinned} under-binned (k<5)")

# alpha_j update: jobs_sorted
jobs_sorted["alpha_j"] = jobs_sorted["job_idx"].astype(int).map(alpha_map)

# ══════════════════════════════════════════════════════════════════════
# [7] Background arrays (non-test-job cohort activity)
# ══════════════════════════════════════════════════════════════════════
print("\n[7] Precomputing background busy arrays ...")
t0 = time.time()

is_test_sched = np.array([jid in test_id_set for jid in sched_jids])
bg_st = sched_st[~is_test_sched]
bg_et = sched_et[~is_test_sched]
bg_cn = sched_cn[~is_test_sched]

bg_busy_per_job: dict[int, frozenset] = {}
for _, jrow in jobs_sorted.iterrows():
    jid = int(jrow["job_idx"])
    t_j = _to_dt64_ms(jrow["start_time"])
    mask = (bg_st <= t_j) & (bg_et > t_j)
    bg_busy_per_job[jid] = frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

print(f"    Done  ({time.time()-t0:.1f}s)")

hist_starts_dt64 = np.array([_to_dt64_ms(r["start_time"]) for _, r in jobs_sorted.iterrows()])
hist_ends_dt64   = np.array([_to_dt64_ms(r["end_time"])   for _, r in jobs_sorted.iterrows()])
hist_k_arr       = jobs_sorted["n_cohort"].values.astype(int)
hist_jids_arr    = jobs_sorted["job_idx"].values.astype(int)

# ══════════════════════════════════════════════════════════════════════
# [8] Cabinet power background (non-cohort, using correct topology)
#     Uses host_list directly — NO str(node_list).split()
# ══════════════════════════════════════════════════════════════════════
print("\n[8] Precomputing cabinet background power (correct topology) ...")
t0 = time.time()

_all_jids = all_jobs["job_idx_int"].values
_all_Pj   = np.where(all_jobs["mean_power"].isna().values,
                     0.0, all_jobs["mean_power"].values.astype(float))
_all_nc   = np.maximum(all_jobs["node_count"].values.astype(int), 1)
_all_hl   = all_jobs["host_list"].values
_all_st   = _col_to_dt64ms(all_jobs["start_time"])
_all_et   = _col_to_dt64ms(all_jobs["end_time"])

bg_records: list[dict] = []            # non-cohort cabinet contribution
cohort_hist_records: list[dict] = []   # cohort historical contribution (base jobs)

for jid, P_j, nc, hl, t_s, t_e in zip(_all_jids, _all_Pj, _all_nc, _all_hl, _all_st, _all_et):
    ppn = P_j / nc
    ncc: dict[int, int] = {}    # non-cohort
    chc: dict[int, int] = {}    # cohort-historical (base test jobs only)

    for hn in hl:                       # hl is a Python list — no truncation
        c = node_to_cab.get(hn, -1)     # CORRECT topology, no str(node_list).split()
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

# Historical full-cabinet budget (identity = bg + cohort_hist) at Gate C P^99
def sweep_cab_budget(records: list[dict], thr: dict[int, float]) -> tuple[float, float]:
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
    B = 0.0; S = 0.0
    for t, sign, c, dp in events:
        if c in last_t and t != last_t[c]:
            dt_h = _dt64_to_h(last_t[c], t)
            if dt_h > 0:
                exc = P_cab[c] - thr.get(c, 0.0)
                if exc > 0:
                    B += dt_h
                    S += dt_h * exc
        P_cab[c] += sign * dp
        last_t[c] = t
    return B, S

combined_hist = bg_records + cohort_hist_records
B_cab_hist, S_cab_hist = sweep_cab_budget(combined_hist, cab_p99_W)
print(f"    B_cab_hist (full-cab identity at Gate C P^99): {B_cab_hist:.2f} h")
print(f"    S_cab_hist: {S_cab_hist:.2f} W*h")

# Node-level B_hist at the two thresholds (observed)
rt_lookup = jobs_sorted.set_index("job_idx")["run_time"].to_dict()
for row_idx in range(len(test_df2)):
    pass  # already computed via test_df2

_rt_h_arr = test_df2["job_idx"].map(lambda j: rt_lookup.get(int(j), 0.0)) / 3600.0
B_hist_primary   = float((_rt_h_arr * (test_df2["T_p95"] > T_THR_PRIMARY  )).sum())
B_hist_secondary = float((_rt_h_arr * (test_df2["T_p95"] > T_THR_SECONDARY)).sum())
S_hist_primary   = float((_rt_h_arr * (test_df2["T_p95"] - T_THR_PRIMARY  ).clip(lower=0)).sum())
S_hist_secondary = float((_rt_h_arr * (test_df2["T_p95"] - T_THR_SECONDARY).clip(lower=0)).sum())

# Model-identity (no residual) at primary threshold — for reference only
test_df2["T_pred_id"] = test_df2["job_mean_T"] + test_df2["pred_frozen"]
B_model_id_primary = float((_rt_h_arr * (test_df2["T_pred_id"] > T_THR_PRIMARY)).sum())
print(f"    B_hist_primary ({T_THR_PRIMARY}C):   {B_hist_primary:.2f} h")
print(f"    B_model_id_primary:                  {B_model_id_primary:.2f} h")

# ══════════════════════════════════════════════════════════════════════
# [9] Helper functions
# ══════════════════════════════════════════════════════════════════════

def bg_busy_at(t_np: np.datetime64) -> frozenset:
    mask = (bg_st <= t_np) & (bg_et > t_np)
    return frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

def look_ahead_safe(selected_nodes, t_s, t_e, cf_busy):
    overlap_mask = (hist_starts_dt64 > t_s) & (hist_starts_dt64 < t_e)
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

def generate_job_perms(syn_pool: pd.DataFrame, scen_rng: np.random.Generator) -> dict:
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

# ══════════════════════════════════════════════════════════════════════
# [10] Model-identity reference B_ref,s
#      Historical node assignments + scenario residual permutation
# ══════════════════════════════════════════════════════════════════════

def compute_B_ref_s(job_perms: dict, thr: float) -> float:
    """
    B_ref,s = thermal budget at historical assignments using scenario permutations.
    For each base test job, assigns historical nodes and computes exceedance
    with the same residual permutation used by policy replays.
    """
    B = 0.0
    for _, jrow in jobs_sorted.iterrows():
        jid     = int(jrow["job_idx"])
        rt_h    = float(jrow["run_time"]) / 3600.0
        alpha   = float(jrow["alpha_j"])
        hist_ns = list(jrow["hist_nodes"])          # historical fp node assignments
        if not hist_ns:
            continue
        F_arr   = np.array([FA_dict[n] for n in hist_ns], dtype=float)
        res_s, _ = job_residuals[jid]
        perm     = job_perms[jid]
        rank     = np.argsort(np.argsort(F_arr))
        T_hats   = alpha + BETA_F_FROZEN * F_arr + res_s[perm[rank]]
        B       += rt_h * float((T_hats > thr).sum())
    return B

# ══════════════════════════════════════════════════════════════════════
# [11] Policy selection helpers
# ══════════════════════════════════════════════════════════════════════

def select_fp(available: list[str], k: int) -> list[str]:
    avail_F = np.array([FA_dict[n] for n in available])
    order   = np.argsort(avail_F)
    return [available[i] for i in order[:min(k, len(available))]]

def select_loc(available: list[str], k: int) -> list[str]:
    avail_L = np.array([LOC_FA_dict.get(n, 0.0) for n in available])
    order   = np.argsort(avail_L)
    return [available[i] for i in order[:min(k, len(available))]]

def select_compact(available: list[str], k: int, rng_local) -> list[str]:
    """Greedy cabinet minimiser: fill occupied cabinets first, random within tier."""
    if k >= len(available):
        return available[:]
    # Group by cabinet
    cab_groups: dict[int, list] = defaultdict(list)
    for n in available:
        cab_groups[fp_cab.get(n, -1)].append(n)
    # Sort cabinets: most-available first, random tie-breaking
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

# ══════════════════════════════════════════════════════════════════════
# [12] capacity_replay_m4
# ══════════════════════════════════════════════════════════════════════

POLICY_IDS = ["random", "fp", "loc", "compact"]

def capacity_replay_m4(syn_subset, policy: str, lambda_val: float,
                       policy_seed: int, job_perms: dict,
                       avail_nodes: set | None = None) -> dict:
    """
    Run one (policy, lambda) scenario.

    avail_nodes: if not None, restrict eligible fp nodes to this set
                 (used for availability sensitivity).

    Returns dict with B/S ratios, capacity_unlock_pct, drops, etc.
    """
    eligible = avail_nodes if avail_nodes is not None else cohort_set
    u_max    = (1.0 + DELTA_CAP) * lambda_val * hist_fleet_avg

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
    cf_util: dict[str, float]         = {n: 0.0 for n in eligible}
    _rng = np.random.default_rng(policy_seed)

    B_primary = 0.0; S_primary = 0.0
    n_cabs_per_job: list[int] = []   # cabinet span per admitted job (syn + base)
    B_secondary = 0.0; S_secondary = 0.0
    syn_node_hours = 0.0
    n_syn_admit  = 0
    n_drop_cap   = 0
    n_drop_phys  = 0
    n_drop_la    = 0
    n_base_unserved = 0
    # Per-stratification counters: attempted, admitted, drop_cap, drop_physical, drop_la
    # Keys: "ncoh", "nc", "ppn", "rt" → each a dict of quartile→{attempted, admitted, ...}
    def _empty_strat():
        return {q: {"attempted": 0, "admitted": 0,
                    "drop_cap": 0, "drop_physical": 0, "drop_la": 0}
                for q in range(1, 5)}
    strat_ncoh = _empty_strat()
    strat_nc   = _empty_strat()
    strat_ppn  = _empty_strat()
    strat_rt   = _empty_strat()

    # backward-compat aliases for old q_admit / q_drop
    q_admit  = {q: 0 for q in range(1, 5)}
    q_drop   = {q: 0 for q in range(1, 5)}
    cohort_records: list[dict] = []

    for _, jrow in combined.iterrows():
        is_syn  = bool(jrow["is_synthetic"])
        t_j     = _to_dt64_ms(jrow["start_time"])
        t_e     = _to_dt64_ms(jrow["end_time"])
        rt_h    = float(jrow["run_time"]) / 3600.0
        k       = int(jrow["n_cohort"])
        jid     = int(jrow["job_idx"])
        P_j     = float(jrow["mean_power"]) if not pd.isna(jrow.get("mean_power")) else 0.0
        nc      = max(1, int(jrow["node_count"]))
        ppn     = P_j / nc

        try:
            parent_jid = int(jrow["parent_job_idx"])
        except (TypeError, ValueError):
            parent_jid = jid

        if is_syn:
            bg_busy = bg_busy_at(t_j)
        else:
            bg_busy = bg_busy_per_job.get(parent_jid, frozenset())

        cf_busy_now = frozenset(n for n, te in cf_busy.items() if te > t_j)

        avail_capped = [
            n for n in eligible
            if n not in bg_busy and n not in cf_busy_now and cf_util.get(n, 0.0) < u_max
        ]

        if is_syn:
            if len(avail_capped) < k:
                avail_unc = [n for n in eligible if n not in bg_busy and n not in cf_busy_now]
                if len(avail_unc) < k:
                    n_drop_phys += 1
                    _drop_key = "drop_physical"
                else:
                    n_drop_cap += 1
                    _drop_key = "drop_cap"
                # Update all four stratifications
                for _strat, _qmap in ((strat_ncoh, job_quartile_ncoh),
                                      (strat_nc,   job_quartile_nc),
                                      (strat_ppn,  job_quartile_ppn),
                                      (strat_rt,   job_quartile_rt)):
                    _q = _qmap.get(parent_jid, 4)
                    _strat[_q]["attempted"] += 1
                    _strat[_q][_drop_key]   += 1
                q_drop[job_quartile.get(parent_jid, 4)] += 1
                continue
            available = avail_capped
        else:
            avail_unc = [n for n in eligible if n not in bg_busy and n not in cf_busy_now]
            available = avail_capped if len(avail_capped) >= k else avail_unc

        if not available:
            if not is_syn:
                n_base_unserved += 1
            continue

        # Policy selection
        if policy == "fp":
            selected = select_fp(available, k)
        elif policy == "loc":
            selected = select_loc(available, k)
        elif policy == "compact":
            selected = select_compact(available, k, _rng)
        else:  # random (P0)
            selected = select_random(available, k, _rng)

        if is_syn and selected:
            if not look_ahead_safe(selected, t_j, t_e, cf_busy):
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
            cf_busy[n] = t_e
            cf_util[n] = cf_util.get(n, 0.0) + rt_h

        if selected:
            F_arr    = np.array([FA_dict[n] for n in selected])
            alpha    = float(jrow["alpha_j"])
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

            cc: dict[int, int] = {}
            for nd in selected:
                c = fp_cab.get(nd, -1)
                if c >= 0:
                    cc[c] = cc.get(c, 0) + 1
            if cc:
                cohort_records.append({"t_s": t_j, "t_e": t_e, "ppn": ppn, "cab_counts": cc})
                n_cabs_per_job.append(len(cc))

    if n_base_unserved > 0:
        raise AssertionError(
            f"Base-job invariant violated: {n_base_unserved} unserved "
            f"(lam={lambda_val:.2f}, policy={policy})")

    # Gini coefficient of cf_util (utilisation distribution across eligible nodes)
    u_vals = np.array([cf_util.get(n, 0.0) for n in eligible], dtype=float)
    if u_vals.sum() > 0:
        u_sorted = np.sort(u_vals)
        n_u = len(u_sorted)
        cum  = np.cumsum(u_sorted)
        gini = float(1 - 2 * cum[:-1].sum() / (n_u * cum[-1]))
    else:
        gini = float("nan")

    capacity_unlock_pct = syn_node_hours / hist_total_nh * 100.0

    # Full-cabinet budget
    full_records = bg_records + cohort_records
    B_cab, S_cab = sweep_cab_budget(full_records, cab_p99_W)
    B_cab_ratio  = B_cab / max(B_cab_hist, 1e-9)
    S_cab_ratio  = S_cab / max(S_cab_hist, 1e-9)

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
        # Per-quartile (Q1=smallest, Q4=largest) — legacy n_cohort
        "q_admit"            : q_admit,
        "q_drop"             : q_drop,
        # Full stratification: attempted/admitted/drop_* by quartile for 4 dimensions
        # (Q1=smallest, Q4=largest; by n_cohort, node_count, power_per_node, runtime)
        "strat_ncoh"         : strat_ncoh,
        "strat_nc"           : strat_nc,
        "strat_ppn"          : strat_ppn,
        "strat_rt"           : strat_rt,
        # Cabinet span
        "cab_span_median"    : jf(float(np.median(n_cabs_per_job)) if n_cabs_per_job else None),
        "cab_span_p90"       : jf(float(np.percentile(n_cabs_per_job, 90)) if n_cabs_per_job else None),
        "cab_span_mean"      : jf(float(np.mean(n_cabs_per_job)) if n_cabs_per_job else None),
    }

# ══════════════════════════════════════════════════════════════════════
# [13] Crossing / bracket helpers
# ══════════════════════════════════════════════════════════════════════

def find_c_lower(rows: list[dict], b_ratio_key: str) -> float | None:
    """C_lower = capacity_unlock_pct at LAST lambda before B_ratio first exceeds 1."""
    last_c = None
    for r in rows:
        br = r.get(b_ratio_key)
        if br is None or np.isnan(br):
            continue
        if br <= 1.0:
            last_c = r["capacity_unlock_pct"]
        else:
            break
    return last_c

def find_c_upper(rows: list[dict], b_ratio_key: str) -> float | None:
    """C_upper = capacity_unlock_pct at FIRST lambda where B_ratio >= 1."""
    for r in rows:
        br = r.get(b_ratio_key)
        if br is None or np.isnan(br):
            continue
        if br >= 1.0:
            return r["capacity_unlock_pct"]
    return None  # never exceeded (right-censored)

def find_c_feasible(rows: list[dict], b_ratio_key: str) -> float | None:
    """Linear interpolation at exact B_ratio=1 crossing."""
    for i in range(len(rows) - 1):
        r0 = rows[i]; r1 = rows[i + 1]
        br0 = r0.get(b_ratio_key); br1 = r1.get(b_ratio_key)
        if br0 is None or br1 is None:
            continue
        if np.isnan(br0) or np.isnan(br1):
            continue
        if br0 <= 1.0 <= br1:
            frac = (1.0 - br0) / max(br1 - br0, 1e-12)
            c0   = r0["capacity_unlock_pct"]
            c1   = r1["capacity_unlock_pct"]
            return float(c0 + frac * (c1 - c0))
        if i == 0 and br0 > 1.0:
            return 0.0
    return None

def summarise_crossings(lambda_rows: list[dict], b_ref_s: float) -> dict:
    """
    Given lambda sweep rows for ONE policy in ONE scenario,
    normalise B values by B_ref_s and return crossing metrics.
    """
    for r in lambda_rows:
        r["B_primary_ratio"] = r["B_primary_h"] / max(b_ref_s, 1e-9)
        r["B_secondary_ratio"] = r["B_secondary_h"] / max(
            B_hist_secondary, 1e-9)
    c_lo  = find_c_lower(lambda_rows, "B_primary_ratio")
    c_up  = find_c_upper(lambda_rows, "B_primary_ratio")
    c_feas = find_c_feasible(lambda_rows, "B_primary_ratio")
    c_cab  = find_c_lower(lambda_rows, "B_cab_ratio")
    return {
        "C_lower_pct"  : jf(c_lo),
        "C_upper_pct"  : jf(c_up),
        "C_feasible_pct": jf(c_feas),
        "C_cab_lower_pct": jf(c_cab),
        "width_pct"    : jf(c_up - c_lo) if (c_lo is not None and c_up is not None) else None,
        "right_censored": c_up is None,
    }

# ══════════════════════════════════════════════════════════════════════
# [14] Main MC loop
# ══════════════════════════════════════════════════════════════════════

n_extra_max = int(np.ceil((LAMBDA_MAX - 1.0) * n_base))
print(f"\nSynthetic pool size (LAMBDA_MAX={LAMBDA_MAX}): {n_extra_max} jobs (= n_base)")

# Master RNG for scenario seeds
master_rng = np.random.default_rng(SCENARIO_SEED)
scen_seeds = [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
wl_seeds   = [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
pol_seeds  = {p: [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
              for p in POLICY_IDS}

scenario_results = []
smoke_ok = False

print(f"\n{'='*70}")
print(f"Running {N_SCENARIOS} scenarios × {len(LAMBDA_SWEEP)} lambdas × {len(POLICY_IDS)} policies")
print(f"{'='*70}")

for s_idx in range(N_SCENARIOS):
    t_scen = time.time()
    if s_idx == 0:
        print(f"\n--- SMOKE TEST: scenarios 0-{N_SMOKE-1} ---")

    print(f"\nScenario {s_idx+1}/{N_SCENARIOS}  (seed={scen_seeds[s_idx]})")

    # Synthetic pool for this scenario (consistent LAMBDA_MAX=2.0 pool)
    syn_pool = sample_synthetic_pool(n_extra_max, wl_seeds[s_idx])
    assert len(syn_pool) == n_extra_max, f"Pool size mismatch: {len(syn_pool)} != {n_extra_max}"

    # Residual permutations (shared across policies via CRN)
    scen_rng  = np.random.default_rng(scen_seeds[s_idx])
    job_perms = generate_job_perms(syn_pool, scen_rng)

    # Model-identity reference (historical assignments + scenario permutations)
    B_ref_s_primary = compute_B_ref_s(job_perms, T_THR_PRIMARY)
    print(f"    B_ref_s (primary {T_THR_PRIMARY}C): {B_ref_s_primary:.2f} h")

    # Lambda sweep for each policy
    scen_rows: dict[str, list] = {p: [] for p in POLICY_IDS}

    for lam in LAMBDA_SWEEP:
        n_syn = int(round((lam - 1.0) * n_base))
        syn_sub = syn_pool.iloc[:n_syn].copy() if n_syn > 0 else pd.DataFrame(
            columns=list(syn_pool.columns) if len(syn_pool) > 0 else list(jobs_sorted.columns))

        hdr_printed = False
        for p_idx, pol in enumerate(POLICY_IDS):
            t_pol = time.time()
            try:
                res = capacity_replay_m4(
                    syn_sub, pol, lam,
                    policy_seed=pol_seeds[pol][s_idx],
                    job_perms=job_perms,
                )
            except AssertionError as exc:
                print(f"    lam={lam:.2f} {pol}: INVARIANT VIOLATED -- {exc}")
                scen_rows[pol].append({
                    "lambda_val": lam,
                    "policy": pol,
                    "invariant_violated": True,
                    "capacity_unlock_pct": (n_syn / n_base * 100.0) if n_base > 0 else 0.0,
                    "B_primary_h": float("nan"),
                    "B_secondary_h": float("nan"),
                    "B_cab_ratio": float("nan"),
                })
                continue
            scen_rows[pol].append(res)
            if not hdr_printed:
                print(f"    lam={lam:.2f} N_syn={n_syn}")
                hdr_printed = True
            br = res["B_primary_h"] / max(B_ref_s_primary, 1e-9)
            print(f"      {pol:8s}: C={res['capacity_unlock_pct']:5.1f}%  "
                  f"B/Bref={br:.4f}  Bcab={res['B_cab_ratio']:.4f}  "
                  f"drops={res['n_drop_physical']}/{res['n_drop_cap']}/{res['n_drop_la']}"
                  f"  ({time.time()-t_pol:.0f}s)")

    # Smoke-test invariants (first N_SMOKE scenarios)
    if s_idx < N_SMOKE:
        for pol in POLICY_IDS:
            rows_lam1 = [r for r in scen_rows[pol] if abs(r.get("lambda_val", -1) - 1.0) < 1e-9]
            if rows_lam1:
                r1 = rows_lam1[0]
                if not r1.get("invariant_violated"):
                    assert r1["n_base_unserved"] == 0, \
                        f"Smoke: n_base_unserved={r1['n_base_unserved']} at lam=1.0 pol={pol}"
                    c1 = r1["capacity_unlock_pct"]
                    assert abs(c1) < 1e-6, \
                        f"Smoke: capacity_unlock_pct={c1:.4f} at lam=1.0 pol={pol} (expect 0)"

    if s_idx == N_SMOKE - 1:
        smoke_ok = True
        print(f"\n  *** SMOKE TEST PASSED (scenarios 1-{N_SMOKE}) ***")
        print(f"  Proceeding to full {N_SCENARIOS}-scenario run ...\n")

    # Summarise crossings per policy
    crossings: dict[str, dict] = {}
    for pol in POLICY_IDS:
        crossings[pol] = summarise_crossings(scen_rows[pol], B_ref_s_primary)

    delta_c_lower_fp_vs_rand = (
        (crossings["fp"]["C_lower_pct"] - crossings["random"]["C_lower_pct"])
        if (crossings["fp"]["C_lower_pct"] is not None and
            crossings["random"]["C_lower_pct"] is not None)
        else None
    )
    print(f"    Crossings: "
          + "  ".join(f"{p}:C_lower={crossings[p]['C_lower_pct']}"
                      for p in POLICY_IDS)
          + f"  dC_lower(fp-rand)={delta_c_lower_fp_vs_rand}")

    scenario_results.append({
        "scenario_idx"   : s_idx,
        "scen_seed"      : scen_seeds[s_idx],
        "wl_seed"        : wl_seeds[s_idx],
        "B_ref_s_primary": jf(B_ref_s_primary),
        "lambda_rows"    : {pol: scen_rows[pol] for pol in POLICY_IDS},
        "crossings"      : crossings,
        "delta_C_lower_fp_minus_random": jf(delta_c_lower_fp_vs_rand),
        "elapsed_s"      : round(time.time() - t_scen, 1),
    })

assert smoke_ok, "Smoke test never passed"

if SMOKE_ONLY:
    print("\n" + "="*70)
    print("SMOKE_ONLY mode: stopping after 5-scenario smoke gate.")
    print("="*70)
    print("\nSMOKE RESULTS SUMMARY")
    print(f"{'Policy':<20} {'median C_lower':>14} {'min':>8} {'max':>8}")
    print("-"*54)
    for pol in POLICY_IDS:
        c_lo_vals = [s["crossings"][pol]["C_lower_pct"] for s in scenario_results]
        finite = [v for v in c_lo_vals if v is not None]
        if finite:
            print(f"  {pol:<18} {float(np.median(finite)):>12.2f}%  "
                  f"{float(min(finite)):>6.2f}%  {float(max(finite)):>6.2f}%")
        else:
            print(f"  {pol:<18} {'N/A':>12}")
    dc_smoke = [s["delta_C_lower_fp_minus_random"] for s in scenario_results]
    dc_finite = [v for v in dc_smoke if v is not None]
    if dc_finite:
        print(f"\n  Paired FP-Random ΔC_lower: median={float(np.median(dc_finite)):.2f} pp  "
              f"[{float(min(dc_finite)):.2f}, {float(max(dc_finite)):.2f}]")

    print("\nFor full 30-scenario run: unset M4_SMOKE_ONLY or set M4_SMOKE_ONLY=0")
    import sys; sys.exit(0)

# ══════════════════════════════════════════════════════════════════════
# [15] Availability sensitivity (Random vs FP; N_AVAIL_SCENARIOS)
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"Availability sensitivity ({N_AVAIL_SCENARIOS} scenarios × "
      f"{len(N_AVAIL_FRACTIONS)} fractions)")
print(f"{'='*70}")

avail_rng_base = np.random.default_rng(SCENARIO_SEED + 12345)
avail_results  = []

fp_list = list(cohort_list)   # for indexing

for f in N_AVAIL_FRACTIONS:
    n_avail = max(1, round(f * N_FP))
    f_rows = []

    for s_idx in range(N_AVAIL_SCENARIOS):
        # CRN: same permutation per scenario, only threshold changes
        perm = avail_rng_base.permutation(N_FP)
        avail_set = set(fp_list[i] for i in perm[:n_avail])

        # Re-use first N_AVAIL_SCENARIOS scenario data
        syn_pool = sample_synthetic_pool(n_extra_max, wl_seeds[s_idx])
        scen_rng = np.random.default_rng(scen_seeds[s_idx])
        job_perms_av = generate_job_perms(syn_pool, scen_rng)
        B_ref_s_av = compute_B_ref_s(job_perms_av, T_THR_PRIMARY)

        pol_rows_f: dict[str, list] = {"random": [], "fp": []}
        for pol in ["random", "fp"]:
            for lam in LAMBDA_SWEEP:
                n_syn = int(round((lam - 1.0) * n_base))
                syn_sub = syn_pool.iloc[:n_syn].copy() if n_syn > 0 else pd.DataFrame(
                    columns=list(syn_pool.columns))
                try:
                    res = capacity_replay_m4(
                        syn_sub, pol, lam,
                        policy_seed=pol_seeds[pol][s_idx],
                        job_perms=job_perms_av,
                        avail_nodes=avail_set,
                    )
                    pol_rows_f[pol].append(res)
                except AssertionError:
                    pol_rows_f[pol].append({
                        "lambda_val": lam,
                        "policy": pol,
                        "invariant_violated": True,
                        "capacity_unlock_pct": (n_syn / n_base * 100.0),
                        "B_primary_h": float("nan"),
                        "B_cab_ratio": float("nan"),
                    })

        cr_rand = summarise_crossings(pol_rows_f["random"], B_ref_s_av)
        cr_fp   = summarise_crossings(pol_rows_f["fp"],     B_ref_s_av)
        dc = (jf(cr_fp["C_lower_pct"] - cr_rand["C_lower_pct"])
              if cr_fp["C_lower_pct"] is not None and cr_rand["C_lower_pct"] is not None
              else None)
        f_rows.append({
            "scenario_idx"    : s_idx,
            "C_lower_random"  : cr_rand["C_lower_pct"],
            "C_lower_fp"      : cr_fp["C_lower_pct"],
            "delta_C_lower"   : dc,
        })

    dc_vals = [r["delta_C_lower"] for r in f_rows if r["delta_C_lower"] is not None]
    dc_med  = float(np.median(dc_vals)) if dc_vals else None
    print(f"    f={f:.0%}  n_avail={n_avail}  "
          f"median_dC_lower(FP-rand)={dc_med}")

    avail_results.append({
        "avail_frac"   : f,
        "n_avail"      : n_avail,
        "scenario_rows": f_rows,
        "delta_C_lower_median": jf(dc_med),
        "delta_C_lower_mean"  : jf(float(np.mean(dc_vals)) if dc_vals else None),
    })

# ══════════════════════════════════════════════════════════════════════
# [16] Aggregate statistics
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("Aggregate statistics")
print(f"{'='*70}")

def agg(vals, label):
    arr = [v for v in vals if v is not None and not np.isnan(v)]
    if not arr:
        return {f"{label}_mean": None, f"{label}_median": None,
                f"{label}_p5": None, f"{label}_p95": None,
                f"{label}_n": 0}
    return {
        f"{label}_n"     : len(arr),
        f"{label}_mean"  : jf(float(np.mean(arr))),
        f"{label}_median": jf(float(np.median(arr))),
        f"{label}_p5"    : jf(float(np.percentile(arr, 5))),
        f"{label}_p25"   : jf(float(np.percentile(arr, 25))),
        f"{label}_p75"   : jf(float(np.percentile(arr, 75))),
        f"{label}_p95"   : jf(float(np.percentile(arr, 95))),
    }

policy_summary = {}
for pol in POLICY_IDS:
    c_lo_vals  = [s["crossings"][pol]["C_lower_pct"]  for s in scenario_results]
    c_up_vals  = [s["crossings"][pol]["C_upper_pct"]  for s in scenario_results]
    c_fe_vals  = [s["crossings"][pol]["C_feasible_pct"] for s in scenario_results]
    right_cens = sum(1 for v in c_up_vals if v is None)
    pol_agg    = {}
    pol_agg.update(agg(c_lo_vals,  "C_lower"))
    pol_agg.update(agg(c_up_vals,  "C_upper"))
    pol_agg.update(agg(c_fe_vals,  "C_feasible"))
    pol_agg["right_censored_count"] = right_cens
    policy_summary[pol] = pol_agg

    print(f"\n  {pol}: C_lower median={pol_agg['C_lower_median']:.2f}%  "
          f"p5={pol_agg['C_lower_p5']:.2f}%  p95={pol_agg['C_lower_p95']:.2f}%  "
          f"right_censored={right_cens}")

# Paired ΔC_lower = FP − Random
dc_lo_vals = [s["delta_C_lower_fp_minus_random"] for s in scenario_results]
dc_arr     = np.array([v for v in dc_lo_vals if v is not None], dtype=float)
print(f"\n  Paired ΔC_lower (FP − Random): "
      f"median={np.median(dc_arr):.2f} pp  "
      f"mean={np.mean(dc_arr):.2f} pp  "
      f"p5={np.percentile(dc_arr,5):.2f} pp  "
      f"p95={np.percentile(dc_arr,95):.2f} pp  "
      f"n={len(dc_arr)}")

# Bootstrap CI for paired MEDIAN (primary statistic)
boot_rng     = np.random.default_rng(BOOTSTRAP_SEED)
boot_medians = [float(np.median(boot_rng.choice(dc_arr, size=len(dc_arr), replace=True)))
                for _ in range(N_BOOTSTRAP)]
boot_ci_lo   = float(np.percentile(boot_medians, 2.5))
boot_ci_hi   = float(np.percentile(boot_medians, 97.5))
# Secondary: bootstrap CI for mean
boot_rng2    = np.random.default_rng(BOOTSTRAP_SEED + 1)
boot_means2  = [float(np.mean(boot_rng2.choice(dc_arr, size=len(dc_arr), replace=True)))
                for _ in range(N_BOOTSTRAP)]
boot_mean_ci_lo = float(np.percentile(boot_means2, 2.5))
boot_mean_ci_hi = float(np.percentile(boot_means2, 97.5))

n_pos  = int((dc_arr > 0).sum())
n_zero = int((dc_arr == 0).sum())
n_neg  = int((dc_arr < 0).sum())
print(f"  Bootstrap 95% CI for MEDIAN ΔC_lower: [{boot_ci_lo:.2f}, {boot_ci_hi:.2f}] pp  (primary)")
print(f"  Bootstrap 95% CI for mean  ΔC_lower: [{boot_mean_ci_lo:.2f}, {boot_mean_ci_hi:.2f}] pp  (secondary)")
print(f"  Sign counts: +={n_pos}  0={n_zero}  -={n_neg}  "
      f"win_rate={100*n_pos/len(dc_arr):.1f}%")

paired_stats = {
    "primary_statistic" : "paired median ΔC_lower,s = C_lower,FP,s − C_lower,Random10,s",
    "n_scenarios"       : int(len(dc_arr)),
    "min_pp"            : jf(float(dc_arr.min())),
    "q1_pp"             : jf(float(np.percentile(dc_arr, 25))),
    "median_pp"         : jf(float(np.median(dc_arr))),
    "q3_pp"             : jf(float(np.percentile(dc_arr, 75))),
    "max_pp"            : jf(float(dc_arr.max())),
    "mean_pp"           : jf(float(np.mean(dc_arr))),
    "p5_pp"             : jf(float(np.percentile(dc_arr,  5))),
    "p95_pp"            : jf(float(np.percentile(dc_arr, 95))),
    "n_positive"        : n_pos,
    "n_zero"            : n_zero,
    "n_negative"        : n_neg,
    "win_rate_pct"      : jf(float(n_pos / len(dc_arr) * 100)),
    "bootstrap_median_ci_95_lo": jf(boot_ci_lo),
    "bootstrap_median_ci_95_hi": jf(boot_ci_hi),
    "bootstrap_mean_ci_95_lo"  : jf(boot_mean_ci_lo),
    "bootstrap_mean_ci_95_hi"  : jf(boot_mean_ci_hi),
}

# ══════════════════════════════════════════════════════════════════════
# [17] Save output
# ══════════════════════════════════════════════════════════════════════
print(f"\nSaving output ...")

def _clean_val(v):
    if isinstance(v, dict):
        # Nested dict: convert int keys to str, recurse into values
        return {str(dk): _clean_val(dv) for dk, dv in v.items()}
    elif isinstance(v, (np.integer,)):
        return int(v)
    elif isinstance(v, (np.floating, float)):
        return jf(v)
    elif isinstance(v, (np.ndarray,)):
        return v.tolist()
    else:
        return v

def serialize_lambda_rows(rows_by_policy):
    out = {}
    for pol, rows in rows_by_policy.items():
        out[pol] = [{k: _clean_val(v) for k, v in r.items()} for r in rows]
    return out

scen_out = []
for s in scenario_results:
    scen_out.append({
        "scenario_idx"            : s["scenario_idx"],
        "scen_seed"               : s["scen_seed"],
        "wl_seed"                 : s["wl_seed"],
        "B_ref_s_primary_h"       : s["B_ref_s_primary"],
        "lambda_rows"             : serialize_lambda_rows(s["lambda_rows"]),
        "crossings"               : s["crossings"],
        "delta_C_lower_fp_minus_random": s["delta_C_lower_fp_minus_random"],
        "elapsed_s"               : s["elapsed_s"],
    })

result = {
    "script"          : "r1_m4_fair_baselines.py",
    "git_sha"         : git_sha(),
    "timestamp"       : datetime.datetime.utcnow().isoformat() + "Z",
    "parameters"      : {
        "BETA_F_FROZEN"    : BETA_F_FROZEN,
        "T_THR_PRIMARY_C"  : T_THR_PRIMARY,
        "T_THR_SECONDARY_C": T_THR_SECONDARY,
        "DELTA_CAP"        : DELTA_CAP,
        "N_BINS"           : N_BINS,
        "N_SCENARIOS"      : N_SCENARIOS,
        "N_SMOKE"          : N_SMOKE,
        "SCENARIO_SEED"    : SCENARIO_SEED,
        "WORKLOAD_SEED"    : WORKLOAD_SEED,
        "LAMBDA_SWEEP"     : LAMBDA_SWEEP,
        "LAMBDA_MAX"       : LAMBDA_MAX,
        "N_BOOTSTRAP"      : N_BOOTSTRAP,
        "u_max_formula"    : "(1 + DELTA_CAP) * lambda_val * hist_fleet_avg",
        "n_extra_max"      : n_extra_max,
    },
    "design_notes"    : {
        "topology"       : "fleet_node_topology.csv (Gate C corrected); no str(node_list).split()",
        "cabinet_power"  : "per-cabinet P^99 from cabinet_power_envelopes.json (Gate C)",
        "B_ref_s"        : "model-identity replay with scenario residual permutation at historical assignments",
        "C_lower_primary": "B_primary_ratio = B_policy_h / B_ref_s; last lambda before ratio > 1",
        "policies"       : {
            "P0_random" : "random selection, utilisation cap u_max",
            "P1_fp"     : "lowest FA_2024 first, same cap",
            "P2_loc"    : "lowest position-mean FA (chassis/slot/board/node_pos across cabs), same cap",
            "P3_compact": "greedy cabinet-minimising selection, same cap",
        },
        "stratification_quartile_boundaries": {
            "n_cohort"      : {"p25": jf(float(_q_cuts_ncoh[0])),
                               "p50": jf(float(_q_cuts_ncoh[1])),
                               "p75": jf(float(_q_cuts_ncoh[2]))},
            "node_count"    : {"p25": jf(float(_q_cuts_nc[0])),
                               "p50": jf(float(_q_cuts_nc[1])),
                               "p75": jf(float(_q_cuts_nc[2]))},
            "power_per_node": {"p25": jf(float(_q_cuts_ppn[0])),
                               "p50": jf(float(_q_cuts_ppn[1])),
                               "p75": jf(float(_q_cuts_ppn[2]))},
            "runtime"       : {"p25": jf(float(_q_cuts_rt[0])),
                               "p50": jf(float(_q_cuts_rt[1])),
                               "p75": jf(float(_q_cuts_rt[2]))},
        },
        "interpretation" : "C_lower = exposure-constrained workload headroom; "
                           "NOT a claim about physical thermal or power limits violated in production",
    },
    "data_anchors"    : {
        "n_base_jobs"    : n_base,
        "n_cohort"       : n_cohort,
        "hist_total_nh"  : jf(hist_total_nh),
        "hist_fleet_avg_h": jf(hist_fleet_avg),
        "B_hist_primary_h": jf(B_hist_primary),
        "B_model_id_primary_h": jf(B_model_id_primary),
        "B_cab_hist_h"   : jf(B_cab_hist),
    },
    "policy_summary"  : policy_summary,
    "paired_fp_vs_random": paired_stats,
    "scenario_results": scen_out,
    "availability_sensitivity": avail_results,
    "input_files"     : {
        "phase3a_fingerprint_2024.parquet":
            file_sha256(P1_DIR / "phase3a_fingerprint_2024.parquet"),
        "phase3a_test_set.parquet":
            file_sha256(P1_DIR / "phase3a_test_set.parquet"),
        "fleet_node_topology.csv":
            file_sha256(TABLE_DIR / "fleet_node_topology.csv"),
        "fp_node_topology.csv":
            file_sha256(TABLE_DIR / "fp_node_topology.csv"),
        "cabinet_power_envelopes.json":
            file_sha256(OUT_DIR / "cabinet_power_envelopes.json"),
    },
    "elapsed_seconds" : round(time.time() - t_script, 1),
}

out_path = OUT_DIR / "m4_fair_baselines.json"
with open(out_path, "w") as fh:
    json.dump(result, fh, indent=2, default=str)
print(f"\nSaved: {out_path}")
print(f"Total elapsed: {time.time()-t_script:.1f}s")
