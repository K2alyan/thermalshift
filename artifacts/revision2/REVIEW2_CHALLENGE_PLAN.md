# REVIEW2_CHALLENGE_PLAN.md
## Preregistered Second-Round Reviewer Challenge Analysis
### ThermalShift — Revision 2

**Date preregistered:** 2026-10-02
**Branch:** revision1/major-revision-analyses
**Preregistration commit:** d28f29d

---

## Amendment 1 — Pre-Analysis Governance Correction (2026-10-02)

**Amendment commit:** 9d4a530
**Status:** No Phase A or Phase B scientific outputs have been generated.
No sc30–54 simulation has been run.  This amendment is therefore pre-results
and preserves the integrity of the preregistration.

**Changes from original preregistration (d28f29d):**

1. **Primary beta rule (§B3):** LOO cross-fitted beta becomes the primary beta
   for sc30–54.  BETA_F_FROZEN=1.12484352 demoted to sensitivity.  Rationale:
   the reviewer challenge (R3) specifically concerns self-inclusion bias in the
   original estimate; using the LOO estimator as primary makes the experiment
   genuinely responsive to R3 rather than treating it as a secondary note.

2. **Cabinet audit blocker (§A1):** Removed arbitrary ">5% job-hours" tolerance.
   Replaced with a structural correctness criterion: the audit is a blocker only
   if the reconstruction assigns historical workload to cabinets/nodes that were
   not actually available at that timestamp, or otherwise uses an invalid topology
   assumption to construct historical power or reference exposure.

3. **Seed collision audit (§F):** Added a dedicated preflight condition requiring
   that all sc30–54 seeds and placebo seeds are internally unique and have zero
   collision with sc0–29 seeds.  Written to preflight JSON.

4. **Placebo wording (§H6):** Replaced "Expected outcome" with "Pre-specified
   interpretation branches."  No placebo result is an acceptance criterion; all
   outcomes are scientifically interpretable.

---

## Amendment 2 — Post-A1 Methodological Corrections (2026-10-02)

**Amendment commit:** 6b45030
**Status:** A1 audit complete (e7b70be, PASS — proceed_with_documentation).
No Phase B beta has been computed.  No new selector has been run on sc30–54.
sc30–54 seeds are frozen and unchanged.  Gate F evidence files are unchanged.

**Changes from Amendment 1 (9d4a530):**

1. **Cross-fitted beta estimator (§B1, §B3):** The previously described procedure
   — many per-job jackknife regressions averaged — does NOT cleanly address the
   reviewer's self-inclusion concern.  Replaced with observation-level LOO: for
   each (node i, job j) observation, compute F_CF[i,j] = FA for node i estimated
   excluding job j from the training data, then fit ONE beta_CF on the complete
   cross-fitted dataset.  The jackknife collection of betas is retained as a
   sensitivity diagnostic only.

2. **Primary comparison list (§D4):** Added `full_fp vs fp_withincab_placebo`
   as an explicit preregistered comparison (the decisive node-level test).
   Changed `fp_withincab_placebo vs Random` and `fp_global_placebo vs Random`
   to direct pairings against `full_fp`.  Reordered to reflect scientific
   priority.  All 8 comparisons are now direct pairings — no comparison is
   inferred by subtraction.

3. **RandomSpread fairness requirements (§C1):** Added explicit pseudocode and
   requirement that `random_spread` uses the same cabinet-spreading mechanism
   as `full_fp_spread` but substitutes FA ranking with the existing deterministic
   event-node priority used by `full_random`.  No new thermal-derived score
   and no new independent RNG stream.

4. **A1 terminology (§A1):** Replaced "commissioned/came online" with "first
   observed in the Frontier job-placement records."  Removed stale 2022–2023
   study-period text; replaced with correct dataset dates (2024–2026).

5. **Post-A1 late-cabinet cohort diagnostic (§A1b):** Added an explicitly
   exploratory descriptive audit of the 78 late-cabinet cohort nodes
   (cabinets 2600/2601/2602) vs the other 1,922 cohort nodes.  This is a
   prospective validation check for FA fingerprint quality, not a new hypothesis.
   No challenge policy or population may be modified based on this diagnostic.

---

## Amendment 3 — LOO Estimand Correction and Preflight Fixes (2026-10-02)

**Amendment commit:** (pending new freeze)
**Supersedes:** run_b1_loo_beta.py (preserved as audit record at commit 2814bb6)
**Status:** No sc30–54 simulation has been run.  All corrections are pre-results.

**Background:**  After the superseded clean freeze at 2814bb6, two critical errors
were identified in the Phase B LOO estimator.  This amendment corrects both, adds
a new equivalence-test preflight condition, and clarifies one terminology point.

### B3-1. Wrong estimand (critical)

`run_b1_loo_beta.py` computed a POOLED fixed-effects slope:
```
beta_CF = sum_j(c_xy[j]) / sum_j(c_xx[j])
```
where `c_xy[j]` and `c_xx[j]` are job-level cross-product aggregates.  This is a
different estimand from BETA_F_FROZEN, which is `median(beta_j)` over 462 per-job
OLS slopes.  A pooled FE slope and a median-of-slopes are not algebraically equivalent
and differ in their sensitivity to outlier jobs.

**Correction:**  PRIMARY_BETA_CHALLENGE must use the same aggregation as BETA_F_FROZEN:
```
PRIMARY_BETA_CHALLENGE = median_j(beta_j_CF)
```
where `beta_j_CF` is the per-job OLS slope fitted on the LOO-corrected predictors
`F_CF[i,j]` for the nodes present in job j.  This preserves the estimand used in
the original M4 analysis while correcting for self-inclusion.  The pooled FE slope
(1.08293343, from run_b1_loo_beta.py) is demoted to a secondary diagnostic and
reported in `loo_beta_results.json` under key `B1_secondary_FE_beta`.

### B3-2. Wrong r_ij in LOO shortcut (critical)

The LOO leave-one-out formula removes job j's contribution from FA_2024[i]:
```
F_i^(-j) = (n_i * FA_2024[i] - r_ij) / (n_i - 1)
```
`run_b1_loo_beta.py` used `r_ij = T_dev[i,j]` — the T_p95 within-job deviation.
This is INCORRECT.  FA_2024[i] is constructed as the mean over all training jobs of
`r_ij = node_scalar_mean[i,j] - job_mean(node_scalar_mean)`, where `node_scalar_mean`
is the FLAT MEAN of ALL non-NaN GCD temperature values (all timestamps × all sensor
columns) for that node in that job.  T_p95 is used only as the OUTCOME in the beta
regression — it is a different quantity from the fingerprint contribution.

**Correction:**  `run_b1_loo_beta_v2.py` reconstructs the exact r_ij:
```python
vals = tmp[node_gcols].values.astype(float)   # (n_timestamps, n_gcds)
flat = vals.flatten()
valid = flat[np.isfinite(flat)]
node_scalar_mean_ij = float(valid.mean())      # flat mean — matches phase3a_validation.py
r_ij = node_scalar_mean_ij - job_mean_nsm      # within-job centred contribution
```
Hard assertion (must pass before any LOO computation proceeds): reproduce the
original per-job betas from m3_train_betas.parquet using FA_2024[i] + T_p95 as
predictor + outcome.  If median(beta_j_repro) deviates from BETA_F_FROZEN by more
than 0.001, the script exits non-zero.

### F-11. Preflight condition 11 correction (dry-run target)

Condition 11 in the superseded preflight referred to "sc30 dry-run" and
"GATE_F_N_FIRST=30" — but sc30–54 must never be touched before the final freeze.
Corrected: condition 11 now verifies a sc0–4 compatibility dry-run (or, when the
data directory is not available, seed/constant verification only).

### F-13. New preflight condition: r1↔r2 equivalence test (hard condition)

A new hard preflight condition (13) is added: `r2_vs_r1_equivalence.json` must exist
and record `overall_pass: true`.  This is produced by `r2_vs_r1_equivalence.py`,
which:
1. Generates sc0–4 seeds from rng(42) and verifies they match the frozen r1 dev output.
2. Verifies all frozen constants (BETA_F_FROZEN, T_THR_PRIMARY etc.) appear in r2 code.
3. If THERMALSHIFT_DATA_DIR is available, runs the full sc0–4 simulation in
   compatibility mode (BETA_F_FROZEN, original 4 policies) and hard-compares
   capacity_unlock_pct, B_primary_ratio, S_primary_ratio, B_cab_ratio per scenario per
   policy per ratio against the frozen r1 dev output files.  Tolerances: absolute
   ≤ 0.01 (percentage points for capacity_unlock_pct, ratios for ratio fields).

### C4. position_template semantics clarification (non-normative)

`position_template` is an alias for `full_loc` from Gate F.  The `LOC_FA_dict` it
uses is constructed as `mean(FA_2024)` over all fp nodes that share the same physical
position (chassis/slot/board/node_pos).  This is THERMALLY INFORMED — it reflects the
average historical thermal fingerprint at that physical position, not a purely
topological index.  This clarification changes no policy behaviour; it documents the
mechanism so reviewers understand what the position_template comparison tests.

### R² Reporting Correction (A2)

The superseded `run_a2_a1b.py` reported `r2 = pearson_r**2` only, which conflates
the frozen-prediction R² (how well FA_2024 predicts T_dev without refitting) with the
calibrated OLS R² (how well a refit OLS slope predicts T_dev).  These are distinct:
- R2_frozen = 1 - SSE(T_dev, F_2024) / SST(T_dev)  [no refit; tests the frozen predictor]
- R2_ols    = pearson_r**2  [allows an OLS slope and intercept]
The corrected script reports both, plus MAE, RMSE, and sign agreement per stratum.

---

## Governing Rule

No policy definition, metric definition, threshold, seed, comparison selection, or
interpretation rule may change after the challenge run begins (Phase G).  The sequence
is strictly linear:

1. Inspect current revision1 code and results (done — Gate F H3 complete at commit e16ec3c)
2. Write and commit this preregistration document (current step)
3. Implement all new policies and tests (Phase C)
4. Run only development/preflight scenarios (Phases D–F)
5. Freeze all code in a clean commit with no untracked files
6. Only then execute challenge scenarios sc30–54 (Phase G)

Deviation from this sequence is a scientific integrity violation and must be reported
in any resulting manuscript.

---

## 1. Motivation

Gate F (sc5–sc29, committed e16ec3c) demonstrated that thermal-aware FP placement
retains a positive capacity advantage even when scheduler choice is substantially
restricted (3.6–5.6 pp at r=1.25–2.0, 25/25 held-out scenarios unanimous).

Anticipated second-round reviewer challenges:

- **R1 (Placebo / confounding):** Is the FP effect due to thermal fingerprint
  information, or to some artefact of the FP selection rule (e.g., systematically
  choosing lower-numbered or cooler-cabinet nodes)?
- **R2 (Spread effect):** Does within-cabinet spread rather than fingerprint sorting
  drive the advantage?  Can a placebo with spread alone replicate the gain?
- **R3 (Beta stability):** BETA_F=1.12484352 is estimated from 30 jobs.  How sensitive
  are the results to leave-one-job-out perturbations?
- **R4 (Cabinet count):** Were 74 or 77 cabinets active during the study period?
  Does the cabinet-power model use the temporally correct count?
- **R5 (Job-size heterogeneity):** Does the FP effect vary across job sizes?  The
  reviewer may suspect the 129–512 node range dominates.
- **R6 (Threshold sensitivity):** Are results sensitive to T_thr or cabinet-envelope
  calibration (±5–10%)?

---

## 2. Frozen Gate F Evidence Record

These results are **read-only** for this challenge analysis.  They define the
baseline against which all challenge comparisons are interpreted.

| File | Commit | Description |
|------|--------|-------------|
| `artifacts/revision1/results/gate_f_sc5-29_1p25_1p5_2p0_4p0_8p0.json` | e16ec3c | H3 merged results (25 held-out scenarios) |
| `artifacts/revision1/results/gate_f_heldout_analysis.json` | e16ec3c | Frozen held-out analysis |
| `artifacts/revision1/results/gate_f_sc0-4_1p25_1p5_2p0_4p0_8p0.json` | e16ec3c | Dev results |
| `artifacts/revision1/results/gate_f_sc0-4_1p0.json` | e16ec3c | r=1.0 negative control (dev) |
| `artifacts/revision1/results/gate_f_sc5-29_1p0.json` | e16ec3c | r=1.0 negative control (held-out) |
| `artifacts/revision1/results/m1_location_identity.json` | e16ec3c | Frozen M1 prospective R² |

### Gate F Primary Results Summary (sc5–sc29, H3)

**FP vs Random (primary comparison):**

| r    | A wins | Indist. | B wins | Median delta_lo (pp) | Bootstrap 95% CI (pp) |
|------|--------|---------|--------|----------------------|-----------------------|
| 1.0  | 0      | 25      | 0      | −0.003               | [−0.301, 0.000]       |
| 1.25 | 25     | 0       | 0      | +4.771               | [+2.585, +6.063]      |
| 1.5  | 25     | 0       | 0      | +5.612               | [+3.178, +8.969]      |
| 2.0  | 24     | 1       | 0      | +4.856               | [+3.561, +7.415]      |
| 4.0  | 24     | 1       | 0      | +4.439               | [+3.171, +5.451]      |
| 8.0  | 24     | 0       | 1      | +3.589               | [+2.590, +4.387]      |
| unr  | 22     | 1       | 2      | +4.236               | [+2.874, +5.297]      |

**FPSpread vs FP:**

| r    | A wins | Indist. | B wins | Median delta_lo (pp) | Bootstrap 95% CI (pp) |
|------|--------|---------|--------|----------------------|-----------------------|
| 1.25 | 3      | 3       | 19     | −3.363               | [−4.935, −1.880]      |
| 1.5  | 1      | 3       | 21     | −3.293               | [−4.889, −2.398]      |
| 2.0  | 3      | 5       | 17     | −2.879               | [−3.899, −1.300]      |
| 4.0  | 16     | 3       | 6      | +0.542               | [−0.644, +1.740]      |
| 8.0  | 20     | 4       | 1      | +1.529               | [+0.715, +2.991]      |
| unr  | 20     | 3       | 2      | +2.849               | [+0.598, +3.704]      |

**FPSpread vs Random:**

| r    | A wins | Indist. | B wins | Median delta_lo (pp) | Bootstrap 95% CI (pp) |
|------|--------|---------|--------|----------------------|-----------------------|
| 1.25 | 21     | 4       | 0      | +1.611               | [+0.438, +2.909]      |
| 1.5  | 19     | 6       | 0      | +2.517               | [+0.778, +4.194]      |
| 2.0  | 22     | 1       | 2      | +3.231               | [+1.407, +5.061]      |
| 4.0  | 25     | 0       | 0      | +6.320               | [+3.504, +7.564]      |
| 8.0  | 24     | 1       | 0      | +7.178               | [+3.879, +8.760]      |
| unr  | 24     | 1       | 0      | +7.128               | [+4.505, +8.987]      |

**Loc vs Random:**

| r    | A wins | Indist. | B wins | Median delta_lo (pp) | Bootstrap 95% CI (pp) |
|------|--------|---------|--------|----------------------|-----------------------|
| 1.25 | 22     | 3       | 0      | +2.621               | [+1.100, +5.149]      |
| 1.5  | 24     | 1       | 0      | +4.495               | [+2.784, +6.197]      |
| 2.0  | 24     | 1       | 0      | +4.146               | [+2.565, +6.905]      |
| 4.0  | 24     | 1       | 0      | +4.046               | [+3.079, +5.033]      |
| 8.0  | 25     | 0       | 0      | +3.627               | [+2.776, +6.139]      |
| unr  | 23     | 2       | 0      | +4.542               | [+2.964, +6.678]      |

---

## 3. Frozen Simulation Constants

These constants are identical to Gate F (r1_gate_f_run.py) and may NOT change
for the challenge run.

```python
BETA_F_FROZEN   = 1.12484352          # frozen from M4
T_THR_PRIMARY   = 63.625              # °C
T_THR_SECONDARY = 60.602770562770566  # °C
DELTA_CAP       = 0.10                # 10 pp QoS ceiling
N_BINS          = 5
LAMBDA_SWEEP    = [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40,
                   1.50, 1.55, 1.60, 1.70, 1.80, 1.90, 2.00]
LAMBDA_MAX      = 2.00
LAMBDA_MAX_EXT  = 4.00
LAMBDA_SWEEP_EXT = [2.25, 2.50, 3.00, 3.50, 4.00]
TARGET_PP       = 0.50
N_REFINE_GRID   = 3
GATE_F_RATIOS   = [1.0, 1.25, 1.5, 2.0, 4.0, 8.0, None]  # None = unrestricted
```

**Original scenario seed (sc0–29, UNCHANGED):**
```python
SCENARIO_SEED = 42   # rng(42) generates sc0-29 scen_seeds and wl_seeds exactly
```

**Challenge scenario seed (sc30–54, SEPARATE):**
```python
CHALLENGE_SEED = 2042   # rng(2042), independent of rng(42)
```

Using a separate seed for sc30–54 is required because extending rng(42) from N=30
to N=55 would shift the wl_seeds draw index from 30 to 55, altering wl_seeds for
sc0–29 and breaking the backward-compatibility invariant.  The scen_seeds[0:30]
from rng(42) are immune (drawn first), but wl_seeds and pol_seeds are not.

---

## 4. Frozen Challenge Scenario Seeds (sc30–54)

Generated by:
```python
rng = np.random.default_rng(2042)
scen_seeds = [int(rng.integers(0, 2**31)) for _ in range(25)]  # sc30-sc54
wl_seeds   = [int(rng.integers(0, 2**31)) for _ in range(25)]
placebo_global_perm_seed    = int(rng.integers(0, 2**31))
placebo_withincab_perm_seed = int(rng.integers(0, 2**31))
```

| sc  | scen_seed  | wl_seed    |
|-----|------------|------------|
| 30  | 1520047186 | 1994769663 |
| 31  | 1145613857 | 98741167   |
| 32  | 1521583570 | 581721350  |
| 33  | 629767374  | 1816866876 |
| 34  | 1112822527 | 1012191133 |
| 35  | 1702157981 | 479602785  |
| 36  | 684253553  | 1332425394 |
| 37  | 118246515  | 201221264  |
| 38  | 418197535  | 342687064  |
| 39  | 552807005  | 1159106977 |
| 40  | 860057835  | 871759594  |
| 41  | 2017429576 | 143054453  |
| 42  | 930605457  | 1086829000 |
| 43  | 904615776  | 1256185540 |
| 44  | 2132759622 | 574886723  |
| 45  | 234115232  | 1255220541 |
| 46  | 1207943457 | 565014714  |
| 47  | 1052894112 | 1984834199 |
| 48  | 1093599206 | 1038460268 |
| 49  | 1506954242 | 1430752378 |
| 50  | 1354524148 | 1493659955 |
| 51  | 982358118  | 194826593  |
| 52  | 1629465822 | 290894800  |
| 53  | 1923189114 | 238926708  |
| 54  | 918802192  | 57164757   |

**Placebo permutation seeds (drawn sequentially after wl_seeds above):**
```python
placebo_global_perm_seed    = 218767960
placebo_withincab_perm_seed = 365514213
```

These seeds are frozen here.  They must not be changed after this commit.

---

## 5. Phase A — Cheap Audits (No New Simulation)

All Phase A tasks read existing frozen artifacts only.  They must complete before
any challenge simulation.  A1 is a potential blocker: if the cabinet count is
temporally wrong, all capacity calculations are suspect and the challenge run
must not proceed until resolved.

### A1. Cabinet Configuration Timeline Audit (POTENTIAL BLOCKER)

**[Amended 2026-10-02 — terminology and date range corrected per Amendment 2]**

**Question:** Were 74 or 77 cabinets present in the Frontier job-placement
records during the test-set replay period (dataset spans 2024-01-17 to
~2026-01-01)?  Does the cabinet-power reconstruction assign any simulated
workload to a cabinet not yet present in the job-placement records at that time?

**Task:**
- Cross-reference `fleet_topology.json` cabinet list against the job start/end
  timestamps in the parquet to determine when each cabinet first appears in
  job-placement records.
- Produce `artifacts/revision2/cabinet_timeline_audit.json` with:
  - n_cabs_fleet_topology: int
  - n_cabs_in_job_data: int
  - first_observed_date_per_cabinet: {cabinet: date}
  - recommendation: "proceed_with_documentation" | "stop_structural_error"
- Produce `artifacts/revision2/cabinet_timeline_audit.md` with narrative.

**Outcome rule (structural correctness criterion):**

This audit is a blocker if and only if the reconstruction is found to be
structurally incorrect in a way that affects historical capacity estimates:

- **STOP** if any simulation replay step assigns workload to a cabinet whose
  nodes do not appear in the job-placement records as of that job's start time.
- **STOP** if cabinets or nodes are modeled as contributing power or thermal
  exposure before they first appear in placement records, in a way that
  materially affects reference budgets.
- **STOP** if the cabinet-power reference uses a topology snapshot that does not
  correspond to the period covered by the workload data in any material way.

The mere fact that some cabinets first appear in job-placement records later
than others is not itself a failure.  If the Gate F replay only processes jobs
that occurred after all cabinets were first observed, document that explicitly
and proceed.  "First observed in job-placement records" is the operative
criterion; no claim about physical commissioning dates is required or implied
unless supported by an independent authoritative Frontier configuration source.

The audit JSON must record for each late-first-observed cabinet: date of first
job record, whether any test-set job precedes that date, and whether any
simulation replay step would assign nodes from that cabinet to a pre-observation
job.  The recommendation field must be one of:
"proceed_with_documentation" | "stop_structural_error".

**Status:** COMPLETE — commit e7b70be.
Result: proceed_with_documentation.
All 2,637 test-set jobs ran on or after 2024-11-22, after all 77 cabinets
were first observed in job-placement records.  No structural error found.
See `artifacts/revision2/cabinet_timeline_audit.json` and `.md`.

### A1b. Post-A1 Late-Cabinet Cohort Diagnostic (EXPLORATORY, NOT A PRIMARY HYPOTHESIS)

**[Added by Amendment 2 — explicitly exploratory; no challenge policy or population
may be modified based on this diagnostic]**

**Background:** A1 found that cabinets 2600, 2601, 2602 first appear in
job-placement records 183–309 days into the study period.  Their 78 cohort nodes
(3.9% of 2,000 fp-analysis nodes) have:
- Fewer fingerprint training jobs (mean 6–24 vs 39 for all other cabinets)
- Strongly negative FA_2024 means (−1.24 to −2.22 vs fleet mean +0.03)
- The FP selector preferentially picks these nodes

The scientific question is whether these negative fingerprints reproduce
prospectively — i.e., are these cabinets genuinely cooler in the 2025 test
period, or are their extreme negative FA values a consequence of sparse training
data?

**Task:** Produce a purely descriptive comparison:

Late-observed cohort nodes (n=78, cabinets 2600/2601/2602) vs other cohort
nodes (n=1,922, all other cabinets):
- Node count, training jobs/node (mean, min, max)
- FA_2024 distribution: mean, SD, min, max, histogram deciles
- Prospective 2025 test set: Pearson r, Spearman r, frozen-prediction R²,
  MAE, RMSE, sign agreement (fraction where FA_2024 < 0 and ΔT < 0)
- Future median relative-temperature distribution (ΔT = T_actual − α_j)

Produce `artifacts/revision2/late_cab_cohort_diagnostic.json`.

**Interpretation rule (frozen):**
- If late-cab nodes are genuinely cooler prospectively (FA_2024 < 0 predicts
  ΔT < 0 at similar rate to other nodes): the thermal fingerprint is valid
  despite fewer training jobs; no concern.
- If late-cab nodes have poor prospective prediction quality (low r², sign
  agreement much worse than other nodes): flag in manuscript as a potential
  FA precision concern for those 78 nodes; do NOT remove them from the
  challenge or modify policy logic.
- Either outcome is reported without omission.

### A2. Prospective Accuracy by Job Size

**Question:** Is BETA_F estimated from job-level data predictive across job sizes?
Does the 129–512 node bin dominate the effect?

**Task:** Stratify the M1 prospective prediction accuracy (T_hat vs T_actual) by
job-size bins:
- [1, 32], [33, 128], [129, 512], [513, 2048], [2049+]

For each bin report: n_jobs, Pearson r, R², slope (OLS fit), intercept.

Produce `artifacts/revision2/prospective_accuracy_by_job_size.json`.

### A3. M1 Sensitivity Packaging

**Task:** From `artifacts/revision1/results/m1_location_identity.json`, extract
and package the key sensitivity results:
- Individual-F frozen prospective R²: 0.8482261482495985 (verified)
- Pearson r: 0.9258770969716581
- Location-only R², location+F OLS R²
- Sensitivity to BETA_F at ±10%: if available in frozen results, report

Produce `artifacts/revision2/m1_sensitivity_summary.json`.

### A4. Manuscript-Ready Tables from Frozen Gate F Results

**Task:** From the frozen `gate_f_heldout_analysis.json`, produce:

1. Full Gate F primary table: all comparisons × all ratios, with:
   - n_definitely_A, n_indistinguishable, n_definitely_B
   - median_delta_lo (pp), bootstrap95 CI [lo, hi] (pp)
   - median_delta_hi (pp)

2. Binding constraint table: per ratio, per policy, fraction of scenarios where
   each constraint (B_cab_ratio, B_ratio, S_ratio) was binding.
   Source: individual per-scenario JSON files in revision1/results/.

3. Cabinet-reference sensitivity table: FP vs Random primary result at r=1.25
   under cabinet-envelope scale factors [0.90, 0.95, 1.00, 1.05, 1.10].
   This requires reading sensitivity-run results if they exist, or flagging
   as "not yet computed — required before manuscript."

4. FPSpread vs FP table at all ratios with both delta_lo AND delta_hi CIs.

Produce `artifacts/revision2/gate_f_manuscript_tables.json`.

---

## 6. Phase B — LOO Cross-Fitted BETA_F

**Question (R3):** How sensitive are Gate F results to leave-one-job-out
perturbations of BETA_F?

### B1. Cross-Fitted Beta Estimator (PRIMARY ESTIMATOR)

**[Amended by Amendment 2 — replaces jackknife-average description from
Amendment 1 §B1]**

The primary estimator addresses the reviewer's self-inclusion concern by
computing observation-level leave-one-job-out cross-fitted fingerprints
and fitting a SINGLE regression on the complete cross-fitted dataset.

**Procedure:**

For every eligible 2024 node-job observation (i, j):

```
F_CF[i,j] = FA for node i computed from the frozen 2024 training set
             with job j entirely excluded from both numerator and denominator
             of node i's fingerprint estimate.
```

Then fit ONE model over the complete set of eligible cross-fitted observations:

```
T_ij = alpha_j + beta_CF * F_CF[i,j] + epsilon_ij
```

or the algebraically equivalent within-job demeaned form used by the existing
pipeline.  This yields a single `beta_CF`.

**Requirements (all must be preserved from the original M4 fit):**
- Same eligibility rules, GCD aggregation, job weighting, and node filtering.
- Job j may contribute to the outcome `T_ij` but may NOT contribute to its
  own predictor `F_CF[i,j]`.
- No 2025 data enter `F_CF` or `beta_CF` estimation.
- Nodes for which no training observation remains after excluding job j are
  excluded from that (i, j) observation; count and report these exclusions.
- If any eligibility rule is mathematically impossible under LOO (e.g., GCD
  threshold leaves zero observations for some i after excluding j), document
  exactly which rule and how many observations are affected before proceeding.

**Uncertainty quantification:**
Job-cluster bootstrap: resample jobs (not observations) with replacement;
recompute F_CF and beta_CF for each bootstrap replicate.  Report 95% CI.

**If the cross-fitted estimator cannot be defined** under the frozen rules
(e.g., model is unidentifiable after observation exclusions), STOP and document
before substituting.  A quarter-wise cross-fit (§B2) may then be proposed only
under a new pre-results amendment — it may not be silently substituted.

Report: beta_CF, bootstrap 95% CI, n_observations, n_excluded_observations,
n_excluded_nodes.

### B2. Sensitivity Diagnostics (NOT the primary estimator)

These are reported as sensitivity checks alongside the primary beta_CF.

**B2a. Jackknife collection (sensitivity):**
For each job j, re-fit the model excluding job j from both fingerprints and
outcome observations (job-level exclusion, NOT observation-level cross-fit).
Record BETA_F^(-j) for each excluded job.
Report: distribution of BETA_F^(-j) — mean, std, min, max, P5, P95.

**B2b. Quarter-wise cross-fit (sensitivity):**
Partition the 2024 dataset by calendar quarter (Q1-2024, Q2-2024, Q3-2024,
Q4-2024 or as available).  For each quarter q, train fingerprints on jobs NOT
in quarter q and estimate beta_q.
Report: beta_q for each quarter, range across quarters.

These diagnostics describe the stability of the slope estimate; they do not
replace beta_CF as the primary challenge beta.

### B3. Primary Beta Choice (Frozen Before Challenge Run)

**[Amended by Amendment 2 — supersedes Amendments 1 and d28f29d §B3]**

```
PRIMARY_BETA_CHALLENGE = beta_CF   [single observation-level LOO cross-fit]
```

`beta_CF` is computed from ONE regression fit on the complete cross-fitted
observation set (§B1).  It is NOT the mean of per-job jackknife regression
coefficients.

This value is written to `artifacts/revision2/loo_beta_results.json` before
any sc30–54 run begins and must not be changed thereafter.

The LOO value is used regardless of its magnitude or direction relative to
BETA_F_FROZEN.  We do not choose between them based on which gives a stronger
scheduling result.

**Sensitivity values (all used in §E2 runs):**
- `BETA_F_FROZEN = 1.12484352` — original model estimate
- `BETA_F_PROSPECTIVE = 0.96` — prospective slope from M1
- `BETA_F_JACKKNIFE_MEAN` — mean of per-job jackknife betas (from §B2a)
- `BETA_F_CF_P5, BETA_F_CF_P95` — 5th and 95th percentile of bootstrap CI

---

## 7. Phase C — New Selector Implementation

Four new policies are added for the challenge run.  All must be implemented,
unit-tested, and code-frozen before sc30–54 executes.

### C1. `random_spread`

**[Fairness requirements added by Amendment 2]**

**Rule:** Identical cabinet-spreading mechanism as `full_fp_spread` (round-robin
by least-loaded cabinet), but within each cabinet select nodes using the SAME
deterministic event-node random priority used by `full_random` — not by FA rank.

**Purpose:** Isolates the cabinet-spread effect from the fingerprint-sorting effect.

**Scientific value of key pairings:**
- `full_fp_spread` vs `random_spread`: fingerprint-ranking contribution after
  controlling for spreading — the cleanest test of whether FA ordering matters
  once cabinets are spread
- `random_spread` vs `full_random`: spreading contribution alone, no thermal info

**Fairness requirements (all mandatory):**
1. The cabinet-spreading loop (round-robin by `cab_active_count`) must be
   IDENTICAL to `full_fp_spread` — same cabinet selection order, same tie-breaking.
2. Within each selected cabinet, node selection must use the SAME `choice_priority`
   hash (BLAKE2b keyed by `scenario_seed` + `event_uid` + `hostname`) that
   `full_random` already uses for its node ordering.  No new random stream.
3. `random_spread` must NEVER read `FA_dict`, `LOC_FA_dict`, or any
   thermally-derived score.  Assert this in the unit tests.
4. The implementation is deterministic given the same scenario_seed and event_uid.

**Pseudocode:**

```python
def select_random_spread(available, k, cab_active_count, scenario_seed, event_uid):
    k = min(k, len(available))
    if k == 0: return []
    if k == len(available): return sorted(available)

    # Same cabinet-spread round-robin as full_fp_spread
    cab_nodes = defaultdict(list)
    for n in sorted(available):       # sort for determinism before round-robin
        cab_nodes[fp_cab[n]].append(n)

    # Within-cabinet order: by choice_priority (same hash as full_random)
    for c in cab_nodes:
        cab_nodes[c].sort(key=lambda n: choice_priority(scenario_seed, event_uid, n))

    temp = dict(cab_active_count)
    selected = []
    for _ in range(k):
        if not cab_nodes: break
        best_c = min(cab_nodes, key=lambda c: (temp.get(c, 0), c))
        best_n = cab_nodes[best_c].pop(0)
        if not cab_nodes[best_c]: del cab_nodes[best_c]
        selected.append(best_n)
        temp[best_c] = temp.get(best_c, 0) + 1
    return selected
```

**Unit test assertion (required before freeze commit):**
- `select_random_spread` and `select_fp_spread_canonical` must produce the
  SAME cabinet sequence (same cab selected at each round-robin step) when
  given the same `available` and `cab_active_count`.
- They must produce DIFFERENT node selections within any cabinet that contains
  >1 node (unless FA ordering and choice_priority ordering coincide by chance).
- `select_random_spread` must not import or call FA_dict.

Implementation note: `random_spread` uses `pol_seed` from the existing pol_seeds
array at the POLICY_IDS index for `"full_random_spread"`.

### C2. `fp_global_placebo`

**Rule:** Permute FA values globally across all nodes before the simulation begins,
using `perm_seed = 218767960`.  Then apply the standard FP selector (sort by
permuted FA, ascending).

**Purpose:** Preserves the marginal distribution of FA values across the fleet but
destroys the hostname→FA mapping.  A positive advantage for `fp_global_placebo`
vs `full_random` would indicate that the FP advantage arises from something other
than actual thermal fingerprint ordering (e.g., node numbering or cabinet topology).

**Expected outcome:** `fp_global_placebo` should be indistinguishable from
`full_random` (the permutation destroys the thermal signal).

### C3. `fp_withincab_placebo`

**Rule:** Within each cabinet independently, permute FA values among nodes of that
cabinet using `perm_seed = 365514213`.  Apply the standard FP selector.

**Purpose:** Preserves cabinet-level thermal structure (which cabinet has high vs low
average FA) while destroying node-level FA ordering within each cabinet.

**Expected outcome:** If the FP advantage is driven by between-cabinet FA variation,
`fp_withincab_placebo` should retain a partial advantage.  If the advantage is
driven by within-cabinet node-level FA variation, it should be attenuated relative
to full FP.

### C4. `position_template` (renamed `full_loc`)

**Rule:** Identical to `full_loc` from Gate F.  Selects nodes by ascending
DRAGONFLY_TEMPLATE position index.

**Purpose:** Retains the Gate F Loc comparison for continuity.  Renaming makes the
mechanism explicit in the policy name.

The challenge run output schema refers to this policy as `"position_template"`.
The Gate F `"full_loc"` frozen results are NOT renamed — only the new runs use
the new name.

---

## 8. Phase D — Challenge Run Design

### D1. Scenario Range

- Scenario indices: sc30–sc54 (N=25 held-out challenge scenarios)
- Seeds: from `rng(2042)` as frozen in §4

### D2. Policies (Challenge Run)

Active policies in the challenge run:

| Policy name          | Algorithm         | Status     |
|----------------------|-------------------|------------|
| `full_random`        | Random            | Carry-over |
| `full_fp`            | FP sort ascending | Carry-over |
| `position_template`  | DRAGONFLY_TEMPLATE| Carry-over |
| `full_fp_spread`     | FP + spread       | Carry-over |
| `random_spread`      | Random + spread   | NEW        |
| `fp_global_placebo`  | Global perm FP    | NEW        |
| `fp_withincab_placebo` | Within-cab perm FP | NEW     |

### D3. Ratios

Same as Gate F: [1.0, 1.25, 1.5, 2.0, 4.0, 8.0, unrestricted]

### D4. Preregistered Primary Comparisons (Challenge Run)

**[Amended by Amendment 2 — corrected comparison list; all are direct pairings;
no comparison is inferred by subtraction from separate baselines]**

| # | Policy A | Policy B | Primary question |
|---|----------|----------|-----------------|
| 1 | `full_fp` | `full_random` | Gate F replication — primary success criterion |
| 2 | `full_fp` | `fp_withincab_placebo` | **Node-level ranking contribution** — decisive R1 test |
| 3 | `full_fp` | `fp_global_placebo` | Global confound check |
| 4 | `full_fp_spread` | `random_spread` | **Fingerprint contribution conditional on spreading** |
| 5 | `random_spread` | `full_random` | Spreading contribution alone (no thermal) |
| 6 | `full_fp` | `position_template` | Gate F Loc replication |
| 7 | `full_fp_spread` | `full_fp` | Spread benefit with fingerprint (Gate F replication) |
| 8 | `full_fp_spread` | `position_template` | FPSpread vs topology-only |

Comparisons 2 and 4 are the two decisive new comparisons for this challenge:
- **#2 (FP vs WithinCab-Placebo):** If FP > WithinCab-Placebo, individual node
  thermal ranking contributes beyond cabinet-level structure.  If indistinguishable,
  cabinet identity explains most of the scheduling gain.
- **#4 (FPSpread vs RandomSpread):** If FPSpread > RandomSpread, FA ranking adds
  value even after controlling for cabinet spread.  This is the cleanest isolation
  of the fingerprint signal.

All comparisons:
- Use the frozen delta formula (§H1)
- Report both delta_lo and delta_hi with paired bootstrap 95% CIs
- Report n_definitely_A, n_indistinguishable, n_definitely_B
- Are reported at all 7 ratios

No comparison is inferred by subtracting two separate baseline comparisons.
Each row is a direct paired A vs B test.

### D5. Ratios Reported

All comparisons are reported at all 7 ratios.  Preregistered primary success
criterion uses r=1.25 for the FP vs Random comparison (same as Gate F).

---

## 9. Phase E — Beta and Threshold Sensitivity

These runs use the same sc30–54 challenge scenarios and are executed in parallel
with the main challenge run (same code freeze):

### E1. Cabinet-Reference Sensitivity

Run the primary comparison (FP vs Random) at r=1.25 with cabinet-envelope
scale factors: [0.90, 0.95, 1.00, 1.05, 1.10] applied to all cabinet power
envelopes.

Report C_lower at each scale factor; confirm that sign of the result is stable.

### E2. Beta Sensitivity Runs

**[Amended by Amendment 2 — updated to reflect beta_CF as primary]**

Run the primary comparison (FP vs Random) at r=1.25 with BETA_F set to each of:
- `PRIMARY_BETA_CHALLENGE = beta_CF` from Phase B1  **(primary run)**
- `BETA_F_FROZEN = 1.12484352` — original model estimate (sensitivity)
- `BETA_F_PROSPECTIVE = 0.96` — prospective slope from M1 (sensitivity)
- `BETA_F_JACKKNIFE_MEAN` — mean of per-job jackknife betas from Phase B2a
- `BETA_F_CF_P5, BETA_F_CF_P95` — 5th and 95th percentile of bootstrap CI

Report C_lower and the FP vs Random comparison verdict at each beta value.
Report whether sign and significance are stable across all six beta values.

---

## 10. Phase F — Preflight Gate (12 Conditions)

The following 12 conditions must ALL pass before sc30–54 executes.
Results are recorded in `artifacts/revision2/challenge_preflight.json`.
The preflight script exits non-zero if any condition fails.

1. **Phase A complete:** All A1–A4 output files present and valid.
   A1 recommendation must be "proceed" or "proceed_with_documentation".
   Any "stop_structural_error" recommendation halts the challenge run.
2. **Phase B complete:** Observation-level cross-fit beta_CF computed and written
   to `loo_beta_results.json` as PRIMARY_BETA_CHALLENGE before this preflight runs.
   If cross-fitted estimator could not be defined: halt and document per §B3.
   Jackknife and quarter-wise sensitivities also present in `loo_beta_results.json`.
3. **Phase C complete:** All four new selectors implemented and unit tests pass.
4. **Seed table verified:** scen_seeds and wl_seeds for sc30–54 reproduced exactly
   from rng(2042) in a dry-run (no simulation).
5. **Seed collision audit (complete):**
   - All 25 sc30–54 scen_seeds are distinct from each other.
   - All 25 sc30–54 wl_seeds are distinct from each other.
   - No sc30–54 scen_seed collides with any sc0–29 scen_seed or wl_seed.
   - No sc30–54 wl_seed collides with any sc0–29 scen_seed or wl_seed.
   - placebo_global_perm_seed (218767960) is distinct from all 50 scenario/workload
     seeds above and from placebo_withincab_perm_seed.
   - placebo_withincab_perm_seed (365514213) is distinct from all 50 scenario/workload
     seeds and from placebo_global_perm_seed.
   Full seed lists and collision check results written to preflight JSON.
6. **No untracked or dirty files:** `git_tracked_dirty = False`,
   `git_untracked_count = 0` at the challenge freeze commit.
7. **Frozen constants match:** BETA_F_FROZEN, T_THR_PRIMARY, T_THR_SECONDARY,
   DELTA_CAP reproduced from r1_gate_f_run.py without modification.
   PRIMARY_BETA_CHALLENGE written and non-null in `loo_beta_results.json`.
8. **REVIEW2_CHALLENGE_PLAN.md committed:** Both d28f29d (original preregistration)
   and the amendment commit present in git history; SHAs recorded in preflight JSON.
9. **Gate F evidence intact:** `gate_f_heldout_analysis.json` SHA matches frozen
   value from e16ec3c.
10. **Policy unit tests pass:** All policies produce deterministic outputs given
    same seeds; fp_global_placebo and fp_withincab_placebo differ from full_fp.
11. **Dev preflight sc30 dry-run:** sc30 at r=1.0 produces no invariant_violated
    crossing and finite C values.
12. **Governing-rule acknowledgement:** Operator must manually confirm that no
    policy/metric/threshold/seed/interpretation rule was changed after this plan
    was committed.  Encoded as `operator_acknowledged: true` in preflight JSON.

Preflight JSON schema:
```json
{
  "plan_commits": {
    "original_preregistration": "d28f29d",
    "amendment": "<sha>"
  },
  "preflight_run_at": "<ISO timestamp>",
  "challenge_freeze_commit": "<sha>",
  "primary_beta_challenge": "<float from loo_beta_results.json>",
  "seed_collision_audit": {
    "sc3054_scen_seeds": [25 ints],
    "sc3054_wl_seeds": [25 ints],
    "sc0029_scen_seeds": [30 ints],
    "sc0029_wl_seeds": [30 ints],
    "placebo_global_perm_seed": 218767960,
    "placebo_withincab_perm_seed": 365514213,
    "collisions_found": [],
    "all_unique": bool
  },
  "conditions": {
    "1_phase_a_complete":    {"pass": bool, "notes": str},
    "2_phase_b_complete":    {"pass": bool, "notes": str, "primary_beta": float},
    "3_phase_c_complete":    {"pass": bool, "notes": str},
    "4_seeds_verified":      {"pass": bool, "notes": str},
    "5_seed_collision_audit":{"pass": bool, "notes": str},
    "6_clean_git":           {"pass": bool, "notes": str},
    "7_frozen_constants":    {"pass": bool, "notes": str},
    "8_plan_committed":      {"pass": bool, "notes": str},
    "9_gate_f_intact":       {"pass": bool, "notes": str},
    "10_unit_tests":         {"pass": bool, "notes": str},
    "11_dev_dryrun":         {"pass": bool, "notes": str},
    "12_operator_ack":       {"pass": bool, "notes": str}
  },
  "overall_pass": bool
}
```

---

## 11. Phase G — Challenge Execution (sc30–54)

Only after all 12 preflight conditions pass:

1. Launch challenge run using the parallel launcher (same pattern as Gate F H3).
2. MAX_WORKERS = 8 (same as H3).
3. Per-scenario output files: `gate_f_sc{k}-{k}_r2challenge.json` (k = 30..54).
4. After completion: run merge validator `r2_gate_f_challenge_merge.py`
   (to be written, analogous to `r1_gate_f_merge.py`).
5. After merge: run analysis `r2_gate_f_challenge_analysis.py`
   (analogous to `r1_gate_f_heldout_analysis.py`, using interpretation rules §12).
6. Commit all outputs.

---

## 12. Phase H — Frozen Interpretation Rules

These rules are locked at preregistration.  They must not change after this
document is committed.

### H1. Delta Formula

Identical to Gate F:
```
delta_lo(A, B) = C_lower_A - C_upper_B
delta_hi(A, B) = C_upper_A - C_lower_B
definitely_A_better   iff  delta_lo > 0
definitely_B_better   iff  delta_hi < 0
indistinguishable     otherwise
```

### H2. Bootstrap CIs

5000 resamples, `bootstrap_seed = 9999` (same as Gate F).
Paired across scenarios (same resampling index applied to all policies).
Bias-corrected percentile method.

### H3. Right-Censored Crossings

If a crossing is right-censored (lambda exhausted before crossing found),
it is excluded from the delta computation for that scenario and flagged in output.
If >10% of challenge scenarios are right-censored for the primary comparison,
flag as an anomaly requiring investigation before manuscript use.

### H4. Primary Success Criterion

**FP vs Random at r=1.25 in sc30–54 challenge scenarios:**
- SUCCESS: bootstrap 95% CI for median delta_lo excludes zero from below
  (CI lo > 0) AND n_definitely_A ≥ 20/25
- PARTIAL: n_definitely_A ≥ 15/25 but CI does not fully exclude zero
- FAIL: n_definitely_A < 15/25 or CI includes zero from above (CI hi < 0)

Report outcome verbatim; do not reinterpret.

### H5. Negative Control Assertion (r=1.0)

FP vs Random at r=1.0 must remain indistinguishable (n_definitely_A = 0 AND
n_definitely_B = 0) in sc30–54.  This is a hard assertion, not a soft check.
If violated, the simulation has a bug and results are invalid.

### H6. Placebo Control Interpretation

**[Amended 2026-10-02 — replaces "Expected outcome" language from d28f29d]**

No placebo result is an acceptance criterion.  Every outcome below is
scientifically interpretable and must be reported verbatim.  The branches are
pre-specified; they are not predictions.

**fp_global_placebo vs Random (at r=1.25):**

| Outcome | Pre-specified interpretation |
|---------|------------------------------|
| Indistinguishable | Global permutation destroyed the thermal signal; FP advantage attributable to hostname→FA mapping, not to node numbering or topology artefacts. |
| Definitely A better (≥10/25) | Arbitrary persistent ranking or state effects are a serious alternative explanation for the FP advantage; report as evidence of confounding; qualify all fingerprint claims accordingly in manuscript. |
| Definitely B better | Global placebo systematically underperforms random; indicates permuted FA values displace nodes that would otherwise be selected by random; report without omission. |

**fp_withincab_placebo vs Full FP (magnitude, at r=1.25):**

| Outcome | Pre-specified interpretation |
|---------|------------------------------|
| Full FP >> withincab placebo | Node-level fingerprint ranking within each cabinet contributes materially beyond cabinet-level thermal structure alone. |
| Full FP ≈ withincab placebo | Scheduling value is largely recoverable from cabinet-level topology/structure; node-specific ranking adds little after cabinet identity is preserved. |
| Withincab placebo > Full FP | Unlikely; would indicate within-cabinet permutation selects nodes that happen to be thermal anomalies in the permuted order — report without interpretation beyond what the data support. |

**RandomSpread vs Random (at r=1.25):**

| Outcome | Pre-specified interpretation |
|---------|------------------------------|
| Definitely A better | Cabinet spreading has independent capacity value even without fingerprint information. |
| Indistinguishable | Spreading alone does not drive the observed advantage; the fingerprint component is more important. |

**FPSpread vs RandomSpread (at r=1.25):**

| Outcome | Pre-specified interpretation |
|---------|------------------------------|
| Definitely A better | Fingerprint ranking adds value conditional on spreading (both mechanisms contribute independently). |
| Indistinguishable | After controlling for spread, fingerprint ranking provides no additional gain at this restriction level. |

### H7. Cross-Fitted Beta Reporting

**[Amended by Amendment 2 — reflects observation-level beta_CF, not jackknife mean]**

`beta_CF` (single observation-level LOO cross-fitted estimate from §B1) is the
operating beta for all sc30–54 runs.  Report the following in the manuscript:

- `beta_CF` with bootstrap 95% CI
- `BETA_F_FROZEN = 1.12484352` as the "original model estimate"
- `BETA_F_PROSPECTIVE = 0.96` as the "prospective slope from M1"
- `BETA_F_JACKKNIFE_MEAN` from §B2a as a jackknife sensitivity diagnostic
- Outcome of §E2 sensitivity runs at each beta value

**Interpretation (pre-specified):**

| beta_CF vs BETA_F_FROZEN | Manuscript statement |
|--------------------------|----------------------|
| Within ±2% | LOO cross-fit correction made negligible difference to beta |
| ±2%–10% | Modest self-inclusion correction; direction noted |
| >10% difference | Substantial self-inclusion bias in original estimate; direction noted explicitly |

In all cases: primary challenge results (C_lower, CIs, comparison verdicts) are
reported using `beta_CF`.  Sensitivity results under BETA_F_FROZEN are reported
alongside.  Sign reversal under any sensitivity beta value must be flagged as a
key limitation if it occurs.

### H8. Cabinet-Reference Sensitivity Interpretation

Report the primary result (FP vs Random, r=1.25, median delta_lo) at each
cabinet scale factor [0.90, 0.95, 1.00, 1.05, 1.10].
If sign changes at any scale factor within [0.95, 1.05]: report as a key
limitation.  If sign is stable across [0.90, 1.10]: report as robust.

### H9. FPSpread Crossover Reporting

Report FPSpread vs FP at all ratios with full delta_lo and delta_hi CIs.
Do not claim FPSpread is better than FP at any ratio unless the 95% CI for
delta_lo excludes zero from below.  At r=4.0 in Gate F (CI=[−0.644, +1.740]):
indistinguishable — do not upgrade this to "preferred."

### H10. Comparison to Gate F Primary Result

The challenge run uses different scenarios (sc30–54) from Gate F (sc5–29).
The two sets of 25 scenarios are independent.  Combining them (pooled N=50)
is permitted as a secondary analysis but must be labeled "pooled (non-preregistered)."
The preregistered primary result for each analysis is its own 25-scenario CI.

### H11. Forbidden Post-Hoc Modifications

After Phase G begins, it is forbidden to:
- Change any selector definition
- Change PRIMARY_BETA_CHALLENGE, T_THR_PRIMARY, T_THR_SECONDARY, or DELTA_CAP
- Change BETA_F_FROZEN or BETA_F_PROSPECTIVE sensitivity values
- Change the delta formula or bootstrap parameters
- Add or remove comparisons from the preregistered list
- Change the primary success criterion threshold (§H4)
- Re-label any right-censored scenario as non-censored
- Substitute a different beta estimator (e.g., quarter-wise) for the LOO mean
  without a new pre-results amendment

---

## 13. Phase I — Required Outputs Before Manuscript Editing

The following 13 artifacts must exist, be committed, and be listed in a final
audit before any manuscript text is edited:

1. `artifacts/revision2/REVIEW2_CHALLENGE_PLAN.md` — this document (committed)
2. `artifacts/revision2/cabinet_timeline_audit.json` — A1 output
3. `artifacts/revision2/cabinet_timeline_audit.md` — A1 narrative
4. `artifacts/revision2/prospective_accuracy_by_job_size.json` — A2 output
5. `artifacts/revision2/m1_sensitivity_summary.json` — A3 output
6. `artifacts/revision2/gate_f_manuscript_tables.json` — A4 output
7. `artifacts/revision2/loo_beta_results.json` — Phase B LOO output
8. `artifacts/revision2/challenge_preflight.json` — Phase F preflight (all 12 PASS)
9. `artifacts/revision2/results/gate_f_sc30-54_r2challenge.json` — Phase G merged
10. `artifacts/revision2/challenge_analysis.json` — Phase G analysis (Phases H rules)
11. `artifacts/revision2/sensitivity_cabinet_scale.json` — Phase E1 output
12. `artifacts/revision2/sensitivity_loo_beta.json` — Phase E2 output
13. `artifacts/revision2/final_output_audit.json` — confirms all 12 above present
    and records SHA of each

---

## 14. Execution Order

```
Phase A (parallel tasks — no simulation needed):
  A1 Cabinet timeline audit (potential blocker — run first)
  A2 Prospective accuracy by job size
  A3 M1 sensitivity packaging
  A4 Manuscript tables

Phase B (analysis of existing M4 data — no simulation needed)
  B1 LOO estimator
  B2 Quarter-wise cross-fit

Phase C (implementation — no simulation):
  C1 Implement random_spread
  C2 Implement fp_global_placebo
  C3 Implement fp_withincab_placebo
  C4 Register position_template alias

Phase D/E prep:
  Write r2_gate_f_run.py (extends r1_gate_f_run.py with new policies)
  Write r2_gate_f_challenge_merge.py
  Write r2_gate_f_challenge_analysis.py

Phase F:
  Write r2_challenge_preflight.py
  Run preflight — all 12 conditions must pass

Code freeze commit (clean git, no untracked files)

Phase G:
  Launch sc30-54 parallel run

Phase G post-processing:
  Merge validate
  Run challenge analysis

Phase I:
  Compile final_output_audit.json
  Confirm all 13 outputs present
  Then and only then: manuscript editing authorized
```

---

## Amendment 4 — Governance Gaps Closed Before Challenge Exposure (2026-10-03)

**Pre-results amendment. No challenge scenarios (sc30–54) had been run at the time
this amendment was written. Superseded freezes: 2814bb6 (Amendment 2) and 4ca95fb
(Amendment 3 corrections). New freeze SHA recorded after 15/15 preflight PASS.**

### Gaps identified after Amendment 3

1. **Equivalence test was Stage 1 only.**  
   `r2_vs_r1_equivalence.py` verified sc0–4 seeds and frozen constants but never
   invoked the simulator.  Preflight condition 13 passed even when
   `stage2_simulation.ran = false`.  This is insufficient governance.

2. **Challenge post-processing code not frozen.**  
   `r2_gate_f_challenge_merge.py` and `r2_gate_f_challenge_analysis.py` were listed
   in the execution order (§14) but had not been written.  The analysis rules in §H
   cannot be verified as faithfully implemented until the script is committed and
   regression-tested against known-good outputs.

### Corrections

**G1 — Full simulation equivalence (Stage 2).**  
`r2_gate_f_run.py` is extended with compat-mode env vars:

| Variable | Value for compat | Purpose |
|---|---|---|
| `GATE_F_COMPAT_SEED` | 42 | Replaces rng(2042) with rng(42) |
| `GATE_F_COMPAT_BETA` | 1.12484352 | Replaces PRIMARY_BETA_CHALLENGE with BETA_F_FROZEN |
| `GATE_F_RESTRICT_POLICIES` | full_random,full_fp,position_template,full_fp_spread | 4 r1 policies |
| `GATE_F_COMPAT_N_SCEN` | 30 | Draw 30 scen/wl seeds (matching rng(42) draw count) |
| `GATE_F_COMPAT_POLICY_ORDER` | full_random,full_fp,full_loc,full_compact,marginal_random,marginal_fp,full_fp_spread | Reproduce r1 pol_seed draw order; alias full_loc→position_template |
| `GATE_F_N_FIRST` | 0 | Run sc0–4 |
| `GATE_F_N_DEV` | 5 | 5 scenarios |

Output: `gate_f_sc0-4_*_r2compat.json` (separate from challenge outputs).

`r2_vs_r1_equivalence.py` is rewritten to run Stage 2: invoke r2 in compat mode as a
subprocess, then hard-compare per scenario × policy × ratio × lambda row against the
three frozen r1 dev files.  Comparison rules:

- int/str/bool fields: exact equality
- float fields: `abs(a − b) ≤ 1e-9`
- policy name alias: `full_loc` (r1) treated as `position_template` (r2)
- Fields present in one format but not the other: skipped (e.g. B_secondary_h in r1)
- Crossing dict fields: C_lower_pct, C_upper_pct, status, right_censored, first_binding_constraint

Output: `r2_vs_r1_equivalence.json` with `stage2_simulation.ran = true` and
`stage2_simulation.pass = true` both required.

**G2 — Challenge merge and analysis scripts frozen.**  
`r2_gate_f_challenge_merge.py`: merges per-batch `*_r2challenge.json` files into a
single unified results file covering all sc30–54.

`r2_gate_f_challenge_analysis.py`: implements the 8 preregistered comparisons from §H:

| # | Comparison | Policy A | Policy B | Category |
|---|---|---|---|---|
| 1 | FP_vs_Random | full_fp | full_random | primary |
| 2 | FP_vs_WithinCabPlacebo | full_fp | fp_withincab_placebo | node_level_placebo |
| 3 | FP_vs_GlobalPlacebo | full_fp | fp_global_placebo | global_placebo |
| 4 | RandomSpread_vs_Random | random_spread | full_random | spread_baseline |
| 5 | FPSpread_vs_RandomSpread | full_fp_spread | random_spread | spread_advantage |
| 6 | FPSpread_vs_FP | full_fp_spread | full_fp | spread_vs_fp |
| 7 | FP_vs_PositionTemplate | full_fp | position_template | thermal_vs_position |
| 8 | FPSpread_vs_PositionTemplate | full_fp_spread | position_template | spread_vs_position |

Bootstrap: 5000 paired scenario resamples, seed=9999, percentile CI (same as Gate F).
Right-censored scenarios excluded from pairwise delta computation.

**G3 — Analysis regression test.**  
`r2_analysis_regression.py` applies the analysis engine to the frozen sc5–29 Gate F
outputs and compares against `gate_f_heldout_analysis.json` for the 5 overlapping
comparisons (FP_vs_Random, Loc_vs_Random, FPSpread_vs_Random, FPSpread_vs_FP,
FPSpread_vs_Loc).  Produces `r2_analysis_regression.json` with `overall_pass = true`.
Tolerance for per-scenario delta values: `abs(a − b) ≤ 1e-9`.  Verdicts must match
exactly.

### New preflight conditions (15/15 required for challenge run)

| # | Condition | Change |
|---|---|---|
| 13 | r1↔r2 equivalence (Stage 1) | Strengthened: `stage2_simulation.ran = true` AND `stage2_simulation.pass = true` both required |
| 14 | Full r1↔r2 SIMULATION equivalence | New: zero-mismatch hard comparison from Stage 2 |
| 15 | r2 challenge analysis regression PASS | New: `r2_analysis_regression.json overall_pass = true` |

### What did NOT change

- No selector definitions changed.
- PRIMARY_BETA_CHALLENGE, T_THR_PRIMARY, T_THR_SECONDARY, DELTA_CAP unchanged.
- BETA_F_FROZEN unchanged.
- Delta formula, bootstrap parameters, comparison list unchanged.
- sc30–54 were not touched.

---

## Amendment 5 — Parallel-Worker Seed-Index Correctness Fix (2026-10-03)

**Status:** Pre-results. No sc30–54 scenario had been run when this amendment was written.
**Nature:** Implementation correctness fix. No selector, metric, threshold, comparison,
seed value, or interpretation rule changes.

### Finding

A parallel-worker audit found that `_sc_idx()` in `r2_gate_f_run.py` used `N_FIRST`
as the seed-array base:

```python
def _sc_idx(sc_abs: int) -> int:
    return sc_abs - N_FIRST          # WRONG for parallel workers
```

This is correct for a monolithic sequential run where one process runs the full
contiguous set (e.g., N_FIRST=30 covers sc30–sc54). It is incorrect for
one-scenario parallel workers: a worker launched with N_FIRST=31 would compute
`_sc_idx(31) = 31 − 31 = 0`, selecting seed-array position 0 — the same entry as
sc30. Every independent worker would silently reuse sc30's RNG entries, which would
badly compromise the claimed 25 independent scenarios.

### Fix

Replaced `N_FIRST` with a fixed experiment-relative base:

```python
SEED_INDEX_BASE = 0 if _is_compat else SCENARIO_FIRST

def _sc_idx(sc_abs: int) -> int:
    idx = sc_abs - SEED_INDEX_BASE
    assert 0 <= idx < len(scen_seeds), ...
    return idx
```

For challenge mode: `SCENARIO_FIRST = 30`, so sc30→0, sc31→1, …, sc54→24.
For compat mode: `SEED_INDEX_BASE = 0`, so sc0→0, sc1→1, …, sc4→4.
A worker with N_FIRST=31 now correctly gets sc31→1.

### Seed-index verification table (challenge, sc30–54)

| Scenario | Seed-array index | scen_seed       | wl_seed         |
|----------|-----------------|-----------------|-----------------|
| sc30     | 0               | from rng(2042)  | from rng(2042)  |
| sc31     | 1               | from rng(2042)  | from rng(2042)  |
| …        | …               | …               | …               |
| sc54     | 24              | from rng(2042)  | from rng(2042)  |

All 25 scen_seeds and wl_seeds are distinct (verified by Stage 1 unit test).

### Seed-index verification table (compat, sc0–4)

| Scenario | Seed-array index | scen_seed       | wl_seed         |
|----------|-----------------|-----------------|-----------------|
| sc0      | 0               | from rng(42)    | from rng(42)    |
| sc1      | 1               | from rng(42)    | from rng(42)    |
| …        | …               | …               | …               |
| sc4      | 4               | from rng(42)    | from rng(42)    |

Exact seed values captured in `r2_vs_r1_equivalence.json` →
`stage1_seed_verification.seed_index_table_compat` and
`stage1_seed_verification.seed_index_table_challenge`.

### Stage 2 parallelization

The sc0–4 equivalence test now runs five parallel one-scenario workers
(N_FIRST=i, N_DEV=1 for i in 0..4). The SEED_INDEX_BASE fix ensures each
worker selects its correct seed-array position. Old sequential checkpoint
archived as `SUPERSEDED_pre_amend5_gate_f_sc0-4_r2compat_checkpoint.json`.

### Comparator null-asymmetry fix

`_compare_row()` and `_compare_crossing()` previously silently skipped any
field where one side was None and the other was non-null. The comparator now
treats this as a mismatch (`null_asymmetry: true`). Fields absent from either
schema entirely are counted as `schema_skipped` (not a content mismatch).

### What did NOT change

- CHALLENGE_SEED (2042), COMPAT_SEED (42), all seed values unchanged.
- PRIMARY_BETA_CHALLENGE, BETA_F_FROZEN, T_THR_PRIMARY, T_THR_SECONDARY, DELTA_CAP unchanged.
- All 8 preregistered comparisons unchanged.
- Bootstrap parameters (N=5000, seed=9999), delta formula, interpretation rules unchanged.
- sc30–54 were not touched. Analysis regression (315/315) preserved.

---

*Preregistered on 2026-10-02. No analysis, simulation, or interpretation rules
may change after this document is committed to git.*
