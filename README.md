# ThermalShift

**Turning persistent server thermal differences into scheduling capacity.**

Frontier, the ORNL/HPE supercomputer, exhibits a consistent and measurable phenomenon:
nodes that run hotter than average in one quarter continue to do so in the next.
ThermalShift shows that this persistent thermal heterogeneity can be used as a scheduling
signal — routing jobs preferentially to thermally cooler nodes increases the amount of
useful work the system can absorb before reaching historical thermal and power operating envelopes.

---

## The Business Question

> Can telemetry-aware placement deliver more useful compute from existing infrastructure
> before thermal or electrical constraints become binding?

**Answer: yes** — and the advantage is robust.

Across 30 matched workload-replay scenarios, thermal-aware fingerprint placement outperformed
thermally unaware random placement in every single scenario. The median paired capacity
advantage was **+15.5 percentage points**, with a bootstrap 95% CI of **+11.5 to +21.9 pp**.

---

## The Signal Is Persistent and Prospective

The scheduling result rests on a prior empirical claim: that thermal fingerprints
carry real, durable predictive information about future node behavior.

| Validation | Result |
|------------|--------|
| 30-min fleet diagnostic vs. longitudinal fingerprint (FA, n=1,435 nodes) | Pearson r = 0.88 |
| Frozen 2024 fingerprint vs. node's typical 2025 thermal position | r = 0.926, R² = 0.857 |
| Power-only model MAE | 1.071 °C |
| Power + fingerprint model MAE | 0.718 °C |
| Test population | 2,000 nodes |

The r = 0.926 result is node-level aggregation over 2025 jobs using fingerprints learned
entirely from 2024 data — a prospective, out-of-sample prediction. It is not single-job
temperature prediction. This creates the scientific chain:

**signal exists → signal persists → signal predicts → signal changes a scheduling decision
→ decision creates capacity.**

---

## Results at a Glance

| Metric | Random-feasible | FP-cap-10 |
|--------|----------------|-----------|
| Median extra cohort workload | 1.95% | 19.94% |
| 90% simulation interval | 0.18 – 6.85% | 9.39 – 29.53% |
| Wins (30 matched scenarios) | — | **30 / 30** |
| Median paired advantage | — | **+15.5 pp** |
| Bootstrap 95% CI on median | — | **+11.5 to +21.9 pp** |
| Discrete lower-bound (symmetric) | — | **+15.6 pp, 28/29** |
| Primary binding constraint | Thermal S-budget | Thermal B-budget (25/30) |

Paired magnitude statistics are based on **29 uncensored scenarios**. One additional scenario
(s27) was right-censored: FP remained feasible at the maximum tested load (lambda = 1.50,
capacity_unlock_pct = 36.2% vs. Random's 4.0%), giving a confirmed lower-bound advantage
of **at least 32.2 pp**. It is counted as a directional win but excluded from magnitude statistics.

The symmetric discrete lower-bound check uses each policy's last confirmed-feasible load point
rather than linear interpolation. The median advantage is essentially unchanged (+15.6 pp vs
+15.5 pp interpolated), confirming the result is not manufactured by interpolation across
the sparse load grid.

---

## Figures

| Figure | Description |
|--------|-------------|
| `figures/fig_mc_paired.png` | Paired Random vs FP capacity across all 30 scenarios |
| `figures/fig_mc_dc_dist.png` | Distribution of paired ΔC with bootstrap CI |
| `figures/fig_mc_constraints.png` | Binding constraint breakdown and FP capacity by constraint type |

---

## Mechanism

FP-cap-10 does not reduce job heat. It **delays the accumulation** of high-temperature
node-hours by routing jobs to nodes with persistent thermal headroom (low historical F-score).

This shows up in the binding-constraint data: FP is limited by the cumulative
exceedance-hours budget (B-budget: node-hours above the temperature threshold) in 25/30
scenarios. Random scheduling is typically limited by the severity-weighted S-budget
(degree-C times node-hours above threshold) — because without routing guidance, work
lands on thermally unfavorable nodes without regard to persistent thermal differences,
causing severity-weighted exposure to accumulate faster. Cabinet electrical power
binds FP in only 4/30 scenarios.

The distinction matters. FP does not simply push jobs to a different bottleneck; it
restructures which resource runs out first, and does so consistently across workloads.

---

## Project Arc

The result did not come from a single model. It is the product of eleven sequential design decisions:

1. **Discovery** — Thermal fingerprints derived from historical telemetry show that nodes
   maintain persistent hot/cool relative positions across quarters.
2. **Prospective validation** — Fingerprints learned in 2024 predict 2025 node thermal
   rankings, confirming the signal is not a data artifact.
3. **Scheduling policy** — Fingerprints are converted into a placement signal: prefer
   lower-F nodes for new job assignments.
4. **First failure mode** — Unconstrained coolest-node scheduling concentrates work on a
   small set of thermally favorable machines, creating severe utilization imbalance.
5. **Constraint** — FP-cap-10 adds a per-node utilization headroom cap (10%) that prevents
   repeated concentration on the same cool machines, preserving balance.
6. **Stateful replay** — All 2,637 historical base jobs retain their original start times,
   durations, and requested node counts. Their cohort node placements are counterfactually
   replayed under each policy; no base job may be delayed or under-served. Synthetic jobs
   add incremental workload beyond the base.
7. **Thermal accounting** — Node-level absolute thermal exposure budgets replace misleading
   job-level temperature-rate metrics. Budgets are anchored to historical baselines.
8. **Residual calibration** — Empirical residual structure (binned by thermal fingerprint)
   is resampled per scenario, reproducing observed temperature tails rather than using
   Gaussian approximations.
9. **Full-cabinet power** — Cabinet power is reconstructed for all 9,856 Frontier nodes
   across 77 Olympus cabinets (not just the 2,000-node study cohort), validated against
   raw node telemetry (cabinet MAE: 0.37 kW, 0.8% of spread).
10. **Second failure mode** — Tier-cap-20's aggressive cool-node routing concentrates
    power in low-F cabinets. Cabinet power becomes the binding constraint — an electrical
    bottleneck that thermal-only optimization creates.
11. **Robustness** — 30 paired Monte Carlo scenarios (common random numbers, varied
    workload draws and residual permutations) show FP-cap-10 outperforms random in all 30,
    with stable median advantage across a wide range of workload mixes.

---

## Experimental Setup

### Cohort

- 2,000 AMD MI250X GPU nodes across 77 Olympus rack HPE cabinets
- ~26 cohort nodes per cabinet (20.3% of each cabinet's 128 nodes)
- Thermal fingerprints: FA\_2024, trained on 2024 historical telemetry, beta\_F = 0.9569
- Test threshold: T\_P95 = 60.60 C

### Base workload

- 2,637 historical jobs (test set), 78,907 cohort node-hours, 8,750 hours
- Historical budgets: B\_hist\_node = 6,093 h, S\_hist\_node = 18,167 degC-h

### Monte Carlo design

- N = 30 scenarios; MC\_BASE\_SEED = 200
- Common random numbers (CRN): both policies share workload draws and residual permutations
  within each scenario; only node selection differs
- Lambda sweep: [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40, 1.50] — 8 load levels per policy per scenario
- Synthetic jobs: stratified by (month, hour) from the 2,637 base test jobs (same pool as the base workload)
- Crossing: linear interpolation between consecutive lambda points; bracket (lower|interp|upper)
  reported to acknowledge interpolation uncertainty

### Policies evaluated

| Policy | Description | Result |
|--------|-------------|--------|
| Random-feasible | Thermally unaware; random node assignment subject to physical constraints | Baseline |
| FP-cap-10 | Prefer thermally cooler available nodes, subject to a 10% per-node utilization headroom constraint that prevents repeated concentration on the same cool machines | Primary |
| Tier-cap-20 | Extreme cool-node preference; coolest-20% tier only (single scenario) | Cautionary |

---

## Whole-System Context

The modeled base workload represents 1.09% of all fleet node-hours in the matched replay
windows (H\_cohort\_base / H\_all\_replay = 78,907 / 7,260,985). The 2,000-node cohort
is physically ~20% of Frontier's nodes; the 1.09% reflects the 78,907 node-hours in the
selected 2,637-job base workload, not all activity on those nodes. The median incremental gain
corresponds to approximately **12,265 additional node-hours** per replay window, or
**0.17% of total fleet activity** in those windows.

This number is reported for scope honesty, not as the primary result. The experiment
has thermal fingerprints only for the 2,000-node study cohort. It does not show what
would happen if fingerprint-aware scheduling were deployed across all 9,856 Frontier nodes.
The cohort-relative scheduling improvement (+15.5 pp) is the correct primary metric.

---

## Economic Interpretation

The conventional path to more compute capacity is capital expenditure: buy more servers.
ThermalShift explores a different lever: **capacity yield** — extracting more useful work
from existing infrastructure by using measured thermal headroom more intelligently while
remaining within historical thermal and power operating envelopes.

The result is best framed as:

> Thermal fingerprints are schedulable information that existing telemetry infrastructure
> already generates. In historical replay, using that information consistently lets the
> scheduler accept materially more work before the same thermal and power operating
> envelopes are exhausted — with a median paired advantage of +15.5 pp in cohort-relative
> capacity across 30 workload scenarios.

**What this is not:**

- A prediction that Frontier (or any system) has 15.5% spare capacity waiting to be
  reclaimed system-wide.
- A dollar-savings projection. Infrastructure costs, cooling, and capital amortization
  are not modeled.
- A claim that the advantage transfers directly from Frontier to cloud infrastructure.
  Thermal fingerprint distributions, cabinet power densities, and scheduling policies
  all differ across systems.

**What this is:**

- Evidence that persistent machine-level thermal heterogeneity, where it exists, is
  actionable scheduling information.
- A replicable methodology: fingerprint derivation, stateful replay, Monte Carlo
  robustness testing, symmetric discrete-bound validation.
- A demonstration that naive thermal optimization has a failure mode (power concentration)
  that a simple cap constraint can avoid — and that the constrained policy is still
  consistently better than thermally unaware placement.

---

## Limitations

- **Cohort scope.** Results are derived from a 2,000-node cohort on Frontier. Generalization
  to other systems requires re-deriving fingerprints and re-running the capacity analysis
  under system-specific thermal and power constraints.

- **Workload coverage.** The 152,400-job dataset covers ~6.8% of all allocated jobs over
  the study period. Workload draws for the Monte Carlo are stratified but synthetic.

- **Sparse lambda grid.** The load sweep has 8 points (1.00–1.50). Crossing values are
  linearly interpolated; exact crossings may differ. The discrete lower-bound sensitivity
  confirms the median result is not an interpolation artifact.

- **Residual model.** Thermal residuals are binned by F-score decile and resampled
  empirically. This reproduces historical tail behavior but does not model non-stationarities
  or future workload shifts.

- **No live deployment.** All results are from historical replay simulation. Live scheduling
  experiments on Frontier are outside the scope of this study.

- **Workload sensitivity unexplained.** Simple workload summary statistics (mean GPU
  utilization, power per node, job size, runtime) do not significantly explain the
  per-scenario variation in ΔC at n = 29. The variance is genuine but its structural
  drivers are not identified.

---

## File Structure

```
thermalops/
  README.md
  artifacts/
    phase1/
      figures/
        fig_mc_paired.png           paired Random vs FP outcomes (30 scenarios)
        fig_mc_dc_dist.png          dC distribution with bootstrap CI
        fig_mc_constraints.png      binding constraint breakdown
      analysis/
        phase3a_fingerprint_2024.parquet   thermal fingerprints (FA_2024)
        phase3a_test_set.parquet           2,637 base test jobs
        phase3b2d_capacity.py             deterministic capacity baseline
        phase3b2d_results.json
        phase3b3f_fullcab.py              full-cabinet power reconstruction
        phase3b3f_results.json
        phase3b3f_val.py                  node-power validation (60 jobs)
        phase3b_mc.py                     Monte Carlo simulation (30 scenarios)
        phase3b_mc_checkpoint.json        per-scenario checkpoint
        phase3b_mc_results.json           final MC output
        phase3b_mc_analysis.py            post-MC summary statistics
        phase3b_mc_analysis.txt           human-readable results
        phase3b_mc_analysis.json          machine-readable results
        phase3b_mc_validate.py            bootstrap CI + discrete sensitivity
        phase3b_figures.py                figure generation script
  docs/
    PHASE_0_THERMAL_FINGERPRINT.md
    THERMALOPS_FEASIBILITY.md
```

---

## Citation Context

Frontier supercomputer: Oak Ridge Leadership Computing Facility, ORNL.
Hardware: HPE Cray EX, 77 Olympus rack HPE cabinets x 128 AMD compute nodes = 9,856 nodes; 4 AMD MI250X GPUs per node.
Dataset: OLCF job telemetry 2024–2025.
