#!/usr/bin/env python3
"""
r1_gate_f_quartile_freeze.py

Freeze job-size quartile boundaries before held-out execution.
Computes the four quartile bins of k (n_cohort, cohort node count per base
test job) from the frozen Phase 1 data, using exactly the same _make_quartile_map
logic as r1_gate_f_run.py.

Quartile stratification is descriptive diagnostics only. No quartile-specific
C_lower/C_upper crossings are introduced (GATE_F_DESIGN §9).

Required env var: THERMALSHIFT_DATA_DIR — directory containing
    frontier-completed-job-info.parquet

Output: artifacts/revision1/results/gate_f_quartile_manifest.json
"""

import sys, io, os, json, hashlib, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
import pandas as pd
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
P1_DIR    = REPO_ROOT / "artifacts" / "phase1" / "analysis"
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR   = REV1_DIR / "results"
DATA_DIR  = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

OUT_FILE  = OUT_DIR / "gate_f_quartile_manifest.json"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def _git_head() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    except Exception:
        return "unknown"

def _make_quartile_map(arr, jids):
    # Identical to r1_gate_f_run.py
    cuts = np.percentile(arr, [25, 50, 75])
    q    = (np.digitize(arr, cuts) + 1).clip(1, 4)
    return {int(jid): int(qi) for jid, qi in zip(jids, q)}

print("Gate F: Job-size Quartile Freeze")
print("=" * 60)

# ── Load data (same as r1_gate_f_run.py steps 0+5) ──────────────────────────
print("[0] Loading data ...")
fp_df    = pd.read_parquet(P1_DIR / "phase3a_fingerprint_2024.parquet")
test_df  = pd.read_parquet(P1_DIR / "phase3a_test_set.parquet")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)

cohort_set = set(fp_df.index)

frontier_sha = sha256_file(DATA_DIR / "frontier-completed-job-info.parquet")
print(f"    frontier parquet SHA-256: {frontier_sha}")

# ── Aggregate test jobs (identical to run script step 5) ────────────────────
print("[1] Aggregating base test jobs ...")
job_agg = (
    test_df.groupby("job_idx")
    .agg(n_cohort=("node", "count"))
    .reset_index()
)
meta = (
    all_jobs[["job_idx_int", "node_count", "start_time", "run_time"]]
    .rename(columns={"job_idx_int": "job_idx"})
)
job_agg = job_agg.merge(meta, on="job_idx", how="left")
jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)
n_base = len(jobs_sorted)
print(f"    {n_base} base test jobs")

# ── Compute quartile boundaries ──────────────────────────────────────────────
print("[2] Computing quartile boundaries ...")
k_arr  = jobs_sorted["n_cohort"].values.astype(int)
_jids  = jobs_sorted["job_idx"].values

cuts = np.percentile(k_arr, [25, 50, 75])
q25_cut = float(cuts[0])
q50_cut = float(cuts[1])
q75_cut = float(cuts[2])

print(f"    k (n_cohort) range: [{k_arr.min()}, {k_arr.max()}]")
print(f"    Q25 cut: {q25_cut}  Q50 cut: {q50_cut}  Q75 cut: {q75_cut}")

# Boundary convention: np.digitize with right=False (default)
#   Q1: k < q25_cut   (digitize returns 0, +1 = 1)
#   Q2: q25_cut <= k < q50_cut   (digitize returns 1, +1 = 2)
#   Q3: q50_cut <= k < q75_cut   (digitize returns 2, +1 = 3)
#   Q4: k >= q75_cut   (digitize returns 3, +1 = 4)
# clip(1,4) handles any edge case from exact percentile values.
q_arr = (np.digitize(k_arr, cuts) + 1).clip(1, 4)

q_counts = {q: int((q_arr == q).sum()) for q in range(1, 5)}
q_k_ranges = {}
for q in range(1, 5):
    mask = q_arr == q
    if mask.any():
        q_k_ranges[q] = [int(k_arr[mask].min()), int(k_arr[mask].max())]
    else:
        q_k_ranges[q] = [None, None]

print("    Quartile distribution:")
for q in range(1, 5):
    lo, hi = q_k_ranges[q]
    print(f"      Q{q}: n={q_counts[q]}  k in [{lo}, {hi}]")

# ── Confirm instrumentation-only: q_admit/q_drop never influence scheduling ──
# These counters are written AFTER placement decisions are committed and are
# never read back by candidate construction, policy selection, look_ahead_safe,
# utilization state, thermal/exposure accounting, cabinet accounting, or
# classify_crossing. They are purely diagnostic accumulators.
INSTRUMENTATION_ONLY_CONFIRMED = True

# ── Save manifest ────────────────────────────────────────────────────────────
print("[3] Saving manifest ...")

manifest = {
    "freeze_head"                   : _git_head(),
    "frozen_by"                     : "r1_gate_f_quartile_freeze.py",
    "quartile_definition_variable"  : "k (n_cohort: cohort node count per base test job)",
    "quartile_count"                : 4,
    "boundary_convention"           : (
        "np.digitize(k, [q25_cut, q50_cut, q75_cut], right=False) + 1, clipped to [1,4]. "
        "Q1: k < q25_cut; Q2: q25_cut <= k < q50_cut; "
        "Q3: q50_cut <= k < q75_cut; Q4: k >= q75_cut. "
        "Left-closed, right-open for Q1–Q3; Q4 is left-closed only."
    ),
    "cuts": {
        "q25": q25_cut,
        "q50": q50_cut,
        "q75": q75_cut,
    },
    "quartile_bins": {
        str(q): {
            "n_jobs"    : q_counts[q],
            "k_min"     : q_k_ranges[q][0],
            "k_max"     : q_k_ranges[q][1],
        }
        for q in range(1, 5)
    },
    "n_base_jobs_total"             : n_base,
    "k_global_min"                  : int(k_arr.min()),
    "k_global_max"                  : int(k_arr.max()),
    "frozen_diagnostic_fields": [
        "attempted",
        "admitted",
        "drop_cap",
        "drop_physical",
        "drop_la",
        "admission_fraction",
        "realized_selector_choice_multiplier",
    ],
    "instrumentation_only_confirmed": INSTRUMENTATION_ONLY_CONFIRMED,
    "instrumentation_only_note": (
        "q_admit, q_drop, and all strat_* dicts are written AFTER placement "
        "decisions are committed (Stages 1–3 complete). They are never read by "
        "candidate construction, policy selection, look_ahead_safe, utilization "
        "state, thermal/exposure accounting, cabinet accounting, or "
        "classify_crossing. Quartile stratification is descriptive diagnostics "
        "only. No quartile-specific C_lower/C_upper crossings are defined "
        "(GATE_F_DESIGN §9)."
    ),
    "frontier_parquet_sha256"       : frontier_sha,
    "frontier_parquet_path"         : str(DATA_DIR / "frontier-completed-job-info.parquet"),
    "phase1_test_set_path"          : str(P1_DIR / "phase3a_test_set.parquet"),
}

with open(OUT_FILE, "w") as f:
    json.dump(manifest, f, indent=2)

print(f"    Saved: {OUT_FILE}")
print()
print("Quartile boundaries frozen. Do not recompute before sc5–29.")
print(f"  Q25={q25_cut}  Q50={q50_cut}  Q75={q75_cut}")
