#!/usr/bin/env python3
"""
C8 Original-Reference PGH Mechanism Diagnostic Analysis

Computes 4 comparisons at r=1.25 under the F1 original cabinet reference:
  1. FP vs PGH (F1 ref)           — main new comparison
  2. PGH vs Random (F1 ref)       — structural signal under original reference
  3. FPSpread vs PGH (F1 ref)     — spreading vs structural comparator
  4. PGH vs PositionTemplate (F1) — comparator-to-comparator difference

Then produces a reference-vs-comparator decomposition table combining C8
results with E2 (F1 reference, PositionTemplate) and C7 (F2 reference, PGH).

Verdict rule (identical to C7):
  delta_lo = C_lower(A) - C_upper(B)
  delta_hi = C_upper(A) - C_lower(B)
  A  iff delta_lo > 0
  B  iff delta_hi < 0
  I  otherwise (straddle, right-censored, zero boundary)

No Holm-Bonferroni. No Wilcoxon. Descriptive bootstrap 95% CI.

Usage:
    python artifacts/manuscript_completion/analysis/c8_analysis.py

Environment:
    C8_FILE  — path to merged C8 output (default: auto-detect)
    E2_FILE  — path to E2 merged raw (for decomposition table)
"""
import sys, json, math, os
from pathlib import Path

import numpy as np

REPO_ROOT  = Path(__file__).resolve().parents[3]
C8_OUT_DIR = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"
E2_OUT_DIR = REPO_ROOT / "artifacts" / "revision2" / "results"
C7_OUT_DIR = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

BOOT_SEED   = 9999
BOOT_DRAWS  = 5000
CHECK_RATIO = "1.25"

# C7 accepted values (from FINAL_SCIENTIFIC_FREEZE.md)
_C7_FP_VS_PGH_CANONICAL = {
    "A/I/B": "24/1/0", "med_lo": 7.265, "ci_lo": 5.120, "ci_hi": 12.497,
    "reference": "F2_corrected_concurrent_load",
}
_C7_PGH_VS_RANDOM_CANONICAL = {
    "A/I/B": "21/4/0", "med_lo": 4.582, "ci_lo": 2.901, "ci_hi": 8.224,
    "reference": "F2_corrected_concurrent_load",
}
_E2_FP_VS_PT = {
    "A/I/B": "16/5/4", "med_lo": 0.741,
    "reference": "F1_original_job_contribution_p99",
}


def _find(directory, pattern):
    hits = sorted(directory.glob(pattern))
    return [h for h in hits if "_checkpoint" not in h.name]


c8_path = os.environ.get("C8_FILE", "")
c8_file = (Path(c8_path) if c8_path
           else (lambda h: h[-1] if h else None)(_find(C8_OUT_DIR, "gate_f_sc30-54_*_c8f1diagnostic.json")))
if c8_file is None:
    print("ERROR: No c8f1diagnostic file found.")
    sys.exit(1)

e2_path = os.environ.get("E2_FILE", "")
e2_file = (Path(e2_path) if e2_path
           else (lambda h: h[-1] if h else None)(_find(E2_OUT_DIR, "gate_f_sc30-54_*_r2challenge_merged.json")))

print("C8 Mechanism Diagnostic Analysis")
print("=" * 65)
print(f"  C8 file: {c8_file.name}")
if e2_file:
    print(f"  E2 file: {e2_file.name}")
print(f"  Ratio: r={CHECK_RATIO}")
print()

c8_data = json.loads(c8_file.read_text(encoding="utf-8"))
e2_data = json.loads(e2_file.read_text(encoding="utf-8")) if e2_file else None


def _get_crossing(data, sc_i, ratio, policy):
    for sc in data["scenario_results"]:
        if sc["scenario_idx"] == sc_i:
            return sc.get("ratios", {}).get(ratio, {}).get(policy, {}).get("crossing")
    return None


def _verdict(cx_a, cx_b):
    """Compute delta_lo, delta_hi, verdict from two crossing dicts."""
    if cx_a is None or cx_b is None:
        return None, None, "I"
    C_lo_A = cx_a.get("C_lower_pct")
    C_up_A = cx_a.get("C_upper_pct")
    C_lo_B = cx_b.get("C_lower_pct")
    C_up_B = cx_b.get("C_upper_pct")

    if C_up_B is None:
        delta_lo = float("nan")
    else:
        delta_lo = (C_lo_A or 0.0) - C_up_B

    if C_up_A is None or C_lo_B is None:
        delta_hi = float("nan")
    else:
        delta_hi = C_up_A - (C_lo_B or 0.0)

    if C_up_B is None:
        verdict = "I"
    elif delta_lo > 0:
        verdict = "A"
    elif not math.isnan(delta_hi) and delta_hi < 0:
        verdict = "B"
    else:
        verdict = "I"

    return delta_lo, delta_hi, verdict


def analyze_comparison(label, pol_a, pol_b, source_data, ratio=CHECK_RATIO):
    """Compute verdict table for pol_a vs pol_b at the given ratio."""
    delta_lo_vals = []
    delta_hi_vals = []
    verdicts      = []
    n_left_a = 0; n_left_b = 0
    n_right_a = 0; n_right_b = 0

    for sc_i in range(30, 55):
        cx_a = _get_crossing(source_data, sc_i, ratio, pol_a)
        cx_b = _get_crossing(source_data, sc_i, ratio, pol_b)
        dl, dh, v = _verdict(cx_a, cx_b)
        delta_lo_vals.append(dl)
        delta_hi_vals.append(dh)
        verdicts.append(v)

        if cx_a and cx_a.get("status") == "left_boundary":   n_left_a += 1
        if cx_b and cx_b.get("status") == "left_boundary":   n_left_b += 1
        if cx_a and cx_a.get("status") == "right_censored":  n_right_a += 1
        if cx_b and cx_b.get("status") == "right_censored":  n_right_b += 1

    n_A = verdicts.count("A")
    n_I = verdicts.count("I")
    n_B = verdicts.count("B")

    finite_lo = [v for v in delta_lo_vals if v is not None and not math.isnan(v)]
    finite_hi = [v for v in delta_hi_vals if v is not None and not math.isnan(v)]

    med_lo = float(np.median(finite_lo)) if finite_lo else float("nan")
    med_hi = float(np.median(finite_hi)) if finite_hi else float("nan")

    rng = np.random.default_rng(BOOT_SEED)
    boot_lo = [float(np.median(rng.choice(finite_lo, size=len(finite_lo), replace=True)))
               for _ in range(BOOT_DRAWS)] if finite_lo else []
    boot_lo_sorted = sorted(boot_lo)
    ci_lo = (boot_lo_sorted[int(0.025 * BOOT_DRAWS)],
             boot_lo_sorted[int(0.975 * BOOT_DRAWS)]) if boot_lo_sorted else (float("nan"), float("nan"))

    result = {
        "comparison"  : label,
        "pol_a"       : pol_a,
        "pol_b"       : pol_b,
        "ratio"       : ratio,
        "n_A"         : n_A, "n_I": n_I, "n_B": n_B,
        "med_delta_lo": round(med_lo, 4) if not math.isnan(med_lo) else None,
        "med_delta_hi": round(med_hi, 4) if not math.isnan(med_hi) else None,
        "ci_95_lo"    : [round(ci_lo[0], 4), round(ci_lo[1], 4)] if not math.isnan(ci_lo[0]) else None,
        "n_left_boundary_a": n_left_a, "n_left_boundary_b": n_left_b,
        "n_right_censored_a": n_right_a, "n_right_censored_b": n_right_b,
        "verdicts_by_scenario": dict(zip(range(30, 55), verdicts)),
    }
    return result


# ── Run 4 comparisons ─────────────────────────────────────────────────────────
comparisons = [
    ("FP_vs_PGH_F1",            "full_fp",          "position_group_hash"),
    ("PGH_vs_Random_F1",        "position_group_hash", "full_random"),
    ("FPSpread_vs_PGH_F1",      "full_fp_spread",    "position_group_hash"),
    ("PGH_vs_PositionTemplate_F1", "position_group_hash", "position_template"),
]

results = {}
for label, pol_a, pol_b in comparisons:
    r = analyze_comparison(label, pol_a, pol_b, c8_data)
    results[label] = r
    print(f"{label}")
    print(f"  {r['n_A']}/{r['n_I']}/{r['n_B']}  med_lo={r['med_delta_lo']} pp  "
          f"CI={r['ci_95_lo']}  med_hi={r['med_delta_hi']} pp")
    print(f"  left_boundary: {pol_a}={r['n_left_boundary_a']}, {pol_b}={r['n_left_boundary_b']}")
    print()

# ── E2 FP vs PositionTemplate (from E2 data if available) ─────────────────────
e2_fp_vs_pt = None
if e2_data is not None:
    r_e2 = analyze_comparison("FP_vs_PT_E2", "full_fp", "position_template", e2_data)
    e2_fp_vs_pt = r_e2
    print(f"E2 FP_vs_PositionTemplate (F1 ref, from E2 data):")
    print(f"  {r_e2['n_A']}/{r_e2['n_I']}/{r_e2['n_B']}  med_lo={r_e2['med_delta_lo']} pp  CI={r_e2['ci_95_lo']}")
    print()

# ── C8 FP vs PositionTemplate (from C8 data — should reproduce E2) ───────────
r_c8_fp_pt = analyze_comparison("FP_vs_PT_C8", "full_fp", "position_template", c8_data)
print(f"C8 FP_vs_PositionTemplate (F1 ref, from C8 data — should match E2):")
print(f"  {r_c8_fp_pt['n_A']}/{r_c8_fp_pt['n_I']}/{r_c8_fp_pt['n_B']}  "
      f"med_lo={r_c8_fp_pt['med_delta_lo']} pp  CI={r_c8_fp_pt['ci_95_lo']}")
print()

# ── Reference-vs-comparator decomposition table ───────────────────────────────
print("=" * 65)
print("REFERENCE VS COMPARATOR DECOMPOSITION TABLE")
print("=" * 65)
print()
print(f"{'Comparison':<35} {'Ref':<6} {'A/I/B':<10} {'med_lo (pp)':<14} {'95% CI'}")
print("-" * 90)

rows_table = [
    ("FP vs PositionTemplate (E2)",
     "F1",
     f"{_E2_FP_VS_PT['A/I/B']}",
     f"+{_E2_FP_VS_PT['med_lo']:.3f}",
     "n/a"),

    ("FP vs PositionTemplate (C8)",
     "F1",
     f"{r_c8_fp_pt['n_A']}/{r_c8_fp_pt['n_I']}/{r_c8_fp_pt['n_B']}",
     f"+{r_c8_fp_pt['med_delta_lo']:.3f}" if r_c8_fp_pt['med_delta_lo'] is not None else "n/a",
     str(r_c8_fp_pt['ci_95_lo']) if r_c8_fp_pt['ci_95_lo'] else "n/a"),

    ("FP vs PGH (C8)",
     "F1",
     f"{results['FP_vs_PGH_F1']['n_A']}/{results['FP_vs_PGH_F1']['n_I']}/{results['FP_vs_PGH_F1']['n_B']}",
     f"+{results['FP_vs_PGH_F1']['med_delta_lo']:.3f}" if results['FP_vs_PGH_F1']['med_delta_lo'] is not None else "n/a",
     str(results['FP_vs_PGH_F1']['ci_95_lo']) if results['FP_vs_PGH_F1']['ci_95_lo'] else "n/a"),

    ("FP vs PGH (C7)",
     "F2",
     _C7_FP_VS_PGH_CANONICAL['A/I/B'],
     f"+{_C7_FP_VS_PGH_CANONICAL['med_lo']:.3f}",
     f"[+{_C7_FP_VS_PGH_CANONICAL['ci_lo']:.3f}, +{_C7_FP_VS_PGH_CANONICAL['ci_hi']:.3f}]"),

    ("PGH vs Random (C8)",
     "F1",
     f"{results['PGH_vs_Random_F1']['n_A']}/{results['PGH_vs_Random_F1']['n_I']}/{results['PGH_vs_Random_F1']['n_B']}",
     f"+{results['PGH_vs_Random_F1']['med_delta_lo']:.3f}" if results['PGH_vs_Random_F1']['med_delta_lo'] is not None else "n/a",
     str(results['PGH_vs_Random_F1']['ci_95_lo']) if results['PGH_vs_Random_F1']['ci_95_lo'] else "n/a"),

    ("PGH vs Random (C7)",
     "F2",
     _C7_PGH_VS_RANDOM_CANONICAL['A/I/B'],
     f"+{_C7_PGH_VS_RANDOM_CANONICAL['med_lo']:.3f}",
     f"[+{_C7_PGH_VS_RANDOM_CANONICAL['ci_lo']:.3f}, +{_C7_PGH_VS_RANDOM_CANONICAL['ci_hi']:.3f}]"),
]

for name, ref, aib, med, ci in rows_table:
    print(f"{name:<35} {ref:<6} {aib:<10} {med:<14} {ci}")

print()
print("Decomposition interpretation:")
print("  Comparator change (F1 fixed): FP vs PT -> FP vs PGH = C8 row 3 - C8 row 1")
print("  Reference change (PGH fixed): F1 -> F2  = C7 FP/PGH - C8 FP/PGH")
print()
c8_fp_pgh   = results['FP_vs_PGH_F1']['med_delta_lo'] or 0.0
c8_fp_pt    = r_c8_fp_pt['med_delta_lo'] or 0.0
c7_fp_pgh   = _C7_FP_VS_PGH_CANONICAL['med_lo']
if not math.isnan(c8_fp_pgh):
    comp_effect = c8_fp_pgh - c8_fp_pt
    ref_effect  = c7_fp_pgh - c8_fp_pgh
    print(f"  Comparator change effect (F1): +{comp_effect:.3f} pp  "
          f"({c8_fp_pt:.3f} -> {c8_fp_pgh:.3f})")
    print(f"  Reference change effect (PGH): +{ref_effect:.3f} pp  "
          f"({c8_fp_pgh:.3f} -> {c7_fp_pgh:.3f})")
    print(f"  Total accounted:               +{comp_effect + ref_effect:.3f} pp "
          f"(vs naive endpoint diff {c7_fp_pgh - c8_fp_pt:.3f} pp)")

# ── Save output ───────────────────────────────────────────────────────────────
out = {
    "script"     : "artifacts/manuscript_completion/analysis/c8_analysis.py",
    "c8_file"    : c8_file.name,
    "e2_file"    : e2_file.name if e2_file else None,
    "ratio"      : CHECK_RATIO,
    "comparisons": results,
    "fp_vs_pt_from_c8": r_c8_fp_pt,
    "fp_vs_pt_from_e2": e2_fp_vs_pt,
    "c7_reference_values": {
        "FP_vs_PGH_canonical"  : _C7_FP_VS_PGH_CANONICAL,
        "PGH_vs_Random_canonical": _C7_PGH_VS_RANDOM_CANONICAL,
    },
    "e2_reference_values": {
        "FP_vs_PT_E2": _E2_FP_VS_PT,
    },
    "decomposition": {
        "comparator_change_effect_pp": round(c8_fp_pgh - c8_fp_pt, 4) if not math.isnan(c8_fp_pgh) else None,
        "reference_change_effect_pp" : round(c7_fp_pgh - c8_fp_pgh, 4) if not math.isnan(c8_fp_pgh) else None,
    },
}

out_file = C8_OUT_DIR / "c8f1diagnostic_analysis.json"
out_file.write_text(json.dumps(out, indent=2), encoding="utf-8")
print(f"\nSaved: {out_file.name}")
