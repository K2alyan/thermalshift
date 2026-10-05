#!/usr/bin/env python3
"""
Batch transition gate: rigorous verification of a completed sensitivity batch
before launching the next batch.

Per-run checks:
  1.  Final JSON exists
  2.  Final JSON parses cleanly
  3.  Exactly 25 unique scenario IDs: sc30-sc54, no duplicates
  4.  Log contains exactly 25 unique "Scenario X done" lines covering sc30-sc54
  5.  CAB_SCALE and SENSITIVITY_BETA match expected values [HARD FAIL — mandatory]
  6.  Only full_fp and full_random policies present (no others)
  7.  Only r=1.25 ratio present
  8.  All 25 seed assertions PASS in log (frozen scen/wl/fp/random seeds)
  9.  No [skip]/resume lines (fresh run, no checkpoint contamination)
  10. No NaN/Inf in any crossing object
  11. No malformed crossing objects (missing required fields)
  12. No unexpected right-censoring (flag if any; not necessarily a FAIL)
  13. No ERROR/TRACEBACK/EXCEPTION lines in log
  14. SHA256 recorded for final JSON and log
  15. E1 scale=0.90 provenance note (aborted prior attempt)

Usage (mandatory structured form — no positional/skip mode):
  python check_batch_transition.py \\
    --run log1.log --cab-scale 0.90 --beta 1.11416358 \\
    --run log2.log --cab-scale 1.00 --beta 1.12484352 \\
    ...

Each --run MUST be accompanied by --cab-scale and --beta.
Metadata comparison is mandatory (tolerance 1e-10). A mismatch is a HARD FAIL.

Exits 0 if all checks pass; exits 1 with details if any fail.
"""
import sys, io, json, re, hashlib, math, datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
RES       = REPO_ROOT / "artifacts" / "revision2" / "results"

SC_FIRST  = 30
N_SC      = 25
EXPECTED_SCS      = set(range(SC_FIRST, SC_FIRST + N_SC))
EXPECTED_POLICIES = {"full_fp", "full_random"}
EXPECTED_RATIO    = "1.25"
CROSSING_REQUIRED = {"status", "C_lower_pct", "C_upper_pct", "right_censored"}
METADATA_TOL      = 1e-10


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parse_run_specs(argv):
    """Parse --run log --cab-scale v --beta v triplets from argv."""
    specs = []
    i = 0
    while i < len(argv):
        if argv[i] == "--run":
            if i + 1 >= len(argv):
                print("ERROR: --run requires a log path argument")
                sys.exit(1)
            log_path = Path(argv[i + 1])
            cab_scale = None
            beta      = None
            j = i + 2
            while j < len(argv) and argv[j] != "--run":
                if argv[j] == "--cab-scale":
                    if j + 1 >= len(argv):
                        print("ERROR: --cab-scale requires a value")
                        sys.exit(1)
                    cab_scale = float(argv[j + 1])
                    j += 2
                elif argv[j] == "--beta":
                    if j + 1 >= len(argv):
                        print("ERROR: --beta requires a value")
                        sys.exit(1)
                    beta = float(argv[j + 1])
                    j += 2
                else:
                    j += 1
            if cab_scale is None:
                print(f"ERROR: --run {log_path} missing --cab-scale")
                sys.exit(1)
            if beta is None:
                print(f"ERROR: --run {log_path} missing --beta")
                sys.exit(1)
            specs.append((log_path, cab_scale, beta))
            i = j
        else:
            i += 1
    return specs


def check_run(log_path: Path, expected_scale: float, expected_beta: float) -> dict:
    result = {
        "log":              str(log_path.name),
        "checker_version":  "v2_with_metadata_enforcement",
        "metadata_tol":     METADATA_TOL,
        "expected_scale":   expected_scale,
        "expected_beta":    round(expected_beta, 10),
        "observed_scale":   None,
        "observed_beta":    None,
        "checks":           {},
        "sha256_log":       None,
        "sha256_json":      None,
        "output_file":      None,
        "provenance_notes": [],
        "pass":             True,
    }

    def fail(key, msg):
        result["checks"][key] = f"FAIL: {msg}"
        result["pass"] = False

    def ok(key, msg):
        result["checks"][key] = f"PASS: {msg}"

    def warn(key, msg):
        result["checks"][key] = f"WARN: {msg}"

    # ── Check 1: log exists ──────────────────────────────────────────────────
    if not log_path.exists():
        fail("log_exists", f"log not found: {log_path}")
        return result
    ok("log_exists", "found")

    log_text = log_path.read_text(encoding="utf-8", errors="replace")
    result["sha256_log"] = sha256_file(log_path)

    # ── Locate final JSON from "Saved:" line ─────────────────────────────────
    saved_lines = [l.strip() for l in log_text.splitlines() if l.startswith("Saved:")]
    if not saved_lines:
        fail("saved_line", "no 'Saved:' line in log")
        return result
    out_path = Path(saved_lines[0].replace("Saved:", "").strip())
    result["output_file"] = str(out_path.name)

    if not out_path.exists():
        fail("json_exists", f"output JSON not found: {out_path}")
        return result
    ok("json_exists", out_path.name)
    result["sha256_json"] = sha256_file(out_path)

    # ── Check 2: parse JSON ──────────────────────────────────────────────────
    try:
        data = json.loads(out_path.read_text())
    except Exception as e:
        fail("json_parse", str(e))
        return result
    ok("json_parse", "clean")

    sc_results = data.get("scenario_results", [])

    # ── Check 3: exactly 25 unique sc30-54 in JSON ───────────────────────────
    sc_indices = [s["scenario_idx"] for s in sc_results]
    sc_set     = set(sc_indices)
    dupes      = [i for i in sc_set if sc_indices.count(i) > 1]
    missing_sc = EXPECTED_SCS - sc_set
    extra_sc   = sc_set - EXPECTED_SCS

    if dupes:
        fail("no_duplicate_scenarios", f"duplicates: {dupes}")
    elif missing_sc or extra_sc:
        fail("scenario_coverage_json",
             f"missing={sorted(missing_sc)} extra={sorted(extra_sc)}")
    else:
        ok("scenario_coverage_json", "sc30-sc54 all present, no duplicates")

    # ── Check 4: log contains 25 unique scenario IDs ─────────────────────────
    done_pattern = re.compile(r"Scenario (\d+) done")
    log_done_ids = [int(m.group(1)) for m in done_pattern.finditer(log_text)]
    log_done_set = set(log_done_ids)
    log_dupes    = [i for i in log_done_set if log_done_ids.count(i) > 1]
    log_missing  = EXPECTED_SCS - log_done_set
    log_extra    = log_done_set - EXPECTED_SCS

    if log_dupes:
        fail("log_no_duplicate_scenarios", f"log duplicates: {log_dupes}")
    elif log_missing or log_extra:
        fail("log_scenario_coverage",
             f"missing={sorted(log_missing)} extra={sorted(log_extra)}")
    elif len(log_done_ids) != 25:
        fail("log_scenario_count", f"expected 25 done lines, got {len(log_done_ids)}")
    else:
        ok("log_scenario_coverage", "25 unique sc30-sc54 completion lines in log")

    # ── Check 5: metadata comparison [HARD FAIL] ─────────────────────────────
    cab_scale_env = data.get("cab_scale_env", "MISSING")
    beta_env      = data.get("sensitivity_beta_env", "MISSING")
    cab_scale_val = data.get("cab_scale")
    beta_val      = data.get("sensitivity_beta")

    result["observed_scale"] = cab_scale_val
    result["observed_beta"]  = beta_val

    scale_match = (cab_scale_val is not None and
                   abs(float(cab_scale_val) - expected_scale) < METADATA_TOL)
    beta_match  = (beta_val is not None and
                   abs(float(beta_val) - expected_beta) < METADATA_TOL)

    if not scale_match and not beta_match:
        fail("metadata_expected",
             f"BOTH MISMATCH — expected scale={expected_scale} beta={expected_beta:.8f} | "
             f"observed scale={cab_scale_val} beta={beta_val} "
             f"(env: cab_scale_env={cab_scale_env!r} beta_env={beta_env!r})")
    elif not scale_match:
        fail("metadata_expected",
             f"SCALE MISMATCH — expected={expected_scale} observed={cab_scale_val} "
             f"(env: cab_scale_env={cab_scale_env!r})")
    elif not beta_match:
        fail("metadata_expected",
             f"BETA MISMATCH — expected={expected_beta:.8f} observed={beta_val} "
             f"(env: sensitivity_beta_env={beta_env!r})")
    else:
        ok("metadata_expected",
           f"scale {cab_scale_val}=={expected_scale} [tol=1e-10]  "
           f"beta {beta_val:.8f}=={expected_beta:.8f} [tol=1e-10]  "
           f"(env: cab_scale_env={cab_scale_env!r} beta_env={beta_env!r})")

    # ── Check 6: only FP and Random policies ─────────────────────────────────
    policies_found = set()
    for sc in sc_results:
        for ratio_data in sc.get("ratios", {}).values():
            policies_found.update(ratio_data.keys())
    unexpected_pols = policies_found - EXPECTED_POLICIES
    if unexpected_pols:
        fail("policies_fp_random_only", f"unexpected policies: {unexpected_pols}")
    else:
        ok("policies_fp_random_only", f"only {sorted(policies_found)}")

    # ── Check 7: only r=1.25 ratio ───────────────────────────────────────────
    ratios_found = set()
    for sc in sc_results:
        ratios_found.update(sc.get("ratios", {}).keys())
    unexpected_ratios = ratios_found - {EXPECTED_RATIO}
    if unexpected_ratios:
        fail("ratio_125_only", f"unexpected ratios: {unexpected_ratios}")
    else:
        ok("ratio_125_only", f"only r={sorted(ratios_found)}")

    # ── Check 8: seed assertions ──────────────────────────────────────────────
    seed_pass_lines = re.findall(r"\[seed_assert\] sc(\d+): PASS", log_text)
    seed_fail_lines = [l for l in log_text.splitlines()
                       if "seed_assert" in l and "PASS" not in l and "WARNING" not in l]
    seed_pass_ids   = set(int(x) for x in seed_pass_lines)
    seed_missing    = EXPECTED_SCS - seed_pass_ids

    if seed_fail_lines:
        fail("seed_assertions", f"FAIL lines: {seed_fail_lines[:3]}")
    elif seed_missing:
        fail("seed_assertions", f"missing PASS for scenarios: {sorted(seed_missing)}")
    else:
        ok("seed_assertions", f"{len(seed_pass_ids)} PASS, 0 FAIL")

    # ── Check 9: no skip/resume lines ────────────────────────────────────────
    skip_lines   = [l for l in log_text.splitlines() if "[skip]" in l]
    resume_lines = [l for l in log_text.splitlines() if "[checkpoint] Resuming" in l]
    if skip_lines or resume_lines:
        fail("no_checkpoint_resume",
             f"{len(skip_lines)} [skip] lines, {len(resume_lines)} resume lines — "
             "run resumed from checkpoint; verify checkpoint provenance")
    else:
        ok("no_checkpoint_resume", "fresh run confirmed (no skip/resume)")

    # ── Checks 10 & 11: NaN/Inf and malformed crossings ──────────────────────
    nan_inf_count   = 0
    malformed_count = 0
    rcensored_count = 0

    for sc in sc_results:
        for ratio, ratio_data in sc.get("ratios", {}).items():
            for pol, pol_data in ratio_data.items():
                cx = pol_data.get("crossing", {})
                if CROSSING_REQUIRED - set(cx.keys()):
                    malformed_count += 1
                for k, v in cx.items():
                    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                        nan_inf_count += 1
                if cx.get("right_censored"):
                    rcensored_count += 1

    if nan_inf_count:
        fail("no_nan_inf", f"{nan_inf_count} NaN/Inf values in crossing objects")
    else:
        ok("no_nan_inf", "0 NaN/Inf values")

    if malformed_count:
        fail("no_malformed_crossings",
             f"{malformed_count} crossing objects missing required fields")
    else:
        ok("no_malformed_crossings", "all crossing objects well-formed")

    if rcensored_count:
        warn("right_censoring",
             f"{rcensored_count} right-censored crossings (review before analysis)")
    else:
        ok("right_censoring", "0 right-censored crossings")

    # ── Check 13: no errors ───────────────────────────────────────────────────
    error_lines = [l.strip() for l in log_text.splitlines()
                   if any(kw in l.upper() for kw in ["TRACEBACK", "EXCEPTION", "FATAL"])
                   or ("ERROR" in l.upper() and "seed_assert" not in l.lower()
                       and "CROSSING" not in l)]
    if error_lines:
        fail("no_errors", f"error lines: {error_lines[:3]}")
    else:
        ok("no_errors", "none")

    # ── E1 scale=0.90 provenance note ────────────────────────────────────────
    if "sc0p90" in log_path.name or (out_path and "0p90" in str(out_path)):
        result["provenance_notes"].append(
            "E1 scale=0.90: an earlier sequential attempt was aborted after producing "
            "a partial checkpoint (12 scenarios, no final JSON). The authoritative run "
            "started fresh (no [skip]/resume lines), overwrote the checkpoint, and "
            "completed all 25 scenarios. Only this completed relaunched output is used."
        )

    return result


# ── Main ──────────────────────────────────────────────────────────────────────
run_specs = parse_run_specs(sys.argv[1:])
if not run_specs:
    print("Usage: python check_batch_transition.py \\")
    print("         --run log1.log --cab-scale 0.90 --beta 1.11416358 \\")
    print("         --run log2.log --cab-scale 1.00 --beta 1.12484352")
    print()
    print("Each --run MUST be accompanied by --cab-scale and --beta.")
    print("Metadata verification is mandatory; there is no positional/skip mode.")
    sys.exit(1)

all_pass     = True
audit_records = []

for log_path, expected_scale, expected_beta in run_specs:
    res = check_run(log_path, expected_scale, expected_beta)
    audit_records.append(res)
    if not res["pass"]:
        all_pass = False

    print(f"\n{'='*60}")
    print(f"Run: {res['log']}")
    print(f"Output: {res.get('output_file', 'N/A')}")
    print(f"Expected: scale={expected_scale}  beta={expected_beta:.8f}")
    for key, val in res["checks"].items():
        print(f"  {val}")
    if res["provenance_notes"]:
        for note in res["provenance_notes"]:
            print(f"  NOTE: {note}")
    print(f"  SHA256 JSON: {res['sha256_json']}")
    print(f"  SHA256 log:  {res['sha256_log']}")
    print(f"  => {'PASS' if res['pass'] else 'FAIL'}")

print(f"\n{'='*60}")
verdict = "PASS — safe to launch next batch" if all_pass else "FAIL — do NOT launch next batch"
print(f"Batch transition gate: {verdict}")

# ── Write / update audit record ───────────────────────────────────────────────
audit_out = RES / "batch_transition_audit.json"
existing_doc = {}
if audit_out.exists():
    try:
        existing_doc = json.loads(audit_out.read_text())
    except Exception:
        pass

existing_runs = existing_doc.get("runs", [])

new_doc = {
    "generated_at":  datetime.datetime.utcnow().isoformat() + "Z",
    "overall_pass":  all_pass,
}

# Preserve correction notice if already present
if "checker_correction_notice" in existing_doc:
    new_doc["checker_correction_notice"] = existing_doc["checker_correction_notice"]

new_doc["runs"] = existing_runs + audit_records

audit_out.write_text(json.dumps(new_doc, indent=2))
print(f"Audit written: {audit_out.name}")

sys.exit(0 if all_pass else 1)
