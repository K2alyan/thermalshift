#!/usr/bin/env python3
"""
Gate F: Dynamic Feasible-Choice Sensitivity  (r1_gate_f_run.py)

THERMALSHIFT_DATA_DIR must point to the directory containing:
    frontier-completed-job-info.parquet

Produces gate_f_dev_results.json (sc0-4). Do NOT run sc5-29 until the
preflight gate passes (§6, §7 of GATE_F_DESIGN.md).

Implementation sequence (see GATE_F_DESIGN.md §14):
  Step 2: unrestricted sc0  — metric-for-metric vs authoritative JSONs
  Step 3: r=1 sc0           — hard inductive negative control assertion
  Step 4: unrestricted sc0-4
  Step 5: r=1 sc0-4
  Step 6: restricted ratios sc0-4
  Then commit SHA; only then run held-out sc5-29.
"""

import sys, io, os, json, time, heapq, math, hashlib, statistics, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

# ── Paths (identical to r1_m4_fair_baselines.py) ──────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
P1_DIR    = REPO_ROOT / "artifacts" / "phase1" / "analysis"
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR   = REV1_DIR / "results"
TABLE_DIR = REV1_DIR / "tables"
DATA_DIR  = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

# ── Frozen M4 constants (identical to r1_m4_fair_baselines.py) ────────────────
BETA_F_FROZEN    = 1.12484352
T_THR_PRIMARY    = 63.625
T_THR_SECONDARY  = 60.602770562770566
DELTA_CAP        = 0.10
N_BINS           = 5
N_SCENARIOS      = 30
SCENARIO_SEED    = 42
LAMBDA_SWEEP     = [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40,
                    1.50, 1.55, 1.60, 1.70, 1.80, 1.90, 2.00]
LAMBDA_MAX       = 2.00
LAMBDA_MAX_EXT   = 4.00
LAMBDA_SWEEP_EXT = [2.25, 2.50, 3.00, 3.50, 4.00]
TARGET_PP        = 0.50
N_REFINE_GRID    = 3

# Full 7-policy list required to replicate the v5 master_rng seed sequence.
POLICY_IDS = ["full_random", "full_fp", "full_loc", "full_compact",
              "marginal_random", "marginal_fp", "full_fp_spread"]

# ── Gate F constants ───────────────────────────────────────────────────────────
_ALL_RATIOS     = [1.0, 1.25, 1.5, 2.0, 4.0, 8.0, None]   # None = unrestricted
_ENV_RATIOS     = os.environ.get("GATE_F_RATIOS_ONLY", "")  # e.g. "unrestricted" or "1.0,unrestricted"
if _ENV_RATIOS:
    _keys = [x.strip() for x in _ENV_RATIOS.split(",")]
    GATE_F_RATIOS = [None if k == "unrestricted" else float(k) for k in _keys]
else:
    GATE_F_RATIOS = _ALL_RATIOS
GATE_F_POLICIES = ["full_random", "full_fp", "full_loc", "full_fp_spread"]
GATE_F_ALG = {   # full policy name -> base algorithm name
    "full_random"    : "random",
    "full_fp"        : "fp",
    "full_loc"       : "loc",
    "full_fp_spread" : "fp_spread",
}
GATE_F_TRACE_R1          = int(os.environ.get("GATE_F_TRACE_R1", "0"))
GATE_F_REQUIRE_CLEAN_GIT = int(os.environ.get("GATE_F_REQUIRE_CLEAN_GIT", "0"))
N_DEV         = int(os.environ.get("GATE_F_N_DEV", "5"))    # sc0-N_DEV-1
N_FIRST       = int(os.environ.get("GATE_F_N_FIRST", "0"))  # start at scenario N_FIRST

# Output filename encodes scenario range and ratio subset so partial runs never
# overwrite each other (e.g. step-2 unrestricted-sc0 vs step-3 r1-sc0).
_scen_tag  = f"sc{N_FIRST}-{N_FIRST + N_DEV - 1}"
_ratio_tag = (_ENV_RATIOS.replace(",", "_").replace(".", "p").replace("unrestricted", "unr")
              if _ENV_RATIOS else "all")
OUT_FILE   = OUT_DIR / f"gate_f_{_scen_tag}_{_ratio_tag}.json"
PREF_FILE  = OUT_DIR / "gate_f_preflight.json"

# ── Utilities ──────────────────────────────────────────────────────────────────
def jf(v):
    if v is None: return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f

def _col_to_dt64ms(series):
    s = pd.to_datetime(series, utc=True)
    return s.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ms]")

def _rec_ts_ms(r):
    v = r["t_s"]
    return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))

def _rec_te_ms(r):
    v = r["t_e"]
    return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))

def pctile(vals, p):
    if not vals: return None
    return float(np.percentile(vals, p))

def _git_provenance() -> dict:
    try:
        full  = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
        short = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
        tracked_dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=str(REPO_ROOT), text=True).strip())
        untracked_lines = [
            x for x in subprocess.check_output(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=str(REPO_ROOT), text=True).strip().splitlines() if x
        ]
        untracked_count   = len(untracked_lines)
        untracked_present = untracked_count > 0
    except Exception:
        full = short = "unknown"
        tracked_dirty = untracked_present = None
        untracked_count = None
    return {
        "git_commit_full"      : full,
        "git_commit_short"     : short,
        "git_tracked_dirty"    : tracked_dirty,
        "git_untracked_present": untracked_present,
        "git_untracked_count"  : untracked_count,
    }

# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING — identical to r1_m4_fair_baselines.py / canonical scripts
# ══════════════════════════════════════════════════════════════════════════════
# ── Provenance (captured before data loading so dirty-check fires early) ──────
_PROV = _git_provenance()
if GATE_F_REQUIRE_CLEAN_GIT and _PROV.get("git_tracked_dirty"):
    sys.exit(
        f"GATE_F_REQUIRE_CLEAN_GIT=1 but working tree is dirty "
        f"(HEAD={_PROV['git_commit_short']}). "
        f"Commit or stash all changes before running held-out scenarios."
    )

print("\nGate F: Dynamic Feasible-Choice Sensitivity")
print("=" * 70)
t_script = time.time()

print("\n[0] Loading inputs ...")
fp_df    = pd.read_parquet(P1_DIR / "phase3a_fingerprint_2024.parquet")
test_df  = pd.read_parquet(P1_DIR / "phase3a_test_set.parquet")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)

fp_df.index.name = "node"
cohort_set   = set(fp_df.index)
FA_dict      = fp_df["FA_2024"].to_dict()
cohort_list  = sorted(cohort_set)
n_cohort     = len(cohort_list)
_F_vals_arr  = np.array(list(FA_dict.values()), dtype=float)
F_COOL10_THR = float(np.percentile(_F_vals_arr, 10))
print(f"    fp nodes: {n_cohort}  test rows: {len(test_df):,}  all jobs: {len(all_jobs):,}")

print("\n[1] Building node-to-cabinet map ...")
fleet_topo   = pd.read_csv(TABLE_DIR / "fleet_node_topology.csv")
node_to_cab  = dict(zip(fleet_topo["hostname"].values,
                        fleet_topo["cabinet"].values.astype(int)))
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
    zip(fp_topo["hostname"].values, fp_topo["FA_loc"].values))
_glob_mean  = float(np.nanmean(list(LOC_FA_dict.values())))
LOC_FA_dict = {k: (v if not np.isnan(v) else _glob_mean)
               for k, v in LOC_FA_dict.items()}

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
job_agg  = job_agg.merge(meta, on="job_idx", how="left")
job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)
jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)
n_base      = len(jobs_sorted)

def _make_quartile_map(arr, jids):
    cuts = np.percentile(arr, [25, 50, 75])
    q    = (np.digitize(arr, cuts) + 1).clip(1, 4)
    return {int(jid): int(qi) for jid, qi in zip(jids, q)}

_jids             = jobs_sorted["job_idx"].values
job_quartile_ncoh = _make_quartile_map(jobs_sorted["n_cohort"].values, _jids)
job_quartile_nc   = _make_quartile_map(jobs_sorted["node_count"].fillna(0).values, _jids)
job_quartile_ppn  = _make_quartile_map(jobs_sorted["power_per_node"].fillna(0).values, _jids)
job_quartile_rt   = _make_quartile_map(jobs_sorted["run_time"].fillna(0).values, _jids)
job_quartile      = job_quartile_ncoh

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
print(f"    {n_base} base test jobs  hist_fleet_avg={hist_fleet_avg:.3f}h")

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
    k_j     = len(grp_s)
    if k_j >= N_BINS:
        try:
            bins = pd.qcut(grp_s["F_2024"], q=N_BINS, labels=False,
                           duplicates="drop").values.astype(int)
        except Exception:
            bins = np.zeros(k_j, dtype=int)
    else:
        bins = np.zeros(k_j, dtype=int)
    job_residuals[jid] = (res_arr, bins)
jobs_sorted["alpha_j"] = jobs_sorted["job_idx"].astype(int).map(alpha_map)
print(f"    {len(job_residuals)} jobs with residuals")

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
hist_starts_ms = _col_to_dt64ms(jobs_sorted["start_time"]).astype(np.int64)
hist_ends_ms   = _col_to_dt64ms(jobs_sorted["end_time"]).astype(np.int64)
hist_k_arr     = jobs_sorted["n_cohort"].values.astype(int)
hist_jids_arr  = jobs_sorted["job_idx"].values.astype(int)
print(f"    Done  ({time.time()-t0:.1f}s)")

print("\n[8] Precomputing cabinet background power ...")
t0 = time.time()
_all_jids = all_jobs["job_idx_int"].values
_all_Pj   = np.where(all_jobs["mean_power"].isna().values, 0.0,
                     all_jobs["mean_power"].values.astype(float))
_all_nc   = np.maximum(all_jobs["node_count"].values.astype(int), 1)
_all_hl   = all_jobs["host_list"].values
_all_st   = _col_to_dt64ms(all_jobs["start_time"])
_all_et   = _col_to_dt64ms(all_jobs["end_time"])
bg_records: list[dict] = []; cohort_hist_records: list[dict] = []
for jid, P_j, nc, hl, t_s, t_e in zip(_all_jids, _all_Pj, _all_nc, _all_hl, _all_st, _all_et):
    ppn = P_j / nc
    ncc: dict[int, int] = {}; chc: dict[int, int] = {}
    for hn in hl:
        c = node_to_cab.get(hn, -1)
        if c < 0: continue
        if hn in cohort_set: chc[c] = chc.get(c, 0) + 1
        else:                ncc[c] = ncc.get(c, 0) + 1
    if ncc: bg_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": ncc})
    if int(jid) in test_id_set and chc:
        cohort_hist_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": chc})
print(f"    bg_records: {len(bg_records):,}  hist_cohort: {len(cohort_hist_records):,}"
      f"  ({time.time()-t0:.1f}s)")

print("[8b] Pre-sorting background cabinet events ...")
t0 = time.time()
bg_events_sorted: list[tuple] = []
for _r in bg_records:
    _ppn = _r["ppn"]; _ts = int(_r["t_s"].astype("int64")); _te = int(_r["t_e"].astype("int64"))
    for _c, _n in _r["cab_counts"].items():
        _dp = _ppn * _n
        bg_events_sorted.append((_ts, +1, _c, _dp))
        bg_events_sorted.append((_te, -1, _c, _dp))
bg_events_sorted.sort()
print(f"    {len(bg_events_sorted):,} bg events sorted  ({time.time()-t0:.1f}s)")

def sweep_cab_budget_fast(cohort_records, thr):
    coh_ev = []
    for r in cohort_records:
        ppn = r["ppn"]; ts = _rec_ts_ms(r); te = _rec_te_ms(r)
        for c, n in r["cab_counts"].items():
            dp = ppn * n
            coh_ev.append((ts, +1, c, dp)); coh_ev.append((te, -1, c, dp))
    coh_ev.sort()
    P_cab: dict[int, float] = defaultdict(float); last_t: dict[int, int] = {}
    B = 0.0; S = 0.0
    for t, sign, c, dp in heapq.merge(bg_events_sorted, coh_ev):
        if c in last_t and t != last_t[c]:
            dt_h = (t - last_t[c]) / 3_600_000.0
            if dt_h > 0:
                exc = P_cab[c] - thr.get(c, 0.0)
                if exc > 0: B += dt_h; S += dt_h * exc
        P_cab[c] += sign * dp; last_t[c] = t
    return B, S

B_cab_hist, _ = sweep_cab_budget_fast(cohort_hist_records, cab_p99_W)
print(f"    B_cab_hist: {B_cab_hist:.2f} h")

# ── Helper functions (verbatim from M4 / canonical scripts) ───────────────────
def bg_busy_at_ms(t_ms: int) -> frozenset:
    mask = (bg_st_ms <= t_ms) & (bg_et_ms > t_ms)
    return frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

def look_ahead_safe(selected_nodes, t_s_ms: int, t_e_ms: int, cf_busy_ms: dict) -> bool:
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

def sample_synthetic_pool(n_extra: int, seed: int) -> pd.DataFrame:
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
    if diff > 0:   n_per[np.argsort(-probs)[:diff]]   += 1
    elif diff < 0: n_per[np.argsort(n_per)[:(-diff)]] -= 1
    chunks = []
    for sk, n_s in zip(unique_strata, n_per):
        if n_s <= 0: continue
        idxs = rng_s.choice(strat_to_idxs[sk], size=int(n_s), replace=True)
        chunks.append(jobs_sorted.iloc[idxs])
    if not chunks:
        return pd.DataFrame(columns=list(jobs_sorted.columns) + ["is_synthetic", "parent_job_idx"])
    syn = pd.concat(chunks, ignore_index=True)
    jitter = rng_s.uniform(-1800.0, 1800.0, size=len(syn))
    syn["start_time"]     = syn["start_time"] + pd.to_timedelta(jitter, unit="s")
    syn["end_time"]       = syn["start_time"] + pd.to_timedelta(syn["run_time"].values, unit="s")
    syn["is_synthetic"]   = True
    syn["parent_job_idx"] = syn["job_idx"].values.copy()
    syn["job_idx"]           = -(np.arange(len(syn), dtype=np.int64) + 1)
    syn["alpha_j"]           = syn["parent_job_idx"].map(alpha_map)
    syn["generation_ordinal"] = np.arange(len(syn), dtype=np.int64)
    syn = syn.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)
    assert (syn["generation_ordinal"].values == -(syn["job_idx"].values + 1)).all(), \
        "generation_ordinal invariant violated: jid must equal -(gen_ord + 1)"
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

_bref_jids   = jobs_sorted["job_idx"].values.astype(int)
_bref_rt_h   = jobs_sorted["run_time"].fillna(0.0).values.astype(float) / 3600.0
_bref_alpha  = jobs_sorted["alpha_j"].fillna(0.0).values.astype(float)
_bref_hnodes = jobs_sorted["hist_nodes"].values

def compute_B_S_ref_s(job_perms: dict, thr: float) -> tuple:
    B = 0.0; S = 0.0
    for _bi in range(len(_bref_jids)):
        jid     = int(_bref_jids[_bi])
        rt_h    = float(_bref_rt_h[_bi])
        alpha   = float(_bref_alpha[_bi])
        hist_ns = _bref_hnodes[_bi]
        if not hist_ns: continue
        F_arr    = np.array([FA_dict[n] for n in hist_ns], dtype=float)
        res_s, _ = job_residuals[jid]
        perm     = job_perms[jid]
        rank     = np.argsort(np.argsort(F_arr))
        T_hats   = alpha + BETA_F_FROZEN * F_arr + res_s[perm[rank]]
        exc      = T_hats - thr
        B       += rt_h * float((exc > 0).sum())
        S       += rt_h * float(exc.clip(min=0).sum())
    return B, S

# ── Gate F hash helpers (frozen §4.2–§4.4 GATE_F_DESIGN.md) ──────────────────
def choice_priority(scenario_seed: int, event_uid: str, hostname: str) -> tuple:
    key    = scenario_seed.to_bytes(8, "big", signed=False)
    msg    = event_uid.encode("utf-8") + b"\x00" + hostname.encode("utf-8")
    digest = hashlib.blake2b(msg, key=key, digest_size=8).digest()
    return int.from_bytes(digest, "big"), hostname

def gate_f_shortlist(full_eligible, scenario_seed: int, event_uid: str, r, k: int) -> list:
    ordered = sorted(full_eligible, key=lambda h: choice_priority(scenario_seed, event_uid, h))
    m = min(len(ordered), math.ceil(r * k))
    return ordered[:m]

# ── Canonical policy selectors (frozen from canonical scripts) ────────────────
def select_fp_canonical(available, k):
    s = sorted(available, key=lambda n: (FA_dict[n], n))
    return s[:min(k, len(s))]

def select_loc_canonical(available, k):
    s = sorted(available, key=lambda n: (LOC_FA_dict.get(n, 0.0), n))
    return s[:min(k, len(s))]

def select_random_canonical(available, k, rng_local):
    s = sorted(available)
    idx = rng_local.choice(len(s), size=min(k, len(s)), replace=False)
    return [s[i] for i in idx]

def select_fp_spread_canonical(available, k, cab_active_count):
    k = min(k, len(available))
    temp = dict(cab_active_count)
    if k == 0: return []
    if k == len(available): return sorted(available)
    cab_nodes: dict[int, list] = {}
    for n in sorted(available):
        c = fp_cab.get(n, -1)
        cab_nodes.setdefault(c, []).append(n)
    for c in cab_nodes:
        cab_nodes[c].sort(key=lambda n: (FA_dict.get(n, 0.0), n))
    selected = []
    for _ in range(k):
        if not cab_nodes: break
        best_c = min(cab_nodes, key=lambda c: (temp.get(c, 0), c))
        best_n = cab_nodes[best_c].pop(0)
        if not cab_nodes[best_c]: del cab_nodes[best_c]
        selected.append(best_n)
        temp[best_c] = temp.get(best_c, 0) + 1
    return selected

# ══════════════════════════════════════════════════════════════════════════════
# Gate F replay function
# ══════════════════════════════════════════════════════════════════════════════
def capacity_replay_gate_f(syn_subset, policy_name: str, lambda_val: float,
                            policy_seed: int, job_perms: dict,
                            scen_seed: int, r,
                            collect_trace: bool = False) -> dict:
    """
    Run one (policy, lambda, ratio) Gate F scenario.

    policy_name: one of GATE_F_POLICIES ('full_random', etc.)
    r: float for restricted ratios; None for unrestricted (= M4 replay)
    scen_seed: scenario seed; used as BLAKE2b key for Gate F hash (§4.2)
    """
    alg      = GATE_F_ALG[policy_name]
    eligible = cohort_set
    u_max    = (1.0 + DELTA_CAP) * lambda_val * hist_fleet_avg
    n_syn    = len(syn_subset)

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
    _cgen_ord = (combined["generation_ordinal"].values
                 if "generation_ordinal" in combined.columns else None)

    cf_busy_ms: dict[str, int]  = {}
    cf_busy_active: set[str]    = set()
    cf_expire_heap: list        = []
    cf_util: dict[str, float]   = {n: 0.0 for n in eligible}
    cap_exceeded: set[str]      = set()
    eligible_set                = set(eligible)
    available_set               = set(eligible)
    _rng = np.random.default_rng(policy_seed)

    B_primary = 0.0; S_primary = 0.0; B_secondary = 0.0; S_secondary = 0.0
    n_cabs_per_job: list[int] = []
    syn_node_hours = 0.0
    n_syn_admit  = 0
    n_drop_cap   = 0
    n_drop_phys  = 0
    n_drop_la    = 0
    n_base_unserved = 0
    _trace: list = []
    cab_active_count: dict[int, int] = {}
    sum_F_syn = 0.0; n_F_syn = 0
    cool10_nh = 0.0
    cohort_records: list[dict] = []

    # Gate F diagnostics (per eligible event — excludes drops at Stage 1)
    gf_full_counts: list[int]    = []  # |A_full,p|
    gf_exposed_counts: list[int] = []  # |C_p,r|
    gf_k_counts: list[int]       = []  # k (job's node request) per Gate-F-exposed event

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

        # Expire completed nodes
        while cf_expire_heap and cf_expire_heap[0][0] <= t_j_ms:
            _exp_ms, _exp_n = heapq.heappop(cf_expire_heap)
            if cf_busy_ms.get(_exp_n, -1) == _exp_ms:
                cf_busy_active.discard(_exp_n)
                _exp_c = fp_cab.get(_exp_n, -1)
                if _exp_c >= 0 and cab_active_count.get(_exp_c, 0) > 0:
                    cab_active_count[_exp_c] -= 1
                if _exp_n not in cap_exceeded:
                    available_set.add(_exp_n)

        # ── Stage 1: node-level eligibility filter (§4.0, §4.1) ─────────────
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
                    n_drop_phys += 1; _drop_key = "drop_physical"
                else:
                    n_drop_cap += 1; _drop_key = "drop_cap"
                for _strat, _qmap in ((strat_ncoh, job_quartile_ncoh),
                                      (strat_nc,   job_quartile_nc),
                                      (strat_ppn,  job_quartile_ppn),
                                      (strat_rt,   job_quartile_rt)):
                    _q = _qmap.get(parent_jid, 4)
                    _strat[_q]["attempted"] += 1
                    _strat[_q][_drop_key]   += 1
                q_drop[job_quartile.get(parent_jid, 4)] += 1
                if collect_trace:
                    assert _cgen_ord is not None, "generation_ordinal array missing for synthetic event"
                    assert not np.isnan(float(_cgen_ord[_i])), f"generation_ordinal NaN at _i={_i} jid={jid}"
                    _d_uid = f"syn:{scen_seed}:{int(_cgen_ord[_i])}"
                    _d_st  = hashlib.sha256(repr((
                        tuple(sorted(available_set)),
                        tuple(sorted(cap_exceeded)),
                        tuple(sorted(cf_busy_ms.items())),
                        tuple(sorted(cf_util.items())),
                        tuple(sorted(cab_active_count.items())),
                    )).encode()).hexdigest()
                    _trace.append({"uid": _d_uid, "stage1_outcome": _drop_key,
                                   "sel_dig": None, "la_out": None, "state_dig": _d_st})
                continue
            available = list(avail_capped_set)   # A_full,p for synthetic
        else:
            # Base job, full-replacement mode (marginal not used in Gate F)
            if n_avail_capped >= k:
                available = list(avail_capped_set)
            else:
                avail_unc_set = eligible_set.difference(cf_busy_active, bg_busy)
                available = list(avail_unc_set)

        if not available:
            if not is_syn:
                n_base_unserved += 1
            continue

        # ── Stage 1½: Gate F shortlist (§4.2, §4.4) ─────────────────────────
        n_full_eligible = len(available)
        if r is None:
            # Unrestricted: C_p,unrestricted = A_full,p; no hash needed
            C_p_r = available
        else:
            if is_syn:
                assert _cgen_ord is not None, "generation_ordinal array missing for synthetic event"
                assert not np.isnan(float(_cgen_ord[_i])), f"generation_ordinal NaN at _i={_i} jid={jid}"
                event_uid = f"syn:{scen_seed}:{int(_cgen_ord[_i])}"
            else:
                event_uid = f"base:{jid}"
            C_p_r = gate_f_shortlist(available, scen_seed, event_uid, r, k)

        n_exposed = len(C_p_r)
        gf_full_counts.append(n_full_eligible)
        gf_exposed_counts.append(n_exposed)
        gf_k_counts.append(k)

        # ── Stage 2: canonical policy selector on C_p_r (§4.5) ──────────────
        if alg == "fp":
            selected = select_fp_canonical(C_p_r, k)
        elif alg == "fp_spread":
            selected = select_fp_spread_canonical(C_p_r, k, cab_active_count)
        elif alg == "loc":
            selected = select_loc_canonical(C_p_r, k)
        else:
            selected = select_random_canonical(C_p_r, k, _rng)

        # Record selection digest for trace (only when collect_trace=True, i.e. r=1.0)
        if collect_trace:
            _tr_uid        = event_uid
            _tr_sel_dig    = hashlib.sha256(",".join(sorted(selected)).encode()).hexdigest()
            _tr_la_out     = None
            _tr_stage1_out = "selector"

        # ── Stage 3: look-ahead (synthetic only, unchanged from M4) ─────────
        if is_syn and selected:
            _la_safe = look_ahead_safe(selected, t_j_ms, t_e_ms, cf_busy_ms)
            if not _la_safe:
                if collect_trace:
                    _la_st = hashlib.sha256(repr((
                        tuple(sorted(available_set)),
                        tuple(sorted(cap_exceeded)),
                        tuple(sorted(cf_busy_ms.items())),
                        tuple(sorted(cf_util.items())),
                        tuple(sorted(cab_active_count.items())),
                    )).encode()).hexdigest()
                    _trace.append({"uid": _tr_uid, "stage1_outcome": _tr_stage1_out,
                                   "sel_dig": _tr_sel_dig,
                                   "la_out": False, "state_dig": _la_st})
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
            elif collect_trace:
                _tr_la_out = True

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

        if collect_trace:
            # Full canonical placement-state: membership + utilization + cabinet counts.
            # All mutable variables that affect future placement decisions at r=1.
            _tr_state_canonical = repr((
                tuple(sorted(available_set)),
                tuple(sorted(cap_exceeded)),
                tuple(sorted(cf_busy_ms.items())),
                tuple(sorted(cf_util.items())),
                tuple(sorted(cab_active_count.items())),
            ))
            _tr_state_dig = hashlib.sha256(_tr_state_canonical.encode()).hexdigest()
            _trace.append({"uid": _tr_uid, "stage1_outcome": _tr_stage1_out,
                            "sel_dig": _tr_sel_dig,
                            "la_out": _tr_la_out, "state_dig": _tr_state_dig})

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
            cc: dict[int, int] = {}
            for nd in selected:
                c = fp_cab.get(nd, -1)
                if c >= 0: cc[c] = cc.get(c, 0) + 1
            if cc:
                cohort_records.append({"t_s": t_j_ms, "t_e": t_e_ms, "ppn": ppn, "cab_counts": cc})
                n_cabs_per_job.append(len(cc))

    if n_base_unserved > 0:
        raise AssertionError(f"n_base_unserved={n_base_unserved} (QoS invariant violated)")

    B_cab_h, _ = sweep_cab_budget_fast(cohort_records, cab_p99_W)
    B_cab_ratio = B_cab_h / max(B_cab_hist, 1e-9)
    cap_unlock  = (syn_node_hours / max(hist_total_nh, 1e-9)) * 100.0

    # Gate F diagnostic percentiles
    # realized_selector_choice_multiplier = |C_p,r| / k  (frozen definition)
    gf_choice_mult = (
        [e / max(kv, 1) for e, kv in zip(gf_exposed_counts, gf_k_counts)]
        if gf_k_counts else []
    )

    return {
        "policy"               : policy_name,
        "lambda_val"           : lambda_val,
        "nominal_choice_ratio" : r,
        "capacity_unlock_pct"  : jf(cap_unlock),
        "B_primary_h"          : jf(B_primary),
        "S_primary_Cdoth"      : jf(S_primary),
        "B_secondary_h"        : jf(B_secondary),
        "B_cab_ratio"          : jf(B_cab_ratio),
        "syn_node_hours"       : jf(syn_node_hours),
        "n_syn_admit"          : n_syn_admit,
        "n_drop_cap"           : n_drop_cap,
        "n_drop_physical"      : n_drop_phys,
        "n_drop_la"            : n_drop_la,
        "n_base_unserved"      : n_base_unserved,
        "mean_F_syn"           : jf(sum_F_syn / n_F_syn) if n_F_syn > 0 else None,
        "cab_span_median"      : jf(float(np.median(n_cabs_per_job))) if n_cabs_per_job else None,
        "full_selector_eligible_count_p10"  : jf(pctile(gf_full_counts, 10)),
        "full_selector_eligible_count_p50"  : jf(pctile(gf_full_counts, 50)),
        "full_selector_eligible_count_p90"  : jf(pctile(gf_full_counts, 90)),
        "exposed_selector_eligible_count_p10": jf(pctile(gf_exposed_counts, 10)),
        "exposed_selector_eligible_count_p50": jf(pctile(gf_exposed_counts, 50)),
        "exposed_selector_eligible_count_p90": jf(pctile(gf_exposed_counts, 90)),
        "realized_selector_choice_mult_p10" : jf(pctile(gf_choice_mult, 10)),
        "realized_selector_choice_mult_p50" : jf(pctile(gf_choice_mult, 50)),
        "realized_selector_choice_mult_p90" : jf(pctile(gf_choice_mult, 90)),
        "invariant_violated"   : False,
        "r1_trace"             : _trace if collect_trace else None,
        "n_combined_events"    : len(combined) if collect_trace else None,
    }


def compare_r1_traces(pol_traces: dict, n_combined_events: int | None = None) -> dict:
    """
    Compare per-event digests across all 4 policies at a single (r, lambda).
    pol_traces: {policy_name: [{"uid", "stage1_outcome", "sel_dig", "la_out", "state_dig"}, ...]}
    n_combined_events: total scheduling events generated (len(combined)); used to assert
                       that every event is traced (trace count must equal this).

    Hard assertions (any failure → overall_pass=False):
    - event_uid_unique_pass: no duplicate uid within any policy trace
    - event_presence_pass: union(uid_sets) == intersection(uid_sets)
    - event_order_pass: all policies have the same ordered uid sequence
    - count_reconcile_pass: trace length per policy == n_combined_events (if provided)
    - stage1_outcome_pass: stage1_outcome identical across policies for every event
    - sel_pass / la_pass / state_pass: digest agreement on events present in all policies
    """
    pols = list(pol_traces.keys())

    # Per-policy ordered uid sequences and counts
    pol_uid_seqs = {p: [e["uid"] for e in pol_traces[p]] for p in pols}
    pol_counts   = {p: len(pol_uid_seqs[p]) for p in pols}

    # Uniqueness: no dup uids within any policy
    uid_unique_pass = all(len(seq) == len(set(seq)) for seq in pol_uid_seqs.values())

    # Presence: every uid seen by at least one policy must be seen by all policies
    uid_sets = [set(seq) for seq in pol_uid_seqs.values()]
    uid_union        = set.union(*uid_sets)        if uid_sets else set()
    uid_intersection = set.intersection(*uid_sets) if uid_sets else set()
    presence_pass = (uid_union == uid_intersection)
    missing_uids  = sorted(uid_union - uid_intersection)[:5]

    # Order: all policies produce events in the same sequence
    ref_seq    = pol_uid_seqs[pols[0]] if pols else []
    order_pass = all(pol_uid_seqs[p] == ref_seq for p in pols)
    first_order_divergence = None
    if not order_pass:
        for p in pols[1:]:
            seq = pol_uid_seqs[p]
            for i, (a, b) in enumerate(zip(ref_seq, seq)):
                if a != b:
                    first_order_divergence = {"event_idx": i, pols[0]: a, p: b}
                    break
            if first_order_divergence:
                break

    # Count reconciliation: all policies must trace every combined event
    counts_agree_pass = len(set(pol_counts.values())) == 1
    if n_combined_events is not None:
        count_reconcile_pass = (counts_agree_pass and
                                all(v == n_combined_events for v in pol_counts.values()))
    else:
        count_reconcile_pass = counts_agree_pass
    first_count_mismatch = None
    if not count_reconcile_pass:
        first_count_mismatch = {
            "n_combined_events_expected": n_combined_events,
            "pol_counts": pol_counts,
        }

    # Per-event digest comparison (only for events present in ALL policies)
    by_uid: dict[str, dict] = {}
    for pol, entries in pol_traces.items():
        for e in entries:
            by_uid.setdefault(e["uid"], {})[pol] = e

    n_all = sum(1 for v in by_uid.values() if len(v) == len(pols))
    n_s1 = n_sel = n_la_chk = n_la = n_st_chk = n_st = 0
    first_sel = first_la = first_st = first_missing = first_s1_div = None

    for uid, ents in by_uid.items():
        if len(ents) < len(pols):
            if first_missing is None:
                first_missing = {
                    "uid"         : uid,
                    "present_in"  : sorted(ents.keys()),
                    "missing_from": [p for p in pols if p not in ents],
                }
            continue

        # stage1_outcome identity
        s1s = [ents[p].get("stage1_outcome") for p in pols]
        if len(set(s1s)) == 1:
            n_s1 += 1
        elif first_s1_div is None:
            first_s1_div = {"uid": uid,
                            "stage1_outcomes": {p: ents[p].get("stage1_outcome") for p in pols}}

        # sel_dig identity (only meaningful when outcome == "selector")
        if s1s[0] == "selector":
            sds = [ents[p]["sel_dig"] for p in pols]
            if len(set(sds)) == 1:
                n_sel += 1
            elif first_sel is None:
                first_sel = {"uid": uid, "sel_digs": {p: ents[p]["sel_dig"] for p in pols}}

        # la_out identity
        las = [ents[p]["la_out"] for p in pols]
        if any(v is not None for v in las):
            n_la_chk += 1
            if len(set(las)) == 1:
                n_la += 1
            elif first_la is None:
                first_la = {"uid": uid, "la_outs": {p: ents[p]["la_out"] for p in pols}}

        # state_dig identity (always present after fix — drops have unchanged state)
        sts = [ents[p].get("state_dig") for p in pols]
        n_st_chk += 1
        if all(s is not None for s in sts) and len(set(sts)) == 1:
            n_st += 1
        elif first_st is None:
            first_st = {"uid": uid,
                        "state_digs": {p: ents[p].get("state_dig") for p in pols}}

    n_sel_events = sum(1 for v in by_uid.values()
                       if len(v) == len(pols) and v[pols[0]].get("stage1_outcome") == "selector")
    stage1_outcome_pass = (n_s1 == n_all)
    digest_sel_pass     = (n_sel == n_sel_events)
    digest_la_pass      = (n_la  == n_la_chk)
    digest_state_pass   = (n_st  == n_st_chk)

    return {
        "pol_event_counts"           : pol_counts,
        "n_combined_events_expected" : n_combined_events,
        "n_events_in_any_trace"      : len(by_uid),
        "n_events_all_pols_present"  : n_all,
        "event_uid_unique_pass"      : uid_unique_pass,
        "event_presence_pass"        : presence_pass,
        "event_order_pass"           : order_pass,
        "count_reconcile_pass"       : count_reconcile_pass,
        "stage1_outcome_pass"        : stage1_outcome_pass,
        "n_stage1_outcome_identical" : n_s1,
        "n_sel_events"               : n_sel_events,
        "n_sel_identical"            : n_sel,
        "n_la_checked"               : n_la_chk,
        "n_la_identical"             : n_la,
        "n_state_checked"            : n_st_chk,
        "n_state_identical"          : n_st,
        "sel_pass"                   : digest_sel_pass,
        "la_pass"                    : digest_la_pass,
        "state_pass"                 : digest_state_pass,
        "overall_pass"               : (uid_unique_pass and presence_pass and order_pass
                                        and count_reconcile_pass and stage1_outcome_pass
                                        and digest_sel_pass and digest_la_pass
                                        and digest_state_pass),
        "first_count_mismatch"       : first_count_mismatch,
        "first_missing_event"        : first_missing,
        "missing_uids_sample"        : missing_uids,
        "first_order_divergence"     : first_order_divergence,
        "first_stage1_divergence"    : first_s1_div,
        "first_sel_divergence"       : first_sel,
        "first_la_divergence"        : first_la,
        "first_state_divergence"     : first_st,
    }


# ── Crossing estimand (v3 capacity-order first-violation) ─────────────────────
def check_infeasible(res: dict, b_ref_s: float, s_ref_s: float):
    if res.get("invariant_violated"):
        return True, "invariant_violated"
    b_ratio = res["B_primary_h"] / max(b_ref_s, 1e-9)
    s_val   = res.get("S_primary_Cdoth")
    s_ratio = (float(s_val) if s_val is not None and not (isinstance(s_val, float)
               and np.isnan(s_val)) else float("nan")) / max(s_ref_s, 1e-9)
    b_cab   = res.get("B_cab_ratio") or 0.0
    violations = []
    if b_ratio > 1.0:                                  violations.append("B_ratio")
    if not np.isnan(s_ratio) and s_ratio > 1.0:       violations.append("S_ratio")
    if b_cab   > 1.0:                                  violations.append("B_cab_ratio")
    return bool(violations), (violations[0] if violations else None)

def classify_crossing(lambda_rows, b_ref_s, s_ref_s, b_cab_ref) -> dict:
    for r in lambda_rows:
        if r.get("invariant_violated"):
            r["infeasible"] = True; r["first_binding"] = "invariant_violated"; continue
        b_ratio   = r["B_primary_h"] / max(b_ref_s, 1e-9)
        s_val     = r.get("S_primary_Cdoth")
        s_ratio   = (float(s_val) if s_val is not None and not (isinstance(s_val, float)
                     and np.isnan(s_val)) else float("nan")) / max(s_ref_s, 1e-9)
        b_cab     = r.get("B_cab_ratio") or 0.0
        r["B_primary_ratio"] = b_ratio; r["S_primary_ratio"] = s_ratio
        violations = []
        if b_ratio > 1.0:                                 violations.append("B_ratio")
        if not np.isnan(s_ratio) and s_ratio > 1.0:      violations.append("S_ratio")
        if b_cab   > 1.0:                                 violations.append("B_cab_ratio")
        r["infeasible"] = bool(violations)
        r["first_binding"] = violations[0] if violations else None
    last_feasible = None
    for r in lambda_rows:
        if not r["infeasible"]:
            last_feasible = r
        else:
            c_up = r["capacity_unlock_pct"]
            if last_feasible is None:
                return {"status": "left_boundary", "C_lower_pct": 0.0,
                        "C_upper_pct": c_up,
                        "first_binding_constraint": r["first_binding"],
                        "right_censored": False}
            return {"status": "exact_bracket",
                    "C_lower_pct": last_feasible["capacity_unlock_pct"],
                    "C_upper_pct": c_up,
                    "first_binding_constraint": r["first_binding"],
                    "right_censored": False}
    c_lo = last_feasible["capacity_unlock_pct"] if last_feasible else 0.0
    return {"status": "right_censored", "C_lower_pct": c_lo, "C_upper_pct": None,
            "first_binding_constraint": None, "right_censored": True}

def refine_gate_f_bracket(cx, policy_name, policy_seed, job_perms, syn_pool,
                           scen_seed, r, b_ref_s, s_ref_s, lambda_rows,
                           collect_trace: bool = False):
    if cx["status"] != "exact_bracket" or cx["C_upper_pct"] is None:
        return cx, []
    if (cx["C_upper_pct"] - cx["C_lower_pct"]) <= TARGET_PP:
        return cx, []
    n_safe = 0; c_safe = 0.0; n_unsafe = None; c_unsafe = None
    binding = cx["first_binding_constraint"]
    for row in sorted(lambda_rows, key=lambda x: x.get("lambda_val", 0)):
        is_inf, bind = check_infeasible(row, b_ref_s, s_ref_s)
        lam = row.get("lambda_val", 1.0)
        n_syn_r = int(round((lam - 1.0) * n_base))
        if not is_inf:
            n_safe = n_syn_r; c_safe = row["capacity_unlock_pct"]
        else:
            if n_unsafe is None:
                n_unsafe = n_syn_r; c_unsafe = row["capacity_unlock_pct"]
                if bind: binding = bind
                break
    if n_unsafe is None or (n_unsafe - n_safe) <= 1:
        return cx, []
    extra_rows = []
    while (c_unsafe - c_safe) > TARGET_PP and (n_unsafe - n_safe) > 1:
        step = (n_unsafe - n_safe) / (N_REFINE_GRID + 1)
        grid_pts = sorted(set(
            int(round(n_safe + step * i))
            for i in range(1, N_REFINE_GRID + 1)
            if n_safe < int(round(n_safe + step * i)) < n_unsafe
        ))
        if not grid_pts: break
        first_inf_pt = None; last_safe_pt = None
        for n_pt in grid_pts:
            if n_pt > len(syn_pool): break
            syn_sub = syn_pool.iloc[:n_pt].copy()
            lam_pt  = 1.0 + n_pt / n_base
            try:
                res = capacity_replay_gate_f(syn_sub, policy_name, lam_pt,
                                             policy_seed, job_perms, scen_seed, r,
                                             collect_trace=collect_trace)
            except AssertionError:
                res = {"lambda_val": lam_pt, "policy": policy_name,
                       "nominal_choice_ratio": r,
                       "invariant_violated": True,
                       "capacity_unlock_pct": n_pt / n_base * 100.0,
                       "B_primary_h": float("nan"), "S_primary_Cdoth": float("nan"),
                       "B_cab_ratio": float("nan"), "syn_node_hours": 0.0}
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
            if last_safe_pt is not None: n_safe, c_safe = last_safe_pt
        else:
            if last_safe_pt is not None: n_safe, c_safe = last_safe_pt
            else: break
    print(f"      [refine] {policy_name} r={r}: [{c_safe:.2f},{c_unsafe:.2f}]%"
          f"  gap={c_unsafe-c_safe:.2f}pp  {len(extra_rows)} evals")
    return {"status": "exact_bracket", "C_lower_pct": c_safe, "C_upper_pct": c_unsafe,
            "first_binding_constraint": binding, "right_censored": False}, extra_rows

# ══════════════════════════════════════════════════════════════════════════════
# Seed generation — must replicate M4 master_rng sequence exactly
# ══════════════════════════════════════════════════════════════════════════════
print("\n[9] Generating scenario seeds (replicating M4 master_rng sequence) ...")
n_extra_max = int(np.ceil((LAMBDA_MAX_EXT - 1.0) * n_base))
print(f"    n_base={n_base}  n_extra_max={n_extra_max}  N_DEV={N_DEV}  N_FIRST={N_FIRST}")
master_rng = np.random.default_rng(SCENARIO_SEED)
scen_seeds = [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
wl_seeds   = [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
pol_seeds  = {p: [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
              for p in POLICY_IDS}
print(f"    sc0: scen_seed={scen_seeds[0]}  wl_seed={wl_seeds[0]}")

# ══════════════════════════════════════════════════════════════════════════════
# Main loop
# ══════════════════════════════════════════════════════════════════════════════
print(f"\n[10] Running Gate F dev scenarios sc{N_FIRST}-sc{N_FIRST+N_DEV-1}")
print(f"     Ratios: {GATE_F_RATIOS}")
print(f"     Policies: {GATE_F_POLICIES}")
print(f"     Lambda sweep: {LAMBDA_SWEEP}")

r_label = lambda r: "unrestricted" if r is None else str(r)

scenario_results = []

for s_idx in range(N_FIRST, N_FIRST + N_DEV):
    t_scen = time.time()
    scen_seed = scen_seeds[s_idx]
    print(f"\n{'='*70}")
    print(f"Scenario {s_idx}  (scen_seed={scen_seed}  wl_seed={wl_seeds[s_idx]})")
    print(f"{'='*70}")

    syn_pool  = sample_synthetic_pool(n_extra_max, wl_seeds[s_idx])
    scen_rng  = np.random.default_rng(scen_seed)
    job_perms = generate_job_perms(syn_pool, scen_rng)
    B_ref_s, S_ref_s = compute_B_S_ref_s(job_perms, T_THR_PRIMARY)
    print(f"    B_ref_s={B_ref_s:.2f}h  S_ref_s={S_ref_s:.4f}C*h")

    ratio_results = {}

    for r in GATE_F_RATIOS:
        rl = r_label(r)
        print(f"\n  -- ratio={rl} --")
        ratio_results[rl] = {}
        do_trace = bool(GATE_F_TRACE_R1 and r == 1.0)
        _r1_pol_traces: dict[str, dict] = {}    # {pol: {lam_str: [trace_entries]}}
        _r1_pol_n_comb: dict[str, dict] = {}    # {pol: {lam_str: n_combined_events}}

        for policy_name in GATE_F_POLICIES:
            pol_seed = pol_seeds[policy_name][s_idx]
            rows: list[dict] = []
            if do_trace:
                _r1_pol_traces[policy_name] = {}

            # Lambda sweep
            for lam in LAMBDA_SWEEP:
                n_syn   = int(round((lam - 1.0) * n_base))
                syn_sub = (syn_pool.iloc[:n_syn].copy() if n_syn > 0
                           else pd.DataFrame(columns=list(syn_pool.columns)))
                t_pol = time.time()
                try:
                    res = capacity_replay_gate_f(syn_sub, policy_name, lam,
                                                 pol_seed, job_perms, scen_seed, r,
                                                 collect_trace=do_trace)
                except AssertionError as exc:
                    print(f"    lam={lam:.2f} {policy_name}: INVARIANT -- {exc}")
                    res = {"lambda_val": lam, "policy": policy_name,
                           "nominal_choice_ratio": r, "invariant_violated": True,
                           "capacity_unlock_pct": n_syn / n_base * 100.0 if n_base > 0 else 0.0,
                           "B_primary_h": float("nan"), "S_primary_Cdoth": float("nan"),
                           "B_cab_ratio": float("nan"), "syn_node_hours": 0.0}
                if do_trace:
                    lam_key = str(round(lam, 10))
                    _r1_pol_traces[policy_name][lam_key] = res.pop("r1_trace", None) or []
                    _r1_pol_n_comb.setdefault(policy_name, {})[lam_key] = res.pop("n_combined_events", None)
                else:
                    res.pop("r1_trace", None)
                    res.pop("n_combined_events", None)
                res["lambda_val"] = lam
                rows.append(res)
                if not res.get("invariant_violated"):
                    br = res["B_primary_h"] / max(B_ref_s, 1e-9)
                    print(f"    lam={lam:.2f} r={rl} {policy_name:16s}: "
                          f"C={res['capacity_unlock_pct']:5.1f}%  B/Bref={br:.4f}  "
                          f"Bcab={res.get('B_cab_ratio', float('nan')):.4f}  "
                          f"drops={res.get('n_drop_physical',0)}/"
                          f"{res.get('n_drop_cap',0)}/{res.get('n_drop_la',0)}"
                          f"  ({time.time()-t_pol:.0f}s)")

            # Compute crossing
            cx = classify_crossing(rows, B_ref_s, S_ref_s, B_cab_hist)

            # Extend sweep if right-censored (same logic as M4, only for non-spread)
            if cx["right_censored"] and policy_name in ("full_random", "full_fp",
                                                         "full_loc"):
                print(f"    [ext] {policy_name} r={rl}: right-censored, extending...")
                for lam_ext in LAMBDA_SWEEP_EXT:
                    n_syn = int(round((lam_ext - 1.0) * n_base))
                    if n_syn > len(syn_pool):
                        print(f"    [ext] pool exhausted at lam={lam_ext:.2f}"); break
                    syn_sub = syn_pool.iloc[:n_syn].copy()
                    try:
                        res = capacity_replay_gate_f(syn_sub, policy_name, lam_ext,
                                                     pol_seed, job_perms, scen_seed, r,
                                                     collect_trace=do_trace)
                    except AssertionError as exc:
                        res = {"lambda_val": lam_ext, "policy": policy_name,
                               "nominal_choice_ratio": r, "invariant_violated": True,
                               "capacity_unlock_pct": n_syn / n_base * 100.0,
                               "B_primary_h": float("nan"), "S_primary_Cdoth": float("nan"),
                               "B_cab_ratio": float("nan"), "syn_node_hours": 0.0}
                    if do_trace:
                        _lk = str(round(lam_ext, 10))
                        _r1_pol_traces[policy_name][_lk] = res.pop("r1_trace", None) or []
                        _r1_pol_n_comb.setdefault(policy_name, {})[_lk] = res.pop("n_combined_events", None)
                    else:
                        res.pop("r1_trace", None)
                        res.pop("n_combined_events", None)
                    res["lambda_val"] = lam_ext
                    rows.append(res)
                    cx = classify_crossing(rows, B_ref_s, S_ref_s, B_cab_hist)
                    if not cx["right_censored"]:
                        print(f"    [ext] crossing found at lam={lam_ext:.2f}"); break
                if cx["right_censored"]:
                    print(f"    [ext] still right-censored at lam={LAMBDA_MAX_EXT}")

            # Refine bracket
            if cx["status"] == "exact_bracket" and cx["C_upper_pct"] is not None:
                gap = cx["C_upper_pct"] - cx["C_lower_pct"]
                if gap > TARGET_PP:
                    cx, extra = refine_gate_f_bracket(
                        cx, policy_name, pol_seed, job_perms, syn_pool,
                        scen_seed, r, B_ref_s, S_ref_s, rows,
                        collect_trace=do_trace)
                    for _erow in extra:
                        if do_trace:
                            _lk = str(round(_erow.get("lambda_val", 0.0), 10))
                            _r1_pol_traces[policy_name][_lk] = _erow.pop("r1_trace", None) or []
                            _r1_pol_n_comb.setdefault(policy_name, {})[_lk] = _erow.pop("n_combined_events", None)
                        else:
                            _erow.pop("r1_trace", None)
                            _erow.pop("n_combined_events", None)
                    rows.extend(extra)

            ratio_results[rl][policy_name] = {
                "lambda_rows": [{k: jf(v) if isinstance(v, float) else v
                                 for k, v in row.items()
                                 if k not in ("r1_trace", "n_combined_events")} for row in rows],
                "crossing": {k: jf(v) if isinstance(v, float) else v
                             for k, v in cx.items()},
            }
            print(f"    CROSSING {policy_name} r={rl}: "
                  f"status={cx['status']}  C_lower={cx['C_lower_pct']}%  "
                  f"C_upper={cx['C_upper_pct']}%")

        # ── r=1 trace comparison (GATE_F_TRACE_R1=1 only) ────────────────
        if do_trace and _r1_pol_traces:
            # Derive the saved lambda keys from the first policy's lambda_rows
            _saved_lam_keys = set(
                str(round(row["lambda_val"], 10))
                for row in ratio_results[rl][GATE_F_POLICIES[0]]["lambda_rows"]
                if row.get("lambda_val") is not None
            )
            # Compare per-lambda across all policies
            _all_lam_keys = sorted(set(k for t in _r1_pol_traces.values() for k in t))
            _lam_cmp: dict[str, dict] = {}
            for _lk in _all_lam_keys:
                _lam_pol_traces = {p: _r1_pol_traces[p].get(_lk, []) for p in GATE_F_POLICIES}
                _n_comb = next(
                    (_r1_pol_n_comb.get(p, {}).get(_lk)
                     for p in GATE_F_POLICIES
                     if _r1_pol_n_comb.get(p, {}).get(_lk) is not None),
                    None)
                _lam_cmp[_lk] = compare_r1_traces(_lam_pol_traces, _n_comb)
            _coverage_pass = _saved_lam_keys == set(_all_lam_keys)
            _agg_overall   = all(v["overall_pass"] for v in _lam_cmp.values())
            _trace_cmp = {
                "enabled"              : True,
                "per_lambda"           : _lam_cmp,
                "lambda_coverage_pass" : _coverage_pass,
                "saved_lambda_keys"    : sorted(_saved_lam_keys),
                "traced_lambda_keys"   : sorted(_all_lam_keys),
                "overall_pass"         : _coverage_pass and _agg_overall,
            }
            ratio_results[rl]["r1_trace_comparison"] = _trace_cmp
            _tc_str = "PASS" if _trace_cmp["overall_pass"] else "FAIL"
            print(f"  r1_trace_comparison: {_tc_str}  "
                  f"(coverage={_coverage_pass}  "
                  f"per_lambda_all_pass={_agg_overall})")

    # ── r=1 inductive negative-control assertion (§4.6) ──────────────────
    r1_key = "1.0"
    if r1_key in ratio_results:
        cx_r1 = {p: ratio_results[r1_key][p]["crossing"] for p in GATE_F_POLICIES}
        vals = [cx_r1[p]["C_lower_pct"] for p in GATE_F_POLICIES]
        if len(set(str(v) for v in vals)) > 1:
            print(f"  WARNING: r=1 crossings differ across policies: {cx_r1}")
        else:
            print(f"  r=1 inductive check: all policies C_lower={vals[0]:.4f}%  [OK]")

    scenario_results.append({
        "scenario_idx" : s_idx,
        "scen_seed"    : scen_seed,
        "wl_seed"      : wl_seeds[s_idx],
        "B_ref_s"      : jf(B_ref_s),
        "S_ref_s"      : jf(S_ref_s),
        "ratios"       : ratio_results,
        "elapsed_s"    : round(time.time() - t_scen, 1),
    })
    print(f"\nScenario {s_idx} done in {time.time()-t_scen:.0f}s")

# ── Save results ────────────────────────────────────────────────────────────
result = {
    "git_commit_full"       : _PROV["git_commit_full"],
    "git_commit_short"      : _PROV["git_commit_short"],
    "git_tracked_dirty"     : _PROV["git_tracked_dirty"],
    "git_untracked_present" : _PROV["git_untracked_present"],
    "git_untracked_count"   : _PROV["git_untracked_count"],
    "script"          : "r1_gate_f_run.py",
    "n_dev"           : N_DEV,
    "n_first"         : N_FIRST,
    "gate_f_ratios"   : [r_label(r) for r in GATE_F_RATIOS],
    "gate_f_policies" : GATE_F_POLICIES,
    "lambda_sweep"    : LAMBDA_SWEEP,
    "target_pp"       : TARGET_PP,
    "scenario_results": scenario_results,
    "elapsed_total_s" : round(time.time() - t_script, 1),
}
OUT_FILE.write_text(json.dumps(result, indent=2))
print(f"\nSaved: {OUT_FILE}")
print(f"Total elapsed: {time.time()-t_script:.0f}s")
print("\nNEXT: Run preflight verification before restricted ratios.")
print("  python artifacts/revision1/analysis/r1_gate_f_preflight.py")
