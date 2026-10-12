#!/usr/bin/env python3
"""
test_gate_f_m4_reference.py

Reference-only completeness test for m4_canonical_comparisons_v3_corrected.json.

Verifies that every one of the 5 Gate F comparisons has exactly 25 held-out
scenario rows (sc5–sc29) with no duplicates. Does not check crossing values —
those are verified numerically in r1_gate_f_heldout_analysis.py.

Expected output:
  FP vs Random             heldout refs = 25 PASS
  Location vs Random       heldout refs = 25 PASS
  FP-spread vs Random      heldout refs = 25 PASS
  FP-spread vs FP          heldout refs = 25 PASS
  FP-spread vs Location    heldout refs = 25 PASS
  duplicates = 0
"""

import sys, io, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from pathlib import Path

REPO_ROOT     = Path(__file__).resolve().parents[3]
M4_FILE       = REPO_ROOT / "artifacts" / "revision1" / "results" / "m4_canonical_comparisons_v3_corrected.json"
HELDOUT_SET   = set(range(5, 30))   # sc5–sc29
N_HELDOUT     = 25

COMPARISONS = [
    ("FP vs Random",          "fp_vs_canonical_rand"),
    ("Location vs Random",    "loc_vs_canonical_rand"),
    ("FP-spread vs Random",   "spread_vs_canonical_rand"),
    ("FP-spread vs FP",       "spread_vs_fp"),
    ("FP-spread vs Location", "spread_vs_canonical_loc"),
]

print("=" * 60)
print("Gate F M4 Reference Completeness Test")
print("=" * 60)

if not M4_FILE.exists():
    print(f"FAIL: file not found: {M4_FILE}", file=sys.stderr)
    sys.exit(1)

with open(M4_FILE) as f:
    d = json.load(f)

comps = d.get("comparisons", {})

n_fail        = 0
total_dups    = 0

for label, m4_key in COMPARISONS:
    comp = comps.get(m4_key)
    if comp is None:
        print(f"  FAIL  {label:<28} key '{m4_key}' not found")
        n_fail += 1
        continue

    scenario_ids = [r["scenario_idx"] for r in comp.get("scenario_rows", [])]

    # Duplicate check
    seen: dict = {}
    for sid in scenario_ids:
        seen[sid] = seen.get(sid, 0) + 1
    dups = sorted(sid for sid, cnt in seen.items() if cnt > 1)
    total_dups += len(dups)

    # Held-out coverage
    heldout_found = [sid for sid in scenario_ids if sid in HELDOUT_SET]
    n_found       = len(heldout_found)
    missing       = sorted(HELDOUT_SET - set(scenario_ids))

    if dups:
        print(f"  FAIL  {label:<28} heldout refs = {n_found}  DUPLICATES: {dups}")
        n_fail += 1
    elif missing:
        print(f"  FAIL  {label:<28} heldout refs = {n_found}  MISSING: {missing}")
        n_fail += 1
    elif n_found != N_HELDOUT:
        print(f"  FAIL  {label:<28} heldout refs = {n_found} (expected {N_HELDOUT})")
        n_fail += 1
    else:
        print(f"  PASS  {label:<28} heldout refs = {n_found} PASS")

print(f"  duplicates = {total_dups}")
print("=" * 60)

if n_fail == 0:
    print(f"ALL {len(COMPARISONS)}/{len(COMPARISONS)} PASS")
else:
    print(f"{len(COMPARISONS) - n_fail}/{len(COMPARISONS)} passed — {n_fail} FAILED")
    sys.exit(1)
