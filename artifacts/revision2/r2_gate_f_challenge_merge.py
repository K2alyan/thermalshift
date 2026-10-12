#!/usr/bin/env python3
"""
Challenge results merger (r2_gate_f_challenge_merge.py)

Merges per-batch *_r2challenge.json files from artifacts/revision2/results/
into a single unified file covering all sc30-54.

Plan ref: REVIEW2_CHALLENGE_PLAN.md Amendment 4 §G2.

Usage:
  python r2_gate_f_challenge_merge.py [--out <path>]

Output: artifacts/revision2/results/gate_f_sc30-54_all_r2challenge_merged.json
"""
import sys, io, json, argparse, datetime, hashlib
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REV2_DIR  = REPO_ROOT / "artifacts" / "revision2"
OUT_DIR   = REV2_DIR / "results"

DEFAULT_OUT  = OUT_DIR / "gate_f_sc30-54_all_r2challenge_merged.json"
SC_FIRST     = 30
SC_LAST      = 54
N_EXPECTED   = SC_LAST - SC_FIRST + 1   # 25 scenarios

EXPECTED_RATIOS   = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"]
EXPECTED_POLICIES = [
    "full_random", "full_fp", "position_template", "full_fp_spread",
    "random_spread", "fp_global_placebo", "fp_withincab_placebo",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(DEFAULT_OUT),
                        help="Output path (default: gate_f_sc30-54_all_r2challenge_merged.json)")
    parser.add_argument("--allow-partial", action="store_true",
                        help="Don't fail if not all 25 scenarios are present")
    args = parser.parse_args()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("Challenge Results Merge")
    print("=" * 70)

    # Collect all _r2challenge.json files (not the merged output itself)
    batch_files = sorted([
        p for p in OUT_DIR.glob("gate_f_*_r2challenge.json")
        if "_merged" not in p.name and "_checkpoint" not in p.name
    ], key=lambda p: p.stat().st_mtime)

    if not batch_files:
        print("ERROR: No *_r2challenge.json files found in results/")
        sys.exit(1)

    print(f"\nFound {len(batch_files)} batch file(s):")
    for f in batch_files:
        print(f"  {f.name}")

    # Merge scenario_results
    merged_scenarios: dict[int, dict] = {}
    source_files = []
    meta_fields: dict[str, object] = {}

    for fpath in batch_files:
        try:
            data = json.loads(fpath.read_text())
        except Exception as exc:
            print(f"  ERROR reading {fpath.name}: {exc}")
            sys.exit(1)

        if not meta_fields:
            for key in ("challenge_seed", "primary_beta_challenge", "beta_f_frozen",
                        "lambda_sweep", "target_pp", "gate_f_policies",
                        "placebo_global_perm_seed", "placebo_withincab_perm_seed"):
                if key in data:
                    meta_fields[key] = data[key]

        source_files.append({
            "file"       : fpath.name,
            "sha256"     : sha256(fpath),
            "git_commit" : data.get("git_commit_short"),
            "n_scenarios": len(data.get("scenario_results", [])),
            "n_first"    : data.get("n_first"),
            "n_dev"      : data.get("n_dev"),
        })

        for sr in data.get("scenario_results", []):
            idx = int(sr["scenario_idx"])
            if idx in merged_scenarios:
                print(f"  WARNING: Duplicate sc{idx} — keeping first occurrence")
                continue
            merged_scenarios[idx] = sr

    print(f"\nMerged {len(merged_scenarios)} unique scenarios: "
          f"{sorted(merged_scenarios.keys())}")

    # Validation
    errors = []
    sc_range = list(range(SC_FIRST, SC_LAST + 1))
    missing = [sc for sc in sc_range if sc not in merged_scenarios]
    extra   = [sc for sc in sorted(merged_scenarios.keys()) if sc not in sc_range]

    if missing:
        errors.append(f"Missing scenarios: {missing}")
    if extra:
        errors.append(f"Unexpected scenarios: {extra}")

    # Per-scenario validation
    n_validated = 0
    ratio_coverage: dict[str, int] = {r: 0 for r in EXPECTED_RATIOS}
    policy_coverage: dict[str, int] = {p: 0 for p in EXPECTED_POLICIES}

    for sc_idx, sr in merged_scenarios.items():
        ratios_present = set(sr.get("ratios", {}).keys())
        for r in EXPECTED_RATIOS:
            if r in ratios_present:
                ratio_coverage[r] += 1
        for r in ratios_present:
            pols = set(sr["ratios"][r].keys())
            for p in EXPECTED_POLICIES:
                if p in pols:
                    policy_coverage[p] += 1
        n_validated += 1

    print(f"\nValidation:")
    print(f"  Scenarios present: {n_validated}/{N_EXPECTED}")
    if missing:
        print(f"  MISSING: {missing}")
    if extra:
        print(f"  EXTRA: {extra}")
    for r, cnt in ratio_coverage.items():
        status = "OK" if cnt == n_validated else f"MISSING in {n_validated - cnt} sc"
        print(f"  ratio {r:12s}: {cnt}/{n_validated} scenarios  [{status}]")

    overall_valid = (len(errors) == 0)
    if not overall_valid:
        for e in errors:
            print(f"  ERROR: {e}")
        if not args.allow_partial:
            print("\nMerge FAILED — resolve errors before challenge analysis.")
            sys.exit(1)
        else:
            print("\nWARNING: Proceeding with partial merge (--allow-partial).")

    # Build output
    scenario_results_sorted = [
        merged_scenarios[sc] for sc in sorted(merged_scenarios.keys())
    ]

    result = {
        "script"           : "artifacts/revision2/r2_gate_f_challenge_merge.py",
        "plan_ref"         : "REVIEW2_CHALLENGE_PLAN.md Amendment 4 §G2",
        "merged_at"        : datetime.datetime.utcnow().isoformat() + "Z",
        "source_files"     : source_files,
        "n_scenarios"      : len(scenario_results_sorted),
        "scenarios_present": sorted(merged_scenarios.keys()),
        "missing_scenarios": missing,
        "extra_scenarios"  : extra,
        "validation_pass"  : overall_valid,
        "ratio_coverage"   : ratio_coverage,
        "policy_coverage"  : policy_coverage,
        **meta_fields,
        "scenario_results" : scenario_results_sorted,
    }

    out_path.write_text(json.dumps(result, indent=2))
    print(f"\nWritten: {out_path}")
    if overall_valid:
        print(f"Merge: PASS — {len(scenario_results_sorted)} scenarios, all validated.")
    else:
        print(f"Merge: PARTIAL — {len(scenario_results_sorted)} scenarios (missing: {missing}).")

    return 0 if overall_valid else 1


if __name__ == "__main__":
    sys.exit(main())
