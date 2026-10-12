#!/usr/bin/env python3
"""
M4 Static Candidate-Pool Sensitivity — Corrected figure.

Reads reconstructed crossings from m4_avail_finalize_v2.json and the
frozen simulation JSON for f<100% fractions. Produces the corrected
C_lower median curve and pairwise comparison table inset.

Outputs: m4_avail_transition_fig.pdf and .png (overwrites stale version)
"""

import json, sys, io, statistics
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[3]
OUT_DIR   = REPO_ROOT / "artifacts" / "revision1" / "results"
V2_FILE   = OUT_DIR / "m4_avail_finalize_v2.json"
TRANS_FILE= OUT_DIR / "m4_avail_transition.json"

v2    = json.loads(V2_FILE.read_text())
trans = json.loads(TRANS_FILE.read_text())

# ── Build reconstructed crossing lookup ────────────────────────────────
recon_cx = {}
for key, entry in v2["reconstructed_crossings"].items():
    s_idx = entry["scenario_idx"]
    pol   = entry["policy"]
    recon_cx[(s_idx, pol)] = entry["reconstructed"]

def get_crossing(trans_row, pol):
    key = (trans_row["scenario_idx"], pol)
    if key in recon_cx:
        return recon_cx[key]
    return trans_row["crossings"][pol]

trans_rows = trans["scenario_rows"]
POLICIES   = trans["policies"]
FRACTIONS  = trans["avail_fractions"]

# ── Compute C_lower medians per fraction/policy ───────────────────────
frac_data = {}
for f in FRACTIONS:
    rows_f = sorted([r for r in trans_rows if abs(r["avail_frac"] - f) < 1e-6],
                    key=lambda r: r["scenario_idx"])
    pol_medians = {}
    for pol in POLICIES:
        lows = [get_crossing(r, pol)["C_lower_pct"] for r in rows_f
                if get_crossing(r, pol).get("C_lower_pct") is not None]
        pol_medians[pol] = statistics.median(lows) if lows else 0.0
    frac_data[f] = pol_medians

# ── Compute corrected held-out (sc5-9) delta_lo medians at f=100% ─────
PAIR_KEYS = [
    ("spread_vs_fp",  "full_fp_spread", "full_fp"),
    ("spread_vs_loc", "full_fp_spread", "full_loc"),
    ("fp_vs_rand",    "full_fp",        "full_random"),
    ("spread_vs_rand","full_fp_spread", "full_random"),
]

rows_f100_held = sorted(
    [r for r in trans_rows if r["avail_frac"] > 0.999 and r["scenario_idx"] >= 5],
    key=lambda r: r["scenario_idx"]
)

def icmp(cx_a, cx_b):
    rc_a = cx_a.get("status") == "right_censored"
    rc_b = cx_b.get("status") == "right_censored"
    lo_a = cx_a["C_lower_pct"] or 0.0
    lo_b = cx_b["C_lower_pct"] or 0.0
    hi_a = None if rc_a else (cx_a.get("C_upper_pct") or lo_a)
    hi_b = None if rc_b else (cx_b.get("C_upper_pct") or lo_b)
    dlo = None if rc_b else lo_a - hi_b
    dhi = None if rc_a else hi_a - lo_b
    if dlo is not None and dlo > 0:   v = "def_a"
    elif dhi is not None and dhi < 0: v = "def_b"
    else:                              v = "ind"
    return dlo, dhi, v

table_rows = []
for pair_key, pol_a, pol_b in PAIR_KEYS:
    dlos, dhis, verdicts = [], [], []
    for r in rows_f100_held:
        cx_a = get_crossing(r, pol_a)
        cx_b = get_crossing(r, pol_b)
        dlo, dhi, v = icmp(cx_a, cx_b)
        dlos.append(dlo); dhis.append(dhi); verdicts.append(v)
    n = len(dlos)
    n_a   = verdicts.count("def_a")
    n_ind = verdicts.count("ind")
    n_b   = verdicts.count("def_b")
    med_lo = statistics.median(dlos)
    table_rows.append({
        "label": pair_key,
        "n_a": n_a, "n_ind": n_ind, "n_b": n_b, "n": n,
        "med_lo": med_lo,
    })

# ── Plot ───────────────────────────────────────────────────────────────
STYLE = {
    "full_random"    : dict(color="#888888", ls="--",  marker="o", label="Random"),
    "full_fp"        : dict(color="#1f77b4", ls="-",   marker="s", label="FP"),
    "full_fp_spread" : dict(color="#d62728", ls="-",   marker="^", label="FP-spread"),
    "full_loc"       : dict(color="#2ca02c", ls="-.", marker="D", label="Location"),
}

fracs_pct = [int(f * 100) for f in FRACTIONS]
x_vals    = np.array(fracs_pct, dtype=float)

fig, ax = plt.subplots(figsize=(7, 4.5))
fig.patch.set_facecolor("white")
ax.set_facecolor("#f7f7f7")

for pol, sty in STYLE.items():
    if pol not in POLICIES:
        continue
    y = [frac_data[f][pol] for f in FRACTIONS]
    ax.plot(x_vals, y, linewidth=1.8, markersize=6, **sty)

# Shade the infeasible region (f=60-90%)
ax.axvspan(55, 92, alpha=0.10, color="#cccccc", zorder=0)
ax.text(75, 2.7,
        "Pool too small for base workload\n(base-replay infeasible, all policies)",
        ha="center", va="center", fontsize=8.5, color="#555555",
        style="italic", multialignment="center")

ax.set_xlabel("Candidate pool fraction (% of fingerprinted cohort)", fontsize=10)
ax.set_ylabel("Median conservative headroom $C_{lower}$ (%)", fontsize=10)
ax.set_title("Static Candidate-Pool Sensitivity", fontsize=12, fontweight="bold")

ax.set_xlim(55, 104)
ax.set_ylim(-0.3, None)
ax.xaxis.set_major_formatter(mticker.PercentFormatter(xmax=100, decimals=0))
ax.yaxis.set_major_formatter(mticker.PercentFormatter(xmax=100, decimals=1))
ax.set_xticks(fracs_pct)
ax.grid(axis="y", linestyle=":", linewidth=0.6, color="#cccccc")
ax.spines[["top", "right"]].set_visible(False)
ax.legend(loc="upper left", fontsize=9, framealpha=0.9)

# Caption
fig.text(0.01, -0.02,
         "Subset fixed for entire replay scenario; does not reproduce time-varying production occupancy.",
         fontsize=7.5, color="#555555", style="italic")

plt.tight_layout()

out_base = OUT_DIR / "m4_avail_transition_fig"
fig.savefig(str(out_base) + ".pdf", bbox_inches="tight", dpi=200)
fig.savefig(str(out_base) + ".png", bbox_inches="tight", dpi=200)
plt.close()
print(f"Saved: {out_base}.pdf / .png")

# ── Print corrected table ──────────────────────────────────────────────
print("\nCorrected C_lower medians at f=100% (all 10 scenarios, reconstructed):")
for pol, sty in STYLE.items():
    if pol in frac_data[1.0]:
        print(f"  {sty['label']:12s}: {frac_data[1.0][pol]:.3f}%")

print("\nCorrected pairwise comparison table (held-out sc5-9, f=100%, reconstructed):")
print(f"  {'Pair':22s}  def_A  ind  def_B  dlo_med")
for tr in table_rows:
    lbl = {
        "spread_vs_fp":   "FP-spread vs FP",
        "spread_vs_loc":  "FP-spread vs Loc",
        "fp_vs_rand":     "FP vs Random",
        "spread_vs_rand": "FP-spread vs Random",
    }.get(tr["label"], tr["label"])
    print(f"  {lbl:22s}  {tr['n_a']}/{tr['n']}    "
          f"{tr['n_ind']}/{tr['n']}   {tr['n_b']}/{tr['n']}   "
          f"{tr['med_lo']:+.2f}pp")
