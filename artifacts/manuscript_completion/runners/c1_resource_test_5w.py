#!/usr/bin/env python3
"""
c1_resource_test_5w.py — 5-worker resource saturation test (RESOURCE TEST ONLY)

Spawns 5 frozen c1_gate_f_run.py workers on dev scenarios sc0-sc4 using the
identical subprocess invocation the production launcher uses. Workers are killed
after 10 minutes of steady-state concurrent operation. Scientific results are
NOT retained.

PowerShell (Get-CimInstance Win32_OperatingSystem + Get-Process) is used to
sample RAM every 30 seconds once all 5 workers are active.

Worker-count ruling (applied automatically at end):
  min_free_pct >= 20%  AND  no worker crash  -> N_WORKERS=5  (authorized)
  otherwise                                   -> N_WORKERS=3  (fallback)

Exit codes: 0 = N_WORKERS=5 authorized, 3 = fallback N_WORKERS=3 authorized,
            1 = unexpected failure.
"""

import sys, os, json, hashlib, subprocess, time, threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNNERS   = Path(__file__).parent
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"
RUNNER    = RUNNERS / "c1_gate_f_run.py"

_RUNNER_SHA256         = "7cb51ebcf541d9c04b932ef879ce5095d34195452ef88151418d01ce844b41ba"
_STEADY_DURATION_S     = 600   # 10 min sampling window once all 5 workers active
_SAMPLE_INTERVAL_S     = 30
_WARMUP_TIMEOUT_S      = 900   # abort if workers not all active within 15 min
_LAMBDA_MARKER         = "lam="  # steady-state indicator in worker logs
_TEST_SCENARIOS        = [0, 1, 2, 3, 4]
_RAM_PASS_PCT          = 20.0


# ── SHA verification ──────────────────────────────────────────────────────────

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_runner():
    if not RUNNER.exists():
        sys.exit(f"[ABORT] Runner not found: {RUNNER}")
    actual = _sha256(RUNNER)
    if actual != _RUNNER_SHA256:
        sys.exit(
            f"[ABORT] Runner SHA256 mismatch.\n"
            f"  Expected: {_RUNNER_SHA256}\n"
            f"  Actual:   {actual}"
        )
    print(f"[OK] Runner SHA256 verified: {_RUNNER_SHA256[:16]}...")


# ── RAM sampling (PowerShell) ─────────────────────────────────────────────────

_PS_SAMPLE = r"""
$os    = Get-CimInstance Win32_OperatingSystem
$procs = Get-Process -Name python* -ErrorAction SilentlyContinue
$total_kb  = $os.TotalVisibleMemorySize
$free_kb   = $os.FreePhysicalMemory
$pct_free  = [math]::Round(100.0 * $free_kb / $total_kb, 2)
$ws_sum_mb = [math]::Round( ($procs | Measure-Object -Property WorkingSet64 -Sum).Sum     / 1MB, 1)
$ws_max_mb = [math]::Round( ($procs | Measure-Object -Property WorkingSet64 -Maximum).Maximum / 1MB, 1)
$n_procs   = if ($procs) { $procs.Count } else { 0 }
"TOTAL_KB=$total_kb FREE_KB=$free_kb PCT_FREE=$pct_free WS_SUM_MB=$ws_sum_mb WS_MAX_MB=$ws_max_mb N_PROCS=$n_procs"
""".strip()


def _sample_ram() -> dict | None:
    try:
        r = subprocess.run(
            ["powershell", "-NonInteractive", "-Command", _PS_SAMPLE],
            capture_output=True, text=True, timeout=15
        )
        line = r.stdout.strip()
        if not line:
            return None
        parts = {}
        for kv in line.split():
            k, _, v = kv.partition("=")
            parts[k] = v
        return {
            "ts":          time.time(),
            "total_mb":    round(int(parts["TOTAL_KB"]) / 1024, 1),
            "free_mb":     round(int(parts["FREE_KB"]) / 1024, 1),
            "pct_free":    float(parts["PCT_FREE"]),
            "ws_sum_mb":   float(parts["WS_SUM_MB"]),
            "ws_max_mb":   float(parts["WS_MAX_MB"]),
            "n_procs":     int(parts["N_PROCS"]),
        }
    except Exception as exc:
        print(f"  [RAM sample error] {exc}")
        return None


# ── Steady-state detection ────────────────────────────────────────────────────

def _wait_for_all_active(log_paths: dict, timeout_s: float) -> float:
    """
    Poll worker log files until all show a 'lam=' line (entered lambda loop).
    Returns the timestamp when the last worker became active.
    Exits if timeout_s exceeded.
    """
    active = set()
    t0 = time.time()
    print(f"\nWaiting for all {len(log_paths)} workers to enter lambda loop "
          f"(timeout={timeout_s}s)...")
    while len(active) < len(log_paths):
        if time.time() - t0 > timeout_s:
            sys.exit(
                f"[ABORT] Steady-state timeout after {timeout_s}s. "
                f"Active: {sorted(active)}, Missing: {sorted(set(log_paths)-active)}"
            )
        for sc, lp in log_paths.items():
            if sc in active:
                continue
            try:
                text = lp.read_text(encoding="utf-8", errors="replace")
                if _LAMBDA_MARKER in text:
                    active.add(sc)
                    elapsed = time.time() - t0
                    print(f"  sc{sc} active ({elapsed:.0f}s elapsed)")
            except FileNotFoundError:
                pass
        if len(active) < len(log_paths):
            time.sleep(5)
    t_steady = time.time()
    print(f"All {len(log_paths)} workers active. Steady-state window starts now.")
    return t_steady


# ── Cleanup ───────────────────────────────────────────────────────────────────

def _kill_workers(procs: dict, log_files: dict):
    """SIGTERM all workers, wait briefly, then SIGKILL stragglers."""
    print("\nTerminating workers...")
    for sc, proc in procs.items():
        try:
            proc.terminate()
        except Exception:
            pass
    time.sleep(5)
    for sc, proc in procs.items():
        try:
            if proc.poll() is None:
                proc.kill()
        except Exception:
            pass
    for lf in log_files.values():
        try:
            lf.close()
        except Exception:
            pass
    print("All workers terminated.")


def _cleanup_artifacts():
    """Remove partial outputs left by killed workers."""
    removed = []
    for sc in _TEST_SCENARIOS:
        stem = f"gate_f_sc{sc}-{sc}_all"
        for suffix in [".json", "_checkpoint.json"]:
            p = OUT_DIR / f"{stem}{suffix}"
            if p.exists():
                p.unlink()
                removed.append(p.name)
    if removed:
        for name in removed:
            print(f"  [cleanup] removed: {name}")
    else:
        print("  [cleanup] no partial outputs found (workers killed before writing)")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 70)
    print("C1 RESOURCE SATURATION TEST — 5 workers (sc0-sc4, dev scenarios)")
    print("RESOURCE TEST ONLY — scientific results will not be retained")
    print("=" * 70)
    print(f"  Runner:    {RUNNER.name}")
    print(f"  Scenarios: sc0-sc4 (dev range)")
    print(f"  Workers:   5")
    print(f"  Sampling:  every {_SAMPLE_INTERVAL_S}s for {_STEADY_DURATION_S}s after all active")
    print(f"  RAM gate:  free >= {_RAM_PASS_PCT:.0f}% during steady-state window")
    print()

    _verify_runner()

    # Pre-check: no leftover artifacts from earlier runs
    for sc in _TEST_SCENARIOS:
        stem = f"gate_f_sc{sc}-{sc}_all"
        for suffix in [".json", "_checkpoint.json"]:
            p = OUT_DIR / f"{stem}{suffix}"
            if p.exists():
                sys.exit(f"[ABORT] Pre-existing artifact: {p.name} — remove before running")

    # Spawn 5 workers
    env_base = os.environ.copy()
    env_base.pop("GATE_F_TRACE_R1", None)

    procs     = {}   # sc_idx -> Popen
    log_files = {}   # sc_idx -> open file handle
    log_paths = {}   # sc_idx -> Path

    print("Spawning 5 workers...")
    for sc in _TEST_SCENARIOS:
        e = env_base.copy()
        e["GATE_F_N_FIRST"] = str(sc)
        e["GATE_F_N_DEV"]   = "1"
        lp = OUT_DIR / f"sc{sc}_restest.log"
        lf = open(lp, "w", encoding="utf-8")
        proc = subprocess.Popen(
            [sys.executable, str(RUNNER)],
            env=e,
            stdout=lf,
            stderr=subprocess.STDOUT,
            cwd=str(REPO_ROOT),
        )
        procs[sc]     = proc
        log_files[sc] = lf
        log_paths[sc] = lp
        print(f"  sc{sc} spawned (PID {proc.pid})")

    # Wait for steady state
    try:
        _wait_for_all_active(log_paths, _WARMUP_TIMEOUT_S)
    except SystemExit:
        _kill_workers(procs, log_files)
        _cleanup_artifacts()
        raise

    # Sample RAM for steady-state duration
    samples = []
    t_end = time.time() + _STEADY_DURATION_S
    remaining = int(t_end - time.time())
    print(f"\nSampling every {_SAMPLE_INTERVAL_S}s for {remaining}s...\n")

    while time.time() < t_end:
        # Check for unexpected worker crashes
        crashed = [sc for sc, p in procs.items() if p.poll() is not None]
        if crashed:
            print(f"[WARN] Workers crashed unexpectedly: {crashed}")

        s = _sample_ram()
        if s:
            samples.append(s)
            ts = time.strftime("%H:%M:%S", time.localtime(s["ts"]))
            print(
                f"  [{ts}]  free={s['pct_free']:.1f}%  "
                f"ws_sum={s['ws_sum_mb']:.0f}MB  ws_max={s['ws_max_mb']:.0f}MB  "
                f"n_py={s['n_procs']}"
            )
        remaining = max(0, int(t_end - time.time()))
        if remaining > 0:
            time.sleep(min(_SAMPLE_INTERVAL_S, remaining))

    # Kill workers and clean up
    _kill_workers(procs, log_files)
    _cleanup_artifacts()

    # ── Report ────────────────────────────────────────────────────────────────
    crashed_final = [sc for sc, p in procs.items() if p.returncode not in (None, -15, -9, 1)]

    print("\n" + "=" * 70)
    print("RESOURCE TEST RESULTS")
    print("=" * 70)

    if not samples:
        print("[FAIL] No RAM samples collected — PowerShell polling failed.")
        sys.exit(1)

    total_mb    = samples[0]["total_mb"] if samples else None
    min_free    = min(s["pct_free"] for s in samples)
    max_ws_sum  = max(s["ws_sum_mb"] for s in samples)
    max_ws_max  = max(s["ws_max_mb"] for s in samples)
    n_samples   = len(samples)

    print(f"  Samples collected:    {n_samples}  ({n_samples * _SAMPLE_INTERVAL_S}s coverage)")
    print(f"  Total physical RAM:   {total_mb:.0f} MB")
    print(f"  Min free RAM:         {min_free:.1f}%")
    print(f"  Max Python WS sum:    {max_ws_sum:.0f} MB")
    print(f"  Max individual WS:    {max_ws_max:.0f} MB")
    print(f"  Worker crashes:       {len(crashed_final)}")
    print()

    ram_ok     = min_free >= _RAM_PASS_PCT
    crash_ok   = len(crashed_final) == 0

    print(f"  RAM gate (>={_RAM_PASS_PCT:.0f}% free):   {'PASS' if ram_ok else 'FAIL'}  [{min_free:.1f}%]")
    print(f"  Crash gate (0 crashes): {'PASS' if crash_ok else 'FAIL'}  [{len(crashed_final)} crash(es)]")

    if ram_ok and crash_ok:
        print("\n[RESULT] N_WORKERS=5 AUTHORIZED")
        print("  All gates passed. Proceed with GATE_F_N_WORKERS=5.")
        return 0
    else:
        print("\n[RESULT] N_WORKERS=5 FAILED — USE N_WORKERS=3 FALLBACK")
        if not ram_ok:
            print(f"  RAM gate failed: {min_free:.1f}% < {_RAM_PASS_PCT:.0f}% required")
        if not crash_ok:
            print(f"  Crash gate failed: {crashed_final}")
        return 3


if __name__ == "__main__":
    sys.exit(main())
