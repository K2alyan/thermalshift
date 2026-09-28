# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.3-F: Node-power uniform approximation validation.

For 60 sampled jobs (20 small + 20 medium + 20 large, high-power emphasis):
  - Load raw-node-power.parquet telemetry (2-second intervals, Watts)
  - Compute actual per-cabinet mean power:  P_actual_c  = sum(mean node power for c)
  - Compute uniform per-cabinet power:      P_uniform_c = (P_j / N_j) * n_nodes_in_c
  - Report: cabinet-power MAE, mean relative error, p95 error, ranking preservation.
"""

import os
import pandas as pd
import numpy as np
import re, time
import os
from pathlib import Path
from collections import defaultdict

ANALYSIS_DIR = Path(__file__).parent
DATA_DIR     = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

SMALL_MAX  = 64
MEDIUM_MAX = 512
N_PER_TIER = 20

print("=== Phase 3B.3-F: Node-power uniform approximation validation ===\n")

# --------------------------------------------------------------------------
# Load job metadata and build node->cabinet map
# --------------------------------------------------------------------------
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)
print(f"Total jobs: {len(all_jobs):,}")

_xe2_re = re.compile(r"x(\d+)c")
node_to_cabinet: dict[str, int] = {}
t0 = time.time()
for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    for hn, xn in zip(hl, str(nl).split()):
        xn = xn.strip("'[]\"")
        if hn not in node_to_cabinet:
            m = _xe2_re.match(xn)
            if m:
                node_to_cabinet[hn] = int(m.group(1))
print(f"Cabinet map: {len(node_to_cabinet):,} nodes, "
      f"{len(set(node_to_cabinet.values()))} cabinets  ({time.time()-t0:.1f}s)")

# --------------------------------------------------------------------------
# Filter to jobs suitable for validation
# --------------------------------------------------------------------------
jobs = all_jobs.dropna(subset=["mean_power"]).copy()
jobs = jobs[jobs["mean_power"].astype(float) > 0].copy()
jobs["mean_power_f"] = jobs["mean_power"].astype(float)
jobs["node_count_i"] = jobs["node_count"].astype(int)

# date_dir column — derive from start_time if not present
if "date_dir" not in jobs.columns:
    jobs["date_dir"] = pd.to_datetime(jobs["start_time"], utc=True).dt.strftime("%Y-%m-%d")

def classify_size(nc):
    if nc <= SMALL_MAX:   return "small"
    if nc <= MEDIUM_MAX:  return "medium"
    return "large"

jobs["size_tier"] = jobs["node_count_i"].apply(classify_size)

def telemetry_path(row):
    jidx = str(row["job_idx"]).zfill(6)
    return DATA_DIR / "job-telemetry" / str(row["date_dir"]) / jidx / f"{jidx}-cleaned-power.parquet"

# --------------------------------------------------------------------------
# Select N_PER_TIER jobs per tier (highest mean_power first)
# --------------------------------------------------------------------------
selected_rows = []
print()
for tier in ["small", "medium", "large"]:
    tier_jobs = (jobs[jobs["size_tier"] == tier]
                 .sort_values("mean_power_f", ascending=False)
                 .reset_index(drop=True))
    count = 0
    for _, jrow in tier_jobs.iterrows():
        if count >= N_PER_TIER:
            break
        if telemetry_path(jrow).exists():
            selected_rows.append(jrow)
            count += 1
    print(f"  {tier:6s}: {count} jobs selected  "
          f"(power range: {tier_jobs['mean_power_f'].iloc[0]/1e3:.0f} kW - "
          f"{tier_jobs['mean_power_f'].iloc[min(count,len(tier_jobs))-1]/1e3:.0f} kW)")

print(f"\nTotal jobs with telemetry: {len(selected_rows)}")

# --------------------------------------------------------------------------
# Validation loop
# --------------------------------------------------------------------------
_node_re = re.compile(r"^(frontier\d+)_node$")

def spearman_rho(x, y):
    n = len(x)
    if n < 2:
        return float("nan")
    rx = np.empty(n, dtype=float)
    rx[np.argsort(x)] = np.arange(n, dtype=float)
    ry = np.empty(n, dtype=float)
    ry[np.argsort(y)] = np.arange(n, dtype=float)
    mx, my = rx.mean(), ry.mean()
    num = ((rx - mx) * (ry - my)).sum()
    den = np.sqrt(((rx - mx) ** 2).sum() * ((ry - my) ** 2).sum())
    return float(num / den) if den > 0 else float("nan")

tier_stats: dict[str, dict] = {t: {"abs": [], "rel": [], "rho": []} for t in ["small", "medium", "large"]}
all_abs: list[float] = []
all_rel: list[float] = []
all_rho: list[float] = []
n_jobs_ok = 0

print("\nProcessing jobs...")
for jrow in selected_rows:
    tier = classify_size(int(jrow["node_count_i"]))
    p = telemetry_path(jrow)
    try:
        telem = pd.read_parquet(p)
    except Exception as e:
        print(f"  WARNING: {p.name}: {e}")
        continue

    # Map telemetry node columns to cabinet
    col_to_cab: dict[str, int] = {}
    for col in telem.columns:
        m = _node_re.match(col)
        if m:
            c = node_to_cabinet.get(m.group(1), -1)
            if c >= 0:
                col_to_cab[col] = c

    if not col_to_cab:
        continue

    # Per-cabinet actual power = sum of per-node mean powers
    cab_actual: dict[int, float] = defaultdict(float)
    for col, c in col_to_cab.items():
        vals = telem[col].dropna().values
        if len(vals) > 0:
            cab_actual[c] += float(np.mean(vals.astype(float)))

    # Per-cabinet uniform power = ppn * n_nodes_in_cabinet
    P_j  = float(jrow["mean_power_f"])
    N_j  = max(1, int(jrow["node_count_i"]))
    ppn  = P_j / N_j
    cab_ncount: dict[int, int] = defaultdict(int)
    for hn in jrow["host_list"]:
        c = node_to_cabinet.get(hn, -1)
        if c >= 0:
            cab_ncount[c] += 1
    cab_uniform = {c: ppn * n for c, n in cab_ncount.items()}

    common = sorted(set(cab_actual) & set(cab_uniform))
    if not common:
        continue

    acts = np.array([cab_actual[c]  for c in common])
    unis = np.array([cab_uniform[c] for c in common])
    ae   = np.abs(unis - acts)
    re_  = ae / np.maximum(acts, 1.0)

    tier_stats[tier]["abs"].extend(ae.tolist())
    tier_stats[tier]["rel"].extend(re_.tolist())
    all_abs.extend(ae.tolist())
    all_rel.extend(re_.tolist())

    if len(common) >= 2:
        rho = spearman_rho(acts, unis)
        if not np.isnan(rho):
            tier_stats[tier]["rho"].append(rho)
            all_rho.append(rho)

    n_jobs_ok += 1

# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
def _stats(ae, re_, rho_list, label):
    ae = np.array(ae); re_ = np.array(re_)
    print(f"\n  {label}  ({len(ae):,} cabinet-job pairs)")
    print(f"    MAE:              {np.mean(ae):>9,.0f} W  ({np.mean(ae)/1e3:.2f} kW)")
    print(f"    Mean rel error:   {np.mean(re_):>9.1%}")
    print(f"    p95 abs error:    {np.percentile(ae, 95):>9,.0f} W")
    print(f"    p95 rel error:    {np.percentile(re_, 95):>9.1%}")
    if rho_list:
        ra = np.array(rho_list)
        print(f"    Spearman rho (cabinet ranking, {len(ra)} multi-cab jobs):")
        print(f"      mean={np.mean(ra):.3f}  median={np.median(ra):.3f}  "
              f"p10={np.percentile(ra,10):.3f}  rho>=0.9: {np.mean(ra>=0.9):.0%}")

print("\n" + "=" * 60)
print("RESULTS: P_uniform vs P_actual (cabinet mean power)")
print("=" * 60)
print(f"\n  Jobs successfully validated: {n_jobs_ok}")

for tier in ["small", "medium", "large"]:
    d = tier_stats[tier]
    if d["abs"]:
        _stats(d["abs"], d["rel"], d["rho"], tier.upper())

_stats(all_abs, all_rel, all_rho, "OVERALL")

# Verdict
print("\n" + "=" * 60)
print("VERDICT")
print("=" * 60)
mae_kw  = np.mean(all_abs) / 1e3 if all_abs else float("nan")
mre_pct = np.mean(all_rel) * 100 if all_rel else float("nan")
rho_med = np.median(all_rho) if all_rho else float("nan")

if mre_pct < 10 and rho_med > 0.8:
    verdict = "ADEQUATE"
elif mre_pct < 20 and rho_med > 0.6:
    verdict = "MARGINAL"
else:
    verdict = "INSUFFICIENT"
print(f"  Uniform approximation: {verdict}")
print(f"  (MAE={mae_kw:.1f} kW, mean rel error={mre_pct:.1f}%, median Spearman rho={rho_med:.3f})")
print(f"  Full-cabinet p99 range 132-181 kW; MAE should be well below the ~49 kW spread")
print(f"  for the uniform model to be defensible as a cabinet-power constraint driver.")
print()
