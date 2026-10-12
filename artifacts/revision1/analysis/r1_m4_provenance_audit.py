#!/usr/bin/env python3
"""
M4 Provenance audit.
Post-processing only. Verifies the frozen simulation output is internally
consistent and uncontaminated before paper numbers are written.

Checks:
  P01  30 unique scenario_idx values 0..29
  P02  Exactly one record per scenario
  P03  Scenario seeds match regeneration from SCENARIO_SEED=42
  P04  Workload seeds match regeneration from SCENARIO_SEED=42
  P05  All 7 expected policies present in every scenario's crossings
  P06  All 7 policies present in every scenario's lambda_rows
  P07  Design hash = fd520723fe2181e1 (v5 frozen run, not v3/v4)
  P08  git_sha starts with e400ff0 (correctness-fix commit)
  P09  T_THR_PRIMARY_C = 63.625 in parameters
  P10  BETA_F_FROZEN = 1.12484352 in parameters
  P11  threshold audit file corroborates 63.625 C (full-population p95)
  P12  No left_boundary scenario for full_fp (fp should always find a crossing)
  P13  All fp_spread scenarios are exact_bracket (not censored)
  P14  Scenario seeds in JSON match the first-5 scen_seeds we observed at runtime
  P15  SHA256 of r1_m4_fair_baselines.py (code identity, embedded in output)

Appends audit record to m4_provenance_audit.json.
"""

import hashlib, json, pathlib, sys
import numpy as np

OUT_DIR      = pathlib.Path(__file__).resolve().parents[3] / "artifacts" / "revision1" / "results"
ANALYSIS_DIR = pathlib.Path(__file__).resolve().parent
PRIMARY_IN   = OUT_DIR / "m4_fair_baselines.json"
CKPT_IN      = OUT_DIR / "m4_checkpoint.json"
THR_AUDIT    = OUT_DIR / "m4_threshold_audit.json"
SCRIPT_PATH  = ANALYSIS_DIR / "r1_m4_fair_baselines.py"
OUT_FILE     = OUT_DIR / "m4_provenance_audit.json"

EXPECTED_POLICIES = [
    "full_random", "full_fp", "full_loc", "full_compact",
    "marginal_random", "marginal_fp", "full_fp_spread",
]
EXPECTED_DESIGN_HASH = "fd520723fe2181e1"
EXPECTED_GIT_SHA_PREFIX = "e400ff0"
EXPECTED_T_THR = 63.625
EXPECTED_BETA_F = 1.12484352
SCENARIO_SEED = 42
N_SCENARIOS   = 30


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def regen_seeds(scenario_seed, n):
    master = np.random.default_rng(scenario_seed)
    scen_seeds = [int(master.integers(0, 2**31)) for _ in range(n)]
    wl_seeds   = [int(master.integers(0, 2**31)) for _ in range(n)]
    return scen_seeds, wl_seeds


def main():
    results = {}
    failures = []

    def check(key, condition, detail=""):
        results[key] = {"pass": bool(condition), "detail": detail}
        if not condition:
            failures.append(key)
        status = "PASS" if condition else "FAIL"
        print(f"  [{status}] {key}: {detail}")

    print("=" * 70)
    print("M4 PROVENANCE AUDIT")
    print("=" * 70)

    # Load primary output
    if not PRIMARY_IN.exists():
        print(f"FATAL: {PRIMARY_IN} not found")
        sys.exit(1)
    d   = json.loads(PRIMARY_IN.read_text())
    srs = sorted(d["scenario_results"], key=lambda x: x["scenario_idx"])

    # P01 — 30 unique scenario indices
    idxs = [sr["scenario_idx"] for sr in srs]
    check("P01_30_unique_scenario_idxs",
          len(set(idxs)) == 30 and set(idxs) == set(range(30)),
          f"found {len(set(idxs))} unique, range=[{min(idxs)},{max(idxs)}]")

    # P02 — exactly one record per scenario
    check("P02_one_record_per_scenario",
          len(idxs) == 30 and len(set(idxs)) == 30,
          f"total records={len(idxs)}")

    # P03/P04 — seed regeneration
    exp_scen, exp_wl = regen_seeds(SCENARIO_SEED, N_SCENARIOS)
    scen_ok = all(sr["scen_seed"] == exp_scen[sr["scenario_idx"]] for sr in srs)
    wl_ok   = all(sr["wl_seed"]   == exp_wl[sr["scenario_idx"]]   for sr in srs)
    check("P03_scenario_seeds_match_regen", scen_ok,
          f"all {N_SCENARIOS} scen_seeds match SCENARIO_SEED={SCENARIO_SEED}")
    check("P04_workload_seeds_match_regen", wl_ok,
          f"all {N_SCENARIOS} wl_seeds match SCENARIO_SEED={SCENARIO_SEED}")

    # P05 — all policies in crossings
    missing_cx = []
    for sr in srs:
        for pol in EXPECTED_POLICIES:
            if pol not in sr["crossings"]:
                missing_cx.append((sr["scenario_idx"], pol))
    check("P05_all_policies_in_crossings",
          len(missing_cx) == 0,
          f"missing={missing_cx[:5] if missing_cx else 'none'}")

    # P06 — all policies in lambda_rows
    missing_lr = []
    for sr in srs:
        for pol in EXPECTED_POLICIES:
            if pol not in sr.get("lambda_rows", {}):
                missing_lr.append((sr["scenario_idx"], pol))
    check("P06_all_policies_in_lambda_rows",
          len(missing_lr) == 0,
          f"missing={missing_lr[:5] if missing_lr else 'none'}")

    # P07 — design hash
    ckpt_hash = None
    if CKPT_IN.exists():
        ckpt = json.loads(CKPT_IN.read_text())
        ckpt_hash = ckpt.get("design_hash", "")
    check("P07_design_hash_matches_v5",
          ckpt_hash == EXPECTED_DESIGN_HASH,
          f"checkpoint hash={ckpt_hash!r} expected={EXPECTED_DESIGN_HASH!r}")

    # P08 — git SHA
    git_sha = d.get("git_sha", "")
    check("P08_git_sha_is_correctness_fix_commit",
          git_sha.startswith(EXPECTED_GIT_SHA_PREFIX),
          f"git_sha={git_sha[:12]!r} (expected prefix {EXPECTED_GIT_SHA_PREFIX!r})")

    # P09 — threshold
    t_thr = d["parameters"].get("T_THR_PRIMARY_C", None)
    check("P09_threshold_63625",
          t_thr is not None and abs(t_thr - EXPECTED_T_THR) < 1e-4,
          f"T_THR_PRIMARY_C={t_thr}")

    # P10 — beta
    beta = d["parameters"].get("BETA_F_FROZEN", None)
    check("P10_beta_f_frozen",
          beta is not None and abs(beta - EXPECTED_BETA_F) < 1e-6,
          f"BETA_F_FROZEN={beta}")

    # P11 — threshold audit corroborates
    if THR_AUDIT.exists():
        ta = json.loads(THR_AUDIT.read_text())
        fp_p95 = ta.get("full_population", {}).get("p95_C", None)
        check("P11_threshold_audit_corroborates",
              fp_p95 is not None and abs(fp_p95 - EXPECTED_T_THR) < 0.01,
              f"full_pop p95={fp_p95}, expected={EXPECTED_T_THR}")
    else:
        check("P11_threshold_audit_corroborates", False,
              f"audit file not found: {THR_AUDIT}")

    # P12 — full_fp never left_boundary
    fp_lb = [sr["scenario_idx"] for sr in srs
             if sr["crossings"]["full_fp"]["status"] == "left_boundary"]
    check("P12_full_fp_no_left_boundary",
          len(fp_lb) == 0,
          f"left_boundary scenarios: {fp_lb}")

    # P13 — fp_spread always exact_bracket
    fps_not_exact = [sr["scenario_idx"] for sr in srs
                     if sr["crossings"]["full_fp_spread"]["status"] != "exact_bracket"]
    check("P13_fp_spread_all_exact_bracket",
          len(fps_not_exact) == 0,
          f"non-exact: {fps_not_exact}")

    # P14 — first-5 seeds match runtime-observed values
    runtime_observed = [
        (191664964, 967354525),
        (1662057958, 487991439),
        (1405681632, 197860369),
        (942484272, 1190961761),
        (929893138, 1906728919),
    ]
    seed_match = all(
        srs[i]["scen_seed"] == runtime_observed[i][0] and
        srs[i]["wl_seed"]   == runtime_observed[i][1]
        for i in range(5)
    )
    check("P14_first5_seeds_match_runtime_log",
          seed_match,
          "scen_seed and wl_seed for sc0-4 match values printed in m4_v5_main.log")

    # P15 — script SHA256
    script_sha = sha256_file(SCRIPT_PATH) if SCRIPT_PATH.exists() else "FILE_NOT_FOUND"
    check("P15_script_sha256_recorded",
          SCRIPT_PATH.exists(),
          f"SHA256({SCRIPT_PATH.name})={script_sha[:16]}...")

    # Summary
    n_pass = sum(1 for v in results.values() if v["pass"])
    n_fail = len(failures)
    print()
    print(f"{'='*70}")
    print(f"RESULT: {n_pass}/15 checks passed")
    if failures:
        print(f"FAILED: {failures}")
    else:
        print("ALL CHECKS PASSED")
    print(f"{'='*70}")

    # Save
    out = {
        "source":        str(PRIMARY_IN),
        "script_sha256": script_sha,
        "git_sha":       git_sha,
        "checks":        results,
        "n_pass":        n_pass,
        "n_fail":        n_fail,
        "failed_checks": failures,
        "overall_pass":  n_fail == 0,
        "note": ("SHA256 of r1_m4_fair_baselines.py recorded for code identity. "
                 "Future design hashes should include this value alongside the "
                 "parameter JSON to make code changes invalidate checkpoints."),
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {OUT_FILE}")

    return n_fail == 0


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)
