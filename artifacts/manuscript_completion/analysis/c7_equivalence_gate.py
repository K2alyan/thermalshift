#!/usr/bin/env python3
"""
Full-field equivalence gate: verify that C7 full_fp, full_random,
fp_withincab_placebo results match the accepted C2 run completely.

Checks (per ROUND7_AMENDMENT.md §Correction-4):
  Per lambda row (tolerance ≤1e-9 for floats, exact for ints/strings):
    lambda_val, capacity_unlock_pct, B_primary_h, S_primary_Cdoth,
    B_secondary_h, B_cab_ratio, syn_node_hours, n_syn_admit,
    n_drop_cap, n_drop_physical, n_drop_la, n_base_unserved,
    mean_F_syn, cab_span_median, all full_selector/exposed_selector/
    realized_selector_choice_mult percentile fields,
    B_primary_ratio, S_primary_ratio, infeasible, first_binding,
    cabinet_accounting (if present in both)

  Per scenario:
    scen_seed, wl_seed (exact), B_ref_s, S_ref_s (≤1e-9)

  Per crossing:
    status, first_binding_constraint, right_censored (exact),
    C_lower_pct, C_upper_pct (≤1e-9)

Any difference in any pre-existing scientific field → FAIL + STOP.

Usage:
    python artifacts/manuscript_completion/analysis/c7_equivalence_gate.py

Environment:
    C7_PRIMARY_FILE  — path to C7 file (default: auto-detect c7primary)
    C2_ACCEPTED_FILE — path to C2 accepted file (default: auto-detect c2manuscript P95)
"""
import sys, json, os, math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

FLOAT_TOL    = 1e-9
CHECK_RATIO  = "1.25"
CHECK_POLICIES = ["full_fp", "full_random", "fp_withincab_placebo"]

# Float fields in lambda_rows (≤1e-9)
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
# Integer/boolean/string fields in lambda_rows (exact)
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
# Crossing fields
FLOAT_CROSSING_FIELDS = ["C_lower_pct", "C_upper_pct"]
EXACT_CROSSING_FIELDS = ["status", "first_binding_constraint", "right_censored"]
# Scenario-level fields
FLOAT_SCEN_FIELDS = ["B_ref_s", "S_ref_s"]
EXACT_SCEN_FIELDS = ["scen_seed", "wl_seed"]


def _find(pattern):
    hits = sorted(OUT_DIR.glob(pattern))
    return [h for h in hits if "_checkpoint" not in h.name]


# ── Load files ────────────────────────────────────────────────────────────────
c7_path = os.environ.get("C7_PRIMARY_FILE", "")
c7_file = Path(c7_path) if c7_path else (lambda h: h[-1] if h else None)(_find("gate_f_sc*_c7primary.json"))
if c7_file is None:
    print("ERROR: No c7primary file found. Run c7_launch_parallel.py + c7_merge.py first.")
    sys.exit(1)

c2_path = os.environ.get("C2_ACCEPTED_FILE", "")
c2_file = Path(c2_path) if c2_path else (lambda h: h[-1] if h else None)(_find("gate_f_sc30-54_*_c2manuscript.json"))
if c2_file is None:
    print("ERROR: No c2manuscript file found.")
    sys.exit(1)

print("C7 Full-Field Equivalence Gate")
print("=" * 65)
print(f"  C7 file: {c7_file.name}")
print(f"  C2 file: {c2_file.name}")
print(f"  Ratio:   r={CHECK_RATIO}")
print(f"  Policies: {CHECK_POLICIES}")
print(f"  Float tolerance: {FLOAT_TOL}")
print()

c7_data = json.loads(c7_file.read_text(encoding="utf-8"))
c2_data = json.loads(c2_file.read_text(encoding="utf-8"))

failures = []
n_float_checks = 0
n_exact_checks = 0


def _fcmp(label, v7, v2, tol=FLOAT_TOL):
    """Float comparison with None handling. Returns True if OK."""
    global n_float_checks
    n_float_checks += 1
    if v7 is None and v2 is None:
        return True
    if v7 is None or v2 is None:
        failures.append(f"{label}: None mismatch  C7={v7}  C2={v2}")
        return False
    if math.isnan(float(v7)) and math.isnan(float(v2)):
        return True
    if math.isnan(float(v7)) or math.isnan(float(v2)):
        failures.append(f"{label}: NaN mismatch  C7={v7}  C2={v2}")
        return False
    diff = abs(float(v7) - float(v2))
    if diff > tol:
        failures.append(f"{label}: diff={diff:.3e}  C7={v7}  C2={v2}")
        return False
    return True


def _ecmp(label, v7, v2):
    """Exact comparison. Returns True if OK."""
    global n_exact_checks
    n_exact_checks += 1
    if v7 != v2:
        failures.append(f"{label}: C7={v7!r}  C2={v2!r}")
        return False
    return True


# Build per-scenario lookup
def _build_idx(data):
    idx = {}
    for sc in data["scenario_results"]:
        si = sc["scenario_idx"]
        idx[si] = sc
    return idx

c7_idx = _build_idx(c7_data)
c2_idx = _build_idx(c2_data)

for sc_i in range(30, 55):
    sc7 = c7_idx.get(sc_i)
    sc2 = c2_idx.get(sc_i)
    if sc7 is None:
        failures.append(f"sc{sc_i}: missing from C7"); continue
    if sc2 is None:
        failures.append(f"sc{sc_i}: missing from C2"); continue

    pfx = f"sc{sc_i}"

    # ── Scenario-level fields ─────────────────────────────────────────────────
    for f in EXACT_SCEN_FIELDS:
        _ecmp(f"{pfx}.{f}", sc7.get(f), sc2.get(f))
    for f in FLOAT_SCEN_FIELDS:
        _fcmp(f"{pfx}.{f}", sc7.get(f), sc2.get(f))

    r7 = sc7.get("ratios", {}).get(CHECK_RATIO, {})
    r2 = sc2.get("ratios", {}).get(CHECK_RATIO, {})

    for pol in CHECK_POLICIES:
        pd7 = r7.get(pol, {})
        pd2 = r2.get(pol, {})
        ppfx = f"{pfx}.r={CHECK_RATIO}.{pol}"

        if not pd7:
            failures.append(f"{ppfx}: missing from C7"); continue
        if not pd2:
            failures.append(f"{ppfx}: missing from C2"); continue

        # ── Lambda rows ───────────────────────────────────────────────────────
        rows7 = pd7.get("lambda_rows", [])
        rows2 = pd2.get("lambda_rows", [])

        if len(rows7) != len(rows2):
            failures.append(f"{ppfx}: lambda_row count C7={len(rows7)} C2={len(rows2)}")
        else:
            for ri, (r7row, r2row) in enumerate(zip(rows7, rows2)):
                rpfx = f"{ppfx}.row{ri}"
                for f in FLOAT_LAMBDA_FIELDS:
                    _fcmp(f"{rpfx}.{f}", r7row.get(f), r2row.get(f))
                for f in EXACT_LAMBDA_FIELDS:
                    _ecmp(f"{rpfx}.{f}", r7row.get(f), r2row.get(f))

                # Cabinet accounting (if present in both)
                ca7 = r7row.get("cabinet_accounting")
                ca2 = r2row.get("cabinet_accounting")
                if ca7 is not None and ca2 is not None:
                    nh7 = ca7.get("node_hours", {})
                    nh2 = ca2.get("node_hours", {})
                    all_cabs = set(nh7.keys()) | set(nh2.keys())
                    for cab in sorted(all_cabs):
                        _fcmp(f"{rpfx}.cab_nh[{cab}]",
                              nh7.get(cab), nh2.get(cab))
                    ev7 = ca7.get("event_touches", {})
                    ev2 = ca2.get("event_touches", {})
                    all_cabs_ev = set(ev7.keys()) | set(ev2.keys())
                    for cab in sorted(all_cabs_ev):
                        _ecmp(f"{rpfx}.cab_ev[{cab}]",
                              ev7.get(cab), ev2.get(cab))

        # ── Crossing ──────────────────────────────────────────────────────────
        cx7 = pd7.get("crossing", {})
        cx2 = pd2.get("crossing", {})
        for f in EXACT_CROSSING_FIELDS:
            _ecmp(f"{ppfx}.crossing.{f}", cx7.get(f), cx2.get(f))
        for f in FLOAT_CROSSING_FIELDS:
            _fcmp(f"{ppfx}.crossing.{f}", cx7.get(f), cx2.get(f))

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
    print("DO NOT PROCEED to sc31-sc54. Investigate seed chain or data mismatch.")
    sys.exit(1)
else:
    print("EQUIVALENCE GATE: PASS")
    print(f"  All {total_checks} pre-existing scientific fields match C2 within tolerance")
    print(f"  C7 pol_seed chain reproduces full_fp, full_random, fp_withincab_placebo")
    print()
    print("Authorized to proceed to sc31-sc54.")
