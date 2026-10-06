#!/usr/bin/env python3
"""
Step 3 (last part): Compare deterministic rerun outputs against committed results.
Produces task_d_deterministic_reproduction.json.

Run AFTER task_d_rerun_modified.py has completed successfully.
"""

import json
import hashlib
import sys
from pathlib import Path

import numpy as np

REPO_ROOT  = Path(__file__).resolve().parents[2]
REV3_DIR   = REPO_ROOT / "artifacts" / "revision3"
ORIG_DIR   = REV3_DIR / "results"
RERUN_DIR  = REV3_DIR / "task_d_deterministic_rerun" / "results"
OUT_JSON   = REV3_DIR / "task_d_deterministic_reproduction.json"

TOLERANCE = 1e-6
STOP_THRESHOLD = 1e-6

PROVENANCE_FIELDS = {"metadata_source_path", "python_version", "numpy_version", "pandas_version", "script_sha256"}

FILES = [
    "f2_timeweighted_cabinet_reference.json",
    "f3_eventweighted_cabinet_reference.json",
    "task_d_f1_reproduction.json",
    "task_d_validation.json",
    "cabinet_support_audit_v2.json",
    "f1_vs_f2_cabinet_reference_audit.json",
]


def sha256_of_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_provenance(obj, parent_key=None):
    """Recursively set provenance fields to null."""
    if isinstance(obj, dict):
        new = {}
        for k, v in obj.items():
            if k in PROVENANCE_FIELDS:
                new[k] = None
            else:
                new[k] = normalize_provenance(v, k)
        return new
    elif isinstance(obj, list):
        return [normalize_provenance(x) for x in obj]
    return obj


def extract_numerics(obj, prefix=""):
    """Flatten all numeric values from nested JSON into {key: value} dict."""
    result = {}
    if isinstance(obj, dict):
        for k, v in obj.items():
            result.update(extract_numerics(v, f"{prefix}.{k}" if prefix else k))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            result.update(extract_numerics(v, f"{prefix}[{i}]"))
    elif isinstance(obj, (int, float)) and not isinstance(obj, bool):
        result[prefix] = float(obj)
    return result


def compare_json(orig_path: Path, rerun_path: Path):
    with open(orig_path) as f:
        orig = json.load(f)
    with open(rerun_path) as f:
        rerun = json.load(f)

    orig_norm  = normalize_provenance(orig)
    rerun_norm = normalize_provenance(rerun)

    orig_nums  = extract_numerics(orig_norm)
    rerun_nums = extract_numerics(rerun_norm)

    # Find max absolute numeric difference
    common_keys = set(orig_nums.keys()) & set(rerun_nums.keys())
    missing_orig  = set(rerun_nums.keys()) - set(orig_nums.keys())
    missing_rerun = set(orig_nums.keys()) - set(rerun_nums.keys())

    max_diff = 0.0
    max_diff_key = None
    diffs = {}
    for k in common_keys:
        v1 = orig_nums[k]
        v2 = rerun_nums[k]
        if v1 is None and v2 is None:
            continue
        if v1 is None or v2 is None:
            diffs[k] = f"None mismatch: orig={v1} rerun={v2}"
            continue
        d = abs(v1 - v2)
        diffs[k] = d
        if d > max_diff:
            max_diff = d
            max_diff_key = k

    # Compute SHA256 of scientific payload (normalized, excluding provenance block)
    # Scientific payload = everything except top-level "provenance" key
    orig_sci  = {k: v for k, v in orig_norm.items()  if k != "provenance"}
    rerun_sci = {k: v for k, v in rerun_norm.items() if k != "provenance"}

    orig_sha  = hashlib.sha256(json.dumps(orig_sci,  sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    rerun_sha = hashlib.sha256(json.dumps(rerun_sci, sort_keys=True, ensure_ascii=False).encode()).hexdigest()

    return {
        "n_common_numeric_keys": len(common_keys),
        "n_missing_in_orig":  len(missing_orig),
        "n_missing_in_rerun": len(missing_rerun),
        "missing_in_orig":  list(missing_orig)[:20],
        "missing_in_rerun": list(missing_rerun)[:20],
        "max_abs_numeric_diff":     max_diff,
        "max_diff_key":             max_diff_key,
        "sha256_orig_scientific":   orig_sha,
        "sha256_rerun_scientific":  rerun_sha,
        "sha256_match":             orig_sha == rerun_sha,
        "within_tolerance":         max_diff <= TOLERANCE,
    }


print("Comparing deterministic rerun vs committed results ...")
file_results = {}
global_max_diff = 0.0
stop_triggered = False
stop_reason = None

for fname in FILES:
    orig_path  = ORIG_DIR  / fname
    rerun_path = RERUN_DIR / fname

    if not orig_path.exists():
        file_results[fname] = {"error": f"original not found: {orig_path}"}
        continue
    if not rerun_path.exists():
        file_results[fname] = {"error": f"rerun output not found: {rerun_path}"}
        stop_triggered = True
        stop_reason = f"Rerun output missing: {fname}"
        continue

    r = compare_json(orig_path, rerun_path)
    file_results[fname] = r

    if r["max_abs_numeric_diff"] > global_max_diff:
        global_max_diff = r["max_abs_numeric_diff"]

    print(f"  {fname}: max_diff={r['max_abs_numeric_diff']:.2e}  sha_match={r['sha256_match']}")

    if r["max_abs_numeric_diff"] > STOP_THRESHOLD:
        stop_triggered = True
        stop_reason = (f"Max numeric difference {r['max_abs_numeric_diff']:.3e} in {fname} "
                       f"exceeds tolerance {STOP_THRESHOLD:.0e} at key: {r['max_diff_key']}")

overall = "PASS" if (not stop_triggered and global_max_diff <= TOLERANCE) else "FAIL"

out = {
    "audit_date": "2026-10-06",
    "plan_commit": "c674209",
    "rerun_script": "artifacts/revision3/task_d_rerun_modified.py",
    "original_commit_f403998": "script committed at f403998 (diff vs 90dc62f: none for .py file)",
    "tolerance": TOLERANCE,
    "global_max_abs_numeric_diff": global_max_diff,
    "overall": overall,
    "stop_triggered": stop_triggered,
    "stop_reason": stop_reason,
    "files": file_results,
}

with open(OUT_JSON, "w", encoding="utf-8") as f:
    json.dump(out, f, indent=2, ensure_ascii=False)

print(f"\n=== DETERMINISTIC REPRODUCTION: {overall} ===")
print(f"  Global max numeric diff: {global_max_diff:.2e}")
print(f"  Written: {OUT_JSON}")

if stop_triggered:
    print(f"\nSTOP CONDITION: {stop_reason}")
    sys.exit(1)
