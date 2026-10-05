# Reviewer Response — Review-2 (ThermalShift)

**Prepared from frozen challenge evidence at commit f1c78a3.**
**Numerical claims are grounded in frozen artifacts; full provenance in `final_output_audit.json`.**

---

## N1: Node-Level vs. Cabinet-Level Confounding

**Concern:** The fingerprint scheduling advantage could reflect cabinet-level structure or other
correlated signals rather than individual node-level thermal identity.

**What we did:** Designed, preregistered, and executed a 25-scenario held-out challenge
experiment (sc30–sc54) with a factorial placebo structure. The scientific code and analysis
plan were frozen at Git commit 5733b73 before any scenario was executed. The 16/16 preflight
gate — including Stage 2 simulation equivalence (condition 14), analysis regression test
(condition 15), and seed-index correctness (condition 16, Amendment 5) — passed before any
scenario ran. After all 25 scenarios completed, a separate completion audit verified scenario
completeness, seeds, provenance hashes, absence of NaN/Inf, and invariant conditions before
the frozen analysis was run.

**Primary result (H4):** At the preregistered 1.25× choice ratio, fingerprint-guided placement
produced a median conservative bracket separation of **+6.71 pp** versus random placement
(bootstrap 95% CI [+3.92, +8.72] pp; 22/25 scenarios definitely FP-first, 1 indistinguishable,
2 definitely random). delta_lo = C_lower(FP) − C_upper(Random) is a strict lower bound on
the capacity separation.

**Factorial comparisons at r = 1.25:**

| Comparison | A / I / B | Median delta_lo | Bootstrap 95% CI |
|---|---|---|---|
| **FP vs Random** (primary) | **22 / 1 / 2** | +6.71 pp | [+3.92, +8.72] |
| **FP vs WithinCabPlacebo** (node-specificity) | **20 / 5 / 0** | +3.54 pp | [+0.56, +4.44] |
| FP vs GlobalPlacebo | 22 / 1 / 2 | +4.55 pp | [+2.95, +7.82] |
| FPSpread vs RandomSpread | 20 / 5 / 0 | +2.15 pp | [+0.52, +4.25] |
| RandomSpread vs Random | 8 / 14 / 3 | 0.00 pp | [−0.26, +0.03] |
| FPSpread vs FP | 4 / 3 / **18** | −2.64 pp | [−4.49, −2.00] |
| FP vs PositionTemplate | 16 / 5 / 4 | +0.74 pp | [−0.82, +1.50] |
| FPSpread vs PositionTemplate | 6 / 11 / 8 | −1.16 pp | [−2.29, −0.25] |

**Pattern of evidence:** The within-cabinet permutation placebo (FP vs WithinCabPlacebo,
20/25, +3.54 pp) preserves cabinet-level score composition while breaking individual
node-fingerprint associations; its positive separation provides held-out evidence that
individual node identity contributes beyond cabinet membership. FPSpread beating
RandomSpread (20/25, +2.15 pp) shows fingerprint ranking adds value beyond spreading
mechanics. RandomSpread vs Random (0.00 pp) confirms the primary-ratio improvement is not
explained by spreading alone. The global placebo (22/25, +4.55 pp) shows the effect is not
reproduced by an arbitrary globally permuted ranking.

**Negative control (r = 1.0):** All 8 comparisons: 0 / 25 / 0 — no spurious separation
where the scheduler has no candidate choice.

**Important limitation — position template:** Fingerprint-guided placement was **not
statistically separated** from the thermally informed structural-position template (16/5/4,
median +0.74 pp, 95% CI [−0.82, +1.50] pp, spanning zero). The position template is not a
purely topological index; it reflects average historical fingerprint scores at each physical
position (chassis/slot/board/node_pos). We do not claim fingerprints outperform all thermally
informed placement strategies.

**Secondary finding — FPSpread crossover (preregistered):** FPSpread underperforms FP at
limited choice ratios (r = 1.25: −2.64 pp) but outperforms at large choice sets (r = 8.0:
+0.72 pp, unrestricted: +2.01 pp). This crossover was preregistered before challenge
execution and replicated exactly in sc30–sc54. A plausible interpretation — explicitly labeled
as an interpretation, not a tested causal mechanism — is that spreading restricts direct
exploitation of the most favorable nodes under constrained choice, while fingerprint and
spreading become complementary at larger choice sets.

**Change to manuscript:**

> Persistent node-level thermal fingerprints provide held-out scheduling value beyond random
> placement, within-cabinet permutation placebos, and spreading alone under the
> constraint-aware replay model. Fingerprint-guided placement was not statistically separated
> from the thermally informed structural-position template at the primary choice ratio.

**Provenance:** Frozen commit 5733b73; evidence freeze f1c78a3; preflight: PASS (16/16
conditions); completion audit: PASS; 25 scenarios; 5,000 bootstrap replicates, seed 9999;
13/13 Phase I artifacts verified (`final_output_audit.json`, overall PASS).

---

## N2: Cabinet Count, Timeline, and Envelope Calibration

**Concern:** Were 74 or 77 cabinets active during the study? Is the cabinet-power model
sensitive to ±5–10% changes in the power envelope?

**What we did:** (A1) Cross-referenced fleet topology against job-placement records to verify
when each cabinet first appeared. (E1) Ran the primary comparison (FP_vs_Random, r = 1.25)
across five prespecified cabinet-envelope scale factors using the 25 held-out scenarios.

**A1 result:** All 2,637 test-set jobs ran after all 77 cabinets first appeared in job-placement
records. Three cabinets (2600–2602) first appeared 183–309 days into the study period (mean
6–24 training observations vs. fleet mean 39) and have strongly negative FA_2024 means
(−1.24 to −2.22 vs. fleet mean +0.03). Their 78 cohort nodes are documented as a calibration
concern but not a structural error — the test period post-dates their first job-placement
record. Recommendation: **proceed_with_documentation**.

**E1 result (H8 = ROBUST):**

| Scale | n_A / n_I / n_B | Median delta_lo | Bootstrap 95% CI |
|---|---|---|---|
| 0.90 | 18 / 6 / 1 | +0.81 pp | [+0.002, +2.38] |
| 0.95 | 21 / 4 / 0 | +2.98 pp | [+0.55, +4.28] |
| **1.00 (primary)** | **22 / 1 / 2** | **+6.71 pp** | **[+3.92, +8.72]** |
| 1.05 | 20 / 3 / 2 | +4.40 pp | [+3.20, +5.54] |
| 1.10 | 20 / 2 / 3 | +4.69 pp | [+0.87, +5.33] |

Sign positive at all five scale factors. **H8 = ROBUST.** Artifact: `sensitivity_cabinet_scale.json`
(commit 0aa995e).

**Change to manuscript:** Add: "The primary comparison is robust to ±10% cabinet-envelope
calibration error (H8 = ROBUST). At −10% scale, the advantage is substantially attenuated
(median +0.81 pp, 95% CI [+0.002, +2.38] pp)."

**Remaining limitation:** At scale = 0.90 the CI barely clears zero. Calibration error beyond
±10% was not tested. Post-exposure disclosure: E1 was prespecified at commit 5733b73 but
executed after primary results were exposed; the design was not changed
(`POST_EXPOSURE_SENSITIVITY_RECOVERY.md`).

---

## N3: Beta Self-Inclusion and LOO Correction

**Concern:** BETA_F and the fingerprints are derived from the same 2024 training-job set,
creating potential self-inclusion bias. How sensitive are Gate F results to leave-one-job-out
perturbations of the beta estimate?

**What we did:** Applied an Amendment-3 per-job leave-one-out cross-fitting procedure over
all 462 qualifying 2024 training jobs. For each qualifying job j: (1) exclude j from node i's
fingerprint estimate to construct F_CF[i,j]; (2) fit the per-job slope β_{j,CF} following the
same procedure as the original estimator; (3) repeat for all 462 qualifying jobs; (4) set
PRIMARY_BETA_CHALLENGE = median_j(β_{j,CF}). The bootstrap (5,000 replicates, seed 9999)
resamples the 462 per-job LOO betas by job. This is a job-level LOO median, not a pooled
regression on the cross-fitted observation set.

**Results:**

| Estimator | Value | Notes |
|---|---|---|
| BETA_F_FROZEN (original) | 1.12484352 | 462 qualifying 2024 training jobs |
| **PRIMARY_BETA_CHALLENGE** | **1.11416358** | **Amendment-3 LOO median; −0.95%** |
| Bootstrap 95% CI | [1.06587054, 1.16910447] | Resampling 462 per-job betas |
| Pooled FE slope | 1.08293343 | Secondary diagnostic; not primary estimator |
| Jackknife mean β | 1.08293397 | Prespecified sensitivity diagnostic |

The −0.95% correction is within the pre-specified ±2% negligible-correction threshold (§H7,
`REVIEW2_CHALLENGE_PLAN.md`). All sc30–sc54 runs used PRIMARY_BETA_CHALLENGE = 1.11416358.

E2 beta sensitivity (H7): no sign reversal across 6 prespecified beta values spanning
[0.96, 1.17]. **H7 = STABLE.** Artifact: `loo_beta_results.json`; `sensitivity_loo_beta.json`
(commit 0aa995e).

**Change to manuscript:** "The primary challenge runs used a per-job LOO cross-fitted beta
(PRIMARY_BETA_CHALLENGE = 1.11416358, −0.95% from BETA_F_FROZEN, within the prespecified
negligible-correction threshold). The qualitative direction is stable across six prespecified
beta values spanning [0.96, 1.17] (H7 = STABLE)."

---

## N4: Thermal Threshold Sensitivity

**Concern:** Are results sensitive to the thermal threshold T_thr used in the cabinet power
model?

**Finding:** T_thr = 63.625°C (primary) / 60.602°C (secondary) was fixed at Gate F calibration
and was not varied in the Review-2 protocol. The E1 cabinet-envelope scale sensitivity (N2)
tests a different calibration dimension — overall cabinet power envelope scaling — and is not
equivalent to T_thr sensitivity. E1's H8 = ROBUST result provides indirect evidence that
calibration error in the power model does not change the qualitative direction of the advantage,
but direct T_thr sensitivity was not isolated and is a documented limitation.

**Change to manuscript / limitation:** "Direct sensitivity to T_thr was not prespecified or
tested in Review-2. E1 cabinet-scale sensitivity (H8 = ROBUST) tests a related but distinct
calibration dimension and does not substitute for T_thr variation. This is a documented
limitation."

---

## N5: Job-Size Heterogeneity

**Concern:** Does the fingerprint scheduling effect vary across job sizes?

**What we did:** Stratified M1 prospective fingerprint prediction accuracy by job-size bin
across 2,637 test-set jobs (fingerprints from 2024 training; accuracy measured against 2025
outcomes). Artifact: `prospective_accuracy_by_job_size.json`.

**Results:**

| Size bin | n_jobs | Pearson r | R² | Sign agreement |
|---|---|---|---|---|
| 1–32 | 1,079 | 0.558 | 0.279 | 77.4% |
| 33–128 | 1,147 | 0.599 | 0.359 | 79.0% |
| 129–512 | 411 | 0.378 | 0.143 | 75.0% |
| 513–2048 / 2049+ | 0 | — | — | — |

All populated bins show positive Pearson r and >75% sign agreement. The 129–512 bin has
lower out-of-sample R² (0.14), which we acknowledge.

**Change to manuscript / limitation:** "Prospective fingerprint accuracy is positive across all
populated job-size bins. The 129–512 range shows lower R² (0.14) than smaller bins (0.28–0.36).
Per-size-bin scheduling advantage was not prespecified in the challenge protocol; the reported
advantage is a scenario-level result over mixed-size workloads."

---

## N6: Metric Definitions and Formulas

**Concern:** Clarification of the conservative bracket separation metric, delta formula, and
bootstrap procedure.

**Definitions (frozen at `REVIEW2_CHALLENGE_PLAN.md` §H1):**

| Term | Definition |
|---|---|
| C_lower(policy) | Conservative lower interpolation bound of the capacity-yield crossing lambda |
| C_upper(policy) | Conservative upper bound |
| delta_lo(A, B) | C_lower(A) − C_upper(B) |
| definitely_A_better | delta_lo > 0 |
| indistinguishable | delta_lo ≤ 0 AND delta_hi ≥ 0 |
| definitely_B_better | delta_hi < 0 |

A positive delta_lo means the lower bound of A's bracket exceeds the upper bound of B's —
a strict lower bound on the actual capacity separation.

**Bootstrap:** 5,000 paired scenario resamples, seed 9999, percentile CI. Scenarios are
resampled paired across all policies simultaneously.

**Unit note:** The authoritative Gate-F source is `gate_f_heldout_analysis.json` (values in pp;
FP_vs_Random r = 1.25: median delta_lo = 4.771 pp). The packaging artifact
`gate_f_manuscript_tables.json` (A4) contains a ×100 formatting defect (e.g., 477.103 instead
of 4.771 pp) and is not authoritative for numerical claims. The Review-2 challenge analysis
(`challenge_analysis.json`) stores values in pp, consistent with `gate_f_heldout_analysis.json`.

---

## N7: Preregistration, Provenance, and Reproducibility

**Concern:** How was the analysis protected from post-hoc modification? What is the full
provenance?

**Preregistration:** Scientific runner and analysis plan frozen at commit 5733b73 before any
sc30–sc54 scenario was executed. The 16-condition preflight — including Stage 2 simulation
equivalence (replicating Gate F sc0–sc4 at 1e-9 tolerance), analysis regression test (315/315
output cells), and challenge seed-index correctness (condition 16, Amendment 5) — passed before
challenge execution. All comparison hypotheses, the beta value, bootstrap parameters, delta
formula, and interpretation rules were frozen at 5733b73 and not changed after execution.

**Batch audit correction (v1 → v2):** A post-execution audit found that the v1 batch-transition
checker recorded expected metadata for each sensitivity run but did not compare against observed
values, meaning "15/15 PASS" in v1 records did not verify correct configuration. The v2
corrected checker performs hard numeric comparison at 1e-10 tolerance and terminates with FAIL
on any mismatch. All 9 non-baseline sensitivity runs were re-audited under v2; all passed.
Records in `batch_transition_audit.json` are labeled `superseded_by_v2_corrected_audit` (v1)
or `authoritative` (v2).

**Post-exposure disclosure:** E1 and E2 were prespecified at commit 5733b73 but executed after
primary challenge results were exposed, due to an omission discovered during post-analysis
review. The design (scale factors, beta values, comparisons, H7/H8 interpretation rules) was
not changed after exposure. Full disclosure: `POST_EXPOSURE_SENSITIVITY_RECOVERY.md`.

**Provenance:**

| Item | Value |
|---|---|
| Frozen commit | 5733b73 |
| Evidence freeze | f1c78a3 |
| Preflight | PASS (16/16 conditions, before execution) |
| Completion audit | PASS (after scenarios, before analysis) |
| n_scenarios | 25 (sc30–sc54) |
| Bootstrap | 5,000 replicates, seed 9999 |
| Sensitivity recovery | commit 0aa995e (E1/E2 + Phase I audit) |
| Phase I artifacts | 13/13 (final_output_audit.json, overall PASS) |

**Change to manuscript:** "The scientific runner and analysis plan were frozen before any
challenge scenario was executed. The 16/16 preflight gate passed before sc30–sc54 ran; a
separate completion audit passed after all scenarios completed and before the frozen analysis
ran. All artifacts are traceable to frozen commits; full provenance is in `final_output_audit.json`."
