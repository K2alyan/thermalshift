#!/usr/bin/env python3
"""
Gate F unit tests 1-6 (§13 of GATE_F_DESIGN.md).
Must all pass before any scenario execution.
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))

from r1_gate_f_helpers import (
    choice_priority, gate_f_shortlist, make_event_uid, syn_generation_ordinal,
)

# ── Shared fixtures ────────────────────────────────────────────────────────────
SEED = 191664964          # sc0 scenario_seed (from m4_fair_baselines.json)
UID  = "syn:191664964:0"  # synthetic event uid for tests

HOSTNAMES_20 = [f"node{i:04d}" for i in range(20)]
K = 4

POLICIES = ["full_random", "full_fp", "full_loc", "full_fp_spread"]

# ── Test runner ────────────────────────────────────────────────────────────────
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


# ── Test 1: Determinism ────────────────────────────────────────────────────────
def test1_determinism():
    """Identical arguments → identical (int, str) tuple."""
    p1 = choice_priority(SEED, UID, "node0001")
    p2 = choice_priority(SEED, UID, "node0001")
    assert p1 == p2, f"non-deterministic: {p1} != {p2}"


# ── Test 2: Input-order independence ──────────────────────────────────────────
def test2_input_order_independence():
    """Ranking is independent of the iteration order of the input list."""
    asc  = sorted(HOSTNAMES_20)
    desc = sorted(HOSTNAMES_20, reverse=True)
    ranked_asc  = sorted(asc,  key=lambda h: choice_priority(SEED, UID, h))
    ranked_desc = sorted(desc, key=lambda h: choice_priority(SEED, UID, h))
    assert ranked_asc == ranked_desc, "ranking differs between asc and desc input order"


# ── Test 3: Single-node stability ─────────────────────────────────────────────
def test3_single_node_stability():
    """Removing one node leaves the relative order of all remaining nodes unchanged."""
    ordered_full = sorted(HOSTNAMES_20, key=lambda h: choice_priority(SEED, UID, h))
    removed = ordered_full[7]
    reduced = [h for h in HOSTNAMES_20 if h != removed]
    ordered_reduced = sorted(reduced, key=lambda h: choice_priority(SEED, UID, h))
    expected = [h for h in ordered_full if h != removed]
    assert ordered_reduced == expected, (
        f"removing {removed!r} reordered remaining nodes"
    )


# ── Test 4: Prefix nesting (fixed A_full) ─────────────────────────────────────
def test4_prefix_nesting():
    """
    For a fixed full_eligible, shortlists at increasing r are nested prefixes.
    C_p,1.0 ⊆ C_p,1.25 ⊆ C_p,1.5 ⊆ C_p,2.0 ⊆ C_p,4.0 ⊆ C_p,8.0 ⊆ C_p,unr
    Verified by set containment. Same full_eligible passed at every ratio call.
    """
    ratios   = [1.0, 1.25, 1.5, 2.0, 4.0, 8.0, None]
    labels   = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"]
    sets = {r: set(gate_f_shortlist(HOSTNAMES_20, SEED, UID, r, K)) for r in ratios}
    for i in range(len(ratios) - 1):
        ra, rb = ratios[i], ratios[i + 1]
        assert sets[ra] <= sets[rb], (
            f"nesting violated: C_p,{labels[i]} not ⊆ C_p,{labels[i+1]}"
        )


# ── Test 5: Hash policy-neutrality ────────────────────────────────────────────
def test5_hash_policy_neutrality():
    """
    The hash takes no policy parameter. Identical full_eligible and (seed, uid)
    produces byte-for-byte identical shortlists across all four policies.
    """
    shortlists = {
        p: gate_f_shortlist(HOSTNAMES_20, SEED, UID, 2.0, K)
        for p in POLICIES
    }
    ref = shortlists[POLICIES[0]]
    for p in POLICIES[1:]:
        assert shortlists[p] == ref, (
            f"policy {p!r} produced different shortlist:\n  got: {shortlists[p]}\n  exp: {ref}"
        )


# ── Test 6: Global event_uid uniqueness ───────────────────────────────────────
def test6_event_uid_uniqueness():
    """
    Within a scenario, all event UIDs are globally unique.
    base: / syn: prefixes make inter-type collisions impossible by construction,
    but the assertion is required regardless (§13).
    """
    n_base_sample = 200     # representative sample of base job indices
    n_syn_sample  = 100     # representative sample of synthetic generation ordinals

    base_idxs    = list(range(1, n_base_sample + 1))       # positive ints
    syn_ordinals = list(range(n_syn_sample))                 # 0-based

    uids = (
        [make_event_uid("base", job_idx=jid) for jid in base_idxs]
        + [make_event_uid("syn", scenario_seed=SEED, generation_ordinal=g)
           for g in syn_ordinals]
    )
    n_events = len(uids)
    n_unique  = len(set(uids))
    assert n_unique == n_events, (
        f"UID collision: {n_events} events, {n_unique} unique"
    )

    # Also verify syn_generation_ordinal round-trips correctly
    for jid in [-(i + 1) for i in range(10)]:
        gen = syn_generation_ordinal(jid)
        uid = make_event_uid("syn", scenario_seed=SEED, generation_ordinal=gen)
        assert uid == f"syn:{SEED}:{abs(jid)-1}", f"round-trip mismatch for job_idx={jid}"


# ── Main ───────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 62)
    print("Gate F Unit Tests (§13 GATE_F_DESIGN.md)")
    print("=" * 62)

    tests = [
        ("Test 1 — Determinism",                test1_determinism),
        ("Test 2 — Input-order independence",    test2_input_order_independence),
        ("Test 3 — Single-node stability",       test3_single_node_stability),
        ("Test 4 — Prefix nesting (fixed A)",    test4_prefix_nesting),
        ("Test 5 — Hash policy-neutrality",      test5_hash_policy_neutrality),
        ("Test 6 — Global event_uid uniqueness", test6_event_uid_uniqueness),
    ]

    results = [run_test(name, fn) for name, fn in tests]

    n_pass = sum(results)
    n_fail = len(results) - n_pass
    print()
    print(f"{'='*62}")
    if n_fail == 0:
        print(f"ALL {n_pass}/{len(results)} TESTS PASSED")
    else:
        print(f"{n_pass}/{len(results)} passed — {n_fail} FAILED")
    print(f"{'='*62}")
    if n_fail:
        sys.exit(1)
