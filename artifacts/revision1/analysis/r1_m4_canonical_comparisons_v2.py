#!/usr/bin/env python3
"""
M4 Canonical Comparisons v2.

m4_canonical_comparisons.json is superseded because it embedded defective
crossing intervals from the original summarizer. This script:

  1. Audits ALL crossings in the three source files for inverted brackets
     (C_upper < C_lower when both are finite and non-right-censored).
  2. Reconstructs each defective crossing from its source lambda_rows
     using the conservative first-violation estimand:
       C_upper = first evaluated violating point, sorted by capacity_unlock_pct
       C_lower = last feasible point below C_upper in that sort order
       feasible re-entries after first violation are excluded
  3. Overrides defective crossings before computing all canonical comparisons.
  4. Asserts delta_lo <= delta_hi for every scenario pair.
  5. Prints an old-vs-new table and saves m4_canonical_comparisons_v2.json.

Source files remain frozen and are not modified.
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import json, pathlib
import numpy as np

OUT_DIR        = pathlib.Path(__file__).resolve().parents[3] / "artifacts" / "revision1" / "results"
V5_PATH        = OUT_DIR / "m4_fair_baselines.json"
RAND_PATH      = OUT_DIR / "m4_random_canonical.json"
CANON_POL_PATH = OUT_DIR / "m4_canonical_policies.json"
OLD_COMP_PATH  = OUT_DIR / "m4_canonical_comparisons.json"
OUT_FILE       = OUT_DIR / "m4_canonical_comparisons_v2.json"

HELD_OUT_START = 5
N_BOOTSTRAP    = 5000
BOOTSTRAP_SEED = 9999


def jf(v):
    if v is None: return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f


# ══════════════════════════════════════════════════════════════════════
# Crossing reconstruction from lambda_rows
# ══════════════════════════════════════════════════════════════════════

def reconstruct_crossing(lambda_rows_for_policy: list) -> dict:
    """Conservative first-violation estimand applied to evaluated lambda rows."""
    pts = sorted(lambda_rows_for_policy,
                 key=lambda x: x.get("capacity_unlock_pct", 0.0))

    # Assert no duplicate capacity with conflicting feasibility
    seen = {}
    for p in pts:
        c   = round(p.get("capacity_unlock_pct", 0.0), 10)
        inf = bool(p.get("infeasible", False))
        if c in seen:
            assert seen[c] == inf, (
                f"Duplicate capacity {c:.6f}% with conflicting feasibility: "
                f"{seen[c]} vs {inf}")
        seen[c] = inf

    if not pts:
        return {"status": "no_data", "C_lower_pct": None, "C_upper_pct": None,
                "first_binding_constraint": None}

    if pts[0].get("infeasible", False):
        return {"status": "left_boundary",
                "C_lower_pct": 0.0, "C_upper_pct": 0.0,
                "first_binding_constraint": pts[0].get("first_binding")}

    c_lower = None
    c_upper = None
    first_binding = None

    for p in pts:
        cap = p.get("capacity_unlock_pct", 0.0)
        inf = bool(p.get("infeasible", False))
        if not inf:
            if c_upper is None:           # feasible before first violation
                c_lower = cap
        else:
            if c_upper is None:           # first violation
                c_upper       = cap
                first_binding = p.get("first_binding")
            # subsequent violations or feasible re-entries ignored

    if c_upper is None:
        c_lower_val = pts[-1].get("capacity_unlock_pct", 0.0)
        return {"status": "right_censored",
                "C_lower_pct": c_lower_val, "C_upper_pct": None,
                "first_binding_constraint": None}

    assert c_lower is not None
    assert c_lower <= c_upper + 1e-12, (
        f"STILL INVERTED: C_lower={c_lower:.8f} C_upper={c_upper:.8f}")

    return {"status": "exact_bracket",
            "C_lower_pct": c_lower,
            "C_upper_pct": c_upper,
            "first_binding_constraint": first_binding}


# ══════════════════════════════════════════════════════════════════════
# Load source files
# ══════════════════════════════════════════════════════════════════════
v5        = json.loads(V5_PATH.read_text())
rand      = json.loads(RAND_PATH.read_text())
canon_pol = json.loads(CANON_POL_PATH.read_text())
old_comp  = json.loads(OLD_COMP_PATH.read_text())

v5_by_sc        = {sr["scenario_idx"]: sr for sr in v5["scenario_results"]}
rand_by_sc      = {sr["scenario_idx"]: sr for sr in rand["scenario_results"]}
canon_pol_by_sc = {sr["scenario_idx"]: sr for sr in canon_pol["scenario_results"]}

# Build mutable crossing dicts (we will patch the defective entries)
def extract_cx(by_sc: dict, pol: str) -> dict:
    return {s: dict(sr["crossings"][pol]) for s, sr in by_sc.items()
            if pol in sr["crossings"]}

cx_fp      = extract_cx(v5_by_sc,        "full_fp")
cx_loc_v5  = extract_cx(v5_by_sc,        "full_loc")   # sensitivity table only
cx_loc_can = extract_cx(canon_pol_by_sc,  "full_loc")
cx_spread  = extract_cx(v5_by_sc,        "full_fp_spread")
cx_rand_can= extract_cx(rand_by_sc,      "full_random")

# ══════════════════════════════════════════════════════════════════════
# [1] Audit — find all inverted brackets across all three source files
# ══════════════════════════════════════════════════════════════════════
print("=" * 70)
print("FULL CROSSING AUDIT — all three source files")
print("=" * 70)

SOURCE_AUDIT = [
    ("v5",    v5_by_sc),
    ("canon", canon_pol_by_sc),
    ("rand",  rand_by_sc),
]
all_inverted = []
for src_tag, by_sc in SOURCE_AUDIT:
    for s, sr in sorted(by_sc.items()):
        for pol, cx in sr["crossings"].items():
            lo = cx.get("C_lower_pct"); hi = cx.get("C_upper_pct")
            if lo is None or hi is None: continue
            if cx.get("status") == "right_censored": continue
            if hi < lo - 1e-12:
                all_inverted.append((src_tag, s, pol, lo, hi, hi - lo))
                print(f"  [{src_tag}] sc{s:2d} {pol:16s}: lo={lo:.6f}%  "
                      f"hi={hi:.6f}%  gap={hi-lo:+.6f}pp")

print(f"\n  Total inverted: {len(all_inverted)}")

# ══════════════════════════════════════════════════════════════════════
# [2] Reconstruct each from lambda_rows
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("RECONSTRUCTION — first-violation estimand from lambda_rows")
print(f"{'='*70}")

# Map each defective (source, scenario, policy) to the cx dict to patch and
# the lambda_rows source.
RECONSTRUCT_SPEC = [
    # (src_tag, s_idx, pol,         cx_dict_to_patch, lambda_rows_from)
    ("v5",    8,  "full_fp_spread", cx_spread,  v5_by_sc),
    ("v5",    13, "full_loc",       cx_loc_v5,  v5_by_sc),
    ("v5",    23, "full_fp",        cx_fp,      v5_by_sc),
    ("canon", 4,  "full_loc",       cx_loc_can, canon_pol_by_sc),
    ("canon", 7,  "full_loc",       cx_loc_can, canon_pol_by_sc),
    ("canon", 8,  "full_loc",       cx_loc_can, canon_pol_by_sc),
]

overrides_applied = {}
for src_tag, s_idx, pol, cx_dict, src_by_sc in RECONSTRUCT_SPEC:
    lambda_rows = src_by_sc[s_idx]["lambda_rows"].get(pol, [])
    assert lambda_rows, f"No lambda_rows for sc{s_idx} {pol} in {src_tag}"

    old_cx  = cx_dict.get(s_idx, {})
    new_cx  = reconstruct_crossing(lambda_rows)

    old_lo = old_cx.get("C_lower_pct", "?")
    old_hi = old_cx.get("C_upper_pct", "?")
    new_lo = new_cx["C_lower_pct"]
    new_hi = new_cx.get("C_upper_pct", "rc")

    cx_dict[s_idx] = new_cx
    overrides_applied[f"sc{s_idx}_{pol}_{src_tag}"] = {
        "src": src_tag, "scenario_idx": s_idx, "policy": pol,
        "old": {"C_lower_pct": old_lo, "C_upper_pct": old_hi},
        "new": {"C_lower_pct": new_lo, "C_upper_pct": new_hi},
    }

    gap_old = (old_hi - old_lo) if isinstance(old_lo, float) and isinstance(old_hi, float) else float("nan")
    gap_new = (new_hi - new_lo) if isinstance(new_hi, float) else float("nan")
    print(f"  [{src_tag}] sc{s_idx:2d} {pol:16s}: "
          f"[{old_lo:.4f}%, {old_hi:.4f}%]  ->  "
          f"[{new_lo:.4f}%, {new_hi:.4f}%]  "
          f"(gap {gap_old:+.4f} -> {gap_new:+.4f} pp)")

print(f"\n  {len(overrides_applied)} crossings reconstructed.")

# ══════════════════════════════════════════════════════════════════════
# [3] Canonical comparison logic (identical to original script)
# ══════════════════════════════════════════════════════════════════════

def interval_compare(cx_a: dict, cx_b: dict, label: str = "") -> dict:
    lo_a = cx_a["C_lower_pct"]
    hi_a = cx_a["C_upper_pct"] if cx_a.get("C_upper_pct") is not None else lo_a
    lo_b = cx_b["C_lower_pct"]
    hi_b = cx_b["C_upper_pct"] if cx_b.get("C_upper_pct") is not None else lo_b
    d_lo = lo_a - hi_b
    d_hi = hi_a - lo_b
    assert d_lo <= d_hi + 1e-12, (
        f"INVERTED DELTA {label}: d_lo={d_lo:.10f} d_hi={d_hi:.10f}\n"
        f"  A: lo={lo_a} hi={hi_a}  B: lo={lo_b} hi={hi_b}")
    if d_lo > 0:   verdict = "definitely_A_better"
    elif d_hi < 0: verdict = "definitely_B_better"
    else:          verdict = "indistinguishable"
    return {"delta_lo": jf(d_lo), "delta_hi": jf(d_hi), "verdict": verdict,
            "C_lower_A": jf(lo_a), "C_upper_A": jf(hi_a),
            "C_lower_B": jf(lo_b), "C_upper_B": jf(hi_b)}


def bootstrap_median_ci(vals: list, n_boot: int, seed: int) -> dict:
    a   = np.array(vals, dtype=float)
    rng = np.random.default_rng(seed)
    meds = [float(np.median(rng.choice(a, size=len(a), replace=True)))
            for _ in range(n_boot)]
    return {
        "median"  : float(np.median(a)),
        "ci_lo_95": float(np.percentile(meds, 2.5)),
        "ci_hi_95": float(np.percentile(meds, 97.5)),
        "q1"      : float(np.percentile(a, 25)),
        "q3"      : float(np.percentile(a, 75)),
        "n"       : len(vals),
    }


def summarize_pair(name_a: str, name_b: str,
                   cx_a_by_sc: dict, cx_b_by_sc: dict,
                   scenarios: list) -> dict:
    rows = []
    for s in scenarios:
        if s not in cx_a_by_sc or s not in cx_b_by_sc:
            continue
        cmp = interval_compare(cx_a_by_sc[s], cx_b_by_sc[s],
                               label=f"sc{s} {name_a} vs {name_b}")
        cmp["scenario_idx"] = s
        rows.append(cmp)

    n       = len(rows)
    n_def_a = sum(1 for r in rows if r["verdict"] == "definitely_A_better")
    n_ind   = sum(1 for r in rows if r["verdict"] == "indistinguishable")
    n_def_b = sum(1 for r in rows if r["verdict"] == "definitely_B_better")

    dlo_vals = [r["delta_lo"] for r in rows if r["delta_lo"] is not None]
    dhi_vals = [r["delta_hi"] for r in rows if r["delta_hi"] is not None]
    clo_a    = [r["C_lower_A"] for r in rows if r["C_lower_A"] is not None]
    clo_b    = [r["C_lower_B"] for r in rows if r["C_lower_B"] is not None]

    dlo_ci = bootstrap_median_ci(dlo_vals, N_BOOTSTRAP, BOOTSTRAP_SEED) if dlo_vals else None
    dhi_ci = bootstrap_median_ci(dhi_vals, N_BOOTSTRAP, BOOTSTRAP_SEED) if dhi_vals else None

    print(f"\n  {name_a} vs {name_b} (n={n}):")
    print(f"    Definitely A better: {n_def_a}/{n} ({100*n_def_a/n:.1f}%)")
    print(f"    Indistinguishable:   {n_ind}/{n}")
    print(f"    Definitely B better: {n_def_b}/{n}")
    if dlo_ci:
        print(f"    delta_lo: median={dlo_ci['median']:+.4f} pp  "
              f"95% CI [{dlo_ci['ci_lo_95']:+.4f}, {dlo_ci['ci_hi_95']:+.4f}]  "
              f"Q1={dlo_ci['q1']:+.4f}  Q3={dlo_ci['q3']:+.4f}")
    if dhi_ci:
        print(f"    delta_hi: median={dhi_ci['median']:+.4f} pp  "
              f"95% CI [{dhi_ci['ci_lo_95']:+.4f}, {dhi_ci['ci_hi_95']:+.4f}]  "
              f"Q1={dhi_ci['q1']:+.4f}  Q3={dhi_ci['q3']:+.4f}")
    if clo_a:
        print(f"    C_lower medians: A={float(np.median(clo_a)):.4f}%  "
              f"B={float(np.median(clo_b)):.4f}%")

    return {
        "name_A"             : name_a,
        "name_B"             : name_b,
        "scenarios"          : scenarios,
        "n"                  : n,
        "n_definitely_A"     : n_def_a,
        "n_indistinguishable": n_ind,
        "n_definitely_B"     : n_def_b,
        "pct_definitely_A"   : round(100 * n_def_a / n, 1) if n else None,
        "delta_lo_ci"        : dlo_ci,
        "delta_hi_ci"        : dhi_ci,
        "C_lower_A_median"   : jf(float(np.median(clo_a))) if clo_a else None,
        "C_lower_B_median"   : jf(float(np.median(clo_b))) if clo_b else None,
        "scenario_rows"      : rows,
    }


# ══════════════════════════════════════════════════════════════════════
# [4] Compute comparisons
# ══════════════════════════════════════════════════════════════════════
all_30   = list(range(30))
held_out = list(range(HELD_OUT_START, 30))

print(f"\n{'='*70}")
print("BASELINE COMPARISONS (all 30 scenarios)")
print(f"{'='*70}")

comparisons = {}
comparisons["fp_vs_canonical_rand"]     = summarize_pair(
    "full_fp",            "canonical_random", cx_fp,      cx_rand_can, all_30)
comparisons["loc_vs_canonical_rand"]    = summarize_pair(
    "full_loc_canonical", "canonical_random", cx_loc_can, cx_rand_can, all_30)
comparisons["spread_vs_canonical_rand"] = summarize_pair(
    "full_fp_spread",     "canonical_random", cx_spread,  cx_rand_can, held_out)

print(f"\n{'='*70}")
print("PRIMARY POLICY-DESIGN COMPARISONS (held-out sc5-29, n=25)")
print(f"{'='*70}")
comparisons["spread_vs_fp"] = summarize_pair(
    "full_fp_spread", "full_fp",            cx_spread, cx_fp,      held_out)
comparisons["spread_vs_canonical_loc"] = summarize_pair(
    "full_fp_spread", "full_loc_canonical", cx_spread, cx_loc_can, held_out)

print(f"\n  All delta_lo <= delta_hi assertions passed.")

# ══════════════════════════════════════════════════════════════════════
# [5] Old vs new comparison
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("OLD vs NEW COMPARISON TABLE")
print(f"{'='*70}")

CMP_KEYS = [
    ("fp_vs_canonical_rand",     "FP vs Random (n=30)"),
    ("loc_vs_canonical_rand",    "Location vs Random (n=30)"),
    ("spread_vs_canonical_rand", "FP-spread vs Random (held-out n=25)"),
    ("spread_vs_fp",             "FP-spread vs FP (held-out n=25)"),
    ("spread_vs_canonical_loc",  "FP-spread vs Location (held-out n=25)"),
]

print(f"\n{'Comparison':42s}  {'OLD verdicts':22s}  {'NEW verdicts':22s}  dlo_med change")
print("-" * 115)
for ck, lbl in CMP_KEYS:
    old = old_comp["comparisons"][ck]
    new = comparisons[ck]
    old_str = f"{old['n_definitely_A']}/{old['n']} def_A  {old['n_indistinguishable']} ind  {old['n_definitely_B']} def_B"
    new_str = f"{new['n_definitely_A']}/{new['n']} def_A  {new['n_indistinguishable']} ind  {new['n_definitely_B']} def_B"
    old_med = old["delta_lo_ci"]["median"]
    new_med = new["delta_lo_ci"]["median"]
    d_med   = new_med - old_med
    changed = "  <-- CHANGED" if (
        old["n_definitely_A"] != new["n_definitely_A"] or
        old["n_indistinguishable"] != new["n_indistinguishable"] or
        abs(d_med) > 1e-4
    ) else ""
    print(f"{lbl:42s}  {old_str:22s}  {new_str:22s}  "
          f"{old_med:+.4f} -> {new_med:+.4f} ({d_med:+.4f}pp){changed}")

print(f"\n{'='*70}")
print("SCENARIO-LEVEL VERDICT AND DELTA CHANGES")
print(f"{'='*70}")
for ck, lbl in CMP_KEYS:
    old_rows = {r["scenario_idx"]: r
                for r in old_comp["comparisons"][ck]["scenario_rows"]}
    new_rows = {r["scenario_idx"]: r
                for r in comparisons[ck]["scenario_rows"]}
    changes  = []
    for s, nr in sorted(new_rows.items()):
        if s not in old_rows: continue
        or_   = old_rows[s]
        v_chg = nr["verdict"] != or_["verdict"]
        d_chg = (abs(nr["delta_lo"] - or_["delta_lo"]) > 5e-5 or
                 abs(nr["delta_hi"] - or_["delta_hi"]) > 5e-5)
        if v_chg or d_chg:
            changes.append((s, or_, nr, v_chg))
    if changes:
        print(f"\n  {lbl}:")
        for s, or_, nr, v_chg in changes:
            vstr = f"  VERDICT: {or_['verdict']} -> {nr['verdict']}" if v_chg else ""
            print(f"    sc{s:2d}: dlo {or_['delta_lo']:+.6f} -> {nr['delta_lo']:+.6f}  "
                  f"dhi {or_['delta_hi']:+.6f} -> {nr['delta_hi']:+.6f}{vstr}")
    else:
        print(f"\n  {lbl}: no changes.")

# ══════════════════════════════════════════════════════════════════════
# [6] Save
# ══════════════════════════════════════════════════════════════════════
out = {
    "supersedes"         : "m4_canonical_comparisons.json",
    "note"               : (
        "Full crossing audit identified 6 inverted brackets across 3 source files. "
        "Each reconstructed using conservative first-violation estimand applied to "
        "evaluated lambda_rows: C_upper = first evaluated violating point sorted by "
        "capacity_unlock_pct; C_lower = last feasible below it; feasible re-entries "
        "excluded. Source files (m4_fair_baselines.json, m4_random_canonical.json, "
        "m4_canonical_policies.json) are not modified."
    ),
    "n_inverted_found"   : len(all_inverted),
    "n_reconstructed"    : len(overrides_applied),
    "overrides_applied"  : overrides_applied,
    "source_v5"          : "m4_fair_baselines.json",
    "source_random"      : "m4_random_canonical.json",
    "source_loc"         : "m4_canonical_policies.json",
    "n_bootstrap"        : N_BOOTSTRAP,
    "bootstrap_seed"     : BOOTSTRAP_SEED,
    "comparisons"        : comparisons,
}

OUT_FILE.write_text(json.dumps(out, indent=2))
print(f"\nSaved: {OUT_FILE}")
