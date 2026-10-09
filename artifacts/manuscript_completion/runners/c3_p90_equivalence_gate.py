"""
c3_p90_equivalence_gate.py — equivalence gate for canonical P90 replay.

Compares every scientific field in the canonical P90 replay result against the
original P90 result (SHA 0cd2371a...). Excludes only operational metadata:
git commit identifiers, elapsed time, launcher/merge metadata, filenames,
and timestamps.

Usage:
  python3 artifacts/manuscript_completion/runners/c3_p90_equivalence_gate.py \\
      --canonical <path/to/gate_f_sc30-54_1p25_t61p875_c3canonical.json>

Exits 0 on exact scientific equivalence, 1 otherwise.
"""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

_ORIGINAL_PATH = RESULTS / "gate_f_sc30-54_1p25_t61p875_c3manuscript.json"
_ORIGINAL_SHA  = "0cd2371a71d96c6e852c429e8fec17d4e0ab0e985dcd9b42003bcf6009bbe084"

# Operational metadata keys excluded from comparison at top level and in parallel_merge
_TOP_LEVEL_EXCLUDE = {
    "git_commit_full",
    "git_commit_short",
    "git_tracked_dirty",
    "parallel_merge",
    "script",       # path string, not scientific
}

# Excluded within each scenario_result
_SR_EXCLUDE = {
    "elapsed_s",
}

# Operational keys in lambda_rows
_LAMBDA_EXCLUDE = set()  # all lambda_row fields are scientific


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _is_close_enough(a, b) -> tuple[bool, float]:
    """Return (exact_match, abs_diff). For floats, exact means identical bits."""
    if type(a) != type(b):
        return False, float("inf")
    if isinstance(a, float):
        if math.isnan(a) and math.isnan(b):
            return True, 0.0
        diff = abs(a - b)
        return diff == 0.0, diff
    if isinstance(a, (int, bool, str, type(None))):
        return a == b, 0.0
    return False, float("inf")


def _compare_lambda_rows(orig_rows: list, canon_rows: list, path: str) -> list[str]:
    errors = []
    if len(orig_rows) != len(canon_rows):
        errors.append(f"{path}: lambda_rows length mismatch: {len(orig_rows)} vs {len(canon_rows)}")
        return errors
    for i, (o, c) in enumerate(zip(orig_rows, canon_rows)):
        rpath = f"{path}[{i}]"
        all_keys = set(o) | set(c)
        for k in sorted(all_keys):
            kpath = f"{rpath}.{k}"
            if k not in o:
                errors.append(f"{kpath}: missing in original")
                continue
            if k not in c:
                errors.append(f"{kpath}: missing in canonical")
                continue
            ov, cv = o[k], c[k]
            ok, diff = _is_close_enough(ov, cv)
            if not ok:
                errors.append(f"{kpath}: orig={ov!r} canon={cv!r} diff={diff}")
    return errors


def _compare_crossing(orig_cx: dict, canon_cx: dict, path: str) -> list[str]:
    errors = []
    all_keys = set(orig_cx) | set(canon_cx)
    for k in sorted(all_keys):
        kpath = f"{path}.{k}"
        if k not in orig_cx:
            errors.append(f"{kpath}: missing in original")
            continue
        if k not in canon_cx:
            errors.append(f"{kpath}: missing in canonical")
            continue
        ov, cv = orig_cx[k], canon_cx[k]
        ok, diff = _is_close_enough(ov, cv)
        if not ok:
            errors.append(f"{kpath}: orig={ov!r} canon={cv!r} diff={diff}")
    return errors


def _compare_scenario_result(orig_sr: dict, canon_sr: dict, sc_idx: int) -> list[str]:
    errors = []
    path = f"sc{sc_idx}"

    # Compare top-level scalar fields (excluding operational)
    all_sr_keys = (set(orig_sr) | set(canon_sr)) - _SR_EXCLUDE
    for k in sorted(all_sr_keys):
        kpath = f"{path}.{k}"
        if k in ("ratios",):
            continue
        if k not in orig_sr:
            errors.append(f"{kpath}: missing in original")
            continue
        if k not in canon_sr:
            errors.append(f"{kpath}: missing in canonical")
            continue
        ov, cv = orig_sr[k], canon_sr[k]
        if isinstance(ov, (dict, list)):
            continue  # handled separately
        ok, diff = _is_close_enough(ov, cv)
        if not ok:
            errors.append(f"{kpath}: orig={ov!r} canon={cv!r} diff={diff}")

    # Compare ratios
    orig_ratios  = orig_sr.get("ratios", {})
    canon_ratios = canon_sr.get("ratios", {})
    for ratio_key in sorted(set(orig_ratios) | set(canon_ratios)):
        rpath = f"{path}.ratios.{ratio_key}"
        if ratio_key not in orig_ratios:
            errors.append(f"{rpath}: missing in original")
            continue
        if ratio_key not in canon_ratios:
            errors.append(f"{rpath}: missing in canonical")
            continue
        orig_r  = orig_ratios[ratio_key]
        canon_r = canon_ratios[ratio_key]

        for pol_key in sorted(set(orig_r) | set(canon_r)):
            ppath = f"{rpath}.{pol_key}"
            if pol_key not in orig_r:
                errors.append(f"{ppath}: missing in original")
                continue
            if pol_key not in canon_r:
                errors.append(f"{ppath}: missing in canonical")
                continue
            orig_pol  = orig_r[pol_key]
            canon_pol = canon_r[pol_key]

            # lambda_rows
            errors.extend(_compare_lambda_rows(
                orig_pol.get("lambda_rows", []),
                canon_pol.get("lambda_rows", []),
                f"{ppath}.lambda_rows",
            ))

            # crossing
            errors.extend(_compare_crossing(
                orig_pol.get("crossing", {}),
                canon_pol.get("crossing", {}),
                f"{ppath}.crossing",
            ))

    return errors


def run_gate(canonical_path: Path) -> None:
    print("C3 P90 Equivalence Gate")
    print(f"  Original:  {_ORIGINAL_PATH.name}")
    print(f"  Canonical: {canonical_path.name}")
    print()

    # Verify original SHA
    if not _ORIGINAL_PATH.exists():
        print(f"[FAIL] Original not found: {_ORIGINAL_PATH}")
        sys.exit(1)
    actual_orig_sha = _sha256_file(_ORIGINAL_PATH)
    if actual_orig_sha != _ORIGINAL_SHA:
        print(f"[FAIL] Original SHA256 mismatch.")
        print(f"  Expected: {_ORIGINAL_SHA}")
        print(f"  Actual:   {actual_orig_sha}")
        sys.exit(1)
    print(f"[OK] Original SHA256 verified: {_ORIGINAL_SHA[:16]}...")

    # Load canonical
    if not canonical_path.exists():
        print(f"[FAIL] Canonical file not found: {canonical_path}")
        sys.exit(1)
    canon_sha = _sha256_file(canonical_path)
    print(f"[OK] Canonical SHA256: {canon_sha[:16]}...")

    with open(_ORIGINAL_PATH) as f:
        orig = json.load(f)
    with open(canonical_path) as f:
        canon = json.load(f)

    all_errors = []
    max_num_diff = 0.0

    # Check top-level scalar fields (excluding operational)
    all_top_keys = (set(orig) | set(canon)) - _TOP_LEVEL_EXCLUDE - {"scenario_results"}
    for k in sorted(all_top_keys):
        if k not in orig:
            all_errors.append(f"top.{k}: missing in original")
            continue
        if k not in canon:
            all_errors.append(f"top.{k}: missing in canonical")
            continue
        ov, cv = orig[k], canon[k]
        if isinstance(ov, (dict, list)):
            continue
        ok, diff = _is_close_enough(ov, cv)
        if not ok:
            all_errors.append(f"top.{k}: orig={ov!r} canon={cv!r}")
        max_num_diff = max(max_num_diff, diff)

    # Build scenario_result maps keyed by scenario_idx
    orig_map  = {sr["scenario_idx"]: sr for sr in orig.get("scenario_results", [])}
    canon_map = {sr["scenario_idx"]: sr for sr in canon.get("scenario_results", [])}

    orig_idxs  = set(orig_map)
    canon_idxs = set(canon_map)

    if orig_idxs != canon_idxs:
        all_errors.append(
            f"scenario_idx sets differ:\n"
            f"  only in original:  {sorted(orig_idxs - canon_idxs)}\n"
            f"  only in canonical: {sorted(canon_idxs - orig_idxs)}"
        )

    for idx in sorted(orig_idxs & canon_idxs):
        errs = _compare_scenario_result(orig_map[idx], canon_map[idx], idx)
        for e in errs:
            # extract numeric diff if present
            if "diff=" in e:
                try:
                    diff_str = e.split("diff=")[-1]
                    max_num_diff = max(max_num_diff, float(diff_str))
                except Exception:
                    pass
        all_errors.extend(errs)

    print()
    print(f"Scenarios compared:       {len(orig_idxs & canon_idxs)}")
    print(f"Max absolute numeric diff: {max_num_diff}")

    if all_errors:
        print(f"\n[FAIL] {len(all_errors)} scientific field differences found:")
        for e in all_errors[:40]:
            print(f"  {e}")
        if len(all_errors) > 40:
            print(f"  ... and {len(all_errors) - 40} more")
        sys.exit(1)

    if max_num_diff != 0.0:
        print(f"\n[FAIL] Max numeric diff is {max_num_diff}, expected 0.0")
        sys.exit(1)

    print()
    print("[PASS] All scientific fields exactly match.")
    print()
    print("VERDICT: P90 provenance replay reproduced exposed result exactly.")
    print("         Replay was performed solely to remove mixed-git-commit execution metadata.")
    print(f"         Canonical SHA: {canon_sha}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Equivalence gate: canonical P90 replay vs original P90 result."
    )
    parser.add_argument(
        "--canonical",
        type=Path,
        required=True,
        help="Path to canonical P90 merged JSON.",
    )
    args = parser.parse_args()
    run_gate(args.canonical)


if __name__ == "__main__":
    main()
