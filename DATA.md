# Data Access

## Frontier Job Dataset

The analysis uses the OLCF Frontier job dataset (completed job info and per-node
power/temperature telemetry) from Oak Ridge Leadership Computing Facility.

**Job-level metadata** (`frontier-completed-job-info.parquet`):
Available through the OLCF Open Data Initiative.
DOI: 10.13139/OLCF/3013979
Dataset page: https://doi.ccs.ornl.gov/dataset/2cfa2292-3f9d-549c-b2d2-c9aff1557218
Request access at: https://www.olcf.ornl.gov/

**Per-node telemetry** (power and temperature at 2-second resolution):
Available in the same OLCF dataset. The telemetry directory structure expected
by the scripts is:

```
<DATA_DIR>/
  frontier-completed-job-info.parquet
  job-telemetry/
    <date_dir>/
      <job_idx_zfill6>/
        <job_idx>-cleaned-power.parquet
```

## Setting the Data Path

All scripts that read raw Frontier data accept the path via the environment variable
`THERMALSHIFT_DATA_DIR`. Set it before running:

```bash
# bash / zsh
export THERMALSHIFT_DATA_DIR=/path/to/frontier/dataset

# PowerShell
$env:THERMALSHIFT_DATA_DIR = "C:\path\to\frontier\dataset"
```

## Derived Artifacts Included in This Repo

The following derived files are small enough to be included directly and are
sufficient to reproduce all final figures and validation results without the
raw dataset:

| File | Contents |
|------|----------|
| `artifacts/phase1/analysis/phase3a_fingerprint_2024.parquet` | Thermal fingerprints (FA_2024, 2,000 nodes) |
| `artifacts/phase1/analysis/phase3a_test_set.parquet` | 2,637 base test jobs |
| `artifacts/phase1/analysis/phase3b3f_results.json` | Full-cabinet power model results |
| `artifacts/phase1/analysis/phase3b_mc_results.json` | Monte Carlo final outputs (30 scenarios) |
| `artifacts/phase1/analysis/phase3b_mc_analysis.json` | Post-MC summary statistics |

Running `phase3b_mc_analysis.py`, `phase3b_mc_validate.py`, and `phase3b_figures.py`
requires only these included files (no raw dataset access needed).

Running `phase3b_mc.py` (to reproduce the Monte Carlo from scratch) additionally
requires the raw Frontier telemetry via `THERMALSHIFT_DATA_DIR`.
