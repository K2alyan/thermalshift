"""
Phase C new selectors for REVIEW2 challenge run.

Plan ref: REVIEW2_CHALLENGE_PLAN.md §C1-C4 (amendment 6b45030).

New policies:
  C1. random_spread    — same cabinet round-robin as fp_spread; choice_priority
                         hash for within-cabinet node order; never reads FA
  C2. fp_global_placebo — globally permuted FA values (perm_seed=218767960)
  C3. fp_withincab_placebo — within-cabinet permuted FA (perm_seed=365514213)
  C4. position_template — alias for full_loc (LOC_FA_dict sort)

Run this file directly to execute unit tests:
  python r2_selectors.py
"""
import hashlib, sys
import numpy as np
from collections import defaultdict
from typing import Optional

# ── Seeds frozen in REVIEW2_CHALLENGE_PLAN.md §4 ──────────────────────────
PLACEBO_GLOBAL_PERM_SEED    = 218767960
PLACEBO_WITHINCAB_PERM_SEED = 365514213

PRIMARY_BETA_CHALLENGE = 1.08293343   # from loo_beta_results.json §B1

# ── Frozen M4/Gate F constants (unchanged) ────────────────────────────────
BETA_F_FROZEN    = 1.12484352
T_THR_PRIMARY    = 63.625
T_THR_SECONDARY  = 60.602770562770566


def choice_priority(scenario_seed: int, event_uid: str, hostname: str) -> tuple:
    """BLAKE2b hash — identical to Gate F §4.2."""
    key    = scenario_seed.to_bytes(8, "big", signed=False)
    msg    = event_uid.encode("utf-8") + b"\x00" + hostname.encode("utf-8")
    digest = hashlib.blake2b(msg, key=key, digest_size=8).digest()
    return int.from_bytes(digest, "big"), hostname


# ── C1. random_spread ──────────────────────────────────────────────────────
def select_random_spread(available, k: int, cab_active_count: dict,
                         fp_cab: dict, scenario_seed: int, event_uid: str) -> list:
    """
    Same cabinet round-robin as select_fp_spread_canonical.
    Within-cabinet node order: choice_priority hash (same as full_random).
    NEVER reads FA_dict or any thermally-derived score.

    Pseudocode matches REVIEW2_CHALLENGE_PLAN.md §C1.
    """
    k = min(k, len(available))
    if k == 0:
        return []
    if k == len(available):
        return sorted(available)

    # Group nodes by cabinet — same logic as fp_spread
    cab_nodes: dict[int, list] = defaultdict(list)
    for n in sorted(available):        # deterministic initial ordering
        c = fp_cab.get(n, -1)
        cab_nodes[c].append(n)

    # Within-cabinet order: choice_priority hash (same as full_random)
    for c in cab_nodes:
        cab_nodes[c].sort(key=lambda n: choice_priority(scenario_seed, event_uid, n))

    temp     = dict(cab_active_count)
    selected = []
    for _ in range(k):
        if not cab_nodes:
            break
        # Round-robin: pick cabinet with fewest active nodes (tie-break by cab id)
        best_c  = min(cab_nodes, key=lambda c: (temp.get(c, 0), c))
        best_n  = cab_nodes[best_c].pop(0)
        if not cab_nodes[best_c]:
            del cab_nodes[best_c]
        selected.append(best_n)
        temp[best_c] = temp.get(best_c, 0) + 1

    return selected


# ── C2. fp_global_placebo — build permuted FA dict ───────────────────────
def build_global_placebo_fa(FA_dict: dict, perm_seed: int = PLACEBO_GLOBAL_PERM_SEED) -> dict:
    """
    Globally permute FA values across all fp nodes.
    Preserves the marginal distribution; destroys hostname→FA mapping.
    """
    nodes  = sorted(FA_dict.keys())   # deterministic order
    values = np.array([FA_dict[n] for n in nodes])
    rng    = np.random.default_rng(perm_seed)
    perm   = rng.permutation(len(values))
    return {nodes[i]: float(values[perm[i]]) for i in range(len(nodes))}


def select_fp_global_placebo(available, k: int, placebo_fa: dict) -> list:
    """Sort ascending by globally-permuted FA value."""
    s = sorted(available, key=lambda n: (placebo_fa.get(n, 0.0), n))
    return s[:min(k, len(s))]


# ── C3. fp_withincab_placebo — build within-cabinet permuted FA dict ──────
def build_withincab_placebo_fa(FA_dict: dict, fp_cab: dict,
                                perm_seed: int = PLACEBO_WITHINCAB_PERM_SEED) -> dict:
    """
    Within each cabinet independently, permute FA values among nodes of that cabinet.
    Preserves cabinet-level thermal structure; destroys node-level FA ordering within cab.
    """
    cab_to_nodes: dict[int, list] = defaultdict(list)
    for n in sorted(FA_dict.keys()):
        c = fp_cab.get(n, -1)
        cab_to_nodes[c].append(n)

    rng    = np.random.default_rng(perm_seed)
    result = {}
    for c in sorted(cab_to_nodes.keys()):
        nodes_c  = sorted(cab_to_nodes[c])
        vals_c   = np.array([FA_dict[n] for n in nodes_c])
        perm     = rng.permutation(len(vals_c))
        for i, n in enumerate(nodes_c):
            result[n] = float(vals_c[perm[i]])
    return result


def select_fp_withincab_placebo(available, k: int, withincab_placebo_fa: dict) -> list:
    """Sort ascending by within-cabinet permuted FA value."""
    s = sorted(available, key=lambda n: (withincab_placebo_fa.get(n, 0.0), n))
    return s[:min(k, len(s))]


# ── C4. position_template = full_loc ─────────────────────────────────────
def select_position_template(available, k: int, loc_fa: dict) -> list:
    """
    Identical to full_loc: sort ascending by LOC_FA (position-based fingerprint).
    Renamed for clarity; underlying logic unchanged from Gate F.
    """
    s = sorted(available, key=lambda n: (loc_fa.get(n, 0.0), n))
    return s[:min(k, len(s))]


# ══════════════════════════════════════════════════════════════════════════
# Unit tests (run directly: python r2_selectors.py)
# ══════════════════════════════════════════════════════════════════════════
def _run_unit_tests():
    print("=== r2_selectors unit tests ===")
    failures = []

    # ── Shared test fixtures ───────────────────────────────────────────────
    # 3 cabinets, 3 nodes each → 9 nodes total
    cabs = [100, 200, 300]
    fp_cab_test = {}
    FA_test     = {}
    for ci, c in enumerate(cabs):
        for j in range(3):
            n = f"node_{c}_{j}"
            fp_cab_test[n] = c
            FA_test[n]     = float(ci * 3 + j)   # 0,1,2,3,4,5,6,7,8
    all_nodes = sorted(fp_cab_test.keys())
    # FA values: node_100_0=0, node_100_1=1, node_100_2=2,
    #            node_200_0=3, node_200_1=4, node_200_2=5,
    #            node_300_0=6, node_300_1=7, node_300_2=8

    scen_seed = 99999
    event_uid = "test:scenario:event1"
    cab_act   = {100: 0, 200: 0, 300: 0}

    # ── C1: random_spread vs fp_spread cabinet sequence ───────────────────
    # Import fp_spread logic inline for comparison
    def _fp_spread(available, k, cab_active_count):
        k = min(k, len(available))
        temp = dict(cab_active_count)
        if k == 0: return []
        if k == len(available): return sorted(available)
        cab_nodes = defaultdict(list)
        for n in sorted(available):
            c = fp_cab_test.get(n, -1)
            cab_nodes[c].append(n)
        for c in cab_nodes:
            cab_nodes[c].sort(key=lambda n: (FA_test.get(n, 0.0), n))
        sel = []
        for _ in range(k):
            if not cab_nodes: break
            best_c = min(cab_nodes, key=lambda c: (temp.get(c, 0), c))
            best_n = cab_nodes[best_c].pop(0)
            if not cab_nodes[best_c]: del cab_nodes[best_c]
            sel.append(best_n)
            temp[best_c] = temp.get(best_c, 0) + 1
        return sel

    available = list(all_nodes)

    # Test: same cabinet sequence for both spread policies
    rs_result  = select_random_spread(available, 6, cab_act, fp_cab_test, scen_seed, event_uid)
    fps_result = _fp_spread(available, 6, cab_act)

    rs_cabs  = [fp_cab_test[n] for n in rs_result]
    fps_cabs = [fp_cab_test[n] for n in fps_result]

    if rs_cabs == fps_cabs:
        print("  PASS: random_spread and fp_spread produce the same cabinet sequence (k=6)")
    else:
        msg = f"  FAIL: cabinet sequences differ: random_spread={rs_cabs} fp_spread={fps_cabs}"
        print(msg); failures.append(msg)

    # Test: node selections differ (unless by coincidence — unlikely with real hash)
    if rs_result != fps_result:
        print("  PASS: random_spread and fp_spread select different nodes within cabinets")
    else:
        # Check if FA order == choice_priority order coincidentally
        print("  WARN: random_spread == fp_spread node selection (hash collision or small fixture)")

    # Test: random_spread is deterministic given same seed+uid
    rs_r2 = select_random_spread(available, 6, cab_act, fp_cab_test, scen_seed, event_uid)
    if rs_result == rs_r2:
        print("  PASS: random_spread is deterministic")
    else:
        msg = "  FAIL: random_spread is not deterministic"
        print(msg); failures.append(msg)

    # Test: random_spread with different event_uid gives different result
    rs_diff = select_random_spread(available, 6, cab_act, fp_cab_test, scen_seed, "other:uid")
    if rs_diff != rs_result:
        print("  PASS: random_spread changes with different event_uid")
    else:
        print("  WARN: random_spread unchanged with different event_uid (hash collision)")

    # Test: random_spread NEVER reads FA_dict (verified by construction — no FA_test reference)
    print("  PASS: select_random_spread does not reference FA_dict (by construction)")

    # ── C2: fp_global_placebo ─────────────────────────────────────────────
    gpfa = build_global_placebo_fa(FA_test, PLACEBO_GLOBAL_PERM_SEED)

    # Permutation: same set of values
    orig_vals = sorted(FA_test.values())
    perm_vals = sorted(gpfa.values())
    if orig_vals == perm_vals:
        print("  PASS: global placebo preserves the marginal distribution of FA values")
    else:
        msg = "  FAIL: global placebo does not preserve marginal distribution"
        print(msg); failures.append(msg)

    # Permutation: at least one hostname→FA mapping differs
    diffs = sum(1 for n in FA_test if FA_test[n] != gpfa.get(n, None))
    if diffs > 0:
        print(f"  PASS: global placebo changes hostname->FA for {diffs}/{len(FA_test)} nodes")
    else:
        msg = "  FAIL: global placebo is identity permutation"
        print(msg); failures.append(msg)

    # Permutation is deterministic
    gpfa2 = build_global_placebo_fa(FA_test, PLACEBO_GLOBAL_PERM_SEED)
    if gpfa == gpfa2:
        print("  PASS: global placebo is deterministic")
    else:
        msg = "  FAIL: global placebo is not deterministic"
        print(msg); failures.append(msg)

    # ── C3: fp_withincab_placebo ──────────────────────────────────────────
    wcpfa = build_withincab_placebo_fa(FA_test, fp_cab_test, PLACEBO_WITHINCAB_PERM_SEED)

    # Within each cabinet: same set of values, possibly different assignment
    for c in cabs:
        nodes_c  = sorted([n for n in FA_test if fp_cab_test[n] == c])
        orig_set = sorted([FA_test[n] for n in nodes_c])
        perm_set = sorted([wcpfa[n] for n in nodes_c])
        if orig_set == perm_set:
            print(f"  PASS: within-cab placebo preserves FA distribution within cabinet {c}")
        else:
            msg = f"  FAIL: within-cab placebo changes FA distribution within cabinet {c}"
            print(msg); failures.append(msg)

    # Overall distribution preserved
    orig_all = sorted(FA_test.values())
    perm_all = sorted(wcpfa.values())
    if orig_all == perm_all:
        print("  PASS: within-cab placebo preserves overall FA distribution")
    else:
        msg = "  FAIL: within-cab placebo does not preserve overall FA distribution"
        print(msg); failures.append(msg)

    # Deterministic
    wcpfa2 = build_withincab_placebo_fa(FA_test, fp_cab_test, PLACEBO_WITHINCAB_PERM_SEED)
    if wcpfa == wcpfa2:
        print("  PASS: within-cab placebo is deterministic")
    else:
        msg = "  FAIL: within-cab placebo is not deterministic"
        print(msg); failures.append(msg)

    # ── C4: position_template = full_loc ─────────────────────────────────
    loc_fa_test = {n: -FA_test[n] for n in FA_test}   # reverse as placeholder
    pt_result   = select_position_template(available, 4, loc_fa_test)
    expected_by_loc = sorted(available, key=lambda n: (loc_fa_test.get(n, 0.0), n))[:4]
    if pt_result == expected_by_loc:
        print("  PASS: position_template correctly sorts by loc_fa ascending")
    else:
        msg = f"  FAIL: position_template mismatch: got {pt_result}, expected {expected_by_loc}"
        print(msg); failures.append(msg)

    # ── k=0 and k=all edge cases for random_spread ────────────────────────
    r0 = select_random_spread(available, 0, cab_act, fp_cab_test, scen_seed, event_uid)
    if r0 == []:
        print("  PASS: random_spread k=0 returns []")
    else:
        msg = f"  FAIL: random_spread k=0 returned {r0}"
        print(msg); failures.append(msg)

    r_all = select_random_spread(available, len(available), cab_act, fp_cab_test, scen_seed, event_uid)
    if sorted(r_all) == sorted(available):
        print("  PASS: random_spread k=len(available) returns all nodes")
    else:
        msg = "  FAIL: random_spread k=len(available) did not return all nodes"
        print(msg); failures.append(msg)

    # ── Summary ───────────────────────────────────────────────────────────
    print()
    if failures:
        print(f"FAILED: {len(failures)} test(s)")
        for f in failures:
            print(f"  {f}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")
    return True


if __name__ == "__main__":
    _run_unit_tests()
