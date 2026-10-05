#!/usr/bin/env python3
"""
Phase E1 — Cabinet-Reference Sensitivity Analysis.

Reads the 5 sensitivity runs at scale factors [0.90, 0.95, 1.00, 1.05, 1.10].
For each scale: FP_vs_Random at r=1.25, 25 held-out scenarios.
Applies H8 interpretation rule (REVIEW2_CHALLENGE_PLAN.md §H8).

Inputs:
  artifacts/revision2/results/gate_f_sc30-54_1p25_r2sensitivity_sc{tag}_bprimary.json
  for tag in [0p90, 0p95, 1p00, 1p05, 1p10]

Output:
  artifacts/revision2/sensitivity_cabinet_scale.json

Run after all 5 E1 sensitivity runs complete (1.00 comes from baseline equivalence run).
"""
import sys, io, json, hashlib
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
REV2_DIR  = REPO_ROOT / "artifacts" / "revision2"
RES       = REV2_DIR / "results"

sys.path.insert(0, str(REV2_DIR))
from r2_gate_f_challenge_analysis import run_analysis, N_BOOTSTRAP, BOOTSTRAP_SEED

SCALES = [0.90, 0.95, 1.00, 1.05, 1.10]
SCALE_TAGS = {0.90: "0p90", 0.95: "0p95", 1.00: "1p00", 1.05: "1p05", 1.10: "1p10"}

COMPARISON = [("FP_vs_Random", "full_fp", "full_random", "primary")]
RATIO      = "1.25"

print("=== Phase E1: Cabinet-Reference Sensitivity Analysis ===")
print(f"Scale factors: {SCALES}")
print(f"Bootstrap: n={N_BOOTSTRAP}, seed={BOOTSTRAP_SEED}")
print()

def load_sensitivity_file(scale: float) -> list:
    tag = SCALE_TAGS[scale]
    # Try exact expected filename first, then wildcards
    candidates = [
        RES / f"gate_f_sc30-54_1p25_r2sensitivity_sc{tag}_bprimary.json",
        *sorted(RES.glob(f"gate_f_sc*_*_r2sensitivity_sc{tag}_bprimary.json")),
        *sorted(RES.glob(f"*sensitivity*sc{tag}*primary*.json")),
    ]
    for path in candidates:
        if path.exists():
            d = json.loads(path.read_text())
            scenarios = d.get("scenario_results", [])
            print(f"  scale={scale}: loaded {len(scenarios)} scenarios from {path.name}")
            return scenarios, str(path.name), hashlib.sha256(path.read_bytes()).hexdigest()
    raise FileNotFoundError(
        f"No sensitivity file found for scale={scale} (tag={tag}).\n"
        f"Expected: {candidates[0]}\n"
        f"Run the sensitivity runner with GATE_F_CAB_SCALE={scale} first."
    )

scale_results = {}
source_files  = {}

for scale in SCALES:
    scenarios, fname, sha = load_sensitivity_file(scale)
    analysis = run_analysis(scenarios, COMPARISON, ratios=[RATIO],
                            n_bootstrap=N_BOOTSTRAP, bootstrap_seed=BOOTSTRAP_SEED)
    r = analysis["results"]["FP_vs_Random"]["ratios"][RATIO]
    scale_results[scale] = {
        "scale": scale,
        "source_file": fname,
        "source_sha256": sha,
        "n_scenarios": r["n"],
        "n_right_censored": r["n_right_censored"],
        "n_definitely_A": r["n_definitely_A"],
        "n_indistinguishable": r["n_indistinguishable"],
        "n_definitely_B": r["n_definitely_B"],
        "median_delta_lo": r["median_delta_lo"],
        "bootstrap95_delta_lo": r["bootstrap95_delta_lo"],
        "delta_lo_per_scenario": r["delta_lo_per_scenario"],
    }
    source_files[str(scale)] = {"file": fname, "sha256": sha}
    print(f"  scale={scale}: n_A={r['n_definitely_A']} n_I={r['n_indistinguishable']} "
          f"n_B={r['n_definitely_B']} median_delta_lo={r['median_delta_lo']:.4f} pp")

print()

# ── H8 interpretation rule (§H8) ─────────────────────────────────────────────
# Sign of median_delta_lo: positive means FP better.
# "sign change" = median_delta_lo crosses zero.
inner_scales = [0.95, 1.00, 1.05]
outer_scales = SCALES

def _sign(x):
    return 1 if x > 0 else (-1 if x < 0 else 0)

primary_sign = _sign(scale_results[1.00]["median_delta_lo"])

inner_sign_change = any(
    _sign(scale_results[s]["median_delta_lo"]) != primary_sign
    for s in inner_scales
)
outer_sign_stable = all(
    _sign(scale_results[s]["median_delta_lo"]) == primary_sign
    for s in outer_scales
)

if inner_sign_change:
    h8_verdict = "KEY_LIMITATION"
    h8_text = (
        "Sign change within [0.95, 1.05]: result is sensitive to cabinet-envelope "
        "calibration. Report as a key limitation."
    )
elif outer_sign_stable:
    h8_verdict = "ROBUST"
    h8_text = (
        "Sign stable across [0.90, 1.10]: FP vs Random advantage is robust to "
        "±10% cabinet-envelope scaling."
    )
else:
    h8_verdict = "MIXED"
    h8_text = (
        "Sign stable within [0.95, 1.05] but changes outside that range. "
        "Partial robustness: stable in inner window, sensitive at ±10%."
    )

print(f"H8 verdict: {h8_verdict}")
print(f"  {h8_text}")
print()
print("Scale-factor table:")
print(f"{'Scale':>8}  {'n_A':>4}  {'n_I':>4}  {'n_B':>4}  {'median_delta_lo':>18}  CI")
for s in SCALES:
    r = scale_results[s]
    ci = r["bootstrap95_delta_lo"]
    print(f"  {s:>6.2f}  {r['n_definitely_A']:>4}  {r['n_indistinguishable']:>4}  "
          f"{r['n_definitely_B']:>4}  {r['median_delta_lo']:>+18.4f}  "
          f"[{ci[0]:+.4f}, {ci[1]:+.4f}]")

result = {
    "script": "artifacts/revision2/analyze_sensitivity_e1.py",
    "plan_ref": "REVIEW2_CHALLENGE_PLAN.md §E1 and §H8",
    "comparison": "FP_vs_Random",
    "ratio": RATIO,
    "n_bootstrap": N_BOOTSTRAP,
    "bootstrap_seed": BOOTSTRAP_SEED,
    "scales": SCALES,
    "h8_verdict": h8_verdict,
    "h8_text": h8_text,
    "inner_sign_change": inner_sign_change,
    "outer_sign_stable": outer_sign_stable,
    "source_files": source_files,
    "scale_results": {str(s): v for s, v in scale_results.items()},
}

out_path = REV2_DIR / "sensitivity_cabinet_scale.json"
out_path.write_text(json.dumps(result, indent=2))
print(f"\nWritten: {out_path}")
