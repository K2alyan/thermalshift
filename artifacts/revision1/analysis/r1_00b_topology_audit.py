#!/usr/bin/env python3
"""
Topology parsing audit for revision1.

ISSUE: phase3b_mc.py, phase3b3f_fullcab.py, and phase3b3f_val.py all use
    for hn, xn in zip(hl, str(nl).split()):
instead of the correct native-array zip:
    for hn, xn in zip(hl, nl):

For jobs with node_count > numpy print threshold (1000), str(numpy.ndarray)
abbreviates the output with '...', causing:
  1. The '...' element to be paired with a real hostname.
  2. Nodes near the end of the array to be misaligned with their actual xnames.
  3. Middle-of-array nodes to be dropped entirely from the map.

This audit:
A. Builds the CORRECT hostname->cabinet map using native array zip.
B. Builds the BUGGY map using str(nl).split() to replicate frozen code.
C. Quantifies differences and affected nodes.
D. Determines which frozen cabinet results are superseded.
E. Builds the correct topology table for the fp analysis nodes.
F. Checks manifest vs fingerprint node-set discrepancy.

Output: artifacts/revision1/results/topology_audit.json
        artifacts/revision1/tables/fp_node_topology.csv
"""

import re, json, hashlib, subprocess, datetime, time
import numpy as np
import pandas as pd
from pathlib import Path
from collections import defaultdict

DATA_DIR   = Path("C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset")
REPO_ROOT  = Path(__file__).resolve().parents[3]
PHASE1_DIR = REPO_ROOT / "artifacts" / "phase1"
ANAL_DIR   = PHASE1_DIR / "analysis"
OUT_DIR    = REPO_ROOT / "artifacts" / "revision1" / "results"
TABLE_DIR  = REPO_ROOT / "artifacts" / "revision1" / "tables"
OUT_DIR.mkdir(parents=True, exist_ok=True)
TABLE_DIR.mkdir(parents=True, exist_ok=True)

XNAME_RE = re.compile(r"x(\d+)c(\d+)s(\d+)b(\d+)n(\d+)")

def git_sha():
    try:
        return subprocess.check_output(["git","rev-parse","HEAD"], text=True,
                                       cwd=str(REPO_ROOT)).strip()
    except Exception:
        return "unknown"

def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

print("=" * 65)
print("Topology Parsing Audit")
print("=" * 65)
t0 = time.time()

# ──────────────────────────────────────────────────────────────────
# Load
# ──────────────────────────────────────────────────────────────────
print("\n[0] Loading job metadata ...")
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
n_total  = len(all_jobs)
numpy_threshold = np.get_printoptions()["threshold"]
n_truncated_jobs = int((all_jobs.node_count > numpy_threshold).sum())
print(f"    {n_total:,} total jobs")
print(f"    numpy print threshold: {numpy_threshold}")
print(f"    Jobs with node_count > threshold (string-truncated): {n_truncated_jobs:,} "
      f"({100*n_truncated_jobs/n_total:.1f}%)")
print(f"    Max node_count: {all_jobs.node_count.max():,}")

# ──────────────────────────────────────────────────────────────────
# A. Correct map (native array zip)
# ──────────────────────────────────────────────────────────────────
print("\n[A] Building CORRECT hostname->xname map (native array zip) ...")
t1 = time.time()
correct_map: dict[str, set] = defaultdict(set)
n_len_mismatch = 0
n_jobs_processed = 0

for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    if len(hl) != len(nl):
        n_len_mismatch += 1
        continue
    for hn, xn in zip(hl, nl):
        correct_map[str(hn)].add(str(xn))
    n_jobs_processed += 1

print(f"    Done in {time.time()-t1:.1f}s")
print(f"    Jobs with len(host_list) != len(node_list): {n_len_mismatch}")
print(f"    Unique hostnames: {len(correct_map):,}")
correct_multi = {hn: list(xns) for hn, xns in correct_map.items() if len(xns) > 1}
print(f"    Hostnames with >1 xname (CORRECT): {len(correct_multi)}")

# Cabinet map from correct mapping
def xn_to_cab(xn):
    m = XNAME_RE.match(str(xn))
    return int(m.group(1)) if m else None

correct_cab: dict[str, int] = {}
for hn, xns in correct_map.items():
    # All should be 1:1 per the correct map; just take the single xname
    for xn in xns:
        cab = xn_to_cab(xn)
        if cab is not None:
            correct_cab[hn] = cab
            break

correct_cabinets = sorted(set(correct_cab.values()))
print(f"    Unique cabinets (correct): {len(correct_cabinets)}")
print(f"    Cabinets: min={min(correct_cabinets)}, max={max(correct_cabinets)}")

# ──────────────────────────────────────────────────────────────────
# B. Buggy map (str(nl).split() as in frozen code)
# ──────────────────────────────────────────────────────────────────
print("\n[B] Building BUGGY hostname->xname map (str(nl).split()) ...")
t2 = time.time()
buggy_map: dict[str, set] = defaultdict(set)
n_ellipsis_hits = 0

for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    # Replicate the frozen code exactly
    xn_list = str(nl).split()
    for hn, xn_raw in zip(hl, xn_list):
        xn = xn_raw.strip("'[]\"")
        if xn == "...":
            n_ellipsis_hits += 1
            continue
        buggy_map[str(hn)].add(xn)

print(f"    Done in {time.time()-t2:.1f}s")
print(f"    '...' ellipsis hits (nodes skipped/misaligned): {n_ellipsis_hits:,}")
buggy_multi = {hn: list(xns) for hn, xns in buggy_map.items() if len(xns) > 1}
print(f"    Hostnames with >1 xname (BUGGY): {len(buggy_multi)}")

buggy_cab: dict[str, int] = {}
for hn, xns in buggy_map.items():
    # Use first valid cabinet assignment
    for xn in xns:
        cab = xn_to_cab(xn)
        if cab is not None:
            buggy_cab[hn] = cab
            break

buggy_cabinets = sorted(set(buggy_cab.values()))
print(f"    Unique cabinets (buggy): {len(buggy_cabinets)}")

# ──────────────────────────────────────────────────────────────────
# C. Compare correct vs buggy
# ──────────────────────────────────────────────────────────────────
print("\n[C] Comparing correct vs buggy maps ...")

# Nodes whose cabinet assignment differs
cab_mismatch = 0
cab_missing_in_buggy = 0
for hn in correct_cab:
    if hn not in buggy_cab:
        cab_missing_in_buggy += 1
    elif correct_cab[hn] != buggy_cab[hn]:
        cab_mismatch += 1

print(f"    Nodes correctly in correct_cab: {len(correct_cab):,}")
print(f"    Nodes correctly in buggy_cab: {len(buggy_cab):,}")
print(f"    Nodes missing from buggy map: {cab_missing_in_buggy:,}")
print(f"    Nodes with WRONG cabinet in buggy map: {cab_mismatch:,}")

# Impact on the cohort fp nodes specifically
fp_df = pd.read_parquet(ANAL_DIR / "phase3a_fingerprint_2024.parquet")
fp_nodes = set(fp_df.index)

fp_correct = {hn: cab for hn, cab in correct_cab.items() if hn in fp_nodes}
fp_buggy   = {hn: cab for hn, cab in buggy_cab.items()   if hn in fp_nodes}
fp_cab_mismatch = sum(1 for hn in fp_correct
                      if hn in fp_buggy and fp_correct[hn] != fp_buggy[hn])
fp_missing = sum(1 for hn in fp_correct if hn not in fp_buggy)

print(f"\n    FP analysis nodes ({len(fp_nodes)}) cabinet impact:")
print(f"    Wrong cabinet in frozen code: {fp_cab_mismatch}")
print(f"    Missing from frozen map:       {fp_missing}")

# ──────────────────────────────────────────────────────────────────
# D. Impact on frozen cabinet results
# ──────────────────────────────────────────────────────────────────
print("\n[D] Impact assessment on frozen cabinet results ...")

# Which jobs contributed corrupted assignments?
# Jobs where node_count > threshold are partially truncated
affected_job_count = int((all_jobs.node_count > numpy_threshold).sum())
affected_node_hours = float(all_jobs.loc[all_jobs.node_count > numpy_threshold,
                                         "node_hour_usage"].sum())
total_node_hours = float(all_jobs["node_hour_usage"].sum())

print(f"    Affected jobs (node_count > {numpy_threshold}): {affected_job_count:,}")
print(f"    Affected node-hours: {affected_node_hours:,.0f} of {total_node_hours:,.0f} "
      f"({100*affected_node_hours/total_node_hours:.1f}%)")

# Are any frozen results directly dependent on buggy cabinet map?
# - phase3b_mc.py: uses node_to_cabinet for cabinet constraint (B_cab_ratio)
# - phase3b3f_fullcab.py: builds cabinet-level power time series
# - phase3b3f_val.py: validates cabinet assignment

# For the fp nodes, the cabinet assignment error rate matters
print(f"\n    For the {len(fp_nodes)} fp analysis nodes:")
print(f"      Cabinet correct in both: "
      f"{sum(1 for hn in fp_nodes if hn in fp_correct and hn in fp_buggy and fp_correct[hn]==fp_buggy[hn])}")
print(f"      Cabinet WRONG in frozen:  {fp_cab_mismatch}")
print(f"      Cabinet MISSING in frozen:{fp_missing}")

# ──────────────────────────────────────────────────────────────────
# E. Build correct topology table for fp analysis nodes
# ──────────────────────────────────────────────────────────────────
print("\n[E] Building correct topology table for fp analysis nodes ...")

# Get xname for each fp node (correct_map should have it)
# Since Phase 0 confirmed 1:1, each fp node has exactly one xname
fp_topology_rows = []
for hn in sorted(fp_nodes):
    xns = correct_map.get(hn, set())
    if not xns:
        xn = None
        cab = chassis = slot = board = node_pos = None
    else:
        xn = next(iter(xns))
        m  = XNAME_RE.match(str(xn))
        if m:
            cab, chassis, slot, board, node_pos = (
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)))
        else:
            cab = chassis = slot = board = node_pos = None
    fp_topology_rows.append(dict(
        hostname=hn, xname=xn,
        cabinet=cab, chassis=chassis, slot=slot, board=board, node_pos=node_pos,
        cabinet_correct=correct_cab.get(hn),
        cabinet_buggy=buggy_cab.get(hn),
        cabinet_matches=(correct_cab.get(hn) == buggy_cab.get(hn)),
    ))

fp_topo_df = pd.DataFrame(fp_topology_rows)
fp_topo_df.to_csv(TABLE_DIR / "fp_node_topology.csv", index=False)
print(f"    Saved {len(fp_topo_df)} fp node topology rows")
print(f"    Unique cabinets (fp nodes): {fp_topo_df.cabinet.nunique()}")
print(f"    Nodes missing xname: {fp_topo_df.xname.isna().sum()}")
print(f"    Cabinet matches (correct vs buggy): {fp_topo_df.cabinet_matches.sum()}")

# ──────────────────────────────────────────────────────────────────
# F. Manifest vs fingerprint discrepancy
# ──────────────────────────────────────────────────────────────────
print("\n[F] Manifest vs fingerprint node-set discrepancy ...")

manifest = pd.read_csv(PHASE1_DIR / "cohort_manifest.csv")
man_nodes = set(manifest.hostname)

overlap  = fp_nodes & man_nodes
only_fp  = fp_nodes - man_nodes
only_man = man_nodes - fp_nodes

print(f"    fp_df nodes:       {len(fp_nodes)}")
print(f"    manifest nodes:    {len(man_nodes)}")
print(f"    Overlap:           {len(overlap)}")
print(f"    Only in fp:        {len(only_fp)}")
print(f"    Only in manifest:  {len(only_man)}")
print()
print("    CONCLUSION: cohort_manifest.csv contains a DIFFERENT 2,000-node")
print("    selection from what was used to compute phase3a_fingerprint_2024.parquet.")
print("    The fingerprint nodes are the AUTHORITATIVE analysis cohort.")
print("    cohort_manifest.csv in the public repo does not match the analysis.")
print()
print("    For M1 and all revision analyses, use fp_node_topology.csv")
print("    (built from fp_df.index + correct xname mapping) instead of")
print("    cohort_manifest.csv for location information.")

# Verify test_set consistency with fp
test_df   = pd.read_parquet(ANAL_DIR / "phase3a_test_set.parquet")
test_nodes = set(test_df.node.unique())
print(f"\n    test_set nodes: {len(test_nodes)}, all in fp: {test_nodes <= fp_nodes}")

discrepancy_summary = {
    "fp_nodes": len(fp_nodes),
    "manifest_nodes": len(man_nodes),
    "overlap": len(overlap),
    "only_in_fp": len(only_fp),
    "only_in_manifest": len(only_man),
    "conclusion": (
        "cohort_manifest.csv (2000 nodes) is a DIFFERENT set from "
        "phase3a_fingerprint_2024.parquet (2000 nodes). Only 1333 overlap. "
        "The fingerprint and test_set parquets define the authoritative "
        "analysis cohort. For M1 location analysis use fp_node_topology.csv."
    ),
    "test_set_consistent_with_fp": bool(test_nodes <= fp_nodes),
}

# ──────────────────────────────────────────────────────────────────
# Assemble JSON
# ──────────────────────────────────────────────────────────────────
result = {
    "script":    "r1_00b_topology_audit.py",
    "git_sha":   git_sha(),
    "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    "input_sha256": {
        "frontier-completed-job-info.parquet":
            file_sha256(DATA_DIR / "frontier-completed-job-info.parquet"),
        "phase3a_fingerprint_2024.parquet":
            file_sha256(ANAL_DIR / "phase3a_fingerprint_2024.parquet"),
        "cohort_manifest.csv":
            file_sha256(PHASE1_DIR / "cohort_manifest.csv"),
    },

    "string_truncation_bug": {
        "bug_description": (
            "phase3b_mc.py line 70, phase3b3f_fullcab.py line 77, "
            "phase3b3f_val.py line 46 all use "
            "'for hn, xn in zip(hl, str(nl).split())' "
            "instead of 'for hn, xn in zip(hl, nl)'. "
            "For jobs with node_count > numpy print threshold ("
            f"{numpy_threshold}), str(ndarray) abbreviates with '...', "
            "causing hostname-xname misalignment and dropped nodes."
        ),
        "numpy_print_threshold": int(numpy_threshold),
        "jobs_affected": {
            "count": int(affected_job_count),
            "fraction": float(affected_job_count / n_total),
            "affected_node_hours": float(affected_node_hours),
            "fraction_of_total_node_hours": float(affected_node_hours / total_node_hours),
        },
        "ellipsis_hits_in_buggy_parse": int(n_ellipsis_hits),
    },

    "hostname_xname_mapping": {
        "correct_unique_hostnames":     len(correct_map),
        "correct_multi_xname_count":    len(correct_multi),
        "correct_unique_cabinets":      len(correct_cabinets),
        "buggy_unique_hostnames":       len(buggy_map),
        "buggy_multi_xname_count":      len(buggy_multi),
        "jobs_with_len_mismatch":       int(n_len_mismatch),
        "fleet_wide_cab_wrong_in_buggy":int(cab_mismatch),
        "fleet_wide_missing_in_buggy":  int(cab_missing_in_buggy),
    },

    "fp_nodes_impact": {
        "n_fp_nodes": len(fp_nodes),
        "fp_cabinet_correct_in_both": int(sum(
            1 for hn in fp_nodes
            if hn in fp_correct and hn in fp_buggy and fp_correct[hn]==fp_buggy[hn])),
        "fp_cabinet_wrong_in_frozen":   int(fp_cab_mismatch),
        "fp_cabinet_missing_in_frozen": int(fp_missing),
        "verdict": (
            "CABINET RESULTS SUPERSEDED" if (fp_cab_mismatch + fp_missing) > 0
            else "CABINET RESULTS UNAFFECTED"
        ),
    },

    "frozen_results_status": {
        "phase3b_mc_fingerprint_prospective":
            "UNAFFECTED — bug only affects cabinet assignment, not fingerprint computation",
        "phase3b_mc_cabinet_constraint":
            "SUPERSEDED — cabinet map was built with buggy str(nl).split()",
        "phase3b3f_fullcab_power":
            "SUPERSEDED — cabinet-level power reconstruction used buggy map",
        "phase3b3f_val":
            "SUPERSEDED — cabinet validation used buggy map",
        "action":
            "M3/M4 must rebuild cabinet map with native array zip before rerunning MC.",
    },

    "manifest_fingerprint_discrepancy": discrepancy_summary,

    "elapsed_seconds": round(time.time() - t0, 1),
}

out_path = OUT_DIR / "topology_audit.json"
with open(out_path, "w") as f:
    json.dump(result, f, indent=2)

print(f"\nSaved: {out_path}")
print(f"Total elapsed: {time.time()-t0:.1f}s")
