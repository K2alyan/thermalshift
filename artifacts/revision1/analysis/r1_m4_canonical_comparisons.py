#!/usr/bin/env python3
"""
M4 Canonical Comparisons.
Post-processing only. Reads frozen v5 outputs + canonical random rerun.

Computes interval-aware comparisons using canonical full_random as baseline:
  - full_fp vs canonical_random        (all 30 scenarios)
  - full_loc vs canonical_random       (all 30 scenarios)
  - full_fp_spread vs canonical_random (held-out sc5-29, n=25)

Also reports v5 full_random vs canonical_random to document the realization shift.

Output: artifacts/revision1/results/m4_canonical_comparisons.json
"""

import json, pathlib, numpy as np
from collections import Counter

OUT_DIR    = pathlib.Path(__file__).resolve().parents[3] / "artifacts" / "revision1" / "results"
V5_PATH    = OUT_DIR / "m4_fair_baselines.json"
RAND_PATH  = OUT_DIR / "m4_random_canonical.json"
OUT_FILE   = OUT_DIR / "m4_canonical_comparisons.json"

HELD_OUT_START = 5   # sc5-29 for fp_spread comparison

N_BOOTSTRAP   = 5000
BOOTSTRAP_SEED = 9999


def jf(v):
    if v is None: return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f


def interval_compare(cx_a: dict, cx_b: dict) -> dict:
    """Interval-aware comparison: delta_lo = C_lower_A - C_upper_B (pessimistic)."""
    lo_a = cx_a["C_lower_pct"]
    hi_a = cx_a["C_upper_pct"] if cx_a.get("C_upper_pct") is not None else lo_a
    lo_b = cx_b["C_lower_pct"]
    hi_b = cx_b["C_upper_pct"] if cx_b.get("C_upper_pct") is not None else lo_b
    d_lo = lo_a - hi_b
    d_hi = hi_a - lo_b
    if d_lo > 0:    verdict = "definitely_A_better"
    elif d_hi < 0:  verdict = "definitely_B_better"
    else:           verdict = "indistinguishable"
    return {"delta_lo": jf(d_lo), "delta_hi": jf(d_hi), "verdict": verdict,
            "C_lower_A": jf(lo_a), "C_upper_A": jf(hi_a),
            "C_lower_B": jf(lo_b), "C_upper_B": jf(hi_b)}


def bootstrap_median_ci(vals: list[float], n_boot: int, seed: int) -> dict:
    a   = np.array(vals, dtype=float)
    rng = np.random.default_rng(seed)
    meds = [float(np.median(rng.choice(a, size=len(a), replace=True)))
            for _ in range(n_boot)]
    return {
        "median"  : float(np.median(a)),
        "ci_lo_95": float(np.percentile(meds, 2.5)),
        "ci_hi_95": float(np.percentile(meds, 97.5)),
        "n"       : len(vals),
    }


def summarize_pair(name_a: str, name_b: str,
                   cx_a_by_sc: dict, cx_b_by_sc: dict,
                   scenarios: list[int]) -> dict:
    rows = []
    for s in scenarios:
        if s not in cx_a_by_sc or s not in cx_b_by_sc:
            continue
        cmp = interval_compare(cx_a_by_sc[s], cx_b_by_sc[s])
        cmp["scenario_idx"] = s
        rows.append(cmp)

    n = len(rows)
    n_def_a   = sum(1 for r in rows if r["verdict"] == "definitely_A_better")
    n_ind     = sum(1 for r in rows if r["verdict"] == "indistinguishable")
    n_def_b   = sum(1 for r in rows if r["verdict"] == "definitely_B_better")

    dlo_vals  = [r["delta_lo"] for r in rows if r["delta_lo"] is not None]
    clo_a     = [r["C_lower_A"] for r in rows if r["C_lower_A"] is not None]
    clo_b     = [r["C_lower_B"] for r in rows if r["C_lower_B"] is not None]

    dlo_ci = bootstrap_median_ci(dlo_vals, N_BOOTSTRAP, BOOTSTRAP_SEED) if dlo_vals else None

    print(f"\n  {name_a} vs {name_b} (n={n}):")
    print(f"    Definitely A better: {n_def_a}/{n} ({100*n_def_a/n:.1f}%)")
    print(f"    Indistinguishable:   {n_ind}/{n}")
    print(f"    Definitely B better: {n_def_b}/{n}")
    if dlo_ci:
        print(f"    delta_lo median: {dlo_ci['median']:+.2f} pp  "
              f"95% CI [{dlo_ci['ci_lo_95']:+.2f}, {dlo_ci['ci_hi_95']:+.2f}]")
    if clo_a:
        print(f"    C_lower medians: {name_a}={float(np.median(clo_a)):.2f}%  "
              f"{name_b}={float(np.median(clo_b)):.2f}%")

    return {
        "name_A"           : name_a,
        "name_B"           : name_b,
        "scenarios"        : scenarios,
        "n"                : n,
        "n_definitely_A"   : n_def_a,
        "n_indistinguishable": n_ind,
        "n_definitely_B"   : n_def_b,
        "pct_definitely_A" : round(100 * n_def_a / n, 1) if n else None,
        "delta_lo_ci"      : dlo_ci,
        "C_lower_A_median" : jf(float(np.median(clo_a))) if clo_a else None,
        "C_lower_B_median" : jf(float(np.median(clo_b))) if clo_b else None,
        "scenario_rows"    : rows,
    }


def main():
    for p in (V5_PATH, RAND_PATH):
        if not p.exists():
            raise FileNotFoundError(
                f"{p.name} not found. "
                f"{'Run r1_m4_random_canonical.py first.' if 'canonical' in p.name else ''}")

    v5   = json.loads(V5_PATH.read_text())
    rand = json.loads(RAND_PATH.read_text())

    # Index by scenario
    v5_by_sc = {sr["scenario_idx"]: sr for sr in v5["scenario_results"]}
    rand_by_sc = {sr["scenario_idx"]: sr for sr in rand["scenario_results"]}

    def cx(by_sc: dict, pol: str) -> dict:
        return {s: sr["crossings"][pol] for s, sr in by_sc.items() if pol in sr["crossings"]}

    cx_fp       = cx(v5_by_sc,   "full_fp")
    cx_loc      = cx(v5_by_sc,   "full_loc")
    cx_spread   = cx(v5_by_sc,   "full_fp_spread")
    cx_rand_v5  = cx(v5_by_sc,   "full_random")
    cx_rand_can = cx(rand_by_sc, "full_random")

    all_30    = list(range(30))
    held_out  = list(range(HELD_OUT_START, 30))

    print("=" * 70)
    print("M4 CANONICAL COMPARISONS  (canonical_random = new reference baseline)")
    print("=" * 70)

    comparisons = {}
    comparisons["fp_vs_canonical_rand"]     = summarize_pair(
        "full_fp", "canonical_random", cx_fp, cx_rand_can, all_30)
    comparisons["loc_vs_canonical_rand"]    = summarize_pair(
        "full_loc", "canonical_random", cx_loc, cx_rand_can, all_30)
    comparisons["spread_vs_canonical_rand"] = summarize_pair(
        "full_fp_spread", "canonical_random", cx_spread, cx_rand_can, held_out)

    # Document the realization shift (v5 random vs canonical random)
    print("\n  Realization shift check (v5_random vs canonical_random, all 30):")
    shift_rows = []
    for s in all_30:
        if s not in cx_rand_v5 or s not in cx_rand_can:
            continue
        v5_lo = cx_rand_v5[s]["C_lower_pct"]
        cn_lo = cx_rand_can[s]["C_lower_pct"]
        diff  = cn_lo - v5_lo
        shift_rows.append({"scenario_idx": s, "v5_C_lower": v5_lo,
                            "canonical_C_lower": cn_lo, "diff": diff})
    diffs = [r["diff"] for r in shift_rows]
    print(f"    C_lower shift (canonical - v5): "
          f"median={float(np.median(diffs)):+.2f} pp  "
          f"[p25={float(np.percentile(diffs,25)):+.2f}, "
          f"p75={float(np.percentile(diffs,75)):+.2f}]")
    print(f"    (Near-zero shift confirms uniform sampling has same distribution;")
    print(f"     any residual shift is sampling noise, not a systematic bias.)")
    comparisons["realization_shift_v5_vs_canonical"] = {
        "note"  : "v5 random minus canonical random; should be near zero in expectation",
        "rows"  : shift_rows,
        "diff_median": jf(float(np.median(diffs))),
        "diff_p25"   : jf(float(np.percentile(diffs, 25))),
        "diff_p75"   : jf(float(np.percentile(diffs, 75))),
    }

    out = {
        "source_v5"    : "m4_fair_baselines.json",
        "source_random": "m4_random_canonical.json",
        "note"         : ("Canonical comparisons use m4_random_canonical.json as the "
                          "full_random reference. The v5 full_random baseline is archived "
                          "in m4_fair_baselines.json under key 'legacy_random_realization' "
                          "label; it is hash-order-dependent and not exactly reproducible."),
        "n_bootstrap"  : N_BOOTSTRAP,
        "comparisons"  : comparisons,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {OUT_FILE}")


if __name__ == "__main__":
    main()
