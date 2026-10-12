#!/usr/bin/env python3
"""
Parallel launcher for c8_gate_f_run.py.

Splits sc30-54 into N_WORKERS worker processes.
    export THERMALSHIFT_DATA_DIR=/path/to/data
    python artifacts/manuscript_completion/runners/c8_launch_parallel.py

Optional env overrides:
    GATE_F_N_WORKERS  — number of parallel workers (default 3)
    GATE_F_RATIOS_ONLY — ratios to run (default "1.0,1.25")
"""
import os, sys, subprocess, time
from pathlib import Path

REPO_ROOT   = Path(__file__).resolve().parents[3]
RUNNER      = Path(__file__).parent / "c8_gate_f_run.py"
N_SCENARIOS = 25
SC_FIRST    = 30
N_WORKERS   = int(os.environ.get("GATE_F_N_WORKERS", "3"))

_per, _rem  = divmod(N_SCENARIOS, N_WORKERS)
splits = []
first = SC_FIRST
for w in range(N_WORKERS):
    n = _per + (1 if w < _rem else 0)
    splits.append((first, n))
    first += n

env = os.environ.copy()

if "GATE_F_RATIOS_ONLY" not in env:
    env["GATE_F_RATIOS_ONLY"] = "1.0,1.25"

print(f"Launching {N_WORKERS} C8 workers")
print(f"  GATE_F_RATIOS_ONLY={env['GATE_F_RATIOS_ONLY']}")
print(f"  Splits: {splits}")

procs = []
for w, (sc_first, n_dev) in enumerate(splits):
    w_env = dict(env)
    w_env["GATE_F_N_FIRST"] = str(sc_first)
    w_env["GATE_F_N_DEV"]   = str(n_dev)
    log_path = REPO_ROOT / "artifacts" / "manuscript_completion" / "results" / \
               f"c8_worker{w}_sc{sc_first}-{sc_first+n_dev-1}.log"
    log_f = open(log_path, "w")
    p = subprocess.Popen(
        [sys.executable, str(RUNNER)],
        env=w_env, stdout=log_f, stderr=subprocess.STDOUT,
        cwd=str(REPO_ROOT),
    )
    procs.append((w, sc_first, n_dev, p, log_path, log_f))
    print(f"  Worker {w}: sc{sc_first}-sc{sc_first+n_dev-1}  pid={p.pid}  log={log_path.name}")

t0 = time.time()
failed = []
for w, sc_first, n_dev, p, log_path, log_f in procs:
    rc = p.wait()
    log_f.close()
    elapsed = time.time() - t0
    if rc == 0:
        print(f"  Worker {w} (sc{sc_first}-sc{sc_first+n_dev-1}): DONE  ({elapsed:.0f}s)")
    else:
        print(f"  Worker {w} (sc{sc_first}-sc{sc_first+n_dev-1}): FAILED rc={rc}  see {log_path.name}")
        failed.append(w)

if failed:
    print(f"\nFAILED workers: {failed}  -- check logs")
    sys.exit(1)
else:
    print(f"\nAll {N_WORKERS} workers completed successfully in {time.time()-t0:.0f}s")
    print("Run c8_merge.py to combine outputs.")
