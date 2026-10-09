#!/usr/bin/env python3
"""
c3_threshold_analysis.py — C3 threshold sensitivity analysis

Analyzes P90, P95, P99 thermal-threshold runs using the same frozen estimand as C1/C2:
    delta_lo(FP, Random) = C_lower_pct(FP) - C_upper_pct(Random)
    delta_hi(FP, Random) = C_upper_pct(FP) - C_lower_pct(Random)
    Verdict: A (FP) if delta_lo > 0, B (Random) if delta_hi < 0, I otherwise

P95 reuses the accepted C2 corrected-reference result (SHA-verified).
P90 and P99 come from C3 production runs.

Reports per threshold:
  - A/I/B tally
  - Median delta_lo / delta_hi with bootstrap 95% CI
  - Absolute capacity (median C_lower, C_upper; quartiles; IQR)
  - Left-boundary and right-censored counts
  - First-binding constraint distribution
  - Mechanism check: how binding constraints shift across thresholds

Bootstrap: 5000 paired draws, seed 9999, percentile CI.
This is exploratory threshold sensitivity, not preregistered primary evidence.
"""

import sys, json, hashlib
from pathlib import Path
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

# ── Input file specs ──────────────────────────────────────────────────────────
THRESHOLDS = {
    "P90": {
        "thr":    61.875,
        "path":   RESULTS / "gate_f_sc30-54_1p25_t61p875_c3manuscript.json",
        "sha":    "0cd2371a71d96c6e852c429e8fec17d4e0ab0e985dcd9b42003bcf6009bbe084",
        "source": "c3_production",
    },
    "P95": {
        "thr":    63.625,
        "path":   RESULTS / "gate_f_sc30-54_1p25_c2manuscript.json",
        "sha":    "b4dbc4bc0f8646f197d0a575f42dc785e97710f22460c7f2c8a1913866c6b129",
        "source": "c2_accepted_corrected_reference",
    },
    "P99": {
        "thr":    66.6625,
        "path":   RESULTS / "gate_f_sc30-54_1p25_t66p6625_c3manuscript.json",
        "sha":    "2fef4c49500e4f3c61bc2de63edf7ee7320be4d301a44544402e610eac6c5cbc",
        "source": "c3_production",
    },
}

OUT_JSON = RESULTS / "c3_threshold_analysis.json"
OUT_MD   = REPO_ROOT / "artifacts" / "manuscript_completion" / "C3_THRESHOLD_ANALYSIS.md"

RATIO       = "1.25"
N_SCENARIOS = 25
SC_FIRST    = 30
SC_LAST     = 54
POL_A       = "full_fp"
POL_B       = "full_random"
N_BOOTSTRAP    = 5000
BOOTSTRAP_SEED = 9999


# ── Helpers ───────────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def bootstrap_median_ci(values: list, seed: int = BOOTSTRAP_SEED,
                        n_draws: int = N_BOOTSTRAP) -> list:
    rng = np.random.default_rng(seed)
    arr = np.array(values, dtype=float)
    n = len(arr)
    idx = rng.integers(0, n, size=(n_draws, n))
    boot_medians = np.median(arr[idx], axis=1)
    return [float(np.percentile(boot_medians, 2.5)),
            float(np.percentile(boot_medians, 97.5))]


def iqr(arr: np.ndarray) -> float:
    return float(np.percentile(arr, 75) - np.percentile(arr, 25))


# ── Load and validate one threshold file ──────────────────────────────────────

def load_threshold(label: str, spec: dict) -> dict:
    """Load and validate one threshold's raw JSON. Returns sc_matrix[sc_idx]."""
    path = spec["path"]
    expected_sha = spec["sha"]

    if not path.exists():
        sys.exit(f"[ABORT] {label} file not found: {path}")

    actual_sha = sha256_file(path)
    if expected_sha is not None and actual_sha != expected_sha:
        sys.exit(
            f"[ABORT] {label} SHA256 mismatch\n"
            f"  expected: {expected_sha}\n  actual:   {actual_sha}"
        )

    with open(path) as f:
        data = json.load(f)

    scenarios = data["scenario_results"]
    sc_indices = sorted(sc["scenario_idx"] for sc in scenarios)
    if len(sc_indices) != N_SCENARIOS or sc_indices != list(range(SC_FIRST, SC_LAST + 1)):
        sys.exit(f"[ABORT] {label}: unexpected scenario indices {sc_indices}")

    sc_matrix = {}
    for sc in scenarios:
        idx = sc["scenario_idx"]
        ratio_data = sc["ratios"].get(RATIO)
        if ratio_data is None:
            sys.exit(f"[ABORT] {label} sc{idx}: ratio {RATIO!r} not found")
        sc_matrix[idx] = {}
        for pol in [POL_A, POL_B]:
            pol_data = ratio_data.get(pol)
            if pol_data is None:
                sys.exit(f"[ABORT] {label} sc{idx}: policy {pol!r} not found")
            cx = pol_data["crossing"]
            sc_matrix[idx][pol] = {
                "cl":            cx["C_lower_pct"],
                "cu":            cx["C_upper_pct"],
                "status":        cx["status"],
                "first_binding": cx.get("first_binding_constraint"),
                "right_censored":cx.get("right_censored", False),
            }

    sha_display = actual_sha[:16] + "..." if len(actual_sha) > 16 else actual_sha
    print(f"[OK] {label} loaded: {path.name}  SHA256: {sha_display}")
    return sc_matrix, actual_sha


# ── Analyse one threshold ─────────────────────────────────────────────────────

def analyse_threshold(label: str, sc_matrix: dict, sc_indices: list) -> dict:
    dls = [sc_matrix[i][POL_A]["cl"] - sc_matrix[i][POL_B]["cu"] for i in sc_indices]
    dhs = [sc_matrix[i][POL_A]["cu"] - sc_matrix[i][POL_B]["cl"] for i in sc_indices]
    verdicts = ["A" if dl > 0 else "B" if dh < 0 else "I" for dl, dh in zip(dls, dhs)]
    n_A = verdicts.count("A")
    n_I = verdicts.count("I")
    n_B = verdicts.count("B")

    med_dl = float(np.median(dls))
    med_dh = float(np.median(dhs))
    ci_dl  = bootstrap_median_ci(dls)
    ci_dh  = bootstrap_median_ci(dhs)

    # Capacity
    fp_cls  = np.array([sc_matrix[i][POL_A]["cl"] for i in sc_indices])
    fp_cus  = np.array([sc_matrix[i][POL_A]["cu"] for i in sc_indices])
    rnd_cls = np.array([sc_matrix[i][POL_B]["cl"] for i in sc_indices])
    rnd_cus = np.array([sc_matrix[i][POL_B]["cu"] for i in sc_indices])

    def cap_stats(cls, cus, pol_data_list):
        statuses = [pol_data_list[i]["status"] for i in sc_indices]
        rcs      = [pol_data_list[i]["right_censored"] for i in sc_indices]
        n_lb = sum(1 for s in statuses if s == "left_boundary")
        n_rc = sum(1 for rc in rcs if rc)
        return {
            "median_C_lower_pp": float(np.median(cls)),
            "q25_C_lower_pp":    float(np.percentile(cls, 25)),
            "q75_C_lower_pp":    float(np.percentile(cls, 75)),
            "iqr_C_lower_pp":    iqr(cls),
            "median_C_upper_pp": float(np.median(cus)),
            "q25_C_upper_pp":    float(np.percentile(cus, 25)),
            "q75_C_upper_pp":    float(np.percentile(cus, 75)),
            "iqr_C_upper_pp":    iqr(cus),
            "n_left_boundary":   n_lb,
            "n_right_censored":  n_rc,
        }

    fp_cap  = cap_stats(fp_cls,  fp_cus,  {i: sc_matrix[i][POL_A] for i in sc_indices})
    rnd_cap = cap_stats(rnd_cls, rnd_cus, {i: sc_matrix[i][POL_B] for i in sc_indices})

    # Binding constraints for FP
    fp_binding: dict = {}
    n_fp_lb = 0
    for i in sc_indices:
        d = sc_matrix[i][POL_A]
        if d["status"] == "left_boundary":
            n_fp_lb += 1
        else:
            bc = d["first_binding"] if d["first_binding"] else "none"
            fp_binding[bc] = fp_binding.get(bc, 0) + 1

    rnd_binding: dict = {}
    n_rnd_lb = 0
    for i in sc_indices:
        d = sc_matrix[i][POL_B]
        if d["status"] == "left_boundary":
            n_rnd_lb += 1
        else:
            bc = d["first_binding"] if d["first_binding"] else "none"
            rnd_binding[bc] = rnd_binding.get(bc, 0) + 1

    return {
        "n": N_SCENARIOS,
        "n_A": n_A, "n_I": n_I, "n_B": n_B,
        "verdict_summary": f"{n_A}A/{n_I}I/{n_B}B",
        "median_delta_lo_pp":         med_dl,
        "bootstrap95_ci_delta_lo_pp": ci_dl,
        "median_delta_hi_pp":         med_dh,
        "bootstrap95_ci_delta_hi_pp": ci_dh,
        "delta_lo_per_scenario": {str(i): dl for i, dl in zip(sc_indices, dls)},
        "delta_hi_per_scenario": {str(i): dh for i, dh in zip(sc_indices, dhs)},
        "verdicts_per_scenario":  {str(i): v  for i, v in zip(sc_indices, verdicts)},
        "capacity": {POL_A: fp_cap, POL_B: rnd_cap},
        "binding_constraints": {
            POL_A: {"left_boundary": n_fp_lb,  "counts": fp_binding,  "n_crossing": N_SCENARIOS - n_fp_lb},
            POL_B: {"left_boundary": n_rnd_lb, "counts": rnd_binding, "n_crossing": N_SCENARIOS - n_rnd_lb},
        },
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    sc_indices = list(range(SC_FIRST, SC_LAST + 1))

    # Load all three thresholds
    sc_matrices = {}
    actual_shas = {}
    for label, spec in THRESHOLDS.items():
        sc_matrix, actual_sha = load_threshold(label, spec)
        sc_matrices[label] = sc_matrix
        actual_shas[label] = actual_sha

    print(f"\nAnalysing P90 / P95 / P99 (FP vs Random, r={RATIO})...")

    threshold_results = {}
    for label in ["P90", "P95", "P99"]:
        r = analyse_threshold(label, sc_matrices[label], sc_indices)
        threshold_results[label] = r
        print(f"  [{label}] {r['verdict_summary']}  "
              f"med_delta_lo={r['median_delta_lo_pp']:+.4f}pp  "
              f"FP_median_C_lower={r['capacity'][POL_A]['median_C_lower_pp']:.4f}pp")

    # Mechanism check: binding constraint shift across thresholds
    print("\nMechanism check: binding constraint shift...")
    all_constraints = set()
    for label in ["P90", "P95", "P99"]:
        for pol in [POL_A, POL_B]:
            all_constraints.update(threshold_results[label]["binding_constraints"][pol]["counts"].keys())

    mechanism_table: dict = {}
    for pol in [POL_A, POL_B]:
        mechanism_table[pol] = {}
        for label in ["P90", "P95", "P99"]:
            bc = threshold_results[label]["binding_constraints"][pol]
            mechanism_table[pol][label] = {
                "n_left_boundary": bc["left_boundary"],
                "n_crossing":      bc["n_crossing"],
                "constraint_counts": bc["counts"],
            }

    script_sha = sha256_file(Path(__file__))

    result = {
        "source": {
            "P90": {"path": str(THRESHOLDS["P90"]["path"].name), "sha256": actual_shas["P90"], "thr": 61.875},
            "P95": {"path": str(THRESHOLDS["P95"]["path"].name), "sha256": actual_shas["P95"], "thr": 63.625,
                    "note": "Reuses accepted C2 corrected-reference result"},
            "P99": {"path": str(THRESHOLDS["P99"]["path"].name), "sha256": actual_shas["P99"], "thr": 66.6625},
        },
        "analysis_script_sha256": script_sha,
        "estimand": {
            "delta_lo": "C_lower_pct(FP) - C_upper_pct(Random)",
            "delta_hi": "C_upper_pct(FP) - C_lower_pct(Random)",
            "verdict":  "A if delta_lo > 0; B if delta_hi < 0; I otherwise",
        },
        "bootstrap": {
            "n_draws": N_BOOTSTRAP,
            "seed": BOOTSTRAP_SEED,
            "method": "paired_scenario_percentile_bootstrap",
            "ci_level": 0.95,
        },
        "note": "Exploratory threshold sensitivity. Not preregistered primary evidence.",
        "ratio": RATIO,
        "n_scenarios": N_SCENARIOS,
        "scenario_range": f"sc{SC_FIRST}-sc{SC_LAST}",
        "comparison": f"{POL_A} vs {POL_B}",
        "thresholds": threshold_results,
        "mechanism_table": mechanism_table,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(f"[OK] Written: {OUT_JSON}")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(result)
    print(f"[OK] Written: {OUT_MD}")

    print(f"\n[DONE]")
    print(f"  Analysis script SHA256: {script_sha}")
    return result


# ── Markdown output ───────────────────────────────────────────────────────────

def write_markdown(result: dict) -> None:
    lines: list = []
    A = lines.append

    A("# C3 Threshold Sensitivity Analysis")
    A("")
    A("**Exploratory post-exposure threshold sensitivity. Not preregistered primary evidence.**  ")
    A("")
    A(f"**Scenarios:** sc{SC_FIRST}-sc{SC_LAST} (n={N_SCENARIOS})  ")
    A(f"**Ratio:** r={RATIO}  **Comparison:** {POL_A} vs {POL_B}  ")
    A(f"**Estimand:** delta_lo = C_lower(FP) - C_upper(Random); verdict A if > 0, B if delta_hi < 0  ")
    A(f"**Bootstrap:** {N_BOOTSTRAP} draws, seed {BOOTSTRAP_SEED}, percentile 95% CI  ")
    A("")

    for label in ["P90", "P95", "P99"]:
        src = result["source"][label]
        A(f"**{label} source:** `{src['path']}` SHA256: `{src['sha256'][:16]}...`  ")
    A("")
    A("---")
    A("")

    # Section 1: Summary table
    A("## 1. FP vs Random Summary — P90 / P95 / P99")
    A("")
    A("| Threshold | T (C) | A/I/B | med delta_lo | 95% CI delta_lo | med delta_hi | 95% CI delta_hi |")
    A("|-----------|-------|-------|-------------|-----------------|-------------|-----------------|")
    THR_LABELS = {"P90": 61.875, "P95": 63.625, "P99": 66.6625}
    for label in ["P90", "P95", "P99"]:
        r = result["thresholds"][label]
        ci_lo = r["bootstrap95_ci_delta_lo_pp"]
        ci_hi = r["bootstrap95_ci_delta_hi_pp"]
        A(f"| {label} | {THR_LABELS[label]} | {r['verdict_summary']} "
          f"| {r['median_delta_lo_pp']:+.4f} "
          f"| [{ci_lo[0]:+.4f}, {ci_lo[1]:+.4f}] "
          f"| {r['median_delta_hi_pp']:+.4f} "
          f"| [{ci_hi[0]:+.4f}, {ci_hi[1]:+.4f}] |")
    A("")
    A("---")
    A("")

    # Section 2: Absolute capacity
    A("## 2. Absolute Capacity")
    A("")
    for pol_label, pol in [("FP (full_fp)", POL_A), ("Random (full_random)", POL_B)]:
        A(f"### {pol_label}")
        A("")
        A("| Threshold | med C_lower | q25 | q75 | IQR | med C_upper | n_lb | n_rc |")
        A("|-----------|------------|-----|-----|-----|------------|------|------|")
        for label in ["P90", "P95", "P99"]:
            ct = result["thresholds"][label]["capacity"][pol]
            A(f"| {label} "
              f"| {ct['median_C_lower_pp']:.4f} "
              f"| {ct['q25_C_lower_pp']:.4f} "
              f"| {ct['q75_C_lower_pp']:.4f} "
              f"| {ct['iqr_C_lower_pp']:.4f} "
              f"| {ct['median_C_upper_pp']:.4f} "
              f"| {ct['n_left_boundary']} "
              f"| {ct['n_right_censored']} |")
        A("")
    A("---")
    A("")

    # Section 3: Binding constraints / mechanism
    A("## 3. Binding Constraints — Mechanism Check")
    A("")
    A("First binding constraint for full_fp (scenarios with a crossing only):")
    A("")
    A("| Threshold | n_crossing | B_ratio | B_thermal | B_cab | Other | n_lb |")
    A("|-----------|-----------|---------|-----------|-------|-------|------|")
    for label in ["P90", "P95", "P99"]:
        bc = result["thresholds"][label]["binding_constraints"][POL_A]
        cc = bc["counts"]
        n_cr = bc["n_crossing"]
        n_lb = bc["left_boundary"]
        b_r = cc.get("B_ratio", 0)
        b_t = cc.get("B_thermal", 0)
        b_c = cc.get("B_cab", 0)
        other = n_cr - b_r - b_t - b_c
        A(f"| {label} | {n_cr} | {b_r} | {b_t} | {b_c} | {other} | {n_lb} |")
    A("")
    A("First binding constraint for full_random:")
    A("")
    A("| Threshold | n_crossing | B_ratio | B_thermal | B_cab | Other | n_lb |")
    A("|-----------|-----------|---------|-----------|-------|-------|------|")
    for label in ["P90", "P95", "P99"]:
        bc = result["thresholds"][label]["binding_constraints"][POL_B]
        cc = bc["counts"]
        n_cr = bc["n_crossing"]
        n_lb = bc["left_boundary"]
        b_r = cc.get("B_ratio", 0)
        b_t = cc.get("B_thermal", 0)
        b_c = cc.get("B_cab", 0)
        other = n_cr - b_r - b_t - b_c
        A(f"| {label} | {n_cr} | {b_r} | {b_t} | {b_c} | {other} | {n_lb} |")
    A("")
    A("---")
    A("")

    # Section 4: Direction persistence
    A("## 4. Direction Persistence")
    A("")
    dir_all = all(
        result["thresholds"][label]["n_A"] > result["thresholds"][label]["n_B"]
        for label in ["P90", "P95", "P99"]
    )
    A(f"Direction consistent (FP majority) across all three thresholds: **{'YES' if dir_all else 'NO'}**  ")
    A("")
    for label in ["P90", "P95", "P99"]:
        r = result["thresholds"][label]
        A(f"- {label} ({THR_LABELS[label]} C): {r['verdict_summary']}  "
          f"med delta_lo = {r['median_delta_lo_pp']:+.4f} pp")
    A("")
    A("---")
    A("")

    # Section 5: Interpretation note
    A("## 5. Interpretation Note")
    A("")
    A("This analysis is exploratory threshold sensitivity. It determines whether the FP advantage:")
    A("- persists across threshold definitions;")
    A("- changes magnitude as thermal budgets change;")
    A("- disappears or reverses at either endpoint.")
    A("")
    A("The primary preregistered evidence is the C2 corrected-reference result at P95 (T=63.625 C).")
    A("P90 and P99 are post-hoc sensitivity probes reported equally without selective emphasis.")
    A("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
