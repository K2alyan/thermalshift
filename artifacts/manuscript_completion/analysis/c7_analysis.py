#!/usr/bin/env python3
"""
Round-7 structural baseline analysis: position_group_hash comparator.

Comparisons (3 total, Holm-Bonferroni corrected):
  1. FP_vs_Random           — full_fp vs full_random
  2. FP_vs_WithinCab        — full_fp vs fp_withincab_placebo
  3. FP_vs_PositionGroupHash — full_fp vs position_group_hash

Estimand: delta_lo(A,B) = C_lower(A) - C_upper(B) at r=1.25
Bootstrap: 5000 paired draws, seed 9999, percentile 95% CI
Wilcoxon signed-rank test (two-tailed)
Holm-Bonferroni: 3 comparisons, alpha=0.05

Usage:
    python artifacts/manuscript_completion/analysis/c7_analysis.py [--primary] [--beta0p960]
    (defaults to primary if no flag given)

Outputs:
    artifacts/manuscript_completion/results/c7primary_analysis.json
    artifacts/manuscript_completion/results/c7beta0p960_analysis.json
"""
import sys, json, argparse, math
import numpy as np
from pathlib import Path
from scipy import stats as sp_stats

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

ANALYSIS_RATIO   = "1.25"
N_BOOTSTRAP      = 5000
BOOT_SEED        = 9999
ALPHA            = 0.05
N_COMPARISONS    = 3

COMPARISONS = [
    ("FP_vs_Random",            "full_fp", "full_random"),
    ("FP_vs_WithinCab",         "full_fp", "fp_withincab_placebo"),
    ("FP_vs_PositionGroupHash", "full_fp", "position_group_hash"),
]

parser = argparse.ArgumentParser()
parser.add_argument("--primary",   action="store_true", default=True)
parser.add_argument("--beta0p960", action="store_true")
args = parser.parse_args()

if args.beta0p960:
    suffix   = "c7beta0p960"
else:
    suffix   = "c7primary"

def _find_merged(sfx):
    hits = sorted(OUT_DIR.glob(f"gate_f_sc30-54_*_{sfx}.json"))
    hits = [h for h in hits if "_checkpoint" not in h.name]
    return hits[-1] if hits else None

in_file = _find_merged(suffix)
if in_file is None:
    print(f"ERROR: No merged file for suffix '{suffix}' found in results/")
    print(f"       Expected pattern: gate_f_sc30-54_*_{suffix}.json")
    sys.exit(1)

print(f"C7 Analysis: {suffix}")
print(f"  Input: {in_file.name}")
print(f"  Ratio: r={ANALYSIS_RATIO}")
print(f"  Comparisons: {[c[0] for c in COMPARISONS]}")
print()

data = json.loads(in_file.read_text(encoding="utf-8"))

# ── Extract per-scenario crossings ────────────────────────────────────────────
crossing: dict[str, dict] = {}   # policy -> scenario_idx -> crossing dict

for sc in data["scenario_results"]:
    si = sc["scenario_idx"]
    ratios = sc.get("ratios", {})
    r_data = ratios.get(ANALYSIS_RATIO, {})
    for pol, pdata in r_data.items():
        crossing.setdefault(pol, {})[si] = pdata.get("crossing", {})

scenarios = sorted(next(iter(crossing.values())).keys())
N = len(scenarios)
print(f"  Scenarios loaded: {N} (sc{scenarios[0]}-sc{scenarios[-1]})")

def _get_C_lower(cx):
    if cx.get("status") == "left_boundary":
        return 0.0
    v = cx.get("C_lower_pct")
    return float(v) if v is not None else 0.0

def _get_C_upper(cx):
    v = cx.get("C_upper_pct")
    if v is None:
        return None
    return float(v)

# ── Comparative analysis ──────────────────────────────────────────────────────
rng_boot = np.random.default_rng(BOOT_SEED)

def analyze_pair(label, pol_A, pol_B):
    delta_lo_vals = []
    n_A = n_I = n_B = 0

    for si in scenarios:
        cx_A = crossing.get(pol_A, {}).get(si, {})
        cx_B = crossing.get(pol_B, {}).get(si, {})

        C_lo_A = _get_C_lower(cx_A)
        C_up_B = _get_C_upper(cx_B)

        if C_up_B is None:
            # B right-censored: treat as indeterminate
            delta_lo = 0.0
            n_I += 1
        else:
            delta_lo = C_lo_A - C_up_B
            if delta_lo > 0:
                n_A += 1
            elif delta_lo < 0:
                n_B += 1
            else:
                n_I += 1
        delta_lo_vals.append(delta_lo)

    arr = np.array(delta_lo_vals)
    med = float(np.median(arr))

    # Bootstrap 95% CI
    boot_meds = np.array([
        np.median(arr[rng_boot.integers(0, N, size=N)])
        for _ in range(N_BOOTSTRAP)
    ])
    ci_lo = float(np.percentile(boot_meds, 2.5))
    ci_hi = float(np.percentile(boot_meds, 97.5))

    # Wilcoxon signed-rank (two-tailed)
    try:
        wstat, wpval = sp_stats.wilcoxon(arr, alternative="two-sided")
    except Exception:
        wstat, wpval = float("nan"), float("nan")

    return {
        "label"             : label,
        "policy_A"          : pol_A,
        "policy_B"          : pol_B,
        "n_A"               : n_A,
        "n_I"               : n_I,
        "n_B"               : n_B,
        "median_delta_lo_pp": med,
        "CI_lo_pp"          : ci_lo,
        "CI_hi_pp"          : ci_hi,
        "wilcoxon_stat"     : wstat if not math.isnan(wstat) else None,
        "wilcoxon_pval"     : wpval if not math.isnan(wpval) else None,
        "delta_lo_per_scenario": [float(v) for v in arr],
    }

comp_results = []
for label, pol_A, pol_B in COMPARISONS:
    res = analyze_pair(label, pol_A, pol_B)
    comp_results.append(res)
    print(f"  {label}: n_A/n_I/n_B={res['n_A']}/{res['n_I']}/{res['n_B']}"
          f"  med={res['median_delta_lo_pp']:+.3f} pp"
          f"  CI=[{res['CI_lo_pp']:+.3f}, {res['CI_hi_pp']:+.3f}]"
          f"  wilcoxon_p={res['wilcoxon_pval']:.2e}" if res['wilcoxon_pval'] else
          f"  {label}: n_A/n_I/n_B={res['n_A']}/{res['n_I']}/{res['n_B']}"
          f"  med={res['median_delta_lo_pp']:+.3f} pp")

# ── Holm-Bonferroni correction ────────────────────────────────────────────────
pvals = [r["wilcoxon_pval"] for r in comp_results if r["wilcoxon_pval"] is not None]
n_valid = len(pvals)
if n_valid == N_COMPARISONS:
    sorted_idx = sorted(range(n_valid), key=lambda i: pvals[i])
    holm_p = [None] * n_valid
    for rank, ci in enumerate(sorted_idx):
        raw = pvals[ci]
        holm_p[ci] = min(1.0, raw * (N_COMPARISONS - rank))
    # Ensure monotonicity
    running_max = 0.0
    for rank in reversed(sorted_idx):
        holm_p[rank] = max(holm_p[rank], running_max)
        running_max  = holm_p[rank]
    for i, res in enumerate(comp_results):
        res["holm_p"]      = holm_p[i]
        res["significant"] = holm_p[i] < ALPHA
else:
    for res in comp_results:
        res["holm_p"] = None; res["significant"] = None

# ── Capacity table (per-policy, per-scenario) ─────────────────────────────────
capacity_table = {}
for pol in set(p for _, a, b in COMPARISONS for p in (a, b)):
    capacity_table[pol] = {}
    for si in scenarios:
        cx = crossing.get(pol, {}).get(si, {})
        capacity_table[pol][str(si)] = {
            "status"     : cx.get("status"),
            "C_lower_pct": _get_C_lower(cx),
            "C_upper_pct": _get_C_upper(cx),
            "first_binding_constraint": cx.get("first_binding_constraint"),
        }

# ── Summary print ─────────────────────────────────────────────────────────────
print()
print(f"{'='*60}")
print(f"Summary ({suffix})")
print(f"{'='*60}")
for res in comp_results:
    sig = "SIG" if res.get("significant") else "NS"
    print(f"  {res['label']:30s}: n={res['n_A']}/{res['n_I']}/{res['n_B']}"
          f"  med={res['median_delta_lo_pp']:+.3f}pp"
          f"  [{res['CI_lo_pp']:+.3f}, {res['CI_hi_pp']:+.3f}]"
          f"  holm_p={res.get('holm_p', '?'):.2e if isinstance(res.get('holm_p'), float) else '?'}"
          f"  {sig}")

# ── Save output ───────────────────────────────────────────────────────────────
output = {
    "script"              : "artifacts/manuscript_completion/analysis/c7_analysis.py",
    "plan_ref"            : f"Round-7 {suffix} analysis (position_group_hash comparator)",
    "run_suffix"          : suffix,
    "input_file"          : in_file.name,
    "analysis_ratio"      : ANALYSIS_RATIO,
    "n_scenarios"         : N,
    "n_bootstrap"         : N_BOOTSTRAP,
    "bootstrap_seed"      : BOOT_SEED,
    "alpha"               : ALPHA,
    "n_comparisons"       : N_COMPARISONS,
    "beta_challenge"      : data.get("beta_challenge"),
    "comparisons"         : {res["label"]: res for res in comp_results},
    "capacity_table"      : capacity_table,
}

out_file = OUT_DIR / f"{suffix}_analysis.json"
out_file.write_text(json.dumps(output, indent=2), encoding="utf-8")
print()
print(f"Saved: {out_file.name}")
