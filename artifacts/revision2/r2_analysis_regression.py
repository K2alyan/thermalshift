#!/usr/bin/env python3
"""
Analysis regression test (r2_analysis_regression.py)

Applies the r2 analysis engine to frozen sc5-29 Gate F outputs and compares
against gate_f_heldout_analysis.json for the 5 overlapping comparisons.

Plan ref: REVIEW2_CHALLENGE_PLAN.md Amendment 4 §G3.

Usage:
  python r2_analysis_regression.py
"""
import sys, io, json, datetime, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
REV2_DIR  = REPO_ROOT / "artifacts" / "revision2"
OUT_FILE  = REV2_DIR / "r2_analysis_regression.json"

# Overlapping comparisons: (r2_name, pol_A_r1, pol_B_r1, r1_name_in_json)
# r1 uses "full_loc"; r2 uses "position_template" — we feed the r1 data as-is.
REGRESSION_COMPARISONS = [
    ("FP_vs_Random",      "full_fp",         "full_random",    "FP_vs_Random"),
    ("Loc_vs_Random",     "full_loc",        "full_random",    "Loc_vs_Random"),
    ("FPSpread_vs_Random","full_fp_spread",  "full_random",    "FPSpread_vs_Random"),
    ("FPSpread_vs_FP",    "full_fp_spread",  "full_fp",        "FPSpread_vs_FP"),
    ("FPSpread_vs_Loc",   "full_fp_spread",  "full_loc",       "FPSpread_vs_Loc"),
]

ALL_RATIOS = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"]
N_BOOTSTRAP    = 5000
BOOTSTRAP_SEED = 9999

FLOAT_TOL = 1e-9


def _load_r1_heldout() -> list:
    """Merge 3 sc5-29 files into unified scenario_results list."""
    files = {
        "1.0"  : REV1_DIR / "results" / "gate_f_sc5-29_1p0.json",
        "multi": REV1_DIR / "results" / "gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json",
        "unr"  : REV1_DIR / "results" / "gate_f_sc5-29_unr.json",
    }
    merged: dict[int, dict] = {}
    for label, fpath in files.items():
        if not fpath.exists():
            raise FileNotFoundError(f"Missing r1 heldout file: {fpath}")
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
    return [merged[idx] for idx in sorted(merged.keys())]


def main():
    print("=" * 70)
    print("r2 Analysis Regression Test")
    print("Plan ref: REVIEW2_CHALLENGE_PLAN.md Amendment 4 §G3")
    print("=" * 70)

    # Load frozen reference
    ref_file = REV1_DIR / "results" / "gate_f_heldout_analysis.json"
    if not ref_file.exists():
        print(f"ERROR: Reference file missing: {ref_file}")
        sys.exit(1)
    ref = json.loads(ref_file.read_text())
    ref_results = ref.get("results", {})

    # Load r1 heldout data
    print("\nLoading sc5-29 r1 heldout data ...")
    try:
        scenario_results = _load_r1_heldout()
    except FileNotFoundError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)
    n = len(scenario_results)
    print(f"  {n} scenarios loaded: "
          f"{sorted(int(sr['scenario_idx']) for sr in scenario_results)}")

    # Determine which ratios are present in the loaded data
    ratios_present = set()
    for sr in scenario_results:
        ratios_present.update(sr.get("ratios", {}).keys())
    ratios_to_use = [r for r in ALL_RATIOS if r in ratios_present]
    print(f"  Ratios present: {ratios_to_use}")

    # Run analysis engine
    sys.path.insert(0, str(REV2_DIR))
    from r2_gate_f_challenge_analysis import run_analysis

    comps_for_analysis = [(name, polA, polB, "") for name, polA, polB, _ in REGRESSION_COMPARISONS]
    print(f"\nRunning analysis engine ({len(comps_for_analysis)} comparisons, "
          f"{N_BOOTSTRAP} bootstrap reps, seed={BOOTSTRAP_SEED}) ...")
    analysis = run_analysis(
        scenario_results, comps_for_analysis,
        ratios=ratios_to_use,
        n_bootstrap=N_BOOTSTRAP,
        bootstrap_seed=BOOTSTRAP_SEED,
    )

    # Compare against reference
    print("\nComparing against gate_f_heldout_analysis.json ...")
    comparison_results: dict[str, dict] = {}
    all_pass = True
    total_checks = 0
    failed_checks = 0

    for r2_name, polA, polB, r1_name in REGRESSION_COMPARISONS:
        ref_comp = ref_results.get(r1_name, {})
        r2_comp  = analysis["results"].get(r2_name, {})
        comp_ok  = True
        comp_notes = []

        for ratio in ratios_to_use:
            ref_r = ref_comp.get("ratios", {}).get(ratio, {})
            r2_r  = r2_comp.get("ratios", {}).get(ratio, {})

            if not ref_r:
                comp_notes.append(f"  ratio {ratio}: not in reference (skipped)")
                continue

            # Check n, n_A, n_I, n_B
            for field in ("n", "n_definitely_A", "n_indistinguishable", "n_definitely_B"):
                v_ref = ref_r.get(field)
                v_r2  = r2_r.get(field)
                total_checks += 1
                if v_ref != v_r2:
                    comp_ok = False; all_pass = False; failed_checks += 1
                    comp_notes.append(f"  FAIL ratio={ratio} {field}: ref={v_ref} r2={v_r2}")

            # Check verdicts list
            ref_v = ref_r.get("verdicts", [])
            r2_v  = r2_r.get("verdicts", [])
            total_checks += 1
            if ref_v != r2_v:
                comp_ok = False; all_pass = False; failed_checks += 1
                diffs = [(i, rv, r2v) for i, (rv, r2v) in enumerate(zip(ref_v, r2_v))
                         if rv != r2v]
                comp_notes.append(
                    f"  FAIL ratio={ratio} verdicts: {len(diffs)} differ "
                    f"(first: sc_idx={diffs[0][0]} ref={diffs[0][1]} r2={diffs[0][2]})"
                    if diffs else f"  FAIL ratio={ratio} verdicts: length mismatch "
                                  f"(ref={len(ref_v)} r2={len(r2_v)})"
                )

            # Check per-scenario delta_lo and delta_hi values
            ref_dlo = ref_r.get("delta_lo_per_scenario", [])
            r2_dlo  = r2_r.get("delta_lo_per_scenario", [])
            ref_dhi = ref_r.get("delta_hi_per_scenario", [])
            r2_dhi  = r2_r.get("delta_hi_per_scenario", [])

            for field_name, r_list, r2_list in [
                ("delta_lo_per_scenario", ref_dlo, r2_dlo),
                ("delta_hi_per_scenario", ref_dhi, r2_dhi),
            ]:
                total_checks += 1
                if len(r_list) != len(r2_list):
                    comp_ok = False; all_pass = False; failed_checks += 1
                    comp_notes.append(
                        f"  FAIL ratio={ratio} {field_name}: length mismatch "
                        f"ref={len(r_list)} r2={len(r2_list)}"
                    )
                    continue
                max_diff = 0.0
                for rv, r2v in zip(r_list, r2_list):
                    if rv is None and r2v is None:
                        continue
                    if rv is None or r2v is None:
                        max_diff = float("inf")
                        break
                    max_diff = max(max_diff, abs(float(rv) - float(r2v)))
                if max_diff > FLOAT_TOL:
                    comp_ok = False; all_pass = False; failed_checks += 1
                    comp_notes.append(
                        f"  FAIL ratio={ratio} {field_name}: max_diff={max_diff:.2e} > {FLOAT_TOL}"
                    )

            # Check median deltas
            for field_name in ("median_delta_lo", "median_delta_hi"):
                v_ref = ref_r.get(field_name)
                v_r2  = r2_r.get(field_name)
                total_checks += 1
                if v_ref is None and v_r2 is None:
                    continue
                if v_ref is None or v_r2 is None:
                    comp_ok = False; all_pass = False; failed_checks += 1
                    comp_notes.append(f"  FAIL ratio={ratio} {field_name}: ref={v_ref} r2={v_r2}")
                elif abs(float(v_ref) - float(v_r2)) > FLOAT_TOL:
                    comp_ok = False; all_pass = False; failed_checks += 1
                    comp_notes.append(
                        f"  FAIL ratio={ratio} {field_name}: diff={abs(float(v_ref)-float(v_r2)):.2e}"
                    )

        status = "PASS" if comp_ok else "FAIL"
        print(f"  [{status}] {r2_name} ({r1_name})")
        for note in comp_notes:
            print(f"        {note}")

        comparison_results[r2_name] = {
            "r1_name"   : r1_name,
            "policy_A"  : polA,
            "policy_B"  : polB,
            "pass"      : comp_ok,
            "notes"     : comp_notes,
        }

    print(f"\n── Summary ──")
    print(f"  Total checks: {total_checks}  Passed: {total_checks - failed_checks}  Failed: {failed_checks}")
    print(f"  Overall: {'PASS' if all_pass else 'FAIL'}")

    result = {
        "script"      : "artifacts/revision2/r2_analysis_regression.py",
        "plan_ref"    : "REVIEW2_CHALLENGE_PLAN.md Amendment 4 §G3",
        "run_at"      : datetime.datetime.utcnow().isoformat() + "Z",
        "reference"   : "artifacts/revision1/results/gate_f_heldout_analysis.json",
        "n_scenarios" : n,
        "n_comparisons": len(REGRESSION_COMPARISONS),
        "n_bootstrap" : N_BOOTSTRAP,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "float_tolerance": FLOAT_TOL,
        "total_checks": total_checks,
        "failed_checks": failed_checks,
        "comparisons" : comparison_results,
        "overall_pass": all_pass,
    }
    OUT_FILE.write_text(json.dumps(result, indent=2))
    print(f"\nWritten: {OUT_FILE}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
