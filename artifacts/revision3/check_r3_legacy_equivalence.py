"""
Round-3 Task Q — Legacy-Mode Equivalence Check (Amendment 2 corrected).

Verifies that the Round-3 legacy-mode runner (using F1 cabinet reference,
identical to r2_gate_f_run.py) produces results matching the frozen sc30-sc54
revision2 challenge results, before any Round-3-specific scenarios are run.

R3-0 replays sc30-sc54 (the exact 25 revision2 held-out scenarios) in legacy
mode. Partial scenario sets are an immediate hard failure — all 25 must be
present. Only full_fp and full_random policies are checked (the two policy
types needed for the primary FP_vs_Random comparison).

Tolerance: 1e-9 numeric for all capacity and crossing values.

Plan ref: artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §Q (v2.1)
Amendment: 2 — corrected R3-0 design (sc30-54, not sc55)
Post-exposure label: designed after sc30-sc54 primary results observed.

USAGE:
  python check_r3_legacy_equivalence.py --r3-output <path_to_r3_legacy_run.json>

The r3-output file must be the result of running the Round-3 legacy-mode
runner on ALL sc30-sc54 scenarios using the frozen revision2 seeds.
"""
import argparse
import json
import pathlib
import sys

ROOT    = pathlib.Path(__file__).parent.parent.parent
REV2    = ROOT / "artifacts" / "revision2"
OUT_DIR = ROOT / "artifacts" / "revision3"

TOLERANCE = 1e-9
REQUIRED_SCENARIOS = set(range(30, 55))   # exact sc30-sc54; partial sets fail immediately
EQUIV_POLICIES = ["full_fp", "full_random"]
EQUIV_RATIO = "1.25"

LAMBDA_ROW_FIELDS = [
    "lambda_val",
    "capacity_unlock_pct",
    "B_primary_h",
    "S_primary_Cdoth",
    "B_secondary_h",
    "B_cab_ratio",
    "syn_node_hours",
    "n_syn_admit",
    "n_drop_cap",
    "n_drop_physical",
    "n_drop_la",
    "n_base_unserved",
]

CROSSING_FIELDS = [
    "status",
    "C_lower_pct",
    "C_upper_pct",
    "first_binding_constraint",
    "right_censored",
]

SCENARIO_FIELDS = [
    "scenario_idx",
    "scenario_array_i",
    "scen_seed",
    "wl_seed",
    "B_ref_s",
    "S_ref_s",
]

POST_EXPOSURE_LABEL = (
    "Post-exposure: designed after sc30-sc54 primary results observed. "
    "Equivalence check verifies Round-3 legacy mode matches revision2 challenge "
    "on all 25 sc30-sc54 scenarios."
)


def _check_numeric(v2, v3, label, failures, checks_passed_ref):
    if v2 is None and v3 is None:
        return checks_passed_ref
    if v2 is None or v3 is None:
        failures.append(f"{label}: one is None ({v2} vs {v3})")
        return checks_passed_ref
    try:
        diff = abs(float(v2) - float(v3))
    except (TypeError, ValueError):
        if v2 != v3:
            failures.append(f"{label}: non-numeric mismatch ({v2!r} vs {v3!r})")
        else:
            checks_passed_ref += 1
        return checks_passed_ref
    if diff > TOLERANCE:
        failures.append(f"{label}: |{v2} - {v3}| = {diff:.2e} > tol={TOLERANCE:.0e}")
    else:
        checks_passed_ref += 1
    return checks_passed_ref


def _check_categorical(v2, v3, label, failures, checks_passed_ref):
    if v2 != v3:
        failures.append(f"{label}: mismatch ({v2!r} vs {v3!r})")
    else:
        checks_passed_ref += 1
    return checks_passed_ref


def check_equivalence(r2_results: dict, r3_results: dict):
    """Compare r2 and r3 results on all REQUIRED_SCENARIOS for EQUIV_POLICIES at EQUIV_RATIO."""
    failures = []
    checks_passed = 0

    def key(s):
        return s.get("scenario_index", s.get("scenario_idx"))

    r2_map = {key(s): s for s in r2_results.get("scenario_results", [])}
    r3_map = {key(s): s for s in r3_results.get("scenario_results", [])}

    # Hard failure: partial scenario set
    r3_present = set(r3_map.keys()) & REQUIRED_SCENARIOS
    missing = REQUIRED_SCENARIOS - r3_present
    if missing:
        return {
            "pass": False,
            "hard_failure": True,
            "reason": f"Partial scenario set: missing {sorted(missing)}. "
                      "All sc30-sc54 required. Subset equivalence never passes.",
            "n_present": len(r3_present),
            "n_required": len(REQUIRED_SCENARIOS),
            "n_failures": 1,
            "failures": [f"Missing scenarios: {sorted(missing)}"],
        }

    r2_missing = REQUIRED_SCENARIOS - set(r2_map.keys())
    if r2_missing:
        return {
            "pass": False,
            "hard_failure": True,
            "reason": f"r2 baseline missing scenarios: {sorted(r2_missing)}",
            "n_failures": 1,
            "failures": [f"r2 missing: {sorted(r2_missing)}"],
        }

    for sc_idx in sorted(REQUIRED_SCENARIOS):
        r2_sc = r2_map[sc_idx]
        r3_sc = r3_map[sc_idx]

        # Scenario-level fields
        for field in SCENARIO_FIELDS:
            v2 = r2_sc.get(field)
            v3 = r3_sc.get(field)
            label = f"sc{sc_idx} scenario.{field}"
            checks_passed = _check_numeric(v2, v3, label, failures, checks_passed)

        ratio_data_r2 = r2_sc.get("ratios", {})
        ratio_data_r3 = r3_sc.get("ratios", {})

        if EQUIV_RATIO not in ratio_data_r2:
            failures.append(f"sc{sc_idx}: r2 missing ratio {EQUIV_RATIO}")
            continue
        if EQUIV_RATIO not in ratio_data_r3:
            failures.append(f"sc{sc_idx}: r3 missing ratio {EQUIV_RATIO}")
            continue

        pol_r2 = ratio_data_r2[EQUIV_RATIO]
        pol_r3 = ratio_data_r3[EQUIV_RATIO]

        for policy in EQUIV_POLICIES:
            if policy not in pol_r2:
                failures.append(f"sc{sc_idx} r={EQUIV_RATIO}: r2 missing policy {policy}")
                continue
            if policy not in pol_r3:
                failures.append(f"sc{sc_idx} r={EQUIV_RATIO}: r3 missing policy {policy}")
                continue

            pd2 = pol_r2[policy]
            pd3 = pol_r3[policy]

            rows_r2 = pd2.get("lambda_rows", [])
            rows_r3 = pd3.get("lambda_rows", [])
            if len(rows_r2) != len(rows_r3):
                failures.append(
                    f"sc{sc_idx} r={EQUIV_RATIO} {policy}: lambda_rows length mismatch "
                    f"({len(rows_r2)} vs {len(rows_r3)})"
                )
            else:
                for i, (row2, row3) in enumerate(zip(rows_r2, rows_r3)):
                    for field in LAMBDA_ROW_FIELDS:
                        label = f"sc{sc_idx} r={EQUIV_RATIO} {policy} row{i} {field}"
                        checks_passed = _check_numeric(
                            row2.get(field), row3.get(field), label, failures, checks_passed
                        )

            # Crossing fields
            cross2 = pd2.get("crossing", {})
            cross3 = pd3.get("crossing", {})
            for field in CROSSING_FIELDS:
                label = f"sc{sc_idx} r={EQUIV_RATIO} {policy} crossing.{field}"
                v2, v3 = cross2.get(field), cross3.get(field)
                if field in ("status", "first_binding_constraint"):
                    checks_passed = _check_categorical(v2, v3, label, failures, checks_passed)
                elif field == "right_censored":
                    checks_passed = _check_categorical(v2, v3, label, failures, checks_passed)
                else:
                    checks_passed = _check_numeric(v2, v3, label, failures, checks_passed)

    return {
        "pass": len(failures) == 0,
        "hard_failure": False,
        "tolerance": TOLERANCE,
        "n_required_scenarios": len(REQUIRED_SCENARIOS),
        "n_policies_checked": len(EQUIV_POLICIES),
        "ratio_checked": EQUIV_RATIO,
        "n_numeric_checks_passed": checks_passed,
        "n_failures": len(failures),
        "failures": failures[:30],
    }


def main():
    parser = argparse.ArgumentParser(description="Round-3 R3-0 legacy equivalence check")
    parser.add_argument("--r3-output", required=False,
                        help="Path to Round-3 legacy-mode run output JSON (must cover sc30-sc54)")
    args = parser.parse_args()

    print("[Q] Round-3 R3-0 Legacy Equivalence Check (Amendment 2 corrected)")
    print(f"    {POST_EXPOSURE_LABEL}")
    print(f"    Required: all sc30-sc54 ({len(REQUIRED_SCENARIOS)} scenarios); "
          f"policies: {EQUIV_POLICIES}; ratio: {EQUIV_RATIO}; tol: {TOLERANCE:.0e}")

    if not args.r3_output:
        print()
        print("    No --r3-output provided.")
        print("    Run R3-0: Round-3 legacy-mode runner on sc30-sc54 (all 25 scenarios).")
        print("    Use frozen revision2 seeds. Pass the output file to this script.")
        print()
        print("    STOP: Do not run corrected-mode simulations until this check passes.")
        stub = {
            "script": "artifacts/revision3/check_r3_legacy_equivalence.py",
            "plan_ref": "artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §Q",
            "amendment": "2",
            "post_exposure_label": POST_EXPOSURE_LABEL,
            "status": "PENDING — no r3-output file provided",
            "tolerance": TOLERANCE,
            "required_scenarios": sorted(REQUIRED_SCENARIOS),
            "equiv_policies": EQUIV_POLICIES,
            "equiv_ratio": EQUIV_RATIO,
            "stop_condition": (
                "Do not run corrected-mode policy simulations until: "
                "(1) D support audit complete; (2) F reference definitions frozen; "
                "(3) this equivalence check passes on all sc30-sc54; (4) plan committed."
            ),
            "subset_equivalence_note": (
                "Subset equivalence never passes. All 25 sc30-sc54 scenarios must be present "
                "in the R3-0 output file. Missing scenarios cause an immediate hard failure."
            ),
        }
        out_path = OUT_DIR / "check_r3_legacy_equivalence_stub.json"
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(stub, fh, indent=2)
        print(f"    Written stub: {out_path}")
        return

    # Locate r2 baseline: prefer the merged all-scenario file
    r2_candidates = [
        REV2 / "results" / "gate_f_sc30-54_all_r2challenge_merged.json",
        REV2 / "challenge_analysis.json",
    ]
    r2_file = next((p for p in r2_candidates if p.exists()), None)
    if r2_file is None:
        print(f"    ERROR: Cannot find r2 baseline. Tried: {[str(p) for p in r2_candidates]}")
        sys.exit(1)

    with open(r2_file, encoding="utf-8") as fh:
        r2_results = json.load(fh)

    with open(args.r3_output, encoding="utf-8") as fh:
        r3_results = json.load(fh)

    result = check_equivalence(r2_results, r3_results)

    output = {
        "script": "artifacts/revision3/check_r3_legacy_equivalence.py",
        "plan_ref": "artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §Q",
        "amendment": "2",
        "post_exposure_label": POST_EXPOSURE_LABEL,
        "r2_source": str(r2_file.relative_to(ROOT)),
        "r3_source": args.r3_output,
        **result,
    }

    out_path = OUT_DIR / "check_r3_legacy_equivalence_result.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)

    if result.get("hard_failure"):
        print(f"\n[HARD FAIL] {result['reason']}")
        print("            STOP: Subset equivalence never passes. Run all sc30-sc54.")
        sys.exit(2)
    elif result["pass"]:
        print(f"\n[PASS] Equivalence check passed: {result['n_numeric_checks_passed']} checks, "
              f"{result['n_required_scenarios']} scenarios, tol={TOLERANCE:.0e}")
        print("       R3-0 legacy mode matches revision2 challenge. Proceed with corrected mode.")
    else:
        print(f"\n[FAIL] Equivalence check FAILED: {result['n_failures']} failures")
        for f in result["failures"][:5]:
            print(f"       {f}")
        print("       STOP: Do not proceed with Round-3 until equivalence is established.")
        sys.exit(1)

    print(f"\n[DONE] Result written: {out_path}")


if __name__ == "__main__":
    main()
