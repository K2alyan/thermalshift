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

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import json, hashlib, subprocess, datetime, time, os, heapq
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
LAMBDA_MAX_EXT   = 4.00          # for right-censored extension
LAMBDA_SWEEP_EXT = [2.25, 2.50, 3.00, 3.50, 4.00]
TARGET_PP         = 0.5    # adaptive refinement target: gap <= 0.5 pp
N_REFINE_GRID     = 3      # interior grid points per refinement level (first-violation scan)
EFFICIENCY_TARGETS = [5.0, 10.0, 20.0]  # % capacity for E_B/E_S
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

CKPT_PATH = OUT_DIR / "m4_checkpoint.json"

def write_checkpoint(data: dict) -> None:
    """Atomically write checkpoint JSON."""
    tmp = CKPT_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh)
    tmp.replace(CKPT_PATH)

def read_checkpoint(design_hash: str) -> dict | None:
    """Read checkpoint if design hash matches."""
    if not CKPT_PATH.exists():
        return None
    try:
        with open(CKPT_PATH, encoding="utf-8") as fh:
            ckpt = json.load(fh)
        if ckpt.get("design_hash") != design_hash:
            print(f"  Checkpoint design_hash mismatch -- ignoring.")
            return None
        return ckpt
    except Exception as e:
        print(f"  Checkpoint read failed ({e}) -- starting fresh.")
        return None

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
    "four_policies_P0_P1_P2_P3"       : False,  # replaced by 6-policy design
    "six_policies_full_marginal"       : True,
    "censoring_aware_reporting"        : True,
    "right_censored_correct_C_lower"   : True,
    "three_constraint_crossing"        : True,
    "extended_lambda_to_4x"            : True,
    "checkpoint_resume"                : True,
    "cabinet_span_metrics"             : True,   # already implemented
    "5_scenario_smoke_gate"            : True,
    "30_scenario_main_run"             : True,
    "availability_sensitivity_f_10_60" : True,
    "bootstrap_CI_for_median_delta_C"  : True,
    "stratification_4_dimensions"      : True,   # ncoh, node_count, ppn, runtime
    # Items NOT in this script → r1_m4_sensitivity.py
    "residual_sensitivity_K1_K3_K10"   : False,
    "parametric_residual_sensitivity"  : False,
    "threshold_sensitivity_p90_p99"    : False,
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
# 10th-percentile F threshold for "coolest-10%" share metric (precomputed once)
_F_vals_arr  = np.array(list(FA_dict.values()), dtype=float)
F_COOL10_THR = float(np.percentile(_F_vals_arr, 10))

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

# Eligible nodes per cabinet (for concurrent-occupancy fraction in fp_spread)
cab_eligible_count: dict[int, int] = {}
for _n in cohort_list:
    _c = fp_cab.get(_n, -1)
    if _c >= 0:
        cab_eligible_count[_c] = cab_eligible_count.get(_c, 0) + 1

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
_nh_rt = jobs_sorted["run_time"].fillna(0.0).values / 3600.0
_nh_ns = jobs_sorted["hist_nodes"].values
for _ni in range(len(jobs_sorted)):
    _rt = float(_nh_rt[_ni])
    for nd in _nh_ns[_ni]:
        if nd in hist_node_hours:
            hist_node_hours[nd] += _rt

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
bg_et    = sched_et[~is_test_sched]
bg_cn    = sched_cn[~is_test_sched]
bg_st_ms = bg_st.astype(np.int64)   # int64 ms — fast scalar compare in bg_busy_at_ms
bg_et_ms = bg_et.astype(np.int64)

# Precompute bg_busy for each test job using vectorised int compare
hist_st_for_precomp = _col_to_dt64ms(jobs_sorted["start_time"]).astype(np.int64)
bg_busy_per_job: dict[int, frozenset] = {}
for i, jid in enumerate(jobs_sorted["job_idx"].values.astype(int)):
    t_ms = int(hist_st_for_precomp[i])
    mask = (bg_st_ms <= t_ms) & (bg_et_ms > t_ms)
    bg_busy_per_job[jid] = frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()
del hist_st_for_precomp

print(f"    Done  ({time.time()-t0:.1f}s)")

hist_starts_dt64 = _col_to_dt64ms(jobs_sorted["start_time"])
hist_ends_dt64   = _col_to_dt64ms(jobs_sorted["end_time"])
hist_starts_ms   = hist_starts_dt64.astype(np.int64)   # int64 ms for fast scalar compare
hist_ends_ms     = hist_ends_dt64.astype(np.int64)
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

# Pre-sort bg events ONCE using int ms — avoids numpy datetime64 overhead in sweep loop
print("\n[8b] Pre-sorting background cabinet events (one-time cost) ...")
t0 = time.time()
bg_events_sorted: list[tuple] = []
for _r in bg_records:
    _ppn  = _r["ppn"]
    _ts   = int(_r["t_s"].astype("int64"))   # numpy datetime64 → int ms (fast int compare)
    _te   = int(_r["t_e"].astype("int64"))
    for _c, _n in _r["cab_counts"].items():
        _dp = _ppn * _n
        bg_events_sorted.append((_ts, +1, _c, _dp))
        bg_events_sorted.append((_te, -1, _c, _dp))
bg_events_sorted.sort()   # plain int tuple sort — no key needed
print(f"    {len(bg_events_sorted):,} bg events sorted  ({time.time()-t0:.1f}s)")

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

def _rec_ts_ms(r: dict) -> int:
    """Extract t_s from a record as int ms — handles both int and numpy datetime64."""
    v = r["t_s"]
    return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))

def _rec_te_ms(r: dict) -> int:
    v = r["t_e"]
    return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))

def sweep_cab_budget_fast(cohort_records: list[dict], thr: dict[int, float]) -> tuple[float, float]:
    """Cabinet budget: merges pre-sorted int-ms bg_events_sorted with small cohort events.
    All timestamps are Python int (ms since epoch) — no numpy scalar overhead in loop."""
    coh_ev: list[tuple] = []
    for r in cohort_records:
        ppn  = r["ppn"]
        ts   = _rec_ts_ms(r)
        te   = _rec_te_ms(r)
        for c, n in r["cab_counts"].items():
            dp = ppn * n
            coh_ev.append((ts, +1, c, dp))
            coh_ev.append((te, -1, c, dp))
    coh_ev.sort()   # plain int tuple sort
    events = heapq.merge(bg_events_sorted, coh_ev)   # both sorted int tuples — no key needed
    P_cab: dict[int, float] = defaultdict(float)
    last_t: dict[int, int]  = {}
    B = 0.0; S = 0.0
    for t, sign, c, dp in events:
        if c in last_t and t != last_t[c]:
            dt_h = (t - last_t[c]) / 3_600_000.0   # int ms delta → hours
            if dt_h > 0:
                exc = P_cab[c] - thr.get(c, 0.0)
                if exc > 0:
                    B += dt_h
                    S += dt_h * exc
        P_cab[c] += sign * dp
        last_t[c] = t
    return B, S

B_cab_hist, S_cab_hist = sweep_cab_budget_fast(cohort_hist_records, cab_p99_W)
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

def bg_busy_at_ms(t_ms: int) -> frozenset:
    """Return set of non-test bg-busy cohort nodes at time t_ms (int ms since epoch)."""
    mask = (bg_st_ms <= t_ms) & (bg_et_ms > t_ms)
    return frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

def look_ahead_safe(selected_nodes, t_s_ms: int, t_e_ms: int, cf_busy_ms: dict) -> bool:
    """cf_busy_ms maps node -> end_time_ms (int). t_s_ms, t_e_ms are int ms."""
    overlap_mask = (hist_starts_ms > t_s_ms) & (hist_starts_ms < t_e_ms)
    if not overlap_mask.any():
        return True
    s_nodes = frozenset(selected_nodes)
    for idx in np.where(overlap_mask)[0]:
        t_h_ms = int(hist_starts_ms[idx])
        k_h    = int(hist_k_arr[idx])
        jid_h  = int(hist_jids_arr[idx])
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

_bref_jids  = jobs_sorted["job_idx"].values.astype(int)
_bref_rt_h  = jobs_sorted["run_time"].fillna(0.0).values.astype(float) / 3600.0
_bref_alpha = jobs_sorted["alpha_j"].fillna(0.0).values.astype(float)
_bref_hnodes = jobs_sorted["hist_nodes"].values  # array of lists

def compute_B_S_ref_s(job_perms: dict, thr: float) -> tuple[float, float]:
    """B_ref,s and S_ref,s = thermal budget/severity at historical assignments + scenario permutations."""
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

# Keep the old name as an alias for backward compat in availability sensitivity
def compute_B_ref_s(job_perms: dict, thr: float) -> float:
    B, _ = compute_B_S_ref_s(job_perms, thr)
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

def select_fp_spread(available: list[str], k: int,
                     cab_active_count: dict[int, int],
                     ) -> tuple[list[str], dict[int, int]]:
    """FP-spread-cap-10: balance concurrent cohort-node occupancy across cabinets,
    then select the coolest available node within the chosen cabinet.

    Selection is ITERATIVE within each job: after choosing each node the temporary
    occupancy count for that cabinet is incremented, so the next node selection
    reflects the emerging intra-job placement. This prevents all k nodes from being
    drawn from the same cabinet when k is large relative to cabinet size.

    Uses ONLY: current eligibility, frozen FA_2024, frozen topology (fp_cab /
    cab_eligible_count), and the current concurrent cab_active_count snapshot.
    No future power, no realized temperatures, no residuals, no fitted weights.

    Returns (selected_nodes, updated_cab_active_count).
    Caller must commit the returned dict to replace the live cab_active_count."""
    k    = min(k, len(available))
    temp = dict(cab_active_count)   # working copy; committed by caller after selection

    if k == 0:
        return [], temp
    if k == len(available):
        for n in available:
            c = fp_cab.get(n, -1)
            if c >= 0:
                temp[c] = temp.get(c, 0) + 1
        return list(available), temp

    # Group nodes by cabinet; pre-sort each group by FA_2024 ascending (coolest first).
    # Pre-sorting is O(|available| log |available|) done once; each iteration then just
    # pops the head of the chosen cabinet's list — O(|cabs|) per node selected.
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
        # Least-loaded cabinet; tie-break by cabinet id for determinism
        best_c = min(cab_nodes, key=lambda c: (temp.get(c, 0), c))
        best_n = cab_nodes[best_c].pop(0)      # coolest node in chosen cabinet
        if not cab_nodes[best_c]:
            del cab_nodes[best_c]
        selected.append(best_n)
        temp[best_c] = temp.get(best_c, 0) + 1  # reflect selection for next iteration

    return selected, temp

# ══════════════════════════════════════════════════════════════════════
# [12] capacity_replay_m4
# ══════════════════════════════════════════════════════════════════════

POLICY_IDS = ["full_random", "full_fp", "full_loc", "full_compact",
              "marginal_random", "marginal_fp", "full_fp_spread"]

POLICY_MAP = {                  # name -> (base_algorithm, is_marginal)
    "full_random"    : ("random",    False),
    "full_fp"        : ("fp",        False),
    "full_loc"       : ("loc",       False),
    "full_compact"   : ("compact",   False),
    "marginal_random": ("random",    True),
    "marginal_fp"    : ("fp",        True),
    "full_fp_spread" : ("fp_spread", False),
}

# Scenarios 0..(FP_SPREAD_DEV_N-1) are the development set used to design
# full_fp_spread; scenarios FP_SPREAD_DEV_N..N_SCENARIOS-1 are held-out.
# Original frozen policies (random, fp, loc, compact) are reported across all 30.
FP_SPREAD_DEV_N = N_SMOKE

def capacity_replay_m4(syn_subset, policy: str, lambda_val: float,
                       policy_seed: int, job_perms: dict,
                       avail_nodes: set | None = None,
                       marginal: bool = False) -> dict:
    """
    Run one (policy, lambda) scenario.

    avail_nodes: if not None, restrict eligible fp nodes to this set
                 (used for availability sensitivity).
    marginal: if True, base jobs use historical node assignments; only synthetic
              jobs are policy-selected.

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

    # Pre-extract all columns as numpy arrays — avoids iterrows + per-row Timestamp overhead
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
    _chist_nodes = combined["hist_nodes"].values  # object array -- lists of historical cohort nodes

    # Incremental availability tracking: heap-based expiry + C-level set ops
    # cf_busy_ms: node -> end_time_ms (int), kept for look_ahead_safe queries
    cf_busy_ms: dict[str, int] = {}
    cf_busy_active: set[str]   = set()   # nodes with end_time_ms > t_j_ms (current)
    cf_expire_heap: list       = []       # (end_time_ms, node) min-heap for lazy expiry
    cf_util: dict[str, float]  = {n: 0.0 for n in eligible}
    cap_exceeded: set[str]     = set()   # nodes where cf_util >= u_max
    eligible_set               = set(eligible)
    available_set              = set(eligible)  # = eligible_set - cf_busy_active - cap_exceeded
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
    # FP-spread: concurrent active nodes per cabinet (snapshot, updated on assign/expire)
    cab_active_count: dict[int, int] = {}
    # Per-policy node quality metrics
    sum_F_syn  = 0.0; n_F_syn = 0   # for mean_F_syn (admitted synthetic nodes only)
    cool10_nh  = 0.0                 # node-hours to coolest-10% nodes (F <= F_COOL10_THR)

    def _empty_strat():
        return {q: {"attempted": 0, "admitted": 0,
                    "drop_cap": 0, "drop_physical": 0, "drop_la": 0}
                for q in range(1, 5)}
    strat_ncoh = _empty_strat()
    strat_nc   = _empty_strat()
    strat_ppn  = _empty_strat()
    strat_rt   = _empty_strat()

    q_admit  = {q: 0 for q in range(1, 5)}
    q_drop   = {q: 0 for q in range(1, 5)}
    cohort_records: list[dict] = []

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

        # Expire cf_busy entries whose end_time <= t_j_ms (heap-based, O(log N) amortised)
        while cf_expire_heap and cf_expire_heap[0][0] <= t_j_ms:
            _exp_ms, _exp_n = heapq.heappop(cf_expire_heap)
            if cf_busy_ms.get(_exp_n, -1) == _exp_ms:   # not superseded by a later job
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

        # C-level set ops — ~50 ns/element vs ~1 μs for Python-level frozenset membership
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
            # BASE JOB
            if marginal:
                # Marginal mode: use historical node assignment, no algorithm
                hist_ns = list(_chist_nodes[_i]) if _chist_nodes[_i] is not None else []
                selected = [n for n in hist_ns if n in eligible_set]
                if len(selected) < k:
                    n_base_unserved += 1
                # Mark as busy so synthetic jobs can't use them
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
                # Compute thermal contribution
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
                continue  # done with this base job
            else:
                # Full-replacement mode: policy selects nodes for base jobs too
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
            # Iterative selection commits intra-job occupancy into temp; returns updated dict
            selected, cab_active_count = select_fp_spread(available, k, cab_active_count)
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
            available_set.discard(n)                # no longer available
            heapq.heappush(cf_expire_heap, (t_e_ms, n))
            _new_util = cf_util.get(n, 0.0) + rt_h
            cf_util[n] = _new_util
            if _new_util >= u_max and n not in cap_exceeded:
                cap_exceeded.add(n)
                available_set.discard(n)            # already discarded above but safe
            # Maintain concurrent cabinet occupancy.
            # fp_spread already committed via select_fp_spread's returned temp dict;
            # all other policies (including base jobs in full-replacement mode) update here.
            if policy != "fp_spread":
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
                # Node quality metrics for admitted synthetic nodes
                for n in selected:
                    f_n = FA_dict.get(n, 0.0)
                    sum_F_syn += f_n
                    n_F_syn   += 1
                    if f_n <= F_COOL10_THR:
                        cool10_nh += rt_h

            cc: dict[int, int] = {}
            for nd in selected:
                c = fp_cab.get(nd, -1)
                if c >= 0:
                    cc[c] = cc.get(c, 0) + 1
            if cc:
                cohort_records.append({"t_s": t_j_ms, "t_e": t_e_ms,
                                       "ppn": ppn, "cab_counts": cc})
                n_cabs_per_job.append(len(cc))

    if n_base_unserved > 0 and not marginal:
        raise AssertionError(
            f"Base-job invariant violated: {n_base_unserved} unserved "
            f"(lam={lambda_val:.2f}, policy={policy})")

    # Integrity check for fp_spread concurrent-occupancy accounting
    if policy == "fp_spread":
        _exp_active = sum(1 for n in cf_busy_active if fp_cab.get(n, -1) >= 0)
        _act_active = sum(cab_active_count.values())
        _neg = [c for c, v in cab_active_count.items() if v < 0]
        assert not _neg, f"fp_spread cab_active_count has negative entries: {_neg}"
        assert _act_active == _exp_active, (
            f"fp_spread cab_active_count={_act_active} != "
            f"active cohort nodes in cf_busy_active={_exp_active} "
            f"(lam={lambda_val:.2f})")

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

    # Full-cabinet budget (fast: merges pre-sorted bg_events_sorted with small cohort events)
    B_cab, S_cab = sweep_cab_budget_fast(cohort_records, cab_p99_W)
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
        # Node quality (synthetic admitted nodes only)
        "mean_F_syn"         : jf(sum_F_syn / n_F_syn) if n_F_syn > 0 else None,
        "cool10_share"       : jf(cool10_nh / syn_node_hours) if syn_node_hours > 0 else None,
    }

# ══════════════════════════════════════════════════════════════════════
# [13] Crossing / bracket helpers
# ══════════════════════════════════════════════════════════════════════

def check_infeasible(res: dict, b_ref_s: float, s_ref_s: float) -> tuple[bool, str | None]:
    """True + binding constraint name if any of the 3 constraints violated."""
    if res.get("invariant_violated"):
        return True, "invariant_violated"
    b_ratio = res["B_primary_h"] / max(b_ref_s, 1e-9)
    s_val   = res.get("S_primary_Cdoth")
    s_ratio = (float(s_val) if s_val is not None and not (isinstance(s_val, float) and np.isnan(s_val))
               else float("nan")) / max(s_ref_s, 1e-9)
    b_cab   = res.get("B_cab_ratio") or 0.0
    violations = []
    if b_ratio > 1.0:                                   violations.append("B_ratio")
    if not np.isnan(s_ratio) and s_ratio > 1.0:        violations.append("S_ratio")
    if b_cab   > 1.0:                                   violations.append("B_cab_ratio")
    return bool(violations), (violations[0] if violations else None)


def classify_crossing(lambda_rows: list[dict],
                      b_ref_s: float,
                      s_ref_s: float,
                      b_cab_ref: float) -> dict:
    """
    Classify a (policy, scenario) sweep with 3-constraint logic.

    A lambda point is INFEASIBLE if ANY of:
      B_primary_ratio = B_primary_h / b_ref_s  > 1.0
      S_primary_ratio = S_primary_Cdoth / max(s_ref_s, 1e-9)  > 1.0
      B_cab_ratio (already in row) > 1.0

    Status values:
      "right_censored"  -- still feasible at last tested lambda (C_lower = confirmed lower bound, NOT None)
      "left_boundary"   -- already infeasible at first tested lambda (C_lower = 0)
      "exact_bracket"   -- found transition

    C_lower is NEVER None.  C_upper is None only when right_censored.
    """
    for r in lambda_rows:
        if r.get("invariant_violated"):
            r["infeasible"] = True
            r["first_binding"] = "invariant_violated"
            continue
        b_ratio   = r["B_primary_h"] / max(b_ref_s, 1e-9)
        s_val     = r.get("S_primary_Cdoth")
        s_ratio   = (float(s_val) if s_val is not None and not (isinstance(s_val, float) and np.isnan(s_val)) else float("nan")) / max(s_ref_s, 1e-9)
        b_cab     = r.get("B_cab_ratio") or 0.0
        r["B_primary_ratio"] = b_ratio
        r["S_primary_ratio"] = s_ratio
        violations = []
        if b_ratio > 1.0:                                     violations.append("B_ratio")
        if not np.isnan(s_ratio) and s_ratio > 1.0:          violations.append("S_ratio")
        if b_cab   > 1.0:                                     violations.append("B_cab_ratio")
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

    # No infeasible point found -- right-censored
    c_lo = last_feasible["capacity_unlock_pct"] if last_feasible else 0.0
    return {"status": "right_censored",
            "C_lower_pct": c_lo,
            "C_upper_pct": None,
            "first_binding_constraint": None,
            "right_censored": True}

def refine_crossing_bracket(cx: dict, pol_name: str, base_pol: str, is_marginal: bool,
                             job_perms: dict, policy_seed: int,
                             syn_pool, n_base: int,
                             b_ref_s: float, s_ref_s: float,
                             lambda_rows: list,
                             target_pp: float = TARGET_PP,
                             n_grid: int = N_REFINE_GRID) -> tuple[dict, list]:
    """First-violation ordered-grid refine an exact_bracket crossing to gap <= target_pp.

    Evaluates n_grid interior points left-to-right per level. Always stops at the
    FIRST (leftmost) infeasible point, correctly handling non-monotone B/S/cabinet
    curves (Gate D finding). Never assumes monotonicity; never binary-searches.
    """
    if cx["status"] != "exact_bracket" or cx["C_upper_pct"] is None:
        return cx, []
    if (cx["C_upper_pct"] - cx["C_lower_pct"]) <= target_pp:
        return cx, []

    # Find n_safe (last feasible N_syn) and n_unsafe (first infeasible N_syn)
    n_safe = 0; c_safe = 0.0
    n_unsafe = None; c_unsafe = None; binding = cx["first_binding_constraint"]
    for r in sorted(lambda_rows, key=lambda x: x.get("lambda_val", 0)):
        is_inf, bind = check_infeasible(r, b_ref_s, s_ref_s)
        lam = r.get("lambda_val", 1.0)
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
        # Generate n_grid evenly-spaced interior points between current safe/unsafe
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

        # Scan left-to-right; stop at first infeasible
        for n_pt in grid_pts:
            if n_pt > len(syn_pool):
                break
            syn_sub = syn_pool.iloc[:n_pt].copy()
            lam_pt  = 1.0 + n_pt / n_base
            try:
                res = capacity_replay_m4(syn_sub, base_pol, lam_pt,
                                         policy_seed=policy_seed,
                                         job_perms=job_perms,
                                         marginal=is_marginal)
            except AssertionError:
                res = {"lambda_val": lam_pt, "policy": pol_name,
                       "invariant_violated": True,
                       "capacity_unlock_pct": n_pt / n_base * 100.0,
                       "B_primary_h": float("nan"), "S_primary_Cdoth": float("nan"),
                       "B_cab_ratio": float("nan"), "syn_node_hours": 0.0}
            extra_rows.append(res)
            is_inf, bind = check_infeasible(res, b_ref_s, s_ref_s)

            if is_inf:
                first_inf_pt = (n_pt, res["capacity_unlock_pct"])
                if bind: binding = bind
                break  # leftmost violation found; do not evaluate further right
            else:
                last_safe_pt = (n_pt, res["capacity_unlock_pct"])

        if first_inf_pt is not None:
            n_unsafe, c_unsafe = first_inf_pt
            if last_safe_pt is not None:
                n_safe, c_safe = last_safe_pt
        else:
            # All grid points feasible — advance safe to rightmost evaluated point
            if last_safe_pt is not None:
                n_safe, c_safe = last_safe_pt
            else:
                break

    print(f"      [refine-grid] {pol_name}: [{c_safe:.2f},{c_unsafe:.2f}]%  "
          f"gap={c_unsafe-c_safe:.2f}pp  {len(extra_rows)} evals")
    return {
        "status": "exact_bracket",
        "C_lower_pct": c_safe,
        "C_upper_pct": c_unsafe,
        "first_binding_constraint": binding,
        "right_censored": False,
    }, extra_rows


def compute_paired_interval(cx_fp: dict, cx_rand: dict) -> dict:
    """
    Interval-valued paired effect: [FP_lo - Rand_up, FP_up - Rand_lo].
    delta_lower > 0 -> FP definitely better.
    delta_upper < 0 -> Random definitely better.
    """
    fp_lo = cx_fp["C_lower_pct"]
    fp_up = cx_fp["C_upper_pct"] if cx_fp["C_upper_pct"] is not None else fp_lo
    rd_lo = cx_rand["C_lower_pct"]
    rd_up = cx_rand["C_upper_pct"] if cx_rand["C_upper_pct"] is not None else rd_lo
    d_lo  = fp_lo - rd_up
    d_up  = fp_up - rd_lo
    if d_lo > 0:   verdict = "FP_definitely_better"
    elif d_up < 0: verdict = "Random_definitely_better"
    else:          verdict = "indistinguishable"
    return {"delta_lower": jf(d_lo), "delta_upper": jf(d_up), "verdict": verdict}


def compute_exposure_efficiency(rows_fp: list, rows_rand: list,
                                 b_ref_s: float, s_ref_s: float,
                                 targets: list | None = None) -> dict:
    """
    At each target % of admitted workload, compute E_B and E_S for FP vs random.
    E_B = (B(lambda) - B_ref) / syn_node_hours  [h/node-h]
    E_S = (S(lambda) - S_ref) / syn_node_hours  [C*h/node-h]
    Negative delta -> FP is thermally cheaper per unit of admitted compute.
    """
    if targets is None:
        targets = EFFICIENCY_TARGETS

    def eff_at(rows, tgt):
        cands = [r for r in rows
                 if r.get("syn_node_hours", 0) > 0 and not r.get("invariant_violated")]
        if not cands:
            return None
        r = min(cands, key=lambda x: abs(x["capacity_unlock_pct"] - tgt))
        nh = r["syn_node_hours"]
        return {
            "actual_pct": jf(r["capacity_unlock_pct"]),
            "lambda_val": jf(r.get("lambda_val")),
            "syn_node_hours": jf(nh),
            "E_B": jf((r["B_primary_h"] - b_ref_s) / nh),
            "E_S": jf((r.get("S_primary_Cdoth", 0) - s_ref_s) / nh),
        }

    result = {}
    for tgt in targets:
        fp   = eff_at(rows_fp,   tgt)
        rand = eff_at(rows_rand, tgt)
        dEB  = jf(fp["E_B"] - rand["E_B"]) if (fp and rand) else None
        dES  = jf(fp["E_S"] - rand["E_S"]) if (fp and rand) else None
        result[str(int(tgt))] = {
            "fp_E_B":  fp["E_B"]   if fp   else None,
            "fp_E_S":  fp["E_S"]   if fp   else None,
            "fp_syn_node_hours":   fp["syn_node_hours"]   if fp   else None,
            "rand_E_B": rand["E_B"] if rand else None,
            "rand_E_S": rand["E_S"] if rand else None,
            "rand_syn_node_hours": rand["syn_node_hours"] if rand else None,
            "delta_E_B": dEB, "delta_E_S": dES,
            "fp_lambda": fp["lambda_val"] if fp else None,
        }
    return result


# ══════════════════════════════════════════════════════════════════════
# [14] Main MC loop
# ══════════════════════════════════════════════════════════════════════

# [14] Main MC loop

# ── Threshold provenance assertion (must pass before evaluation begins) ────
_thr_audit_path = OUT_DIR / "m4_threshold_audit.json"
print(f"\n{'='*70}")
print("THRESHOLD PROVENANCE")
print(f"{'='*70}")
if _thr_audit_path.exists():
    _thr_audit = json.load(open(_thr_audit_path))
    _fpop = _thr_audit["full_population"]
    print(f"  T_THR_PRIMARY (code):  {T_THR_PRIMARY:.4f} C")
    print(f"  Full-population p95:   {_fpop['p95_C']:.4f} C  (n={_fpop['n_contributing_jobs']:,} jobs,"
          f"  {_fpop['n_node_job_pairs']:,} node-job pairs)")
    print(f"  Inclusion rule:        {_fpop['selection_rule']}")
    print(f"  Audit verdict:         {_thr_audit['verdict']}")
    assert abs(_fpop['p95_C'] - T_THR_PRIMARY) < 0.01, (
        f"STOP: threshold mismatch: full_pop_p95={_fpop['p95_C']} C "
        f"vs T_THR_PRIMARY={T_THR_PRIMARY} C. Fix before evaluation.")
    print(f"  PROVENANCE OK: full-population p95 == T_THR_PRIMARY")
else:
    print(f"  WARNING: audit file not found at {_thr_audit_path}")
    print(f"  Proceeding with T_THR_PRIMARY={T_THR_PRIMARY} C from code constant.")
print(f"{'='*70}\n")

# ── FP-spread policy freeze summary ────────────────────────────────────────
print(f"{'='*70}")
print("FP-SPREAD POLICY FREEZE")
print(f"{'='*70}")
print(f"  Policy: full_fp_spread (fp_spread_cap_10)")
print(f"  Rule:   balance concurrent cohort-node occupancy across cabinets,")
print(f"          then select lowest-FA_2024 node in chosen cabinet.")
print(f"          Iterative within each job (k nodes selected one at a time).")
print(f"  Inputs: eligibility, frozen FA_2024, frozen topology, cab_active_count snapshot.")
print(f"  NOT used: realized mean_power, ppn, future temperatures, residuals, fitted weights.")
print(f"  Dev set:    scenarios 0..{FP_SPREAD_DEV_N-1} (N={FP_SPREAD_DEV_N})")
print(f"  Held-out:   scenarios {FP_SPREAD_DEV_N}..{N_SCENARIOS-1} (N={N_SCENARIOS-FP_SPREAD_DEV_N})")
print(f"{'='*70}\n")

n_extra_main = int(np.ceil((LAMBDA_MAX     - 1.0) * n_base))
n_extra_max  = int(np.ceil((LAMBDA_MAX_EXT - 1.0) * n_base))
print(f"\nSynthetic pool: main={n_extra_main} jobs (lam<=2), ext={n_extra_max} jobs (lam<=4)")

master_rng = np.random.default_rng(SCENARIO_SEED)
scen_seeds = [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
wl_seeds   = [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
pol_seeds  = {p: [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
              for p in POLICY_IDS}

_design_hash = hashlib.sha256(json.dumps({
    "BETA_F_FROZEN": BETA_F_FROZEN, "T_THR_PRIMARY": T_THR_PRIMARY,
    "N_SCENARIOS": N_SCENARIOS, "SCENARIO_SEED": SCENARIO_SEED,
    "WORKLOAD_SEED": WORKLOAD_SEED, "LAMBDA_SWEEP": LAMBDA_SWEEP,
    "LAMBDA_SWEEP_EXT": LAMBDA_SWEEP_EXT, "POLICY_IDS": POLICY_IDS,
    "N_BINS": N_BINS, "TARGET_PP": TARGET_PP, "N_REFINE_GRID": N_REFINE_GRID,
    "FP_SPREAD_DEV_N": FP_SPREAD_DEV_N,
}, sort_keys=True).encode()).hexdigest()[:16]
print(f"Design hash: {_design_hash}  (freeze verification)")

_ckpt = read_checkpoint(_design_hash)
_completed_scenarios: dict[int, dict] = {}
if _ckpt:
    for sr in _ckpt.get("scenario_results", []):
        _completed_scenarios[sr["scenario_idx"]] = sr
    print(f"  Resuming: {len(_completed_scenarios)} scenarios already done")

scenario_results: list[dict] = []
smoke_ok = False

print(f"\n{'='*70}")
print(f"Running {N_SCENARIOS} scenarios x {len(LAMBDA_SWEEP)} lambdas x {len(POLICY_IDS)} policies")
print(f"{'='*70}")

for s_idx in range(N_SCENARIOS):
    if s_idx == 0:
        print(f"\n--- SMOKE TEST: scenarios 0-{N_SMOKE-1} ---")

    # Resume from checkpoint if available
    if s_idx in _completed_scenarios:
        scenario_results.append(_completed_scenarios[s_idx])
        print(f"\nScenario {s_idx+1}/{N_SCENARIOS}  (seed={scen_seeds[s_idx]})  [resumed]")
        if s_idx == N_SMOKE - 1:
            smoke_ok = True
        continue

    t_scen = time.time()
    print(f"\nScenario {s_idx+1}/{N_SCENARIOS}  (seed={scen_seeds[s_idx]})")

    # Generate large synthetic pool covering lambda=4.0 (nested prefixes used for all lambdas)
    syn_pool = sample_synthetic_pool(n_extra_max, wl_seeds[s_idx])
    assert len(syn_pool) == n_extra_max, f"Pool size mismatch: {len(syn_pool)} != {n_extra_max}"

    scen_rng  = np.random.default_rng(scen_seeds[s_idx])
    job_perms = generate_job_perms(syn_pool, scen_rng)

    B_ref_s, S_ref_s = compute_B_S_ref_s(job_perms, T_THR_PRIMARY)
    print(f"    B_ref_s (primary {T_THR_PRIMARY}C): {B_ref_s:.2f} h   S_ref_s: {S_ref_s:.4f} C*h")

    scen_rows: dict[str, list] = {p: [] for p in POLICY_IDS}

    # --- Main lambda sweep [1.0 .. LAMBDA_MAX] ---
    for lam in LAMBDA_SWEEP:
        n_syn = int(round((lam - 1.0) * n_base))
        syn_sub = (syn_pool.iloc[:n_syn].copy() if n_syn > 0
                   else pd.DataFrame(columns=list(syn_pool.columns)))

        hdr_printed = False
        for pol_name in POLICY_IDS:
            base_pol, is_marginal = POLICY_MAP[pol_name]
            t_pol = time.time()
            try:
                res = capacity_replay_m4(
                    syn_sub, base_pol, lam,
                    policy_seed=pol_seeds[pol_name][s_idx],
                    job_perms=job_perms,
                    marginal=is_marginal,
                )
            except AssertionError as exc:
                print(f"    lam={lam:.2f} {pol_name}: INVARIANT VIOLATED -- {exc}")
                res = {
                    "lambda_val": lam, "policy": pol_name,
                    "invariant_violated": True,
                    "capacity_unlock_pct": (n_syn / n_base * 100.0) if n_base > 0 else 0.0,
                    "B_primary_h": float("nan"), "S_primary_Cdoth": float("nan"),
                    "B_secondary_h": float("nan"), "B_cab_ratio": float("nan"),
                }
            scen_rows[pol_name].append(res)
            if not hdr_printed:
                print(f"    lam={lam:.2f} N_syn={n_syn}")
                hdr_printed = True
            if not res.get("invariant_violated"):
                br = res["B_primary_h"] / max(B_ref_s, 1e-9)
                print(f"      {pol_name:16s}: C={res['capacity_unlock_pct']:5.1f}%  "
                      f"B/Bref={br:.4f}  Bcab={res.get('B_cab_ratio', float('nan')):.4f}  "
                      f"drops={res.get('n_drop_physical',0)}/"
                      f"{res.get('n_drop_cap',0)}/{res.get('n_drop_la',0)}"
                      f"  ({time.time()-t_pol:.0f}s)")

    # --- Compute initial crossings ---
    crossings: dict[str, dict] = {}
    for pol_name in POLICY_IDS:
        crossings[pol_name] = classify_crossing(
            scen_rows[pol_name], B_ref_s, S_ref_s, B_cab_hist)

    # --- Extend sweep for right-censored primary policies ---
    primary_policies_to_extend = ["full_random", "full_fp", "marginal_random", "marginal_fp"]
    for pol_name in primary_policies_to_extend:
        if not crossings[pol_name]["right_censored"]:
            continue
        print(f"    [ext] {pol_name} right-censored at lam={LAMBDA_MAX} -- extending...")
        base_pol, is_marginal = POLICY_MAP[pol_name]
        for lam_ext in LAMBDA_SWEEP_EXT:
            n_syn = int(round((lam_ext - 1.0) * n_base))
            if n_syn > len(syn_pool):
                print(f"    [ext] {pol_name}: pool exhausted at lam={lam_ext:.2f}")
                break
            syn_sub = syn_pool.iloc[:n_syn].copy()
            t_pol = time.time()
            try:
                res = capacity_replay_m4(
                    syn_sub, base_pol, lam_ext,
                    policy_seed=pol_seeds[pol_name][s_idx],
                    job_perms=job_perms,
                    marginal=is_marginal,
                )
            except AssertionError as exc:
                print(f"    [ext] lam={lam_ext:.2f} {pol_name}: INVARIANT -- {exc}")
                res = {"lambda_val": lam_ext, "policy": pol_name,
                       "invariant_violated": True,
                       "capacity_unlock_pct": (n_syn / n_base * 100.0),
                       "B_primary_h": float("nan"), "S_primary_Cdoth": float("nan"),
                       "B_cab_ratio": float("nan")}
            scen_rows[pol_name].append(res)
            if not res.get("invariant_violated"):
                br = res["B_primary_h"] / max(B_ref_s, 1e-9)
                print(f"    [ext] lam={lam_ext:.2f} {pol_name}: C={res['capacity_unlock_pct']:.1f}%  "
                      f"B/Bref={br:.4f}  ({time.time()-t_pol:.0f}s)")
            crossings[pol_name] = classify_crossing(
                scen_rows[pol_name], B_ref_s, S_ref_s, B_cab_hist)
            if not crossings[pol_name]["right_censored"]:
                print(f"    [ext] {pol_name}: crossing found at lam={lam_ext:.2f}")
                break
        if crossings[pol_name]["right_censored"]:
            print(f"    [ext] {pol_name}: still right-censored at lam={LAMBDA_MAX_EXT}")

    # --- Adaptive refinement for exact_bracket cases with gap > TARGET_PP ---
    print("    [refine] Checking brackets...")
    for pol_name in POLICY_IDS:
        cx = crossings[pol_name]
        if cx["status"] == "exact_bracket" and cx["C_upper_pct"] is not None:
            gap = cx["C_upper_pct"] - cx["C_lower_pct"]
            if gap > TARGET_PP:
                base_pol, is_marginal = POLICY_MAP[pol_name]
                cx_ref, extra = refine_crossing_bracket(
                    cx, pol_name, base_pol, is_marginal,
                    job_perms, pol_seeds[pol_name][s_idx],
                    syn_pool, n_base,
                    B_ref_s, S_ref_s,
                    scen_rows[pol_name],
                    target_pp=TARGET_PP)
                crossings[pol_name] = cx_ref
                scen_rows[pol_name].extend(extra)

    # --- Paired interval: FP vs Random (full and marginal) ---
    pi_full = compute_paired_interval(crossings["full_fp"],     crossings["full_random"])
    pi_marg = compute_paired_interval(crossings["marginal_fp"], crossings["marginal_random"])

    # --- Exposure efficiency for marginal policies ---
    eff_marg = compute_exposure_efficiency(
        scen_rows["marginal_fp"], scen_rows["marginal_random"],
        B_ref_s, S_ref_s)

    # --- Smoke test invariants (first N_SMOKE scenarios) ---
    if s_idx < N_SMOKE:
        for pol_name in POLICY_IDS:
            rows_lam1 = [r for r in scen_rows[pol_name]
                         if abs(r.get("lambda_val", -1) - 1.0) < 1e-9]
            if rows_lam1 and not rows_lam1[0].get("invariant_violated"):
                r1 = rows_lam1[0]
                assert r1.get("n_base_unserved", 0) == 0, \
                    f"Smoke: n_base_unserved={r1['n_base_unserved']} at lam=1.0 pol={pol_name}"
                if not POLICY_MAP[pol_name][1]:  # only check capacity=0 for non-marginal at lam=1
                    c1 = r1["capacity_unlock_pct"]
                    assert abs(c1) < 1e-6, \
                        f"Smoke: C={c1:.4f} at lam=1.0 pol={pol_name} (expect 0)"

    if s_idx == N_SMOKE - 1:
        smoke_ok = True
        print(f"\n  *** SMOKE TEST PASSED (scenarios 1-{N_SMOKE}) ***")
        if SMOKE_ONLY:
            print(f"  SMOKE_ONLY=True -- reporting 5-scenario results and exiting.")

    # --- Print crossing summary ---
    print("    Crossings:")
    for pol_name in POLICY_IDS:
        cx = crossings[pol_name]
        print(f"      {pol_name:18s}: status={cx['status']:15s}  "
              f"C_lower={cx['C_lower_pct']:.2f}%  "
              f"C_upper={str(cx['C_upper_pct']):<8s}  "
              f"binding={cx['first_binding_constraint']}")
    pi_full_str = f"[{pi_full['delta_lower']:+.2f},{pi_full['delta_upper']:+.2f}] pp  {pi_full['verdict']}"
    pi_marg_str = f"[{pi_marg['delta_lower']:+.2f},{pi_marg['delta_upper']:+.2f}] pp  {pi_marg['verdict']}"
    print(f"    Paired(FP-Rand) full:     {pi_full_str}")
    print(f"    Paired(FP-Rand) marginal: {pi_marg_str}")

    # Paired delta: full_fp - full_random (for reporting; censoring-aware at aggregate stage)
    cx_fp   = crossings["full_fp"]
    cx_rand = crossings["full_random"]
    delta_fp_rand = jf(cx_fp["C_lower_pct"] - cx_rand["C_lower_pct"])

    cx_mfp  = crossings["marginal_fp"]
    cx_mrand= crossings["marginal_random"]
    delta_marg = jf(cx_mfp["C_lower_pct"] - cx_mrand["C_lower_pct"])

    scenario_results.append({
        "scenario_idx"        : s_idx,
        "scen_seed"           : scen_seeds[s_idx],
        "wl_seed"             : wl_seeds[s_idx],
        "B_ref_s_primary_h"   : jf(B_ref_s),
        "S_ref_s_primary"     : jf(S_ref_s),
        "lambda_rows"         : {p: scen_rows[p] for p in POLICY_IDS},
        "crossings"           : crossings,
        "delta_C_lower_full_fp_minus_random"  : delta_fp_rand,
        "delta_C_lower_marg_fp_minus_random"  : delta_marg,
        "paired_interval_full"    : pi_full,
        "paired_interval_marginal": pi_marg,
        "exposure_efficiency"     : eff_marg,
        "elapsed_s"           : round(time.time() - t_scen, 1),
    })

    # Write checkpoint after every scenario
    write_checkpoint({
        "design_hash"     : _design_hash,
        "scenario_results": scenario_results,
    })

    if SMOKE_ONLY and smoke_ok:
        break  # Exit loop after smoke gate

assert smoke_ok, "Smoke test never passed"

if SMOKE_ONLY:
    print("\n" + "="*70)
    print(f"SMOKE RESULTS ({N_SMOKE} scenarios)")
    print("="*70)
    print(f"\n  {'Policy':<20} {'status':>15} {'C_lower':>10} {'C_upper':>10}")
    print(f"  {'-'*60}")
    for pol_name in POLICY_IDS:
        vals_lo = [s["crossings"][pol_name]["C_lower_pct"] for s in scenario_results]
        vals_st = [s["crossings"][pol_name]["status"] for s in scenario_results]
        rc_count = sum(1 for s in vals_st if s == "right_censored")
        med_lo = float(np.median(vals_lo))
        print(f"  {pol_name:<20} rc={rc_count}/{len(vals_lo)}  "
              f"median_C_lower={med_lo:.2f}%")
    print(f"\nFor full {N_SCENARIOS}-scenario run: set M4_SMOKE_ONLY=0")

    print("\n  Paired intervals (refined, FP vs Random):")
    print(f"  {'Sc':>3}  {'Rand [lo,up]':>16}  {'FP [lo,up]':>14}  {'Delta [lo,up]':>16}  {'Verdict':>22}")
    for sr in scenario_results:
        pi = sr["paired_interval_full"]
        cx_fp = sr["crossings"]["full_fp"]; cx_r = sr["crossings"]["full_random"]
        fp_up = cx_fp['C_upper_pct'] if cx_fp['C_upper_pct'] is not None else cx_fp['C_lower_pct']
        rd_up = cx_r['C_upper_pct']  if cx_r['C_upper_pct']  is not None else cx_r['C_lower_pct']
        print(f"  {sr['scenario_idx']+1:>3}  [{cx_r['C_lower_pct']:>4.1f},{rd_up:>5.1f}]%        "
              f"[{cx_fp['C_lower_pct']:>4.1f},{fp_up:>5.1f}]%    "
              f"[{pi['delta_lower']:>+5.2f},{pi['delta_upper']:>+5.2f}] pp   {pi['verdict']}")

    print("\n  Marginal exposure efficiency (median dE_B across scenarios, by target):")
    for tgt_key in ["5", "10", "20"]:
        dEB_vals = [sr["exposure_efficiency"][tgt_key]["delta_E_B"]
                    for sr in scenario_results
                    if sr.get("exposure_efficiency") and tgt_key in sr["exposure_efficiency"]
                    and sr["exposure_efficiency"][tgt_key]["delta_E_B"] is not None]
        if dEB_vals:
            print(f"    @+{tgt_key:>2}%: median dE_B={np.median(dEB_vals):.4f}  (fp thermally {'cheaper' if np.median(dEB_vals)<0 else 'costlier'} per syn node-hour)")

    import sys; sys.exit(0)

# ══════════════════════════════════════════════════════════════════════
# [15] Availability sensitivity (Random vs FP; N_AVAIL_SCENARIOS)
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"Availability sensitivity ({N_AVAIL_SCENARIOS} scenarios x "
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

        pol_rows_f: dict[str, list] = {"full_random": [], "full_fp": []}
        for pol_name in ["full_random", "full_fp"]:
            base_pol, _ = POLICY_MAP[pol_name]
            for lam in LAMBDA_SWEEP:
                n_syn = int(round((lam - 1.0) * n_base))
                syn_sub = syn_pool.iloc[:n_syn].copy() if n_syn > 0 else pd.DataFrame(
                    columns=list(syn_pool.columns))
                try:
                    res = capacity_replay_m4(
                        syn_sub, base_pol, lam,
                        policy_seed=pol_seeds[pol_name][s_idx],
                        job_perms=job_perms_av,
                        avail_nodes=avail_set,
                        marginal=False,
                    )
                    pol_rows_f[pol_name].append(res)
                except AssertionError:
                    pol_rows_f[pol_name].append({
                        "lambda_val": lam,
                        "policy": pol_name,
                        "invariant_violated": True,
                        "capacity_unlock_pct": (n_syn / n_base * 100.0),
                        "B_primary_h": float("nan"),
                        "S_primary_Cdoth": float("nan"),
                        "B_cab_ratio": float("nan"),
                    })

        B_ref_s_av_s, S_ref_s_av_s = compute_B_S_ref_s(job_perms_av, T_THR_PRIMARY)
        cr_rand = classify_crossing(pol_rows_f["full_random"], B_ref_s_av_s, S_ref_s_av_s, B_cab_hist)
        cr_fp   = classify_crossing(pol_rows_f["full_fp"],     B_ref_s_av_s, S_ref_s_av_s, B_cab_hist)
        dc = jf(cr_fp["C_lower_pct"] - cr_rand["C_lower_pct"])
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
    right_cens = sum(1 for v in c_up_vals if v is None)
    pol_agg    = {}
    pol_agg.update(agg(c_lo_vals,  "C_lower"))
    pol_agg.update(agg(c_up_vals,  "C_upper"))
    pol_agg["right_censored_count"] = right_cens
    policy_summary[pol] = pol_agg

    _med = pol_agg.get("C_lower_median")
    _p5  = pol_agg.get("C_lower_p5")
    _p95 = pol_agg.get("C_lower_p95")
    print(f"\n  {pol}: C_lower median={_med:.2f}%  "
          f"p5={_p5:.2f}%  p95={_p95:.2f}%  "
          f"right_censored={right_cens}")

# Censoring summary
print("\nCensoring summary:")
for pol_name in POLICY_IDS:
    statuses = [s["crossings"][pol_name]["status"] for s in scenario_results]
    rc = sum(1 for st in statuses if st == "right_censored")
    lb = sum(1 for st in statuses if st == "left_boundary")
    ex = sum(1 for st in statuses if st == "exact_bracket")
    print(f"  {pol_name:<20}: exact={ex}  left_boundary={lb}  right_censored={rc}")

# Paired delta: full_fp vs full_random
dc_full = []
for s in scenario_results:
    c_fp   = s["crossings"]["full_fp"]["C_lower_pct"]
    c_rand = s["crossings"]["full_random"]["C_lower_pct"]
    if c_fp is not None and c_rand is not None:
        dc_full.append(c_fp - c_rand)
dc_full_arr = np.array(dc_full, dtype=float)

# Paired delta: marginal_fp vs marginal_random
dc_marg = []
for s in scenario_results:
    c_fp   = s["crossings"]["marginal_fp"]["C_lower_pct"]
    c_rand = s["crossings"]["marginal_random"]["C_lower_pct"]
    if c_fp is not None and c_rand is not None:
        dc_marg.append(c_fp - c_rand)
dc_marg_arr = np.array(dc_marg, dtype=float)

print(f"\n  Paired dC_lower (full_fp - full_random): "
      f"median={np.median(dc_full_arr):.2f} pp  "
      f"mean={np.mean(dc_full_arr):.2f} pp  "
      f"p5={np.percentile(dc_full_arr,5):.2f} pp  "
      f"p95={np.percentile(dc_full_arr,95):.2f} pp  "
      f"n={len(dc_full_arr)}")

if len(dc_marg_arr) > 0:
    print(f"  Paired dC_lower (marginal_fp - marginal_random): "
          f"median={np.median(dc_marg_arr):.2f} pp  "
          f"mean={np.mean(dc_marg_arr):.2f} pp  "
          f"n={len(dc_marg_arr)}")

# Bootstrap CI for paired MEDIAN (primary statistic) -- full_fp vs full_random
dc_arr = dc_full_arr
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
print(f"  Bootstrap 95% CI for MEDIAN dC_lower (full): [{boot_ci_lo:.2f}, {boot_ci_hi:.2f}] pp  (primary)")
print(f"  Bootstrap 95% CI for mean  dC_lower (full): [{boot_mean_ci_lo:.2f}, {boot_mean_ci_hi:.2f}] pp  (secondary)")
print(f"  Sign counts: +={n_pos}  0={n_zero}  -={n_neg}  "
      f"win_rate={100*n_pos/len(dc_arr):.1f}%")

paired_stats = {
    "primary_statistic" : "paired median dC_lower,s = C_lower,full_fp,s - C_lower,full_random,s",
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

# Bootstrap CI for marginal pair
if len(dc_marg_arr) > 0:
    boot_rng_m   = np.random.default_rng(BOOTSTRAP_SEED + 2)
    boot_meds_m  = [float(np.median(boot_rng_m.choice(dc_marg_arr, size=len(dc_marg_arr), replace=True)))
                    for _ in range(N_BOOTSTRAP)]
    boot_ci_m_lo = float(np.percentile(boot_meds_m, 2.5))
    boot_ci_m_hi = float(np.percentile(boot_meds_m, 97.5))
    n_pos_m  = int((dc_marg_arr > 0).sum())
    n_zero_m = int((dc_marg_arr == 0).sum())
    n_neg_m  = int((dc_marg_arr < 0).sum())
    paired_stats_marginal = {
        "primary_statistic" : "paired median dC_lower,s = C_lower,marg_fp,s - C_lower,marg_random,s",
        "n_scenarios"       : int(len(dc_marg_arr)),
        "median_pp"         : jf(float(np.median(dc_marg_arr))),
        "mean_pp"           : jf(float(np.mean(dc_marg_arr))),
        "n_positive"        : n_pos_m,
        "n_zero"            : n_zero_m,
        "n_negative"        : n_neg_m,
        "win_rate_pct"      : jf(float(n_pos_m / len(dc_marg_arr) * 100)),
        "bootstrap_median_ci_95_lo": jf(boot_ci_m_lo),
        "bootstrap_median_ci_95_hi": jf(boot_ci_m_hi),
    }
else:
    paired_stats_marginal = {"n_scenarios": 0}

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
        "B_ref_s_primary_h"       : s.get("B_ref_s_primary_h") or s.get("B_ref_s_primary"),
        "S_ref_s_primary"         : s.get("S_ref_s_primary"),
        "lambda_rows"             : serialize_lambda_rows(s["lambda_rows"]),
        "crossings"               : {p: {k: _clean_val(v) for k, v in cx.items()}
                                     for p, cx in s["crossings"].items()},
        "delta_C_lower_full_fp_minus_random": s.get("delta_C_lower_full_fp_minus_random"),
        "delta_C_lower_marg_fp_minus_random": s.get("delta_C_lower_marg_fp_minus_random"),
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
        "LAMBDA_MAX_EXT"   : LAMBDA_MAX_EXT,
        "LAMBDA_SWEEP_EXT" : LAMBDA_SWEEP_EXT,
        "N_BOOTSTRAP"      : N_BOOTSTRAP,
        "u_max_formula"    : "(1 + DELTA_CAP) * lambda_val * hist_fleet_avg",
        "n_extra_main"     : n_extra_main,
        "n_extra_max"      : n_extra_max,
    },
    "design_notes"    : {
        "topology"       : "fleet_node_topology.csv (Gate C corrected); no str(node_list).split()",
        "cabinet_power"  : "per-cabinet P^99 from cabinet_power_envelopes.json (Gate C)",
        "B_ref_s"        : "model-identity replay with scenario residual permutation at historical assignments",
        "C_lower_primary": "B_primary_ratio = B_policy_h / B_ref_s; last lambda before ratio > 1",
        "policies"       : {
            "full_random"    : "full-replacement: random selection, utilisation cap u_max",
            "full_fp"        : "full-replacement: lowest FA_2024 first, same cap",
            "full_loc"       : "full-replacement: lowest position-mean FA (chassis/slot/board/node_pos), same cap",
            "full_compact"   : "full-replacement: greedy cabinet-minimising selection, same cap",
            "marginal_random": "marginal: base jobs use historical nodes; synthetic jobs use random selection",
            "marginal_fp"    : "marginal: base jobs use historical nodes; synthetic jobs use fp selection",
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
    "policy_summary"          : policy_summary,
    "paired_full_fp_vs_random": paired_stats,
    "paired_marginal_fp_vs_random": paired_stats_marginal,
    "scenario_results"        : scen_out,
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
