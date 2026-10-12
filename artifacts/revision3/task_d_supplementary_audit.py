#!/usr/bin/env python3
"""
Task D Supplementary Audit
===========================
Computes missing audit items (concurrency association, support-edge diagnostics)
and provides a full A-J review table from committed outputs and parquet data.

Writes: artifacts/revision3/task_d_supplementary_audit.json

Does NOT modify any result files in artifacts/revision3/results/.
Does NOT run any scheduling simulation.
"""

import os
import sys
import json
import hashlib
import datetime
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats as scipy_stats

REPO_ROOT = Path(__file__).resolve().parents[2]
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
REV3_DIR  = REPO_ROOT / "artifacts" / "revision3"
RESULTS   = REV3_DIR / "results"
OUT_JSON  = REV3_DIR / "task_d_supplementary_audit.json"

TOPOLOGY_CSV      = REV1_DIR / "tables" / "fleet_node_topology.csv"
F1_ENVELOPE_JSON  = REV1_DIR / "results" / "cabinet_power_envelopes.json"
F2_JSON           = RESULTS / "f2_timeweighted_cabinet_reference.json"
F3_JSON           = RESULTS / "f3_eventweighted_cabinet_reference.json"
SUP_JSON          = RESULTS / "cabinet_support_audit_v2.json"
F1F2_JSON         = RESULTS / "f1_vs_f2_cabinet_reference_audit.json"

data_dir_env = os.environ.get("THERMALSHIFT_DATA_DIR")
if not data_dir_env:
    sys.exit("FATAL: THERMALSHIFT_DATA_DIR not set")
DATA_DIR = Path(data_dir_env)
PARQUET  = DATA_DIR / "frontier-completed-job-info.parquet"


def jf(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if (np.isnan(f) or np.isinf(f)) else f
    except Exception:
        return None


print("Loading committed outputs ...")
with open(F2_JSON) as fh:
    f2_data = json.load(fh)
with open(F3_JSON) as fh:
    f3_data = json.load(fh)
with open(SUP_JSON) as fh:
    sup_data = json.load(fh)
with open(F1F2_JSON) as fh:
    f1f2_data = json.load(fh)

f2_per_cab = {r["cabinet"]: r for r in f2_data["per_cabinet"]}
f3_per_cab = {r["cabinet"]: r for r in f3_data["per_cabinet"]}
cab_ids_all = sorted(f2_per_cab.keys())

print("Loading parquet ...")
df_raw = pd.read_parquet(
    PARQUET,
    columns=["job_idx", "date_dir", "start_time", "end_time",
             "mean_power", "node_count", "host_list"],
)
print(f"  Loaded {len(df_raw):,} rows")

print("Loading topology ...")
topo = pd.read_csv(TOPOLOGY_CSV)
node_to_cab = dict(zip(topo["hostname"], topo["cabinet"]))
print(f"  {len(node_to_cab):,} nodes, {len(set(node_to_cab.values()))} cabinets")

# Filter to qualifying jobs (same as original script)
mask = (
    df_raw["mean_power"].notna() &
    (df_raw["mean_power"] > 0) &
    (df_raw["node_count"] > 0) &
    df_raw["start_time"].notna() &
    df_raw["end_time"].notna()
)
df = df_raw[mask].copy()
df["start_time"] = pd.to_datetime(df["start_time"], utc=True)
df["end_time"]   = pd.to_datetime(df["end_time"],   utc=True)
df_raw["start_time"] = pd.to_datetime(df_raw["start_time"], utc=True, errors="coerce")
df_raw["end_time"]   = pd.to_datetime(df_raw["end_time"],   utc=True, errors="coerce")

n_qualifying = len(df)
print(f"  Qualifying rows: {n_qualifying:,}")

# Reconstruct support blocks (same logic as original script)
unique_date_strs = df_raw["date_dir"].dropna().unique()
parsed_dates     = sorted(datetime.date.fromisoformat(d) for d in unique_date_strs)
blocks_raw = []
bs = parsed_dates[0]; be = parsed_dates[0]
for d in parsed_dates[1:]:
    if (d - be).days == 1:
        be = d
    else:
        blocks_raw.append((bs, be)); bs = d; be = d
blocks_raw.append((bs, be))

support_blocks = [
    (pd.Timestamp(s, tz="UTC"), pd.Timestamp(e + datetime.timedelta(days=1), tz="UTC"))
    for s, e in blocks_raw
]
total_support_h = sum((e - s).total_seconds() / 3600 for s, e in support_blocks)
n_blocks = len(support_blocks)

print(f"  Support: {len(parsed_dates)} dates, {n_blocks} blocks, {total_support_h:.1f}h")

# ── A. Support table ────────────────────────────────────────────────────────────
print("\n[A] Support table ...")
dataset_level = sup_data["dataset_level"]
total_rows    = dataset_level["total_rows"]
n_dates       = dataset_level["n_unique_dates"]
n_blks        = dataset_level["n_blocks"]
total_cal_h   = dataset_level["total_calendar_support_h"]

excl_nonpos_power = int(dataset_level.get("nonpositive_mean_power", 0))
excl_missing_time = int(dataset_level.get("missing_start_or_end", 0))
excl_nonpos_nc    = int(dataset_level.get("nonpositive_node_count", 0))

active_fracs = [r["active_fraction"] for r in f2_per_cab.values() if r.get("active_fraction") is not None]
af_arr = np.array(active_fracs)
q1, q3 = np.percentile(af_arr, [25, 75])

# B_section: concurrent jobs/nodes at event timestamps (fleet-level)
print("[A] Computing fleet-level concurrent job/node counts at event timestamps ...")
# Collect all job start/end events within support
event_ts_all = []
for _, row in df.iterrows():
    s = row["start_time"]; e = row["end_time"]
    nc = int(row["node_count"])
    pw = float(row["mean_power"])
    event_ts_all.append((s, nc, pw, "start"))
    event_ts_all.append((e, nc, pw, "end"))

# Sample: collect all unique event timestamps within support
all_ts = sorted(set(
    ts for ts, _, _, _ in event_ts_all
    if any(blk_s <= ts < blk_e for blk_s, blk_e in support_blocks)
))
print(f"  Total event timestamps in support: {len(all_ts):,}")

# For fleet concurrent counts: at each event timestamp, count active jobs
# Build intervals: sorted list (start, end, node_count)
starts_s = df["start_time"].values
ends_s   = df["end_time"].values
ncs_s    = df["node_count"].values

# Sample 10000 random event timestamps for speed
rng = np.random.default_rng(42)
if len(all_ts) > 10000:
    sample_ts = sorted(rng.choice(all_ts, 10000, replace=False).tolist())
else:
    sample_ts = all_ts

concurrent_jobs_list  = []
concurrent_nodes_list = []

starts_ns = pd.array(df["start_time"]).asi8
ends_ns   = pd.array(df["end_time"]).asi8

for ts in sample_ts:
    ts_ns = ts.value
    active_mask = (starts_ns <= ts_ns) & (ends_ns > ts_ns)
    n_jobs  = int(active_mask.sum())
    n_nodes = int(ncs_s[active_mask].sum())
    concurrent_jobs_list.append(n_jobs)
    concurrent_nodes_list.append(n_nodes)

cj_arr = np.array(concurrent_jobs_list)
cn_arr = np.array(concurrent_nodes_list)

support_section = {
    "total_rows": total_rows,
    "qualifying_jobs": n_qualifying,
    "excluded_jobs": {
        "nonpositive_mean_power": excl_nonpos_power,
        "missing_start_or_end":   excl_missing_time,
        "nonpositive_node_count": excl_nonpos_nc,
        "note": "Overlap categories possible; total_rows - qualifying_jobs may exceed sum"
    },
    "n_unique_dates": int(n_dates),
    "n_blocks": int(n_blks),
    "total_calendar_support_h": float(total_cal_h),
    "active_fraction": {
        "median": jf(float(np.median(af_arr))),
        "iqr": jf(float(q3 - q1)),
        "min": jf(float(af_arr.min())),
        "max": jf(float(af_arr.max()))
    },
    "concurrent_observed_jobs_at_event_ts": {
        "n_sample": len(cj_arr),
        "median": jf(float(np.median(cj_arr))),
        "p90": jf(float(np.percentile(cj_arr, 90))),
        "p99": jf(float(np.percentile(cj_arr, 99))),
        "max": int(cj_arr.max()) if len(cj_arr) else None
    },
    "concurrent_observed_nodes_at_event_ts": {
        "n_sample": len(cn_arr),
        "median": jf(float(np.median(cn_arr))),
        "p90": jf(float(np.percentile(cn_arr, 90))),
        "p99": jf(float(np.percentile(cn_arr, 99))),
        "max": int(cn_arr.max()) if len(cn_arr) else None
    }
}

# ── B. Edge effects ────────────────────────────────────────────────────────────
print("[B] Edge effects ...")
# For each support block boundary, count jobs crossing in/out
block_start_nonzero = 0
block_end_nonzero   = 0
start_powers = []
end_powers   = []
n_crossing_starts = 0
n_crossing_ends   = 0

starts_s = df["start_time"]
ends_s   = df["end_time"]
ppn_vals = df["mean_power"] / df["node_count"]  # W per node

starts_ns_arr = pd.array(df["start_time"]).asi8
ends_ns_arr   = pd.array(df["end_time"]).asi8
ppn_arr       = (df["mean_power"] / df["node_count"]).values

for blk_s, blk_e in support_blocks:
    blk_s_ns = blk_s.value
    blk_e_ns = blk_e.value

    # Jobs crossing INTO block start: start < blk_s AND end > blk_s
    cross_in_mask  = (starts_ns_arr < blk_s_ns) & (ends_ns_arr > blk_s_ns)
    cross_out_mask = (starts_ns_arr < blk_e_ns) & (ends_ns_arr > blk_e_ns)

    n_cross_in  = int(cross_in_mask.sum())
    n_cross_out = int(cross_out_mask.sum())
    n_crossing_starts += n_cross_in
    n_crossing_ends   += n_cross_out

    if n_cross_in > 0:
        block_start_nonzero += 1
        # Total power crossing in: sum of ppn * node_count for those jobs (simplified: use mean_power)
        pw_in = df.loc[cross_in_mask, "mean_power"].sum() / 1000  # kW
        start_powers.append(pw_in)
    if n_cross_out > 0:
        block_end_nonzero += 1
        pw_out = df.loc[cross_out_mask, "mean_power"].sum() / 1000  # kW
        end_powers.append(pw_out)

edge_section = {
    "n_blocks_with_nonzero_start_power": block_start_nonzero,
    "n_blocks_with_nonzero_end_power":   block_end_nonzero,
    "n_job_instances_crossing_block_start": n_crossing_starts,
    "n_job_instances_crossing_block_end":   n_crossing_ends,
    "start_power_kW": {
        "median": jf(float(np.median(start_powers))) if start_powers else None,
        "p90":    jf(float(np.percentile(start_powers, 90))) if start_powers else None,
        "max":    jf(float(np.max(start_powers))) if start_powers else None,
    },
    "end_power_kW": {
        "median": jf(float(np.median(end_powers))) if end_powers else None,
        "p90":    jf(float(np.percentile(end_powers, 90))) if end_powers else None,
        "max":    jf(float(np.max(end_powers))) if end_powers else None,
    },
    "note": "start_power_kW and end_power_kW are sums of mean_power for crossing jobs per block, not per-cabinet values"
}

# ── C. F1 threshold statistics ─────────────────────────────────────────────────
print("[C] F1 stats ...")
q_f1_vals   = np.array([r["Q_F1_kW"] for r in f2_per_cab.values()])
f1_exc_vals = np.array([r["f1_exceedance_fraction"] for r in f2_per_cab.values() if r.get("f1_exceedance_fraction") is not None])

# Aggregate exceedance: total time > Q_F1 / total calendar time
# Cannot compute true aggregate without re-running; use mean as proxy
f1_exc_agg_proxy = float(np.mean(f1_exc_vals))
q1_exc, q3_exc = np.percentile(f1_exc_vals, [25, 75])

f1_stats = {
    "Q_F1_kW": {
        "min":    jf(float(q_f1_vals.min())),
        "p10":    jf(float(np.percentile(q_f1_vals, 10))),
        "median": jf(float(np.median(q_f1_vals))),
        "p90":    jf(float(np.percentile(q_f1_vals, 90))),
        "max":    jf(float(q_f1_vals.max()))
    },
    "f1_exceedance_fraction": {
        "mean_across_cabinets": jf(f1_exc_agg_proxy),
        "median": jf(float(np.median(f1_exc_vals))),
        "iqr":    jf(float(q3_exc - q1_exc)),
        "p90":    jf(float(np.percentile(f1_exc_vals, 90))),
        "max":    jf(float(f1_exc_vals.max())),
        "min":    jf(float(f1_exc_vals.min()))
    }
}

# ── D. F2 threshold statistics ─────────────────────────────────────────────────
print("[D] F2 stats ...")
q_f2_vals   = np.array([r["Q_F2_kW"] for r in f2_per_cab.values()])
f2_exc_vals = np.array([r["f2_exceedance_fraction"] for r in f2_per_cab.values() if r.get("f2_exceedance_fraction") is not None])
f2_exc_agg_proxy = float(np.mean(f2_exc_vals))
q1_exc2, q3_exc2 = np.percentile(f2_exc_vals, [25, 75])

n_exc_le_1pct  = int((f2_exc_vals <= 0.010).sum())
n_exc_le_15pct = int((f2_exc_vals <= 0.015).sum())
n_exc_le_2pct  = int((f2_exc_vals <= 0.020).sum())

f2_stats = {
    "Q_F2_kW": {
        "min":    jf(float(q_f2_vals.min())),
        "p10":    jf(float(np.percentile(q_f2_vals, 10))),
        "median": jf(float(np.median(q_f2_vals))),
        "p90":    jf(float(np.percentile(q_f2_vals, 90))),
        "max":    jf(float(q_f2_vals.max()))
    },
    "f2_exceedance_fraction": {
        "mean_across_cabinets": jf(f2_exc_agg_proxy),
        "median": jf(float(np.median(f2_exc_vals))),
        "iqr":    jf(float(q3_exc2 - q1_exc2)),
        "p90":    jf(float(np.percentile(f2_exc_vals, 90))),
        "max":    jf(float(f2_exc_vals.max())),
        "min":    jf(float(f2_exc_vals.min()))
    },
    "n_cabinets_exceedance_le_1pct":  n_exc_le_1pct,
    "n_cabinets_exceedance_le_1p5pct": n_exc_le_15pct,
    "n_cabinets_exceedance_le_2pct":  n_exc_le_2pct
}

# ── E. F2/F1 ratio ─────────────────────────────────────────────────────────────
print("[E] F2/F1 ratio ...")
ratio_arr = np.array([r["ratio_F2_over_F1"] for r in f2_per_cab.values()])
q1_r, q3_r = np.percentile(ratio_arr, [25, 75])

f2_f1_ratio = {
    "min":    jf(f1f2_data["ratio_F2_over_F1_min"]),
    "p10":    jf(f1f2_data["ratio_F2_over_F1_p10"]),
    "median": jf(f1f2_data["ratio_F2_over_F1_median"]),
    "iqr":    jf(f1f2_data["ratio_F2_over_F1_iqr"]),
    "p90":    jf(f1f2_data["ratio_F2_over_F1_p90"]),
    "max":    jf(f1f2_data["ratio_F2_over_F1_max"]),
    "n_F2_gt_F1": f1f2_data["n_F2_gt_F1"],
    "n_F2_approx_eq_F1": f1f2_data["n_F2_approx_eq_F1"],
    "n_F2_lt_F1": f1f2_data["n_F2_lt_F1"],
    "pearson_r":  jf(f1f2_data["pearson_r"]),
    "spearman_r": jf(f1f2_data["spearman_r"])
}

# ── F. Active-only sensitivity ─────────────────────────────────────────────────
print("[F] Active-only sensitivity ...")
ao_ratios = []
ao_diffs  = []
for r in f2_per_cab.values():
    q_f2  = r.get("Q_F2_kW")
    q_ao  = r.get("f2_active_only_p99_kW")
    if q_f2 and q_ao and q_f2 > 0:
        ao_ratios.append(q_ao / q_f2)
        ao_diffs.append(abs(q_ao - q_f2))

ao_ratios_arr = np.array(ao_ratios)
ao_diffs_arr  = np.array(ao_diffs)
q1_ao, q3_ao  = np.percentile(ao_ratios_arr, [25, 75])

n_diff_gt1pct  = int((np.abs(ao_ratios_arr - 1.0) > 0.01).sum())
n_diff_gt5pct  = int((np.abs(ao_ratios_arr - 1.0) > 0.05).sum())
n_diff_gt10pct = int((np.abs(ao_ratios_arr - 1.0) > 0.10).sum())

active_only_sensitivity = {
    "ratio_active_only_over_calendar": {
        "min":    jf(float(ao_ratios_arr.min())),
        "median": jf(float(np.median(ao_ratios_arr))),
        "iqr":    jf(float(q3_ao - q1_ao)),
        "max":    jf(float(ao_ratios_arr.max()))
    },
    "max_abs_kW_difference": jf(float(ao_diffs_arr.max())),
    "n_cabinets_diff_gt_1pct":  n_diff_gt1pct,
    "n_cabinets_diff_gt_5pct":  n_diff_gt5pct,
    "n_cabinets_diff_gt_10pct": n_diff_gt10pct
}

# ── G. F3 vs F2 ────────────────────────────────────────────────────────────────
print("[G] F3 vs F2 ...")
f3_f2_ratios = []
q_f2_list = []
q_f3_list = []
for cab in cab_ids_all:
    r2 = f2_per_cab.get(cab)
    r3 = f3_per_cab.get(cab)
    if r2 and r3:
        q_f2 = r2.get("Q_F2_kW")
        q_f3 = r3.get("Q_F3_kW")
        if q_f2 and q_f3 and q_f2 > 0:
            f3_f2_ratios.append(q_f3 / q_f2)
            q_f2_list.append(q_f2)
            q_f3_list.append(q_f3)

r_f3f2 = np.array(f3_f2_ratios)
q1_gf, q3_gf = np.percentile(r_f3f2, [25, 75])
pearson_f3f2,  _ = scipy_stats.pearsonr(q_f2_list, q_f3_list)
spearman_f3f2, _ = scipy_stats.spearmanr(q_f2_list, q_f3_list)
f3_tendency = "below" if float(np.median(r_f3f2)) < 1.0 else "above"

f3_vs_f2 = {
    "ratio_Q_F3_over_Q_F2": {
        "min":    jf(float(r_f3f2.min())),
        "median": jf(float(np.median(r_f3f2))),
        "iqr":    jf(float(q3_gf - q1_gf)),
        "p90":    jf(float(np.percentile(r_f3f2, 90))),
        "max":    jf(float(r_f3f2.max()))
    },
    "pearson_r_Q_F3_vs_Q_F2":  jf(float(pearson_f3f2)),
    "spearman_r_Q_F3_vs_Q_F2": jf(float(spearman_f3f2)),
    "tendency": f"F3 tends to be {f3_tendency} F2 (median ratio {float(np.median(r_f3f2)):.4f})"
}

# ── H. Severity ────────────────────────────────────────────────────────────────
print("[H] Severity ...")
sev_f1_vals = np.array([r["severity_f1_kWh"] for r in f2_per_cab.values() if r.get("severity_f1_kWh") is not None])
sev_f2_vals = np.array([r["severity_f2_kWh"] for r in f2_per_cab.values() if r.get("severity_f2_kWh") is not None])

total_sev_f1 = float(sev_f1_vals.sum())
total_sev_f2 = float(sev_f2_vals.sum())
pct_reduction = (total_sev_f1 - total_sev_f2) / total_sev_f1 * 100 if total_sev_f1 > 0 else None

severity = {
    "fleet_total_severity_f1_kWh": jf(total_sev_f1),
    "fleet_total_severity_f2_kWh": jf(total_sev_f2),
    "pct_reduction_f2_vs_f1": jf(pct_reduction),
    "per_cabinet_f1_kWh": {
        "median": jf(float(np.median(sev_f1_vals))),
        "p90":    jf(float(np.percentile(sev_f1_vals, 90)))
    },
    "per_cabinet_f2_kWh": {
        "median": jf(float(np.median(sev_f2_vals))),
        "p90":    jf(float(np.percentile(sev_f2_vals, 90)))
    }
}

# ── I. Late cabinets ────────────────────────────────────────────────────────────
print("[I] Late cabinets ...")
late_cabs = [2600, 2601, 2602]
q_f1_all_sorted = sorted([(c, f2_per_cab[c]["Q_F1_kW"]) for c in cab_ids_all], key=lambda x: x[1])
q_f2_all_sorted = sorted([(c, f2_per_cab[c]["Q_F2_kW"]) for c in cab_ids_all], key=lambda x: x[1])
f1_rank_map = {c: i+1 for i, (c, _) in enumerate(q_f1_all_sorted)}
f2_rank_map = {c: i+1 for i, (c, _) in enumerate(q_f2_all_sorted)}
n_total_cabs = len(cab_ids_all)

late_cabinet_results = {}
for cab in late_cabs:
    r2 = f2_per_cab.get(cab, {})
    r3 = f3_per_cab.get(cab, {})
    f1_rank = f1_rank_map.get(cab)
    f2_rank = f2_rank_map.get(cab)
    late_cabinet_results[str(cab)] = {
        "Q_F1_kW":   jf(r2.get("Q_F1_kW")),
        "Q_F1_rank": f1_rank,
        "Q_F1_percentile": jf(f1_rank / n_total_cabs * 100) if f1_rank else None,
        "Q_F2_kW":   jf(r2.get("Q_F2_kW")),
        "Q_F2_rank": f2_rank,
        "Q_F2_percentile": jf(f2_rank / n_total_cabs * 100) if f2_rank else None,
        "Q_F3_kW":   jf(r3.get("Q_F3_kW")),
        "ratio_F2_over_F1": jf(r2.get("ratio_F2_over_F1")),
        "active_fraction":  jf(r2.get("active_fraction")),
        "f1_exceedance_fraction": jf(r2.get("f1_exceedance_fraction")),
        "f2_exceedance_fraction": jf(r2.get("f2_exceedance_fraction")),
        "severity_f1_kWh": jf(r2.get("severity_f1_kWh")),
        "severity_f2_kWh": jf(r2.get("severity_f2_kWh")),
    }

# Assess: are late cabs among lowest?
late_f2_ranks = [f2_rank_map.get(c) for c in late_cabs if f2_rank_map.get(c)]
late_remain_lowest = all(r <= 5 for r in late_f2_ranks) if late_f2_ranks else False
late_cabinet_results["conclusion"] = (
    "Yes — late cabinets 2600, 2601, 2602 remain among the lowest cabinet-reference "
    f"thresholds under F2 (ranks {late_f2_ranks} out of {n_total_cabs})."
    if late_remain_lowest else
    f"Late cabinets have F2 ranks {late_f2_ranks} out of {n_total_cabs}. "
    "Check whether these remain the lowest-ranked under F2."
)

late_cabinets_section = late_cabinet_results

# ── J. Concurrency association ─────────────────────────────────────────────────
print("[J] Concurrency association (per-cabinet concurrent job/node counts) ...")
print("  This requires computing per-cabinet concurrent job counts at event timestamps.")

# Build per-cabinet contributions
contributions = []
for _, row in df.iterrows():
    hosts   = row["host_list"]
    ppn_W   = float(row["mean_power"]) / int(row["node_count"])
    start   = row["start_time"]
    end     = row["end_time"]
    job_idx = row["job_idx"]

    cab_counts = defaultdict(int)
    for h in hosts:
        c = node_to_cab.get(h)
        if c is not None:
            cab_counts[c] += 1

    for cab, n in cab_counts.items():
        if cab in set(cab_ids_all):
            contributions.append((job_idx, cab, n, start, end))

print(f"  Job-cabinet pairs: {len(contributions):,}")

# Group by cabinet
cab_jobs = defaultdict(list)  # cab -> [(job_idx, n_nodes, start, end)]
for job_idx, cab, n_nodes, start, end in contributions:
    cab_jobs[cab].append((job_idx, n_nodes, start, end))

# For each cabinet, compute mean/p99 concurrent jobs and nodes at event timestamps
# Sample events within support (max 500 per cabinet for speed)
cab_mean_conc_jobs  = {}
cab_p99_conc_jobs   = {}
cab_mean_conc_nodes = {}
cab_p99_conc_nodes  = {}

rng2 = np.random.default_rng(2024)

for cab in cab_ids_all:
    jobs = cab_jobs.get(cab, [])
    if not jobs:
        continue

    # Collect all event timestamps for this cabinet within support
    cab_events = set()
    for _, _, _, s, e in [(j, 0, 0, jstart, jend) for j, _, jstart, jend in jobs]:
        pass

    starts_c = []
    ends_c   = []
    nc_c     = []
    for job_idx, n_nodes, start, end in jobs:
        starts_c.append(start)
        ends_c.append(end)
        nc_c.append(n_nodes)

    starts_c_arr = np.array([t.value for t in starts_c], dtype=np.int64)
    ends_c_arr   = np.array([t.value for t in ends_c],   dtype=np.int64)
    nc_c_arr     = np.array(nc_c, dtype=np.int64)

    # All unique timestamps (start + end) within support
    all_ev = []
    for i in range(len(starts_c)):
        for ts_ns in [starts_c_arr[i], ends_c_arr[i]]:
            ts = pd.Timestamp(ts_ns, tz="UTC")
            if any(blk_s <= ts < blk_e for blk_s, blk_e in support_blocks):
                all_ev.append(ts_ns)
    all_ev = list(set(all_ev))

    if not all_ev:
        continue

    if len(all_ev) > 500:
        all_ev = rng2.choice(all_ev, 500, replace=False).tolist()

    conc_jobs  = []
    conc_nodes = []
    for ts_ns in all_ev:
        active = (starts_c_arr <= ts_ns) & (ends_c_arr > ts_ns)
        conc_jobs.append(int(active.sum()))
        conc_nodes.append(int(nc_c_arr[active].sum()))

    if conc_jobs:
        cab_mean_conc_jobs[cab]  = float(np.mean(conc_jobs))
        cab_p99_conc_jobs[cab]   = float(np.percentile(conc_jobs, 99))
        cab_mean_conc_nodes[cab] = float(np.mean(conc_nodes))
        cab_p99_conc_nodes[cab]  = float(np.percentile(conc_nodes, 99))

# Compute Spearman between ratio_F2_over_F1 and concurrent metrics
ratio_vals   = []
mean_cj_vals = []
p99_cj_vals  = []
mean_cn_vals = []
p99_cn_vals  = []

for cab in cab_ids_all:
    r = f2_per_cab.get(cab)
    if not r:
        continue
    ratio_v = r.get("ratio_F2_over_F1")
    if ratio_v is None:
        continue
    if cab not in cab_mean_conc_jobs:
        continue
    ratio_vals.append(ratio_v)
    mean_cj_vals.append(cab_mean_conc_jobs[cab])
    p99_cj_vals.append(cab_p99_conc_jobs[cab])
    mean_cn_vals.append(cab_mean_conc_nodes[cab])
    p99_cn_vals.append(cab_p99_conc_nodes[cab])

n_corr = len(ratio_vals)

def safe_spearman(x, y):
    if len(x) < 3:
        return None, None
    r, p = scipy_stats.spearmanr(x, y)
    return float(r), float(p)

sp_ratio_mean_cj,  pp1 = safe_spearman(ratio_vals, mean_cj_vals)
sp_ratio_p99_cj,   pp2 = safe_spearman(ratio_vals, p99_cj_vals)
sp_ratio_mean_cn,  pp3 = safe_spearman(ratio_vals, mean_cn_vals)
sp_ratio_p99_cn,   pp4 = safe_spearman(ratio_vals, p99_cn_vals)

concurrency_association = {
    "n_cabinets": n_corr,
    "note": "Per-cabinet concurrent counts computed from sample of <=500 event timestamps per cabinet",
    "spearman_ratio_F2F1_vs_mean_concurrent_jobs":  {"r": jf(sp_ratio_mean_cj),  "p": jf(pp1)},
    "spearman_ratio_F2F1_vs_p99_concurrent_jobs":   {"r": jf(sp_ratio_p99_cj),   "p": jf(pp2)},
    "spearman_ratio_F2F1_vs_mean_concurrent_nodes":  {"r": jf(sp_ratio_mean_cn),  "p": jf(pp3)},
    "spearman_ratio_F2F1_vs_p99_concurrent_nodes":   {"r": jf(sp_ratio_p99_cn),   "p": jf(pp4)},
}

# ── Step 6 embedded: date_dir semantics ────────────────────────────────────────
print("[date_dir] Checking date_dir semantics from documentation and data ...")

# Look for documentation
doc_files = []
for pat in ["README.md", "README.txt", "*.md", "*.txt", "dataset_description*", "*metadata*"]:
    doc_files.extend(DATA_DIR.glob(pat))

doc_content = ""
for f in doc_files:
    try:
        doc_content += f"\n=== {f.name} ===\n" + f.read_text(encoding="utf-8", errors="replace")[:2000]
    except Exception:
        pass

# Compute empirical fractions
# For each date_dir, check:
#   fraction of jobs with start_time in [date_dir, date_dir+1)
#   fraction of jobs with end_time in [date_dir, date_dir+1)
#   fraction of jobs spanning date_dir date within [start_time, end_time)

sample_dates = list(parsed_dates[:20])  # sample first 20 dates for speed

n_start_within = 0
n_end_within   = 0
n_span_within  = 0
n_checked      = 0

for dd in sample_dates:
    dd_ts_s = pd.Timestamp(dd, tz="UTC")
    dd_ts_e = pd.Timestamp(dd + datetime.timedelta(days=1), tz="UTC")
    sub = df_raw[df_raw["date_dir"] == str(dd)].copy()
    if sub.empty:
        continue
    n_total_sub = len(sub)
    n_checked += n_total_sub

    start_ok = sub["start_time"].notna() & (sub["start_time"] >= dd_ts_s) & (sub["start_time"] < dd_ts_e)
    end_ok   = sub["end_time"].notna()   & (sub["end_time"]   >= dd_ts_s) & (sub["end_time"]   < dd_ts_e)
    span_ok  = sub["start_time"].notna() & sub["end_time"].notna() & (sub["start_time"] <= dd_ts_e) & (sub["end_time"] >= dd_ts_s)

    n_start_within += int(start_ok.sum())
    n_end_within   += int(end_ok.sum())
    n_span_within  += int(span_ok.sum())

frac_start = n_start_within / n_checked if n_checked > 0 else None
frac_end   = n_end_within   / n_checked if n_checked > 0 else None
frac_span  = n_span_within  / n_checked if n_checked > 0 else None

if doc_content.strip():
    doc_finding = f"Documentation found. Content (first 500 chars): {doc_content[:500]}"
else:
    doc_finding = "No documentation file found in dataset directory. Semantics inferred from data only."

if frac_end is not None and frac_end > 0.8:
    semantics_conclusion = f"date_dir likely = job end date (frac_end={frac_end:.3f})"
elif frac_start is not None and frac_start > 0.8:
    semantics_conclusion = f"date_dir likely = job start date (frac_start={frac_start:.3f})"
else:
    semantics_conclusion = (
        f"date_dir semantics ambiguous from data alone. "
        f"frac_start_within={frac_start:.3f if frac_start else 'N/A'}, "
        f"frac_end_within={frac_end:.3f if frac_end else 'N/A'}, "
        f"frac_spanning={frac_span:.3f if frac_span else 'N/A'}. "
        "This is a limitation — documentation is needed for definitive answer."
    )

date_dir_semantics = {
    "documentation_found": bool(doc_files),
    "documentation_excerpt": doc_content[:500] if doc_content else None,
    "empirical_analysis": {
        "n_jobs_checked": n_checked,
        "n_sample_dates": len(sample_dates),
        "frac_start_time_within_date_dir_day": jf(frac_start),
        "frac_end_time_within_date_dir_day":   jf(frac_end),
        "frac_job_spans_date_dir_day":          jf(frac_span)
    },
    "conclusion": semantics_conclusion,
    "limitation": (
        "If documentation does not definitively answer the question, "
        "the date_dir semantics remain a limitation. The empirical analysis "
        "uses the first 20 unique date_dir values as a sample."
    )
}

# ── Assemble output ─────────────────────────────────────────────────────────────
print("\nWriting task_d_supplementary_audit.json ...")
output = {
    "audit_date": "2026-10-06",
    "plan_commit": "c674209",
    "r3_evidence_commit": "a80d51f",
    "support": support_section,
    "edge_effects": edge_section,
    "f1_stats": f1_stats,
    "f2_stats": f2_stats,
    "f2_f1_ratio": f2_f1_ratio,
    "active_only_sensitivity": active_only_sensitivity,
    "f3_vs_f2": f3_vs_f2,
    "severity": severity,
    "late_cabinets": late_cabinets_section,
    "concurrency_association": concurrency_association,
    "date_dir_semantics": date_dir_semantics,
}

with open(OUT_JSON, "w", encoding="utf-8") as fh:
    json.dump(output, fh, indent=2, ensure_ascii=False)

print(f"Done. Wrote: {OUT_JSON}")
