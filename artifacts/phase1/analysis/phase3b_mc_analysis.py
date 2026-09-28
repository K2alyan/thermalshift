#!/usr/bin/env python3
"""
Phase 3B Monte Carlo post-completion analysis.

Inputs:  phase3b_mc_checkpoint.json  (or phase3b_mc_results.json when identical)
Outputs: phase3b_mc_analysis.json    -- full per-scenario enriched data
         phase3b_mc_analysis.txt     -- human-readable report

Computes:
  1. Crossing brackets (lower/upper) per scenario/policy
  2. Win rate  P(C_FP > C_Random)
  3. Paired dC distribution -- median, p5, p95
  4. FP / Random capacity distributions
  5. Binding constraint frequencies for FP
  6. Workload sensitivity: regenerate synthetic pools (same seeds),
     compute mean_alpha, hi_alpha_frac, mean_power_kw, large_job_frac,
     mean_runtime_h; correlate with C_FP and dC
"""

import os
import pandas as pd
import numpy as np
import json, time
from pathlib import Path
from scipy import stats as spstats

ANALYSIS_DIR = Path(__file__).parent
# Set THERMALSHIFT_DATA_DIR env var to your local Frontier dataset directory.
DATA_DIR     = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

BETA_F           = 0.9569
N_BINS           = 5
T_P95_THRESHOLD  = 60.602770562770566
MC_BASE_SEED     = 200
MC_LAMBDA_SWEEP  = [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40, 1.50]
LARGE_NODE_THRESH = 512
HI_ALPHA_PCT     = 75   # percentile threshold for "high alpha" classification

CKPT = ANALYSIS_DIR / "phase3b_mc_checkpoint.json"
if not CKPT.exists():
    CKPT = ANALYSIS_DIR / "phase3b_mc_results.json"

print("=== Phase 3B MC Analysis ===\n")
print(f"Loading checkpoint: {CKPT.name}")
with open(CKPT) as f:
    raw = json.load(f)

# Normalise: checkpoint is a list; results.json wraps it
if isinstance(raw, dict):
    scenarios = raw.get("scenarios", raw)
else:
    scenarios = raw

N = len(scenarios)
print(f"Scenarios: {N}\n")

# ============================================================
# 1. Crossing brackets + binding constraints per scenario
# ============================================================
def crossing_bracket(rows, key, target=1.0):
    """Return (lower_pct, upper_pct, interp_pct, binding) for a ratio key."""
    vals = [(r["capacity_unlock_pct"], r[key])
            for r in rows if key in r and r[key] is not None and not np.isnan(r[key])]
    if not vals:
        return None, None, None, False
    xs, ys = zip(*vals)
    # lower = last point still <= target; upper = first point > target
    lower_x = None; upper_x = None
    for i, (x, y) in enumerate(zip(xs, ys)):
        if y <= target:
            lower_x = x
        else:
            if upper_x is None:
                upper_x = x
    # interpolated crossing
    interp = None
    for i in range(len(ys) - 1):
        if ys[i] <= target <= ys[i + 1]:
            frac = (target - ys[i]) / max(ys[i + 1] - ys[i], 1e-12)
            interp = float(xs[i] + frac * (xs[i + 1] - xs[i]))
            break
        if i == 0 and ys[i] >= target:
            interp = 0.0
            break
    crossed = upper_x is not None
    return lower_x, upper_x, interp, crossed

enriched = []
for sc in scenarios:
    s = sc["scenario"]
    rec = {"scenario": s, "scen_seed": sc["scen_seed"],
           "wl_seed": sc["scen_seed"] + 50000}
    for pk in ["random", "fp", "tier20"]:
        if pk not in sc:
            continue
        d   = sc[pk]
        rows = d.get("rows", [])
        lo_B, hi_B, ip_B, cx_B = crossing_bracket(rows, "B_node_ratio")
        lo_S, hi_S, ip_S, cx_S = crossing_bracket(rows, "S_node_ratio")
        lo_C, hi_C, ip_C, cx_C = crossing_bracket(rows, "B_cab_ratio_full")

        cfeas = d.get("C_feasible")
        # which constraint binds first?
        cands = {k: v for k, v in
                 [("B_thermal", ip_B), ("S_thermal", ip_S), ("cab_power", ip_C)]
                 if v is not None}
        binding = min(cands, key=cands.__getitem__) if cands else None

        # bracket for the binding constraint
        if binding == "B_thermal":  lo, hi = lo_B, hi_B
        elif binding == "S_thermal": lo, hi = lo_S, hi_S
        elif binding == "cab_power": lo, hi = lo_C, hi_C
        else:                        lo, hi = None, None

        rec[pk] = {
            "C_feasible"        : cfeas,
            "C_bracket_lo"      : lo,
            "C_bracket_hi"      : hi,
            "C_B_th"            : ip_B,
            "C_S_th"            : ip_S,
            "C_cab_full"        : ip_C,
            "binding"           : binding,
            "C_system_replay"   : d.get("C_system_replay"),
            "syn_node_hours"    : d.get("syn_node_hours"),
            "gini_util"         : d.get("gini_util"),
            "coolest10_share"   : d.get("coolest10_share"),
            "large_job_frac"    : d.get("large_job_frac"),
        }

    rec["delta_C"]    = sc.get("delta_C")
    fp_cf  = rec.get("fp",     {}).get("C_feasible")
    rnd_cf = rec.get("random", {}).get("C_feasible")
    # FP wins if: (a) both defined and FP > Random, or (b) FP is right-censored
    # (exceeded sweep range) and Random is defined
    if fp_cf is not None and rnd_cf is not None:
        rec["fp_wins"] = fp_cf > rnd_cf
    elif fp_cf is None and rnd_cf is not None:
        rec["fp_wins"] = True   # right-censored: FP > lambda_max > Random
    else:
        rec["fp_wins"] = False
    rec["fp_censored"] = (fp_cf is None and rnd_cf is not None)
    enriched.append(rec)

# ============================================================
# 2. Workload sensitivity -- regenerate synthetic pools
# ============================================================
print("Loading base data for workload pool regeneration...")
t0 = time.time()

fp_df      = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
test_df    = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")
all_jobs   = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)

meta = (all_jobs[["job_idx_int","node_count","start_time","end_time","mean_power","run_time"]]
        .rename(columns={"job_idx_int":"job_idx"}))
job_agg = (test_df.groupby("job_idx")
           .agg(F_hist_mean=("F_2024","mean"), n_cohort=("node","count"),
                T_p95_hist=("T_p95","mean"))
           .reset_index())
job_agg = job_agg.merge(meta, on="job_idx", how="left")
job_agg["power_per_node"] = job_agg["mean_power"] / job_agg["node_count"].clip(lower=1)
jobs_sorted = job_agg.sort_values("start_time").reset_index(drop=True)
n_base = len(jobs_sorted)

jobs_sorted["alpha_j"] = (jobs_sorted["T_p95_hist"]
                           - BETA_F * jobs_sorted["F_hist_mean"])
alpha_map = jobs_sorted.set_index("job_idx")["alpha_j"].to_dict()
jobs_sorted["alpha_j_col"] = jobs_sorted["job_idx"].map(alpha_map)

# Global alpha percentile threshold for "high alpha"
alpha_vals = np.array([v for v in alpha_map.values() if not np.isnan(v)])
hi_alpha_thresh = np.percentile(alpha_vals, HI_ALPHA_PCT)
print(f"  Base jobs: {n_base}  |  hi_alpha threshold (p{HI_ALPHA_PCT}): {hi_alpha_thresh:.3f}")
print(f"  ({time.time()-t0:.1f}s)")

n_extra_max = int(np.ceil((max(MC_LAMBDA_SWEEP) - 1.0) * n_base))

def sample_synthetic_pool(n_extra, seed):
    rng_s      = np.random.default_rng(seed)
    base_months = jobs_sorted["start_time"].dt.month.values
    base_hours  = jobs_sorted["start_time"].dt.hour.values
    strat_keys = list(zip(base_months.tolist(), base_hours.tolist()))
    strat_to_idxs: dict = {}
    for i, sk in enumerate(strat_keys):
        strat_to_idxs.setdefault(sk, []).append(i)
    unique_strata = sorted(strat_to_idxs.keys())
    counts = np.array([len(strat_to_idxs[s]) for s in unique_strata])
    probs  = counts / counts.sum()
    n_per  = np.round(probs * n_extra).astype(int)
    diff   = n_extra - n_per.sum()
    if diff > 0: n_per[np.argsort(-probs)[:diff]] += 1
    elif diff < 0: n_per[np.argsort(n_per)[:(-diff)]] -= 1
    chunks = []
    for sk, n_s in zip(unique_strata, n_per):
        if n_s <= 0: continue
        idxs = rng_s.choice(strat_to_idxs[sk], size=int(n_s), replace=True)
        chunks.append(jobs_sorted.iloc[idxs])
    if not chunks:
        return pd.DataFrame()
    syn = pd.concat(chunks, ignore_index=True)
    jitter = rng_s.uniform(-1800., 1800., size=len(syn))
    syn["start_time"]     = syn["start_time"] + pd.to_timedelta(jitter, unit="s")
    syn["is_synthetic"]   = True
    syn["parent_job_idx"] = syn["job_idx"].values.copy()
    syn["job_idx"]        = -(np.arange(len(syn), dtype=np.int64) + 1)
    syn["alpha_j"]        = syn["parent_job_idx"].map(alpha_map)
    syn = syn.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)
    return syn

print("\nRegenerating workload pools for workload sensitivity...")
t0 = time.time()
for rec in enriched:
    s        = rec["scenario"]
    wl_seed  = rec["wl_seed"]
    pool     = sample_synthetic_pool(n_extra_max, wl_seed)
    if len(pool) == 0:
        rec["wl"] = {}
        continue

    alpha_arr  = pool["alpha_j"].dropna().values
    power_arr  = pool["mean_power"].fillna(0).values / 1e3   # kW
    nc_arr     = pool["node_count"].fillna(1).values.astype(float)
    rt_arr     = pool["run_time"].fillna(0).values / 3600.0  # hours
    large_mask = nc_arr >= LARGE_NODE_THRESH

    rec["wl"] = {
        "mean_alpha"      : float(np.nanmean(alpha_arr)),
        "hi_alpha_frac"   : float(np.mean(alpha_arr > hi_alpha_thresh)),
        "mean_power_kw"   : float(np.nanmean(power_arr)),
        "large_job_frac"  : float(np.mean(large_mask)),
        "mean_runtime_h"  : float(np.nanmean(rt_arr)),
        "mean_nh_offered" : float(np.nanmean(nc_arr * rt_arr)),
        "n_pool"          : len(pool),
    }

print(f"  ({time.time()-t0:.1f}s)")

# ============================================================
# 3. Aggregate statistics
# ============================================================
def arr(key, pk="fp"):
    return [r[pk][key] for r in enriched if pk in r and r[pk].get(key) is not None]

def pct(a, p): return float(np.percentile(a, p)) if a else float("nan")

rnd_cf = arr("C_feasible", "random")
fp_cf  = arr("C_feasible", "fp")
dc     = [r["delta_C"] for r in enriched if r.get("delta_C") is not None]
win_n  = sum(1 for r in enriched if r.get("fp_wins"))

fp_lo  = arr("C_bracket_lo", "fp")
fp_hi  = arr("C_bracket_hi", "fp")

# Binding constraint frequencies for FP
fp_bind = [r["fp"]["binding"] for r in enriched if "fp" in r and r["fp"].get("binding")]
bind_counts = {}
for b in fp_bind:
    bind_counts[b] = bind_counts.get(b, 0) + 1

# Workload sensitivity correlations
wl_keys = ["mean_alpha", "hi_alpha_frac", "mean_power_kw",
           "large_job_frac", "mean_runtime_h", "mean_nh_offered"]

wl_corr_cfp = {}
wl_corr_dc  = {}
for wk in wl_keys:
    xs  = [r["wl"].get(wk) for r in enriched if "wl" in r and r["wl"].get(wk) is not None]
    yc  = [r["fp"].get("C_feasible") for r in enriched
           if "wl" in r and r["wl"].get(wk) is not None and "fp" in r
           and r["fp"].get("C_feasible") is not None]
    yd  = [r.get("delta_C") for r in enriched
           if "wl" in r and r["wl"].get(wk) is not None and r.get("delta_C") is not None]
    xs2 = [r["wl"].get(wk) for r in enriched
           if "wl" in r and r["wl"].get(wk) is not None and r.get("delta_C") is not None]
    if len(xs) >= 3:
        r_c, p_c = spstats.pearsonr(xs[:len(yc)], yc)
        wl_corr_cfp[wk] = (float(r_c), float(p_c), len(yc))
    if len(xs2) >= 3:
        r_d, p_d = spstats.pearsonr(xs2, yd)
        wl_corr_dc[wk] = (float(r_d), float(p_d), len(xs2))

# ============================================================
# 4. Report
# ============================================================
lines = []
SEP = "=" * 68

def ln(s=""): lines.append(s)

ln(SEP)
ln("PHASE 3B MONTE CARLO -- FINAL ANALYSIS")
ln(f"Scenarios completed: {N}/30")
ln(SEP)

# Win rate
ln()
ln("1. WIN RATE")
ln("-" * 40)
ln(f"   P(C_FP > C_Random):  {win_n}/{N}  ({win_n/N:.0%})")
ln()

# Paired dC
ln("2. PAIRED dC = C_FP - C_Random  (per scenario)")
ln("-" * 40)
ln(f"   Median:  {pct(dc,50):+.2f} pp")
ln(f"   p5:      {pct(dc, 5):+.2f} pp")
ln(f"   p95:     {pct(dc,95):+.2f} pp")
ln(f"   Min:     {min(dc):+.2f} pp" if dc else "")
ln(f"   Max:     {max(dc):+.2f} pp" if dc else "")
ln()

# FP and Random capacity
ln("3. CAPACITY DISTRIBUTIONS")
ln("-" * 40)
ln(f"   {'Metric':<30} {'Random':>10} {'FP-cap-10':>10}")
ln(f"   {'-'*50}")
for label, p in [("Median (%)", 50), ("p5 (%)", 5), ("p95 (%)", 95)]:
    ln(f"   {label:<30} {pct(rnd_cf,p):>10.2f} {pct(fp_cf,p):>10.2f}")
ln()

# Crossing brackets for FP
ln("4. FP CROSSING BRACKETS  (lower | interp | upper)")
ln("-" * 40)
for r in enriched:
    if "fp" not in r: continue
    fp = r["fp"]
    lo = fp["C_bracket_lo"]; hi = fp["C_bracket_hi"]; ip = fp["C_feasible"]
    lo_s = f"{lo:.1f}%" if lo is not None else " ---"
    hi_s = f"{hi:.1f}%" if hi is not None else ">max"
    ip_s = f"{ip:.2f}%" if ip is not None else "  n/a"
    ln(f"   s={r['scenario']:02d}: [{lo_s}, {ip_s}, {hi_s}]  bind={fp['binding']}")
ln()

# Binding constraints
ln("5. FP BINDING CONSTRAINT FREQUENCIES")
ln("-" * 40)
for k, v in sorted(bind_counts.items(), key=lambda x: -x[1]):
    ln(f"   {k:<20}: {v:2d}/{N}  ({v/N:.0%})")
ln()

# Workload sensitivity
ln("6. WORKLOAD SENSITIVITY  (Pearson r vs C_FP and vs dC)")
ln("-" * 40)
ln(f"   {'Predictor':<20} {'r(C_FP)':>9} {'p':>8}  {'r(dC)':>9} {'p':>8}  n")
ln(f"   {'-'*62}")
for wk in wl_keys:
    r_c, p_c, n_c = wl_corr_cfp.get(wk, (float("nan"), float("nan"), 0))
    r_d, p_d, n_d = wl_corr_dc.get(wk,  (float("nan"), float("nan"), 0))
    sig_c = "*" if not np.isnan(p_c) and p_c < 0.05 else " "
    sig_d = "*" if not np.isnan(p_d) and p_d < 0.05 else " "
    ln(f"   {wk:<20} {r_c:>+9.3f} {p_c:>8.3f}{sig_c} {r_d:>+9.3f} {p_d:>8.3f}{sig_d} {n_c}")
ln()

# Per-scenario table
ln("7. PER-SCENARIO TABLE")
ln("-" * 40)
hdr = f"   {'s':>3}  {'Rand%':>7}  {'FP%':>7}  {'dC':>7}  {'lo':>6}  {'hi':>6}  {'bind_FP':<12}"
ln(hdr)
for r in enriched:
    s   = r["scenario"]
    rc  = r.get("random", {}).get("C_feasible")
    fc  = r.get("fp", {}).get("C_feasible")
    dc_ = r.get("delta_C")
    lo  = r.get("fp", {}).get("C_bracket_lo")
    hi  = r.get("fp", {}).get("C_bracket_hi")
    bd  = r.get("fp", {}).get("binding", "?")
    def f(v, fmt="7.2f"): return format(v, fmt) if v is not None else "    n/a"
    lo_s = f"{lo:.1f}" if lo is not None else "  ---"
    hi_s = f"{hi:.1f}" if hi is not None else ">max"
    ln(f"   {s:>3}  {f(rc)}  {f(fc)}  {f(dc_):>7}  {lo_s:>6}  {hi_s:>6}  {bd}")
ln()
ln(SEP)

report = "\n".join(lines)
print(report)

# ============================================================
# 5. Save outputs
# ============================================================
out_path = ANALYSIS_DIR / "phase3b_mc_analysis.txt"
with open(out_path, "w", encoding="utf-8") as f:
    f.write(report)
print(f"\nReport written: {out_path}")

json_path = ANALYSIS_DIR / "phase3b_mc_analysis.json"
with open(json_path, "w") as f:
    json.dump({"N": N, "enriched": enriched,
               "win_rate": win_n / N if N > 0 else None,
               "dc_median": pct(dc, 50), "dc_p5": pct(dc, 5), "dc_p95": pct(dc, 95),
               "fp_median": pct(fp_cf, 50), "fp_p5": pct(fp_cf, 5), "fp_p95": pct(fp_cf, 95),
               "rnd_median": pct(rnd_cf, 50), "rnd_p5": pct(rnd_cf, 5), "rnd_p95": pct(rnd_cf, 95),
               "bind_counts": bind_counts,
               "wl_corr_cfp": wl_corr_cfp, "wl_corr_dc": wl_corr_dc},
              f, indent=2, default=str)
print(f"JSON written:   {json_path}")
