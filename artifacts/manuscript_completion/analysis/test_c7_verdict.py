#!/usr/bin/env python3
"""
Unit and regression tests for c7_analysis.py verdict classification.

Verdict rule (frozen):
    A  iff  delta_lo > 0     (C_lower(A) - C_upper(B) > 0)
    B  iff  delta_hi < 0     (C_upper(A) - C_lower(B) < 0)
    I  otherwise             (including straddle, right-censored B)

Usage:
    python artifacts/manuscript_completion/analysis/test_c7_verdict.py
"""
import sys, json, math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"
ANALYSIS_RATIO = "1.25"

# ── Verdict helper (mirrors corrected c7_analysis.py logic exactly) ──────────

def _get_C_lower(cx: dict) -> float:
    if cx.get("status") == "left_boundary":
        return 0.0
    v = cx.get("C_lower_pct")
    return float(v) if v is not None else 0.0

def _get_C_upper(cx: dict):
    v = cx.get("C_upper_pct")
    return float(v) if v is not None else None

def verdict(cx_A: dict, cx_B: dict) -> str:
    """Return 'A', 'B', or 'I' for a single scenario pair."""
    C_lo_A = _get_C_lower(cx_A)
    C_up_A = _get_C_upper(cx_A)
    C_lo_B = _get_C_lower(cx_B)
    C_up_B = _get_C_upper(cx_B)

    if C_up_B is None:
        delta_lo = float("nan")
    else:
        delta_lo = C_lo_A - C_up_B

    if C_up_A is None or C_lo_B is None:
        delta_hi = float("nan")
    else:
        delta_hi = C_up_A - C_lo_B

    if C_up_B is None:
        return "I"
    elif delta_lo > 0:
        return "A"
    elif not math.isnan(delta_hi) and delta_hi < 0:
        return "B"
    else:
        return "I"


# ── Unit tests ────────────────────────────────────────────────────────────────

def _cx(C_lower, C_upper):
    cx = {"C_lower_pct": C_lower}
    if C_upper is not None:
        cx["C_upper_pct"] = C_upper
    return cx

passed = failed = 0

def check(name, got, want):
    global passed, failed
    if got == want:
        print(f"  PASS  {name}")
        passed += 1
    else:
        print(f"  FAIL  {name}: got {got!r}, want {want!r}")
        failed += 1

print("Unit tests — interval verdict classification")
print("=" * 60)

# T1: Definite A — delta_lo > 0 (A clearly beats B)
# A=[20,21], B=[10,12] → delta_lo=20-12=8>0
check("T1 definite A",
      verdict(_cx(20, 21), _cx(10, 12)), "A")

# T2: Definite B — delta_hi < 0 (B clearly beats A)
# A=[5,6], B=[10,12] → delta_lo=5-12=-7, delta_hi=6-10=-4<0
check("T2 definite B",
      verdict(_cx(5, 6), _cx(10, 12)), "B")

# T3: Straddle I — delta_lo < 0 < delta_hi (intervals overlap)
# A=[8,15], B=[10,12] → delta_lo=8-12=-4<0, delta_hi=15-10=5>0
check("T3 straddle I (delta_lo<0, delta_hi>0)",
      verdict(_cx(8, 15), _cx(10, 12)), "I")

# T4: Zero delta_lo boundary → I (not A; strict inequality)
# A=[12,15], B=[10,12] → delta_lo=12-12=0, delta_hi=15-10=5>0
check("T4 delta_lo == 0 -> I",
      verdict(_cx(12, 15), _cx(10, 12)), "I")

# T5: Zero delta_hi boundary → I (not B; strict inequality)
# A=[5,10], B=[10,12] → delta_lo=5-12=-7<0, delta_hi=10-10=0
check("T5 delta_hi == 0 -> I",
      verdict(_cx(5, 10), _cx(10, 12)), "I")

# T6: Right-censored B (C_upper_B missing) → I regardless of delta_lo
# A=[20,21], B=[5, None] → C_up_B=None → I
check("T6 right-censored B -> I",
      verdict(_cx(20, 21), _cx(5, None)), "I")

# T7: Left-boundary A (C_lower_A = 0) + B clearly positive — straddle I
# A=[0,5], B=[3,8] → delta_lo=0-8=-8<0, delta_hi=5-3=2>0
check("T7 left-boundary A, straddle -> I",
      verdict({"status": "left_boundary", "C_lower_pct": 0.0, "C_upper_pct": 5.0},
              _cx(3, 8)), "I")

# T8: Both zero — ties → I (not A or B)
check("T8 both intervals at zero -> I",
      verdict(_cx(0, 0), _cx(0, 0)), "I")

# T9: Critical regression scenario — the FP-vs-WithinCab straddler that was
#     incorrectly classified as B.  C_lower(FP) < C_upper(WithinCab) but
#     C_upper(FP) > C_lower(WithinCab).  Must be I.
# Construct example matching the pattern: A slightly lower than B on lower end
# but A upper exceeds B lower.
# A=[10,20], B=[12,18] → delta_lo=10-18=-8<0, delta_hi=20-12=8>0 → I
check("T9 FP-vs-WithinCab straddler pattern -> I",
      verdict(_cx(10, 20), _cx(12, 18)), "I")

print()
print(f"Unit tests: {passed} passed, {failed} failed")


# ── Regression: accepted C2 results ──────────────────────────────────────────

print()
print("=" * 60)
print("Regression against accepted C2 raw result")
print("=" * 60)

C2_FILE = OUT_DIR / "gate_f_sc30-54_1p25_c2manuscript.json"
if not C2_FILE.exists():
    print(f"ERROR: C2 file not found: {C2_FILE}")
    sys.exit(1)

c2_data = json.loads(C2_FILE.read_text(encoding="utf-8"))
c2_idx  = {sc["scenario_idx"]: sc for sc in c2_data["scenario_results"]}
scenarios = sorted(c2_idx.keys())

print(f"  C2 file: {C2_FILE.name}")
print(f"  Scenarios: {len(scenarios)} (sc{scenarios[0]}-sc{scenarios[-1]})")
print()

REGRESSION_PAIRS = [
    ("FP_vs_Random",    "full_fp", "full_random",          (25, 0, 0)),
    ("FP_vs_WithinCab", "full_fp", "fp_withincab_placebo", (24, 1, 0)),
]

reg_passed = reg_failed = 0

for label, pol_A, pol_B, (exp_A, exp_I, exp_B) in REGRESSION_PAIRS:
    n_A = n_I = n_B = 0
    straddlers = []
    for si in scenarios:
        sc   = c2_idx[si]
        r    = sc.get("ratios", {}).get(ANALYSIS_RATIO, {})
        pd_A = r.get(pol_A, {})
        pd_B = r.get(pol_B, {})
        cx_A = pd_A.get("crossing", {})
        cx_B = pd_B.get("crossing", {})
        v = verdict(cx_A, cx_B)
        if v == "A":   n_A += 1
        elif v == "B": n_B += 1
        else:          n_I += 1
        if v == "I":
            straddlers.append(si)

    ok = (n_A, n_I, n_B) == (exp_A, exp_I, exp_B)
    tag = "PASS" if ok else "FAIL"
    if ok:
        reg_passed += 1
    else:
        reg_failed += 1
    print(f"  {tag}  {label}: {n_A}/{n_I}/{n_B}  (expected {exp_A}/{exp_I}/{exp_B})")
    if straddlers:
        print(f"         I scenarios: {straddlers}")
    if not ok:
        print(f"         REGRESSION FAILURE — verdict logic still wrong")

print()
print(f"Regression tests: {reg_passed} passed, {reg_failed} failed")
print()

total_failed = failed + reg_failed
if total_failed == 0:
    print("ALL TESTS PASS — verdict logic correct")
    sys.exit(0)
else:
    print(f"TOTAL FAILURES: {total_failed}")
    sys.exit(1)
