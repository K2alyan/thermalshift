# NOTE: This is a legacy exploratory script from the ThermalShift research process.
# It contains hardcoded local paths that were valid on the original development machine.
# It is included for provenance and reproducibility of intermediate findings,
# but is not required to reproduce the final results (see phase3b_mc.py onwards).
# Set THERMALSHIFT_DATA_DIR and update ANALYSIS_DIR before running.

#!/usr/bin/env python3
"""
Phase 3B.2-E: Residual-fingerprint sensitivity analysis.

Question: are within-job residuals correlated with within-job fingerprint rank?
If E[e_ij | F_i] != 0 within jobs, then random residual permutation gives
thermal policies a free temperature benefit they wouldn't have in reality.

Protocol:
  Step 1 -- Measure: compute residual mean / median by within-job fingerprint decile.
            If gradient < ~0.1 degC across deciles, permutation scheme is fine.
            If gradient is larger, proceed to conditioned permutation.

  Step 2 -- Conditioned permutation: permute residuals only within fingerprint-rank
            bins within each job (default: 5 bins of equal width in F rank).
            Re-run historical-assignment identity check with conditioned permutation.
            Target: E[B_ratio]~1, E[S_ratio]~1 (should be tighter than random perm).

  Step 3 -- Compare capacity crossings: run a single-scenario lambda sweep under
            conditioned permutation for Random-feasible and the two primary deployable
            policies (FP-cap-10, Tier-cap-20). Report shift in crossing point vs
            unconditional permutation result.

If primary policy crossing shifts by <3 pp, declare permutation scheme robust.
If shift >= 3 pp, switch to conditioned permutation for the final Monte Carlo.
"""

import os
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import time, re
from pathlib import Path

ANALYSIS_DIR    = Path(__file__).parent
DATA_DIR        = Path(os.environ.get("THERMALSHIFT_DATA_DIR", ""))

BETA_F          = 0.9569
T_P95_THRESHOLD = 60.602770562770566
N_IDENT         = 20
IDENT_SEED_BASE = 33331
N_BINS          = 5    # fingerprint-rank bins for conditioned permutation

print("=== Phase 3B.2-E: Residual-fingerprint sensitivity ===\n")

# ============================================================
# Load
# ============================================================
fp_df      = pd.read_parquet(ANALYSIS_DIR / "phase3a_fingerprint_2024.parquet")
cohort_set = set(fp_df.index)
F_dict     = fp_df["FA_2024"].to_dict()
print(f"  Cohort: {len(cohort_set):,} nodes")

test_df = pd.read_parquet(ANALYSIS_DIR / "phase3a_test_set.parquet")
print(f"  Test set: {len(test_df):,} node-job pairs, {test_df['job_idx'].nunique()} jobs")

print("  Loading run_time...")
t0 = time.time()
sched = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet",
                        columns=["job_idx", "run_time"])
sched["job_idx_int"] = sched["job_idx"].astype(int)
rt_from_jobs = dict(zip(sched["job_idx_int"], sched["run_time"]))
print(f"  Done ({time.time()-t0:.1f}s)")

# ============================================================
# Compute residuals and within-job F deviation
# ============================================================
job_agg = (
    test_df.groupby("job_idx")
    .agg(
        F_hist_mean = ("F_2024", "mean"),
        T_p95_hist  = ("T_p95",  "mean"),
        hist_nodes  = ("node",   list),
        n_cohort    = ("node",   "count"),
    )
    .reset_index()
)
job_agg["run_time"] = job_agg["job_idx"].astype(int).map(rt_from_jobs)
job_agg["alpha_j"]  = job_agg["T_p95_hist"] - BETA_F * job_agg["F_hist_mean"]

alpha_map    = job_agg.set_index("job_idx")["alpha_j"].to_dict()
F_mean_map   = job_agg.set_index("job_idx")["F_hist_mean"].to_dict()

test_res            = test_df.copy()
test_res["alpha_j"] = test_res["job_idx"].map(lambda j: alpha_map.get(int(j), np.nan))
test_res["F_i"]     = test_res["node"].map(F_dict)
test_res["F_mean_j"] = test_res["job_idx"].map(lambda j: F_mean_map.get(int(j), np.nan))
test_res["dF_ij"]   = test_res["F_i"] - test_res["F_mean_j"]   # within-job F deviation
test_res["residual"] = (test_res["T_p95"]
                        - test_res["alpha_j"]
                        - BETA_F * test_res["F_i"])

# Drop rows where F_i is not in cohort (should not happen but be safe)
test_res = test_res.dropna(subset=["F_i", "residual", "dF_ij"])

# ============================================================
# Step 1: Residual vs within-job F rank gradient
# ============================================================
print("\n" + "="*60)
print("STEP 1: Residual vs within-job fingerprint rank")
print("="*60)

# Global correlation
corr_spearman = test_res[["dF_ij", "residual"]].corr(method="spearman").iloc[0, 1]
corr_pearson  = test_res[["dF_ij", "residual"]].corr(method="pearson").iloc[0, 1]
print(f"\n  Global: Pearson r(dF, e) = {corr_pearson:.4f}")
print(f"          Spearman r(dF, e) = {corr_spearman:.4f}")

# Within-job: for each job, compute Pearson r(dF, e)
within_corrs = []
for jid, grp in test_res.groupby("job_idx"):
    if len(grp) > 1:
        r = grp[["dF_ij", "residual"]].corr().iloc[0, 1]
        if np.isfinite(r):
            within_corrs.append(r)
within_corrs = np.array(within_corrs)
print(f"\n  Within-job r(dF, e): mean={within_corrs.mean():.4f}"
      f"  median={np.median(within_corrs):.4f}"
      f"  SD={within_corrs.std():.4f}")

# By within-job F decile
test_res["dF_decile"] = pd.qcut(test_res["dF_ij"], q=10,
                                 labels=[f"D{i+1}" for i in range(10)],
                                 duplicates="drop")
decile_stats = (test_res.groupby("dF_decile", observed=True)["residual"]
                .agg(["mean", "median", "std", "count"]))
print(f"\n  Residual by within-job F decile:")
print(f"  {'Decile':<8} | {'mean e':>8} | {'median e':>8} | {'SD e':>6} | n")
print("  " + "-"*48)
for dec, row in decile_stats.iterrows():
    print(f"  {str(dec):<8} | {row['mean']:>8.4f} | {row['median']:>8.4f}"
          f" | {row['std']:>6.3f} | {int(row['count'])}")

decile_means = decile_stats["mean"].values
gradient = decile_means[-1] - decile_means[0]  # D10 - D1
print(f"\n  Gradient (D10 - D1): {gradient:+.4f} degC")
print(f"  Range across deciles: [{decile_means.min():.4f}, {decile_means.max():.4f}] degC")

if abs(gradient) < 0.10:
    gradient_verdict = "SMALL (<0.10 degC) -- unconditional permutation likely adequate"
elif abs(gradient) < 0.25:
    gradient_verdict = "MODERATE (0.10-0.25 degC) -- conditioned permutation recommended"
else:
    gradient_verdict = "LARGE (>0.25 degC) -- conditioned permutation required"
print(f"  Verdict: {gradient_verdict}")

# ============================================================
# Figure: residual mean by within-job F decile
# ============================================================
fig, axes = plt.subplots(1, 2, figsize=(12, 4))

ax = axes[0]
dec_labels = decile_stats.index.astype(str)
ax.bar(range(len(dec_labels)), decile_stats["mean"], color="#4488cc", alpha=0.8)
ax.axhline(0, color="black", lw=1)
ax.set_xticks(range(len(dec_labels)))
ax.set_xticklabels(dec_labels, fontsize=9)
ax.set_xlabel("Within-job F rank decile (D1=coolest, D10=hottest)")
ax.set_ylabel("Mean residual e_ij (degC)")
ax.set_title(f"Residual vs within-job F rank  (gradient={gradient:+.3f} degC D1-D10)")
ax.grid(True, alpha=0.3, axis="y")

ax = axes[1]
ax.hist(within_corrs, bins=40, color="#cc4444", alpha=0.8, edgecolor="white", lw=0.5)
ax.axvline(within_corrs.mean(), color="black", lw=2, ls="--",
           label=f"mean={within_corrs.mean():.3f}")
ax.set_xlabel("Within-job Pearson r(dF_ij, e_ij)")
ax.set_ylabel("Number of jobs")
ax.set_title("Distribution of within-job residual-F correlations")
ax.legend()
ax.grid(True, alpha=0.3)

plt.tight_layout()
outfig = ANALYSIS_DIR / "phase3b2e_residual_gradient.png"
fig.savefig(outfig, dpi=150)
plt.close()
print(f"\n  Saved {outfig}")

# ============================================================
# Build job_residuals and per-job F-rank bins for conditioned permutation
# ============================================================
# For each job: sort nodes by F_i, assign to N_BINS equal-count bins, permute within bins
job_residuals_uncond: dict[int, np.ndarray] = {}   # unconditional (random order as stored)
job_residuals_cond:   dict[int, tuple]      = {}   # conditioned: (residuals, bin_labels)

for jid, grp in test_res.groupby("job_idx"):
    jid = int(jid)
    grp_sorted = grp.sort_values("F_i")              # sort by F ascending
    res_arr    = grp_sorted["residual"].values.copy()
    job_residuals_uncond[jid] = res_arr

    # Assign bin labels (equal-count bins within this job)
    k = len(grp_sorted)
    if k >= N_BINS:
        try:
            bin_labels = pd.qcut(grp_sorted["F_i"], q=N_BINS,
                                 labels=False, duplicates="drop").values
        except Exception:
            bin_labels = np.zeros(k, dtype=int)
    else:
        bin_labels = np.zeros(k, dtype=int)  # single bin if too few nodes
    job_residuals_cond[jid] = (res_arr, bin_labels)

rt_h_map = {int(j): float(rt) / 3600.0 for j, rt in zip(job_agg["job_idx"], job_agg["run_time"])}

# ============================================================
# Historical B and S
# ============================================================
test_res_rth  = test_res["job_idx"].map(lambda j: rt_h_map.get(int(j), 0.0))
node_excess   = test_res["T_p95"] - T_P95_THRESHOLD
B_hist_node   = float((test_res_rth * (node_excess > 0)).sum())
S_hist_node   = float((test_res_rth * node_excess.clip(lower=0)).sum())
print(f"\n  B_hist_node = {B_hist_node:.1f} h    S_hist_node = {S_hist_node:.1f} degC-h")

# ============================================================
# Step 2: Identity check with conditioned permutation
# ============================================================
print("\n" + "="*60)
print("STEP 2: Identity check -- conditioned vs unconditional permutation")
print("="*60)

def identity_replay_conditioned(seed: int) -> tuple[float, float]:
    """Historical nodes, conditioned residual permutation (within F-rank bins)."""
    rng   = np.random.default_rng(seed)
    B_tot = 0.0
    S_tot = 0.0
    for _, jrow in job_agg.iterrows():
        jid        = int(jrow["job_idx"])
        rt_h       = float(jrow["run_time"]) / 3600.0
        alpha      = float(jrow["alpha_j"])
        hist_nodes = jrow["hist_nodes"]
        k          = len(hist_nodes)
        if k == 0 or not np.isfinite(rt_h):
            continue
        res_sorted, bin_labels = job_residuals_cond[jid]
        # Permute within each bin
        perm = np.arange(k)
        for b in np.unique(bin_labels):
            idx_b = np.where(bin_labels == b)[0]
            perm[idx_b] = rng.permutation(idx_b)
        # Apply permuted residuals (res_sorted is ordered by F ascending,
        # hist_nodes are in arbitrary order -- map by F rank)
        F_sel = np.array([F_dict.get(n, 0.0) for n in hist_nodes])
        rank  = np.argsort(np.argsort(F_sel))    # rank of each selected node by F
        T_hats = alpha + BETA_F * F_sel + res_sorted[perm[rank]]
        excesses = T_hats - T_P95_THRESHOLD
        B_tot   += rt_h * float((excesses > 0).sum())
        S_tot   += rt_h * float(excesses.clip(min=0).sum())
    return B_tot / B_hist_node, S_tot / S_hist_node

print(f"\nRunning {N_IDENT} conditioned identity scenarios...")
Bc_ratios = []
Sc_ratios = []
for scen in range(N_IDENT):
    Br, Sr = identity_replay_conditioned(IDENT_SEED_BASE + scen)
    Bc_ratios.append(Br)
    Sc_ratios.append(Sr)
    print(f"  Scen {scen+1:2d}/{N_IDENT}: B/Bh={Br:.4f}  S/Sh={Sr:.4f}")

Bc_mean = float(np.mean(Bc_ratios))
Bc_se   = float(np.std(Bc_ratios) / np.sqrt(N_IDENT))
Sc_mean = float(np.mean(Sc_ratios))
Sc_se   = float(np.std(Sc_ratios) / np.sqrt(N_IDENT))

print(f"\n  Conditioned identity:")
print(f"    E[B_ratio] = {Bc_mean:.4f} +/- {Bc_se:.4f}")
print(f"    E[S_ratio] = {Sc_mean:.4f} +/- {Sc_se:.4f}")
print(f"\n  Unconditional identity (prior run):")
print(f"    E[B_ratio] = 0.9805  E[S_ratio] = 0.9723")

# ============================================================
# Step 3: Sensitivity in capacity crossings
# Reuse the full capacity sweep infrastructure
# ============================================================
print("\n" + "="*60)
print("STEP 3: Capacity crossing sensitivity -- load sweep infrastructure")
print("="*60)
print("  (Loading full sweep data for conditioned-permutation replay)")

# Import what we need from the sweep script
# Rather than re-importing, rebuild here (same data already loaded above)

print("  Loading full job schedule for stateful replay...")
t0 = time.time()
all_jobs = pd.read_parquet(DATA_DIR / "frontier-completed-job-info.parquet")
all_jobs["job_idx_int"] = all_jobs["job_idx"].astype(int)

# Topology
_xe2_re = re.compile(r"x(\d+)c")
node_to_cabinet: dict[str, int] = {}
for hl, nl in zip(all_jobs["host_list"].values, all_jobs["node_list"].values):
    for hn, xn in zip(hl, nl):
        if hn in cohort_set and hn not in node_to_cabinet:
            m = _xe2_re.match(xn)
            if m:
                node_to_cabinet[hn] = int(m.group(1))
    if len(node_to_cabinet) >= len(cohort_set):
        break

# Schedule arrays
cohort_per_job: dict[int, frozenset] = {}
for jid, hl in zip(all_jobs["job_idx_int"].values, all_jobs["host_list"].values):
    cn = frozenset(n for n in hl if n in cohort_set)
    if cn:
        cohort_per_job[jid] = cn
has_cohort = np.array([jid in cohort_per_job for jid in all_jobs["job_idx_int"].values])
sched_jids = all_jobs["job_idx_int"].values[has_cohort]
sched_st   = all_jobs["start_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_et   = all_jobs["end_time"].dt.tz_convert("UTC").dt.tz_localize(None).values[has_cohort]
sched_cn   = np.array([cohort_per_job[jid] for jid in sched_jids], dtype=object)

# Job-level test summary
meta = (all_jobs[["job_idx_int", "node_count", "start_time", "end_time", "mean_power", "run_time"]]
        .rename(columns={"job_idx_int": "job_idx"}))
jobs_sorted = job_agg.drop(columns=["run_time"], errors="ignore").merge(meta, on="job_idx", how="left")
jobs_sorted["power_per_node"] = jobs_sorted["mean_power"] / jobs_sorted["node_count"].clip(lower=1)
test_id_set = set(jobs_sorted["job_idx"].astype(int))
jobs_sorted = jobs_sorted.sort_values("start_time").reset_index(drop=True)
n_base = len(jobs_sorted)

# Historical node-hours
cohort_list    = sorted(cohort_set)
F_cohort_arr   = np.array([F_dict[n] for n in cohort_list])
F_cohort_sidx  = np.argsort(F_cohort_arr)
hist_node_hours = {n: 0.0 for n in cohort_list}
for _, jrow in jobs_sorted.iterrows():
    rth = float(jrow["run_time"]) / 3600.0
    for n in jrow["hist_nodes"]:
        if n in hist_node_hours:
            hist_node_hours[n] += rth
hist_util_arr  = np.array([hist_node_hours[n] for n in cohort_list])
hist_total_nh  = float(hist_util_arr.sum())
hist_fleet_avg = hist_total_nh / len(cohort_list)

# Background busy
is_test = np.array([jid in test_id_set for jid in sched_jids])
bg_st = sched_st[~is_test];  bg_et = sched_et[~is_test];  bg_cn = sched_cn[~is_test]

def _to_dt64(ts):
    return np.datetime64(pd.Timestamp(ts).tz_convert("UTC").tz_localize(None), "ms")

bg_busy_per_job: dict[int, frozenset] = {}
for _, jrow in jobs_sorted.iterrows():
    jid = int(jrow["job_idx"])
    t_j = _to_dt64(jrow["start_time"])
    mask = (bg_st <= t_j) & (bg_et > t_j)
    bg_busy_per_job[jid] = frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

# Look-ahead arrays
hist_st64  = np.array([_to_dt64(r["start_time"]) for _, r in jobs_sorted.iterrows()])
hist_et64  = np.array([_to_dt64(r["end_time"])   for _, r in jobs_sorted.iterrows()])
hist_k_arr = jobs_sorted["n_cohort"].values.astype(int)
hist_j_arr = jobs_sorted["job_idx"].values.astype(int)

print(f"  Done ({time.time()-t0:.1f}s)  {n_base} base jobs  {hist_total_nh:.0f} node-h")

# alpha_j
jobs_sorted["alpha_j"] = jobs_sorted["T_p95_hist"] - BETA_F * jobs_sorted["F_hist_mean"]
alpha_map2 = jobs_sorted.set_index("job_idx")["alpha_j"].to_dict()

P50_PWR = 896.4571428571429
P80_PWR = 1496.4923809523812
P95_PWR = 1955.5884126984126

def bg_at(t):
    mask = (bg_st <= t) & (bg_et > t)
    return frozenset().union(*bg_cn[mask]) if mask.any() else frozenset()

def gini(arr):
    a = np.abs(np.sort(arr));  n = len(a)
    if n == 0 or a.sum() == 0: return 0.0
    idx = np.arange(1, n+1)
    return float((2*(idx*a).sum()/(n*a.sum())) - (n+1)/n)

def look_ahead_safe(snodes, ts, es, cfb):
    mask = (hist_st64 > ts) & (hist_st64 < es)
    if not mask.any(): return True
    sn = frozenset(snodes)
    for i in np.where(mask)[0]:
        th = hist_st64[i]; kh = int(hist_k_arr[i]); jh = int(hist_j_arr[i])
        bgth = bg_busy_per_job[jh]
        cfth = frozenset(n for n, te in cfb.items() if te > th)
        blk  = bgth | cfth | sn
        # Use <= th to include co-start base jobs (same timestamp, processed before i).
        # Exclude i itself -- it is the target being protected, not a consumer.
        fb_mask = (hist_st64 > ts) & (hist_st64 <= th) & (hist_et64 > th)
        fb_mask = fb_mask.copy(); fb_mask[i] = False
        fbk = min(int(hist_k_arr[fb_mask].sum()), max(0, len(cohort_set)-len(blk)))
        if len(cohort_set) - len(blk) - fbk < kh:
            return False
    return True

def tier_sel(avail, k, pj, rng_l):
    na = len(avail); ck = min(k, na)
    aF = np.array([F_dict[n] for n in avail]); ord_ = np.argsort(aF)
    if np.isnan(pj) or pj < P50_PWR:
        return [avail[i] for i in rng_l.choice(na, ck, replace=False)]
    elif pj < P80_PWR:
        pe = max(ck, int(na*0.75)); pick = rng_l.choice(pe, ck, replace=False)
        return [avail[ord_[i]] for i in pick]
    else:
        return [avail[ord_[i]] for i in range(ck)]

def sample_pool(n_extra, seed):
    rng_s = np.random.default_rng(seed)
    months = jobs_sorted["start_time"].dt.month.values
    hours  = jobs_sorted["start_time"].dt.hour.values
    sk_map = {}
    for i, sk in enumerate(zip(months.tolist(), hours.tolist())):
        sk_map.setdefault(sk, []).append(i)
    ukeys = sorted(sk_map.keys())
    cnts  = np.array([len(sk_map[s]) for s in ukeys])
    probs = cnts / cnts.sum()
    nper  = np.round(probs * n_extra).astype(int)
    diff  = n_extra - nper.sum()
    if diff > 0: nper[np.argsort(-probs)[:diff]] += 1
    elif diff < 0: nper[np.argsort(nper)[:(-diff)]] -= 1
    chunks = []
    for sk, ns in zip(ukeys, nper):
        if ns <= 0: continue
        idxs = rng_s.choice(sk_map[sk], size=int(ns), replace=True)
        chunks.append(jobs_sorted.iloc[idxs])
    if not chunks:
        return pd.DataFrame(columns=list(jobs_sorted.columns))
    syn = pd.concat(chunks, ignore_index=True)
    jit = rng_s.uniform(-1800, 1800, size=len(syn))
    syn["start_time"]     = syn["start_time"] + pd.to_timedelta(jit, unit="s")
    syn["end_time"]       = syn["start_time"] + pd.to_timedelta(syn["run_time"].values, unit="s")
    syn["is_synthetic"]   = True
    syn["parent_job_idx"] = syn["job_idx"].values.copy()
    syn["job_idx"]        = -(np.arange(len(syn), dtype=np.int64) + 1)
    syn["alpha_j"]        = syn["parent_job_idx"].map(alpha_map2)
    syn = syn.sample(frac=1, random_state=int(rng_s.integers(0, 2**31))).reset_index(drop=True)
    return syn

def gen_cond_perms(syn_pool, scen_rng):
    """Generate fingerprint-conditioned permutations for all jobs."""
    perms = {}
    for jid in jobs_sorted["job_idx"].astype(int):
        res_s, bins = job_residuals_cond[jid]
        k = len(res_s)
        perm = np.arange(k)
        for b in np.unique(bins):
            idx_b = np.where(bins == b)[0]
            perm[idx_b] = scen_rng.permutation(idx_b)
        perms[jid] = perm
    for sjid, pjid in zip(syn_pool["job_idx"].astype(int),
                           syn_pool["parent_job_idx"].astype(int)):
        res_s, bins = job_residuals_cond[pjid]
        k = len(res_s)
        perm = np.arange(k)
        for b in np.unique(bins):
            idx_b = np.where(bins == b)[0]
            perm[idx_b] = scen_rng.permutation(idx_b)
        perms[sjid] = perm
    return perms

def replay_cond(syn_sub, policy, delta_cap, lam, pseed, job_perms_cond):
    cap = (1 + delta_cap) * lam * hist_fleet_avg
    n_syn = len(syn_sub)
    if n_syn > 0:
        bc = jobs_sorted.copy()
        bc["is_synthetic"] = False; bc["parent_job_idx"] = bc["job_idx"].values.copy()
        comb = pd.concat([bc, syn_sub], ignore_index=True)
    else:
        comb = jobs_sorted.copy()
        comb["is_synthetic"] = False; comb["parent_job_idx"] = comb["job_idx"].values.copy()
    comb = comb.sort_values("start_time").reset_index(drop=True)

    cfb  = {}; util = {n: 0.0 for n in cohort_set}
    _rng = np.random.default_rng(pseed)

    B = 0.0; S = 0.0; syn_nh = 0.0; n_adm = 0
    n_base_unsrv = 0

    for _, row in comb.iterrows():
        is_syn = bool(row["is_synthetic"])
        tj = _to_dt64(row["start_time"]); te = _to_dt64(row["end_time"])
        rth = float(row["run_time"]) / 3600.0; k = int(row["n_cohort"])
        jid = int(row["job_idx"])
        ppn = row.get("power_per_node", np.nan)
        pj  = float(ppn) if not pd.isnull(ppn) else np.nan
        try: pjid = int(row["parent_job_idx"])
        except: pjid = jid

        bgb = bg_at(tj) if is_syn else bg_busy_per_job.get(pjid, frozenset())
        cfn = frozenset(n for n, te2 in cfb.items() if te2 > tj)

        avcap = [n for n in cohort_set if n not in bgb and n not in cfn and util[n] < cap]
        if is_syn:
            if len(avcap) < k:
                avunc = [n for n in cohort_set if n not in bgb and n not in cfn]
                continue   # drop synthetic job (physical or cap)
            av = avcap
        else:
            av = avcap if len(avcap) >= k else [n for n in cohort_set if n not in bgb and n not in cfn]

        na = len(av)
        if na == 0: sel = []
        elif policy == "fp":
            aF = np.array([F_dict[n] for n in av]); ord_ = np.argsort(aF)
            sel = [av[i] for i in ord_[:min(k, na)]]
        elif policy in ("tier20", "tiernc"):
            sel = tier_sel(av, k, pj, _rng)
        else:
            sel = [av[i] for i in _rng.choice(na, min(k, na), replace=False)]

        if is_syn and sel:
            if not look_ahead_safe(sel, tj, te, cfb):
                continue

        if not is_syn and len(sel) < k:
            n_base_unsrv += 1
            raise AssertionError(
                f"Base-job invariant violated: job {int(row['job_idx'])} "
                f"needed {k} nodes, got {len(sel)}"
            )

        for n in sel: cfb[n] = te; util[n] += rth

        if sel:
            FA = np.array([F_dict[n] for n in sel])
            alpha = float(row["alpha_j"])
            res_s, bins = job_residuals_cond[pjid]
            perm = job_perms_cond[jid]
            # For conditioned assignment: map each selected node to its F rank position
            rank = np.argsort(np.argsort(FA))   # rank in [0, k-1] by ascending F
            T_hats = alpha + BETA_F * FA + res_s[perm[rank]]
            exc = T_hats - T_P95_THRESHOLD
            B += rth * float((exc > 0).sum())
            S += rth * float(exc.clip(min=0).sum())
            if is_syn:
                n_adm += 1; syn_nh += len(sel) * rth

    util_v = np.array([util[n] for n in cohort_list])
    return {
        "B_node_ratio"       : B / B_hist_node,
        "S_node_ratio"       : S / S_hist_node,
        "capacity_unlock_pct": syn_nh / hist_total_nh * 100.0,
        "gini"               : gini(util_v),
        "n_base_unserved"    : n_base_unsrv,
    }

# Lambda sweep (sparse -- same as 3B.2d)
LAMBDA_SWEEP  = [1.00, 1.05, 1.10, 1.15, 1.20, 1.25, 1.30, 1.40, 1.50, 1.65, 1.80]
LAMBDA_MAX    = max(LAMBDA_SWEEP)
SCENARIO_SEED = 42
WORKLOAD_SEED = 77777

# Policies: only the ones that matter for this comparison
COMP_POLICIES = [
    ("random", 1e6,  "Random-feasible"),
    ("fp",     0.10, "FP-cap-10"),
    ("tier20", 0.20, "Tier-cap-20"),
]

print("\nGenerating workload pool...")
n_extra_max = int(np.ceil((LAMBDA_MAX - 1.0) * n_base))
syn_pool = sample_pool(n_extra_max, WORKLOAD_SEED)
print(f"  {len(syn_pool)} synthetic jobs")

print("Generating conditioned permutations (CRN)...")
scen_rng = np.random.default_rng(SCENARIO_SEED)
job_perms_cond = gen_cond_perms(syn_pool, scen_rng)
print(f"  {len(job_perms_cond)} permutations")

cond_results: dict[str, list[dict]] = {pk: [] for pk, _, _ in COMP_POLICIES}

for lam in LAMBDA_SWEEP:
    n_syn     = int(round((lam-1.0)*n_base))
    syn_sub   = syn_pool.iloc[:n_syn].copy() if n_syn > 0 else pd.DataFrame(
        columns=syn_pool.columns if len(syn_pool)>0 else jobs_sorted.columns)
    added_pct = (lam-1.0)*100.0
    print(f"\n  lam={lam:.2f} (+{added_pct:.0f}%) N_syn={n_syn}")
    for pk, dc, label in COMP_POLICIES:
        t0 = time.time()
        r  = replay_cond(syn_sub, pk, dc, lam,
                         pseed=SCENARIO_SEED + abs(hash(pk))%1000,
                         job_perms_cond=job_perms_cond)
        cond_results[pk].append({**r, "lambda_val": lam})
        q = "!" if r["n_base_unserved"] > 0 else " "
        print(f"    {label:<20}: NH%={r['capacity_unlock_pct']:>5.1f}"
              f"  B/Bh={r['B_node_ratio']:.4f}  S/Sh={r['S_node_ratio']:.4f}"
              f"  Gini={r['gini']:.3f} {q} ({time.time()-t0:.0f}s)")

# Crossing analysis
def find_cross(rows, key, tgt=1.0):
    xs = [r["capacity_unlock_pct"] for r in rows]
    ys = [r[key] for r in rows]
    for i in range(len(ys)-1):
        if ys[i] <= tgt <= ys[i+1]:
            frac = (tgt-ys[i])/max(ys[i+1]-ys[i],1e-12)
            return float(xs[i]+frac*(xs[i+1]-xs[i]))
        if i==0 and ys[i]>=tgt: return 0.0
    return None

print("\n" + "="*60)
print("CROSSING COMPARISON: conditioned vs unconditional permutation")
print("="*60)

# Load prior unconditional results
prior_path = ANALYSIS_DIR / "phase3b2d_results.json"
prior = None
if prior_path.exists():
    with open(prior_path) as f:
        prior = json.load(f)

print(f"\n  {'Policy':<22} | C_B cond | C_B uncond | shift")
print("  " + "-"*55)
for pk, dc, label in COMP_POLICIES:
    c_B_cond = find_cross(cond_results[pk], "B_node_ratio")
    if prior:
        rows_u   = prior["policy_results"].get(pk, [])
        c_B_u    = find_cross(rows_u, "B_node_ratio") if rows_u else None
    else:
        c_B_u = None
    cond_s = f"{c_B_cond:.1f}%" if c_B_cond is not None else ">80%"
    unc_s  = f"{c_B_u:.1f}%"    if c_B_u    is not None else ">80% / n/a"
    if c_B_cond is not None and c_B_u is not None:
        shift = c_B_cond - c_B_u
        shift_s = f"{shift:+.1f} pp"
    else:
        shift_s = "N/A"
    print(f"  {label:<22} | {cond_s:>8} | {unc_s:>10} | {shift_s}")

# Save
results = {
    "gradient_D10_minus_D1" : float(gradient),
    "gradient_verdict"      : gradient_verdict,
    "within_job_corr_mean"  : float(within_corrs.mean()),
    "within_job_corr_median": float(np.median(within_corrs)),
    "decile_means"          : decile_means.tolist(),
    "identity_cond_B_mean"  : Bc_mean,
    "identity_cond_B_se"    : Bc_se,
    "identity_cond_S_mean"  : Sc_mean,
    "identity_cond_S_se"    : Sc_se,
    "cond_crossings"        : {
        pk: {
            "C_B": find_cross(cond_results[pk], "B_node_ratio"),
            "C_S": find_cross(cond_results[pk], "S_node_ratio"),
        }
        for pk, _, _ in COMP_POLICIES
    },
    "cond_results"          : cond_results,
}
outpath = ANALYSIS_DIR / "phase3b2e_results.json"
with open(outpath, "w") as f:
    json.dump(results, f, indent=2, default=str)
print(f"\n  Saved {outpath}")
print("\n=== Done ===")
