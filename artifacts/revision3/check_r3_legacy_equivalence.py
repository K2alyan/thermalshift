"""
Round-3 Task Q — Legacy-Mode Equivalence Check.

Verifies that the Round-3 legacy-mode runner (using F1 cabinet reference,
identical to r2_gate_f_run.py) produces results matching sc30-sc54 on
shared scenarios, before any Round-3-specific scenarios are run.

Tolerance: 1e-9 numeric for all capacity values.

Plan ref: artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §Q
Post-exposure label: designed after sc30-sc54 primary results observed.

USAGE:
  python check_r3_legacy_equivalence.py --r3-output <path_to_r3_legacy_run.json>

The r3-output file must be the result of running the Round-3 legacy-mode
runner on sc30-sc54 scenarios (same seeds as challenge_seed_index_audit.json).
"""
import argparse
import json
import pathlib
import sys

ROOT    = pathlib.Path(__file__).parent.parent.parent
REV2    = ROOT / "artifacts" / "revision2"
OUT_DIR = ROOT / "artifacts" / "revision3"

TOLERANCE = 1e-9

POST_EXPOSURE_LABEL = (
    "Post-exposure: designed after sc30-sc54 primary results observed. "
    "Equivalence check verifies Round-3 legacy mode matches revision2 challenge."
)


def check_equivalence(r2_results: dict, r3_results: dict, tol: float = TOLERANCE):
    """Compare r2 and r3 results on shared scenarios."""
    failures = []
    checks_passed = 0

    r2_scenarios = {s.get("scenario_index", s.get("scenario_idx")): s
                    for s in r2_results.get("scenario_results", [])}
    r3_scenarios = {s.get("scenario_index", s.get("scenario_idx")): s
                    for s in r3_results.get("scenario_results", [])}

    shared = sorted(set(r2_scenarios.keys()) & set(r3_scenarios.keys()))
    if not shared:
        return {"pass": False, "failures": ["No shared scenario indices found"],
                "n_shared": 0, "n_checked": 0}

    for sc_idx in shared:
        r2_sc = r2_scenarios[sc_idx]
        r3_sc = r3_scenarios[sc_idx]
        for ratio, r2_ratio_data in r2_sc.get("ratios", {}).items():
            r3_ratio_data = r3_sc.get("ratios", {}).get(ratio, {})
            for policy, r2_pol_data in r2_ratio_data.items():
                r3_pol_data = r3_ratio_data.get(policy, {})
                rows_r2 = r2_pol_data.get("lambda_rows", [])
                rows_r3 = r3_pol_data.get("lambda_rows", [])
                if len(rows_r2) != len(rows_r3):
                    failures.append(
                        f"sc{sc_idx} r={ratio} {policy}: lambda_rows length mismatch "
                        f"({len(rows_r2)} vs {len(rows_r3)})"
                    )
                    continue
                for i, (row2, row3) in enumerate(zip(rows_r2, rows_r3)):
                    for field in ["capacity_unlock_pct", "B_primary_h", "S_primary_Cdoth",
                                  "B_cab_ratio"]:
                        v2 = row2.get(field)
                        v3 = row3.get(field)
                        if v2 is None and v3 is None:
                            continue
                        if v2 is None or v3 is None:
                            failures.append(
                                f"sc{sc_idx} r={ratio} {policy} row{i} {field}: "
                                f"one is None ({v2} vs {v3})"
                            )
                            continue
                        if abs(v2 - v3) > tol:
                            failures.append(
                                f"sc{sc_idx} r={ratio} {policy} row{i} {field}: "
                                f"|{v2} - {v3}| = {abs(v2-v3):.2e} > tol={tol:.0e}"
                            )
                        else:
                            checks_passed += 1

    return {
        "pass": len(failures) == 0,
        "tolerance": tol,
        "n_shared_scenarios": len(shared),
        "n_numeric_checks_passed": checks_passed,
        "n_failures": len(failures),
        "failures": failures[:20]  # cap for readability
    }


def main():
    parser = argparse.ArgumentParser(description="Round-3 legacy equivalence check")
    parser.add_argument("--r3-output", required=False,
                        help="Path to Round-3 legacy-mode run output JSON")
    args = parser.parse_args()

    print("[Q] Round-3 Legacy Equivalence Check")
    print(f"    {POST_EXPOSURE_LABEL}")

    if not args.r3_output:
        print()
        print("    No --r3-output provided. This check requires a Round-3 legacy-mode run.")
        print("    Run the Round-3 runner in legacy mode on sc30-sc54 scenarios,")
        print("    then pass the output file to this script.")
        print()
        print("    STOP: Do not run corrected-mode simulations until this check passes.")
        stub = {
            "script": "artifacts/revision3/check_r3_legacy_equivalence.py",
            "plan_ref": "artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §Q",
            "post_exposure_label": POST_EXPOSURE_LABEL,
            "status": "PENDING — no r3-output file provided",
            "tolerance": TOLERANCE,
            "stop_condition": (
                "Do not run corrected-mode policy simulations until: "
                "(1) D support audit complete; (2) F reference definitions frozen; "
                "(3) this equivalence check passes; (4) plan committed."
            )
        }
        out_path = OUT_DIR / "check_r3_legacy_equivalence_stub.json"
        with open(out_path, "w") as fh:
            json.dump(stub, fh, indent=2)
        print(f"    Written stub: {out_path}")
        return

    # Load r2 challenge run results for sc30-sc54
    r2_file = REV2 / "results" / "gate_f_sc30-54_1p25_r2sensitivity_sc1p00_bprimary.json"
    if not r2_file.exists():
        # Try challenge run log
        r2_file = REV2 / "results" / "challenge_run_log_4w.json"
    if not r2_file.exists():
        print(f"    ERROR: Cannot find r2 baseline results. Checked: {r2_file}")
        sys.exit(1)

    with open(r2_file) as fh:
        r2_results = json.load(fh)

    with open(args.r3_output) as fh:
        r3_results = json.load(fh)

    result = check_equivalence(r2_results, r3_results)

    output = {
        "script": "artifacts/revision3/check_r3_legacy_equivalence.py",
        "plan_ref": "artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §Q",
        "post_exposure_label": POST_EXPOSURE_LABEL,
        "r2_source": str(r2_file.relative_to(ROOT)),
        "r3_source": args.r3_output,
        **result
    }

    out_path = OUT_DIR / "check_r3_legacy_equivalence_result.json"
    with open(out_path, "w") as fh:
        json.dump(output, fh, indent=2)

    if result["pass"]:
        print(f"\n[PASS] Equivalence check passed: {result['n_numeric_checks_passed']} checks, "
              f"{result['n_shared_scenarios']} shared scenarios, tol={TOLERANCE:.0e}")
        print("       Round-3 legacy mode matches revision2 challenge. Proceed with corrected mode.")
    else:
        print(f"\n[FAIL] Equivalence check FAILED: {result['n_failures']} failures")
        for f in result["failures"][:5]:
            print(f"       {f}")
        print("       STOP: Do not proceed with Round-3 until equivalence is established.")
        sys.exit(1)

    print(f"\n[DONE] Result written: {out_path}")


if __name__ == "__main__":
    main()
