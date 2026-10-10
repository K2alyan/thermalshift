"""
Round 7 selectors: position_group_hash (frozen before execution).
Corrected structural-position comparator replacing invalid position_loo.

position_group_hash properties (from ROUND7_STRUCTURAL_BASELINE_AUDIT.md §5):
  Group key:  chassis + "_" + slot + "_" + board + "_" + node_pos
  Score:      pre-2025 arithmetic mean FA_2024 for ALL group members (no LOO)
  Sort:       ascending (lower score = cooler structural position = preferred)
  Tie-break:  BLAKE2b(event_uid + hostname, key=scenario_seed) — same construction
              as Gate F Stage-1 choice_priority; event-specific, policy-blind
  Hostname:   NOT used as tie-break
  FA_2024:    NOT used individually as tie-break (encoded only in group score)

Run unit tests: python c7_selectors.py
"""
import hashlib, sys
import numpy as np
from collections import defaultdict

# Carried over unchanged from c2_selectors.py
PLACEBO_GLOBAL_PERM_SEED    = 218767960
PLACEBO_WITHINCAB_PERM_SEED = 365514213
PRIMARY_BETA_CHALLENGE      = 1.11416358   # median(beta_j_CF), 462 per-job LOO betas (v2)

BETA_F_FROZEN   = 1.12484352
T_THR_PRIMARY   = 63.625
T_THR_SECONDARY = 60.602770562770566

# Beta for D-series sensitivity
BETA_D_SENSITIVITY = 0.960


# ── position_group_hash: build ─────────────────────────────────────────────────
def build_position_group_hash_fa(fp_topo, FA_dict: dict) -> tuple:
    """
    Build group-mean position score dict for all fp nodes.

    Group key: chassis_slot_board_node_pos (identical to C1 full_loc).
    Score: arithmetic mean FA_2024 for ALL nodes sharing the group key —
           no self-exclusion, no leave-one-out.
    NaN FA_2024 values replaced with global cohort mean before group mean
    computation (same fill rule as C1 full_loc / position_template).

    Returns:
      group_fa_dict : hostname -> group mean FA (float)
      n_groups      : int — number of distinct position groups
      n_nan         : int — nodes whose FA_2024 was NaN before fill
    """
    topo = fp_topo.copy()
    topo["FA_2024"] = topo["hostname"].map(FA_dict)
    _finite_mask = topo["FA_2024"].notna()
    _global_mean = float(topo.loc[_finite_mask, "FA_2024"].mean())
    topo["FA_2024_filled"] = topo["FA_2024"].fillna(_global_mean)
    n_nan = int((~_finite_mask).sum())

    topo["gk"] = (topo["chassis"].astype(str) + "_" +
                  topo["slot"].astype(str)    + "_" +
                  topo["board"].astype(str)   + "_" +
                  topo["node_pos"].astype(str))

    group_means = topo.groupby("gk")["FA_2024_filled"].mean()

    group_fa_dict: dict[str, float] = {}
    for _, row in topo.iterrows():
        group_fa_dict[row["hostname"]] = float(group_means[row["gk"]])

    n_groups = int(topo["gk"].nunique())
    print(f"    position_group_hash: {len(group_fa_dict)} nodes, "
          f"{n_groups} groups, NaN_FA={n_nan}")
    return group_fa_dict, n_groups, n_nan


# ── position_group_hash: select ────────────────────────────────────────────────
def select_position_group_hash(available, k: int, group_fa_dict: dict,
                                scenario_seed: int, event_uid: str) -> list:
    """
    Select k nodes ascending by group mean FA score.
    Tie-break within tied groups: BLAKE2b hash keyed by scenario_seed and
    event_uid, identical construction to Gate F Stage-1 choice_priority hash.
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
    print("=== c7_selectors unit tests ===")
    failures = []

    # Minimal topology: 2 position groups, 2 nodes each
    # group A (gk="1_1_1_1"): nodes n1(FA=1.0), n2(FA=3.0) -> group_mean=2.0
    # group B (gk="1_1_1_2"): nodes n3(FA=5.0), n4(FA=7.0) -> group_mean=6.0
    import pandas as pd
    fp_topo = pd.DataFrame({
        "hostname": ["n1", "n2", "n3", "n4"],
        "chassis":  [1, 1, 1, 1],
        "slot":     [1, 1, 1, 1],
        "board":    [1, 1, 1, 1],
        "node_pos": [1, 1, 2, 2],
    })
    FA = {"n1": 1.0, "n2": 3.0, "n3": 5.0, "n4": 7.0}

    gfd, n_groups, n_nan = build_position_group_hash_fa(fp_topo, FA)

    # group mean check
    if abs(gfd["n1"] - 2.0) < 1e-9 and abs(gfd["n2"] - 2.0) < 1e-9:
        print("  PASS: group A nodes both get group mean 2.0")
    else:
        msg = f"  FAIL: group A means {gfd['n1']}, {gfd['n2']} (expected 2.0)"
        print(msg); failures.append(msg)

    if abs(gfd["n3"] - 6.0) < 1e-9 and abs(gfd["n4"] - 6.0) < 1e-9:
        print("  PASS: group B nodes both get group mean 6.0")
    else:
        msg = f"  FAIL: group B means {gfd['n3']}, {gfd['n4']} (expected 6.0)"
        print(msg); failures.append(msg)

    if n_groups == 2 and n_nan == 0:
        print("  PASS: n_groups=2, n_nan=0")
    else:
        msg = f"  FAIL: n_groups={n_groups}, n_nan={n_nan}"
        print(msg); failures.append(msg)

    # NaN fill: replace n4 with NaN -> global mean of (1,3,5) = 3.0 -> group B mean = (5+3)/2 = 4.0
    FA_nan = {"n1": 1.0, "n2": 3.0, "n3": 5.0, "n4": None}
    import numpy as _np
    FA_nan2 = {k: (float(v) if v is not None else float("nan")) for k, v in FA_nan.items()}
    gfd2, _, n_nan2 = build_position_group_hash_fa(fp_topo, FA_nan2)
    if n_nan2 == 1:
        print("  PASS: n_nan=1 for one NaN FA node")
    else:
        msg = f"  FAIL: expected n_nan=1, got {n_nan2}"
        print(msg); failures.append(msg)

    # global mean of finite values: (1+3+5)/3 = 3.0; group B: (5+3)/2 = 4.0
    if abs(gfd2["n3"] - 4.0) < 1e-9 and abs(gfd2["n4"] - 4.0) < 1e-9:
        print("  PASS: NaN FA fills with global mean before group mean")
    else:
        msg = f"  FAIL: group B with NaN fill: n3={gfd2['n3']}, n4={gfd2['n4']} (expected 4.0)"
        print(msg); failures.append(msg)

    # Select: with group_mean(A)=2.0 < group_mean(B)=6.0, ascending sort should prefer A nodes
    scen_seed = 42
    event_uid = "test:event:001"
    sel2 = select_position_group_hash(["n1", "n2", "n3", "n4"], 2, gfd, scen_seed, event_uid)
    if set(sel2) == {"n1", "n2"}:
        print("  PASS: select k=2 returns both group-A (cooler) nodes")
    else:
        msg = f"  FAIL: expected {{n1, n2}}, got {set(sel2)}"
        print(msg); failures.append(msg)

    # Within tied group: deterministic and changes with event_uid
    sel_all = select_position_group_hash(["n1", "n2"], 1, gfd, scen_seed, event_uid)
    sel_all2 = select_position_group_hash(["n1", "n2"], 1, gfd, scen_seed, event_uid)
    if sel_all == sel_all2:
        print("  PASS: select_position_group_hash is deterministic")
    else:
        msg = "  FAIL: non-deterministic within-group selection"
        print(msg); failures.append(msg)

    sel_diff_uid = select_position_group_hash(["n1", "n2"], 1, gfd, scen_seed, "other:event")
    # With different event_uid, the hash tie-break may produce different result (very likely)
    print(f"  INFO: different event_uid gives {'different' if sel_diff_uid != sel_all else 'same (hash collision)'} selection")

    # None event_uid handled as "unrestricted"
    sel_none = select_position_group_hash(["n1", "n2"], 1, gfd, scen_seed, None)
    sel_unr  = select_position_group_hash(["n1", "n2"], 1, gfd, scen_seed, "unrestricted")
    if sel_none == sel_unr:
        print("  PASS: event_uid=None treated as 'unrestricted'")
    else:
        msg = "  FAIL: event_uid=None not equivalent to 'unrestricted'"
        print(msg); failures.append(msg)

    # k=0 and k=all edge cases
    if select_position_group_hash(["n1", "n2"], 0, gfd, scen_seed, event_uid) == []:
        print("  PASS: k=0 returns []")
    else:
        msg = "  FAIL: k=0 should return []"
        print(msg); failures.append(msg)

    sel_full = select_position_group_hash(["n1", "n2", "n3", "n4"], 4, gfd, scen_seed, event_uid)
    if sorted(sel_full) == sorted(["n1", "n2", "n3", "n4"]):
        print("  PASS: k=len(available) returns all nodes")
    else:
        msg = "  FAIL: k=len(available) did not return all nodes"
        print(msg); failures.append(msg)

    # Summary
    print()
    if failures:
        print(f"FAILED: {len(failures)} test(s)")
        for f in failures: print(f"  {f}")
        sys.exit(1)
    else:
        print("ALL TESTS PASSED")


if __name__ == "__main__":
    _run_unit_tests()
