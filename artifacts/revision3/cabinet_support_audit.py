"""
Round-3 Task D — Cabinet Support Audit.

Determine the exact support over which historical concurrent cabinet power
can be reconstructed from training job telemetry.

Outputs:
  artifacts/revision3/cabinet_support_audit.json

Plan ref: artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §D
Post-exposure label: designed after sc30-sc54 primary results observed.

IMPORTANT: This script reads job-level power telemetry. The telemetry
parquet paths must be set to the actual data location on this machine.
Edit DATA_DIR below before running.

All concurrent power values are labeled "observed reconstructed concurrent
cabinet power" to distinguish from the legacy job-contribution P99.
"""
import json
import pathlib
import numpy as np
from collections import defaultdict

ROOT    = pathlib.Path(__file__).parent.parent.parent
OUT_DIR = ROOT / "artifacts" / "revision3"

# ── DATA PATHS — edit before running ──────────────────────────────────────
# Expected: a parquet or CSV with columns:
#   job_id, cabinet, start_time (unix epoch or datetime), end_time, mean_power_kW, n_nodes
# This is the full 152,400-job training telemetry.
DATA_DIR = ROOT / "artifacts" / "revision1" / "results"
ENVELOPE_FILE = DATA_DIR / "cabinet_power_envelopes.json"

# ── Constants ──────────────────────────────────────────────────────────────
BIN_SIZE_HOURS = 1.0  # Bin size for concurrent power reconstruction

POST_EXPOSURE_LABEL = (
    "Post-exposure: designed after sc30-sc54 primary results observed. "
    "All values labeled 'observed reconstructed concurrent cabinet power'."
)


def compute_concurrent_power_bins(jobs_df, cabinet_col, start_col, end_col,
                                  power_col, bin_size_h=1.0):
    """
    For each cabinet, compute sum of concurrent job power in each time bin.
    Returns dict: cabinet_id -> array of (bin_start, concurrent_power_kW).
    All values labeled 'observed reconstructed concurrent cabinet power'.
    """
    raise NotImplementedError(
        "compute_concurrent_power_bins requires raw job telemetry parquet. "
        "Load the telemetry from the appropriate data source and implement "
        "the binning logic. See DATA_DIR configuration above."
    )


def main():
    print("[D] Cabinet Support Audit")
    print(f"    {POST_EXPOSURE_LABEL}")
    print()

    if not ENVELOPE_FILE.exists():
        print(f"    ERROR: {ENVELOPE_FILE} not found")
        return

    with open(ENVELOPE_FILE) as fh:
        env = json.load(fh)

    cabinets = list(env.get("per_cabinet_p99_kW_correct", {}).keys())
    n_cabinets = len(cabinets)

    output = {
        "script": "artifacts/revision3/cabinet_support_audit.py",
        "plan_ref": "artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §D",
        "post_exposure_label": POST_EXPOSURE_LABEL,
        "status": "STUB — requires raw job telemetry parquet",
        "n_cabinets_from_envelope": n_cabinets,
        "bin_size_hours": BIN_SIZE_HOURS,
        "terminology": "observed reconstructed concurrent cabinet power",
        "instructions": (
            "To complete this audit: "
            "(1) Load the full job telemetry with start_time, end_time, mean_power_kW, n_nodes, cabinet columns. "
            "(2) For each hourly bin and each cabinet, sum the power contributions of all jobs overlapping that bin. "
            "(3) Record: n_bins_with_jobs per cabinet, contiguous_blocks, support_hours, "
            "concurrent_job_distribution, concurrent_node_distribution. "
            "(4) Compute legacy_exceedance_fraction per cabinet (Task E). "
            "(5) Compute F2 and F3 P99 estimates per cabinet (Task F). "
            "All outputs must use the label 'observed reconstructed concurrent cabinet power'."
        ),
        "required_output_fields": [
            "collection_dates",
            "contiguous_blocks",
            "support_hours_per_cabinet",
            "concurrent_job_distribution",
            "concurrent_node_distribution",
            "fraction_bins_with_jobs"
        ],
        "task_e_output": {
            "legacy_exceedance_fraction_per_cabinet": "PENDING",
            "aggregate_exceedance_fraction": "PENDING",
            "median_exceedance_fraction": "PENDING",
            "iqr_exceedance_fraction": "PENDING",
            "p90_exceedance_fraction": "PENDING",
            "max_exceedance_fraction": "PENDING",
            "min_exceedance_fraction": "PENDING"
        }
    }

    out_path = OUT_DIR / "cabinet_support_audit.json"
    with open(out_path, "w") as fh:
        json.dump(output, fh, indent=2)
    print(f"[DONE] Written stub: {out_path}")
    print("       Complete this script when raw job telemetry is available.")


if __name__ == "__main__":
    main()
