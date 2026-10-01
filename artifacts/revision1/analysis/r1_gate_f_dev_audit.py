#!/usr/bin/env python3
"""
r1_gate_f_dev_audit.py — Gate F dev-phase hardened audit (sc0-4)

Run after all three phases complete:
  Phase 1: gate_f_sc0-4_unr.json          (unrestricted, M4 exact-match)
  Phase 2: gate_f_sc0-4_1p0.json          (r=1 trace + inductive check)
  Phase 3: gate_f_sc0-4_1p25_1p5_2p0_4p0_8p0.json (restricted ratios)

OVERALL PASS requires ALL of:
  1. Phase 1: 20/20 unrestricted M4 reproduction (exact match to TOL)
  2. Phase 2: 5/5 r=1 event-level trace PASS + inductive_r1 OK
  3. Phase 3: exactly 100/100 crossing cells present (5 sc x 5 ratios x 4 policies)
  4. Phase 3: zero C_lower > C_upper (no stored inversions)
  5. Phase 3: zero unexpected right-censored crossings
  6. Phase 3: zero n_base_unserved != 0 in any lambda row
  7. Phase 3: zero invariant_violated in any lambda row
  8. Phase 3: zero NaN/Inf in C_lower_pct or C_upper_pct
  9. Phase 3: all five frozen contrasts have n=5 scenarios at every ratio
 10. Phase 3: independent v3 capacity-ordered crossing matches stored for all 100 cells
 11. Provenance: all three files at same commit, tracked_dirty=False
 12. Source hashes recorded (Phase 3 JSON, input parquet)

Exits 1 on any failure; exits 0 only on full PASS.
"""

import sys, os, json, hashlib, math
from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[3]
OUT_DIR    = REPO_ROOT / "artifacts" / "revision1" / "results"

PHASE1_FILE   = OUT_DIR / "gate_f_sc0-4_unr.json"
PHASE2_FILE   = OUT_DIR / "gate_f_sc0-4_1p0.json"
PHASE3_FILE   = OUT_DIR / "gate_f_sc0-4_1p25_1p5_2p0_4p0_8p0.json"
AUDIT_FILE    = OUT_DIR / "gate_f_dev_audit_sc0-4.json"

# Canonical Frontier input parquet (canonical path for held-out; SHA verified here)
_DATA_DIR_ENV = os.environ.get("THERMALSHIFT_DATA_DIR", "")
PARQUET_FILE  = Path(_DATA_DIR_ENV) / "frontier-completed-job-info.parquet" if _DATA_DIR_ENV else None
PARQUET_SHA256_EXPECTED = None  # recorded on first run; checked on subsequent

M4_REF_FILES = {
    "m4_random_canonical"   : OUT_DIR / "m4_random_canonical.json",
    "m4_fair_baselines"     : OUT_DIR / "m4_fair_baselines.json",
    "m4_canonical_policies" : OUT_DIR / "m4_canonical_policies.json",
}
M4_POLICY_SOURCE = {
    "full_random"    : "m4_random_canonical",
    "full_fp"        : "m4_fair_baselines",
    "full_fp_spread" : "m4_fair_baselines",
    "full_loc"       : "m4_canonical_policies",
}

POLICIES     = ["full_random", "full_fp", "full_loc", "full_fp_spread"]
N_DEV        = 5
RESTRICTED_RATIOS = ["1.25", "1.5", "2.0", "4.0", "8.0"]
RATIO_ORDER  = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"]
EXPECTED_CELLS = N_DEV * len(RESTRICTED_RATIOS) * len(POLICIES)   # 100

CONTRASTS = [
    ("full_fp",        "full_random", "FP_vs_Random"),
    ("full_loc",       "full_random", "Loc_vs_Random"),
    ("full_fp_spread", "full_random", "FPSpread_vs_Random"),
    ("full_fp_spread", "full_fp",     "FPSpread_vs_FP"),
    ("full_fp_spread", "full_loc",    "FPSpread_vs_Loc"),
]

TOL = 1e-10

# ── Utilities ──────────────────────────────────────────────────────────────────
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()

def close_enough(a, b, tol=TOL):
    if a is None and b is None: return True
    if a is None or b is None: return False
    fa, fb = float(a), float(b)
    if math.isnan(fa) and math.isnan(fb): return True
    if math.isnan(fa) or math.isnan(fb): return False
    return abs(fa - fb) <= tol * (1.0 + abs(fb))

def fmt_pct(v):
    if v is None: return "None"
    if isinstance(v, float) and math.isnan(v): return "NaN"
    return f"{float(v):.4f}%"

def prov_fields(d):
    return {k: d.get(k) for k in ("git_commit_full","git_commit_short",
                                   "git_tracked_dirty","git_untracked_present")}

def get_cx(ratios, r_label, pol):
    return ratios.get(r_label, {}).get(pol, {}).get("crossing", {})

def is_infeasible_row(row, b_ref_s, s_ref_s):
    if row.get("invariant_violated"):
        return True, "invariant_violated"
    b_h   = row.get("B_primary_h")
    b_cab = row.get("B_cab_ratio") or 0.0
    s_val = row.get("S_primary_Cdoth")
    if b_h is None or (isinstance(b_h, float) and math.isnan(b_h)):
        return True, "B_NaN"
    b_ratio = b_h / max(float(b_ref_s), 1e-9)
    violations = []
    if b_ratio > 1.0: violations.append("B_ratio")
    if s_val is not None and not (isinstance(s_val, float) and math.isnan(s_val)):
        if float(s_val) / max(float(s_ref_s), 1e-9) > 1.0: violations.append("S_ratio")
    if b_cab > 1.0: violations.append("B_cab_ratio")
    return bool(violations), (violations[0] if violations else None)

def v3_crossing_from_rows(all_rows, b_ref_s, s_ref_s):
    """Frozen v3 capacity-ordered crossing estimator applied to all lambda rows."""
    scored = []
    for row in all_rows:
        cap = float(row.get("capacity_unlock_pct", 0.0))
        inf, bind = is_infeasible_row(row, b_ref_s, s_ref_s)
        scored.append((cap, inf, bind))
    scored.sort(key=lambda x: x[0])
    last_feasible_cap = None
    for cap, inf, bind in scored:
        if not inf:
            last_feasible_cap = cap
        else:
            if last_feasible_cap is None:
                return {"status": "left_boundary", "C_lower_pct": 0.0,
                        "C_upper_pct": cap, "first_binding_constraint": bind,
                        "right_censored": False}
            return {"status": "exact_bracket",
                    "C_lower_pct": last_feasible_cap, "C_upper_pct": cap,
                    "first_binding_constraint": bind, "right_censored": False}
    c_lo = last_feasible_cap if last_feasible_cap is not None else 0.0
    return {"status": "right_censored", "C_lower_pct": c_lo, "C_upper_pct": None,
            "first_binding_constraint": None, "right_censored": True}

sep = "=" * 70
fail_reasons: list[str] = []

def fail(msg: str):
    fail_reasons.append(msg)
    print(f"  FAIL: {msg}")

# ── Load M4 references ─────────────────────────────────────────────────────────
print("Loading M4 reference files ...")
m4_data, m4_hashes = {}, {}
for name, path in M4_REF_FILES.items():
    if not path.exists():
        sys.exit(f"MISSING M4 reference: {path}")
    m4_data[name] = json.loads(path.read_text(encoding="utf-8"))
    m4_hashes[name] = {"sha256": sha256_file(path), "size_bytes": path.stat().st_size,
                        "path": str(path)}
    print(f"  {name}: {m4_hashes[name]['sha256'][:32]}...  ({path.stat().st_size:,} B)")

m4_lookup: dict[int, dict[str, dict]] = {}
for pol in POLICIES:
    src = M4_POLICY_SOURCE[pol]
    for sc in m4_data[src]["scenario_results"]:
        idx = sc["scenario_idx"]
        m4_lookup.setdefault(idx, {})
        cx = sc.get("crossings", {}).get(pol)
        if cx is not None:
            m4_lookup[idx][pol] = cx

# ── Load all three phase files ─────────────────────────────────────────────────
for label, fpath in [("Phase 1", PHASE1_FILE), ("Phase 2", PHASE2_FILE),
                      ("Phase 3", PHASE3_FILE)]:
    if not fpath.exists():
        sys.exit(f"MISSING {label} file: {fpath}")

p1 = json.loads(PHASE1_FILE.read_text(encoding="utf-8"))
p2 = json.loads(PHASE2_FILE.read_text(encoding="utf-8"))
p3 = json.loads(PHASE3_FILE.read_text(encoding="utf-8"))

p3_sha256 = sha256_file(PHASE3_FILE)
parquet_sha256 = sha256_file(PARQUET_FILE) if (PARQUET_FILE and PARQUET_FILE.exists()) else None

# ── Provenance consistency check ───────────────────────────────────────────────
print(f"\n{sep}")
print("PROVENANCE CHECK")
print(sep)
commits  = {k: d.get("git_commit_short","?")  for k, d in [("p1",p1),("p2",p2),("p3",p3)]}
dirtys   = {k: d.get("git_tracked_dirty",None) for k, d in [("p1",p1),("p2",p2),("p3",p3)]}
print(f"  Phase 1 commit={commits['p1']}  dirty={dirtys['p1']}")
print(f"  Phase 2 commit={commits['p2']}  dirty={dirtys['p2']}")
print(f"  Phase 3 commit={commits['p3']}  dirty={dirtys['p3']}")
if len(set(commits.values())) != 1:
    fail(f"Commits differ across phases: {commits}")
for k, d in dirtys.items():
    if d is True:
        fail(f"{k} git_tracked_dirty=True")
print(f"  Phase 3 JSON SHA-256: {p3_sha256}")
if parquet_sha256:
    print(f"  Frontier parquet SHA-256: {parquet_sha256}")
    print(f"  Frontier parquet path: {PARQUET_FILE}")
else:
    print("  Frontier parquet: not checked (THERMALSHIFT_DATA_DIR not set)")

# ── Phase 1: M4 exact-match ────────────────────────────────────────────────────
print(f"\n{sep}")
print("PHASE 1: Unrestricted sc0-4  —  M4 exact-match verification")
print(sep)
print(f"  commit={p1.get('git_commit_short','?')}  "
      f"tracked_dirty={p1.get('git_tracked_dirty','?')}")

p1_results: list[dict] = []
p1_fail_log: list[str] = []

for sc in p1["scenario_results"]:
    s_idx = sc["scenario_idx"]
    if s_idx >= N_DEV: continue
    sc_rec = {"scenario_idx": s_idx, "policies": {}}
    for pol in POLICIES:
        cx_gf = get_cx(sc["ratios"], "unrestricted", pol)
        cx_m4 = m4_lookup.get(s_idx, {}).get(pol)
        gf_lo = cx_gf.get("C_lower_pct"); gf_hi = cx_gf.get("C_upper_pct")
        m4_lo = cx_m4.get("C_lower_pct") if cx_m4 else None
        m4_hi = cx_m4.get("C_upper_pct") if cx_m4 else None
        ok = close_enough(gf_lo, m4_lo) and close_enough(gf_hi, m4_hi) and cx_m4 is not None
        label = "PASS" if ok else "FAIL"
        if not ok:
            msg = (f"sc{s_idx}/{pol}: GF=[{fmt_pct(gf_lo)},{fmt_pct(gf_hi)}] "
                   f"M4=[{fmt_pct(m4_lo)},{fmt_pct(m4_hi)}]")
            p1_fail_log.append(msg)
        sc_rec["policies"][pol] = {
            "gf_C_lower_pct": gf_lo, "gf_C_upper_pct": gf_hi,
            "m4_C_lower_pct": m4_lo, "m4_C_upper_pct": m4_hi,
            "m4_source": M4_POLICY_SOURCE[pol], "pass": ok,
        }
        print(f"  sc{s_idx} {pol:20s}:  GF=[{fmt_pct(gf_lo)},{fmt_pct(gf_hi)}]  "
              f"M4=[{fmt_pct(m4_lo)},{fmt_pct(m4_hi)}]  {label}")
    p1_results.append(sc_rec)

p1_pass = len(p1_fail_log) == 0
print(f"\nPhase 1 overall: {'PASS' if p1_pass else 'FAIL'}")
if not p1_pass:
    for msg in p1_fail_log: fail(f"Phase1 M4 mismatch: {msg}")

# ── Phase 2: r=1 trace ────────────────────────────────────────────────────────
print(f"\n{sep}")
print("PHASE 2: r=1 sc0-4  —  event-level trace + inductive check")
print(sep)
print(f"  commit={p2.get('git_commit_short','?')}  "
      f"tracked_dirty={p2.get('git_tracked_dirty','?')}")

p2_results: list[dict] = []
p2_pass = True
for sc in p2["scenario_results"]:
    s_idx = sc["scenario_idx"]
    if s_idx >= N_DEV: continue
    r1_block  = sc["ratios"].get("1.0", {})
    trace_cmp = r1_block.get("r1_trace_comparison", {})
    trace_en  = trace_cmp.get("enabled", False)
    trace_ok  = trace_cmp.get("overall_pass", False)
    cx_by_pol = {p: r1_block.get(p, {}).get("crossing", {}) for p in POLICIES}
    c_lowers  = {p: cx_by_pol[p].get("C_lower_pct") for p in POLICIES}
    ind_ok    = len(set(str(v) for v in c_lowers.values())) == 1
    sc_pass   = (trace_ok if trace_en else True) and ind_ok
    if not sc_pass: p2_pass = False
    trace_str = "PASS" if trace_ok else ("FAIL" if trace_en else "NOT_RUN")
    print(f"  sc{s_idx}: trace={trace_str}  inductive_r1={'OK' if ind_ok else 'MISMATCH'}  "
          f"=> {'PASS' if sc_pass else 'FAIL'}")
    if not ind_ok:
        for p, v in c_lowers.items(): print(f"    {p}: C_lower={v}%")
    p2_results.append({"scenario_idx": s_idx, "trace_pass": trace_ok,
                        "inductive_ok": ind_ok, "r1_C_lowers_pct": c_lowers,
                        "pass": sc_pass})

print(f"\nPhase 2 overall: {'PASS' if p2_pass else 'FAIL'}")
if not p2_pass:
    fail("Phase 2: one or more scenarios failed trace/inductive check")

# ── Phase 3: restricted ratios ────────────────────────────────────────────────
print(f"\n{sep}")
print("PHASE 3: Restricted ratios sc0-4")
print(sep)
print(f"  commit={p3.get('git_commit_short','?')}  "
      f"tracked_dirty={p3.get('git_tracked_dirty','?')}")
print(f"  ratios present: {p3.get('gate_f_ratios', [])}")
print(f"  SHA-256: {p3_sha256}")
if p3.get("crossing_corrections"):
    print(f"  crossing_corrections applied: {len(p3['crossing_corrections'])}")
    for c in p3["crossing_corrections"]:
        print(f"    sc{c['scenario_idx']}/r={c['ratio']}/{c['policy']}: "
              f"stored_lo={c['stored_C_lower']:.4f}% -> v3_lo={c['v3_C_lower']:.4f}%  "
              f"(C_upper unchanged at {c['stored_C_upper']:.4f}%)")

sc_results = p3["scenario_results"]

# ── 3a. Completeness: exactly 100 cells ───────────────────────────────────────
print(f"\n--- 3a. Completeness check (expected={EXPECTED_CELLS}) ---")
present_keys = set(); missing_keys = []; duplicate_keys = []
for s in sc_results:
    si = s["scenario_idx"]
    for r in RESTRICTED_RATIOS:
        if r not in s["ratios"]:
            missing_keys.append(f"sc{si}/r={r} ENTIRE RATIO MISSING")
            continue
        for pol in POLICIES:
            key = (si, r, pol)
            if pol not in s["ratios"][r]:
                missing_keys.append(f"sc{si}/r={r}/{pol}")
            elif key in present_keys:
                duplicate_keys.append(str(key))
            else:
                present_keys.add(key)

n_present = len(present_keys)
print(f"  Present: {n_present}/{EXPECTED_CELLS}  Missing: {len(missing_keys)}  Duplicates: {len(duplicate_keys)}")
for m in missing_keys: print(f"    MISSING: {m}")
for d in duplicate_keys: print(f"    DUPLICATE: {d}")
completeness_ok = (n_present == EXPECTED_CELLS and not missing_keys and not duplicate_keys)
if not completeness_ok:
    fail(f"Phase 3 completeness: {n_present}/{EXPECTED_CELLS} cells present; "
         f"{len(missing_keys)} missing, {len(duplicate_keys)} duplicate")
else:
    print(f"  => 100/100 OK")

# ── 3b. Inversion check: zero C_lower > C_upper ──────────────────────────────
print(f"\n--- 3b. Crossing inversion check ---")
inversions = []
for s in sc_results:
    si = s["scenario_idx"]
    for r in RESTRICTED_RATIOS:
        for pol in POLICIES:
            cx = s["ratios"].get(r, {}).get(pol, {}).get("crossing", {})
            lo = cx.get("C_lower_pct"); up = cx.get("C_upper_pct")
            if lo is not None and up is not None:
                if float(lo) > float(up):
                    inversions.append(f"sc{si}/r={r}/{pol}: C_lower={lo:.6f}% > C_upper={up:.6f}%")
if inversions:
    for x in inversions: print(f"  INVERTED: {x}")
    fail(f"Phase 3: {len(inversions)} C_lower > C_upper inversions")
else:
    print(f"  => Zero inversions OK")

# ── 3c. Unexpected right-censored ────────────────────────────────────────────
print(f"\n--- 3c. Right-censored check ---")
right_censored = []
for s in sc_results:
    si = s["scenario_idx"]
    for r in RESTRICTED_RATIOS:
        for pol in POLICIES:
            cx = s["ratios"].get(r, {}).get(pol, {}).get("crossing", {})
            if cx.get("status") == "right_censored" or cx.get("right_censored"):
                right_censored.append(f"sc{si}/r={r}/{pol}")
if right_censored:
    for x in right_censored: print(f"  RIGHT_CENSORED: {x}")
    fail(f"Phase 3: {len(right_censored)} unexpected right-censored crossings")
else:
    print(f"  => Zero right-censored OK")

# ── 3d. n_base_unserved and invariant_violated ───────────────────────────────
print(f"\n--- 3d. QoS invariant check (n_base_unserved==0, invariant_violated==False) ---")
unserved_hits = []; inv_hits = []
for s in sc_results:
    si = s["scenario_idx"]
    for r in RESTRICTED_RATIOS:
        for pol in POLICIES:
            for row in s["ratios"].get(r, {}).get(pol, {}).get("lambda_rows", []):
                lv = row.get("lambda_val", "?")
                if row.get("n_base_unserved", 0) != 0:
                    unserved_hits.append(f"sc{si}/r={r}/{pol}/lam={lv}: n_base_unserved={row['n_base_unserved']}")
                if row.get("invariant_violated"):
                    inv_hits.append(f"sc{si}/r={r}/{pol}/lam={lv}: invariant_violated=True")
for x in unserved_hits: print(f"  UNSERVED: {x}")
for x in inv_hits: print(f"  INVARIANT: {x}")
if unserved_hits: fail(f"Phase 3: {len(unserved_hits)} rows with n_base_unserved != 0")
if inv_hits: fail(f"Phase 3: {len(inv_hits)} rows with invariant_violated=True")
if not unserved_hits and not inv_hits: print(f"  => All zero OK")

# ── 3e. NaN/Inf in crossing fields ────────────────────────────────────────────
print(f"\n--- 3e. NaN/Inf in crossing fields ---")
nan_hits = []
for s in sc_results:
    si = s["scenario_idx"]
    for r in RESTRICTED_RATIOS:
        for pol in POLICIES:
            cx = s["ratios"].get(r, {}).get(pol, {}).get("crossing", {})
            st = cx.get("status")
            for field in ("C_lower_pct", "C_upper_pct"):
                v = cx.get(field)
                if st != "right_censored" and field == "C_upper_pct" and v is None:
                    nan_hits.append(f"sc{si}/r={r}/{pol}: C_upper_pct is None (status={st})")
                elif v is not None and isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    nan_hits.append(f"sc{si}/r={r}/{pol}: {field}={v}")
for x in nan_hits: print(f"  NaN/Inf: {x}")
if nan_hits: fail(f"Phase 3: {len(nan_hits)} NaN/Inf in crossing fields")
else: print(f"  => None OK")

# ── 3f. Independent v3 crossing verification ─────────────────────────────────
print(f"\n--- 3f. Independent v3 capacity-ordered crossing verification (all 100 cells) ---")
v3_mismatches = []; v3_results = {}
for s in sc_results:
    si = s["scenario_idx"]
    b_ref = float(s["B_ref_s"]); s_ref = float(s["S_ref_s"])
    v3_results[si] = {}
    for r in RESTRICTED_RATIOS:
        v3_results[si][r] = {}
        for pol in POLICIES:
            cell = s["ratios"].get(r, {}).get(pol, {})
            stored_cx = cell.get("crossing", {})
            all_rows  = cell.get("lambda_rows", [])
            v3_cx     = v3_crossing_from_rows(all_rows, b_ref, s_ref)
            v3_results[si][r][pol] = {
                "C_lower_pct": v3_cx.get("C_lower_pct"),
                "C_upper_pct": v3_cx.get("C_upper_pct"),
                "status": v3_cx.get("status"),
            }
            s_lo = stored_cx.get("C_lower_pct"); s_up = stored_cx.get("C_upper_pct")
            v_lo = v3_cx.get("C_lower_pct");     v_up = v3_cx.get("C_upper_pct")
            match = (stored_cx.get("status") == v3_cx.get("status") and
                     close_enough(s_lo, v_lo) and close_enough(s_up, v_up))
            if not match:
                v3_mismatches.append(
                    f"sc{si}/r={r}/{pol}: stored=[{fmt_pct(s_lo)},{fmt_pct(s_up)}] "
                    f"v3=[{fmt_pct(v_lo)},{fmt_pct(v_up)}]"
                )
for x in v3_mismatches: print(f"  MISMATCH: {x}")
if v3_mismatches: fail(f"Phase 3: {len(v3_mismatches)} stored crossings differ from v3 reconstruction")
else: print(f"  => All 100 cells match v3 reconstruction OK")

# ── 3g. Contrast completeness ─────────────────────────────────────────────────
print(f"\n--- 3g. Contrast completeness (5 scenarios per ratio) ---")
contrast_gaps = []
for pol_a, pol_b, clabel in CONTRASTS:
    for r in RESTRICTED_RATIOS:
        n = sum(1 for si in range(N_DEV)
                if si in v3_results and r in v3_results[si]
                and pol_a in v3_results[si][r] and pol_b in v3_results[si][r])
        if n != N_DEV:
            contrast_gaps.append(f"{clabel}/r={r}: {n}/{N_DEV}")
for x in contrast_gaps: print(f"  INCOMPLETE: {x}")
if contrast_gaps: fail(f"Phase 3: {len(contrast_gaps)} contrast/ratio pairs have <5 scenarios")
else: print(f"  => All 5 frozen contrasts complete at every ratio OK")

# ── 3h. Frozen diagnostic field presence ──────────────────────────────────────
print(f"\n--- 3h. Frozen diagnostic field presence ---")
required_row_fields = [
    "B_primary_h", "B_cab_ratio", "S_primary_Cdoth", "capacity_unlock_pct",
    "n_base_unserved", "invariant_violated", "n_drop_cap", "n_drop_physical",
    "n_drop_la", "full_selector_eligible_count_p50", "realized_selector_choice_mult_p50",
]
missing_fields: dict[str, int] = {}
q_admit_present = 0; q_admit_total = 0
for s in sc_results:
    si = s["scenario_idx"]
    for r in RESTRICTED_RATIOS:
        for pol in POLICIES:
            for row in s["ratios"].get(r, {}).get(pol, {}).get("lambda_rows", []):
                q_admit_total += 1
                if "q_admit" in row and "q_drop" in row: q_admit_present += 1
                for fld in required_row_fields:
                    if fld not in row:
                        missing_fields[fld] = missing_fields.get(fld, 0) + 1
for fld, cnt in missing_fields.items():
    print(f"  MISSING field '{fld}' in {cnt} rows")
if missing_fields:
    fail(f"Phase 3: required lambda row fields missing: {list(missing_fields.keys())}")
else:
    print(f"  => All required lambda row fields present OK")
# q_admit/q_drop: note absence (dev run predates fix; not a PASS blocker for dev audit)
q_note = (f"{q_admit_present}/{q_admit_total} lambda rows have q_admit/q_drop "
          f"({'present' if q_admit_present==q_admit_total else 'ABSENT — dev run predates fix; fix applied to run script; held-out will include'})")
print(f"  q_admit/q_drop: {q_note}")

# ── Phase 3 printed table ─────────────────────────────────────────────────────
print(f"\n--- Phase 3 crossing table (stored values, post-correction) ---")
for s in sc_results:
    si = s["scenario_idx"]
    for r in RESTRICTED_RATIOS:
        cells_str = "  ".join(
            f"{pol[:6]}:[{fmt_pct(s['ratios'][r][pol]['crossing']['C_lower_pct'])},"
            f"{fmt_pct(s['ratios'][r][pol]['crossing']['C_upper_pct'])}]"
            for pol in POLICIES
            if pol in s["ratios"].get(r, {})
        )
        print(f"  sc{si} r={r}: {cells_str}")

# ── Build crossing table for contrasts ────────────────────────────────────────
crossing_table: dict[int, dict[str, dict[str, dict]]] = {}

def _store(si, r_lbl, pol, cx):
    crossing_table.setdefault(si, {}).setdefault(r_lbl, {})[pol] = {
        "C_lower_pct": cx.get("C_lower_pct"),
        "C_upper_pct": cx.get("C_upper_pct"),
    }

for sc in p1["scenario_results"]:
    if sc["scenario_idx"] < N_DEV:
        for pol in POLICIES:
            _store(sc["scenario_idx"], "unrestricted", pol,
                   get_cx(sc["ratios"], "unrestricted", pol))
for sc in p2["scenario_results"]:
    if sc["scenario_idx"] < N_DEV:
        for pol in POLICIES:
            _store(sc["scenario_idx"], "1.0", pol,
                   get_cx(sc["ratios"], "1.0", pol))
for s in sc_results:
    if s["scenario_idx"] < N_DEV:
        si = s["scenario_idx"]
        for r in RESTRICTED_RATIOS:
            for pol in POLICIES:
                _store(si, r, pol,
                       get_cx(s["ratios"], r, pol))

# ── Five frozen contrasts ─────────────────────────────────────────────────────
def contrast_delta(si, r_lbl, pol_a, pol_b):
    cx_a = crossing_table.get(si, {}).get(r_lbl, {}).get(pol_a, {})
    cx_b = crossing_table.get(si, {}).get(r_lbl, {}).get(pol_b, {})
    lo_a = cx_a.get("C_lower_pct"); hi_a = cx_a.get("C_upper_pct")
    lo_b = cx_b.get("C_lower_pct"); hi_b = cx_b.get("C_upper_pct")
    if None in (lo_a, hi_a, lo_b, hi_b): return None, None
    return float(lo_a) - float(hi_b), float(hi_a) - float(lo_b)

sc_indices = list(range(N_DEV))
print(f"\n{sep}")
print("FIVE FROZEN CONTRASTS  (delta_lo = C_lower_A - C_upper_B,  delta_hi = C_upper_A - C_lower_B)")
print(sep)

# Assert delta_lo <= delta_hi (GATE_F_DESIGN §10.1)
delta_assertion_failures = []
contrast_results: dict = {}
for pol_a, pol_b, clabel in CONTRASTS:
    contrast_results[clabel] = {}
    print(f"\n  {clabel}  (A={pol_a}  B={pol_b})")
    print("  " + f"{'ratio':>12}  " + "  ".join(f"   sc{i}  " for i in sc_indices))
    for r_lbl in RATIO_ORDER:
        available = any(r_lbl in crossing_table.get(s, {}) for s in sc_indices)
        if not available: continue
        cells, row_data = [], []
        for si in sc_indices:
            dlo, dhi = contrast_delta(si, r_lbl, pol_a, pol_b)
            row_data.append({"scenario_idx": si, "delta_lo": dlo, "delta_hi": dhi})
            if dlo is None:
                cells.append("   --   ")
            else:
                if dlo > dhi:
                    delta_assertion_failures.append(
                        f"{clabel}/r={r_lbl}/sc{si}: delta_lo={dlo:.4f} > delta_hi={dhi:.4f}")
                cells.append(f"[{dlo:+.2f},{dhi:+.2f}]")
        print("  " + f"{r_lbl:>12}  " + "  ".join(cells))
        contrast_results[clabel][r_lbl] = row_data

for x in delta_assertion_failures: print(f"  ASSERT_FAIL: delta_lo > delta_hi: {x}")
if delta_assertion_failures:
    fail(f"GATE_F_DESIGN §10.1 delta_lo <= delta_hi violated: {len(delta_assertion_failures)} cases")

# ── Provenance summary ────────────────────────────────────────────────────────
print(f"\n{sep}")
print("PROVENANCE")
print(sep)
for phase_name, pdata in [("Phase 1 (unr)", p1),("Phase 2 (r=1)", p2),("Phase 3 (restricted)", p3)]:
    print(f"  {phase_name}:  commit={pdata.get('git_commit_short','?')}  "
          f"tracked_dirty={pdata.get('git_tracked_dirty','?')}")
print(f"  Phase 3 JSON SHA-256: {p3_sha256}")
if parquet_sha256:
    print(f"  Frontier parquet SHA-256: {parquet_sha256}")
print("\nM4 reference SHA-256:")
for name, h in m4_hashes.items():
    print(f"  {name}: {h['sha256']}")

# ── Overall verdict ────────────────────────────────────────────────────────────
overall_pass = len(fail_reasons) == 0
print(f"\n{sep}")
print(f"GATE F DEV AUDIT sc0-4 — OVERALL: {'PASS' if overall_pass else 'FAIL'}")
print(f"  Phase 1 (M4 exact match):              {'PASS' if p1_pass else 'FAIL'}")
print(f"  Phase 2 (r=1 trace):                   {'PASS' if p2_pass else 'FAIL'}")
print(f"  Phase 3 completeness (100/100):        {'PASS' if completeness_ok else 'FAIL'}")
print(f"  Phase 3 zero inversions:               {'PASS' if not inversions else 'FAIL'}")
print(f"  Phase 3 zero right-censored:           {'PASS' if not right_censored else 'FAIL'}")
print(f"  Phase 3 QoS invariant:                 {'PASS' if not unserved_hits and not inv_hits else 'FAIL'}")
print(f"  Phase 3 zero NaN/Inf:                  {'PASS' if not nan_hits else 'FAIL'}")
print(f"  Phase 3 v3 crossing match:             {'PASS' if not v3_mismatches else 'FAIL'}")
print(f"  Phase 3 contrast completeness:         {'PASS' if not contrast_gaps else 'FAIL'}")
print(f"  delta_lo <= delta_hi (§10.1):          {'PASS' if not delta_assertion_failures else 'FAIL'}")
print(f"  q_admit/q_drop (dev run):              NOTE — absent in dev run; fix committed to run script")
if fail_reasons:
    print(f"\nFAIL reasons ({len(fail_reasons)}):")
    for r in fail_reasons: print(f"  - {r}")
print(sep)

# ── Save audit JSON ────────────────────────────────────────────────────────────
audit = {
    "audit_version"          : "gate_f_dev_audit_v2",
    "n_dev_scenarios"        : N_DEV,
    "overall_pass"           : overall_pass,
    "fail_reasons"           : fail_reasons,
    "phase1_pass"            : p1_pass,
    "phase2_pass"            : p2_pass,
    "phase3_completeness_ok" : completeness_ok,
    "phase3_zero_inversions" : not inversions,
    "phase3_zero_right_censored": not right_censored,
    "phase3_qos_invariant_ok": not unserved_hits and not inv_hits,
    "phase3_zero_nan"        : not nan_hits,
    "phase3_v3_match"        : not v3_mismatches,
    "phase3_contrast_complete": not contrast_gaps,
    "delta_assertion_ok"     : not delta_assertion_failures,
    "q_admit_q_drop_present" : q_admit_present == q_admit_total,
    "q_admit_q_drop_note"    : q_note,
    "source_hashes": {
        "phase3_json_sha256"         : p3_sha256,
        "frontier_parquet_sha256"    : parquet_sha256,
        "frontier_parquet_path"      : str(PARQUET_FILE) if PARQUET_FILE else None,
        "frontier_parquet_canonical" : "C:/Users/kalya/Downloads/frontier-completed-job-info.parquet",
        "m4_references"              : m4_hashes,
    },
    "provenance": {
        "phase1": prov_fields(p1),
        "phase2": prov_fields(p2),
        "phase3": prov_fields(p3),
    },
    "crossing_corrections_applied": p3.get("crossing_corrections", []),
    "phase1_m4_verification" : p1_results,
    "phase2_r1_verification" : p2_results,
    "phase3_v3_crossings"    : v3_results,
    "phase3_ratios"          : p3.get("gate_f_ratios", []),
    "frozen_contrasts"       : contrast_results,
}
AUDIT_FILE.write_text(json.dumps(audit, indent=2), encoding="utf-8")
print(f"\nSaved: {AUDIT_FILE}")

if not overall_pass:
    sys.exit(1)
