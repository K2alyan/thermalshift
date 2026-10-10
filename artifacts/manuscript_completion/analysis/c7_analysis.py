#!/usr/bin/env python3
"""
Round-7 post-exposure corrective analysis: position_group_hash comparator.
(ROUND7_AMENDMENT.md §Correction-3)

This is a descriptive robustness analysis. No confirmatory testing family.
No Holm-Bonferroni. No Wilcoxon p-values used as claims.

Canonical-beta (beta=1.11416358) comparison set:
  NEW structural comparisons (primary Round-7 evidence):
    1. FP_vs_PositionGroupHash   — full_fp vs position_group_hash
    2. PositionGroupHash_vs_Random — position_group_hash vs full_random
  Reproductions from accepted C2 (labeled — not new evidence):
    3. FP_vs_Random              — full_fp vs full_random
    4. FP_vs_WithinCab           — full_fp vs fp_withincab_placebo

Beta=0.960 sensitivity: same 4 comparisons.

Estimand: delta_lo(A,B) = C_lower_pct(A) - C_upper_pct(B)
          delta_hi(A,B) = C_upper_pct(A) - C_lower_pct(B)
Bootstrap: 5,000 paired draws, seed 9999, percentile 95% CI (for delta_lo only)

Usage:
    python artifacts/manuscript_completion/analysis/c7_analysis.py --suffix c7primary
    python artifacts/manuscript_completion/analysis/c7_analysis.py --suffix c7beta0p960

Output:
    artifacts/manuscript_completion/results/c7primary_analysis.json
    artifacts/manuscript_completion/results/c7beta0p960_analysis.json
"""
import sys, json, argparse, math
import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

ANALYSIS_RATIO = "1.25"
N_BOOTSTRAP    = 5000
BOOT_SEED      = 9999
ALPHA_EXPLORATORY = 0.05   # for exploratory sign test only — not used for claims

# ── Comparison definitions ────────────────────────────────────────────────────
# (label, policy_A, policy_B, is_new_evidence)
COMPARISONS_CANONICAL = [
    ("FP_vs_PositionGroupHash",   "full_fp",              "position_group_hash", True),
    ("PositionGroupHash_vs_Random","position_group_hash", "full_random",         True),
    ("FP_vs_Random",              "full_fp",              "full_random",         False),
    ("FP_vs_WithinCab",           "full_fp",              "fp_withincab_placebo",False),
]

parser = argparse.ArgumentParser()
parser.add_argument("--suffix", default="c7primary",
                    choices=["c7primary", "c7beta0p960"])
args = parser.parse_args()
suffix = args.suffix

def _find_merged(sfx):
    hits = sorted(OUT_DIR.glob(f"gate_f_sc30-54_*_{sfx}.json"))
    hits = [h for h in hits if "_checkpoint" not in h.name]
    return hits[-1] if hits else None

in_file = _find_merged(suffix)
if in_file is None:
    print(f"ERROR: No merged file for suffix '{suffix}' found.")
    print(f"       Expected: gate_f_sc30-54_*_{suffix}.json")
    sys.exit(1)

print(f"C7 Post-Exposure Corrective Analysis: {suffix}")
print(f"  Input: {in_file.name}")
print(f"  Ratio: r={ANALYSIS_RATIO}")
print(f"  Bootstrap: {N_BOOTSTRAP} draws, seed {BOOT_SEED}")
print()

data = json.loads(in_file.read_text(encoding="utf-8"))

# ── Extract crossings per policy per scenario ─────────────────────────────────
crossings: dict[str, dict[int, dict]] = {}
for sc in data["scenario_results"]:
    si     = sc["scenario_idx"]
    r_data = sc.get("ratios", {}).get(ANALYSIS_RATIO, {})
    for pol, pdata in r_data.items():
        crossings.setdefault(pol, {})[si] = pdata.get("crossing", {})

# Also extract lambda rows for per-policy capacity stats
lambda_rows: dict[str, dict[int, list]] = {}
for sc in data["scenario_results"]:
    si     = sc["scenario_idx"]
    r_data = sc.get("ratios", {}).get(ANALYSIS_RATIO, {})
    for pol, pdata in r_data.items():
        lambda_rows.setdefault(pol, {})[si] = pdata.get("lambda_rows", [])

scenarios = sorted(next(iter(crossings.values())).keys())
N = len(scenarios)
print(f"  Scenarios: {N} (sc{scenarios[0]}-sc{scenarios[-1]})")

rng_boot = np.random.default_rng(BOOT_SEED)


def _get_C_lower(cx: dict) -> float:
    if cx.get("status") == "left_boundary":
        return 0.0
    v = cx.get("C_lower_pct")
    return float(v) if v is not None else 0.0

def _get_C_upper(cx: dict):
    v = cx.get("C_upper_pct")
    return float(v) if v is not None else None


def analyze_pair(label: str, pol_A: str, pol_B: str, is_new: bool) -> dict:
    """
    Compute full descriptive statistics for one policy pair.
    No p-value is used as a claim. An exploratory sign test is appended but
    not used for verdict; labeled accordingly.
    """
    delta_lo_vals = []
    delta_hi_vals = []
    C_lo_A_vals   = []
    C_up_A_vals   = []
    C_lo_B_vals   = []
    C_up_B_vals   = []
    n_A = n_I = n_B = 0
    n_left_boundary_A = n_left_boundary_B = 0
    n_right_censor_A  = n_right_censor_B  = 0
    binding_A: dict[str, int] = {}
    binding_B: dict[str, int] = {}

    cx_A_all = crossings.get(pol_A, {})
    cx_B_all = crossings.get(pol_B, {})

    for si in scenarios:
        cx_A = cx_A_all.get(si, {})
        cx_B = cx_B_all.get(si, {})

        C_lo_A = _get_C_lower(cx_A)
        C_up_A = _get_C_upper(cx_A)
        C_lo_B = _get_C_lower(cx_B)
        C_up_B = _get_C_upper(cx_B)

        # Status tracking
        if cx_A.get("status") == "left_boundary":  n_left_boundary_A += 1
        if cx_B.get("status") == "left_boundary":  n_left_boundary_B += 1
        if cx_A.get("right_censored"):             n_right_censor_A  += 1
        if cx_B.get("right_censored"):             n_right_censor_B  += 1

        b_A = cx_A.get("first_binding_constraint")
        b_B = cx_B.get("first_binding_constraint")
        if b_A: binding_A[b_A] = binding_A.get(b_A, 0) + 1
        if b_B: binding_B[b_B] = binding_B.get(b_B, 0) + 1

        C_lo_A_vals.append(C_lo_A)
        C_up_A_vals.append(C_up_A if C_up_A is not None else float("nan"))
        C_lo_B_vals.append(C_lo_B)
        C_up_B_vals.append(C_up_B if C_up_B is not None else float("nan"))

        # delta_lo verdict
        if C_up_B is None:
            # B right-censored: verdict indeterminate
            delta_lo = float("nan")
            n_I += 1
        else:
            delta_lo = C_lo_A - C_up_B
            if delta_lo > 0:   n_A += 1
            elif delta_lo < 0: n_B += 1
            else:              n_I += 1
        delta_lo_vals.append(delta_lo)

        # delta_hi (optimistic bound)
        if C_up_A is None or C_lo_B is None:
            delta_hi = float("nan")
        else:
            delta_hi = C_up_A - C_lo_B
        delta_hi_vals.append(delta_hi)

    arr_lo = np.array([v for v in delta_lo_vals if not math.isnan(v)])
    arr_hi = np.array([v for v in delta_hi_vals if not math.isnan(v)])

    med_lo = float(np.median(arr_lo)) if len(arr_lo) else float("nan")
    med_hi = float(np.median(arr_hi)) if len(arr_hi) else float("nan")

    # Bootstrap 95% CI for delta_lo (on non-NaN values only)
    if len(arr_lo) >= 2:
        boot_meds = np.array([
            np.median(arr_lo[rng_boot.integers(0, len(arr_lo), size=len(arr_lo))])
            for _ in range(N_BOOTSTRAP)
        ])
        ci_lo = float(np.percentile(boot_meds, 2.5))
        ci_hi = float(np.percentile(boot_meds, 97.5))
    else:
        ci_lo = ci_hi = float("nan")

    # Absolute capacity stats
    def _stats(vals):
        arr = np.array([v for v in vals if not math.isnan(v)])
        if len(arr) == 0:
            return {"median": None, "q1": None, "q3": None, "n_finite": 0}
        return {
            "median"  : float(np.median(arr)),
            "q1"      : float(np.percentile(arr, 25)),
            "q3"      : float(np.percentile(arr, 75)),
            "n_finite": len(arr),
        }

    # Exploratory sign test (labeled — not used for claims)
    n_pos = n_A; n_neg = n_B; n_total_nonzero = n_A + n_B
    if n_total_nonzero > 0:
        from scipy import stats as sp_stats
        try:
            binom_p = float(sp_stats.binom_test(n_pos, n_total_nonzero, 0.5,
                                                  alternative="two-sided"))
        except Exception:
            binom_p = float("nan")
    else:
        binom_p = float("nan")

    print(f"  {'[NEW] ' if is_new else '[REP] '}{label}: "
          f"n={n_A}/{n_I}/{n_B}  "
          f"med_lo={med_lo:+.3f}pp  med_hi={med_hi:+.3f}pp  "
          f"CI=[{ci_lo:+.3f},{ci_hi:+.3f}]")

    return {
        "label"                 : label,
        "is_new_evidence"       : is_new,
        "policy_A"              : pol_A,
        "policy_B"              : pol_B,
        "n_A"                   : n_A,
        "n_I"                   : n_I,
        "n_B"                   : n_B,
        "median_delta_lo_pp"    : med_lo if not math.isnan(med_lo) else None,
        "median_delta_hi_pp"    : med_hi if not math.isnan(med_hi) else None,
        "CI_lo_pp"              : ci_lo  if not math.isnan(ci_lo)  else None,
        "CI_hi_pp"              : ci_hi  if not math.isnan(ci_hi)  else None,
        "C_lower_A"             : _stats(C_lo_A_vals),
        "C_upper_A"             : _stats(C_up_A_vals),
        "C_lower_B"             : _stats(C_lo_B_vals),
        "C_upper_B"             : _stats(C_up_B_vals),
        "n_left_boundary_A"     : n_left_boundary_A,
        "n_left_boundary_B"     : n_left_boundary_B,
        "n_right_censor_A"      : n_right_censor_A,
        "n_right_censor_B"      : n_right_censor_B,
        "first_binding_A"       : binding_A,
        "first_binding_B"       : binding_B,
        "delta_lo_per_scenario" : [float(v) for v in delta_lo_vals],
        "delta_hi_per_scenario" : [float(v) for v in delta_hi_vals],
        "exploratory_sign_test" : {
            "note"    : "exploratory only — not used for claims; no multiplicity adjustment",
            "n_pos"   : n_pos,
            "n_neg"   : n_neg,
            "binom_p" : binom_p if not math.isnan(binom_p) else None,
        },
    }


# ── Run all comparisons ───────────────────────────────────────────────────────
comp_results = []
for label, pol_A, pol_B, is_new in COMPARISONS_CANONICAL:
    res = analyze_pair(label, pol_A, pol_B, is_new)
    comp_results.append(res)

# ── Per-policy capacity summary ───────────────────────────────────────────────
all_policies = list({p for _, a, b, _ in COMPARISONS_CANONICAL for p in (a, b)})
capacity_summary = {}
for pol in all_policies:
    cx_pol = crossings.get(pol, {})
    c_los = [_get_C_lower(cx_pol[si]) for si in scenarios if si in cx_pol]
    c_ups_raw = [_get_C_upper(cx_pol[si]) for si in scenarios if si in cx_pol]
    c_ups = [v for v in c_ups_raw if v is not None]
    statuses = [cx_pol[si].get("status", "") for si in scenarios if si in cx_pol]
    bindings = [cx_pol[si].get("first_binding_constraint") for si in scenarios if si in cx_pol]
    capacity_summary[pol] = {
        "C_lower_pct": {
            "median": float(np.median(c_los)) if c_los else None,
            "q1"    : float(np.percentile(c_los, 25)) if c_los else None,
            "q3"    : float(np.percentile(c_los, 75)) if c_los else None,
        },
        "C_upper_pct": {
            "median"  : float(np.median(c_ups)) if c_ups else None,
            "q1"      : float(np.percentile(c_ups, 25)) if c_ups else None,
            "q3"      : float(np.percentile(c_ups, 75)) if c_ups else None,
            "n_finite": len(c_ups),
        },
        "n_left_boundary" : statuses.count("left_boundary"),
        "n_right_censored": sum(1 for si in scenarios if si in cx_pol and cx_pol[si].get("right_censored")),
        "first_binding_distribution": {b: bindings.count(b) for b in set(b for b in bindings if b)},
    }

# ── Summary ───────────────────────────────────────────────────────────────────
print()
print("=" * 65)
print(f"Round-7 Summary ({suffix})")
print("=" * 65)
for res in comp_results:
    tag = "[NEW]" if res["is_new_evidence"] else "[REP]"
    print(f"  {tag} {res['label']:35s}: "
          f"{res['n_A']}/{res['n_I']}/{res['n_B']}  "
          f"med_lo={res['median_delta_lo_pp']:+.3f}pp  "
          f"[{res['CI_lo_pp']:+.3f},{res['CI_hi_pp']:+.3f}]"
          if res['median_delta_lo_pp'] is not None else
          f"  {tag} {res['label']}: n={res['n_A']}/{res['n_I']}/{res['n_B']}")

# ── Save ──────────────────────────────────────────────────────────────────────
output = {
    "script"           : "artifacts/manuscript_completion/analysis/c7_analysis.py",
    "plan_ref"         : "Round-7 post-exposure corrective robustness analysis (position_group_hash)",
    "governance_note"  : "Post-exposure corrective analysis. Not preregistered. Descriptive only.",
    "run_suffix"       : suffix,
    "input_file"       : in_file.name,
    "analysis_ratio"   : ANALYSIS_RATIO,
    "n_scenarios"      : N,
    "n_bootstrap"      : N_BOOTSTRAP,
    "bootstrap_seed"   : BOOT_SEED,
    "beta_challenge"   : data.get("beta_challenge"),
    "comparisons"      : {res["label"]: res for res in comp_results},
    "capacity_summary" : capacity_summary,
}

out_file = OUT_DIR / f"{suffix}_analysis.json"
out_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
print()
print(f"Saved: {out_file.name}")
