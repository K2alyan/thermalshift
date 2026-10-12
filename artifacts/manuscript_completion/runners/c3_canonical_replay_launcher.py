"""
c3_canonical_replay_launcher.py — P90 provenance-repair canonical replay.

Purpose: produce gate_f_sc30-54_1p25_t61p875_c3canonical.json under a single
clean git commit, replacing the prior mixed-commit P90 artifact for submission.

This is NOT a new experiment. Seeds, thresholds, ratio, policies, runner SHA,
reference files are identical to the original P90 run. The only change is that
all 25 workers run under one git HEAD with no commits in flight.

Usage:
  THERMALSHIFT_DATA_DIR=<path> [GATE_F_N_WORKERS=3] \\
  python3 artifacts/manuscript_completion/runners/c3_canonical_replay_launcher.py

Strict requirements:
  - git status --porcelain --untracked-files=all must be empty at launch time
  - gate_f_sc30-54_1p25_t61p875_c3canonical.json must not already exist
  - merger is called WITHOUT --allow-commit-mismatch
  - all 25 workers must share one identical git_commit_full (enforced by merger)
"""

import hashlib
import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNERS   = Path(__file__).parent
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

_RUNNER_NAME   = "c3_gate_f_run.py"
_RUNNER_PATH   = RUNNERS / _RUNNER_NAME
_RUNNER_SHA256 = "3b4e9825462a5f8b80bc6f76c6938bcf88d460d12f782210474b38573654e91c"

REV3_DIR       = REPO_ROOT / "artifacts" / "revision3"
_F2_REF_PATH   = REV3_DIR / "f2_local_scheduling_reference.json"
_F2_REF_SHA    = "71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34"
_F2_DENOM_PATH = REV3_DIR / "f2_replay_denominator.json"
_F2_DENOM_SHA  = "b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48"

_MERGER_PATH   = RUNNERS / "c3_parallel_merge.py"

_N_FIRST    = 30
_N_DEV      = 25
_THR        = 61.875
_RATIO      = "1.25"
_RATIO_TAG  = "1p25"
_THR_TAG    = "t61p875"

# Workers write this suffix (runner-controlled, cannot be overridden)
_WORKER_SUFFIX   = "c3manuscript"
# Canonical merged output uses this suffix to distinguish from original
_CANONICAL_SUFFIX = "c3canonical"

_STRIP_KEYS = {
    "GATE_F_TRACE_R1",
    "GATE_F_COMPAT_SEED",
    "GATE_F_COMPAT_BETA",
    "GATE_F_COMPAT_N_SCEN",
    "GATE_F_RESTRICT_POLICIES",
    "GATE_F_C3_SMOKE",
}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head() -> str:
    try:
        r = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        return r.stdout.strip() if r.returncode == 0 else "(unknown)"
    except Exception:
        return "(unknown)"


def _git_status_porcelain_all() -> str:
    r = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        capture_output=True, text=True, cwd=REPO_ROOT
    )
    return r.stdout.strip() if r.returncode == 0 else "(error)"


def _scenario_stem(sc: int) -> str:
    return f"gate_f_sc{sc}-{sc}_{_RATIO_TAG}_{_THR_TAG}_{_WORKER_SUFFIX}"


def _preflight(n_workers: int) -> None:
    errors = []

    # 1. Runner SHA
    if not _RUNNER_PATH.exists():
        errors.append(f"Runner not found: {_RUNNER_PATH}")
    else:
        actual = _sha256_file(_RUNNER_PATH)
        if actual != _RUNNER_SHA256:
            errors.append(
                f"Runner SHA256 mismatch.\n"
                f"  expected: {_RUNNER_SHA256}\n"
                f"  actual:   {actual}"
            )

    # 2. F2 reference
    if not _F2_REF_PATH.exists():
        errors.append(f"F2 reference not found: {_F2_REF_PATH}")
    else:
        actual = _sha256_file(_F2_REF_PATH)
        if actual != _F2_REF_SHA:
            errors.append(f"F2 reference SHA256 mismatch: {actual}")

    # 3. F2 denominator
    if not _F2_DENOM_PATH.exists():
        errors.append(f"F2 denominator not found: {_F2_DENOM_PATH}")
    else:
        actual = _sha256_file(_F2_DENOM_PATH)
        if actual != _F2_DENOM_SHA:
            errors.append(f"F2 denominator SHA256 mismatch: {actual}")

    # 4. Git clean: --untracked-files=all must be empty
    dirty = _git_status_porcelain_all()
    if dirty:
        errors.append(
            f"git status --porcelain --untracked-files=all is not empty.\n"
            f"  Commit or stash all changes before canonical replay.\n"
            f"  Output:\n{dirty}"
        )

    # 5. Canonical merged output must not already exist
    canonical_out = OUT_DIR / f"gate_f_sc{_N_FIRST}-{_N_FIRST + _N_DEV - 1}_{_RATIO_TAG}_{_THR_TAG}_{_CANONICAL_SUFFIX}.json"
    if canonical_out.exists():
        errors.append(f"Canonical output already exists: {canonical_out}")

    # 6. THERMALSHIFT_DATA_DIR
    data_dir = os.environ.get("THERMALSHIFT_DATA_DIR", "")
    if not data_dir:
        errors.append("THERMALSHIFT_DATA_DIR is not set")
    else:
        parquet = Path(data_dir) / "frontier-completed-job-info.parquet"
        if not parquet.exists():
            errors.append(f"frontier-completed-job-info.parquet not found in {data_dir}")

    if errors:
        print("CANONICAL REPLAY PREFLIGHT FAILED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


def _run_worker(sc_idx: int) -> dict:
    log_path = OUT_DIR / f"sc{sc_idx}_c3canonical_{_THR_TAG}_worker.log"

    env = {k: v for k, v in os.environ.items() if k not in _STRIP_KEYS}
    env["GATE_F_N_FIRST"]     = str(sc_idx)
    env["GATE_F_N_DEV"]       = "1"
    env["GATE_F_RATIOS_ONLY"] = _RATIO
    env["T_THR_C3"]           = str(_THR)

    cmd = [sys.executable, str(_RUNNER_PATH)]

    t0 = time.time()
    with open(log_path, "w") as lf:
        proc = subprocess.run(cmd, env=env, stdout=lf, stderr=subprocess.STDOUT)
    elapsed = time.time() - t0

    return {
        "sc_idx":     sc_idx,
        "returncode": proc.returncode,
        "elapsed":    elapsed,
        "log_path":   str(log_path),
    }


def main() -> None:
    n_workers = int(os.environ.get("GATE_F_N_WORKERS", "3"))
    n_last    = _N_FIRST + _N_DEV - 1
    scenarios = list(range(_N_FIRST, n_last + 1))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _preflight(n_workers)

    head = _git_head()
    launch_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    print("=" * 72)
    print(f"C3 CANONICAL REPLAY LAUNCHER — P90 PROVENANCE REPAIR")
    print(f"  ({len(scenarios)} scenarios, T_THR_C3={_THR})")
    print("=" * 72)
    print(f"  git HEAD (single commit for all workers): {head}")
    print(f"  Runner SHA256:     {_RUNNER_SHA256[:16]}...")
    print(f"  F2 ref SHA256:     {_F2_REF_SHA[:16]}...")
    print(f"  F2 denom SHA256:   {_F2_DENOM_SHA[:16]}...")
    print(f"  Threshold:         {_THR}")
    print(f"  Scenarios:         sc{_N_FIRST}-sc{n_last} ({len(scenarios)} total)")
    print(f"  N_WORKERS:         {n_workers}")
    print(f"  Ratio (forced):    {_RATIO}")
    print(f"  Output (canonical): gate_f_sc{_N_FIRST}-{n_last}_{_RATIO_TAG}_{_THR_TAG}_{_CANONICAL_SUFFIX}.json")
    print(f"  Launch time (UTC): {launch_utc}")
    print("=" * 72)
    print()
    print("NOTE: This is a provenance-repair replay, not a new experiment.")
    print("      Seeds, thresholds, runner SHA, references are unchanged.")
    print("      Merger will be called WITHOUT --allow-commit-mismatch.")
    print()

    print(f"Dispatching {len(scenarios)} workers (max parallel={n_workers})...")

    results = []
    failed  = []
    completed = 0

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_run_worker, sc): sc for sc in scenarios}
        for fut in as_completed(futures):
            res = fut.result()
            results.append(res)
            completed += 1
            sc      = res["sc_idx"]
            rc      = res["returncode"]
            elapsed = res["elapsed"]
            status  = "OK" if rc == 0 else "FAILED"
            print(
                f"  [{completed}/{len(scenarios)}] sc{sc} {status}"
                f" (rc={rc}, {elapsed:.1f}s)"
                + (f"  log: {res['log_path']}" if rc != 0 else "")
            )
            if rc != 0:
                failed.append(res)

    print()

    if failed:
        print("WORKER FAILURES — canonical replay aborted:")
        for res in failed:
            print(f"  sc{res['sc_idx']} rc={res['returncode']}  log: {res['log_path']}")
        sys.exit(1)

    # Build manifest listing per-scenario c3manuscript files (runner-controlled names)
    manifest_path = OUT_DIR / f"c3_canonical_manifest_sc{_N_FIRST}-{n_last}_{_THR_TAG}.txt"
    lines = []
    for res in sorted(results, key=lambda r: r["sc_idx"]):
        sc   = res["sc_idx"]
        stem = _scenario_stem(sc)
        lines.append(str(OUT_DIR / f"{stem}.json"))
    manifest_path.write_text("\n".join(lines) + "\n")
    print(f"Manifest written: {manifest_path}")

    # Canonical merged output path
    canonical_out = OUT_DIR / f"gate_f_sc{_N_FIRST}-{n_last}_{_RATIO_TAG}_{_THR_TAG}_{_CANONICAL_SUFFIX}.json"

    merger_cmd = [
        sys.executable, str(_MERGER_PATH),
        "--manifest", str(manifest_path),
        "--n-first",  str(_N_FIRST),
        "--n-dev",    str(_N_DEV),
        "--thr",      str(_THR),
        "--out",      str(canonical_out),
        # NO --allow-commit-mismatch
    ]

    print(f"Invoking strict merger (no commit-mismatch exception):")
    print(f"  {' '.join(merger_cmd)}")
    merger_result = subprocess.run(merger_cmd)
    if merger_result.returncode != 0:
        print(f"Merger FAILED (rc={merger_result.returncode})")
        print("All 25 workers must share a single git_commit_full for canonical replay.")
        sys.exit(1)

    print(f"\nCanonical output: {canonical_out}")
    print("C3 canonical replay COMPLETE.")


if __name__ == "__main__":
    main()
