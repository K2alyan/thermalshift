#!/usr/bin/env python3
"""
Phase E2 — Beta Sensitivity Analysis.

Reads the 6 sensitivity runs at prespecified beta values.
For each beta: FP_vs_Random at r=1.25, 25 held-out scenarios.
Applies H7 interpretation rule (REVIEW2_CHALLENGE_PLAN.md §H7):
  - Sign reversal under any beta value → flag as key limitation.

Beta values (from REVIEW2_CHALLENGE_PLAN.md §E2):
  1. PRIMARY_BETA_CHALLENGE = 1.11416358  (operating beta; from baseline run)
  2. BETA_F_FROZEN = 1.12484352
  3. BETA_F_PROSPECTIVE = 0.96
  4. BETA_F_JACKKNIFE_MEAN = 1.08293397   (recovered from beta_jackknife_recovery.json)
  5. BETA_F_CF_P5 = 1.06587054
  6. BETA_F_CF_P95 = 1.16910447

Input files (sensitivity runner output):
  baseline (primary beta, no GATE_F_SENSITIVITY_BETA set):
    gate_f_sc30-54_1p25_r2sensitivity_sc1p00_bprimary.json
  non-primary betas (GATE_F_SENSITIVITY_BETA=<value>):
    gate_f_sc30-54_1p25_r2sensitivity_sc1p00_b<tag>.json

Output:
  artifacts/revision2/sensitivity_loo_beta.json
"""
import sys, io, json, hashlib
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
REV2_DIR  = REPO_ROOT / "artifacts" / "revision2"
RES       = REV2_DIR / "results"

sys.path.insert(0, str(REV2_DIR))
from r2_gate_f_challenge_analysis import run_analysis, N_BOOTSTRAP, BOOTSTRAP_SEED

# Recover BETA_F_JACKKNIFE_MEAN from committed artifact
_jk_path = REV2_DIR / "beta_jackknife_recovery.json"
if _jk_path.exists():
    _jk = json.loads(_jk_path.read_text())
    BETA_F_JACKKNIFE_MEAN = _jk["BETA_F_JACKKNIFE_MEAN"]
else:
    raise FileNotFoundError("beta_jackknife_recovery.json not found — run beta_jackknife_recovery.py first")

BETAS = [
    # (label, beta_value, env_tag, description)
    ("primary",       1.11416358,          "primary",     "PRIMARY_BETA_CHALLENGE (operating beta)"),
    ("beta_f_frozen", 1.12484352,          "1p12484352",  "BETA_F_FROZEN (original model estimate)"),
    ("prospective",   0.96,                "0p96",        "BETA_F_PROSPECTIVE (M1 slope)"),
    ("jackknife",     BETA_F_JACKKNIFE_MEAN, None,        "BETA_F_JACKKNIFE_MEAN (§B2a jackknife)"),
    ("cf_p5",         1.06587054,          "1p06587054",  "BETA_F_CF_P5 (5th pct cross-fit)"),
    ("cf_p95",        1.16910447,          "1p16910447",  "BETA_F_CF_P95 (95th pct cross-fit)"),
]

# Compute jackknife tag: same logic as runner (replace . with p)
BETAS[3] = (BETAS[3][0], BETA_F_JACKKNIFE_MEAN,
            str(round(BETA_F_JACKKNIFE_MEAN, 8)).replace(".", "p"),
            BETAS[3][3])

COMPARISON = [("FP_vs_Random", "full_fp", "full_random", "primary")]
RATIO      = "1.25"

print("=== Phase E2: Beta Sensitivity Analysis ===")
print(f"BETA_F_JACKKNIFE_MEAN: {BETA_F_JACKKNIFE_MEAN:.8f}")
print(f"Bootstrap: n={N_BOOTSTRAP}, seed={BOOTSTRAP_SEED}")
print()

def load_beta_file(label: str, env_tag: str) -> tuple:
    if label == "primary" or env_tag == "primary":
        candidates = [
            RES / "gate_f_sc30-54_1p25_r2sensitivity_sc1p00_bprimary.json",
            *sorted(RES.glob("gate_f_sc*_*_r2sensitivity_sc1p00_bprimary.json")),
        ]
    else:
        candidates = [
            RES / f"gate_f_sc30-54_1p25_r2sensitivity_sc1p00_b{env_tag}.json",
            *sorted(RES.glob(f"gate_f_sc*_*_r2sensitivity_sc1p00_b{env_tag}.json")),
            *sorted(RES.glob(f"*sensitivity*1p00*{env_tag}*.json")),
        ]
    for path in candidates:
        if path.exists():
            d = json.loads(path.read_text())
            scenarios = d.get("scenario_results", [])
            print(f"  {label}: loaded {len(scenarios)} scenarios from {path.name}")
            return scenarios, str(path.name), hashlib.sha256(path.read_bytes()).hexdigest()
    raise FileNotFoundError(
        f"No sensitivity file found for beta label={label!r} (env_tag={env_tag!r}).\n"
        f"Expected: {candidates[0]}\n"
        f"Run the sensitivity runner with GATE_F_SENSITIVITY_BETA=<value> first."
    )

beta_results = {}

for label, beta_val, env_tag, description in BETAS:
    scenarios, fname, sha = load_beta_file(label, env_tag)
    analysis = run_analysis(scenarios, COMPARISON, ratios=[RATIO],
                            n_bootstrap=N_BOOTSTRAP, bootstrap_seed=BOOTSTRAP_SEED)
    r = analysis["results"]["FP_vs_Random"]["ratios"][RATIO]
    beta_results[label] = {
        "label": label,
        "beta_value": round(beta_val, 8),
        "description": description,
        "source_file": fname,
        "source_sha256": sha,
        "n_scenarios": r["n"],
        "n_right_censored": r["n_right_censored"],
        "n_definitely_A": r["n_definitely_A"],
        "n_indistinguishable": r["n_indistinguishable"],
        "n_definitely_B": r["n_definitely_B"],
        "median_delta_lo": r["median_delta_lo"],
        "bootstrap95_delta_lo": r["bootstrap95_delta_lo"],
    }
    print(f"    n_A={r['n_definitely_A']} n_I={r['n_indistinguishable']} "
          f"n_B={r['n_definitely_B']} median_delta_lo={r['median_delta_lo']:.4f} pp")

print()

# ── H7 interpretation rule (§H7) ─────────────────────────────────────────────
# "Sign reversal under any sensitivity beta value must be flagged as a key limitation."
def _sign(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)

primary_median = beta_results["primary"]["median_delta_lo"]
primary_sign   = _sign(primary_median)

sign_reversals = [
    label for label, _, _, _ in BETAS
    if _sign(beta_results[label]["median_delta_lo"]) != primary_sign
]

if sign_reversals:
    h7_verdict = "KEY_LIMITATION"
    h7_text = (
        f"Sign reversal detected under beta values: {sign_reversals}. "
        "Primary FP vs Random result is sensitive to beta choice. Flag as key limitation."
    )
else:
    h7_verdict = "STABLE"
    h7_text = (
        "Sign stable across all 6 prespecified beta values. "
        "FP vs Random advantage is robust to beta calibration uncertainty."
    )

print(f"H7 verdict: {h7_verdict}")
print(f"  {h7_text}")
print()
print("Beta sensitivity table:")
print(f"{'Label':>14}  {'Beta':>12}  {'n_A':>4}  {'n_I':>4}  {'n_B':>4}  {'median_delta_lo':>18}  CI")
for label, beta_val, _, _ in BETAS:
    r = beta_results[label]
    ci = r["bootstrap95_delta_lo"]
    print(f"  {label:>14}  {beta_val:>12.8f}  {r['n_definitely_A']:>4}  "
          f"{r['n_indistinguishable']:>4}  {r['n_definitely_B']:>4}  "
          f"{r['median_delta_lo']:>+18.4f}  [{ci[0]:+.4f}, {ci[1]:+.4f}]")

result = {
    "script": "artifacts/revision2/analyze_sensitivity_e2.py",
    "plan_ref": "REVIEW2_CHALLENGE_PLAN.md §E2 and §H7",
    "comparison": "FP_vs_Random",
    "ratio": RATIO,
    "n_bootstrap": N_BOOTSTRAP,
    "bootstrap_seed": BOOTSTRAP_SEED,
    "beta_values_tested": [
        {"label": l, "beta": round(bv, 8), "description": d}
        for l, bv, _, d in BETAS
    ],
    "BETA_F_JACKKNIFE_MEAN_source": "artifacts/revision2/beta_jackknife_recovery.json",
    "h7_verdict": h7_verdict,
    "h7_text": h7_text,
    "sign_reversals": sign_reversals,
    "beta_results": beta_results,
}

out_path = REV2_DIR / "sensitivity_loo_beta.json"
out_path.write_text(json.dumps(result, indent=2))
print(f"\nWritten: {out_path}")
