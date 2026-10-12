#!/usr/bin/env python3
"""
M4 Sensitivity Analyses
========================
Companion to r1_m4_fair_baselines.py (M4-primary).
Runs after the 30-scenario primary results are in hand.

Items covered here (not in M4-primary to avoid bloating the main replay):
  S1. Residual bin sensitivity: K=1, K=3, K=10 (vs K=5 primary)
  S2. Parametric heteroscedastic residual sensitivity
  S3. Threshold sensitivity: 2024 p90 (61.875 C), 2024 p99 (66.263 C)
      vs primary 2024 p95 (63.625 C)
  S4. Cabinet span metrics: median / p90 cabinets-per-job by policy

All sensitivities share the SAME scenario seeds, workload draws, and
residual permutations as M4-primary for paired comparability.

Run order: run r1_m4_fair_baselines.py FIRST.
Input:     artifacts/revision1/results/m4_fair_baselines.json (M4-primary output)
Output:    artifacts/revision1/results/m4_sensitivity.json

NOTE: This script is a STUB — it confirms the design intent but is not
yet implemented.  Implement after M4-primary smoke-test results are reviewed.
"""

import json
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parents[3] / "artifacts" / "revision1" / "results"
PRIMARY = OUT_DIR / "m4_fair_baselines.json"

print("M4 Sensitivity — stub")
print("Reads M4-primary output:", PRIMARY)
print()
print("Planned sensitivity items:")
items = {
    "S1_residual_K1_K3_K10": "Re-run 30-scenario sweep with K=1, K=3, K=10 bin counts. "
                              "Primary K=5 is the reference. Report delta_C_lower relative to K=5.",
    "S2_parametric_residual": "Replace within-bin permutation with parametric N(0, bin_sigma^2) "
                               "draw. Report delta_C_lower vs non-parametric.",
    "S3_threshold_p90_p99"  : "Re-run B/S ratio computation at T_thr=61.875 (p90) and "
                               "66.263 C (p99). Delta C_lower relative to p95 primary.",
    "S4_cabinet_span"       : "Report median/p90 cabinets-per-job by policy × lambda. "
                               "Compact-cap-10 should show lower span; verify.",
}
for k, v in items.items():
    print(f"  {k}:")
    print(f"    {v}")
    print()

if not PRIMARY.exists():
    print(f"ERROR: M4-primary output not found at {PRIMARY}")
    print("Run r1_m4_fair_baselines.py first.")
else:
    with open(PRIMARY) as fh:
        prim = json.load(fh)
    print(f"M4-primary loaded: {prim['parameters']['N_SCENARIOS']} scenarios, "
          f"timestamp={prim['timestamp']}")
    print("Sensitivity implementation: NOT YET STARTED")
