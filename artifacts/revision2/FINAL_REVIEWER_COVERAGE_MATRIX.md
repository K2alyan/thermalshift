# Final Reviewer Coverage Matrix

**Purpose:** For every reviewer concern (N1–N7) document what evidence was collected,
the exact result, the required manuscript language, and wording constraints.

**Frozen result sources:**
- `artifacts/revision2/challenge_analysis.json` — 8 preregistered comparisons (sc30–54)
- `artifacts/revision2/sensitivity_cabinet_scale.json` — E1 (H8 verdict)
- `artifacts/revision2/sensitivity_loo_beta.json` — E2 (H7 verdict)
- `artifacts/revision2/loo_beta_results.json` — LOO cross-fit
- `artifacts/revision2/prospective_accuracy_by_job_size.json` — A2
- `artifacts/revision2/cabinet_timeline_audit.json` — A1
- `artifacts/revision2/final_output_audit.json` — Phase I 13/13

---

## N1: Node-Level vs. Cabinet-Level Confounding

**Reviewer concern:** The fingerprint scheduling advantage could reflect cabinet-level
structure (nodes being in cooler cabinets) rather than individual node-level thermal
identity. The original experiment cannot isolate the contribution of node-specific
fingerprint ranking.

**Challenge designed for:** Preregistered factorial placebo decomposition (sc30–54, §D4)
with three confound-control comparisons: within-cabinet permutation placebo, global
permutation placebo, and cabinet spreading controls.

| Sub-issue | Analysis | Key result | Source |
|---|---|---|---|
| Primary replication | FP_vs_Random at r=1.25 | **22/25 definitely FP, +6.71 pp, CI [+3.92, +8.72] pp** — primary_success | challenge_analysis.json |
| Node-level ranking (decisive) | FP_vs_WithinCabPlacebo at r=1.25 | **20/25 definitely FP, +3.54 pp, CI [+0.56, +4.44] pp** | challenge_analysis.json |
| Global confound | FP_vs_GlobalPlacebo at r=1.25 | 22/25 definitely FP, +4.55 pp, CI [+2.95, +7.82] pp | challenge_analysis.json |
| Spread contribution | FPSpread_vs_RandomSpread at r=1.25 | **20/25 definitely FPSpread, +2.15 pp, CI [+0.52, +4.25] pp** | challenge_analysis.json |
| Spread-alone | RandomSpread_vs_Random at r=1.25 | 8/14/3, **0.00 pp, CI [−0.26, +0.03] pp** | challenge_analysis.json |
| FPSpread cost | FPSpread_vs_FP at r=1.25 | 4/3/18, **−2.64 pp, CI [−4.49, −2.00] pp** | challenge_analysis.json |
| Position template | FP_vs_PositionTemplate at r=1.25 | **16/5/4, +0.74 pp, CI [−0.82, +1.50] pp** (CI includes zero) | challenge_analysis.json |
| Negative control | All comparisons at r=1.0 | 0 definitely-A, 25 indistinguishable, 0 definitely-B for all 8 | challenge_analysis.json |

**Manuscript section:** Add after Gate F held-out results. Update limitations to reflect position-template non-separation.

**Reviewer response section:** N1 — COMPLETE (reviewer_response_r2.md, full section written)

**Wording constraints (mandatory):**
- "provides held-out evidence that … contributes … beyond cabinet-level structure" — NOT "proves" or "directly isolates"
- "within the historical operating-envelope replay model" — required qualifier
- Must state position-template non-separation: "Fingerprint-guided placement was not statistically separated from the thermally informed structural-position template at the primary choice ratio (16/5/4, +0.74 pp, CI [−0.82, +1.50] pp)."
- Do NOT claim FPSpread improves over FP at r=4.0 in Gate F (CI included zero)
- RandomSpread_vs_Random result must be reported: spreading alone shows no primary-ratio advantage

**Status:** Evidence complete. Reviewer response written. Manuscript update required.

---

## N2: Cabinet Count, Timeline, and Envelope Calibration

**Reviewer concern (R4 + R6):** Were 74 or 77 cabinets active during the study period?
Does the cabinet-power model use the temporally correct count? Are results sensitive to
±5–10% changes in the cabinet power envelope?

| Sub-issue | Analysis | Key result | Source |
|---|---|---|---|
| Cabinet count and timeline | A1 cabinet timeline audit | **All 2,637 test-set jobs ran on or after 2024-11-22; all 77 cabinets were first observed in job-placement records before the test period.** Recommendation: proceed_with_documentation. | cabinet_timeline_audit.json |
| Late-observed cabinets | A1b exploratory diagnostic | Cabinets 2600/2601/2602 first appeared 183–309 days into study; 78 cohort nodes (3.9%). Not a structural error. | cabinet_timeline_audit.json |
| Cabinet-envelope sensitivity | E1 at scale 0.90–1.10 | **H8 verdict: ROBUST. Sign positive at all 5 scale factors.** Weakest at scale=0.90 (+0.81 pp, CI [+0.002, +2.38]) but median positive. | sensitivity_cabinet_scale.json |

**E1 results table (FP_vs_Random at r=1.25, 25 scenarios):**

| Cab scale | n_A / n_I / n_B | Median delta_lo | 95% CI |
|---|---|---|---|
| 0.90 | 18 / 6 / 1 | +0.81 pp | [+0.002, +2.38] |
| 0.95 | 21 / 4 / 0 | +2.98 pp | [+0.55, +4.28] |
| 1.00 (primary) | 22 / 1 / 2 | +6.71 pp | [+3.92, +8.72] |
| 1.05 | 20 / 3 / 2 | +4.40 pp | [+3.20, +5.54] |
| 1.10 | 20 / 2 / 3 | +4.69 pp | [+0.87, +5.33] |

**H8 rule (frozen):** "Sign stable across [0.90, 1.10] → ROBUST." No sign change at any scale. Inner window [0.95, 1.05] entirely positive. H8 = ROBUST ✓

**Wording constraints:**
- "Results are robust to ±10% cabinet-envelope scaling (H8 = ROBUST)" — permitted
- At scale=0.90, the CI just clears zero ([+0.002, +2.38]); do NOT claim this is as strong as the primary result
- Must acknowledge late-observed cabinets (A1b) as a documented limitation, not a finding of error
- "proceed_with_documentation" — not "no problem found"; document the late-cab diagnostic in manuscript limitations

**Reviewer response section:** N2 — NOT YET WRITTEN

**Manuscript section:** Add to sensitivity results section; add late-cab diagnostic to limitations.

**Status:** Evidence complete (artifacts #2, #3, #11 in Phase I). Reviewer response N2 must be written.

---

## N3: Beta Self-Inclusion and LOO Correction

**Reviewer concern (R3):** BETA_F = 1.12484352 is estimated from the same 30 jobs used
in training the fingerprint. How sensitive are Gate F results to leave-one-job-out
perturbations of BETA_F?

| Sub-issue | Analysis | Key result | Source |
|---|---|---|---|
| LOO cross-fit (primary) | B1 — observation-level LOO cross-fit over 462 training jobs | **PRIMARY_BETA_CHALLENGE = 1.11416358; −0.95% from BETA_F_FROZEN; within ±2% → "negligible correction" (§H7 rule)** | loo_beta_results.json |
| Bootstrap CI | B1 — job-cluster bootstrap (n=5000) | **95% CI: [1.06587054, 1.16910447]** | loo_beta_results.json |
| Jackknife (diagnostic) | B2a — per-job beta distribution | BETA_F_JACKKNIFE_MEAN = 1.08293397; 462 jobs; mean=1.151, std=0.448 | loo_beta_results.json |
| Beta range sensitivity (E2) | 6 prespecified beta values at r=1.25 | **H7 verdict: STABLE. No sign reversal across any beta value.** | sensitivity_loo_beta.json |

**E2 results table (FP_vs_Random at r=1.25, 25 scenarios):**

| Beta label | Value | n_A / n_I / n_B | Median delta_lo |
|---|---|---|---|
| primary (LOO CF) | 1.11416358 | 22 / 1 / 2 | +6.71 pp |
| beta_f_frozen | 1.12484352 | 22 / 1 / 2 | +6.48 pp |
| prospective (M1) | 0.96 | 22 / 1 / 2 | +6.67 pp |
| jackknife mean | 1.08293397 | 22 / 1 / 2 | +5.59 pp |
| cf_p5 (5th pct) | 1.06587054 | 21 / 2 / 2 | +6.42 pp |
| cf_p95 (95th pct) | 1.16910447 | 22 / 1 / 2 | +5.35 pp |

**Post-exposure disclosure:** E2 sensitivity runs were prespecified at commit 5733b73 but
executed after primary challenge results (Phase G) were exposed, due to an omission
discovered during post-analysis review. The design (parameters, comparisons, interpretation
rules) was not changed after exposure. Full disclosure in POST_EXPOSURE_SENSITIVITY_RECOVERY.md
and final_output_audit.json.

**Wording constraints:**
- "LOO cross-fitted estimate reduced BETA_F by 0.95%, within the pre-specified ±2% negligible-correction threshold" — permitted
- "sensitivity to beta choice is negligible for the primary comparison result" — permitted under H7 STABLE
- Do NOT claim E2 was executed before primary results — disclose the post-exposure timing
- JACKKNIFE_MEAN is a "sensitivity diagnostic" not a primary estimand — do not upgrade it
- Do NOT use BETA_F_FROZEN as the primary operating beta for Review-2 — PRIMARY_BETA_CHALLENGE is 1.11416358

**Reviewer response section:** N3 — NOT YET WRITTEN

**Status:** Evidence complete (artifacts #7, #12 in Phase I). Reviewer response N3 must be written.

---

## N4: Thermal Threshold Sensitivity

**Reviewer concern (R6):** Are results sensitive to the thermal threshold T_thr used in
cabinet power modeling?

| Sub-issue | Analysis | Key result | Source |
|---|---|---|---|
| Cabinet-envelope scaling (proxy) | E1 at ±10% scale | **H8=ROBUST**: sign stable at all 5 scale factors. This addresses calibration error in cabinet power envelopes. | sensitivity_cabinet_scale.json |
| T_thr value | Frozen constant from revision1 | T_THR_PRIMARY = 63.625°C; T_THR_SECONDARY = 60.602°C. These were fixed at Gate F and not varied in sensitivity runs. | REVIEW2_CHALLENGE_PLAN.md §3 |

**Limitation to acknowledge:** Direct T_thr sensitivity (varying the threshold itself) was not
a prespecified sensitivity run in Review-2. The E1 cabinet-scale sensitivity addresses
calibration uncertainty in the power envelope but does not directly test T_thr variation.
This should be stated honestly.

**Wording constraints:**
- "Cabinet-envelope calibration uncertainty of ±10% was tested directly (E1: H8=ROBUST)" — permitted
- "Direct sensitivity to T_thr was not tested in the Review-2 challenge protocol" — must acknowledge
- Do NOT imply E1 addressed T_thr; it addressed cabinet-envelope scaling only

**Reviewer response section:** N4 — NOT YET WRITTEN (brief section needed)

**Status:** Evidence partially complete (E1 covers cabinet-scale sensitivity). Direct T_thr sensitivity is a documented gap; must be stated as such.

---

## N5: Job-Size Heterogeneity and Effect Generalization

**Reviewer concern (R5):** Does the FP effect vary across job sizes? The reviewer may
suspect the 129–512 node range dominates the advantage.

| Sub-issue | Analysis | Key result | Source |
|---|---|---|---|
| Prospective fingerprint accuracy by job size | A2 — stratify M1 accuracy by size bin | All three populated bins show positive Pearson r and >75% sign agreement. See table below. | prospective_accuracy_by_job_size.json |
| Scheduling advantage by job size | Not directly tested in challenge | Challenge scenarios mix job sizes from test set. Per-size-bin capacity advantage was not prespecified. | N/A |

**A2 results (prospective fingerprint prediction accuracy by job-size bin):**

| Size bin | n_jobs | n_obs | Pearson r | R²_frozen | Sign agreement |
|---|---|---|---|---|---|
| 1–32 | 1,079 | 7,703 | 0.558 | 0.279 | 77.4% |
| 33–128 | 1,147 | 28,154 | 0.599 | 0.359 | 79.0% |
| 129–512 | 411 | 28,688 | 0.378 | 0.143 | 75.0% |
| 513–2048 | 0 | — | — | — | — |
| 2049+ | 0 | — | — | — | — |
| **Overall** | 2,637 | 64,545 | 0.455 | 0.206 | 77.0% |

**Key findings:**
- The 129–512 node bin has the lowest predictive accuracy (R²=0.143, r=0.378) but still positive
- The 1–32 and 33–128 bins dominate the test set by job count (1,079 and 1,147 of 2,637 jobs)
- All bins show positive correlation and >75% sign agreement
- No size bin shows the fingerprint performing at chance or negatively

**Limitation:** Per-size-bin scheduling advantage was not prespecified for the challenge.
The reported per-scenario variation in ΔC is genuine but its structural drivers (including
whether job-size mix per scenario matters) are not identified.

**Wording constraints:**
- "Fingerprint prediction accuracy is positive across all job-size bins in the test set" — permitted
- "The 129–512 node range shows lower R² (0.14) than smaller bins" — must acknowledge
- Do NOT claim job-size-specific scheduling advantages from the challenge run (not tested)
- "Simple workload summary statistics do not significantly explain per-scenario variation in ΔC" — permitted (existing README limitation is correct)

**Reviewer response section:** N5 — NOT YET WRITTEN

**Status:** Evidence complete (artifact #4). Reviewer response N5 must be written.

---

## N6: Metric Definitions and Formulas

**Reviewer concern:** Clarifications needed on how delta_lo is computed, what C_lower
means, and how the conservative bracket metric is defined.

| Item | Definition | Source |
|---|---|---|
| delta_lo | C_lower_A − C_upper_B | challenge_analysis.json (delta_formula field) |
| delta_hi | C_upper_A − C_lower_B | challenge_analysis.json |
| definitely_A_better | delta_lo > 0 (lower FP bound exceeds upper Random bound) | challenge_analysis.json |
| indistinguishable | delta_lo ≤ 0 and delta_hi ≥ 0 | challenge_analysis.json |
| C_lower | Lower interpolation bound of the crossing lambda | Gate F frozen analysis |
| Bootstrap | 5,000 paired scenario resamples, seed=9999, percentile CI | challenge_analysis.json |

**Notes:**
- Gate F (sc5–29) stores C values as 100× pp (e.g., 477.103 = 4.771 pp). Review-2 stores values directly in pp. Division by 100 applies only to Gate F artifact.
- "Scenario" = one Monte Carlo draw of workload and residual permutation; comparisons are paired within scenarios.

**Reviewer response section:** N6 — NOT YET WRITTEN (brief clarification section)

**Status:** Formulas frozen and consistent. A brief N6 section should confirm the formulas and note the Gate F unit convention.

---

## N7: Provenance, Reproducibility, and Hygiene

**Reviewer concern:** How was the analysis preregistered and protected from post-hoc
modification? What is the full provenance of all artifacts?

| Item | Status | Source |
|---|---|---|
| Code freeze | Git commit 5733b73, before sc30–54 runs | challenge_preflight.json |
| Runner SHA256 | 750150c337a1f81368bdba35e2af6ccda23f2917297d5f9ab3ebf51dd8281856 | challenge_preflight.json |
| 16/16 preflight conditions | PASS — all 16 including simulation equivalence (Stage 2), analysis regression, and seed-index audit (condition 16 / Amendment 5) | challenge_preflight.json |
| Merged artifact SHA256 | 181161082cbf79e32fb138779af20327fd026d5383d70a942e7373a64d635a71 | reviewer_response_r2.md |
| Analysis SHA256 | 3a8bbd0aba95209e8d383bb94f9b57b93df98a37d8cfa7423d8db0db115edac4 | reviewer_response_r2.md |
| Completion audit SHA256 | 33ff32a8a9a996d9c26c1aa94a302b2696010fdd7def1223ce741891f14f2768 | reviewer_response_r2.md |
| Post-exposure disclosure | E1/E2 prespecified at 5733b73, executed post-exposure | POST_EXPOSURE_SENSITIVITY_RECOVERY.md |
| Batch audit v1→v2 correction | v1 checker recorded but did not compare metadata; v2 enforces hard numeric comparison at 1e-10 | batch_transition_audit.json (checker_correction_notice) |
| Sensitivity recovery commit | 0aa995e — 26 files (9 sensitivity runs, analysis scripts, audit artifacts) | Git log |
| Phase I artifacts | 13/13 complete, overall PASS | final_output_audit.json |

**Post-exposure sensitivity disclosure (required in manuscript and reviewer response):**

> Phase E1 (cabinet-scale sensitivity) and E2 (beta sensitivity) were prespecified at
> Git commit 5733b73, before any challenge scenario (sc30–sc54) was executed. However,
> execution occurred after primary challenge results (Phase G) were exposed, due to an
> omission discovered during post-analysis review. The analysis design (parameters,
> scenarios, comparisons, and interpretation rules) was not changed after primary-result
> exposure. This is disclosed explicitly per POST_EXPOSURE_SENSITIVITY_RECOVERY.md.

**Wording constraints:**
- Must include the post-exposure disclosure verbatim (or equivalent) wherever E1/E2 results are reported
- Do NOT claim E1/E2 were pre-exposure; they were prespecified pre-exposure but executed post-exposure
- Batch audit v1 defect must be noted in N7: v1 records are superseded; v2 records are authoritative
- distinct_simulation_outputs = 9 (not 18 — v1 and v2 audits cover the same 9 non-baseline runs)

**Reviewer response section:** N7 — NOT YET WRITTEN

**Status:** All provenance artifacts complete. N7 section must be written.

---

## Summary Table

| Issue | Plan ref | Evidence | Key verdict | RR section | Status |
|---|---|---|---|---|---|
| N1: Node-level confounding | §D4, §H4–H6 | challenge_analysis.json | FP beats WithinCabPlacebo 20/25 (+3.54 pp); global placebo 22/25 (+4.55 pp); FP vs Random 22/25 (+6.71 pp) | COMPLETE | Manuscript update needed |
| N2: Cabinet count/envelope | §A1, §E1 | cabinet_timeline_audit.json, sensitivity_cabinet_scale.json | A1: proceed; E1: H8=ROBUST across ±10% | NOT WRITTEN | Write N2 |
| N3: Beta self-inclusion | §B1, §E2 | loo_beta_results.json, sensitivity_loo_beta.json | LOO correction −0.95%; H7=STABLE | NOT WRITTEN | Write N3; disclose post-exposure |
| N4: Thermal threshold | §E1 (proxy) | sensitivity_cabinet_scale.json | E1 covers envelope scaling; direct T_thr not tested | NOT WRITTEN | Write N4; acknowledge gap |
| N5: Job-size heterogeneity | §A2 | prospective_accuracy_by_job_size.json | All bins positive; 129–512 has lower R² (0.14) | NOT WRITTEN | Write N5 |
| N6: Metric formulas | §H1 | challenge_analysis.json | Formulas consistent and frozen | NOT WRITTEN | Write N6 (brief) |
| N7: Provenance/hygiene | §I, §13 | final_output_audit.json, batch_transition_audit.json | 13/13 Phase-I; v2 batch audit authoritative; post-exposure disclosure | NOT WRITTEN | Write N7 |
