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

The repository includes frozen simulation outputs at every analysis tier. No raw
Frontier telemetry is required to reproduce any analysis beyond fingerprint
derivation from scratch.

### Development analysis (Phase 3B)

| File | Contents |
|------|----------|
| `artifacts/phase1/analysis/phase3a_fingerprint_2024.parquet` | Thermal fingerprints (FA_2024, 2,000 nodes) |
| `artifacts/phase1/analysis/phase3a_test_set.parquet` | 2,637 base test jobs |
| `artifacts/phase1/analysis/phase3b3f_results.json` | Full-cabinet power model results |
| `artifacts/phase1/analysis/phase3b_mc_results.json` | Monte Carlo outputs (30 development scenarios) |
| `artifacts/phase1/analysis/phase3b_mc_analysis.json` | Post-MC summary statistics |

Running `phase3b_mc_analysis.py`, `phase3b_mc_validate.py`, and `phase3b_figures.py`
reproduces the development-era (Phase 3B) analysis without raw dataset access.
Running `phase3b_mc.py` to regenerate the Monte Carlo from scratch requires
`THERMALSHIFT_DATA_DIR`.

### Primary challenge experiment (R2, sc30–54) — preregistered

| File | Contents |
|------|----------|
| `artifacts/revision2/results/gate_f_sc30-54_all_r2challenge_merged.json` | Merged raw simulation outputs, all 25 challenge scenarios |
| `artifacts/revision2/challenge_analysis.json` | Frozen analysis output (8 comparisons, bootstrap CIs) |
| `artifacts/revision2/sensitivity_cabinet_scale.json` | E1 cabinet-scale sensitivity outputs |
| `artifacts/revision2/sensitivity_loo_beta.json` | E2 beta sensitivity outputs |

### Corrected-reference analyses (C1/C2) — primary claims source

| File | Contents |
|------|----------|
| `artifacts/manuscript_completion/results/gate_f_sc5-29_all.json` | C1 raw: sc5–sc29, all ratios, corrected reference |
| `artifacts/manuscript_completion/results/gate_f_sc30-54_1p25_c2manuscript.json` | C2 raw: sc30–sc54, r=1.25, corrected reference |
| `artifacts/manuscript_completion/results/c1_correctedref_analysis.json` | C1 frozen analysis output |
| `artifacts/manuscript_completion/results/c2_correctedref_analysis.json` | C2 frozen analysis output |

### Structural position analysis (Round-7, PositionGroupHash) — post-exposure corrective robustness

| File | Contents |
|------|----------|
| `artifacts/manuscript_completion/results/gate_f_sc30-54_1p0_1p25_c7primary.json` | C7 raw: sc30–54, canonical beta |
| `artifacts/manuscript_completion/results/c7primary_analysis.json` | C7 frozen analysis output |

### Gate F held-out evaluation (revision1) — preregistered held-out design

| File | Contents |
|------|----------|
| `artifacts/revision1/results/gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json` | Gate F raw: sc5–sc29, multiple ratios |
| `artifacts/revision1/results/gate_f_heldout_analysis_E1.json` | Gate F frozen analysis output |
