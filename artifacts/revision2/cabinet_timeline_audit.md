# A1 Cabinet Configuration Timeline Audit

**Date:** 2026-10-02
**Plan reference:** REVIEW2_CHALLENGE_PLAN.md Phase A1 (amendment 9d4a530)
**Recommendation:** proceed_with_documentation

---

## Question

Were 74 or 77 cabinets active during the study period? Does the cabinet-power
model use the temporally correct count? Does any capacity calculation assign
historical workload to cabinets or nodes that were not actually available at
that timestamp?

---

## Findings

### Cabinet count

The `fleet_topology.json` and `cabinet_power_envelopes.json` both contain 77
cabinets. All 77 appear in the job placement data (`frontier-completed-job-info.parquet`).
The 77 cabinets are named 2000–2611, with the 2600-series group containing
6 cabinets: 2600, 2601, 2602, 2609, 2610, 2611.

### Late-commissioned cabinets

3 of the 77 cabinets first appear in job data well after the study start date
(2024-01-17):

| Cabinet | First job in data | Days from study start |
|---------|-------------------|-----------------------|
| 2601    | 2024-07-18        | 183 days              |
| 2602    | 2024-07-18        | 183 days              |
| 2600    | 2024-11-22        | 309 days              |

The remaining 74 cabinets appear in job data from 2024-01-17 (study start).
This is the source of the "74 vs 77" question.

### Structural correctness of the Gate F simulation

The Gate F simulation replays **only test-set jobs** — a specific set of 2,637
large-scale jobs selected for the capacity analysis. The simulation does not
replay all 152,400 jobs.

**Critical finding: All 2,637 test-set jobs ran on or after 2024-11-22** — the
date when the last of the three late-commissioned cabinets (2600) first appears
in job data. Zero test-set jobs ran before this date.

| Threshold                    | Test jobs before | Fraction |
|------------------------------|-----------------|---------|
| Cabs 2601/2602 commissioning (2024-07-18) | 0 | 0.0% |
| Cab 2600 commissioning (2024-11-22)        | 0 | 0.0% |

**The structural correctness criterion is satisfied.** No simulation step
assigns workload to a cabinet that was not yet online at the time of that job.
The node→cabinet mapping is derived from actual job placement records
(hostname, xname pairs), not from static assumptions.

Additionally, 1,121 of the 2,637 test-set jobs (42.5%) historically placed
at least one node on a late-commissioned cabinet, which is consistent with
those jobs running after all cabinets were online.

### Power envelope assessment

Late-commissioned cabinets have lower p99 power envelopes than the fleet
median, as expected from their partial-period operational history:

| Cabinet | p99 power (kW) | Fleet percentile |
|---------|---------------|-----------------|
| 2600    | 71.2          | 3rd             |
| 2601    | 74.0          | 5th             |
| 2602    | 68.7          | 1st             |
| Fleet median | 92.5   | 50th            |

These values are correctly estimated from actual operational data during each
cabinet's active period. The lower envelopes impose tighter power constraints
in the simulation when nodes from these cabinets are selected — a conservative
bias relative to using a full-period estimate.

### FA fingerprint assessment

Late cabinets have strongly negative FA_2024 means, indicating they are among
the coolest in the fleet:

| Cabinet | FA_2024 mean | n_jobs_train mean |
|---------|-------------|-------------------|
| 2600    | −2.22       | 6                 |
| 2601    | −1.24       | 24                |
| 2602    | −1.84       | 18                |
| Fleet   | +0.03       | 39                |

The FP selector sorts by ascending FA, so it preferentially selects nodes from
these cool cabinets. Since all test jobs ran after these cabinets were
commissioned, this selection is temporally valid — those nodes were genuinely
available at the time of each simulated job.

The lower `n_jobs_train` values (6–24 vs fleet mean 39) reduce the precision of
FA estimates for late-cabinet nodes but do not introduce directional bias.

---

## Structural Error Determination

**No structural errors found.** The three criteria from the amended plan (§A1)
are evaluated as follows:

1. "Maps any historical job/node to an incorrect cabinet for that timestamp":
   **NOT FOUND.** The node→cabinet map is built from actual job records.
   All test jobs ran after all cabinets were online.

2. "Treats cabinets/nodes as active before they appear in the machine
   configuration in a way that affects reconstructed power or reference exposure":
   **NOT FOUND.** The power envelopes are computed from actual load data;
   cabinet records are 0 in periods before those cabinets ran jobs.
   No test job is scheduled to a pre-commissioning cabinet.

3. "Uses a topology snapshot that does not correspond to the workload period":
   **NOT FOUND.** The fleet_topology is derived from the same job dataset
   that the simulation replays. The 77-cabinet configuration is correct for
   the November 2024–January 2026 period in which all test jobs ran.

---

## What to document in the manuscript

The "74 vs 77 cabinet" question resolves cleanly:

- **74 cabinets** were operational from the start of the study period (January 2024).
- **3 additional cabinets** (2600, 2601, 2602) came online during the study
  period: 2601 and 2602 in July 2024, 2600 in November 2024.
- **The Gate F capacity analysis replays jobs from the period when all 77
  cabinets were online.** No test job is assigned to a cabinet that did not
  exist at that time.
- The power envelopes for the 3 late-commissioned cabinets are computed from
  their actual operational history and are correctly lower than the fleet
  median.
- These 3 cabinets are the coolest in the fleet and contain 78 of the 2,000
  fp-analysis nodes (3.9%). The FP selector preferentially picks them, but
  their thermal fingerprints are measured from genuine operational data.

---

*Audit produced by `artifacts/revision2/run_a1_audit.py`, 2026-10-02.*
*No Phase B/G scientific results observed before or during this audit.*
