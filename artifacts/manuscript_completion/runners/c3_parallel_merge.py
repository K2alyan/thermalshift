import sys
import os
import json
import hashlib
import argparse
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

_RUNNER_NAME         = "c3_gate_f_run.py"
_RUNNER_SCRIPT_FIELD = "artifacts/manuscript_completion/runners/c3_gate_f_run.py"
_RUNNER_SHA256       = "3b4e9825462a5f8b80bc6f76c6938bcf88d460d12f782210474b38573654e91c"
_F2_REFERENCE_SHA256 = "71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34"
_F2_DENOM_SHA256     = "b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48"
_SCIENTIFIC_FREEZE_COMMIT = "5733b73b"
_EXPECTED_RATIOS     = ["1.25"]
_EXPECTED_POLICIES   = ["full_fp", "full_random"]
_CABINET_REFERENCE_MODE = "corrected_timeweighted_total_p99_local"
_AUTHORIZED_THRESHOLDS = {61.875, 63.625, 66.6625}

_RUNNER_PATH = REPO_ROOT / "artifacts" / "manuscript_completion" / "runners" / _RUNNER_NAME


def _fail(msg):
    print(f"[FAIL] {msg}", file=sys.stderr)
    sys.exit(1)


def _sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_runner_sha():
    if not _RUNNER_PATH.exists():
        _fail(f"Runner script not found: {_RUNNER_PATH}")
    actual = _sha256_file(_RUNNER_PATH)
    if actual != _RUNNER_SHA256:
        _fail(
            f"Runner SHA256 mismatch.\n"
            f"  Expected: {_RUNNER_SHA256}\n"
            f"  Actual:   {actual}"
        )
    print(f"[OK] Runner SHA256 verified: {_RUNNER_SHA256[:16]}...")


def load_and_validate(file_paths, n_first, n_dev, thr):
    errors = []
    results = []
    seen_indices = {}
    git_commits = {}

    expected_range = set(range(n_first, n_first + n_dev))

    for fpath in file_paths:
        try:
            with open(fpath, "r") as f:
                data = json.load(f)
        except Exception as e:
            errors.append(f"{fpath}: failed to load JSON: {e}")
            continue

        label = str(fpath)

        if data.get("script") != _RUNNER_SCRIPT_FIELD:
            errors.append(
                f"{label}: script mismatch: got {data.get('script')!r}, "
                f"expected {_RUNNER_SCRIPT_FIELD!r}"
            )

        if data.get("f2_reference_sha256") != _F2_REFERENCE_SHA256:
            errors.append(
                f"{label}: f2_reference_sha256 mismatch: "
                f"got {data.get('f2_reference_sha256')!r}"
            )

        if data.get("f2_replay_denominator_sha256") != _F2_DENOM_SHA256:
            errors.append(
                f"{label}: f2_replay_denominator_sha256 mismatch: "
                f"got {data.get('f2_replay_denominator_sha256')!r}"
            )

        if data.get("scientific_freeze_commit") != _SCIENTIFIC_FREEZE_COMMIT:
            errors.append(
                f"{label}: scientific_freeze_commit mismatch: "
                f"got {data.get('scientific_freeze_commit')!r}, "
                f"expected {_SCIENTIFIC_FREEZE_COMMIT!r}"
            )

        if data.get("cabinet_reference_mode") != _CABINET_REFERENCE_MODE:
            errors.append(
                f"{label}: cabinet_reference_mode mismatch: "
                f"got {data.get('cabinet_reference_mode')!r}, "
                f"expected {_CABINET_REFERENCE_MODE!r}"
            )

        if data.get("gate_f_ratios") != _EXPECTED_RATIOS:
            errors.append(
                f"{label}: gate_f_ratios mismatch: "
                f"got {data.get('gate_f_ratios')!r}, "
                f"expected {_EXPECTED_RATIOS!r}"
            )

        if data.get("gate_f_policies") != _EXPECTED_POLICIES:
            errors.append(
                f"{label}: gate_f_policies mismatch: "
                f"got {data.get('gate_f_policies')!r}, "
                f"expected {_EXPECTED_POLICIES!r}"
            )

        file_thr = data.get("T_THR_C3")
        if file_thr != thr:
            errors.append(
                f"{label}: T_THR_C3 mismatch: "
                f"got {file_thr!r}, expected {thr!r}"
            )

        if data.get("smoke_mode") is not False:
            errors.append(
                f"{label}: smoke_mode must be False; "
                f"got {data.get('smoke_mode')!r}"
            )

        if data.get("git_tracked_dirty") is not False:
            errors.append(
                f"{label}: git_tracked_dirty must be False; "
                f"got {data.get('git_tracked_dirty')!r}"
            )

        scenario_results = data.get("scenario_results", [])
        if len(scenario_results) != 1:
            errors.append(
                f"{label}: expected exactly 1 scenario_result, "
                f"got {len(scenario_results)}"
            )
            continue

        sr = scenario_results[0]
        idx = sr.get("scenario_idx")

        if idx is None:
            errors.append(f"{label}: scenario_result missing scenario_idx")
            continue

        if idx not in expected_range:
            errors.append(
                f"{label}: scenario_idx {idx} out of range "
                f"[{n_first}, {n_first + n_dev - 1}]"
            )

        if idx in seen_indices:
            errors.append(
                f"{label}: duplicate scenario_idx {idx} "
                f"(also in {seen_indices[idx]})"
            )
        else:
            seen_indices[idx] = label

        commit = data.get("git_commit_full")
        if commit:
            git_commits[label] = commit

        results.append((idx, sr, data))

    if errors:
        print("[FAIL] Validation errors:", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        sys.exit(1)

    unique_commits = set(git_commits.values())
    if len(unique_commits) > 1:
        _fail(
            f"Workers have differing git_commit_full values: "
            f"{sorted(unique_commits)}"
        )

    present = set(seen_indices.keys())
    missing = expected_range - present
    if missing:
        _fail(
            f"Missing scenario indices: "
            f"{sorted(missing)}"
        )

    results.sort(key=lambda t: t[0])
    sorted_results = [sr for (_, sr, _) in results]

    first_data = results[0][2]
    base_meta = {k: v for k, v in first_data.items() if k != "scenario_results"}

    return sorted_results, base_meta


def write_merged(out_path, sorted_results, base_meta, n_first, n_dev, file_paths, thr, dry_run):
    merged = dict(base_meta)
    merged["n_first"] = n_first
    merged["n_dev"] = n_dev
    merged["scenario_results"] = sorted_results
    merged["parallel_merge"] = {
        "merger_script": "artifacts/manuscript_completion/runners/c3_parallel_merge.py",
        "n_input_files": len(file_paths),
        "merged_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "T_THR_C3": thr,
    }

    if dry_run:
        print(f"[DRY-RUN] Would write merged output to: {out_path}")
        print(f"[DRY-RUN] scenario_results count: {len(sorted_results)}")
        return

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(merged, f, indent=2)
    print(f"[OK] Merged output written to: {out_path}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="C3 parallel merge: validate and merge per-scenario JSONs."
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        "--files",
        nargs="+",
        metavar="FILE",
        help="Per-scenario JSON files to merge.",
    )
    group.add_argument(
        "--manifest",
        type=Path,
        metavar="MANIFEST",
        help="Path to a manifest file listing per-scenario JSON paths (one per line).",
    )

    parser.add_argument(
        "--n-first",
        type=int,
        required=True,
        metavar="N",
        help="Index of the first scenario (inclusive).",
    )
    parser.add_argument(
        "--n-dev",
        type=int,
        required=True,
        metavar="N",
        help="Number of scenarios expected.",
    )
    parser.add_argument(
        "--thr",
        type=float,
        required=True,
        metavar="THR",
        help="T_THR_C3 value; must be in authorized set.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        metavar="OUT",
        help="Path for merged output JSON.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Validate inputs and print what would be written, without writing.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    if args.thr not in _AUTHORIZED_THRESHOLDS:
        _fail(
            f"--thr {args.thr} is not an authorized threshold. "
            f"Authorized: {sorted(_AUTHORIZED_THRESHOLDS)}"
        )

    if args.files:
        file_paths = [Path(p) for p in args.files]
    else:
        manifest_path = args.manifest
        if not manifest_path.exists():
            _fail(f"Manifest file not found: {manifest_path}")
        with open(manifest_path, "r") as f:
            lines = [l.strip() for l in f if l.strip()]
        file_paths = [Path(l) for l in lines]

    print("C3 Parallel Merge")
    print(f"  Threshold: T_THR_C3={args.thr}")
    print(f"  Scenarios: sc{args.n_first}-sc{args.n_first + args.n_dev - 1} ({args.n_dev} total)")
    print(f"  Input files: {len(file_paths)}")
    print(f"  Output: {args.out}")

    verify_runner_sha()

    sorted_results, base_meta = load_and_validate(
        file_paths, args.n_first, args.n_dev, args.thr
    )

    write_merged(
        args.out,
        sorted_results,
        base_meta,
        args.n_first,
        args.n_dev,
        file_paths,
        args.thr,
        args.dry_run,
    )


if __name__ == "__main__":
    main()
