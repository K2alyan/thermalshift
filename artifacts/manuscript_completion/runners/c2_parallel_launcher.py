#!/usr/bin/env python3
"""
c2_parallel_launcher.py — Governed parallel launcher for C2 (sc30–sc54)

Spawns one c2_gate_f_run.py subprocess per scenario with GATE_F_N_FIRST=i
GATE_F_N_DEV=1 GATE_F_RATIOS_ONLY=1.25, running up to N_WORKERS simultaneously.
After all 25 workers succeed, delegates to c2_parallel_merge.py.

Governance:
  - Verifies c2_gate_f_run.py SHA (frozen: e0de9d35...)
  - Verifies corrected-reference input SHAs (f2_local_scheduling_reference.json,
    f2_replay_denominator.json)
  - Requires git clean tracked-file state
  - Requires explicit GATE_F_N_FIRST and GATE_F_N_DEV (fails closed otherwise)
  - Checks no pre-existing output or checkpoint for any scenario in range
  - Each worker: isolated stdout/stderr log, isolated checkpoint, isolated JSON
  - Forces GATE_F_RATIOS_ONLY=1.25 on every worker

Usage:
  THERMALSHIFT_DATA_DIR=<path> \\
  GATE_F_N_FIRST=30 GATE_F_N_DEV=25 GATE_F_N_WORKERS=3 \\
  python3 artifacts/manuscript_completion/runners/c2_parallel_launcher.py

Environment variables:
  GATE_F_N_FIRST       Required. First scenario index (30 for production).
  GATE_F_N_DEV         Required. Number of scenarios (25 for production).
  GATE_F_N_WORKERS     Optional. Concurrent workers. Default: 3.
  THERMALSHIFT_DATA_DIR Required.
"""

import sys, os, json, hashlib, subprocess, time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNERS   = Path(__file__).parent
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

# ── Frozen constants ──────────────────────────────────────────────────────────
_RUNNER_NAME   = "c2_gate_f_run.py"
_RUNNER_PATH   = RUNNERS / _RUNNER_NAME
_RUNNER_SHA256 = "e0de9d35a99715bc05c08177b08ad399bb25902fb492ef3487223135b7d3c44a"

REV3_DIR        = REPO_ROOT / "artifacts" / "revision3"
_F2_REF_PATH    = REV3_DIR / "f2_local_scheduling_reference.json"
_F2_REF_SHA     = "71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34"
_F2_DENOM_PATH  = REV3_DIR / "f2_replay_denominator.json"
_F2_DENOM_SHA   = "b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48"

_MERGER_PATH    = RUNNERS / "c2_parallel_merge.py"

_C2_SCEN_FIRST  = 30
_C2_SCEN_LAST   = 54
_RATIOS_ONLY    = "1.25"   # enforced on every worker
_RATIO_TAG      = "1p25"   # matches c2_gate_f_run.py filename construction
_RUN_SUFFIX     = "c2manuscript"
_DEFAULT_WORKERS = 3       # authorized by resource gate (5-worker gate failed)


# ── Utilities ─────────────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "log", "--oneline", "-1"], cwd=str(REPO_ROOT), text=True
        ).strip()
    except Exception:
        return "unknown"


def _git_is_clean() -> tuple[bool, str]:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=str(REPO_ROOT), text=True
        ).strip()
        return (not out), out
    except Exception:
        return False, "git status failed"


def _scenario_stem(sc_idx: int) -> str:
    """Expected output file stem for a single-scenario worker (no extension)."""
    return f"gate_f_sc{sc_idx}-{sc_idx}_{_RATIO_TAG}_{_RUN_SUFFIX}"


def _find_worker_output(sc_idx: int) -> Path | None:
    p = OUT_DIR / f"{_scenario_stem(sc_idx)}.json"
    return p if p.exists() else None


# ── Pre-flight ────────────────────────────────────────────────────────────────

def preflight(scenarios: list[int], n_workers: int):
    errors = []

    # 1. Runner SHA
    if not _RUNNER_PATH.exists():
        errors.append(f"Runner not found: {_RUNNER_PATH}")
    else:
        actual = _sha256(_RUNNER_PATH)
        if actual != _RUNNER_SHA256:
            errors.append(
                f"Runner SHA256 mismatch:\n"
                f"  expected: {_RUNNER_SHA256}\n  actual:   {actual}"
            )

    # 2. Corrected-reference SHAs
    for path, expected_sha, label in [
        (_F2_REF_PATH,   _F2_REF_SHA,   "f2_local_scheduling_reference.json"),
        (_F2_DENOM_PATH, _F2_DENOM_SHA, "f2_replay_denominator.json"),
    ]:
        if not path.exists():
            errors.append(f"{label} not found: {path}")
        else:
            actual = _sha256(path)
            if actual != expected_sha:
                errors.append(
                    f"{label} SHA256 mismatch:\n"
                    f"  expected: {expected_sha}\n  actual:   {actual}"
                )

    # 3. Git clean (tracked files only)
    clean, dirty = _git_is_clean()
    if not clean:
        errors.append(
            f"Working tree has uncommitted tracked changes:\n{dirty}\n"
            f"  Commit or stash before running."
        )

    # 4. THERMALSHIFT_DATA_DIR
    data_dir = os.environ.get("THERMALSHIFT_DATA_DIR", "")
    if not data_dir:
        errors.append("THERMALSHIFT_DATA_DIR is not set.")
    else:
        parquet = Path(data_dir) / "frontier-completed-job-info.parquet"
        if not parquet.exists():
            errors.append(f"frontier-completed-job-info.parquet not found in THERMALSHIFT_DATA_DIR")

    # 5. No pre-existing outputs or checkpoints
    n_first = scenarios[0]
    n_dev   = len(scenarios)
    for sc in scenarios:
        stem = _scenario_stem(sc)
        out_p  = OUT_DIR / f"{stem}.json"
        ckpt_p = OUT_DIR / f"{stem}_checkpoint.json"
        if out_p.exists():
            errors.append(f"Pre-existing worker output: {out_p.name}")
        if ckpt_p.exists():
            errors.append(f"Pre-existing checkpoint: {ckpt_p.name}")

    merged = OUT_DIR / f"gate_f_sc{n_first}-{n_first + n_dev - 1}_{_RATIO_TAG}_{_RUN_SUFFIX}.json"
    if merged.exists():
        errors.append(f"Merged output already exists: {merged.name}")

    if errors:
        print("\nPREFLIGHT ERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    print("=" * 70)
    print(f"C2 PARALLEL LAUNCHER — PRODUCTION ({len(scenarios)} scenarios)")
    print("=" * 70)
    print(f"  git HEAD:          {_git_head()}")
    print(f"  Runner SHA256:     {_RUNNER_SHA256[:16]}...")
    print(f"  F2 ref SHA256:     {_F2_REF_SHA[:16]}...")
    print(f"  F2 denom SHA256:   {_F2_DENOM_SHA[:16]}...")
    print(f"  Scenarios:         sc{scenarios[0]}–sc{scenarios[-1]}  ({len(scenarios)} total)")
    print(f"  N_WORKERS:         {n_workers}")
    print(f"  Ratio:             {_RATIOS_ONLY} (forced on all workers)")
    print(f"  Output dir:        {OUT_DIR}")
    print(f"  Launch time:       {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print("=" * 70)


# ── Worker execution ──────────────────────────────────────────────────────────

def _run_worker(sc_idx: int, log_path: Path) -> dict:
    """Run c2_gate_f_run.py for one scenario (r=1.25 only)."""
    env = os.environ.copy()
    env["GATE_F_N_FIRST"]     = str(sc_idx)
    env["GATE_F_N_DEV"]       = "1"
    env["GATE_F_RATIOS_ONLY"] = _RATIOS_ONLY
    # Remove C1 / compat env vars that must not bleed into C2
    for k in ("GATE_F_TRACE_R1", "GATE_F_COMPAT_SEED", "GATE_F_COMPAT_BETA",
              "GATE_F_COMPAT_N_SCEN", "GATE_F_RESTRICT_POLICIES"):
        env.pop(k, None)

    t0 = time.time()
    with open(log_path, "w", encoding="utf-8") as logf:
        proc = subprocess.run(
            [sys.executable, str(_RUNNER_PATH)],
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            cwd=str(REPO_ROOT),
        )
    elapsed = time.time() - t0

    out_path = _find_worker_output(sc_idx)
    return {
        "scenario_idx": sc_idx,
        "returncode":   proc.returncode,
        "elapsed_s":    elapsed,
        "log_path":     str(log_path),
        "out_path":     str(out_path) if out_path else None,
        "success":      proc.returncode == 0 and out_path is not None,
    }


# ── Production run ────────────────────────────────────────────────────────────

def run_production(scenarios: list[int], n_workers: int) -> list[Path]:
    worker_jsons = []
    failed = []
    t0 = time.time()

    print(f"\nDispatching {len(scenarios)} scenarios ({n_workers} workers)...\n")

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(
                _run_worker,
                sc,
                OUT_DIR / f"sc{sc}_c2worker.log"
            ): sc
            for sc in scenarios
        }
        for fut in as_completed(futures):
            sc = futures[fut]
            r  = fut.result()
            elapsed_min = r["elapsed_s"] / 60
            done_count  = len(worker_jsons) + len(failed) + 1
            wall_min    = (time.time() - t0) / 60

            if r["success"]:
                worker_jsons.append(Path(r["out_path"]))
                print(
                    f"  [sc{sc}] DONE  {elapsed_min:.1f}min  "
                    f"({done_count}/{len(scenarios)}, wall={wall_min:.1f}min)",
                    flush=True
                )
            else:
                failed.append(sc)
                print(
                    f"  [sc{sc}] FAILED  rc={r['returncode']}  "
                    f"{elapsed_min:.1f}min  log: {OUT_DIR / f'sc{sc}_c2worker.log'}",
                    flush=True
                )

    if failed:
        print(f"\n[ABORT] {len(failed)} scenario(s) failed: {sorted(failed)}", file=sys.stderr)
        print("Fix failures and re-run failed scenarios. Do not merge partial results.", file=sys.stderr)
        sys.exit(1)

    return worker_jsons


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    n_first_env = os.environ.get("GATE_F_N_FIRST", "")
    n_dev_env   = os.environ.get("GATE_F_N_DEV", "")
    if not n_first_env or not n_dev_env:
        sys.exit(
            "ERROR: GATE_F_N_FIRST and GATE_F_N_DEV must be set explicitly.\n"
            "  Production C2: GATE_F_N_FIRST=30 GATE_F_N_DEV=25 GATE_F_N_WORKERS=3"
        )

    n_first   = int(n_first_env)
    n_dev     = int(n_dev_env)
    n_workers = int(os.environ.get("GATE_F_N_WORKERS", str(_DEFAULT_WORKERS)))

    if n_first < _C2_SCEN_FIRST or (n_first + n_dev - 1) > _C2_SCEN_LAST:
        sys.exit(
            f"ERROR: Scenario range sc{n_first}–sc{n_first+n_dev-1} is outside "
            f"the authorized C2 held-out range sc{_C2_SCEN_FIRST}–sc{_C2_SCEN_LAST}."
        )

    scenarios = list(range(n_first, n_first + n_dev))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    preflight(scenarios, n_workers)
    worker_jsons = run_production(scenarios, n_workers)

    # Write manifest
    manifest_path = OUT_DIR / f"c2_worker_manifest_sc{n_first}-{n_first+n_dev-1}.txt"
    manifest_path.write_text("\n".join(str(p) for p in sorted(worker_jsons)), encoding="utf-8")
    print(f"\nManifest written: {manifest_path}")

    # Invoke merger
    merged_out = OUT_DIR / f"gate_f_sc{n_first}-{n_first+n_dev-1}_{_RATIO_TAG}_{_RUN_SUFFIX}.json"
    merger_cmd = [
        sys.executable, str(_MERGER_PATH),
        "--manifest", str(manifest_path),
        "--n-first",  str(n_first),
        "--n-dev",    str(n_dev),
        "--out",      str(merged_out),
    ]
    print(f"\nInvoking merger: c2_parallel_merge.py")
    ret = subprocess.run(merger_cmd, cwd=str(REPO_ROOT))
    if ret.returncode != 0:
        sys.exit(f"[ABORT] Merger failed with exit code {ret.returncode}.")

    print(f"\nC2 PARALLEL RUN COMPLETE")
    print(f"  Output: {merged_out}")


if __name__ == "__main__":
    main()
