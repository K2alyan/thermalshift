#!/usr/bin/env python3
"""
Crossing-estimator tests for Gate F v3 capacity-ordered rule.

Tests verify:
1. Normal exact-bracket: monotone capacity, crossing at expected point.
2. Left-boundary: all evaluated points are infeasible.
3. Right-censored: all evaluated points are feasible.
4. Non-monotone capacity: simulation noise makes capacity_unlock_pct
   non-monotone with lambda. v3 rule (sort by capacity, not lambda)
   must find the correct bracket without inversion.
5. Inversion reproduction and correction: exactly reproduces the
   sc4/r=8/fp_spread inversion pattern (lam=1.1407 FEASIBLE cap=11.037%
   after lam=1.1414 INFEASIBLE cap=11.033%) and confirms v3 gives
   C_lower <= C_upper.
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

# Import classify_crossing from run script
import importlib.util, types

def _load_classify_crossing():
    import ast, numpy as np_mod
    src = (Path(__file__).resolve().parent / "r1_gate_f_run.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    func_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "classify_crossing":
            func_src = ast.get_source_segment(src, node)
            break
    if func_src is None:
        raise RuntimeError("classify_crossing not found in r1_gate_f_run.py")
    ns = {"np": np_mod}
    exec(func_src, ns)
    return ns["classify_crossing"]

classify_crossing = _load_classify_crossing()

B_REF  = 100.0   # arbitrary reference values
S_REF  = 100.0
B_CAB_REF = None  # cabinet check disabled for unit tests

def _make_row(lam, capacity_pct, infeasible, binding="B_ratio"):
    """Construct a synthetic lambda row for crossing estimation tests."""
    B_primary_h = B_REF * (1.05 if infeasible else 0.95)
    return {
        "lambda_val"         : lam,
        "capacity_unlock_pct": capacity_pct,
        "B_primary_h"        : B_primary_h,
        "S_primary_Cdoth"    : S_REF * (1.05 if infeasible else 0.95),
        "B_cab_ratio"        : 1.01 if infeasible else 0.99,
        "n_base_unserved"    : 0,
        "invariant_violated" : False,
        "infeasible"         : infeasible,
        "first_binding"      : binding if infeasible else None,
    }


def run_test(name, fn):
    try:
        fn()
        print(f"  PASS  {name}")
        return True
    except AssertionError as e:
        print(f"  FAIL  {name}: {e}")
        return False
    except Exception as e:
        print(f"  ERROR {name}: {type(e).__name__}: {e}")
        return False


# ── Test C1: Normal exact bracket (monotone) ─────────────────────────────────
def test_c1_normal_exact_bracket():
    rows = [
        _make_row(1.0, 0.0,  False),
        _make_row(1.1, 5.0,  False),
        _make_row(1.2, 10.0, False),
        _make_row(1.3, 15.0, True),
        _make_row(1.4, 20.0, True),
    ]
    cx = classify_crossing(rows, B_REF, S_REF, B_CAB_REF)
    assert cx["status"] == "exact_bracket", f"Expected exact_bracket, got {cx['status']}"
    assert abs(cx["C_lower_pct"] - 10.0) < 1e-9, f"C_lower={cx['C_lower_pct']}"
    assert abs(cx["C_upper_pct"] - 15.0) < 1e-9, f"C_upper={cx['C_upper_pct']}"
    assert cx["C_lower_pct"] <= cx["C_upper_pct"], "Inversion in normal case"


# ── Test C2: Left boundary (first evaluated point is infeasible) ──────────────
def test_c2_left_boundary():
    rows = [
        _make_row(1.0, 5.0,  True),
        _make_row(1.1, 10.0, True),
    ]
    cx = classify_crossing(rows, B_REF, S_REF, B_CAB_REF)
    assert cx["status"] == "left_boundary", f"Expected left_boundary, got {cx['status']}"
    assert cx["C_lower_pct"] == 0.0, f"C_lower={cx['C_lower_pct']}"
    assert cx["right_censored"] is False


# ── Test C3: Right-censored (all feasible) ────────────────────────────────────
def test_c3_right_censored():
    rows = [
        _make_row(1.0, 5.0,  False),
        _make_row(1.5, 20.0, False),
        _make_row(2.0, 40.0, False),
    ]
    cx = classify_crossing(rows, B_REF, S_REF, B_CAB_REF)
    assert cx["status"] == "right_censored", f"Expected right_censored, got {cx['status']}"
    assert cx["right_censored"] is True
    assert cx["C_upper_pct"] is None


# ── Test C4: Non-monotone capacity (lambda order != capacity order) ───────────
def test_c4_nonmonotone_capacity():
    # capacity_unlock_pct is NOT monotone with lambda.
    # In lambda order: [0, 5, 12, 8, 18] → first infeasible in lambda order is idx 3 (cap=8)
    # In capacity order: [0, 5, 8, 12, 18] → first infeasible is cap=8, last feasible is cap=5
    # v3 rule (capacity order) gives: C_lower=5.0, C_upper=8.0
    # Lambda-order rule would give: last_feasible=cap=12 (idx 2), first_infeasible=cap=8 (idx 3)
    #   which is INVERTED (C_lower=12 > C_upper=8).
    rows = [
        _make_row(1.00, 0.0,  False),
        _make_row(1.10, 5.0,  False),
        _make_row(1.20, 12.0, False),   # feasible at cap=12
        _make_row(1.30, 8.0,  True),    # infeasible at cap=8 (capacity regression)
        _make_row(1.40, 18.0, True),
    ]
    cx = classify_crossing(rows, B_REF, S_REF, B_CAB_REF)
    assert cx["status"] == "exact_bracket", f"Expected exact_bracket, got {cx['status']}"
    # v3 capacity-ordered: C_lower=5.0 (last feasible before first infeasible in cap order)
    assert abs(cx["C_lower_pct"] - 5.0) < 1e-9, (
        f"v3 should give C_lower=5.0 (last feasible in cap order), got {cx['C_lower_pct']}"
    )
    assert abs(cx["C_upper_pct"] - 8.0) < 1e-9, (
        f"v3 should give C_upper=8.0 (first infeasible in cap order), got {cx['C_upper_pct']}"
    )
    assert cx["C_lower_pct"] <= cx["C_upper_pct"], (
        f"Inversion: C_lower={cx['C_lower_pct']} > C_upper={cx['C_upper_pct']}"
    )


# ── Test C5: sc4/r=8/fp_spread inversion pattern ────────────────────────────
def test_c5_inversion_pattern_sc4_r8_fp_spread():
    # Reproduces the exact inversion pattern found in sc4/r=8.0/full_fp_spread:
    # lam=1.1407, cap=11.037%, B_cab=0.999931 → FEASIBLE
    # lam=1.1414, cap=11.033%, B_cab=1.000014 → INFEASIBLE
    # Lambda-order rule (bug): last_feasible=cap=11.037, first_infeasible=cap=11.033
    #   → C_lower=11.037 > C_upper=11.033 (INVERTED)
    # v3 capacity-order rule (fix): sort by cap → [11.033, 11.037] in cap order
    #   first infeasible = cap=11.033, but last feasible before it = ???
    #   (depends on what's below 11.033 in capacity order)
    # Let's include earlier feasible rows to see correct C_lower
    rows = [
        # Earlier lambda evaluations (feasible, lower capacity)
        _make_row(1.00, 0.0,   False),
        _make_row(1.10, 8.0,   False),
        _make_row(1.1407, 11.037, False),  # FEASIBLE but at high cap (due to noise)
        _make_row(1.1414, 11.033, True),   # INFEASIBLE at slightly lower cap
        _make_row(1.50, 20.0,  True),
    ]
    # v3: sort by capacity: [0.0 F, 8.0 F, 11.033 INF, 11.037 F(ignored), 20.0 INF]
    # Scan: 0→F (last_feasible=0), 8→F (last_feasible=8), 11.033→INF → bracket [8, 11.033]
    # Note: 11.037 F comes after 11.033 INF in capacity order but v3 stops at first INF
    cx = classify_crossing(rows, B_REF, S_REF, B_CAB_REF)
    assert cx["status"] == "exact_bracket", f"Expected exact_bracket, got {cx['status']}"
    assert cx["C_lower_pct"] <= cx["C_upper_pct"], (
        f"Inversion: C_lower={cx['C_lower_pct']:.6f} > C_upper={cx['C_upper_pct']:.6f}"
    )
    # C_upper must be 11.033 (first infeasible in capacity order)
    assert abs(cx["C_upper_pct"] - 11.033) < 1e-9, (
        f"C_upper should be 11.033, got {cx['C_upper_pct']}"
    )
    # C_lower must be the last feasible BEFORE 11.033 in capacity order = 8.0
    assert abs(cx["C_lower_pct"] - 8.0) < 1e-9, (
        f"C_lower should be 8.0 (last feasible before 11.033 in cap order), "
        f"got {cx['C_lower_pct']}"
    )


# ── Test C6: All infeasible rows after a feasible cluster (multi-crossing) ───
def test_c6_monotone_with_large_gap():
    rows = [
        _make_row(1.0, 2.0,  False),
        _make_row(1.1, 4.0,  False),
        _make_row(1.2, 6.0,  False),
        _make_row(1.3, 100.0, True),  # large jump
        _make_row(1.4, 120.0, True),
    ]
    cx = classify_crossing(rows, B_REF, S_REF, B_CAB_REF)
    assert cx["status"] == "exact_bracket"
    assert abs(cx["C_lower_pct"] - 6.0)   < 1e-9
    assert abs(cx["C_upper_pct"] - 100.0) < 1e-9
    assert cx["C_lower_pct"] <= cx["C_upper_pct"]


# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 62)
    print("Gate F Crossing-Estimator Tests (v3 capacity-ordered rule)")
    print("=" * 62)

    tests = [
        ("C1 — Normal exact bracket (monotone)",              test_c1_normal_exact_bracket),
        ("C2 — Left boundary (all infeasible)",               test_c2_left_boundary),
        ("C3 — Right-censored (all feasible)",                test_c3_right_censored),
        ("C4 — Non-monotone capacity (v3 vs lambda-order)",   test_c4_nonmonotone_capacity),
        ("C5 — sc4/r=8/fp_spread inversion pattern",         test_c5_inversion_pattern_sc4_r8_fp_spread),
        ("C6 — Large capacity gap, exact bracket",            test_c6_monotone_with_large_gap),
    ]

    results = [run_test(name, fn) for name, fn in tests]
    n_pass  = sum(results)
    n_fail  = len(results) - n_pass
    print()
    print(f"{'='*62}")
    if n_fail == 0:
        print(f"ALL {n_pass}/{len(results)} TESTS PASSED")
    else:
        print(f"{n_pass}/{len(results)} passed — {n_fail} FAILED")
    print(f"{'='*62}")
    if n_fail:
        sys.exit(1)
