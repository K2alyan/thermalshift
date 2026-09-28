"""
Phase 1 thermal fingerprint analysis.

Computes three fingerprint variants for each cohort node:
  F^A  — job fixed-effect residual (mean temp - job mean)
  F^B  — power-corrected residual (F^A after removing within-job power slope)
  F^C  — matched-job residual (node temp - median of co-running cohort nodes)

Each variant is computed separately for:
  longitudinal stream  — 8,303 production jobs (excludes job 107165)
  fleet stream         — job 107165 only (fleet-matched control)

Validation: Pearson r, Spearman rho, ICC(2,1), sign agreement, rank MAE,
            MAE, bootstrap 95% CI, null permutation test (within-job 107165).

Outputs (written to artifacts/phase1/analysis/):
  fingerprints.parquet   — per-node fingerprint table (all variants x streams)
  validation.json        — all scalar metrics
  null_distribution.npy  — permutation null ICC values (n=1000)
"""
# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.



import os
import os, json, warnings
import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy import stats
import os
from pathlib import Path

warnings.filterwarnings("ignore")

# ── paths ──────────────────────────────────────────────────────────────────────
DATA_DIR   = Path(os.environ.get("THERMALSHIFT_DATA_DIR", "")) / "job-telemetry"
COHORT_DIR = Path(__file__).parent.parent
OUT_DIR    = COHORT_DIR / "analysis"
OUT_DIR.mkdir(exist_ok=True)

FLEET_JOB_IDX = 107165

# ── load manifests ─────────────────────────────────────────────────────────────
print("Loading cohort manifests...")
cohort_jobs     = pd.read_csv(COHORT_DIR / "cohort_job_list.csv")
cohort_manifest = pd.read_csv(COHORT_DIR / "cohort_manifest.csv")
cohort_nodes    = set(cohort_manifest["hostname"])

longitudinal = cohort_jobs[cohort_jobs["selection_role"] == "longitudinal_cohort"].copy()
fleet_row    = cohort_jobs[cohort_jobs["job_idx"] == FLEET_JOB_IDX].iloc[0]

print(f"  Longitudinal jobs: {len(longitudinal)}")
print(f"  Cohort nodes: {len(cohort_nodes)}")


# ── helpers ────────────────────────────────────────────────────────────────────

def load_job(job_idx, date_dir):
    job_str = str(job_idx).zfill(6)
    jdir = DATA_DIR / date_dir / job_str
    temp = pq.read_table(jdir / f"{job_str}-cleaned-temperature.parquet").to_pandas()
    power = pq.read_table(jdir / f"{job_str}-cleaned-power.parquet").to_pandas()
    return temp, power


def node_mean_cpu_temp(temp_df, nodes_subset=None):
    """
    Returns Series: node -> mean CPU temperature across all timestamps.
    Only CPU columns. Optionally restrict to nodes_subset.
    """
    cpu_cols = [c for c in temp_df.columns if c.startswith("frontier") and c.endswith("_cpu")]
    if nodes_subset is not None:
        cpu_cols = [c for c in cpu_cols if c.replace("_cpu", "") in nodes_subset]
    if not cpu_cols:
        return pd.Series(dtype=float)
    sub = temp_df[cpu_cols]
    means = sub.mean(axis=0)
    means.index = [c.replace("_cpu", "") for c in means.index]
    return means


def node_mean_node_power(power_df, nodes_subset=None):
    """
    Returns Series: node -> mean node-level power across all timestamps.
    """
    node_cols = [c for c in power_df.columns if c.startswith("frontier") and c.endswith("_node")]
    if nodes_subset is not None:
        node_cols = [c for c in node_cols if c.replace("_node", "") in nodes_subset]
    if not node_cols:
        return pd.Series(dtype=float)
    sub = power_df[node_cols]
    means = sub.mean(axis=0)
    means.index = [c.replace("_node", "") for c in means.index]
    return means


# ── single-pass longitudinal accumulator (computes F^A, F^B, F^C together) ────

def power_corrected_residual(node_temps, node_powers):
    """
    Regress temp on power across nodes; return mean-centered residuals.
    Returns None if regression is impossible (< 3 common nodes or constant power).
    """
    common = node_temps.index.intersection(node_powers.index)
    if len(common) < 3:
        return None
    t = node_temps[common].values
    p = node_powers[common].values
    if np.ptp(p) == 0:
        return None
    slope, intercept, _, _, _ = stats.linregress(p, t)
    fitted = intercept + slope * p
    resids = pd.Series(t - fitted, index=common)
    return resids - resids.mean()


def compute_longitudinal_all(jobs_df):
    """
    Single pass over all longitudinal jobs.
    Returns (FA_accum, FB_accum, FC_accum): dicts of node -> [values].
    """
    FA, FB, FC = {}, {}, {}
    n_jobs = len(jobs_df)
    for i, (_, row) in enumerate(jobs_df.iterrows()):
        if i % 500 == 0:
            print(f"  Longitudinal pass: {i}/{n_jobs} jobs", flush=True)
        try:
            temp, power = load_job(row["job_idx"], row["date_dir"])
        except Exception:
            continue

        # --- F^A ---
        node_temps = node_mean_cpu_temp(temp, cohort_nodes)
        if node_temps.empty:
            continue
        job_mean = node_temps.mean()
        for node, val in node_temps.items():
            FA.setdefault(node, []).append(val - job_mean)

        # --- F^B ---
        node_powers = node_mean_node_power(power, cohort_nodes)
        if not node_powers.empty:
            resids = power_corrected_residual(node_temps, node_powers)
            if resids is not None:
                for node, val in resids.items():
                    if node in cohort_nodes:
                        FB.setdefault(node, []).append(val)

        # --- F^C ---
        cpu_cols = [c for c in temp.columns if c.startswith("frontier") and c.endswith("_cpu")]
        cohort_cpu_cols = [c for c in cpu_cols if c.replace("_cpu", "") in cohort_nodes]
        if len(cohort_cpu_cols) >= 2:
            sub = temp[cohort_cpu_cols]
            medians = sub.median(axis=1)
            residuals = sub.subtract(medians, axis=0)
            node_means = residuals.mean(axis=0)
            node_means.index = [c.replace("_cpu", "") for c in node_means.index]
            for node, val in node_means.items():
                FC.setdefault(node, []).append(val)

    FA_s = pd.Series({n: np.mean(d) for n, d in FA.items()}, name="FA_longitudinal")
    FB_s = pd.Series({n: np.mean(d) for n, d in FB.items()}, name="FB_longitudinal")
    FC_s = pd.Series({n: np.mean(d) for n, d in FC.items()}, name="FC_longitudinal")
    return FA_s, FB_s, FC_s


def compute_fleet_all(fleet_row):
    """Single pass over fleet job 107165. Returns FA, FB, FC series."""
    temp, power = load_job(fleet_row["job_idx"], fleet_row["date_dir"])

    node_temps = node_mean_cpu_temp(temp, cohort_nodes)
    FA = (node_temps - node_temps.mean()).rename("FA_fleet")

    node_powers = node_mean_node_power(power, cohort_nodes)
    _fb = power_corrected_residual(node_temps, node_powers)
    FB = (_fb if _fb is not None else pd.Series(dtype=float)).rename("FB_fleet")

    cpu_cols = [c for c in temp.columns if c.startswith("frontier") and c.endswith("_cpu")]
    cohort_cpu_cols = [c for c in cpu_cols if c.replace("_cpu", "") in cohort_nodes]
    sub = temp[cohort_cpu_cols]
    medians = sub.median(axis=1)
    residuals = sub.subtract(medians, axis=0)
    node_means = residuals.mean(axis=0)
    node_means.index = [c.replace("_cpu", "") for c in node_means.index]
    FC = node_means.rename("FC_fleet")

    return FA, FB, FC


# ── validation metrics ─────────────────────────────────────────────────────────

def icc_2_1(x, y):
    """ICC(2,1) — two-way random, single measures, k=2 raters."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n, k = len(x), 2
    if n < 3:
        return np.nan
    data = np.column_stack([x, y])
    grand = data.mean()
    row_means = data.mean(axis=1)
    ssb = k * ((row_means - grand) ** 2).sum()   # multiplied by k, not n
    ssw = ((data - row_means[:, None]) ** 2).sum()
    msb = ssb / (n - 1)
    msw = ssw / (n * (k - 1))
    return float((msb - msw) / (msb + msw))


def bootstrap_ci(x, y, metric_fn, n_boot=1000, seed=42):
    rng = np.random.default_rng(seed)
    x, y = np.asarray(x, float), np.asarray(y, float)
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)
    vals = []
    for _ in range(n_boot):
        idx = rng.integers(0, n, n)  # same idx keeps pairs intact
        vals.append(metric_fn(x[idx], y[idx]))
    return float(np.percentile(vals, 2.5)), float(np.percentile(vals, 97.5))


def compute_metrics(longitudinal_fp, fleet_fp, label):
    common = longitudinal_fp.index.intersection(fleet_fp.index)
    x = longitudinal_fp[common].values
    y = fleet_fp[common].values
    mask = np.isfinite(x) & np.isfinite(y)
    x, y = x[mask], y[mask]
    n = len(x)

    pearson_r, pearson_p = stats.pearsonr(x, y)
    spearman_r, spearman_p = stats.spearmanr(x, y)
    icc = icc_2_1(x, y)
    sign_agree = float(np.mean(np.sign(x) == np.sign(y)))
    rank_mae = float(np.mean(np.abs(stats.rankdata(x) - stats.rankdata(y))))
    mae = float(np.mean(np.abs(x - y)))

    pearson_ci = bootstrap_ci(x, y, lambda a, b: stats.pearsonr(a, b)[0])
    icc_ci     = bootstrap_ci(x, y, icc_2_1)

    return {
        "label": label,
        "n_nodes": n,
        "pearson_r": float(pearson_r),
        "pearson_p": float(pearson_p),
        "pearson_ci_95": pearson_ci,
        "spearman_r": float(spearman_r),
        "spearman_p": float(spearman_p),
        "icc_2_1": icc,
        "icc_ci_95": icc_ci,
        "sign_agreement": sign_agree,
        "rank_mae": rank_mae,
        "mae_C": mae,
    }


# ── null permutation test on fleet job 107165 ─────────────────────────────────

def null_permutation_icc(fleet_row, n_perm=1000, seed=0):
    """
    Within job 107165: permute node identity, compute ICC vs un-permuted.
    Produces null distribution of ICC under no-fingerprint hypothesis.
    """
    print("  Computing null permutation distribution (n=1000)...", flush=True)
    temp, _ = load_job(fleet_row["job_idx"], fleet_row["date_dir"])
    cpu_cols = [c for c in temp.columns if c.startswith("frontier") and c.endswith("_cpu")]
    cohort_cpu_cols = [c for c in cpu_cols if c.replace("_cpu", "") in cohort_nodes]
    sub = temp[cohort_cpu_cols]
    medians = sub.median(axis=1)
    residuals = sub.subtract(medians, axis=0)
    true_fp = residuals.mean(axis=0).values

    rng = np.random.default_rng(seed)
    null_iccs = []
    for _ in range(n_perm):
        perm = rng.permutation(true_fp)
        null_iccs.append(icc_2_1(true_fp, perm))
    return np.array(null_iccs)


# ── temporal stability within fleet job ───────────────────────────────────────

def temporal_stability_fleet(fleet_row):
    """
    Split job 107165 timestamps in half. Compute F^C on each half.
    Report ICC between halves.
    """
    temp, _ = load_job(fleet_row["job_idx"], fleet_row["date_dir"])
    cpu_cols = [c for c in temp.columns if c.startswith("frontier") and c.endswith("_cpu")]
    cohort_cpu_cols = [c for c in cpu_cols if c.replace("_cpu", "") in cohort_nodes]
    sub = temp[cohort_cpu_cols]
    n = len(sub)
    h1, h2 = sub.iloc[:n // 2], sub.iloc[n // 2:]

    def half_fp(half):
        med = half.median(axis=1)
        res = half.subtract(med, axis=0)
        return res.mean(axis=0)

    fp1 = half_fp(h1)
    fp2 = half_fp(h2)
    common = fp1.index.intersection(fp2.index)
    icc = icc_2_1(fp1[common].values, fp2[common].values)
    pearson_r, _ = stats.pearsonr(fp1[common].values, fp2[common].values)
    return {"icc_2_1": float(icc), "pearson_r": float(pearson_r), "n_nodes": len(common)}


# ── main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== Single-pass longitudinal (F^A + F^B + F^C) ===")
    FA_long, FB_long, FC_long = compute_longitudinal_all(longitudinal)

    print("\n=== Fleet job 107165 (F^A + F^B + F^C) ===")
    FA_fleet, FB_fleet, FC_fleet = compute_fleet_all(fleet_row)

    print("\n=== Assembling fingerprint table ===")
    fp_table = pd.DataFrame({
        "FA_longitudinal": FA_long,
        "FA_fleet":        FA_fleet,
        "FB_longitudinal": FB_long,
        "FB_fleet":        FB_fleet,
        "FC_longitudinal": FC_long,
        "FC_fleet":        FC_fleet,
    })
    fp_table.index.name = "node"
    fp_table.to_parquet(OUT_DIR / "fingerprints.parquet")
    print(f"  Saved fingerprints.parquet ({len(fp_table)} nodes)")

    print("\n=== Validation metrics ===")
    metrics = {}
    for label, (long_fp, fleet_fp) in [
        ("FA", (FA_long, FA_fleet)),
        ("FB", (FB_long, FB_fleet)),
        ("FC", (FC_long, FC_fleet)),
    ]:
        m = compute_metrics(long_fp, fleet_fp, label)
        metrics[label] = m
        print(f"  {label}: Pearson r={m['pearson_r']:.3f}, Spearman r={m['spearman_r']:.3f}, "
              f"ICC={m['icc_2_1']:.3f}, sign_agree={m['sign_agreement']:.3f}, "
              f"MAE={m['mae_C']:.3f} C, n={m['n_nodes']}")

    print("\n=== Temporal stability (fleet job split-half) ===")
    ts = temporal_stability_fleet(fleet_row)
    metrics["temporal_stability_fleet"] = ts
    print(f"  Split-half ICC={ts['icc_2_1']:.3f}, Pearson r={ts['pearson_r']:.3f}, n={ts['n_nodes']}")

    print("\n=== Null permutation test ===")
    null_iccs = null_permutation_icc(fleet_row)
    np.save(OUT_DIR / "null_distribution.npy", null_iccs)
    observed_icc = metrics["FC"]["icc_2_1"]
    p_null = float(np.mean(null_iccs >= observed_icc))
    metrics["null_permutation"] = {
        "observed_FC_icc": observed_icc,
        "null_mean_icc":   float(null_iccs.mean()),
        "null_p95_icc":    float(np.percentile(null_iccs, 95)),
        "p_value":         p_null,
        "n_permutations":  1000,
    }
    print(f"  Observed F^C ICC={observed_icc:.3f}, null mean={null_iccs.mean():.3f}, "
          f"null p95={np.percentile(null_iccs, 95):.3f}, p={p_null:.4f}")

    with open(OUT_DIR / "validation.json", "w") as f:
        json.dump(metrics, f, indent=2)
    print(f"\n  Saved validation.json")
    print("\nDone.")
