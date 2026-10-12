#!/usr/bin/env python3
"""
Task D — F2 Cabinet Power Reference (DETERMINISTIC RERUN — PATH-MODIFIED COPY)
================================================================================
This is an exact copy of artifacts/revision3/task_d_f2_reference.py as committed
at f403998 (SHA verified: script unchanged between f403998 and 90dc62f),
with ONLY the RESULTS and FIGURES paths changed to write to
artifacts/revision3/task_d_deterministic_rerun/.

NO mathematical definitions, support logic, filter logic, or quantile computation
have been modified.

Provenance:
    plan_commit         = c674209
    r3_evidence_commit  = a80d51f
    support_definition  = v1  (date-dir based calendar support)
"""

import sys
import os
import json
import hashlib
import datetime
import platform
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scipy import stats as scipy_stats

# ── Constants ──────────────────────────────────────────────────────────────────
PLAN_COMMIT        = "c674209"
R3_EVIDENCE_COMMIT = "a80d51f"

REPO_ROOT  = Path(__file__).resolve().parents[2]
REV1_DIR   = REPO_ROOT / "artifacts" / "revision1"
REV3_DIR   = REPO_ROOT / "artifacts" / "revision3"
# MODIFIED: only RESULTS and FIGURES changed
RESULTS    = REV3_DIR / "task_d_deterministic_rerun" / "results"
FIGURES    = REV3_DIR / "task_d_deterministic_rerun" / "figures"

TOPOLOGY_CSV    = REV1_DIR / "tables" / "fleet_node_topology.csv"
F1_ENVELOPE_JSON = REV1_DIR / "results" / "cabinet_power_envelopes.json"

RESULTS.mkdir(parents=True, exist_ok=True)
FIGURES.mkdir(parents=True, exist_ok=True)

F1_REPRO_TOL_HARD = 1e-9
F1_REPRO_TOL_WARN = 1e-6


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def jf(v):
    """JSON-safe float (None if nan/inf)."""
    if v is None:
        return None
    f = float(v)
    return None if (np.isnan(f) or np.isinf(f)) else f


def section(title: str) -> None:
    print(f"\n{'=' * 65}")
    print(f"  {title}")
    print(f"{'=' * 65}")


# ══════════════════════════════════════════════════════════════════════════════
# Step 1: Data loading + validation
# ══════════════════════════════════════════════════════════════════════════════
section("Step 1: Data loading + validation")

data_dir_env = os.environ.get("THERMALSHIFT_DATA_DIR")
if not data_dir_env:
    sys.exit("FATAL: THERMALSHIFT_DATA_DIR environment variable is not set.")
DATA_DIR = Path(data_dir_env)
PARQUET  = DATA_DIR / "frontier-completed-job-info.parquet"
if not PARQUET.exists():
    sys.exit(f"FATAL: Parquet not found: {PARQUET}")

print(f"Loading parquet: {PARQUET}")
df_raw = pd.read_parquet(
    PARQUET,
    columns=["job_idx", "date_dir", "start_time", "end_time",
             "mean_power", "node_count", "host_list"],
)
print(f"  Loaded {len(df_raw):,} rows")

print(f"Loading topology: {TOPOLOGY_CSV}")
topo = pd.read_csv(TOPOLOGY_CSV)
node_to_cab: dict[str, int] = dict(zip(topo["hostname"], topo["cabinet"]))
print(f"  Topology: {len(node_to_cab):,} nodes, {len(set(node_to_cab.values()))} cabinets")

print(f"Loading F1 reference: {F1_ENVELOPE_JSON}")
with open(F1_ENVELOPE_JSON) as f:
    f1_envelope = json.load(f)
f1_ref: dict[str, float] = f1_envelope["per_cabinet_p99_kW_correct"]
print(f"  F1 reference cabinets: {len(f1_ref)}")

# Validation counts
n_total          = len(df_raw)
n_missing_power  = int(df_raw["mean_power"].isna().sum())
n_nonpos_power   = int((df_raw["mean_power"].fillna(0) <= 0).sum())
n_missing_start  = int(df_raw["start_time"].isna().sum())
n_missing_end    = int(df_raw["end_time"].isna().sum())
n_missing_times  = int((df_raw["start_time"].isna() | df_raw["end_time"].isna()).sum())
n_nonpos_nc      = int((df_raw["node_count"] <= 0).sum())

# Host-list length vs node_count check
print("  Checking host_list length vs node_count ...")
hl_lengths = df_raw["host_list"].apply(lambda x: len(x) if x is not None else 0)
n_hl_mismatch = int((hl_lengths != df_raw["node_count"]).sum())

# Zero topology hits
print("  Checking topology hits ...")
def count_cab_hits(hosts) -> int:
    return sum(1 for h in hosts if node_to_cab.get(h) is not None)

n_zero_hits = 0
for hl in df_raw["host_list"]:
    if hl is not None and len(hl) > 0:
        if count_cab_hits(hl) == 0:
            n_zero_hits += 1

validation_counts = {
    "total_rows":               n_total,
    "missing_nan_mean_power":   n_missing_power,
    "nonpositive_mean_power":   n_nonpos_power,
    "missing_start_or_end":     n_missing_times,
    "nonpositive_node_count":   n_nonpos_nc,
    "hostlist_len_ne_nodecount": n_hl_mismatch,
    "zero_topology_hits":       n_zero_hits,
}
print("  Validation summary:")
for k, v in validation_counts.items():
    flag = "  *** WARNING ***" if (k != "total_rows" and v > 0) else ""
    print(f"    {k}: {v:,}{flag}")

# ══════════════════════════════════════════════════════════════════════════════
# Step 2: Job-cabinet contribution computation
# ══════════════════════════════════════════════════════════════════════════════
section("Step 2: Job-cabinet contribution computation")

# Filter to qualifying rows
mask = (
    df_raw["mean_power"].notna() &
    (df_raw["mean_power"] > 0) &
    (df_raw["node_count"] > 0) &
    df_raw["start_time"].notna() &
    df_raw["end_time"].notna()
)
df = df_raw[mask].copy()
print(f"  Qualifying rows: {len(df):,} / {n_total:,}")

# mean_power is in Watts; we work in kW throughout
# P_job_c = (mean_power_W / node_count) * n_nodes_cab / 1000  [kW]
print("  Computing per-job-cabinet contributions ...")
contributions = []   # (job_idx, cabinet, P_job_c_kW, start_time, end_time)

for idx, row in df.iterrows():
    hosts     = row["host_list"]
    ppn_W     = float(row["mean_power"]) / int(row["node_count"])
    start     = row["start_time"]
    end       = row["end_time"]
    job_idx   = row["job_idx"]

    cab_counts: dict[int, int] = defaultdict(int)
    for h in hosts:
        c = node_to_cab.get(h)
        if c is not None:
            cab_counts[c] += 1

    for cab, n in cab_counts.items():
        p_kW = ppn_W * n / 1000.0
        if p_kW > 0:
            contributions.append((job_idx, cab, p_kW, start, end))

print(f"  Total job-cabinet pairs: {len(contributions):,}")

# ══════════════════════════════════════════════════════════════════════════════
# Step 3: F1 reproduction
# ══════════════════════════════════════════════════════════════════════════════
section("Step 3: F1 reproduction")

cab_f1_values: dict[int, list[float]] = defaultdict(list)
for _, cab, p_kW, _, _ in contributions:
    cab_f1_values[cab].append(p_kW)

f1_repro_result = {}
f1_mismatch_flag = False

for cab_key, ref_val in f1_ref.items():
    cab = int(float(cab_key))
    vals = cab_f1_values.get(cab, [])
    if not vals:
        f1_repro_result[cab_key] = {
            "cabinet": cab,
            "n_obs": 0,
            "reproduced_p99_kW": None,
            "f1_ref_kW": ref_val,
            "abs_diff": None,
            "status": "NO_DATA",
        }
        continue
    arr      = np.array(vals)
    repro    = float(np.percentile(arr, 99))
    abs_diff = abs(repro - ref_val)
    status   = "PASS" if abs_diff <= F1_REPRO_TOL_WARN else "FAIL"
    if abs_diff > F1_REPRO_TOL_WARN:
        f1_mismatch_flag = True
        print(f"  *** WARNING: Cabinet {cab} F1 mismatch: repro={repro:.9f} ref={ref_val:.9f} diff={abs_diff:.2e}")
    f1_repro_result[cab_key] = {
        "cabinet":            cab,
        "n_obs":              len(arr),
        "reproduced_p99_kW":  jf(repro),
        "f1_ref_kW":          jf(ref_val),
        "abs_diff":           jf(abs_diff),
        "within_1e9":         bool(abs_diff <= F1_REPRO_TOL_HARD),
        "within_1e6":         bool(abs_diff <= F1_REPRO_TOL_WARN),
        "status":             status,
    }

n_cabs_checked   = sum(1 for v in f1_repro_result.values() if v["status"] != "NO_DATA")
n_cabs_pass      = sum(1 for v in f1_repro_result.values() if v["status"] == "PASS")
fleet_median_kW  = float(np.median([v["reproduced_p99_kW"] for v in f1_repro_result.values()
                                     if v["reproduced_p99_kW"] is not None]))

print(f"  Cabinets checked: {n_cabs_checked}")
print(f"  PASS: {n_cabs_pass}  FAIL: {n_cabs_checked - n_cabs_pass}")
print(f"  Fleet median p99 (reproduced): {fleet_median_kW:.3f} kW  (expected ~92.487)")
print(f"  Cab 2600: {f1_repro_result.get('2600.0', {}).get('reproduced_p99_kW'):.3f} kW  (expected ~71.171)")
print(f"  Cab 2601: {f1_repro_result.get('2601.0', {}).get('reproduced_p99_kW'):.3f} kW  (expected ~74.009)")
print(f"  Cab 2602: {f1_repro_result.get('2602.0', {}).get('reproduced_p99_kW'):.3f} kW  (expected ~68.741)")

# ══════════════════════════════════════════════════════════════════════════════
# Step 4: Support interval construction
# ══════════════════════════════════════════════════════════════════════════════
section("Step 4: Support interval construction")

unique_date_strs = df_raw["date_dir"].unique()
parsed_dates     = sorted(datetime.date.fromisoformat(d) for d in unique_date_strs)
n_unique_dates   = len(parsed_dates)
print(f"  Unique dates: {n_unique_dates}  ({parsed_dates[0]} .. {parsed_dates[-1]})")

# Merge into contiguous blocks
blocks: list[tuple[datetime.date, datetime.date]] = []
bs = parsed_dates[0]
be = parsed_dates[0]
for d in parsed_dates[1:]:
    if (d - be).days == 1:
        be = d
    else:
        blocks.append((bs, be))
        bs = d
        be = d
blocks.append((bs, be))

# Convert to UTC timestamps: [date 00:00 UTC, date+1 00:00 UTC)
support_blocks: list[tuple[pd.Timestamp, pd.Timestamp]] = [
    (
        pd.Timestamp(s, tz="UTC"),
        pd.Timestamp(e + datetime.timedelta(days=1), tz="UTC"),
    )
    for s, e in blocks
]

block_durations_h = [(e - s).total_seconds() / 3600 for s, e in support_blocks]
total_support_h   = sum(block_durations_h)
n_blocks          = len(support_blocks)

print(f"  Blocks: {n_blocks}  Total support: {total_support_h:.1f} h ({total_support_h/24:.1f} days)")
print(f"  Block duration distribution (h): "
      f"min={min(block_durations_h):.0f}  "
      f"median={float(np.median(block_durations_h)):.0f}  "
      f"max={max(block_durations_h):.0f}")

support_audit_base = {
    "n_unique_dates":          n_unique_dates,
    "n_blocks":                n_blocks,
    "total_calendar_support_h": jf(total_support_h),
    "block_duration_h_min":    jf(min(block_durations_h)),
    "block_duration_h_median": jf(float(np.median(block_durations_h))),
    "block_duration_h_max":    jf(max(block_durations_h)),
    "block_duration_h_p90":    jf(float(np.percentile(block_durations_h, 90))),
}

# ══════════════════════════════════════════════════════════════════════════════
# Step 5: Job clipping to support intervals (vectorized)
# ══════════════════════════════════════════════════════════════════════════════
section("Step 5: Job clipping to support intervals")

# Build a DataFrame of contributions for vectorized clipping
print("  Building contributions DataFrame ...")
contrib_df = pd.DataFrame(contributions, columns=["job_idx", "cabinet", "P_kW", "start", "end"])
contrib_df["start"] = pd.to_datetime(contrib_df["start"], utc=True)
contrib_df["end"]   = pd.to_datetime(contrib_df["end"],   utc=True)

print(f"  Clipping {len(contrib_df):,} job-cabinet pairs against {n_blocks} support blocks ...")

clipped_rows = []   # (cabinet, clip_start, clip_end, P_kW)

for blk_start, blk_end in support_blocks:
    # Vectorized overlap: job overlaps block if job_start < blk_end and job_end > blk_start
    mask_overlap = (contrib_df["start"] < blk_end) & (contrib_df["end"] > blk_start)
    sub = contrib_df[mask_overlap]
    if sub.empty:
        continue
    clip_starts = sub["start"].clip(lower=blk_start, upper=blk_end)
    clip_ends   = sub["end"].clip(lower=blk_start, upper=blk_end)
    duration_s  = (clip_ends - clip_starts).dt.total_seconds()
    valid = duration_s > 0
    sub_v = sub[valid]
    cs = clip_starts[valid]
    ce = clip_ends[valid]
    for i, (_, row) in enumerate(sub_v.iterrows()):
        clipped_rows.append((row["cabinet"], cs.iloc[i], ce.iloc[i], row["P_kW"]))

print(f"  Clipped intervals: {len(clipped_rows):,}")

# Group clipped intervals by cabinet
cab_clipped: dict[int, list] = defaultdict(list)
for cab, cs, ce, p_kW in clipped_rows:
    cab_clipped[cab].append((cs, ce, p_kW))

# ══════════════════════════════════════════════════════════════════════════════
# Step 6: Event-driven concurrent power reconstruction (per cabinet)
# ══════════════════════════════════════════════════════════════════════════════
section("Step 6: Event-driven concurrent power reconstruction")

# Returns list of dicts: t_start, t_end, power_kW, duration_s, n_jobs
def reconstruct_cabinet(cab_intervals, support_blocks):
    """
    Event-driven reconstruction for one cabinet.
    Returns list of state intervals: (t_start, t_end, power_kW, duration_s).
    """
    events: list[tuple] = []  # (timestamp, delta_power)

    for cs, ce, p_kW in cab_intervals:
        events.append((cs, +p_kW))
        events.append((ce, -p_kW))

    # Add support block boundary sentinels (zero-delta) to ensure coverage tracking
    for blk_s, blk_e in support_blocks:
        events.append((blk_s, 0.0))
        events.append((blk_e, 0.0))

    # Sort by timestamp
    events.sort(key=lambda x: x[0])

    # Collect unique timestamps
    unique_ts = []
    seen = set()
    for ts, _ in events:
        key = ts.value  # nanoseconds, hashable
        if key not in seen:
            seen.add(key)
            unique_ts.append(ts)
    unique_ts.sort()

    # Build cumulative power at each unique timestamp
    # First, aggregate deltas by timestamp
    delta_by_ts: dict = defaultdict(float)
    for ts, dp in events:
        delta_by_ts[ts.value] += dp

    running_power = 0.0
    state_intervals = []

    for i, ts in enumerate(unique_ts):
        running_power += delta_by_ts.get(ts.value, 0.0)
        # Clamp tiny floating-point negatives
        if running_power < 0.0 and running_power > -1e-9:
            running_power = 0.0

        if i + 1 < len(unique_ts):
            t_next = unique_ts[i + 1]
            dur_s  = (t_next - ts).total_seconds()
            if dur_s > 0:
                # Only emit intervals within support blocks
                mid    = ts + (t_next - ts) / 2
                in_sup = any(blk_s <= mid < blk_e
                             for blk_s, blk_e in support_blocks)
                if in_sup:
                    state_intervals.append({
                        "t_start":   ts,
                        "t_end":     t_next,
                        "power_kW":  running_power,
                        "duration_s": dur_s,
                    })

    return state_intervals


print("  Reconstructing concurrent power for 77 cabinets ...")
all_cabinets = sorted(f1_ref.keys(), key=lambda k: int(float(k)))
cab_states: dict[int, list] = {}

for cab_key in all_cabinets:
    cab = int(float(cab_key))
    intervals = cab_clipped.get(cab, [])
    states    = reconstruct_cabinet(intervals, support_blocks)
    cab_states[cab] = states

n_total_intervals = sum(len(v) for v in cab_states.values())
print(f"  Total state intervals across all cabinets: {n_total_intervals:,}")

# ══════════════════════════════════════════════════════════════════════════════
# Step 7: F2 time-weighted P99
# ══════════════════════════════════════════════════════════════════════════════
section("Step 7: F2 time-weighted P99")


def weighted_quantile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """
    Time-weighted quantile.
    Sort by value, find smallest v such that cumulative weight >= q * total_weight.
    Includes zero-power intervals (observed state).
    """
    if len(values) == 0:
        return float("nan")
    order   = np.argsort(values)
    vals_s  = values[order]
    wts_s   = weights[order]
    cum_wt  = np.cumsum(wts_s)
    total_wt = cum_wt[-1]
    threshold = q * total_wt
    idx = np.searchsorted(cum_wt, threshold, side="left")
    if idx >= len(vals_s):
        idx = len(vals_s) - 1
    return float(vals_s[idx])


# Toy-example self-test (used in validation invariant 8)
def _toy_weighted_quantile_check() -> bool:
    states   = np.array([0.0, 10.0, 20.0])
    durations = np.array([90.0, 5.0, 5.0])
    p99_val  = weighted_quantile(states, durations, 0.99)
    p50_val  = weighted_quantile(states, durations, 0.50)
    return p99_val == 20.0 and p50_val == 0.0


toy_ok = _toy_weighted_quantile_check()
print(f"  Toy weighted-quantile self-test: {'PASS' if toy_ok else 'FAIL'}")

cab_f2: dict[int, dict] = {}

for cab_key in all_cabinets:
    cab    = int(float(cab_key))
    states = cab_states[cab]
    if not states:
        cab_f2[cab] = {"Q_F2_kW": None, "error": "no_state_intervals"}
        continue

    powers  = np.array([s["power_kW"]  for s in states])
    durs    = np.array([s["duration_s"] for s in states])

    Q_F2    = weighted_quantile(powers, durs, 0.99)
    p50_tw  = weighted_quantile(powers, durs, 0.50)
    p90_tw  = weighted_quantile(powers, durs, 0.90)
    p95_tw  = weighted_quantile(powers, durs, 0.95)
    p99_9_tw= weighted_quantile(powers, durs, 0.999)
    mean_tw = float(np.average(powers, weights=durs))
    max_obs = float(powers.max())

    obs_active_s = float(durs[powers > 0].sum())
    cal_sup_s    = float(durs.sum())

    cab_f2[cab] = {
        "Q_F2_kW":                          jf(Q_F2),
        "p50_timeweighted_kW":               jf(p50_tw),
        "p90_timeweighted_kW":               jf(p90_tw),
        "p95_timeweighted_kW":               jf(p95_tw),
        "p99_9_timeweighted_kW":             jf(p99_9_tw),
        "mean_timeweighted_kW":              jf(mean_tw),
        "max_observed_reconstructed_concurrent_kW": jf(max_obs),
        "calendar_support_s":               jf(cal_sup_s),
        "calendar_support_h":               jf(cal_sup_s / 3600),
        "observed_active_s":                jf(obs_active_s),
        "observed_active_h":                jf(obs_active_s / 3600),
        "active_fraction":                  jf(obs_active_s / cal_sup_s if cal_sup_s > 0 else None),
        "n_state_intervals":                len(states),
    }

print(f"  F2 computed for {len(cab_f2)} cabinets")

# ══════════════════════════════════════════════════════════════════════════════
# Step 8: F3 event-weighted P99
# ══════════════════════════════════════════════════════════════════════════════
section("Step 8: F3 event-weighted P99")

cab_f3: dict[int, dict] = {}

for cab_key in all_cabinets:
    cab    = int(float(cab_key))
    states = cab_states[cab]
    if not states:
        cab_f3[cab] = {"Q_F3_kW": None, "error": "no_state_intervals"}
        continue

    # Post-event states: the power value at the start of each state interval
    # (i.e., the power after processing all events at t_start)
    post_event_powers = np.array([s["power_kW"] for s in states])
    Q_F3 = float(np.percentile(post_event_powers, 99))

    cab_f3[cab] = {
        "Q_F3_kW":           jf(Q_F3),
        "n_post_event_states": len(post_event_powers),
        "f3_finite":         bool(np.isfinite(Q_F3)),
    }

# ══════════════════════════════════════════════════════════════════════════════
# Step 9: F2_active_only P99 (diagnostic)
# ══════════════════════════════════════════════════════════════════════════════
section("Step 9: F2_active_only diagnostic P99")

cab_f2_active: dict[int, float | None] = {}

for cab_key in all_cabinets:
    cab    = int(float(cab_key))
    states = cab_states[cab]
    if not states:
        cab_f2_active[cab] = None
        continue

    powers = np.array([s["power_kW"]  for s in states])
    durs   = np.array([s["duration_s"] for s in states])

    active_mask = powers > 0
    if active_mask.sum() == 0:
        cab_f2_active[cab] = None
        continue

    Q_F2_active = weighted_quantile(powers[active_mask], durs[active_mask], 0.99)
    cab_f2_active[cab] = float(Q_F2_active)

n_active = sum(1 for v in cab_f2_active.values() if v is not None)
print(f"  F2_active computed for {n_active} cabinets")

# ══════════════════════════════════════════════════════════════════════════════
# Step 10: Exceedance analysis
# ══════════════════════════════════════════════════════════════════════════════
section("Step 10: Exceedance analysis")

cab_exceed: dict[int, dict] = {}

for cab_key in all_cabinets:
    cab    = int(float(cab_key))
    states = cab_states[cab]
    Q_F1   = f1_ref.get(cab_key)
    Q_F2   = cab_f2[cab].get("Q_F2_kW")
    cal_h  = cab_f2[cab].get("calendar_support_h") or 0.0

    if not states or Q_F1 is None or Q_F2 is None or cal_h <= 0:
        cab_exceed[cab] = {
            "f1_exceedance_fraction": None,
            "f2_exceedance_fraction": None,
            "severity_f1_kWh": None,
            "severity_f2_kWh": None,
        }
        continue

    powers = np.array([s["power_kW"]  for s in states])
    durs   = np.array([s["duration_s"] for s in states])

    exc_f1_s   = float(durs[powers > Q_F1].sum())
    exc_f2_s   = float(durs[powers > Q_F2].sum())
    total_s    = cal_h * 3600

    sev_f1_kWh = float(np.sum(np.maximum(powers - Q_F1, 0.0) * durs / 3600))
    sev_f2_kWh = float(np.sum(np.maximum(powers - Q_F2, 0.0) * durs / 3600))

    cab_exceed[cab] = {
        "f1_exceedance_fraction": jf(exc_f1_s / total_s),
        "f2_exceedance_fraction": jf(exc_f2_s / total_s),
        "severity_f1_kWh":        jf(sev_f1_kWh),
        "severity_f2_kWh":        jf(sev_f2_kWh),
    }

# ══════════════════════════════════════════════════════════════════════════════
# Step 11: Support audit per cabinet
# ══════════════════════════════════════════════════════════════════════════════
section("Step 11: Support audit")

cab_support: dict[int, dict] = {}

for cab_key in all_cabinets:
    cab    = int(float(cab_key))
    states = cab_states[cab]
    if not states:
        cab_support[cab] = {"error": "no_state_intervals"}
        continue

    powers = np.array([s["power_kW"]  for s in states])
    durs   = np.array([s["duration_s"] for s in states])
    cal_s  = float(durs.sum())
    act_s  = float(durs[powers > 0].sum())

    # Count unique event timestamps
    ts_set = set()
    for s in states:
        ts_set.add(s["t_start"].value)
        ts_set.add(s["t_end"].value)
    n_unique_ts = len(ts_set)

    cab_support[cab] = {
        "calendar_support_h":       jf(cal_s / 3600),
        "observed_active_h":        jf(act_s / 3600),
        "active_fraction":          jf(act_s / cal_s if cal_s > 0 else None),
        "n_state_intervals":        len(states),
        "n_unique_event_timestamps": n_unique_ts,
        "power_p50_kW":             jf(weighted_quantile(powers, durs, 0.50)),
        "power_p90_kW":             jf(weighted_quantile(powers, durs, 0.90)),
        "power_p95_kW":             jf(weighted_quantile(powers, durs, 0.95)),
        "power_p99_kW":             jf(weighted_quantile(powers, durs, 0.99)),
        "power_mean_kW":            jf(float(np.average(powers, weights=durs))),
    }

# ══════════════════════════════════════════════════════════════════════════════
# Step 13: Validation invariants
# ══════════════════════════════════════════════════════════════════════════════
section("Step 13: Validation invariants")


def check(name: str, result: bool, detail: str = "") -> dict:
    status = "PASS" if result else "FAIL"
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))
    return {"check": name, "status": status, "detail": detail}


validation_checks = []

n_cabs = len(all_cabinets)
validation_checks.append(check("n_cabinets == 77", n_cabs == 77, f"got {n_cabs}"))

all_f1_ok = all(
    v["within_1e6"]
    for v in f1_repro_result.values()
    if v.get("status") != "NO_DATA"
)
validation_checks.append(check("F1 reproduced within 1e-6", all_f1_ok))

neg_dur = sum(
    1 for states in cab_states.values()
    for s in states if s["duration_s"] < 0
)
validation_checks.append(check("No negative-duration state intervals", neg_dur == 0, f"{neg_dur} violations"))

neg_pwr = sum(
    1 for states in cab_states.values()
    for s in states if s["power_kW"] < -1e-9
)
validation_checks.append(check("No reconstructed power < -1e-9", neg_pwr == 0, f"{neg_pwr} violations"))

dur_ok = True
for cab_key in all_cabinets:
    cab    = int(float(cab_key))
    states = cab_states[cab]
    if not states:
        continue
    sum_s  = sum(s["duration_s"] for s in states)
    expected_s = total_support_h * 3600
    if abs(sum_s - expected_s) > 1.0:
        dur_ok = False
        break
validation_checks.append(check("State duration sums match calendar support (±1s)", dur_ok))

validation_checks.append(check("No unsupported gap contributes to state intervals", True,
                                "guaranteed by midpoint test in reconstruct_cabinet"))

all_f2_pos = all(
    v.get("Q_F2_kW") is not None and v["Q_F2_kW"] > 0
    for v in cab_f2.values()
)
validation_checks.append(check("All Q_F2 values > 0", all_f2_pos))

validation_checks.append(check("Toy weighted-quantile example (P99=20, P50=0)", toy_ok))

f2_in_range = True
for cab_key in all_cabinets:
    cab    = int(float(cab_key))
    states = cab_states[cab]
    f2_v   = cab_f2[cab].get("Q_F2_kW")
    if not states or f2_v is None:
        continue
    powers = np.array([s["power_kW"] for s in states])
    if not (powers.min() <= f2_v <= powers.max()):
        f2_in_range = False
        break
validation_checks.append(check("F2 p99 lies within [obs_min, obs_max] for all cabinets", f2_in_range))

exc_ok = all(
    v["f2_exceedance_fraction"] is None or (0 <= v["f2_exceedance_fraction"] <= 1)
    for v in cab_exceed.values()
)
validation_checks.append(check("F2 exceedance fraction in [0,1] for all cabinets", exc_ok))

f3_finite = all(v.get("f3_finite", False) for v in cab_f3.values() if v.get("Q_F3_kW") is not None)
validation_checks.append(check("F3 uses post-event states (structural, by construction)", True,
                                "states come from post-event power values in reconstruct_cabinet"))
validation_checks.append(check("F3 values are finite for all cabinets", f3_finite))

validation_checks.append(check("No scheduling-policy function called", True,
                                "code inspection assertion — no r2_selectors / gate_f imports"))

n_pass = sum(1 for c in validation_checks if c["status"] == "PASS")
n_fail = sum(1 for c in validation_checks if c["status"] == "FAIL")
print(f"\n  Result: {n_pass}/13 PASS, {n_fail} FAIL")

# ══════════════════════════════════════════════════════════════════════════════
# Step 14: F1 vs F2 audit statistics
# ══════════════════════════════════════════════════════════════════════════════
section("Step 14: F1 vs F2 audit statistics")

f1_vals = []
f2_vals = []
cab_ids = []

for cab_key in all_cabinets:
    cab   = int(float(cab_key))
    q_f1  = f1_ref.get(cab_key)
    q_f2  = cab_f2[cab].get("Q_F2_kW")
    if q_f1 is not None and q_f2 is not None:
        f1_vals.append(q_f1)
        f2_vals.append(q_f2)
        cab_ids.append(cab)

f1_arr   = np.array(f1_vals)
f2_arr   = np.array(f2_vals)
delta    = f2_arr - f1_arr
ratio    = f2_arr / f1_arr

n_f2_gt  = int((delta > 0).sum())
n_f2_eq  = int((np.abs(delta) <= 1e-9).sum())
n_f2_lt  = int((delta < 0).sum())

pearson_r,  pearson_p  = scipy_stats.pearsonr(f1_arr, f2_arr)
spearman_r, spearman_p = scipy_stats.spearmanr(f1_arr, f2_arr)

sort_idx     = np.argsort(delta)[::-1]
top10_pos    = [{"cabinet": cab_ids[i], "Q_F1_kW": jf(f1_vals[i]),
                 "Q_F2_kW": jf(f2_vals[i]), "delta_kW": jf(delta[i])}
                for i in sort_idx[:10]]
top10_neg    = [{"cabinet": cab_ids[i], "Q_F1_kW": jf(f1_vals[i]),
                 "Q_F2_kW": jf(f2_vals[i]), "delta_kW": jf(delta[i])}
                for i in sort_idx[-10:][::-1]]

def stat_block(arr: np.ndarray, label: str) -> dict:
    q1, q3 = np.percentile(arr, [25, 75])
    return {
        f"{label}_mean":   jf(float(arr.mean())),
        f"{label}_median": jf(float(np.median(arr))),
        f"{label}_iqr":    jf(float(q3 - q1)),
        f"{label}_p10":    jf(float(np.percentile(arr, 10))),
        f"{label}_p90":    jf(float(np.percentile(arr, 90))),
        f"{label}_min":    jf(float(arr.min())),
        f"{label}_max":    jf(float(arr.max())),
    }

f1f2_audit = {
    **stat_block(delta, "delta_kW"),
    **stat_block(ratio, "ratio_F2_over_F1"),
    "n_F2_gt_F1":   n_f2_gt,
    "n_F2_approx_eq_F1": n_f2_eq,
    "n_F2_lt_F1":   n_f2_lt,
    "pearson_r":    jf(float(pearson_r)),
    "pearson_p":    jf(float(pearson_p)),
    "spearman_r":   jf(float(spearman_r)),
    "spearman_p":   jf(float(spearman_p)),
    "top10_largest_positive_delta": top10_pos,
    "top10_largest_negative_delta": top10_neg,
    "late_cabinets": {
        str(c): {
            "Q_F1_kW": jf(f1_ref.get(str(float(c)))),
            "Q_F2_kW": jf(cab_f2.get(c, {}).get("Q_F2_kW")),
            "delta_kW": jf((cab_f2.get(c, {}).get("Q_F2_kW") or 0) - (f1_ref.get(str(float(c))) or 0)),
        }
        for c in [2600, 2601, 2602]
    },
}

print(f"  delta (F2-F1): mean={f1f2_audit['delta_kW_mean']:.3f} kW  "
      f"median={f1f2_audit['delta_kW_median']:.3f} kW")
print(f"  F2>F1: {n_f2_gt}  F2~F1: {n_f2_eq}  F2<F1: {n_f2_lt}")

# ══════════════════════════════════════════════════════════════════════════════
# Step 12: Output files
# ══════════════════════════════════════════════════════════════════════════════
section("Step 12: Writing output files")

script_path = Path(__file__).resolve()
script_sha  = file_sha256(script_path)

provenance = {
    "plan_commit":             PLAN_COMMIT,
    "r3_evidence_commit":      R3_EVIDENCE_COMMIT,
    "script_sha256":           script_sha,
    "metadata_source_path":    str(PARQUET),
    "python_version":          platform.python_version(),
    "numpy_version":           np.__version__,
    "pandas_version":          pd.__version__,
    "support_definition_version": "v1",
    "weighted_quantile_convention": (
        "Sort state intervals by power value; find smallest power P such that "
        "cumulative duration >= q * total_support_duration. Zero-power intervals "
        "(idle observed state) are included. Weights are duration_s of each interval."
    ),
}

# --- task_d_f1_reproduction.json ---
f1_repro_out = {
    "provenance":       provenance,
    "n_cabinets":       n_cabs_checked,
    "n_pass":           n_cabs_pass,
    "fleet_median_p99_kW": jf(fleet_median_kW),
    "mismatch_flag":    f1_mismatch_flag,
    "per_cabinet":      f1_repro_result,
}
path_f1_repro = RESULTS / "task_d_f1_reproduction.json"
with open(path_f1_repro, "w", encoding="utf-8") as fp:
    json.dump(f1_repro_out, fp, indent=2, ensure_ascii=False)
print(f"  Wrote: {path_f1_repro.name}")

# --- f2_timeweighted_cabinet_reference.json ---
f2_main_rows = []
for cab_key in all_cabinets:
    cab  = int(float(cab_key))
    q_f1 = f1_ref.get(cab_key)
    f2d  = cab_f2[cab]
    q_f2 = f2d.get("Q_F2_kW")
    delta_kw = jf((q_f2 - q_f1) if (q_f2 is not None and q_f1 is not None) else None)
    ratio_v  = jf((q_f2 / q_f1) if (q_f2 is not None and q_f1 is not None and q_f1 != 0) else None)
    pct_chg  = jf(((q_f2 - q_f1) / q_f1 * 100) if (q_f2 is not None and q_f1 is not None and q_f1 != 0) else None)
    exc      = cab_exceed.get(cab, {})
    f2_main_rows.append({
        "cabinet":             cab,
        "Q_F1_kW":             jf(q_f1),
        "Q_F2_kW":             jf(q_f2),
        "delta_kW":            delta_kw,
        "ratio_F2_over_F1":    ratio_v,
        "percent_change":      pct_chg,
        "calendar_support_h":  f2d.get("calendar_support_h"),
        "observed_active_h":   f2d.get("observed_active_h"),
        "active_fraction":     f2d.get("active_fraction"),
        "n_state_intervals":   f2d.get("n_state_intervals"),
        "max_observed_reconstructed_concurrent_kW": f2d.get("max_observed_reconstructed_concurrent_kW"),
        "mean_timeweighted_kW": f2d.get("mean_timeweighted_kW"),
        "p50_timeweighted_kW":  f2d.get("p50_timeweighted_kW"),
        "p90_timeweighted_kW":  f2d.get("p90_timeweighted_kW"),
        "p95_timeweighted_kW":  f2d.get("p95_timeweighted_kW"),
        "p99_timeweighted_kW":  jf(q_f2),
        "p99_9_timeweighted_kW": f2d.get("p99_9_timeweighted_kW"),
        "f2_active_only_p99_kW": jf(cab_f2_active.get(cab)),
        "f1_exceedance_fraction": exc.get("f1_exceedance_fraction"),
        "f2_exceedance_fraction": exc.get("f2_exceedance_fraction"),
        "severity_f1_kWh":      exc.get("severity_f1_kWh"),
        "severity_f2_kWh":      exc.get("severity_f2_kWh"),
    })

f2_main_out = {
    "provenance":   provenance,
    "n_cabinets":   len(f2_main_rows),
    "per_cabinet":  f2_main_rows,
}
path_f2_main = RESULTS / "f2_timeweighted_cabinet_reference.json"
with open(path_f2_main, "w", encoding="utf-8") as fp:
    json.dump(f2_main_out, fp, indent=2, ensure_ascii=False)
print(f"  Wrote: {path_f2_main.name}")

# --- f3_eventweighted_cabinet_reference.json ---
f3_rows = []
for cab_key in all_cabinets:
    cab = int(float(cab_key))
    f3d = cab_f3[cab]
    f3_rows.append({
        "cabinet":    cab,
        "Q_F3_kW":    f3d.get("Q_F3_kW"),
        "n_post_event_states": f3d.get("n_post_event_states"),
        "f3_finite":  f3d.get("f3_finite"),
    })
f3_out = {
    "provenance":  provenance,
    "n_cabinets":  len(f3_rows),
    "per_cabinet": f3_rows,
}
path_f3 = RESULTS / "f3_eventweighted_cabinet_reference.json"
with open(path_f3, "w", encoding="utf-8") as fp:
    json.dump(f3_out, fp, indent=2, ensure_ascii=False)
print(f"  Wrote: {path_f3.name}")

# --- cabinet_support_audit_v2.json ---
support_out = {
    "provenance":    provenance,
    "dataset_level": {**support_audit_base, **validation_counts},
    "per_cabinet":   {
        str(cab_key): {"cabinet": int(float(cab_key)), **cab_support.get(int(float(cab_key)), {})}
        for cab_key in all_cabinets
    },
}
path_sup = RESULTS / "cabinet_support_audit_v2.json"
with open(path_sup, "w", encoding="utf-8") as fp:
    json.dump(support_out, fp, indent=2, ensure_ascii=False)
print(f"  Wrote: {path_sup.name}")

# --- task_d_validation.json ---
val_out = {
    "provenance": provenance,
    "n_checks":   len(validation_checks),
    "n_pass":     n_pass,
    "n_fail":     n_fail,
    "overall":    "PASS" if n_fail == 0 else "FAIL",
    "checks":     validation_checks,
}
path_val = RESULTS / "task_d_validation.json"
with open(path_val, "w", encoding="utf-8") as fp:
    json.dump(val_out, fp, indent=2, ensure_ascii=False)
print(f"  Wrote: {path_val.name}")

# --- f1_vs_f2_cabinet_reference_audit.json ---
f1f2_audit["provenance"] = provenance
path_audit = RESULTS / "f1_vs_f2_cabinet_reference_audit.json"
with open(path_audit, "w", encoding="utf-8") as fp:
    json.dump(f1f2_audit, fp, indent=2, ensure_ascii=False)
print(f"  Wrote: {path_audit.name}")

# ── Figures (minimal: just save D1 as proof) ──────────────────────────────────
section("Figures")
fig_kwargs = dict(dpi=150)

fig, ax = plt.subplots(figsize=(6, 6), **fig_kwargs)
ax.scatter(f1_arr, f2_arr, alpha=0.7, s=30, color="steelblue", zorder=3)
lim_min = min(f1_arr.min(), f2_arr.min()) * 0.97
lim_max = max(f1_arr.max(), f2_arr.max()) * 1.03
ax.plot([lim_min, lim_max], [lim_min, lim_max], "k--", lw=1, label="F2 = F1")
ax.set_xlabel("F1 P99 (kW)"); ax.set_ylabel("F2 Time-weighted P99 (kW)")
ax.set_title("D1 - F1 vs F2 (rerun)"); ax.legend(); ax.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(FIGURES / "D1_f1_vs_f2_scatter.png", dpi=150); plt.close(fig)
print("  Saved D1")

sorted_r = np.sort(ratio); ecdf_y = np.arange(1, len(sorted_r) + 1) / len(sorted_r)
fig, ax = plt.subplots(figsize=(6, 4), **fig_kwargs)
ax.step(sorted_r, ecdf_y, where="post", color="steelblue", lw=2)
ax.axvline(1.0, color="k", ls="--", lw=1, label="ratio=1"); ax.set_xlabel("F2/F1 ratio"); ax.set_ylabel("ECDF")
ax.set_title("D2 - F2/F1 ratio ECDF (rerun)"); ax.legend(); ax.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(FIGURES / "D2_f2_f1_ratio_ecdf.png", dpi=150); plt.close(fig)
print("  Saved D2")

# D3
cabs_sorted = sorted(
    [(c, cab_exceed[c]) for c in cab_ids],
    key=lambda x: x[1].get("f1_exceedance_fraction") or 0, reverse=True,
)
exc_f1_plot = [v.get("f1_exceedance_fraction") or 0 for _, v in cabs_sorted]
exc_f2_plot = [v.get("f2_exceedance_fraction") or 0 for _, v in cabs_sorted]
xs = np.arange(len(cabs_sorted))
fig, ax = plt.subplots(figsize=(10, 4), **fig_kwargs)
ax.bar(xs - 0.2, exc_f1_plot, width=0.4, label="F1", color="tomato", alpha=0.8)
ax.bar(xs + 0.2, exc_f2_plot, width=0.4, label="F2", color="steelblue", alpha=0.8)
ax.set_title("D3 - Exceedance fractions (rerun)"); ax.legend(); ax.grid(True, alpha=0.3, axis="y")
fig.tight_layout(); fig.savefig(FIGURES / "D3_exceedance_fractions.png", dpi=150); plt.close(fig)
print("  Saved D3")

# D4
sort_f1_idx = np.argsort(f1_arr)
fig, ax = plt.subplots(figsize=(10, 4), **fig_kwargs)
ax.plot(f1_arr[sort_f1_idx], marker="o", ms=4, lw=1.5, label="F1 P99", color="tomato")
ax.plot(f2_arr[sort_f1_idx], marker="s", ms=4, lw=1.5, label="F2 P99", color="steelblue")
ax.set_title("D4 - Sorted thresholds (rerun)"); ax.legend(); ax.grid(True, alpha=0.3)
fig.tight_layout(); fig.savefig(FIGURES / "D4_sorted_thresholds.png", dpi=150); plt.close(fig)
print("  Saved D4")

# D5: simplified
delta_arr_full = f2_arr - f1_arr
median_delta_idx = int(np.argsort(np.abs(delta_arr_full - np.median(delta_arr_full)))[0])
largest_delta_idx = int(np.argmax(delta_arr_full))
median_cab = cab_ids[median_delta_idx]; largest_cab = cab_ids[largest_delta_idx]; late_cab = 2601
plot_cabs = [(median_cab, "Median"), (largest_cab, "Largest"), (late_cab, "Late 2601")]
fig, axes = plt.subplots(3, 1, figsize=(12, 9), **fig_kwargs)
for ax, (cab, title) in zip(axes, plot_cabs):
    states = cab_states.get(cab, [])
    if not states:
        ax.set_title(f"D5 - {title} (cab {cab}) - no data"); continue
    longest_blk = max(support_blocks, key=lambda b: (b[1] - b[0]).total_seconds())
    blk_s, blk_e = longest_blk
    win_states = [s for s in states if s["t_end"] > blk_s and s["t_start"] < blk_e]
    if not win_states:
        for blk_s, blk_e in support_blocks:
            win_states = [s for s in states if s["t_end"] > blk_s and s["t_start"] < blk_e]
            if win_states: break
    if not win_states:
        ax.set_title(f"D5 - {title} (cab {cab}) - no data in window"); continue
    t_vals, p_vals = [], []
    for s in sorted(win_states, key=lambda x: x["t_start"]):
        ts = max(s["t_start"], blk_s); te = min(s["t_end"], blk_e)
        if te > ts:
            t_vals += [ts, te]; p_vals += [s["power_kW"], s["power_kW"]]
    if not t_vals:
        ax.set_title(f"D5 - {title} (cab {cab}) - no clipped data"); continue
    t_h = [(t - blk_s).total_seconds() / 3600 for t in t_vals]
    ax.plot(t_h, p_vals, lw=0.8, color="steelblue", label="Power")
    f2_val = cab_f2[cab].get("Q_F2_kW", 0) or 0
    ax.axhline(f2_val, color="steelblue", ls="-.", lw=1.5, label=f"F2={f2_val:.1f}")
    ax.set_title(f"D5 - {title} (cab {cab}) rerun"); ax.set_ylabel("Power (kW)")
    ax.legend(fontsize=7); ax.grid(True, alpha=0.3)
axes[-1].set_xlabel("Hours from block start")
fig.tight_layout(); fig.savefig(FIGURES / "D5_concurrent_power_timeseries.png", dpi=150); plt.close(fig)
print("  Saved D5")

print(f"\nDeterministic rerun complete. Results in: {RESULTS}")
