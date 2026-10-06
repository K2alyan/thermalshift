"""
Round-3 existing-output diagnostics (Task B) — Amendment 2 corrected.

Reads only frozen artifacts/revision2/challenge_analysis.json and
artifacts/revision2/results/gate_f_sc30-54_all_r2challenge_merged.json.
B7 reads artifacts/revision1/results/gate_f_heldout_analysis.json as authoritative source.
No new simulation.

Post-exposure label: all analyses here were designed after sc30-sc54 primary
results were observed. Results are labeled as post-exposure exploratory or
post-exposure reviewer-requested.

Corrections in Amendment 2:
  B4: Holm-Bonferroni now applies correct cumulative-maximum step.
  B3: FP-over-FPSpread reverse direction uses -delta_hi (not -delta_lo).
  B5: Direct paired contrasts from per-scenario crossing brackets (delta_lo AND delta_hi);
      algebraic median subtraction removed.
  B7: Reads gate_f_heldout_analysis.json as authoritative source.

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
HELDOUT_FILE   = REV1_RESULTS / "gate_f_heldout_analysis.json"

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

POLICIES_R2 = ["full_fp", "full_random", "full_fp_spread", "random_spread",
               "fp_withincab_placebo", "fp_global_placebo", "position_template"]

# Expected Holm-adjusted p-values for assertion in B4
EXPECTED_HOLM = {
    "FP_vs_Random":              0.00021529197692871094,
    "FP_vs_WithinCabPlacebo":    0.0000152587890625,
    "FP_vs_GlobalPlacebo":       0.00021529197692871094,
    "RandomSpread_vs_Random":    0.453125,
    "FPSpread_vs_RandomSpread":  0.0000152587890625,
    "FPSpread_vs_FP":            0.017374038696289062,
    "FP_vs_PositionTemplate":    0.03545379638671875,
    "FPSpread_vs_PositionTemplate": 0.79052734375,
}


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
    """Holm-Bonferroni correction with correct cumulative-maximum step.

    Algorithm:
      1. Sort p ascending; record original indices.
      2. Compute adjusted = (m - rank) * p  (rank is 0-based, so multiplier is m-rank).
      3. Apply cumulative maximum over sorted adjusted values.
      4. Cap each at 1.0.
      5. Map back to original order.

    Returns list of (reject, adjusted_p).
    """
    m = len(p_values)
    indexed = sorted(enumerate(p_values), key=lambda x: x[1])

    # Step 2: compute (m - rank) * p for each sorted position (rank 0-based)
    sorted_adj = []
    for rank, (orig_idx, p) in enumerate(indexed):
        sorted_adj.append(p * (m - rank))

    # Step 3: cumulative maximum
    cum_max = []
    running_max = sorted_adj[0]
    for v in sorted_adj:
        running_max = max(running_max, v)
        cum_max.append(running_max)

    # Step 4+5: cap at 1.0 and map back
    adj_p  = [1.0] * m
    reject = [False] * m
    for i, (rank_tup) in enumerate(indexed):
        orig_idx = rank_tup[0]
        adj_p[orig_idx] = min(cum_max[i], 1.0)
        reject[orig_idx] = adj_p[orig_idx] < alpha

    return reject, adj_p


def _verify_holm_values(test_results):
    """Assert all 8 Holm-adjusted p-values match EXPECTED_HOLM within 1e-12.

    Raises AssertionError with details if any value fails.
    """
    tol = 1e-12
    failures = []
    for tr in test_results:
        if "error" in tr:
            continue
        comp = tr["comparison"]
        expected = EXPECTED_HOLM.get(comp)
        if expected is None:
            continue
        actual = tr.get("p_holm_adjusted_two_sided_full")
        if actual is None:
            failures.append(f"  {comp}: p_holm_adjusted_two_sided_full not set")
            continue
        diff = abs(actual - expected)
        if diff > tol:
            failures.append(
                f"  {comp}: actual={actual!r}, expected={expected!r}, diff={diff!r}"
            )
    if failures:
        raise AssertionError(
            "Holm p-value verification FAILED (tolerance 1e-12):\n" + "\n".join(failures)
        )


# ── Per-scenario crossing loader ───────────────────────────────────────────

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
            "floor_rule": (
                "base_infeasible=[0,0] excluded from bracket-width stats; "
                "floor_at_zero=C_lower=0,C_upper>0 included in delta_lo as 0-C_upper_B"
            ),
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
    """B3: FPSpread_vs_FP across ratios, plus FP-over-FPSpread reverse.

    FPSpread_vs_FP direction: delta_lo(FPSpread, FP) = C_lower(FPSpread) - C_upper(FP).
    FP-over-FPSpread reverse direction:
      delta_lo(FP, FPSpread) = C_lower(FP) - C_upper(FPSpread)
                              = -delta_hi(FPSpread, FP)
    So: FP_over_FPSpread_median = median(-delta_hi_per_scenario)
    NEVER negate delta_lo for the reverse direction.
    """
    results_raw = challenge.get("results", {})
    ratios_list = challenge.get("ratios", ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"])
    comp = results_raw.get("FPSpread_vs_FP", {})
    comp_ratios = comp.get("ratios", {})

    out = {}
    for r in ratios_list:
        rv = comp_ratios.get(r, {})
        if not rv:
            continue

        # Forward direction: FPSpread_vs_FP
        delta_lo_per_sc = rv.get("delta_lo_per_scenario", [])
        forward_med = rv.get("median_delta_lo", 0)
        forward_boot = rv.get("bootstrap95_delta_lo", [0, 0])

        # Reverse direction: FP over FPSpread = -delta_hi(FPSpread, FP)
        delta_hi_per_sc = rv.get("delta_hi_per_scenario", [])
        if delta_hi_per_sc:
            neg_dhi = [-x for x in delta_hi_per_sc]
            rev_med = float(np.median(neg_dhi))
            rev_boot_lo, rev_boot_hi = bootstrap_median_ci(neg_dhi)
        else:
            neg_dhi = []
            rev_med = None
            rev_boot_lo, rev_boot_hi = None, None

        out[r] = {
            "FPSpread_vs_FP": {
                "median_delta_lo": round(forward_med, 10),
                "bootstrap95_delta_lo": [round(x, 10) for x in forward_boot],
                "A_I_B": f"{rv.get('n_definitely_A',0)}/{rv.get('n_indistinguishable',0)}/{rv.get('n_definitely_B',0)}",
            },
            "FP_over_FPSpread_reverse": {
                "method": "median(-delta_hi_per_scenario) from FPSpread_vs_FP data",
                "identity": "delta_lo(FP, FPSpread) = -delta_hi(FPSpread, FP)",
                "median_delta_lo": round(rev_med, 10) if rev_med is not None else None,
                "bootstrap95_delta_lo": (
                    [round(rev_boot_lo, 10), round(rev_boot_hi, 10)]
                    if rev_boot_lo is not None else None
                ),
                "note": "NEVER negate delta_lo; uses -delta_hi identity",
            },
        }

    # Find crossover point (where FPSpread_vs_FP flips from negative to positive)
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
    """B4: Two-sided exact binomial sign tests on decisive scenarios, with correct Holm.

    Holm fix: cumulative-maximum step applied over sorted adjusted values before capping.
    """
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
            "p_raw_two_sided": round(p, 10),
        })

    reject, adj_p = holm_bonferroni(p_values)
    for i, tr in enumerate(test_results):
        if "error" in tr:
            continue
        # Store full precision for verification; also rounded for JSON readability
        tr["p_holm_adjusted_two_sided_full"] = adj_p[i]
        tr["p_holm_adjusted_two_sided"] = round(adj_p[i], 10)
        tr["reject_H0_alpha05"] = reject[i]

    return test_results


# ── B5: Direct paired decomposition contrasts ─────────────────────────────

def b5_decomposition(merged):
    """B5: Direct paired contrasts from per-scenario crossing brackets.

    Computes:
      delta_lo(A, B) = C_lower(A) - C_upper(B)  per scenario
      delta_hi(A, B) = C_upper(A) - C_lower(B)  per scenario
      Verdict: definitely_A if delta_lo > 0; definitely_B if delta_hi < 0; else indistinguishable

    When BOTH policies are left_boundary (base infeasible), treat both as [0, 0] brackets;
    this contributes delta_lo = 0, delta_hi = 0 -> indistinguishable.

    Three contrasts (exploratory, post-exposure):
      a. GlobalPlacebo vs Random
      b. WithinCabPlacebo vs GlobalPlacebo
      c. FP vs WithinCabPlacebo

    Sign test: two-sided exact binomial on decisive scenarios only.
    """
    scenarios = merged.get("scenario_results", [])

    def get_crossing(sc, policy):
        r125 = sc.get("ratios", {}).get("1.25", {})
        pol = r125.get(policy, {})
        cr = pol.get("crossing", {})
        return cr

    def compute_contrast(pol_a, pol_b):
        delta_lo_list = []
        delta_hi_list = []
        both_infeasible = 0
        for sc in scenarios:
            cra = get_crossing(sc, pol_a)
            crb = get_crossing(sc, pol_b)
            status_a = cra.get("status", "unknown")
            status_b = crb.get("status", "unknown")
            if status_a == "left_boundary" and status_b == "left_boundary":
                both_infeasible += 1
                # Treat as [0,0] for both -> delta_lo=0, delta_hi=0 -> indistinguishable
                clo_a, chi_a = 0.0, 0.0
                clo_b, chi_b = 0.0, 0.0
            else:
                clo_a = cra.get("C_lower_pct", 0.0)
                chi_a = cra.get("C_upper_pct", 0.0)
                clo_b = crb.get("C_lower_pct", 0.0)
                chi_b = crb.get("C_upper_pct", 0.0)
            dl = clo_a - chi_b
            dh = chi_a - clo_b
            delta_lo_list.append(dl)
            delta_hi_list.append(dh)
        return np.asarray(delta_lo_list), np.asarray(delta_hi_list), both_infeasible

    CONTRASTS = [
        ("GlobalPlacebo_vs_Random",         "fp_global_placebo",    "full_random",          "global_placebo_vs_random"),
        ("WithinCabPlacebo_vs_GlobalPlacebo","fp_withincab_placebo", "fp_global_placebo",    "withincab_vs_global"),
        ("FP_vs_WithinCabPlacebo",          "full_fp",              "fp_withincab_placebo", "fp_vs_withincab"),
    ]

    results = {}
    for comp_name, pol_a, pol_b, label in CONTRASTS:
        dlo, dhi, bi = compute_contrast(pol_a, pol_b)
        n_A = int((dlo > 0).sum())
        n_B = int((dhi < 0).sum())
        n_I = len(dlo) - n_A - n_B
        med_lo = float(np.median(dlo))
        med_hi = float(np.median(dhi))
        boot_lo_lo, boot_lo_hi = bootstrap_median_ci(dlo.tolist())
        n_decisive = n_A + n_B
        p = exact_sign_test_two_sided(n_A, n_B)
        results[comp_name] = {
            "label": label,
            "policy_A": pol_a,
            "policy_B": pol_b,
            "n_definitely_A": n_A,
            "n_indistinguishable": n_I,
            "n_definitely_B": n_B,
            "n_decisive": n_decisive,
            "n_both_base_infeasible": bi,
            "median_delta_lo": round(med_lo, 10),
            "median_delta_hi": round(med_hi, 10),
            "bootstrap95_delta_lo": [round(boot_lo_lo, 10), round(boot_lo_hi, 10)],
            "p_sign_test_two_sided": p,
            "method": "direct paired contrasts: delta_lo=C_lower(A)-C_upper(B), delta_hi=C_upper(A)-C_lower(B)",
            "both_infeasible_treatment": "both left_boundary -> [0,0] brackets -> indistinguishable",
        }

    return {
        "label": "Direct paired decomposition contrasts (post-exposure exploratory)",
        "note": "Algebraic median subtraction NOT used. Direct per-scenario bracket contrasts only.",
        "r": "1.25",
        "n_scenarios": len(scenarios),
        "contrasts": results,
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
    """B7: Read gate_f_heldout_analysis.json as authoritative source.

    Returns stored values directly. Label: development-era sc5-sc29 evaluation
    on the same underlying base dataset.

    Source: artifacts/revision1/results/gate_f_heldout_analysis.json
    """
    if not HELDOUT_FILE.exists():
        return {"error": f"File not found: {HELDOUT_FILE}"}

    with open(HELDOUT_FILE, encoding="utf-8") as fh:
        d = json.load(fh)

    authoritative_scenarios = d.get("authoritative_scenarios", [])
    n = d.get("n", len(authoritative_scenarios))
    ratios = d.get("ratios", [])
    policies = d.get("policies", [])
    comparisons_frozen = d.get("comparisons_frozen", [])
    results = d.get("results", {})

    # Extract r=1.25 comparison summaries from stored data
    comparisons_r125 = {}
    for comp_name in comparisons_frozen:
        comp = results.get(comp_name, {})
        rv = comp.get("ratios", {}).get("1.25", {})
        if not rv:
            comparisons_r125[comp_name] = {"error": "no r=1.25 data"}
            continue
        comparisons_r125[comp_name] = {
            "n": rv.get("n", n),
            "n_definitely_A": rv.get("n_definitely_A"),
            "n_indistinguishable": rv.get("n_indistinguishable"),
            "n_definitely_B": rv.get("n_definitely_B"),
            "median_delta_lo": rv.get("median_delta_lo"),
            "bootstrap95_delta_lo": rv.get("bootstrap95_delta_lo"),
            "median_delta_hi": rv.get("median_delta_hi"),
            "bootstrap95_delta_hi": rv.get("bootstrap95_delta_hi"),
        }

    return {
        "label": "development-era sc5–sc29 evaluation on the same underlying base dataset",
        "authoritative_source": str(HELDOUT_FILE.relative_to(ROOT)),
        "note": "Values read directly from gate_f_heldout_analysis.json (authoritative source). NOT from gate_f_sc5-29 file.",
        "analysis_type": d.get("analysis_type", "held_out"),
        "n_scenarios": n,
        "scenario_indices": authoritative_scenarios,
        "policies_available": policies,
        "ratios_available": ratios,
        "comparisons_frozen": comparisons_frozen,
        "validation": d.get("validation", {}),
        "comparisons_r125": comparisons_r125,
    }


# ── Main ───────────────────────────────────────────────────────────────────

def main():
    print("[B] Loading challenge_analysis.json ...")
    with open(CHALLENGE_FILE, encoding="utf-8") as fh:
        challenge = json.load(fh)

    print("[B] Loading merged sc30-54 for per-scenario crossing data ...")
    with open(MERGED_FILE, encoding="utf-8") as fh:
        merged = json.load(fh)
    per_sc_crossings = load_per_scenario_crossings(merged)

    print("[B1] Absolute capacity levels at r=1.25 ...")
    b1 = b1_absolute_capacity(challenge, per_sc_crossings)

    print("[B2] Binding constraint diagnostic ...")
    b2 = b2_binding_constraints(challenge, per_sc_crossings)

    print("[B3] FPSpread vs FP both directions (corrected reverse via -delta_hi) ...")
    b3 = b3_fpspread_vs_fp(challenge)

    print("[B4] Sign tests with Holm correction (corrected cumulative-max step) ...")
    b4 = b4_sign_tests(challenge)
    _verify_holm_values(b4)
    print("[B4] Holm p-value verification PASSED.")

    print("[B5] Direct paired decomposition contrasts ...")
    b5 = b5_decomposition(merged)

    print("[B6] Order-statistic median CI ...")
    b6 = b6_order_stat_ci(challenge)

    print("[B7] sc5-sc29 evaluation (from gate_f_heldout_analysis.json) ...")
    b7 = b7_sc5_sc29()

    output = {
        "script": "artifacts/revision3/analyze_existing_round3_requests.py",
        "amendment": "2",
        "plan_version": "2.1",
        "plan_ref": "artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §B",
        "post_exposure_label": (
            "post-exposure reviewer-requested; designed and executed after "
            "sc30-sc54 primary results observed"
        ),
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
        f"**Amendment:** {out.get('amendment', '2')}  **Plan version:** {out.get('plan_version', '2.1')}",
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
        "| Comparison | A/I/B | n_both_infeasible | Median delta_lo (pp) | Bootstrap 95% CI |",
        "|---|---|---|---|---|",
    ]
    for comp_name, v in out["B2_binding_constraint_diagnostic"].items():
        if "error" in v:
            lines.append(f"| {comp_name} | — | — | — | — |")
        else:
            aib = f"{v['n_definitely_A']}/{v['n_indistinguishable']}/{v['n_definitely_B']}"
            ci = v["bootstrap95_delta_lo"]
            lines.append(
                f"| {comp_name} | {aib} | {v['n_both_base_infeasible']} "
                f"| {v['median_delta_lo']:+.3f} "
                f"| [{ci[0]:+.3f}, {ci[1]:+.3f}] |"
            )

    lines += [
        "",
        "## B3. FPSpread vs FP — Both Directions",
        "",
        "FPSpread_vs_FP: delta_lo = C_lower(FPSpread) - C_upper(FP).",
        "FP-over-FPSpread reverse: uses identity delta_lo(FP,FPSpread) = -delta_hi(FPSpread,FP).",
        "NEVER negate delta_lo for the reverse direction.",
        "",
        f"Crossover point (FPSpread_vs_FP median delta_lo flips +): **{out['B3_fpspread_vs_fp_both_directions'].get('crossover_point', 'none detected')}**",
        "",
        "| Ratio | FPSpread_vs_FP median delta_lo | A/I/B | FP_over_FPSpread median (-delta_hi) |",
        "|---|---|---|---|",
    ]
    for r, rv in out["B3_fpspread_vs_fp_both_directions"].items():
        if r == "crossover_point":
            continue
        fps = rv.get("FPSpread_vs_FP", {})
        rev = rv.get("FP_over_FPSpread_reverse", {})
        rev_med = rev.get("median_delta_lo")
        rev_str = f"{rev_med:+.4f}" if rev_med is not None else "—"
        lines.append(
            f"| {r} | {fps.get('median_delta_lo', 0):+.4f} | {fps.get('A_I_B', '—')} | {rev_str} |"
        )

    lines += [
        "",
        "## B4. Sign Tests with Holm-Bonferroni Correction (r=1.25)",
        "",
        "Two-sided exact binomial on decisive scenarios only (indistinguishable excluded from n_decisive).",
        "Holm correction: cumulative-maximum step applied before capping at 1.0 (Amendment 2 fix).",
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
                f"| {tr['p_raw_two_sided']:.6f} | {tr['p_holm_adjusted_two_sided']:.6f} "
                f"| {'YES' if tr['reject_H0_alpha05'] else 'no'} |"
            )

    lines += [
        "",
        "## B5. Direct Paired Decomposition Contrasts (post-exposure exploratory)",
        "",
        "Direct per-scenario bracket contrasts: delta_lo(A,B) = C_lower(A) - C_upper(B);",
        "delta_hi(A,B) = C_upper(A) - C_lower(B). Algebraic median subtraction NOT used.",
        "Both-infeasible scenarios: treated as [0,0] -> indistinguishable.",
        "",
        "| Contrast | A/I/B | n_both_infeasible | Median delta_lo | Median delta_hi | Boot95 delta_lo | p (sign test) |",
        "|---|---|---|---|---|---|---|",
    ]
    b5 = out["B5_decomposition_contrasts"]
    for comp_name, v in b5.get("contrasts", {}).items():
        aib = f"{v['n_definitely_A']}/{v['n_indistinguishable']}/{v['n_definitely_B']}"
        boot = v.get("bootstrap95_delta_lo", [None, None])
        boot_str = f"[{boot[0]:+.4f}, {boot[1]:+.4f}]" if boot[0] is not None else "—"
        p_val = v.get("p_sign_test_two_sided")
        p_str = f"{p_val:.6f}" if p_val is not None else "—"
        lines.append(
            f"| {comp_name} | {aib} | {v['n_both_base_infeasible']} "
            f"| {v['median_delta_lo']:+.4f} | {v['median_delta_hi']:+.4f} "
            f"| {boot_str} | {p_str} |"
        )

    lines += [
        "",
        "## B6. Order-Statistic Median CI (n=25)",
        "",
        f"OS_{out['B6_order_stat_median_ci']['OS_lower_k']} and OS_{out['B6_order_stat_median_ci']['OS_upper_k']}; "
        f"actual coverage = {out['B6_order_stat_median_ci']['actual_coverage']:.4f}",
        "",
        "| Comparison | Median delta_lo | OS CI | Bootstrap 95% CI |",
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

    b7 = out["B7_sc5_sc29_evaluation"]
    lines += [
        "",
        "## B7. sc5-sc29 Evaluation (revision1 design, development-era, exploratory context)",
        "",
        f"**Authoritative source:** `{b7.get('authoritative_source', 'gate_f_heldout_analysis.json')}`",
        "**Note:** Values read directly from gate_f_heldout_analysis.json (NOT gate_f_sc5-29 file).",
        f"n_scenarios: {b7.get('n_scenarios', '?')}",
        "",
        "| Comparison | A/I/B | Median delta_lo | Bootstrap95 delta_lo |",
        "|---|---|---|---|",
    ]
    for comp_name, v in b7.get("comparisons_r125", {}).items():
        if "error" in v:
            lines.append(f"| {comp_name} | — | — | — |")
        else:
            n_A = v.get("n_definitely_A", "?")
            n_I = v.get("n_indistinguishable", "?")
            n_B = v.get("n_definitely_B", "?")
            aib = f"{n_A}/{n_I}/{n_B}"
            med = v.get("median_delta_lo")
            med_str = f"{med:.6f}" if med is not None else "—"
            boot = v.get("bootstrap95_delta_lo", [None, None])
            boot_str = f"[{boot[0]:.6f}, {boot[1]:.6f}]" if boot and boot[0] is not None else "—"
            lines.append(f"| {comp_name} | {aib} | {med_str} | {boot_str} |")

    lines += ["", "---", "", "*Post-exposure reviewer-requested analysis. Amendment 2 corrected.*"]

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
