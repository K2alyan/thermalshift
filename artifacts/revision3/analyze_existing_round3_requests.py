"""
Round-3 existing-output diagnostics (Task B).

Reads only frozen artifacts/revision2/challenge_analysis.json and
artifacts/revision1/results/gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json.
No new simulation.

Post-exposure label: all analyses here were designed after sc30-sc54 primary
results were observed. Results are labeled as post-exposure exploratory or
post-exposure reviewer-requested.

Outputs:
  artifacts/revision3/existing_round3_diagnostics.json
  artifacts/revision3/existing_round3_diagnostics.md

Plan ref: artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §B
"""
import json
import math
import pathlib
import numpy as np
from scipy.stats import binom

ROOT = pathlib.Path(__file__).parent.parent.parent
REV2 = ROOT / "artifacts" / "revision2"
REV1_RESULTS = ROOT / "artifacts" / "revision1" / "results"
OUT_DIR = ROOT / "artifacts" / "revision3"

CHALLENGE_FILE = REV2 / "challenge_analysis.json"
MERGED_FILE    = REV2 / "results" / "gate_f_sc30-54_all_r2challenge_merged.json"
SC5_29_FILE    = REV1_RESULTS / "gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json"

BOOTSTRAP_N    = 5000
BOOTSTRAP_SEED = 9999

# Comparison order for sign tests
COMPARISONS_R125 = [
    ("FP_vs_Random",             "full_fp",          "full_random",          "primary"),
    ("FP_vs_WithinCabPlacebo",   "full_fp",          "fp_withincab_placebo", "node_level_placebo"),
    ("FP_vs_GlobalPlacebo",      "full_fp",          "fp_global_placebo",    "global_placebo"),
    ("RandomSpread_vs_Random",   "random_spread",    "full_random",          "spread_baseline"),
    ("FPSpread_vs_RandomSpread", "full_fp_spread",   "random_spread",        "spread_advantage"),
    ("FPSpread_vs_FP",           "full_fp_spread",   "full_fp",              "spread_vs_fp"),
    ("FP_vs_PositionTemplate",   "full_fp",          "position_template",    "position_placebo"),
    ("FPSpread_vs_PositionTemplate", "full_fp_spread","position_template",   "spread_vs_position"),
]

# ── helpers ────────────────────────────────────────────────────────────────

def bootstrap_median_ci(values, n_boot=BOOTSTRAP_N, seed=BOOTSTRAP_SEED, alpha=0.05):
    rng = np.random.default_rng(seed)
    arr = np.asarray(values, dtype=float)
    medians = np.array([np.median(rng.choice(arr, size=len(arr), replace=True))
                        for _ in range(n_boot)])
    lo = float(np.quantile(medians, alpha / 2))
    hi = float(np.quantile(medians, 1 - alpha / 2))
    return lo, hi


def order_stat_median_ci(n, alpha=0.05):
    """Return (k_lo, k_hi) order statistics for exact median CI (1-indexed)."""
    # Find k such that sum_{j=k}^{n} C(n,j) * 0.5^n >= 1-alpha/2
    # Use CDF of binomial(n, 0.5) — OS_k = x_(k), OS_{n+1-k} for symmetric
    # Conover 1999: k_lo = qbinom(alpha/2, n, 0.5), k_hi = n + 1 - k_lo
    k_lo = int(binom.ppf(alpha / 2, n, 0.5))
    k_hi = n + 1 - k_lo
    actual_coverage = 1 - 2 * binom.cdf(k_lo - 1, n, 0.5)
    return k_lo, k_hi, actual_coverage


def exact_sign_test_two_sided(n_A, n_B):
    """Two-sided exact binomial sign test on DECISIVE scenarios only.

    H0: P(A better | decisive) = 0.5.
    n_decisive = n_A + n_B  (indistinguishable scenarios excluded).
    p = 2 * min(P(X <= min(n_A,n_B)), P(X >= max(n_A,n_B))) under Binom(n_decisive, 0.5).
    Capped at 1.0.
    """
    n_decisive = n_A + n_B
    if n_decisive == 0:
        return 1.0
    k = min(n_A, n_B)
    p_val = float(min(1.0, 2.0 * binom.cdf(k, n_decisive, 0.5)))
    return p_val


def holm_bonferroni(p_values, alpha=0.05):
    """Holm-Bonferroni correction. Returns list of (reject, adjusted_p)."""
    n = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])
    reject = [False] * n
    adj_p  = [1.0] * n
    prev_reject = True
    for rank, (orig_idx, p) in enumerate(indexed):
        adj = min(p * (n - rank), 1.0)
        adj_p[orig_idx] = adj
        if prev_reject and adj < alpha:
            reject[orig_idx] = True
        else:
            prev_reject = False
    return reject, adj_p


# ── Per-scenario crossing loader ───────────────────────────────────────────

POLICIES_R2 = ["full_fp", "full_random", "full_fp_spread", "random_spread",
               "fp_withincab_placebo", "fp_global_placebo", "position_template"]


def load_per_scenario_crossings(merged):
    """Extract crossing data per policy per scenario from merged file.

    Returns dict: policy -> list of {status, C_lower_pct, C_upper_pct, ...} for each scenario.
    """
    scenarios = merged.get("scenario_results", [])
    crossings = {p: [] for p in POLICIES_R2}
    for sc in scenarios:
        r125 = sc.get("ratios", {}).get("1.25", {})
        for policy in POLICIES_R2:
            pd = r125.get(policy, {})
            cr = pd.get("crossing", {})
            crossings[policy].append({
                "scenario_idx": sc.get("scenario_idx"),
                "status": cr.get("status", "unknown"),
                "C_lower_pct": cr.get("C_lower_pct", 0.0),
                "C_upper_pct": cr.get("C_upper_pct", 0.0),
                "first_binding_constraint": cr.get("first_binding_constraint", None),
                "right_censored": cr.get("right_censored", False),
            })
    return crossings


# ── B1: Absolute capacity levels ───────────────────────────────────────────

def b1_absolute_capacity(challenge, per_sc_crossings):
    ps = challenge["policy_summaries"]
    results = {}
    for policy in POLICIES_R2:
        r125 = ps.get(policy, {}).get("1.25", {})
        if not r125:
            results[policy] = {"error": "no r=1.25 data"}
            continue
        crlist = per_sc_crossings.get(policy, [])
        # Floor/left-censor classification
        n_base_infeasible = sum(
            1 for c in crlist if c["status"] == "left_boundary"
        )
        n_floor_at_zero = sum(
            1 for c in crlist
            if c["status"] == "exact_bracket" and c["C_lower_pct"] == 0.0 and c["C_upper_pct"] > 0.0
        )
        n_right_censored = sum(1 for c in crlist if c["right_censored"])
        # Bracket widths excluding [0,0] infeasible cells
        widths = [
            c["C_upper_pct"] - c["C_lower_pct"]
            for c in crlist if c["status"] != "left_boundary"
        ]
        results[policy] = {
            "median_C_lower_pct":  round(r125.get("median_C_lower_pct", 0), 6),
            "median_C_upper_pct":  round(r125.get("median_C_upper_pct", 0), 6),
            "median_bracket_width_excl_infeasible": round(float(np.median(widths)), 6) if widths else None,
            "n_right_censored":    n_right_censored,
            "n_base_infeasible":   n_base_infeasible,
            "n_floor_at_zero":     n_floor_at_zero,
            "n_total_C_lower_0":   n_base_infeasible + n_floor_at_zero,
            "n_scenarios":         r125.get("n_scenarios", 25),
            "floor_rule": "base_infeasible=[0,0] excluded from bracket-width stats; floor_at_zero=C_lower=0,C_upper>0 included in delta_lo as 0-C_upper_B",
        }
    return results


# ── B2: Binding constraints ────────────────────────────────────────────────

def b2_binding_constraints(challenge, per_sc_crossings):
    """
    Extract n_definitely_A, n_indistinguishable, n_definitely_B per comparison at r=1.25.
    Also computes n_both_base_infeasible: scenarios where BOTH policies are left_boundary.
    Cabinet reference = legacy job-contribution P99 (event-weighted).
    """
    results_raw = challenge.get("results", {})
    out = {}
    for comp_name, pol_a, pol_b, cat in COMPARISONS_R125:
        comp = results_raw.get(comp_name, {})
        ratios = comp.get("ratios", {})
        r125 = ratios.get("1.25", {})
        if not r125:
            out[comp_name] = {"error": "no r=1.25 data"}
            continue
        verdicts = r125.get("verdicts", [])
        n_A = verdicts.count("definitely_A_better")
        n_I = verdicts.count("indistinguishable")
        n_B = verdicts.count("definitely_B_better")

        # n_both_base_infeasible: scenarios where both pol_a and pol_b are left_boundary
        cr_a = per_sc_crossings.get(pol_a, [])
        cr_b = per_sc_crossings.get(pol_b, [])
        n_both_infeasible = sum(
            1 for ca, cb in zip(cr_a, cr_b)
            if ca["status"] == "left_boundary" and cb["status"] == "left_boundary"
        )

        # First-binding constraint counts at crossing for policy_A scenarios
        binding_A = {}
        for c in cr_a:
            if c["status"] != "left_boundary":
                bc = c.get("first_binding_constraint", "unknown")
                binding_A[bc] = binding_A.get(bc, 0) + 1

        out[comp_name] = {
            "label": "legacy_cabinet_reference_binding_diagnostic",
            "policy_A": pol_a,
            "policy_B": pol_b,
            "n_definitely_A": n_A,
            "n_indistinguishable": n_I,
            "n_definitely_B": n_B,
            "n_both_base_infeasible": n_both_infeasible,
            "first_binding_constraint_counts_polA": binding_A,
            "median_delta_lo": round(r125.get("median_delta_lo", 0), 6),
            "bootstrap95_delta_lo": [round(x, 6) for x in r125.get("bootstrap95_delta_lo", [0, 0])],
            "note": "Cabinet reference = legacy event-weighted job-contribution P99 (cabinet_power_envelopes.json)"
        }
    return out


# ── B3: FPSpread vs FP both directions ────────────────────────────────────

def b3_fpspread_vs_fp(challenge):
    results_raw = challenge.get("results", {})
    ratios_list = challenge.get("ratios", ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"])
    comp = results_raw.get("FPSpread_vs_FP", {})
    comp_ratios = comp.get("ratios", {})

    out = {}
    for r in ratios_list:
        rv = comp_ratios.get(r, {})
        if not rv:
            continue
        delta_los = rv.get("delta_lo_per_scenario", [])
        delta_los_neg = [-x for x in delta_los]  # reverse direction: FP_vs_FPSpread
        out[r] = {
            "FPSpread_vs_FP": {
                "median_delta_lo": round(rv.get("median_delta_lo", 0), 6),
                "bootstrap95_delta_lo": [round(x, 6) for x in rv.get("bootstrap95_delta_lo", [0, 0])],
                "A_I_B": f"{rv.get('n_definitely_A',0)}/{rv.get('n_indistinguishable',0)}/{rv.get('n_definitely_B',0)}",
            },
            "FP_vs_FPSpread_implied": {
                "median_delta_lo": round(-rv.get("median_delta_lo", 0), 6),
                "note": "Sign-flipped; FP wins where FPSpread_vs_FP loses"
            }
        }
    # Find crossover point
    crossover = None
    prev_sign = None
    for r in ["1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"]:
        med = out.get(r, {}).get("FPSpread_vs_FP", {}).get("median_delta_lo", None)
        if med is None:
            continue
        sign = 1 if med > 0 else (-1 if med < 0 else 0)
        if prev_sign is not None and prev_sign < 0 and sign > 0:
            crossover = r
            break
        prev_sign = sign
    out["crossover_point"] = crossover
    return out


# ── B4: Sign tests with Holm correction ───────────────────────────────────

def b4_sign_tests(challenge):
    results_raw = challenge.get("results", {})
    p_values = []
    test_results = []

    for comp_name, pol_a, pol_b, cat in COMPARISONS_R125:
        comp = results_raw.get(comp_name, {})
        r125 = comp.get("ratios", {}).get("1.25", {})
        if not r125:
            p_values.append(1.0)
            test_results.append({
                "comparison": comp_name, "error": "no data",
                "p_raw": 1.0
            })
            continue
        verdicts = r125.get("verdicts", [])
        n_A = verdicts.count("definitely_A_better")
        n_I = verdicts.count("indistinguishable")
        n_B = verdicts.count("definitely_B_better")
        n_decisive = n_A + n_B
        # Two-sided exact sign test on decisive scenarios only (indistinguishable excluded)
        p = exact_sign_test_two_sided(n_A, n_B)
        p_values.append(p)
        test_results.append({
            "comparison": comp_name,
            "policy_A": pol_a,
            "policy_B": pol_b,
            "category": cat,
            "n_definitely_A": n_A,
            "n_indistinguishable": n_I,
            "n_definitely_B": n_B,
            "n_decisive": n_decisive,
            "test": "two-sided exact binomial on decisive scenarios only",
            "p_raw_two_sided": round(p, 6)
        })

    reject, adj_p = holm_bonferroni(p_values)
    for i, tr in enumerate(test_results):
        tr["p_holm_adjusted_two_sided"] = round(adj_p[i], 6)
        tr["reject_H0_alpha05"] = reject[i]

    return test_results


# ── B5: Decomposition contrasts ────────────────────────────────────────────

def b5_decomposition(challenge):
    results_raw = challenge.get("results", {})
    def get_med(name):
        r = results_raw.get(name, {}).get("ratios", {}).get("1.25", {})
        return r.get("median_delta_lo", None)

    fp_vs_rand  = get_med("FP_vs_Random")
    fp_vs_gp    = get_med("FP_vs_GlobalPlacebo")
    fp_vs_wcp   = get_med("FP_vs_WithinCabPlacebo")
    fps_vs_fp   = get_med("FPSpread_vs_FP")

    return {
        "label": "exploratory — not preregistered",
        "global_score_advantage": {
            "comparison": "FP_vs_GlobalPlacebo",
            "median_delta_lo_pp": round(fp_vs_gp, 4) if fp_vs_gp is not None else None,
            "interpretation": "Advantage from knowing global thermal ordering vs random permutation"
        },
        "node_vs_cabinet_specificity": {
            "comparison": "FP_vs_WithinCabPlacebo",
            "median_delta_lo_pp": round(fp_vs_wcp, 4) if fp_vs_wcp is not None else None,
            "interpretation": "Node-level fingerprint advantage beyond cabinet-level composition"
        },
        "cabinet_composition_advantage": {
            "method": "FP_vs_Random minus FP_vs_GlobalPlacebo (algebraic approximation)",
            "median_delta_lo_pp_approx": (
                round(fp_vs_rand - fp_vs_gp, 4)
                if fp_vs_rand is not None and fp_vs_gp is not None else None
            ),
            "interpretation": "Advantage attributable to cabinet-level thermal composition (approximate decomposition)"
        },
        "spreading_cost_constrained": {
            "comparison": "FPSpread_vs_FP",
            "median_delta_lo_pp": round(fps_vs_fp, 4) if fps_vs_fp is not None else None,
            "interpretation": "Cost of cabinet-spreading at r=1.25 (FPSpread loses to FP)"
        }
    }


# ── B6: Order-statistic median CI ─────────────────────────────────────────

def b6_order_stat_ci(challenge):
    results_raw = challenge.get("results", {})
    n = 25
    k_lo, k_hi, coverage = order_stat_median_ci(n)

    out = {
        "n_scenarios": n,
        "OS_lower_k": k_lo,
        "OS_upper_k": k_hi,
        "actual_coverage": round(coverage, 4),
        "method": "Exact binomial order-statistic CI on median (Conover 1999)",
        "comparisons": {}
    }

    for comp_name, pol_a, pol_b, cat in COMPARISONS_R125:
        comp = results_raw.get(comp_name, {})
        r125 = comp.get("ratios", {}).get("1.25", {})
        if not r125:
            continue
        delta_los = sorted(r125.get("delta_lo_per_scenario", []))
        if len(delta_los) != n:
            out["comparisons"][comp_name] = {"error": f"expected {n} scenarios, got {len(delta_los)}"}
            continue
        median_val  = float(np.median(delta_los))
        os_lo = delta_los[k_lo - 1]  # k-th order statistic (1-indexed)
        os_hi = delta_los[k_hi - 1]
        boot_lo, boot_hi = r125.get("bootstrap95_delta_lo", [None, None])
        out["comparisons"][comp_name] = {
            "median_delta_lo": round(median_val, 6),
            "os_ci_lower":  round(os_lo, 6),
            "os_ci_upper":  round(os_hi, 6),
            "bootstrap95_lo": round(boot_lo, 6) if boot_lo is not None else None,
            "bootstrap95_hi": round(boot_hi, 6) if boot_hi is not None else None,
        }
    return out


# ── B7: sc5-sc29 evaluation ────────────────────────────────────────────────

def b7_sc5_sc29():
    if not SC5_29_FILE.exists():
        return {"error": f"File not found: {SC5_29_FILE}"}

    with open(SC5_29_FILE) as fh:
        d = json.load(fh)

    scenarios = d.get("scenario_results", [])
    if not scenarios:
        return {"error": "No scenario_results in file"}

    sc_indices = [s.get("scenario_idx") for s in scenarios]
    policies = d.get("gate_f_policies", [])
    ratios   = d.get("gate_f_ratios", [])

    # Collect delta_lo per comparison at r=1.25
    # revision1 comparisons: FP_vs_Random, FP_vs_Loc (= position_template)
    rev1_comps = {
        "FP_vs_Random": ("full_fp", "full_random"),
        "FP_vs_Loc":    ("full_fp", "full_loc"),
        "FPSpread_vs_FP": ("full_fp_spread", "full_fp"),
    }

    delta_los = {c: [] for c in rev1_comps}

    for sc in scenarios:
        r125_data = sc.get("ratios", {}).get("1.25", {})
        for comp_name, (pol_a, pol_b) in rev1_comps.items():
            entry_a = r125_data.get(pol_a, {})
            entry_b = r125_data.get(pol_b, {})
            # Find capacity unlock at crossing lambda
            # Take max capacity_unlock_pct from lambda_rows
            def get_cap(entry):
                rows = entry.get("lambda_rows", [])
                if not rows:
                    return None
                # Find crossing (capacity_unlock_pct > 0) or take max
                caps = [r.get("capacity_unlock_pct", 0) for r in rows]
                return max(caps) if caps else None

            cap_a = get_cap(entry_a)
            cap_b = get_cap(entry_b)
            if cap_a is not None and cap_b is not None:
                # delta_lo approximation: cap_A_lower - cap_B_upper
                # revision1 format stores capacity_unlock_pct, not brackets
                # Use crossing capacity as C_lower ≈ C_upper (no bracket in r1)
                delta_los[comp_name].append(cap_a - cap_b)

    out = {
        "label": "exploratory context — revision1 design, different selectors from revision2 challenge",
        "source": str(SC5_29_FILE.relative_to(ROOT)),
        "n_scenarios": len(scenarios),
        "scenario_indices": [s for s in sc_indices if s is not None],
        "policies_available": policies,
        "ratios_available": ratios,
        "note": "revision1 does not use delta_lo brackets; capacity_unlock_pct used as proxy. Results are qualitative context only.",
        "comparisons_r125": {}
    }

    rng = np.random.default_rng(BOOTSTRAP_SEED)
    for comp_name, vals in delta_los.items():
        if not vals:
            out["comparisons_r125"][comp_name] = {"error": "no data"}
            continue
        arr = np.asarray(vals)
        n_pos = int((arr > 0).sum())
        n_neg = int((arr < 0).sum())
        n_tie = int((arr == 0).sum())
        med = float(np.median(arr))
        boot_lo, boot_hi = bootstrap_median_ci(vals)
        out["comparisons_r125"][comp_name] = {
            "n": len(vals),
            "median_delta_approx": round(med, 4),
            "bootstrap95": [round(boot_lo, 4), round(boot_hi, 4)],
            "n_positive": n_pos,
            "n_zero": n_tie,
            "n_negative": n_neg,
        }
    return out


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("[B] Loading challenge_analysis.json ...")
    with open(CHALLENGE_FILE) as fh:
        challenge = json.load(fh)

    print("[B] Loading merged sc30-54 for per-scenario crossing data ...")
    with open(MERGED_FILE) as fh:
        merged = json.load(fh)
    per_sc_crossings = load_per_scenario_crossings(merged)

    print("[B1] Absolute capacity levels at r=1.25 ...")
    b1 = b1_absolute_capacity(challenge, per_sc_crossings)

    print("[B2] Binding constraint diagnostic ...")
    b2 = b2_binding_constraints(challenge, per_sc_crossings)

    print("[B3] FPSpread vs FP both directions ...")
    b3 = b3_fpspread_vs_fp(challenge)

    print("[B4] Sign tests with Holm correction ...")
    b4 = b4_sign_tests(challenge)

    print("[B5] Decomposition contrasts ...")
    b5 = b5_decomposition(challenge)

    print("[B6] Order-statistic median CI ...")
    b6 = b6_order_stat_ci(challenge)

    print("[B7] sc5-sc29 evaluation ...")
    b7 = b7_sc5_sc29()

    output = {
        "script": "artifacts/revision3/analyze_existing_round3_requests.py",
        "plan_ref": "artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §B",
        "post_exposure_label": "post-exposure reviewer-requested; designed and executed after sc30-sc54 primary results observed",
        "source_artifact": str(CHALLENGE_FILE.relative_to(ROOT)),
        "n_bootstrap": BOOTSTRAP_N,
        "bootstrap_seed": BOOTSTRAP_SEED,
        "B1_absolute_capacity_r125": b1,
        "B2_binding_constraint_diagnostic": b2,
        "B3_fpspread_vs_fp_both_directions": b3,
        "B4_sign_tests_holm": b4,
        "B5_decomposition_contrasts": b5,
        "B6_order_stat_median_ci": b6,
        "B7_sc5_sc29_evaluation": b7,
    }

    out_json = OUT_DIR / "existing_round3_diagnostics.json"
    with open(out_json, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2)
    print(f"\n[DONE] Written: {out_json}")

    # Write markdown summary
    _write_md_summary(output, OUT_DIR / "existing_round3_diagnostics.md")
    print(f"[DONE] Written: {OUT_DIR / 'existing_round3_diagnostics.md'}")


def _write_md_summary(out, path):
    lines = [
        "# Existing-Output Diagnostics — Round-3 (Task B)",
        "",
        f"**Post-exposure:** {out['post_exposure_label']}",
        f"**Source:** `{out['source_artifact']}`",
        "",
        "---",
        "",
        "## B1. Absolute Capacity Levels at r=1.25",
        "",
        "| Policy | Median C_lower (%) | Median C_upper (%) | Bracket width (excl infeasible) | n_base_infeasible | n_floor_at_zero | n_right_censored |",
        "|---|---|---|---|---|---|---|",
    ]
    for policy, v in out["B1_absolute_capacity_r125"].items():
        if "error" in v:
            lines.append(f"| {policy} | ERROR | — | — | — | — | — |")
        else:
            bw = v.get("median_bracket_width_excl_infeasible")
            bw_str = f"{bw:.4f}" if bw is not None else "—"
            lines.append(
                f"| {policy} | {v['median_C_lower_pct']:.4f} | {v['median_C_upper_pct']:.4f} "
                f"| {bw_str} | {v['n_base_infeasible']} | {v['n_floor_at_zero']} | {v['n_right_censored']} |"
            )

    lines += [
        "",
        "## B2. Binding Constraint Diagnostic (legacy cabinet reference)",
        "",
        "| Comparison | A/I/B | Median δ_lo (pp) | Bootstrap 95% CI |",
        "|---|---|---|---|",
    ]
    for comp_name, v in out["B2_binding_constraint_diagnostic"].items():
        if "error" in v:
            lines.append(f"| {comp_name} | — | — | — |")
        else:
            aib = f"{v['n_definitely_A']}/{v['n_indistinguishable']}/{v['n_definitely_B']}"
            ci = v['bootstrap95_delta_lo']
            lines.append(
                f"| {comp_name} | {aib} | {v['median_delta_lo']:+.3f} "
                f"| [{ci[0]:+.3f}, {ci[1]:+.3f}] |"
            )

    lines += [
        "",
        "## B3. FPSpread vs FP — crossover",
        "",
        f"Crossover point: **{out['B3_fpspread_vs_fp_both_directions'].get('crossover_point', 'none detected')}**",
        "",
        "| Ratio | FPSpread_vs_FP median δ_lo | A/I/B |",
        "|---|---|---|",
    ]
    for r, rv in out["B3_fpspread_vs_fp_both_directions"].items():
        if r == "crossover_point":
            continue
        fps = rv.get("FPSpread_vs_FP", {})
        lines.append(
            f"| {r} | {fps.get('median_delta_lo', 0):+.4f} | {fps.get('A_I_B', '—')} |"
        )

    lines += [
        "",
        "## B4. Sign Tests with Holm-Bonferroni Correction (r=1.25)",
        "",
        "Two-sided exact binomial on decisive scenarios only (indistinguishable excluded from N).",
        "",
        "| Comparison | A/I/B | n_decisive | p_raw (two-sided) | p_Holm | Reject H0 |",
        "|---|---|---|---|---|---|",
    ]
    for tr in out["B4_sign_tests_holm"]:
        if "error" in tr:
            lines.append(f"| {tr['comparison']} | — | — | — | — | — |")
        else:
            aib = f"{tr['n_definitely_A']}/{tr['n_indistinguishable']}/{tr['n_definitely_B']}"
            nd = tr.get("n_decisive", tr["n_definitely_A"] + tr["n_definitely_B"])
            lines.append(
                f"| {tr['comparison']} | {aib} | {nd} "
                f"| {tr['p_raw_two_sided']:.4f} | {tr['p_holm_adjusted_two_sided']:.4f} "
                f"| {'YES' if tr['reject_H0_alpha05'] else 'no'} |"
            )

    lines += [
        "",
        "## B5. Decomposition Contrasts (exploratory)",
        "",
        "| Contrast | Median δ_lo (pp) | Interpretation |",
        "|---|---|---|",
    ]
    b5 = out["B5_decomposition_contrasts"]
    for key in ["global_score_advantage", "node_vs_cabinet_specificity",
                "cabinet_composition_advantage", "spreading_cost_constrained"]:
        v = b5.get(key, {})
        med = v.get("median_delta_lo_pp") or v.get("median_delta_lo_pp_approx")
        interp = v.get("interpretation", "—")
        lines.append(f"| {key} | {med:+.4f} | {interp} |" if med is not None else f"| {key} | — | {interp} |")

    lines += [
        "",
        "## B6. Order-Statistic Median CI (n=25)",
        "",
        f"OS_{out['B6_order_stat_median_ci']['OS_lower_k']} and OS_{out['B6_order_stat_median_ci']['OS_upper_k']}; "
        f"actual coverage = {out['B6_order_stat_median_ci']['actual_coverage']:.4f}",
        "",
        "| Comparison | Median δ_lo | OS CI | Bootstrap 95% CI |",
        "|---|---|---|---|",
    ]
    for comp_name, v in out["B6_order_stat_median_ci"]["comparisons"].items():
        if "error" in v:
            lines.append(f"| {comp_name} | — | — | — |")
        else:
            lines.append(
                f"| {comp_name} | {v['median_delta_lo']:+.3f} "
                f"| [{v['os_ci_lower']:+.3f}, {v['os_ci_upper']:+.3f}] "
                f"| [{v['bootstrap95_lo']:+.3f}, {v['bootstrap95_hi']:+.3f}] |"
            )

    lines += [
        "",
        "## B7. sc5–sc29 Evaluation (revision1 design, exploratory context)",
        "",
        f"n_scenarios: {out['B7_sc5_sc29_evaluation'].get('n_scenarios', '?')}",
        "",
        "| Comparison | n | Median δ_approx | Bootstrap 95% | n+/0/− |",
        "|---|---|---|---|---|",
    ]
    b7 = out["B7_sc5_sc29_evaluation"]
    for comp_name, v in b7.get("comparisons_r125", {}).items():
        if "error" in v:
            lines.append(f"| {comp_name} | — | — | — | — |")
        else:
            npos = v.get("n_positive", 0)
            ntie = v.get("n_zero", 0)
            nneg = v.get("n_negative", 0)
            boot = v.get("bootstrap95", ["?", "?"])
            lines.append(
                f"| {comp_name} | {v['n']} | {v['median_delta_approx']:+.4f} "
                f"| [{boot[0]:+.4f}, {boot[1]:+.4f}] | {npos}/{ntie}/{nneg} |"
            )

    lines += ["", "---", "", "*Post-exposure reviewer-requested analysis.*"]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
