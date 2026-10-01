#!/usr/bin/env python3
"""
M4 Comprehensive Crossing Audit.

Reconstructs EVERY crossing used in the canonical comparisons from its
source lambda_rows using the conservative first-violation estimand, whether
or not the stored bracket appears inverted. Detects both:

  (a) Inverted brackets  — C_upper < C_lower (already found 6)
  (b) Non-inverted-but-wrong brackets — C_lower < C_upper in stored value,
      but the true first-violation scan produces a different C_upper because
      the summarizer followed lambda order instead of capacity-unlock order,
      and a lower-capacity violating point appeared later in lambda order.

Also asserts:
  - No right_censored crossings in any of the 120 source crossings.
  - delta_lo <= delta_hi for every comparison row after full reconstruction.

Sources:
  full_fp        → m4_fair_baselines.json   (v5, all 30 scenarios)
  full_fp_spread → m4_fair_baselines.json   (v5, all 30 scenarios)
  full_loc       → m4_canonical_policies.json (canonical, all 30)
  full_random    → m4_random_canonical.json   (canonical, all 30)

Output: m4_crossing_audit.json  (audit record + fully reconstructed crossings)
If any new discrepancies beyond the 6 known inverted brackets are found,
m4_canonical_comparisons_v3.json is produced; otherwise v2 is confirmed.
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import json, pathlib
import numpy as np

OUT_DIR        = pathlib.Path(__file__).resolve().parents[3] / "artifacts" / "revision1" / "results"
V5_PATH        = OUT_DIR / "m4_fair_baselines.json"
RAND_PATH      = OUT_DIR / "m4_random_canonical.json"
CANON_POL_PATH = OUT_DIR / "m4_canonical_policies.json"
V2_PATH        = OUT_DIR / "m4_canonical_comparisons_v2.json"
AUDIT_FILE     = OUT_DIR / "m4_crossing_audit.json"
V3_FILE        = OUT_DIR / "m4_canonical_comparisons_v3.json"

HELD_OUT_START = 5
N_BOOTSTRAP    = 5000
BOOTSTRAP_SEED = 9999
TOL_PP         = 1e-6    # tolerance for "exact match" (stored == reconstructed)


# ── Reconstruction ─────────────────────────────────────────────────────
def reconstruct_crossing(lambda_rows: list) -> dict:
    pts = sorted(lambda_rows, key=lambda x: x.get("capacity_unlock_pct", 0.0))
    seen = {}
    for p in pts:
        c   = round(p.get("capacity_unlock_pct", 0.0), 12)
        inf = bool(p.get("infeasible", False))
        if c in seen:
            assert seen[c] == inf, f"Dup cap {c} conflicts: {seen[c]} vs {inf}"
        seen[c] = inf

    if not pts:
        return {"status": "no_data", "C_lower_pct": None, "C_upper_pct": None,
                "first_binding_constraint": None}

    if pts[0].get("infeasible", False):
        return {"status": "left_boundary",
                "C_lower_pct": 0.0, "C_upper_pct": 0.0,
                "first_binding_constraint": pts[0].get("first_binding")}

    c_lower = c_upper = first_binding = None
    for p in pts:
        cap = p.get("capacity_unlock_pct", 0.0)
        inf = bool(p.get("infeasible", False))
        if not inf:
            if c_upper is None:
                c_lower = cap
        else:
            if c_upper is None:
                c_upper       = cap
                first_binding = p.get("first_binding")

    if c_upper is None:
        return {"status": "right_censored",
                "C_lower_pct": pts[-1].get("capacity_unlock_pct", 0.0),
                "C_upper_pct": None,
                "first_binding_constraint": None}

    assert c_lower is not None
    assert c_lower <= c_upper + 1e-12, f"INVERTED post-recon: {c_lower} {c_upper}"
    return {"status": "exact_bracket",
            "C_lower_pct": c_lower, "C_upper_pct": c_upper,
            "first_binding_constraint": first_binding}


# ── Load sources ────────────────────────────────────────────────────────
v5        = json.loads(V5_PATH.read_text())
rand      = json.loads(RAND_PATH.read_text())
canon_pol = json.loads(CANON_POL_PATH.read_text())

v5_by_sc        = {r["scenario_idx"]: r for r in v5["scenario_results"]}
rand_by_sc      = {r["scenario_idx"]: r for r in rand["scenario_results"]}
canon_pol_by_sc = {r["scenario_idx"]: r for r in canon_pol["scenario_results"]}

# Policies to reconstruct and their sources
AUDIT_SPEC = [
    # (policy, source_tag, by_sc_dict)
    ("full_fp",        "v5",    v5_by_sc),
    ("full_fp_spread", "v5",    v5_by_sc),
    ("full_loc",       "canon", canon_pol_by_sc),
    ("full_random",    "rand",  rand_by_sc),
]

# ══════════════════════════════════════════════════════════════════════
# [1] Reconstruct all 120 crossings and compare to stored
# ══════════════════════════════════════════════════════════════════════
print("=" * 70)
print("COMPREHENSIVE CROSSING AUDIT (all 120 source crossings)")
print("=" * 70)

all_30  = list(range(30))
audit_rows = []      # one entry per (scenario, policy)
new_cx_tables = {    # fully reconstructed crossing tables
    "full_fp":        {},
    "full_fp_spread": {},
    "full_loc":       {},
    "full_random":    {},
}

n_exact     = 0
n_inverted  = 0
n_wrong     = 0   # stored non-inverted but reconstructed differs
max_d_lower = 0.0
max_d_upper = 0.0

for pol, src_tag, by_sc in AUDIT_SPEC:
    for s in all_30:
        row = by_sc.get(s)
        if row is None:
            continue
        stored = row["crossings"].get(pol)
        if stored is None:
            continue

        # Assert no right_censored in source
        assert stored.get("status") != "right_censored", (
            f"Unexpected right_censored: sc{s} {pol} [{src_tag}]")

        lrows = row["lambda_rows"].get(pol, [])
        recon = reconstruct_crossing(lrows)

        # Store the reconstructed crossing
        new_cx_tables[pol][s] = recon

        s_lo = stored.get("C_lower_pct", 0.0)
        s_hi = stored.get("C_upper_pct", s_lo)
        r_lo = recon.get("C_lower_pct", 0.0)
        r_hi = recon.get("C_upper_pct", r_lo)

        d_lo = abs(r_lo - s_lo) if (r_lo is not None and s_lo is not None) else None
        d_hi = abs(r_hi - s_hi) if (r_hi is not None and s_hi is not None) else None

        stored_inverted = (s_hi is not None and s_lo is not None and s_hi < s_lo - 1e-12)
        exact = ((d_lo is None or d_lo < TOL_PP) and (d_hi is None or d_hi < TOL_PP)
                 and stored.get("status") == recon.get("status"))

        if d_lo is not None: max_d_lower = max(max_d_lower, d_lo)
        if d_hi is not None: max_d_upper = max(max_d_upper, d_hi)

        if exact:
            n_exact += 1
            category = "exact"
        elif stored_inverted:
            n_inverted += 1
            category = "inverted"
        else:
            n_wrong += 1
            category = "wrong"

        audit_rows.append({
            "policy": pol, "source": src_tag, "scenario_idx": s,
            "category": category,
            "stored_status": stored.get("status"),
            "recon_status":  recon.get("status"),
            "stored_C_lower": s_lo, "recon_C_lower": r_lo,
            "stored_C_upper": s_hi, "recon_C_upper": r_hi,
            "delta_C_lower": d_lo, "delta_C_upper": d_hi,
            "stored_first_binding": stored.get("first_binding_constraint"),
            "recon_first_binding":  recon.get("first_binding_constraint"),
        })

n_total = len(audit_rows)
assert n_total == 120, f"Expected 120 audit rows, got {n_total}"
assert n_inverted + n_wrong + n_exact == 120

print(f"\n  Total crossings audited: {n_total}")
print(f"  Exact matches:           {n_exact}")
print(f"  Inverted (C_hi<C_lo):    {n_inverted}")
print(f"  Non-inverted but wrong:  {n_wrong}")
print(f"  Max |ΔC_lower|:          {max_d_lower:.8f} pp")
print(f"  Max |ΔC_upper|:          {max_d_upper:.8f} pp")
print(f"  Right-censored:          0 (asserted)")

if n_wrong > 0:
    print(f"\n  NON-INVERTED DISCREPANCIES:")
    for row in audit_rows:
        if row["category"] == "wrong":
            print(f"    sc{row['scenario_idx']:2d} {row['policy']:16s} [{row['source']}]: "
                  f"stored [{row['stored_C_lower']:.6f}%, {row['stored_C_upper']:.6f}%] "
                  f"-> recon [{row['recon_C_lower']:.6f}%, {row['recon_C_upper']:.6f}%]  "
                  f"Δlo={row['delta_C_lower']:+.8f}pp  Δhi={row['delta_C_upper']:+.8f}pp")

if n_inverted > 0:
    print(f"\n  INVERTED BRACKETS (already addressed in v2):")
    for row in audit_rows:
        if row["category"] == "inverted":
            print(f"    sc{row['scenario_idx']:2d} {row['policy']:16s} [{row['source']}]: "
                  f"gap={row['stored_C_upper']-row['stored_C_lower']:+.6f}pp")

# ══════════════════════════════════════════════════════════════════════
# [2] Right-censored assertion for all five comparison pairs
# ══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print("RIGHT-CENSORED ASSERTION")
print(f"{'='*70}")
n_rc_recon = sum(1 for r in audit_rows if r["recon_status"] == "right_censored")
n_rc_store = sum(1 for r in audit_rows if r["stored_status"] == "right_censored")
print(f"  Stored right_censored:       {n_rc_store}/120")
print(f"  Reconstructed right_censored:{n_rc_recon}/120")
assert n_rc_store == 0, "Stored right_censored found — review interval_compare()"
assert n_rc_recon == 0, "Reconstructed right_censored found — wider interval set needed"
print(f"  ASSERTION PASSED: no right_censored crossings in any of the 120.")
print(f"  The interval_compare() collapse of C_upper=None to C_lower does not")
print(f"  affect any comparison in this analysis.")

# ══════════════════════════════════════════════════════════════════════
# [3] Decide: v2 confirmed or v3 needed?
# ══════════════════════════════════════════════════════════════════════
need_v3 = (n_wrong > 0)

if not need_v3:
    print(f"\n{'='*70}")
    print("VERDICT: m4_canonical_comparisons_v2.json IS AUTHORITATIVE")
    print(f"{'='*70}")
    print(f"  All {n_wrong} non-inverted discrepancies: 0.")
    print(f"  The 6 inverted brackets corrected in v2 are the complete set of")
    print(f"  crossing defects. v2 is confirmed as the authoritative output.")
else:
    print(f"\n{'='*70}")
    print("NEW DISCREPANCIES FOUND — COMPUTING v3")
    print(f"{'='*70}")

# ══════════════════════════════════════════════════════════════════════
# [4] If v3 needed, recompute all comparisons from fully reconstructed table
# ══════════════════════════════════════════════════════════════════════
if need_v3:
    def jf(v):
        if v is None: return None
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else f

    def interval_compare(cx_a, cx_b, label=""):
        lo_a = cx_a["C_lower_pct"]
        hi_a = cx_a["C_upper_pct"] if cx_a.get("C_upper_pct") is not None else lo_a
        lo_b = cx_b["C_lower_pct"]
        hi_b = cx_b["C_upper_pct"] if cx_b.get("C_upper_pct") is not None else lo_b
        d_lo = lo_a - hi_b; d_hi = hi_a - lo_b
        assert d_lo <= d_hi + 1e-12, f"INVERTED {label}: {d_lo:.10f} {d_hi:.10f}"
        if d_lo > 0:   v = "definitely_A_better"
        elif d_hi < 0: v = "definitely_B_better"
        else:          v = "indistinguishable"
        return {"delta_lo": jf(d_lo), "delta_hi": jf(d_hi), "verdict": v,
                "C_lower_A": jf(lo_a), "C_upper_A": jf(hi_a),
                "C_lower_B": jf(lo_b), "C_upper_B": jf(hi_b)}

    def bootstrap_median_ci(vals, n_boot, seed):
        a = np.array(vals, dtype=float)
        rng = np.random.default_rng(seed)
        meds = [float(np.median(rng.choice(a, size=len(a), replace=True)))
                for _ in range(n_boot)]
        return {"median": float(np.median(a)),
                "ci_lo_95": float(np.percentile(meds, 2.5)),
                "ci_hi_95": float(np.percentile(meds, 97.5)),
                "q1": float(np.percentile(a, 25)),
                "q3": float(np.percentile(a, 75)), "n": len(vals)}

    def summarize_pair(name_a, name_b, cx_a_tbl, cx_b_tbl, scenarios):
        rows = []
        for s in scenarios:
            if s not in cx_a_tbl or s not in cx_b_tbl: continue
            cmp = interval_compare(cx_a_tbl[s], cx_b_tbl[s],
                                   label=f"sc{s} {name_a} vs {name_b}")
            cmp["scenario_idx"] = s
            rows.append(cmp)
        n = len(rows)
        n_a = sum(1 for r in rows if r["verdict"] == "definitely_A_better")
        n_i = sum(1 for r in rows if r["verdict"] == "indistinguishable")
        n_b = sum(1 for r in rows if r["verdict"] == "definitely_B_better")
        dlo = [r["delta_lo"] for r in rows if r["delta_lo"] is not None]
        dhi = [r["delta_hi"] for r in rows if r["delta_hi"] is not None]
        cla = [r["C_lower_A"] for r in rows if r["C_lower_A"] is not None]
        clb = [r["C_lower_B"] for r in rows if r["C_lower_B"] is not None]
        dlo_ci = bootstrap_median_ci(dlo, N_BOOTSTRAP, BOOTSTRAP_SEED) if dlo else None
        dhi_ci = bootstrap_median_ci(dhi, N_BOOTSTRAP, BOOTSTRAP_SEED) if dhi else None
        print(f"\n  {name_a} vs {name_b} (n={n}):")
        print(f"    Def_A={n_a}  Ind={n_i}  Def_B={n_b}")
        if dlo_ci:
            print(f"    delta_lo: median={dlo_ci['median']:+.4f}  "
                  f"CI=[{dlo_ci['ci_lo_95']:+.4f},{dlo_ci['ci_hi_95']:+.4f}]  "
                  f"Q1={dlo_ci['q1']:+.4f}  Q3={dlo_ci['q3']:+.4f}")
        return {"name_A": name_a, "name_B": name_b, "scenarios": scenarios,
                "n": n, "n_definitely_A": n_a, "n_indistinguishable": n_i,
                "n_definitely_B": n_b, "pct_definitely_A": round(100*n_a/n,1) if n else None,
                "delta_lo_ci": dlo_ci, "delta_hi_ci": dhi_ci,
                "C_lower_A_median": jf(float(np.median(cla))) if cla else None,
                "C_lower_B_median": jf(float(np.median(clb))) if clb else None,
                "scenario_rows": rows}

    held_out = list(range(HELD_OUT_START, 30))
    cx_fp    = new_cx_tables["full_fp"]
    cx_spread= new_cx_tables["full_fp_spread"]
    cx_loc   = new_cx_tables["full_loc"]
    cx_rand  = new_cx_tables["full_random"]

    comps = {}
    comps["fp_vs_canonical_rand"]     = summarize_pair(
        "full_fp",        "canonical_random", cx_fp,    cx_rand, all_30)
    comps["loc_vs_canonical_rand"]    = summarize_pair(
        "full_loc_canonical","canonical_random",cx_loc, cx_rand, all_30)
    comps["spread_vs_canonical_rand"] = summarize_pair(
        "full_fp_spread", "canonical_random", cx_spread,cx_rand, held_out)
    comps["spread_vs_fp"]             = summarize_pair(
        "full_fp_spread", "full_fp",          cx_spread,cx_fp,   held_out)
    comps["spread_vs_canonical_loc"]  = summarize_pair(
        "full_fp_spread", "full_loc_canonical",cx_spread,cx_loc, held_out)

    v3_out = {
        "supersedes": "m4_canonical_comparisons_v2.json",
        "note": "Fully reconstructed from lambda_rows; all 120 crossings replaced.",
        "n_bootstrap": N_BOOTSTRAP, "bootstrap_seed": BOOTSTRAP_SEED,
        "comparisons": comps,
    }
    V3_FILE.write_text(json.dumps(v3_out, indent=2))
    print(f"\nSaved v3: {V3_FILE}")

# ══════════════════════════════════════════════════════════════════════
# [5] Save audit record
# ══════════════════════════════════════════════════════════════════════
audit_out = {
    "note": ("Comprehensive crossing audit: all 120 source crossings reconstructed "
             "from lambda_rows using first-violation estimand and compared to stored values."),
    "n_total": n_total, "n_exact": n_exact,
    "n_inverted": n_inverted, "n_non_inverted_but_wrong": n_wrong,
    "max_delta_C_lower_pp": max_d_lower, "max_delta_C_upper_pp": max_d_upper,
    "n_right_censored_stored": n_rc_store,
    "n_right_censored_reconstructed": n_rc_recon,
    "v3_needed": need_v3,
    "authoritative_comparisons": "m4_canonical_comparisons_v3.json" if need_v3 else "m4_canonical_comparisons_v2.json",
    "audit_rows": audit_rows,
}
AUDIT_FILE.write_text(json.dumps(audit_out, indent=2))
print(f"\nSaved audit: {AUDIT_FILE}")
print(f"Authoritative comparisons: {audit_out['authoritative_comparisons']}")
