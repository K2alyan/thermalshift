"""
Phase 3B flagship figures.

Outputs (written to artifacts/phase1/figures/):
  fig_mc_paired.png        -- paired Random vs FP capacity across 30 scenarios
  fig_mc_dc_dist.png       -- distribution of paired dC with bootstrap CI
  fig_mc_constraints.png   -- binding constraint breakdown
"""

import json
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path

# ---- paths ----
ANALYSIS_DIR = Path(__file__).parent
FIGURES_DIR  = Path(__file__).parent.parent / "figures"
FIGURES_DIR.mkdir(exist_ok=True)

CKPT     = ANALYSIS_DIR / "phase3b_mc_checkpoint.json"
VALIDATE = ANALYSIS_DIR / "phase3b_mc_validate.py"   # numbers already computed; re-derive here

# ---- frozen numbers (from phase3b_mc_validate.py) ----
BOOT_CI_LO   = 11.52
BOOT_CI_HI   = 21.93
BOOT_SEED    = 42
N_BOOT       = 20_000

# ---- style ----
COLOR_FP    = "#E87722"   # warm orange
COLOR_RND   = "#2E86AB"   # steel blue
COLOR_CENSORED_ARROW = "#D45000"
ALPHA_LINE  = 0.25
ALPHA_SHADE = 0.18
FONTSIZE_TITLE = 11
FONTSIZE_AXIS  = 9
FONTSIZE_ANNOT = 8

plt.rcParams.update({
    "font.family":   "sans-serif",
    "font.size":     FONTSIZE_AXIS,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "figure.dpi":        150,
})

# -----------------------------------------------------------------------
# Load data
# -----------------------------------------------------------------------
with open(CKPT) as f:
    ckpt = json.load(f)

scenarios, fp_vals, rnd_vals, dc_vals, bind_constraints = [], [], [], [], []
censored_s = None

for rec in ckpt:
    s     = rec["scenario"]
    fp_cf = rec.get("fp",     {}).get("C_feasible")
    rnd_cf = rec.get("random",{}).get("C_feasible")
    # binding constraint for FP
    bind = None
    if fp_cf is not None:
        fp_data = rec.get("fp", {})
        b = fp_data.get("C_B_th")
        s_ = fp_data.get("C_S_th")
        c = fp_data.get("C_cab_full")
        # binding = whichever constraint crossed first (lowest C_feasible value).
        # Only include constraints that actually crossed (not None).
        candidates = []
        if b  is not None: candidates.append(("B_thermal", b))
        if s_ is not None: candidates.append(("S_thermal", s_))
        if c  is not None: candidates.append(("cab_power",  c))
        bind = min(candidates, key=lambda x: x[1])[0] if candidates else "B_thermal"

    if fp_cf is None:
        censored_s = s
        # compute last definitely-safe FP load as the lower bound for display
        fp_rows = rec.get("fp", {}).get("rows", [])
        lb = 0.0
        for r in fp_rows:
            bv = r.get("B_node_ratio")
            sv = r.get("S_node_ratio")
            cv = r.get("B_cab_ratio_full")
            if None not in (bv, sv, cv) and bv < 1.0 and sv < 1.0 and cv < 1.0:
                lb = r["capacity_unlock_pct"]
        fp_vals.append(("censored", lb))   # tuple signals censored; lb = lower bound
        scenarios.append(s)
        rnd_vals.append(rnd_cf)
        dc_vals.append(None)
        bind_constraints.append("censored")
        continue

    scenarios.append(s)
    fp_vals.append(fp_cf)
    rnd_vals.append(rnd_cf)
    dc_vals.append(fp_cf - rnd_cf)
    bind_constraints.append(bind if bind else "B_thermal")

# paired dC and observed FP/Random values excluding censored
dc_obs  = np.array([d for d in dc_vals if d is not None])
fp_obs  = np.array([f for f in fp_vals  if not isinstance(f, tuple)])
rnd_obs = np.array([r for i, r in enumerate(rnd_vals) if not isinstance(fp_vals[i], tuple)])

# bootstrap for CI
rng = np.random.default_rng(BOOT_SEED)
boot_med = np.array([np.median(rng.choice(dc_obs, size=len(dc_obs), replace=True)) for _ in range(N_BOOT)])

# -----------------------------------------------------------------------
# Figure 1: Paired scenario outcomes
# -----------------------------------------------------------------------
# Sort by FP value (ascending), censored scenario at end
order = []
for i, (s, fp, rnd) in enumerate(zip(scenarios, fp_vals, rnd_vals)):
    sort_key = fp if not isinstance(fp, tuple) else 9999
    order.append((sort_key, i))
order.sort()
sorted_indices = [o[1] for o in order]

fig1, ax = plt.subplots(figsize=(9, 4.5))

plot_x = 0
xticks, xlabels = [], []

for rank, idx in enumerate(sorted_indices):
    s   = scenarios[idx]
    fp  = fp_vals[idx]
    rnd = rnd_vals[idx]

    is_censored = isinstance(fp, tuple)
    rnd_y = rnd if rnd is not None else 0.0
    fp_y  = fp  if not is_censored else fp[1]   # fp[1] = lower bound for censored

    # connecting line (only to last safe point for censored)
    ax.plot([rank, rank], [rnd_y, fp_y],
            color="grey", lw=0.8, alpha=ALPHA_LINE, zorder=1)

    # Random dot
    ax.scatter(rank, rnd_y, color=COLOR_RND, s=28, zorder=3,
               marker="o", linewidths=0.3, edgecolors="white")

    if is_censored:
        # hollow lower-bound marker at last confirmed-safe load level
        ax.scatter(rank, fp_y, color="none", s=32, zorder=3,
                   marker="^", linewidths=1.0, edgecolors=COLOR_CENSORED_ARROW)
        # upward arrow from lower bound to chart top boundary
        ax.annotate("", xy=(rank, 36.5), xytext=(rank, fp_y + 1.5),
                    arrowprops=dict(arrowstyle="->", color=COLOR_CENSORED_ARROW,
                                   lw=1.2))
        ax.text(rank, 37.2, "s27\n> max", ha="center", va="bottom",
                fontsize=6.5, color=COLOR_CENSORED_ARROW)
    else:
        ax.scatter(rank, fp_y, color=COLOR_FP, s=28, zorder=3,
                   marker="^", linewidths=0.3, edgecolors="white")

    xticks.append(rank)
    xlabels.append(f"s{s:02d}")

# median lines
ax.axhline(np.median(fp_obs),  color=COLOR_FP,  lw=1.2, ls="--", alpha=0.8,
           label=f"FP median {np.median(fp_obs):.1f}%")
ax.axhline(np.median(rnd_obs), color=COLOR_RND, lw=1.2, ls="--", alpha=0.8,
           label=f"Random median {np.median(rnd_obs):.1f}%")

ax.set_xticks(xticks)
ax.set_xticklabels(xlabels, rotation=70, fontsize=6.5)
ax.set_ylabel("Feasible cohort capacity unlock (%)", fontsize=FONTSIZE_AXIS)
ax.set_title(
    "FP-cap-10 vs Random-feasible: 30 matched workload scenarios\n"
    "(sorted by FP capacity; arrows = right-censored)",
    fontsize=FONTSIZE_TITLE, pad=10)

fp_patch  = mpatches.Patch(color=COLOR_FP,  label="FP-cap-10  (triangle)")
rnd_patch = mpatches.Patch(color=COLOR_RND, label="Random-feasible  (circle)")
ax.legend(handles=[fp_patch, rnd_patch], fontsize=FONTSIZE_ANNOT,
          loc="upper left", frameon=False)

ax.set_xlim(-0.8, len(scenarios) - 0.2)
ax.set_ylim(-1, 38)

fig1.tight_layout()
out1 = FIGURES_DIR / "fig_mc_paired.png"
fig1.savefig(out1, dpi=180, bbox_inches="tight")
print(f"Saved {out1}")
plt.close(fig1)

# -----------------------------------------------------------------------
# Figure 2: dC distribution with bootstrap CI
# -----------------------------------------------------------------------
fig2, ax = plt.subplots(figsize=(6.5, 3.5))

# strip plot (jittered)
rng2 = np.random.default_rng(7)
jitter = rng2.uniform(-0.15, 0.15, size=len(dc_obs))
ax.scatter(dc_obs, jitter, color=COLOR_FP, s=40, alpha=0.75, zorder=4,
           marker="^", linewidths=0.3, edgecolors="white",
           label="Observed scenario (n=29)")

# bootstrap CI shaded band
ax.axvspan(BOOT_CI_LO, BOOT_CI_HI, alpha=ALPHA_SHADE * 1.5, color=COLOR_FP,
           label=f"Bootstrap 95% CI  [{BOOT_CI_LO:.1f}, {BOOT_CI_HI:.1f}] pp")

# median line
med = np.median(dc_obs)
ax.axvline(med, color=COLOR_FP, lw=1.8, ls="-",
           label=f"Median  +{med:.2f} pp")

# p5 / p95 tick marks
p5, p95 = np.percentile(dc_obs, 5), np.percentile(dc_obs, 95)
for pv, lbl in [(p5, "p5"), (p95, "p95")]:
    ax.axvline(pv, color=COLOR_FP, lw=0.9, ls=":", alpha=0.7)
    ax.text(pv, 0.42, lbl, ha="center", va="bottom", fontsize=7,
            color=COLOR_FP, alpha=0.9)

# censored note in margin -- not a data-space arrow
ax.text(0.99, 0.03,
        "s27 excluded: FP crossing > max tested load (+50%)",
        ha="right", va="bottom", fontsize=7, color=COLOR_CENSORED_ARROW,
        transform=ax.transAxes,
        bbox=dict(boxstyle="round,pad=0.25", fc="white",
                  ec=COLOR_CENSORED_ARROW, lw=0.6, alpha=0.9))

ax.set_xlabel("Paired feasible-capacity advantage  FP − Random (pp)", fontsize=FONTSIZE_AXIS)
ax.set_yticks([])
ax.set_ylim(-0.55, 0.55)
ax.set_xlim(-1, 36)
ax.set_title("Distribution of paired ΔC across 29 uncensored scenarios",
             fontsize=FONTSIZE_TITLE, pad=8)
ax.legend(fontsize=FONTSIZE_ANNOT, loc="upper left", frameon=False)

fig2.tight_layout()
out2 = FIGURES_DIR / "fig_mc_dc_dist.png"
fig2.savefig(out2, dpi=180, bbox_inches="tight")
print(f"Saved {out2}")
plt.close(fig2)

# -----------------------------------------------------------------------
# Figure 3: Binding constraint breakdown
# -----------------------------------------------------------------------
constraint_counts = {"B_thermal": 0, "cab_power": 0, "censored": 0}
for bc in bind_constraints:
    if bc in constraint_counts:
        constraint_counts[bc] += 1
    elif bc == "S_thermal":
        constraint_counts["B_thermal"] += 1   # roll up (shouldn't occur for FP)

labels  = ["Thermal B-budget\n(25/30)", "Cabinet power\n(4/30)", "Right-censored\n(1/30)"]
sizes   = [constraint_counts["B_thermal"], constraint_counts["cab_power"],
           constraint_counts["censored"]]
colors  = [COLOR_FP, "#555555", COLOR_CENSORED_ARROW]

fig3, axes = plt.subplots(1, 2, figsize=(8, 3.5),
                          gridspec_kw={"width_ratios": [1, 1.6]})

# Left: donut
wedge_props = dict(width=0.45, edgecolor="white", linewidth=1.5)
axes[0].pie(sizes, labels=None, colors=colors, autopct="%1.0f%%",
            pctdistance=0.75, startangle=90,
            wedgeprops=wedge_props, textprops={"fontsize": 8})
axes[0].set_title("FP-cap-10 binding constraint\n(30 scenarios)",
                  fontsize=FONTSIZE_TITLE, pad=8)

# add legend manually
for lbl, col in zip(labels, colors):
    axes[0].plot([], [], color=col, marker="s", linestyle="", ms=8, label=lbl)
axes[0].legend(loc="lower center", bbox_to_anchor=(0.5, -0.22),
               fontsize=7, frameon=False, ncol=1)

# Right: FP capacity sorted by constraint type, coloured
fp_by_bind = {"B_thermal": [], "cab_power": [], "censored": []}
for s, fp, bc in zip(scenarios, fp_vals, bind_constraints):
    key = bc if bc in fp_by_bind else "B_thermal"
    if fp is not None:
        fp_by_bind[key].append(fp)

ax_r = axes[1]
color_map = {"B_thermal": COLOR_FP, "cab_power": "#555555", "censored": COLOR_CENSORED_ARROW}
rank = 0
for key in ["B_thermal", "cab_power"]:
    vals = sorted(fp_by_bind[key])
    xs = range(rank, rank + len(vals))
    ax_r.bar(xs, vals, color=color_map[key], width=0.7, alpha=0.85)
    rank += len(vals)

ax_r.set_xlabel("Scenarios (grouped by binding constraint)", fontsize=FONTSIZE_AXIS)
ax_r.set_ylabel("FP feasible capacity (%)", fontsize=FONTSIZE_AXIS)
ax_r.set_title("FP capacity by binding constraint (29 uncensored scenarios)", fontsize=FONTSIZE_TITLE, pad=8)
ax_r.axhline(np.median(fp_obs), color=COLOR_FP, lw=1.2, ls="--", alpha=0.8,
             label=f"Median {np.median(fp_obs):.1f}%")
ax_r.set_xticks([])
ax_r.set_ylim(0, 38)
for key in ["B_thermal", "cab_power"]:
    ax_r.plot([], [], color=color_map[key], marker="s", ls="", ms=8,
              label=key.replace("_", " "))
ax_r.legend(fontsize=7, frameon=False)

fig3.tight_layout()
out3 = FIGURES_DIR / "fig_mc_constraints.png"
fig3.savefig(out3, dpi=180, bbox_inches="tight")
print(f"Saved {out3}")
plt.close(fig3)

print("All figures written.")
