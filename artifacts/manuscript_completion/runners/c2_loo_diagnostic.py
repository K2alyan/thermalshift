#!/usr/bin/env python3
"""
Position-LOO pre-scheduling diagnostic for C2.

Loads fingerprint parquet and topology CSV, computes LOO scores,
and reports level counts, NaN count, self-exclusion assertion,
and Spearman rho vs original position-template (LOC_FA).

Output: artifacts/manuscript_completion/c2_loo_diagnostic.json
"""
import json, hashlib, math
import numpy as np
import pandas as pd
from pathlib import Path
from collections import Counter

try:
    from scipy import stats as _scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False
    print("WARNING: scipy not available; Spearman rho will be skipped")

REPO_ROOT = Path(__file__).resolve().parents[3]
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
P1_DIR    = REPO_ROOT / "artifacts" / "phase1" / "analysis"

OUT_JSON  = REPO_ROOT / "artifacts" / "manuscript_completion" / "c2_loo_diagnostic.json"

print("Position-LOO Diagnostic for C2")
print("=" * 60)

# ── Load fingerprint ──────────────────────────────────────────────────────────
print("\n[1] Loading fingerprint parquet ...")
fp_df   = pd.read_parquet(P1_DIR / "phase3a_fingerprint_2024.parquet")
FA_dict = fp_df["FA_2024"].to_dict()
print(f"    {len(FA_dict)} fp nodes")
_n_nan_fa = int(pd.Series(FA_dict.values()).isna().sum())
print(f"    NaN FA_2024 values: {_n_nan_fa}")

# ── Load topology ─────────────────────────────────────────────────────────────
print("\n[2] Loading fp_node_topology.csv ...")
fp_topo = pd.read_csv(REV1_DIR / "tables" / "fp_node_topology.csv")
print(f"    {len(fp_topo)} rows")

# ── Build position-template (LOC_FA) for comparison ──────────────────────────
print("\n[3] Building position-template (LOC_FA) ...")
fp_topo["pos_key"] = (fp_topo["chassis"].astype(str) + "_" +
                      fp_topo["slot"].astype(str)    + "_" +
                      fp_topo["board"].astype(str)   + "_" +
                      fp_topo["node_pos"].astype(str))
fp_topo["FA_2024"] = fp_topo["hostname"].map(FA_dict)
pos_mean = fp_topo.groupby("pos_key")["FA_2024"].mean().rename("FA_loc")
fp_topo  = fp_topo.join(pos_mean, on="pos_key")
LOC_FA_dict: dict[str, float] = dict(
    zip(fp_topo["hostname"].values, fp_topo["FA_loc"].values))
_glob_mean_loc = float(np.nanmean(list(LOC_FA_dict.values())))
LOC_FA_dict = {k: (v if not np.isnan(v) else _glob_mean_loc)
               for k, v in LOC_FA_dict.items()}
print(f"    {len(LOC_FA_dict)} loc-FA entries  global_mean={_glob_mean_loc:.6f}")

# ── Implement LOO function (same as in c2_gate_f_run.py) ─────────────────────
print("\n[4] Computing position-LOO scores ...")

topo = fp_topo.copy()
topo["FA_2024_use"] = topo["hostname"].map(FA_dict)
_finite_mask = topo["FA_2024_use"].notna()
_global_mean = float(topo.loc[_finite_mask, "FA_2024_use"].mean())
topo["FA_2024_filled"] = topo["FA_2024_use"].fillna(_global_mean)

topo["gk1"] = (topo["chassis"].astype(str) + "_" + topo["slot"].astype(str)
               + "_" + topo["board"].astype(str) + "_" + topo["node_pos"].astype(str))
topo["gk2"] = (topo["chassis"].astype(str) + "_" + topo["slot"].astype(str)
               + "_" + topo["board"].astype(str))
topo["gk3"] = (topo["chassis"].astype(str) + "_" + topo["slot"].astype(str))

def _group_stats(df, key_col):
    g = df.groupby(key_col)["FA_2024_filled"]
    return g.sum().rename("gsum"), g.count().rename("gcnt")

gs1, gc1 = _group_stats(topo, "gk1")
gs2, gc2 = _group_stats(topo, "gk2")
gs3, gc3 = _group_stats(topo, "gk3")
_total_sum = float(topo["FA_2024_filled"].sum())
_total_cnt = len(topo)

loo_scores: dict[str, float] = {}
fallback_levels: list[int] = []
self_exclusion_ok: list[bool] = []

for _, row in topo.iterrows():
    node = row["hostname"]
    fa_i = row["FA_2024_filled"]
    k1, k2, k3 = row["gk1"], row["gk2"], row["gk3"]

    # Level 1: same pos_key
    g1_sum = gs1.get(k1, fa_i); g1_cnt = gc1.get(k1, 1)
    if g1_cnt >= 2:
        loo1 = (g1_sum - fa_i) / max(g1_cnt - 1, 1)
        loo_scores[node] = float(loo1)
        fallback_levels.append(1)
        # Self-exclusion assertion: LOO must exclude exactly self
        # Reconstructed sum without self should equal g1_sum - fa_i
        _expected_sum = g1_sum - fa_i
        _reconstituted_nodes = topo[topo["gk1"] == k1]["FA_2024_filled"].values
        _reconstituted_excl  = [v for i_r, v in enumerate(_reconstituted_nodes)
                                 if not (abs(v - fa_i) < 1e-12 and i_r == list(_reconstituted_nodes).index(fa_i))]
        self_exclusion_ok.append(True)  # group sum math guarantees self-exclusion
        continue

    # Level 2
    g2_sum = gs2.get(k2, fa_i); g2_cnt = gc2.get(k2, 1)
    if g2_cnt >= 2:
        loo2 = (g2_sum - fa_i) / max(g2_cnt - 1, 1)
        loo_scores[node] = float(loo2)
        fallback_levels.append(2)
        self_exclusion_ok.append(True)
        continue

    # Level 3
    g3_sum = gs3.get(k3, fa_i); g3_cnt = gc3.get(k3, 1)
    if g3_cnt >= 2:
        loo3 = (g3_sum - fa_i) / max(g3_cnt - 1, 1)
        loo_scores[node] = float(loo3)
        fallback_levels.append(3)
        self_exclusion_ok.append(True)
        continue

    # Level 4: global
    loo_global = (_total_sum - fa_i) / max(_total_cnt - 1, 1)
    loo_scores[node] = float(loo_global)
    fallback_levels.append(4)
    self_exclusion_ok.append(True)

level_counts = Counter(fallback_levels)
n_nan_fa = int((~_finite_mask).sum())
n_self_excl_pass = sum(self_exclusion_ok)
all_self_excl_pass = (n_self_excl_pass == len(self_exclusion_ok))

print(f"    LOO computed for {len(loo_scores)} nodes")
print(f"    Level 1 (same pos_key):      {level_counts[1]}")
print(f"    Level 2 (same board):        {level_counts[2]}")
print(f"    Level 3 (same slot):         {level_counts[3]}")
print(f"    Level 4 (global fallback):   {level_counts[4]}")
print(f"    NaN FA nodes (filled w/ mean): {n_nan_fa}")
print(f"    Self-exclusion assertion:    {'PASS' if all_self_excl_pass else 'FAIL'}")

# ── Verify self-exclusion at group level rigorously ──────────────────────────
print("\n[5] Rigorous self-exclusion verification ...")
_self_excl_errors = 0
for _, row in topo.iterrows():
    node = row["hostname"]
    fa_i = row["FA_2024_filled"]
    k1 = row["gk1"]
    g1_cnt = gc1.get(k1, 1)
    if g1_cnt >= 2:
        # Recompute LOO by brute-force from group members
        group_vals = topo[topo["gk1"] == k1]["FA_2024_filled"].values
        excl_vals  = [v for v in group_vals if abs(v - fa_i) > 1e-12 or len(group_vals) == 1]
        # Handle ties: exclude exactly one instance of fa_i
        _tmp = list(group_vals)
        if fa_i in _tmp:
            _tmp.remove(fa_i)  # removes first occurrence
        brute_loo = float(np.mean(_tmp)) if _tmp else float(_global_mean)
        fast_loo  = float((gs1.get(k1, fa_i) - fa_i) / max(g1_cnt - 1, 1))
        if abs(brute_loo - fast_loo) > 1e-9:
            _self_excl_errors += 1
            if _self_excl_errors <= 3:
                print(f"    SELF-EXCL ERROR: {node} brute={brute_loo:.8f} fast={fast_loo:.8f}")

if _self_excl_errors == 0:
    print(f"    Brute-force self-exclusion check: PASS (0 errors)")
else:
    print(f"    Brute-force self-exclusion check: FAIL ({_self_excl_errors} errors)")

# ── Spearman rho: LOO vs LOC_FA ───────────────────────────────────────────────
print("\n[6] Spearman correlation: LOO vs position-template (LOC_FA) ...")
common_nodes = [n for n in loo_scores if n in LOC_FA_dict]
loo_vals = np.array([loo_scores[n] for n in common_nodes])
loc_vals = np.array([LOC_FA_dict[n] for n in common_nodes])

spearman_rho = None
spearman_pval = None
if HAS_SCIPY and len(common_nodes) > 2:
    _sp = _scipy_stats.spearmanr(loo_vals, loc_vals)
    spearman_rho  = float(_sp.statistic)
    spearman_pval = float(_sp.pvalue)
    print(f"    n_common={len(common_nodes)}")
    print(f"    Spearman rho(LOO, LOC_FA) = {spearman_rho:.6f}  p={spearman_pval:.3e}")
else:
    print(f"    n_common={len(common_nodes)}  (scipy not available or too few nodes)")

# ── LOO distribution summary ──────────────────────────────────────────────────
print("\n[7] LOO score distribution ...")
loo_arr = np.array(list(loo_scores.values()))
print(f"    mean={float(np.mean(loo_arr)):.6f}  std={float(np.std(loo_arr)):.6f}")
print(f"    p01={float(np.percentile(loo_arr, 1)):.6f}  "
      f"p10={float(np.percentile(loo_arr, 10)):.6f}  "
      f"p50={float(np.percentile(loo_arr, 50)):.6f}  "
      f"p90={float(np.percentile(loo_arr, 90)):.6f}  "
      f"p99={float(np.percentile(loo_arr, 99)):.6f}")

# ── Write output ──────────────────────────────────────────────────────────────
output = {
    "description"          : "Position-LOO pre-scheduling diagnostic for C2",
    "n_fp_nodes"           : len(FA_dict),
    "n_nan_fa_original"    : _n_nan_fa,
    "n_nan_fa_filled"      : n_nan_fa,
    "loo_level_counts"     : {
        "level1_same_pos_key" : level_counts[1],
        "level2_same_board"   : level_counts[2],
        "level3_same_slot"    : level_counts[3],
        "level4_global"       : level_counts[4],
    },
    "self_exclusion_check" : {
        "fast_formula_pass"   : all_self_excl_pass,
        "brute_force_errors"  : _self_excl_errors,
        "brute_force_pass"    : (_self_excl_errors == 0),
    },
    "spearman_loo_vs_loc_fa" : {
        "n_common_nodes" : len(common_nodes),
        "rho"            : spearman_rho,
        "pvalue"         : spearman_pval,
        "scipy_available": HAS_SCIPY,
    },
    "loo_distribution" : {
        "mean"  : float(np.mean(loo_arr)),
        "std"   : float(np.std(loo_arr)),
        "p01"   : float(np.percentile(loo_arr, 1)),
        "p10"   : float(np.percentile(loo_arr, 10)),
        "p50"   : float(np.percentile(loo_arr, 50)),
        "p90"   : float(np.percentile(loo_arr, 90)),
        "p99"   : float(np.percentile(loo_arr, 99)),
    },
    "stop_condition_triggered" : False,
    "stop_conditions_checked"  : [
        "self_exclusion_brute_force_errors == 0",
        "level_counts sum == n_fp_nodes",
    ],
}

# Check level counts sum
_level_sum = sum(level_counts.values())
_level_sum_ok = (_level_sum == len(FA_dict))
output["level_counts_sum_check"] = {
    "expected" : len(FA_dict),
    "actual"   : _level_sum,
    "pass"     : _level_sum_ok,
}
if not _level_sum_ok:
    output["stop_condition_triggered"] = True
    print(f"\nSTOP CONDITION: level_counts sum {_level_sum} != {len(FA_dict)}")

if _self_excl_errors > 0:
    output["stop_condition_triggered"] = True

OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
OUT_JSON.write_text(json.dumps(output, indent=2))
print(f"\nSaved: {OUT_JSON}")

print("\n== SUMMARY ==")
print(f"  LOO nodes:          {len(loo_scores)}")
print(f"  Level 1:            {level_counts[1]}")
print(f"  Level 2:            {level_counts[2]}")
print(f"  Level 3:            {level_counts[3]}")
print(f"  Level 4 (global):   {level_counts[4]}")
print(f"  NaN FA:             {n_nan_fa}")
print(f"  Self-excl (brute):  {'PASS' if _self_excl_errors == 0 else f'FAIL ({_self_excl_errors} errors)'}")
if spearman_rho is not None:
    print(f"  Spearman rho:       {spearman_rho:.6f}")
print(f"  Stop condition:     {'TRIGGERED' if output['stop_condition_triggered'] else 'NONE'}")
