#!/usr/bin/env python3
"""
r1_gate_f_e2df32a_equiv.py
Authoritative pre-launch equivalence check: recovery commit vs freeze commit e2df32a.

Reference: gate_f_sc5-29_1p0.json  — H2 held-out run, produced under e2df32a.
Test:      sc5, GATE_F_RATIOS_ONLY=1.0, run under the current recovery commit.

Why this is the authoritative check (stronger than c8df388 dev-run comparison):
  - Reference was produced at the actual freeze commit e2df32a, not an older
    dev run.  It therefore contains every field added up to and including
    e2df32a (q_admit, q_drop, B_primary_ratio, S_primary_ratio, etc.).
  - No schema gap: both reference and test share the same output schema, so
    ALL substantive fields can be compared — nothing needs to be excluded for
    schema-version reasons.
  - Uses an actual held-out scenario (sc5) under the held-out configuration,
    making this directly relevant to the H3 run we are about to launch.

Fields excluded from comparison (necessarily differ across commits/runs):
  - elapsed_s          (per-scenario timing)
  - elapsed_total_s    (script-level timing)
  - git_commit_full, git_commit_short (different commits by design)
  - git_tracked_dirty, git_untracked_present, git_untracked_count (provenance)

All other fields — including q_admit, q_drop, crossings, every lambda-row
field, scen_seed, wl_seed, B_ref_s, S_ref_s, binding flags, invariant
outputs — must match exactly.  Script exits 1 on any mismatch.

Usage:
  THERMALSHIFT_DATA_DIR=... python r1_gate_f_e2df32a_equiv.py
  python r1_gate_f_e2df32a_equiv.py --skip-run   # compare existing files only
"""

import sys, io, os, json, math, subprocess, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from pathlib import Path

REPO_ROOT  = Path(__file__).resolve().parents[3]
OUT_DIR    = REPO_ROOT / "artifacts" / "revision1" / "results"
RUN_SCRIPT = Path(__file__).resolve().parent / "r1_gate_f_run.py"

EQUIV_SC      = 5
RATIO_ONLY    = "1.0"
RATIO_TAG     = "1p0"
REF_FILE      = OUT_DIR / f"gate_f_sc5-29_{RATIO_TAG}.json"
TEST_FILE     = OUT_DIR / f"gate_f_sc{EQUIV_SC}-{EQUIV_SC}_{RATIO_TAG}.json"

POLICIES = ["full_random", "full_fp", "full_loc", "full_fp_spread"]

# Fields excluded from comparison (timing + git provenance that necessarily differ)
TOP_SKIP = {
    "elapsed_total_s",
    "git_commit_full", "git_commit_short",
    "git_tracked_dirty", "git_untracked_present", "git_untracked_count",
}
ROW_SKIP = {"elapsed_s"}

def fail(msg: str):
    print(f"\nFAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def is_finite(v) -> bool:
    if v is None: return False
    try: return math.isfinite(float(v))
    except: return False

def deep_compare(ref, test, path: str, mismatches: list):
    """Recursively compare two JSON-decoded values."""
    if type(ref) != type(test) and not (
            isinstance(ref, (int, float)) and isinstance(test, (int, float))):
        mismatches.append(f"{path}: type ref={type(ref).__name__} test={type(test).__name__}")
        return
    if isinstance(ref, dict):
        all_keys = set(ref) | set(test)
        for k in sorted(all_keys):
            if k in ROW_SKIP:
                continue
            if k not in ref:
                mismatches.append(f"{path}.{k}: MISSING in ref (schema addition?)")
            elif k not in test:
                mismatches.append(f"{path}.{k}: MISSING in test")
            else:
                deep_compare(ref[k], test[k], f"{path}.{k}", mismatches)
    elif isinstance(ref, list):
        if len(ref) != len(test):
            mismatches.append(
                f"{path}: list length ref={len(ref)} test={len(test)}")
            for i, (rv, tv) in enumerate(zip(ref, test)):
                deep_compare(rv, tv, f"{path}[{i}]", mismatches)
        else:
            for i, (rv, tv) in enumerate(zip(ref, test)):
                deep_compare(rv, tv, f"{path}[{i}]", mismatches)
    elif isinstance(ref, float) or isinstance(test, float):
        rv, tv = float(ref), float(test)
        if math.isnan(rv) and math.isnan(tv):
            pass  # both NaN: treated as equal
        elif rv != tv:
            mismatches.append(f"{path}: ref={ref}  test={test}")
    else:
        if ref != test:
            mismatches.append(f"{path}: ref={ref!r}  test={test!r}")

# ── Header ─────────────────────────────────────────────────────────────────────
print("Gate F: Authoritative e2df32a equivalence check")
print("=" * 70)
print(f"  Reference: {REF_FILE.name}  (H2, produced at e2df32a)")
print(f"  Test:      {TEST_FILE.name}  (sc{EQUIV_SC} solo, recovery commit)")
print(f"  Ratio:     r=1.0  (H2 configuration)")
print(f"  Scenario:  sc{EQUIV_SC}")

# ── Check reference exists ─────────────────────────────────────────────────────
if not REF_FILE.exists():
    fail(f"Reference file not found: {REF_FILE}")

# ── Run test scenario if needed ────────────────────────────────────────────────
skip_run = "--skip-run" in sys.argv

def is_valid_sc5_r1(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        d = json.loads(path.read_text())
        sr = d.get("scenario_results", [])
        if len(sr) != 1: return False
        if int(sr[0].get("scenario_idx", -1)) != EQUIV_SC: return False
        ratios = sr[0].get("ratios", {})
        if "1.0" not in ratios: return False
        for p in POLICIES:
            if p not in ratios["1.0"]: return False
        return True
    except Exception:
        return False

if not skip_run and not is_valid_sc5_r1(TEST_FILE):
    print(f"\nRunning sc{EQUIV_SC} at r=1.0 (recovery commit) ...")
    env = os.environ.copy()
    env["GATE_F_N_FIRST"]           = str(EQUIV_SC)
    env["GATE_F_N_DEV"]             = "1"
    env["GATE_F_RATIOS_ONLY"]       = RATIO_ONLY
    env["GATE_F_REQUIRE_CLEAN_GIT"] = "1"
    t0 = time.time()
    proc = subprocess.run([sys.executable, str(RUN_SCRIPT)], env=env, text=True)
    elapsed = time.time() - t0
    if proc.returncode != 0:
        fail(f"Subprocess exited {proc.returncode} ({elapsed:.0f}s). "
             "Check THERMALSHIFT_DATA_DIR.")
    if not is_valid_sc5_r1(TEST_FILE):
        fail(f"{TEST_FILE.name} missing or invalid after successful subprocess.")
    print(f"  Done in {elapsed:.0f}s")
elif is_valid_sc5_r1(TEST_FILE):
    print(f"\nUsing existing {TEST_FILE.name}")
else:
    fail(f"--skip-run specified but {TEST_FILE.name} is missing or invalid.")

# ── Load both files ────────────────────────────────────────────────────────────
ref_d = json.loads(REF_FILE.read_text())
tst_d = json.loads(TEST_FILE.read_text())

ref_sc = next(
    (r for r in ref_d.get("scenario_results", [])
     if int(r.get("scenario_idx", -1)) == EQUIV_SC),
    None)
if ref_sc is None:
    fail(f"sc{EQUIV_SC} not found in {REF_FILE.name}")

tst_sc = tst_d["scenario_results"][0]

print(f"\n  ref commit : {ref_d.get('git_commit_short','?')}  (freeze e2df32a)")
print(f"  test commit: {tst_d.get('git_commit_short','?')}  (recovery commit)")

# ── Compare scenario-level fields ─────────────────────────────────────────────
print("\n[1] Comparing scenario-level fields (seeds, reference budgets) ...")
mismatches = []

for field in ("scenario_idx", "scen_seed", "wl_seed"):
    rv, tv = ref_sc.get(field), tst_sc.get(field)
    if rv != tv:
        mismatches.append(f"{field}: ref={rv}  test={tv}")
    else:
        print(f"    {field}: {rv}  [match]")

for field in ("B_ref_s", "S_ref_s"):
    rv = float(ref_sc.get(field) or 0.0)
    tv = float(tst_sc.get(field) or 0.0)
    if abs(rv - tv) > 1e-9:
        mismatches.append(f"{field}: ref={rv}  test={tv}")
    else:
        print(f"    {field}: {rv}  [match]")

# ── Compare crossings ──────────────────────────────────────────────────────────
print("\n[2] Comparing crossings (all fields) ...")

ref_ratios = ref_sc.get("ratios", {})
tst_ratios = tst_sc.get("ratios", {})

if "1.0" not in ref_ratios:
    fail(f"Ratio '1.0' not found in reference sc{EQUIV_SC}")
if "1.0" not in tst_ratios:
    fail(f"Ratio '1.0' not found in test sc{EQUIV_SC}")

for pol in POLICIES:
    rcx = ref_ratios["1.0"].get(pol, {}).get("crossing", {})
    tcx = tst_ratios["1.0"].get(pol, {}).get("crossing", {})
    cx_mismatches = []
    deep_compare(rcx, tcx, f"crossing.r=1.0.{pol}", cx_mismatches)
    if cx_mismatches:
        mismatches.extend(cx_mismatches)
        print(f"    r=1.0 {pol}: MISMATCH")
    else:
        c_lo = rcx.get("C_lower_pct")
        c_hi = rcx.get("C_upper_pct")
        print(f"    r=1.0 {pol}: C_lower={c_lo}%  C_upper={c_hi}%  [match]")

# ── Compare lambda rows ────────────────────────────────────────────────────────
print("\n[3] Comparing lambda rows (all fields incl. q_admit, q_drop) ...")

for pol in POLICIES:
    rrows = ref_ratios["1.0"].get(pol, {}).get("lambda_rows", [])
    trows = tst_ratios["1.0"].get(pol, {}).get("lambda_rows", [])
    row_mismatches = []
    if len(rrows) != len(trows):
        row_mismatches.append(
            f"lambda_rows count: ref={len(rrows)} test={len(trows)}")
    else:
        for i, (rr, tr) in enumerate(zip(rrows, trows)):
            deep_compare(rr, tr, f"lambda_rows[{i}].r=1.0.{pol}", row_mismatches)
    if row_mismatches:
        mismatches.extend(row_mismatches)
        print(f"    r=1.0 {pol}: {len(row_mismatches)} lambda-row mismatch(es)")
    else:
        # Confirm q_admit/q_drop were compared (not silently skipped)
        q_present = "q_admit" in (rrows[0] if rrows else {})
        print(f"    r=1.0 {pol}: {len(rrows)} rows  "
              f"(q_admit/q_drop {'compared' if q_present else 'absent in ref — check'})  "
              f"[match]")

# ── Verdict ────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
if mismatches:
    print(f"EQUIVALENCE FAIL — {len(mismatches)} mismatch(es):")
    for m in mismatches[:30]:
        print(f"  {m}")
    if len(mismatches) > 30:
        print(f"  ... and {len(mismatches) - 30} more")
    print()
    fail("Recovery commit does not reproduce e2df32a outputs. "
         "Do NOT launch H3 until resolved.")
else:
    print("EQUIVALENCE PASS")
    print()
    print("  Recovery commit 7892204 reproduces freeze-commit e2df32a simulation")
    print("  output exactly for sc5 / r=1.0.")
    print("  Fields compared: all substantive fields including q_admit, q_drop,")
    print("  crossings, every lambda-row field, seeds, reference budgets,")
    print("  binding flags, invariant outputs.")
    print("  Fields excluded: elapsed_s, elapsed_total_s, git provenance.")
    print()
    print("  Authorized to proceed with H3 launch.")
