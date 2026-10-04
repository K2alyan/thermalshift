#!/usr/bin/env python3
"""
Challenge completion audit — read-only with respect to all challenge outputs.
Checks all 16 conditions from the frozen audit spec.
Writes artifacts/revision2/challenge_completion_audit.json.
"""
import sys, io, json, hashlib, math, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parents[2]
REV2_DIR    = REPO_ROOT / "artifacts" / "revision2"
RESULTS_DIR = REV2_DIR / "results"
AUDIT_FILE  = REV2_DIR / "challenge_seed_index_audit.json"
OUT_FILE    = REV2_DIR / "challenge_completion_audit.json"

EXPECTED_SCENARIOS = list(range(30, 55))
EXPECTED_RATIOS    = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"]
EXPECTED_POLICIES  = [
    "full_random", "full_fp", "position_template", "full_fp_spread",
    "random_spread", "fp_global_placebo", "fp_withincab_placebo",
]
PRIMARY_BETA_CHALLENGE = 1.11416358
CHALLENGE_SEED         = 2042
FREEZE_SHA_SHORT       = "5733b73"
FREEZE_SHA_FULL        = "5733b73bd715157f479821d969aac99811eee0d7"

# Frozen SHA256s from provenance record
SC30_SHA256           = "70808e6105e7fb9f1bfc9b04b5b39df534cd26c6fc2930ab53ea132ab7ea67fb"
SC31_SHA256           = "e3c860fdd4a8213d620fee8c8ae70d82b909122ae41ac6064c8282b314857b6f"
SC32_SHA256           = "45c75ab877b946ccd7eceb383410975dda24e1ee210eb2f14db9858b33a18e38"
ORIG_ORCH_SHA256      = "c45e97aa67607200b4b1349f538e07b77a370a36302a8cbd277cf9d672f586d3"
FINAL_4W_ORCH_SHA256  = "f4f4bd9eda899c878e6e31698f9d191345e78fb5f27b034ca922d87e3bf3d2a7"
FROZEN_RUNNER_SHA256  = "750150c337a1f81368bdba35e2af6ccda23f2917297d5f9ab3ebf51dd8281856"
INCIDENT_FILE         = RESULTS_DIR / "OPERATIONAL_INCIDENT_sc33_sc34_aborted.json"

# Lambda-row numeric fields that must not be NaN/Inf (null/None is acceptable)
LAMBDA_NUM_FIELDS = [
    "capacity_unlock_pct", "B_primary_h", "S_primary_Cdoth", "B_secondary_h",
    "B_cab_ratio", "syn_node_hours", "cab_span_median",
    "full_selector_eligible_count_p10", "full_selector_eligible_count_p50",
    "full_selector_eligible_count_p90", "exposed_selector_eligible_count_p10",
    "exposed_selector_eligible_count_p50", "exposed_selector_eligible_count_p90",
    "realized_selector_choice_mult_p10", "realized_selector_choice_mult_p50",
    "realized_selector_choice_mult_p90", "B_primary_ratio", "S_primary_ratio",
]
CROSSING_NUM_FIELDS = ["C_lower_pct", "C_upper_pct"]


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def is_bad_float(v):
    if v is None:
        return False
    if isinstance(v, (int, float)):
        return math.isnan(v) or math.isinf(v)
    return False


def main():
    failures         = []
    notes            = []
    per_file         = {}
    nan_inf_counts   = {}
    invariant_violations  = {}
    right_censored_counts = {}   # {policy: {ratio: count}}
    seed_mismatches  = []
    prov_mismatches  = []
    missing_ratios   = {}
    missing_policies = {}
    malformed_files  = []
    duplicate_scenarios = []

    print("=" * 70)
    print("Challenge Completion Audit")
    print(f"  run_utc : {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print("=" * 70)

    # Load seed audit table
    seed_audit = json.loads(AUDIT_FILE.read_text(encoding="utf-8"))
    seed_table = seed_audit["scenario_table"]

    # --- CHECK 1/2/3: file existence, count, indices, duplicates ---
    files  = sorted(RESULTS_DIR.glob("gate_f_sc*_all_r2challenge.json"))
    n_files = len(files)
    notes.append(f"Found {n_files} r2challenge files in results/")

    if n_files != 25:
        failures.append(f"CHECK 1 FAIL: expected 25 files, found {n_files}")

    sc_to_file = {}
    for f in files:
        stem = f.stem   # e.g. gate_f_sc30-30_all_r2challenge
        try:
            sc_str = stem.split("_sc")[1].split("_")[0]  # "30-30"
            sc = int(sc_str.split("-")[0])
        except Exception as e:
            failures.append(f"CHECK 2 FAIL: cannot parse sc index from {f.name}: {e}")
            continue
        if sc in sc_to_file:
            failures.append(f"CHECK 3 FAIL: duplicate output for sc{sc}: {f.name}")
            duplicate_scenarios.append(sc)
        else:
            sc_to_file[sc] = f

    found_indices = sorted(sc_to_file.keys())
    missing_sc    = sorted(set(EXPECTED_SCENARIOS) - set(found_indices))
    extra_sc      = sorted(set(found_indices) - set(EXPECTED_SCENARIOS))

    if missing_sc:
        failures.append(f"CHECK 2 FAIL: missing scenario indices: {missing_sc}")
    if extra_sc:
        failures.append(f"CHECK 2 FAIL: unexpected scenario indices: {extra_sc}")
    notes.append(f"Scenario indices: {found_indices}")

    # --- CHECK 14: SHA256 verification for sc30/sc31/sc32 ---
    for sc, expected_sha in [(30, SC30_SHA256), (31, SC31_SHA256), (32, SC32_SHA256)]:
        if sc in sc_to_file:
            actual = sha256_file(sc_to_file[sc])
            per_file[f"sc{sc}"] = {"sha256": actual, "path": sc_to_file[sc].name}
            if actual != expected_sha:
                failures.append(
                    f"CHECK 14 FAIL: sc{sc} SHA256 mismatch\n"
                    f"  got      {actual}\n"
                    f"  expected {expected_sha}"
                )
            else:
                notes.append(f"sc{sc} SHA256 verified [PASS]")

    # --- CHECK 15: incident record present ---
    if INCIDENT_FILE.exists():
        notes.append(f"Incident record present: {INCIDENT_FILE.name} [PASS]")
    else:
        failures.append(f"CHECK 15 FAIL: incident record not found: {INCIDENT_FILE.name}")

    # --- PER-FILE checks (4–13) ---
    for sc in EXPECTED_SCENARIOS:
        if sc not in sc_to_file:
            continue

        fpath  = sc_to_file[sc]
        sc_key = f"sc{sc}"

        # Compute SHA256 for all (sc30/31/32 already done above)
        if sc_key not in per_file:
            per_file[sc_key] = {"sha256": sha256_file(fpath), "path": fpath.name}

        # CHECK 5: non-empty
        if fpath.stat().st_size == 0:
            failures.append(f"CHECK 5 FAIL: sc{sc} file is empty")
            malformed_files.append(sc)
            continue

        # CHECK 4: JSON parseable
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception as e:
            failures.append(f"CHECK 4 FAIL: sc{sc} JSON parse error: {e}")
            malformed_files.append(sc)
            continue

        # CHECK 7: provenance fields
        pbc = data.get("primary_beta_challenge")
        cs  = data.get("challenge_seed")
        gcs = data.get("git_commit_short")
        gcf = data.get("git_commit_full", "")

        if pbc != PRIMARY_BETA_CHALLENGE:
            msg = f"sc{sc} primary_beta_challenge={pbc!r} expected {PRIMARY_BETA_CHALLENGE}"
            failures.append(f"CHECK 7 FAIL: {msg}")
            prov_mismatches.append(msg)
        if cs != CHALLENGE_SEED:
            msg = f"sc{sc} challenge_seed={cs!r} expected {CHALLENGE_SEED}"
            failures.append(f"CHECK 7 FAIL: {msg}")
            prov_mismatches.append(msg)
        if gcs != FREEZE_SHA_SHORT and not gcf.startswith(FREEZE_SHA_SHORT):
            msg = f"sc{sc} git_commit_short={gcs!r} expected {FREEZE_SHA_SHORT}"
            failures.append(f"CHECK 7 FAIL: {msg}")
            prov_mismatches.append(msg)

        # CHECK 8: scenario_results present
        if "scenario_results" not in data or not data["scenario_results"]:
            failures.append(f"CHECK 8 FAIL: sc{sc} has no scenario_results")
            malformed_files.append(sc)
            continue

        sr = data["scenario_results"][0]

        # CHECK 6: seeds match frozen audit
        audit_row = seed_table.get(sc_key)
        if audit_row:
            got_idx  = sr.get("scenario_idx")
            got_scen = sr.get("scen_seed")
            got_wl   = sr.get("wl_seed")
            if got_idx != sc:
                msg = f"sc{sc} scenario_idx={got_idx} expected {sc}"
                failures.append(f"CHECK 6 FAIL: {msg}")
                seed_mismatches.append(msg)
            if got_scen != audit_row["scen_seed"]:
                msg = f"sc{sc} scen_seed={got_scen} expected {audit_row['scen_seed']}"
                failures.append(f"CHECK 6 FAIL: {msg}")
                seed_mismatches.append(msg)
            if got_wl != audit_row["wl_seed"]:
                msg = f"sc{sc} wl_seed={got_wl} expected {audit_row['wl_seed']}"
                failures.append(f"CHECK 6 FAIL: {msg}")
                seed_mismatches.append(msg)
        else:
            failures.append(f"CHECK 6 FAIL: sc{sc} not found in seed audit table")

        # CHECK 8: all 7 ratios present
        ratios_dict = sr.get("ratios", {})
        sc_ratios_missing = [r for r in EXPECTED_RATIOS if r not in ratios_dict]
        if sc_ratios_missing:
            failures.append(f"CHECK 8 FAIL: sc{sc} missing ratios: {sc_ratios_missing}")
            missing_ratios[sc_key] = sc_ratios_missing

        # Per ratio/policy
        for ratio_key in EXPECTED_RATIOS:
            if ratio_key not in ratios_dict:
                continue
            ratio_obj = ratios_dict[ratio_key]

            # CHECK 9: all 7 policies
            sc_pol_missing = [p for p in EXPECTED_POLICIES if p not in ratio_obj]
            if sc_pol_missing:
                failures.append(
                    f"CHECK 9 FAIL: sc{sc} ratio={ratio_key} missing policies: {sc_pol_missing}"
                )
                missing_policies[f"{sc_key}_r{ratio_key}"] = sc_pol_missing

            for pol in EXPECTED_POLICIES:
                if pol not in ratio_obj:
                    continue
                pol_obj = ratio_obj[pol]

                # CHECK 12: crossing exists
                if "crossing" not in pol_obj:
                    failures.append(
                        f"CHECK 12 FAIL: sc{sc} ratio={ratio_key} pol={pol} missing crossing"
                    )
                else:
                    crossing = pol_obj["crossing"]
                    # CHECK 13: right-censoring (outcome state, not corruption)
                    if crossing.get("right_censored", False):
                        right_censored_counts.setdefault(pol, {})
                        right_censored_counts[pol][ratio_key] = (
                            right_censored_counts[pol].get(ratio_key, 0) + 1
                        )
                    # CHECK 10: NaN/Inf in crossing numeric fields
                    for field in CROSSING_NUM_FIELDS:
                        v = crossing.get(field)
                        if is_bad_float(v):
                            key = f"{sc_key}_{ratio_key}_{pol}_{field}"
                            failures.append(f"CHECK 10 FAIL: NaN/Inf in crossing {key}={v}")
                            nan_inf_counts[key] = str(v)

                # CHECK 11: invariant violations; CHECK 10: NaN/Inf in lambda_rows
                lambda_rows = pol_obj.get("lambda_rows", [])
                if not lambda_rows:
                    failures.append(
                        f"CHECK 11 FAIL: sc{sc} ratio={ratio_key} pol={pol} has no lambda_rows"
                    )
                for lr_i, lr in enumerate(lambda_rows):
                    if lr.get("invariant_violated", False):
                        vkey = f"{sc_key}_{ratio_key}_{pol}"
                        invariant_violations.setdefault(vkey, []).append(lr.get("lambda_val"))
                    for field in LAMBDA_NUM_FIELDS:
                        v = lr.get(field)
                        if is_bad_float(v):
                            key = f"{sc_key}_{ratio_key}_{pol}_lr{lr_i}_{field}"
                            failures.append(f"CHECK 10 FAIL: NaN/Inf {key}={v}")
                            nan_inf_counts[key] = str(v)

    # --- Right-censoring summary (CHECK 13) ---
    total_rc = sum(sum(v.values()) for v in right_censored_counts.values())
    notes.append(f"Right-censored crossing events (total): {total_rc} — reported as outcome state, not corruption")

    # --- Invariant violations summary ---
    if invariant_violations:
        notes.append(f"Invariant violations found in {len(invariant_violations)} policy×ratio×scenario combinations")
        for vkey, lams in invariant_violations.items():
            failures.append(f"CHECK 11 FAIL: invariant_violated=True at {vkey} lambda_vals={lams}")

    # --- Final result ---
    audit_pass = len(failures) == 0

    result = {
        "audit_script"                : "artifacts/revision2/challenge_completion_audit.py",
        "audit_run_utc"               : datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "audit_pass"                  : audit_pass,
        "n_files_found"               : n_files,
        "n_scenarios"                 : len(found_indices),
        "scenario_indices"            : found_indices,
        "missing_scenarios"           : missing_sc,
        "extra_scenarios"             : extra_sc,
        "duplicate_scenarios"         : duplicate_scenarios,
        "seed_mismatches"             : seed_mismatches,
        "provenance_mismatches"       : prov_mismatches,
        "missing_ratios"              : missing_ratios,
        "missing_policies"            : missing_policies,
        "malformed_files"             : malformed_files,
        "nan_inf_counts"              : nan_inf_counts,
        "invariant_violations"        : invariant_violations,
        "right_censored_counts_by_policy_ratio": right_censored_counts,
        "right_censored_total"        : total_rc,
        "per_file_sha256"             : per_file,
        "provenance"                  : {
            "original_orchestrator_sha256"  : ORIG_ORCH_SHA256,
            "final_4w_orchestrator_sha256"  : FINAL_4W_ORCH_SHA256,
            "frozen_runner_sha256"          : FROZEN_RUNNER_SHA256,
            "frozen_head_sha"               : FREEZE_SHA_SHORT,
            "sc30_sha256_verified"          : (per_file.get("sc30", {}).get("sha256") == SC30_SHA256),
            "sc31_sha256_verified"          : (per_file.get("sc31", {}).get("sha256") == SC31_SHA256),
            "sc32_sha256_verified"          : (per_file.get("sc32", {}).get("sha256") == SC32_SHA256),
            "incident_record_present"       : INCIDENT_FILE.exists(),
            "incident_record_path"          : INCIDENT_FILE.name,
        },
        "notes"                       : notes,
        "failures"                    : failures,
    }

    OUT_FILE.write_text(json.dumps(result, indent=2))

    print(f"\nAudit: {'PASS' if audit_pass else 'FAIL'}")
    print(f"  n_files              : {n_files}")
    print(f"  n_scenarios          : {len(found_indices)}")
    print(f"  missing_scenarios    : {missing_sc}")
    print(f"  seed_mismatches      : {len(seed_mismatches)}")
    print(f"  prov_mismatches      : {len(prov_mismatches)}")
    print(f"  malformed_files      : {malformed_files}")
    print(f"  nan_inf_count        : {len(nan_inf_counts)}")
    print(f"  invariant_violations : {len(invariant_violations)}")
    print(f"  right_censored_total : {total_rc}")
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures:
            print(f"  FAIL: {f}")
    print(f"\nWritten: {OUT_FILE}")
    return 0 if audit_pass else 1


if __name__ == "__main__":
    sys.exit(main())
