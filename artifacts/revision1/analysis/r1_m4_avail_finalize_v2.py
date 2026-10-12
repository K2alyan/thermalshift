#!/usr/bin/env python3
"""
M4 Static Candidate-Pool Sensitivity — Post-processing finalization v2.

ba80d44 (r1_m4_avail_finalize.py) is diagnostic only: it used midpoint
point estimates for 4 inverted crossing brackets, which are not valid
corrections (midpoint is neither an evaluated feasible nor an evaluated
violating point).

This script reconstructs the 4 defective crossings from their already
evaluated lambda_rows, applying the same conservative first-violation
estimand used in the M4 analysis:

  C_upper = capacity at FIRST evaluated violating point (sorted by C)
  C_lower = largest evaluated feasible C strictly below C_upper
  Feasible re-entry after first violation does NOT increase C_lower.

Sources for reconstruction:
  full_fp_spread  → m4_fair_baselines.json   (frozen v5, immune)
  full_loc        → m4_canonical_policies.json (canonical rerun)

Simulation output (m4_avail_transition.json) is not modified.
"""

import json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from pathlib import Path
from collections import Counter

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "revision1" / "results"

TRANS_FILE   = OUT_DIR / "m4_avail_transition.json"
V5_FILE      = OUT_DIR / "m4_fair_baselines.json"
CANPOL_FILE  = OUT_DIR / "m4_canonical_policies.json"
OUT_V2_FILE  = OUT_DIR / "m4_avail_finalize_v2.json"

# ── Load sources ───────────────────────────────────────────────────────
trans   = json.loads(TRANS_FILE.read_text())
v5      = json.loads(V5_FILE.read_text())
canpol  = json.loads(CANPOL_FILE.read_text())

trans_rows = trans["scenario_rows"]

v5_by_sc     = {r["scenario_idx"]: r for r in v5["scenario_results"]}
canpol_by_sc = {r["scenario_idx"]: r for r in canpol["scenario_results"]}

PAIRS = [
    ("fp_vs_rand",    "full_fp",       "full_random"),
    ("loc_vs_rand",   "full_loc",      "full_random"),
    ("spread_vs_rand","full_fp_spread","full_random"),
    ("spread_vs_fp",  "full_fp_spread","full_fp"),
    ("spread_vs_loc", "full_fp_spread","full_loc"),
]

# ══════════════════════════════════════════════════════════════════════
# [1] Reconstruct crossing from evaluated lambda_rows
# ══════════════════════════════════════════════════════════════════════

def reconstruct_crossing(lambda_rows_for_policy: list) -> dict:
    """
    Apply conservative first-violation estimand to evaluated lambda rows.

    Scan ALL evaluated points sorted by capacity_unlock_pct (not lambda).
    C_upper = capacity at first evaluated point where infeasible=True.
    C_lower = largest feasible capacity strictly below C_upper.
    Feasible re-entries after the first violation are ignored for C_lower.
    """
    pts = sorted(lambda_rows_for_policy,
                 key=lambda x: x.get("capacity_unlock_pct", 0.0))

    # Assert no duplicate capacity values with conflicting feasibility
    seen = {}
    for p in pts:
        c = round(p.get("capacity_unlock_pct", 0.0), 10)
        inf = p.get("infeasible", False)
        if c in seen:
            assert seen[c] == inf, (
                f"Duplicate capacity {c}% with conflicting feasibility: "
                f"{seen[c]} vs {inf}"
            )
        seen[c] = inf

    if not pts:
        return {"status": "no_data", "C_lower_pct": None, "C_upper_pct": None,
                "first_binding_constraint": None}

    # First evaluated point violates → left_boundary
    if pts[0].get("infeasible", False):
        return {"status": "left_boundary",
                "C_lower_pct": 0.0, "C_upper_pct": 0.0,
                "first_binding_constraint": pts[0].get("first_binding")}

    # Scan for first violation
    c_lower = None
    c_upper = None
    first_binding = None

    for p in pts:
        cap = p.get("capacity_unlock_pct", 0.0)
        inf = p.get("infeasible", False)
        if not inf:
            # feasible — candidate for C_lower (only before first violation)
            if c_upper is None:
                c_lower = cap
        else:
            # first violation found
            if c_upper is None:
                c_upper = cap
                first_binding = p.get("first_binding")
            # subsequent violations (or feasible re-entries) are ignored

    if c_upper is None:
        # No violation found → right_censored at the highest evaluated point
        c_lower_val = pts[-1].get("capacity_unlock_pct", 0.0)
        return {"status": "right_censored",
                "C_lower_pct": c_lower_val, "C_upper_pct": None,
                "first_binding_constraint": None}

    assert c_lower is not None, "C_lower is None but C_upper is set; first point was feasible?"
    assert c_lower < c_upper + 1e-12, (
        f"STILL INVERTED after reconstruction: C_lower={c_lower} C_upper={c_upper}")

    return {"status": "exact_bracket",
            "C_lower_pct": c_lower,
            "C_upper_pct": c_upper,
            "first_binding_constraint": first_binding}


# The four inverted cases and their authoritative lambda_rows source
RECONSTRUCT_CASES = [
    # (scenario_idx, policy, source_key)  source_key: "v5" or "canpol"
    (4, "full_loc",       "canpol"),
    (7, "full_loc",       "canpol"),
    (8, "full_fp_spread", "v5"),
    (8, "full_loc",       "canpol"),
]

print("=" * 70)
print("CROSSING RECONSTRUCTION — first-violation estimand from lambda_rows")
print("=" * 70)

reconstructed = {}   # (scenario_idx, policy) -> new crossing dict

for s_idx, pol, src_key in RECONSTRUCT_CASES:
    if src_key == "v5":
        ref_row = v5_by_sc[s_idx]
    else:
        ref_row = canpol_by_sc[s_idx]

    lambda_rows_pol = ref_row["lambda_rows"].get(pol, [])
    assert lambda_rows_pol, f"No lambda_rows for sc{s_idx} {pol} in {src_key}"

    old_cx = next(
        r["crossings"][pol]
        for r in trans_rows
        if r["scenario_idx"] == s_idx and abs(r["avail_frac"] - 1.0) < 1e-6
    )
    new_cx = reconstruct_crossing(lambda_rows_pol)

    print(f"\nsc{s_idx} {pol} (source={src_key}):")
    print(f"  evaluated points: {len(lambda_rows_pol)}")
    print(f"  stored   crossing: lo={old_cx['C_lower_pct']:.6f}%  "
          f"hi={old_cx.get('C_upper_pct'):.6f}%  status={old_cx['status']}")
    print(f"  recon    crossing: lo={new_cx['C_lower_pct']:.6f}%  "
          f"hi={new_cx['C_upper_pct']:.6f}%  status={new_cx['status']}")
    if new_cx["status"] == "exact_bracket":
        gap_old = (old_cx.get('C_upper_pct') or 0) - old_cx['C_lower_pct']
        gap_new = new_cx['C_upper_pct'] - new_cx['C_lower_pct']
        print(f"  gap: stored={gap_old:+.4f}pp  recon={gap_new:+.4f}pp")

    reconstructed[(s_idx, pol)] = new_cx

    # Verify assertion
    if new_cx["status"] == "exact_bracket":
        lo = new_cx["C_lower_pct"]; hi = new_cx["C_upper_pct"]
        assert lo <= hi + 1e-12, f"FAILED: sc{s_idx} {pol}: lo={lo} hi={hi}"

print("\n  All reconstructed brackets satisfy C_lower <= C_upper.")

# ══════════════════════════════════════════════════════════════════════
# [2] Build corrected crossing lookup for f=100% rows
# ══════════════════════════════════════════════════════════════════════

def get_crossing(trans_row, pol):
    """Return crossing dict, substituting reconstruction where applicable."""
    key = (trans_row["scenario_idx"], pol)
    if key in reconstructed:
        return reconstructed[key]
    return trans_row["crossings"][pol]

# ══════════════════════════════════════════════════════════════════════
# [3] Recompute pairwise deltas
# ══════════════════════════════════════════════════════════════════════

def _icmp(cx_a, cx_b):
    rc_a = (cx_a.get("status") == "right_censored")
    rc_b = (cx_b.get("status") == "right_censored")
    lo_a = cx_a["C_lower_pct"] if cx_a["C_lower_pct"] is not None else 0.0
    lo_b = cx_b["C_lower_pct"] if cx_b["C_lower_pct"] is not None else 0.0
    hi_a = None if rc_a else cx_a.get("C_upper_pct", lo_a)
    hi_b = None if rc_b else cx_b.get("C_upper_pct", lo_b)
    dlo = None if rc_b else lo_a - hi_b
    dhi = None if rc_a else hi_a - lo_b
    if dlo is not None and dhi is not None:
        assert dlo <= dhi + 1e-12, (
            f"INVERTED after reconstruction: dlo={dlo:.6f} dhi={dhi:.6f}\n"
            f"  cx_a={cx_a}\n  cx_b={cx_b}")
    if dlo is not None and dlo > 0:
        v = "def_a_better"
    elif dhi is not None and dhi < 0:
        v = "def_b_better"
    elif rc_a or rc_b:
        v = "indeterminate_censored"
    else:
        v = "indistinguishable"
    return dlo, dhi, v

rows_f100 = sorted([r for r in trans_rows if r["avail_frac"] > 0.999],
                   key=lambda r: r["scenario_idx"])

print(f"\n{'='*70}")
print("RECONSTRUCTED PAIRWISE INTERVALS — f=100%, held-out sc5-9")
print(f"{'='*70}")

def compute_pair_summary(scenario_list):
    result = {}
    for pair_key, pol_a, pol_b in PAIRS:
        dlos, dhis = [], []
        v_counts = Counter()
        rows_detail = []
        for r in scenario_list:
            cx_a = get_crossing(r, pol_a)
            cx_b = get_crossing(r, pol_b)
            dlo, dhi, v = _icmp(cx_a, cx_b)
            dlos.append(dlo); dhis.append(dhi)
            v_counts[v] += 1
            rows_detail.append({
                "scenario_idx": r["scenario_idx"],
                "cx_a": {
                    "C_lower_pct": cx_a["C_lower_pct"],
                    "C_upper_pct": cx_a.get("C_upper_pct"),
                    "status": cx_a["status"],
                    "reconstructed": (r["scenario_idx"], pol_a) in reconstructed,
                },
                "cx_b": {
                    "C_lower_pct": cx_b["C_lower_pct"],
                    "C_upper_pct": cx_b.get("C_upper_pct"),
                    "status": cx_b["status"],
                    "reconstructed": (r["scenario_idx"], pol_b) in reconstructed,
                },
                "delta_lo": dlo,
                "delta_hi": dhi,
                "verdict": v,
            })
        import statistics
        result[pair_key] = {
            "n": len(dlos),
            "n_def_a_better"      : v_counts["def_a_better"],
            "n_indistinguishable" : v_counts["indistinguishable"],
            "n_def_b_better"      : v_counts["def_b_better"],
            "n_indeterminate_censored": v_counts["indeterminate_censored"],
            "delta_lo_median"     : statistics.median(dlos),
            "delta_hi_median"     : statistics.median(dhis),
            "rows_detail"         : rows_detail,
        }
    return result

held_sc   = [r for r in rows_f100 if r["scenario_idx"] >= 5]
all10_sc  = rows_f100

held5_pairs  = compute_pair_summary(held_sc)
all10_pairs  = compute_pair_summary(all10_sc)

PAIR_LABELS = {
    "fp_vs_rand"    : "FP vs Random",
    "loc_vs_rand"   : "Location vs Random",
    "spread_vs_rand": "FP-spread vs Random",
    "spread_vs_fp"  : "FP-spread vs FP (primary)",
    "spread_vs_loc" : "FP-spread vs Location (primary)",
}

# Print held-out detail
for pair_key, pol_a, pol_b in PAIRS:
    if pair_key not in held5_pairs:
        continue
    d = held5_pairs[pair_key]
    print(f"\n{PAIR_LABELS[pair_key]}:")
    print(f"  {'sc':3s}  {'lo_A':7s}  {'hi_A':7s}  {'lo_B':7s}  {'hi_B':7s}  "
          f"{'dlo':8s}  {'dhi':8s}  {'verdict'}")
    for row in d["rows_detail"]:
        s   = row["scenario_idx"]
        cx_a = row["cx_a"]; cx_b = row["cx_b"]
        la = cx_a["C_lower_pct"]
        ha = cx_a["C_upper_pct"] if cx_a["C_upper_pct"] is not None else float("inf")
        lb = cx_b["C_lower_pct"]
        hb = cx_b["C_upper_pct"] if cx_b["C_upper_pct"] is not None else float("inf")
        ra = " *" if cx_a["reconstructed"] else "  "
        rb = " *" if cx_b["reconstructed"] else "  "
        dlo = row["delta_lo"]; dhi = row["delta_hi"]
        v = row["verdict"]
        print(f"  sc{s}  {la:7.3f}{ra}  {ha:7.3f}{ra}  {lb:7.3f}{rb}  {hb:7.3f}{rb}  "
              f"{dlo:+8.4f}  {dhi:+8.4f}  {v}")
    ml = d["delta_lo_median"]; mh = d["delta_hi_median"]
    a  = d["n_def_a_better"]; ind = d["n_indistinguishable"]; b = d["n_def_b_better"]
    n  = d["n"]
    print(f"  MEDIAN dlo={ml:+.4f}pp  dhi={mh:+.4f}pp  "
          f"| {a}/{n} def_a  {ind}/{n} ind  {b}/{n} def_b")

# ══════════════════════════════════════════════════════════════════════
# [4] Summary table
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("SUMMARY TABLE — f=100%, reconstructed crossings")
print(f"{'='*70}")

print(f"\nHeld-out (sc5-9, n=5):")
print(f"  {'Comparison':36s}  def_A  ind  def_B   dlo_med   dhi_med")
print(f"  {'-'*36}  -----  ---  -----   -------   -------")
for pair_key, *_ in PAIRS:
    if pair_key not in held5_pairs:
        continue
    d = held5_pairs[pair_key]
    a = d["n_def_a_better"]; ind = d["n_indistinguishable"]; b = d["n_def_b_better"]
    n = d["n"]; ml = d["delta_lo_median"]; mh = d["delta_hi_median"]
    print(f"  {PAIR_LABELS[pair_key]:36s}  {a}/{n}    {ind}/{n}   {b}/{n}    "
          f"{ml:+.2f}pp   {mh:+.2f}pp")

print(f"\nAll 10 scenarios (sc0-9):")
print(f"  {'Comparison':36s}  def_A  ind  def_B   dlo_med   dhi_med")
print(f"  {'-'*36}  -----  ---  -----   -------   -------")
for pair_key, *_ in PAIRS:
    if pair_key not in all10_pairs:
        continue
    d = all10_pairs[pair_key]
    a = d["n_def_a_better"]; ind = d["n_indistinguishable"]; b = d["n_def_b_better"]
    n = d["n"]; ml = d["delta_lo_median"]; mh = d["delta_hi_median"]
    print(f"  {PAIR_LABELS[pair_key]:36s}  {a}/{n}    {ind}/{n}   {b}/{n}    "
          f"{ml:+.2f}pp   {mh:+.2f}pp")

print(f"\n  * reconstructed bracket (vs stored).")
print(f"\n  Note on spread_vs_loc: sc8 full_loc is reconstructed as "
      f"[{reconstructed[(8,'full_loc')]['C_lower_pct']:.3f}%, "
      f"{reconstructed[(8,'full_loc')]['C_upper_pct']:.3f}%], a wider interval "
      f"whose upper bound was missing from the stored crossing. The sc8 "
      f"spread bracket [{reconstructed[(8,'full_fp_spread')]['C_lower_pct']:.3f}%, "
      f"{reconstructed[(8,'full_fp_spread')]['C_upper_pct']:.3f}%] overlaps "
      f"the reconstructed loc bracket, yielding indistinguishable for sc8.")

# ══════════════════════════════════════════════════════════════════════
# [5] Cliff-pattern summary (f<100% cells unaffected)
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("CLIFF PATTERN — f<100% (unaffected by crossing defects)")
print(f"{'='*70}")
rows_lt100 = [r for r in trans_rows if r["avail_frac"] < 0.999]
st_counts = Counter()
for r in rows_lt100:
    for pol in trans["policies"]:
        st_counts[r["crossings"][pol]["status"]] += 1
print(f"  f=60-90%: {len(rows_lt100)*len(trans['policies'])} crossing cells")
for st, cnt in st_counts.items():
    print(f"    {st}: {cnt}")
print("  All f<100% crossings are unaffected by the f=100% summarizer defects.")

# ══════════════════════════════════════════════════════════════════════
# [6] Save
# ══════════════════════════════════════════════════════════════════════

# Strip rows_detail for per-pair summaries to keep JSON clean but include
# the reconstruction audit
def strip_detail(pair_summary):
    out = {}
    for pk, v in pair_summary.items():
        out[pk] = {k: val for k, val in v.items() if k != "rows_detail"}
        out[pk]["rows_detail"] = v["rows_detail"]  # keep for audit
    return out

output = {
    "supersedes": "m4_avail_finalize.json (ba80d44) — midpoint correction was diagnostic only",
    "method": "first_violation_reconstruction",
    "note": (
        "Crossings reconstructed from evaluated lambda_rows using conservative "
        "first-violation estimand: C_upper = first evaluated violating point "
        "(sorted by capacity_unlock_pct); C_lower = largest feasible point below "
        "C_upper; feasible re-entry after first violation is excluded from C_lower. "
        "All f<100% crossings are taken as-is from the frozen simulation JSON "
        "(all 160 cells are left_boundary / invariant_violated and unaffected). "
        "Simulation output (m4_avail_transition.json) is not modified."
    ),
    "reconstructed_crossings": {
        f"sc{s_idx}_{pol}": {
            "scenario_idx": s_idx,
            "policy": pol,
            "source": ("m4_fair_baselines.json" if pol == "full_fp_spread"
                       else "m4_canonical_policies.json"),
            "stored": next(
                r["crossings"][pol]
                for r in trans_rows
                if r["scenario_idx"] == s_idx and r["avail_frac"] > 0.999
            ),
            "reconstructed": reconstructed[(s_idx, pol)],
            "n_evaluated_pts": len(
                (v5_by_sc if pol == "full_fp_spread" else canpol_by_sc)
                [s_idx]["lambda_rows"][pol]
            ),
        }
        for s_idx, pol, _ in RECONSTRUCT_CASES
    },
    "f100_held5_pairs": strip_detail(held5_pairs),
    "f100_all10_pairs": strip_detail(all10_pairs),
}

OUT_V2_FILE.write_text(json.dumps(output, indent=2))
print(f"\nSaved: {OUT_V2_FILE}")
