#!/usr/bin/env python3
"""
Equivalence gate: verify that C7 full_fp, full_random, fp_withincab_placebo
results at r=1.25 match the accepted C2 run within tolerance 1e-9 pp.

Checks per scenario (sc30-sc54):
  - crossing.C_lower_pct
  - crossing.C_upper_pct
  - crossing.status

Usage:
    python artifacts/manuscript_completion/analysis/c7_equivalence_gate.py

Environment:
    C7_PRIMARY_FILE  — path to merged C7 JSON (default: auto-detect c7primary)
    C2_ACCEPTED_FILE — path to C2 accepted JSON (default: auto-detect c2manuscript P95)
"""
import sys, json, os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

TOLERANCE   = 1e-9    # pp; crossing values should be bit-for-bit identical
CHECK_RATIO = "1.25"
CHECK_POLICIES = ["full_fp", "full_random", "fp_withincab_placebo"]

def _find(pattern):
    hits = sorted(OUT_DIR.glob(pattern))
    hits = [h for h in hits if "_checkpoint" not in h.name]
    return hits

# ── Load C7 primary ───────────────────────────────────────────────────────────
c7_path = os.environ.get("C7_PRIMARY_FILE", "")
if c7_path:
    c7_file = Path(c7_path)
else:
    c7_hits = _find("gate_f_sc30-54_*_c7primary.json")
    if not c7_hits:
        print("ERROR: No c7primary merged file found in results/.")
        print("       Run c7_merge.py --suffix c7primary first.")
        sys.exit(1)
    c7_file = c7_hits[-1]

# ── Load C2 accepted ──────────────────────────────────────────────────────────
c2_path = os.environ.get("C2_ACCEPTED_FILE", "")
if c2_path:
    c2_file = Path(c2_path)
else:
    c2_hits = _find("gate_f_sc30-54_*_c2manuscript.json")
    if not c2_hits:
        print("ERROR: No c2manuscript file found in results/.")
        sys.exit(1)
    c2_file = c2_hits[-1]

print("C7 Equivalence Gate")
print("=" * 60)
print(f"  C7 file: {c7_file.name}")
print(f"  C2 file: {c2_file.name}")
print(f"  Ratio:   r={CHECK_RATIO}")
print(f"  Policies: {CHECK_POLICIES}")
print(f"  Tolerance: {TOLERANCE} pp")
print()

c7_data = json.loads(c7_file.read_text(encoding="utf-8"))
c2_data = json.loads(c2_file.read_text(encoding="utf-8"))

# Build lookup: scenario_idx -> ratio -> policy -> crossing
def _build_idx(data):
    idx = {}
    for sc in data["scenario_results"]:
        si = sc["scenario_idx"]
        ratios = sc.get("ratios", {})
        idx[si] = {}
        for rl, pol_dict in ratios.items():
            idx[si][rl] = {}
            for pol, pdata in pol_dict.items():
                idx[si][rl][pol] = pdata.get("crossing", {})
    return idx

c7_idx = _build_idx(c7_data)
c2_idx = _build_idx(c2_data)

failures = []
checks   = 0

for sc_i in range(30, 55):
    if sc_i not in c7_idx:
        failures.append(f"sc{sc_i}: missing from C7 output")
        continue
    if sc_i not in c2_idx:
        failures.append(f"sc{sc_i}: missing from C2 output")
        continue

    c7_r = c7_idx[sc_i].get(CHECK_RATIO, {})
    c2_r = c2_idx[sc_i].get(CHECK_RATIO, {})

    for pol in CHECK_POLICIES:
        cx7 = c7_r.get(pol, {})
        cx2 = c2_r.get(pol, {})

        if not cx7:
            failures.append(f"sc{sc_i} r={CHECK_RATIO} {pol}: missing from C7")
            continue
        if not cx2:
            failures.append(f"sc{sc_i} r={CHECK_RATIO} {pol}: missing from C2")
            continue

        # Check status
        if cx7.get("status") != cx2.get("status"):
            failures.append(
                f"sc{sc_i} r={CHECK_RATIO} {pol}: "
                f"status C7={cx7.get('status')} vs C2={cx2.get('status')}"
            )

        # Check C_lower_pct
        v7_lo = cx7.get("C_lower_pct")
        v2_lo = cx2.get("C_lower_pct")
        if v7_lo is None and v2_lo is None:
            pass
        elif v7_lo is None or v2_lo is None:
            failures.append(f"sc{sc_i} r={CHECK_RATIO} {pol}: C_lower None mismatch C7={v7_lo} C2={v2_lo}")
        else:
            diff = abs(float(v7_lo) - float(v2_lo))
            if diff > TOLERANCE:
                failures.append(
                    f"sc{sc_i} r={CHECK_RATIO} {pol}: "
                    f"C_lower diff={diff:.2e}  C7={v7_lo:.6f}  C2={v2_lo:.6f}"
                )
        checks += 1

        # Check C_upper_pct
        v7_up = cx7.get("C_upper_pct")
        v2_up = cx2.get("C_upper_pct")
        if v7_up is None and v2_up is None:
            pass
        elif v7_up is None or v2_up is None:
            failures.append(f"sc{sc_i} r={CHECK_RATIO} {pol}: C_upper None mismatch C7={v7_up} C2={v2_up}")
        else:
            diff = abs(float(v7_up) - float(v2_up))
            if diff > TOLERANCE:
                failures.append(
                    f"sc{sc_i} r={CHECK_RATIO} {pol}: "
                    f"C_upper diff={diff:.2e}  C7={v7_up:.6f}  C2={v2_up:.6f}"
                )
        checks += 1

print(f"Checked {checks} crossing values across {len(CHECK_POLICIES)} policies × 25 scenarios")
print()

if failures:
    print(f"EQUIVALENCE GATE: FAIL  ({len(failures)} failures)")
    for f in failures:
        print(f"  FAIL: {f}")
    sys.exit(1)
else:
    print(f"EQUIVALENCE GATE: PASS")
    print(f"  All {checks} C_lower/C_upper values match C2 within {TOLERANCE} pp")
    print(f"  C7 pol_seed chain preserved full_fp, full_random, fp_withincab_placebo identity")
