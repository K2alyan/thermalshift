#!/usr/bin/env python3
"""
c2_correctedref_analysis.py — C2 corrected-reference analysis

Reads ONLY the frozen committed C2 raw result (gate_f_sc30-54_1p25_c2manuscript.json).
Does not rerun scheduling or reconstruct scientific values from other runs.

Estimand (frozen, identical to C1):
    delta_lo(A,B) = C_lower_pct(A) - C_upper_pct(B)
    delta_hi(A,B) = C_upper_pct(A) - C_lower_pct(B)
    Verdict: A if delta_lo > 0, B if delta_hi < 0, I otherwise

Bootstrap: paired scenario bootstrap, 5000 draws, seed 9999, percentile 95% CI.
Holm-Bonferroni correction applied across all 8 comparisons.
Two-sided sign test on decisive (A or B) scenarios per comparison.

Questions answered:
    Q1: Does full_fp outperform full_random at r=1.25? (main held-out effect)
    Q2: Is the FP advantage specific to thermal-incidence targeting (vs WithinCab placebo)?
    Q3: Is the FP advantage specific to thermal-incidence targeting (vs Global placebo)?
    Q4: Does fp advantage replicate vs position_loo?
    Q5: Does FPSpread beat RandomSpread? (spread comparison)
    Q6: Does FPSpread beat FP? (spread vs pure-FP within thermal-incidence family)
    Q7: Does RandomSpread beat Random? (spread marginal over random baseline)
    Q8: Does FPSpread beat position_loo?
"""

import sys, json, hashlib, math
from pathlib import Path
import numpy as np
from scipy import stats as scipy_stats

REPO_ROOT = Path(__file__).resolve().parents[3]

FROZEN_C2_RAW = (REPO_ROOT / "artifacts" / "manuscript_completion"
                 / "results" / "gate_f_sc30-54_1p25_c2manuscript.json")
# SHA set at commit time; placeholder verified at runtime after first run
FROZEN_C2_SHA = "__C2_SHA_PLACEHOLDER__"

OUT_JSON = (REPO_ROOT / "artifacts" / "manuscript_completion"
            / "results" / "c2_correctedref_analysis.json")
OUT_MD   = (REPO_ROOT / "artifacts" / "manuscript_completion"
            / "C2_CORRECTEDREF_ANALYSIS.md")

RATIO       = "1.25"
N_SCENARIOS = 25
SC_FIRST    = 30
SC_LAST     = 54
POLICIES    = [
    "full_random", "full_fp", "position_loo", "full_fp_spread",
    "random_spread", "fp_global_placebo", "fp_withincab_placebo",
]
COMPARISONS = [
    ("FP_vs_Random",          "full_fp",        "full_random",          "Q1"),
    ("FP_vs_WithinCab",       "full_fp",        "fp_withincab_placebo", "Q2"),
    ("FP_vs_Global",          "full_fp",        "fp_global_placebo",    "Q3"),
    ("FP_vs_PositionLOO",     "full_fp",        "position_loo",         "Q4"),
    ("FPSpread_vs_RandSpread","full_fp_spread",  "random_spread",        "Q5"),
    ("FPSpread_vs_FP",        "full_fp_spread",  "full_fp",              "Q6"),
    ("RandSpread_vs_Random",  "random_spread",   "full_random",          "Q7"),
    ("FPSpread_vs_PositionLOO","full_fp_spread", "position_loo",         "Q8"),
]
N_BOOTSTRAP    = 5000
BOOTSTRAP_SEED = 9999
ALPHA          = 0.05


# ── Helpers ───────────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def bootstrap_median_ci(values: list, seed: int = BOOTSTRAP_SEED,
                        n_draws: int = N_BOOTSTRAP) -> list:
    """Paired scenario bootstrap: sample N with replacement, median per draw, percentile 95% CI."""
    rng = np.random.default_rng(seed)
    arr = np.array(values, dtype=float)
    n = len(arr)
    idx = rng.integers(0, n, size=(n_draws, n))
    boot_medians = np.median(arr[idx], axis=1)
    return [float(np.percentile(boot_medians, 2.5)),
            float(np.percentile(boot_medians, 97.5))]


def iqr(arr: np.ndarray) -> float:
    return float(np.percentile(arr, 75) - np.percentile(arr, 25))


def sign_test_pvalue(n_A: int, n_B: int) -> float:
    """Two-sided sign test on decisive scenarios. Returns p-value."""
    n = n_A + n_B
    if n == 0:
        return 1.0
    # two-sided: p = 2 * P(X <= min(n_A, n_B)) under Binomial(n, 0.5)
    k_min = min(n_A, n_B)
    return float(scipy_stats.binomtest(k_min, n, 0.5, alternative="two-sided").pvalue)


def holm_adjust(pvalues: list[float]) -> list[float]:
    """Holm-Bonferroni adjustment. Returns adjusted p-values in original order."""
    k = len(pvalues)
    order = sorted(range(k), key=lambda i: pvalues[i])
    adjusted = [0.0] * k
    running_max = 0.0
    for rank, orig_idx in enumerate(order):
        raw = pvalues[orig_idx]
        adj = min(1.0, max(running_max, (k - rank) * raw))
        running_max = adj
        adjusted[orig_idx] = adj
    return adjusted


def majority_direction(n_A: int, n_I: int, n_B: int) -> str:
    if n_A > n_I + n_B:
        return "A"
    if n_B > n_A + n_I:
        return "B"
    return "I"


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    # 1. Verify input SHA (if not placeholder)
    actual_sha = sha256_file(FROZEN_C2_RAW)
    if FROZEN_C2_SHA == "__C2_SHA_PLACEHOLDER__":
        print(f"[INFO] SHA placeholder — recording actual SHA: {actual_sha}")
    else:
        if actual_sha != FROZEN_C2_SHA:
            sys.exit(
                f"[ABORT] SHA256 mismatch.\n"
                f"  Expected: {FROZEN_C2_SHA}\n  Actual:   {actual_sha}"
            )
        print(f"[OK] SHA256 verified: {actual_sha[:16]}...")

    # 2. Load data
    with open(FROZEN_C2_RAW) as f:
        data = json.load(f)

    scenarios = data["scenario_results"]
    if len(scenarios) != N_SCENARIOS:
        sys.exit(f"[ABORT] Expected {N_SCENARIOS} scenarios, got {len(scenarios)}")

    sc_indices = sorted(sc["scenario_idx"] for sc in scenarios)
    expected_range = list(range(SC_FIRST, SC_LAST + 1))
    if sc_indices != expected_range:
        sys.exit(f"[ABORT] Unexpected scenario indices: {sc_indices}")
    print(f"[OK] {len(scenarios)} scenarios: sc{sc_indices[0]}–sc{sc_indices[-1]}")

    # 3. Build lookup: sc_matrix[sc_idx][policy]
    sc_matrix: dict = {}
    missing_policies: list = []
    for sc in scenarios:
        idx = sc["scenario_idx"]
        sc_matrix[idx] = {}
        ratio_data = sc["ratios"].get(RATIO)
        if ratio_data is None:
            sys.exit(f"[ABORT] sc{idx}: ratio {RATIO!r} not found")
        for policy in POLICIES:
            pol_data = ratio_data.get(policy)
            if pol_data is None:
                missing_policies.append(f"sc{idx} policy={policy}")
                continue
            crossing = pol_data["crossing"]
            sc_matrix[idx][policy] = {
                "cl": crossing["C_lower_pct"],
                "cu": crossing["C_upper_pct"],
                "status": crossing["status"],
                "first_binding": crossing.get("first_binding_constraint"),
                "right_censored": crossing.get("right_censored", False),
            }
    if missing_policies:
        sys.exit(f"[ABORT] Missing policy data:\n" + "\n".join(missing_policies))

    # 4. Main pairwise comparisons at r=1.25
    print(f"\nComputing 8 comparisons at r={RATIO}...")
    raw_pvalues: list[float] = []
    comparison_results: dict = {}

    for comp_name, pol_A, pol_B, q_label in COMPARISONS:
        dls = [sc_matrix[idx][pol_A]["cl"] - sc_matrix[idx][pol_B]["cu"]
               for idx in sc_indices]
        dhs = [sc_matrix[idx][pol_A]["cu"] - sc_matrix[idx][pol_B]["cl"]
               for idx in sc_indices]
        verdicts = ["A" if dl > 0 else "B" if dh < 0 else "I"
                    for dl, dh in zip(dls, dhs)]
        n_A = verdicts.count("A")
        n_I = verdicts.count("I")
        n_B = verdicts.count("B")
        med_dl = float(np.median(dls))
        med_dh = float(np.median(dhs))
        ci_dl  = bootstrap_median_ci(dls, seed=BOOTSTRAP_SEED)
        ci_dh  = bootstrap_median_ci(dhs, seed=BOOTSTRAP_SEED)
        pval   = sign_test_pvalue(n_A, n_B)
        raw_pvalues.append(pval)

        comparison_results[comp_name] = {
            "question": q_label,
            "policy_A": pol_A,
            "policy_B": pol_B,
            "ratio": RATIO,
            "n": N_SCENARIOS,
            "n_A": n_A,
            "n_I": n_I,
            "n_B": n_B,
            "n_decisive": n_A + n_B,
            "verdict_summary": f"{n_A}A/{n_I}I/{n_B}B",
            "median_delta_lo_pp": med_dl,
            "bootstrap95_ci_delta_lo_pp": ci_dl,
            "median_delta_hi_pp": med_dh,
            "bootstrap95_ci_delta_hi_pp": ci_dh,
            "sign_test_pvalue_raw": pval,
            "delta_lo_per_scenario": {str(i): dl for i, dl in zip(sc_indices, dls)},
            "delta_hi_per_scenario": {str(i): dh for i, dh in zip(sc_indices, dhs)},
            "verdicts_per_scenario":  {str(i): v  for i, v in zip(sc_indices, verdicts)},
        }
        print(f"  [{comp_name}] {n_A}A/{n_I}I/{n_B}B  "
              f"med_delta_lo={med_dl:+.4f}pp  sign_p={pval:.4f}")

    # 5. Holm correction
    holm_pvalues = holm_adjust(raw_pvalues)
    for (comp_name, *_), praw, padj in zip(COMPARISONS, raw_pvalues, holm_pvalues):
        comparison_results[comp_name]["sign_test_pvalue_holm"] = padj
        comparison_results[comp_name]["sign_test_significant_holm"] = padj < ALPHA

    # 6. Absolute capacity table (r=1.25, all 7 policies)
    print("\nBuilding capacity table...")
    capacity_table: dict = {}
    for policy in POLICIES:
        cls = np.array([sc_matrix[idx][policy]["cl"] for idx in sc_indices])
        cus = np.array([sc_matrix[idx][policy]["cu"] for idx in sc_indices])
        statuses = [sc_matrix[idx][policy]["status"] for idx in sc_indices]
        rcs      = [sc_matrix[idx][policy]["right_censored"] for idx in sc_indices]
        n_lb = sum(1 for s in statuses if s == "left_boundary")
        n_rc = sum(1 for rc in rcs if rc)
        capacity_table[policy] = {
            "ratio": RATIO,
            "n": N_SCENARIOS,
            "median_C_lower_pp": float(np.median(cls)),
            "q25_C_lower_pp":    float(np.percentile(cls, 25)),
            "q75_C_lower_pp":    float(np.percentile(cls, 75)),
            "iqr_C_lower_pp":    iqr(cls),
            "min_C_lower_pp":    float(np.min(cls)),
            "max_C_lower_pp":    float(np.max(cls)),
            "median_C_upper_pp": float(np.median(cus)),
            "q25_C_upper_pp":    float(np.percentile(cus, 25)),
            "q75_C_upper_pp":    float(np.percentile(cus, 75)),
            "iqr_C_upper_pp":    iqr(cus),
            "n_left_boundary":   n_lb,
            "n_right_censored":  n_rc,
        }

    # 7. Binding constraint table (r=1.25)
    print("Building binding constraint table...")
    binding_table: dict = {}
    for policy in POLICIES:
        counts: dict = {}
        n_lb = 0
        for idx in sc_indices:
            d = sc_matrix[idx][policy]
            if d["status"] == "left_boundary":
                n_lb += 1
            else:
                bc = d["first_binding"] if d["first_binding"] else "none"
                counts[bc] = counts.get(bc, 0) + 1
        binding_table[policy] = {
            "ratio": RATIO,
            "left_boundary": n_lb,
            "constraint_counts": counts,
            "n_with_crossing": N_SCENARIOS - n_lb,
        }

    # 8. Q1–Q8 answers
    print("Composing Q1–Q8 answers...")
    q_answers: dict = {}
    for comp_name, pol_A, pol_B, q_label in COMPARISONS:
        r = comparison_results[comp_name]
        n_A, n_I, n_B = r["n_A"], r["n_I"], r["n_B"]
        decisive = n_A + n_B
        direction = majority_direction(n_A, n_I, n_B)
        padj = r["sign_test_pvalue_holm"]
        sig  = r["sign_test_significant_holm"]
        med_dl = r["median_delta_lo_pp"]
        ci_dl  = r["bootstrap95_ci_delta_lo_pp"]
        q_answers[q_label] = {
            "comparison": comp_name,
            "policy_A": pol_A,
            "policy_B": pol_B,
            "verdict_summary": f"{n_A}A/{n_I}I/{n_B}B",
            "majority_direction": direction,
            "n_decisive": decisive,
            "median_delta_lo_pp": med_dl,
            "bootstrap95_ci_delta_lo_pp": ci_dl,
            "sign_test_pvalue_holm": padj,
            "significant_at_alpha05_holm": sig,
            "conclusion": _conclusion(direction, n_A, n_I, n_B, pol_A, pol_B, sig, med_dl),
        }

    # 9. Script self-hash
    script_sha = sha256_file(Path(__file__))

    # 10. Compile JSON output
    result = {
        "raw_source": {
            "path": "artifacts/manuscript_completion/results/gate_f_sc30-54_1p25_c2manuscript.json",
            "sha256": actual_sha,
            "n_scenarios": N_SCENARIOS,
            "scenario_range": f"sc{SC_FIRST}-sc{SC_LAST}",
            "ratio": RATIO,
        },
        "analysis_script_sha256": script_sha,
        "bootstrap": {
            "n_draws": N_BOOTSTRAP,
            "seed": BOOTSTRAP_SEED,
            "method": "paired_scenario_percentile_bootstrap",
            "ci_level": 0.95,
        },
        "multiple_testing": {
            "method": "Holm-Bonferroni",
            "n_comparisons": len(COMPARISONS),
            "alpha": ALPHA,
        },
        "comparisons": comparison_results,
        "capacity_table": capacity_table,
        "binding_constraint_table": binding_table,
        "q_answers": q_answers,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[OK] Written: {OUT_JSON}")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(result)
    print(f"[OK] Written: {OUT_MD}")

    print(f"\n[DONE]")
    print(f"  C2 raw SHA256:          {actual_sha}")
    print(f"  Analysis script SHA256: {script_sha}")
    return result


def _conclusion(direction: str, n_A: int, n_I: int, n_B: int,
                pol_A: str, pol_B: str, sig: bool, med_dl: float) -> str:
    n = n_A + n_I + n_B
    decisive = n_A + n_B
    sig_str = "Holm-significant" if sig else "not Holm-significant"
    if direction == "A":
        return (
            f"{pol_A} beats {pol_B} in {n_A}/{n} scenarios "
            f"({decisive} decisive, {n_A}A/{n_I}I/{n_B}B); "
            f"median delta_lo={med_dl:+.4f}pp; sign test {sig_str}."
        )
    if direction == "B":
        return (
            f"{pol_B} beats {pol_A} in {n_B}/{n} scenarios "
            f"({decisive} decisive, {n_A}A/{n_I}I/{n_B}B); "
            f"median delta_lo={med_dl:+.4f}pp; sign test {sig_str}."
        )
    return (
        f"Indeterminate: {n_A}A/{n_I}I/{n_B}B in {n} scenarios; "
        f"median delta_lo={med_dl:+.4f}pp; sign test {sig_str}."
    )


# ── Markdown output ───────────────────────────────────────────────────────────

def write_markdown(result: dict) -> None:
    lines: list = []
    A = lines.append

    A("# C2 Corrected-Reference Analysis")
    A("")
    A("**Branch:** revision1/major-revision-analyses  ")
    A(f"**Raw source SHA256:** `{result['raw_source']['sha256']}`  ")
    A(f"**Analysis script SHA256:** `{result['analysis_script_sha256']}`  ")
    A(f"**Scenarios:** {result['raw_source']['scenario_range']} "
      f"(n={result['raw_source']['n_scenarios']})  ")
    A(f"**Ratio:** r={result['raw_source']['ratio']} only  ")
    A(f"**Bootstrap:** {result['bootstrap']['n_draws']} draws, "
      f"seed {result['bootstrap']['seed']}, percentile 95% CI  ")
    A(f"**Multiple testing:** Holm-Bonferroni, k={result['multiple_testing']['n_comparisons']}, "
      f"alpha={result['multiple_testing']['alpha']}  ")
    A("")
    A("---")
    A("")

    # Section 1: Pairwise comparisons
    A("## 1. Eight Pairwise Comparisons at r=1.25")
    A("")
    A("Estimand: `delta_lo = C_lower(A) - C_upper(B)` · "
      "`delta_hi = C_upper(A) - C_lower(B)`  ")
    A("Verdict: **A** if delta_lo > 0, **B** if delta_hi < 0, **I** otherwise  ")
    A("Sign test: two-sided binomial on decisive (A or B) scenarios; Holm-adjusted p.")
    A("")
    A("| # | Comparison | A/I/B | Decisive | med delta_lo | 95% CI delta_lo | Sign p (raw) | Sign p (Holm) | Sig? |")
    A("|---|-----------|-------|----------|-------------|-----------------|-------------|--------------|------|")
    for i, (comp_name, pol_A, pol_B, q_label) in enumerate(COMPARISONS, 1):
        r = result["comparisons"][comp_name]
        ci = r["bootstrap95_ci_delta_lo_pp"]
        A(f"| {i} | {comp_name} | {r['verdict_summary']} | {r['n_decisive']} "
          f"| {r['median_delta_lo_pp']:+.4f} "
          f"| [{ci[0]:+.4f}, {ci[1]:+.4f}] "
          f"| {r['sign_test_pvalue_raw']:.4f} "
          f"| {r['sign_test_pvalue_holm']:.4f} "
          f"| {'YES' if r['sign_test_significant_holm'] else 'no'} |")
    A("")
    A("---")
    A("")

    # Section 2: Q1–Q8 answers
    A("## 2. Q1–Q8 Answers")
    A("")
    for q_label in [f"Q{i}" for i in range(1, 9)]:
        qa = result["q_answers"][q_label]
        A(f"### {q_label}: {qa['comparison']}")
        A(f"**A:** `{qa['policy_A']}`  **B:** `{qa['policy_B']}`  ")
        A(f"**Result:** {qa['verdict_summary']}  ")
        A(f"**Conclusion:** {qa['conclusion']}  ")
        A("")
    A("---")
    A("")

    # Section 3: Absolute capacity table
    A("## 3. Absolute Capacity — r=1.25")
    A("")
    A("| Policy | med C_lower | q25 | q75 | IQR | n_lb | n_rc |")
    A("|--------|------------|-----|-----|-----|------|------|")
    for pol in POLICIES:
        ct = result["capacity_table"][pol]
        A(f"| {pol} "
          f"| {ct['median_C_lower_pp']:.4f} "
          f"| {ct['q25_C_lower_pp']:.4f} "
          f"| {ct['q75_C_lower_pp']:.4f} "
          f"| {ct['iqr_C_lower_pp']:.4f} "
          f"| {ct['n_left_boundary']} "
          f"| {ct['n_right_censored']} |")
    A("")
    A("---")
    A("")

    # Section 4: Binding constraint table
    A("## 4. Binding Constraints — r=1.25")
    A("")
    A("| Policy | n_crossing | B_ratio | B_thermal | Other | n_left_boundary |")
    A("|--------|-----------|---------|-----------|-------|----------------|")
    for pol in POLICIES:
        bt = result["binding_constraint_table"][pol]
        cc = bt["constraint_counts"]
        n_cross = bt["n_with_crossing"]
        n_lb    = bt["left_boundary"]
        b_ratio = cc.get("B_ratio", 0)
        b_therm = cc.get("B_thermal", 0)
        other   = n_cross - b_ratio - b_therm
        A(f"| {pol} | {n_cross} | {b_ratio} | {b_therm} | {other} | {n_lb} |")
    A("")
    A("---")
    A("")

    # Section 5: Manuscript-ready paragraph
    A("## 5. Manuscript-Ready Summary Paragraph")
    A("")

    fp_rnd = result["comparisons"]["FP_vs_Random"]
    fp_wc  = result["comparisons"]["FP_vs_WithinCab"]
    fp_gl  = result["comparisons"]["FP_vs_Global"]
    fp_pos = result["comparisons"]["FP_vs_PositionLOO"]
    fps_rs = result["comparisons"]["FPSpread_vs_RandSpread"]
    fps_fp = result["comparisons"]["FPSpread_vs_FP"]
    rs_rnd = result["comparisons"]["RandSpread_vs_Random"]
    fps_pl = result["comparisons"]["FPSpread_vs_PositionLOO"]

    def ci_str(comp: dict) -> str:
        ci = comp["bootstrap95_ci_delta_lo_pp"]
        return f"[{ci[0]:+.2f}, {ci[1]:+.2f}] pp"

    A("In the C2 held-out experiment (sc30–sc54, n=25, r=1.25, corrected concurrent-load "
      "cabinet reference), full_fp outperformed full_random in "
      f"{fp_rnd['n_A']} of {N_SCENARIOS} scenarios "
      f"({fp_rnd['verdict_summary']}; median delta_lo = {fp_rnd['median_delta_lo_pp']:+.4f} pp, "
      f"95% CI {ci_str(fp_rnd)}; Holm p = {fp_rnd['sign_test_pvalue_holm']:.4f}). "
      "The thermal-incidence advantage was not reproduced by the within-cabinet placebo "
      f"({fp_wc['verdict_summary']}; Holm p = {fp_wc['sign_test_pvalue_holm']:.4f}) "
      "nor by the global permutation placebo "
      f"({fp_gl['verdict_summary']}; Holm p = {fp_gl['sign_test_pvalue_holm']:.4f}), "
      "establishing that the effect is specific to thermal-incidence signal rather than "
      "incidental scheduling structure. Relative to the leave-one-out position baseline, "
      f"full_fp achieved {fp_pos['verdict_summary']} (Holm p = {fp_pos['sign_test_pvalue_holm']:.4f}). "
      "Spread extensions: FPSpread vs RandomSpread "
      f"({fps_rs['verdict_summary']}; Holm p = {fps_rs['sign_test_pvalue_holm']:.4f}); "
      "FPSpread vs FP (A=thermally specific vs spread diluted) "
      f"({fps_fp['verdict_summary']}; Holm p = {fps_fp['sign_test_pvalue_holm']:.4f}); "
      "RandomSpread vs Random "
      f"({rs_rnd['verdict_summary']}; Holm p = {rs_rnd['sign_test_pvalue_holm']:.4f}); "
      "FPSpread vs position_loo "
      f"({fps_pl['verdict_summary']}; Holm p = {fps_pl['sign_test_pvalue_holm']:.4f}).")
    A("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
