#!/usr/bin/env python3
"""
Challenge run orchestrator v2 (final): sc33-54, 4 concurrent workers.
Operational only — scientific behavior IDENTICAL to r2_challenge_orchestrator.py
(original SHA256: c45e97aa67607200b4b1349f538e07b77a370a36302a8cbd277cf9d672f586d3).

Provenance context:
  sc30, sc31, sc32 completed under original 2-worker orchestrator.
  sc33, sc34 were killed (no final output) by Windows process-tree termination
    during an attempted orchestrator handoff — see OPERATIONAL_INCIDENT_sc33_sc34_aborted.json.
  sc35–sc54 were never started.
  This launcher's permitted queue is EXACTLY sc33–sc54 (FIRST_SCENARIO=33).
  It cannot submit sc30–sc32 under any circumstance.

Superseded draft: r2_challenge_orchestrator_4w.py SHA e5d5f5c7...89bd was
  written but never executed to produce a challenge result.

Differences from original 2-worker launcher (operational only):
  1. FIRST_SCENARIO = 33, LAST_SCENARIO = 54  — hard queue bound, never sc30-sc32
  2. MAX_WORKERS = 4  (was 2)
  3. Skips scenarios where gate_f_scN-N_all_r2challenge.json already exists
     and is non-empty at startup.
  4. Safety re-check inside _launch_one: if output appears between startup
     scan and actual subprocess launch, logs SKIP and returns ok=True.
  5. Records original orchestrator SHA256 and incident reference in run log.
  6. Uses datetime.timezone.utc (avoids DeprecationWarning).

Does NOT change:
  - r2_gate_f_run.py (frozen at 5733b73)
  - Seeds, policies, thresholds, ratios, beta, lambda grid, analysis logic
  - GATE_F_N_DEV, GATE_F_N_FIRST, GATE_F_REQUIRE_CLEAN_GIT, THERMALSHIFT_DATA_DIR
  - Compat/override env vars (still explicitly popped)
  - Seed assertion logic (identical to original)

Windows handoff lesson: never attempt orchestrator replacement while worker
  subprocesses are active. Only hand off at a clean point with no active workers.
"""
import sys, io, os, json, subprocess, time, datetime
import concurrent.futures
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parents[2]
REV2_DIR    = REPO_ROOT / "artifacts" / "revision2"
RESULTS_DIR = REV2_DIR / "results"
AUDIT_FILE  = REV2_DIR / "challenge_seed_index_audit.json"
RUN_SCRIPT  = REV2_DIR / "r2_gate_f_run.py"
DATA_DIR    = "C:/Users/kalya/Downloads"
FREEZE_SHA  = "5733b73"
MAX_WORKERS = 4
TIMEOUT_S   = 21600   # 6 hours per worker

FIRST_SCENARIO = 33   # hard lower bound — sc30–sc32 completed under original launcher
LAST_SCENARIO  = 54   # inclusive

ORIGINAL_ORCHESTRATOR_SHA256 = (
    "c45e97aa67607200b4b1349f538e07b77a370a36302a8cbd277cf9d672f586d3"
)
INCIDENT_RECORD = "OPERATIONAL_INCIDENT_sc33_sc34_aborted.json"

CHALLENGE_POLICY_IDS = [
    "full_random", "full_fp", "position_template", "full_fp_spread",
    "random_spread", "fp_global_placebo", "fp_withincab_placebo",
]


def _assert_seeds(sc: int, tbl: dict, rng_scen: list, rng_wl: list, rng_pol: dict):
    idx = sc - 30
    row = tbl[f"sc{sc}"]
    fails = []
    if rng_scen[idx] != row["scen_seed"]:
        fails.append(f"scen_seed derived={rng_scen[idx]} audit={row['scen_seed']}")
    if rng_wl[idx] != row["wl_seed"]:
        fails.append(f"wl_seed derived={rng_wl[idx]} audit={row['wl_seed']}")
    for p in CHALLENGE_POLICY_IDS:
        d = rng_pol[p][idx]; a = row[f"pol_seed_{p}"]
        if d != a:
            fails.append(f"pol_seed_{p} derived={d} audit={a}")
    if fails:
        raise AssertionError(f"sc{sc} seed assertion FAILURES: {fails}")


def _launch_one(sc: int, tbl: dict, rng_scen: list, rng_wl: list, rng_pol: dict) -> tuple:
    # Hard guard: this launcher must never submit sc30–sc32
    if sc < FIRST_SCENARIO or sc > LAST_SCENARIO:
        raise RuntimeError(f"sc{sc} outside permitted range [{FIRST_SCENARIO},{LAST_SCENARIO}]")

    idx = sc - 30
    row = tbl[f"sc{sc}"]
    _assert_seeds(sc, tbl, rng_scen, rng_wl, rng_pol)

    out_file = RESULTS_DIR / f"gate_f_sc{sc}-{sc}_all_r2challenge.json"

    # Safety re-check: output may have appeared between startup scan and now
    if out_file.exists() and out_file.stat().st_size > 0:
        print(f"\n  [SKIP sc{sc}] output already exists at launch-time "
              f"({out_file.stat().st_size:,} bytes)", flush=True)
        return sc, {"ok": True, "skipped": True, "output_file": out_file.name,
                    "elapsed_s": 0}

    print(f"\n  [LAUNCH sc{sc}] idx={idx} scen={row['scen_seed']} wl={row['wl_seed']}"
          f" → {out_file.name}", flush=True)

    env = dict(os.environ)
    env["THERMALSHIFT_DATA_DIR"]    = DATA_DIR
    env["GATE_F_N_FIRST"]           = str(sc)
    env["GATE_F_N_DEV"]             = "1"
    env["GATE_F_REQUIRE_CLEAN_GIT"] = "1"
    for v in ["GATE_F_COMPAT_SEED", "GATE_F_COMPAT_BETA", "GATE_F_COMPAT_N_SCEN",
              "GATE_F_COMPAT_POLICY_ORDER", "GATE_F_RESTRICT_POLICIES", "GATE_F_RATIOS_ONLY"]:
        env.pop(v, None)

    t0 = time.time()
    try:
        proc = subprocess.run(
            [sys.executable, str(RUN_SCRIPT)],
            env=env, capture_output=True, text=True, encoding="utf-8",
            cwd=str(REPO_ROOT), timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        return sc, {"ok": False, "error": f"timed out (>{TIMEOUT_S}s)",
                    "elapsed_s": round(time.time() - t0, 1)}
    except Exception as exc:
        return sc, {"ok": False, "error": str(exc),
                    "elapsed_s": round(time.time() - t0, 1)}

    elapsed = round(time.time() - t0, 1)
    if proc.returncode != 0:
        err = (proc.stderr or proc.stdout or "")[-3000:]
        return sc, {"ok": False, "error": f"rc={proc.returncode}: {err}", "elapsed_s": elapsed}

    if not out_file.exists():
        return sc, {"ok": False, "error": f"output file not found: {out_file.name}",
                    "elapsed_s": elapsed}

    return sc, {"ok": True, "elapsed_s": elapsed, "output_file": out_file.name}


def main():
    now_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    print("=" * 70)
    print(f"Review-2 Challenge Orchestrator v2 (final): sc{FIRST_SCENARIO}-{LAST_SCENARIO}, 4 workers")
    print(f"  original_sha256 : {ORIGINAL_ORCHESTRATOR_SHA256}")
    print(f"  incident_record : {INCIDENT_RECORD}")
    print(f"  freeze_sha      : {FREEZE_SHA}")
    print(f"  data_dir        : {DATA_DIR}")
    print(f"  max_workers     : {MAX_WORKERS}")
    print(f"  first_scenario  : {FIRST_SCENARIO}  (sc30-sc32 completed under original launcher)")
    print(f"  last_scenario   : {LAST_SCENARIO}")
    print(f"  timeout/worker  : {TIMEOUT_S}s ({TIMEOUT_S//3600}h)")
    print(f"  started_utc     : {now_utc}")
    print("=" * 70)

    sa  = json.loads(AUDIT_FILE.read_text())
    tbl = sa["scenario_table"]

    # Re-derive seeds from rng(2042) for independent pre-launch assertion
    rng      = np.random.default_rng(2042)
    scen_s   = [int(rng.integers(0, 2**31)) for _ in range(25)]
    wl_s     = [int(rng.integers(0, 2**31)) for _ in range(25)]
    _pg      = int(rng.integers(0, 2**31))
    _pwc     = int(rng.integers(0, 2**31))
    assert _pg  == 218767960, f"placebo_global mismatch: {_pg}"
    assert _pwc == 365514213, f"placebo_withincab mismatch: {_pwc}"
    pol_s    = {p: [int(rng.integers(0, 2**31)) for _ in range(25)]
                for p in CHALLENGE_POLICY_IDS}

    print(f"\nSeed derivation verified: pg={_pg} pwc={_pwc}")

    # Build permitted scenario queue: FIRST_SCENARIO..LAST_SCENARIO only
    all_permitted = list(range(FIRST_SCENARIO, LAST_SCENARIO + 1))

    # Detect completed scenarios (output file exists and is non-empty)
    done_at_start = []
    scenarios     = []
    for sc in all_permitted:
        out_file = RESULTS_DIR / f"gate_f_sc{sc}-{sc}_all_r2challenge.json"
        if out_file.exists() and out_file.stat().st_size > 0:
            done_at_start.append(sc)
        else:
            scenarios.append(sc)

    print(f"\nPermitted range : sc{FIRST_SCENARIO}–sc{LAST_SCENARIO}")
    print(f"Already done    ({len(done_at_start)}): sc{done_at_start}")
    print(f"To run          ({len(scenarios)}): sc{scenarios}")

    if not scenarios:
        print(f"\nAll permitted scenarios sc{FIRST_SCENARIO}–{LAST_SCENARIO} already complete.")
        return 0

    results = {}
    t0_all  = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fs = {ex.submit(_launch_one, sc, tbl, scen_s, wl_s, pol_s): sc
              for sc in scenarios}
        for future in concurrent.futures.as_completed(fs):
            sc_abs, res = future.result()
            results[sc_abs] = res
            tag = "OK" if res.get("ok") else f"ERROR: {res.get('error','?')[:200]}"
            skip_note = " [skipped-already-done]" if res.get("skipped") else ""
            print(f"\n  [DONE sc{sc_abs}] {tag}{skip_note}  elapsed={res.get('elapsed_s','?')}s",
                  flush=True)

    elapsed_all = time.time() - t0_all
    failed = sorted(
        sc for sc, r in results.items()
        if not r.get("ok") and not r.get("skipped")
    )

    print("\n" + "=" * 70)
    print(f"All workers done. Total: {elapsed_all/3600:.2f}h")
    print(f"Already done at start ({len(done_at_start)}): sc{done_at_start}")
    if failed:
        print(f"FAILURES ({len(failed)}): sc{failed}")
    else:
        print(f"All {len(scenarios)} remaining scenarios completed successfully.")
    print("=" * 70)

    log = {
        "orchestrator"                 : "r2_challenge_orchestrator_4w.py",
        "version"                      : "final (FIRST_SCENARIO=33)",
        "original_orchestrator_sha256" : ORIGINAL_ORCHESTRATOR_SHA256,
        "incident_record"              : INCIDENT_RECORD,
        "superseded_draft_sha256"      : "e5d5f5c79dd6e852765b5f461dca344b04965aa6161ffc2a5e1bd41f1cbd89bd",
        "freeze_sha"                   : FREEZE_SHA,
        "data_dir"                     : DATA_DIR,
        "max_workers"                  : MAX_WORKERS,
        "first_scenario"               : FIRST_SCENARIO,
        "last_scenario"                : LAST_SCENARIO,
        "timeout_s"                    : TIMEOUT_S,
        "started_utc"                  : now_utc,
        "done_at_start"                : done_at_start,
        "scenarios_this_run"           : scenarios,
        "completed_utc"                : datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "elapsed_total_s"              : round(elapsed_all, 1),
        "results"                      : {str(k): v for k, v in sorted(results.items())},
        "n_run"                        : sum(1 for r in results.values() if not r.get("skipped")),
        "n_skipped_at_launch"          : sum(1 for r in results.values() if r.get("skipped")),
        "n_skipped_at_start"           : len(done_at_start),
        "n_failed"                     : len(failed),
        "all_pass"                     : len(failed) == 0,
    }
    log_file = RESULTS_DIR / "challenge_run_log_4w.json"
    log_file.write_text(json.dumps(log, indent=2))
    print(f"\nRun log: {log_file}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
