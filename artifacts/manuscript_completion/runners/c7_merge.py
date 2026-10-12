#!/usr/bin/env python3
"""
Merge per-worker c7 output JSONs into a single file.

Usage:
    python artifacts/manuscript_completion/runners/c7_merge.py [--suffix c7primary]
    python artifacts/manuscript_completion/runners/c7_merge.py --suffix c7beta0p960

Finds all gate_f_sc*_{suffix}.json files in results/, merges scenario_results
sorted by scenario_idx, validates 25 scenarios with no duplicates.
"""
import sys, json, argparse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"

parser = argparse.ArgumentParser()
parser.add_argument("--suffix", default="c7primary",
                    help="run suffix to merge (c7primary or c7beta0p960)")
args = parser.parse_args()

suffix = args.suffix
pattern = f"gate_f_sc*_{suffix}.json"
parts = sorted(OUT_DIR.glob(pattern))

# Exclude checkpoint files and the merged output itself
parts = [p for p in parts
         if "_checkpoint" not in p.name
         and not p.name.startswith("gate_f_sc30-54_")]

print(f"Merging {len(parts)} files matching '{pattern}':")
for p in parts:
    print(f"  {p.name}")

if not parts:
    print("No files found. Run c7_launch_parallel.py first.")
    sys.exit(1)

all_scenarios = []
meta = None

for fp in parts:
    data = json.loads(fp.read_text(encoding="utf-8"))
    if meta is None:
        meta = {k: v for k, v in data.items() if k != "scenario_results"}
    sc_results = data["scenario_results"]
    print(f"  {fp.name}: {len(sc_results)} scenarios  "
          f"git={data.get('git_commit_short', '?')}  "
          f"beta={data.get('beta_challenge', '?')}")
    all_scenarios.extend(sc_results)

# Sort by scenario_idx and validate
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

# Build merged output
merged = dict(meta)
merged["merged_from"]     = [p.name for p in parts]
merged["n_scenarios_total"] = len(all_scenarios)
merged["scenario_results"]  = all_scenarios

# Determine merged filename: gate_f_sc30-54_<ratios>_{suffix}.json
# Infer ratio tag from first part's ratios field
ratios = meta.get("gate_f_ratios", [])
ratio_tag = "_".join(r.replace(".", "p") for r in ratios) if ratios else "unknown"

out_file = OUT_DIR / f"gate_f_sc30-54_{ratio_tag}_{suffix}.json"
out_file.write_text(json.dumps(merged, indent=2), encoding="utf-8")
size_mb = out_file.stat().st_size / 1024 / 1024
print(f"Merged output: {out_file.name}  ({size_mb:.1f} MB)")
