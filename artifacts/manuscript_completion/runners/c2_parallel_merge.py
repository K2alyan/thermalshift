#!/usr/bin/env python3
"""
c2_parallel_merge.py — Governed merger for C2 parallel scenario outputs

Merges per-scenario JSONs produced by c2_parallel_launcher.py into the
combined output that a sequential run would produce.

Validation requirements (all must pass; any failure aborts without writing):
  - Runner SHA matches frozen c2_gate_f_run.py SHA
  - Per-scenario f2_reference_sha256 matches frozen value
  - Per-scenario f2_replay_denominator_sha256 matches frozen value
  - Per-scenario scientific_freeze_commit == "5733b73b"
  - Per-scenario per_scenario_placebo_seed_root == 847291653
  - Per-scenario script == "artifacts/manuscript_completion/runners/c2_gate_f_run.py"
  - Per-scenario gate_f_ratios == ["1.25"]
  - Per-scenario gate_f_policies == exactly the 7 authorized C2 policies
  - Per-scenario git_tracked_dirty == False (no dirty-run contamination)
  - No duplicate scenario IDs
  - No missing scenario IDs in [N_FIRST, N_FIRST + N_DEV - 1]
  - No scenario outside that range
  - Exactly N_DEV unique scenarios for a full merge

Merger NEVER averages, regenerates, or modifies scenario-level scientific fields.
Scenario results are taken directly from validated per-scenario files and sorted
by absolute scenario_idx. Only container-level metadata is computed for the merged file.

Usage:
  python3 c2_parallel_merge.py \\
    --manifest results/c2_worker_manifest_sc30-54.txt \\
    --n-first 30 --n-dev 25 \\
    --out results/gate_f_sc30-54_1p25_c2manuscript.json

Exit codes: 0 = success, 1 = any validation failure.
"""

import sys, os, json, hashlib, argparse, time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

# ── Frozen provenance constants ────────────────────────────────────────────────
_RUNNER_NAME              = "c2_gate_f_run.py"
_RUNNER_SCRIPT_FIELD      = "artifacts/manuscript_completion/runners/c2_gate_f_run.py"
_RUNNER_SHA256            = "e0de9d35a99715bc05c08177b08ad399bb25902fb492ef3487223135b7d3c44a"
_F2_REFERENCE_SHA256      = "71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34"
_F2_DENOM_SHA256          = "b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48"
_SCIENTIFIC_FREEZE_COMMIT = "5733b73b"
_PLACEBO_SEED_ROOT        = 847291653
_CABINET_REFERENCE_MODE   = "corrected_timeweighted_total_p99_local"
_EXPECTED_RATIOS          = ["1.25"]
_EXPECTED_POLICIES        = [
    "full_random", "full_fp", "position_loo", "full_fp_spread",
    "random_spread", "fp_global_placebo", "fp_withincab_placebo",
]
_RUNNER_PATH = REPO_ROOT / "artifacts" / "manuscript_completion" / "runners" / _RUNNER_NAME


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _fail(msg: str):
    print(f"[MERGE FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def _check(cond: bool, msg: str):
    if not cond:
        _fail(msg)


# ── Step 1: Verify runner SHA ─────────────────────────────────────────────────

def verify_runner_sha():
    if not _RUNNER_PATH.exists():
        _fail(f"Runner not found: {_RUNNER_PATH}")
    actual = _sha256(_RUNNER_PATH)
    if actual != _RUNNER_SHA256:
        _fail(
            f"Runner SHA256 mismatch — runner has been modified since freeze.\n"
            f"  Expected: {_RUNNER_SHA256}\n"
            f"  Actual:   {actual}\n"
            f"  Refusing to merge outputs from an unverified runner."
        )
    print(f"[OK] Runner SHA256 verified: {_RUNNER_SHA256[:16]}...")


# ── Step 2: Load and validate per-scenario files ──────────────────────────────

def load_and_validate(file_paths: list[Path], n_first: int, n_dev: int) -> list[dict]:
    """
    Load each per-scenario JSON, validate provenance fields, collect scenario_results.
    Returns sorted list of scenario result dicts and the base metadata dict.
    """
    errors = []
    scenario_results = {}   # scenario_idx -> scenario_result dict
    merged_meta = None      # metadata from first file (for cross-file consistency)

    for path in file_paths:
        if not path.exists():
            errors.append(f"File not found: {path}")
            continue

        try:
            with open(path) as f:
                d = json.load(f)
        except json.JSONDecodeError as e:
            errors.append(f"JSON decode error in {path.name}: {e}")
            continue

        fname = path.name

        # script field (C2 embeds the full relative path, not just the filename)
        if d.get("script") != _RUNNER_SCRIPT_FIELD:
            errors.append(
                f"{fname}: script mismatch\n"
                f"  got:      {d.get('script')}\n"
                f"  expected: {_RUNNER_SCRIPT_FIELD}"
            )

        # frozen input SHAs
        if d.get("f2_reference_sha256") != _F2_REFERENCE_SHA256:
            errors.append(
                f"{fname}: f2_reference_sha256 mismatch\n"
                f"  got:      {d.get('f2_reference_sha256')}\n"
                f"  expected: {_F2_REFERENCE_SHA256}"
            )
        if d.get("f2_replay_denominator_sha256") != _F2_DENOM_SHA256:
            errors.append(
                f"{fname}: f2_replay_denominator_sha256 mismatch\n"
                f"  got:      {d.get('f2_replay_denominator_sha256')}\n"
                f"  expected: {_F2_DENOM_SHA256}"
            )

        # scientific freeze commit
        if d.get("scientific_freeze_commit") != _SCIENTIFIC_FREEZE_COMMIT:
            errors.append(
                f"{fname}: scientific_freeze_commit mismatch\n"
                f"  got:      {d.get('scientific_freeze_commit')}\n"
                f"  expected: {_SCIENTIFIC_FREEZE_COMMIT}"
            )

        # per-scenario placebo seed root
        if d.get("per_scenario_placebo_seed_root") != _PLACEBO_SEED_ROOT:
            errors.append(
                f"{fname}: per_scenario_placebo_seed_root mismatch\n"
                f"  got:      {d.get('per_scenario_placebo_seed_root')}\n"
                f"  expected: {_PLACEBO_SEED_ROOT}"
            )

        # cabinet reference mode
        if d.get("cabinet_reference_mode") != _CABINET_REFERENCE_MODE:
            errors.append(
                f"{fname}: cabinet_reference_mode mismatch — got '{d.get('cabinet_reference_mode')}'"
            )

        # exactly r=1.25
        got_ratios = d.get("gate_f_ratios")
        if got_ratios != _EXPECTED_RATIOS:
            errors.append(
                f"{fname}: gate_f_ratios mismatch\n"
                f"  got:      {got_ratios}\n"
                f"  expected: {_EXPECTED_RATIOS}\n"
                f"  C2 production runs r=1.25 only."
            )

        # exactly 7 authorized C2 policies
        got_policies = d.get("gate_f_policies")
        if got_policies != _EXPECTED_POLICIES:
            errors.append(
                f"{fname}: gate_f_policies mismatch\n"
                f"  got:      {got_policies}\n"
                f"  expected: {_EXPECTED_POLICIES}"
            )

        # no dirty-run contamination
        if d.get("git_tracked_dirty", True):
            errors.append(f"{fname}: git_tracked_dirty is True — dirty-run output rejected")

        # scenario results: must be exactly 1 (N_DEV=1 worker)
        sc_results = d.get("scenario_results", [])
        if len(sc_results) != 1:
            errors.append(
                f"{fname}: expected exactly 1 scenario_result (N_DEV=1 worker), "
                f"got {len(sc_results)}"
            )
            continue

        sc = sc_results[0]
        sc_idx = sc.get("scenario_idx")

        if sc_idx is None:
            errors.append(f"{fname}: scenario_result missing 'scenario_idx'")
            continue

        # range check
        if not (n_first <= sc_idx < n_first + n_dev):
            errors.append(
                f"{fname}: scenario_idx {sc_idx} out of expected range "
                f"[{n_first}, {n_first + n_dev - 1}]"
            )
            continue

        # duplicate check
        if sc_idx in scenario_results:
            errors.append(
                f"Duplicate scenario_idx {sc_idx} — found in both "
                f"{path.name} and a previously loaded file"
            )
            continue

        scenario_results[sc_idx] = sc

        # cross-file consistency: all workers must share the same git commit
        if merged_meta is None:
            merged_meta = {k: v for k, v in d.items() if k != "scenario_results"}
        else:
            if d.get("git_commit_full") != merged_meta.get("git_commit_full"):
                errors.append(
                    f"{fname}: git_commit_full mismatch across workers\n"
                    f"  this file: {d.get('git_commit_full')}\n"
                    f"  first file: {merged_meta.get('git_commit_full')}\n"
                    f"  All workers must run from the same git commit."
                )

    if errors:
        print(f"\n[MERGE FAIL] {len(errors)} validation error(s):", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    # completeness check
    expected = set(range(n_first, n_first + n_dev))
    got = set(scenario_results.keys())
    missing = expected - got
    if missing:
        _fail(
            f"Missing scenarios: {sorted(missing)}\n"
            f"  Refusing to merge incomplete result set. "
            f"Re-run missing workers before merging."
        )

    print(f"[OK] All {n_dev} scenarios validated (sc{n_first}–sc{n_first + n_dev - 1})")
    return sorted(scenario_results.values(), key=lambda s: s["scenario_idx"]), merged_meta


# ── Step 3: Write merged output ───────────────────────────────────────────────

def write_merged(sorted_results: list[dict], base_meta: dict,
                 n_first: int, n_dev: int, out_path: Path):
    """Produce the merged JSON. Schema matches sequential c2_gate_f_run.py output."""

    merged = dict(base_meta)
    merged["n_first"] = n_first
    merged["n_dev"]   = n_dev

    # Merger provenance addendum (does not overwrite any scientific fields)
    merged["parallel_merge"] = {
        "merger_script":    Path(__file__).name,
        "merger_sha256":    _sha256(Path(__file__)),
        "runner_sha256":    _RUNNER_SHA256,
        "n_scenarios":      n_dev,
        "merge_time_utc":   time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    merged["scenario_results"] = sorted_results

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    sha = _sha256(out_path)
    print(f"[OK] Merged output written: {out_path}")
    print(f"     SHA256: {sha}")
    return sha


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    grp = parser.add_mutually_exclusive_group(required=True)
    grp.add_argument("--files",    nargs="+", type=Path, help="Per-scenario JSON files")
    grp.add_argument("--manifest", type=Path, help="Text file listing one JSON path per line")
    parser.add_argument("--n-first", type=int, required=True, help="First scenario index (e.g. 30)")
    parser.add_argument("--n-dev",   type=int, required=True, help="Number of scenarios (e.g. 25)")
    parser.add_argument("--out",     type=Path, required=True, help="Merged output JSON path")
    parser.add_argument("--dry-run", action="store_true", help="Validate only, do not write output")
    args = parser.parse_args()

    if args.manifest:
        lines = args.manifest.read_text().splitlines()
        file_paths = [Path(l.strip()) for l in lines if l.strip()]
    else:
        file_paths = args.files

    if args.out.exists() and not args.dry_run:
        _fail(f"Output already exists: {args.out}\n  Move or remove it before merging.")

    print(f"\nC2 Parallel Merge")
    print(f"  Scenarios: sc{args.n_first}–sc{args.n_first + args.n_dev - 1} ({args.n_dev} total)")
    print(f"  Input files: {len(file_paths)}")
    print(f"  Output: {args.out}")
    if args.dry_run:
        print("  DRY RUN — no output will be written")
    print()

    # Step 1: verify runner
    verify_runner_sha()

    # Step 2: load and validate
    sorted_results, base_meta = load_and_validate(file_paths, args.n_first, args.n_dev)

    # Step 3: write merged output
    if not args.dry_run:
        write_merged(sorted_results, base_meta, args.n_first, args.n_dev, args.out)
        print(f"\nMerge complete. {args.n_dev} scenarios -> {args.out.name}")
    else:
        print("\n[DRY RUN] All validations passed. No output written.")


if __name__ == "__main__":
    main()
