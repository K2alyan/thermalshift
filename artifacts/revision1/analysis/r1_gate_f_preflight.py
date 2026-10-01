#!/usr/bin/env python3
"""
Gate F Preflight Audit  (r1_gate_f_preflight.py)

Produces two durable audit records:
  gate_f_audit_unr_sc0.json  — field-by-field comparison of unrestricted sc0
                               against authoritative M4 reference files
  gate_f_audit_r1_sc0.json   — event-level identity verification for r=1 sc0:
                               selected-set identity, look-ahead identity,
                               state-snapshot identity, pairwise verdict audit

THERMALSHIFT_DATA_DIR must point to the directory containing
  frontier-completed-job-info.parquet
(required for the event-level r=1 verification only).

Usage:
  python r1_gate_f_preflight.py
"""

import sys, io, os, json, time, heapq, math, hashlib, statistics, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).resolve().parent))
from r1_gate_f_helpers import gate_f_shortlist as _gf_shortlist

REPO_ROOT = Path(__file__).resolve().parents[3]
P1_DIR    = REPO_ROOT / "artifacts" / "phase1" / "analysis"
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR   = REV1_DIR / "results"
TABLE_DIR = REV1_DIR / "tables"
DATA_DIR  = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

GATE_F_POLICIES = ["full_random", "full_fp", "full_loc", "full_fp_spread"]
GATE_F_ALG = {
    "full_random"    : "random",
    "full_fp"        : "fp",
    "full_loc"       : "loc",
    "full_fp_spread" : "fp_spread",
}

# Authoritative M4 source for each Gate F policy
POLICY_REF_FILE = {
    "full_random"    : "m4_random_canonical.json",
    "full_fp"        : "m4_fair_baselines.json",
    "full_loc"       : "m4_canonical_policies.json",
    "full_fp_spread" : "m4_fair_baselines.json",
}

NUMERIC_FIELDS = [
    "capacity_unlock_pct", "B_primary_ratio", "S_primary_ratio",
    "B_cab_ratio", "syn_node_hours", "B_primary_h", "S_primary_Cdoth",
]
EXACT_INT_FIELDS = [
    "n_syn_admit", "n_drop_cap", "n_drop_physical", "n_drop_la",
    "n_base_unserved",
]
EXACT_OTHER_FIELDS = ["infeasible", "first_binding"]

COMPARE_FIELDS = NUMERIC_FIELDS + EXACT_INT_FIELDS + EXACT_OTHER_FIELDS

# Lambda points at which to run event-level r=1 verification
R1_VERIFY_LAMBDAS = [1.0, 1.06, 1.30]

# ── Frozen M4 constants ────────────────────────────────────────────────────────
BETA_F_FROZEN   = 1.12484352
T_THR_PRIMARY   = 63.625
DELTA_CAP       = 0.10
N_BINS          = 5
N_SCENARIOS     = 30
SCENARIO_SEED   = 42
TARGET_PP       = 0.50
N_REFINE_GRID   = 3
POLICY_IDS = ["full_random", "full_fp", "full_loc", "full_compact",
              "marginal_random", "marginal_fp", "full_fp_spread"]


def git_provenance() -> dict:
    try:
        full  = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
        short = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=str(REPO_ROOT), text=True).strip())
    except Exception:
        full = short = "unknown"; dirty = None
    return {"git_commit_full": full, "git_commit_short": short, "git_dirty": dirty}


# ══════════════════════════════════════════════════════════════════════════════
# PART 1 — Unrestricted sc0 audit (no simulation data required)
# ══════════════════════════════════════════════════════════════════════════════
def load_m4_rows(pol: str, ref: dict) -> tuple[list, dict, float, float]:
    """
    Returns (lambda_rows, crossing_dict, B_ref_h, S_ref_h) from a M4 JSON.
    Computes B_primary_ratio / S_primary_ratio if not stored.
    """
    B_ref = ref["scenario_results"][0].get(
        "B_ref_s_primary_h", ref["scenario_results"][0].get("B_ref_s", None))
    S_ref = ref["scenario_results"][0].get(
        "S_ref_s_primary", ref["scenario_results"][0].get("S_ref_s", None))
    lr    = ref["scenario_results"][0]["lambda_rows"]
    rows  = lr[pol] if isinstance(lr, dict) else lr
    cx    = ref["scenario_results"][0].get("crossings", {}).get(pol, {})
    # Ensure B_primary_ratio / S_primary_ratio exist
    for r in rows:
        if "B_primary_ratio" not in r and "B_primary_h" in r and B_ref:
            r["B_primary_ratio"] = r["B_primary_h"] / max(B_ref, 1e-9)
        if "S_primary_ratio" not in r and "S_primary_Cdoth" in r and S_ref:
            r["S_primary_ratio"] = r["S_primary_Cdoth"] / max(S_ref, 1e-9)
    return rows, cx, float(B_ref) if B_ref is not None else None, float(S_ref) if S_ref is not None else None


def compare_rows(gf_rows: list, ref_rows: list, B_ref: float, S_ref: float,
                 pol: str) -> dict:
    """
    Compare Gate F unrestricted lambda_rows against M4 reference rows.
    Rows are matched by lambda_val (float key).
    """
    def fkey(v):
        return round(float(v), 10)

    gf_by_lam  = {fkey(r["lambda_val"]): r for r in gf_rows}
    ref_by_lam = {fkey(r["lambda_val"]): r for r in ref_rows}

    all_lams = sorted(set(gf_by_lam) | set(ref_by_lam))
    lams_expected = sorted(ref_by_lam.keys())
    lams_observed = sorted(gf_by_lam.keys())
    n_expected = len(lams_expected)
    n_observed = len(lams_observed)
    n_matched  = len(set(gf_by_lam) & set(ref_by_lam))

    exact_match_by_field: dict[str, bool] = {}
    max_abs_diff: dict[str, float | None] = {}
    mismatched_rows: list[dict] = []

    for field in COMPARE_FIELDS:
        exact_all = True
        diffs     = []
        for lam in all_lams:
            gf_row  = gf_by_lam.get(lam)
            ref_row = ref_by_lam.get(lam)
            if gf_row is None or ref_row is None:
                continue
            gf_val  = gf_row.get(field)
            ref_val = ref_row.get(field)
            if gf_val is None and ref_val is None:
                continue
            if type(gf_val) != type(ref_val) or gf_val != ref_val:
                exact_all = False
                if isinstance(gf_val, (int, float)) and isinstance(ref_val, (int, float)):
                    try:
                        diffs.append(abs(float(gf_val) - float(ref_val)))
                    except (TypeError, ValueError):
                        pass
        exact_match_by_field[field] = exact_all
        max_abs_diff[field] = max(diffs) if diffs else (0.0 if exact_all else None)

    # Per-row detail for any mismatch
    for lam in all_lams:
        gf_row  = gf_by_lam.get(lam)
        ref_row = ref_by_lam.get(lam)
        if gf_row is None or ref_row is None:
            continue
        row_diffs = {}
        for field in COMPARE_FIELDS:
            gv = gf_row.get(field)
            rv = ref_row.get(field)
            if gv != rv:
                row_diffs[field] = {"gf": gv, "ref": rv}
        if row_diffs:
            mismatched_rows.append({"lambda_val": lam, "diffs": row_diffs})

    exact_row_match = (n_matched == n_expected == n_observed
                       and len(mismatched_rows) == 0)
    return {
        "lambda_values_expected"      : lams_expected,
        "lambda_values_observed"      : lams_observed,
        "n_rows_expected"             : n_expected,
        "n_rows_observed"             : n_observed,
        "n_rows_matched_by_lambda"    : n_matched,
        "exact_row_match"             : exact_row_match,
        "exact_match_by_field"        : exact_match_by_field,
        "max_abs_diff_by_numeric_field": {f: max_abs_diff[f] for f in NUMERIC_FIELDS},
        "mismatched_rows"             : mismatched_rows,
    }


def compare_crossings(gf_cx: dict, ref_cx: dict) -> dict:
    return {
        "crossing_status_match"   : gf_cx.get("status")         == ref_cx.get("status"),
        "C_lower_match"           : gf_cx.get("C_lower_pct")    == ref_cx.get("C_lower_pct"),
        "C_upper_match"           : gf_cx.get("C_upper_pct")    == ref_cx.get("C_upper_pct"),
        "first_binding_match"     : gf_cx.get("first_binding_constraint")
                                    == ref_cx.get("first_binding_constraint"),
        "right_censored_match"    : gf_cx.get("right_censored") == ref_cx.get("right_censored"),
        "gf_crossing"             : gf_cx,
        "ref_crossing"            : ref_cx,
    }


def run_unrestricted_audit(gf_sc0: dict, refs: dict) -> dict:
    print("\n" + "=" * 70)
    print("PART 1 — Unrestricted sc0 audit (field-by-field vs M4 references)")
    print("=" * 70)
    pol_audits = {}
    overall_pass = True
    for pol in GATE_F_POLICIES:
        ref_name = POLICY_REF_FILE[pol]
        ref      = refs[ref_name]
        ref_rows, ref_cx, B_ref, S_ref = load_m4_rows(pol, ref)
        gf_rows  = gf_sc0["ratios"]["unrestricted"][pol]["lambda_rows"]
        gf_cx    = gf_sc0["ratios"]["unrestricted"][pol]["crossing"]

        # Ensure GF rows have B_primary_ratio / S_primary_ratio (added by classify_crossing)
        # Already present from the GF output, but recompute if missing
        gf_B_ref = gf_sc0.get("B_ref_s", B_ref)
        gf_S_ref = gf_sc0.get("S_ref_s", S_ref)
        for r in gf_rows:
            if "B_primary_ratio" not in r and "B_primary_h" in r and gf_B_ref:
                r["B_primary_ratio"] = r["B_primary_h"] / max(float(gf_B_ref), 1e-9)
            if "S_primary_ratio" not in r and "S_primary_Cdoth" in r and gf_S_ref:
                r["S_primary_ratio"] = r["S_primary_Cdoth"] / max(float(gf_S_ref), 1e-9)

        row_audit = compare_rows(gf_rows, ref_rows, B_ref, S_ref, pol)
        cx_audit  = compare_crossings(gf_cx, ref_cx)

        all_exact     = all(row_audit["exact_match_by_field"].values())
        cx_all_match  = (cx_audit["C_lower_match"] and cx_audit["C_upper_match"]
                         and cx_audit["crossing_status_match"])
        pol_pass = row_audit["exact_row_match"] and cx_all_match
        overall_pass = overall_pass and pol_pass

        status = "PASS" if pol_pass else "FAIL"
        print(f"  {pol:20s} [{ref_name}]  {status}")
        if not row_audit["exact_row_match"]:
            print(f"    n_rows: exp={row_audit['n_rows_expected']} "
                  f"obs={row_audit['n_rows_observed']} "
                  f"matched={row_audit['n_rows_matched_by_lambda']}")
        if row_audit["mismatched_rows"]:
            for mr in row_audit["mismatched_rows"][:3]:
                print(f"    lam={mr['lambda_val']:.6f}  diffs={mr['diffs']}")
        max_diffs = {f: d for f, d in row_audit["max_abs_diff_by_numeric_field"].items()
                     if d is not None and d > 0.0}
        if max_diffs:
            print(f"    max_abs_diff: {max_diffs}")
        else:
            print(f"    all numeric fields: max_abs_diff=0.0 (exact)")
        if not cx_all_match:
            print(f"    crossing mismatch: {cx_audit}")

        pol_audits[pol] = {
            "authoritative_source_file" : ref_name,
            "scenario_idx"              : 0,
            **row_audit,
            **cx_audit,
        }

    return {"overall_pass": overall_pass, "policies": pol_audits}


# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING — identical to r1_gate_f_run.py
# ══════════════════════════════════════════════════════════════════════════════
def load_simulation_data():
    print("\n" + "=" * 70)
    print("PART 2 — Loading simulation data for r=1 event-level verification")
    print("=" * 70)
    t0 = time.time()

    print("[0] Loading inputs ...")
    fp_df    = pd.read_parquet(P1_DIR / "phase3a_fingerprint_2024.parquet")
    test_df  = pd.read_parquet(P1_DIR / "phase3a_test_set.parquet")
    all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
    all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
    fp_df.index.name = "node"
    cohort_set  = set(fp_df.index)
    FA_dict     = fp_df["FA_2024"].to_dict()
    cohort_list = sorted(cohort_set)
    n_cohort    = len(cohort_list)
    print(f"    fp nodes: {n_cohort}  all jobs: {len(all_jobs):,}")

    print("[1] Building topology ...")
    fleet_topo  = pd.read_csv(TABLE_DIR / "fleet_node_topology.csv")
    node_to_cab = dict(zip(fleet_topo["hostname"].values,
                           fleet_topo["cabinet"].values.astype(int)))
    all_cabinets = sorted(set(node_to_cab.values()))
    fp_cab = {n: node_to_cab[n] for n in cohort_list if n in node_to_cab}

    print("[2] Building LOC fingerprint ...")
    fp_topo = pd.read_csv(TABLE_DIR / "fp_node_topology.csv")
    fp_topo["pos_key"] = (fp_topo["chassis"].astype(str) + "_" +
                          fp_topo["slot"].astype(str)    + "_" +
                          fp_topo["board"].astype(str)   + "_" +
                          fp_topo["node_pos"].astype(str))
    fp_topo["FA_2024"] = fp_topo["hostname"].map(FA_dict)
    pos_mean = fp_topo.groupby("pos_key")["FA_2024"].mean().rename("FA_loc")
    fp_topo  = fp_topo.join(pos_mean, on="pos_key")
    LOC_FA_dict = dict(zip(fp_topo["hostname"].values, fp_topo["FA_loc"].values))
    _gmean = float(np.nanmean(list(LOC_FA_dict.values())))
    LOC_FA_dict = {k: (v if not np.isnan(v) else _gmean) for k, v in LOC_FA_dict.items()}

    print("[3] Loading cabinet P99 ...")
    with open(OUT_DIR / "cabinet_power_envelopes.json") as fh:
        cab_env = json.load(fh)
    cab_p99_W = {int(float(k)): v * 1e3
                 for k, v in cab_env["per_cabinet_p99_kW_correct"].items()}
    _p99_med  = float(np.median(list(cab_p99_W.values())))
    cab_p99_W = {c: cab_p99_W.get(c, _p99_med) for c in all_cabinets}

    def _col_to_dt64ms(series):
        s = pd.to_datetime(series, utc=True)
        return s.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ms]")

    print("[4] Building schedule arrays ...")
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

    print("[5] Aggregating test-job summaries ...")
    test_id_set = set(test_df["job_idx"].astype(int))
    test_df2 = test_df.copy()
    job_agg = (test_df.groupby("job_idx")
               .agg(F_hist_mean=("F_2024", "mean"), n_cohort=("node", "count"),
                    T_p95_hist=("T_p95", "mean"), hist_nodes=("node", list))
               .reset_index())
    meta = (all_jobs[["job_idx_int", "node_count", "start_time", "end_time",
                       "mean_power", "run_time"]]
            .rename(columns={"job_idx_int": "job_idx"}))
    job_agg = job_agg.merge(meta, on="job_idx", how="left")
    job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)
    jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)
    n_base = len(jobs_sorted)
    print(f"    n_base={n_base}  hist_fleet_avg={jobs_sorted['n_cohort'].mean():.3f}")

    print("[6] Building residual model ...")
    test_df2["job_mean_T"] = test_df2.groupby("job_idx")["T_p95"].transform("mean")
    alpha_map = test_df2.groupby("job_idx")["job_mean_T"].first().to_dict()
    test_df2["delta_T_p95"] = test_df2["T_p95"] - test_df2["job_mean_T"]
    test_df2["pred_frozen"]  = BETA_F_FROZEN * test_df2["F_2024"]
    test_df2["residual"]     = test_df2["delta_T_p95"] - test_df2["pred_frozen"]
    job_residuals: dict[int, tuple] = {}
    for jid, grp in test_df2.groupby("job_idx"):
        jid   = int(jid)
        grp_s = grp.sort_values("F_2024")
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

    print("[7] Precomputing background busy arrays ...")
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

    print("[8] Precomputing cabinet background power ...")
    _all_jids = all_jobs["job_idx_int"].values
    _all_Pj   = np.where(all_jobs["mean_power"].isna().values, 0.0,
                         all_jobs["mean_power"].values.astype(float))
    _all_nc   = np.maximum(all_jobs["node_count"].values.astype(int), 1)
    _all_hl   = all_jobs["host_list"].values
    _all_st   = _col_to_dt64ms(all_jobs["start_time"])
    _all_et   = _col_to_dt64ms(all_jobs["end_time"])
    bg_records: list[dict] = []
    cohort_hist_records: list[dict] = []
    for jid, P_j, nc, hl, t_s, t_e in zip(_all_jids, _all_Pj, _all_nc, _all_hl,
                                            _all_st, _all_et):
        ppn = P_j / nc
        ncc: dict[int, int] = {}; chc: dict[int, int] = {}
        for hn in hl:
            c = node_to_cab.get(hn, -1)
            if c < 0: continue
            if hn in cohort_set: chc[c] = chc.get(c, 0) + 1
            else:                ncc[c] = ncc.get(c, 0) + 1
        if ncc:
            bg_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": ncc})
        if int(jid) in test_id_set and chc:
            cohort_hist_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": chc})

    def _rec_ts_ms(r):
        v = r["t_s"]
        return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))
    def _rec_te_ms(r):
        v = r["t_e"]
        return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))

    bg_events_sorted: list[tuple] = []
    for _r in bg_records:
        _ppn = _r["ppn"]
        _ts  = int(_r["t_s"].astype("int64"))
        _te  = int(_r["t_e"].astype("int64"))
        for _c, _n in _r["cab_counts"].items():
            bg_events_sorted.append((_ts, +1, _c, _ppn * _n))
            bg_events_sorted.append((_te, -1, _c, _ppn * _n))
    bg_events_sorted.sort()

    hist_fleet_avg = float(jobs_sorted["n_cohort"].mean())
    print(f"    loaded in {time.time()-t0:.1f}s")

    return dict(
        cohort_set=cohort_set, cohort_list=cohort_list, FA_dict=FA_dict,
        n_cohort=n_cohort, fp_cab=fp_cab, LOC_FA_dict=LOC_FA_dict,
        node_to_cab=node_to_cab, all_cabinets=all_cabinets, cab_p99_W=cab_p99_W,
        jobs_sorted=jobs_sorted, n_base=n_base, job_residuals=job_residuals,
        alpha_map=alpha_map, hist_fleet_avg=hist_fleet_avg,
        bg_st_ms=bg_st_ms, bg_et_ms=bg_et_ms, bg_cn=bg_cn,
        bg_busy_per_job=bg_busy_per_job, bg_events_sorted=bg_events_sorted,
        cohort_hist_records=cohort_hist_records,
        hist_starts_ms=hist_starts_ms, hist_ends_ms=hist_ends_ms,
        hist_k_arr=hist_k_arr, hist_jids_arr=hist_jids_arr,
        _col_to_dt64ms=_col_to_dt64ms,
    )


# ══════════════════════════════════════════════════════════════════════════════
# PART 2 — r=1 event-level identity verification
# ══════════════════════════════════════════════════════════════════════════════
def fp_equivalent(a: float, b: float) -> bool:
    """True iff |a-b| <= max(8*spacing(max(|a|,|b|,1)), 1e-12)."""
    if a == b:
        return True
    scale = max(abs(a), abs(b), 1.0)
    tol = max(8 * np.spacing(scale), 1e-12)
    return abs(a - b) <= tol


def select_fp(available, k, FA_dict):
    s = sorted(available, key=lambda n: (FA_dict[n], n))
    return s[:min(k, len(s))]

def select_loc(available, k, LOC_FA_dict):
    s = sorted(available, key=lambda n: (LOC_FA_dict.get(n, 0.0), n))
    return s[:min(k, len(s))]

def select_random(available, k, rng):
    s = sorted(available)
    idx = rng.choice(len(s), size=min(k, len(s)), replace=False)
    return [s[i] for i in idx]

def select_fp_spread(available, k, fp_cab, FA_dict, cab_active_count):
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


def verify_r1_single_lambda(lam: float, syn_subset, scen_seed: int,
                             pol_seeds: dict, job_perms: dict,
                             sim: dict) -> dict:
    """
    Run all 4 Gate F policies simultaneously at r=1.0 for one lambda.
    Maintain SEPARATE per-policy state (more rigorous than shared state).
    Assert identity at each selection event.
    Returns event-level counts and first divergence info if any.
    """
    cohort_set    = sim["cohort_set"]
    cohort_list   = sim["cohort_list"]
    FA_dict       = sim["FA_dict"]
    LOC_FA_dict   = sim["LOC_FA_dict"]
    fp_cab        = sim["fp_cab"]
    n_cohort      = sim["n_cohort"]
    jobs_sorted   = sim["jobs_sorted"]
    job_residuals = sim["job_residuals"]
    bg_st_ms      = sim["bg_st_ms"]
    bg_et_ms      = sim["bg_et_ms"]
    bg_cn         = sim["bg_cn"]
    bg_busy_per_job = sim["bg_busy_per_job"]
    hist_starts_ms  = sim["hist_starts_ms"]
    hist_ends_ms    = sim["hist_ends_ms"]
    hist_k_arr      = sim["hist_k_arr"]
    hist_jids_arr   = sim["hist_jids_arr"]
    hist_fleet_avg  = sim["hist_fleet_avg"]
    _col_to_dt64ms  = sim["_col_to_dt64ms"]

    u_max = (1.0 + DELTA_CAP) * lam * hist_fleet_avg
    n_syn = len(syn_subset)

    def bg_busy_at_ms(t_ms):
        mask = (bg_st_ms <= t_ms) & (bg_et_ms > t_ms)
        return frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

    def look_ahead_safe(selected_nodes, t_s_ms, t_e_ms, cf_busy_ms_pol):
        overlap = (hist_starts_ms > t_s_ms) & (hist_starts_ms < t_e_ms)
        if not overlap.any():
            return True
        s_nodes = frozenset(selected_nodes)
        for idx in np.where(overlap)[0]:
            t_h_ms  = int(hist_starts_ms[idx])
            k_h     = int(hist_k_arr[idx])
            jid_h   = int(hist_jids_arr[idx])
            bg_at_h = bg_busy_per_job[jid_h]
            cf_at_h = frozenset(n for n, te_ms in cf_busy_ms_pol.items() if te_ms > t_h_ms)
            blocked = bg_at_h | cf_at_h | s_nodes
            fb_mask = ((hist_starts_ms > t_s_ms) & (hist_starts_ms <= t_h_ms)
                       & (hist_ends_ms > t_h_ms))
            fb_mask = fb_mask.copy(); fb_mask[idx] = False
            fk = min(int(hist_k_arr[fb_mask].sum()), max(0, n_cohort - len(blocked)))
            if n_cohort - len(blocked) - fk < k_h:
                return False
        return True

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
    _cgen_ord = (combined["generation_ordinal"].values
                 if "generation_ordinal" in combined.columns else None)

    # Per-policy state
    PS = {}
    for pol in GATE_F_POLICIES:
        PS[pol] = {
            "cf_busy_ms"     : {},
            "cf_busy_active" : set(),
            "cf_expire_heap" : [],
            "cf_util"        : {n: 0.0 for n in cohort_list},
            "cap_exceeded"   : set(),
            "available_set"  : set(cohort_set),
            "_rng"           : np.random.default_rng(pol_seeds[pol]),
            "cab_active"     : {},
        }

    n_events_checked         = 0   # ALL scheduling events (including Stage-1 drops)
    n_sel_events_checked     = 0   # events that passed Stage 1 → selection verified
    n_sel_identical          = 0
    n_stage1_drop_checked    = 0   # Stage-1 drops (synthetic only)
    n_stage1_drop_agree      = 0   # drops where all policies agree on drop
    n_la_checked             = 0
    n_la_identical           = 0
    n_state_checked          = 0
    n_state_identical        = 0
    n_avail_identical        = 0
    first_sel_divergence     = None
    first_la_divergence      = None
    first_state_divergence   = None
    first_drop_disagree      = None

    for _i in range(len(combined)):
        is_syn     = bool(_cissyn[_i])
        t_j_ms     = int(_cst_ms[_i])
        t_e_ms     = int(_cet_ms[_i])
        rt_h       = float(_crt_h[_i])
        k          = int(_ck[_i])
        jid        = int(_cjid[_i])
        parent_jid = int(_cpid[_i])

        # Expire per policy
        for pol in GATE_F_POLICIES:
            s = PS[pol]
            while s["cf_expire_heap"] and s["cf_expire_heap"][0][0] <= t_j_ms:
                exp_ms, exp_n = heapq.heappop(s["cf_expire_heap"])
                if s["cf_busy_ms"].get(exp_n, -1) == exp_ms:
                    s["cf_busy_active"].discard(exp_n)
                    ec = fp_cab.get(exp_n, -1)
                    if ec >= 0 and s["cab_active"].get(ec, 0) > 0:
                        s["cab_active"][ec] -= 1
                    if exp_n not in s["cap_exceeded"]:
                        s["available_set"].add(exp_n)

        # Background busy (same for all policies)
        if is_syn:
            bg_busy = bg_busy_at_ms(t_j_ms)
        else:
            bg_busy = bg_busy_per_job.get(parent_jid, frozenset())

        # Pre-compute event_uid (needed for Stage-1 drops in count reconciliation)
        if is_syn:
            _gen_ord = int(_cgen_ord[_i]) if _cgen_ord is not None else abs(jid) - 1
            event_uid = f"syn:{scen_seed}:{_gen_ord}"
        else:
            event_uid = f"base:{jid}"

        # Stage 1: compute available per policy and verify identity
        available_per_pol: dict[str, list | None] = {}
        for pol in GATE_F_POLICIES:
            s = PS[pol]
            avail_capped = s["available_set"].difference(bg_busy)
            if is_syn:
                if len(avail_capped) < k:
                    available_per_pol[pol] = None  # drop
                    continue
                available_per_pol[pol] = list(avail_capped)
            else:
                if len(avail_capped) >= k:
                    available_per_pol[pol] = list(avail_capped)
                else:
                    avail_unc = set(cohort_set).difference(s["cf_busy_active"], bg_busy)
                    available_per_pol[pol] = list(avail_unc)

        # State snapshot (available_set size, cap_exceeded, cf_busy_active)
        state_vals = {
            pol: (len(PS[pol]["available_set"]),
                  len(PS[pol]["cap_exceeded"]),
                  len(PS[pol]["cf_busy_active"]))
            for pol in GATE_F_POLICIES
        }
        ref_state = state_vals[GATE_F_POLICIES[0]]
        state_identical = all(state_vals[p] == ref_state for p in GATE_F_POLICIES[1:])
        n_state_checked += 1
        if state_identical:
            n_state_identical += 1
        elif first_state_divergence is None:
            first_state_divergence = {"event_idx": _i, "is_syn": is_syn,
                                      "state_vals": state_vals}

        # Count every scheduling event (including Stage-1 drops)
        n_events_checked += 1

        # Stage-1 drop: all policies must agree (at r=1 they share identical state)
        any_drop = any(v is None for v in available_per_pol.values())
        all_drop = all(v is None for v in available_per_pol.values())
        if any_drop:
            n_stage1_drop_checked += 1
            drop_agree = (any_drop == all_drop)
            if drop_agree:
                n_stage1_drop_agree += 1
            elif first_drop_disagree is None:
                first_drop_disagree = {
                    "event_idx" : _i,
                    "event_uid" : event_uid,
                    "drop_mask" : {p: available_per_pol[p] is None for p in GATE_F_POLICIES},
                }
            continue

        # Available sets should be identical (verify)
        ref_avail_set = frozenset(available_per_pol[GATE_F_POLICIES[0]])
        avail_identical = all(
            frozenset(available_per_pol[p]) == ref_avail_set
            for p in GATE_F_POLICIES[1:])
        if avail_identical:
            n_avail_identical += 1

        # Stage 1½ — Gate F at r=1.0
        # event_uid already computed above (before Stage-1 drop check)

        # Compute shortlist from first policy's available (identical across policies)
        # r=1.0: m = min(ceil(1.0 * k), |A_full|) = k (when |A_full| >= k, guaranteed above)
        C_p_r = _gf_shortlist(available_per_pol[GATE_F_POLICIES[0]],
                               scen_seed, event_uid, 1.0, k)
        # |C_p_r| = k (guaranteed for syn since avail >= k; base may < k handled above)

        # Stage 2 — run all 4 selectors on C_p_r
        selections: dict[str, frozenset] = {}
        for pol in GATE_F_POLICIES:
            alg = GATE_F_ALG[pol]
            s   = PS[pol]
            if alg == "fp":
                sel = select_fp(C_p_r, k, FA_dict)
            elif alg == "loc":
                sel = select_loc(C_p_r, k, LOC_FA_dict)
            elif alg == "fp_spread":
                sel = select_fp_spread(C_p_r, k, fp_cab, FA_dict, s["cab_active"])
            else:
                sel = select_random(C_p_r, k, s["_rng"])
            selections[pol] = frozenset(sel)

        # Verify selection identity
        ref_sel = selections[GATE_F_POLICIES[0]]
        sel_identical = all(selections[p] == ref_sel for p in GATE_F_POLICIES[1:])
        n_sel_events_checked += 1
        if sel_identical:
            n_sel_identical += 1
        elif first_sel_divergence is None:
            first_sel_divergence = {
                "event_idx"  : _i,
                "event_uid"  : event_uid,
                "is_syn"     : is_syn,
                "shortlist"  : C_p_r[:10],
                "selections" : {p: sorted(selections[p]) for p in GATE_F_POLICIES},
            }

        # Stage 3 — look-ahead (synthetic only; identical since sel identical)
        if is_syn and sel_identical:
            # run look-ahead once per policy using THAT policy's cf_busy_ms
            la_results: dict[str, bool] = {}
            for pol in GATE_F_POLICIES:
                la_results[pol] = look_ahead_safe(
                    list(ref_sel), t_j_ms, t_e_ms, PS[pol]["cf_busy_ms"])
            ref_la = la_results[GATE_F_POLICIES[0]]
            la_ident = all(la_results[p] == ref_la for p in GATE_F_POLICIES[1:])
            n_la_checked += 1
            if la_ident:
                n_la_identical += 1
            elif first_la_divergence is None:
                first_la_divergence = {
                    "event_idx"  : _i,
                    "event_uid"  : event_uid,
                    "la_results" : la_results,
                }
            if not ref_la:
                continue  # look-ahead drop — no state update

        # State update (identical for all policies since ref_sel used)
        for pol in GATE_F_POLICIES:
            s = PS[pol]
            for n in ref_sel:
                s["cf_busy_ms"][n]  = t_e_ms
                s["cf_busy_active"].add(n)
                s["available_set"].discard(n)
                heapq.heappush(s["cf_expire_heap"], (t_e_ms, n))
                s["cf_util"][n] = s["cf_util"].get(n, 0.0) + rt_h
                if s["cf_util"][n] >= u_max and n not in s["cap_exceeded"]:
                    s["cap_exceeded"].add(n)
                    s["available_set"].discard(n)
                nc = fp_cab.get(n, -1)
                if nc >= 0:
                    s["cab_active"][nc] = s["cab_active"].get(nc, 0) + 1

    count_reconcile = (n_events_checked == len(combined))
    return {
        "lam"                             : lam,
        "n_combined_events"               : len(combined),
        "n_events_checked"                : n_events_checked,
        "count_reconcile_pass"            : count_reconcile,
        "n_stage1_drop_checked"           : n_stage1_drop_checked,
        "n_stage1_drop_agree"             : n_stage1_drop_agree,
        "stage1_drop_agree_pass"          : n_stage1_drop_agree == n_stage1_drop_checked,
        "n_sel_events_checked"            : n_sel_events_checked,
        "n_events_selected_sets_identical": n_sel_identical,
        "n_avail_sets_identical"          : n_avail_identical,
        "n_lookahead_events_checked"      : n_la_checked,
        "n_lookahead_outcomes_identical"  : n_la_identical,
        "n_state_snapshots_checked"       : n_state_checked,
        "n_state_snapshots_identical"     : n_state_identical,
        "sel_pass"                        : n_sel_identical == n_sel_events_checked,
        "la_pass"                         : n_la_identical  == n_la_checked,
        "state_pass"                      : n_state_identical == n_state_checked,
        "first_sel_divergence"            : first_sel_divergence,
        "first_la_divergence"             : first_la_divergence,
        "first_state_divergence"          : first_state_divergence,
        "first_drop_disagree"             : first_drop_disagree,
    }


# ── Pairwise verdict and delta-symmetry audit ─────────────────────────────────
def pairwise_r1_audit(gf_r1_sc0: dict) -> dict:
    """
    From the saved r=1 sc0 output, compute all 5 pairwise verdicts and verify
    delta_lo = L - U, delta_hi = U - L, delta_lo = -delta_hi.
    """
    cx = {pol: gf_r1_sc0["scenario_results"][0]["ratios"]["1.0"][pol]["crossing"]
          for pol in GATE_F_POLICIES}
    lowers = {p: cx[p]["C_lower_pct"] for p in GATE_F_POLICIES}
    uppers = {p: cx[p]["C_upper_pct"] for p in GATE_F_POLICIES}

    # All crossing intervals should be identical across policies
    ref_lo = lowers[GATE_F_POLICIES[0]]
    ref_hi = uppers[GATE_F_POLICIES[0]]
    intervals_identical = all(
        lowers[p] == ref_lo and uppers[p] == ref_hi
        for p in GATE_F_POLICIES)

    PAIRS = [(GATE_F_POLICIES[i], GATE_F_POLICIES[j])
             for i in range(len(GATE_F_POLICIES))
             for j in range(i+1, len(GATE_F_POLICIES))]

    verdicts: dict[str, dict] = {}
    all_indistinguishable = True
    delta_symmetry_pass   = True
    TOL = 1e-9

    for A, B in PAIRS:
        pair_key = f"{A}_vs_{B}"
        lo_A, hi_A = lowers[A], uppers[A]
        lo_B, hi_B = lowers[B], uppers[B]
        if lo_A is None or hi_A is None or lo_B is None or hi_B is None:
            verdicts[pair_key] = {"verdict": "undefined", "reason": "right_censored"}
            all_indistinguishable = False
            continue
        delta_lo = lo_A - hi_B
        delta_hi = hi_A - lo_B
        # Verdict
        if delta_lo > 0:
            verdict = "A_definitely_better"
        elif delta_hi < 0:
            verdict = "B_definitely_better"
        else:
            verdict = "indistinguishable"
        # Delta symmetry (for identical policies lo_A==lo_B, hi_A==hi_B)
        sym_check = abs(delta_lo + delta_hi) < TOL  # delta_lo = -delta_hi iff delta_lo+delta_hi=0
        # For identical intervals [L,U]: delta_lo = L-U, delta_hi = U-L => sum = 0 ✓
        verdicts[pair_key] = {
            "verdict"       : verdict,
            "delta_lo"      : delta_lo,
            "delta_hi"      : delta_hi,
            "delta_symmetry": sym_check,
            "C_lower_A"     : lo_A, "C_upper_A": hi_A,
            "C_lower_B"     : lo_B, "C_upper_B": hi_B,
        }
        if verdict != "indistinguishable":
            all_indistinguishable = False
        if not sym_check:
            delta_symmetry_pass = False

    return {
        "crossing_intervals"          : {p: {"C_lower_pct": lowers[p], "C_upper_pct": uppers[p]}
                                          for p in GATE_F_POLICIES},
        "crossing_intervals_identical": intervals_identical,
        "pairwise_verdicts"           : verdicts,
        "pairwise_verdicts_all_indistinguishable": all_indistinguishable,
        "delta_interval_symmetry_pass": delta_symmetry_pass,
        "note_on_delta_lo"            : (
            "delta_lo = C_lower_A - C_upper_B. For identical policies with interval [L,U]: "
            "delta_lo = L - U (<=0, not zero). Do not assert delta_lo == 0."
        ),
    }


# ── Lambda-row identity check (from saved r=1 output) ────────────────────────
def r1_lambda_rows_identical(gf_r1_sc0: dict) -> dict:
    """
    Check that saved lambda_rows are equivalent across all 4 policies at r=1.

    Count fields (n_syn_admit, drops): must be bit-for-bit identical — hard assertion.
    Float fields: must satisfy fp_equivalent(a, b), i.e. |a-b| <= max(8*ULP, 1e-12).

    At r=1 all policies select the same k-node SET but in different orderings
    (fp: FA-ascending, random: random permutation, etc.). numpy computes
    (T_hats - thr).clip(min=0).sum() in insertion order, so different orderings
    produce ±1 ULP differences in S_primary_Cdoth. This is expected floating-point
    behavior, not a scientific deviation.
    """
    ratios_r1 = gf_r1_sc0["scenario_results"][0]["ratios"]["1.0"]
    pol0_rows = ratios_r1[GATE_F_POLICIES[0]]["lambda_rows"]
    pol0_lams = {r["lambda_val"] for r in pol0_rows}

    INT_ROW   = ["n_syn_admit", "n_drop_cap", "n_drop_physical", "n_drop_la",
                 "n_base_unserved"]
    FLOAT_ROW = ["capacity_unlock_pct", "B_primary_h", "S_primary_Cdoth",
                 "B_cab_ratio", "syn_node_hours", "B_primary_ratio", "S_primary_ratio"]

    count_mismatches: list[dict] = []
    float_mismatches: list[dict] = []
    field_max_diff: dict[str, float] = {f: 0.0 for f in FLOAT_ROW}
    field_max_tol:  dict[str, float] = {f: 0.0 for f in FLOAT_ROW}
    field_fp_pass:  dict[str, bool]  = {f: True for f in FLOAT_ROW}

    pol0_by_lam = {r["lambda_val"]: r for r in pol0_rows}
    for pol in GATE_F_POLICIES[1:]:
        pol_rows   = ratios_r1[pol]["lambda_rows"]
        pol_by_lam = {r["lambda_val"]: r for r in pol_rows}
        for lam, ref_row in pol0_by_lam.items():
            comp_row = pol_by_lam.get(lam)
            if comp_row is None:
                count_mismatches.append({"pol": pol, "lam": lam, "issue": "missing"})
                continue
            for f in INT_ROW:
                v0 = ref_row.get(f); vp = comp_row.get(f)
                if v0 != vp:
                    count_mismatches.append({"pol": pol, "lam": lam, "field": f,
                                             "ref": v0, "got": vp})
            for f in FLOAT_ROW:
                v0 = ref_row.get(f); vp = comp_row.get(f)
                if v0 is None and vp is None:
                    continue
                if v0 is None or vp is None:
                    field_fp_pass[f] = False
                    float_mismatches.append({"pol": pol, "lam": lam, "field": f,
                                             "ref": v0, "got": vp, "reason": "one_is_none"})
                    continue
                try:
                    a, b = float(v0), float(vp)
                except (TypeError, ValueError) as _conv_err:
                    field_fp_pass[f] = False
                    float_mismatches.append({"pol": pol, "lam": lam, "field": f,
                                             "ref": v0, "got": vp,
                                             "reason": f"conversion_error: {_conv_err}"})
                    continue
                diff  = abs(a - b)
                scale = max(abs(a), abs(b), 1.0)
                tol   = max(8 * np.spacing(scale), 1e-12)
                field_max_diff[f] = max(field_max_diff[f], diff)
                field_max_tol[f]  = max(field_max_tol[f], tol)
                if not fp_equivalent(a, b):
                    field_fp_pass[f] = False
                    float_mismatches.append({"pol": pol, "lam": lam, "field": f,
                                             "ref": v0, "got": vp,
                                             "diff": diff, "tol": tol})

    counts_identical      = len(count_mismatches) == 0
    floats_fp_equivalent  = all(field_fp_pass.values())
    lambda_rows_equiv     = counts_identical and floats_fp_equivalent

    return {
        "lambda_rows_equivalent_within_fp_tolerance": lambda_rows_equiv,
        "count_fields_identical"                    : counts_identical,
        "float_fields_fp_equivalent"                : floats_fp_equivalent,
        "max_abs_diff_by_float_field"               : field_max_diff,
        "permitted_tol_by_float_field"              : field_max_tol,
        "float_diff_note"                           : (
            "S_primary_Cdoth ±1 ULP differences are expected: all policies select "
            "the same k-node SET at r=1 but in different orderings, so numpy's "
            "sequential sum produces different float rounding. Not a scientific "
            "deviation. Count fields (n_syn_admit, drops) are exactly identical. "
            "fp_equivalent(a,b): |a-b| <= max(8*spacing(max(|a|,|b|,1)), 1e-12)."
        ),
        "n_lambda_points"                           : len(pol0_lams),
        "count_mismatches"                          : count_mismatches[:10],
        "float_mismatches_beyond_fp_tolerance"      : float_mismatches[:10],
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    t_main = time.time()
    prov   = git_provenance()
    print("\nGate F Preflight Audit")
    print("=" * 70)
    print(f"git HEAD: {prov['git_commit_short']}  dirty={prov['git_dirty']}")
    print(f"date    : 2026-10-01")

    # ── Load reference JSONs ────────────────────────────────────────────────
    print("\nLoading reference files ...")
    refs = {}
    for fname in set(POLICY_REF_FILE.values()):
        refs[fname] = json.load(open(OUT_DIR / fname))
    gf_unr   = json.load(open(OUT_DIR / "gate_f_sc0-0_unr.json"))
    gf_r1    = json.load(open(OUT_DIR / "gate_f_sc0-0_1p0.json"))
    gf_unr_sc0  = gf_unr["scenario_results"][0]
    _unr_commit = gf_unr.get("git_commit_short", gf_unr.get("git_head", "unknown"))
    _unr_full   = gf_unr.get("git_commit_full",  "unknown")
    _unr_dirty  = gf_unr.get("git_dirty",        None)
    _r1_commit  = gf_r1.get("git_commit_short",  gf_r1.get("git_head",  "unknown"))
    _r1_full    = gf_r1.get("git_commit_full",   "unknown")
    _r1_dirty   = gf_r1.get("git_dirty",         None)
    print(f"  GF unrestricted: gate_f_sc0-0_unr.json "
          f"(commit={_unr_commit}  dirty={_unr_dirty})")
    print(f"  GF r=1:          gate_f_sc0-0_1p0.json "
          f"(commit={_r1_commit}  dirty={_r1_dirty})")

    # Derive lambda points from saved r=1 output (all points in the sweep)
    _r1_ref_rows = gf_r1["scenario_results"][0]["ratios"]["1.0"][GATE_F_POLICIES[0]]["lambda_rows"]
    R1_VERIFY_LAMBDAS = sorted([row["lambda_val"] for row in _r1_ref_rows])

    # ── Part 1: Unrestricted sc0 audit ─────────────────────────────────────
    unr_audit = run_unrestricted_audit(gf_unr_sc0, refs)
    print(f"\n  Unrestricted overall: {'PASS' if unr_audit['overall_pass'] else 'FAIL'}")

    # ── Part 1b: Lambda-row identity at r=1 (from saved file) ─────────────
    print("\nChecking r=1 lambda_rows identity (from saved output) ...")
    lr_check = r1_lambda_rows_identical(gf_r1)
    _lr_equiv = lr_check["lambda_rows_equivalent_within_fp_tolerance"]
    print(f"  lambda_rows_equivalent_within_fp_tolerance:  {_lr_equiv}  "
          f"({lr_check['n_lambda_points']} lambda points)")
    print(f"  count_fields_identical:     {lr_check['count_fields_identical']}")
    print(f"  float_fields_fp_equivalent: {lr_check['float_fields_fp_equivalent']}")
    max_diffs = lr_check["max_abs_diff_by_float_field"]
    max_tols  = lr_check["permitted_tol_by_float_field"]
    non_zero_floats = {f: d for f, d in max_diffs.items() if d > 0.0}
    if non_zero_floats:
        print(f"  float max_abs_diff (non-zero): {non_zero_floats}")
        print(f"  permitted_tol (corresponding):  "
              f"{ {f: max_tols[f] for f in non_zero_floats} }")
        print(f"  [{lr_check['float_diff_note']}]")
    else:
        print(f"  all float fields: max_abs_diff=0.0 (exact)")
    if lr_check["count_mismatches"]:
        print(f"  COUNT MISMATCHES (unexpected): {lr_check['count_mismatches']}")
    if lr_check["float_mismatches_beyond_fp_tolerance"]:
        print(f"  FLOAT MISMATCHES BEYOND TOLERANCE: "
              f"{lr_check['float_mismatches_beyond_fp_tolerance']}")

    # ── Part 1c: Pairwise verdict and delta-symmetry audit ─────────────────
    print("\nPairwise verdict and delta-symmetry audit (from saved r=1 output) ...")
    pw_audit = pairwise_r1_audit(gf_r1)
    print(f"  crossing_intervals_identical:            {pw_audit['crossing_intervals_identical']}")
    print(f"  pairwise_verdicts_all_indistinguishable: {pw_audit['pairwise_verdicts_all_indistinguishable']}")
    print(f"  delta_interval_symmetry_pass:            {pw_audit['delta_interval_symmetry_pass']}")
    for pair_key, v in pw_audit["pairwise_verdicts"].items():
        lo = v.get("delta_lo")
        hi = v.get("delta_hi")
        lo_str = f"{lo:.6f}" if lo is not None else "N/A"
        hi_str = f"{hi:.6f}" if hi is not None else "N/A"
        print(f"  {pair_key}: verdict={v['verdict']}  "
              f"delta_lo={lo_str}  delta_hi={hi_str}  "
              f"sym={v.get('delta_symmetry')}")

    # Save Part 1 artifact (no simulation needed)
    audit_unr = {
        "artifact_type"    : "gate_f_preflight_unrestricted_sc0",
        "created_date"     : "2026-10-01",
        "git_commit_short_preflight_run" : prov["git_commit_short"],
        "git_commit_full_preflight_run"  : prov["git_commit_full"],
        "git_dirty_preflight_run"        : prov["git_dirty"],
        "git_commit_short_unrestricted_run": _unr_commit,
        "git_commit_full_unrestricted_run" : _unr_full,
        "git_dirty_unrestricted_run"       : _unr_dirty,
        "git_commit_short_r1_run"          : _r1_commit,
        "git_commit_full_r1_run"           : _r1_full,
        "git_dirty_r1_run"                 : _r1_dirty,
        "source_files"     : {
            "gf_unrestricted" : "gate_f_sc0-0_unr.json",
            "gf_r1"           : "gate_f_sc0-0_1p0.json",
        },
        "unrestricted_sc0_audit" : unr_audit,
        "r1_sc0_lambda_row_check": lr_check,
        "r1_sc0_pairwise_audit"  : pw_audit,
    }
    out_unr = OUT_DIR / "gate_f_audit_unr_sc0.json"
    out_unr.write_text(json.dumps(audit_unr, indent=2))
    print(f"\nSaved: {out_unr}")

    # ── Part 2: Event-level r=1 verification (needs simulation data) ───────
    if not DATA_DIR.exists() or not (DATA_DIR / "frontier-completed-job-info.parquet").exists():
        print("\nWARNING: THERMALSHIFT_DATA_DIR not set or missing parquet.")
        print("Skipping event-level verification. Set env var and re-run.")
        sys.exit(0)

    sim = load_simulation_data()
    n_base = sim["n_base"]

    # Replicate M4 master_rng seed sequence
    LAMBDA_MAX_EXT = 4.0
    n_extra_max = int(np.ceil((LAMBDA_MAX_EXT - 1.0) * n_base))
    master_rng  = np.random.default_rng(SCENARIO_SEED)
    scen_seeds  = [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
    wl_seeds    = [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
    pol_seeds   = {p: [int(master_rng.integers(0, 2**31)) for _ in range(N_SCENARIOS)]
                   for p in POLICY_IDS}

    scen_seed   = scen_seeds[0]
    pol_seeds_0 = {pol: pol_seeds[pol][0] for pol in GATE_F_POLICIES}

    # Generate sc0 syn pool and job permutations
    def sample_synthetic_pool(n_extra, seed):
        rng_s = np.random.default_rng(seed)
        jobs_sorted = sim["jobs_sorted"]
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
        syn["job_idx"]        = -(np.arange(len(syn), dtype=np.int64) + 1)
        syn["alpha_j"]        = syn["parent_job_idx"].map(sim["alpha_map"])
        syn = syn.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)
        return syn

    def generate_job_perms(syn_pool, scen_rng):
        job_perms = {}
        job_residuals = sim["job_residuals"]
        jobs_sorted   = sim["jobs_sorted"]
        for jid in jobs_sorted["job_idx"].astype(int):
            res_s, bins = job_residuals[jid]
            k_j = len(res_s); perm = np.arange(k_j)
            for b in np.unique(bins):
                idx_b = np.where(bins == b)[0]
                perm[idx_b] = scen_rng.permutation(idx_b)
            job_perms[jid] = perm
        if len(syn_pool) > 0:
            for syn_jid, parent_jid in zip(syn_pool["job_idx"].astype(int),
                                            syn_pool["parent_job_idx"].astype(int)):
                res_s, bins = job_residuals[parent_jid]
                k_j = len(res_s); perm = np.arange(k_j)
                for b in np.unique(bins):
                    idx_b = np.where(bins == b)[0]
                    perm[idx_b] = scen_rng.permutation(idx_b)
                job_perms[syn_jid] = perm
        return job_perms

    print(f"\n[E] Generating sc0 synthetic pool and job permutations ...")
    syn_pool  = sample_synthetic_pool(n_extra_max, wl_seeds[0])
    scen_rng  = np.random.default_rng(scen_seed)
    job_perms = generate_job_perms(syn_pool, scen_rng)
    print(f"    pool size: {len(syn_pool):,}")

    print("\nPART 2 — r=1 event-level identity verification")
    print("=" * 70)
    print(f"Lambda points: {R1_VERIFY_LAMBDAS}")

    verify_results = []
    total_combined_events = 0
    total_events_checked  = 0
    total_stage1_drops    = 0
    total_stage1_agree    = 0
    total_sel_checked     = 0
    total_sel_identical   = 0
    total_la_checked      = 0
    total_la_identical    = 0
    total_state_checked   = 0
    total_state_identical = 0
    all_pass = True

    for lam in R1_VERIFY_LAMBDAS:
        n_syn_for_lam = int(round((lam - 1.0) * n_base))
        syn_sub = (syn_pool.iloc[:n_syn_for_lam].copy() if n_syn_for_lam > 0
                   else pd.DataFrame(columns=list(syn_pool.columns)))
        t0 = time.time()
        print(f"\n  lam={lam:.2f}  n_syn={n_syn_for_lam} ...", end=" ", flush=True)
        res = verify_r1_single_lambda(
            lam, syn_sub, scen_seed, pol_seeds_0, job_perms, sim)
        print(f"  ({time.time()-t0:.0f}s)")
        print(f"    n_events_checked={res['n_events_checked']}  "
              f"sel_identical={res['n_events_selected_sets_identical']}  "
              f"la_checked={res['n_lookahead_events_checked']}  "
              f"la_identical={res['n_lookahead_outcomes_identical']}  "
              f"state_checked={res['n_state_snapshots_checked']}  "
              f"state_identical={res['n_state_snapshots_identical']}")
        lam_pass = (res["sel_pass"] and res["la_pass"] and res["state_pass"]
                    and res["count_reconcile_pass"] and res["stage1_drop_agree_pass"])
        pass_str = "PASS" if lam_pass else "FAIL"
        print(f"    n_events_checked={res['n_events_checked']}  "
              f"sel_identical={res['n_events_selected_sets_identical']}  "
              f"la_checked={res['n_lookahead_events_checked']}  "
              f"la_identical={res['n_lookahead_outcomes_identical']}  "
              f"state_checked={res['n_state_snapshots_checked']}  "
              f"state_identical={res['n_state_snapshots_identical']}")
        print(f"    stage1_drops={res['n_stage1_drop_checked']}  "
              f"drops_agree={res['n_stage1_drop_agree']}  "
              f"count_reconcile={res['count_reconcile_pass']}")
        print(f"    sel_pass={res['sel_pass']}  la_pass={res['la_pass']}  "
              f"state_pass={res['state_pass']}  => {pass_str}")
        if res["first_sel_divergence"]:
            print(f"    FIRST SEL DIVERGENCE: {res['first_sel_divergence']}")
        if res["first_la_divergence"]:
            print(f"    FIRST LA DIVERGENCE: {res['first_la_divergence']}")
        if res["first_state_divergence"]:
            print(f"    FIRST STATE DIVERGENCE: {res['first_state_divergence']}")
        if res["first_drop_disagree"]:
            print(f"    FIRST DROP DISAGREE: {res['first_drop_disagree']}")

        verify_results.append(res)
        total_combined_events += res["n_combined_events"]
        total_events_checked  += res["n_events_checked"]
        total_stage1_drops    += res["n_stage1_drop_checked"]
        total_stage1_agree    += res["n_stage1_drop_agree"]
        total_sel_checked     += res["n_sel_events_checked"]
        total_sel_identical   += res["n_events_selected_sets_identical"]
        total_la_checked      += res["n_lookahead_events_checked"]
        total_la_identical    += res["n_lookahead_outcomes_identical"]
        total_state_checked   += res["n_state_snapshots_checked"]
        total_state_identical += res["n_state_snapshots_identical"]
        if not lam_pass:
            all_pass = False

    # Aggregate
    aggregate = {
        "n_lambda_points_verified"                   : len(R1_VERIFY_LAMBDAS),
        "lambda_points"                              : R1_VERIFY_LAMBDAS,
        "n_combined_events_total"                    : total_combined_events,
        "n_events_checked_total"                     : total_events_checked,
        "count_reconcile_pass"                       : (total_events_checked == total_combined_events),
        "n_stage1_drops_total"                       : total_stage1_drops,
        "n_stage1_drops_agree"                       : total_stage1_agree,
        "stage1_drop_agree_pass"                     : total_stage1_agree == total_stage1_drops,
        "n_events_checked"                           : total_sel_checked,
        "n_events_selected_sets_identical"           : total_sel_identical,
        "n_lookahead_events_checked"                 : total_la_checked,
        "n_lookahead_outcomes_identical"             : total_la_identical,
        "n_state_snapshots_checked"                  : total_state_checked,
        "n_state_snapshots_identical"                : total_state_identical,
        "lambda_rows_equivalent_within_fp_tolerance" : lr_check["lambda_rows_equivalent_within_fp_tolerance"],
        "count_fields_identical"                     : lr_check["count_fields_identical"],
        "float_fields_fp_equivalent"                 : lr_check["float_fields_fp_equivalent"],
        "float_max_abs_diff_by_field"                : lr_check["max_abs_diff_by_float_field"],
        "permitted_tol_by_float_field"               : lr_check["permitted_tol_by_float_field"],
        "float_diff_note"                            : lr_check["float_diff_note"],
        "crossing_intervals_identical"               : pw_audit["crossing_intervals_identical"],
        "pairwise_verdicts_all_indistinguishable"    : pw_audit["pairwise_verdicts_all_indistinguishable"],
        "delta_interval_symmetry_pass"               : pw_audit["delta_interval_symmetry_pass"],
        "event_level_all_pass"                       : all_pass,
        "per_lambda_results"                         : verify_results,
        "pairwise_verdicts"                          : pw_audit["pairwise_verdicts"],
        "crossing_intervals"                         : pw_audit["crossing_intervals"],
    }

    print(f"\n{'='*70}")
    print(f"AGGREGATE r=1 sc0 event-level results:")
    print(f"  n_combined_events_total:         {aggregate['n_combined_events_total']}")
    print(f"  n_events_checked_total:          {aggregate['n_events_checked_total']}"
          f"  (count_reconcile={aggregate['count_reconcile_pass']})")
    print(f"  n_stage1_drops_total:            {aggregate['n_stage1_drops_total']}"
          f"  agree={aggregate['n_stage1_drops_agree']}"
          f"  pass={aggregate['stage1_drop_agree_pass']}")
    print(f"  n_events_checked:                {aggregate['n_events_checked']}")
    print(f"  n_events_selected_sets_identical: {aggregate['n_events_selected_sets_identical']}")
    print(f"  n_lookahead_events_checked:       {aggregate['n_lookahead_events_checked']}")
    print(f"  n_lookahead_outcomes_identical:   {aggregate['n_lookahead_outcomes_identical']}")
    print(f"  n_state_snapshots_checked:        {aggregate['n_state_snapshots_checked']}")
    print(f"  n_state_snapshots_identical:      {aggregate['n_state_snapshots_identical']}")
    print(f"  lambda_rows_equivalent_within_fp_tolerance: "
          f"{aggregate['lambda_rows_equivalent_within_fp_tolerance']}  "
          f"(counts exact; S_primary_Cdoth ±1 ULP within fp_equivalent tolerance)")
    print(f"  crossing_intervals_identical:     {aggregate['crossing_intervals_identical']}")
    print(f"  pairwise_verdicts_indisting.:     {aggregate['pairwise_verdicts_all_indistinguishable']}")
    print(f"  delta_interval_symmetry_pass:     {aggregate['delta_interval_symmetry_pass']}")
    overall = (aggregate["event_level_all_pass"]
               and aggregate["count_reconcile_pass"]
               and aggregate["stage1_drop_agree_pass"]
               and aggregate["lambda_rows_equivalent_within_fp_tolerance"]
               and aggregate["crossing_intervals_identical"]
               and aggregate["pairwise_verdicts_all_indistinguishable"]
               and aggregate["delta_interval_symmetry_pass"]
               and unr_audit["overall_pass"])
    print(f"\n  GATE F PREFLIGHT OVERALL: {'PASS' if overall else 'FAIL'}")
    print(f"{'='*70}")

    # Save combined artifact
    audit_r1 = {
        "artifact_type"                      : "gate_f_preflight_r1_sc0",
        "created_date"                       : "2026-10-01",
        "git_commit_short_preflight_run"     : prov["git_commit_short"],
        "git_commit_full_preflight_run"      : prov["git_commit_full"],
        "git_dirty_preflight_run"            : prov["git_dirty"],
        "git_commit_short_unrestricted_run"  : _unr_commit,
        "git_commit_full_unrestricted_run"   : _unr_full,
        "git_dirty_unrestricted_run"         : _unr_dirty,
        "git_commit_short_r1_run"            : _r1_commit,
        "git_commit_full_r1_run"             : _r1_full,
        "git_dirty_r1_run"                   : _r1_dirty,
        "source_files": {
            "gf_unrestricted": "gate_f_sc0-0_unr.json",
            "gf_r1"          : "gate_f_sc0-0_1p0.json",
        },
        "unrestricted_sc0_overall_pass"  : unr_audit["overall_pass"],
        "r1_sc0_event_level"             : aggregate,
        "elapsed_total_s"                : round(time.time() - t_main, 1),
    }
    out_r1 = OUT_DIR / "gate_f_audit_r1_sc0.json"
    out_r1.write_text(json.dumps(audit_r1, indent=2))
    print(f"\nSaved: {out_r1}")
    print(f"Total elapsed: {time.time()-t_main:.0f}s")
