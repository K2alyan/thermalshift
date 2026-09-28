# ThermalOps Feasibility Investigation

**Date:** 2026-09-23  
**Status:** Pre-implementation research. No code has been written.  
**Verdict:** GO — REFRAME (see Section 13)

> **Note:** Sections 1 and 2 incorporate direct inspection of the Frontier README and 100-job sample dataset. Empirical statistics in Section 2 are measured from real data, not inferred.

---

## Table of Contents

1. [Frontier Dataset Investigation](#1-frontier-dataset-investigation)
2. [Empirical Data Verification](#2-empirical-data-verification)
3. [Thermal Forecasting Feasibility](#3-thermal-forecasting-feasibility)
4. [Physics-Based Modeling](#4-physics-based-modeling)
5. [Causal and Root-Cause Claims](#5-causal-and-root-cause-claims)
6. [Complementary Public Datasets](#6-complementary-public-datasets)
7. [GitHub Prior Art](#7-github-prior-art)
8. [Literature Review](#8-literature-review)
9. [Candidate Scientific Questions](#9-candidate-scientific-questions)
10. [Modeling Approaches](#10-modeling-approaches)
11. [Senior Applied Scientist Perspective](#11-senior-applied-scientist-perspective)
12. [Arguments Against the Project](#12-arguments-against-the-project)
13. [Alternative Questions from the Data](#13-alternative-questions-from-the-data)
14. [Final Recommendation](#14-final-recommendation)

---

## 1. Frontier Dataset Investigation

### Identity

| Field | Value |
|-------|-------|
| Title | Frontier Job-Centric Telemetry Dataset |
| DOI | 10.13139/OLCF/3013979 |
| Authors | Leah Huk, Rachel Palumbo, Woong Shin, Tim Osborne, Ryan Adamson, Michael Sandoval, Corwin Lester (ORNL) |
| Release date | September 2, 2026 |
| Data collection period | 2024-01-17 to 2025-12-31 |
| Associated paper | "Constructing a Job-Centric Frontier Telemetry Dataset to Accelerate HPC Operations, Systems, and Energy Research," SC26, November 17, 2026 |

### Access and License

- **Download:** Globus file transfer from ORNL Constellation. Path confirmed: `/gen101/world-shared/doi-data/OLCF/202609/10.13139_OLCF_3013979/frontier-job-centric-telemetry-dataset/`
- **License:** "None, data is free to use and reuse." Confirmed open from README.
- **Format:** Apache Parquet (Snappy-compressed). Tools: pyarrow, polars, dask.
- **Total size:** 571 GB (job-telemetry directory); 39 MB (job-info file); 56 MB (100-job sample)

### File Structure

```
root/
├── frontier-completed-job-info.parquet       # 39 MB, 152,400 rows, 26 columns
├── sample-data.tar.gz                        # 56 MB, 100 random jobs
├── figures/cleaning_process.drawio.png
├── notebooks/
│   ├── dataset-explorer.ipynb
│   ├── paper-figures.ipynb
│   └── requirements.txt
└── job-telemetry/                            # 571 GB total
    └── YYYY-MM-DD/
        └── {job_idx}/
            ├── {job_idx}-raw-node-power.parquet       # 2s bins, per-node total power
            ├── {job_idx}-raw-device-power.parquet     # 15s bins, per CPU + GPU0-3 per node
            ├── {job_idx}-raw-device-temperature.parquet  # 60s bins, per CPU + GCD0-7 per node
            ├── {job_idx}-cleaned-power.parquet        # joined 1s bins, forward-filled
            ├── {job_idx}-cleaned-temperature.parquet  # 60s bins, interpolated
            ├── {job_idx}-data-stats-power.parquet
            ├── {job_idx}-data-stats-temperature.parquet
            ├── {job_idx}-{txBW,rxBW,rxCongestion,idle}-cassini.parquet  # when available
            └── {job_idx}-data-stats-interconnect.parquet
```

### Confirmed Data Dictionary

**Sampling rates (confirmed from README):**

| Metric type | Source | Resolution |
|-------------|--------|------------|
| Node total power | HPCM Cray PM | 2 seconds |
| CPU power + GPU0-3 power | HPCM Cray PM | 15 seconds |
| CPU temperature + GCD0-7 temperature | HPCM Cray PM | **60 seconds** |
| Network (txBW, rxBW, rxCongestion, idle) | Slingshot/Cassini | 60 seconds (available from June 2025 only) |

**Per-node temperature variables (confirmed present):**

| Column name | Description |
|-------------|-------------|
| `{hostname}_cpu` | CPU socket temperature (°C) — 1 per node |
| `{hostname}_gpu0_gcd0` | GPU 0, Compute Die 0 temperature (°C) |
| `{hostname}_gpu0_gcd1` | GPU 0, Compute Die 1 temperature (°C) |
| `{hostname}_gpu1_gcd2` | GPU 1, Compute Die 2 temperature (°C) |
| `{hostname}_gpu1_gcd3` | GPU 1, Compute Die 3 temperature (°C) |
| `{hostname}_gpu2_gcd4` | GPU 2, Compute Die 4 temperature (°C) |
| `{hostname}_gpu2_gcd5` | GPU 2, Compute Die 5 temperature (°C) |
| `{hostname}_gpu3_gcd6` | GPU 3, Compute Die 6 temperature (°C) |
| `{hostname}_gpu3_gcd7` | GPU 3, Compute Die 7 temperature (°C) |

9 temperature channels per node (1 CPU + 8 GCDs). Each AMD MI250X GPU contains 2 GCDs; there are 4 GPUs per node.

**Per-node power variables (confirmed present):**

| Column name | Description |
|-------------|-------------|
| `{hostname}_node` | Total node power (W), 2-second bins |
| `{hostname}_cpu` | CPU package power (W), 15-second bins |
| `{hostname}_gpu0` | GPU 0 power (W), 15-second bins |
| `{hostname}_gpu1` | GPU 1 power (W), 15-second bins |
| `{hostname}_gpu2` | GPU 2 power (W), 15-second bins |
| `{hostname}_gpu3` | GPU 3 power (W), 15-second bins |

**Cleaned power file also includes aggregates across all nodes:**

`node_agg_{total,mean,min,max}_power`, `cpu_agg_{total,mean,min,max}_power`, `gpu_agg_{total,mean,min,max}_power`

**Job-level metadata (frontier-completed-job-info.parquet, 26 columns confirmed):**

| Column | Type | Description |
|--------|------|-------------|
| `job_idx` | String | Row-index identifier (Slurm jobid redacted) |
| `node_count` | Int64 | Number of nodes allocated |
| `submit/start/end_time` | Datetime UTC | Scheduler timestamps |
| `run_time` | Int64 | Elapsed seconds in RUNNING state |
| `completion_state` | String | COMPLETED, CANCELLED, or TIMEOUT |
| `gpu_enabled` | String | 'true'/'false'/null (null if before June 2025) |
| `peak_power` / `mean_power` | Float64 | Aggregated over all nodes [W] |
| `user_id` / `project_id` | String | Anonymized (incremental integer encoding) |
| `project_prefix` | String | Anonymized category prefix (preserves scientific domain grouping) |
| `host_list` | List[String] | Node hostnames |
| `node_list` | List[String] | Node xnames (geolocation: rack/chassis/slot/board/node) |
| `interconnect_exists` | String | 'true'/'false' |
| `queue` | String | SLURM partition |

**Confirmed absent:**

| Variable | Status |
|----------|--------|
| Coolant / inlet / outlet temperature | Not per-node; only in separate facility dataset |
| CPU frequency | Not collected |
| GPU utilization (time series) | Not present as time series; only aggregated `gpu_enabled` boolean |
| GPU memory utilization (time series) | Not present as time series |
| Fan speed | Not applicable (direct liquid cooling) |
| Throttling events / hardware alarms / failures | Not in this dataset |
| Physical CPU/GPU frequency | Not collected |

### Known Data Quality Issues

1. **Temperature is at 60-second resolution** — the coarsest of all metrics. This constrains RC model identification (requires thermal time constants well above 60 seconds).
2. **Network data only from June 2025** — `interconnect_exists` is null or false for 2024 jobs.
3. **`gpu_enabled` is null for pre-June-2025 jobs** (32 of 100 sample jobs had null; approximately proportional in the full dataset).
4. **Sample is 6.8% of total jobs**, biased toward leadership-class jobs (large node count).
5. **Node xnames provide physical rack/chassis/slot location**, enabling spatial topology analysis.
6. **Power thresholds for filtering**: CPU 20–310W, GPU 50–615W, node 300–3200W. Values outside these are set to null before cleaning.

---

## 2. Empirical Data Verification

**Source:** Direct inspection of 100-job sample dataset (`sample-data.tar.gz`). All statistics are measured, not inferred.

### Temperature Distributions

| Statistic | CPU Temperature (°C) | GCD Temperature (°C) |
|-----------|---------------------|---------------------|
| N observations | 203,743 | 1,629,871 |
| Min | 34.8 | 28.0 |
| p5 | 41.8 | 38.0 |
| p25 | 49.2 | 42.0 |
| **Median** | **51.9** | **47.0** |
| Mean | 51.4 | 48.1 |
| p75 | 54.5 | 52.0 |
| p95 | 57.4 | 63.0 |
| p99 | 59.4 | 71.0 |
| **Max** | **64.5** | **86.0** |
| Std | 4.5 | 7.8 |

**GCD temperature exceedance:**

| Threshold | Count | Fraction |
|-----------|-------|----------|
| > 70°C | 18,620 | 1.1% |
| > 80°C | 143 | 0.01% |
| > 90°C | 0 | 0.0% |
| > 100°C | 0 | 0.0% |

The AMD MI250X thermal design maximum junction temperature is ~110°C. The maximum observed GCD temperature in 1.6 million observations across 100 diverse jobs is **86°C** — 24°C below the hardware limit, and in the >80°C band for only 143 observations (0.01%). No true thermal excursion events appear in the sample.

### Power Distributions

| Statistic | Node Agg Mean Power (W) | GPU Agg Mean Power (W) |
|-----------|------------------------|------------------------|
| N observations | 369,783 | 369,783 |
| Min | 414 | 79 |
| p25 | 679 | 90 |
| Median | 1,090 | 171 |
| Mean | 1,188 | 214 |
| p75 | 1,598 | 303 |
| p95 | 2,377 | 474 |
| Max | 2,871 | 563 |
| Std | 609 | 130 |

Node power spans 414–2871W (7× range). GPU power spans 79–563W (7× range). This is substantial variability — modeling power-to-temperature is a well-conditioned regression problem.

### Power-Temperature Correlation

Per-job mean GPU power vs. per-job mean GCD temperature: **r = 0.971** (N=100 jobs).

This is extremely high. It confirms that GPU power is the dominant driver of GCD temperature at the job level, and that a power-conditioned thermal prediction is physically well-motivated. The remaining 6% of variance (1 - 0.971²) captures workload-specific effects, inter-node variability, cooling state, and sensor noise.

### Within-Job Temperature Dynamics

| Metric | CPU | GCD |
|--------|-----|-----|
| Median within-job std | 3.5°C | 5.1°C |
| p95 within-job std | 6.3°C | 9.6°C |
| Max within-job std | 7.9°C | 14.2°C |
| Median within-job range | — | 13.0°C |
| p95 within-job range | — | 22.0°C |
| Max within-job range | — | 37.0°C |

Temperature varies meaningfully within jobs. A median job shows a 13°C GCD range — large enough to learn from. The 22°C p95 range and 37°C maximum range demonstrate that workload transitions produce measurable thermal responses.

### Thermal Ramp (Start vs. End of Job)

| Metric | Value |
|--------|-------|
| Jobs with ramp data (≥4 temp obs) | 92 of 100 |
| Mean ramp (end − start) | +2.0°C |
| Median ramp | +0.6°C |
| p5 ramp | −2.9°C |
| p95 ramp | +11.8°C |
| Jobs with ramp > 5°C | 15 (16%) |
| Jobs with ramp > 10°C | 10 (11%) |

Most jobs show small end-to-start ramps, suggesting either: (a) the system reaches thermal steady state quickly relative to the 60-second sampling resolution, (b) the GCD thermal time constant is shorter than the bin width, or (c) jobs start and end at similar workload intensity. The 10–11% of jobs with >10°C ramps are where physics-based transient modeling has the most to offer.

### Scheduler Metadata (Sample)

- **Jobs:** 59 COMPLETED, 34 TIMEOUT, 7 CANCELLED
- **GPU-enabled:** 50 true, 18 false, 32 null
- **Queues:** batch-normal (87), batch-debug (9), batch-spi-normal (2), extended-normal (2)
- **Top project prefixes:** VNY (23), OHF (7), FZN (7), LYB (7) — anonymized but clusterable as workload proxies
- **Node xname format:** `x{rack}c{chassis}s{slot}b{board}n{node}` — full 3D topology derivable

### Node Reuse (for Fixed-Effect Modeling)

In the 100-job sample:
- Unique nodes appearing: 4,874
- Nodes with ≥2 jobs: 1,269 (26%)
- Nodes with ≥3 jobs: 189
- Max jobs per node: 5
- Median jobs per node: 1

In the full 152,400-job dataset, node reuse will be substantially higher — many nodes will appear in dozens to hundreds of jobs, enabling robust per-node thermal baseline estimation.

---

## 3. Thermal Forecasting Feasibility

### Revised Assessment After Data Inspection

The original proposal targeted binary prediction of "thermal excursions" near hardware limits. The empirical data eliminates this framing:

**There are no thermal excursions in this dataset in the sense of approaching hardware limits.** The highest observed GCD temperature is 86°C in 1.6M observations, 24°C below the ~110°C MI250X thermal design maximum. The system's direct liquid cooling is sufficiently effective that GCDs never approach thermal throttling in the observed sample.

This is not fatal to the project. It does require a scientifically honest reframing.

### What Is Scientifically Defensible

**Target 1 — Workload-conditioned temperature estimation (regression):**
```
T_predicted(t) = f(power(t), workload_class, job_phase, node_id)
residual(t) = T_observed(t) - T_predicted(t)
```
Well-defined, measurable, and interpretable. Power-temperature correlation r=0.971 means residuals are small but structured — they capture cooling system effects, node-to-node differences, and workload-specific thermal inefficiencies.

**Target 2 — Node thermal anomaly scoring:**
Nodes whose temperature residuals deviate systematically from peers on equivalent workloads. This is always observable, requires no rare events, and is directly operationally useful.

**Target 3 — Per-node thermal characterization:**
What is each node's effective thermal resistance and time constant? How do these vary with GPU generation, rack location, or cooling zone? Changes in these parameters over time (across jobs) identify emerging cooling degradation.

### Defining "Abnormal" Without Hardware-Limit Events

| Definition | Scientific validity | Feasibility |
|------------|---------------------|-------------|
| Temperature > hardware-limit threshold | Strong physically | No events in data — cannot use |
| Temperature > workload-conditioned baseline + Nσ | Strong statistically | Valid — this is the residual approach |
| Temperature > peer-node distribution at same workload | Strong operationally | Valid — identifies hot nodes relative to peers |
| Within-job temperature variance exceeds normal for job type | Moderate | Valid — captures cooling state changes mid-job |
| Thermal resistance change across sequential jobs | Strong physically | Valid — parameter drift detection |

### Are Seasonal or Workload Effects Present?

The r=0.971 power-temperature correlation strongly suggests workload is the dominant driver. The 6% unexplained variance likely captures:
- Node-to-node cooling differences (rack location, chassis, CDU health)
- Workload thermal efficiency (FLOPS/Watt → heat/FLOPS ratio varies by application)
- Long-term cooling state drift
- Sensor noise (~1°C for Cray PM temperature sensors)

**Conclusion:** The data supports thermal modeling and workload-conditioned anomaly detection. The target must be shifted from binary excursion classification to continuous anomaly scoring relative to expected thermal behavior. This is more scientifically rigorous, not a downgrade.

---

## 4. Physics-Based Modeling

### The RC Thermal Model

Standard first-order RC model for a compute node:

```
C · dT/dt = P - (T - T_cool) / R
```

Steady state: `T_ss = T_cool + R·P`  
Time constant: `τ = R·C`

### Confirmed Constraints from Data Inspection

**T_cool is NOT measured per node.** This was known before; confirmed.

**Temperature is sampled at 60-second bins.** This is the most important constraint for RC model identification:
- For a thermal time constant τ = 120s (2 minutes), the 60-second sampling captures one point per half-time-constant — workable.
- For τ = 60s or less, the 60-second sampling misses most of the transient — RC identification becomes unreliable.
- The GlassChip paper found τ = 116–394s for HPC nodes. At 116s minimum, 60-second sampling captures the transient adequately but marginally.
- The thermal ramp data (median 0.6°C end-to-start over typical job duration) suggests that either τ << job duration (system reaches steady state quickly) or τ is long enough that ramp is still in progress at job end.

**Power is sampled at 2s (node) and 15s (device).** Power resolution is substantially finer than temperature. This creates an asymmetry: we can track power at 2-second resolution and use it as input, but temperature feedback is only 60-second resolution.

### What Can and Cannot Be Estimated

| Analysis | Feasibility | Method | Constraint |
|----------|-------------|--------|------------|
| Steady-state P→T relationship | Yes, clean | Linear regression T vs P per node | Valid even without T_cool if T_cool is approximately constant |
| Thermal time constant τ | Yes, with caveats | Fit exponential to job-start temperature ramp | 60s resolution limits precision; only 11% of jobs have >10°C ramp to fit to |
| Effective thermal resistance R_eff | Yes with approximation | R_eff = (T_ss - T_cool_est)/P; T_cool_est from idle periods | Accuracy bounded by T_cool approximation |
| T_cool estimation | Partial | From idle GCD temperatures (P≈0 → T≈T_cool) | Idle observations required; quality depends on how often nodes go idle |
| Thermal capacitance C | Yes with caveats | C = τ/R_eff | Accumulates uncertainty from both |
| Absolute T_cool (per CDU) | No | Not measured per node | Requires facility dataset (10-min resolution) — too coarse for transient analysis |

### Justification for Treating T_cool as Approximately Constant

Frontier's direct liquid cooling achieves PUE 1.03–1.08 year-round, with coolant supply temperature held near 32°C. The facility-level waste heat dataset shows coolant temperature varying in the 30–38°C range over a full year at 10-minute resolution. This ~8°C annual variation appears constant at the 60-second timescale of thermal telemetry. Therefore:

- At any single measurement session, T_cool error from approximating it as constant is ≤±4°C (half of annual range)
- Within a single job (duration typically 10–6000 seconds), T_cool variation is negligible
- The steady-state approximation `T_ss = T_cool_baseline + R_eff·P` is defensible with stated uncertainty bounds

**Scientific requirement:** Any paper claiming R_eff estimates must state: "T_cool was estimated from idle node temperatures; uncertainty in T_cool introduces ±X°C uncertainty in R_eff estimates, propagated as follows..."

---

## 5. Causal and Root-Cause Claims

### Classification Framework

**A** — Directly supported by observed variables  
**B** — Plausible but not identifiable from this observational data alone  
**C** — Unsupported

### Claims Classified

| Claim | Class | Reasoning |
|-------|-------|-----------|
| GPU power drives GCD temperature (observed correlation) | A | r=0.971 in sample. Directly measurable. |
| Workload type (project_prefix) is associated with different power distributions | A | project_prefix is observed; power is observed; association is directly measurable |
| High-power GPU jobs produce higher GCD temperatures than low-power jobs | A | Both observed; comparison is valid |
| Cooling degradation causes a node's temperature to rise relative to its peers at similar power | B | Plausible. Node-relative residual analysis is feasible. But without cooling metrics, we cannot separate degraded cooling from other explanations (bad sensor, different rack location, etc.) |
| Neighbor load in the same chassis affects a node's temperature | B | xname topology available; node power available; correlation analysis feasible. But confounded by job co-allocation patterns |
| Reducing GPU power by 10% will reduce GCD temperature by Y°C | B | The RC model gives a physics-based prediction under stated assumptions. NOT a measured intervention effect |
| A specific project_prefix causes higher thermal stress | B | Association measurable; causation not identifiable without controlling for all confounders |
| Sensor fault causes an apparent temperature anomaly | B | No redundant sensors to cross-validate; cannot be distinguished from true thermal event from data alone |

### Firm Constraints

The dataset is **observational with no recorded interventions** (no power cap changes, no cooling adjustments, no controlled workload assignments). Therefore:

- All statistical findings are associations, not causal effects
- "What-if" scenarios (reduce power by X%) are physics-model predictions under stated assumptions, not empirical causal estimates
- "Root cause" language should not appear in the paper; use "associated factor" or "correlated predictor"

---

## 6. Complementary Public Datasets

All datasets listed here are confirmed accessible without NDA.

### Tier 1

**ORNL Summit Power and Thermal Dataset**
- DOI: 10.13139/OLCF/1861393 | GitHub: github.com/at-aaims/summit_power_and_thermal_data
- License: CC-BY 4.0 | Size: 612 GB (10s resolution), 120 GB (1-min)
- Variables: Per-node AC input power; per-CPU power (×2); per-GPU power (×6 V100s); per-CPU core temperatures (23 cores each); per-GPU core and memory temperatures (×6)
- Nodes: 4,626 Summit nodes (IBM POWER9 + NVIDIA V100)
- Resolution: 10-second means — **finer than Frontier temperature (60s)**
- Duration: Five month-long segments 2020–2022
- Relevance: **Best candidate for cross-system validation.** All variables confirmed. Per-GPU temperature confirmed. Better temporal resolution than Frontier. SC21 Best Paper established this dataset — robust and well-characterized.

**M100 ExaData — Marconi100**
- DOI: 10.5281/zenodo.10533504 | License: CC-BY 4.0 | Size: 18.7 TB raw
- Variables: CPU temps, GPU temps, fan speed, liquid cooling loop temps, power, SLURM metadata, fault logs
- Nodes: 980+ IBM AC922 (V100 GPUs, POWER9 CPUs) | Duration: 2.5 years
- Relevance: **Has inlet/outlet cooling temperatures** — enables full RC model validation (T_cool is known). The only major public HPC dataset where both T_in and T_out per cooling loop are measured. Third system for generalization.

**HazardNet Dataset — Marconi A2**
- DOI: 10.5281/zenodo.10050368 | License: CC-BY 4.0 | Size: 1 GB
- Variables: Inlet temperature, outlet temperature, node power — 3,312 nodes, full 2019
- Relevance: **Smallest and most convenient dataset with measured T_cool.** Ideal for validating RC model with known coolant temperature, then comparing to Frontier results where T_cool is estimated.

**Frontier Waste Heat Recovery Dataset**
- DOI: 10.6084/m9.figshare.24391240 | License: CC-BY 4.0 | Size: <1 GB
- Variables: Facility-level coolant supply/return temperature, flow rate, power, PUE — 10-minute bins, full year 2023
- Relevance: **Same machine as the job-centric dataset.** Facility-level T_cool can improve RC model estimates with the caveat that 10-minute resolution requires interpolation to 60-second job telemetry.

### Tier 2

**MIT Supercloud** — s3://mit-supercloud-dataset/ | License: Open | Size: 2.1 TB  
GPU temp + power at 100 ms resolution. 224 V100 nodes. Useful for validating thermal time constant estimates at fine temporal resolution.

**PM100 — Marconi100 Job-Level Power** — DOI: 10.5281/zenodo.8129258 | CC-BY 4.0 | 106 MB  
231,238 jobs, 20-second resolution, per-job power. No temperature. Useful for workload power modeling validation.

### Not Recommended

Google 2019 (no per-node thermal), Alibaba (no power/temp), NERSC Cori (no per-node temp, 1-hour resolution), Azure (utilization only), Meta (no public telemetry dataset).

---

## 7. GitHub Prior Art

### Critical Repositories

**MSKazemi/HazardNet** — github.com/MSKazemi/HazardNet | Apache-2.0 | Recent  
Closest prior art to ThermalOps. Binary thermal hazard prediction on Marconi A2 with TCN and LSTM. F1 0.87–0.98. No workload conditioning, no calibrated uncertainty. ThermalOps must explicitly differentiate.

**Azeez404/GlassChip** — github.com/Azeez404/GlassChip | MIT | 2025  
RC thermal model identification on Summit and Marconi100 data. Demonstrates τ = 116–394s depending on data quality. Directly defines the physics baseline methodology for ThermalOps.

**ExaDigiT/RAPS** — github.com/ExaDigiT/RAPS | Apache-2.0 | Active  
Workload trace replay simulator for Frontier, Marconi100, and others. Power estimation from SLURM traces. Useful for generating synthetic workload scenarios.

**pascme05/ThermoPINN** — github.com/pascme05/ThermoPINN | MIT | Active  
RC + LSTM PINN with physics regularization loss. Motor thermal data but architecture directly portable to HPC node thermal modeling. ~50–60% MSE reduction vs. pure LSTM.

**aangelopoulos/conformal-time-series** — github.com/aangelopoulos/conformal-time-series | MIT | Active  
Conformal PID control for non-stationary time series. Best choice for calibrated prediction intervals on drifting thermal telemetry.

**OliverHennhoefer/nonconform** — github.com/OliverHennhoefer/nonconform | BSD-3 | Active  
Conformal anomaly detection for streaming data with martingale-based sequential monitoring and FDR control. Most production-ready for calibrated HPC thermal alerting.

**at-aaims/summit_power_and_thermal_data** — github.com/at-aaims/summit_power_and_thermal_data | CC-BY 4.0  
Companion notebooks to Summit SC21 paper. Data loading, Dask/Parquet toolchain, analysis patterns directly applicable.

**ExaDigiT/POWER9CSM** — code.ornl.gov/exadigit/datacenterCoolingModel | Apache-2.0  
Modelica FMU cooling models for Frontier, Summit, Marconi100. Most authoritative physics model of Frontier's cooling system. If simulation-generated T_cool is needed, this is the source.

All critical repositories use MIT, Apache-2.0, BSD-3, or CC-BY. No GPL contamination risk.

---

## 8. Literature Review

### Papers That Directly Define the Competitive Landscape

**HazardNet (Seyedkazemi Ardebili et al., FGCS 2024)**  
Thermal hazard prediction on Marconi A2 (3,312 nodes, inlet/outlet temp + power) using TCN/LSTM. F1 0.87 (causality-enforced). Dataset on Zenodo. **This is the primary competing paper.** Gaps vs. ThermalOps: no workload conditioning, no calibrated uncertainty, different system (CINECA, not ORNL), older architecture.

**RUAD (Molan et al., arXiv:2208.13169)**  
Unsupervised LSTM autoencoder on Marconi100. AUC 0.767. Mixed anomaly types (not thermal-specific). Required baseline comparison.

**Revealing Power, Energy and Thermal Dynamics of Summit (Shin et al., SC21 Best Paper)**  
First full-system thermal characterization of a pre-exascale machine. Descriptive only. Companion dataset (OSTI 1861393) is Tier 1 for ThermalOps.

**Robust Identification of Thermal Models for HPC (Pittino et al., 2020)**  
RC/state-space model identification from production HPC data. <1°C mean error with careful trace selection. CPU-era HPC. Direct methodology reference for ThermalOps physics baseline.

**ThermoCast (Li et al., ACM KDD 2011)**  
Cyber-physical state-space thermal model predicting alarms 4.2 minutes ahead. 15-year-old technology, airflow sensors not BMC telemetry, no GPU workloads. Gap in the literature remains open for modern HPC — ThermalOps fills it.

**SeT-Diff (Esposito et al., ACM Computing Frontiers 2026)**  
Diffusion-based foundation model for HPC telemetry. MAE 0.033 for thermal inference on Marconi100. Most advanced published thermal ML for HPC. No workload conditioning, no uncertainty, no excursion detection. Very recent — establishes the ceiling for the field.

**Toward Physics-Informed ML for Data Center Operations (Wang et al., arXiv:2505.19414, 2025)**  
PIML for facility-level HVAC control. 5% error vs. 7–9% for MLP. Facility level, not node level. No uncertainty.

**PI-DLinear for GPU Power (AlShaikh Saleh et al., arXiv:2605.04074, 2026)**  
RC thermal network embedded in DLinear for GPU power forecasting. MSE improvement 0.78–39%. Targets power, not temperature anomaly, no job context. Closest to ThermalOps method.

**Generic and ML Workloads in HPC (Chu et al., ICPADS 2024)**  
Statistical characterization showing ML training jobs cause GPU thermal limit hits significantly more than generic MPI jobs. No predictor built. This is ThermalOps's primary "motivation" citation.

**Adaptive Conformal Anomaly Detection (Martinez Gil et al., ICLR 2026)**  
Conformal prediction bounds for time-series anomaly detection. No HPC evaluation. Establishes ThermalOps's uncertainty methodology.

**Federated Transfer Learning for HPC Anomaly Detection (Farooq et al., EAAI 2025)**  
FL+TL on Marconi100. F1 0.867, AUC 0.808. Not thermal-specific.

### Gap Analysis

| Sub-problem | Status |
|-------------|--------|
| Thermal prediction from BMC telemetry | Solved on Marconi (HazardNet, SeT-Diff) — not solved on Frontier |
| Workload-conditioned thermal anomaly detection | **Open everywhere** |
| Calibrated conformal uncertainty for HPC thermal | **Open everywhere** |
| Physics-informed hybrid for GPU-era HPC | **Open** — Pittino (2020) was CPU-era |
| Cross-system thermal model generalization | **Open everywhere** |
| Thermal analysis on Frontier node telemetry | **Open** — dataset released 2026-09-02, no published ML work |

The Bologna/CINECA group has saturated the Marconi100 niche with 15+ papers. ThermalOps on Frontier occupies genuinely unexplored territory.

---

## 9. Candidate Scientific Questions

Scale: 1–5 per dimension (higher is better; for "Risk of Overclaiming" lower is better).

### Q1: Can future GCD temperature be forecast from power and workload telemetry?

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Scientific validity | 5 | Well-posed regression; GCD temp confirmed present |
| Novelty | 3 | Thermal forecasting has been done; Frontier + job metadata is new |
| Dataset support | 5 | Power (15s) and GCD temp (60s) both confirmed present; project_prefix as workload proxy |
| Evaluation quality | 4 | RMSE/MAE; temporal split validation; compare to persistence |
| Difficulty | 3 | Supervised regression |
| Real infrastructure relevance | 4 | Useful for capacity planning |
| Senior Applied Scientist relevance | 3 | Needs depth to be interesting |
| Compelling visuals | 3 | Prediction vs. actual time series |
| Risk of overclaiming | 1 (good) | Regression results are bounded |
| **Total** | **31/45** | Necessary component, insufficient alone |

### Q2: Can abnormal thermal behavior be detected after conditioning on workload and power?

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Scientific validity | 5 | Workload-conditioned residual is rigorously defined |
| Novelty | 4 | No paper uses job scheduler features for conditional HPC thermal anomaly detection |
| Dataset support | 5 | All needed variables confirmed: power, GCD temp, project_prefix, node_count, queue |
| Evaluation quality | 3 | No labeled anomalies; proxy labels or comparative retrospective validation |
| Difficulty | 4 | Conditional distribution estimation + anomaly scoring |
| Real infrastructure relevance | 5 | Identifies hot nodes without false alarms from expected high-power heat |
| Senior Applied Scientist relevance | 5 | Requires physical judgment in defining "normal" |
| Compelling visuals | 4 | Residual heatmaps, anomaly rank plots, node fingerprint charts |
| Risk of overclaiming | 3 | "Anomaly" definition requires care; no confirmed labeled events |
| **Total** | **38/45** | Strong core question; must be primary |

### Q3: Can a physics-informed RC model compete with black-box ML for temperature prediction?

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Scientific validity | 5 | Direct comparison is well-defined |
| Novelty | 4 | No published RC identification result for AMD MI250X GPU nodes |
| Dataset support | 3 | T_cool missing; 60s resolution limits τ estimation precision; ~11% of jobs show usable ramps |
| Evaluation quality | 5 | RMSE comparison; parameter distributions; AIC |
| Difficulty | 4 | RC identification requires implementation care |
| Real infrastructure relevance | 5 | Interpretable models preferred in operations |
| Senior Applied Scientist relevance | 5 | Demonstrates physical reasoning over ML defaults |
| Compelling visuals | 4 | τ distribution across 9k+ nodes; R_eff node map |
| Risk of overclaiming | 2 (good) | Bounded claims about a specific model |
| **Total** | **37/45** | Essential component; validates physics understanding |

### Q4: Can a hybrid physics + ML model outperform either independently?

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Scientific validity | 5 | Well-defined ablation; clean null hypothesis |
| Novelty | 5 | No published hybrid physics+ML thermal predictor for GPU-era HPC nodes |
| Dataset support | 4 | Power and GCD temp confirmed; T_cool approximation is manageable |
| Evaluation quality | 5 | Three-way ablation: physics-only / ML-only / hybrid |
| Difficulty | 4 | Residual hybrid is tractable; PINN variant is ambitious |
| Real infrastructure relevance | 5 | Best of both worlds |
| Senior Applied Scientist relevance | 5 | Integrating domain knowledge with ML is the defining senior skill |
| Compelling visuals | 4 | Ablation table; gain-over-baseline chart; learned vs. physical parameter comparison |
| Risk of overclaiming | 3 | Hybrid gain can be marginal; must be honest |
| **Total** | **40/45** | Core scientific contribution |

### Q5: Can models trained on one HPC system generalize to another?

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Scientific validity | 5 | Generalization is a fundamental scientific question |
| Novelty | 5 | No published cross-system HPC thermal generalization study |
| Dataset support | 5 | Frontier (AMD MI250X, confirmed) + Summit (NVIDIA V100, confirmed) + Marconi100 (V100, confirmed) |
| Evaluation quality | 5 | Train on Frontier, test on Summit and Marconi100 — clear transfer gap metric |
| Difficulty | 4 | Architectural differences require feature alignment thinking |
| Real infrastructure relevance | 5 | Critical for operators adopting models on new systems |
| Senior Applied Scientist relevance | 5 | Distribution shift thinking is senior-level |
| Compelling visuals | 5 | Cross-system performance table; architecture factor comparison |
| Risk of overclaiming | 3 | Must clearly articulate what features transfer and why |
| **Total** | **42/45** | Strongest single question; primary novel contribution if executed |

### Q6: Can calibrated uncertainty identify when thermal predictions should not be trusted?

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Scientific validity | 5 | Conformal coverage guarantees are mathematically proven |
| Novelty | 5 | No published paper applies conformal prediction to HPC thermal telemetry |
| Dataset support | 4 | Can be applied post-hoc to any predictor |
| Evaluation quality | 5 | Coverage plots, ECE, Winkler score — all well-defined |
| Difficulty | 3 | Conformal implementation is well-understood |
| Real infrastructure relevance | 5 | Operators need confidence estimates; point predictions are insufficient |
| Senior Applied Scientist relevance | 5 | Uncertainty awareness is explicitly senior-level |
| Compelling visuals | 5 | Calibration curves; prediction interval visualizations; alarm precision at confidence thresholds |
| Risk of overclaiming | 1 (excellent) | Coverage guarantees are distribution-free mathematical results |
| **Total** | **38/45** | Should be in every version; low risk, high reward |

### Q7: Can changes in effective thermal parameters detect emerging anomalies?

| Dimension | Score | Reasoning |
|-----------|-------|-----------|
| Scientific validity | 4 | Parameter drift is well-defined if identification is stable |
| Novelty | 5 | No published paper does this for HPC thermal parameters |
| Dataset support | 2 | 60s resolution + missing T_cool + small ramps limit τ estimation precision; per-node job count may be insufficient in 100-job sample but full 152k-job dataset helps |
| Evaluation quality | 2 | No labeled "cooling degradation" events as ground truth |
| Difficulty | 5 | Parameter identification + change-point detection |
| Real infrastructure relevance | 5 | Identifies degrading CDU circuits without hardware inspection |
| Senior Applied Scientist relevance | 5 | Statistical process control thinking |
| Compelling visuals | 4 | R_eff drift time series; detection events |
| Risk of overclaiming | 4 (bad) | Cannot validate detected drift against real cooling events without labeled data |
| **Total** | **32/45** | Interesting secondary analysis; evaluation is fragile |

---

## 10. Modeling Approaches

### Physics

**RC thermal model** — Mandatory baseline. Fit `C·dT/dt = P - (T - T_cool_est)/R` per node using transient segments from job starts. Use GlassChip methodology. Report τ distribution across all nodes — this alone is a contribution (first such characterization for MI250X). Limitation: 60-second temperature resolution means reliable τ estimation requires jobs with ≥3 temperature increases visible (ramp > noise). Restrict RC fitting to jobs with run_time > 300s and measured ramp > 3°C.

**Kalman filtering** — Appropriate for tracking drifting R and C over time. Treat parameters as slowly time-varying states. Change-point detection on parameter estimates implements Q7.

### Classical ML

**Persistence model** — T(t+Δ) = T(t). Always required as floor baseline.

**Linear regression** — T = a·P_gpu + b·P_cpu + c·project_prefix_encoding + d. Sets linear baseline; its residual is the target for anomaly detection.

**LightGBM** — Captures nonlinear P→T relationships, job-type interactions. Required competitive baseline. Use 5-fold time-series cross-validation (not random splits — temporal autocorrelation would inflate naive CV).

### Time-Series ML

**TCN** — Efficient, parallelizable, good for long sequences. HazardNet used TCN successfully on similar data. Recommend as primary neural baseline.

**LSTM** — RUAD baseline. Slower than TCN; useful if temporal order of state transitions matters.

**Transformer (PatchTST or iTransformer)** — Appropriate for long sequences if 60-minute jobs provide enough temperature observations. Evaluate against TCN; do not assume it wins.

**Temporal Fusion Transformer** — Appropriate only if variable importance from scheduler features is a specific research question. Overhead not justified for point forecasting alone.

### Hybrid (Recommended Primary)

**Physics-informed residual model:**
1. Fit RC model per node → predict `T_RC`
2. Train LightGBM/TCN on residuals `(T_observed - T_RC)`
3. Final prediction = `T_RC + residual_model`

This is tractable, interpretable, and differentiates from pure ML work. Start here before escalating to PINN.

**RC-constrained PINN loss (ThermoPINN architecture):**
Embed the RC ODE as a regularization loss term during neural network training. More principled but harder to implement. Pursue only if residual hybrid shows strong results and there is scope to demonstrate physics constraint value.

### Anomaly Detection

**Residual-based** (primary) — Use conformal prediction intervals on residuals to score anomalousness. Guarantees distribution-free marginal coverage.

**LSTM autoencoder** — RUAD baseline (AUC 0.767 on Marconi100). Implement as unsupervised comparison. Expected to be weaker than workload-conditioned residual approach because it doesn't leverage job metadata.

**Isolation Forest** — Unsupervised point anomaly baseline. Does not use temporal structure.

**Change-point detection** — Ruptures library (PELT or BOCPD) on rolling R_eff estimates for Q7.

### Uncertainty

**Conformal prediction** (primary) — Use `aangelopoulos/conformal-time-series` for adaptive conformal PID intervals. Handle temporal autocorrelation explicitly (use rolling calibration sets, not naive split conformal, which undercovers for time series).

**Quantile regression** — LightGBM pinball loss for 10th/90th percentiles. Non-parametric alternative comparison to conformal.

**Ensemble variance** — Bootstrap 10–20 LightGBM models. Less rigorous than conformal but quick to implement as comparison.

---

## 11. Senior Applied Scientist Perspective

### What Would Impress

1. You identified that GCD temperatures are present at 60-second resolution and explicitly designed the RC model identification approach around this constraint — including restricting fitting to jobs with visible ramps.
2. You built a workload-conditioned temperature model and showed that conditioning reduces false alarm rate compared to unconditional thresholding.
3. You used conformal prediction with correct temporal calibration sets, not naive split conformal, and reported marginal coverage on held-out temporal blocks.
4. You demonstrated transfer learning: trained on Frontier, evaluated on Summit (different GPU architecture, different vendor, ORNL same facility) and on Marconi100 (different country, different hardware, different cooling regime).
5. You honestly reported: maximum observed GCD temperature is 86°C (24°C below thermal limit), reframing the problem as thermal anomaly detection rather than excursion prediction.
6. The τ distribution across all 9,408 Frontier nodes is a novel empirical contribution requiring no modeling claims.

### What Would Look Like a Toy

- Binary classification on a threshold you invented (e.g., ">70°C is an anomaly") without physical or operational justification.
- Reporting cross-validated accuracy without temporal splitting (data leakage from autocorrelation).
- Calling the project "causal" without a DAG, do-calculus, or any causal inference structure.
- Reporting R² = 0.95 on a regression that predicts a strongly autocorrelated signal (near-tautological when predicting T(t) from T(t-1)).

### Mandatory Baselines

1. Persistence model: T(t+k) = T(t)
2. Job-mean model: predict job's mean temperature from project_prefix
3. Linear regression on power features
4. LightGBM without physics features
5. RUAD-style LSTM autoencoder (unsupervised, no workload features)

### Mandatory Ablations

1. Physics baseline vs. ML baseline vs. physics+ML hybrid
2. With project_prefix / workload features vs. without
3. Frontier-trained model on Frontier test vs. Summit test vs. Marconi100 test
4. Conformal vs. quantile vs. no uncertainty
5. 60-second temperature resolution vs. interpolated (to verify resolution isn't limiting)
6. Estimated T_cool (from idle) vs. constant T_cool (sensitivity check)

### Challenges a Reviewer Will Raise

1. "How do you evaluate anomaly detection without labeled anomalies?" — answer: proxy labels (node-relative outlier ranking), comparative analysis (nodes flagged for maintenance vs. not), and empirical calibration of alert precision.
2. "Your RC model uses T_cool from idle periods, but what is the idle period definition, and how many idle observations are available?" — must be answered quantitatively.
3. "Transfer learning between Frontier (MI250X) and Summit (V100) involves completely different GPU architectures. What feature mapping did you use, and what transfers vs. what does not?" — must be answered with specific feature analysis.
4. "Your conformal prediction intervals — how did you handle the autocorrelation of the time series when selecting calibration sets?" — answer: rolling calibration window, not random split.
5. "The temperature data has null values filled by PCHIP interpolation. How many observations were interpolated vs. original, and does this affect your model's performance?" — the data-stats files can answer this.

---

## 12. Arguments Against the Project

### Argument 1 (RESOLVED): GPU Temperature Was Not Confirmed

**Status: Eliminated.** GCD temperatures (8 per node, one per AMD MI250X Compute Die) are confirmed present at 60-second resolution. This was the stated near-fatal risk. It is no longer a concern.

### Argument 2: No Real Thermal Excursions in the Data

The maximum observed GCD temperature in 1.6M observations is 86°C. Zero observations exceed 90°C. The AMD MI250X thermal limit is ~110°C. The original framing ("predict thermal excursions") is not supported — excursions do not occur in this dataset in the sense of approaching hardware limits.

**Assessment:** Real constraint, not fatal. The reframing to workload-conditioned anomaly detection is scientifically stronger and more honest. The 7.8°C standard deviation, 37°C maximum within-job range, and 13°C median within-job range provide ample signal for thermal modeling. The 86°C observations (top 0.01%) are still physically interesting — identifying which nodes, jobs, or conditions produce elevated temperatures is the operative question.

### Argument 3: Temperature Resolution Is 60 Seconds — Too Coarse for Transient Analysis

At 60-second resolution, GCD thermal dynamics below 2–3 minutes are invisible. RC time constant estimation is unreliable for jobs shorter than ~5 minutes. The thermal ramp data shows median ramp of 0.6°C, meaning most jobs don't exhibit measurable transients at 60-second resolution.

**Assessment:** Real constraint on the physics modeling component. It does not affect the primary anomaly detection target (steady-state or near-steady-state residuals). It limits RC model identification to ~11% of jobs that show >10°C ramps. Workable, but must be stated explicitly. The power data (2s/15s) is substantially richer and can substitute for temperature as input in many analyses.

### Argument 4: The Problem Is Already Solved on Different Data

HazardNet achieves F1 0.87–0.98 on thermal hazard prediction on Marconi A2. SeT-Diff achieves MAE 0.033 on thermal inference on Marconi100. The Bologna/CINECA group has produced extensive work on this exact problem.

**Assessment:** Real risk. Mitigation requires genuine differentiation: (1) Frontier data — first published ML result; (2) workload conditioning — no prior paper uses job scheduler metadata as thermal features; (3) calibrated uncertainty — no prior paper uses conformal prediction for HPC thermal; (4) cross-system generalization — no prior paper tests this for HPC thermal. All four differentiators must be in the final paper.

### Argument 5: Observational Data Prevents Causal Claims

The dataset has no intervention records. Every "what-if" estimate is a physics model prediction, not a measured effect. Any claim of "root cause" or "counterfactual" is associational at best.

**Assessment:** Real constraint on claim language. Not a project-killer. Requires careful framing: "associated factor," "physics-model-predicted effect," "consistent with" — never "caused by" or "root cause."

### Argument 6: Node Reuse Is Low in Small Samples

In the 100-job sample, only 26% of nodes appear in ≥2 jobs, and the median node appears in only 1 job. Per-node fixed effects require multiple observations per node.

**Assessment:** This is a sample artifact. The full 152,400-job dataset will have substantially more node reuse — most nodes will appear in many jobs over the 2-year collection period. Verify node reuse distribution in the full job-info file before committing to node-fixed-effect models.

### Summary

The one unresolvable concern is that temperature variability is moderate (not extreme). This means the project cannot make dramatic claims like "predict failures" or "prevent hardware damage." The achievable claim is: "detect nodes with anomalous thermal behavior relative to workload expectations, with calibrated uncertainty, across multiple HPC architectures." This is scientifically rigorous and operationally valuable, but requires a specific audience (HPC systems research, reliability engineering) rather than a broad ML audience.

---

## 13. Alternative Questions from the Data

Ignoring the original ThermalOps framing entirely.

### Alternative A: Empirical Characterization of Frontier Thermal Dynamics

**Question:** What is the distribution of thermal response parameters (τ, R_eff) across all 9,408 Frontier nodes, and what architectural and operational factors predict them?

**Why interesting:** First systematic thermal characterization of an exascale AMD GPU cluster. The τ distribution alone, mapped to physical node location (xname), would reveal CDU performance variability across cooling zones. No modeling claims required — this is a measurement paper.

**Datasets:** Frontier job-centric only.

**Publishability:** SC/HPDC/ISC. Descriptive science is publishable when it characterizes a new system at unprecedented scale.

### Alternative B: Power-Aware Job Classification via Thermal Signature

**Question:** Can we classify job workload type (compute-bound, memory-bound, communication-dominated, idle-heavy) from power telemetry time series alone, without access to the application name or batch script?

**Why interesting:** project_prefix is anonymized but preserved as a categorical variable. If thermal/power signatures cluster by project_prefix, it demonstrates that thermal behavior encodes workload type — enabling automated workload classification from monitoring telemetry alone.

**Datasets:** Frontier job-centric.

### Alternative C: GCD-Level Thermal Heterogeneity Within a Node

**Question:** Do different GCDs within the same node (same power supply, same cooling plate) show systematically different temperatures, and is the pattern stable across jobs?

**Why interesting:** Each node has 8 GCDs (2 per GPU × 4 GPUs). If GCDs within one node differ systematically in temperature, this reveals intra-node cooling heterogeneity — a manufacturing or assembly quality signal. This question requires only within-node analysis and needs no external labels.

**Datasets:** Frontier job-centric only.

### Alternative D: Cross-Architecture Thermal Response Scaling Laws

**Question:** Do thermal response parameters scale predictably with GPU TDP, package design, and cooling technology across different architectures (MI250X → V100 → HBM-based accelerators)?

**Why interesting:** If scaling laws exist, thermal models trained on one architecture could be analytically adapted (not just empirically transferred) to a new architecture. This is the strongest version of cross-system generalization.

**Datasets:** Frontier + Summit + Marconi100.

---

## 14. Final Recommendation

### Verdict: GO — REFRAME

### Justification

1. GPU (GCD) temperatures are confirmed present at 60-second resolution — the near-fatal risk is eliminated.
2. The Frontier dataset is 3 weeks old. No published ML work exists on it. First-mover advantage is genuine.
3. Power-temperature correlation r=0.971 demonstrates the data is well-conditioned for thermal modeling.
4. The combination of (Frontier as primary data) + (workload conditioning) + (calibrated conformal uncertainty) + (cross-system generalization) does not exist in any published paper.
5. The original "thermal excursion prediction" framing is not supported by the data; the reframe to "workload-conditioned thermal anomaly detection" is scientifically stronger.

### Recommended Research Question

> *Can a hybrid physics-informed model with calibrated conformal uncertainty characterize and detect anomalous thermal behavior in exascale HPC compute nodes, conditioned on workload and power telemetry, and do the learned thermal dynamics transfer across supercomputer architectures?*

### Complete Project Specification

| Item | Specification |
|------|---------------|
| **Primary dataset** | Frontier Job-Centric Telemetry Dataset (571 GB, CC0/open, 152,400 jobs, 2024–2025) |
| **Cross-system validation 1** | ORNL Summit (OSTI 1861393, CC-BY 4.0, 612 GB, P9+V100, 10s resolution) |
| **Cross-system validation 2** | M100 ExaData — Marconi100 (Zenodo, CC-BY 4.0, 18.7 TB, V100+P9, cooling loop temps) |
| **RC calibration dataset** | HazardNet Marconi A2 (Zenodo, CC-BY 4.0, 1 GB) — only public dataset with measured T_cool at node level, use to validate RC model quality with known coolant temperature |
| **Primary target variable** | Workload-conditioned GCD temperature residual: `r(t) = T_GCD_observed(t) - T_GCD_predicted(power(t), project_prefix, job_phase)` |
| **Secondary target** | Per-node effective thermal resistance `R_eff` distribution and temporal drift |
| **Core input features** | `gpu{0-3}_power` (15s); `cpu_power` (15s); `node_power` (2s, resampled to 15s); `project_prefix` (categorical); `job_phase` (fraction through job); `queue`; `node_count`; prior-job thermal state if available |
| **Spatial features** | Rack/chassis/slot from xname (encode cooling zone) |
| **Physics baseline** | RC model per node fitted to job-start transients (restrict to jobs with run_time > 300s and GCD ramp > 3°C); use GlassChip methodology; report τ distribution across all nodes |
| **Statistical baseline 1** | Persistence: T(t+Δ) = T(t) |
| **Statistical baseline 2** | Job-mean model: predict from project_prefix only |
| **ML baseline** | LightGBM on full feature set; 5-fold time-series CV |
| **Neural baseline** | TCN (1D) on 30-minute sliding windows |
| **Advanced model** | Physics-informed residual model: RC→residual→LightGBM; optionally escalate to RC-PINN loss |
| **Anomaly detection** | Conformal prediction intervals on residuals (aangelopoulos/conformal-time-series); LSTM autoencoder for unsupervised comparison |
| **Uncertainty method** | Adaptive conformal prediction with rolling calibration sets; quantile regression as comparison |
| **Primary metrics** | RMSE, MAE (regression); Winkler score, marginal coverage (uncertainty); precision@k, NDCG (anomaly ranking); transfer RMSE lift (generalization) |
| **Calibration metric** | ECE (Expected Calibration Error); reliability diagram |

### Required Ablations

1. Physics-only vs. ML-only vs. hybrid (validates physics contribution)
2. With workload features vs. without (validates conditioning contribution)
3. Frontier-trained model on Frontier test / Summit test / Marconi100 test (validates generalization)
4. Conformal intervals vs. quantile regression vs. no uncertainty (validates uncertainty contribution)
5. RC model with estimated T_cool (idle-based) vs. constant T_cool (sensitivity to T_cool assumption)
6. 60-second temperature resolution vs. power-based surrogate at 15s (validates resolution isn't bottleneck)

### Proposed Figures

1. **Dataset thermal statistics:** GCD temperature distribution conditioned on GPU power quintile; CPU temp distribution; power time series for three representative jobs (GPU-heavy, CPU-heavy, idle-heavy)
2. **RC parameter maps:** τ and R_eff per node mapped to xname rack location; reveal CDU zone variability across the 9,408-node system
3. **Power-temperature correlation:** scatter plot of per-job mean GPU power vs. mean GCD temp (r=0.971); residual structure after linear fit; workload class coloring
4. **Workload-conditioned residuals:** distribution of GCD temperature residuals by project_prefix; shows conditioning reduces variance significantly
5. **Anomaly score map:** node-level anomaly scores across a representative sampling day; highlight outlier nodes; cross-reference with rack location
6. **Cross-system transfer:** performance table (RMSE, coverage) across Frontier/Summit/Marconi100; adaptation learning curve
7. **Calibration curve:** expected vs. actual coverage for conformal intervals on each dataset; demonstrates calibration is maintained across systems
8. **Ablation table:** quantitative gain from each component (physics prior, workload conditioning, uncertainty, cross-system adaptation)

### Computational Requirements

| Component | Hardware | Estimated time |
|-----------|----------|----------------|
| Frontier EDA + feature engineering | 32 GB RAM, CPU | 8–16 hours |
| RC model identification (all 152k jobs) | 16 GB RAM, CPU (parallelizable) | 4–8 hours |
| LightGBM training + hyperopt | 16 GB RAM, CPU | 2–4 hours |
| TCN/LSTM training | Single GPU (A100 or RTX 4090) | 4–12 hours per model |
| Summit dataset processing | 32 GB RAM | 8–16 hours |
| Conformal calibration | CPU | 1–2 hours |
| Full pipeline including ablations | Single GPU workstation | ~3–5 days |

### Scientific Limitations to State Explicitly

1. No hardware-limit thermal events observed (max GCD 86°C vs. ~110°C design max). Anomaly detection targets statistical deviations, not physical safety thresholds.
2. T_cool is estimated from idle node temperatures; uncertainty in T_cool introduces ±Y°C uncertainty in R_eff estimates (quantify Y empirically from Marconi A2 data where T_cool is measured).
3. GCD temperature sampled at 60-second bins — RC time constant estimation restricted to jobs with visible transients.
4. Dataset is observational; no power cap or cooling interventions recorded; all "what-if" scenarios are physics-model predictions under stated assumptions, not causal estimates.
5. project_prefix is an anonymized workload proxy; we cannot determine exact application type.
6. Sample is biased toward large leadership-class jobs; models may underfit single-node job thermal behavior.

### What We CAN Claim

- GCD temperature is predictable from GPU power with r² > X at Y-minute forecast horizon, conditional on workload class.
- Workload conditioning reduces false positive anomaly rate by Z% relative to unconditional temperature thresholding.
- Conformal prediction intervals achieve stated marginal coverage on held-out temporal blocks.
- Per-node thermal resistance R_eff varies by ±W% across the 9,408-node system; xname rack location explains Q% of this variance.
- A Frontier-trained model achieves P% of in-distribution accuracy when evaluated on Summit (measured), demonstrating partial cross-architecture transfer.
- Physics-informed hybrid reduces RMSE by X% over ML baseline and Y% over physics baseline.

### What We CANNOT Claim

- That these results predict hardware failures or safety events.
- That "root cause" of elevated temperatures is determined.
- That "reducing power by X% will reduce temperature by Y°C" (this is a model prediction, not a measured intervention).
- That the model generalizes to all HPC architectures (we tested three specific systems).
- That project_prefix clusters correspond to specific scientific application types (the mapping is anonymized).

### Estimated Project Scope

| Phase | Duration | Deliverable |
|-------|----------|-------------|
| Data ingestion and EDA | 2 weeks | EDA notebook; data dictionary update; temperature distribution figures |
| Physics baseline | 2 weeks | RC identification pipeline; τ and R_eff node maps |
| ML baselines | 2 weeks | LightGBM, TCN; temporal CV results |
| Hybrid model + uncertainty | 3 weeks | Residual hybrid; conformal intervals; calibration curves |
| Cross-system generalization | 2 weeks | Summit and Marconi100 evaluation; transfer learning curves |
| Writing and figures | 2 weeks | Paper-ready manuscript |
| **Total** | **13 weeks** | |

### Repository Name

`thermal-fingerprint-hpc`

### One-Sentence Résumé Description

> Built the first published thermal anomaly detection system for the Frontier exascale supercomputer — combining per-node RC thermal identification, workload-conditioned residual modeling, and conformal prediction intervals — with cross-architecture validation across Summit and Marconi100.

---

*Investigation complete. All empirical statistics are from direct dataset inspection. No code has been written for the project itself.*
