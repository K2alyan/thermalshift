"""
Review-2 supplemental robustness figure: 2-panel sensitivity analysis.

Panel A (E1): FP_vs_Random median delta_lo (pp) vs cabinet-envelope scale factor [0.90–1.10].
Panel B (E2): FP_vs_Random median delta_lo (pp) vs 6 prespecified beta values.

Reads from frozen sensitivity analysis outputs:
  artifacts/revision2/sensitivity_cabinet_scale.json  (E1 / H8=ROBUST)
  artifacts/revision2/sensitivity_loo_beta.json        (E2 / H7=STABLE)

Writes: artifacts/revision2/figures/fig_r2_robustness.png
"""
import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REV2_DIR   = os.path.join(SCRIPT_DIR, "..")
E1_JSON    = os.path.join(REV2_DIR, "sensitivity_cabinet_scale.json")
E2_JSON    = os.path.join(REV2_DIR, "sensitivity_loo_beta.json")
OUT_PNG    = os.path.join(SCRIPT_DIR, "fig_r2_robustness.png")
OUT_PDF    = os.path.join(SCRIPT_DIR, "fig_r2_robustness.pdf")

PRIMARY_COLOR = "#1a6faf"
POINT_COLOR   = "#1a6faf"
ERROR_COLOR   = "#5599cc"

def load(path):
    with open(path) as f:
        return json.load(f)

def make_figure():
    e1 = load(E1_JSON)
    e2 = load(E2_JSON)

    # ── Panel A: E1 cabinet-scale sensitivity ──────────────────────────────
    scales = sorted(e1["scale_results"].keys(), key=float)
    a_x    = [float(s) for s in scales]
    a_med  = [e1["scale_results"][s]["median_delta_lo"] for s in scales]
    a_lo   = [e1["scale_results"][s]["bootstrap95_delta_lo"][0] for s in scales]
    a_hi   = [e1["scale_results"][s]["bootstrap95_delta_lo"][1] for s in scales]
    a_yerr = [
        [m - lo for m, lo in zip(a_med, a_lo)],
        [hi - m  for m, hi  in zip(a_med, a_hi)],
    ]

    # ── Panel B: E2 beta sensitivity ──────────────────────────────────────
    beta_order = ["primary", "beta_f_frozen", "prospective", "jackknife", "cf_p5", "cf_p95"]
    beta_labels = {
        "primary":      "Primary\n(LOO CF\n1.114)",
        "beta_f_frozen":"Frozen\n(1.125)",
        "prospective":  "Prospective\n(0.96)",
        "jackknife":    "Jackknife\nmean\n(1.083)",
        "cf_p5":        "CF P5\n(1.066)",
        "cf_p95":       "CF P95\n(1.169)",
    }
    b_results = e2["beta_results"]
    b_x    = np.arange(len(beta_order))
    b_med  = [b_results[k]["median_delta_lo"] for k in beta_order]
    b_lo   = [b_results[k]["bootstrap95_delta_lo"][0] for k in beta_order]
    b_hi   = [b_results[k]["bootstrap95_delta_lo"][1] for k in beta_order]
    b_yerr = [
        [m - lo for m, lo in zip(b_med, b_lo)],
        [hi - m  for m, hi  in zip(b_med, b_hi)],
    ]

    # ── Layout ────────────────────────────────────────────────────────────
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))
    fig.suptitle(
        "Review-2 Robustness: FP vs Random at $r = 1.25$ (sc30–54, $N = 25$)",
        fontsize=11, fontweight="bold", y=1.02,
    )

    # ── Panel A ───────────────────────────────────────────────────────────
    ax1.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
    ax1.errorbar(
        a_x, a_med,
        yerr=a_yerr,
        fmt="o", color=POINT_COLOR, ecolor=ERROR_COLOR,
        capsize=4, linewidth=1.5, markersize=6, zorder=3,
    )
    # Highlight primary (scale=1.00)
    primary_idx = a_x.index(1.0)
    ax1.scatter([a_x[primary_idx]], [a_med[primary_idx]],
                s=80, color=PRIMARY_COLOR, zorder=5, marker="D",
                label="Primary (scale=1.00)")
    ax1.set_xlabel("Cabinet-envelope scale factor", fontsize=10)
    ax1.set_ylabel("Median conservative bracket separation (pp)", fontsize=9)
    ax1.set_title("Panel A — E1: Cabinet-scale sensitivity\n(H8 = ROBUST)", fontsize=10)
    ax1.set_xticks(a_x)
    ax1.set_xticklabels([f"{s:.2f}" for s in a_x], fontsize=9)
    ax1.set_xlim(0.87, 1.13)
    ax1.set_ylim(bottom=-2)
    ax1.legend(fontsize=8, loc="upper right")
    ax1.annotate(
        "H8 = ROBUST\nSign positive at all scales",
        xy=(0.03, 0.97), xycoords="axes fraction",
        va="top", ha="left", fontsize=8,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#e8f4e8", edgecolor="#2ca02c", alpha=0.8),
    )

    # ── Panel B ───────────────────────────────────────────────────────────
    ax2.axhline(0, color="black", linewidth=0.8, linestyle="--", alpha=0.5)
    ax2.errorbar(
        b_x, b_med,
        yerr=b_yerr,
        fmt="o", color=POINT_COLOR, ecolor=ERROR_COLOR,
        capsize=4, linewidth=1.5, markersize=6, zorder=3,
    )
    # Highlight primary beta
    ax2.scatter([b_x[0]], [b_med[0]],
                s=80, color=PRIMARY_COLOR, zorder=5, marker="D",
                label="Primary (LOO CF)")
    ax2.set_xlabel("Beta value", fontsize=10)
    ax2.set_ylabel("Median conservative bracket separation (pp)", fontsize=9)
    ax2.set_title("Panel B — E2: Beta sensitivity\n(H7 = STABLE)", fontsize=10)
    ax2.set_xticks(b_x)
    ax2.set_xticklabels([beta_labels[k] for k in beta_order], fontsize=7.5)
    ax2.set_ylim(bottom=-2)
    ax2.legend(fontsize=8, loc="upper right")
    ax2.annotate(
        "H7 = STABLE\nNo sign reversal",
        xy=(0.03, 0.97), xycoords="axes fraction",
        va="top", ha="left", fontsize=8,
        bbox=dict(boxstyle="round,pad=0.3", facecolor="#e8f4e8", edgecolor="#2ca02c", alpha=0.8),
    )

    # ── Post-exposure note ────────────────────────────────────────────────
    fig.text(
        0.5, -0.04,
        "E1/E2 design prespecified at commit 5733b73; executed after primary results (Phase G) were "
        "exposed — disclosed in POST_EXPOSURE_SENSITIVITY_RECOVERY.md.",
        ha="center", va="top", fontsize=7, style="italic", color="#666666",
        wrap=True,
    )

    plt.tight_layout()
    plt.savefig(OUT_PNG, dpi=300, bbox_inches="tight")
    plt.savefig(OUT_PDF, bbox_inches="tight")
    plt.close()
    print(f"Written: {OUT_PNG}")
    print(f"Written: {OUT_PDF}")

if __name__ == "__main__":
    make_figure()
