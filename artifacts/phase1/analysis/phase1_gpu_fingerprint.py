"""
GPU thermal fingerprint — same method as phase1_fingerprint.py but using
mean GCD temperature (average across all 8 GCDs per node) instead of CPU temp.

Computes F^A and F^C (F^B skipped — GPU power channels are per-GCD, not
cleanly node-aggregated, and CPU power already proved beta_P negligible).

Outputs:
  gpu_fingerprints.parquet   — per-node (FA_longitudinal, FA_fleet, FC_longitudinal, FC_fleet)
  gpu_validation.json        — Pearson r, Spearman r, ICC(2,1), sign agree, MAE + null test
  gpu_null_distribution.npy  — 1000-sample permutation null
"""
# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.



import os
import json, warnings
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import stats
import os
from pathlib import Path

warnings.filterwarnings("ignore")

DATA_DIR   = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "job-telemetry"
COHORT_DIR = Path(__file__).parent.parent
OUT_DIR    = COHORT_DIR / "analysis"

FLEET_JOB_IDX = 107165

print("Loading cohort manifests...")
cohort_jobs     = pd.read_csv(COHORT_DIR / "cohort_job_list.csv")
cohort_manifest = pd.read_csv(COHORT_DIR / "cohort_manifest.csv")
cohort_nodes    = set(cohort_manifest["hostname"])
longitudinal    = cohort_jobs[cohort_jobs["selection_role"] == "longitudinal_cohort"].copy()
fleet_row       = cohort_jobs[cohort_jobs["job_idx"] == FLEET_JOB_IDX].iloc[0]
print(f"  Longitudinal jobs: {len(longitudinal)}, cohort nodes: {len(cohort_nodes)}")


# ── helpers ────────────────────────────────────────────────────────────────────

def load_temp(job_idx, date_dir):
    job_str = str(job_idx).zfill(6)
    return pq.read_table(
        DATA_DIR / date_dir / job_str / f"{job_str}-cleaned-temperature.parquet"
    ).to_pandas()


def node_mean_gcd_temp(temp_df, nodes_subset=None):
    """
    Returns Series: node -> mean GPU temperature averaged across all GCDs
    and all timestamps.  GCD columns match pattern *_gcd[0-7].
    """
    gcd_cols = [c for c in temp_df.columns
                if c.startswith("frontier") and "_gcd" in c]
    if nodes_subset is not None:
        # strip everything after the first underscore to get hostname
        gcd_cols = [c for c in gcd_cols
                    if c.split("_")[0] in nodes_subset]
    if not gcd_cols:
        return pd.Series(dtype=float)

    # group by node: average across GCDs then across timestamps
    df = temp_df[gcd_cols]
    node_map = {}
    for col in gcd_cols:
        node = col.split("_")[0]
        node_map.setdefault(node, []).append(col)

    result = {}
    for node, cols in node_map.items():
        vals = df[cols].values.flatten()
        vals = vals[np.isfinite(vals)]
        if len(vals):
            result[node] = float(vals.mean())
    return pd.Series(result)


# ── single-pass longitudinal (F^A + F^C) ──────────────────────────────────────

def compute_longitudinal_all(jobs_df):
    FA, FC = {}, {}
    n_jobs = len(jobs_df)
    for i, (_, row) in enumerate(jobs_df.iterrows()):
        if i % 500 == 0:
            print(f"  GPU longitudinal pass: {i}/{n_jobs} jobs", flush=True)
        try:
            temp = load_temp(row["job_idx"], row["date_dir"])
        except Exception:
            continue

        node_temps = node_mean_gcd_temp(temp, cohort_nodes)
        if node_temps.empty:
            continue

        # F^A
        job_mean = node_temps.mean()
        for node, val in node_temps.items():
            FA.setdefault(node, []).append(val - job_mean)

        # F^C
        gcd_cols = [c for c in temp.columns
                    if c.startswith("frontier") and "_gcd" in c]
        cohort_gcd_cols = [c for c in gcd_cols
                           if c.split("_")[0] in cohort_nodes]
        if len(cohort_gcd_cols) < 2:
            continue

        # collapse to node-level first (mean across GCDs per timestamp)
        node_ts = {}
        for col in cohort_gcd_cols:
            node = col.split("_")[0]
            node_ts.setdefault(node, []).append(col)
        node_mean_ts = pd.DataFrame(
            {node: temp[cols].mean(axis=1) for node, cols in node_ts.items()}
        )
        medians = node_mean_ts.median(axis=1)
        residuals = node_mean_ts.subtract(medians, axis=0)
        node_means = residuals.mean(axis=0)
        for node, val in node_means.items():
            FC.setdefault(node, []).append(val)

    FA_s = pd.Series({n: np.mean(d) for n, d in FA.items()}, name="FA_longitudinal")
    FC_s = pd.Series({n: np.mean(d) for n, d in FC.items()}, name="FC_longitudinal")
    return FA_s, FC_s


def compute_fleet_all(fleet_row):
    temp = load_temp(fleet_row["job_idx"], fleet_row["date_dir"])

    node_temps = node_mean_gcd_temp(temp, cohort_nodes)
    FA = (node_temps - node_temps.mean()).rename("FA_fleet")

    # F^C
    gcd_cols = [c for c in temp.columns
                if c.startswith("frontier") and "_gcd" in c]
    cohort_gcd_cols = [c for c in gcd_cols
                       if c.split("_")[0] in cohort_nodes]
    node_ts = {}
    for col in cohort_gcd_cols:
        node = col.split("_")[0]
        node_ts.setdefault(node, []).append(col)
    node_mean_ts = pd.DataFrame(
        {node: temp[cols].mean(axis=1) for node, cols in node_ts.items()}
    )
    medians = node_mean_ts.median(axis=1)
    residuals = node_mean_ts.subtract(medians, axis=0)
    FC = residuals.mean(axis=0).rename("FC_fleet")

    return FA, FC


# ── metrics ────────────────────────────────────────────────────────────────────

def icc_2_1(x, y):
    x, y = np.asarray(x, float), np.asarray(y, float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n, k = len(x), 2
    if n < 3:
        return np.nan
    data = np.column_stack([x, y])
    grand = data.mean()
    row_means = data.mean(axis=1)
    ssb = k * ((row_means - grand) ** 2).sum()
    ssw = ((data - row_means[:, None]) ** 2).sum()
    msb = ssb / (n - 1)
    msw = ssw / (n * (k - 1))
    return float((msb - msw) / (msb + msw))


def bootstrap_ci(x, y, fn, n_boot=1000, seed=42):
    rng = np.random.default_rng(seed)
    x, y = np.asarray(x, float), np.asarray(y, float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    vals = [fn(x[idx := rng.integers(0, n, n)], y[idx]) for _ in range(n_boot)]
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def compute_metrics(long_fp, fleet_fp, label):
    common = long_fp.index.intersection(fleet_fp.index)
    x = long_fp[common].values
    y = fleet_fp[common].values
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    r,  rp  = stats.pearsonr(x, y)
    sr, srp = stats.spearmanr(x, y)
    icc     = icc_2_1(x, y)
    sign_agree = float(np.mean(np.sign(x) == np.sign(y)))
    mae        = float(np.mean(np.abs(x - y)))
    r_ci   = bootstrap_ci(x, y, lambda a, b: stats.pearsonr(a, b)[0])
    icc_ci = bootstrap_ci(x, y, icc_2_1)
    m = {
        "label": label, "n_nodes": int(len(x)),
        "pearson_r": round(float(r), 4), "pearson_p": float(rp),
        "pearson_ci_95": [round(c, 4) for c in r_ci],
        "spearman_r": round(float(sr), 4), "spearman_p": float(srp),
        "icc_2_1": round(icc, 4),
        "icc_ci_95": [round(c, 4) for c in icc_ci],
        "sign_agreement": round(sign_agree, 4),
        "mae_C": round(mae, 4),
    }
    print(f"  F^{label[-1]}: Pearson r={r:.4f} {[round(c,3) for c in r_ci]}, "
          f"Spearman r={sr:.4f}, ICC={icc:.4f}, "
          f"sign_agree={sign_agree:.4f}, MAE={mae:.4f}°C, n={len(x)}")
    return m


def null_permutation_icc(fleet_row, n_perm=1000, seed=0):
    print("  GPU null permutation (n=1000)...", flush=True)
    temp = load_temp(fleet_row["job_idx"], fleet_row["date_dir"])
    gcd_cols = [c for c in temp.columns
                if c.startswith("frontier") and "_gcd" in c]
    cohort_gcd_cols = [c for c in gcd_cols if c.split("_")[0] in cohort_nodes]
    node_ts = {}
    for col in cohort_gcd_cols:
        node = col.split("_")[0]
        node_ts.setdefault(node, []).append(col)
    node_mean_ts = pd.DataFrame(
        {node: temp[cols].mean(axis=1) for node, cols in node_ts.items()}
    )
    medians = node_mean_ts.median(axis=1)
    residuals = node_mean_ts.subtract(medians, axis=0)
    true_fp = residuals.mean(axis=0).values

    rng = np.random.default_rng(seed)
    null_iccs = [icc_2_1(true_fp, rng.permutation(true_fp)) for _ in range(n_perm)]
    return np.array(null_iccs)


def temporal_stability(fleet_row):
    temp = load_temp(fleet_row["job_idx"], fleet_row["date_dir"])
    gcd_cols = [c for c in temp.columns
                if c.startswith("frontier") and "_gcd" in c]
    cohort_gcd_cols = [c for c in gcd_cols if c.split("_")[0] in cohort_nodes]
    node_ts = {}
    for col in cohort_gcd_cols:
        node = col.split("_")[0]
        node_ts.setdefault(node, []).append(col)
    node_mean_ts = pd.DataFrame(
        {node: temp[cols].mean(axis=1) for node, cols in node_ts.items()}
    )
    n = len(node_mean_ts)
    h1, h2 = node_mean_ts.iloc[:n // 2], node_mean_ts.iloc[n // 2:]

    def half_fc(half):
        med = half.median(axis=1)
        return half.subtract(med, axis=0).mean(axis=0)

    fp1, fp2 = half_fc(h1), half_fc(h2)
    common = fp1.index.intersection(fp2.index)
    r, _ = stats.pearsonr(fp1[common].values, fp2[common].values)
    return {"icc_2_1": round(icc_2_1(fp1[common].values, fp2[common].values), 4),
            "pearson_r": round(float(r), 4), "n_nodes": len(common)}


# ── main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== GPU single-pass longitudinal (F^A + F^C) ===")
    FA_long, FC_long = compute_longitudinal_all(longitudinal)

    print("\n=== GPU fleet job 107165 ===")
    FA_fleet, FC_fleet = compute_fleet_all(fleet_row)

    print("\n=== GPU fingerprint table ===")
    gpu_fp = pd.DataFrame({
        "FA_longitudinal": FA_long,
        "FA_fleet":        FA_fleet,
        "FC_longitudinal": FC_long,
        "FC_fleet":        FC_fleet,
    })
    gpu_fp.index.name = "node"
    gpu_fp.to_parquet(OUT_DIR / "gpu_fingerprints.parquet")
    print(f"  Saved gpu_fingerprints.parquet ({len(gpu_fp)} nodes)")
    print(f"  FA_long: {FA_long.notna().sum()} nodes, "
          f"range [{FA_long.min():.2f}, {FA_long.max():.2f}]°C")
    print(f"  FC_long: {FC_long.notna().sum()} nodes, "
          f"range [{FC_long.min():.2f}, {FC_long.max():.2f}]°C")
    print(f"  FA_fleet: {FA_fleet.notna().sum()} nodes, "
          f"range [{FA_fleet.min():.2f}, {FA_fleet.max():.2f}]°C")

    print("\n=== GPU validation metrics ===")
    metrics = {}
    for label, (long_fp, fleet_fp) in [("FA", (FA_long, FA_fleet)),
                                        ("FC", (FC_long, FC_fleet))]:
        metrics[label] = compute_metrics(long_fp, fleet_fp, label)

    print("\n=== GPU temporal stability (fleet split-half) ===")
    ts = temporal_stability(fleet_row)
    metrics["temporal_stability_fleet"] = ts
    print(f"  Split-half ICC={ts['icc_2_1']:.4f}, Pearson r={ts['pearson_r']:.4f}, n={ts['n_nodes']}")

    print("\n=== GPU null permutation test ===")
    null_iccs = null_permutation_icc(fleet_row)
    np.save(OUT_DIR / "gpu_null_distribution.npy", null_iccs)
    obs_icc = metrics["FC"]["icc_2_1"]
    p_null  = float(np.mean(null_iccs >= obs_icc))
    metrics["null_permutation"] = {
        "observed_FC_icc": obs_icc,
        "null_mean_icc":   round(float(null_iccs.mean()), 5),
        "null_p95_icc":    round(float(np.percentile(null_iccs, 95)), 5),
        "p_value":         p_null,
        "n_permutations":  1000,
    }
    print(f"  Observed F^C ICC={obs_icc:.4f}, null mean={null_iccs.mean():.4f}, "
          f"null p95={np.percentile(null_iccs, 95):.4f}, p={p_null:.4f}")

    with open(OUT_DIR / "gpu_validation.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n  Saved gpu_validation.json")
    print("\nDone.")
