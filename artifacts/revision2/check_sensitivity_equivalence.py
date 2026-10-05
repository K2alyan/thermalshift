#!/usr/bin/env python3
"""
Equivalence check: sensitivity baseline (cab_scale=1.00, primary beta, r=1.25)
versus frozen challenge outputs for full_fp and full_random at r=1.25.

Requirements (per POST_EXPOSURE_SENSITIVITY_RECOVERY.md):
  - Zero mismatches
  - Zero null asymmetries
  - Float difference <= 1e-9 for all numeric crossing fields and lambda_row fields
  - Both policies present for all 25 scenarios

Writes: artifacts/revision2/sensitivity_runner_equivalence.json
If FAIL: prints diff summary and exits with code 1.
"""
import sys, io, json, math, glob
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

REV2     = Path("artifacts/revision2")
RES      = REV2 / "results"
OUT_PATH = REV2 / "sensitivity_runner_equivalence.json"

FLOAT_TOL   = 1e-9
RATIO       = "1.25"
POLICIES    = ["full_random", "full_fp"]
N_SCENARIOS = 25
SC_FIRST    = 30

print("=== Sensitivity Runner Equivalence Check ===")
print(f"Tolerance: {FLOAT_TOL:.0e}")
print(f"Ratio: {RATIO}, Policies: {POLICIES}")
print()

# ── Load frozen challenge outputs (merged) ────────────────────────────────────
challenge_path = RES / "gate_f_sc30-54_all_r2challenge_merged.json"
print(f"Loading frozen challenge: {challenge_path.name}")
challenge = json.loads(challenge_path.read_text())
chall_by_sc = {s["scenario_idx"]: s for s in challenge["scenario_results"]}
print(f"  Scenarios in frozen: {sorted(chall_by_sc.keys())}")
print()

# ── Load sensitivity baseline outputs ─────────────────────────────────────────
# Look for per-scenario or merged sensitivity files with cab_scale=1p00/1.00 and primary beta
# The sensitivity runner writes: gate_f_sc{sc}-{sc}_r2sensitivity_sc1p00_bprimary.json
# or merged: gate_f_sc*_r2sensitivity_sc1p00_bprimary_merged.json
sens_patterns = [
    # Exact expected filename from run: GATE_F_RATIOS_ONLY=1.25, no beta/scale override
    "gate_f_sc30-54_1p25_r2sensitivity_sc1p00_bprimary.json",
    # Wildcard fallback (ratio tag may vary)
    "gate_f_sc*_*_r2sensitivity_sc1p00_bprimary.json",
    "gate_f_sc*_r2sensitivity_sc1p00_bprimary.json",
    "*sensitivity*sc1p00*primary*.json",
]

sens_files = []
for pat in sens_patterns:
    found = sorted(RES.glob(pat))
    if found:
        print(f"Found {len(found)} file(s) matching pattern: {pat}")
        sens_files = found
        break

if not sens_files:
    print("ERROR: No sensitivity baseline output files found.")
    print(f"Expected in: {RES}")
    print("Run the sensitivity baseline first, then re-run this checker.")
    sys.exit(1)

# Collect all scenario results from sensitivity files
sens_by_sc = {}
for fpath in sens_files:
    d = json.loads(fpath.read_text())
    for s in d.get("scenario_results", []):
        idx = s["scenario_idx"]
        if idx not in sens_by_sc:
            sens_by_sc[idx] = s

print(f"Sensitivity scenarios loaded: {sorted(sens_by_sc.keys())}")
print()

# ── Check coverage ────────────────────────────────────────────────────────────
expected_scs = set(range(SC_FIRST, SC_FIRST + N_SCENARIOS))
missing_sens  = expected_scs - set(sens_by_sc.keys())
missing_chall = expected_scs - set(chall_by_sc.keys())

if missing_sens:
    print(f"MISSING from sensitivity baseline: sc{sorted(missing_sens)}")
if missing_chall:
    print(f"MISSING from frozen challenge: sc{sorted(missing_chall)}")

if missing_sens or missing_chall:
    print("\nCoverage FAIL — cannot run equivalence check.")
    result = {
        "status": "FAIL",
        "reason": "missing_scenarios",
        "missing_sens": sorted(missing_sens),
        "missing_chall": sorted(missing_chall),
    }
    OUT_PATH.write_text(json.dumps(result, indent=2))
    sys.exit(1)

print(f"Coverage: OK — all {N_SCENARIOS} scenarios present in both sets")
print()

# ── Compare ───────────────────────────────────────────────────────────────────
def _float_eq(a, b, field):
    """Return (match:bool, diff:float|None)."""
    if a is None and b is None:
        return True, None
    if a is None or b is None:
        return False, None  # null asymmetry
    try:
        fa, fb = float(a), float(b)
    except (TypeError, ValueError):
        return (a == b), None
    diff = abs(fa - fb)
    return diff <= FLOAT_TOL, diff

CROSSING_FIELDS = ["C_lower_pct", "C_upper_pct", "status", "right_censored",
                   "first_binding_constraint"]

n_mismatches    = 0
n_null_asym     = 0
n_row_mismatches = 0
max_diff        = 0.0
diffs = []

for sc_idx in sorted(expected_scs):
    s_chall = chall_by_sc[sc_idx]
    s_sens  = sens_by_sc[sc_idx]

    for pol in POLICIES:
        r_chall = s_chall["ratios"][RATIO][pol]
        r_sens  = s_sens["ratios"][RATIO][pol]

        # ── Crossing fields ───────────────────────────────────────────────
        c_chall = r_chall["crossing"]
        c_sens  = r_sens["crossing"]

        for field in CROSSING_FIELDS:
            vc = c_chall.get(field)
            vs = c_sens.get(field)
            if isinstance(vc, float) or isinstance(vs, float):
                ok, diff = _float_eq(vc, vs, field)
                if diff is not None:
                    max_diff = max(max_diff, diff)
                if not ok:
                    if diff is None:
                        n_null_asym += 1
                        print(f"NULL ASYMMETRY sc{sc_idx} {pol} crossing.{field}: chall={vc!r} sens={vs!r}")
                    else:
                        n_mismatches += 1
                        print(f"MISMATCH sc{sc_idx} {pol} crossing.{field}: chall={vc} sens={vs} diff={diff:.3e}")
                    diffs.append({"sc": sc_idx, "pol": pol, "field": f"crossing.{field}",
                                  "chall": vc, "sens": vs})
            else:
                if vc != vs:
                    n_mismatches += 1
                    print(f"MISMATCH sc{sc_idx} {pol} crossing.{field}: chall={vc!r} sens={vs!r}")
                    diffs.append({"sc": sc_idx, "pol": pol, "field": f"crossing.{field}",
                                  "chall": vc, "sens": vs})

        # ── Lambda rows ───────────────────────────────────────────────────
        lrows_c = r_chall["lambda_rows"]
        lrows_s = r_sens["lambda_rows"]

        if len(lrows_c) != len(lrows_s):
            n_mismatches += 1
            print(f"MISMATCH sc{sc_idx} {pol} lambda_rows len: chall={len(lrows_c)} sens={len(lrows_s)}")
            continue

        for ri, (rc, rs) in enumerate(zip(lrows_c, lrows_s)):
            # Only compare numeric fields; skip policy label (may differ in internal format)
            for field, vc in rc.items():
                if field == "policy":
                    continue
                vs = rs.get(field)
                if isinstance(vc, float) or (isinstance(vs, float)):
                    ok, diff = _float_eq(vc, vs, field)
                    if diff is not None:
                        max_diff = max(max_diff, diff)
                    if not ok:
                        if diff is None:
                            n_null_asym += 1
                        else:
                            n_row_mismatches += 1
                            if n_row_mismatches <= 10:
                                print(f"ROW MISMATCH sc{sc_idx} {pol} row[{ri}].{field}: "
                                      f"diff={diff:.3e}  chall={vc:.12g} sens={vs:.12g}")

print()
print(f"Max float diff across all fields: {max_diff:.3e}")
print(f"Crossing mismatches: {n_mismatches}")
print(f"Null asymmetries:    {n_null_asym}")
print(f"Lambda-row mismatches: {n_row_mismatches}")
print()

overall_pass = (n_mismatches == 0 and n_null_asym == 0 and n_row_mismatches == 0
                and max_diff <= FLOAT_TOL)

status = "PASS" if overall_pass else "FAIL"
print(f"Equivalence: {status}")

result = {
    "script": "artifacts/revision2/check_sensitivity_equivalence.py",
    "plan_ref": "POST_EXPOSURE_SENSITIVITY_RECOVERY.md §Baseline equivalence requirement",
    "status": status,
    "tolerance": FLOAT_TOL,
    "ratio": RATIO,
    "policies_checked": POLICIES,
    "n_scenarios": N_SCENARIOS,
    "frozen_challenge_source": str(challenge_path.name),
    "sensitivity_source_files": [str(f.name) for f in sens_files],
    "n_scenarios_compared": len(expected_scs),
    "crossing_mismatches": n_mismatches,
    "null_asymmetries": n_null_asym,
    "lambda_row_mismatches": n_row_mismatches,
    "max_float_diff": max_diff,
    "mismatch_details": diffs[:20],  # cap at 20 for readability
}

OUT_PATH.write_text(json.dumps(result, indent=2))
print(f"Written: {OUT_PATH}")

if not overall_pass:
    sys.exit(1)
