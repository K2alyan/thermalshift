"""
Review-2 main figure: forest-style plot of 8 preregistered comparisons at r=1.25.
Reads from challenge_analysis.json (frozen analysis output).
"""
import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ANALYSIS_JSON = os.path.join(SCRIPT_DIR, "..", "challenge_analysis.json")
OUT_DIR = SCRIPT_DIR

RATIO = "1.25"

# Display order (top to bottom): primary first, then node-specificity, then others
COMPARISON_ORDER = [
    "FP_vs_Random",
    "FP_vs_WithinCabPlacebo",
    "FP_vs_GlobalPlacebo",
    "FPSpread_vs_RandomSpread",
    "RandomSpread_vs_Random",
    "FPSpread_vs_FP",
    "FP_vs_PositionTemplate",
    "FPSpread_vs_PositionTemplate",
]

LABELS = {
    "FP_vs_Random":               "FP vs Random",
    "FP_vs_WithinCabPlacebo":     "FP vs Within-Cab Placebo",
    "FP_vs_GlobalPlacebo":        "FP vs Global Placebo",
    "FPSpread_vs_RandomSpread":   "FPSpread vs RandomSpread",
    "RandomSpread_vs_Random":     "RandomSpread vs Random",
    "FPSpread_vs_FP":             "FPSpread vs FP",
    "FP_vs_PositionTemplate":     "FP vs Position Template",
    "FPSpread_vs_PositionTemplate": "FPSpread vs Position Template",
}

CATEGORY_COLOR = {
    "primary":             "#1a6faf",
    "node_level_placebo":  "#2ca02c",
    "global_placebo":      "#7fbc41",
    "spread_advantage":    "#9467bd",
    "spread_baseline":     "#d62728",
    "spread_vs_fp":        "#e6550d",
    "thermal_vs_position": "#8c564b",
    "spread_vs_position":  "#c49c94",
}

SPECIAL_LABEL = {
    "FP_vs_Random":           "Primary endpoint",
    "FP_vs_WithinCabPlacebo": "Node-specificity test",
}

def load_data():
    with open(ANALYSIS_JSON) as f:
        data = json.load(f)
    return data

def extract_r125(data):
    rows = []
    for name in COMPARISON_ORDER:
        comp = data["results"][name]
        r = comp["ratios"][RATIO]
        rows.append({
            "name": name,
            "label": LABELS[name],
            "category": comp["category"],
            "n_A": r["n_definitely_A"],
            "n_I": r["n_indistinguishable"],
            "n_B": r["n_definitely_B"],
            "median_lo": r["median_delta_lo"],
            "ci_lo": r["bootstrap95_delta_lo"][0],
            "ci_hi": r["bootstrap95_delta_lo"][1],
        })
    return rows

def make_forest_plot(rows):
    n = len(rows)
    fig, ax = plt.subplots(figsize=(10, 6.5))

    y_positions = list(range(n - 1, -1, -1))  # top to bottom

    for i, (row, y) in enumerate(zip(rows, y_positions)):
        color = CATEGORY_COLOR.get(row["category"], "#555555")
        ci_lo = row["ci_lo"]
        ci_hi = row["ci_hi"]
        med = row["median_lo"]

        # CI line
        ax.plot([ci_lo, ci_hi], [y, y], color=color, linewidth=2.0, solid_capstyle="round")
        # Median point
        ax.scatter([med], [y], color=color, s=60, zorder=5)

        # A/I/B counts annotation (right side)
        count_str = f"{row['n_A']} / {row['n_I']} / {row['n_B']}"
        ax.text(1.01, y, count_str, transform=ax.get_yaxis_transform(),
                va="center", ha="left", fontsize=8.5, color="#333333")

        # Special label indicator (left of y-axis label area)
        if row["name"] in SPECIAL_LABEL:
            special = SPECIAL_LABEL[row["name"]]
            color_special = "#1a6faf" if row["name"] == "FP_vs_Random" else "#2ca02c"
            ax.text(-0.01, y, f"[{special}]",
                    transform=ax.get_yaxis_transform(),
                    va="center", ha="right", fontsize=7.5,
                    color=color_special, style="italic")

    # Separator line between node-specificity (idx 1) and global placebo (idx 2)
    ax.axhline(y=y_positions[1] - 0.5, color="#cccccc", linewidth=0.8, linestyle="--")

    # Zero line
    ax.axvline(x=0, color="black", linewidth=1.0, linestyle="-")

    ax.set_yticks(y_positions)
    ax.set_yticklabels([r["label"] for r in rows], fontsize=10)
    ax.set_xlabel("Conservative bracket separation, delta_lo (pp)\n"
                  r"[C$_{\rm lower}$(A) $-$ C$_{\rm upper}$(B)]",
                  fontsize=10)
    ax.set_title(
        "Review-2 Challenge: 8 Preregistered Comparisons at r = 1.25\n"
        "(25 held-out scenarios, sc30–sc54; bootstrap 95% CI on median delta_lo)",
        fontsize=11, pad=10
    )

    # Legend patches
    legend_items = [
        mpatches.Patch(color=CATEGORY_COLOR["primary"], label="Primary (FP vs Random)"),
        mpatches.Patch(color=CATEGORY_COLOR["node_level_placebo"], label="Node-specificity placebo"),
        mpatches.Patch(color=CATEGORY_COLOR["global_placebo"], label="Global placebo"),
        mpatches.Patch(color=CATEGORY_COLOR["spread_advantage"], label="Spread comparisons"),
        mpatches.Patch(color=CATEGORY_COLOR["spread_baseline"], label="Spread baseline"),
        mpatches.Patch(color=CATEGORY_COLOR["spread_vs_fp"], label="FPSpread vs FP"),
        mpatches.Patch(color=CATEGORY_COLOR["thermal_vs_position"], label="Position template"),
    ]
    ax.legend(handles=legend_items, loc="lower right", fontsize=8, framealpha=0.8)

    # A/I/B column header
    ax.text(1.01, 1.01, "A / I / B", transform=ax.transAxes,
            va="bottom", ha="left", fontsize=8.5, fontweight="bold", color="#333333")

    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.tick_params(axis="y", length=0)
    ax.margins(y=0.07)

    plt.tight_layout()
    out_path = os.path.join(OUT_DIR, "fig_r2_factorial_r125.png")
    out_pdf  = os.path.join(OUT_DIR, "fig_r2_factorial_r125.pdf")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.savefig(out_pdf, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")
    print(f"Saved: {out_pdf}")
    return out_path

def make_crossover_plot(data):
    comp = data["results"]["FPSpread_vs_FP"]
    ratios_ordered = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"]
    ratio_labels = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "Unr."]

    medians, ci_lo_list, ci_hi_list, n_A_list, n_I_list, n_B_list = [], [], [], [], [], []
    for r in ratios_ordered:
        rd = comp["ratios"][r]
        medians.append(rd["median_delta_lo"])
        ci_lo_list.append(rd["bootstrap95_delta_lo"][0])
        ci_hi_list.append(rd["bootstrap95_delta_lo"][1])
        n_A_list.append(rd["n_definitely_A"])
        n_I_list.append(rd["n_indistinguishable"])
        n_B_list.append(rd["n_definitely_B"])

    x = np.arange(len(ratios_ordered))
    fig, ax = plt.subplots(figsize=(9, 5))

    color = "#e6550d"
    ax.fill_between(x, ci_lo_list, ci_hi_list, alpha=0.18, color=color)
    ax.plot(x, medians, color=color, linewidth=2.0, marker="o", markersize=6, zorder=4)
    ax.axhline(y=0, color="black", linewidth=1.0)

    # Annotate A/I/B
    for xi, (na, ni, nb, med) in enumerate(zip(n_A_list, n_I_list, n_B_list, medians)):
        offset = 0.6 if med >= 0 else -1.0
        ax.text(xi, med + offset, f"{na}/{ni}/{nb}",
                ha="center", va="bottom" if offset > 0 else "top",
                fontsize=7.5, color="#444444")

    ax.set_xticks(x)
    ax.set_xticklabels(ratio_labels, fontsize=10)
    ax.set_xlabel("Candidate choice ratio (r)", fontsize=10)
    ax.set_ylabel("Median delta_lo (pp)", fontsize=10)
    ax.set_title(
        "Supplementary: FPSpread vs FP Crossover Across Candidate Ratios\n"
        "(Preregistered secondary finding; 25 held-out scenarios; bootstrap 95% CI shaded;\n"
        "annotation: A / I / B per ratio)",
        fontsize=10, pad=8
    )
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    out_path = os.path.join(OUT_DIR, "fig_r2_fpspread_crossover.png")
    out_pdf  = os.path.join(OUT_DIR, "fig_r2_fpspread_crossover.pdf")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.savefig(out_pdf, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")
    print(f"Saved: {out_pdf}")
    return out_path

def make_policy_matrix(data):
    """7 policies × 7 ratios heatmap of median delta_lo vs full_random baseline."""
    ratios_ordered = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"]
    ratio_labels   = ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "Unr."]

    # Comparisons that have full_random as policy_B give absolute reading vs random
    # We want the median_delta_lo for each comparison×ratio cell
    comparisons_for_matrix = [
        ("FP_vs_Random",             "FP\nvs Random"),
        ("FP_vs_WithinCabPlacebo",   "FP\nvs WCab"),
        ("FP_vs_GlobalPlacebo",      "FP\nvs Global"),
        ("FPSpread_vs_RandomSpread", "FPSpread\nvs RndSpread"),
        ("RandomSpread_vs_Random",   "RndSpread\nvs Random"),
        ("FPSpread_vs_FP",           "FPSpread\nvs FP"),
        ("FP_vs_PositionTemplate",   "FP\nvs PosTmpl"),
        ("FPSpread_vs_PositionTemplate", "FPSpread\nvs PosTmpl"),
    ]

    matrix = np.zeros((len(comparisons_for_matrix), len(ratios_ordered)))
    for ci, (cname, _) in enumerate(comparisons_for_matrix):
        for ri, ratio in enumerate(ratios_ordered):
            matrix[ci, ri] = data["results"][cname]["ratios"][ratio]["median_delta_lo"]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    vlim = max(abs(matrix.min()), abs(matrix.max()))
    im = ax.imshow(matrix, aspect="auto", cmap="RdBu", vmin=-vlim, vmax=vlim)

    ax.set_xticks(range(len(ratios_ordered)))
    ax.set_xticklabels(ratio_labels, fontsize=9)
    ax.set_yticks(range(len(comparisons_for_matrix)))
    ax.set_yticklabels([label for _, label in comparisons_for_matrix], fontsize=9)
    ax.set_xlabel("Candidate choice ratio (r)", fontsize=10)
    ax.set_title(
        "Supplementary: Median delta_lo Across 8 Comparisons × 7 Ratios\n"
        "(Blue = A better; Red = B better; 25 held-out scenarios)",
        fontsize=10, pad=8
    )

    # Cell annotations
    for ci in range(matrix.shape[0]):
        for ri in range(matrix.shape[1]):
            val = matrix[ci, ri]
            ax.text(ri, ci, f"{val:+.1f}", ha="center", va="center",
                    fontsize=7.5, color="black" if abs(val) < 0.6 * vlim else "white")

    plt.colorbar(im, ax=ax, label="Median delta_lo (pp)", shrink=0.8)
    plt.tight_layout()
    out_path = os.path.join(OUT_DIR, "fig_r2_policy_matrix.png")
    out_pdf  = os.path.join(OUT_DIR, "fig_r2_policy_matrix.pdf")
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.savefig(out_pdf, bbox_inches="tight")
    plt.close()
    print(f"Saved: {out_path}")
    print(f"Saved: {out_pdf}")
    return out_path

if __name__ == "__main__":
    data = load_data()
    rows = extract_r125(data)
    make_forest_plot(rows)
    make_crossover_plot(data)
    make_policy_matrix(data)
    print("Done.")
