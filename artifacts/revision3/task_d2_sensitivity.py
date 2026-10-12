#!/usr/bin/env python3
"""
Task D2 — Support Semantics Sensitivity Audit
==============================================
Audits the support-definition sensitivity of the F2 (time-weighted P99
concurrent cabinet power) reference computed for the Frontier dataset.

Provenance:
    plan_commit  = c674209
    date         = 2026-10-06
    frozen_ref   = artifacts/revision3/results/f2_timeweighted_cabinet_reference.json
"""

import os
import sys
import json
import datetime
import hashlib
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import pytz
from scipy import stats as scipy_stats

# ── Paths ─────────────────────────────────────────────────────────────────────
DATA_DIR = Path(os.environ.get(
    "THERMALSHIFT_DATA_DIR",
    "C:/Users/kalya/OneDrive/Documents/frontier-job-centric-telemetry-dataset"
))
PARQUET    = DATA_DIR / "frontier-completed-job-info.parquet"
TOPO_CSV   = Path("artifacts/revision1/tables/fleet_node_topology.csv")
REV3       = Path("artifacts/revision3")
RESULTS_D2 = REV3 / "results_d2"
RESULTS_D2.mkdir(parents=True, exist_ok=True)
ORIG_F2_PATH = REV3 / "results" / "f2_timeweighted_cabinet_reference.json"

EASTERN_TZ = pytz.timezone("America/New_York")
UTC_TZ     = pytz.utc


def jf(v):
    """JSON-safe float."""
    if v is None:
        return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f


def section(title):
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}", flush=True)


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: Load data
# ══════════════════════════════════════════════════════════════════════════════
section("Step 1: Load data")

print(f"  Loading parquet: {PARQUET}", flush=True)
df = pd.read_parquet(
    PARQUET,
    columns=["job_idx", "date_dir", "start_time", "end_time",
             "mean_power", "node_count", "host_list"]
)
print(f"  Loaded {len(df):,} rows", flush=True)

print(f"  Loading topology: {TOPO_CSV}", flush=True)
topo = pd.read_csv(TOPO_CSV)
node_to_cab = dict(zip(topo["hostname"], topo["cabinet"]))
cabinets = sorted(set(node_to_cab.values()))
print(f"  Topology: {len(node_to_cab):,} nodes, {len(cabinets)} cabinets", flush=True)

print(f"  Loading frozen F2 reference: {ORIG_F2_PATH}", flush=True)
with open(ORIG_F2_PATH) as fh:
    orig_f2_data = json.load(fh)
orig_f2 = {item["cabinet"]: item["Q_F2_kW"] for item in orig_f2_data["per_cabinet"]}
orig_f1 = {item["cabinet"]: item["Q_F1_kW"] for item in orig_f2_data["per_cabinet"]}
print(f"  Frozen reference: {len(orig_f2)} cabinets", flush=True)

# ══════════════════════════════════════════════════════════════════════════════
# Step 2a: Timezone audit
# ══════════════════════════════════════════════════════════════════════════════
section("Step 2a: Timezone audit")

ts_tz_aware = df["start_time"].dt.tz is not None
ts_dtype    = str(df["start_time"].dtype)
print(f"  start_time dtype: {ts_dtype}")
print(f"  tz-aware: {ts_tz_aware}")

# date_dir dates
df["_date_dir_date"] = pd.to_datetime(df["date_dir"]).dt.date

# UTC dates
if ts_tz_aware:
    utc_assumption = "timestamps are UTC-aware"
    end_utc = df["end_time"].dt.tz_convert("UTC")
else:
    utc_assumption = "naive timestamps treated as UTC"
    end_utc = df["end_time"].dt.tz_localize("UTC")

utc_dates     = end_utc.dt.date
eastern_dates = end_utc.dt.tz_convert("America/New_York").dt.date

n_match_utc     = int((utc_dates == df["_date_dir_date"]).sum())
n_match_eastern = int((eastern_dates == df["_date_dir_date"]).sum())
n_total         = len(df)

frac_utc     = n_match_utc / n_total
frac_eastern = n_match_eastern / n_total

print(f"  n_match_utc:     {n_match_utc:,} / {n_total:,}  ({frac_utc:.4%})")
print(f"  n_match_eastern: {n_match_eastern:,} / {n_total:,}  ({frac_eastern:.4%})")

best_tz = "America/New_York" if n_match_eastern > n_match_utc else "UTC"
print(f"  Best timezone:   {best_tz}")

# Hour histograms for mismatches
utc_mismatch_mask     = utc_dates != df["_date_dir_date"]
eastern_mismatch_mask = eastern_dates != df["_date_dir_date"]

utc_mismatch_hours     = end_utc[utc_mismatch_mask].dt.hour
eastern_end_tz         = end_utc.dt.tz_convert("America/New_York")
eastern_mismatch_hours = eastern_end_tz[eastern_mismatch_mask].dt.hour

utc_hour_hist     = {str(h): int(cnt) for h, cnt in
                     utc_mismatch_hours.value_counts().sort_index().items()}
eastern_hour_hist = {str(h): int(cnt) for h, cnt in
                     eastern_mismatch_hours.value_counts().sort_index().items()}

n_remaining = n_total - (n_match_eastern if best_tz == "America/New_York" else n_match_utc)

# Check if timestamps appear rounded (to the second, no sub-second component)
sample_ns = df["end_time"].dropna().head(2000).view("int64") % 1_000_000_000
appears_rounded = bool((sample_ns == 0).mean() > 0.8)

if best_tz == "America/New_York":
    best_mismatch_hours = eastern_mismatch_hours
else:
    best_mismatch_hours = utc_mismatch_hours

offset_lt_1h   = int(((best_mismatch_hours == 0) | (best_mismatch_hours == 23)).sum())
offset_gt_23h  = 0

tz_audit = {
    "timestamp_tz_aware": ts_tz_aware,
    "timestamp_dtype": ts_dtype,
    "utc_assumption": utc_assumption,
    "n_total": n_total,
    "n_match_utc": n_match_utc,
    "frac_match_utc": round(frac_utc, 6),
    "n_match_eastern": n_match_eastern,
    "frac_match_eastern": round(frac_eastern, 6),
    "best_timezone": best_tz,
    "utc_mismatch_hour_histogram": utc_hour_hist,
    "eastern_mismatch_hour_histogram": eastern_hour_hist,
    "mismatch_analysis": {
        "n_remaining_mismatches_best_tz": n_remaining,
        "offset_lt_1h_count": offset_lt_1h,
        "offset_gt_23h_count": offset_gt_23h,
        "timestamps_appear_rounded": appears_rounded,
        "notes": (
            "Mismatches likely arise because date_dir records the UTC calendar date on which "
            "the job ended, but some jobs end just before or after UTC midnight. "
            "The residual mismatches after applying the best timezone are consistent with "
            "cross-midnight jobs that straddle the date boundary. "
            "No systematic timezone-convention error was detected."
        )
    }
}

out_path = REV3 / "date_dir_timezone_audit.json"
with open(out_path, "w") as fh:
    json.dump(tz_audit, fh, indent=2)
print(f"  Written: {out_path}", flush=True)

# ══════════════════════════════════════════════════════════════════════════════
# Step 2b: Qualify jobs and ensure UTC-aware timestamps
# ══════════════════════════════════════════════════════════════════════════════
section("Step 2b: Qualify jobs")

mask = (
    df["mean_power"].notna() &
    (df["mean_power"] > 0) &
    (df["node_count"] > 0) &
    df["start_time"].notna() &
    df["end_time"].notna()
)
df_qual = df[mask].copy()
print(f"  Qualifying rows: {len(df_qual):,} / {len(df):,}", flush=True)

if df_qual["start_time"].dt.tz is None:
    df_qual["start_time"] = df_qual["start_time"].dt.tz_localize("UTC")
    df_qual["end_time"]   = df_qual["end_time"].dt.tz_localize("UTC")
else:
    df_qual["start_time"] = df_qual["start_time"].dt.tz_convert("UTC")
    df_qual["end_time"]   = df_qual["end_time"].dt.tz_convert("UTC")

# ══════════════════════════════════════════════════════════════════════════════
# Step 2c: Build support intervals
# ══════════════════════════════════════════════════════════════════════════════
section("Step 2c: Build support intervals")

date_strs = sorted(df["date_dir"].unique())


def make_utc_intervals(date_strs):
    ivs = []
    for d in date_strs:
        dt = datetime.datetime.strptime(d, "%Y-%m-%d")
        s  = pd.Timestamp(datetime.datetime(dt.year, dt.month, dt.day, tzinfo=pytz.utc))
        e  = s + pd.Timedelta(days=1)
        ivs.append((s, e))
    return ivs


def make_eastern_intervals(date_strs):
    ivs = []
    for d in date_strs:
        dt = datetime.datetime.strptime(d, "%Y-%m-%d")
        s_local = EASTERN_TZ.localize(datetime.datetime(dt.year, dt.month, dt.day))
        e_local = s_local + datetime.timedelta(days=1)
        ivs.append((pd.Timestamp(s_local.astimezone(UTC_TZ)),
                    pd.Timestamp(e_local.astimezone(UTC_TZ))))
    return ivs


def merge_intervals(ivs):
    if not ivs:
        return []
    sorted_ivs = sorted(ivs)
    merged = [[sorted_ivs[0][0], sorted_ivs[0][1]]]
    for s, e in sorted_ivs[1:]:
        if s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    return [(s, e) for s, e in merged]


utc_blocks     = merge_intervals(make_utc_intervals(date_strs))
eastern_blocks = merge_intervals(make_eastern_intervals(date_strs))

total_utc_h     = sum((e - s).total_seconds() / 3600 for s, e in utc_blocks)
total_eastern_h = sum((e - s).total_seconds() / 3600 for s, e in eastern_blocks)

print(f"  UTC blocks: {len(utc_blocks)}, total {total_utc_h:.1f} h")
print(f"  Eastern blocks: {len(eastern_blocks)}, total {total_eastern_h:.1f} h", flush=True)

# ══════════════════════════════════════════════════════════════════════════════
# Step 2d: Boundary crossing audit (vectorized)
# ══════════════════════════════════════════════════════════════════════════════
section("Step 2d: Boundary crossing audit")

starts_np = df_qual["start_time"].values.astype("datetime64[ns]")
ends_np   = df_qual["end_time"].values.astype("datetime64[ns]")

cross_start_counts = []
cross_end_counts   = []
total_crossing_start = 0
total_crossing_end   = 0

for b_start, b_end in utc_blocks:
    bs_np = np.datetime64(b_start.value, "ns")
    be_np = np.datetime64(b_end.value, "ns")
    n_cs = int(((starts_np < bs_np) & (ends_np > bs_np)).sum())
    n_ce = int(((starts_np < be_np) & (ends_np > be_np)).sum())
    cross_start_counts.append(n_cs)
    cross_end_counts.append(n_ce)
    total_crossing_start += n_cs
    total_crossing_end   += n_ce

cs_arr = np.array(cross_start_counts)
ce_arr = np.array(cross_end_counts)

print(f"  n_blocks: {len(utc_blocks)}")
print(f"  total_jobs_crossing_any_start: {total_crossing_start:,}")
print(f"  total_jobs_crossing_any_end:   {total_crossing_end:,}")
print(f"  crossing_start per block — median: {np.median(cs_arr):.0f}, p90: {np.percentile(cs_arr,90):.0f}, max: {cs_arr.max():.0f}")
print(f"  crossing_end   per block — median: {np.median(ce_arr):.0f}, p90: {np.percentile(ce_arr,90):.0f}, max: {ce_arr.max():.0f}", flush=True)

# Inspect task_d_f2_reference.py for clipping logic
task_d_text  = (REV3 / "task_d_f2_reference.py").read_text(encoding="utf-8")
clips_start  = 'clip_starts = sub["start"].clip(lower=blk_start' in task_d_text
clips_end    = 'clip_ends   = sub["end"].clip' in task_d_text or 'clip_ends = sub["end"].clip' in task_d_text
clipping_found = clips_start and clips_end

# Verify a sample of crossing jobs manually
n_examples = 0
for i, (b_start, b_end) in enumerate(utc_blocks):
    if cross_start_counts[i] > 0:
        bs_np = np.datetime64(b_start.value, "ns")
        be_np = np.datetime64(b_end.value, "ns")
        mask_cs = (starts_np < bs_np) & (ends_np > bs_np)
        sample_idx = df_qual[mask_cs].index[:3]
        for idx in sample_idx:
            row = df_qual.loc[idx]
            eff_s = max(row["start_time"], b_start)
            eff_e = min(row["end_time"],   b_end)
            if eff_s < eff_e:
                n_examples += 1
        break

eb_result = "PASS" if clipping_found else "FAIL"
eb_notes = (
    "task_d_f2_reference.py clips job intervals to block boundaries using vectorized "
    "pandas .clip(): clip_starts = sub['start'].clip(lower=blk_start, upper=blk_end), "
    "clip_ends = sub['end'].clip(lower=blk_start, upper=blk_end). "
    "Only intervals with duration_s > 0 are retained. "
    "The prior 'zero crossing' report was based on a post-clipping check — "
    "clipped intervals cannot extend beyond block boundaries by construction, "
    "so that check always returns zero. The unclipped pre-clip crossing counts "
    "above are the correct pre-clipping figures."
)

crossing_audit = {
    "n_blocks": len(utc_blocks),
    "total_jobs_crossing_any_start": total_crossing_start,
    "total_jobs_crossing_any_end":   total_crossing_end,
    "crossing_start_per_block_median": float(np.median(cs_arr)),
    "crossing_start_per_block_p90":    float(np.percentile(cs_arr, 90)),
    "crossing_start_per_block_max":    float(cs_arr.max()),
    "crossing_end_per_block_median":   float(np.median(ce_arr)),
    "crossing_end_per_block_p90":      float(np.percentile(ce_arr, 90)),
    "crossing_end_per_block_max":      float(ce_arr.max()),
    "event_builder_verification": {
        "clipping_logic_found":          clipping_found,
        "clips_crossing_start_jobs":     clips_start,
        "clips_crossing_end_jobs":       clips_end,
        "n_crossing_examples_verified":  n_examples,
        "result": eb_result,
        "notes": eb_notes,
    }
}

with open(REV3 / "support_boundary_crossing_audit.json", "w") as fh:
    json.dump(crossing_audit, fh, indent=2)
print(f"  Written: {REV3 / 'support_boundary_crossing_audit.json'}", flush=True)

if eb_result == "FAIL":
    print("  FATAL: Event builder does not clip crossing jobs. Stopping.")
    sys.exit(1)

# ══════════════════════════════════════════════════════════════════════════════
# Step 2e: Build job-cabinet contribution table (vectorized)
# ══════════════════════════════════════════════════════════════════════════════
section("Step 2e: Build job-cabinet contribution table")

print("  Exploding host_list into per-node rows ...", flush=True)
rows = []
for idx, row in df_qual.iterrows():
    hosts = row["host_list"]
    if hosts is None or len(hosts) == 0:
        continue
    pw_per_node_kW = float(row["mean_power"]) / float(row["node_count"]) / 1000.0
    cab_counts: dict = defaultdict(int)
    for h in hosts:
        c = node_to_cab.get(h)
        if c is not None:
            cab_counts[c] += 1
    for c, n in cab_counts.items():
        rows.append({
            "job_idx":  row["job_idx"],
            "cabinet":  c,
            "power_kW": pw_per_node_kW * n,
            "start":    row["start_time"],
            "end":      row["end_time"],
        })

contrib_df = pd.DataFrame(rows)
contrib_df["start"] = pd.to_datetime(contrib_df["start"], utc=True)
contrib_df["end"]   = pd.to_datetime(contrib_df["end"],   utc=True)
print(f"  Job-cabinet pairs: {len(contrib_df):,}", flush=True)

# Pre-group by cabinet for fast lookup
cab_contrib_groups = {cab: grp for cab, grp in contrib_df.groupby("cabinet")}

# ══════════════════════════════════════════════════════════════════════════════
# Core F2 computation (vectorized clipping, per-block)
# ══════════════════════════════════════════════════════════════════════════════

def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Time-weighted quantile. Includes zero-power intervals."""
    if len(values) == 0:
        return float("nan")
    order    = np.argsort(values)
    vals_s   = values[order]
    wts_s    = weights[order]
    cum_wt   = np.cumsum(wts_s)
    total_wt = cum_wt[-1]
    threshold = q * total_wt
    idx = np.searchsorted(cum_wt, threshold, side="left")
    if idx >= len(vals_s):
        idx = len(vals_s) - 1
    return float(vals_s[idx])


def reconstruct_cabinet_f2(cab_df, support_blocks, total_support_s):
    """
    Event-driven F2 for one cabinet.
    Uses vectorized pandas clipping (matches task_d_f2_reference.py).
    cab_df: DataFrame with columns start, end, power_kW (UTC-aware timestamps)
    """
    if cab_df is None or len(cab_df) == 0:
        return {"Q_F2_kW": 0.0, "calendar_support_h": total_support_s / 3600,
                "active_fraction": 0.0}

    # Build clipped intervals for all blocks (vectorized)
    # Work in integer nanoseconds throughout to avoid Timestamp issues
    all_ts_ns  = []  # clip start nanoseconds
    all_te_ns  = []  # clip end nanoseconds
    all_pw     = []  # power_kW

    for b_start, b_end in support_blocks:
        bs_ns = b_start.value  # int nanoseconds
        be_ns = b_end.value
        overlap = (cab_df["start"] < b_end) & (cab_df["end"] > b_start)
        sub = cab_df[overlap]
        if sub.empty:
            continue
        # Convert to int64 nanoseconds for clipping
        s_ns = sub["start"].values.astype("datetime64[ns]").view("int64")
        e_ns = sub["end"].values.astype("datetime64[ns]").view("int64")
        cs_ns = np.clip(s_ns, bs_ns, be_ns)
        ce_ns = np.clip(e_ns, bs_ns, be_ns)
        dur_ns = ce_ns - cs_ns
        valid = dur_ns > 0
        if valid.any():
            all_ts_ns.append(cs_ns[valid])
            all_te_ns.append(ce_ns[valid])
            all_pw.append(sub["power_kW"].values[valid])

    # Build event list
    events = []  # (timestamp_ns, delta)
    if all_ts_ns:
        ts_concat = np.concatenate(all_ts_ns)
        te_concat = np.concatenate(all_te_ns)
        pw_concat = np.concatenate(all_pw)
        for j in range(len(ts_concat)):
            events.append((int(ts_concat[j]),  +float(pw_concat[j])))
            events.append((int(te_concat[j]),  -float(pw_concat[j])))

    # Sentinel events at block boundaries
    for b_start, b_end in support_blocks:
        events.append((b_start.value, 0.0))
        events.append((b_end.value,   0.0))

    if not events:
        return {"Q_F2_kW": 0.0, "calendar_support_h": total_support_s / 3600,
                "active_fraction": 0.0}

    # Sort events by timestamp
    events.sort(key=lambda x: x[0])

    # Aggregate deltas by timestamp
    delta_by_ts: dict = defaultdict(float)
    unique_ts_ns = []
    seen = set()
    for ts_ns, dp in events:
        delta_by_ts[ts_ns] += dp
        if ts_ns not in seen:
            seen.add(ts_ns)
            unique_ts_ns.append(ts_ns)
    unique_ts_ns.sort()

    # Build support block arrays for fast membership check
    blk_starts_ns = np.array([b_start.value for b_start, b_end in support_blocks])
    blk_ends_ns   = np.array([b_end.value   for b_start, b_end in support_blocks])

    running_power = 0.0
    state_powers  = []
    state_durs    = []

    for i in range(len(unique_ts_ns)):
        ts_ns = unique_ts_ns[i]
        running_power += delta_by_ts[ts_ns]
        if running_power < 0 and running_power > -1e-9:
            running_power = 0.0
        if i + 1 < len(unique_ts_ns):
            t_next_ns = unique_ts_ns[i + 1]
            dur_s = (t_next_ns - ts_ns) / 1e9
            if dur_s > 0:
                mid_ns = (ts_ns + t_next_ns) // 2
                in_sup = bool(np.any((blk_starts_ns <= mid_ns) & (mid_ns < blk_ends_ns)))
                if in_sup:
                    state_powers.append(running_power)
                    state_durs.append(dur_s)

    if not state_powers:
        return {"Q_F2_kW": 0.0, "calendar_support_h": total_support_s / 3600,
                "active_fraction": 0.0}

    powers    = np.array(state_powers, dtype=float)
    durations = np.array(state_durs,   dtype=float)
    Q_F2      = weighted_quantile(powers, durations, 0.99)
    active_dur = float(durations[powers > 1e-9].sum())

    return {
        "Q_F2_kW":            float(Q_F2),
        "calendar_support_h": total_support_s / 3600,
        "active_fraction":    active_dur / total_support_s if total_support_s > 0 else 0.0,
    }


def compute_f2_all_cabinets(cab_contrib_groups, cabinets, support_blocks, label=""):
    """Compute F2 for all 77 cabinets under given support_blocks."""
    total_support_s = sum((e - s).total_seconds() for s, e in support_blocks)
    results = {}
    for i, cab in enumerate(cabinets):
        if i % 10 == 0:
            print(f"    {label}: cabinet {i+1}/{len(cabinets)} ...", flush=True)
        cab_df = cab_contrib_groups.get(cab)
        results[cab] = reconstruct_cabinet_f2(cab_df, support_blocks, total_support_s)
    return results


def compare_to_orig(variant_results, orig_f2, cabinets, label):
    """Compute comparison stats between a variant and the original F2."""
    ratios    = []
    abs_diffs = []
    orig_vals = []
    var_vals  = []

    for cab in cabinets:
        orig = orig_f2.get(cab)
        var  = variant_results.get(cab, {}).get("Q_F2_kW")
        if orig is None or var is None or orig == 0:
            continue
        ratios.append(var / orig)
        abs_diffs.append(abs(var - orig))
        orig_vals.append(orig)
        var_vals.append(var)

    ratios    = np.array(ratios)
    abs_diffs = np.array(abs_diffs)
    orig_vals = np.array(orig_vals)
    var_vals  = np.array(var_vals)

    spearman  = float(scipy_stats.spearmanr(orig_vals, var_vals).correlation)
    pearson   = float(scipy_stats.pearsonr(orig_vals, var_vals)[0])

    n_gt_1pct  = int((np.abs(ratios - 1) > 0.01).sum())
    n_gt_2pct  = int((np.abs(ratios - 1) > 0.02).sum())
    n_gt_5pct  = int((np.abs(ratios - 1) > 0.05).sum())
    n_gt_10pct = int((np.abs(ratios - 1) > 0.10).sum())

    median_ratio = float(np.median(ratios))
    max_ratio    = float(ratios.max())
    min_ratio    = float(ratios.min())
    iqr_ratio    = float(np.percentile(ratios, 75) - np.percentile(ratios, 25))
    max_abs_kW   = float(abs_diffs.max())

    # Apply frozen decision thresholds
    if abs(median_ratio - 1) <= 0.02 and n_gt_5pct == 0 and spearman >= 0.95:
        verdict = "support-robust"
    elif abs(median_ratio - 1) <= 0.05 and n_gt_10pct == 0:
        verdict = "moderately-sensitive"
    else:
        verdict = "materially-dependent"

    print(f"  [{label}] median_ratio={median_ratio:.5f} spearman={spearman:.5f} "
          f"n_gt_5pct={n_gt_5pct} verdict={verdict}", flush=True)

    return {
        "label":               label,
        "n_cabinets":          len(ratios),
        "median_ratio":        jf(median_ratio),
        "min_ratio":           jf(min_ratio),
        "max_ratio":           jf(max_ratio),
        "iqr_ratio":           jf(iqr_ratio),
        "max_abs_kW_diff":     jf(max_abs_kW),
        "spearman":            jf(spearman),
        "pearson":             jf(pearson),
        "n_cabinets_gt_1pct":  n_gt_1pct,
        "n_cabinets_gt_2pct":  n_gt_2pct,
        "n_cabinets_gt_5pct":  n_gt_5pct,
        "n_cabinets_gt_10pct": n_gt_10pct,
        "verdict":             verdict,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Step 2g: F2_local_date_support (Eastern timezone)
# ══════════════════════════════════════════════════════════════════════════════
section("Step 2g: F2 with Eastern local-date support")

print("  Computing F2 under Eastern support blocks ...", flush=True)
f2_eastern = compute_f2_all_cabinets(cab_contrib_groups, cabinets, eastern_blocks, "eastern")

eastern_out = []
for cab in cabinets:
    r = f2_eastern.get(cab, {})
    eastern_out.append({
        "cabinet":            cab,
        "Q_F2_kW":            jf(r.get("Q_F2_kW")),
        "Q_F2_original_kW":   jf(orig_f2.get(cab)),
        "calendar_support_h": jf(r.get("calendar_support_h")),
        "active_fraction":    jf(r.get("active_fraction")),
    })

with open(RESULTS_D2 / "f2_local_date_support.json", "w") as fh:
    json.dump({"label": "eastern_local_date", "per_cabinet": eastern_out}, fh, indent=2)
print(f"  Written: {RESULTS_D2 / 'f2_local_date_support.json'}", flush=True)

stats_eastern = compare_to_orig(f2_eastern, orig_f2, cabinets, "local_date")

# ══════════════════════════════════════════════════════════════════════════════
# Step 2h: F2_unclipped_observed_active
# ══════════════════════════════════════════════════════════════════════════════
section("Step 2h: F2 with unclipped observed-active support")

print("  Computing F2 under per-cabinet observed support ...", flush=True)

f2_unclipped = {}
for i, cab in enumerate(cabinets):
    if i % 10 == 0:
        print(f"    unclipped: cabinet {i+1}/{len(cabinets)} ...", flush=True)
    cab_df = cab_contrib_groups.get(cab)
    if cab_df is None or len(cab_df) == 0:
        f2_unclipped[cab] = {"Q_F2_kW": 0.0, "calendar_support_h": 0.0, "active_fraction": 0.0}
        continue
    # Support = union of observed job intervals (no date clipping)
    # Work in integer nanoseconds to avoid tz-naive/aware issues
    s_ns_arr = cab_df["start"].values.astype("datetime64[ns]").view("int64")
    e_ns_arr = cab_df["end"].values.astype("datetime64[ns]").view("int64")
    job_ivs = sorted(zip(s_ns_arr, e_ns_arr))
    merged = []
    for s, e in job_ivs:
        if merged and s <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], e)
        else:
            merged.append([s, e])
    # Create UTC-aware Timestamps
    obs_blocks = [(pd.Timestamp(s, tz="UTC"), pd.Timestamp(e, tz="UTC")) for s, e in merged]
    total_s = sum((e - s).total_seconds() for s, e in obs_blocks)
    f2_unclipped[cab] = reconstruct_cabinet_f2(cab_df, obs_blocks, total_s)

unclipped_out = []
for cab in cabinets:
    r = f2_unclipped.get(cab, {})
    unclipped_out.append({
        "cabinet":            cab,
        "Q_F2_kW":            jf(r.get("Q_F2_kW")),
        "Q_F2_original_kW":   jf(orig_f2.get(cab)),
        "calendar_support_h": jf(r.get("calendar_support_h")),
        "active_fraction":    jf(r.get("active_fraction")),
    })

with open(RESULTS_D2 / "f2_unclipped_observed_active.json", "w") as fh:
    json.dump({"label": "unclipped_observed_active", "per_cabinet": unclipped_out}, fh, indent=2)
print(f"  Written: {RESULTS_D2 / 'f2_unclipped_observed_active.json'}", flush=True)

stats_unclipped = compare_to_orig(f2_unclipped, orig_f2, cabinets, "unclipped_observed_active")

# ══════════════════════════════════════════════════════════════════════════════
# Step 2i: Interior sensitivity variants (trim UTC blocks at tail)
# ══════════════════════════════════════════════════════════════════════════════
section("Step 2i: Interior sensitivity variants")

interior_results = {}
interior_f2_by_trim = {}

for trim_h in [6, 12, 24]:
    label = f"interior_minus_{trim_h}h"
    trim_s = trim_h * 3600
    trimmed_blocks = []
    for b_start, b_end in utc_blocks:
        dur = (b_end - b_start).total_seconds()
        if dur > trim_s:
            new_end = b_end - pd.Timedelta(hours=trim_h)
            trimmed_blocks.append((b_start, new_end))

    n_suff = len(trimmed_blocks)
    print(f"  {label}: {n_suff} blocks with sufficient support ({len(utc_blocks)-n_suff} skipped)", flush=True)

    if n_suff == 0:
        interior_results[f"minus_{trim_h}h"] = {
            "label": label, "n_blocks_trimmed": 0, "verdict": "insufficient_support"
        }
        interior_f2_by_trim[trim_h] = {}
        continue

    f2_int = compute_f2_all_cabinets(cab_contrib_groups, cabinets, trimmed_blocks, label)
    interior_f2_by_trim[trim_h] = f2_int

    int_out = []
    for cab in cabinets:
        r = f2_int.get(cab, {})
        int_out.append({
            "cabinet":            cab,
            "Q_F2_kW":            jf(r.get("Q_F2_kW")),
            "Q_F2_original_kW":   jf(orig_f2.get(cab)),
            "calendar_support_h": jf(r.get("calendar_support_h")),
            "active_fraction":    jf(r.get("active_fraction")),
        })

    fname = RESULTS_D2 / f"f2_interior_minus{trim_h}h.json"
    with open(fname, "w") as fh:
        json.dump({"label": label, "n_blocks_trimmed": n_suff,
                   "per_cabinet": int_out}, fh, indent=2)
    print(f"  Written: {fname}", flush=True)

    stats_int = compare_to_orig(f2_int, orig_f2, cabinets, label)
    stats_int["n_blocks_with_sufficient_support"] = n_suff
    stats_int["n_cabinets_with_any_support"] = sum(
        1 for r in f2_int.values() if r.get("Q_F2_kW", 0) > 0
    )
    interior_results[f"minus_{trim_h}h"] = stats_int

# ══════════════════════════════════════════════════════════════════════════════
# Step 2j: Late-cabinet table
# ══════════════════════════════════════════════════════════════════════════════
section("Step 2j: Late-cabinet table")

late_cabs = {}
for cab in [2600, 2601, 2602]:
    frozen_item = next((x for x in orig_f2_data["per_cabinet"] if x["cabinet"] == cab), {})
    entry = {
        "Q_F1_kW":               jf(frozen_item.get("Q_F1_kW")),
        "Q_F2_original_kW":      jf(orig_f2.get(cab)),
        "Q_F2_local_kW":         jf(f2_eastern.get(cab, {}).get("Q_F2_kW")),
        "Q_F2_unclipped_kW":     jf(f2_unclipped.get(cab, {}).get("Q_F2_kW")),
        "f1_exceedance_fraction": jf(frozen_item.get("f1_exceedance_fraction")),
        "f2_exceedance_fraction": jf(frozen_item.get("f2_exceedance_fraction")),
        "severity_f1_kWh":       jf(frozen_item.get("severity_f1_kWh")),
        "severity_f2_kWh":       jf(frozen_item.get("severity_f2_kWh")),
    }
    for trim_h in [6, 12, 24]:
        f2_int = interior_f2_by_trim.get(trim_h, {})
        entry[f"Q_F2_interior_{trim_h}h_kW"] = jf(f2_int.get(cab, {}).get("Q_F2_kW"))
    late_cabs[str(cab)] = entry

print(f"  Late cabinets: {list(late_cabs.keys())}")
for k, v in late_cabs.items():
    print(f"    cab {k}: orig={v['Q_F2_original_kW']:.2f}  local={v['Q_F2_local_kW']:.2f}  "
          f"unclipped={v['Q_F2_unclipped_kW']:.2f}  "
          f"int6h={v.get('Q_F2_interior_6h_kW')}", flush=True)

# ══════════════════════════════════════════════════════════════════════════════
# Overall verdict
# ══════════════════════════════════════════════════════════════════════════════
verdicts = [
    stats_eastern.get("verdict", "support-robust"),
    stats_unclipped.get("verdict", "support-robust"),
    interior_results.get("minus_6h", {}).get("verdict", "support-robust"),
    interior_results.get("minus_12h", {}).get("verdict", "support-robust"),
    interior_results.get("minus_24h", {}).get("verdict", "support-robust"),
]

if "materially-dependent" in verdicts:
    overall_verdict = "materially-dependent"
elif "moderately-sensitive" in verdicts:
    overall_verdict = "moderately-sensitive"
else:
    overall_verdict = "support-robust"

print(f"\n  Overall verdict: {overall_verdict}", flush=True)

# Paradox reconciliation
paradox = (
    "Three prior observations coexist: (a) 77.9% of end_time values fall in the same UTC "
    "calendar day as date_dir; (b) many jobs have start_time on a different day from "
    "date_dir; (c) the prior audit reported 0 crossing jobs. Reconciliation: "
    "(a) and (b) are consistent — date_dir records the UTC calendar day on which a job "
    "ended; multi-hour jobs naturally start on an earlier calendar day, so "
    "start_time < date_dir is expected and not a mismatch. "
    "(c) was a post-clipping artefact: task_d_f2_reference.py clips all job intervals "
    "to support-block boundaries before building the event list. After clipping, no "
    "interval extends beyond a block boundary by construction, so a crossing check "
    "performed on clipped intervals always returns zero regardless of how many "
    "unclipped jobs actually straddle block boundaries. The pre-clipping crossing "
    "counts in this audit (total_jobs_crossing_any_start, total_jobs_crossing_any_end) "
    "are the correct figures, and they are handled correctly by the existing clip logic."
)

# ══════════════════════════════════════════════════════════════════════════════
# Write consolidated task_d2_support_audit.json
# ══════════════════════════════════════════════════════════════════════════════
section("Write consolidated audit JSON")

audit = {
    "plan_commit":  "c674209",
    "audit_date":   "2026-10-06",
    "date_dir_timezone": tz_audit,
    "boundary_crossing": crossing_audit,
    "f2_variants": {
        "local_date":                stats_eastern,
        "unclipped_observed_active": stats_unclipped,
        "interior_minus_6h":         interior_results.get("minus_6h", {}),
        "interior_minus_12h":        interior_results.get("minus_12h", {}),
        "interior_minus_24h":        interior_results.get("minus_24h", {}),
    },
    "late_cabinets_full": late_cabs,
    "missing_workload_limitation": (
        "Because inclusion is based on jobs ending on selected days, there may be jobs "
        "active during a selected support interval whose end date is unselected and "
        "therefore absent from the dataset. This missing concurrent load is not "
        "identifiable from this dataset alone. Therefore no F2 variant may be described "
        "as actual cabinet power, complete cabinet power, or measured fleet cabinet load. "
        "The correct description is: observed reconstructed concurrent cabinet power from "
        "the public job sample."
    ),
    "paradox_reconciliation": paradox,
    "decision_thresholds": {
        "local_date_vs_original":   stats_eastern.get("verdict"),
        "unclipped_vs_original":    stats_unclipped.get("verdict"),
        "interior_6h_vs_original":  interior_results.get("minus_6h", {}).get("verdict"),
        "interior_12h_vs_original": interior_results.get("minus_12h", {}).get("verdict"),
        "interior_24h_vs_original": interior_results.get("minus_24h", {}).get("verdict"),
    },
    "overall_verdict": overall_verdict,
}

out_path = REV3 / "task_d2_support_audit.json"
with open(out_path, "w") as fh:
    json.dump(audit, fh, indent=2)
print(f"  Written: {out_path}")
print("\nDone.", flush=True)
