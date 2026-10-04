#!/usr/bin/env python3
"""
Challenge run orchestrator: sc30-54, 2 concurrent workers, frozen config at 5733b73.
Operational only — does not affect seeds, policies, thresholds, or analysis logic.

Asserts each scenario's seeds against challenge_seed_index_audit.json (and
re-derives independently from rng(2042)) before the worker subprocess launches.
Workers write: gate_f_sc{n}-{n}_all_r2challenge.json (one per scenario).
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
MAX_WORKERS = 2
TIMEOUT_S   = 21600   # 6 hours per worker

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
    idx = sc - 30
    row = tbl[f"sc{sc}"]
    _assert_seeds(sc, tbl, rng_scen, rng_wl, rng_pol)

    out_file = RESULTS_DIR / f"gate_f_sc{sc}-{sc}_all_r2challenge.json"
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
    print("=" * 70)
    print("Review-2 Challenge Orchestrator: sc30-54")
    print(f"  freeze_sha     : {FREEZE_SHA}")
    print(f"  data_dir       : {DATA_DIR}")
    print(f"  max_workers    : {MAX_WORKERS}")
    print(f"  timeout/worker : {TIMEOUT_S}s ({TIMEOUT_S//3600}h)")
    print(f"  started_utc    : {datetime.datetime.utcnow().isoformat()}Z")
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

    scenarios = list(range(30, 55))
    results   = {}
    t0_all    = time.time()

    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        fs = {ex.submit(_launch_one, sc, tbl, scen_s, wl_s, pol_s): sc
              for sc in scenarios}
        for future in concurrent.futures.as_completed(fs):
            sc_abs, res = future.result()
            results[sc_abs] = res
            tag = "OK" if res.get("ok") else f"ERROR: {res.get('error','?')[:200]}"
            print(f"\n  [DONE sc{sc_abs}] {tag}  elapsed={res.get('elapsed_s','?')}s",
                  flush=True)

    elapsed_all = time.time() - t0_all
    failed = sorted(sc for sc, r in results.items() if not r.get("ok"))

    print("\n" + "=" * 70)
    print(f"All workers done. Total: {elapsed_all/3600:.2f}h")
    if failed:
        print(f"FAILURES ({len(failed)}): sc{failed}")
    else:
        print(f"All {len(scenarios)} scenarios completed successfully.")
    print("=" * 70)

    log = {
        "orchestrator"    : "r2_challenge_orchestrator.py",
        "freeze_sha"      : FREEZE_SHA,
        "data_dir"        : DATA_DIR,
        "max_workers"     : MAX_WORKERS,
        "timeout_s"       : TIMEOUT_S,
        "scenarios"       : scenarios,
        "completed_utc"   : datetime.datetime.utcnow().isoformat() + "Z",
        "elapsed_total_s" : round(elapsed_all, 1),
        "results"         : {str(k): v for k, v in sorted(results.items())},
        "n_completed"     : sum(1 for r in results.values() if r.get("ok")),
        "n_failed"        : len(failed),
        "all_pass"        : len(failed) == 0,
    }
    log_file = RESULTS_DIR / "challenge_run_log.json"
    log_file.write_text(json.dumps(log, indent=2))
    print(f"\nRun log: {log_file}")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
