#!/usr/bin/env python3
"""
Full-field equivalence gate: verify that C8 full_fp, full_random,
full_fp_spread, position_template results match the accepted E2 run
exactly (max_abs_diff <= 1e-9 for floats, exact for ints/strings).

The gate confirms that the C8 seed chain correctly reproduces E2's
pol_seeds for all four shared policies. 0 failures required before
committing the C8 raw output.

Usage:
    python artifacts/manuscript_completion/analysis/c8_equivalence_gate.py

Environment:
    C8_FILE  — path to merged C8 output (default: auto-detect c8f1diagnostic)
    E2_FILE  — path to E2 merged raw (default: auto-detect r2challenge)
"""
import sys, json, os, math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
C8_OUT_DIR = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"
E2_OUT_DIR = REPO_ROOT / "artifacts" / "revision2" / "results"

FLOAT_TOL       = 1e-9
CHECK_RATIO     = "1.25"
CHECK_POLICIES  = ["full_fp", "full_random", "full_fp_spread", "position_template"]

FLOAT_LAMBDA_FIELDS = [
    "lambda_val",
    "capacity_unlock_pct",
    "B_primary_h",
    "S_primary_Cdoth",
    "B_secondary_h",
    "B_cab_ratio",
    "syn_node_hours",
    "mean_F_syn",
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
    "B_primary_ratio",
    "S_primary_ratio",
]
EXACT_LAMBDA_FIELDS = [
    "n_syn_admit",
    "n_drop_cap",
    "n_drop_physical",
    "n_drop_la",
    "n_base_unserved",
    "invariant_violated",
    "infeasible",
    "first_binding",
]
FLOAT_CROSSING_FIELDS = ["C_lower_pct", "C_upper_pct"]
EXACT_CROSSING_FIELDS = ["status", "first_binding_constraint", "right_censored"]
FLOAT_SCEN_FIELDS = ["B_ref_s", "S_ref_s"]
EXACT_SCEN_FIELDS = ["scen_seed", "wl_seed"]


def _find(directory, pattern):
    hits = sorted(directory.glob(pattern))
    return [h for h in hits if "_checkpoint" not in h.name]


c8_path = os.environ.get("C8_FILE", "")
c8_file = (Path(c8_path) if c8_path
           else (lambda h: h[-1] if h else None)(_find(C8_OUT_DIR, "gate_f_sc30-54_*_c8f1diagnostic.json")))
if c8_file is None:
    print("ERROR: No c8f1diagnostic file found. Run c8_launch_parallel.py + c8_merge.py first.")
    sys.exit(1)

e2_path = os.environ.get("E2_FILE", "")
e2_file = (Path(e2_path) if e2_path
           else (lambda h: h[-1] if h else None)(_find(E2_OUT_DIR, "gate_f_sc30-54_*_r2challenge_merged.json")))
if e2_file is None:
    print("ERROR: No E2 merged file found.")
    print(f"  Expected in: {E2_OUT_DIR}")
    sys.exit(1)

print("C8 Full-Field Equivalence Gate vs E2")
print("=" * 65)
print(f"  C8 file: {c8_file.name}")
print(f"  E2 file: {e2_file.name}")
print(f"  Ratio:   r={CHECK_RATIO}")
print(f"  Policies: {CHECK_POLICIES}")
print(f"  Float tolerance: {FLOAT_TOL}")
print()

c8_data = json.loads(c8_file.read_text(encoding="utf-8"))
e2_data = json.loads(e2_file.read_text(encoding="utf-8"))

failures = []
n_float_checks = 0
n_exact_checks = 0


def _fcmp(label, v8, v2, tol=FLOAT_TOL):
    global n_float_checks
    n_float_checks += 1
    if v8 is None and v2 is None:
        return True
    if v8 is None or v2 is None:
        failures.append(f"{label}: None mismatch  C8={v8}  E2={v2}")
        return False
    if math.isnan(float(v8)) and math.isnan(float(v2)):
        return True
    if math.isnan(float(v8)) or math.isnan(float(v2)):
        failures.append(f"{label}: NaN mismatch  C8={v8}  E2={v2}")
        return False
    diff = abs(float(v8) - float(v2))
    if diff > tol:
        failures.append(f"{label}: diff={diff:.3e}  C8={v8}  E2={v2}")
        return False
    return True


def _ecmp(label, v8, v2):
    global n_exact_checks
    n_exact_checks += 1
    if v8 != v2:
        failures.append(f"{label}: C8={v8!r}  E2={v2!r}")
        return False
    return True


def _build_idx(data):
    idx = {}
    for sc in data["scenario_results"]:
        si = sc["scenario_idx"]
        idx[si] = sc
    return idx


c8_idx = _build_idx(c8_data)
e2_idx = _build_idx(e2_data)

for sc_i in range(30, 55):
    sc8 = c8_idx.get(sc_i)
    sc2 = e2_idx.get(sc_i)
    if sc8 is None:
        failures.append(f"sc{sc_i}: missing from C8"); continue
    if sc2 is None:
        failures.append(f"sc{sc_i}: missing from E2"); continue

    pfx = f"sc{sc_i}"

    for f in EXACT_SCEN_FIELDS:
        _ecmp(f"{pfx}.{f}", sc8.get(f), sc2.get(f))
    for f in FLOAT_SCEN_FIELDS:
        _fcmp(f"{pfx}.{f}", sc8.get(f), sc2.get(f))

    r8 = sc8.get("ratios", {}).get(CHECK_RATIO, {})
    r2 = sc2.get("ratios", {}).get(CHECK_RATIO, {})

    for pol in CHECK_POLICIES:
        pd8 = r8.get(pol, {})
        pd2 = r2.get(pol, {})
        ppfx = f"{pfx}.r={CHECK_RATIO}.{pol}"

        if not pd8:
            failures.append(f"{ppfx}: missing from C8"); continue
        if not pd2:
            failures.append(f"{ppfx}: missing from E2"); continue

        rows8 = pd8.get("lambda_rows", [])
        rows2 = pd2.get("lambda_rows", [])

        # E2 may have more rows (more refinement at some scenarios).
        # Only compare rows where lambda_val matches — C8 must match for every row it has.
        e2_by_lam = {}
        for row in rows2:
            lam_key = round(float(row.get("lambda_val", 0)), 6)
            e2_by_lam[lam_key] = row

        for ri, r8row in enumerate(rows8):
            lam_key = round(float(r8row.get("lambda_val", 0)), 6)
            r2row = e2_by_lam.get(lam_key)
            if r2row is None:
                # C8 has a row at this lambda that E2 doesn't — skip (refinement may differ)
                continue
            rpfx = f"{ppfx}.lam={lam_key}"
            for f in FLOAT_LAMBDA_FIELDS:
                _fcmp(f"{rpfx}.{f}", r8row.get(f), r2row.get(f))
            for f in EXACT_LAMBDA_FIELDS:
                _ecmp(f"{rpfx}.{f}", r8row.get(f), r2row.get(f))

        cx8 = pd8.get("crossing", {})
        cx2 = pd2.get("crossing", {})
        for f in EXACT_CROSSING_FIELDS:
            _ecmp(f"{ppfx}.crossing.{f}", cx8.get(f), cx2.get(f))
        for f in FLOAT_CROSSING_FIELDS:
            _fcmp(f"{ppfx}.crossing.{f}", cx8.get(f), cx2.get(f))

# ── Report ────────────────────────────────────────────────────────────────────
total_checks = n_float_checks + n_exact_checks
print(f"Checked {total_checks} fields "
      f"({n_float_checks} float <={FLOAT_TOL}, {n_exact_checks} exact) "
      f"across {len(CHECK_POLICIES)} policies x 25 scenarios")
print()

if failures:
    print(f"EQUIVALENCE GATE: FAIL  ({len(failures)} failure(s))")
    for i, f in enumerate(failures[:50]):
        print(f"  FAIL: {f}")
    if len(failures) > 50:
        print(f"  ... and {len(failures)-50} more")
    print()
    print("DO NOT COMMIT raw output. Investigate seed chain or reference mismatch.")
    sys.exit(1)
else:
    print("EQUIVALENCE GATE: PASS")
    print(f"  All {total_checks} shared-policy fields match E2 within tolerance")
    print(f"  C8 seed chain reproduces full_fp, full_random, full_fp_spread, position_template")
    print()
    print("Authorized to commit C8 raw output and proceed to analysis.")
