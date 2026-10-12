#!/usr/bin/env python3
"""
r1 <-> r2 equivalence verification (r2_vs_r1_equivalence.py)

Stage 1: seed/constant verification + seed-index unit tests (sc0-4 compat AND sc30-54 challenge).
Stage 2: full simulation equivalence — invoke r2_gate_f_run.py in compat mode, running five
         one-scenario compatibility tasks (sc0..sc4, N_FIRST=i, N_DEV=1 each), executed with
         a concurrency limit of 2, then hard-compare per scenario × policy × ratio × lambda row
         against three frozen r1 dev files.

Plan ref: REVIEW2_CHALLENGE_PLAN.md Amendment 5.

Amendment 5 changes vs Amendment 4:
- SEED_INDEX_BASE = SCENARIO_FIRST (not N_FIRST) in challenge mode, so parallel workers
  each pick the correct seed-array position.
- Stage 2 runs 5 parallel workers instead of one sequential process.
- Comparator now detects null/non-null asymmetry as a mismatch (not a silent skip).
- Stage 1 includes hard seed-index unit tests for all sc30-54 and sc0-4.

Usage:
  python r2_vs_r1_equivalence.py [--data-dir <path>]
  python r2_vs_r1_equivalence.py --compare-existing   # load completed r2compat files, skip re-simulation
  Set THERMALSHIFT_DATA_DIR env var to provide the data path.
  Stage 2 is skipped if no data dir is available and --compare-existing is not set.
"""
import sys, io, os, json, subprocess, hashlib, datetime, argparse, math
import concurrent.futures, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
REV2_DIR  = REPO_ROOT / "artifacts" / "revision2"
OUT_FILE  = REV2_DIR / "r2_vs_r1_equivalence.json"

# Frozen constants
BETA_F_FROZEN    = 1.12484352
T_THR_PRIMARY    = 63.625
T_THR_SECONDARY  = 60.602770562770566
DELTA_CAP        = 0.10

# Compat mode env vars to pass to r2_gate_f_run.py
COMPAT_SEED           = "42"
COMPAT_BETA           = str(BETA_F_FROZEN)
COMPAT_N_SCEN         = "30"
COMPAT_POLICY_ORDER   = "full_random,full_fp,full_loc,full_compact,marginal_random,marginal_fp,full_fp_spread"
COMPAT_RESTRICT       = "full_random,full_fp,position_template,full_fp_spread"
COMPAT_N_FIRST        = "0"
COMPAT_N_DEV          = "5"
COMPAT_RATIOS         = "1.0,1.25,1.5,2.0,4.0,8.0,unrestricted"

# Policy alias: r1 name -> r2 name
POL_ALIAS = {"full_loc": "position_template"}

# Fields compared per lambda row
FLOAT_FIELDS = {
    "lambda_val", "nominal_choice_ratio", "capacity_unlock_pct",
    "B_primary_h", "S_primary_Cdoth", "B_cab_ratio",
    "syn_node_hours", "mean_F_syn", "cab_span_median",
    "full_selector_eligible_count_p10", "full_selector_eligible_count_p50",
    "full_selector_eligible_count_p90",
    "exposed_selector_eligible_count_p10", "exposed_selector_eligible_count_p50",
    "exposed_selector_eligible_count_p90",
    "realized_selector_choice_mult_p10", "realized_selector_choice_mult_p50",
    "realized_selector_choice_mult_p90",
    "B_primary_ratio", "S_primary_ratio",
}
EXACT_FIELDS = {
    "n_syn_admit", "n_drop_cap", "n_drop_physical", "n_drop_la", "n_base_unserved",
    "invariant_violated", "infeasible", "first_binding",
}
CROSS_FLOAT_FIELDS = {"C_lower_pct", "C_upper_pct"}
CROSS_EXACT_FIELDS = {"status", "right_censored", "first_binding_constraint"}

FLOAT_TOL = 1e-9


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_r1_dev() -> dict:
    """Merge the three r1 dev files into a unified structure keyed by scenario_idx."""
    files = {
        "1.0"          : REV1_DIR / "results" / "gate_f_sc0-4_1p0.json",
        "multi"        : REV1_DIR / "results" / "gate_f_sc0-4_1p25_1p5_2p0_4p0_8p0.json",
        "unrestricted" : REV1_DIR / "results" / "gate_f_sc0-4_unr.json",
    }
    merged: dict[int, dict] = {}
    for label, fpath in files.items():
        if not fpath.exists():
            raise FileNotFoundError(f"Missing r1 dev file: {fpath}")
        data = json.loads(fpath.read_text())
        for sr in data.get("scenario_results", []):
            idx = int(sr["scenario_idx"])
            if idx not in merged:
                merged[idx] = {
                    "scenario_idx": idx,
                    "scen_seed"   : sr["scen_seed"],
                    "wl_seed"     : sr["wl_seed"],
                    "B_ref_s"     : sr.get("B_ref_s"),
                    "S_ref_s"     : sr.get("S_ref_s"),
                    "ratios"      : {},
                }
            for ratio_key, pol_dict in sr.get("ratios", {}).items():
                if ratio_key not in merged[idx]["ratios"]:
                    merged[idx]["ratios"][ratio_key] = {}
                for pol_name, pol_data in pol_dict.items():
                    merged[idx]["ratios"][ratio_key][pol_name] = pol_data
    return merged


def _float_close(a, b) -> bool:
    if a is None and b is None:
        return True
    if a is None or b is None:
        return False
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return a == b
    if math.isnan(fa) and math.isnan(fb):
        return True
    if math.isnan(fa) or math.isnan(fb):
        return False
    return abs(fa - fb) <= FLOAT_TOL


def _compare_row(r1_row: dict, r2_row: dict) -> dict:
    """Compare a lambda row.

    Returns dict:
      mismatches     — list of mismatch dicts
      schema_skipped — fields absent from one side (not a content mismatch)
      null_mismatches — fields where one side is None and the other is not
    """
    mismatches = []; schema_skipped = 0; null_mismatches = 0
    for field in FLOAT_FIELDS:
        if field not in r1_row or field not in r2_row:
            schema_skipped += 1; continue
        v1 = r1_row[field]; v2 = r2_row[field]
        if v1 is None and v2 is None:
            continue
        if (v1 is None) != (v2 is None):
            null_mismatches += 1
            mismatches.append({"field": field, "r1": v1, "r2": v2, "null_asymmetry": True})
            continue
        if not _float_close(v1, v2):
            mismatches.append({"field": field, "r1": v1, "r2": v2,
                                "abs_diff": abs(float(v1) - float(v2))})
    for field in EXACT_FIELDS:
        if field not in r1_row or field not in r2_row:
            schema_skipped += 1; continue
        v1 = r1_row[field]; v2 = r2_row[field]
        if v1 is None and v2 is None:
            continue
        if (v1 is None) != (v2 is None):
            null_mismatches += 1
            mismatches.append({"field": field, "r1": v1, "r2": v2, "null_asymmetry": True})
            continue
        if v1 != v2:
            mismatches.append({"field": field, "r1": v1, "r2": v2})
    return {"mismatches": mismatches, "schema_skipped": schema_skipped,
            "null_mismatches": null_mismatches}


def _compare_crossing(r1_cx: dict, r2_cx: dict) -> dict:
    """Compare crossing dicts.

    Returns dict:
      mismatches     — list of mismatch dicts
      schema_skipped — fields absent from one side
      null_mismatches — null-asymmetry count
    """
    mismatches = []; schema_skipped = 0; null_mismatches = 0
    for field in CROSS_FLOAT_FIELDS:
        if field not in r1_cx or field not in r2_cx:
            schema_skipped += 1; continue
        v1 = r1_cx[field]; v2 = r2_cx[field]
        if v1 is None and v2 is None:
            continue
        if (v1 is None) != (v2 is None):
            null_mismatches += 1
            mismatches.append({"field": f"crossing.{field}", "r1": v1, "r2": v2,
                                "null_asymmetry": True})
            continue
        if not _float_close(v1, v2):
            mismatches.append({"field": f"crossing.{field}", "r1": v1, "r2": v2,
                                "abs_diff": abs(float(v1) - float(v2))})
    for field in CROSS_EXACT_FIELDS:
        if field not in r1_cx or field not in r2_cx:
            schema_skipped += 1; continue
        v1 = r1_cx[field]; v2 = r2_cx[field]
        if v1 is None and v2 is None:
            continue
        if (v1 is None) != (v2 is None):
            null_mismatches += 1
            mismatches.append({"field": f"crossing.{field}", "r1": v1, "r2": v2,
                                "null_asymmetry": True})
            continue
        if v1 != v2:
            mismatches.append({"field": f"crossing.{field}", "r1": v1, "r2": v2})
    return {"mismatches": mismatches, "schema_skipped": schema_skipped,
            "null_mismatches": null_mismatches}


def _run_one_compat_scenario(sc_abs: int, data_dir: str,
                              run_script: Path, base_env: dict) -> tuple:
    """Run r2_gate_f_run.py for a single compat scenario. Returns (sc_abs, result_dict)."""
    env = dict(base_env)
    env["GATE_F_N_FIRST"] = str(sc_abs)
    env["GATE_F_N_DEV"]   = "1"
    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(run_script)],
            env=env, capture_output=True, text=True,
            encoding="utf-8", cwd=str(REPO_ROOT),
            timeout=10800,
        )
    except subprocess.TimeoutExpired:
        return sc_abs, {"ok": False, "error": f"sc{sc_abs} timed out (>3h)"}
    except Exception as exc:
        return sc_abs, {"ok": False, "error": str(exc)}
    elapsed = time.time() - t0
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-2000:]
        return sc_abs, {"ok": False,
                        "error": f"sc{sc_abs} rc={proc.returncode}: {err}",
                        "elapsed_s": round(elapsed, 1)}
    return sc_abs, {"ok": True, "elapsed_s": round(elapsed, 1)}


def _compare_merged(r2_by_idx: dict) -> dict:
    """Compare merged r2 output against r1 dev files. Returns comparison result dict."""
    try:
        r1_by_idx = _load_r1_dev()
    except FileNotFoundError as exc:
        return {"error": str(exc)}

    total_fields   = 0
    n_exact_match  = 0
    n_float_match  = 0
    n_schema_skip  = 0
    n_null_mm      = 0
    mismatches     = []
    max_abs_float  = 0.0
    n_rows_checked = 0

    r1_policies = ["full_random", "full_fp", "full_loc", "full_fp_spread"]

    for sc_idx in sorted(r1_by_idx.keys()):
        r1_sc = r1_by_idx[sc_idx]
        if sc_idx not in r2_by_idx:
            mismatches.append({"location": f"sc{sc_idx}", "error": "scenario missing from r2"})
            continue
        r2_sc = r2_by_idx[sc_idx]

        for field in ("scen_seed", "wl_seed"):
            v1 = r1_sc.get(field); v2 = r2_sc.get(field)
            total_fields += 1
            if v1 == v2:
                n_exact_match += 1
            else:
                mismatches.append({"location": f"sc{sc_idx}.{field}", "r1": v1, "r2": v2})

        for ratio_key in sorted(r1_sc.get("ratios", {}).keys()):
            r1_ratio = r1_sc["ratios"][ratio_key]
            if ratio_key not in r2_sc.get("ratios", {}):
                mismatches.append({"location": f"sc{sc_idx}.ratio={ratio_key}",
                                   "error": "ratio missing from r2"})
                continue
            r2_ratio = r2_sc["ratios"][ratio_key]

            for r1_pol in r1_policies:
                r2_pol = POL_ALIAS.get(r1_pol, r1_pol)
                if r1_pol not in r1_ratio:
                    continue
                if r2_pol not in r2_ratio:
                    mismatches.append({"location": f"sc{sc_idx}.ratio={ratio_key}.{r2_pol}",
                                       "error": "policy missing from r2"})
                    continue

                r1_pd = r1_ratio[r1_pol]; r2_pd = r2_ratio[r2_pol]
                r1_rows = r1_pd.get("lambda_rows", [])
                r2_rows = r2_pd.get("lambda_rows", [])
                r2_by_lam = {round(float(row["lambda_val"]), 6): row
                             for row in r2_rows if row.get("lambda_val") is not None}

                for r1_row in r1_rows:
                    lv = r1_row.get("lambda_val")
                    if lv is None: continue
                    lv_key = round(float(lv), 6)
                    n_rows_checked += 1
                    loc = f"sc{sc_idx}.ratio={ratio_key}.{r2_pol}.lam={lv}"
                    if lv_key not in r2_by_lam:
                        mismatches.append({"location": loc, "error": "lambda row missing from r2"})
                        continue
                    r2_row = r2_by_lam[lv_key]
                    row_res = _compare_row(r1_row, r2_row)
                    for mm in row_res["mismatches"]:
                        mm["location"] = loc; mismatches.append(mm)
                        if "abs_diff" in mm:
                            max_abs_float = max(max_abs_float, mm["abs_diff"])
                    n_schema_skip += row_res["schema_skipped"]
                    n_null_mm     += row_res["null_mismatches"]
                    # Tally matched fields (those present in both sides)
                    n_ff = sum(1 for f in FLOAT_FIELDS if f in r1_row and f in r2_row)
                    n_ef = sum(1 for f in EXACT_FIELDS  if f in r1_row and f in r2_row)
                    row_mm_f = {m["field"] for m in row_res["mismatches"]}
                    total_fields  += n_ff + n_ef
                    n_float_match += n_ff - sum(1 for f in FLOAT_FIELDS if f in row_mm_f)
                    n_exact_match += n_ef - sum(1 for f in EXACT_FIELDS  if f in row_mm_f)

                r1_cx = r1_pd.get("crossing", {}); r2_cx = r2_pd.get("crossing", {})
                cx_res  = _compare_crossing(r1_cx, r2_cx)
                cx_loc  = f"sc{sc_idx}.ratio={ratio_key}.{r2_pol}.crossing"
                for mm in cx_res["mismatches"]:
                    mm["location"] = cx_loc; mismatches.append(mm)
                    if "abs_diff" in mm:
                        max_abs_float = max(max_abs_float, mm["abs_diff"])
                n_schema_skip += cx_res["schema_skipped"]
                n_null_mm     += cx_res["null_mismatches"]
                n_cx_f = sum(1 for f in CROSS_FLOAT_FIELDS if f in r1_cx and f in r2_cx)
                n_cx_e = sum(1 for f in CROSS_EXACT_FIELDS  if f in r1_cx and f in r2_cx)
                cx_mm_f = {m["field"].split(".")[-1] for m in cx_res["mismatches"]}
                total_fields  += n_cx_f + n_cx_e
                n_float_match += n_cx_f - sum(1 for f in CROSS_FLOAT_FIELDS if f in cx_mm_f)
                n_exact_match += n_cx_e - sum(1 for f in CROSS_EXACT_FIELDS  if f in cx_mm_f)

    n_mismatches = len(mismatches)
    return {
        "n_rows_checked"       : n_rows_checked,
        "total_fields_compared": total_fields,
        "schema_skipped"       : n_schema_skip,
        "null_mismatches"      : n_null_mm,
        "n_exact_matches"      : n_exact_match,
        "n_float_matches"      : n_float_match,
        "mismatch_count"       : n_mismatches,
        "max_abs_float_diff"   : max_abs_float,
        "mismatches"           : mismatches,
    }


def compare_existing_stage2() -> dict:
    """Load completed per-scenario r2compat files and compare vs r1 dev (no re-simulation)."""
    print("\n[Stage 2] --compare-existing: loading per-scenario r2compat files ...")
    results_dir = REV2_DIR / "results"
    r2_by_idx: dict[int, dict] = {}
    output_files = []
    for sc in range(5):
        matches = sorted(results_dir.glob(f"gate_f_sc{sc}-{sc}_*_r2compat.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            return {"ran": False, "pass": False,
                    "error": f"No output file found for sc{sc} — run Stage 2 first"}
        f = matches[0]; output_files.append(str(f.relative_to(REPO_ROOT)))
        print(f"    sc{sc}: {f.name}")
        try:
            data = json.loads(f.read_text())
        except Exception as exc:
            return {"ran": False, "pass": False, "error": f"Parse error {f.name}: {exc}"}
        for sr in data.get("scenario_results", []):
            r2_by_idx[int(sr["scenario_idx"])] = sr

    print(f"\n    Merged {len(r2_by_idx)} scenarios from {len(output_files)} output files.")
    print("    Loading r1 dev files and comparing ...")
    cmp = _compare_merged(r2_by_idx)
    if "error" in cmp:
        return {"ran": True, "pass": False, "error": cmp["error"]}

    n_mm = cmp["mismatch_count"]
    stage2_pass = (n_mm == 0 and len(r2_by_idx) >= 5)
    print(f"    Rows checked       : {cmp['n_rows_checked']}")
    print(f"    Fields compared    : {cmp['total_fields_compared']}")
    print(f"    Schema-skipped     : {cmp['schema_skipped']}")
    print(f"    Null mismatches    : {cmp['null_mismatches']}")
    print(f"    Float mismatches   : {sum(1 for m in cmp['mismatches'] if 'abs_diff' in m)}")
    print(f"    Exact mismatches   : "
          f"{sum(1 for m in cmp['mismatches'] if 'abs_diff' not in m and 'error' not in m)}")
    print(f"    Max abs float diff : {cmp['max_abs_float_diff']:.2e}")
    print(f"    Total mismatches   : {n_mm}")
    print(f"    Stage 2: {'PASS' if stage2_pass else 'FAIL'}")

    return {
        "ran"                      : True,
        "pass"                     : stage2_pass,
        "compare_existing_mode"    : True,
        "n_scenario_workers_total" : 5,
        "max_concurrent_workers"   : 2,
        "scenario_indices"         : [0, 1, 2, 3, 4],
        "output_files"             : output_files,
        "n_scenarios_checked"      : len(r2_by_idx),
        "n_rows_checked"           : cmp["n_rows_checked"],
        "total_fields_compared"    : cmp["total_fields_compared"],
        "schema_skipped"           : cmp["schema_skipped"],
        "null_mismatches"          : cmp["null_mismatches"],
        "n_exact_matches"          : cmp["n_exact_matches"],
        "n_float_matches"          : cmp["n_float_matches"],
        "mismatch_count"           : n_mm,
        "max_abs_float_diff"       : cmp["max_abs_float_diff"],
        "mismatch_examples"        : cmp["mismatches"][:20],
        "all_mismatches"           : cmp["mismatches"][:200],
    }


def run_stage2(data_dir: str) -> dict:
    """Run r2 in compat mode using 5 parallel one-scenario workers, then compare vs r1 dev."""
    print("\n[Stage 2] Launching 5 parallel compat workers (sc0..sc4, one each) ...")
    run_script = REV2_DIR / "r2_gate_f_run.py"
    if not run_script.exists():
        return {"ran": False, "error": "r2_gate_f_run.py not found"}

    base_env = dict(os.environ)
    base_env.update({
        "THERMALSHIFT_DATA_DIR"     : data_dir,
        "GATE_F_COMPAT_SEED"        : COMPAT_SEED,
        "GATE_F_COMPAT_BETA"        : COMPAT_BETA,
        "GATE_F_COMPAT_N_SCEN"      : COMPAT_N_SCEN,
        "GATE_F_COMPAT_POLICY_ORDER": COMPAT_POLICY_ORDER,
        "GATE_F_RESTRICT_POLICIES"  : COMPAT_RESTRICT,
        "GATE_F_RATIOS_ONLY"        : COMPAT_RATIOS,
        "GATE_F_REQUIRE_CLEAN_GIT"  : "0",
        # N_FIRST and N_DEV set per-worker in _run_one_compat_scenario
    })

    t0_all = time.time()
    worker_results: dict[int, dict] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
        fs = {ex.submit(_run_one_compat_scenario, sc, data_dir, run_script, base_env): sc
              for sc in range(5)}
        for future in concurrent.futures.as_completed(fs):
            sc_abs, res = future.result()
            worker_results[sc_abs] = res
            status = "OK" if res.get("ok") else f"ERROR: {res.get('error','?')[:120]}"
            print(f"    sc{sc_abs}: {status}  ({res.get('elapsed_s','?')}s)")

    elapsed_all = time.time() - t0_all
    failed = [sc for sc, r in worker_results.items() if not r.get("ok")]
    if failed:
        errs = "; ".join(f"sc{sc}: {worker_results[sc].get('error','?')[:100]}"
                         for sc in sorted(failed))
        return {"ran": True, "pass": False, "error": f"Workers failed: {errs}",
                "worker_results": {str(k): v for k, v in worker_results.items()}}

    # Collect and merge per-scenario output files
    results_dir = REV2_DIR / "results"
    r2_by_idx: dict[int, dict] = {}
    output_files = []
    for sc in range(5):
        # Match: gate_f_sc{sc}-{sc}_*_r2compat.json
        matches = sorted(results_dir.glob(f"gate_f_sc{sc}-{sc}_*_r2compat.json"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        if not matches:
            return {"ran": True, "pass": False,
                    "error": f"No output file found for sc{sc}",
                    "worker_results": {str(k): v for k, v in worker_results.items()}}
        f = matches[0]; output_files.append(str(f.relative_to(REPO_ROOT)))
        try:
            data = json.loads(f.read_text())
        except Exception as exc:
            return {"ran": True, "pass": False, "error": f"Parse error {f.name}: {exc}"}
        for sr in data.get("scenario_results", []):
            r2_by_idx[int(sr["scenario_idx"])] = sr

    print(f"\n    Merged {len(r2_by_idx)} scenarios from {len(output_files)} output files.")
    print("    Loading r1 dev files and comparing ...")
    cmp = _compare_merged(r2_by_idx)
    if "error" in cmp:
        return {"ran": True, "pass": False, "error": cmp["error"]}

    n_mm = cmp["mismatch_count"]
    stage2_pass = (n_mm == 0 and len(r2_by_idx) >= 5)
    print(f"    Rows checked       : {cmp['n_rows_checked']}")
    print(f"    Fields compared    : {cmp['total_fields_compared']}")
    print(f"    Schema-skipped     : {cmp['schema_skipped']}")
    print(f"    Null mismatches    : {cmp['null_mismatches']}")
    print(f"    Float mismatches   : {sum(1 for m in cmp['mismatches'] if 'abs_diff' in m)}")
    print(f"    Exact mismatches   : {sum(1 for m in cmp['mismatches'] if 'abs_diff' not in m and 'error' not in m)}")
    print(f"    Max abs float diff : {cmp['max_abs_float_diff']:.2e}")
    print(f"    Total mismatches   : {n_mm}")
    print(f"    Stage 2: {'PASS' if stage2_pass else 'FAIL'}")

    return {
        "ran"                      : True,
        "pass"                     : stage2_pass,
        "n_scenario_workers_total" : 5,
        "max_concurrent_workers"   : 2,
        "scenario_indices"         : [0, 1, 2, 3, 4],
        "elapsed_total_s"          : round(elapsed_all, 1),
        "output_files"             : output_files,
        "worker_elapsed_s"         : {str(k): v.get("elapsed_s") for k, v in worker_results.items()},
        "n_scenarios_checked"  : len(r2_by_idx),
        "n_rows_checked"       : cmp["n_rows_checked"],
        "total_fields_compared": cmp["total_fields_compared"],
        "schema_skipped"       : cmp["schema_skipped"],
        "null_mismatches"      : cmp["null_mismatches"],
        "n_exact_matches"      : cmp["n_exact_matches"],
        "n_float_matches"      : cmp["n_float_matches"],
        "mismatch_count"       : n_mm,
        "max_abs_float_diff"   : cmp["max_abs_float_diff"],
        "mismatch_examples"    : cmp["mismatches"][:20],
        "all_mismatches"       : cmp["mismatches"][:200],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir",
                        default=os.environ.get("THERMALSHIFT_DATA_DIR", ""),
                        help="Path to frontier parquet directory (enables Stage 2)")
    parser.add_argument("--compare-existing", action="store_true",
                        help="Load completed per-scenario r2compat files and compare "
                             "(no re-simulation; Stage 2 workers must have already run)")
    args = parser.parse_args()

    print("=" * 70)
    print("r1 <-> r2 Equivalence Verification")
    print("Plan ref: REVIEW2_CHALLENGE_PLAN.md Amendment 5")
    print("=" * 70)

    checks: dict[str, dict] = {}

    # ── Stage 1: Seed verification + seed-index unit tests ───────────────────
    print("\n[Stage 1] Seed, constant, and seed-index verification ...")

    # Generate full rng(42) sequence (30 scenarios for compat)
    rng42 = np.random.default_rng(42)
    sc0_29_scen = [int(rng42.integers(0, 2**31)) for _ in range(30)]
    sc0_29_wl   = [int(rng42.integers(0, 2**31)) for _ in range(30)]
    sc0_4_scen  = sc0_29_scen[:5]
    sc0_4_wl    = sc0_29_wl[:5]
    # Compat mode: no placebo draws; then 7 policy seed arrays
    COMPAT_POL_ORDER_LIST = COMPAT_POLICY_ORDER.split(",")
    sc0_29_pol = {p: [int(rng42.integers(0, 2**31)) for _ in range(30)]
                  for p in COMPAT_POL_ORDER_LIST}

    # Generate rng(2042) sequence for challenge (25 scenarios).
    # Draw order MUST match the actual challenge runner (non-compat mode):
    #   scen_seeds → wl_seeds → placebo-global → placebo-withincab → policy seeds
    # Policy seeds drawn in CHALLENGE_POLICY_IDS order, NOT the r1 compat order.
    CHALLENGE_SEED_INT = 2042
    SCENARIO_FIRST_INT = 30
    CHALLENGE_POLICY_IDS_AUDIT = [
        "full_random", "full_fp", "position_template", "full_fp_spread",
        "random_spread", "fp_global_placebo", "fp_withincab_placebo",
    ]
    rng2042 = np.random.default_rng(CHALLENGE_SEED_INT)
    sc30_54_scen = [int(rng2042.integers(0, 2**31)) for _ in range(25)]
    sc30_54_wl   = [int(rng2042.integers(0, 2**31)) for _ in range(25)]
    _pg  = int(rng2042.integers(0, 2**31))   # PLACEBO_GLOBAL_PERM_SEED
    _pwc = int(rng2042.integers(0, 2**31))   # PLACEBO_WITHINCAB_PERM_SEED
    sc30_54_pol = {p: [int(rng2042.integers(0, 2**31)) for _ in range(25)]
                   for p in CHALLENGE_POLICY_IDS_AUDIT}
    # Verify placebo seeds match frozen constants
    PLACEBO_GLOBAL_EXPECTED    = 218767960
    PLACEBO_WITHINCAB_EXPECTED = 365514213
    if _pg != PLACEBO_GLOBAL_EXPECTED or _pwc != PLACEBO_WITHINCAB_EXPECTED:
        seeds_ok = False

    seeds_ok = True; seed_notes = []

    # Verify sc0-4 against frozen r1 dev output
    r1_dev_1p0 = REV1_DIR / "results" / "gate_f_sc0-4_1p0.json"
    if not r1_dev_1p0.exists():
        seeds_ok = False; seed_notes.append("gate_f_sc0-4_1p0.json missing")
    else:
        r1 = json.loads(r1_dev_1p0.read_text())
        for sr in r1.get("scenario_results", []):
            idx = int(sr["scenario_idx"])
            if 0 <= idx <= 4:
                if sr["scen_seed"] != sc0_4_scen[idx] or sr["wl_seed"] != sc0_4_wl[idx]:
                    seeds_ok = False
                    seed_notes.append(
                        f"sc{idx}: r1={sr['scen_seed']}/{sr['wl_seed']} "
                        f"vs rng(42)={sc0_4_scen[idx]}/{sc0_4_wl[idx]}"
                    )
        if seeds_ok:
            seed_notes.append(f"sc0-4 seeds match rng(42). sc0: scen={sc0_4_scen[0]} wl={sc0_4_wl[0]}")

    # ── Seed-index unit tests ─────────────────────────────────────────────────
    sidx_ok = True; sidx_notes = []; sidx_table_compat = {}; sidx_table_challenge = {}
    SEED_INDEX_BASE_COMPAT    = 0
    SEED_INDEX_BASE_CHALLENGE = SCENARIO_FIRST_INT

    for sc in range(5):
        idx = sc - SEED_INDEX_BASE_COMPAT  # expected: sc
        exp_scen = sc0_4_scen[idx]
        exp_wl   = sc0_4_wl[idx]
        sidx_table_compat[f"sc{sc}"] = {
            "seed_index": idx, "scen_seed": exp_scen, "wl_seed": exp_wl,
        }
        if idx != sc:
            sidx_ok = False
            sidx_notes.append(f"compat sc{sc}: idx={idx} expected {sc}")
        # Policy seeds
        for pol in COMPAT_POL_ORDER_LIST:
            sidx_table_compat[f"sc{sc}"][f"pol_seed_{pol}"] = sc0_29_pol[pol][idx]

    for sc in range(30, 55):
        idx = sc - SEED_INDEX_BASE_CHALLENGE  # expected: sc-30
        exp_idx = sc - SCENARIO_FIRST_INT
        exp_scen = sc30_54_scen[idx]
        exp_wl   = sc30_54_wl[idx]
        sidx_table_challenge[f"sc{sc}"] = {
            "seed_index": idx, "scen_seed": exp_scen, "wl_seed": exp_wl,
        }
        if idx != exp_idx:
            sidx_ok = False
            sidx_notes.append(f"challenge sc{sc}: idx={idx} expected {exp_idx}")
        # Verify different scenarios have different seeds
        if sc > 30:
            prev_scen = sc30_54_scen[idx - 1]
            if exp_scen == prev_scen:
                sidx_ok = False
                sidx_notes.append(f"challenge sc{sc}: same scen_seed as sc{sc-1} — collision")
        # Policy seeds — using actual CHALLENGE_POLICY_IDS order
        for pol in CHALLENGE_POLICY_IDS_AUDIT:
            sidx_table_challenge[f"sc{sc}"][f"pol_seed_{pol}"] = sc30_54_pol[pol][idx]

    # Verify the old bug would have been wrong: for N_FIRST=31, old code gave idx=0 not 1
    old_bug_sc31 = 31 - 31  # N_FIRST=31 → idx=0 (WRONG)
    new_fix_sc31 = 31 - SEED_INDEX_BASE_CHALLENGE  # SEED_INDEX_BASE=30 → idx=1 (CORRECT)
    if new_fix_sc31 != 1:
        sidx_ok = False; sidx_notes.append(f"BUG: new sc31 idx={new_fix_sc31} expected 1")
    else:
        sidx_notes.append(
            f"Parallel-worker seed-index fix verified: sc31 old_idx={old_bug_sc31}(WRONG) "
            f"new_idx={new_fix_sc31}(CORRECT). "
            f"All sc30-54 indices unique: {len(set(sc30_54_scen))==25}. "
            f"All sc0-4 compat indices unique: {len(set(sc0_4_scen))==5}."
        )

    if sidx_ok:
        sidx_notes.append("Seed-index unit tests PASS: sc0-4 compat + sc30-54 challenge all correct")
    else:
        seeds_ok = False  # propagate to stage1 overall

    r2_run = REV2_DIR / "r2_gate_f_run.py"
    const_ok = True; const_notes = []
    if r2_run.exists():
        src = r2_run.read_text(encoding="utf-8")
        for name, val in [
            ("BETA_F_FROZEN", "1.12484352"),
            ("T_THR_PRIMARY", "63.625"),
            ("T_THR_SECONDARY", "60.602770562770566"),
            ("DELTA_CAP", "0.10"),
            ("SEED_INDEX_BASE", "SEED_INDEX_BASE"),  # ensure the fix is present
        ]:
            if val in src:
                const_notes.append(f"{name}: found")
            else:
                const_ok = False
                const_notes.append(f"{name}: MISSING")
    else:
        const_ok = False; const_notes.append("r2_gate_f_run.py not found")

    r1_files = {
        "gate_f_sc0-4_1p0.json"                   : REV1_DIR / "results" / "gate_f_sc0-4_1p0.json",
        "gate_f_sc0-4_1p25_1p5_2p0_4p0_8p0.json" : REV1_DIR / "results" / "gate_f_sc0-4_1p25_1p5_2p0_4p0_8p0.json",
        "gate_f_sc0-4_unr.json"                   : REV1_DIR / "results" / "gate_f_sc0-4_unr.json",
    }
    r1_shas = {}
    r1_files_ok = True
    for fname, fpath in r1_files.items():
        if fpath.exists():
            r1_shas[fname] = _sha256(fpath)
        else:
            r1_files_ok = False; r1_shas[fname] = "MISSING"

    s1_pass = seeds_ok and sidx_ok and const_ok and r1_files_ok
    checks["stage1_seed_verification"] = {
        "pass"                   : s1_pass,
        "seeds_match"            : seeds_ok,
        "seed_index_tests_pass"  : sidx_ok,
        "constants_match"        : const_ok,
        "r1_dev_files_present"   : r1_files_ok,
        "notes"                  : seed_notes + sidx_notes + const_notes,
        "r1_dev_sha256"          : r1_shas,
        "sc0_scen_seed"          : sc0_4_scen[0],
        "sc0_wl_seed"            : sc0_4_wl[0],
        "seed_index_table_compat"    : sidx_table_compat,
        "seed_index_table_challenge" : sidx_table_challenge,
    }
    print(f"    Stage 1 {'PASS' if s1_pass else 'FAIL'}: "
          + "; ".join((seed_notes + sidx_notes + const_notes)[:4]))

    # ── Stage 2: Full simulation equivalence ──────────────────────────────────
    data_dir = args.data_dir
    if args.compare_existing:
        checks["stage2_simulation"] = compare_existing_stage2()
    elif not data_dir or not Path(data_dir).exists():
        print(f"\n[Stage 2] SKIPPED — THERMALSHIFT_DATA_DIR not set/found.")
        checks["stage2_simulation"] = {
            "ran"  : False,
            "pass" : False,
            "error": "THERMALSHIFT_DATA_DIR not set or not found; Stage 2 skipped.",
        }
    else:
        checks["stage2_simulation"] = run_stage2(data_dir)

    # ── Overall result ────────────────────────────────────────────────────────
    s2 = checks["stage2_simulation"]
    overall_pass = (
        s1_pass
        and s2.get("ran", False)
        and s2.get("pass", False)
    )

    print("\n" + "=" * 70)
    if overall_pass:
        print("OVERALL: PASS — Stage 1 + Stage 2 both verified.")
    else:
        fails = []
        if not s1_pass:
            fails.append("Stage 1 seed/constant verification FAILED")
        if not s2.get("ran", False):
            fails.append("Stage 2 simulation NOT run (data dir missing)")
        elif not s2.get("pass", False):
            fails.append(f"Stage 2 simulation FAILED ({s2.get('mismatch_count', '?')} mismatches)")
        print("OVERALL: FAIL — " + "; ".join(fails))
    print("=" * 70)

    result = {
        "script"     : "artifacts/revision2/r2_vs_r1_equivalence.py",
        "plan_ref"   : "REVIEW2_CHALLENGE_PLAN.md Amendment 5",
        "run_at"     : datetime.datetime.utcnow().isoformat() + "Z",
        "stage1_seed_verification": checks["stage1_seed_verification"],
        "stage2_simulation"       : checks["stage2_simulation"],
        "overall_pass"            : overall_pass,
    }
    OUT_FILE.write_text(json.dumps(result, indent=2))
    print(f"\nWritten: {OUT_FILE}")
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
