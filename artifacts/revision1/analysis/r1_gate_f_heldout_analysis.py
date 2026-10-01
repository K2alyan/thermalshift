#!/usr/bin/env python3
"""
r1_gate_f_heldout_analysis.py

Frozen held-out summarizer for Gate F: Dynamic Feasible-Choice Sensitivity.

THIS FILE MUST NOT BE MODIFIED AFTER SEEING sc5–29 DATA.

Hard-coded constants (frozen per GATE_F_DESIGN §8.3, §10, §12):
  authoritative_scenarios = sc5..sc29 only  (N = 25)
  ratios = 1.0, 1.25, 1.5, 2.0, 4.0, 8.0, unrestricted
  comparisons:
    FP_vs_Random       A=full_fp         B=full_random
    Loc_vs_Random      A=full_loc        B=full_random
    FPSpread_vs_Random A=full_fp_spread  B=full_random
    FPSpread_vs_FP     A=full_fp_spread  B=full_fp
    FPSpread_vs_Loc    A=full_fp_spread  B=full_loc
  delta_lo = C_lower_A - C_upper_B   (pessimistic; A better iff > 0)
  delta_hi = C_upper_A - C_lower_B   (optimistic)
  definitely_A_better iff delta_lo > 0
  definitely_B_better iff delta_hi < 0
  otherwise indistinguishable
  N_BOOTSTRAP = 5000
  BOOTSTRAP_SEED = 9999
  bootstrap resampling unit = scenario (paired)

Fails immediately (exit 1) if any of the following are violated:
  - any authoritative scenario missing from input files
  - any scenario outside authoritative range enters primary analysis
  - any ratio missing from input files
  - any policy missing from input files
  - duplicate (sc, ratio, policy) cell
  - C_lower > C_upper in any cell
  - n_base_unserved != 0 in any lambda row
  - invariant_violated == True in any lambda row
  - NaN or Inf in C_lower_pct or C_upper_pct of any cell
  - unexpected right-censored cell
  - delta_lo > delta_hi (GATE_F_DESIGN §10.1)
  - unrestricted crossings do not reproduce M4 v3 reference values

Usage:
  python r1_gate_f_heldout_analysis.py                 # held-out sc5-29
  python r1_gate_f_heldout_analysis.py --dry-run       # dev sc0-4 (code test only)
"""

import sys, io, os, json, hashlib, math, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
from pathlib import Path

# ── Frozen constants ───────────────────────────────────────────────────────────
HELDOUT_SCENARIOS = list(range(5, 30))   # sc5–sc29, N=25
N                 = 25
DEV_SCENARIOS     = list(range(0, 5))    # sc0–sc4, for dry-run only

RATIOS_STR = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"]
POLICIES   = ["full_random", "full_fp", "full_loc", "full_fp_spread"]

COMPARISONS = [
    ("FP_vs_Random",      "full_fp",        "full_random",  "fp_vs_canonical_rand"),
    ("Loc_vs_Random",     "full_loc",        "full_random",  "loc_vs_canonical_rand"),
    ("FPSpread_vs_Random","full_fp_spread",  "full_random",  "spread_vs_canonical_rand"),
    ("FPSpread_vs_FP",    "full_fp_spread",  "full_fp",      "spread_vs_fp"),
    ("FPSpread_vs_Loc",   "full_fp_spread",  "full_loc",     "spread_vs_canonical_loc"),
]

N_BOOTSTRAP    = 5000
BOOTSTRAP_SEED = 9999

M4_TOLERANCE_PP = 1e-9  # tolerance for unrestricted vs M4 v3 verification

# ── Paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "revision1" / "results"

# Input file name templates (same naming convention as r1_gate_f_run.py)
# held-out:  gate_f_sc5-29_unr.json, gate_f_sc5-29_1p0.json,
#            gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json
# dry-run:   gate_f_sc0-4_unr.json, gate_f_sc0-4_1p0.json,
#            gate_f_sc0-4_1p25_1p5_2p0_4p0_8p0.json

# ── CLI ────────────────────────────────────────────────────────────────────────
DRY_RUN = "--dry-run" in sys.argv

if DRY_RUN:
    AUTHORITATIVE_SCENARIOS = DEV_SCENARIOS
    SCEN_TAG   = "sc0-4"
    ANALYSIS_TYPE = "dry_run_dev"
    OUT_FILE   = OUT_DIR / "gate_f_heldout_analysis_dryrun.json"
else:
    AUTHORITATIVE_SCENARIOS = HELDOUT_SCENARIOS
    SCEN_TAG   = "sc5-29"
    ANALYSIS_TYPE = "held_out"
    OUT_FILE   = OUT_DIR / "gate_f_heldout_analysis.json"

N_AUTH = len(AUTHORITATIVE_SCENARIOS)

# ── Helpers ────────────────────────────────────────────────────────────────────
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def sha256_script() -> str:
    return sha256_file(Path(__file__))

def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    except Exception:
        return "unknown"

def _git_clean() -> bool:
    try:
        return not bool(subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=str(REPO_ROOT), text=True).strip())
    except Exception:
        return None

def fail(msg: str):
    print(f"\nFAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def _is_finite(v) -> bool:
    if v is None:
        return False
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False

# ── Load and parse JSON files ─────────────────────────────────────────────────
def load_json_file(path: Path) -> dict:
    if not path.exists():
        fail(f"Input file not found: {path}")
    with open(path) as f:
        return json.load(f)

def extract_crossings_from_file(d: dict, expected_ratios: list[str],
                                 source_label: str) -> dict:
    """
    Returns: crossings[sc_idx][ratio_str][policy] = crossing dict
    Also returns a list of (sc_idx, ratio_str, policy, lambda_rows) for QoS checks.
    """
    crossings = {}
    lambda_data = []  # (sc_idx, ratio_str, policy, lambda_rows_list)

    sr = d.get("scenario_results", [])
    if not isinstance(sr, list):
        fail(f"{source_label}: scenario_results is not a list")

    for sc_entry in sr:
        sc_idx = sc_entry.get("scenario_idx")
        if sc_idx is None:
            fail(f"{source_label}: scenario entry missing scenario_idx")
        sc_idx = int(sc_idx)

        ratios_dict = sc_entry.get("ratios", {})
        for ratio_str, pol_dict in ratios_dict.items():
            if ratio_str not in expected_ratios:
                # Skip ratios not expected from this file
                continue
            if sc_idx not in crossings:
                crossings[sc_idx] = {}
            if ratio_str not in crossings[sc_idx]:
                crossings[sc_idx][ratio_str] = {}

            for pol in POLICIES:
                pol_data = pol_dict.get(pol, {})
                cx = pol_data.get("crossing", {})
                lr = pol_data.get("lambda_rows", [])

                if pol in crossings[sc_idx][ratio_str]:
                    fail(f"{source_label}: duplicate cell sc={sc_idx} r={ratio_str} pol={pol}")
                crossings[sc_idx][ratio_str][pol] = cx
                lambda_data.append((sc_idx, ratio_str, pol, lr))

    return crossings, lambda_data

print(f"\nGate F: Held-Out Analysis  [{ANALYSIS_TYPE}]")
print("=" * 70)

# Locate input files
FILE_UNR  = OUT_DIR / f"gate_f_{SCEN_TAG}_unr.json"
FILE_R1   = OUT_DIR / f"gate_f_{SCEN_TAG}_1p0.json"
FILE_REST = OUT_DIR / f"gate_f_{SCEN_TAG}_1p25_1p5_2p0_4p0_8p0.json"
FILE_M4   = OUT_DIR / "m4_canonical_comparisons_v3_corrected.json"
FILE_QMAN = OUT_DIR / "gate_f_quartile_manifest.json"

print("\n[0] Input files ...")
for label, fp in [("unrestricted", FILE_UNR), ("r=1", FILE_R1),
                  ("restricted", FILE_REST), ("M4 v3 corrected", FILE_M4),
                  ("quartile manifest", FILE_QMAN)]:
    status = "found" if fp.exists() else "MISSING"
    print(f"    {label}: {fp.name}  [{status}]")

for fp in [FILE_UNR, FILE_R1, FILE_REST, FILE_M4, FILE_QMAN]:
    if not fp.exists():
        fail(f"Required input file not found: {fp}")

# Record SHA-256 of all input files
input_sha = {
    "gate_f_unr"     : sha256_file(FILE_UNR),
    "gate_f_r1"      : sha256_file(FILE_R1),
    "gate_f_rest"    : sha256_file(FILE_REST),
    "m4_v3"          : sha256_file(FILE_M4),
    "quartile_manifest": sha256_file(FILE_QMAN),
    "this_script"    : sha256_script(),
}
print("\n  Input SHA-256:")
for k, v in input_sha.items():
    print(f"    {k}: {v[:16]}...")

# Load all files
d_unr  = load_json_file(FILE_UNR)
d_r1   = load_json_file(FILE_R1)
d_rest = load_json_file(FILE_REST)
d_m4   = load_json_file(FILE_M4)

# ── Build combined crossing table ─────────────────────────────────────────────
print("\n[1] Building crossing table ...")

cx_unr,  lr_unr  = extract_crossings_from_file(d_unr,  ["unrestricted"],                       "unr file")
cx_r1,   lr_r1   = extract_crossings_from_file(d_r1,   ["1.0"],                                "r1 file")
cx_rest, lr_rest = extract_crossings_from_file(d_rest, ["1.25","1.5","2.0","4.0","8.0"],       "rest file")

# Merge into unified crossings dict
all_crossings: dict[int, dict[str, dict[str, dict]]] = {}
all_lambda_data = lr_unr + lr_r1 + lr_rest

def _merge_crossings(source: dict, target: dict, source_label: str):
    for sc_idx, ratio_dict in source.items():
        if sc_idx not in target:
            target[sc_idx] = {}
        for ratio_str, pol_dict in ratio_dict.items():
            if ratio_str not in target[sc_idx]:
                target[sc_idx][ratio_str] = {}
            for pol, cx in pol_dict.items():
                if pol in target[sc_idx].get(ratio_str, {}):
                    fail(f"Duplicate cell across files: sc={sc_idx} r={ratio_str} pol={pol} (source={source_label})")
                target[sc_idx][ratio_str][pol] = cx

_merge_crossings(cx_unr,  all_crossings, "unr")
_merge_crossings(cx_r1,   all_crossings, "r1")
_merge_crossings(cx_rest, all_crossings, "rest")

print(f"    Scenarios found: {sorted(all_crossings.keys())}")

# ── Validation ────────────────────────────────────────────────────────────────
print("\n[2] Validation ...")

errors = []

# 2a. Correct scenario set
found_scenarios = set(all_crossings.keys())
auth_set        = set(AUTHORITATIVE_SCENARIOS)
missing  = auth_set - found_scenarios
extra    = found_scenarios - auth_set

if missing:
    errors.append(f"Missing authoritative scenarios: {sorted(missing)}")
if extra:
    errors.append(f"Extra scenarios outside authoritative range: {sorted(extra)}")

# 2b. All ratios and policies present for each authoritative scenario
n_cells_expected = N_AUTH * len(RATIOS_STR) * len(POLICIES)
n_cells_found = 0
for sc_idx in AUTHORITATIVE_SCENARIOS:
    if sc_idx not in all_crossings:
        continue
    for ratio_str in RATIOS_STR:
        if ratio_str not in all_crossings[sc_idx]:
            errors.append(f"sc={sc_idx}: ratio '{ratio_str}' missing")
            continue
        for pol in POLICIES:
            if pol not in all_crossings[sc_idx][ratio_str]:
                errors.append(f"sc={sc_idx} r={ratio_str}: policy '{pol}' missing")
            else:
                n_cells_found += 1

# 2c. Crossing validity: C_lower <= C_upper, no NaN/Inf, no unexpected right-censored
n_inversions = 0
n_nan_inf    = 0
n_right_cens = 0
for sc_idx in AUTHORITATIVE_SCENARIOS:
    if sc_idx not in all_crossings:
        continue
    for ratio_str in RATIOS_STR:
        if ratio_str not in all_crossings.get(sc_idx, {}):
            continue
        for pol in POLICIES:
            cx = all_crossings[sc_idx][ratio_str].get(pol, {})
            c_lo = cx.get("C_lower_pct")
            c_hi = cx.get("C_upper_pct")
            rc   = cx.get("right_censored", False)

            if rc:
                n_right_cens += 1
                errors.append(f"Unexpected right-censored: sc={sc_idx} r={ratio_str} pol={pol}")

            if c_lo is None or c_hi is None:
                if not rc:
                    errors.append(f"Missing C_lower/C_upper: sc={sc_idx} r={ratio_str} pol={pol}")
                continue

            if not _is_finite(c_lo) or not _is_finite(c_hi):
                n_nan_inf += 1
                errors.append(f"NaN/Inf: sc={sc_idx} r={ratio_str} pol={pol}: lo={c_lo} hi={c_hi}")
                continue

            if float(c_lo) > float(c_hi) + 1e-12:
                n_inversions += 1
                errors.append(f"Inverted crossing: sc={sc_idx} r={ratio_str} pol={pol}: C_lower={c_lo:.6f}% > C_upper={c_hi:.6f}%")

# 2d. QoS invariants: n_base_unserved==0, invariant_violated==False for every lambda row
n_qos_violations = 0
for sc_idx, ratio_str, pol, lr_list in all_lambda_data:
    if sc_idx not in auth_set:
        continue
    for lr in lr_list:
        if int(lr.get("n_base_unserved", 0)) != 0:
            n_qos_violations += 1
            errors.append(f"n_base_unserved != 0: sc={sc_idx} r={ratio_str} pol={pol}")
        if lr.get("invariant_violated", False):
            n_qos_violations += 1
            errors.append(f"invariant_violated==True: sc={sc_idx} r={ratio_str} pol={pol}")

print(f"    Expected cells: {n_cells_expected}  Found: {n_cells_found}")
print(f"    Inversions: {n_inversions}  NaN/Inf: {n_nan_inf}  Right-censored: {n_right_cens}")
print(f"    QoS violations: {n_qos_violations}")

if errors:
    for e in errors[:20]:
        print(f"  ERROR: {e}", file=sys.stderr)
    if len(errors) > 20:
        print(f"  ... and {len(errors)-20} more errors", file=sys.stderr)
    fail(f"Validation failed: {len(errors)} error(s)")

print("    => All validation checks PASS")

# ── Per-scenario delta computation ────────────────────────────────────────────
print("\n[3] Computing per-scenario deltas ...")

def get_crossing(sc_idx: int, ratio_str: str, pol: str) -> tuple[float, float]:
    cx = all_crossings[sc_idx][ratio_str][pol]
    return float(cx["C_lower_pct"]), float(cx["C_upper_pct"])

# results[comp_name][ratio_str] = {delta_lo_arr, delta_hi_arr, verdicts, ...}
results: dict[str, dict[str, dict]] = {}

for comp_name, pol_A, pol_B, m4_key in COMPARISONS:
    results[comp_name] = {}
    for ratio_str in RATIOS_STR:
        delta_lo_list = []
        delta_hi_list = []
        verdicts      = []

        for sc_idx in AUTHORITATIVE_SCENARIOS:
            lo_A, hi_A = get_crossing(sc_idx, ratio_str, pol_A)
            lo_B, hi_B = get_crossing(sc_idx, ratio_str, pol_B)
            d_lo = lo_A - hi_B
            d_hi = hi_A - lo_B
            if d_lo > d_hi + 1e-12:
                fail(f"delta_lo > delta_hi violated (§10.1): {comp_name} sc={sc_idx} r={ratio_str}"
                     f"  d_lo={d_lo:.6f} d_hi={d_hi:.6f}")
            if d_lo > 0:
                verdict = "definitely_A_better"
            elif d_hi < 0:
                verdict = "definitely_B_better"
            else:
                verdict = "indistinguishable"
            delta_lo_list.append(d_lo)
            delta_hi_list.append(d_hi)
            verdicts.append(verdict)

        delta_lo_arr = np.array(delta_lo_list)
        delta_hi_arr = np.array(delta_hi_list)

        n_A   = sum(1 for v in verdicts if v == "definitely_A_better")
        n_B   = sum(1 for v in verdicts if v == "definitely_B_better")
        n_ind = sum(1 for v in verdicts if v == "indistinguishable")

        results[comp_name][ratio_str] = {
            "n"                 : N_AUTH,
            "n_definitely_A"    : n_A,
            "n_indistinguishable": n_ind,
            "n_definitely_B"    : n_B,
            "delta_lo_arr"      : delta_lo_arr,
            "delta_hi_arr"      : delta_hi_arr,
            "verdicts"          : verdicts,
        }

# ── Bootstrap ─────────────────────────────────────────────────────────────────
print(f"\n[4] Bootstrap CI  (N={N_BOOTSTRAP}, seed={BOOTSTRAP_SEED}) ...")

rng = np.random.default_rng(BOOTSTRAP_SEED)

for comp_name, pol_A, pol_B, m4_key in COMPARISONS:
    for ratio_str in RATIOS_STR:
        r = results[comp_name][ratio_str]
        d_lo = r["delta_lo_arr"]
        d_hi = r["delta_hi_arr"]

        bs_med_lo = np.empty(N_BOOTSTRAP)
        bs_med_hi = np.empty(N_BOOTSTRAP)
        for b in range(N_BOOTSTRAP):
            idx = rng.integers(0, N_AUTH, size=N_AUTH)
            bs_med_lo[b] = np.median(d_lo[idx])
            bs_med_hi[b] = np.median(d_hi[idx])

        r["median_delta_lo"]      = float(np.median(d_lo))
        r["bootstrap95_delta_lo"] = [float(np.percentile(bs_med_lo, 2.5)),
                                      float(np.percentile(bs_med_lo, 97.5))]
        r["median_delta_hi"]      = float(np.median(d_hi))
        r["bootstrap95_delta_hi"] = [float(np.percentile(bs_med_hi, 2.5)),
                                      float(np.percentile(bs_med_hi, 97.5))]

print("    Done.")

# ── Unrestricted vs M4 v3 verification ────────────────────────────────────────
print("\n[5] Unrestricted vs M4 v3 verification ...")

m4_comps = d_m4.get("comparisons", {})
m4_n_bootstrap  = d_m4.get("n_bootstrap",   None)
m4_bootstrap_seed = d_m4.get("bootstrap_seed", None)

if m4_n_bootstrap != N_BOOTSTRAP:
    print(f"  NOTE: M4 n_bootstrap={m4_n_bootstrap}, Gate F uses {N_BOOTSTRAP}")
if m4_bootstrap_seed != BOOTSTRAP_SEED:
    print(f"  NOTE: M4 bootstrap_seed={m4_bootstrap_seed}, Gate F uses {BOOTSTRAP_SEED}")

m4_verify_results = {}
unr_verify_pass = True

for comp_name, pol_A, pol_B, m4_key in COMPARISONS:
    m4_comp = m4_comps.get(m4_key)
    if m4_comp is None:
        fail(f"M4 v3 comparison '{m4_key}' not found in {FILE_M4.name}")

    m4_sc_rows = {r["scenario_idx"]: r for r in m4_comp["scenario_rows"]}

    # ── Reference completeness guard ──────────────────────────────────────────
    n_ref_expected = len(AUTHORITATIVE_SCENARIOS)
    n_ref_observed = sum(1 for sc in AUTHORITATIVE_SCENARIOS if sc in m4_sc_rows)
    ref_complete   = (n_ref_observed == n_ref_expected)

    if not DRY_RUN:
        # Held-out: all 25 reference rows must be present and the set must be exact.
        expected_set = set(AUTHORITATIVE_SCENARIOS)   # sc5–sc29
        actual_set   = set(m4_sc_rows.keys())
        missing_refs = sorted(expected_set - actual_set)
        extra_refs   = sorted(actual_set   - expected_set)
        if missing_refs:
            fail(f"M4 reference missing {len(missing_refs)} scenario(s) for "
                 f"'{m4_key}': {missing_refs}. "
                 f"Expected exactly {n_ref_expected} rows (sc5–sc29).")
        if extra_refs:
            fail(f"M4 reference has {len(extra_refs)} unexpected scenario(s) for "
                 f"'{m4_key}': {extra_refs}. "
                 f"Expected exactly sc5–sc29.")
        assert ref_complete, (
            f"Internal: completeness mismatch post-check for {m4_key}")

    max_diff_lo = 0.0
    max_diff_hi = 0.0
    cell_errors = []

    for sc_idx in AUTHORITATIVE_SCENARIOS:
        m4_row = m4_sc_rows.get(sc_idx)
        if m4_row is None:
            if DRY_RUN:
                # Known design gap: spread comparisons have no sc0–4 entries in
                # the M4 corrected reference. Silently skip in dry-run only.
                continue
            else:
                # Unreachable after the completeness assertion above.
                fail(f"Internal: sc={sc_idx} missing from '{m4_key}' "
                     f"after completeness check passed")

        lo_A, hi_A = get_crossing(sc_idx, "unrestricted", pol_A)
        lo_B, hi_B = get_crossing(sc_idx, "unrestricted", pol_B)
        gf_d_lo = lo_A - hi_B
        gf_d_hi = hi_A - lo_B

        # M4 stores C_lower_A, C_upper_A, C_lower_B, C_upper_B directly
        m4_d_lo = m4_row["C_lower_A"] - m4_row["C_upper_B"]
        m4_d_hi = m4_row["C_upper_A"] - m4_row["C_lower_B"]

        diff_lo = abs(gf_d_lo - m4_d_lo)
        diff_hi = abs(gf_d_hi - m4_d_hi)
        max_diff_lo = max(max_diff_lo, diff_lo)
        max_diff_hi = max(max_diff_hi, diff_hi)

        if diff_lo > M4_TOLERANCE_PP or diff_hi > M4_TOLERANCE_PP:
            cell_errors.append(
                f"sc={sc_idx}: GF d_lo={gf_d_lo:.10f} M4 d_lo={m4_d_lo:.10f} "
                f"diff={diff_lo:.2e}pp"
            )

    status = "PASS" if not cell_errors else "FAIL"
    if cell_errors:
        unr_verify_pass = False
    ref_status = "COMPLETE" if ref_complete else "INCOMPLETE (dry-run gap)"
    print(f"  {comp_name}: ref={n_ref_observed}/{n_ref_expected}  "
          f"max_diff_lo={max_diff_lo:.2e}pp  max_diff_hi={max_diff_hi:.2e}pp  "
          f"=> {status}  [{ref_status}]")
    for ce in cell_errors[:5]:
        print(f"    ERROR: {ce}", file=sys.stderr)

    m4_verify_results[comp_name] = {
        "m4_key"                  : m4_key,
        "expected_reference_rows" : n_ref_expected,
        "observed_reference_rows" : n_ref_observed,
        "reference_completeness_pass": ref_complete,
        "max_diff_lo_pp"          : max_diff_lo,
        "max_diff_hi_pp"          : max_diff_hi,
        "pass"                    : not cell_errors,
        "errors"                  : cell_errors,
    }

if not unr_verify_pass:
    fail("Unrestricted crossings do not reproduce M4 v3 reference values")

# ── Print summary table ───────────────────────────────────────────────────────
print("\n" + "=" * 70)
print("RESULTS SUMMARY")
print("=" * 70)

for comp_name, pol_A, pol_B, _ in COMPARISONS:
    print(f"\n  {comp_name}  (A={pol_A}  B={pol_B})")
    print(f"  {'ratio':>14}  {'n_A':>5}  {'n_ind':>5}  {'n_B':>5}"
          f"  {'med_dlo':>10}  {'CI95_dlo':>22}  {'med_dhi':>10}")
    for ratio_str in RATIOS_STR:
        r = results[comp_name][ratio_str]
        ci_lo = r["bootstrap95_delta_lo"]
        print(f"  {ratio_str:>14}  {r['n_definitely_A']:>5}  "
              f"{r['n_indistinguishable']:>5}  {r['n_definitely_B']:>5}  "
              f"{r['median_delta_lo']:>+10.3f}  "
              f"[{ci_lo[0]:>+8.3f},{ci_lo[1]:>+8.3f}]  "
              f"{r['median_delta_hi']:>+10.3f}")

# ── Serialize results ─────────────────────────────────────────────────────────
def _arr_to_list(v):
    if isinstance(v, np.ndarray):
        return [float(x) for x in v]
    return v

out_results = {}
for comp_name, pol_A, pol_B, m4_key in COMPARISONS:
    out_results[comp_name] = {
        "policy_A": pol_A,
        "policy_B": pol_B,
        "ratios"  : {},
    }
    for ratio_str in RATIOS_STR:
        r = results[comp_name][ratio_str]
        out_results[comp_name]["ratios"][ratio_str] = {
            "n"                    : r["n"],
            "n_definitely_A"       : r["n_definitely_A"],
            "n_indistinguishable"  : r["n_indistinguishable"],
            "n_definitely_B"       : r["n_definitely_B"],
            "verdicts"             : r["verdicts"],
            "median_delta_lo"      : r["median_delta_lo"],
            "bootstrap95_delta_lo" : r["bootstrap95_delta_lo"],
            "median_delta_hi"      : r["median_delta_hi"],
            "bootstrap95_delta_hi" : r["bootstrap95_delta_hi"],
            "delta_lo_per_scenario": _arr_to_list(r["delta_lo_arr"]),
            "delta_hi_per_scenario": _arr_to_list(r["delta_hi_arr"]),
        }

out = {
    "analysis_type"          : ANALYSIS_TYPE,
    "authoritative_scenarios": AUTHORITATIVE_SCENARIOS,
    "n"                      : N_AUTH,
    "ratios"                 : RATIOS_STR,
    "policies"               : POLICIES,
    "comparisons_frozen"     : [c[0] for c in COMPARISONS],
    "n_bootstrap"            : N_BOOTSTRAP,
    "bootstrap_seed"         : BOOTSTRAP_SEED,
    "delta_formula"          : {
        "delta_lo" : "C_lower_A - C_upper_B",
        "delta_hi" : "C_upper_A - C_lower_B",
        "definitely_A_better": "delta_lo > 0",
        "definitely_B_better": "delta_hi < 0",
        "indistinguishable"  : "otherwise",
    },
    "validation": {
        "n_cells_expected"   : n_cells_expected,
        "n_cells_found"      : n_cells_found,
        "n_inversions"       : n_inversions,
        "n_nan_inf"          : n_nan_inf,
        "n_right_censored"   : n_right_cens,
        "n_qos_violations"   : n_qos_violations,
        "missing_scenarios"  : sorted(missing) if missing else [],
        "extra_scenarios"    : sorted(extra) if extra else [],
        "all_pass"           : True,
    },
    "unrestricted_m4_verification": m4_verify_results,
    "results"               : out_results,
    "provenance"            : {
        "freeze_head"        : _git_head(),
        "tracked_tree_clean" : _git_clean(),
        "input_sha256"       : input_sha,
        "analysis_script"    : str(Path(__file__).name),
    },
}

with open(OUT_FILE, "w") as f:
    json.dump(out, f, indent=2)

print(f"\nSaved: {OUT_FILE}")
print()
print("=" * 70)
print(f"Gate F Held-Out Analysis [{ANALYSIS_TYPE.upper()}]: COMPLETE")
print(f"  Scenarios: {SCEN_TAG}  N={N_AUTH}")
print(f"  All validation: PASS")
print(f"  Unrestricted vs M4 v3: PASS")
print("=" * 70)
