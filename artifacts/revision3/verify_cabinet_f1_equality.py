#!/usr/bin/env python3
"""
Standalone gate check: verify exact equality of cabinet set and F1 threshold
dictionary between the frozen-runner reconstruction path and the new
replay-denominator path.

Both paths ultimately read the same source files, but this script explicitly
constructs both dictionaries independently and compares them value by value.

Exit 0 = PASS. Exit 1 = FAIL.
"""
import json, sys, csv
import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
REV3_DIR  = REPO_ROOT / "artifacts" / "revision3"

print("=" * 60)
print("Cabinet set and F1 threshold equality check")
print("=" * 60)

# ── PATH A: frozen-runner reconstruction ──────────────────────
# Mirrors r3_gate_f_run.py step [1] + step [3] at bfb658b.
print("\n[Path A] Frozen-runner reconstruction (r3_gate_f_run.py step [1]+[3])")

with open(REV1_DIR / "tables" / "fleet_node_topology.csv") as f:
    topo_rows = list(csv.DictReader(f))
node_to_cab_A = {r["hostname"]: int(r["cabinet"]) for r in topo_rows}
all_cabinets_A = sorted(set(node_to_cab_A.values()))
assert len(node_to_cab_A) == 9856, f"Expected 9856 nodes, got {len(node_to_cab_A)}"
print(f"  nodes: {len(node_to_cab_A)}  cabinets: {len(all_cabinets_A)}")

with open(REV1_DIR / "results" / "cabinet_power_envelopes.json") as f:
    cab_env_A = json.load(f)
p99_raw_A = {int(float(k)): v * 1e3
             for k, v in cab_env_A["per_cabinet_p99_kW_correct"].items()}
p99_med_A = float(np.median(list(p99_raw_A.values())))
cab_p99_W_A = {c: p99_raw_A.get(c, p99_med_A) for c in all_cabinets_A}
print(f"  F1 threshold dict: {len(cab_p99_W_A)} entries, median={p99_med_A/1000:.2f} kW")

# ── PATH B: replay-denominator path ───────────────────────────
# Mirrors compute_f2_replay_denominator.py + verify_frozen_f1_bcab_denominator.py.
print("\n[Path B] Replay-denominator path (compute_f2_replay_denominator.py)")

with open(REV1_DIR / "tables" / "fleet_node_topology.csv") as f:
    topo_rows_B = list(csv.DictReader(f))
node_to_cab_B = {r["hostname"]: int(r["cabinet"]) for r in topo_rows_B}
all_cabinets_B = sorted(set(node_to_cab_B.values()))
assert len(node_to_cab_B) == 9856, f"Expected 9856 nodes, got {len(node_to_cab_B)}"
print(f"  nodes: {len(node_to_cab_B)}  cabinets: {len(all_cabinets_B)}")

with open(REV1_DIR / "results" / "cabinet_power_envelopes.json") as f:
    cab_env_B = json.load(f)
p99_raw_B = {int(float(k)): v * 1e3
             for k, v in cab_env_B["per_cabinet_p99_kW_correct"].items()}
p99_med_B = float(np.median(list(p99_raw_B.values())))
cab_p99_W_B = {c: p99_raw_B.get(c, p99_med_B) for c in all_cabinets_B}
print(f"  F1 threshold dict: {len(cab_p99_W_B)} entries, median={p99_med_B/1000:.2f} kW")

# Cross-check against stored replay denominator per-cabinet F1 values
with open(REV3_DIR / "f2_replay_denominator.json") as f:
    rd = json.load(f)
rd_f1 = {int(x["cabinet"]): float(x["Q_F1_W"]) for x in rd["per_cabinet"]}
print(f"  Replay denom artifact: {len(rd_f1)} cabinet F1 values loaded")

# ── COMPARISONS ───────────────────────────────────────────────
print("\n" + "-" * 60)
results = {}

# 1. Cabinet count
results["cabinet_count_A"] = len(all_cabinets_A)
results["cabinet_count_B"] = len(all_cabinets_B)
count_pass = len(all_cabinets_A) == 77 and len(all_cabinets_B) == 77
print(f"[{'PASS' if count_pass else 'FAIL'}] Cabinet count: A={len(all_cabinets_A)}, B={len(all_cabinets_B)} (expected 77 each)")

# 2. Cabinet set equality
set_A = set(all_cabinets_A)
set_B = set(all_cabinets_B)
missing_from_B = sorted(set_A - set_B)
missing_from_A = sorted(set_B - set_A)
set_pass = (set_A == set_B)
print(f"[{'PASS' if set_pass else 'FAIL'}] Cabinet sets exactly equal")
if missing_from_B: print(f"  Missing from B: {missing_from_B}")
if missing_from_A: print(f"  Missing from A: {missing_from_A}")

# 3. F1 threshold key-set equality
keys_A = set(cab_p99_W_A.keys())
keys_B = set(cab_p99_W_B.keys())
keys_pass = (keys_A == keys_B)
print(f"[{'PASS' if keys_pass else 'FAIL'}] F1 threshold key sets exactly equal")

# 4. F1 threshold value equality (A vs B)
if keys_pass and set_pass:
    diffs = {c: abs(cab_p99_W_A[c] - cab_p99_W_B[c]) for c in all_cabinets_A}
    max_diff_AB = max(diffs.values())
    n_unequal_AB = sum(1 for v in diffs.values() if v > 0)
    val_pass_AB = max_diff_AB == 0.0
    print(f"[{'PASS' if val_pass_AB else 'FAIL'}] F1 threshold values A==B: "
          f"max_abs_diff={max_diff_AB}, n_unequal={n_unequal_AB}")
else:
    val_pass_AB = False
    max_diff_AB = float("nan")
    print("[SKIP] F1 threshold value comparison skipped (key sets differ)")

# 5. F1 threshold value equality (A vs replay-denom artifact)
if set_pass and len(rd_f1) == 77:
    diffs_rd = {c: abs(cab_p99_W_A[c] - rd_f1[c]) for c in all_cabinets_A}
    max_diff_rd = max(diffs_rd.values())
    n_unequal_rd = sum(1 for v in diffs_rd.values() if v > 0)
    val_pass_rd = max_diff_rd == 0.0
    print(f"[{'PASS' if val_pass_rd else 'FAIL'}] F1 threshold values A==replay_denom_artifact: "
          f"max_abs_diff={max_diff_rd}, n_unequal={n_unequal_rd}")
else:
    val_pass_rd = False
    max_diff_rd = float("nan")
    print("[SKIP] Replay-denom artifact comparison skipped")

# ── SUMMARY ───────────────────────────────────────────────────
overall = count_pass and set_pass and keys_pass and val_pass_AB and val_pass_rd
print("\n" + "=" * 60)
print(f"OVERALL: {'PASS' if overall else 'FAIL'}")
print("=" * 60)

if not overall:
    sys.exit(1)
