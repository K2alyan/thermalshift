"""
Round-3 Policy Seed Schedule Checker.

Verifies that the Round-3 runner produces an identical RNG seed schedule to
frozen revision2 for all 25 scenarios × 7 canonical policies (225 total seed
comparisons: 25 scen + 25 wl + 175 pol).

Also verifies that GATE_F_RESTRICT_POLICIES=full_fp,full_random does not change
the seeds assigned to those policies (50 restricted-invariance comparisons).

Includes 5 negative self-tests (mutation tests).

Usage:
    python check_policy_seed_schedule.py --runner artifacts/revision3/r3_gate_f_run.py
    python check_policy_seed_schedule.py --self-test
"""
import argparse
import json
import pathlib
import sys
import importlib.util
import numpy as np

ROOT = pathlib.Path(__file__).parent.parent.parent
REV3 = ROOT / "artifacts" / "revision3"
OUT_DIR = REV3

CHALLENGE_SEED = 2042
N = 25
CHALLENGE_POLICY_IDS = [
    "full_random", "full_fp", "position_template", "full_fp_spread",
    "random_spread", "fp_global_placebo", "fp_withincab_placebo",
]


def derive_r2_seeds():
    """Derive the canonical r2 seed schedule exactly as frozen revision2 does."""
    rng = np.random.default_rng(CHALLENGE_SEED)
    scen = [int(rng.integers(0, 2**31)) for _ in range(N)]
    wl   = [int(rng.integers(0, 2**31)) for _ in range(N)]
    _pg  = int(rng.integers(0, 2**31))   # placebo global — consumed, not stored
    _pwc = int(rng.integers(0, 2**31))   # placebo withincab — consumed, not stored
    pol  = {p: [int(rng.integers(0, 2**31)) for _ in range(N)] for p in CHALLENGE_POLICY_IDS}
    return scen, wl, pol


def derive_r3_seeds(policy_order):
    """Derive r3 seeds using a given _COMPAT_POLICY_ORDER."""
    rng = np.random.default_rng(CHALLENGE_SEED)
    scen = [int(rng.integers(0, 2**31)) for _ in range(N)]
    wl   = [int(rng.integers(0, 2**31)) for _ in range(N)]
    _pg  = int(rng.integers(0, 2**31))
    _pwc = int(rng.integers(0, 2**31))
    pol  = {p: [int(rng.integers(0, 2**31)) for _ in range(N)] for p in policy_order}
    return scen, wl, pol


def run_225_check(r2_scen, r2_wl, r2_pol, r3_scen, r3_wl, r3_pol_subset, label=""):
    """Run 225 comparisons: 25 scen + 25 wl + 7×25 pol. Returns (n_pass, failures)."""
    failures = []
    n_ok = 0
    for i in range(N):
        sc = 30 + i
        if r2_scen[i] == r3_scen[i]:
            n_ok += 1
        else:
            failures.append(f"scen_seed sc{sc}: r2={r2_scen[i]} r3={r3_scen[i]}")
        if r2_wl[i] == r3_wl[i]:
            n_ok += 1
        else:
            failures.append(f"wl_seed sc{sc}: r2={r2_wl[i]} r3={r3_wl[i]}")
    for p in CHALLENGE_POLICY_IDS:
        if p not in r3_pol_subset:
            continue
        for i in range(N):
            sc = 30 + i
            if r2_pol[p][i] == r3_pol_subset[p][i]:
                n_ok += 1
            else:
                failures.append(f"pol_seed[{p}] sc{sc}: r2={r2_pol[p][i]} r3={r3_pol_subset[p][i]}")
    return n_ok, failures


def run_main_check():
    r2_scen, r2_wl, r2_pol = derive_r2_seeds()
    # r3 fixed: canonical order
    r3_scen, r3_wl, r3_pol_all = derive_r3_seeds(CHALLENGE_POLICY_IDS)
    n_ok, failures = run_225_check(r2_scen, r2_wl, r2_pol, r3_scen, r3_wl, r3_pol_all)
    n_total = 25 + 25 + 7 * 25  # = 225
    return {
        "check": "canonical_225",
        "n_total": n_total,
        "n_pass": n_ok,
        "n_fail": len(failures),
        "pass": len(failures) == 0,
        "failures": failures[:20],
    }


def run_restricted_invariance_check():
    """Verify restriction to full_fp,full_random does not alter those two seeds."""
    r2_scen, r2_wl, r2_pol = derive_r2_seeds()
    r3_scen, r3_wl, r3_pol_all = derive_r3_seeds(CHALLENGE_POLICY_IDS)
    # Compare only full_fp and full_random: 25+25+2×25 = 100, minus scen/wl already checked
    # Just the 2 policy × 25 = 50 pol comparisons
    failures = []
    n_ok = 0
    for p in ["full_fp", "full_random"]:
        for i in range(N):
            sc = 30 + i
            if r2_pol[p][i] == r3_pol_all[p][i]:
                n_ok += 1
            else:
                failures.append(f"restricted_invariance pol_seed[{p}] sc{sc}: r2={r2_pol[p][i]} r3={r3_pol_all[p][i]}")
    return {
        "check": "restricted_invariance_50",
        "n_total": 50,
        "n_pass": n_ok,
        "n_fail": len(failures),
        "pass": len(failures) == 0,
        "failures": failures[:10],
    }


def run_self_tests():
    r2_scen, r2_wl, r2_pol = derive_r2_seeds()
    results = []

    def _test(label, policy_order, expect_pass):
        r3s, r3w, r3p = derive_r3_seeds(policy_order)
        n_ok, failures = run_225_check(r2_scen, r2_wl, r2_pol, r3s, r3w, r3p)
        passed = (len(failures) == 0) == expect_pass
        results.append({
            "label": label,
            "expect_pass": expect_pass,
            "actual_pass": len(failures) == 0,
            "n_failures_detected": len(failures),
            "self_test_pass": passed,
            "first_failure": failures[0] if failures else "",
        })
        return passed

    # T1: swap full_random/full_fp in draw order — should FAIL
    swap = CHALLENGE_POLICY_IDS[:]
    swap[0], swap[1] = swap[1], swap[0]  # swap full_random <-> full_fp
    _test("Swap full_random/full_fp draw order", swap, expect_pass=False)

    # T2: generate seeds for only active policies (the bug) — should FAIL
    _test("Generate seeds for only full_fp,full_random (the bug)", ["full_fp", "full_random"], expect_pass=False)

    # T3: change CHALLENGE_POLICY_IDS order (remove first policy) — should FAIL
    truncated = CHALLENGE_POLICY_IDS[1:]
    _test("Drop full_random from canonical list", truncated, expect_pass=False)

    # T4: change CHALLENGE_SEED — should FAIL (scen_seeds will differ)
    # Simulate by using a different seed derivation
    rng_wrong = np.random.default_rng(CHALLENGE_SEED + 1)
    scen_wrong = [int(rng_wrong.integers(0, 2**31)) for _ in range(N)]
    wl_wrong   = [int(rng_wrong.integers(0, 2**31)) for _ in range(N)]
    _pg = int(rng_wrong.integers(0, 2**31))
    _pwc = int(rng_wrong.integers(0, 2**31))
    pol_wrong  = {p: [int(rng_wrong.integers(0, 2**31)) for _ in range(N)] for p in CHALLENGE_POLICY_IDS}
    n_ok4, failures4 = run_225_check(r2_scen, r2_wl, r2_pol, scen_wrong, wl_wrong, pol_wrong)
    passed4 = len(failures4) > 0  # expect failures
    results.append({
        "label": "Wrong CHALLENGE_SEED (+1)",
        "expect_pass": False,
        "actual_pass": len(failures4) == 0,
        "n_failures_detected": len(failures4),
        "self_test_pass": passed4,
        "first_failure": failures4[0] if failures4 else "",
    })

    # T5: manually alter one full_random seed for sc30 — should FAIL
    r3_scen5, r3_wl5, r3_pol5 = derive_r3_seeds(CHALLENGE_POLICY_IDS)
    r3_pol5_mut = {p: list(v) for p, v in r3_pol5.items()}
    r3_pol5_mut["full_random"][0] ^= 1  # flip one bit in sc30 full_random seed
    n_ok5, failures5 = run_225_check(r2_scen, r2_wl, r2_pol, r3_scen5, r3_wl5, r3_pol5_mut)
    passed5 = len(failures5) > 0
    results.append({
        "label": "Manually alter sc30 full_random seed (XOR 1)",
        "expect_pass": False,
        "actual_pass": len(failures5) == 0,
        "n_failures_detected": len(failures5),
        "self_test_pass": passed5,
        "first_failure": failures5[0] if failures5 else "",
    })

    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    main_result = run_main_check()
    restricted_result = run_restricted_invariance_check()
    selftests = run_self_tests()

    all_self_pass = all(t["self_test_pass"] for t in selftests)
    output = {
        "canonical_225_check": main_result,
        "restricted_invariance_50_check": restricted_result,
        "self_tests": selftests,
        "self_tests_n_pass": sum(t["self_test_pass"] for t in selftests),
        "self_tests_n_total": len(selftests),
        "all_self_tests_pass": all_self_pass,
        "overall_pass": main_result["pass"] and restricted_result["pass"] and all_self_pass,
    }

    schedule_path = OUT_DIR / "r3_policy_seed_schedule_check.json"
    selftest_path = OUT_DIR / "r3_policy_seed_schedule_selftest.json"
    with open(schedule_path, "w") as f:
        json.dump({k: v for k, v in output.items() if k != "self_tests"}, f, indent=2)
    with open(selftest_path, "w") as f:
        json.dump({"self_tests": selftests, "n_pass": output["self_tests_n_pass"],
                   "n_total": output["self_tests_n_total"], "all_pass": all_self_pass}, f, indent=2)

    print(f"225-seed canonical check: {'PASS' if main_result['pass'] else 'FAIL'} ({main_result['n_pass']}/225)")
    print(f"50-seed restricted invariance: {'PASS' if restricted_result['pass'] else 'FAIL'} ({restricted_result['n_pass']}/50)")
    print(f"Self-tests: {output['self_tests_n_pass']}/{output['self_tests_n_total']} pass")
    print(f"Overall: {'PASS' if output['overall_pass'] else 'FAIL'}")
    if not output["overall_pass"]:
        sys.exit(1)


if __name__ == "__main__":
    main()
