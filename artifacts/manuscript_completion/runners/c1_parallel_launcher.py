#!/usr/bin/env python3
"""
c1_parallel_launcher.py — Governed parallel launcher for C1 (sc5–sc29)

Spawns one c1_gate_f_run.py subprocess per scenario with GATE_F_N_FIRST=i
GATE_F_N_DEV=1, running up to GATE_F_N_WORKERS simultaneously. After all
succeed, delegates to c1_parallel_merge.py to produce the final merged JSON.

Governance:
  - Verifies c1_gate_f_run.py SHA (frozen: 7cb51ebc...)
  - Verifies corrected-reference input SHAs (f2_local_scheduling_reference.json,
    f2_replay_denominator.json)
  - Requires git clean tracked-file state
  - Requires explicit GATE_F_N_FIRST and GATE_F_N_DEV (fails closed otherwise)
  - Checks no pre-existing output or checkpoint for any scenario in range
  - Each worker: isolated stdout/stderr log, isolated checkpoint, isolated JSON

Resource pilot mode (GATE_F_PILOT=1):
  Runs exactly 2 workers with scenarios GATE_F_PILOT_SC_A and GATE_F_PILOT_SC_B
  (defaults: sc0 and sc1 — dev scenarios). Measures elapsed time and peak
  system RAM. Does NOT call the merger. Used to calibrate N_WORKERS.

Usage (full production run):
  THERMALSHIFT_DATA_DIR=<path> \\
  GATE_F_N_FIRST=5 GATE_F_N_DEV=25 GATE_F_N_WORKERS=8 \\
  python3 artifacts/manuscript_completion/runners/c1_parallel_launcher.py

Usage (resource pilot — dev scenarios, does not touch sc5–29):
  THERMALSHIFT_DATA_DIR=<path> \\
  GATE_F_PILOT=1 GATE_F_PILOT_SC_A=0 GATE_F_PILOT_SC_B=1 \\
  python3 artifacts/manuscript_completion/runners/c1_parallel_launcher.py

Usage (equivalence preflight — single worker, sc5 only):
  THERMALSHIFT_DATA_DIR=<path> \\
  GATE_F_N_FIRST=5 GATE_F_N_DEV=1 GATE_F_N_WORKERS=1 \\
  python3 artifacts/manuscript_completion/runners/c1_parallel_launcher.py
  (Then compare results/gate_f_sc5-5_all.json against SEQUENTIAL_SC5_REFERENCE.json)

Environment variables:
  GATE_F_N_FIRST       Required (unless GATE_F_PILOT=1). First scenario index.
  GATE_F_N_DEV         Required (unless GATE_F_PILOT=1). Number of scenarios.
  GATE_F_N_WORKERS     Optional. Concurrent workers. Default: min(N_DEV, 8).
  GATE_F_RATIOS_ONLY   Optional. Forwarded to each worker.
  GATE_F_PILOT         Optional. Set to 1 to run resource pilot (2 workers only).
  GATE_F_PILOT_SC_A    Optional. First pilot scenario index. Default: 0.
  GATE_F_PILOT_SC_B    Optional. Second pilot scenario index. Default: 1.
  THERMALSHIFT_DATA_DIR Required.
"""

import sys, os, json, hashlib, subprocess, time, threading
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

REPO_ROOT  = Path(__file__).resolve().parents[3]
RUNNERS    = Path(__file__).parent
OUT_DIR    = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

# ── Frozen constants ──────────────────────────────────────────────────────────
_RUNNER_NAME   = "c1_gate_f_run.py"
_RUNNER_PATH   = RUNNERS / _RUNNER_NAME
_RUNNER_SHA256 = "7cb51ebcf541d9c04b932ef879ce5095d34195452ef88151418d01ce844b41ba"

REV3_DIR = REPO_ROOT / "artifacts" / "revision3"
_F2_REF_PATH    = REV3_DIR / "f2_local_scheduling_reference.json"
_F2_REF_SHA     = "71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34"
_F2_DENOM_PATH  = REV3_DIR / "f2_replay_denominator.json"
_F2_DENOM_SHA   = "b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48"

_MERGER_PATH = RUNNERS / "c1_parallel_merge.py"

_C1_SCEN_FIRST = 5   # sc5–sc29 are the production held-out scenarios
_C1_SCEN_LAST  = 29


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
    """Expected output file stem for a single-scenario worker."""
    return f"gate_f_sc{sc_idx}-{sc_idx}_all"


def _find_worker_output(sc_idx: int) -> Path | None:
    stem = _scenario_stem(sc_idx)
    p = OUT_DIR / f"{stem}.json"
    return p if p.exists() else None


# ── Pre-flight ────────────────────────────────────────────────────────────────

def preflight(scenarios: list[int], n_workers: int, pilot: bool = False):
    errors = []

    # 1. Runner SHA
    if not _RUNNER_PATH.exists():
        errors.append(f"Runner not found: {_RUNNER_PATH}")
    else:
        actual = _sha256(_RUNNER_PATH)
        if actual != _RUNNER_SHA256:
            errors.append(
                f"Runner SHA256 mismatch:\n"
                f"  expected: {_RUNNER_SHA256}\n"
                f"  actual:   {actual}"
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
                    f"  expected: {expected_sha}\n"
                    f"  actual:   {actual}"
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

    # 5. No pre-existing outputs or checkpoints (production scenarios only, not pilot)
    if not pilot:
        for sc in scenarios:
            stem = _scenario_stem(sc)
            out_p  = OUT_DIR / f"{stem}.json"
            ckpt_p = OUT_DIR / f"{stem}_checkpoint.json"
            if out_p.exists():
                errors.append(f"Pre-existing worker output: {out_p.name}")
            if ckpt_p.exists():
                errors.append(f"Pre-existing checkpoint: {ckpt_p.name}")

        # Also check no merged output exists
        n_first = scenarios[0]
        n_dev   = len(scenarios)
        merged  = OUT_DIR / f"gate_f_sc{n_first}-{n_first + n_dev - 1}_all.json"
        if merged.exists():
            errors.append(f"Merged output already exists: {merged.name}")

    if errors:
        print("\nPREFLIGHT ERRORS:", file=sys.stderr)
        for e in errors:
            print(f"  ERROR: {e}", file=sys.stderr)
        sys.exit(1)

    mode = "PILOT (2 workers, dev scenarios)" if pilot else f"PRODUCTION ({len(scenarios)} scenarios)"
    print("=" * 70)
    print(f"C1 PARALLEL LAUNCHER — {mode}")
    print("=" * 70)
    print(f"  git HEAD:          {_git_head()}")
    print(f"  Runner SHA256:     {_RUNNER_SHA256[:16]}...")
    print(f"  F2 ref SHA256:     {_F2_REF_SHA[:16]}...")
    print(f"  F2 denom SHA256:   {_F2_DENOM_SHA[:16]}...")
    print(f"  Scenarios:         sc{scenarios[0]}–sc{scenarios[-1]}  ({len(scenarios)} total)")
    print(f"  N_WORKERS:         {n_workers}")
    print(f"  Output dir:        {OUT_DIR}")
    print(f"  Launch time:       {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print("=" * 70)


# ── Resource monitor (pilot only) ─────────────────────────────────────────────

class _ResourceMonitor:
    """
    Background thread that polls system memory every 5 seconds.
    Uses 'wmic OS get FreePhysicalMemory' on Windows (no psutil dependency).
    """
    def __init__(self):
        self.samples = []   # list of (timestamp, free_MB)
        self._stop  = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()
        self._thread.join(timeout=10)

    def _poll_free_mb(self) -> float | None:
        try:
            # Windows: wmic returns FreePhysicalMemory in KB
            out = subprocess.check_output(
                ["wmic", "OS", "get", "FreePhysicalMemory", "/value"],
                text=True, timeout=5
            )
            for line in out.splitlines():
                if "FreePhysicalMemory" in line:
                    kb = int(line.split("=")[1].strip())
                    return kb / 1024  # → MB
        except Exception:
            pass
        return None

    def _poll_total_mb(self) -> float | None:
        try:
            out = subprocess.check_output(
                ["wmic", "computersystem", "get", "TotalPhysicalMemory", "/value"],
                text=True, timeout=5
            )
            for line in out.splitlines():
                if "TotalPhysicalMemory" in line:
                    b = int(line.split("=")[1].strip())
                    return b / (1024 * 1024)  # → MB
        except Exception:
            pass
        return None

    def _run(self):
        while not self._stop.wait(5):
            free = self._poll_free_mb()
            if free is not None:
                self.samples.append((time.time(), free))

    def report(self, total_mb: float | None = None) -> dict:
        if not self.samples:
            return {"error": "no samples collected"}
        free_vals  = [s[1] for s in self.samples]
        min_free   = min(free_vals)
        total      = total_mb or self._poll_total_mb()
        peak_used  = (total - min_free) if total else None
        return {
            "total_ram_MB":     round(total, 0) if total else None,
            "min_free_MB":      round(min_free, 0),
            "peak_used_MB":     round(peak_used, 0) if peak_used else None,
            "peak_pct_used":    round(100 * peak_used / total, 1) if (total and peak_used) else None,
            "n_samples":        len(self.samples),
            "sample_interval_s": 5,
        }


# ── Worker execution ──────────────────────────────────────────────────────────

def _run_worker(sc_idx: int, log_path: Path) -> dict:
    """Run c1_gate_f_run.py for one scenario. Returns result metadata dict."""
    env = os.environ.copy()
    env["GATE_F_N_FIRST"] = str(sc_idx)
    env["GATE_F_N_DEV"]   = "1"
    # Ensure no checkpoint-reuse env leakage
    env.pop("GATE_F_TRACE_R1", None)

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


# ── Pilot mode ────────────────────────────────────────────────────────────────

def run_pilot(sc_a: int, sc_b: int) -> dict:
    """
    Run 2 workers simultaneously on dev scenarios. Monitor RAM.
    Returns pilot report dict.
    """
    log_a = OUT_DIR / f"sc{sc_a}_pilot.log"
    log_b = OUT_DIR / f"sc{sc_b}_pilot.log"

    monitor = _ResourceMonitor()
    monitor.start()
    t0 = time.time()

    results = {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {
            pool.submit(_run_worker, sc_a, log_a): sc_a,
            pool.submit(_run_worker, sc_b, log_b): sc_b,
        }
        for fut in as_completed(futures):
            sc = futures[fut]
            r  = fut.result()
            results[sc] = r
            status = "DONE" if r["success"] else f"FAILED (rc={r['returncode']})"
            print(
                f"  [pilot sc{sc}] {status}  {r['elapsed_s']/60:.1f}min",
                flush=True
            )

    wall_clock = time.time() - t0
    monitor.stop()
    ram = monitor.report()

    pilot_report = {
        "pilot_sc_a":       sc_a,
        "pilot_sc_b":       sc_b,
        "wall_clock_s":     round(wall_clock, 1),
        "wall_clock_min":   round(wall_clock / 60, 1),
        "sc_a_elapsed_s":   round(results[sc_a]["elapsed_s"], 1),
        "sc_b_elapsed_s":   round(results[sc_b]["elapsed_s"], 1),
        "sc_a_success":     results[sc_a]["success"],
        "sc_b_success":     results[sc_b]["success"],
        "ram":              ram,
    }

    print("\nPilot RAM report:")
    for k, v in ram.items():
        print(f"  {k}: {v}")

    # Clean up pilot output files (dev scenarios — not production data)
    for sc in [sc_a, sc_b]:
        stem = _scenario_stem(sc)
        for suffix in [".json", "_checkpoint.json"]:
            p = OUT_DIR / f"{stem}{suffix}"
            if p.exists():
                p.unlink()
                print(f"  [cleanup] removed pilot output: {p.name}")

    return pilot_report


# ── Production run ────────────────────────────────────────────────────────────

def run_production(scenarios: list[int], n_workers: int) -> list[Path]:
    """
    Fan out scenarios to N_WORKERS subprocesses. Returns list of output paths.
    Aborts (without merging) if any worker fails.
    """
    worker_jsons = []
    failed = []
    t0 = time.time()

    print(f"\nDispatching {len(scenarios)} scenarios ({n_workers} workers)...\n")

    with ThreadPoolExecutor(max_workers=n_workers) as pool:
        futures = {
            pool.submit(
                _run_worker,
                sc,
                OUT_DIR / f"sc{sc}_worker.log"
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
                    f"{elapsed_min:.1f}min  log: {OUT_DIR / f'sc{sc}_worker.log'}",
                    flush=True
                )

    if failed:
        print(f"\n[ABORT] {len(failed)} scenario(s) failed: {sorted(failed)}", file=sys.stderr)
        print("Fix failures and re-run failed scenarios. Do not merge partial results.", file=sys.stderr)
        sys.exit(1)

    return worker_jsons


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    pilot_mode = bool(int(os.environ.get("GATE_F_PILOT", "0")))

    if pilot_mode:
        sc_a = int(os.environ.get("GATE_F_PILOT_SC_A", "0"))
        sc_b = int(os.environ.get("GATE_F_PILOT_SC_B", "1"))
        scenarios = [sc_a, sc_b]
        n_workers = 2
        preflight(scenarios, n_workers, pilot=True)
        report = run_pilot(sc_a, sc_b)
        print("\n[PILOT COMPLETE]")
        print(json.dumps(report, indent=2))
        return

    # Production / equivalence-preflight mode
    n_first_env = os.environ.get("GATE_F_N_FIRST", "")
    n_dev_env   = os.environ.get("GATE_F_N_DEV", "")
    if not n_first_env or not n_dev_env:
        sys.exit(
            "ERROR: GATE_F_N_FIRST and GATE_F_N_DEV must be set explicitly.\n"
            "  Production C1: GATE_F_N_FIRST=5 GATE_F_N_DEV=25\n"
            "  Equivalence preflight: GATE_F_N_FIRST=5 GATE_F_N_DEV=1"
        )

    n_first   = int(n_first_env)
    n_dev     = int(n_dev_env)
    n_workers = int(os.environ.get("GATE_F_N_WORKERS", str(min(n_dev, 8))))

    # Validate production range
    if n_first < _C1_SCEN_FIRST or (n_first + n_dev - 1) > _C1_SCEN_LAST:
        sys.exit(
            f"ERROR: Scenario range sc{n_first}–sc{n_first+n_dev-1} is outside "
            f"the authorized C1 held-out range sc{_C1_SCEN_FIRST}–sc{_C1_SCEN_LAST}.\n"
            f"  Use GATE_F_PILOT=1 to run dev-scenario pilots."
        )

    scenarios = list(range(n_first, n_first + n_dev))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    preflight(scenarios, n_workers)
    worker_jsons = run_production(scenarios, n_workers)

    # Write manifest
    manifest_path = OUT_DIR / f"c1_worker_manifest_sc{n_first}-{n_first+n_dev-1}.txt"
    manifest_path.write_text("\n".join(str(p) for p in sorted(worker_jsons)), encoding="utf-8")
    print(f"\nManifest written: {manifest_path}")

    # Invoke merger
    merged_out = OUT_DIR / f"gate_f_sc{n_first}-{n_first+n_dev-1}_all.json"
    merger_cmd = [
        sys.executable, str(_MERGER_PATH),
        "--manifest", str(manifest_path),
        "--n-first",  str(n_first),
        "--n-dev",    str(n_dev),
        "--out",      str(merged_out),
    ]
    print(f"\nInvoking merger: c1_parallel_merge.py")
    ret = subprocess.run(merger_cmd, cwd=str(REPO_ROOT))
    if ret.returncode != 0:
        sys.exit(f"[ABORT] Merger failed with exit code {ret.returncode}.")

    print(f"\nC1 PARALLEL RUN COMPLETE")
    print(f"  Output: {merged_out}")


if __name__ == "__main__":
    main()
