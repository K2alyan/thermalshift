"""
Phase 2: Business case for thermal-aware scheduling and infrastructure management.

Three analyses, all metadata-only (fast — no per-job file reads):

  A. Rack-level thermal diagnosis
       Fingerprint distribution by rack; identify systematically hot racks.
       How concentrated is the thermal underperformance?

  B. Node reliability cost (Arrhenius)
       Every 10 degC increase in sustained temperature roughly halves CMOS device lifetime.
       Hot-fingerprint nodes fail earlier. Quantify the fleet-wide replacement cost delta.

  C. Scheduling counterfactual (152,400 jobs)
       Replay the full job history under:
         Baseline  : actual random node assignment (fingerprint-agnostic)
         Policy A  : thermal-aware (assign coolest available cohort nodes to each job)
       Metric: distribution of max predicted CPU temp per job-node assignment;
               fraction of node-job-hours above T_threshold.
       Uses T_pred = alpha + gamma * F_node (power term negligible, R^2=0.96 without it).

Outputs (artifacts/phase1/analysis/):
  phase2_results.json     — all scalar business metrics
  phase2_rack_profile.csv — per-rack fingerprint stats
"""
# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.



import os
import json
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import os
from pathlib import Path
from scipy import stats

# ── paths ──────────────────────────────────────────────────────────────────────
COHORT_DIR = Path(__file__).parent.parent
OUT_DIR    = COHORT_DIR / "analysis"
JOB_INFO   = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "frontier-completed-job-info.parquet"

# ── load data ──────────────────────────────────────────────────────────────────
print("Loading data...")
fp       = pq.read_table(OUT_DIR / "fingerprints.parquet").to_pandas()
manifest = pd.read_csv(COHORT_DIR / "cohort_manifest.csv")
jinfo    = pq.read_table(JOB_INFO).to_pandas()

# Fleet thermal model intercept (T at F=0, from phase1 fleet regression)
ALPHA  = 47.72   # degC intercept
GAMMA  = 0.9997  # fingerprint coefficient (≈1.0)

# Empirical temperature thresholds from fleet job
T_P95  = 49.74   # degC — fleet p95 CPU temp
T_P99  = 50.82   # degC — fleet p99 CPU temp
T_MAX  = T_P99   # threshold above which we call a node "stressed"

# AMD EPYC CMOS reference temp for Arrhenius (nominal operating, degC)
T_REF  = 47.70   # fleet mean CPU temp
# Arrhenius: every 10 degC doubles failure rate (Q10 rule, conservative)
Q10    = 2.0
# Assumed node replacement cost (USD, FY2025 list price estimate for blade+GPUs)
NODE_COST_USD = 80_000
# Fleet size and annual hours
FLEET_NODES   = 9856
HOURS_PER_YR  = 8760

print(f"  Fingerprints: {len(fp)} nodes")
print(f"  Job metadata: {len(jinfo)} jobs")


# ══════════════════════════════════════════════════════════════════════════════
# A. Rack-level thermal diagnosis
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== A. Rack-level thermal diagnosis ===")

fp_fc = fp["FC_fleet"].dropna().rename("fingerprint")
df = manifest.set_index("hostname").join(fp_fc).dropna(subset=["fingerprint"])

rack_stats = (
    df.groupby("rack")["fingerprint"]
    .agg(n="count", mean="mean", std="std",
         p25=lambda x: x.quantile(0.25),
         p75=lambda x: x.quantile(0.75),
         max="max")
    .sort_values("mean", ascending=False)
    .reset_index()
)

# Hot rack = mean fingerprint > fleet mean + 1 SD
fp_fleet_mean = fp_fc.mean()
fp_fleet_std  = fp_fc.std()
hot_threshold = fp_fleet_mean + fp_fleet_std
cold_threshold= fp_fleet_mean - fp_fleet_std
n_hot_racks  = (rack_stats["mean"] > hot_threshold).sum()
n_cold_racks = (rack_stats["mean"] < cold_threshold).sum()
n_racks      = len(rack_stats)

# Fraction of nodes in hot vs cold racks
hot_nodes  = df[df["fingerprint"] > hot_threshold]
cold_nodes = df[df["fingerprint"] < cold_threshold]

print(f"  Fleet fingerprint mean={fp_fleet_mean:.3f}°C, std={fp_fleet_std:.3f}°C")
print(f"  Total racks with fingerprint data: {n_racks}")
print(f"  Hot racks (mean > +1SD = +{hot_threshold:.2f}°C): {n_hot_racks} ({n_hot_racks/n_racks*100:.1f}%)")
print(f"  Cold racks (mean < -1SD = {cold_threshold:.2f}°C): {n_cold_racks} ({n_cold_racks/n_racks*100:.1f}%)")
print(f"  Hot nodes (F > +{hot_threshold:.2f}°C): {len(hot_nodes)} ({len(hot_nodes)/len(df)*100:.1f}%)")
print(f"  Cold nodes (F < {cold_threshold:.2f}°C): {len(cold_nodes)} ({len(cold_nodes)/len(df)*100:.1f}%)")
print(f"  Hottest rack: rack {rack_stats.iloc[0]['rack']}, "
      f"mean F={rack_stats.iloc[0]['mean']:.2f}°C, n={rack_stats.iloc[0]['n']:.0f}")
print(f"  Coolest rack: rack {rack_stats.iloc[-1]['rack']}, "
      f"mean F={rack_stats.iloc[-1]['mean']:.2f}°C, n={rack_stats.iloc[-1]['n']:.0f}")

rack_stats.to_csv(OUT_DIR / "phase2_rack_profile.csv", index=False)


# ══════════════════════════════════════════════════════════════════════════════
# B. Arrhenius reliability cost
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== B. Arrhenius reliability cost ===")

# Relative failure rate: RFR = Q10 ^ (delta_T / 10)
# A node at T_ref + F runs at RFR = 2^(F/10) relative to the fleet mean
df["rfr"] = Q10 ** (df["fingerprint"] / 10.0)
rfr_fleet_mean = df["rfr"].mean()

# Mean time to failure (MTTF) is inversely proportional to RFR
# If fleet mean MTTF = 1 (normalized), hot node MTTF = 1/RFR
df["rel_mttf"] = 1.0 / df["rfr"]

# Annual failures: if fleet-wide annual failure rate is r_base,
# hot nodes fail at r_base * RFR. Excess failures vs fleet-mean node:
# excess_annual_failures = n_hot * r_base * (RFR_mean_hot - 1)
# We report as a ratio (not needing r_base).
rfr_hot  = df.loc[df["fingerprint"] > hot_threshold, "rfr"].mean()
rfr_cold = df.loc[df["fingerprint"] < cold_threshold, "rfr"].mean()
n_hot_cohort = len(hot_nodes)
n_cold_cohort= len(cold_nodes)

# Extrapolate to full fleet (assume cohort is representative)
hot_frac  = n_hot_cohort / len(df)
cold_frac = n_cold_cohort / len(df)
n_hot_fleet  = int(FLEET_NODES * hot_frac)
n_cold_fleet = int(FLEET_NODES * cold_frac)

# Excess failure rate of hot vs cold nodes (relative)
rfr_delta_hot_vs_cold = rfr_hot / rfr_cold
# If you could move hot nodes to cold-node thermal behavior, MTTF increases by 1/rfr_hot * rfr_cold
mttf_improvement = rfr_hot / rfr_cold  # = how many more times longer cold nodes last

# Annual replacement savings if hot nodes operated at fleet mean temp
# = (RFR_hot - 1) * n_hot * r_base * NODE_COST
# We express this as a fraction of total fleet annual maintenance cost
excess_rfr_fraction = (rfr_hot - rfr_fleet_mean) / rfr_fleet_mean

print(f"  Fleet mean relative failure rate (RFR): {rfr_fleet_mean:.4f}")
print(f"  Hot node mean RFR:  {rfr_hot:.4f}  ({rfr_hot/rfr_fleet_mean-1:+.1%} vs fleet mean)")
print(f"  Cold node mean RFR: {rfr_cold:.4f}  ({rfr_cold/rfr_fleet_mean-1:+.1%} vs fleet mean)")
print(f"  Hot/cold RFR ratio: {rfr_delta_hot_vs_cold:.3f}x "
      f"(hot nodes fail ~{rfr_delta_hot_vs_cold:.2f}x faster than cold nodes)")
print(f"  Fleet-scale: ~{n_hot_fleet:,} hot nodes, ~{n_cold_fleet:,} cold nodes")
print(f"  Excess failure burden of hot nodes vs fleet mean: {excess_rfr_fraction:+.1%}")
print(f"  If hot nodes cooled to fleet mean: failure rate reduction = "
      f"{(1 - rfr_fleet_mean/rfr_hot)*100:.1f}% for those nodes")


# ══════════════════════════════════════════════════════════════════════════════
# C. Scheduling counterfactual (full 152,400-job history)
# ══════════════════════════════════════════════════════════════════════════════
print("\n=== C. Scheduling counterfactual ===")

# Build node-fingerprint lookup
node_fp = df["fingerprint"].to_dict()   # hostname -> fingerprint degC
cohort_set = set(node_fp.keys())

# Parse node_list from job metadata
# node_list is a Python-list-like string: ['frontierNNNNN', ...]
import ast

def parse_node_list(s):
    if s is None:
        return []
    if isinstance(s, (list, np.ndarray)):
        return list(s)
    try:
        return ast.literal_eval(str(s))
    except Exception:
        return []

print("  Parsing node lists from 152,400 jobs...", flush=True)
jinfo["nodes"] = jinfo["host_list"].apply(parse_node_list)

# Keep only jobs that include at least 1 cohort node
jinfo["cohort_nodes"] = jinfo["nodes"].apply(
    lambda nl: [n for n in nl if n in cohort_set]
)
jinfo["n_cohort"] = jinfo["cohort_nodes"].apply(len)
jobs_with_cohort = jinfo[jinfo["n_cohort"] >= 1].copy()
print(f"  Jobs with >=1 cohort node: {len(jobs_with_cohort):,} of {len(jinfo):,}")

# Predicted peak CPU temperature for a node in a job:
#   T_pred = ALPHA + GAMMA * F_node
# (power term dropped — beta_P is negligible, R^2 unchanged)

def max_fingerprint(node_list):
    fps = [node_fp[n] for n in node_list if n in node_fp]
    return max(fps) if fps else np.nan

def mean_fingerprint(node_list):
    fps = [node_fp[n] for n in node_list if n in node_fp]
    return np.mean(fps) if fps else np.nan

print("  Computing baseline max predicted temps...", flush=True)
jobs_with_cohort["max_F_baseline"] = jobs_with_cohort["cohort_nodes"].apply(max_fingerprint)
jobs_with_cohort["mean_F_baseline"]= jobs_with_cohort["cohort_nodes"].apply(mean_fingerprint)
jobs_with_cohort["T_max_baseline"]  = ALPHA + GAMMA * jobs_with_cohort["max_F_baseline"]

# Policy A: for each job, choose the n_cohort coolest available nodes.
# In this counterfactual we have all cohort nodes available (we treat them as
# a shared pool — a conservative assumption since in reality only idle nodes
# are available). The benefit is thus an upper-bound estimate.
sorted_nodes = sorted(node_fp.keys(), key=lambda n: node_fp[n])  # coldest first
fingerprints_sorted = np.array([node_fp[n] for n in sorted_nodes])

def policy_a_max_fp(n_cohort_needed):
    if n_cohort_needed <= 0 or n_cohort_needed > len(sorted_nodes):
        return np.nan
    return fingerprints_sorted[:n_cohort_needed].max()

print("  Computing Policy A max predicted temps...", flush=True)
jobs_with_cohort["max_F_policyA"] = jobs_with_cohort["n_cohort"].apply(policy_a_max_fp)
jobs_with_cohort["T_max_policyA"] = ALPHA + GAMMA * jobs_with_cohort["max_F_policyA"]

# Drop rows where either is NaN
valid = jobs_with_cohort.dropna(subset=["T_max_baseline", "T_max_policyA"])
delta_T = valid["T_max_baseline"] - valid["T_max_policyA"]

print(f"\n  Jobs analyzed: {len(valid):,}")
print(f"  Baseline  — mean max T: {valid['T_max_baseline'].mean():.3f}°C, "
      f"std={valid['T_max_baseline'].std():.3f}°C")
print(f"  Policy A  — mean max T: {valid['T_max_policyA'].mean():.3f}°C, "
      f"std={valid['T_max_policyA'].std():.3f}°C")
print(f"  Mean delta_T (baseline - policy A): {delta_T.mean():.3f}°C")
print(f"  P95 delta_T: {delta_T.quantile(0.95):.3f}°C")
print(f"  Max delta_T: {delta_T.max():.3f}°C")

# Jobs above T_MAX threshold
n_above_baseline = (valid["T_max_baseline"] > T_MAX).sum()
n_above_policyA  = (valid["T_max_policyA"]  > T_MAX).sum()
pct_baseline     = n_above_baseline / len(valid) * 100
pct_policyA      = n_above_policyA  / len(valid) * 100
reduction_pct    = (1 - n_above_policyA / max(n_above_baseline, 1)) * 100

print(f"\n  T_max threshold (fleet p99 = {T_MAX:.2f}°C):")
print(f"  Jobs with a cohort node above T_max — baseline: {n_above_baseline:,} ({pct_baseline:.1f}%)")
print(f"  Jobs with a cohort node above T_max — Policy A: {n_above_policyA:,} ({pct_policyA:.1f}%)")
print(f"  Reduction in thermal exceedances: {reduction_pct:.1f}%")

# Node-job-hours above threshold
valid["run_time_h"] = valid["run_time"].fillna(0) / 3600
stressed_hours_baseline = (valid[valid["T_max_baseline"] > T_MAX]["run_time_h"] * valid[valid["T_max_baseline"] > T_MAX]["n_cohort"]).sum()
stressed_hours_policyA  = (valid[valid["T_max_policyA"]  > T_MAX]["run_time_h"] * valid[valid["T_max_policyA"]  > T_MAX]["n_cohort"]).sum()
recovered_hours = stressed_hours_baseline - stressed_hours_policyA

print(f"\n  Thermally stressed node-hours — baseline: {stressed_hours_baseline:,.0f}")
print(f"  Thermally stressed node-hours — Policy A: {stressed_hours_policyA:,.0f}")
print(f"  Node-hours recovered from thermal stress:  {recovered_hours:,.0f}")

# Express as fraction of total node-hours
total_cohort_hours = (valid["run_time_h"] * valid["n_cohort"]).sum()
print(f"  Total cohort node-hours in dataset: {total_cohort_hours:,.0f}")
print(f"  Fraction of node-hours de-stressed: {recovered_hours/total_cohort_hours*100:.2f}%")


# ══════════════════════════════════════════════════════════════════════════════
# Save results
# ══════════════════════════════════════════════════════════════════════════════
results = {
    "rack_diagnosis": {
        "n_racks_analyzed": int(n_racks),
        "n_hot_racks": int(n_hot_racks),
        "n_cold_racks": int(n_cold_racks),
        "hot_rack_frac": round(n_hot_racks / n_racks, 4),
        "fp_fleet_mean_C": round(float(fp_fleet_mean), 4),
        "fp_fleet_std_C": round(float(fp_fleet_std), 4),
        "hot_threshold_C": round(float(hot_threshold), 4),
        "n_hot_nodes_cohort": int(len(hot_nodes)),
        "n_cold_nodes_cohort": int(len(cold_nodes)),
    },
    "arrhenius": {
        "q10_assumption": Q10,
        "rfr_fleet_mean": round(float(rfr_fleet_mean), 5),
        "rfr_hot_nodes": round(float(rfr_hot), 5),
        "rfr_cold_nodes": round(float(rfr_cold), 5),
        "hot_vs_cold_rfr_ratio": round(float(rfr_delta_hot_vs_cold), 4),
        "excess_failure_burden_hot_nodes_pct": round(float(excess_rfr_fraction) * 100, 2),
        "n_hot_nodes_fleet_est": n_hot_fleet,
        "n_cold_nodes_fleet_est": n_cold_fleet,
    },
    "scheduling_counterfactual": {
        "jobs_analyzed": int(len(valid)),
        "T_threshold_C": T_MAX,
        "mean_max_T_baseline_C": round(float(valid["T_max_baseline"].mean()), 4),
        "mean_max_T_policyA_C": round(float(valid["T_max_policyA"].mean()), 4),
        "mean_delta_T_C": round(float(delta_T.mean()), 4),
        "p95_delta_T_C": round(float(delta_T.quantile(0.95)), 4),
        "max_delta_T_C": round(float(delta_T.max()), 4),
        "jobs_above_threshold_baseline": int(n_above_baseline),
        "jobs_above_threshold_policyA": int(n_above_policyA),
        "pct_above_baseline": round(pct_baseline, 2),
        "pct_above_policyA": round(pct_policyA, 2),
        "exceedance_reduction_pct": round(float(reduction_pct), 2),
        "stressed_node_hours_baseline": round(stressed_hours_baseline, 1),
        "stressed_node_hours_policyA": round(stressed_hours_policyA, 1),
        "node_hours_recovered": round(recovered_hours, 1),
        "total_cohort_node_hours": round(total_cohort_hours, 1),
        "pct_node_hours_destressed": round(recovered_hours / total_cohort_hours * 100, 3),
    },
}

with open(OUT_DIR / "phase2_results.json", "w") as f:
    json.dump(results, f, indent=2)
print(f"\n  Saved phase2_results.json")
print("\nDone.")
