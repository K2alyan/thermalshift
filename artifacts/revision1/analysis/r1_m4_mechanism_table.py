#!/usr/bin/env python3
"""
M4 Mechanism table.
Post-processing only. Reads m4_fair_baselines.json. Does NOT rerun simulation.

For each of full_fp, full_loc, full_fp_spread, on held-out scenarios sc5-29:

At the CROSSING LAMBDA (last feasible lambda for each policy x scenario):
  - node-hour-weighted mean FA_2024 of admitted synthetic nodes (mean_F_syn)
  - cool-10% node-hour share (cool10_share)
  - median cabinets per job (cab_span_median)
  - p90 cabinets per job (cab_span_p90)
  - utilization Gini coefficient (util_gini)

Across ALL lambdas for each policy x scenario:
  - maximum B_cab_ratio (cabinet power binding pressure)

From crossings dict:
  - binding constraint (first_binding_constraint)

Reported as medians across the 25 held-out scenarios, with [p25, p75].

Goal: test whether:
  mean_F(FP) < mean_F(spread) < mean_F(loc)  -- thermal preference ordering
  cab_concentration(FP) > cab_concentration(spread)  -- cabinet-spreading hypothesis
"""

import json, pathlib, numpy as np
from collections import Counter

OUT_DIR    = pathlib.Path(__file__).resolve().parents[3] / "artifacts" / "revision1" / "results"
PRIMARY_IN = OUT_DIR / "m4_fair_baselines.json"
OUT_FILE   = OUT_DIR / "m4_mechanism_table.json"

FOCAL_POLICIES = ["full_fp", "full_loc", "full_fp_spread"]
HELD_OUT_START = 5   # sc5..sc29


def get_crossing_lambda_row(lambda_rows_for_policy, c_lower_pct):
    """Return the lambda_row with capacity_unlock_pct closest to c_lower_pct
    from below (last feasible). Falls back to last infeasible=False row."""
    feasible = [r for r in lambda_rows_for_policy if not r.get("infeasible", False)]
    if not feasible:
        return None
    if len(feasible) == 1:
        return feasible[0]
    # Take the feasible row with capacity_unlock_pct closest to c_lower_pct
    best = min(feasible, key=lambda r: abs(r["capacity_unlock_pct"] - c_lower_pct))
    return best


def scenario_metrics(sr, pol):
    """Extract mechanism metrics for one policy x scenario."""
    lr_list  = sr["lambda_rows"].get(pol, [])
    crossing = sr["crossings"].get(pol, {})
    c_lower  = crossing.get("C_lower_pct", 0.0)
    binding  = crossing.get("first_binding_constraint", "?")

    # Max B_cab_ratio across all lambdas
    max_bcab = max((r.get("B_cab_ratio", 0.0) for r in lr_list), default=float("nan"))

    # Metrics at the crossing lambda
    cx_row = get_crossing_lambda_row(lr_list, c_lower)
    if cx_row is None or cx_row.get("n_syn_admit", 0) == 0:
        return {
            "mean_F_syn":      None,
            "cool10_share":    None,
            "cab_span_median": None,
            "cab_span_p90":    None,
            "util_gini":       None,
            "max_B_cab_ratio": max_bcab,
            "binding":         binding,
            "n_syn_admit":     0,
            "lambda_val":      cx_row["lambda_val"] if cx_row else None,
        }

    return {
        "mean_F_syn":      cx_row.get("mean_F_syn"),
        "cool10_share":    cx_row.get("cool10_share"),
        "cab_span_median": cx_row.get("cab_span_median"),
        "cab_span_p90":    cx_row.get("cab_span_p90"),
        "util_gini":       cx_row.get("util_gini"),
        "max_B_cab_ratio": max_bcab,
        "binding":         binding,
        "n_syn_admit":     cx_row.get("n_syn_admit", 0),
        "lambda_val":      cx_row.get("lambda_val"),
    }


def agg(vals):
    """Aggregate non-None values: median, [p25, p75], n_valid."""
    v = [x for x in vals if x is not None]
    if not v:
        return {"median": None, "p25": None, "p75": None, "n_valid": 0}
    a = np.array(v, dtype=float)
    return {
        "median": float(np.median(a)),
        "p25":    float(np.percentile(a, 25)),
        "p75":    float(np.percentile(a, 75)),
        "min":    float(np.min(a)),
        "max":    float(np.max(a)),
        "n_valid": len(v),
    }


def main():
    d    = json.loads(PRIMARY_IN.read_text())
    srs  = sorted(d["scenario_results"], key=lambda x: x["scenario_idx"])
    held = [sr for sr in srs if sr["scenario_idx"] >= HELD_OUT_START]

    print("=" * 70)
    print(f"M4 MECHANISM TABLE — held-out sc{HELD_OUT_START}-29 (n={len(held)})")
    print("=" * 70)

    table = {}
    metrics_list = ["mean_F_syn", "cool10_share", "cab_span_median",
                    "cab_span_p90", "util_gini", "max_B_cab_ratio"]

    for pol in FOCAL_POLICIES:
        rows = [scenario_metrics(sr, pol) for sr in held]
        summary = {m: agg([r[m] for r in rows]) for m in metrics_list}
        bindings = Counter(r["binding"] for r in rows)
        summary["binding_counts"] = dict(bindings)
        summary["n_syn_admit_median"] = agg([r["n_syn_admit"] for r in rows])["median"]
        table[pol] = {"summary": summary, "scenario_rows": rows}

    # Print table
    col_w = 14
    print(f"\n  {'Metric':<22}", end="")
    for pol in FOCAL_POLICIES:
        label = pol.replace("full_", "").replace("_", "-")
        print(f"  {label:>{col_w}}", end="")
    print()
    print("  " + "-" * (22 + (col_w + 2) * len(FOCAL_POLICIES)))

    for m in metrics_list:
        label = {
            "mean_F_syn":      "mean_F_syn (C)",
            "cool10_share":    "cool10_share (%)",
            "cab_span_median": "cab_span median",
            "cab_span_p90":    "cab_span p90",
            "util_gini":       "util_gini",
            "max_B_cab_ratio": "max_B_cab_ratio",
        }[m]
        print(f"  {label:<22}", end="")
        for pol in FOCAL_POLICIES:
            s = table[pol]["summary"][m]
            v = s["median"]
            if v is None:
                print(f"  {'—':>{col_w}}", end="")
            else:
                print(f"  {v:>{col_w}.3f}", end="")
        print()

    # Binding counts
    print(f"\n  {'Binding constraint':<22}")
    all_bindings = set()
    for pol in FOCAL_POLICIES:
        all_bindings.update(table[pol]["summary"]["binding_counts"].keys())
    for b in sorted(all_bindings):
        print(f"    {b:<20}", end="")
        for pol in FOCAL_POLICIES:
            cnt = table[pol]["summary"]["binding_counts"].get(b, 0)
            print(f"  {cnt:>{col_w}d}", end="")
        print()

    # Hypothesis check
    print("\n  Hypothesis check (held-out medians):")
    mf = {p: table[p]["summary"]["mean_F_syn"]["median"] for p in FOCAL_POLICIES}
    print(f"    mean_F_syn:  fp={mf['full_fp']:.3f}  spread={mf['full_fp_spread']:.3f}  loc={mf['full_loc']:.3f}")
    if mf["full_fp"] is not None and mf["full_fp_spread"] is not None and mf["full_loc"] is not None:
        therm_order = mf["full_fp"] < mf["full_fp_spread"] < mf["full_loc"]
        print(f"    F(FP) < F(spread) < F(loc): {'YES' if therm_order else 'NO'}")
    cab_med = {p: table[p]["summary"]["cab_span_median"]["median"] for p in FOCAL_POLICIES}
    print(f"    cab_span median: fp={cab_med['full_fp']:.1f}  spread={cab_med['full_fp_spread']:.1f}  loc={cab_med['full_loc']:.1f}")
    bcab = {p: table[p]["summary"]["max_B_cab_ratio"]["median"] for p in FOCAL_POLICIES}
    print(f"    max_B_cab_ratio: fp={bcab['full_fp']:.4f}  spread={bcab['full_fp_spread']:.4f}  loc={bcab['full_loc']:.4f}")

    # Save
    out = {
        "source":       "m4_fair_baselines.json",
        "scope":        f"held_out_sc{HELD_OUT_START}_29",
        "n_scenarios":  len(held),
        "focal_policies": FOCAL_POLICIES,
        "metrics_at":   "last_feasible_lambda_for_each_policy_x_scenario",
        "max_B_cab_ratio_at": "max_across_all_lambdas",
        "table": table,
    }
    OUT_FILE.write_text(json.dumps(out, indent=2))
    print(f"\nSaved: {OUT_FILE}")


if __name__ == "__main__":
    main()
