#!/usr/bin/env python3
"""
Gate F: Experiment-2 Under Corrected Concurrent-Load Cabinet Reference with LOO Position Policy
(c2_gate_f_run.py — manuscript-completion runner)

Base: r2_gate_f_run.py at commit 5733b73b (Review-2 Challenge freeze)

Provenance:
  R2 scientific freeze:     5733b73b (r2_gate_f_run.py at Review-2 challenge)
  R2 challenge runner SHA256: (see project_r2_challenge_provenance.md)
  Diff from r2 base: see modifications below

Modifications from r2 base:
  1. Cabinet reference: corrected concurrent-load (f2_local_scheduling_reference.json)
     instead of job-contribution cabinet_power_envelopes.json
  2. B_cab_hist: loaded from f2_replay_denominator.json (B_cab_hist_F2_replay_h)
     instead of computed from cohort_hist_records
  3. Output path: artifacts/manuscript_completion/results/
  4. position_template replaced by position_loo (leave-one-out position scoring)
  5. Per-scenario placebo seeds derived from SeedSequence([_R3_ROOT, i, pid])
     instead of one-time draws from rng(2042)
  6. Cabinet accounting instrumentation (OBSERVATIONAL ONLY — does not affect scheduler)
  7. Checkpoint REUSE is PROHIBITED (checkpoint write retained)

Manuscript-completion checkpoint rule:
  Checkpoint READ is DISABLED for this runner. The checkpoint write infrastructure
  is retained but checkpoint REUSE is prohibited. Assert no checkpoint file exists
  at launch.
"""
import sys, io, os, json, time, heapq, math, hashlib, statistics, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

# ── Import new Phase C selectors from local runners directory ─────────────────
sys.path.insert(0, str(Path(__file__).parent))
from c2_selectors import (
    select_random_spread,
    build_global_placebo_fa,    select_fp_global_placebo,
    build_withincab_placebo_fa, select_fp_withincab_placebo,
    select_position_template,
    PLACEBO_GLOBAL_PERM_SEED, PLACEBO_WITHINCAB_PERM_SEED,
    PRIMARY_BETA_CHALLENGE,
)

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT  = Path(__file__).resolve().parents[3]
P1_DIR     = REPO_ROOT / "artifacts" / "phase1" / "analysis"
REV1_DIR   = REPO_ROOT / "artifacts" / "revision1"
REV2_DIR   = REPO_ROOT / "artifacts" / "revision2"
REV3_DIR   = REPO_ROOT / "artifacts" / "revision3"
OUT_DIR    = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"
TABLE_DIR  = REV1_DIR / "tables"    # frozen topology tables live in revision1
DATA_DIR   = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ── Corrected cabinet reference (manuscript-completion) ───────────────────────
_C2_CAB_REF_PATH  = REV3_DIR / "f2_local_scheduling_reference.json"
_C2_CAB_REF_SHA   = "71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34"
_C2_DENOM_PATH    = REV3_DIR / "f2_replay_denominator.json"
_C2_DENOM_SHA     = "b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48"
_C2_B_CAB_HIST_F2 = 871.3691666666647

# ── Frozen simulation constants (identical to Gate F; MUST NOT change) ────────
BETA_F_FROZEN    = 1.12484352          # kept for reference / sensitivity
T_THR_PRIMARY    = 63.625
T_THR_SECONDARY  = 60.602770562770566
DELTA_CAP        = 0.10
N_BINS           = 5
LAMBDA_SWEEP     = [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40,
                    1.50, 1.55, 1.60, 1.70, 1.80, 1.90, 2.00]
LAMBDA_MAX       = 2.00
LAMBDA_MAX_EXT   = 4.00
LAMBDA_SWEEP_EXT = [2.25, 2.50, 3.00, 3.50, 4.00]
TARGET_PP        = 0.50
N_REFINE_GRID    = 3

# PRIMARY beta for this run (LOO cross-fitted; plan §B3)
BETA_CHALLENGE   = PRIMARY_BETA_CHALLENGE   # imported from c2_selectors.py

# ── Challenge scenario parameters ─────────────────────────────────────────────
CHALLENGE_SEED      = 2042
N_SCENARIOS_TOTAL   = 25          # sc30-sc54
SCENARIO_FIRST      = 30          # default first scenario index

# Policies for seed-generation and dispatch (plan §D2)
# Order here fixes the pol_seeds draw order from rng(2042).
# position_template replaced by position_loo for manuscript-completion C2
CHALLENGE_POLICY_IDS = [
    "full_random", "full_fp", "position_loo", "full_fp_spread",
    "random_spread", "fp_global_placebo", "fp_withincab_placebo",
]
GATE_F_ALG = {
    "full_random"           : "random",
    "full_fp"               : "fp",
    "position_loo"          : "position_loo",
    "full_fp_spread"        : "fp_spread",
    "random_spread"         : "random_spread",
    "fp_global_placebo"     : "fp_global_placebo",
    "fp_withincab_placebo"  : "fp_withincab_placebo",
}

# ── Runtime overrides ─────────────────────────────────────────────────────────
_ALL_RATIOS     = [1.0, 1.25, 1.5, 2.0, 4.0, 8.0, None]
_ENV_RATIOS     = os.environ.get("GATE_F_RATIOS_ONLY", "")
if _ENV_RATIOS:
    _keys = [x.strip() for x in _ENV_RATIOS.split(",")]
    GATE_F_RATIOS = [None if k == "unrestricted" else float(k) for k in _keys]
else:
    GATE_F_RATIOS = _ALL_RATIOS

GATE_F_POLICIES          = CHALLENGE_POLICY_IDS
GATE_F_REQUIRE_CLEAN_GIT = int(os.environ.get("GATE_F_REQUIRE_CLEAN_GIT", "0"))

# ── Compat mode overrides (r1↔r2 equivalence; plan Amendment 4 §G1) ──────────
_COMPAT_SEED_ENV = os.environ.get("GATE_F_COMPAT_SEED", "")
_is_compat       = bool(_COMPAT_SEED_ENV)
if _is_compat:
    CHALLENGE_SEED    = int(_COMPAT_SEED_ENV)
    _env_beta = os.environ.get("GATE_F_COMPAT_BETA", "")
    if _env_beta:
        BETA_CHALLENGE = float(_env_beta)
    N_SCENARIOS_TOTAL = int(os.environ.get("GATE_F_COMPAT_N_SCEN", "30"))
_restrict = os.environ.get("GATE_F_RESTRICT_POLICIES", "")
if _restrict:
    GATE_F_POLICIES = [p.strip() for p in _restrict.split(",")]
_COMPAT_POLICY_ORDER_ENV = os.environ.get("GATE_F_COMPAT_POLICY_ORDER", "")
_COMPAT_POLICY_ORDER = (_COMPAT_POLICY_ORDER_ENV.split(",")
                        if _COMPAT_POLICY_ORDER_ENV else list(GATE_F_POLICIES))

N_DEV    = int(os.environ.get("GATE_F_N_DEV",   str(N_SCENARIOS_TOTAL)))
N_FIRST  = int(os.environ.get("GATE_F_N_FIRST", str(SCENARIO_FIRST) if not _is_compat else "0"))

_scen_tag  = f"sc{N_FIRST}-{N_FIRST + N_DEV - 1}"
_ratio_tag = (_ENV_RATIOS.replace(",", "_").replace(".", "p").replace("unrestricted", "unr")
              if _ENV_RATIOS else "all")
_run_suffix = "c2compat" if _is_compat else "c2manuscript"
OUT_FILE  = OUT_DIR / f"gate_f_{_scen_tag}_{_ratio_tag}_{_run_suffix}.json"
CKPT_FILE = OUT_FILE.with_name(OUT_FILE.stem + "_checkpoint.json")

# ── Utilities ─────────────────────────────────────────────────────────────────
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
        "git_commit_full"       : full,
        "git_commit_short"      : short,
        "git_tracked_dirty"     : tracked_dirty,
        "git_untracked_present" : untracked_present,
        "git_untracked_count"   : untracked_count,
    }

# ── Provenance (fires before data loading so dirty-check fires early) ─────────
_PROV = _git_provenance()
if GATE_F_REQUIRE_CLEAN_GIT and _PROV.get("git_tracked_dirty"):
    sys.exit(
        f"GATE_F_REQUIRE_CLEAN_GIT=1 but working tree is dirty "
        f"(HEAD={_PROV['git_commit_short']}). Commit all changes first."
    )

print("\nGate F C2: Manuscript-completion runner (corrected reference + position_loo)")
print("=" * 70)
print(f"  BETA_CHALLENGE = {BETA_CHALLENGE}  (PRIMARY_BETA_CHALLENGE from §B1)")
print(f"  CHALLENGE_SEED = {CHALLENGE_SEED}  sc{N_FIRST}-sc{N_FIRST+N_DEV-1}")
print(f"  Policies: {GATE_F_POLICIES}")
t_script = time.time()

# ════════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ════════════════════════════════════════════════════════════════════════════
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
fleet_topo  = pd.read_csv(TABLE_DIR / "fleet_node_topology.csv")
node_to_cab = dict(zip(fleet_topo["hostname"].values,
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

print("\n[2] Building location-only fingerprint (position means) ...")
fp_topo_df = pd.read_csv(TABLE_DIR / "fp_node_topology.csv")
fp_topo_df["pos_key"] = (fp_topo_df["chassis"].astype(str) + "_" +
                          fp_topo_df["slot"].astype(str)    + "_" +
                          fp_topo_df["board"].astype(str)   + "_" +
                          fp_topo_df["node_pos"].astype(str))
fp_topo_df["FA_2024"] = fp_topo_df["hostname"].map(FA_dict)
pos_mean = fp_topo_df.groupby("pos_key")["FA_2024"].mean().rename("FA_loc")
fp_topo_df  = fp_topo_df.join(pos_mean, on="pos_key")
LOC_FA_dict: dict[str, float] = dict(
    zip(fp_topo_df["hostname"].values, fp_topo_df["FA_loc"].values))
_glob_mean  = float(np.nanmean(list(LOC_FA_dict.values())))
LOC_FA_dict = {k: (v if not np.isnan(v) else _glob_mean)
               for k, v in LOC_FA_dict.items()}


def build_position_loo_fa(fp_topo: "pd.DataFrame", FA_dict: dict) -> tuple:
    """
    Build leave-one-out position-score dict for all fp nodes.
    LOO mean FA_2024 over nodes sharing the same structural position, excluding self.
    Fallback hierarchy (all within-chassis):
      Level 1: same (chassis, slot, board, node_pos) — same pos_key
      Level 2: same (chassis, slot, board)
      Level 3: same (chassis, slot)
      Level 4: global cohort mean (last resort)
    Missing FA_2024 replaced with global mean before LOO computation.
    Returns dict: hostname -> LOO FA score
    """
    import numpy as _np

    # Attach FA values; replace NaN with global mean
    topo = fp_topo.copy()
    topo["FA_2024"] = topo["hostname"].map(FA_dict)
    _finite_mask = topo["FA_2024"].notna()
    _global_mean = float(topo.loc[_finite_mask, "FA_2024"].mean())
    topo["FA_2024_filled"] = topo["FA_2024"].fillna(_global_mean)

    # Group keys
    topo["gk1"] = (topo["chassis"].astype(str) + "_" + topo["slot"].astype(str)
                   + "_" + topo["board"].astype(str) + "_" + topo["node_pos"].astype(str))
    topo["gk2"] = (topo["chassis"].astype(str) + "_" + topo["slot"].astype(str)
                   + "_" + topo["board"].astype(str))
    topo["gk3"] = (topo["chassis"].astype(str) + "_" + topo["slot"].astype(str))

    # Precompute group sums and counts for each level
    def _group_stats(df, key_col):
        g = df.groupby(key_col)["FA_2024_filled"]
        return g.sum().rename("gsum"), g.count().rename("gcnt")

    gs1, gc1 = _group_stats(topo, "gk1")
    gs2, gc2 = _group_stats(topo, "gk2")
    gs3, gc3 = _group_stats(topo, "gk3")
    _total_sum   = float(topo["FA_2024_filled"].sum())
    _total_cnt   = len(topo)

    loo_scores: dict[str, float] = {}
    fallback_levels: list[int] = []

    for _, row in topo.iterrows():
        node = row["hostname"]
        fa_i = row["FA_2024_filled"]
        k1, k2, k3 = row["gk1"], row["gk2"], row["gk3"]

        # Level 1: same pos_key
        g1_sum = gs1.get(k1, fa_i); g1_cnt = gc1.get(k1, 1)
        loo1 = (g1_sum - fa_i) / max(g1_cnt - 1, 1)
        if g1_cnt >= 2:
            loo_scores[node] = float(loo1); fallback_levels.append(1); continue

        # Level 2: same (chassis, slot, board)
        g2_sum = gs2.get(k2, fa_i); g2_cnt = gc2.get(k2, 1)
        loo2 = (g2_sum - fa_i) / max(g2_cnt - 1, 1)
        if g2_cnt >= 2:
            loo_scores[node] = float(loo2); fallback_levels.append(2); continue

        # Level 3: same (chassis, slot)
        g3_sum = gs3.get(k3, fa_i); g3_cnt = gc3.get(k3, 1)
        loo3 = (g3_sum - fa_i) / max(g3_cnt - 1, 1)
        if g3_cnt >= 2:
            loo_scores[node] = float(loo3); fallback_levels.append(3); continue

        # Level 4: global cohort mean
        loo_global = (_total_sum - fa_i) / max(_total_cnt - 1, 1)
        loo_scores[node] = float(loo_global); fallback_levels.append(4)

    from collections import Counter
    level_counts = Counter(fallback_levels)
    n_nan = int((~_finite_mask).sum())
    print(f"    position_loo: level1={level_counts[1]}, level2={level_counts[2]}, "
          f"level3={level_counts[3]}, global={level_counts[4]}, NaN_FA={n_nan}")
    return loo_scores, level_counts, n_nan


print("\n[2c] Building position LOO fingerprint ...")
LOO_FA_dict, _loo_level_counts, _loo_nan_count = build_position_loo_fa(fp_topo_df, FA_dict)


def select_position_loo(available, k, loo_fa_dict: dict):
    """Select k nodes by position-LOO FA score, descending."""
    scored = [(loo_fa_dict.get(n, 0.0), n) for n in available]
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:k]]


print("\n[3] Loading corrected concurrent-load cabinet reference ...")
_c2_cab_sha_actual = hashlib.sha256(open(_C2_CAB_REF_PATH, "rb").read()).hexdigest()
if _c2_cab_sha_actual != _C2_CAB_REF_SHA:
    sys.exit(f"f2_local_scheduling_reference.json SHA256 mismatch: "
             f"expected {_C2_CAB_REF_SHA}, got {_c2_cab_sha_actual}")
with open(_C2_CAB_REF_PATH) as fh:
    _f2_ref = json.load(fh)
cab_p99_W: dict[int, float] = {
    int(x["cabinet_id"]): float(x["Q_F2_local_W"])
    for x in _f2_ref["per_cabinet"]
}
_p99_med = float(np.median(list(cab_p99_W.values())))
cab_p99_W = {c: cab_p99_W.get(c, _p99_med) for c in all_cabinets}
print(f"    {len(cab_p99_W)} cabinets loaded (corrected F2 local-date reference)")
print(f"    F2 median threshold: {_p99_med/1000:.2f} kW")
print(f"    Cabinet reference SHA256: {_c2_cab_sha_actual[:16]}...")
_c2_denom_sha_actual = hashlib.sha256(open(_C2_DENOM_PATH, "rb").read()).hexdigest()
if _c2_denom_sha_actual != _C2_DENOM_SHA:
    sys.exit(f"f2_replay_denominator.json SHA256 mismatch: "
             f"expected {_C2_DENOM_SHA}, got {_c2_denom_sha_actual}")
print(f"    Replay denominator SHA256: {_c2_denom_sha_actual[:16]}...")

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

print("\n[6] Building residual model (BETA_CHALLENGE = {:.8f}) ...".format(BETA_CHALLENGE))
test_df2 = test_df.copy()
test_df2["job_mean_T"] = test_df2.groupby("job_idx")["T_p95"].transform("mean")
alpha_map: dict[int, float] = test_df2.groupby("job_idx")["job_mean_T"].first().to_dict()
test_df2["delta_T_p95"] = test_df2["T_p95"] - test_df2["job_mean_T"]
# Use BETA_CHALLENGE (not BETA_F_FROZEN) for residuals — plan §B3
test_df2["pred_challenge"] = BETA_CHALLENGE * test_df2["F_2024"]
test_df2["residual"]       = test_df2["delta_T_p95"] - test_df2["pred_challenge"]
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
bg_st_ms = sched_st.astype(np.int64)
bg_et_ms = sched_et.astype(np.int64)
is_test_sched = np.array([jid in test_id_set for jid in sched_jids])
bg_st_ms_bg = bg_st_ms[~is_test_sched]
bg_et_ms_bg = bg_et_ms[~is_test_sched]
bg_cn_bg    = sched_cn[~is_test_sched]
hist_st_for_precomp = _col_to_dt64ms(jobs_sorted["start_time"]).astype(np.int64)
bg_busy_per_job: dict[int, frozenset] = {}
for i, jid in enumerate(jobs_sorted["job_idx"].values.astype(int)):
    t_ms = int(hist_st_for_precomp[i])
    mask = (bg_st_ms_bg <= t_ms) & (bg_et_ms_bg > t_ms)
    bg_busy_per_job[jid] = frozenset().union(*bg_cn_bg[mask]) if mask.any() else frozenset()
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

# Manuscript-completion: use replay-matched denominator from frozen artifact
B_cab_hist = _C2_B_CAB_HIST_F2
print(f"    B_cab_hist (F2 replay, frozen): {B_cab_hist:.6f} h")

# ── Per-scenario placebo seeds (manuscript-completion C2) ─────────────────────
from numpy.random import SeedSequence as _SeedSequence
_R3_ROOT             = 847291653
_PLACEBO_GLOBAL_ID   = 1
_PLACEBO_WITHINCAB_ID = 2

# Canonical check values (from addendum v1.2):
_EXPECTED_GLOBAL_SEED_I0    = 2514122466
_EXPECTED_WITHINCAB_SEED_I0 = 4138460386

def _get_placebo_seeds(scenario_array_i: int) -> tuple:
    """Return (global_seed, withincab_seed) for scenario array index i."""
    g = int(_SeedSequence([_R3_ROOT, scenario_array_i, _PLACEBO_GLOBAL_ID]).generate_state(1)[0])
    w = int(_SeedSequence([_R3_ROOT, scenario_array_i, _PLACEBO_WITHINCAB_ID]).generate_state(1)[0])
    return g, w

# Verify canonical values at startup
_g0, _w0 = _get_placebo_seeds(0)
assert _g0 == _EXPECTED_GLOBAL_SEED_I0, f"Placebo global seed i=0: got {_g0}, expected {_EXPECTED_GLOBAL_SEED_I0}"
assert _w0 == _EXPECTED_WITHINCAB_SEED_I0, f"Placebo withincab seed i=0: got {_w0}, expected {_EXPECTED_WITHINCAB_SEED_I0}"
print(f"    Placebo seed canonical check PASSED (i=0: global={_g0}, withincab={_w0})")

# ── Helper functions ──────────────────────────────────────────────────────────
def bg_busy_at_ms(t_ms: int) -> frozenset:
    mask = (bg_st_ms_bg <= t_ms) & (bg_et_ms_bg > t_ms)
    return frozenset().union(*bg_cn_bg[mask]) if mask.any() else frozenset()

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
        "generation_ordinal invariant violated"
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
    """Reference thermal budget using BETA_CHALLENGE (not BETA_F_FROZEN)."""
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
        T_hats   = alpha + BETA_CHALLENGE * F_arr + res_s[perm[rank]]
        exc      = T_hats - thr
        B       += rt_h * float((exc > 0).sum())
        S       += rt_h * float(exc.clip(min=0).sum())
    return B, S

# ── Gate F hash helpers ───────────────────────────────────────────────────────
def choice_priority(scenario_seed: int, event_uid: str, hostname: str) -> tuple:
    key    = scenario_seed.to_bytes(8, "big", signed=False)
    msg    = event_uid.encode("utf-8") + b"\x00" + hostname.encode("utf-8")
    digest = hashlib.blake2b(msg, key=key, digest_size=8).digest()
    return int.from_bytes(digest, "big"), hostname

def gate_f_shortlist(full_eligible, scenario_seed: int, event_uid: str, r, k: int) -> list:
    ordered = sorted(full_eligible, key=lambda h: choice_priority(scenario_seed, event_uid, h))
    m = min(len(ordered), math.ceil(r * k))
    return ordered[:m]

# ── Canonical policy selectors ────────────────────────────────────────────────
def select_fp_canonical(available, k):
    s = sorted(available, key=lambda n: (FA_dict[n], n))
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

# ════════════════════════════════════════════════════════════════════════════
# Gate F replay function
# ════════════════════════════════════════════════════════════════════════════
def capacity_replay_gate_f(syn_subset, policy_name: str, lambda_val: float,
                            policy_seed: int, job_perms: dict,
                            scen_seed: int, r,
                            placebo_fa_global: dict,
                            placebo_fa_withincab: dict,
                            collect_trace: bool = False) -> dict:
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

    gf_full_counts: list[int]    = []
    gf_exposed_counts: list[int] = []
    gf_k_counts: list[int]       = []

    def _empty_strat():
        return {q: {"attempted": 0, "admitted": 0,
                    "drop_cap": 0, "drop_physical": 0, "drop_la": 0}
                for q in range(1, 5)}
    strat_ncoh = _empty_strat(); strat_nc = _empty_strat()
    strat_ppn  = _empty_strat(); strat_rt = _empty_strat()
    q_admit = {q: 0 for q in range(1, 5)}
    q_drop  = {q: 0 for q in range(1, 5)}

    # Cabinet accounting (OBSERVATIONAL ONLY — does not affect selection or thermal)
    _cab_nh: dict[int, float] = defaultdict(float)
    _cab_ev: dict[int, int]   = defaultdict(int)

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

        # Stage 1: node-level eligibility filter
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
                continue
            available = list(avail_capped_set)
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

        # Stage 1.5: Gate F shortlist
        n_full_eligible = len(available)
        if r is None:
            C_p_r = available
            event_uid = None
        else:
            if is_syn:
                assert _cgen_ord is not None
                assert not np.isnan(float(_cgen_ord[_i]))
                event_uid = f"syn:{scen_seed}:{int(_cgen_ord[_i])}"
            else:
                event_uid = f"base:{jid}"
            C_p_r = gate_f_shortlist(available, scen_seed, event_uid, r, k)

        n_exposed = len(C_p_r)
        gf_full_counts.append(n_full_eligible)
        gf_exposed_counts.append(n_exposed)
        gf_k_counts.append(k)

        # Stage 2: policy selector on C_p_r
        if alg == "fp":
            selected = select_fp_canonical(C_p_r, k)
        elif alg == "fp_spread":
            selected = select_fp_spread_canonical(C_p_r, k, cab_active_count)
        elif alg == "position_loo":
            selected = select_position_loo(C_p_r, k, LOO_FA_dict)
        elif alg == "random_spread":
            # Need event_uid for choice_priority; use same derivation as above
            _uid = event_uid if r is not None else (
                f"syn:{scen_seed}:{int(_cgen_ord[_i])}" if is_syn else f"base:{jid}"
            )
            selected = select_random_spread(C_p_r, k, cab_active_count,
                                            fp_cab, scen_seed, _uid)
        elif alg == "fp_global_placebo":
            selected = select_fp_global_placebo(C_p_r, k, placebo_fa_global)
        elif alg == "fp_withincab_placebo":
            selected = select_fp_withincab_placebo(C_p_r, k, placebo_fa_withincab)
        else:
            selected = select_random_canonical(C_p_r, k, _rng)

        # Stage 3: look-ahead (synthetic only)
        if is_syn and selected:
            _la_safe = look_ahead_safe(selected, t_j_ms, t_e_ms, cf_busy_ms)
            if not _la_safe:
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
            # T_hats use BETA_CHALLENGE (plan §B3)
            T_hats   = alpha + BETA_CHALLENGE * F_arr + res_s[perm[rank]]
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
                if c >= 0:
                    cc[c] = cc.get(c, 0) + 1
            if cc:
                cohort_records.append({"t_s": t_j_ms, "t_e": t_e_ms, "ppn": ppn, "cab_counts": cc})
                n_cabs_per_job.append(len(cc))

            # Cabinet accounting (OBSERVATIONAL ONLY — after all selection decisions)
            # These dicts are read-only after the scheduler advances; inert to future choices.
            _touched_cabs: set[int] = set()
            for _sel_node in selected:
                _sel_cab = fp_cab.get(_sel_node, -1)
                if _sel_cab >= 0:
                    _cab_nh[_sel_cab] += rt_h
                    _touched_cabs.add(_sel_cab)
            for _tc in _touched_cabs:
                _cab_ev[_tc] += 1

    if n_base_unserved > 0:
        raise AssertionError(f"n_base_unserved={n_base_unserved} (QoS invariant violated)")

    B_cab_h, _ = sweep_cab_budget_fast(cohort_records, cab_p99_W)
    B_cab_ratio = B_cab_h / max(B_cab_hist, 1e-9)
    cap_unlock  = (syn_node_hours / max(hist_total_nh, 1e-9)) * 100.0

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
        "q_admit"              : dict(q_admit),
        "q_drop"               : dict(q_drop),
        "invariant_violated"   : False,
        # Cabinet accounting (OBSERVATIONAL ONLY — does not affect scheduling)
        "cabinet_accounting"   : {
            "node_hours"    : {str(k): v for k, v in _cab_nh.items()},
            "event_touches" : {str(k): v for k, v in _cab_ev.items()},
        },
    }


# ── Crossing classification (identical to Gate F) ─────────────────────────────
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
    sorted_rows = sorted(lambda_rows, key=lambda x: float(x.get("capacity_unlock_pct", 0)))
    last_feasible = None
    for r in sorted_rows:
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
                           placebo_fa_global, placebo_fa_withincab):
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
                                             placebo_fa_global, placebo_fa_withincab)
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
    all_rows = list(lambda_rows) + list(extra_rows)
    cx_v3 = classify_crossing(all_rows, b_ref_s, s_ref_s, None)
    if cx_v3["status"] == "exact_bracket":
        c_safe   = cx_v3["C_lower_pct"]
        c_unsafe = cx_v3["C_upper_pct"]
        binding  = cx_v3["first_binding_constraint"] or binding
    print(f"      [refine] {policy_name} r={r}: [{c_safe:.2f},{c_unsafe:.2f}]%"
          f"  gap={c_unsafe-c_safe:.2f}pp  {len(extra_rows)} evals")
    return {"status": "exact_bracket", "C_lower_pct": c_safe, "C_upper_pct": c_unsafe,
            "first_binding_constraint": binding, "right_censored": False}, extra_rows


# ════════════════════════════════════════════════════════════════════════════
# Seed generation from rng(CHALLENGE_SEED=2042)
# ════════════════════════════════════════════════════════════════════════════
print("\n[9] Generating challenge scenario seeds from rng(2042) ...")
n_extra_max = int(np.ceil((LAMBDA_MAX_EXT - 1.0) * n_base))
print(f"    n_base={n_base}  n_extra_max={n_extra_max}  N_DEV={N_DEV}  N_FIRST={N_FIRST}")

_challenge_rng = np.random.default_rng(CHALLENGE_SEED)
scen_seeds = [int(_challenge_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS_TOTAL)]
wl_seeds   = [int(_challenge_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS_TOTAL)]
if not _is_compat:
    # Consume the two placebo-seed draws to maintain the rng sequence
    _pg_seed  = int(_challenge_rng.integers(0, 2**31))
    _pwc_seed = int(_challenge_rng.integers(0, 2**31))
    assert _pg_seed  == PLACEBO_GLOBAL_PERM_SEED,    \
        f"Placebo global seed mismatch: got {_pg_seed}, expected {PLACEBO_GLOBAL_PERM_SEED}"
    assert _pwc_seed == PLACEBO_WITHINCAB_PERM_SEED, \
        f"Placebo withincab seed mismatch: got {_pwc_seed}, expected {PLACEBO_WITHINCAB_PERM_SEED}"
# pol_seeds: draw in policy order
_POL_ALIAS = {"full_loc": "position_loo"}
_pol_seeds_all = {p: [int(_challenge_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS_TOTAL)]
                  for p in _COMPAT_POLICY_ORDER}
pol_seeds: dict[str, list] = {}
for _p_raw, _seeds in _pol_seeds_all.items():
    _p_active = _POL_ALIAS.get(_p_raw, _p_raw)
    if _p_active in GATE_F_POLICIES:
        pol_seeds[_p_active] = _seeds
del _challenge_rng

# Seed-index base is fixed to the experiment's SCENARIO_FIRST (30 for challenge, 0 for compat)
SEED_INDEX_BASE = 0 if _is_compat else SCENARIO_FIRST

def _sc_idx(sc_abs: int) -> int:
    idx = sc_abs - SEED_INDEX_BASE
    assert 0 <= idx < len(scen_seeds), \
        f"_sc_idx({sc_abs}): idx={idx} out of range [0, {len(scen_seeds)})"
    return idx

_sc0_label = "sc0" if _is_compat else "sc30"
print(f"    {_sc0_label}: scen_seed={scen_seeds[0]}  wl_seed={wl_seeds[0]}")
if not _is_compat:
    print(f"    Placebo global/withincab seeds from rng(2042): global={_pg_seed}  withincab={_pwc_seed}  [PASS]")
    print(f"    Per-scenario placebo seeds: derived from SeedSequence([{_R3_ROOT}, i, pid])")

# ════════════════════════════════════════════════════════════════════════════
# Main scenario loop
# ════════════════════════════════════════════════════════════════════════════
print(f"\n[10] Running C2 manuscript scenarios sc{N_FIRST}-sc{N_FIRST+N_DEV-1}")
print(f"     Ratios: {GATE_F_RATIOS}")
print(f"     Policies: {GATE_F_POLICIES}")
print(f"     Lambda sweep: {LAMBDA_SWEEP}")

r_label = lambda r: "unrestricted" if r is None else str(r)

scenario_results = []

# ── Manuscript-completion checkpoint policy ───────────────────────────────────
# Checkpoint WRITE is retained; checkpoint READ/REUSE is PROHIBITED.
# Every manuscript-completion C2 run must start from scratch.
_ckpt_ratios   = [r_label(r) for r in GATE_F_RATIOS]
completed_idxs: set[int] = set()
if CKPT_FILE.exists():
    sys.exit(
        f"[ABORT] Manuscript-completion C2 checkpoint file exists: {CKPT_FILE}\n"
        f"  Checkpoint reuse is PROHIBITED for manuscript-completion runs.\n"
        f"  Archive or delete the partial checkpoint before restarting.\n"
        f"  Partial run must be invalidated before a restart can be authorized."
    )

for s_abs in range(N_FIRST, N_FIRST + N_DEV):
    if s_abs in completed_idxs:
        print(f"    [skip] Scenario {s_abs} (in completed_idxs)")
        continue
    t_scen = time.time()
    _si    = _sc_idx(s_abs)          # 0-based index into 25-element seed arrays
    scen_seed = scen_seeds[_si]
    print(f"\n{'='*70}")
    print(f"Scenario {s_abs}  (idx={_si}  scen_seed={scen_seed}  wl_seed={wl_seeds[_si]})")
    print(f"{'='*70}")

    # Per-scenario placebo FA dicts (manuscript-completion C2)
    _s_array_i = _si  # 0-based array index within this experiment
    _pg_seed_s, _pw_seed_s = _get_placebo_seeds(_s_array_i)
    placebo_fa_global    = build_global_placebo_fa(FA_dict, _pg_seed_s)
    placebo_fa_withincab = build_withincab_placebo_fa(FA_dict, fp_cab, _pw_seed_s)
    print(f"    Placebo seeds (i={_s_array_i}): global={_pg_seed_s}, withincab={_pw_seed_s}")

    syn_pool  = sample_synthetic_pool(n_extra_max, wl_seeds[_si])
    scen_rng  = np.random.default_rng(scen_seed)
    job_perms = generate_job_perms(syn_pool, scen_rng)
    B_ref_s, S_ref_s = compute_B_S_ref_s(job_perms, T_THR_PRIMARY)
    print(f"    B_ref_s={B_ref_s:.2f}h  S_ref_s={S_ref_s:.4f}C*h")

    ratio_results = {}

    for r in GATE_F_RATIOS:
        rl = r_label(r)
        print(f"\n  -- ratio={rl} --")
        ratio_results[rl] = {}

        for policy_name in GATE_F_POLICIES:
            pol_seed = pol_seeds[policy_name][_si]
            rows: list[dict] = []

            # Lambda sweep
            for lam in LAMBDA_SWEEP:
                n_syn   = int(round((lam - 1.0) * n_base))
                syn_sub = (syn_pool.iloc[:n_syn].copy() if n_syn > 0
                           else pd.DataFrame(columns=list(syn_pool.columns)))
                t_pol = time.time()
                try:
                    res = capacity_replay_gate_f(syn_sub, policy_name, lam,
                                                 pol_seed, job_perms, scen_seed, r,
                                                 placebo_fa_global, placebo_fa_withincab)
                except AssertionError as exc:
                    print(f"    lam={lam:.2f} {policy_name}: INVARIANT -- {exc}")
                    res = {"lambda_val": lam, "policy": policy_name,
                           "nominal_choice_ratio": r, "invariant_violated": True,
                           "capacity_unlock_pct": n_syn / n_base * 100.0 if n_base > 0 else 0.0,
                           "B_primary_h": float("nan"), "S_primary_Cdoth": float("nan"),
                           "B_cab_ratio": float("nan"), "syn_node_hours": 0.0}
                res["lambda_val"] = lam
                rows.append(res)
                if not res.get("invariant_violated"):
                    br = res["B_primary_h"] / max(B_ref_s, 1e-9)
                    print(f"    lam={lam:.2f} r={rl} {policy_name:22s}: "
                          f"C={res['capacity_unlock_pct']:5.1f}%  B/Bref={br:.4f}  "
                          f"Bcab={res.get('B_cab_ratio', float('nan')):.4f}  "
                          f"drops={res.get('n_drop_physical',0)}/"
                          f"{res.get('n_drop_cap',0)}/{res.get('n_drop_la',0)}"
                          f"  ({time.time()-t_pol:.0f}s)")

            # Crossing classification
            cx = classify_crossing(rows, B_ref_s, S_ref_s, B_cab_hist)

            # Extend if right-censored
            if cx["right_censored"] and policy_name in (
                    "full_random", "full_fp", "position_loo", "full_fp_spread",
                    "random_spread", "fp_global_placebo", "fp_withincab_placebo"):
                print(f"    [ext] {policy_name} r={rl}: right-censored, extending...")
                for lam_ext in LAMBDA_SWEEP_EXT:
                    n_syn = int(round((lam_ext - 1.0) * n_base))
                    if n_syn > len(syn_pool):
                        print(f"    [ext] pool exhausted at lam={lam_ext:.2f}"); break
                    syn_sub = syn_pool.iloc[:n_syn].copy()
                    try:
                        res = capacity_replay_gate_f(syn_sub, policy_name, lam_ext,
                                                     pol_seed, job_perms, scen_seed, r,
                                                     placebo_fa_global, placebo_fa_withincab)
                    except AssertionError as exc:
                        res = {"lambda_val": lam_ext, "policy": policy_name,
                               "nominal_choice_ratio": r, "invariant_violated": True,
                               "capacity_unlock_pct": n_syn / n_base * 100.0,
                               "B_primary_h": float("nan"), "S_primary_Cdoth": float("nan"),
                               "B_cab_ratio": float("nan"), "syn_node_hours": 0.0}
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
                        placebo_fa_global, placebo_fa_withincab)
                    rows.extend(extra)

            ratio_results[rl][policy_name] = {
                "lambda_rows": [{k: jf(v) if isinstance(v, float) else v
                                 for k, v in row.items()} for row in rows],
                "crossing": {k: jf(v) if isinstance(v, float) else v
                             for k, v in cx.items()},
            }
            print(f"    CROSSING {policy_name:22s} r={rl}: "
                  f"status={cx['status']}  C_lower={cx['C_lower_pct']}%  "
                  f"C_upper={cx['C_upper_pct']}%")

    # r=1 negative control assertion
    r1_key = "1.0"
    if r1_key in ratio_results:
        cx_r1 = {p: ratio_results[r1_key][p]["crossing"] for p in GATE_F_POLICIES}
        fp_lo = cx_r1.get("full_fp", {}).get("C_lower_pct")
        rn_lo = cx_r1.get("full_random", {}).get("C_lower_pct")
        if fp_lo is not None and rn_lo is not None:
            if abs(float(fp_lo or 0) - float(rn_lo or 0)) < 0.01:
                print(f"  r=1 check: fp C_lower={fp_lo:.4f}  random C_lower={rn_lo:.4f}  [OK]")
            else:
                print(f"  r=1 check: WARNING fp={fp_lo} vs random={rn_lo}")

    scenario_results.append({
        "scenario_idx"    : s_abs,
        "scenario_array_i": _si,
        "scen_seed"       : scen_seed,
        "wl_seed"         : wl_seeds[_si],
        "placebo_seeds"   : {"global": _pg_seed_s, "withincab": _pw_seed_s},
        "B_ref_s"         : jf(B_ref_s),
        "S_ref_s"         : jf(S_ref_s),
        "ratios"          : ratio_results,
        "elapsed_s"       : round(time.time() - t_scen, 1),
    })
    print(f"\nScenario {s_abs} done in {time.time()-t_scen:.0f}s")

    # Checkpoint save
    _ck_tmp = CKPT_FILE.with_suffix(".tmp")
    _ck_tmp.write_text(json.dumps({
        "n_first"         : N_FIRST,
        "n_dev"           : N_DEV,
        "gate_f_ratios"   : _ckpt_ratios,
        "git_commit_full" : _PROV["git_commit_full"],
        "scenario_results": scenario_results,
    }, indent=2))
    _ck_tmp.replace(CKPT_FILE)
    print(f"    [checkpoint] {len(scenario_results)}/{N_DEV} saved -> {CKPT_FILE.name}")

# ── Save final results ────────────────────────────────────────────────────────
result = {
    "script"                         : "artifacts/manuscript_completion/runners/c2_gate_f_run.py",
    "plan_ref"                       : "manuscript-completion C2 (corrected reference + position_loo)",
    "compat_mode"                    : _is_compat,
    "compat_seed"                    : CHALLENGE_SEED if _is_compat else None,
    "git_commit_full"                : _PROV["git_commit_full"],
    "git_commit_short"               : _PROV["git_commit_short"],
    "git_tracked_dirty"              : _PROV["git_tracked_dirty"],
    "git_untracked_present"          : _PROV["git_untracked_present"],
    "git_untracked_count"            : _PROV["git_untracked_count"],
    "challenge_seed"                 : CHALLENGE_SEED,
    "primary_beta_challenge"         : BETA_CHALLENGE,
    "beta_f_frozen"                  : BETA_F_FROZEN,
    "n_scenarios_total"              : N_SCENARIOS_TOTAL,
    "scenario_first"                 : SCENARIO_FIRST,
    "n_dev"                          : N_DEV,
    "n_first"                        : N_FIRST,
    "gate_f_ratios"                  : [r_label(r) for r in GATE_F_RATIOS],
    "gate_f_policies"                : GATE_F_POLICIES,
    "lambda_sweep"                   : LAMBDA_SWEEP,
    "target_pp"                      : TARGET_PP,
    "cabinet_reference_mode"         : "corrected_timeweighted_total_p99_local",
    "f2_reference_sha256"            : _C2_CAB_REF_SHA,
    "f2_replay_denominator_sha256"   : _C2_DENOM_SHA,
    "B_cab_hist_F2_replay_h"         : _C2_B_CAB_HIST_F2,
    "scientific_freeze_commit"       : "5733b73b",
    "per_scenario_placebo_seed_root" : _R3_ROOT,
    "scenario_results"               : scenario_results,
    "elapsed_total_s"                : round(time.time() - t_script, 1),
}
OUT_FILE.write_text(json.dumps(result, indent=2))
print(f"\nSaved: {OUT_FILE}")
CKPT_FILE.unlink(missing_ok=True)
print(f"Total elapsed: {time.time()-t_script:.0f}s")
print("\nNEXT: Run preflight before manuscript-completion C2 scenarios sc30-54.")
