"""
Round-3 Task Q — Legacy-Mode Equivalence Check (Amendment 3).

Verifies that the Round-3 legacy-mode runner (using F1 cabinet reference,
identical to r2_gate_f_run.py) produces results matching the frozen sc30-sc54
revision2 challenge results, before any Round-3-specific scenarios are run.

R3-0 replays sc30-sc54 (the exact 25 revision2 held-out scenarios) in legacy
mode. The scenario set must be EXACTLY {30,...,54}:
- Missing scenarios: HARD FAIL (exit 2)
- Extra scenarios beyond {30,...,54}: HARD FAIL (exit 2)
- Duplicate scenario IDs in either file: HARD FAIL (exit 2)

Field comparison:
- Required fields are checked for presence on BOTH sides before comparison.
- Key absent on either side -> HARD FAIL for that field.
- Key present with JSON null on both sides -> pass (legitimate null).
- Key present with JSON null on one side only -> FAIL (null mismatch).
- None-vs-None on ABSENT keys can never pass: the sentinel distinguishes
  "key absent" from "key present with None".

Schema source: artifacts/revision3/r2_equivalence_schema.json
Plan ref: artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §Q (v2.2)
Amendment: 3

USAGE:
  python check_r3_legacy_equivalence.py --r3-output <path>
  python check_r3_legacy_equivalence.py --self-test
"""
import argparse
import copy
import json
import pathlib
import sys

ROOT    = pathlib.Path(__file__).parent.parent.parent
REV2    = ROOT / "artifacts" / "revision2"
OUT_DIR = ROOT / "artifacts" / "revision3"

TOLERANCE = 1e-9
REQUIRED_SCENARIOS = set(range(30, 55))  # exactly sc30-sc54
EQUIV_POLICIES     = ["full_fp", "full_random"]
EQUIV_RATIO        = "1.25"

POST_EXPOSURE_LABEL = (
    "Post-exposure: designed after sc30-sc54 primary results observed. "
    "Equivalence check verifies Round-3 legacy mode matches revision2 challenge "
    "on ALL 25 sc30-sc54 scenarios. Partial sets and extra scenarios both fail."
)

# ---------------------------------------------------------------------------
# Authoritative field lists (from r2_equivalence_schema.json)
# ---------------------------------------------------------------------------
SCENARIO_FIELDS = [
    "scenario_idx",
    "scenario_array_i",
    "scen_seed",
    "wl_seed",
    "B_ref_s",      # thermal node-level budget reference (hours); varies per scenario
    "S_ref_s",      # thermal severity reference (C*h); varies per scenario
]
# Note: B_ref_s and S_ref_s are THERMAL references, NOT cabinet exceedance denominators.
# The cabinet exceedance denominator is B_cab_hist (not stored in per-scenario output).

LAMBDA_ROW_NUMERIC = [
    "lambda_val",
    "nominal_choice_ratio",
    "capacity_unlock_pct",
    "B_primary_h",
    "S_primary_Cdoth",
    "B_secondary_h",
    "B_cab_ratio",
    "B_primary_ratio",
    "S_primary_ratio",
    "syn_node_hours",
    "n_syn_admit",
    "n_drop_cap",
    "n_drop_physical",
    "n_drop_la",
    "n_base_unserved",
    "cab_span_median",
    "full_selector_eligible_count_p10",
    "full_selector_eligible_count_p50",
    "full_selector_eligible_count_p90",
    "exposed_selector_eligible_count_p10",
    "exposed_selector_eligible_count_p50",
    "exposed_selector_eligible_count_p90",
    "realized_selector_choice_mult_p10",
    "realized_selector_choice_mult_p50",
    "realized_selector_choice_mult_p90",
]
LAMBDA_ROW_NULLABLE_NUMERIC = [
    "mean_F_syn",     # null when no synthetic jobs admitted
]
LAMBDA_ROW_NULLABLE_CATEGORICAL = [
    "first_binding",  # null or constraint name string (e.g. "B_cab_ratio")
]
LAMBDA_ROW_CATEGORICAL = [
    "policy",
    "invariant_violated",
    "infeasible",
]
CROSSING_NUMERIC = [
    "C_lower_pct",
    "C_upper_pct",
]
CROSSING_CATEGORICAL = [
    "status",
    "first_binding_constraint",
    "right_censored",
]

# ---------------------------------------------------------------------------
# Field-presence sentinel
# ---------------------------------------------------------------------------
_ABSENT = object()   # distinguishes key-absent from key-present-with-None


def _get(obj, key):
    """Return (present: bool, value). None value is legitimate if key exists."""
    if key in obj:
        return True, obj[key]
    return False, _ABSENT


def _cmp_numeric(key, obj2, obj3, label, failures, n_ok):
    ok2, v2 = _get(obj2, key)
    ok3, v3 = _get(obj3, key)
    if not ok2:
        failures.append(f"MISSING_KEY r2 {label}.{key}")
        return n_ok
    if not ok3:
        failures.append(f"MISSING_KEY r3 {label}.{key}")
        return n_ok
    # Both keys exist
    if v2 is None and v3 is None:
        return n_ok + 1            # legitimate JSON null on both sides
    if v2 is None or v3 is None:
        failures.append(f"NULL_MISMATCH {label}.{key}: r2={v2!r} r3={v3!r}")
        return n_ok
    try:
        diff = abs(float(v2) - float(v3))
    except (TypeError, ValueError):
        failures.append(f"TYPE_ERROR {label}.{key}: r2={v2!r} r3={v3!r}")
        return n_ok
    if diff > TOLERANCE:
        failures.append(f"NUMERIC_DIFF {label}.{key}: |{v2!r}-{v3!r}|={diff:.3e} > {TOLERANCE:.0e}")
    else:
        n_ok += 1
    return n_ok


def _cmp_categorical(key, obj2, obj3, label, failures, n_ok):
    ok2, v2 = _get(obj2, key)
    ok3, v3 = _get(obj3, key)
    if not ok2:
        failures.append(f"MISSING_KEY r2 {label}.{key}")
        return n_ok
    if not ok3:
        failures.append(f"MISSING_KEY r3 {label}.{key}")
        return n_ok
    if v2 == v3:
        return n_ok + 1
    failures.append(f"CATEGORICAL_MISMATCH {label}.{key}: r2={v2!r} r3={v3!r}")
    return n_ok


def _cmp_nullable_numeric(key, obj2, obj3, label, failures, n_ok):
    """Nullable numeric: null-vs-null OK; null-vs-value FAIL; both non-null -> numeric cmp."""
    ok2, v2 = _get(obj2, key)
    ok3, v3 = _get(obj3, key)
    if not ok2:
        failures.append(f"MISSING_KEY r2 {label}.{key}")
        return n_ok
    if not ok3:
        failures.append(f"MISSING_KEY r3 {label}.{key}")
        return n_ok
    if v2 is None and v3 is None:
        return n_ok + 1
    if v2 is None or v3 is None:
        failures.append(f"NULL_MISMATCH {label}.{key}: r2={v2!r} r3={v3!r}")
        return n_ok
    try:
        diff = abs(float(v2) - float(v3))
    except (TypeError, ValueError):
        failures.append(f"TYPE_ERROR {label}.{key}: r2={v2!r} r3={v3!r}")
        return n_ok
    if diff > TOLERANCE:
        failures.append(f"NUMERIC_DIFF {label}.{key}: |{v2!r}-{v3!r}|={diff:.3e} > {TOLERANCE:.0e}")
    else:
        n_ok += 1
    return n_ok


def _cmp_nullable_categorical(key, obj2, obj3, label, failures, n_ok):
    """Nullable categorical: null-vs-null OK; null-vs-value FAIL; both non-null -> exact equality."""
    ok2, v2 = _get(obj2, key)
    ok3, v3 = _get(obj3, key)
    if not ok2:
        failures.append(f"MISSING_KEY r2 {label}.{key}")
        return n_ok
    if not ok3:
        failures.append(f"MISSING_KEY r3 {label}.{key}")
        return n_ok
    if v2 is None and v3 is None:
        return n_ok + 1
    if v2 is None or v3 is None:
        failures.append(f"NULL_MISMATCH {label}.{key}: r2={v2!r} r3={v3!r}")
        return n_ok
    if v2 == v3:
        return n_ok + 1
    failures.append(f"CATEGORICAL_MISMATCH {label}.{key}: r2={v2!r} r3={v3!r}")
    return n_ok


# ---------------------------------------------------------------------------
# Scenario-set validation
# ---------------------------------------------------------------------------
def _validate_scenario_set(scenario_list, label):
    """Return (id_set, errors). Checks for exact {30,...,54}, extras, duplicates."""
    errors = []
    ids = []
    for s in scenario_list:
        idx = s.get("scenario_idx", s.get("scenario_index"))
        if idx is None:
            errors.append(f"{label}: scenario with no scenario_idx found")
        else:
            ids.append(int(idx))
    # Duplicates
    seen = set()
    for i in ids:
        if i in seen:
            errors.append(f"{label}: duplicate scenario_idx={i}")
        seen.add(i)
    id_set = set(ids)
    missing = REQUIRED_SCENARIOS - id_set
    extra   = id_set - REQUIRED_SCENARIOS
    if missing:
        errors.append(f"{label}: missing scenarios {sorted(missing)}")
    if extra:
        errors.append(f"{label}: extra scenarios not in {{30..54}}: {sorted(extra)}")
    return id_set, errors


# ---------------------------------------------------------------------------
# Main equivalence check
# ---------------------------------------------------------------------------
def check_equivalence(r2_results, r3_results):
    failures = []
    n_ok     = 0

    r2_list = r2_results.get("scenario_results", [])
    r3_list = r3_results.get("scenario_results", [])

    # Validate scenario sets — both sides must be exactly {30,...,54}
    r2_ids, r2_errs = _validate_scenario_set(r2_list, "r2")
    r3_ids, r3_errs = _validate_scenario_set(r3_list, "r3")
    set_errors = r2_errs + r3_errs
    if set_errors:
        return {
            "pass": False,
            "hard_failure": True,
            "reason": "Scenario-set validation failed",
            "set_errors": set_errors,
            "n_failures": len(set_errors),
            "failures": set_errors,
        }

    r2_map = {s["scenario_idx"]: s for s in r2_list}
    r3_map = {s["scenario_idx"]: s for s in r3_list}

    for sc_idx in sorted(REQUIRED_SCENARIOS):
        sc2 = r2_map[sc_idx]
        sc3 = r3_map[sc_idx]
        lbl_sc = f"sc{sc_idx}"

        # Scenario-level fields
        for fld in SCENARIO_FIELDS:
            n_ok = _cmp_numeric(fld, sc2, sc3, lbl_sc, failures, n_ok)

        # Ratio structure
        r2_ratios = sc2.get("ratios", {})
        r3_ratios = sc3.get("ratios", {})
        if EQUIV_RATIO not in r2_ratios:
            failures.append(f"MISSING_RATIO r2 sc{sc_idx} ratio={EQUIV_RATIO}")
            continue
        if EQUIV_RATIO not in r3_ratios:
            failures.append(f"MISSING_RATIO r3 sc{sc_idx} ratio={EQUIV_RATIO}")
            continue

        r2_pol = r2_ratios[EQUIV_RATIO]
        r3_pol = r3_ratios[EQUIV_RATIO]

        for policy in EQUIV_POLICIES:
            lbl_pol = f"sc{sc_idx} r={EQUIV_RATIO} {policy}"
            if policy not in r2_pol:
                failures.append(f"MISSING_POLICY r2 {lbl_pol}")
                continue
            if policy not in r3_pol:
                failures.append(f"MISSING_POLICY r3 {lbl_pol}")
                continue

            pd2 = r2_pol[policy]
            pd3 = r3_pol[policy]

            # Lambda rows
            rows2 = pd2.get("lambda_rows", [])
            rows3 = pd3.get("lambda_rows", [])
            if len(rows2) != len(rows3):
                failures.append(
                    f"LAMBDA_COUNT_MISMATCH {lbl_pol}: r2={len(rows2)} r3={len(rows3)}"
                )
            else:
                for i, (row2, row3) in enumerate(zip(rows2, rows3)):
                    lbl_row = f"{lbl_pol} lambda_row[{i}]"
                    for fld in LAMBDA_ROW_NUMERIC:
                        n_ok = _cmp_numeric(fld, row2, row3, lbl_row, failures, n_ok)
                    for fld in LAMBDA_ROW_NULLABLE_NUMERIC:
                        n_ok = _cmp_nullable_numeric(fld, row2, row3, lbl_row, failures, n_ok)
                    for fld in LAMBDA_ROW_NULLABLE_CATEGORICAL:
                        n_ok = _cmp_nullable_categorical(fld, row2, row3, lbl_row, failures, n_ok)
                    for fld in LAMBDA_ROW_CATEGORICAL:
                        n_ok = _cmp_categorical(fld, row2, row3, lbl_row, failures, n_ok)

            # Crossing
            cross2 = pd2.get("crossing", {})
            cross3 = pd3.get("crossing", {})
            lbl_cx = f"{lbl_pol} crossing"
            for fld in CROSSING_NUMERIC:
                n_ok = _cmp_numeric(fld, cross2, cross3, lbl_cx, failures, n_ok)
            for fld in CROSSING_CATEGORICAL:
                n_ok = _cmp_categorical(fld, cross2, cross3, lbl_cx, failures, n_ok)

    return {
        "pass": len(failures) == 0,
        "hard_failure": False,
        "tolerance": TOLERANCE,
        "n_required_scenarios": len(REQUIRED_SCENARIOS),
        "n_policies_checked": len(EQUIV_POLICIES),
        "ratio_checked": EQUIV_RATIO,
        "n_checks_passed": n_ok,
        "n_failures": len(failures),
        "failures": failures[:50],
    }


# ---------------------------------------------------------------------------
# Self-tests: 10 mutations + 1 identity
# ---------------------------------------------------------------------------
def run_self_tests(r2_results):
    """Run 10 negative tests + 1 positive identity test against frozen r2 data."""
    results = []

    def _run(label, r2_mod, r3_mod, expect_pass):
        result = check_equivalence(r2_mod, r3_mod)
        passed = result["pass"] == expect_pass
        results.append({
            "test_id": len(results) + 1,
            "label": label,
            "expect_pass": expect_pass,
            "actual_pass": result["pass"],
            "hard_failure": result.get("hard_failure", False),
            "n_failures_detected": result.get("n_failures", 0),
            "self_test_pass": passed,
            "first_failure": result.get("failures", [""])[0] if not result["pass"] else "",
        })
        return passed

    base = copy.deepcopy(r2_results)
    scenarios = base["scenario_results"]

    # Test 10: identity — deep copy of r2 vs itself PASSES
    _run("Identity: r2 deep copy vs itself", copy.deepcopy(base), copy.deepcopy(base), True)

    # Test 1: remove one scenario from r3 — HARD FAIL
    r3_short = copy.deepcopy(base)
    r3_short["scenario_results"] = [s for s in r3_short["scenario_results"] if s["scenario_idx"] != 30]
    _run("Remove sc30 from r3 (missing scenario)", copy.deepcopy(base), r3_short, False)

    # Test 2: add one extra scenario to r3 — HARD FAIL
    r3_extra = copy.deepcopy(base)
    extra_sc = copy.deepcopy(r3_extra["scenario_results"][0])
    extra_sc["scenario_idx"] = 99  # not in {30..54}
    r3_extra["scenario_results"].append(extra_sc)
    _run("Extra sc99 in r3 (out-of-range scenario)", copy.deepcopy(base), r3_extra, False)

    # Test 3: change scen_seed of sc30 in r3
    r3_seed = copy.deepcopy(base)
    for s in r3_seed["scenario_results"]:
        if s["scenario_idx"] == 30:
            s["scen_seed"] = s["scen_seed"] + 1
    _run("Mutate scen_seed of sc30 in r3", copy.deepcopy(base), r3_seed, False)

    # Test 4: change wl_seed of sc31 in r3
    r3_wl = copy.deepcopy(base)
    for s in r3_wl["scenario_results"]:
        if s["scenario_idx"] == 31:
            s["wl_seed"] = s["wl_seed"] + 1
    _run("Mutate wl_seed of sc31 in r3", copy.deepcopy(base), r3_wl, False)

    # Test 5: change lambda_val of row[0] of full_fp at r=1.25 for sc32 by 2e-9 > tol
    r3_lval = copy.deepcopy(base)
    for s in r3_lval["scenario_results"]:
        if s["scenario_idx"] == 32:
            row0 = s["ratios"]["1.25"]["full_fp"]["lambda_rows"][0]
            row0["lambda_val"] = row0["lambda_val"] + 2e-9
    _run("Mutate lambda_val of sc32 full_fp row[0] by 2e-9", copy.deepcopy(base), r3_lval, False)

    # Test 6: change C_lower_pct of full_random crossing for sc33 by 2e-9
    r3_clower = copy.deepcopy(base)
    for s in r3_clower["scenario_results"]:
        if s["scenario_idx"] == 33:
            cross = s["ratios"]["1.25"]["full_random"]["crossing"]
            cross["C_lower_pct"] = cross["C_lower_pct"] + 2e-9
    _run("Mutate C_lower_pct of sc33 full_random crossing by 2e-9", copy.deepcopy(base), r3_clower, False)

    # Test 7: change first_binding_constraint of full_fp crossing for sc34
    r3_fbc = copy.deepcopy(base)
    for s in r3_fbc["scenario_results"]:
        if s["scenario_idx"] == 34:
            cross = s["ratios"]["1.25"]["full_fp"]["crossing"]
            old = cross.get("first_binding_constraint", "B_cab_ratio")
            cross["first_binding_constraint"] = "B_ratio" if old != "B_ratio" else "B_cab_ratio"
    _run("Mutate first_binding_constraint of sc34 full_fp", copy.deepcopy(base), r3_fbc, False)

    # Test 8: delete required field B_ref_s from sc35 in r3
    r3_del = copy.deepcopy(base)
    for s in r3_del["scenario_results"]:
        if s["scenario_idx"] == 35:
            del s["B_ref_s"]
    _run("Delete B_ref_s field from sc35 in r3", copy.deepcopy(base), r3_del, False)

    # Test 9: change B_primary_h from value to null for sc36 full_fp row[1] in r3
    r3_null = copy.deepcopy(base)
    for s in r3_null["scenario_results"]:
        if s["scenario_idx"] == 36:
            rows = s["ratios"]["1.25"]["full_fp"]["lambda_rows"]
            if len(rows) > 1:
                rows[1]["B_primary_h"] = None
            else:
                rows[0]["B_primary_h"] = None
    _run("Set B_primary_h to null for sc36 full_fp in r3", copy.deepcopy(base), r3_null, False)

    n_pass = sum(1 for r in results if r["self_test_pass"])
    return results, n_pass


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def _load_r2():
    candidates = [
        REV2 / "results" / "gate_f_sc30-54_all_r2challenge_merged.json",
    ]
    p = next((f for f in candidates if f.exists()), None)
    if p is None:
        print(f"ERROR: r2 baseline not found. Tried: {[str(f) for f in candidates]}")
        sys.exit(1)
    with open(p, encoding="utf-8") as fh:
        return json.load(fh), p


def main():
    parser = argparse.ArgumentParser(description="Round-3 R3-0 legacy equivalence check")
    parser.add_argument("--r3-output", help="R3 legacy-mode run output JSON (must cover sc30-sc54)")
    parser.add_argument("--self-test", action="store_true", help="Run negative self-tests and exit")
    args = parser.parse_args()

    print("[Q] Round-3 R3-0 Legacy Equivalence Check (Amendment 3)")
    print(f"    Required: exactly sc30-sc54 ({len(REQUIRED_SCENARIOS)} scenarios, no extras)")
    print(f"    Policies: {EQUIV_POLICIES}   Ratio: {EQUIV_RATIO}   Tol: {TOLERANCE:.0e}")
    print()

    r2_results, r2_path = _load_r2()

    if args.self_test:
        print("[SELF-TEST] Running 10 self-tests against frozen r2 data...")
        test_results, n_pass = run_self_tests(r2_results)
        n_total = len(test_results)
        for tr in test_results:
            status = "PASS" if tr["self_test_pass"] else "FAIL"
            print(f"  [{status}] T{tr['test_id']:02d}: {tr['label']}")
            if not tr["self_test_pass"]:
                print(f"           expect_pass={tr['expect_pass']} actual_pass={tr['actual_pass']}")
                if tr["first_failure"]:
                    print(f"           first_failure: {tr['first_failure'][:100]}")
        print()
        overall = "PASS" if n_pass == n_total else "FAIL"
        print(f"[{overall}] Self-tests: {n_pass}/{n_total}")
        out = OUT_DIR / "equivalence_checker_selftest.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({
                "script": "artifacts/revision3/check_r3_legacy_equivalence.py",
                "amendment": "3",
                "r2_source": str(r2_path.relative_to(ROOT)),
                "n_tests": n_total,
                "n_passed": n_pass,
                "overall_self_test_pass": n_pass == n_total,
                "tests": test_results,
            }, fh, indent=2)
        print(f"    Written: {out}")
        sys.exit(0 if n_pass == n_total else 1)

    if not args.r3_output:
        print("    No --r3-output provided.")
        print("    Run R3-0: Round-3 legacy-mode runner on all sc30-sc54 scenarios.")
        print("    STOP: Do not run corrected-mode simulations until this check passes.")
        stub = {
            "script": "artifacts/revision3/check_r3_legacy_equivalence.py",
            "plan_ref": "artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §Q",
            "amendment": "3",
            "post_exposure_label": POST_EXPOSURE_LABEL,
            "status": "PENDING — no r3-output file provided",
            "tolerance": TOLERANCE,
            "required_scenarios": sorted(REQUIRED_SCENARIOS),
            "equiv_policies": EQUIV_POLICIES,
            "equiv_ratio": EQUIV_RATIO,
            "subset_equivalence_note": "Missing OR extra scenarios both cause immediate hard failure.",
            "stop_condition": (
                "Do not run corrected-mode policy simulations until: "
                "(1) D support audit complete and reviewed; (2) F2 per-cabinet thresholds generated; "
                "(3) this equivalence check passes on exactly sc30-sc54; (4) plan committed."
            ),
        }
        out = OUT_DIR / "check_r3_legacy_equivalence_stub.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump(stub, fh, indent=2)
        print(f"    Written stub: {out}")
        return

    with open(args.r3_output, encoding="utf-8") as fh:
        r3_results = json.load(fh)

    result = check_equivalence(r2_results, r3_results)

    output = {
        "script": "artifacts/revision3/check_r3_legacy_equivalence.py",
        "plan_ref": "artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §Q",
        "amendment": "3",
        "post_exposure_label": POST_EXPOSURE_LABEL,
        "r2_source": str(r2_path.relative_to(ROOT)),
        "r3_source": args.r3_output,
        **result,
    }

    out_path = OUT_DIR / "check_r3_legacy_equivalence_result.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    if result.get("hard_failure"):
        print(f"[HARD FAIL] {result.get('reason', 'hard failure')}")
        for e in result.get("set_errors", result.get("failures", []))[:5]:
            print(f"  {e}")
        print("STOP: Fix scenario set before proceeding.")
        sys.exit(2)
    elif result["pass"]:
        print(f"[PASS] {result['n_checks_passed']} checks passed across "
              f"{result['n_required_scenarios']} scenarios, tol={TOLERANCE:.0e}")
        print("       R3-0 legacy mode matches revision2 challenge. Proceed with corrected mode.")
    else:
        print(f"[FAIL] {result['n_failures']} failures")
        for f in result["failures"][:5]:
            print(f"  {f}")
        print("STOP: Do not proceed until equivalence is established.")
        sys.exit(1)

    print(f"[DONE] Result written: {out_path}")


if __name__ == "__main__":
    main()
