#!/usr/bin/env python3
"""
c4_cabinet_diagnostic.py — Cabinet accounting diagnostic for cabinets 2600, 2601, 2602

Reads from:
  - C2 merged output: gate_f_sc30-54_1p25_c2manuscript.json  (cabinet_accounting fields)
  - fp_node_topology.csv                                       (structural cohort share)
  - phase3a_fingerprint_2024.parquet (optional)                (FA_2024 per node)

No new scheduling replay. All diagnostic metrics derived from committed and
static-input data only.

Reports per-cabinet (2600, 2601, 2602):
  - Structural cohort share: fraction of FP cohort nodes in each cabinet
  - FA_2024 summary: median / q25 / q75 across cohort nodes (if parquet available)
  - full_fp realized node_hours share: per scenario, per lambda; aggregated across scenarios
  - full_random realized node_hours share: same
  - FP enrichment ratio vs Random and vs structural share
  - event_touches share per policy
  - Scenario-level distribution of cabinet dominance
"""

import sys, json, hashlib
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT    = Path(__file__).resolve().parents[3]
RESULTS      = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"
TABLE_DIR    = REPO_ROOT / "artifacts" / "revision1" / "tables"
P1_DIR       = REPO_ROOT / "artifacts" / "phase1" / "analysis"
DATA_DIR     = Path(__file__).parent   # fallback; overridden if env var set

import os
_data_env = os.environ.get("THERMALSHIFT_DATA_DIR", "")
if _data_env:
    DATA_DIR = Path(_data_env)

C2_PATH      = RESULTS / "gate_f_sc30-54_1p25_c2manuscript.json"
TOPO_PATH    = TABLE_DIR / "fp_node_topology.csv"
FA_PATH      = P1_DIR / "phase3a_fingerprint_2024.parquet"

OUT_JSON     = RESULTS / "c4_cabinet_diagnostic.json"
OUT_MD       = REPO_ROOT / "artifacts" / "manuscript_completion" / "C4_CABINET_DIAGNOSTIC.md"

TARGET_CABS  = [2600, 2601, 2602]
RATIO        = "1.25"
FOCUS_POLS   = ["full_fp", "full_random"]
N_SCENARIOS  = 25
SC_FIRST     = 30
SC_LAST      = 54


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _aggregate_cab_metrics(lambda_rows: list[dict]) -> dict:
    """
    Sum node_hours and event_touches across all lambda rows for one policy run.
    Returns {cab_id: {"node_hours": float, "event_touches": int}}.
    """
    totals: dict = {}
    for row in lambda_rows:
        cab_acct = row.get("cabinet_accounting")
        if not cab_acct:
            continue
        for cab_str, nh in cab_acct.get("node_hours", {}).items():
            cab = int(cab_str)
            if cab not in totals:
                totals[cab] = {"node_hours": 0.0, "event_touches": 0}
            totals[cab]["node_hours"] += float(nh or 0.0)
        for cab_str, ev in cab_acct.get("event_touches", {}).items():
            cab = int(cab_str)
            if cab not in totals:
                totals[cab] = {"node_hours": 0.0, "event_touches": 0}
            totals[cab]["event_touches"] += int(ev or 0)
    return totals


def main():
    # 1. Load C2 merged output
    if not C2_PATH.exists():
        sys.exit(f"[ABORT] C2 merged output not found: {C2_PATH}")
    print(f"[OK] C2 merged output: {C2_PATH.name}  (SHA256: {sha256_file(C2_PATH)[:16]}...)")

    with open(C2_PATH) as f:
        c2_data = json.load(f)

    # 2. Load fp topology for structural cohort share
    if not TOPO_PATH.exists():
        sys.exit(f"[ABORT] FP topology not found: {TOPO_PATH}")
    fp_topo = pd.read_csv(TOPO_PATH)
    total_fp_nodes = len(fp_topo)
    structural_share: dict = {}
    for cab in TARGET_CABS:
        n_cab = int((fp_topo["cabinet"] == cab).sum())
        structural_share[cab] = n_cab / total_fp_nodes if total_fp_nodes > 0 else 0.0
    print(f"[OK] FP topology loaded: {total_fp_nodes} nodes")
    for cab in TARGET_CABS:
        n = int((fp_topo["cabinet"] == cab).sum())
        print(f"     Cabinet {cab}: {n}/{total_fp_nodes} FP nodes "
              f"({structural_share[cab]*100:.2f}% structural share)")

    # 3. Load FA_2024 per node (optional)
    fa_available = False
    fa_by_cab: dict = {}
    if FA_PATH.exists():
        try:
            fp_fa = pd.read_parquet(FA_PATH)
            fp_topo_merged = fp_topo.merge(
                fp_fa[["FA_2024"]].rename_axis("hostname").reset_index(),
                on="hostname", how="left"
            )
            for cab in TARGET_CABS:
                mask = fp_topo_merged["cabinet"] == cab
                fa_vals = fp_topo_merged.loc[mask, "FA_2024"].dropna().values
                if len(fa_vals) > 0:
                    fa_by_cab[cab] = {
                        "n_with_fa":  int(len(fa_vals)),
                        "median":     float(np.median(fa_vals)),
                        "q25":        float(np.percentile(fa_vals, 25)),
                        "q75":        float(np.percentile(fa_vals, 75)),
                        "mean":       float(np.mean(fa_vals)),
                    }
            fa_available = True
            print(f"[OK] FA_2024 data loaded from {FA_PATH.name}")
        except Exception as e:
            print(f"[WARN] Could not load FA_2024: {e} — FA stats omitted")
    else:
        print(f"[INFO] FA_2024 parquet not found — FA stats omitted (no data dir needed)")

    # 4. Per-scenario cabinet accounting aggregation
    scenarios = c2_data["scenario_results"]
    sc_indices = sorted(sc["scenario_idx"] for sc in scenarios)
    assert sc_indices == list(range(SC_FIRST, SC_LAST + 1)), f"Unexpected scenario indices: {sc_indices}"

    # Accumulated across scenarios: {pol: {cab: {node_hours, event_touches}}}
    global_totals: dict = {pol: {} for pol in FOCUS_POLS}
    # Per-scenario fractions for distribution analysis
    sc_fractions: dict = {pol: {cab: [] for cab in TARGET_CABS} for pol in FOCUS_POLS}

    for sc in sorted(scenarios, key=lambda s: s["scenario_idx"]):
        sc_idx = sc["scenario_idx"]
        ratio_data = sc["ratios"].get(RATIO, {})

        for pol in FOCUS_POLS:
            pol_data = ratio_data.get(pol)
            if pol_data is None:
                continue
            lambda_rows = pol_data.get("lambda_rows", [])
            cab_metrics = _aggregate_cab_metrics(lambda_rows)

            # Total node_hours across all cabinets
            total_nh = sum(m["node_hours"] for m in cab_metrics.values())
            total_ev = sum(m["event_touches"] for m in cab_metrics.values())

            # Per-cabinet share for this scenario
            for cab in TARGET_CABS:
                m = cab_metrics.get(cab, {"node_hours": 0.0, "event_touches": 0})
                nh_frac = m["node_hours"] / total_nh if total_nh > 0 else 0.0
                sc_fractions[pol][cab].append(nh_frac)

            # Accumulate global totals
            for cab, m in cab_metrics.items():
                if cab not in global_totals[pol]:
                    global_totals[pol][cab] = {"node_hours": 0.0, "event_touches": 0}
                global_totals[pol][cab]["node_hours"]    += m["node_hours"]
                global_totals[pol][cab]["event_touches"] += m["event_touches"]

    # 5. Compute summary metrics per cabinet
    per_cabinet: dict = {}
    for cab in TARGET_CABS:
        cab_result: dict = {
            "cabinet": cab,
            "structural_cohort_share": structural_share[cab],
            "n_fp_nodes": int((fp_topo["cabinet"] == cab).sum()),
        }
        if fa_available and cab in fa_by_cab:
            cab_result["fa_2024"] = fa_by_cab[cab]

        for pol in FOCUS_POLS:
            total_pol_nh = sum(m["node_hours"] for m in global_totals[pol].values())
            total_pol_ev = sum(m["event_touches"] for m in global_totals[pol].values())
            cab_pol = global_totals[pol].get(cab, {"node_hours": 0.0, "event_touches": 0})

            global_nh_frac = cab_pol["node_hours"] / total_pol_nh if total_pol_nh > 0 else 0.0
            global_ev_frac = cab_pol["event_touches"] / total_pol_ev if total_pol_ev > 0 else 0.0

            sc_frac_arr = np.array(sc_fractions[pol][cab])
            cab_result[pol] = {
                "global_node_hours_share":    global_nh_frac,
                "global_event_touches_share": global_ev_frac,
                "total_node_hours":           cab_pol["node_hours"],
                "total_event_touches":        cab_pol["event_touches"],
                "per_scenario_nh_share": {
                    "median": float(np.median(sc_frac_arr)),
                    "q25":    float(np.percentile(sc_frac_arr, 25)),
                    "q75":    float(np.percentile(sc_frac_arr, 75)),
                    "min":    float(np.min(sc_frac_arr)),
                    "max":    float(np.max(sc_frac_arr)),
                    "values": [round(v, 6) for v in sc_frac_arr.tolist()],
                },
            }

        # Enrichment ratios
        fp_share  = cab_result["full_fp"]["global_node_hours_share"]
        rnd_share = cab_result["full_random"]["global_node_hours_share"]
        struct    = structural_share[cab]
        cab_result["enrichment"] = {
            "fp_vs_structural":    fp_share  / struct    if struct    > 0 else None,
            "fp_vs_random":        fp_share  / rnd_share if rnd_share > 0 else None,
            "random_vs_structural":rnd_share / struct    if struct    > 0 else None,
        }

        per_cabinet[str(cab)] = cab_result

    # 6. Combined target-cabinet share (2600+2601+2602)
    combined: dict = {}
    for pol in FOCUS_POLS:
        total_pol_nh = sum(m["node_hours"] for m in global_totals[pol].values())
        combined_nh = sum(
            global_totals[pol].get(c, {"node_hours": 0.0})["node_hours"]
            for c in TARGET_CABS
        )
        combined[pol] = {
            "combined_node_hours_share": combined_nh / total_pol_nh if total_pol_nh > 0 else 0.0,
        }
    struct_combined = sum(structural_share[c] for c in TARGET_CABS)
    combined["structural_combined_share"] = struct_combined
    fp_comb = combined["full_fp"]["combined_node_hours_share"]
    rnd_comb = combined["full_random"]["combined_node_hours_share"]
    combined["enrichment_fp_vs_structural"] = fp_comb / struct_combined if struct_combined > 0 else None
    combined["enrichment_fp_vs_random"]     = fp_comb / rnd_comb        if rnd_comb       > 0 else None

    # 7. Compile result
    result = {
        "source": {
            "c2_merged": str(C2_PATH.name),
            "c2_sha256": sha256_file(C2_PATH),
            "topology":  str(TOPO_PATH.name),
            "fa_available": fa_available,
        },
        "target_cabinets": TARGET_CABS,
        "ratio": RATIO,
        "n_scenarios": N_SCENARIOS,
        "n_fp_cohort_nodes": total_fp_nodes,
        "per_cabinet": per_cabinet,
        "combined_target_cabinets": combined,
    }

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n[OK] Written: {OUT_JSON}")

    OUT_MD.parent.mkdir(parents=True, exist_ok=True)
    write_markdown(result)
    print(f"[OK] Written: {OUT_MD}")

    # 8. Console summary
    print("\n-- Cabinet 2600/2601/2602 Diagnostic Summary --")
    print(f"{'Cabinet':>8} {'Structural%':>12} {'FP share%':>10} {'Rnd share%':>11} {'FP/Rnd':>7} {'FP/Struct':>10}")
    for cab in TARGET_CABS:
        cr = per_cabinet[str(cab)]
        struct_pct = cr["structural_cohort_share"] * 100
        fp_pct     = cr["full_fp"]["global_node_hours_share"] * 100
        rnd_pct    = cr["full_random"]["global_node_hours_share"] * 100
        enr_rnd    = cr["enrichment"]["fp_vs_random"]
        enr_str    = cr["enrichment"]["fp_vs_structural"]
        print(f"{cab:>8} {struct_pct:>11.2f}% {fp_pct:>9.2f}% {rnd_pct:>10.2f}% "
              f"{enr_rnd:>7.2f}x {enr_str:>9.2f}x")
    print(f"{'COMBINED':>8} {combined['structural_combined_share']*100:>11.2f}% "
          f"{combined['full_fp']['combined_node_hours_share']*100:>9.2f}% "
          f"{combined['full_random']['combined_node_hours_share']*100:>10.2f}% "
          f"{combined.get('enrichment_fp_vs_random', 0.0):>7.2f}x "
          f"{combined.get('enrichment_fp_vs_structural', 0.0):>9.2f}x")


# ── Markdown output ───────────────────────────────────────────────────────────

def write_markdown(result: dict) -> None:
    lines: list = []
    A = lines.append
    per_cabinet = result["per_cabinet"]
    combined = result["combined_target_cabinets"]

    A("# C4 Cabinet Accounting Diagnostic")
    A("")
    A(f"**Source:** `{result['source']['c2_merged']}`  ")
    A(f"**SHA256:** `{result['source']['c2_sha256']}`  ")
    A(f"**Ratio:** r={result['ratio']}  **Scenarios:** {result['n_scenarios']} (sc30–sc54)  ")
    A(f"**FP cohort size:** {result['n_fp_cohort_nodes']} nodes  ")
    A(f"**FA_2024 available:** {result['source']['fa_available']}  ")
    A("")
    A("---")
    A("")

    A("## 1. Per-Cabinet Summary")
    A("")
    A("| Cabinet | FP nodes | Structural% | FP node-hr% | Rnd node-hr% | FP/Rnd | FP/Struct |")
    A("|---------|----------|------------|------------|-------------|--------|----------|")
    for cab in TARGET_CABS:
        cr = per_cabinet[str(cab)]
        A(f"| {cab} "
          f"| {cr['n_fp_nodes']} "
          f"| {cr['structural_cohort_share']*100:.2f}% "
          f"| {cr['full_fp']['global_node_hours_share']*100:.2f}% "
          f"| {cr['full_random']['global_node_hours_share']*100:.2f}% "
          f"| {cr['enrichment']['fp_vs_random']:.2f}x "
          f"| {cr['enrichment']['fp_vs_structural']:.2f}x |")
    A(f"| **Combined** "
      f"| — "
      f"| {combined['structural_combined_share']*100:.2f}% "
      f"| {combined['full_fp']['combined_node_hours_share']*100:.2f}% "
      f"| {combined['full_random']['combined_node_hours_share']*100:.2f}% "
      f"| {combined.get('enrichment_fp_vs_random', 0.0):.2f}x "
      f"| {combined.get('enrichment_fp_vs_structural', 0.0):.2f}x |")
    A("")
    A("---")
    A("")

    A("## 2. Per-Scenario Node-Hour Share Distribution (full_fp)")
    A("")
    A("| Cabinet | median% | q25% | q75% | min% | max% |")
    A("|---------|---------|------|------|------|------|")
    for cab in TARGET_CABS:
        cr = per_cabinet[str(cab)]["full_fp"]["per_scenario_nh_share"]
        A(f"| {cab} "
          f"| {cr['median']*100:.2f}% "
          f"| {cr['q25']*100:.2f}% "
          f"| {cr['q75']*100:.2f}% "
          f"| {cr['min']*100:.2f}% "
          f"| {cr['max']*100:.2f}% |")
    A("")
    A("---")
    A("")

    A("## 3. Per-Scenario Node-Hour Share Distribution (full_random)")
    A("")
    A("| Cabinet | median% | q25% | q75% | min% | max% |")
    A("|---------|---------|------|------|------|------|")
    for cab in TARGET_CABS:
        cr = per_cabinet[str(cab)]["full_random"]["per_scenario_nh_share"]
        A(f"| {cab} "
          f"| {cr['median']*100:.2f}% "
          f"| {cr['q25']*100:.2f}% "
          f"| {cr['q75']*100:.2f}% "
          f"| {cr['min']*100:.2f}% "
          f"| {cr['max']*100:.2f}% |")
    A("")
    A("---")
    A("")

    if result["source"]["fa_available"]:
        A("## 4. FA_2024 Distribution for Target Cabinets")
        A("")
        A("| Cabinet | n_nodes | median FA | q25 FA | q75 FA | mean FA |")
        A("|---------|---------|----------|--------|--------|--------|")
        for cab in TARGET_CABS:
            cr = per_cabinet[str(cab)]
            if "fa_2024" in cr:
                fa = cr["fa_2024"]
                A(f"| {cab} | {fa['n_with_fa']} | {fa['median']:.4f} "
                  f"| {fa['q25']:.4f} | {fa['q75']:.4f} | {fa['mean']:.4f} |")
        A("")
        A("---")
        A("")

    A("## 5. Interpretation")
    A("")
    comb_fp_pct  = combined["full_fp"]["combined_node_hours_share"] * 100
    comb_rnd_pct = combined["full_random"]["combined_node_hours_share"] * 100
    comb_str_pct = combined["structural_combined_share"] * 100
    A(f"Cabinets 2600–2602 together hold {comb_str_pct:.2f}% of FP cohort nodes structurally. "
      f"Under full_fp they receive {comb_fp_pct:.2f}% of selected node-hours "
      f"(enrichment vs structural: {combined.get('enrichment_fp_vs_structural', 0.0):.2f}x; "
      f"vs random: {combined.get('enrichment_fp_vs_random', 0.0):.2f}x). "
      f"Under full_random they receive {comb_rnd_pct:.2f}% "
      f"(consistent with random allocation relative to structural share: "
      f"{combined.get('enrichment_fp_vs_structural', 0.0):.2f}x random/structural = "
      f"{combined['full_random']['combined_node_hours_share'] / combined['structural_combined_share']:.2f}x).")
    A("")

    OUT_MD.write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()
