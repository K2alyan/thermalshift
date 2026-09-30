#!/usr/bin/env python3
"""
M4 Selector Sensitivity Audit.

Quantifies how many tied values each policy selector can encounter so that
the canonical (score, hostname) tie-break requirement can be calibrated.

Reports for the frozen cohort+model artifacts:
  FP       — global FA_2024 uniqueness; number of equal-score pairs
  Location — location-score uniqueness; number of equal-score pairs
  FP-spread — FA_2024 ties within each cabinet (the only within-cabinet
               non-determinism after the cabinet-selection key was already
               deterministic via (occupancy, cabinet_id))
  Random   — always affected by hash order; fixed by sorted(available)

Also checks whether the v5 FP-spread cabinet-selection key was already
deterministic (it uses (temp[c], c) as min key, which is total-order).

Output: artifacts/revision1/results/m4_selector_audit.json
        + human-readable summary printed to stdout
"""

import json, os, sys, io
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[3]
P1_DIR    = REPO_ROOT / "artifacts" / "phase1" / "analysis"
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR   = REV1_DIR / "results"
TABLE_DIR = REV1_DIR / "tables"
DATA_DIR  = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

print("M4 Selector Sensitivity Audit")
print("=" * 70)

# ── Load fingerprint ────────────────────────────────────────────────────
fp_df = pd.read_parquet(P1_DIR / "phase3a_fingerprint_2024.parquet")
fp_df.index.name = "node"
FA_dict     = fp_df["FA_2024"].to_dict()
cohort_list = sorted(fp_df.index.tolist())
n_cohort    = len(cohort_list)
FA_vals     = np.array([FA_dict[n] for n in cohort_list])

print(f"\n[1] FA_2024 (full-population fingerprint score)  n_nodes={n_cohort}")
n_unique_FA = len(np.unique(FA_vals))
n_dup_FA    = n_cohort - n_unique_FA
from collections import Counter
fa_counts   = Counter(round(v, 12) for v in FA_vals)
max_mult_FA = max(fa_counts.values())
dup_groups  = sum(1 for v in fa_counts.values() if v > 1)

print(f"    n_unique FA_2024:      {n_unique_FA:,}  ({100*n_unique_FA/n_cohort:.2f}% of {n_cohort})")
print(f"    n_duplicated values:   {n_dup_FA:,}  across {dup_groups} groups")
print(f"    max multiplicity:      {max_mult_FA}")
if n_dup_FA == 0:
    print("    => FP selector is HASH-IMMUNE: no FA_2024 ties exist globally.")
    print("       np.argsort tie-break can never be triggered.")
else:
    print(f"    => FP selector IS VULNERABLE: {n_dup_FA} nodes share an FA_2024 value.")

fp_result = {
    "n_nodes": n_cohort,
    "n_unique_FA": n_unique_FA,
    "n_duplicated_nodes": n_dup_FA,
    "n_duplicated_groups": dup_groups,
    "max_multiplicity": max_mult_FA,
    "hash_immune": (n_dup_FA == 0),
}

# ── Location scores ─────────────────────────────────────────────────────
print(f"\n[2] Location scores (position-mean FA_2024 per physical slot)")
fp_topo = pd.read_csv(TABLE_DIR / "fp_node_topology.csv")
fp_topo["pos_key"] = (fp_topo["chassis"].astype(str) + "_" +
                      fp_topo["slot"].astype(str)    + "_" +
                      fp_topo["board"].astype(str)   + "_" +
                      fp_topo["node_pos"].astype(str))
fp_topo["FA_2024"] = fp_topo["hostname"].map(FA_dict)
pos_mean   = fp_topo.groupby("pos_key")["FA_2024"].mean().rename("FA_loc")
fp_topo    = fp_topo.join(pos_mean, on="pos_key")
glob_mean  = float(fp_topo["FA_loc"].dropna().mean())
LOC_FA     = {row["hostname"]: (row["FA_loc"] if not pd.isna(row["FA_loc"]) else glob_mean)
              for _, row in fp_topo.iterrows()}

loc_vals   = np.array([LOC_FA.get(n, glob_mean) for n in cohort_list])
n_unique_L = len(np.unique(np.round(loc_vals, 12)))
n_dup_L    = n_cohort - n_unique_L
loc_counts = Counter(round(v, 12) for v in loc_vals)
max_mult_L = max(loc_counts.values())
dup_grps_L = sum(1 for v in loc_counts.values() if v > 1)

print(f"    n_unique location scores: {n_unique_L:,}  ({100*n_unique_L/n_cohort:.2f}%)")
print(f"    n_duplicated nodes:       {n_dup_L:,}  across {dup_grps_L} groups")
print(f"    max multiplicity:         {max_mult_L}")
if n_dup_L == 0:
    print("    => Location selector is HASH-IMMUNE: no location-score ties.")
else:
    print(f"    => Location selector IS VULNERABLE: {n_dup_L} nodes share a location score.")
    # Show how ties arise: nodes in the same position slot share the same mean FA
    n_positions = fp_topo["pos_key"].nunique()
    nodes_per_pos = fp_topo.groupby("pos_key")["hostname"].count()
    multi_pos = (nodes_per_pos > 1).sum()
    print(f"       ({multi_pos} position slots have >1 node; those nodes share identical loc score)")

loc_result = {
    "n_unique_scores": n_unique_L,
    "n_duplicated_nodes": n_dup_L,
    "n_duplicated_groups": dup_grps_L,
    "max_multiplicity": max_mult_L,
    "hash_immune": (n_dup_L == 0),
}

# ── FP-spread: within-cabinet FA_2024 ties ──────────────────────────────
print(f"\n[3] FP-spread within-cabinet FA_2024 ties")
fleet_topo  = pd.read_csv(TABLE_DIR / "fleet_node_topology.csv")
node_to_cab = dict(zip(fleet_topo["hostname"].values,
                       fleet_topo["cabinet"].values.astype(int)))
fp_cab = {n: node_to_cab[n] for n in cohort_list if n in node_to_cab}

cab_groups: dict[int, list] = defaultdict(list)
for n in cohort_list:
    c = fp_cab.get(n, -1)
    if c >= 0:
        cab_groups[c].append(n)

n_cabs_total   = len(cab_groups)
cabs_with_ties = 0
total_dup_within_cab = 0
max_mult_within_cab  = 0
cab_tie_details: list[dict] = []

for c, nodes in cab_groups.items():
    fa_c = [FA_dict[n] for n in nodes]
    cnt  = Counter(round(v, 12) for v in fa_c)
    dups = sum(v - 1 for v in cnt.values() if v > 1)
    if dups > 0:
        cabs_with_ties += 1
        total_dup_within_cab += dups
        mx = max(cnt.values())
        max_mult_within_cab = max(max_mult_within_cab, mx)
        cab_tie_details.append({"cabinet": c, "n_nodes": len(nodes),
                                 "n_dup": dups, "max_mult": mx})

print(f"    n_cabinets with any FA tie:  {cabs_with_ties} / {n_cabs_total}")
print(f"    total duplicated node-pairs: {total_dup_within_cab}")
print(f"    max multiplicity within cab: {max_mult_within_cab}")
if cabs_with_ties == 0:
    print("    => FP-spread within-cabinet sort is HASH-IMMUNE: no FA ties per cabinet.")
    print("       Cabinet-selection key (occupancy, cab_id) was already deterministic in v5.")
else:
    print(f"    => FP-spread IS VULNERABLE in {cabs_with_ties} cabinets.")
    for d in sorted(cab_tie_details, key=lambda x: -x["n_dup"])[:5]:
        print(f"       cab={d['cabinet']:3d}  n_nodes={d['n_nodes']:3d}  "
              f"n_dup={d['n_dup']}  max_mult={d['max_mult']}")

# Cabinet-selection key analysis (v5 code)
print(f"\n    Cabinet-selection key in v5 select_fp_spread:")
print(f"      min(cab_nodes, key=lambda c: (temp.get(c, 0), c))")
print(f"      This is a TOTAL ORDER over integer cabinet IDs — deterministic.")
print(f"      Cabinet-selection ties on occupancy are broken by cabinet ID (int).")
print(f"      => The only non-determinism is within-cabinet node order for equal FA.")

spread_result = {
    "n_cabinets": n_cabs_total,
    "n_cabs_with_fa_ties": cabs_with_ties,
    "total_dup_nodes_within_cab": total_dup_within_cab,
    "max_multiplicity_within_cab": max_mult_within_cab,
    "cabinet_selection_hash_immune": True,  # (occupancy, cab_id) is total order
    "within_cabinet_sort_hash_immune": (cabs_with_ties == 0),
    "cab_tie_details": cab_tie_details,
}

# ── Random ──────────────────────────────────────────────────────────────
print(f"\n[4] Random selector")
print(f"    select_random draws rng.choice(n, size=k) from a list built by list(set).")
print(f"    list(set) is ALWAYS hash-order-dependent (no ties needed).")
print(f"    Fix: sorted(available) before rng.choice  [applied in canonical scripts].")
print(f"    => Random is ALWAYS VULNERABLE in v5; always fixed in canonical.")

# ── Compact ─────────────────────────────────────────────────────────────
print(f"\n[5] Compact selector")
print(f"    Builds cab_groups by iterating available (hash-ordered).")
print(f"    Within each cabinet, draws rng.choice(len(nodes), ...) by index.")
print(f"    => Vulnerable IF within-cabinet node ordering matters for rng.choice.")
print(f"    Cabinet-level sorting key: (-len(cab_groups[c]), rng.integers(0,1000))")
print(f"    That uses RNG to break ties on cabinet size, so it is intentionally random")
print(f"    but depends on the ordering of keys in cab_groups (hash-ordered dict).")
print(f"    Fix: sorted(available) before building cab_groups [applied in canonical].")
print(f"    Note: Compact does not appear in the primary paper headline comparisons.")

# ── Summary ─────────────────────────────────────────────────────────────
print(f"\n{'='*70}")
print("SUMMARY")
print(f"{'='*70}")

rows = [
    ("Random",    "Always",        "sorted(available) before rng.choice"),
    ("FP",        "If FA ties",    f"n_dup={n_dup_FA} => {'IMMUNE' if n_dup_FA==0 else 'VULNERABLE'}"),
    ("Location",  "If score ties", f"n_dup={n_dup_L} => {'IMMUNE' if n_dup_L==0 else 'VULNERABLE'}"),
    ("FP-spread", "If within-cab FA ties",
     f"cab_sel: deterministic; within-cab: n_cabs_affected={cabs_with_ties}"),
    ("Compact",   "Always (key ordering)", "not in primary comparisons"),
]
col_w = [12, 22, 50]
hdr   = f"  {'Policy':<{col_w[0]}} {'Hash-dep condition':<{col_w[1]}} {'Status / fix'}"
print(hdr)
print("  " + "-" * 80)
for name, cond, status in rows:
    print(f"  {name:<{col_w[0]}} {cond:<{col_w[1]}} {status}")

print(f"\n  RECOMMENDATION:")
if n_dup_FA == 0 and n_dup_L == 0 and cabs_with_ties == 0:
    print("  FP, Location, and FP-spread are HASH-IMMUNE in this dataset.")
    print("  Only Random requires a canonical rerun for exact reproducibility.")
    print("  However, canonical selectors should still be used for future-proofing.")
else:
    vulnerable = []
    if n_dup_FA > 0:   vulnerable.append("FP")
    if n_dup_L  > 0:   vulnerable.append("Location")
    if cabs_with_ties > 0: vulnerable.append("FP-spread")
    print(f"  VULNERABLE policies requiring canonical rerun: {', '.join(vulnerable)}")
    print("  Run r1_m4_canonical_policies.py to get deterministic outputs for all.")

# ── Save ────────────────────────────────────────────────────────────────
out = {
    "full_fp": fp_result,
    "full_loc": loc_result,
    "full_fp_spread": spread_result,
    "full_random": {
        "always_vulnerable": True,
        "fix": "sorted(available) before rng.choice",
        "canonical_rerun": "m4_random_canonical.json",
    },
    "full_compact": {
        "vulnerable": True,
        "note": "Not in primary paper headline comparisons; "
                "fix applied in canonical scripts nonetheless.",
    },
}
out_path = OUT_DIR / "m4_selector_audit.json"
out_path.write_text(json.dumps(out, indent=2))
print(f"\nSaved: {out_path}")
