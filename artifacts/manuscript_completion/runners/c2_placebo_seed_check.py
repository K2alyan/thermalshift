#!/usr/bin/env python3
"""
Placebo seed verification for C2 manuscript-completion runner.
Verifies per-scenario placebo seed derivation via SeedSequence.
"""
from numpy.random import SeedSequence

R3_ROOT = 847291653

checks = [
    (0,  1, 2514122466,  "global i=0"),
    (0,  2, 4138460386,  "withincab i=0"),
    (1,  1, 239530002,   "global i=1"),
    (1,  2, 2821695500,  "withincab i=1"),
    (24, 1, 1242389544,  "global i=24"),
    (24, 2, 2325658828,  "withincab i=24"),
]

all_pass = True
for i, pid, expected, label in checks:
    got = int(SeedSequence([R3_ROOT, i, pid]).generate_state(1)[0])
    status = "PASS" if got == expected else "FAIL"
    if got != expected: all_pass = False
    print(f"  {status}: {label}: got={got}, expected={expected}")

if all_pass:
    print("\nAll placebo seed checks PASSED")
else:
    print("\nSOME CHECKS FAILED")
    raise SystemExit(1)
