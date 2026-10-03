# REVIEW2_CHALLENGE_PLAN.md
## Preregistered Second-Round Reviewer Challenge Analysis
### ThermalShift — Revision 2

**Date preregistered:** 2026-10-02
**Branch:** revision1/major-revision-analyses
**Preregistration commit:** (set at commit time)

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

**Question:** Were 74 or 77 cabinets active during the study period
(2022-09-01 to 2023-03-31)?  Do the 74 cabinets used in the capacity model
correspond to the cabinets that were actually online during each job?

**Task:**
- Cross-reference `fleet_topology.json` cabinet list against the job start/end
  timestamps in the parquet to determine which cabinet set was active for >90%
  of job-hours.
- Produce `artifacts/revision2/cabinet_timeline_audit.json` with:
  - n_cabs_fleet_topology: int
  - n_cabs_in_job_data: int
  - temporal_match: bool
  - discrepancy_description: str or null
  - recommendation: "proceed" | "stop_and_report" | "flag_in_paper"
- Produce `artifacts/revision2/cabinet_timeline_audit.md` with narrative.

**Outcome rule:**
- If `temporal_match = false` and the discrepancy affects ≥5% of job-hours:
  STOP.  Do not proceed with challenge simulation.  Report as scientific blocker.
- If discrepancy is ≤5% or affects only inactive cabinets: flag in paper, proceed.

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

### B1. LOO Estimator

For each job j in the M4 training set, compute F_i^(-j) (FA excluding job j)
and re-fit the linear model T_peak ~ location_effect + BETA * F_i^(-j).
Record BETA_F^(-j) for each excluded job.

Report: mean, std, min, max, percentile distribution of BETA_F^(-j) over all j.

### B2. Quarter-Wise Cross-Fit

Partition jobs into four calendar quarters (Q4-2022, Q1-2023, Q2-2023, Q3-2023
or as available).  For each quarter q, train on jobs NOT in quarter q and report
BETA_F^(-q).

Report: BETA_F^(-q) for each quarter, and the range across quarters.

### B3. Primary Beta Choice (Frozen Before Challenge Run)

After reviewing LOO and quarter-wise results, record here the primary beta choice
for the challenge analysis:

```
PRIMARY_BETA_CHOICE = BETA_F_FROZEN = 1.12484352   [LOCKED — do not change after commit]
```

If LOO perturbations exceed ±5% from BETA_F_FROZEN (i.e., any BETA_F^(-j)
falls outside [1.068, 1.181]), flag this as a sensitivity note in the paper.
Do NOT change the primary beta: BETA_F_FROZEN is locked by the Gate F
preregistration (commit 86a95ec) and the H3 equivalence check (commit e2df32a).

LOO results are reported as a sensitivity robustness check, not as a reason to
re-estimate.

---

## 7. Phase C — New Selector Implementation

Four new policies are added for the challenge run.  All must be implemented,
unit-tested, and code-frozen before sc30–54 executes.

### C1. `random_spread`

**Rule:** Round-robin cabinet selection (same spread mechanism as `full_fp_spread`),
but within each cabinet choose nodes uniformly at random rather than by ascending FA.

**Purpose:** Isolates the cabinet-spread effect from the fingerprint-sorting effect.
- `random_spread` vs `full_random`: spread effect alone (no fingerprint)
- `full_fp_spread` vs `random_spread`: fingerprint effect under spread
- `full_fp_spread` vs `full_fp`: spread effect with fingerprint

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

1. **FP vs Random** (replication of Gate F primary; primary success criterion)
2. **FP_global_placebo vs Random** (R1 confounding check; expected: indistinguishable)
3. **FP_withincab_placebo vs Random** (R1 partial-confounding check)
4. **RandomSpread vs Random** (R2 spread-only effect)
5. **FPSpread vs RandomSpread** (R2 fingerprint effect under spread)
6. **FPSpread vs FP** (R2 spread benefit, replication)
7. **PositionTemplate vs Random** (replication of Gate F Loc comparison)

All comparisons use the delta formula frozen below (§10).

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

### E2. LOO Beta Sensitivity

Run the primary comparison (FP vs Random) at r=1.25 with BETA_F replaced by:
- BETA_F_FROZEN (primary)
- mean(BETA_F^(-j)) from Phase B
- percentile-5 and percentile-95 of the LOO distribution

Report C_lower at each beta; confirm that sign of the result is stable.

---

## 10. Phase F — Preflight Gate (12 Conditions)

The following 12 conditions must ALL pass before sc30–54 executes.
Results are recorded in `artifacts/revision2/challenge_preflight.json`.
The preflight script exits non-zero if any condition fails.

1. **Phase A complete:** All A1–A4 output files present and valid.
   A1 `temporal_match` must be true OR discrepancy documented as ≤5%.
2. **Phase B complete:** LOO results present; PRIMARY_BETA_CHOICE locked to
   BETA_F_FROZEN.
3. **Phase C complete:** All four new selectors implemented and unit tests pass.
4. **Seed table verified:** scen_seeds and wl_seeds for sc30–54 reproduced exactly
   from rng(2042) in a dry-run (no simulation).
5. **Placebo seeds verified:** placebo_global_perm_seed and
   placebo_withincab_perm_seed reproduced exactly from rng(2042).
6. **No untracked or dirty files:** `git_tracked_dirty = False`,
   `git_untracked_count = 0` at the challenge freeze commit.
7. **Frozen constants match:** BETA_F_FROZEN, T_THR_PRIMARY, T_THR_SECONDARY,
   DELTA_CAP reproduced from r1_gate_f_run.py without modification.
8. **REVIEW2_CHALLENGE_PLAN.md committed:** This file present in git history,
   commit SHA recorded in preflight JSON.
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
  "plan_commit": "<sha>",
  "preflight_run_at": "<ISO timestamp>",
  "challenge_freeze_commit": "<sha>",
  "conditions": {
    "1_phase_a_complete":    {"pass": bool, "notes": str},
    "2_phase_b_complete":    {"pass": bool, "notes": str},
    "3_phase_c_complete":    {"pass": bool, "notes": str},
    "4_seeds_verified":      {"pass": bool, "notes": str},
    "5_placebo_seeds":       {"pass": bool, "notes": str},
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

**fp_global_placebo vs Random:**
- Expected: indistinguishable (no advantage; global permutation destroys signal)
- If definitely_A_better for ≥10/25 scenarios at r=1.25: ANOMALY — report as
  evidence of confounding; do not claim thermal fingerprint effect in manuscript.

**fp_withincab_placebo vs Random:**
- Expected: attenuated relative to full FP (some advantage possible if
  between-cabinet variation drives part of the effect)
- Report the magnitude relative to full FP without prejudging direction.

### H7. LOO Stability

If any BETA_F^(-j) from Phase B exceeds ±5% from BETA_F_FROZEN, include a
sensitivity note in the manuscript: "Results are qualitatively robust to
leave-one-job-out beta perturbation (range [min, max])."
Do NOT change the primary beta.

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
- Change BETA_F_FROZEN, T_THR_PRIMARY, T_THR_SECONDARY, or DELTA_CAP
- Change the delta formula or bootstrap parameters
- Add or remove comparisons from the preregistered list
- Change the primary success criterion threshold
- Re-label any right-censored scenario as non-censored

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

*Preregistered on 2026-10-02. No analysis, simulation, or interpretation rules
may change after this document is committed to git.*
