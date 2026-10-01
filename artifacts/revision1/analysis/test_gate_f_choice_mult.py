#!/usr/bin/env python3
"""
Unit test for realized_selector_choice_multiplier = |C_p,r| / k

The shortlist size is min(ceil(r * k), |A_full,p|).
At r=1.0, size=k, so multiplier=1.0 exactly.
At unrestricted (r=None), C_p,r = A_full,p, so multiplier = |A_full| / k.
"""
import math, sys


def shortlist_size(n_full: int, k: int, r) -> int:
    """Replicates gate_f_shortlist size logic. r=None means unrestricted."""
    if r is None:
        return n_full
    return min(n_full, math.ceil(r * k))


def choice_mult(n_full: int, k: int, r) -> float:
    return shortlist_size(n_full, k, r) / k


def run_tests():
    failures = []

    def check(label, got, expected):
        if abs(got - expected) > 1e-12:
            failures.append(f"{label}: got {got}, expected {expected}")

    # |A_full|=20, k=4
    n, k = 20, 4
    check("|A|=20 k=4 r=1.0",         choice_mult(n, k, 1.0),   1.00)
    check("|A|=20 k=4 r=1.25",        choice_mult(n, k, 1.25),  1.25)
    check("|A|=20 k=4 r=1.5",         choice_mult(n, k, 1.5),   1.50)
    check("|A|=20 k=4 r=2.0",         choice_mult(n, k, 2.0),   2.00)
    check("|A|=20 k=4 r=4.0",         choice_mult(n, k, 4.0),   4.00)
    check("|A|=20 k=4 r=8.0 (cap)",   choice_mult(n, k, 8.0),   5.00)
    check("|A|=20 k=4 unrestricted",  choice_mult(n, k, None),  5.00)

    # |A_full|=6, k=4
    n, k = 6, 4
    check("|A|=6 k=4 r=2.0 (cap)",    choice_mult(n, k, 2.0),   1.50)
    check("|A|=6 k=4 unrestricted",   choice_mult(n, k, None),  1.50)

    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        sys.exit(1)
    else:
        print(f"PASS: all {9} realized_selector_choice_multiplier cases correct")


if __name__ == "__main__":
    run_tests()
