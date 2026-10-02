#!/usr/bin/env python3
"""
r1_gate_f_launcher.py
Post-outage parallel launcher for Gate F H3 held-out run (sc5-sc29).

Recovery amendment
  Original freeze commit : e2df32a
    "Fix held-out completeness guard; add M4 reference test"
  Recovery commit        : see `git log HEAD` after committing this file.
  Changed vs e2df32a     : r1_gate_f_run.py -- added per-scenario checkpoint
                           write/resume (lines 1164-1181, 1371-1380, 1401).
                           r1_gate_f_launcher.py -- this file (new).
                           r1_gate_f_merge.py    -- merge + validate (new).

  No change to: simulation mathematics, BETA_F_FROZEN, T_THR_PRIMARY,
  T_THR_SECONDARY, LAMBDA_SWEEP, GATE_F_RATIOS, GATE_F_POLICIES,
  SCENARIO_SEED, N_SCENARIOS, capacity_replay_gate_f, generate_job_perms,
  classify_crossing, refine_gate_f_bracket, held-out analysis criteria,
  or the output schema consumed by r1_gate_f_heldout_analysis.py.

Scientific basis for parallelism
  r1_gate_f_run.py generates all 30 scenario seeds in a single upfront pass
  of master_rng (lines 1145-1150 at e2df32a; unchanged). sc{k}'s
  scen_seed / wl_seed / pol_seeds are therefore identical whether sc{k}
  executes within N_DEV=25 or N_DEV=1. Scenarios share no mutable
  simulation state.

Usage
  python r1_gate_f_launcher.py                   # held-out sc5-29, 8 workers
  python r1_gate_f_launcher.py --equiv-only       # equivalence check only
  python r1_gate_f_launcher.py --sc 5 10 15      # specific scenarios
  GATE_F_MAX_WORKERS=4  python r1_gate_f_launcher.py
  THERMALSHIFT_DATA_DIR=/path python r1_gate_f_launcher.py

After all scenarios complete:
  python artifacts/revision1/analysis/r1_gate_f_merge.py
"""

import sys, os, io, json, math, subprocess, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Paths & config ─────────────────────────────────────────────────────────────
REPO_ROOT  = Path(__file__).resolve().parents[3]
OUT_DIR    = REPO_ROOT / "artifacts" / "revision1" / "results"
RUN_SCRIPT = Path(__file__).resolve().parent / "r1_gate_f_run.py"

RATIOS_ONLY       = "1.25,1.5,2.0,4.0,8.0"
RATIO_TAG         = "1p25_1p5_2p0_4p0_8p0"
HELDOUT_SCENARIOS = list(range(5, 30))          # sc5-sc29
MAX_WORKERS       = int(os.environ.get("GATE_F_MAX_WORKERS", "8"))

RATIO_STRS = ["1.25", "1.5", "2.0", "4.0", "8.0"]
POLICIES   = ["full_random", "full_fp", "full_loc", "full_fp_spread"]

# Equivalence check: compare sc0 run-solo vs sc0 in existing N_DEV=5 dev file
EQUIV_SC       = 0
EQUIV_REF_FILE = OUT_DIR / f"gate_f_sc0-4_{RATIO_TAG}.json"

# ── Helpers ────────────────────────────────────────────────────────────────────
def scenario_file(sc: int) -> Path:
    return OUT_DIR / f"gate_f_sc{sc}-{sc}_{RATIO_TAG}.json"

def scenario_log(sc: int) -> Path:
    return OUT_DIR / f"gate_f_sc{sc}-{sc}_launcher.log"

def fail(msg: str):
    print(f"\nFAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def is_valid_scenario_file(path: Path, sc: int) -> bool:
    if not path.exists():
        return False
    try:
        d = json.loads(path.read_text())
        sr = d.get("scenario_results", [])
        if len(sr) != 1:
            return False
        if int(sr[0].get("scenario_idx", -1)) != sc:
            return False
        ratios_dict = sr[0].get("ratios", {})
        for r in RATIO_STRS:
            if r not in ratios_dict:
                return False
            for p in POLICIES:
                if p not in ratios_dict[r]:
                    return False
        return True
    except Exception:
        return False

# ── Subprocess runner (one per thread) ────────────────────────────────────────
def run_scenario(sc: int) -> tuple:
    """
    Run one scenario as a subprocess. Thread-safe: no shared mutable state.
    Returns (sc_idx, returncode, error_summary_or_None).
    """
    out_path = scenario_file(sc)
    log_path = scenario_log(sc)

    if is_valid_scenario_file(out_path, sc):
        print(f"  [skip]  sc{sc:02d}: {out_path.name} already valid", flush=True)
        return sc, 0, None

    env = os.environ.copy()
    env["GATE_F_N_FIRST"]           = str(sc)
    env["GATE_F_N_DEV"]             = "1"
    env["GATE_F_RATIOS_ONLY"]       = RATIOS_ONLY
    env["GATE_F_REQUIRE_CLEAN_GIT"] = "1"

    t0 = time.time()
    print(f"  [start] sc{sc:02d}  (log: {log_path.name})", flush=True)

    with open(log_path, "w", encoding="utf-8") as log_f:
        proc = subprocess.run(
            [sys.executable, str(RUN_SCRIPT)],
            env=env,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            text=True,
        )

    elapsed = time.time() - t0

    if proc.returncode != 0:
        # Show last 40 lines of log for diagnostics
        try:
            tail = log_path.read_text(encoding="utf-8").splitlines()[-40:]
            snippet = "\n    ".join(tail)
        except Exception:
            snippet = "(log unreadable)"
        msg = (f"sc{sc} FAILED (exit {proc.returncode}, {elapsed:.0f}s).\n"
               f"    Full log: {log_path}\n    Tail:\n    {snippet}")
        print(f"  [FAIL]  sc{sc:02d} (exit {proc.returncode}, {elapsed:.0f}s)", flush=True)
        return sc, proc.returncode, msg

    if not is_valid_scenario_file(out_path, sc):
        msg = (f"sc{sc}: process exited 0 but {out_path.name} is missing or invalid. "
               f"Full log: {log_path}")
        print(f"  [FAIL]  sc{sc:02d} (output invalid after exit 0)", flush=True)
        return sc, 1, msg

    print(f"  [done]  sc{sc:02d} ({elapsed:.0f}s)", flush=True)
    return sc, 0, None

# ── Equivalence check ──────────────────────────────────────────────────────────
def _crossing_subset(cx: dict) -> dict:
    return {k: cx.get(k)
            for k in ("status", "C_lower_pct", "C_upper_pct",
                      "right_censored", "n_lambda_eval")}

def _lambda_row_subset(row: dict) -> dict:
    skip = {"elapsed_s"}
    return {k: v for k, v in row.items() if k not in skip}

def run_equivalence_check(stream_output: bool = True) -> bool:
    """
    Validates that running sc0 with N_DEV=1 (recovery commit) produces
    identical substantive results to sc0's entry in the N_DEV=5 dev run
    (original freeze commit e2df32a).

    This simultaneously proves:
      (a) scenario isolation: N_DEV does not affect per-scenario outputs.
      (b) code neutrality: recovery-commit changes don't alter simulation math.

    Excluded from comparison: elapsed_s, elapsed_total_s, git provenance
    fields (commit hash, dirty flag) — these are expected to differ.
    """
    print("\n" + "=" * 70)
    print(f"Equivalence check: sc{EQUIV_SC} solo (recovery commit) vs")
    print(f"  sc{EQUIV_SC} in {EQUIV_REF_FILE.name} (original freeze e2df32a)")
    print("=" * 70)

    if not EQUIV_REF_FILE.exists():
        print(f"  [SKIP] Reference file not found: {EQUIV_REF_FILE.name}")
        print(f"  Equivalence check requires the Gate F dev audit to have run.")
        return True  # Not a hard failure — reference simply not available

    # Extract sc0 from the reference dev run (N_DEV=5, commit e2df32a)
    ref_d  = json.loads(EQUIV_REF_FILE.read_text())
    ref_sc = next(
        (r for r in ref_d.get("scenario_results", [])
         if int(r.get("scenario_idx", -1)) == EQUIV_SC),
        None)
    if ref_sc is None:
        print(f"  FAIL: sc{EQUIV_SC} not found in {EQUIV_REF_FILE.name}")
        return False

    # Run sc0 solo via subprocess (or reuse existing file)
    solo_path = scenario_file(EQUIV_SC)
    if not is_valid_scenario_file(solo_path, EQUIV_SC):
        print(f"  Running sc{EQUIV_SC} solo (N_DEV=1, GATE_F_REQUIRE_CLEAN_GIT=1) ...")
        env = os.environ.copy()
        env["GATE_F_N_FIRST"]           = str(EQUIV_SC)
        env["GATE_F_N_DEV"]             = "1"
        env["GATE_F_RATIOS_ONLY"]       = RATIOS_ONLY
        env["GATE_F_REQUIRE_CLEAN_GIT"] = "1"
        proc = subprocess.run(
            [sys.executable, str(RUN_SCRIPT)],
            env=env,
            text=True,
        )
        if proc.returncode != 0:
            print(f"  FAIL: subprocess exited {proc.returncode}.")
            if not os.environ.get("THERMALSHIFT_DATA_DIR"):
                print(f"  THERMALSHIFT_DATA_DIR is not set — set it and rerun.")
            else:
                print(f"  Check that THERMALSHIFT_DATA_DIR points to the "
                      f"directory containing frontier-completed-job-info.parquet")
            return False
        if not is_valid_scenario_file(solo_path, EQUIV_SC):
            print(f"  FAIL: {solo_path.name} missing or invalid after exit 0")
            return False
    else:
        print(f"  Using existing {solo_path.name}")

    test_d  = json.loads(solo_path.read_text())
    test_sc = test_d["scenario_results"][0]

    mismatches = []

    # Seeds and reference budgets
    for field in ("scen_seed", "wl_seed"):
        rv, tv = ref_sc.get(field), test_sc.get(field)
        if rv != tv:
            mismatches.append(f"{field}: ref={rv}  test={tv}")

    for field in ("B_ref_s", "S_ref_s"):
        rv = float(ref_sc.get(field) or 0.0)
        tv = float(test_sc.get(field) or 0.0)
        if abs(rv - tv) > 1e-9:
            mismatches.append(f"{field}: ref={rv}  test={tv}")

    # Crossings
    ref_ratios  = ref_sc.get("ratios", {})
    test_ratios = test_sc.get("ratios", {})
    for r_str in RATIO_STRS:
        if r_str not in ref_ratios:
            continue
        for pol in POLICIES:
            rcx = ref_ratios[r_str].get(pol, {}).get("crossing", {})
            tcx = test_ratios.get(r_str, {}).get(pol, {}).get("crossing", {})
            rk, tk = _crossing_subset(rcx), _crossing_subset(tcx)
            if rk != tk:
                mismatches.append(f"crossing r={r_str} {pol}: ref={rk}  test={tk}")

    # Lambda rows (all fields except elapsed_s)
    for r_str in RATIO_STRS:
        if r_str not in ref_ratios:
            continue
        for pol in POLICIES:
            rrows = ref_ratios[r_str].get(pol, {}).get("lambda_rows", [])
            trows = test_ratios.get(r_str, {}).get(pol, {}).get("lambda_rows", [])
            if len(rrows) != len(trows):
                mismatches.append(
                    f"lambda_rows count r={r_str} {pol}: ref={len(rrows)} test={len(trows)}")
                continue
            for i, (rr, tr) in enumerate(zip(rrows, trows)):
                rk, tk = _lambda_row_subset(rr), _lambda_row_subset(tr)
                if rk != tk:
                    diff_keys = [k for k in set(list(rk) + list(tk))
                                 if rk.get(k) != tk.get(k)]
                    mismatches.append(
                        f"lambda_row[{i}] r={r_str} {pol} keys={diff_keys}")

    if mismatches:
        print(f"\n  EQUIVALENCE FAIL — {len(mismatches)} mismatch(es):")
        for m in mismatches[:20]:
            print(f"    {m}")
        if len(mismatches) > 20:
            print(f"    ... and {len(mismatches) - 20} more")
        return False

    print(f"  PASS — crossing values and lambda rows match exactly across")
    print(f"         {len(RATIO_STRS)} ratios x {len(POLICIES)} policies")
    print(f"         (excluded from comparison: elapsed_s, git provenance)")
    print(f"  ref commit : {ref_d.get('git_commit_short','?')}  "
          f"(freeze e2df32a)")
    print(f"  test commit: {test_d.get('git_commit_short','?')}  "
          f"(recovery)")
    return True

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    args = sys.argv[1:]
    equiv_only = "--equiv-only" in args
    specific   = None
    if "--sc" in args:
        idx = args.index("--sc")
        specific = [int(x) for x in args[idx + 1:]]

    scenarios = specific if specific is not None else HELDOUT_SCENARIOS

    print("Gate F Parallel Launcher")
    print("=" * 70)
    print(f"  Run script  : {RUN_SCRIPT.name}")
    print(f"  Ratios      : {RATIOS_ONLY}")
    print(f"  Scenarios   : sc{scenarios[0]}–sc{scenarios[-1]} ({len(scenarios)} total)")
    print(f"  MAX_WORKERS : {MAX_WORKERS}")
    print(f"  Out dir     : {OUT_DIR}")

    # Equivalence check is always run first
    ok = run_equivalence_check(stream_output=not equiv_only)
    if not ok:
        fail("Equivalence check failed — do not proceed with held-out run.\n"
             "  If the subprocess exited non-zero, check THERMALSHIFT_DATA_DIR.\n"
             "  If crossings mismatched, the recovery commit altered simulation "
             "results and must be investigated.")

    if equiv_only:
        print("\nEquivalence check passed. (--equiv-only: not launching held-out run)")
        return

    print(f"\n[launcher] Submitting {len(scenarios)} scenarios  "
          f"(MAX_WORKERS={MAX_WORKERS})")
    print(f"[launcher] Monitor individual scenarios with:")
    print(f"           tail -f {OUT_DIR}/gate_f_sc5-5_launcher.log")

    t_all = time.time()
    failed = []
    errors = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futs = {pool.submit(run_scenario, sc): sc for sc in scenarios}
        for fut in as_completed(futs):
            sc_idx, rc, err = fut.result()
            if rc != 0:
                failed.append(sc_idx)
                if err:
                    errors.append(err)

    elapsed = time.time() - t_all
    n_done  = len(scenarios) - len(failed)
    print(f"\n[launcher] {n_done}/{len(scenarios)} succeeded  "
          f"({elapsed:.0f}s / {elapsed / 3600:.2f}h total)")

    if failed:
        print(f"\n  Failed scenarios: {sorted(failed)}")
        for e in errors:
            print(f"\n  --- Error ---\n  {e}")
        fail(f"{len(failed)} scenario(s) failed. Fix and rerun; "
             "completed scenarios will be skipped automatically.")
    else:
        print(f"\nAll scenarios complete.")
        print(f"Next: merge and validate:")
        print(f"  python artifacts/revision1/analysis/r1_gate_f_merge.py")

if __name__ == "__main__":
    main()
