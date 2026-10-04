#!/usr/bin/env python3
"""
Review 2 Challenge Analysis (r2_gate_f_challenge_analysis.py)

8 preregistered direct comparisons with paired bootstrap 95% CIs.
Per-policy outcome summaries. §H interpretation rules.

Plan ref: REVIEW2_CHALLENGE_PLAN.md §H and Amendment 4 §G2.

Usage:
  python r2_gate_f_challenge_analysis.py [<merged_results_json>] [--out <path>]

Input default:  artifacts/revision2/results/gate_f_sc30-54_all_r2challenge_merged.json
Output default: artifacts/revision2/challenge_analysis.json

Can also be imported:
  from r2_gate_f_challenge_analysis import run_analysis
"""
import sys, io, os, json, argparse, datetime, statistics, math
import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REV2_DIR  = REPO_ROOT / "artifacts" / "revision2"

DEFAULT_IN  = REV2_DIR / "results" / "gate_f_sc30-54_all_r2challenge_merged.json"
DEFAULT_OUT = REV2_DIR / "challenge_analysis.json"

# Preregistered comparisons (plan §H, Amendment 4 §G2)
COMPARISONS_R2 = [
    # (name, policy_A, policy_B, category)
    ("FP_vs_Random",              "full_fp",          "full_random",          "primary"),
    ("FP_vs_WithinCabPlacebo",    "full_fp",          "fp_withincab_placebo", "node_level_placebo"),
    ("FP_vs_GlobalPlacebo",       "full_fp",          "fp_global_placebo",    "global_placebo"),
    ("RandomSpread_vs_Random",    "random_spread",    "full_random",          "spread_baseline"),
    ("FPSpread_vs_RandomSpread",  "full_fp_spread",   "random_spread",        "spread_advantage"),
    ("FPSpread_vs_FP",            "full_fp_spread",   "full_fp",              "spread_vs_fp"),
    ("FP_vs_PositionTemplate",    "full_fp",          "position_template",    "thermal_vs_position"),
    ("FPSpread_vs_PositionTemplate","full_fp_spread", "position_template",    "spread_vs_position"),
]

ALL_RATIOS = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"]

N_BOOTSTRAP    = 5000
BOOTSTRAP_SEED = 9999

# §H4 primary success: n_definitely_A >= 13/25 at r=1.25 for FP_vs_Random
PRIMARY_SUCCESS_THRESHOLD = 13
PRIMARY_COMPARISON = "FP_vs_Random"
PRIMARY_RATIO      = "1.25"

# §H5 right-censored anomaly threshold: >10% of 25 scenarios
RCENSOR_ANOMALY_PCT = 0.10


def _get_crossing(sc_result: dict, ratio: str, policy: str) -> dict | None:
    """Extract crossing dict for a scenario/ratio/policy."""
    return sc_result.get("ratios", {}).get(ratio, {}).get(policy, {}).get("crossing")


def _delta(cx_A: dict, cx_B: dict) -> tuple:
    """
    Compute (delta_lo, delta_hi) for pair (A, B).
    Returns (None, None) if either is right-censored.
    """
    if cx_A is None or cx_B is None:
        return None, None
    if cx_A.get("right_censored") or cx_B.get("right_censored"):
        return None, None
    c_lo_A = cx_A.get("C_lower_pct")
    c_hi_A = cx_A.get("C_upper_pct")
    c_lo_B = cx_B.get("C_lower_pct")
    c_hi_B = cx_B.get("C_upper_pct")
    if any(v is None for v in [c_lo_A, c_hi_A, c_lo_B, c_hi_B]):
        return None, None
    delta_lo = float(c_lo_A) - float(c_hi_B)
    delta_hi = float(c_hi_A) - float(c_lo_B)
    return delta_lo, delta_hi


def _verdict(delta_lo: float | None, delta_hi: float | None) -> str:
    if delta_lo is None or delta_hi is None:
        return "right_censored"
    if delta_lo > 0.0:
        return "definitely_A_better"
    if delta_hi < 0.0:
        return "definitely_B_better"
    return "indistinguishable"


def _bootstrap_ci(values: list, rng: np.random.Generator, n_reps: int = N_BOOTSTRAP) -> list:
    """Percentile bootstrap 95% CI for the median. Returns [lo, hi]."""
    n = len(values)
    if n == 0:
        return [None, None]
    arr = np.array(values, dtype=float)
    medians = np.array([
        float(np.median(arr[rng.integers(0, n, size=n)]))
        for _ in range(n_reps)
    ])
    lo = float(np.percentile(medians, 2.5))
    hi = float(np.percentile(medians, 97.5))
    return [lo, hi]


def _per_policy_summary(scenario_results: list, policy: str,
                         ratios: list) -> dict:
    """Compute per-policy outcome statistics across scenarios."""
    summary: dict[str, dict] = {}
    for ratio in ratios:
        c_lowers   = []
        c_uppers   = []
        n_rc       = 0
        n_drop_cap = []
        n_drop_phys= []
        n_drop_la  = []
        mean_f_syn = []
        cab_spans  = []
        for sc in scenario_results:
            cx = _get_crossing(sc, ratio, policy)
            if cx is None:
                continue
            if cx.get("right_censored"):
                n_rc += 1
            else:
                c_lowers.append(cx.get("C_lower_pct", 0.0))
                if cx.get("C_upper_pct") is not None:
                    c_uppers.append(cx["C_upper_pct"])
            # Aggregate lambda-row metrics from the sweep rows
            rows = sc.get("ratios", {}).get(ratio, {}).get(policy, {}).get("lambda_rows", [])
            for row in rows:
                if row.get("infeasible") is False:
                    if row.get("n_drop_cap") is not None:
                        n_drop_cap.append(int(row["n_drop_cap"]))
                    if row.get("n_drop_physical") is not None:
                        n_drop_phys.append(int(row["n_drop_physical"]))
                    if row.get("n_drop_la") is not None:
                        n_drop_la.append(int(row["n_drop_la"]))
                    if row.get("mean_F_syn") is not None:
                        mean_f_syn.append(float(row["mean_F_syn"]))
                    if row.get("cab_span_median") is not None:
                        cab_spans.append(float(row["cab_span_median"]))

        def _safe_median(lst):
            return float(np.median(lst)) if lst else None

        def _safe_p90(lst):
            return float(np.percentile(lst, 90)) if lst else None

        summary[ratio] = {
            "n_scenarios"           : len(scenario_results),
            "n_right_censored"      : n_rc,
            "median_C_lower_pct"    : _safe_median(c_lowers),
            "median_C_upper_pct"    : _safe_median(c_uppers),
            "mean_C_lower_pct"      : float(np.mean(c_lowers)) if c_lowers else None,
            "mean_C_upper_pct"      : float(np.mean(c_uppers)) if c_uppers else None,
            "median_drop_cap"       : _safe_median(n_drop_cap),
            "median_drop_physical"  : _safe_median(n_drop_phys),
            "median_drop_la"        : _safe_median(n_drop_la),
            "median_mean_F_syn"     : _safe_median(mean_f_syn),
            "median_cab_span"       : _safe_median(cab_spans),
            "p90_cab_span"          : _safe_p90(cab_spans),
        }
    return summary


def run_analysis(scenario_results: list, comparisons: list,
                 ratios: list = None,
                 n_bootstrap: int = N_BOOTSTRAP,
                 bootstrap_seed: int = BOOTSTRAP_SEED) -> dict:
    """
    Core analysis engine. Used by both main challenge and regression test.

    Args:
        scenario_results: list of scenario dicts (each has 'scenario_idx' and 'ratios')
        comparisons: list of (name, policy_A, policy_B, category) or (name, pol_A, pol_B)
        ratios: list of ratio labels to analyze (default: ALL_RATIOS)
        n_bootstrap: bootstrap replicate count (default 5000)
        bootstrap_seed: RNG seed (default 9999)

    Returns:
        dict with 'results' (per comparison) and 'policies' (per policy summary)
    """
    if ratios is None:
        ratios = ALL_RATIOS

    # Normalize comparisons to 4-tuples
    comps = []
    for c in comparisons:
        if len(c) == 4:
            comps.append(c)
        elif len(c) == 3:
            comps.append((c[0], c[1], c[2], ""))
        else:
            raise ValueError(f"Comparison must be (name, polA, polB[, category]): {c}")

    # Collect all policies from comparisons
    all_policies = sorted(set(p for _, a, b, _ in comps for p in [a, b]))

    # Initialize a SINGLE rng, used across all comparisons and ratios in order
    rng = np.random.default_rng(bootstrap_seed)

    results: dict[str, dict] = {}

    for (comp_name, pol_A, pol_B, category) in comps:
        results[comp_name] = {
            "policy_A": pol_A,
            "policy_B": pol_B,
            "category": category,
            "ratios"  : {},
        }

        for ratio in ratios:
            delta_los = []
            delta_his = []
            verdicts  = []
            n_rc      = 0

            sc_indices = []
            for sc in scenario_results:
                cx_A = _get_crossing(sc, ratio, pol_A)
                cx_B = _get_crossing(sc, ratio, pol_B)
                dlo, dhi = _delta(cx_A, cx_B)
                v = _verdict(dlo, dhi)
                verdicts.append(v)
                if v == "right_censored":
                    n_rc += 1
                else:
                    delta_los.append(dlo)
                    delta_his.append(dhi)
                    sc_indices.append(int(sc.get("scenario_idx", -1)))

            n = len(delta_los)
            n_A = sum(1 for v in verdicts if v == "definitely_A_better")
            n_I = sum(1 for v in verdicts if v == "indistinguishable")
            n_B = sum(1 for v in verdicts if v == "definitely_B_better")

            med_lo = float(np.median(delta_los)) if delta_los else None
            med_hi = float(np.median(delta_his)) if delta_his else None

            # Bootstrap CI (uses the shared rng — order matters for reproducibility)
            ci_lo = _bootstrap_ci(delta_los, rng, n_bootstrap)
            ci_hi = _bootstrap_ci(delta_his, rng, n_bootstrap)

            results[comp_name]["ratios"][ratio] = {
                "n"                    : n,
                "n_right_censored"     : n_rc,
                "n_definitely_A"       : n_A,
                "n_indistinguishable"  : n_I,
                "n_definitely_B"       : n_B,
                "verdicts"             : verdicts,
                "median_delta_lo"      : med_lo,
                "bootstrap95_delta_lo" : ci_lo,
                "median_delta_hi"      : med_hi,
                "bootstrap95_delta_hi" : ci_hi,
                "delta_lo_per_scenario": delta_los,
                "delta_hi_per_scenario": delta_his,
                "scenario_indices_used": sc_indices,
            }

    # Per-policy summaries
    policies_summary: dict[str, dict] = {}
    for pol in all_policies:
        policies_summary[pol] = _per_policy_summary(scenario_results, pol, ratios)

    return {"results": results, "policies": policies_summary}


def _apply_h_rules(analysis: dict, n_scenarios: int) -> dict:
    """Apply §H interpretation rules to analysis output."""
    interp: dict = {}
    results = analysis.get("results", {})

    # §H4: Primary success criterion
    fp_vs_rand = results.get(PRIMARY_COMPARISON, {})
    r125 = fp_vs_rand.get("ratios", {}).get(PRIMARY_RATIO, {})
    n_A_primary = r125.get("n_definitely_A", 0)
    n_primary   = r125.get("n", n_scenarios)
    h4_pass = (n_A_primary >= PRIMARY_SUCCESS_THRESHOLD) if n_primary > 0 else False
    interp["H4_primary_success"] = {
        "comparison"           : PRIMARY_COMPARISON,
        "ratio"                : PRIMARY_RATIO,
        "n_definitely_A"       : n_A_primary,
        "n_total"              : n_primary,
        "threshold"            : PRIMARY_SUCCESS_THRESHOLD,
        "pass"                 : h4_pass,
        "verdict"              : "primary_success" if h4_pass else "no_primary_success",
        "bootstrap95_delta_lo" : r125.get("bootstrap95_delta_lo"),
        "bootstrap95_delta_hi" : r125.get("bootstrap95_delta_hi"),
    }

    # §H5: r=1 negative control
    r10_checks = {}
    for comp_name, comp_data in results.items():
        r10 = comp_data.get("ratios", {}).get("1.0", {})
        n_A = r10.get("n_definitely_A", 0)
        n_B = r10.get("n_definitely_B", 0)
        r10_checks[comp_name] = {"n_A": n_A, "n_B": n_B,
                                  "all_indistinguishable": (n_A == 0 and n_B == 0)}
    all_r1_indist = all(v["all_indistinguishable"] for v in r10_checks.values())
    interp["H5_r1_negative_control"] = {
        "per_comparison": r10_checks,
        "all_indistinguishable": all_r1_indist,
        "verdict": "negative_control_pass" if all_r1_indist else "negative_control_anomaly",
    }

    # §H6: Placebo checks
    placebo_comps = {
        "FP_vs_GlobalPlacebo"  : "fp_global_placebo",
        "FP_vs_WithinCabPlacebo": "fp_withincab_placebo",
    }
    placebo_results = {}
    for comp_name, _ in placebo_comps.items():
        pc = results.get(comp_name, {})
        r125p = pc.get("ratios", {}).get("1.25", {})
        n_A = r125p.get("n_definitely_A", 0)
        n = r125p.get("n", n_scenarios)
        placebo_results[comp_name] = {
            "n_definitely_A": n_A,
            "n": n,
            "fp_beats_placebo_at_r125": n_A >= PRIMARY_SUCCESS_THRESHOLD,
        }
    interp["H6_placebo_checks"] = {
        "per_placebo": placebo_results,
        "verdict": ("placebo_confirmed"
                    if any(v["fp_beats_placebo_at_r125"] for v in placebo_results.values())
                    else "placebo_not_confirmed"),
    }

    # §H7: Beta reporting (factual)
    interp["H7_beta_reporting"] = {
        "note": ("PRIMARY_BETA_CHALLENGE is the primary estimand (per-job median LOO beta). "
                 "BETA_F_FROZEN is the original Gate F beta (sensitivity reference). "
                 "See loo_beta_results.json for full LOO distribution."),
    }

    # §H9: FPSpread crossover
    fpspread_fp = results.get("FPSpread_vs_FP", {})
    crossover: dict = {}
    for ratio in ALL_RATIOS:
        rd = fpspread_fp.get("ratios", {}).get(ratio, {})
        crossover[ratio] = {
            "n_definitely_A": rd.get("n_definitely_A", 0),
            "n_indistinguishable": rd.get("n_indistinguishable", 0),
            "n_definitely_B": rd.get("n_definitely_B", 0),
            "median_delta_lo": rd.get("median_delta_lo"),
            "median_delta_hi": rd.get("median_delta_hi"),
            "bootstrap95_delta_lo": rd.get("bootstrap95_delta_lo"),
            "bootstrap95_delta_hi": rd.get("bootstrap95_delta_hi"),
        }
    interp["H9_fpspread_crossover"] = {
        "comparison": "FPSpread_vs_FP",
        "note": ("FPSpread beats FP only if 95% CI for delta_lo excludes zero from below. "
                 "At r=4.0 in Gate F (sc5-29): indistinguishable [−0.644, +1.740] pp."),
        "per_ratio": crossover,
    }

    # §H5 right-censored anomaly flag
    for comp_name, comp_data in results.items():
        r125d = comp_data.get("ratios", {}).get("1.25", {})
        n_rc = r125d.get("n_right_censored", 0)
        n_tot = r125d.get("n", 0) + n_rc
        if n_tot > 0 and n_rc / n_tot > RCENSOR_ANOMALY_PCT:
            interp.setdefault("right_censored_anomalies", []).append({
                "comparison": comp_name,
                "ratio": "1.25",
                "n_right_censored": n_rc,
                "n_total": n_tot,
                "pct": n_rc / n_tot,
            })

    return interp


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", nargs="?", default=str(DEFAULT_IN),
                        help="Merged results JSON (default: gate_f_sc30-54_all_r2challenge_merged.json)")
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    parser.add_argument("--n-bootstrap", type=int, default=N_BOOTSTRAP)
    args = parser.parse_args()

    in_path  = Path(args.input)
    out_path = Path(args.out)

    if not in_path.exists():
        print(f"ERROR: Input file not found: {in_path}")
        sys.exit(1)

    print("=" * 70)
    print("Review 2 Challenge Analysis")
    print("Plan ref: REVIEW2_CHALLENGE_PLAN.md §H, Amendment 4 §G2")
    print("=" * 70)

    data = json.loads(in_path.read_text())
    scenario_results = data.get("scenario_results", [])
    n_scenarios = len(scenario_results)
    print(f"\nLoaded {n_scenarios} scenarios from {in_path.name}")

    ratios_present = []
    if scenario_results:
        ratios_present = sorted(scenario_results[0].get("ratios", {}).keys())
    ratios_to_analyze = [r for r in ALL_RATIOS if r in ratios_present]
    print(f"Ratios: {ratios_to_analyze}")
    print(f"Comparisons: {len(COMPARISONS_R2)}")
    print(f"Bootstrap: {args.n_bootstrap} replicates, seed={BOOTSTRAP_SEED}")

    analysis = run_analysis(
        scenario_results, COMPARISONS_R2,
        ratios=ratios_to_analyze,
        n_bootstrap=args.n_bootstrap,
        bootstrap_seed=BOOTSTRAP_SEED,
    )

    # Validation
    n_cells = sum(
        len(comp_data.get("ratios", {}))
        for comp_data in analysis["results"].values()
    )
    print(f"\nAnalysis cells computed: {n_cells}")

    # §H interpretation rules
    interp = _apply_h_rules(analysis, n_scenarios)

    # Summary printout
    print("\n── Primary result (FP_vs_Random r=1.25) ──")
    h4 = interp["H4_primary_success"]
    print(f"  n_definitely_A = {h4['n_definitely_A']}/{h4['n_total']}  "
          f"threshold={h4['threshold']}  "
          f"verdict={h4['verdict']}")
    ci = h4.get("bootstrap95_delta_lo") or ["?", "?"]
    print(f"  bootstrap95_delta_lo = [{ci[0]:.3f}, {ci[1]:.3f}]" if all(
        isinstance(x, (int, float)) for x in ci) else f"  bootstrap95_delta_lo = {ci}")

    print("\n── r=1 negative control ──")
    print(f"  {interp['H5_r1_negative_control']['verdict']}")

    print("\n── All comparison summaries (r=1.25) ──")
    for comp_name, comp_data in analysis["results"].items():
        r125 = comp_data.get("ratios", {}).get("1.25", {})
        pol_a = comp_data.get("policy_A", "")
        pol_b = comp_data.get("policy_B", "")
        n_A = r125.get("n_definitely_A", 0)
        n_I = r125.get("n_indistinguishable", 0)
        n_B = r125.get("n_definitely_B", 0)
        n   = r125.get("n", 0)
        print(f"  {comp_name:35s}: A={n_A} I={n_I} B={n_B} (n={n})")

    # Write output
    result = {
        "script"         : "artifacts/revision2/r2_gate_f_challenge_analysis.py",
        "plan_ref"       : "REVIEW2_CHALLENGE_PLAN.md §H, Amendment 4 §G2",
        "analysis_type"  : "challenge",
        "run_at"         : datetime.datetime.utcnow().isoformat() + "Z",
        "input_file"     : str(in_path.relative_to(REPO_ROOT) if in_path.is_relative_to(REPO_ROOT) else in_path),
        "n"              : n_scenarios,
        "authoritative_scenarios": [int(sr["scenario_idx"]) for sr in scenario_results],
        "ratios"         : ratios_to_analyze,
        "comparisons"    : [{"name": c[0], "policy_A": c[1], "policy_B": c[2], "category": c[3]}
                            for c in COMPARISONS_R2],
        "n_bootstrap"    : args.n_bootstrap,
        "bootstrap_seed" : BOOTSTRAP_SEED,
        "delta_formula"  : {
            "delta_lo"          : "C_lower_A - C_upper_B",
            "delta_hi"          : "C_upper_A - C_lower_B",
            "definitely_A_better": "delta_lo > 0",
            "definitely_B_better": "delta_hi < 0",
            "indistinguishable" : "otherwise",
        },
        "interpretation"    : interp,
        "results"           : analysis["results"],
        "policy_summaries"  : analysis["policies"],
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nWritten: {out_path}")
    return 0


if __name__ == "__main__":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
    sys.exit(main())
