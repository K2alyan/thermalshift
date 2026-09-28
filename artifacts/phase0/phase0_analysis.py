"""
Phase 0 Hypothesis Validation: Thermal Fingerprint Experiment
Tests H1 (power explains temp), H2 (node identity explains residual), H3 (fingerprint stability).
Unit of analysis: GCD level (8 per node, one row per GCD per 60s timestep).
"""
# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.



import os
import pyarrow.parquet as pq
import pandas as pd
import numpy as np
import json
import os
import sys
import os
from pathlib import Path
from scipy import stats

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

# ── Paths ──────────────────────────────────────────────────────────────────────
SAMPLE_BASE = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))
OUT_DIR = Path(__file__).parent
FIG_DIR = OUT_DIR / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

np.random.seed(42)

# ── 1. Data loading ────────────────────────────────────────────────────────────

def load_job(job_dir: Path, job_idx: str) -> pd.DataFrame | None:
    """Load one job -> long-format DataFrame: (job_idx, hostname, gcd_id, gpu_id, ts, gcd_temp, gpu_power)."""
    t_file = job_dir / f"{job_idx}-cleaned-temperature.parquet"
    p_file = job_dir / f"{job_idx}-cleaned-power.parquet"
    if not t_file.exists() or not p_file.exists():
        return None

    try:
        t_df = pq.read_table(t_file).to_pandas()
        p_df = pq.read_table(p_file).to_pandas()
    except Exception:
        return None

    t_df["Timestamp"] = pd.to_datetime(t_df["Timestamp"])
    p_df["Timestamp"] = pd.to_datetime(p_df["Timestamp"])

    # Resample power to 60s bins (mean) matching temperature resolution
    p_df = p_df.set_index("Timestamp").resample("60s").mean(numeric_only=True).reset_index()

    # Infer hostnames from temperature columns (_cpu suffix)
    hostnames = [c.replace("_cpu", "") for c in t_df.columns if c.endswith("_cpu") and "ncount" not in c]

    rows = []
    for host in hostnames:
        for gpu_id in range(4):
            for gcd_in_gpu in range(2):
                gcd_id = gpu_id * 2 + gcd_in_gpu
                temp_col = f"{host}_gpu{gpu_id}_gcd{gcd_id}"
                power_col = f"{host}_gpu{gpu_id}"
                if temp_col not in t_df.columns or power_col not in p_df.columns:
                    continue

                merged = pd.merge_asof(
                    t_df[["Timestamp", temp_col]].sort_values("Timestamp"),
                    p_df[["Timestamp", power_col]].sort_values("Timestamp"),
                    on="Timestamp",
                    tolerance=pd.Timedelta("65s"),
                    direction="nearest"
                )
                merged = merged.dropna(subset=[temp_col, power_col])
                if len(merged) < 3:
                    continue

                merged["job_idx"] = job_idx
                merged["hostname"] = host
                merged["gcd_id"] = gcd_id
                merged["gpu_id"] = gpu_id
                merged["gcd_temp"] = pd.to_numeric(merged[temp_col], errors="coerce")
                merged["gpu_power"] = pd.to_numeric(merged[power_col], errors="coerce")
                merged = merged.dropna(subset=["gcd_temp", "gpu_power"])
                rows.append(merged[["job_idx", "hostname", "gcd_id", "gpu_id", "Timestamp", "gcd_temp", "gpu_power"]])

    if not rows:
        return None
    return pd.concat(rows, ignore_index=True)


def load_all_jobs(base: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load all jobs from the sample. Returns (long_df, job_info_df)."""
    ji = pq.read_table(base / "frontier-completed-job-info-SAMPLE.parquet").to_pandas()
    ji["start_time"] = pd.to_datetime(ji["start_time"])
    ji["end_time"] = pd.to_datetime(ji["end_time"])

    job_dirs = sorted((base / "job-telemetry").iterdir())
    all_frames = []
    loaded = 0
    skipped = 0
    for jd in job_dirs:
        job_idx = jd.name
        df = load_job(jd, job_idx)
        if df is not None and len(df) > 0:
            all_frames.append(df)
            loaded += 1
        else:
            skipped += 1

    print(f"Loaded {loaded} jobs, skipped {skipped}")
    if not all_frames:
        raise RuntimeError("No jobs loaded — check paths")
    return pd.concat(all_frames, ignore_index=True), ji


# ── 2. Node reuse quantification ───────────────────────────────────────────────

def quantify_node_reuse(df: pd.DataFrame, ji: pd.DataFrame) -> dict:
    """Count how many jobs each node appears in."""
    node_job_counts = df.groupby("hostname")["job_idx"].nunique()
    reused = (node_job_counts >= 2).sum()
    multi_job_nodes = node_job_counts[node_job_counts >= 2]
    return {
        "total_nodes": int(node_job_counts.shape[0]),
        "nodes_in_1_job": int((node_job_counts == 1).sum()),
        "nodes_in_2plus_jobs": int(reused),
        "nodes_in_5plus_jobs": int((node_job_counts >= 5).sum()),
        "max_jobs_per_node": int(node_job_counts.max()),
        "median_jobs_per_node": float(node_job_counts.median()),
        "reuse_fraction": float(reused / len(node_job_counts)),
        "multi_job_node_examples": node_job_counts.nlargest(5).to_dict(),
    }


# ── 3. H1: Power explains temperature ─────────────────────────────────────────

def test_h1_power(df: pd.DataFrame) -> dict:
    """
    H1: Power explains most GCD temperature variation.
    Model A: T = α + beta·P (global OLS, no conditioning).
    Also compute within-job demeaned version.
    """
    # Model A: global regression
    X = df["gpu_power"].values
    y = df["gcd_temp"].values
    mask = np.isfinite(X) & np.isfinite(y)
    X, y = X[mask], y[mask]

    slope_A, intercept_A, r_A, p_A, se_A = stats.linregress(X, y)
    r2_A = r_A ** 2
    resid_A = y - (intercept_A + slope_A * X)

    # Model B: within-job demeaned (job fixed effects)
    df2 = df[mask].copy()
    job_means = df2.groupby("job_idx")[["gcd_temp", "gpu_power"]].transform("mean")
    df2["T_dem"] = df2["gcd_temp"] - job_means["gcd_temp"]
    df2["P_dem"] = df2["gpu_power"] - job_means["gpu_power"]

    slope_B, intercept_B, r_B, p_B, se_B = stats.linregress(df2["P_dem"].values, df2["T_dem"].values)
    r2_B = r_B ** 2
    df2["resid_B"] = df2["T_dem"] - slope_B * df2["P_dem"]

    print(f"\n=== H1: Power -> Temperature ===")
    print(f"  Model A (global):      R2={r2_A:.3f}  beta={slope_A:.4f} degC/W  N={len(y):,}")
    print(f"  Model B (within-job):  R2={r2_B:.3f}  beta={slope_B:.4f} degC/W")

    return {
        "r2_global": float(r2_A),
        "beta_global_degC_per_W": float(slope_A),
        "intercept_global": float(intercept_A),
        "r2_within_job": float(r2_B),
        "beta_within_job_degC_per_W": float(slope_B),
        "n_obs": int(len(y)),
        "resid_A": resid_A,
        "df_B": df2,
    }


# ── 4. H2: Node identity explains residual (ICC) ──────────────────────────────

def compute_icc_anova(values: np.ndarray, groups: np.ndarray) -> dict:
    """
    One-way ANOVA-based ICC.
    ICC = (MS_between - MS_within) / (MS_between + (n0-1)*MS_within)
    where n0 is the harmonic mean of group sizes.
    """
    unique_groups, group_inv = np.unique(groups, return_inverse=True)
    k = len(unique_groups)
    if k < 2:
        return {"icc": 0.0, "f_stat": np.nan, "p_value": np.nan, "k_groups": k}

    N = len(values)
    grand_mean = values.mean()
    group_ns = np.bincount(group_inv)
    group_means = np.bincount(group_inv, weights=values) / group_ns

    SS_between = np.sum(group_ns * (group_means - grand_mean) ** 2)
    SS_within = float(np.sum((values - group_means[group_inv]) ** 2))
    df_between = k - 1
    df_within = N - k

    if df_between <= 0 or df_within <= 0:
        return {"icc": 0.0, "f_stat": np.nan, "p_value": np.nan, "k_groups": k}

    MS_between = SS_between / df_between
    MS_within = SS_within / df_within

    f_stat = MS_between / MS_within if MS_within > 0 else np.inf
    p_value = 1 - stats.f.cdf(f_stat, df_between, df_within)

    # Harmonic mean of group sizes
    n0 = k / np.sum(1.0 / group_ns)
    icc = max(0.0, (MS_between - MS_within) / (MS_between + (n0 - 1) * MS_within))

    return {
        "icc": float(icc),
        "f_stat": float(f_stat),
        "p_value": float(p_value),
        "k_groups": int(k),
        "MS_between": float(MS_between),
        "MS_within": float(MS_within),
        "n0_harmonic": float(n0),
    }


def bootstrap_icc(values: np.ndarray, groups: np.ndarray, n_boot: int = 200) -> tuple[float, float]:
    """Bootstrap CI for ICC resampling at node level (vectorized for speed)."""
    unique_nodes, group_inv = np.unique(groups, return_inverse=True)
    k = len(unique_nodes)
    # Build node->obs index lookup once
    node_idx = [np.where(group_inv == i)[0] for i in range(k)]
    icc_boot = []
    for b in range(n_boot):
        if b % 50 == 0:
            print(f"  Bootstrap {b}/{n_boot}...", flush=True)
        sampled = np.random.randint(0, k, size=k)
        idx = np.concatenate([node_idx[i] for i in sampled])
        icc_b = compute_icc_anova(values[idx], group_inv[idx])["icc"]
        icc_boot.append(icc_b)
    arr = np.array(icc_boot)
    return float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))


def test_h2_node_identity(h1_results: dict) -> dict:
    """H2: Node identity explains residual variance (ICC on resid_A and resid_B)."""
    df2 = h1_results["df_B"]
    resid_A = h1_results["resid_A"]

    # ICC on global residuals (resid_A) — using nodes from the aligned df
    # Need to align resid_A with the original filtered df
    # resid_A corresponds to df after mask applied in h1; we use df2 which has mask applied
    # For resid_A, compute on df2 rows (both use same mask)
    nodes_A = df2["hostname"].values
    icc_A = compute_icc_anova(resid_A[: len(nodes_A)], nodes_A)

    # ICC on within-job demeaned residuals (resid_B)
    nodes_B = df2["hostname"].values
    resid_B_vals = df2["resid_B"].values
    mask_B = np.isfinite(resid_B_vals)
    icc_B = compute_icc_anova(resid_B_vals[mask_B], nodes_B[mask_B])

    print(f"\n=== H2: Node Identity (ICC) ===", flush=True)
    print(f"  ICC(resid_A, global):     {icc_A['icc']:.3f}  F={icc_A['f_stat']:.1f}  p={icc_A['p_value']:.4f}  k={icc_A['k_groups']}", flush=True)
    print(f"  ICC(resid_B, within-job): {icc_B['icc']:.3f}  F={icc_B['f_stat']:.1f}  p={icc_B['p_value']:.4f}  k={icc_B['k_groups']}", flush=True)

    # Bootstrap CI on resid_B (cleaner estimate)
    print("  Computing bootstrap CI for ICC(resid_B)...", flush=True)
    ci_lo, ci_hi = bootstrap_icc(resid_B_vals[mask_B], nodes_B[mask_B], n_boot=200)
    print(f"  Bootstrap 95% CI: [{ci_lo:.3f}, {ci_hi:.3f}]")

    # Node-level fingerprints: mean residual per node
    df2["resid_B_valid"] = np.where(mask_B, resid_B_vals, np.nan)
    node_fingerprints = df2.groupby("hostname")["resid_B_valid"].agg(["mean", "std", "count"]).reset_index()
    node_fingerprints.columns = ["hostname", "mean_resid", "std_resid", "n_obs"]
    node_fingerprints = node_fingerprints[node_fingerprints["n_obs"] >= 5]

    return {
        "icc_global_residual": icc_A,
        "icc_within_job_residual": icc_B,
        "icc_within_job_ci95": [ci_lo, ci_hi],
        "node_fingerprints": node_fingerprints,
        "df_with_resid": df2,
    }


# ── 5. H3: Fingerprint stability ───────────────────────────────────────────────

def test_h3_stability(h2_results: dict, ji: pd.DataFrame) -> dict:
    """
    H3: Fingerprints estimated on first-half jobs predict second-half jobs.
    Split jobs by start_time (temporal). For each node seen in both halves,
    compare mean residual in first vs. second half.
    """
    df2 = h2_results["df_with_resid"]

    # Temporal job split
    job_times = ji[["job_idx", "start_time"]].dropna().set_index("job_idx")["start_time"]
    df2["start_time"] = df2["job_idx"].map(job_times)
    df2 = df2.dropna(subset=["start_time"])

    time_median = df2["start_time"].median()
    df2["half"] = (df2["start_time"] > time_median).map({False: "first", True: "second"})

    # Per-node, per-half mean residual
    node_half = (
        df2.groupby(["hostname", "half"])["resid_B_valid"]
        .agg(["mean", "count"])
        .reset_index()
    )
    node_half.columns = ["hostname", "half", "mean_resid", "n_obs"]
    node_half = node_half[node_half["n_obs"] >= 3]

    first = node_half[node_half["half"] == "first"].set_index("hostname")["mean_resid"]
    second = node_half[node_half["half"] == "second"].set_index("hostname")["mean_resid"]
    common = first.index.intersection(second.index)

    if len(common) < 3:
        print(f"\n=== H3: Stability ===")
        print(f"  Only {len(common)} nodes seen in both halves — insufficient for stability test")
        return {
            "n_common_nodes": int(len(common)),
            "r_stability": None,
            "p_stability": None,
            "verdict": "insufficient_reuse",
        }

    r_val, p_val = stats.pearsonr(first[common].values, second[common].values)
    spearman_r, spearman_p = stats.spearmanr(first[common].values, second[common].values)

    print(f"\n=== H3: Fingerprint Stability ===")
    print(f"  Nodes in both halves: {len(common)}")
    print(f"  Pearson  r={r_val:.3f}  p={p_val:.4f}")
    print(f"  Spearman r={spearman_r:.3f}  p={spearman_p:.4f}")

    return {
        "n_common_nodes": int(len(common)),
        "r_stability": float(r_val),
        "p_stability": float(p_val),
        "spearman_r": float(spearman_r),
        "spearman_p": float(spearman_p),
        "first_half_fingerprints": first[common].to_dict(),
        "second_half_fingerprints": second[common].to_dict(),
        "split_time": str(time_median),
        "n_first_half_jobs": int((df2[df2["half"] == "first"]["job_idx"].nunique())),
        "n_second_half_jobs": int((df2[df2["half"] == "second"]["job_idx"].nunique())),
    }


# ── 6. GCD-level analysis ──────────────────────────────────────────────────────

def analyze_gcd_level(h2_results: dict) -> dict:
    """
    Does thermal fingerprint vary by GCD position within a node?
    Compute ICC separately for each GCD slot (0-7).
    Also test whether GCD position itself predicts residual (GPU position effect).
    """
    df2 = h2_results["df_with_resid"].copy()
    mask = np.isfinite(df2["resid_B_valid"].values)
    df2 = df2[mask]

    icc_by_gcd = {}
    for gcd_id in range(8):
        sub = df2[df2["gcd_id"] == gcd_id]
        if len(sub) < 20:
            continue
        icc_res = compute_icc_anova(sub["resid_B_valid"].values, sub["hostname"].values)
        icc_by_gcd[gcd_id] = icc_res["icc"]
        print(f"  GCD {gcd_id}: ICC={icc_res['icc']:.3f}  k={icc_res['k_groups']}")

    # GCD position effect: does gcd_id predict residual after controlling for node?
    # Demean by node first
    node_means = df2.groupby("hostname")["resid_B_valid"].transform("mean")
    df2["resid_node_dem"] = df2["resid_B_valid"] - node_means
    gcd_means = df2.groupby("gcd_id")["resid_node_dem"].mean()

    print(f"\n=== GCD Position Effect (mean residual per GCD slot, node-demeaned) ===")
    for gcd_id, mu in gcd_means.items():
        print(f"  GCD {gcd_id}: {mu:+.2f} degC")

    # F-test for GCD position effect
    groups = [df2[df2["gcd_id"] == g]["resid_node_dem"].dropna().values for g in range(8) if len(df2[df2["gcd_id"] == g]) > 5]
    if len(groups) >= 2:
        f_gcd, p_gcd = stats.f_oneway(*groups)
    else:
        f_gcd, p_gcd = np.nan, np.nan

    print(f"  F-test GCD position: F={f_gcd:.2f}  p={p_gcd:.4f}")

    return {
        "icc_by_gcd": icc_by_gcd,
        "gcd_position_means": gcd_means.to_dict(),
        "f_gcd_position": float(f_gcd) if np.isfinite(f_gcd) else None,
        "p_gcd_position": float(p_gcd) if np.isfinite(p_gcd) else None,
    }


# ── 7. Spatial structure (xname topology) ──────────────────────────────────────

def parse_xname(xname: str) -> dict | None:
    """Parse Frontier xname like 'x2507c2s7b1n0' -> rack/chassis/slot."""
    import re
    m = re.match(r"x(\d+)c(\d+)s(\d+)b(\d+)n(\d+)", xname)
    if not m:
        return None
    rack, chassis, slot, board, node = [int(x) for x in m.groups()]
    return {"rack": rack, "chassis": chassis, "slot": slot, "board": board, "node": node, "xname": xname}


def analyze_spatial(h2_results: dict, ji: pd.DataFrame) -> dict:
    """
    Parse xnames from job_info node_list and correlate with fingerprints.
    Test if rack/chassis explains spatial clustering of fingerprints.
    """
    node_fingerprints = h2_results["node_fingerprints"]
    if len(node_fingerprints) == 0:
        return {"error": "no fingerprints"}

    # Build hostname -> xname mapping from node_list
    xname_map = {}
    for _, row in ji.iterrows():
        node_list = row.get("node_list", None)
        host_list = row.get("host_list", None)
        if node_list is None or host_list is None:
            continue
        try:
            # node_list and host_list are lists of equal length
            for xname, host in zip(node_list, host_list):
                if host not in xname_map:
                    xname_map[host] = xname
        except Exception:
            continue

    # Parse rack/chassis for each fingerprinted node
    spatial_rows = []
    for _, row in node_fingerprints.iterrows():
        host = row["hostname"]
        xname = xname_map.get(host, None)
        if xname is None:
            continue
        parsed = parse_xname(xname)
        if parsed is None:
            continue
        parsed["hostname"] = host
        parsed["mean_resid"] = row["mean_resid"]
        parsed["n_obs"] = row["n_obs"]
        spatial_rows.append(parsed)

    if len(spatial_rows) < 5:
        print(f"\n=== Spatial Analysis ===")
        print(f"  Only {len(spatial_rows)} nodes with xname mappings — limited spatial analysis")
        return {"n_spatial_nodes": len(spatial_rows), "spatial_df": pd.DataFrame(spatial_rows)}

    sp_df = pd.DataFrame(spatial_rows)
    print(f"\n=== Spatial Analysis ===")
    print(f"  Nodes with xname: {len(sp_df)}")
    print(f"  Racks covered: {sp_df['rack'].nunique()}")
    print(f"  Chassis covered: {sp_df['chassis'].nunique()}")

    # ICC of fingerprints by rack
    if sp_df["rack"].nunique() >= 2:
        icc_rack = compute_icc_anova(sp_df["mean_resid"].values, sp_df["rack"].values)
        print(f"  ICC(fingerprint ~ rack): {icc_rack['icc']:.3f}  F={icc_rack['f_stat']:.2f}  p={icc_rack['p_value']:.4f}")
    else:
        icc_rack = {"icc": None}

    # ICC by chassis
    if sp_df["chassis"].nunique() >= 2:
        icc_chassis = compute_icc_anova(sp_df["mean_resid"].values, sp_df["chassis"].values)
        print(f"  ICC(fingerprint ~ chassis): {icc_chassis['icc']:.3f}  F={icc_chassis['f_stat']:.2f}  p={icc_chassis['p_value']:.4f}")
    else:
        icc_chassis = {"icc": None}

    return {
        "n_spatial_nodes": len(sp_df),
        "n_racks": int(sp_df["rack"].nunique()),
        "n_chassis": int(sp_df["chassis"].nunique()),
        "icc_by_rack": icc_rack,
        "icc_by_chassis": icc_chassis,
        "spatial_df": sp_df,
    }


# ── 8. Negative controls ────────────────────────────────────────────────────────

def negative_controls(h2_results: dict) -> dict:
    """
    Three negative controls to verify the ICC signal is real.
    NC1: Permute node labels within jobs — should collapse ICC to ~0.
    NC2: Cross-node fingerprint mismatch — predict second-half with wrong node's fingerprint.
    NC3: Random-group demeaning vs job demeaning — compare R2 to confirm job conditioning matters.
    """
    df2 = h2_results["df_with_resid"].copy()
    mask = np.isfinite(df2["resid_B_valid"].values)
    df2 = df2[mask]

    results = {}

    # NC1: Permute node labels within each job -> ICC should -> 0
    df_perm = df2.copy()
    for job in df_perm["job_idx"].unique():
        idx = df_perm[df_perm["job_idx"] == job].index
        nodes = df_perm.loc[idx, "hostname"].values.copy()
        np.random.shuffle(nodes)
        df_perm.loc[idx, "hostname"] = nodes
    icc_perm = compute_icc_anova(df_perm["resid_B_valid"].values, df_perm["hostname"].values)
    print(f"\n=== NC1: Permuted node labels ===")
    print(f"  ICC={icc_perm['icc']:.3f}  (expect ~0)")
    results["nc1_permuted_icc"] = icc_perm["icc"]

    # NC2: Fingerprint mismatch — shift node index by 1 for prediction
    node_fp = df2.groupby("hostname")["resid_B_valid"].mean()
    nodes = node_fp.index.tolist()
    shifted = {nodes[i]: node_fp[nodes[(i + 1) % len(nodes)]] for i in range(len(nodes))}
    df2["fp_wrong"] = df2["hostname"].map(shifted)
    df2["fp_correct"] = df2["hostname"].map(node_fp)
    has_both = df2.dropna(subset=["fp_wrong", "fp_correct"])
    if len(has_both) > 10:
        r_correct, _ = stats.pearsonr(has_both["resid_B_valid"], has_both["fp_correct"])
        r_wrong, _ = stats.pearsonr(has_both["resid_B_valid"], has_both["fp_wrong"])
        print(f"\n=== NC2: Fingerprint mismatch ===")
        print(f"  r(resid, correct fingerprint) = {r_correct:.3f}")
        print(f"  r(resid, wrong fingerprint)   = {r_wrong:.3f}  (expect ~0)")
        results["nc2_r_correct"] = float(r_correct)
        results["nc2_r_wrong"] = float(r_wrong)
    else:
        results["nc2_r_correct"] = None
        results["nc2_r_wrong"] = None

    # NC3: Random group demeaning — assign random groups of same size as jobs, compute R2
    df_rand = df2.copy()
    n_jobs = df2["job_idx"].nunique()
    rand_groups = np.random.randint(0, n_jobs, size=len(df_rand))
    rand_means_T = pd.Series(df_rand["gcd_temp"].values).groupby(rand_groups).transform("mean")
    rand_means_P = pd.Series(df_rand["gpu_power"].values).groupby(rand_groups).transform("mean")
    T_dem_rand = df_rand["gcd_temp"].values - rand_means_T.values
    P_dem_rand = df_rand["gpu_power"].values - rand_means_P.values
    if np.std(P_dem_rand) > 0:
        slope_rand, _, r_rand, _, _ = stats.linregress(P_dem_rand, T_dem_rand)
        print(f"\n=== NC3: Random group demeaning vs. job demeaning ===")
        print(f"  R2(within-job demeaned):   {h2_results['icc_within_job_residual']['icc']:.3f} ICC")
        print(f"  R2(random group demeaned): {r_rand**2:.3f}  (should be lower than job)")
        results["nc3_r2_job_demeaned"] = float(h2_results["icc_within_job_residual"]["icc"])
        results["nc3_r2_random_group"] = float(r_rand ** 2)
    else:
        results["nc3_r2_job_demeaned"] = None
        results["nc3_r2_random_group"] = None

    return results


# ── 9. Figure generation ────────────────────────────────────────────────────────

def make_figures(df_raw: pd.DataFrame, h1: dict, h2: dict, h3: dict, spatial: dict):
    fig_paths = []

    # Fig 1: Power vs GCD Temperature scatter + regression line
    fig, ax = plt.subplots(figsize=(7, 5))
    df2 = h1["df_B"]
    # Sample 5000 points for readability
    idx = np.random.choice(len(df2), size=min(5000, len(df2)), replace=False)
    ax.scatter(df2["gpu_power"].values[idx], df2["gcd_temp"].values[idx],
               alpha=0.15, s=4, color="steelblue", rasterized=True)
    pw = np.linspace(df2["gpu_power"].min(), df2["gpu_power"].max(), 100)
    ax.plot(pw, h1["intercept_global"] + h1["beta_global_degC_per_W"] * pw,
            "r-", linewidth=2, label=f"OLS: R2={h1['r2_global']:.3f}")
    ax.set_xlabel("GPU Power (W)")
    ax.set_ylabel("GCD Temperature (degC)")
    ax.set_title("Fig 1: Power -> Temperature (global)")
    ax.legend()
    p = FIG_DIR / "fig1_power_vs_temp.png"
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    fig_paths.append(str(p))
    print(f"  Saved {p.name}")

    # Fig 2: Residual distribution (resid_A vs resid_B)
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    resid_A = h1["resid_A"]
    resid_B = h2["df_with_resid"]["resid_B"].dropna().values
    for ax, arr, label, color in [
        (axes[0], resid_A, "resid_A (global)", "steelblue"),
        (axes[1], resid_B, "resid_B (within-job)", "darkorange"),
    ]:
        ax.hist(arr, bins=60, color=color, alpha=0.7, density=True)
        ax.set_xlabel("Residual (degC)")
        ax.set_ylabel("Density")
        ax.set_title(f"Fig 2: {label}\nstd={np.std(arr):.2f}degC  skew={float(stats.skew(arr)):.2f}")
    fig.tight_layout()
    p = FIG_DIR / "fig2_residual_distribution.png"
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    fig_paths.append(str(p))
    print(f"  Saved {p.name}")

    # Fig 3: Fingerprint stability scatter (first-half vs second-half)
    fig, ax = plt.subplots(figsize=(6, 5))
    if h3.get("r_stability") is not None:
        fh = h3["first_half_fingerprints"]
        sh = h3["second_half_fingerprints"]
        common = sorted(set(fh) & set(sh))
        xv = [fh[n] for n in common]
        yv = [sh[n] for n in common]
        ax.scatter(xv, yv, s=30, alpha=0.7, color="steelblue")
        mn, mx = min(xv + yv), max(xv + yv)
        ax.plot([mn, mx], [mn, mx], "k--", linewidth=1, label="y=x")
        ax.set_xlabel("Mean residual — first half (degC)")
        ax.set_ylabel("Mean residual — second half (degC)")
        ax.set_title(f"Fig 3: Fingerprint stability\nr={h3['r_stability']:.3f}  N={len(common)} nodes")
        ax.legend()
    else:
        ax.text(0.5, 0.5, "Insufficient node reuse\nfor stability test",
                ha="center", va="center", transform=ax.transAxes, fontsize=12)
        ax.set_title("Fig 3: Fingerprint stability (insufficient data)")
    p = FIG_DIR / "fig3_fingerprint_stability.png"
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    fig_paths.append(str(p))
    print(f"  Saved {p.name}")

    # Fig 4: Fingerprint distribution (sorted node mean residuals with ±1 SD)
    fig, ax = plt.subplots(figsize=(10, 4))
    nf = h2["node_fingerprints"].sort_values("mean_resid").reset_index(drop=True)
    ax.bar(range(len(nf)), nf["mean_resid"], color="steelblue", alpha=0.7, width=0.8)
    ax.axhline(0, color="k", linewidth=0.8, linestyle="--")
    ax.set_xlabel("Node rank (sorted by mean residual)")
    ax.set_ylabel("Mean thermal residual (degC)")
    ax.set_title(f"Fig 4: Node thermal fingerprints (N={len(nf)} nodes)\nICC={h2['icc_within_job_residual']['icc']:.3f}")
    p = FIG_DIR / "fig4_fingerprint_distribution.png"
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    fig_paths.append(str(p))
    print(f"  Saved {p.name}")

    # Fig 5: Spatial topology (rack × chassis heatmap of mean fingerprint)
    fig, ax = plt.subplots(figsize=(8, 5))
    sp_df = spatial.get("spatial_df", pd.DataFrame())
    if len(sp_df) >= 5 and "rack" in sp_df.columns:
        pivot = sp_df.pivot_table(values="mean_resid", index="chassis", columns="rack", aggfunc="mean")
        im = ax.imshow(pivot.values, aspect="auto", cmap="RdBu_r",
                       vmin=-pivot.abs().max().max(), vmax=pivot.abs().max().max())
        ax.set_xticks(range(len(pivot.columns)))
        ax.set_xticklabels(pivot.columns, fontsize=7, rotation=45)
        ax.set_yticks(range(len(pivot.index)))
        ax.set_yticklabels(pivot.index, fontsize=7)
        ax.set_xlabel("Rack")
        ax.set_ylabel("Chassis")
        ax.set_title("Fig 5: Spatial topology — mean fingerprint (degC)\nRed=hot, Blue=cool")
        plt.colorbar(im, ax=ax, label="Mean residual (degC)")
    else:
        ax.text(0.5, 0.5, "Insufficient spatial data\nfor topology map",
                ha="center", va="center", transform=ax.transAxes, fontsize=12)
        ax.set_title("Fig 5: Spatial topology (insufficient data)")
    p = FIG_DIR / "fig5_spatial_topology.png"
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    fig_paths.append(str(p))
    print(f"  Saved {p.name}")

    # Fig 6: GCD position effects (mean residual per GCD slot)
    fig, ax = plt.subplots(figsize=(7, 4))
    df2_full = h2["df_with_resid"].copy()
    mask = np.isfinite(df2_full["resid_B_valid"])
    df2_full = df2_full[mask]
    node_means = df2_full.groupby("hostname")["resid_B_valid"].transform("mean")
    df2_full["resid_node_dem"] = df2_full["resid_B_valid"] - node_means
    gcd_stats = df2_full.groupby("gcd_id")["resid_node_dem"].agg(["mean", "std", "count"]).reset_index()
    ax.bar(gcd_stats["gcd_id"], gcd_stats["mean"], yerr=gcd_stats["std"] / np.sqrt(gcd_stats["count"]),
           color=["#2166ac" if i < 4 else "#d6604d" for i in range(len(gcd_stats))],
           alpha=0.8, capsize=4)
    ax.axhline(0, color="k", linewidth=0.8, linestyle="--")
    ax.set_xlabel("GCD slot (0-7)")
    ax.set_ylabel("Mean residual — node demeaned (degC)")
    ax.set_title("Fig 6: GCD position effect on thermal residual\n(Blue: GCDs 0-3, Red: GCDs 4-7)")
    ax.set_xticks(range(8))
    p = FIG_DIR / "fig6_gcd_position_effects.png"
    fig.savefig(p, dpi=120, bbox_inches="tight")
    plt.close(fig)
    fig_paths.append(str(p))
    print(f"  Saved {p.name}")

    return fig_paths


# ── 10. Verdict logic ──────────────────────────────────────────────────────────

def compute_verdict(reuse: dict, h1: dict, h2: dict, h3: dict) -> dict:
    """
    GO:         ICC(resid_B) > 0.10 AND r_stability > 0.50 AND reuse_fraction > 0.30
    GO-REFRAME: ICC(resid_B) > 0.05 OR meaningful signal with caveats
    NO-GO:      ICC(resid_B) < 0.05 AND r_stability < 0.20 (or insufficient reuse)
    """
    icc = h2["icc_within_job_residual"]["icc"]
    icc_lo = h2["icc_within_job_ci95"][0]
    r_stab = h3.get("r_stability")
    reuse_frac = reuse["reuse_fraction"]
    n_common = h3.get("n_common_nodes", 0)

    if icc > 0.10 and (r_stab is not None and r_stab > 0.50) and reuse_frac > 0.30:
        verdict = "GO"
        rationale = f"ICC={icc:.3f} > 0.10, stability r={r_stab:.3f} > 0.50, reuse={reuse_frac:.2f} > 0.30"
    elif icc > 0.05 and icc_lo > 0.01:
        verdict = "GO-REFRAME"
        rationale = f"ICC={icc:.3f} > 0.05 (CI_lo={icc_lo:.3f}), but "
        if r_stab is None or n_common < 5:
            rationale += "insufficient node reuse to confirm stability"
        elif r_stab < 0.50:
            rationale += f"stability r={r_stab:.3f} < 0.50 threshold"
        else:
            rationale += "marginal signal warrants more data before full commitment"
    else:
        verdict = "NO-GO"
        rationale = f"ICC={icc:.3f} < 0.05 threshold; fingerprint signal too weak to justify project"

    print(f"\n{'='*60}")
    print(f"VERDICT: {verdict}")
    print(f"Rationale: {rationale}")
    print(f"{'='*60}")

    return {"verdict": verdict, "rationale": rationale, "icc_key": float(icc), "r_stability_key": r_stab}


# ── 11. Main ───────────────────────────────────────────────────────────────────

def main():
    print("Loading job telemetry from 100-job sample...")
    df_raw, ji = load_all_jobs(SAMPLE_BASE)
    print(f"Total observations: {len(df_raw):,}  |  Jobs: {df_raw['job_idx'].nunique()}  |  Nodes: {df_raw['hostname'].nunique()}")

    # Node reuse
    print("\n=== Node Reuse ===")
    reuse = quantify_node_reuse(df_raw, ji)
    for k, v in reuse.items():
        if k != "multi_job_node_examples":
            print(f"  {k}: {v}")
    print(f"  Top nodes by job count: {reuse['multi_job_node_examples']}")

    # H1
    h1 = test_h1_power(df_raw)

    # H2
    h2 = test_h2_node_identity(h1)

    # H3
    h3 = test_h3_stability(h2, ji)

    # GCD-level
    print("\n=== GCD-Level ICC ===")
    gcd_analysis = analyze_gcd_level(h2)

    # Spatial
    spatial = analyze_spatial(h2, ji)

    # Negative controls
    nc = negative_controls(h2)

    # Verdict
    verdict = compute_verdict(reuse, h1, h2, h3)

    # Selected jobs CSV
    job_summary = df_raw.groupby("job_idx").agg(
        n_nodes=("hostname", "nunique"),
        n_obs=("gcd_temp", "count"),
        mean_temp=("gcd_temp", "mean"),
        mean_power=("gpu_power", "mean"),
    ).reset_index()
    job_summary.to_csv(OUT_DIR / "selected_jobs.csv", index=False)
    print(f"\nSaved selected_jobs.csv ({len(job_summary)} jobs)")

    # Results JSON
    def safe(x):
        if isinstance(x, (np.integer,)): return int(x)
        if isinstance(x, (np.floating,)): return float(x) if np.isfinite(x) else None
        if isinstance(x, dict): return {str(k): safe(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)): return [safe(i) for i in x]
        return x

    results = {
        "sample_stats": {
            "n_jobs": int(df_raw["job_idx"].nunique()),
            "n_nodes": int(df_raw["hostname"].nunique()),
            "n_obs": int(len(df_raw)),
            "gcd_temp_mean": float(df_raw["gcd_temp"].mean()),
            "gcd_temp_std": float(df_raw["gcd_temp"].std()),
            "gcd_temp_min": float(df_raw["gcd_temp"].min()),
            "gcd_temp_max": float(df_raw["gcd_temp"].max()),
        },
        "node_reuse": {k: safe(v) for k, v in reuse.items() if k != "multi_job_node_examples"},
        "h1_power": {
            "r2_global": h1["r2_global"],
            "r2_within_job": h1["r2_within_job"],
            "beta_global": h1["beta_global_degC_per_W"],
            "beta_within_job": h1["beta_within_job_degC_per_W"],
            "n_obs": h1["n_obs"],
        },
        "h2_node_icc": {
            "icc_global_residual": safe(h2["icc_global_residual"]),
            "icc_within_job_residual": safe(h2["icc_within_job_residual"]),
            "icc_ci95": h2["icc_within_job_ci95"],
            "n_fingerprinted_nodes": len(h2["node_fingerprints"]),
            "fingerprint_range_degC": [
                float(h2["node_fingerprints"]["mean_resid"].min()),
                float(h2["node_fingerprints"]["mean_resid"].max()),
            ],
        },
        "h3_stability": {k: safe(v) for k, v in h3.items() if k not in ("first_half_fingerprints", "second_half_fingerprints")},
        "gcd_analysis": safe(gcd_analysis),
        "spatial": {k: safe(v) for k, v in spatial.items() if k != "spatial_df"},
        "negative_controls": safe(nc),
        "verdict": verdict,
    }

    with open(OUT_DIR / "results.json", "w") as f:
        json.dump(results, f, indent=2)
    print(f"Saved results.json")

    # Figures
    print("\nGenerating figures...")
    fig_paths = make_figures(df_raw, h1, h2, h3, spatial)

    print(f"\nAll done. Figures: {len(fig_paths)}")
    return results


if __name__ == "__main__":
    results = main()
