#!/usr/bin/env python3
"""
Independent reproduction of the frozen F1 B_cab_hist denominator.
Code blocks copied verbatim from r3_gate_f_run.py at commit bfb658b
(runner SHA256: fa1b6549d2e9b33f42eb5318194d2cb6a67c72e52c1352aeb9a78a8838584a6d).

Source lines reproduced:
  _col_to_dt64ms  : bfb658b runner lines 158-160
  _rec_ts_ms      : bfb658b runner lines 162-163
  _rec_te_ms      : bfb658b runner lines 165-166
  record building : bfb658b runner lines 393-410
  bg_events_sorted: bfb658b runner lines 412-423
  sweep_cab_budget_fast: bfb658b runner lines 425-444
  B_cab_hist call : bfb658b runner line 444

This script does NOT import or call compute_f2_replay_denominator.py.

Acceptance criterion: B_cab_hist_F1_h == 67917.76333331302 to <=1e-9.
Pre-existing anchor: artifacts/revision1/results/m4_fair_baselines.json
  .data_anchors.B_cab_hist_h = 67917.76333331302
  SHA256: cfb4912b9a73bf8b4aaa4a20f16b25490b8110c4fc3b6aba2e2d300a0ec6badc
  Committed: 2026-09-30, before any F2 work.

Output: artifacts/revision3/frozen_f1_bcab_denominator_verification.json
"""
import os, json, hashlib, heapq, sys, time
from pathlib import Path
from collections import defaultdict

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
P1_DIR    = REPO_ROOT / "artifacts" / "phase1" / "analysis"
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
REV3_DIR  = REPO_ROOT / "artifacts" / "revision3"
TABLE_DIR = REV1_DIR / "tables"
DATA_DIR  = Path(os.environ.get("THERMALSHIFT_DATA_DIR",
    "C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset"))
OUT       = REV3_DIR / "frozen_f1_bcab_denominator_verification.json"

# ── Pre-existing anchor (revision1, pre-F2, 2026-09-30) ──────────────────────
ANCHOR_PATH      = REV1_DIR / "results" / "m4_fair_baselines.json"
ANCHOR_SHA256    = "cfb4912b9a73bf8b4aaa4a20f16b25490b8110c4fc3b6aba2e2d300a0ec6badc"
ANCHOR_VALUE_H   = 67917.76333331302
ANCHOR_JSON_KEY  = ".data_anchors.B_cab_hist_h"

# ── Frozen runner provenance ──────────────────────────────────────────────────
RUNNER_COMMIT    = "bfb658b"
RUNNER_SHA256    = "fa1b6549d2e9b33f42eb5318194d2cb6a67c72e52c1352aeb9a78a8838584a6d"
F1_THR_SHA256    = "c74634a4e5cfdad94d93fd42a462c5a7f2350d4bdff786f91057de7ab5e2c371"

# ── Verify anchor file integrity ──────────────────────────────────────────────
print("Verifying pre-existing anchor ...")
actual_anchor_sha = hashlib.sha256(open(ANCHOR_PATH, "rb").read()).hexdigest()
if actual_anchor_sha != ANCHOR_SHA256:
    sys.exit(f"ANCHOR SHA256 MISMATCH: expected {ANCHOR_SHA256}, got {actual_anchor_sha}")
with open(ANCHOR_PATH) as f:
    anchor_data = json.load(f)
anchor_val = anchor_data["data_anchors"]["B_cab_hist_h"]
if abs(anchor_val - ANCHOR_VALUE_H) > 1e-15:
    sys.exit(f"ANCHOR VALUE MISMATCH: expected {ANCHOR_VALUE_H}, got {anchor_val}")
print(f"  Anchor OK: {ANCHOR_PATH.name} SHA256 matches, value={anchor_val}")

# ── Verify F1 threshold file integrity ───────────────────────────────────────
print("Verifying F1 threshold artifact ...")
thr_path = REV1_DIR / "results" / "cabinet_power_envelopes.json"
actual_thr_sha = hashlib.sha256(open(thr_path, "rb").read()).hexdigest()
if actual_thr_sha != F1_THR_SHA256:
    sys.exit(f"F1 THRESHOLD SHA256 MISMATCH: expected {F1_THR_SHA256}, got {actual_thr_sha}")
print(f"  F1 threshold artifact SHA256 matches.")

# ══════════════════════════════════════════════════════════════════════════════
# CODE BLOCKS VERBATIM FROM bfb658b runner
# ══════════════════════════════════════════════════════════════════════════════

# bfb658b lines 158-160
def _col_to_dt64ms(series):
    s = pd.to_datetime(series, utc=True)
    return s.dt.tz_convert("UTC").dt.tz_localize(None).values.astype("datetime64[ms]")

# bfb658b lines 162-163
def _rec_ts_ms(r):
    v = r["t_s"]
    return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))

# bfb658b lines 165-166
def _rec_te_ms(r):
    v = r["t_e"]
    return int(v) if isinstance(v, (int, np.integer)) else int(v.astype("int64"))

# bfb658b lines 425-443
def sweep_cab_budget_fast(cohort_records, thr):
    coh_ev = []
    for r in cohort_records:
        ppn = r["ppn"]; ts = _rec_ts_ms(r); te = _rec_te_ms(r)
        for c, n in r["cab_counts"].items():
            dp = ppn * n
            coh_ev.append((ts, +1, c, dp)); coh_ev.append((te, -1, c, dp))
    coh_ev.sort()
    P_cab: dict[int, float] = defaultdict(float); last_t: dict[int, int] = {}
    B = 0.0; S = 0.0
    for t, sign, c, dp in heapq.merge(bg_events_sorted, coh_ev):
        if c in last_t and t != last_t[c]:
            dt_h = (t - last_t[c]) / 3_600_000.0
            if dt_h > 0:
                exc = P_cab[c] - thr.get(c, 0.0)
                if exc > 0: B += dt_h; S += dt_h * exc
        P_cab[c] += sign * dp; last_t[c] = t
    return B, S

# ══════════════════════════════════════════════════════════════════════════════
# DATA LOADING (same paths as frozen runner)
# ══════════════════════════════════════════════════════════════════════════════
print("\nLoading data ...")
t0 = time.time()
fp_df    = pd.read_parquet(P1_DIR / "phase3a_fingerprint_2024.parquet")
test_df  = pd.read_parquet(P1_DIR / "phase3a_test_set.parquet")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
fp_df.index.name = "node"

# bfb658b lines 227-240 (runner step [1])
cohort_set  = set(fp_df.index)
test_id_set = set(test_df["job_idx"].astype(int))
fleet_topo  = pd.read_csv(TABLE_DIR / "fleet_node_topology.csv")
node_to_cab = dict(zip(fleet_topo["hostname"].values,
                       fleet_topo["cabinet"].values.astype(int)))
all_cabinets = sorted(set(node_to_cab.values()))
assert len(node_to_cab) == 9856, f"Expected 9856 nodes, got {len(node_to_cab)}"
assert len(all_cabinets) == 77,  f"Expected 77 cabinets, got {len(all_cabinets)}"

# bfb658b runner step [3]: F1 thresholds
with open(thr_path) as f:
    cab_env = json.load(f)
_p99_med = float(np.median([v * 1e3 for v in cab_env["per_cabinet_p99_kW_correct"].values()]))
cab_p99_W: dict[int, float] = {
    int(float(k)): v * 1e3 for k, v in cab_env["per_cabinet_p99_kW_correct"].items()
}
cab_p99_W = {c: cab_p99_W.get(c, _p99_med) for c in all_cabinets}

print(f"  Loaded in {time.time()-t0:.1f}s: {len(all_jobs):,} jobs  "
      f"{len(cohort_set)} cohort  {len(test_id_set):,} test IDs  77 cabinets")

# ── Build records (bfb658b runner lines 392-410) ──────────────────────────────
print("Building bg_records and cohort_hist_records ...")
t0 = time.time()
_all_jids = all_jobs["job_idx_int"].values
_all_Pj   = np.where(all_jobs["mean_power"].isna().values, 0.0,
                     all_jobs["mean_power"].values.astype(float))
_all_nc   = np.maximum(all_jobs["node_count"].values.astype(int), 1)
_all_hl   = all_jobs["host_list"].values
_all_st   = _col_to_dt64ms(all_jobs["start_time"])
_all_et   = _col_to_dt64ms(all_jobs["end_time"])
bg_records: list[dict] = []; cohort_hist_records: list[dict] = []
for jid, P_j, nc, hl, t_s, t_e in zip(_all_jids, _all_Pj, _all_nc, _all_hl, _all_st, _all_et):
    ppn = P_j / nc
    ncc: dict[int, int] = {}; chc: dict[int, int] = {}
    for hn in hl:
        c = node_to_cab.get(hn, -1)
        if c < 0: continue
        if hn in cohort_set: chc[c] = chc.get(c, 0) + 1
        else:                ncc[c] = ncc.get(c, 0) + 1
    if ncc: bg_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": ncc})
    if int(jid) in test_id_set and chc:
        cohort_hist_records.append({"t_s": t_s, "t_e": t_e, "ppn": ppn, "cab_counts": chc})
print(f"  bg_records={len(bg_records):,}  cohort_hist_records={len(cohort_hist_records):,}"
      f"  ({time.time()-t0:.1f}s)")

# ── Build bg_events_sorted (bfb658b lines 412-423) ────────────────────────────
print("Building bg_events_sorted ...")
t0 = time.time()
bg_events_sorted: list[tuple] = []
for _r in bg_records:
    _ppn = _r["ppn"]; _ts = int(_r["t_s"].astype("int64")); _te = int(_r["t_e"].astype("int64"))
    for _c, _n in _r["cab_counts"].items():
        _dp = _ppn * _n
        bg_events_sorted.append((_ts, +1, _c, _dp))
        bg_events_sorted.append((_te, -1, _c, _dp))
bg_events_sorted.sort()
print(f"  {len(bg_events_sorted):,} events  ({time.time()-t0:.1f}s)")

# ── Compute B_cab_hist (bfb658b line 444) ────────────────────────────────────
print("Computing B_cab_hist_F1 ...")
t0 = time.time()
B_cab_hist, _ = sweep_cab_budget_fast(cohort_hist_records, cab_p99_W)
print(f"  B_cab_hist_F1_h = {B_cab_hist:.10f} h  ({time.time()-t0:.1f}s)")

# ── Structural comparison targets (from compute_f2_replay_denominator.py) ────
# These must match exactly for the two scripts to be computing the same thing.
EXPECTED_STRUCTURAL = {
    "n_all_jobs":                152400,
    "n_test_id_set":             2637,    # unique job IDs in test_df
    "n_cohort_set":              2000,
    "bg_records":                141363,
    "cohort_hist_records":       2637,
    "bg_events_sorted":          None,    # not stored in replay denom, skip
}

structural_ok = True
checks = {
    "n_all_jobs":          (int(len(all_jobs)),          EXPECTED_STRUCTURAL["n_all_jobs"]),
    "n_test_id_set":       (int(len(test_id_set)),       EXPECTED_STRUCTURAL["n_test_id_set"]),
    "n_cohort_set":        (int(len(cohort_set)),        EXPECTED_STRUCTURAL["n_cohort_set"]),
    "bg_records":          (int(len(bg_records)),        EXPECTED_STRUCTURAL["bg_records"]),
    "cohort_hist_records": (int(len(cohort_hist_records)), EXPECTED_STRUCTURAL["cohort_hist_records"]),
}
print("\nStructural comparison (vs compute_f2_replay_denominator.py):")
for name, (got, exp) in checks.items():
    ok = got == exp
    status = "OK" if ok else "MISMATCH"
    print(f"  [{status}] {name}: {got} (expected {exp})")
    if not ok: structural_ok = False

# ── Acceptance tests ──────────────────────────────────────────────────────────
print("\nAcceptance tests:")
diff_anchor = abs(B_cab_hist - ANCHOR_VALUE_H)
anchor_pass = diff_anchor <= 1e-9
print(f"  [{'PASS' if anchor_pass else 'FAIL'}] vs pre-existing anchor "
      f"(m4_fair_baselines.json, 2026-09-30): "
      f"|{B_cab_hist:.10f} - {ANCHOR_VALUE_H:.10f}| = {diff_anchor:.2e}")

diff_replay = abs(B_cab_hist - 67917.76333331302)
replay_pass = diff_replay <= 1e-9
print(f"  [{'PASS' if replay_pass else 'FAIL'}] vs compute_f2_replay_denominator.py output: "
      f"|{B_cab_hist:.10f} - 67917.76333331302| = {diff_replay:.2e}")

overall_pass = anchor_pass and replay_pass and structural_ok
print(f"\nOverall: {'PASS' if overall_pass else 'FAIL'}")

# ── Write output ──────────────────────────────────────────────────────────────
bg_node_contrib = sum(sum(r["cab_counts"].values()) for r in bg_records)
coh_node_contrib = sum(sum(r["cab_counts"].values()) for r in cohort_hist_records)
output = {
    "script": "verify_frozen_f1_bcab_denominator.py",
    "purpose": "Independent reproduction of F1 B_cab_hist from frozen runner code blocks",
    "runner_commit": RUNNER_COMMIT,
    "runner_sha256": RUNNER_SHA256,
    "f1_threshold_artifact_sha256": F1_THR_SHA256,
    "pre_existing_anchor": {
        "file": "artifacts/revision1/results/m4_fair_baselines.json",
        "json_key": ANCHOR_JSON_KEY,
        "value_h": ANCHOR_VALUE_H,
        "sha256": ANCHOR_SHA256,
        "committed": "2026-09-30",
        "note": "Created before any F2 work; independent of compute_f2_replay_denominator.py",
    },
    "structural_inputs": {
        "n_all_jobs":                int(len(all_jobs)),
        "n_test_id_set":             int(len(test_id_set)),
        "n_cohort_set":              int(len(cohort_set)),
        "bg_records":                int(len(bg_records)),
        "cohort_hist_records":       int(len(cohort_hist_records)),
        "bg_events_sorted":          int(len(bg_events_sorted)),
        "bg_node_cab_contributions": int(bg_node_contrib),
        "coh_node_cab_contributions": int(coh_node_contrib),
    },
    "result": {
        "B_cab_hist_F1_h": float(B_cab_hist),
    },
    "acceptance": {
        "vs_pre_existing_anchor_diff": float(diff_anchor),
        "vs_pre_existing_anchor_pass": anchor_pass,
        "vs_replay_denominator_diff":  float(diff_replay),
        "vs_replay_denominator_pass":  replay_pass,
        "structural_inputs_match":     structural_ok,
        "overall_pass":                overall_pass,
    },
}
with open(OUT, "w") as f:
    json.dump(output, f, indent=2)
print(f"Written: {OUT}")
if not overall_pass:
    sys.exit(1)
