#!/usr/bin/env python3
"""
M4 Interval-aware comparison statistics.
Post-processing only. Reads m4_fair_baselines.json. Does NOT rerun simulation.

For every scenario and comparison:
  delta_lo = A.C_lower - B.C_upper   (pessimistic: strongest evidence for A)
  delta_hi = A.C_upper - B.C_lower   (optimistic: weakest evidence against A)

Classification per scenario:
  definitely_A_better:   delta_lo > 0
  indistinguishable:     delta_lo <= 0 <= delta_hi
  definitely_B_better:   delta_hi < 0

Comparisons:
  1. full_fp    vs full_random   all 30 scenarios
  2. full_loc   vs full_random   all 30 scenarios
  3. fp_spread  vs full_random   held-out sc5-29 (n=25)
  4. fp_spread  vs full_fp       held-out sc5-29 (n=25)
  5. fp_spread  vs full_loc      held-out sc5-29 (n=25)

Bootstrap: 10,000 scenario resamples; 2.5/97.5 CI for median(delta_lo)
and median(delta_hi) separately. C_lower-point-difference kept as
secondary descriptive only.
"""

import json, pathlib, numpy as np

RNG_SEED    = 20260929
N_BOOTSTRAP = 10_000
OUT_DIR     = pathlib.Path(__file__).resolve().parents[3] / "artifacts" / "revision1" / "results"
PRIMARY_IN  = OUT_DIR / "m4_fair_baselines.json"
OUT_FILE    = OUT_DIR / "m4_interval_stats.json"


def load_scenarios():
    d = json.loads(PRIMARY_IN.read_text())
    return sorted(d["scenario_results"], key=lambda x: x["scenario_idx"])


def crossing(sr, pol):
    cx = sr["crossings"][pol]
    return cx["C_lower_pct"], cx["C_upper_pct"]


def compare_interval(scen_list, pol_A, pol_B):
    rows = []
    for sr in scen_list:
        lo_A, hi_A = crossing(sr, pol_A)
        lo_B, hi_B = crossing(sr, pol_B)
        d_lo = lo_A - hi_B   # pessimistic bound on A - B
        d_hi = hi_A - lo_B   # optimistic bound on A - B
        d_pt = lo_A - lo_B   # point-difference (legacy descriptive)
        if d_lo > 0:
            verdict = "definitely_A_better"
        elif d_hi < 0:
            verdict = "definitely_B_better"
        else:
            verdict = "indistinguishable"
        rows.append({
            "scenario_idx": sr["scenario_idx"],
            "lo_A": lo_A, "hi_A": hi_A,
            "lo_B": lo_B, "hi_B": hi_B,
            "delta_lo": d_lo,
            "delta_hi": d_hi,
            "delta_pt": d_pt,
            "verdict": verdict,
        })
    return rows


def bootstrap_ci(arr, n=N_BOOTSTRAP, seed=RNG_SEED):
    rng  = np.random.default_rng(seed)
    arr  = np.asarray(arr, dtype=float)
    boot = [float(np.median(rng.choice(arr, size=len(arr), replace=True)))
            for _ in range(n)]
    return float(np.percentile(boot, 2.5)), float(np.percentile(boot, 97.5))


def summarise(rows, pol_A, pol_B, scope):
    n     = len(rows)
    dlo   = np.array([r["delta_lo"] for r in rows])
    dhi   = np.array([r["delta_hi"] for r in rows])
    dpt   = np.array([r["delta_pt"] for r in rows])
    n_A   = sum(1 for r in rows if r["verdict"] == "definitely_A_better")
    n_ind = sum(1 for r in rows if r["verdict"] == "indistinguishable")
    n_B   = sum(1 for r in rows if r["verdict"] == "definitely_B_better")

    ci_lo  = bootstrap_ci(dlo, seed=RNG_SEED)
    ci_hi  = bootstrap_ci(dhi, seed=RNG_SEED + 1)
    ci_pt  = bootstrap_ci(dpt, seed=RNG_SEED + 2)

    def stats(v):
        return {
            "median": float(np.median(v)),
            "mean":   float(np.mean(v)),
            "q1":     float(np.percentile(v, 25)),
            "q3":     float(np.percentile(v, 75)),
            "p5":     float(np.percentile(v,  5)),
            "p95":    float(np.percentile(v, 95)),
            "min":    float(np.min(v)),
            "max":    float(np.max(v)),
        }

    return {
        "comparison":              f"{pol_A}_vs_{pol_B}",
        "pol_A":                   pol_A,
        "pol_B":                   pol_B,
        "scenario_scope":          scope,
        "n_scenarios":             n,
        "n_definitely_A_better":   n_A,
        "n_indistinguishable":     n_ind,
        "n_definitely_B_better":   n_B,
        "pct_definitely_A_better": round(100 * n_A / n, 1),
        "delta_lo": {**stats(dlo), "bootstrap_ci_median_95": list(ci_lo)},
        "delta_hi": {**stats(dhi), "bootstrap_ci_median_95": list(ci_hi)},
        "delta_pt_descriptive_only": {
            **stats(dpt),
            "bootstrap_ci_median_95": list(ci_pt),
            "n_positive": int(np.sum(dpt > 0)),
        },
        "scenario_rows": rows,
    }


def main():
    srs      = load_scenarios()
    all_30   = srs
    held_out = [sr for sr in srs if sr["scenario_idx"] >= 5]

    specs = [
        ("full_fp",        "full_random", all_30,   "all_30"),
        ("full_loc",       "full_random", all_30,   "all_30"),
        ("full_fp_spread", "full_random", held_out, "held_out_sc5_29"),
        ("full_fp_spread", "full_fp",     held_out, "held_out_sc5_29"),
        ("full_fp_spread", "full_loc",    held_out, "held_out_sc5_29"),
    ]

    comparisons = []
    for pol_A, pol_B, scens, scope in specs:
        rows = compare_interval(scens, pol_A, pol_B)
        comparisons.append(summarise(rows, pol_A, pol_B, scope))

    out = {
        "source":         "m4_fair_baselines.json",
        "method":         ("interval_comparison: "
                           "delta_lo=A.C_lower-B.C_upper, "
                           "delta_hi=A.C_upper-B.C_lower"),
        "classification": {
            "definitely_A_better": "delta_lo > 0",
            "indistinguishable":   "delta_lo <= 0 <= delta_hi",
            "definitely_B_better": "delta_hi < 0",
        },
        "n_bootstrap":  N_BOOTSTRAP,
        "comparisons":  comparisons,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"Saved: {OUT_FILE}\n")

    for c in comparisons:
        scope_tag = "(all 30)" if c["scenario_scope"] == "all_30" else "(held-out sc5-29)"
        print(f"{c['comparison']} {scope_tag}")
        print(f"  Definitely A better : {c['n_definitely_A_better']}/{c['n_scenarios']}  ({c['pct_definitely_A_better']:.1f}%)")
        print(f"  Indistinguishable   : {c['n_indistinguishable']}/{c['n_scenarios']}")
        print(f"  Definitely B better : {c['n_definitely_B_better']}/{c['n_scenarios']}")
        lo = c["delta_lo"]
        hi = c["delta_hi"]
        pt = c["delta_pt_descriptive_only"]
        print(f"  delta_lo  median={lo['median']:+.2f} pp  CI=[{lo['bootstrap_ci_median_95'][0]:.2f}, {lo['bootstrap_ci_median_95'][1]:.2f}]  [p5,p95]=[{lo['p5']:.2f},{lo['p95']:.2f}]")
        print(f"  delta_hi  median={hi['median']:+.2f} pp  CI=[{hi['bootstrap_ci_median_95'][0]:.2f}, {hi['bootstrap_ci_median_95'][1]:.2f}]  [p5,p95]=[{hi['p5']:.2f},{hi['p95']:.2f}]")
        print(f"  delta_pt  (descr.) median={pt['median']:+.2f} pp  CI=[{pt['bootstrap_ci_median_95'][0]:.2f}, {pt['bootstrap_ci_median_95'][1]:.2f}]  n_pos={pt['n_positive']}/{c['n_scenarios']}")
        print()


if __name__ == "__main__":
    main()
