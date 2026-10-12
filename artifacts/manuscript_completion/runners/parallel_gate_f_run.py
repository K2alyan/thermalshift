#!/usr/bin/env python3
"""
parallel_gate_f_run.py — Parallel scenario launcher for Gate F runners

Fans out GATE_F_N_DEV=1 subprocess calls (one per scenario), running up to
GATE_F_N_WORKERS in parallel. After all succeed, merges per-scenario JSONs
into the combined output the sequential runner would produce.

Each worker is an independent subprocess: full dataset load + one scenario.
Setup overhead ~30s per worker; dominated by scenario compute (~80 min each).
With 8 workers and 25 scenarios: ~4 hours wall-clock vs ~33 hours sequential.

Usage (C2):
  THERMALSHIFT_DATA_DIR=<path> \\
  GATE_F_N_FIRST=30 GATE_F_N_DEV=25 GATE_F_N_WORKERS=8 \\
  GATE_F_RATIOS_ONLY="1.25" \\
  python3 artifacts/manuscript_completion/runners/parallel_gate_f_run.py \\
    artifacts/manuscript_completion/runners/c2_gate_f_run.py

Usage (C3-P90):
  THERMALSHIFT_DATA_DIR=<path> \\
  GATE_F_N_FIRST=30 GATE_F_N_DEV=25 GATE_F_N_WORKERS=8 \\
  GATE_F_RATIOS_ONLY="1.25" T_THR_C3=61.875 \\
  python3 artifacts/manuscript_completion/runners/parallel_gate_f_run.py \\
    artifacts/manuscript_completion/runners/c3_gate_f_run.py

Environment variables:
  GATE_F_N_FIRST       Required. First scenario index (e.g. 30).
  GATE_F_N_DEV         Required. Number of scenarios (e.g. 25).
  GATE_F_N_WORKERS     Optional. Concurrent workers. Default: min(N_DEV, 8).
  GATE_F_KEEP_WORKER_FILES  Optional. Set to 1 to keep per-scenario JSONs after merge.
  All other GATE_F_* and T_THR_C3 env vars are forwarded to each worker.

Output:
  Per-worker:  results/gate_f_sc{i}-{i}_*.json  (intermediate, deleted after merge)
  Per-worker:  results/gate_f_sc{i}-{i}_*_checkpoint.json  (deleted after merge)
  Per-worker:  results/sc{i}_worker.log  (kept for audit)
  Merged:      results/gate_f_sc{N_FIRST}-{N_FIRST+N_DEV-1}_*.json

Exit codes: 0 = success, 1 = pre-flight failure or worker failure(s).
"""

import sys, os, json, time, subprocess, hashlib, re, shutil
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

# Known runner SHA256s — checked before launch.
_KNOWN_RUNNER_SHAS = {
    "c2_gate_f_run.py": "e0de9d35a99715bc05c08177b08ad399bb25902fb492ef3487223135b7d3c44a",
    "c3_gate_f_run.py": "3b4e9825462a5f8b80bc6f76c6938bcf88d460d12f782210474b38573654e91c",
}


# ── Utilities ─────────────────────────────────────────────────────────────────

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git_is_clean() -> tuple[bool, str]:
    try:
        out = subprocess.check_output(
            ["git", "status", "--porcelain", "--untracked-files=no"],
            cwd=str(REPO_ROOT), text=True
        ).strip()
        return (not out), out
    except subprocess.CalledProcessError:
        return False, "git status failed"


def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "log", "--oneline", "-1"], cwd=str(REPO_ROOT), text=True
        ).strip()
    except subprocess.CalledProcessError:
        return "unknown"


# ── Per-scenario filename inference ──────────────────────────────────────────

def _infer_per_scenario_filename(scenario_idx: int, runner_name: str) -> str:
    """
    Replicate each runner's OUT_FILE naming logic for a single-scenario worker.
    Returns the expected stem (no .json) so we can find both the output and checkpoint.
    """
    n_first = scenario_idx
    scen_tag = f"sc{n_first}-{n_first}"

    ratios_only = os.environ.get("GATE_F_RATIOS_ONLY", "")
    if ratios_only:
        ratio_tag = (ratios_only
                     .replace(",", "_")
                     .replace(".", "p")
                     .replace("unrestricted", "unr"))
    else:
        ratio_tag = "all"

    if runner_name == "c2_gate_f_run.py":
        return f"gate_f_{scen_tag}_{ratio_tag}_c2manuscript"

    if runner_name == "c3_gate_f_run.py":
        t_thr = float(os.environ.get("T_THR_C3", "63.625"))
        thr_tag = f"t{str(t_thr).replace('.', 'p')}"
        return f"gate_f_{scen_tag}_{ratio_tag}_{thr_tag}_c3manuscript"

    # Fallback: search glob
    return None


def _merged_filename(n_first: int, n_dev: int, runner_name: str) -> str:
    scen_tag = f"sc{n_first}-{n_first + n_dev - 1}"
    ratios_only = os.environ.get("GATE_F_RATIOS_ONLY", "")
    if ratios_only:
        ratio_tag = (ratios_only
                     .replace(",", "_")
                     .replace(".", "p")
                     .replace("unrestricted", "unr"))
    else:
        ratio_tag = "all"

    if runner_name == "c2_gate_f_run.py":
        return f"gate_f_{scen_tag}_{ratio_tag}_c2manuscript.json"

    if runner_name == "c3_gate_f_run.py":
        t_thr = float(os.environ.get("T_THR_C3", "63.625"))
        thr_tag = f"t{str(t_thr).replace('.', 'p')}"
        return f"gate_f_{scen_tag}_{ratio_tag}_{thr_tag}_c3manuscript.json"

    raise ValueError(f"Unknown runner: {runner_name}")


# ── Pre-flight checks ─────────────────────────────────────────────────────────

def preflight(runner_path: Path, n_first: int, n_dev: int, n_workers: int):
    runner_name = runner_path.name
    errors = []

    # 1. Runner exists
    if not runner_path.exists():
        errors.append(f"Runner not found: {runner_path}")
        _abort(errors)

    # 2. Runner SHA
    if runner_name in _KNOWN_RUNNER_SHAS:
        actual = sha256_file(runner_path)
        expected = _KNOWN_RUNNER_SHAS[runner_name]
        if actual != expected:
            errors.append(
                f"Runner SHA256 mismatch for {runner_name}:\n"
                f"  expected: {expected}\n"
                f"  actual:   {actual}\n"
                f"  Runner has been modified. Verify before running."
            )

    # 3. Git clean
    clean, dirty = _git_is_clean()
    if not clean:
        errors.append(
            f"Working tree has uncommitted tracked changes:\n{dirty}\n"
            f"  Commit or stash before running."
        )

    # 4. No pre-existing merged output
    merged_name = _merged_filename(n_first, n_dev, runner_name)
    merged_path = OUT_DIR / merged_name
    if merged_path.exists():
        errors.append(
            f"Merged output already exists: {merged_path}\n"
            f"  Move or rename before rerunning."
        )

    # 5. No pre-existing per-scenario outputs or checkpoints
    for i in range(n_first, n_first + n_dev):
        stem = _infer_per_scenario_filename(i, runner_name)
        if stem:
            out = OUT_DIR / f"{stem}.json"
            ckpt = OUT_DIR / f"{stem}_checkpoint.json"
            if out.exists():
                errors.append(f"Per-scenario output already exists: {out}")
            if ckpt.exists():
                errors.append(f"Per-scenario checkpoint already exists: {ckpt}")

    # 6. THERMALSHIFT_DATA_DIR set and has expected parquet
    data_dir = os.environ.get("THERMALSHIFT_DATA_DIR", "")
    if not data_dir:
        errors.append("THERMALSHIFT_DATA_DIR is not set.")
    else:
        parquet = Path(data_dir) / "frontier-completed-job-info.parquet"
        if not parquet.exists():
            errors.append(f"frontier-completed-job-info.parquet not found in THERMALSHIFT_DATA_DIR: {data_dir}")

    if errors:
        _abort(errors)

    print("=" * 70)
    print("PARALLEL GATE F LAUNCH — PRE-FLIGHT PASSED")
    print("=" * 70)
    print(f"  git HEAD:          {_git_head()}")
    print(f"  Runner:            {runner_name}")
    if runner_name in _KNOWN_RUNNER_SHAS:
        print(f"  Runner SHA256:     {_KNOWN_RUNNER_SHAS[runner_name][:16]}...")
    print(f"  Scenario range:    sc{n_first}–sc{n_first + n_dev - 1}  ({n_dev} scenarios)")
    print(f"  Workers:           {n_workers}")
    print(f"  GATE_F_RATIOS_ONLY:{os.environ.get('GATE_F_RATIOS_ONLY', '(all)')}")
    if runner_name == "c3_gate_f_run.py":
        print(f"  T_THR_C3:          {os.environ.get('T_THR_C3', '63.625')}")
    print(f"  Output dir:        {OUT_DIR}")
    print(f"  Expected merged:   {merged_name}")
    print(f"  Launch time:       {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print("=" * 70)


def _abort(errors):
    print("\nPREFLIGHT ERRORS:", file=sys.stderr)
    for e in errors:
        print(f"  ERROR: {e}", file=sys.stderr)
    sys.exit(1)


# ── Worker execution ──────────────────────────────────────────────────────────

def _run_worker(runner_path: Path, scenario_idx: int, log_dir: Path) -> dict:
    """
    Run the runner for a single scenario. Blocks until completion.
    Returns a result dict with keys: scenario_idx, returncode, elapsed_s, log_path.
    """
    env = os.environ.copy()
    env["GATE_F_N_FIRST"] = str(scenario_idx)
    env["GATE_F_N_DEV"]   = "1"
    # Suppress checkpoint-reuse guard output noise — each worker starts clean.

    log_path = log_dir / f"sc{scenario_idx}_worker.log"
    t0 = time.time()

    with open(log_path, "w", encoding="utf-8") as logf:
        proc = subprocess.run(
            [sys.executable, str(runner_path)],
            env=env,
            stdout=logf,
            stderr=subprocess.STDOUT,
            cwd=str(REPO_ROOT),
        )

    elapsed = time.time() - t0
    return {
        "scenario_idx": scenario_idx,
        "returncode":   proc.returncode,
        "elapsed_s":    elapsed,
        "log_path":     log_path,
    }


# ── Merge ─────────────────────────────────────────────────────────────────────

def merge_outputs(worker_json_paths: list[Path], n_first: int, n_dev: int,
                  runner_name: str, n_workers: int) -> Path:
    """
    Merge per-scenario JSON files into the combined output.
    Returns the merged output path.
    """
    scenario_results = []
    base_meta = None

    for path in sorted(worker_json_paths):
        with open(path) as f:
            d = json.load(f)
        if base_meta is None:
            base_meta = {k: v for k, v in d.items() if k != "scenario_results"}
        scenario_results.extend(d["scenario_results"])

    scenario_results.sort(key=lambda s: s["scenario_idx"])

    # Verify completeness
    expected = set(range(n_first, n_first + n_dev))
    got = {s["scenario_idx"] for s in scenario_results}
    if got != expected:
        missing = expected - got
        extra   = got - expected
        raise RuntimeError(
            f"Merge integrity check failed.\n"
            f"  Missing scenarios: {sorted(missing)}\n"
            f"  Unexpected scenarios: {sorted(extra)}"
        )

    merged = dict(base_meta)
    merged["n_first"] = n_first
    merged["n_dev"]   = n_dev
    merged["parallel_run"] = {
        "launcher":              Path(__file__).name,
        "n_workers":             n_workers,
        "worker_files_merged":   [p.name for p in sorted(worker_json_paths)],
        "merge_time_utc":        time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    merged["scenario_results"] = scenario_results

    merged_name = _merged_filename(n_first, n_dev, runner_name)
    merged_path = OUT_DIR / merged_name
    merged_path.write_text(json.dumps(merged, indent=2), encoding="utf-8")
    return merged_path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    runner_path = Path(sys.argv[1]).resolve()
    runner_name = runner_path.name

    # Required env vars
    n_first_env = os.environ.get("GATE_F_N_FIRST", "")
    n_dev_env   = os.environ.get("GATE_F_N_DEV", "")
    if not n_first_env or not n_dev_env:
        sys.exit("ERROR: GATE_F_N_FIRST and GATE_F_N_DEV must be set explicitly.")

    n_first   = int(n_first_env)
    n_dev     = int(n_dev_env)
    n_workers = int(os.environ.get("GATE_F_N_WORKERS", str(min(n_dev, 8))))
    keep_files = bool(int(os.environ.get("GATE_F_KEEP_WORKER_FILES", "0")))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log_dir = OUT_DIR  # worker logs go in the same results/ dir

    preflight(runner_path, n_first, n_dev, n_workers)

    scenarios = list(range(n_first, n_first + n_dev))
    t_start   = time.time()

    # Track results
    completed   = {}  # scenario_idx -> result dict
    failed      = []
    worker_jsons = []

    print(f"\nDispatching {n_dev} scenarios with {n_workers} workers...\n")

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(_run_worker, runner_path, sc, log_dir): sc
            for sc in scenarios
        }
        for fut in as_completed(futures):
            sc = futures[fut]
            try:
                result = fut.result()
            except Exception as exc:
                print(f"  [sc{sc}] EXCEPTION: {exc}", flush=True)
                failed.append(sc)
                continue

            elapsed_min = result["elapsed_s"] / 60
            if result["returncode"] == 0:
                stem = _infer_per_scenario_filename(sc, runner_name)
                out_path = OUT_DIR / f"{stem}.json" if stem else None

                # Fallback: glob for the output
                if out_path is None or not out_path.exists():
                    candidates = [
                        p for p in OUT_DIR.glob(f"gate_f_sc{sc}-{sc}_*.json")
                        if "_checkpoint" not in p.name
                    ]
                    out_path = candidates[0] if len(candidates) == 1 else None

                if out_path and out_path.exists():
                    worker_jsons.append(out_path)
                    completed[sc] = result
                    done_count = len(completed)
                    elapsed_total = (time.time() - t_start) / 60
                    print(
                        f"  [sc{sc}] DONE  {elapsed_min:.1f}min  "
                        f"({done_count}/{n_dev} complete, {elapsed_total:.1f}min elapsed)",
                        flush=True
                    )
                else:
                    print(
                        f"  [sc{sc}] DONE but output JSON not found! "
                        f"Log: {result['log_path']}",
                        flush=True
                    )
                    failed.append(sc)
            else:
                print(
                    f"  [sc{sc}] FAILED  rc={result['returncode']}  "
                    f"{elapsed_min:.1f}min  log: {result['log_path']}",
                    flush=True
                )
                failed.append(sc)

    if failed:
        print(f"\nFAILED scenarios: {sorted(failed)}", file=sys.stderr)
        print("Not merging. Fix failures and rerun.", file=sys.stderr)
        sys.exit(1)

    # ── Merge ────────────────────────────────────────────────────────────────
    print(f"\nAll {n_dev} scenarios complete. Merging...")
    merged_path = merge_outputs(worker_jsons, n_first, n_dev, runner_name, n_workers)
    merged_sha  = sha256_file(merged_path)

    total_min = (time.time() - t_start) / 60
    print(f"\nMerged output: {merged_path}")
    print(f"Merged SHA256: {merged_sha}")
    print(f"Total wall-clock: {total_min:.1f}min")

    # ── Cleanup intermediate files ────────────────────────────────────────────
    if not keep_files:
        print("\nCleaning up per-scenario intermediates...")
        for jp in worker_jsons:
            jp.unlink(missing_ok=True)
            ckpt = jp.with_name(jp.stem + "_checkpoint.json")
            ckpt.unlink(missing_ok=True)
        print(f"  Removed {len(worker_jsons)} worker JSONs and their checkpoints.")
        print(f"  Worker logs retained in: {log_dir}")

    print("\nDone.")


if __name__ == "__main__":
    main()
