"""
Round 7 selectors: position_group_hash (pre-execution freeze, post-exposure corrective).
Amended per ROUND7_AMENDMENT.md — singleton correction applied.

position_group_hash properties (frozen per ROUND7_STRUCTURAL_BASELINE_AUDIT.md §5 and
ROUND7_AMENDMENT.md §Correction-2):

  Group key:  chassis + "_" + slot + "_" + board + "_" + node_pos
  Score:
    If group size >= 2:  arithmetic mean FA_2024 of entire group (group-constant)
    If group size == 1:  global cohort mean FA_2024 (neutral; no individual identity)
  Sort:       ascending (lower score = cooler structural position = preferred)
  Tie-break:  BLAKE2b(event_uid + hostname, key=scenario_seed) — same construction
              as Gate F Stage-1 choice_priority; event-specific, policy-blind
  Hostname:   NOT used as tie-break
  FA_2024:    NOT used individually as tie-break (encoded only in group score for >=2 groups)

Structural group-size audit (2,000-node cohort):
  Total groups: 67  |  Singleton groups: 10  |  Missing FA_2024: 0
  Global cohort mean FA_2024: -0.03720489 (assigned to all 10 singletons)

Run unit tests: python c7_selectors.py
"""
import hashlib, sys
import numpy as np
from collections import defaultdict

# Carried over unchanged from c2_selectors.py
PLACEBO_GLOBAL_PERM_SEED    = 218767960
PLACEBO_WITHINCAB_PERM_SEED = 365514213
PRIMARY_BETA_CHALLENGE      = 1.11416358   # median(beta_j_CF), 462 per-job LOO betas (v2)

BETA_F_FROZEN      = 1.12484352
T_THR_PRIMARY      = 63.625
T_THR_SECONDARY    = 60.602770562770566
BETA_D_SENSITIVITY = 0.960   # D-series sensitivity value


# ── position_group_hash: build ─────────────────────────────────────────────────
def build_position_group_hash_fa(fp_topo, FA_dict: dict) -> tuple:
    """
    Build group-mean position score dict for all fp nodes.

    Group key: chassis_slot_board_node_pos (identical to C1 full_loc).

    Score rule (frozen, ROUND7_AMENDMENT.md §Correction-2):
      group size >= 2:  arithmetic mean FA_2024 for ALL members (group-constant)
      group size == 1:  global cohort mean FA_2024 (neutral fallback, no identity)

    NaN FA_2024 values replaced with global cohort mean before group mean
    computation (same fill rule as C1 full_loc / position_template).
    The same global mean is used as the singleton fallback score.

    Returns:
      group_fa_dict  : hostname -> assigned score (float)
      n_groups       : int — number of distinct position groups
      n_singletons   : int — number of singleton groups (assigned global mean)
      n_nan          : int — nodes whose FA_2024 was NaN before fill
    """
    topo = fp_topo.copy()
    topo["FA_2024"] = topo["hostname"].map(FA_dict)
    _finite_mask = topo["FA_2024"].notna()
    # Global cohort mean: computed from all finite FA_2024 values BEFORE group aggregation.
    # Used both as NaN fill and as the neutral singleton fallback.
    _global_mean = float(topo.loc[_finite_mask, "FA_2024"].mean())
    topo["FA_2024_filled"] = topo["FA_2024"].fillna(_global_mean)
    n_nan = int((~_finite_mask).sum())

    topo["gk"] = (topo["chassis"].astype(str) + "_" +
                  topo["slot"].astype(str)    + "_" +
                  topo["board"].astype(str)   + "_" +
                  topo["node_pos"].astype(str))

    group_means = topo.groupby("gk")["FA_2024_filled"].mean()
    group_sizes = topo.groupby("gk")["FA_2024_filled"].count()

    group_fa_dict: dict[str, float] = {}
    n_singletons = 0

    for _, row in topo.iterrows():
        node = row["hostname"]
        gk   = row["gk"]
        if int(group_sizes[gk]) == 1:
            # Singleton: assign global mean — do NOT expose own FA_2024
            group_fa_dict[node] = _global_mean
            n_singletons += 1
        else:
            group_fa_dict[node] = float(group_means[gk])

    # Count unique singleton groups (not nodes)
    n_singleton_groups = int((group_sizes == 1).sum())
    n_groups = int(topo["gk"].nunique())

    print(f"    position_group_hash: {len(group_fa_dict)} nodes, {n_groups} groups, "
          f"{n_singleton_groups} singleton groups ({n_singletons} nodes -> global_mean={_global_mean:.6f}), "
          f"NaN_FA={n_nan}")
    return group_fa_dict, n_groups, n_singletons, n_nan


# ── position_group_hash: select ────────────────────────────────────────────────
def select_position_group_hash(available, k: int, group_fa_dict: dict,
                                scenario_seed: int, event_uid: str) -> list:
    """
    Select k nodes ascending by group-constant score.
    Tie-break within tied scores: BLAKE2b hash keyed by scenario_seed and
    event_uid, identical construction to Gate F Stage-1 choice_priority hash.
    Hostname and individual FA are NOT secondary sort keys.
    """
    if event_uid is None:
        event_uid = "unrestricted"
    _key   = scenario_seed.to_bytes(8, "big", signed=False)
    _uid_b = event_uid.encode("utf-8") + b"\x00"

    def _sort_key(n: str) -> tuple:
        group_score = group_fa_dict.get(n, 0.0)
        hash_val    = int.from_bytes(
            hashlib.blake2b(_uid_b + n.encode("utf-8"),
                            key=_key, digest_size=8).digest(),
            "big",
        )
        return (group_score, hash_val)

    scored = sorted(available, key=_sort_key)
    return scored[:min(k, len(scored))]


# ── fp_withincab_placebo (copied from c2_selectors for self-contained import) ──
def build_withincab_placebo_fa(FA_dict: dict, fp_cab: dict,
                                perm_seed: int = PLACEBO_WITHINCAB_PERM_SEED) -> dict:
    """Within each cabinet, permute FA values among nodes of that cabinet."""
    cab_to_nodes: dict[int, list] = defaultdict(list)
    for n in sorted(FA_dict.keys()):
        c = fp_cab.get(n, -1)
        cab_to_nodes[c].append(n)
    rng    = np.random.default_rng(perm_seed)
    result = {}
    for c in sorted(cab_to_nodes.keys()):
        nodes_c = sorted(cab_to_nodes[c])
        vals_c  = np.array([FA_dict[n] for n in nodes_c])
        perm    = rng.permutation(len(vals_c))
        for i, n in enumerate(nodes_c):
            result[n] = float(vals_c[perm[i]])
    return result


def select_fp_withincab_placebo(available, k: int, withincab_placebo_fa: dict) -> list:
    """Sort ascending by within-cabinet permuted FA value."""
    s = sorted(available, key=lambda n: (withincab_placebo_fa.get(n, 0.0), n))
    return s[:min(k, len(s))]


# ── Unit tests ─────────────────────────────────────────────────────────────────
def _run_unit_tests():
    print("=== c7_selectors unit tests (amended) ===")
    failures = []

    import pandas as pd
    import numpy as _np

    # ── Test fixture ──────────────────────────────────────────────────────────
    # 3 groups:
    #   groupA (gk=1_1_1_1): n1(FA=1.0), n2(FA=3.0) -> group_mean=2.0
    #   groupB (gk=1_1_1_2): n3(FA=5.0), n4(FA=7.0) -> group_mean=6.0
    #   groupS (gk=2_2_2_2): n5(FA=9.0) -> singleton -> global_mean
    # FA values: [1,3,5,7,9]; global mean = 5.0
    fp_topo = pd.DataFrame({
        "hostname": ["n1", "n2", "n3", "n4", "n5"],
        "chassis":  [1, 1, 1, 1, 2],
        "slot":     [1, 1, 1, 1, 2],
        "board":    [1, 1, 1, 1, 2],
        "node_pos": [1, 1, 2, 2, 2],
    })
    FA = {"n1": 1.0, "n2": 3.0, "n3": 5.0, "n4": 7.0, "n5": 9.0}
    global_mean_expected = 5.0   # mean of [1,3,5,7,9]

    gfd, n_groups, n_singletons, n_nan = build_position_group_hash_fa(fp_topo, FA)

    # ── T1: Multi-node group members get bit-identical scores ─────────────────
    if gfd["n1"] == gfd["n2"] and abs(gfd["n1"] - 2.0) < 1e-12:
        print("  PASS T1a: group-A members get identical score 2.0")
    else:
        msg = f"  FAIL T1a: group-A scores n1={gfd['n1']}, n2={gfd['n2']} (expected 2.0)"
        print(msg); failures.append(msg)

    if gfd["n3"] == gfd["n4"] and abs(gfd["n3"] - 6.0) < 1e-12:
        print("  PASS T1b: group-B members get identical score 6.0")
    else:
        msg = f"  FAIL T1b: group-B scores n3={gfd['n3']}, n4={gfd['n4']} (expected 6.0)"
        print(msg); failures.append(msg)

    # ── T2: Singleton gets global mean, NOT own FA_2024 ──────────────────────
    if abs(gfd["n5"] - global_mean_expected) < 1e-12:
        print(f"  PASS T2: singleton n5 gets global_mean={global_mean_expected} (own FA=9.0)")
    else:
        msg = f"  FAIL T2: singleton n5 got {gfd['n5']}, expected {global_mean_expected} (own FA=9.0)"
        print(msg); failures.append(msg)

    if abs(gfd["n5"] - 9.0) > 1e-6:
        print("  PASS T2b: singleton score differs from own FA_2024=9.0")
    else:
        msg = "  FAIL T2b: singleton score equals own FA_2024 (identity leaked)"
        print(msg); failures.append(msg)

    # ── T3: Changing one member's FA changes group score (same for both) ──────
    FA_mod = dict(FA); FA_mod["n2"] = 10.0   # was 3.0; new group_A mean = (1+10)/2 = 5.5
    gfd_mod, _, _, _ = build_position_group_hash_fa(fp_topo, FA_mod)
    expected_new = 5.5
    if abs(gfd_mod["n1"] - expected_new) < 1e-12 and abs(gfd_mod["n2"] - expected_new) < 1e-12:
        print("  PASS T3a: changing one member's FA changes both members' score")
    else:
        msg = f"  FAIL T3a: modified scores n1={gfd_mod['n1']}, n2={gfd_mod['n2']} (expected {expected_new})"
        print(msg); failures.append(msg)

    # Within-group ordering after score change: still BLAKE2b only
    scen_seed = 42; event_uid = "test:event:001"
    sel_orig = select_position_group_hash(["n1", "n2"], 1, gfd,     scen_seed, event_uid)
    sel_mod  = select_position_group_hash(["n1", "n2"], 1, gfd_mod, scen_seed, event_uid)
    if sel_orig == sel_mod:
        print("  PASS T3b: within-group ordering unchanged despite FA change (BLAKE2b tie-break)")
    else:
        msg = f"  FAIL T3b: ordering changed: orig={sel_orig} mod={sel_mod}"
        print(msg); failures.append(msg)

    # ── T4: Within-group ordering is solely BLAKE2b, not hostname order ───────
    # Force a case: pick 1 from {n1, n2} using multiple (seed, uid) combinations
    # and verify that sometimes n1 wins, sometimes n2 wins (non-deterministic across events)
    wins = {"n1": 0, "n2": 0}
    for seed in [1, 2, 3, 4, 5, 100, 200, 9999]:
        for uid in ["event:A", "event:B", "event:C"]:
            s = select_position_group_hash(["n1", "n2"], 1, gfd, seed, uid)
            wins[s[0]] += 1

    if wins["n1"] > 0 and wins["n2"] > 0:
        print(f"  PASS T4: BLAKE2b tie-break gives non-deterministic within-group order "
              f"(n1 wins {wins['n1']}x, n2 wins {wins['n2']}x across 24 event/seed combos)")
    else:
        msg = f"  WARN T4: one node always wins ({wins}) — may indicate hostname bias"
        print(msg)
        # This is a warning, not necessarily a failure (hash could still be BLAKE2b-correct)

    # ── T5: Hostname lexicographic ordering is NOT imposed ────────────────────
    # Create two nodes where hostname order ("na" < "nz") differs from hash order.
    # Group them identically (same group score), then verify the selector can pick either.
    fp_topo5 = pd.DataFrame({
        "hostname": ["na", "nz"],
        "chassis":  [9, 9], "slot": [9, 9], "board": [9, 9], "node_pos": [9, 9],
    })
    FA5 = {"na": 2.0, "nz": 2.0}   # identical FA (same group)
    gfd5, _, _, _ = build_position_group_hash_fa(fp_topo5, FA5)
    # Both get same group score (2.0). BLAKE2b will break tie.
    wins5 = {"na": 0, "nz": 0}
    for seed in range(50):
        for uid in ["u:1", "u:2"]:
            s = select_position_group_hash(["na", "nz"], 1, gfd5, seed, uid)
            wins5[s[0]] += 1
    if wins5["na"] > 0 and wins5["nz"] > 0:
        print(f"  PASS T5: hostname lexicographic order not imposed "
              f"(na wins {wins5['na']}x, nz wins {wins5['nz']}x across 100 combos)")
    else:
        msg = (f"  FAIL T5: one hostname always wins ({wins5}) "
               f"— suggests lexicographic tie-break")
        print(msg); failures.append(msg)

    # ── T6: FA_2024 not used after group score when resolving ties ────────────
    # Verify that two nodes with IDENTICAL group score but DIFFERENT individual FA
    # are ordered solely by BLAKE2b (not by FA).
    # Group A: n1(FA=1.0), n2(FA=3.0) both have group score 2.0.
    # If FA were used as tiebreak, n1 would always precede n2 (lower FA first).
    # If BLAKE2b, sometimes n2 could precede n1.
    # T4 already tested this through wins; assert gfd["n1"] == gfd["n2"] and no further FA use.
    if gfd["n1"] == gfd["n2"]:
        print("  PASS T6: both group-A nodes have identical score; FA not reachable as tiebreak")
    else:
        msg = "  FAIL T6: group-A node scores differ — FA leaking into group score"
        print(msg); failures.append(msg)

    # Additional: ascending selection prefers cooler group (group A < group B < singleton)
    sel2 = select_position_group_hash(["n1","n2","n3","n4","n5"], 2, gfd, scen_seed, event_uid)
    if set(sel2) == {"n1", "n2"}:
        print("  PASS T6b: ascending sort selects cooler group-A (score=2.0) before group-B (6.0)")
    else:
        msg = f"  FAIL T6b: expected {{n1,n2}} got {set(sel2)}"
        print(msg); failures.append(msg)

    # Singleton (score=global_mean=5.0) should be between group-A (2.0) and group-B (6.0)
    sel3 = select_position_group_hash(["n1","n2","n3","n4","n5"], 3, gfd, scen_seed, event_uid)
    if set(sel3) == {"n1", "n2", "n5"}:
        print("  PASS T6c: singleton (global_mean=5.0) selected before group-B (6.0)")
    else:
        msg = f"  FAIL T6c: expected {{n1,n2,n5}} got {set(sel3)}"
        print(msg); failures.append(msg)

    # ── T7: NaN fill with global mean before group mean ───────────────────────
    FA_nan = {"n1": 1.0, "n2": float("nan"), "n3": 5.0, "n4": 7.0, "n5": 9.0}
    # Finite values: 1, 5, 7, 9 -> global_mean = 5.5
    # Group A: (1 + 5.5) / 2 = 3.25 (n2 NaN filled with 5.5)
    gfd_nan, _, _, n_nan2 = build_position_group_hash_fa(fp_topo, FA_nan)
    if n_nan2 == 1:
        print("  PASS T7a: n_nan=1 for one NaN node")
    else:
        msg = f"  FAIL T7a: expected n_nan=1, got {n_nan2}"
        print(msg); failures.append(msg)
    if abs(gfd_nan["n1"] - 3.25) < 1e-9 and abs(gfd_nan["n2"] - 3.25) < 1e-9:
        print("  PASS T7b: NaN fill with global mean propagates to group mean")
    else:
        msg = f"  FAIL T7b: group-A after NaN fill: n1={gfd_nan['n1']}, n2={gfd_nan['n2']} (expected 3.25)"
        print(msg); failures.append(msg)

    # ── T8: Determinism and edge cases ────────────────────────────────────────
    s1 = select_position_group_hash(["n1","n2"], 1, gfd, scen_seed, event_uid)
    s2 = select_position_group_hash(["n1","n2"], 1, gfd, scen_seed, event_uid)
    if s1 == s2:
        print("  PASS T8a: select_position_group_hash is deterministic")
    else:
        msg = "  FAIL T8a: non-deterministic"; print(msg); failures.append(msg)

    if select_position_group_hash([], 1, gfd, scen_seed, event_uid) == []:
        print("  PASS T8b: empty available returns []")
    else:
        failures.append("  FAIL T8b: empty available did not return []")

    if select_position_group_hash(["n1","n2"], 0, gfd, scen_seed, event_uid) == []:
        print("  PASS T8c: k=0 returns []")
    else:
        failures.append("  FAIL T8c: k=0 did not return []")

    if select_position_group_hash(["n1","n2","n3"], 3, gfd, scen_seed, None) == \
       select_position_group_hash(["n1","n2","n3"], 3, gfd, scen_seed, "unrestricted"):
        print("  PASS T8d: event_uid=None treated as 'unrestricted'")
    else:
        failures.append("  FAIL T8d: event_uid=None not equivalent to 'unrestricted'")

    # ── Summary ───────────────────────────────────────────────────────────────
    print()
    if failures:
        print(f"FAILED: {len(failures)} test(s)")
        for f in failures: print(f"  {f}")
        sys.exit(1)
    else:
        print(f"ALL TESTS PASSED ({8} test groups)")


if __name__ == "__main__":
    _run_unit_tests()
