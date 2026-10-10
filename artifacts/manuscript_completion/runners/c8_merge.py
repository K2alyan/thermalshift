#!/usr/bin/env python3
"""
Merge per-worker c8 output JSONs into a single file.

Usage:
    python artifacts/manuscript_completion/runners/c8_merge.py

Finds all gate_f_sc*_c8f1diagnostic.json files in results/ root (not
subdirectories), merges scenario_results sorted by scenario_idx,
validates 25 scenarios with no duplicates.
"""
import sys, json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

suffix  = "c8f1diagnostic"
pattern = f"gate_f_sc*_{suffix}.json"
# Only root-level files — exclude preflight/ subdirectory
parts = sorted(p for p in OUT_DIR.glob(pattern)
               if "_checkpoint" not in p.name
               and not p.name.startswith("gate_f_sc30-54_"))

print(f"Merging {len(parts)} files matching '{pattern}':")
for p in parts:
    print(f"  {p.name}")

if not parts:
    print("No files found. Run c8_launch_parallel.py first.")
    sys.exit(1)

all_scenarios = []
meta = None

for fp in parts:
    data = json.loads(fp.read_text(encoding="utf-8"))
    if meta is None:
        meta = {k: v for k, v in data.items() if k != "scenario_results"}
    sc_results = data["scenario_results"]
    print(f"  {fp.name}: {len(sc_results)} scenarios  "
          f"git={data.get('git_commit_short', '?')}")
    all_scenarios.extend(sc_results)

all_scenarios.sort(key=lambda s: s["scenario_idx"])
idxs = [s["scenario_idx"] for s in all_scenarios]
dups = [i for i in idxs if idxs.count(i) > 1]
if dups:
    print(f"ERROR: Duplicate scenario indices: {sorted(set(dups))}")
    sys.exit(1)

expected = list(range(30, 55))
missing  = [i for i in expected if i not in idxs]
extra    = [i for i in idxs if i not in expected]
if missing:
    print(f"ERROR: Missing scenarios: {missing}")
    sys.exit(1)
if extra:
    print(f"ERROR: Unexpected scenarios: {extra}")
    sys.exit(1)

print(f"\nAll 25 scenarios present (sc30-sc54), no duplicates.")

merged = dict(meta)
merged["merged_from"]       = [p.name for p in parts]
merged["n_scenarios_total"] = len(all_scenarios)
merged["scenario_results"]  = all_scenarios

ratios    = meta.get("gate_f_ratios", [])
ratio_tag = "_".join(r.replace(".", "p") for r in ratios) if ratios else "unknown"

out_file = OUT_DIR / f"gate_f_sc30-54_{ratio_tag}_{suffix}.json"
out_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
size_mb = out_file.stat().st_size / 1024 / 1024
print(f"Merged output: {out_file.name}  ({size_mb:.1f} MB)")
