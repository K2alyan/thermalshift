#!/usr/bin/env python3
"""
r1_gate_f_merge.py
Merge and validate 25 per-scenario Gate F results into the canonical file
expected by r1_gate_f_heldout_analysis.py.

Reads  : gate_f_sc{k}-{k}_1p25_1p5_2p0_4p0_8p0.json  (k = 5..29)
Writes : gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json

Fails closed unless ALL ten conditions pass:
  1.  Exactly 25 files present; indices exactly 5..29; no duplicates.
  2.  Same ratio config ["1.25","1.5","2.0","4.0","8.0"] in every file.
  3.  Same git_commit_full across all files.
  4.  git_tracked_dirty == False in every file.
  5.  script == "r1_gate_f_run.py" and n_dev == 1 in every file.
  6.  Each file: exactly 1 scenario_result; scenario_idx == filename index;
      n_first == filename index.
  7.  All five ratios and four policies present for every scenario.
  8.  No NaN/Inf in C_lower_pct / C_upper_pct; C_lower <= C_upper.
  9.  No invariant_violated crossing.
 10.  Merged scenario_results sorted by scenario_idx; count == 25.

Output schema is identical to a monolithic N_DEV=25 run so that
r1_gate_f_heldout_analysis.py requires no changes.
"""

import sys, io, json, math
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "revision1" / "results"

HELDOUT_SCENARIOS = list(range(5, 30))        # sc5-sc29, N=25
RATIO_STRS        = ["1.25", "1.5", "2.0", "4.0", "8.0"]
POLICIES          = ["full_random", "full_fp", "full_loc", "full_fp_spread"]
RATIO_TAG         = "1p25_1p5_2p0_4p0_8p0"
OUT_FILE          = OUT_DIR / f"gate_f_sc5-29_{RATIO_TAG}.json"

errors:   list[str] = []
warnings: list[str] = []

def fail(msg: str):
    print(f"\nFAIL: {msg}", file=sys.stderr)
    sys.exit(1)

def err(msg: str):
    errors.append(msg)
    print(f"  ERROR: {msg}")

def warn(msg: str):
    warnings.append(msg)
    print(f"  WARN:  {msg}")

def is_finite(v) -> bool:
    if v is None:
        return False
    try:
        return math.isfinite(float(v))
    except (TypeError, ValueError):
        return False

print("Gate F: Per-scenario merge + validate")
print("=" * 70)

# ── Check 1: File presence ─────────────────────────────────────────────────────
print("\n[1] Checking file presence ...")
found: dict[int, Path] = {}
for sc in HELDOUT_SCENARIOS:
    p = OUT_DIR / f"gate_f_sc{sc}-{sc}_{RATIO_TAG}.json"
    if p.exists():
        found[sc] = p
    else:
        err(f"Missing: {p.name}")

missing = sorted(set(HELDOUT_SCENARIOS) - set(found))
extra   = sorted(set(found) - set(HELDOUT_SCENARIOS))
if extra:
    err(f"Unexpected scenario indices in found set: {extra}")

n_found = len(found)
print(f"    {n_found}/25 files present"
      + (f"  — missing: {missing}" if missing else "  (all present)"))

if errors:
    for e in errors:
        print(f"    {e}")
    fail(f"File presence check failed ({len(errors)} errors). Cannot merge.")

# ── Load all files ─────────────────────────────────────────────────────────────
print("\n[2-9] Loading and validating each file ...")
loaded: dict[int, dict] = {}
all_commits: set[str]   = set()

for sc in HELDOUT_SCENARIOS:
    path = found[sc]
    try:
        d = json.loads(path.read_text())
    except Exception as e:
        err(f"sc{sc}: JSON parse error: {e}")
        continue
    loaded[sc] = d

    # Check 5: script and n_dev
    if d.get("script") != "r1_gate_f_run.py":
        err(f"sc{sc}: script={d.get('script')!r} (expected 'r1_gate_f_run.py')")
    if d.get("n_dev") != 1:
        err(f"sc{sc}: n_dev={d.get('n_dev')} (expected 1)")

    # Check 2: ratio config
    file_ratios = d.get("gate_f_ratios", [])
    if file_ratios != RATIO_STRS:
        err(f"sc{sc}: gate_f_ratios={file_ratios} (expected {RATIO_STRS})")

    # Check 3: collect commit hash
    commit = d.get("git_commit_full", "")
    if commit:
        all_commits.add(commit)
    else:
        err(f"sc{sc}: git_commit_full missing")

    # Check 4: clean git
    if d.get("git_tracked_dirty") is not False:
        err(f"sc{sc}: git_tracked_dirty={d.get('git_tracked_dirty')} (expected False)")

    # Check 6: scenario_results structure
    sr = d.get("scenario_results", [])
    if len(sr) != 1:
        err(f"sc{sc}: scenario_results has {len(sr)} entries (expected 1)")
        continue

    sc_entry = sr[0]
    actual_idx = int(sc_entry.get("scenario_idx", -1))
    if actual_idx != sc:
        err(f"sc{sc}: scenario_idx={actual_idx} inside result (expected {sc})")
    if d.get("n_first") != sc:
        err(f"sc{sc}: n_first={d.get('n_first')} (expected {sc})")

    # Check 7: ratios and policies present
    ratios_dict = sc_entry.get("ratios", {})
    for r_str in RATIO_STRS:
        if r_str not in ratios_dict:
            err(f"sc{sc}: ratio {r_str!r} missing from scenario_results")
            continue
        for pol in POLICIES:
            if pol not in ratios_dict[r_str]:
                err(f"sc{sc} r={r_str}: policy {pol!r} missing")
                continue

            cx     = ratios_dict[r_str][pol].get("crossing", {})
            status = cx.get("status", "")
            c_lo   = cx.get("C_lower_pct")
            c_hi   = cx.get("C_upper_pct")

            # Check 9: no invariant violation
            if status == "invariant_violated":
                err(f"sc{sc} r={r_str} {pol}: invariant_violated")

            # Check 8: finite, ordered C values
            if status not in ("right_censored", "no_crossing", "invariant_violated"):
                if not is_finite(c_lo):
                    err(f"sc{sc} r={r_str} {pol}: C_lower_pct not finite ({c_lo})")
                if not is_finite(c_hi):
                    err(f"sc{sc} r={r_str} {pol}: C_upper_pct not finite ({c_hi})")
                if is_finite(c_lo) and is_finite(c_hi):
                    if float(c_lo) > float(c_hi):
                        err(f"sc{sc} r={r_str} {pol}: "
                            f"C_lower={c_lo} > C_upper={c_hi}")

            if cx.get("right_censored"):
                warn(f"sc{sc} r={r_str} {pol}: right_censored "
                     f"(C_lower={c_lo})")

    status_str = "OK" if not any(e.startswith(f"sc{sc}:") or e.startswith(f"sc{sc} ")
                                  for e in errors) else "ERRORS"
    print(f"    sc{sc:02d}: {status_str}  "
          f"commit={d.get('git_commit_short','?')}  "
          f"dirty={d.get('git_tracked_dirty')}")

# ── Check 3: Commit consistency ────────────────────────────────────────────────
print("\n[3] Cross-file commit consistency ...")
if len(all_commits) == 1:
    common_commit = next(iter(all_commits))
    print(f"    Commit: {common_commit[:16]}...  (same across all {len(loaded)} files)")
elif len(all_commits) == 0:
    err("No git_commit_full found in any file")
else:
    err(f"Commit hash mismatch — {len(all_commits)} distinct commits: {all_commits}")

# ── Abort if any errors ────────────────────────────────────────────────────────
if errors:
    print(f"\n{'='*70}")
    print(f"Validation FAILED — {len(errors)} error(s):")
    for e in errors:
        print(f"  {e}")
    fail("Output NOT written. Fix errors and rerun.")

if warnings:
    print(f"\n  {len(warnings)} warning(s) (right-censored crossings — allowed):")
    for w in warnings:
        print(f"    {w}")

print(f"\n  All 25 scenario files passed checks 1-9.")

# ── Check 10: Merge and final count ───────────────────────────────────────────
print("\n[10] Merging (sorted by scenario_idx) ...")

merged_results = [loaded[sc]["scenario_results"][0]
                  for sc in sorted(loaded.keys())]

idx_seq = [int(r["scenario_idx"]) for r in merged_results]
if idx_seq != list(range(5, 30)):
    fail(f"Merged scenario_idx sequence wrong: {idx_seq}")
if len(merged_results) != 25:
    fail(f"Merged count = {len(merged_results)} (expected 25)")

# Build canonical output — same top-level schema as a monolithic N_DEV=25 run.
# Use metadata from sc5 (first scenario file) for shared fields.
ref = loaded[5]
elapsed_sum = sum(
    loaded[sc].get("elapsed_total_s", 0) for sc in HELDOUT_SCENARIOS)

merged = {
    "git_commit_full"       : ref["git_commit_full"],
    "git_commit_short"      : ref["git_commit_short"],
    "git_tracked_dirty"     : ref.get("git_tracked_dirty"),
    "git_untracked_present" : ref.get("git_untracked_present"),
    "git_untracked_count"   : ref.get("git_untracked_count"),
    "script"                : "r1_gate_f_run.py",
    "merged_by"             : "r1_gate_f_merge.py",
    "n_dev"                 : 25,
    "n_first"               : 5,
    "gate_f_ratios"         : RATIO_STRS,
    "gate_f_policies"       : POLICIES,
    "lambda_sweep"          : ref.get("lambda_sweep"),
    "target_pp"             : ref.get("target_pp"),
    "scenario_results"      : merged_results,
    "elapsed_total_s"       : round(elapsed_sum, 1),
}

OUT_FILE.write_text(json.dumps(merged, indent=2))
print(f"    Written: {OUT_FILE.name}")
print(f"    Scenarios: sc{idx_seq[0]}-sc{idx_seq[-1]}  (n={len(merged_results)})")
print(f"    Commit:    {ref.get('git_commit_short','?')}")
print(f"    Elapsed sum: {elapsed_sum:.0f}s ({elapsed_sum/3600:.2f}h)")

if warnings:
    print(f"\n  Note: {len(warnings)} right-censored crossing(s) — "
          "held-out analyzer will check these.")

print(f"\nMerge complete. All 10 validation conditions passed.")
print(f"\nNext:")
print(f"  python artifacts/revision1/analysis/r1_gate_f_heldout_analysis.py")
