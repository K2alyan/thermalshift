"""
C3 threshold-sensitivity parallel launcher — production run.

Usage:
  THERMALSHIFT_DATA_DIR=<path> \\
  GATE_F_N_FIRST=30 GATE_F_N_DEV=25 GATE_F_N_WORKERS=3 \\
  T_THR_C3=61.875 \\
  python3 artifacts/manuscript_completion/runners/c3_parallel_launcher.py
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

_C3_SCEN_FIRST  = 30
_C3_SCEN_LAST   = 54
_RATIOS_ONLY    = "1.25"
_RATIO_TAG      = "1p25"
_RUN_SUFFIX     = "c3manuscript"
_DEFAULT_WORKERS = 3

_AUTHORIZED_THRESHOLDS = {61.875, 63.625, 66.6625}

# Keys injected only for compat/trace modes — must be absent from C3 workers
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


def _thr_tag(thr: float) -> str:
    return f"t{str(thr).replace('.', 'p')}"


def _scenario_stem(sc_idx: int, thr: float) -> str:
    return f"gate_f_sc{sc_idx}-{sc_idx}_{_RATIO_TAG}_{_thr_tag(thr)}_{_RUN_SUFFIX}"


def _git_head() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        return result.stdout.strip() if result.returncode == 0 else "(unknown)"
    except Exception:
        return "(unknown)"


def _git_clean() -> tuple[bool, str]:
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        if result.returncode != 0:
            return False, f"git status failed: {result.stderr.strip()}"
        dirty = result.stdout.strip()
        if dirty:
            return False, f"working tree has uncommitted tracked changes:\n{dirty}"
        return True, ""
    except Exception as exc:
        return False, f"git status error: {exc}"


def _preflight(n_first: int, n_dev: int, thr: float, n_workers: int) -> None:
    errors = []

    # 1. Runner SHA256
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

    # 2. F2 reference SHA256
    if not _F2_REF_PATH.exists():
        errors.append(f"F2 reference not found: {_F2_REF_PATH}")
    else:
        actual = _sha256_file(_F2_REF_PATH)
        if actual != _F2_REF_SHA:
            errors.append(
                f"F2 reference SHA256 mismatch.\n"
                f"  expected: {_F2_REF_SHA}\n"
                f"  actual:   {actual}"
            )

    # 2b. F2 denominator SHA256
    if not _F2_DENOM_PATH.exists():
        errors.append(f"F2 denominator not found: {_F2_DENOM_PATH}")
    else:
        actual = _sha256_file(_F2_DENOM_PATH)
        if actual != _F2_DENOM_SHA:
            errors.append(
                f"F2 denominator SHA256 mismatch.\n"
                f"  expected: {_F2_DENOM_SHA}\n"
                f"  actual:   {actual}"
            )

    # 3. Git clean
    clean, msg = _git_clean()
    if not clean:
        errors.append(f"Git check failed: {msg}")

    # 4. THERMALSHIFT_DATA_DIR set and contains parquet
    data_dir = os.environ.get("THERMALSHIFT_DATA_DIR", "")
    if not data_dir:
        errors.append("THERMALSHIFT_DATA_DIR is not set")
    else:
        parquet = Path(data_dir) / "frontier-completed-job-info.parquet"
        if not parquet.exists():
            errors.append(
                f"frontier-completed-job-info.parquet not found in THERMALSHIFT_DATA_DIR={data_dir}"
            )

    # 5. No pre-existing per-worker output or checkpoint for any scenario in range
    n_last = n_first + n_dev - 1
    for sc in range(n_first, n_last + 1):
        stem = _scenario_stem(sc, thr)
        out_json = OUT_DIR / f"{stem}.json"
        ckpt     = OUT_DIR / f"{stem}.checkpoint.json"
        log_path = OUT_DIR / f"sc{sc}_c3_{_thr_tag(thr)}_worker.log"
        for p in (out_json, ckpt, log_path):
            if p.exists():
                errors.append(f"Pre-existing file would be overwritten: {p}")

    # 6. No pre-existing merged output
    merged_out = OUT_DIR / f"gate_f_sc{n_first}-{n_last}_{_RATIO_TAG}_{_thr_tag(thr)}_{_RUN_SUFFIX}.json"
    if merged_out.exists():
        errors.append(f"Pre-existing merged output: {merged_out}")

    if errors:
        print("PREFLIGHT FAILED:")
        for e in errors:
            print(f"  - {e}")
        sys.exit(1)


def _print_banner(n_first: int, n_dev: int, thr: float, n_workers: int) -> None:
    n_last    = n_first + n_dev - 1
    scenarios = list(range(n_first, n_last + 1))
    head      = _git_head()
    launch_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    print("=" * 72)
    print(f"C3 PARALLEL LAUNCHER — PRODUCTION ({len(scenarios)} scenarios, T_THR_C3={thr})")
    print("=" * 72)
    print(f"  git HEAD:          {head}")
    print(f"  Runner SHA256:     {_RUNNER_SHA256[:16]}...")
    print(f"  F2 ref SHA256:     {_F2_REF_SHA[:16]}...")
    print(f"  F2 denom SHA256:   {_F2_DENOM_SHA[:16]}...")
    print(f"  Threshold:         {thr}")
    print(f"  Scenarios:         sc{n_first}–sc{n_last} ({len(scenarios)} total)")
    print(f"  N_WORKERS:         {n_workers}")
    print(f"  Ratio (forced):    {_RATIOS_ONLY}")
    print(f"  Output dir:        {OUT_DIR}")
    print(f"  Launch time (UTC): {launch_utc}")
    print("=" * 72)


def _run_worker(sc_idx: int, thr: float) -> dict:
    tag      = _thr_tag(thr)
    log_path = OUT_DIR / f"sc{sc_idx}_c3_{tag}_worker.log"

    env = {k: v for k, v in os.environ.items() if k not in _STRIP_KEYS}
    env["GATE_F_N_FIRST"]    = str(sc_idx)
    env["GATE_F_N_DEV"]      = "1"
    env["GATE_F_RATIOS_ONLY"] = _RATIOS_ONLY
    env["T_THR_C3"]          = str(thr)

    cmd = [sys.executable, str(_RUNNER_PATH)]

    t0 = time.time()
    with open(log_path, "w") as lf:
        proc = subprocess.run(cmd, env=env, stdout=lf, stderr=subprocess.STDOUT)
    elapsed = time.time() - t0

    return {
        "sc_idx":   sc_idx,
        "thr":      thr,
        "returncode": proc.returncode,
        "elapsed":  elapsed,
        "log_path": str(log_path),
    }


def _write_manifest(
    manifest_path: Path,
    n_first: int,
    n_dev: int,
    thr: float,
    results: list[dict],
) -> None:
    lines = []
    for res in sorted(results, key=lambda r: r["sc_idx"]):
        sc   = res["sc_idx"]
        stem = _scenario_stem(sc, thr)
        lines.append(str(OUT_DIR / f"{stem}.json"))
    manifest_path.write_text("\n".join(lines) + "\n")


def run_production(n_first: int, n_dev: int, thr: float, n_workers: int) -> None:
    n_last    = n_first + n_dev - 1
    scenarios = list(range(n_first, n_last + 1))

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    _preflight(n_first, n_dev, thr, n_workers)
    _print_banner(n_first, n_dev, thr, n_workers)

    print(f"\nDispatching {len(scenarios)} workers (max parallel={n_workers})...")

    results   = []
    failed    = []
    completed = 0

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {pool.submit(_run_worker, sc, thr): sc for sc in scenarios}
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
        print("WORKER FAILURES:")
        for res in failed:
            print(f"  sc{res['sc_idx']} rc={res['returncode']}  log: {res['log_path']}")
        sys.exit(1)

    # All workers succeeded — write manifest and invoke merger
    manifest_path = OUT_DIR / f"c3_worker_manifest_sc{n_first}-{n_last}_{_thr_tag(thr)}.txt"
    _write_manifest(manifest_path, n_first, n_dev, thr, results)
    print(f"Manifest written: {manifest_path}")

    merged_out = OUT_DIR / f"gate_f_sc{n_first}-{n_last}_{_RATIO_TAG}_{_thr_tag(thr)}_{_RUN_SUFFIX}.json"

    merger_cmd = [
        sys.executable, str(_MERGER_PATH),
        "--manifest", str(manifest_path),
        "--n-first",  str(n_first),
        "--n-dev",    str(n_dev),
        "--thr",      str(thr),
        "--out",      str(merged_out),
    ]

    print(f"Invoking merger: {' '.join(merger_cmd)}")
    merger_result = subprocess.run(merger_cmd)
    if merger_result.returncode != 0:
        print(f"Merger FAILED (rc={merger_result.returncode})")
        sys.exit(1)

    print(f"\nMerged output: {merged_out}")
    print("C3 parallel run COMPLETE.")


def main() -> None:
    # Validate required environment variables before reading any values
    missing = [k for k in ("GATE_F_N_FIRST", "GATE_F_N_DEV", "T_THR_C3") if not os.environ.get(k)]
    if missing:
        print(f"Missing required env vars: {', '.join(missing)}")
        print(__doc__)
        sys.exit(1)

    try:
        n_first = int(os.environ["GATE_F_N_FIRST"])
    except ValueError:
        print(f"GATE_F_N_FIRST must be an integer, got: {os.environ['GATE_F_N_FIRST']!r}")
        sys.exit(1)

    try:
        n_dev = int(os.environ["GATE_F_N_DEV"])
    except ValueError:
        print(f"GATE_F_N_DEV must be an integer, got: {os.environ['GATE_F_N_DEV']!r}")
        sys.exit(1)

    try:
        thr = float(os.environ["T_THR_C3"])
    except ValueError:
        print(f"T_THR_C3 must be a float, got: {os.environ['T_THR_C3']!r}")
        sys.exit(1)

    if thr not in _AUTHORIZED_THRESHOLDS:
        print(
            f"T_THR_C3={thr} is not an authorized C3 threshold.\n"
            f"Authorized values: {sorted(_AUTHORIZED_THRESHOLDS)}"
        )
        sys.exit(1)

    n_workers = int(os.environ.get("GATE_F_N_WORKERS", str(_DEFAULT_WORKERS)))

    n_last = n_first + n_dev - 1
    if n_first < _C3_SCEN_FIRST or n_last > _C3_SCEN_LAST:
        print(
            f"Scenario range sc{n_first}–sc{n_last} falls outside C3 bounds "
            f"sc{_C3_SCEN_FIRST}–sc{_C3_SCEN_LAST}."
        )
        sys.exit(1)

    run_production(n_first, n_dev, thr, n_workers)


if __name__ == "__main__":
    main()
