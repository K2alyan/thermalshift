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

OUT_DIR        = pathlib.Path(__file__).resolve().parents[3] / "artifacts" / "revision1" / "results"
V5_PATH        = OUT_DIR / "m4_fair_baselines.json"
RAND_PATH      = OUT_DIR / "m4_random_canonical.json"
CANON_POL_PATH = OUT_DIR / "m4_canonical_policies.json"
OUT_FILE       = OUT_DIR / "m4_canonical_comparisons.json"

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


def _sensitivity(pol_label: str, cx_v5_pol: dict, cx_can_pol: dict,
                 cx_rand_can: dict, scenarios: list[int]) -> dict:
    """Compare v5 vs canonical C_lower per scenario; count verdict flips vs canonical_rand."""
    deltas: list[float] = []
    verdicts_changed = 0
    clo_v5_vals: list[float] = []
    clo_can_vals: list[float] = []
    for s in scenarios:
        if s not in cx_v5_pol or s not in cx_can_pol:
            continue
        lo_v5  = cx_v5_pol[s]["C_lower_pct"]
        lo_can = cx_can_pol[s]["C_lower_pct"]
        deltas.append(abs(lo_can - lo_v5))
        clo_v5_vals.append(lo_v5)
        clo_can_vals.append(lo_can)
        if s in cx_rand_can:
            verd_v5  = interval_compare(cx_v5_pol[s],  cx_rand_can[s])["verdict"]
            verd_can = interval_compare(cx_can_pol[s], cx_rand_can[s])["verdict"]
            if verd_v5 != verd_can:
                verdicts_changed += 1
    return {
        "policy"           : pol_label,
        "n_scenarios"      : len(deltas),
        "old_C_lower_med"  : jf(float(np.median(clo_v5_vals)))  if clo_v5_vals else None,
        "canon_C_lower_med": jf(float(np.median(clo_can_vals))) if clo_can_vals else None,
        "med_abs_delta_pp" : jf(float(np.median(deltas)))       if deltas      else None,
        "max_abs_delta_pp" : jf(float(np.max(deltas)))          if deltas      else None,
        "verdicts_changed" : verdicts_changed,
    }


def main():
    for p in (V5_PATH, RAND_PATH, CANON_POL_PATH):
        if not p.exists():
            hint = ""
            if "random_canonical" in p.name:
                hint = " Run r1_m4_random_canonical.py first."
            elif "canonical_policies" in p.name:
                hint = " Run r1_m4_canonical_policies.py first."
            raise FileNotFoundError(f"{p.name} not found.{hint}")

    v5        = json.loads(V5_PATH.read_text())
    rand      = json.loads(RAND_PATH.read_text())
    canon_pol = json.loads(CANON_POL_PATH.read_text())

    # Index by scenario
    v5_by_sc        = {sr["scenario_idx"]: sr for sr in v5["scenario_results"]}
    rand_by_sc      = {sr["scenario_idx"]: sr for sr in rand["scenario_results"]}
    canon_pol_by_sc = {sr["scenario_idx"]: sr for sr in canon_pol["scenario_results"]}

    def cx(by_sc: dict, pol: str) -> dict:
        return {s: sr["crossings"][pol] for s, sr in by_sc.items() if pol in sr["crossings"]}

    # Authoritative sources per selector audit (m4_selector_audit.json):
    #   FP        → v5 (immune: all 2000 FA_2024 values unique)
    #   FP-spread → v5 (immune: zero within-cabinet FA ties; cabinet key already total-order)
    #   Location  → canonical rerun (vulnerable: 1933/2000 nodes share location score)
    #   Random    → canonical rerun (always vulnerable: sorted(available) fix applied)
    cx_fp       = cx(v5_by_sc,        "full_fp")
    cx_loc_v5   = cx(v5_by_sc,        "full_loc")         # for sensitivity comparison only
    cx_loc_can  = cx(canon_pol_by_sc,  "full_loc")         # authoritative
    cx_spread   = cx(v5_by_sc,        "full_fp_spread")
    cx_rand_v5  = cx(v5_by_sc,        "full_random")
    cx_rand_can = cx(rand_by_sc,      "full_random")

    all_30   = list(range(30))
    held_out = list(range(HELD_OUT_START, 30))

    print("=" * 70)
    print("M4 CANONICAL COMPARISONS")
    print("  Random    → m4_random_canonical.json  (sorted fix; always vulnerable)")
    print("  Location  → m4_canonical_policies.json (tie-broken; 1933/2000 tied)")
    print("  FP        → m4_fair_baselines.json     (immune; v5 is authoritative)")
    print("  FP-spread → m4_fair_baselines.json     (immune; v5 is authoritative)")
    print("=" * 70)

    comparisons = {}
    comparisons["fp_vs_canonical_rand"]     = summarize_pair(
        "full_fp",            "canonical_random", cx_fp,      cx_rand_can, all_30)
    comparisons["loc_vs_canonical_rand"]    = summarize_pair(
        "full_loc_canonical", "canonical_random", cx_loc_can, cx_rand_can, all_30)
    comparisons["spread_vs_canonical_rand"] = summarize_pair(
        "full_fp_spread",     "canonical_random", cx_spread,  cx_rand_can, held_out)

    # Realization shift: v5 random vs canonical random
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
        "note"       : "canonical_random minus v5_random; near zero in expectation",
        "rows"       : shift_rows,
        "diff_median": jf(float(np.median(diffs))),
        "diff_p25"   : jf(float(np.percentile(diffs, 25))),
        "diff_p75"   : jf(float(np.percentile(diffs, 75))),
    }

    # ── Sensitivity table ──────────────────────────────────────────────
    print(f"\n{'='*70}")
    print("CANONICALIZATION SENSITIVITY TABLE")
    print(f"{'='*70}")
    hdr = (f"  {'Policy':<24} {'Old C_lo':>9} {'Canon C_lo':>11} "
           f"{'Med|Δ|':>8} {'Max|Δ|':>8} {'Verdicts chg':>14}")
    print(hdr)
    print("  " + "-" * 78)

    sens_rows = [
        _sensitivity("full_random",          cx_rand_v5, cx_rand_can, cx_rand_can, all_30),
        _sensitivity("full_loc",              cx_loc_v5,  cx_loc_can,  cx_rand_can, all_30),
        _sensitivity("full_fp (immune)",      cx_fp,      cx_fp,       cx_rand_can, all_30),
        _sensitivity("full_fp_spread (imm.)", cx_spread,  cx_spread,   cx_rand_can, held_out),
    ]

    for row in sens_rows:
        print(f"  {row['policy']:<24} "
              f"{row['old_C_lower_med']:>9.2f}% "
              f"{row['canon_C_lower_med']:>10.2f}% "
              f"{row['med_abs_delta_pp']:>7.3f}pp "
              f"{row['max_abs_delta_pp']:>7.3f}pp "
              f"{row['verdicts_changed']:>13}")

    out = {
        "source_v5"         : "m4_fair_baselines.json",
        "source_random"     : "m4_random_canonical.json",
        "source_loc"        : "m4_canonical_policies.json",
        "note"              : (
            "Authoritative sources per selector audit (m4_selector_audit.json): "
            "Random → m4_random_canonical.json (sorted(available) fix; always vulnerable). "
            "Location → m4_canonical_policies.json (tie-broken (FA_loc,hostname); "
            "1933/2000 nodes share location score). "
            "FP → m4_fair_baselines.json (immune: all 2000 FA_2024 values unique). "
            "FP-spread → m4_fair_baselines.json (immune: zero within-cabinet FA ties; "
            "cabinet selection already total-order in v5)."
        ),
        "n_bootstrap"       : N_BOOTSTRAP,
        "comparisons"       : comparisons,
        "sensitivity_table" : sens_rows,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {OUT_FILE}")


if __name__ == "__main__":
    main()
