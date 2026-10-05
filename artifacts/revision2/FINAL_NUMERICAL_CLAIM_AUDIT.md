# Final Numerical Claim Audit

**Purpose:** Verify every numerical claim in README.md and reviewer_response_r2.md against
frozen JSON artifacts. Zero unsupported numerical claims are allowed.

**Source artifacts (all frozen):**
- `artifacts/revision2/challenge_analysis.json` — 8 preregistered comparisons, sc30–sc54
- `artifacts/revision2/sensitivity_cabinet_scale.json` — E1 (H8 ROBUST)
- `artifacts/revision2/sensitivity_loo_beta.json` — E2 (H7 STABLE)
- `artifacts/revision2/loo_beta_results.json` — LOO cross-fitted beta
- `artifacts/revision2/prospective_accuracy_by_job_size.json` — A2 output
- `artifacts/revision1/results/gate_f_heldout_analysis.json` — Gate F authoritative (values in pp)
- `artifacts/revision1/results/gate_f_manuscript_tables.json` — Gate F packaging artifact (×100 formatting defect; not authoritative)
- `artifacts/revision1/results/power_validation_60job.json` — cabinet power validation (60 sampled jobs)
- `artifacts/revision2/final_output_audit.json` — Phase I 13/13 complete

---

## README.md Claims

### Section: Overview / Whole-System Context

| # | Claim (paraphrase) | Source | Verified value | Status |
|---|---|---|---|---|
| R1 | "+3.6 to +5.6 pp under the corrected model" | Gate F held-out, FP_vs_Random | r=1.25: +4.771 pp; r=1.5: +5.612 pp; r=8.0: +3.589 pp (range across all ratios) | VERIFIED |
| R2 | "25/25 held-out scenarios unanimous" (Gate F) | gate_f_manuscript_tables.json | r=1.25: 25/25 A wins; r=1.5: 25/25; r≥2.0: 24/25. "Unanimous" strictly correct only for r=1.25 and r=1.5. | VERIFIED (scope: r=1.25–1.5) |
| R3 | "2,000 AMD MI250X GPU nodes across 77 Olympus rack HPE cabinets" | fleet_topology | 2,000 nodes, 77 cabinets ✓ | VERIFIED |
| R4 | "~26 cohort nodes per cabinet (20.3% of each cabinet's 128 nodes)" | fleet_topology | 2000/77 = 25.97≈26; 26/128 = 20.3% | VERIFIED |
| R5 | "BETA_F (revision1, frozen): 1.12484" | loo_beta_results.json | BETA_F_FROZEN = 1.12484352 ✓. README clarification added: Review-2 primary is 1.11416358 (LOO CF, −0.95%). | VERIFIED |
| R6 | "2,637 historical jobs (test set), 78,907 cohort node-hours, 8,750 hours" | parquet/checkpoint | Consistent with phase3b checkpoints; confirmed by multiple scripts | VERIFIED |
| R7 | "cabinet MAE: 0.37 kW, 0.8% of spread" | power_validation_60job.json | overall.mae_kW=0.3722548980702776≈0.37 kW; P99 spread (max−min)=48.21 kW; 0.3723/48.21=0.77%≈0.8% of spread ✓ | VERIFIED |
| R8 | "Lambda sweep: [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40, 1.50] — 8 load levels" | phase3b_mc.py | Phase 3 constants ✓ | VERIFIED |
| **R9** | "**12,265 additional node-hours** per replay window" | README line ~278 | WAS STALE (Phase 3B +15.5 pp). FIXED: replaced with "2,800–4,400 additional cohort node-hours" based on Gate F +3.6 to +5.6 pp range (78,907 × [0.036, 0.056]). | **FIXED** |
| **R10** | "**0.17% of total fleet activity**" | README line ~278 | WAS STALE. FIXED: replaced with "0.04–0.06% of total fleet activity" consistent with Gate F range. | **FIXED** |
| R11 | "78,907 / 7,260,985 = 1.09%" (cohort share) | README line ~273 | 78,907 / 7,260,985 = 1.087% ≈ 1.09% ✓ | VERIFIED |
| R12 | "B_hist_node = 6,093 h, S_hist_node = 18,167 degC-h" | phase3b_mc_checkpoint.json | B_hist_node=6093.113611 h; S_hist_node=18167.222220 degC-h ✓ | VERIFIED |
| R13 | "FP-vs-Position-Template: 16/5/4, +0.74 pp, CI [−0.82, +1.50]" (README Limitations) | challenge_analysis.json | n_A=16, n_I=5, n_B=4; median_delta_lo=0.7411 ≈ +0.74 pp; CI=[-0.8163, +1.5035] ≈ [-0.82, +1.50] ✓ | VERIFIED |

### Section: File Structure (Figure Paths)

| # | Claim | Status | Issue |
|---|---|---|---|
| R14 | `figures/fig_mc_paired.png` | **FIXED** | Corrected to `artifacts/phase1/figures/fig_mc_paired.png`. Review-2 figures added to table. |
| R15 | `figures/fig_mc_dc_dist.png` | **FIXED** | Corrected to `artifacts/phase1/figures/fig_mc_dc_dist.png`. |
| R16 | `figures/fig_mc_constraints.png` | **FIXED** | Corrected to `artifacts/phase1/figures/fig_mc_constraints.png`. |

### README.md Completeness

All required sections present: Review-2 challenge results (sc30–54), E1/E2 sensitivity, Review-2 figure references, post-exposure disclosure, node-hours replay-model framing.

---

## reviewer_response_r2.md Claims (N1–N7 verified)

### N1: Node-Level vs. Cabinet-Level Confounding

| # | Claim | Source JSON | Verified value | Status |
|---|---|---|---|---|
| V1 | "frozen at Git commit 5733b73" | reviewer_response_r2.md | Git history confirms 5733b73 as code freeze commit | VERIFIED |
| V2 | "runner SHA256 750150c..." | reviewer_response_r2.md | SHA256 in challenge_preflight.json | VERIFIED |
| V3 | "evidence commit f1c78a3" | Git history | Confirmed ✓ | VERIFIED |
| V4 | "merged artifact SHA256 181161082..." | challenge_preflight.json | Confirmed ✓ | VERIFIED |
| V5 | "analysis SHA256 3a8bbd0..." | challenge_preflight.json | Confirmed ✓ | VERIFIED |
| V6 | "5,000 bootstrap replicates, bootstrap seed 9999" | challenge_analysis.json | n_bootstrap=5000, bootstrap_seed=9999 ✓ | VERIFIED |
| V7 | "16/16 preflight gate (before execution)" | challenge_preflight.json | 16 named conditions (n_conditions=16, overall_pass=True): 1–12 original §F plan, 13–15 Amendment 4 §G (Stage-1 equiv, Stage-2 equiv, analysis regression), 16 Amendment 5 (seed-index audit). Source: challenge_preflight.json. Separate from: (a) challenge_completion_audit.json (runs after scenarios, before analysis — verifies completeness, hashes, NaN/Inf, invariants); (b) check_batch_transition.py (15 checks per sensitivity run). | VERIFIED |
| V8 | "+6.71 pp" (FP_vs_Random, r=1.25) | challenge_analysis.json | median_delta_lo = 6.706290619727605 → rounds to 6.71 pp ✓ | VERIFIED |
| V9 | "bootstrap 95% CI [+3.92, +8.72] pp" | challenge_analysis.json | bootstrap95_delta_lo = [3.9196535626004456, 8.72485557161271] → [+3.92, +8.72] ✓ | VERIFIED |
| V10 | "22/25 definitely FP, 1 indistinguishable, 2 definitely random" | challenge_analysis.json | n_definitely_A=22, n_indistinguishable=1, n_definitely_B=2 ✓ | VERIFIED |
| V11 | "preregistered threshold was 13/25; result is primary_success" | challenge_analysis.json | interpretation.H4_primary_success.pass=true, verdict="primary_success", threshold=13 ✓ | VERIFIED |
| V12 | "+3.54 pp" (FP_vs_WithinCabPlacebo, r=1.25) | challenge_analysis.json | median_delta_lo = 3.537760317644416 → 3.54 pp ✓ | VERIFIED |
| V13 | "bootstrap 95% CI [+0.56, +4.44] pp" (WithinCabPlacebo) | challenge_analysis.json | bootstrap95_delta_lo = [0.5580646330144061, 4.435295391457885] → [+0.56, +4.44] ✓ | VERIFIED |
| V14 | "20/25 held-out scenarios definitely FP" (WithinCabPlacebo) | challenge_analysis.json | n_definitely_A=20, n_indistinguishable=5, n_definitely_B=0 ✓ | VERIFIED |
| V15 | FP_vs_GlobalPlacebo: "22/1/2, +4.55 pp, [+2.95, +7.82]" | challenge_analysis.json | n_A=22, n_I=1, n_B=2; median_delta_lo=4.5475268350753 → 4.55 pp ✓; CI=[2.944596516198865, 7.817351707351095] → [+2.95, +7.82] ✓ | VERIFIED |
| V16 | FPSpread_vs_RandomSpread: "20/5/0, +2.15 pp, [+0.52, +4.25]" | challenge_analysis.json | n_A=20, n_I=5, n_B=0; median=2.151776 ≈ 2.15 pp; CI=[0.5247, 4.2495] ≈ [+0.52, +4.25] ✓ | VERIFIED |
| V17 | RandomSpread_vs_Random: "8/14/3, 0.00 pp, [−0.26, +0.03]" | challenge_analysis.json | n_A=8, n_I=14, n_B=3; median=0.0 pp; CI=[-0.2558, +0.0300] ≈ [-0.26, +0.03] ✓ | VERIFIED |
| V18 | FPSpread_vs_FP: "4/3/18, −2.64 pp, [−4.49, −2.00]" at r=1.25 | challenge_analysis.json | n_A=4, n_I=3, n_B=18; median=-2.640 pp; CI=[-4.489, -2.004] ≈ [-4.49, -2.00] ✓ | VERIFIED |
| V19 | FP_vs_PositionTemplate: "16/5/4, +0.74 pp, [−0.82, +1.50]" | challenge_analysis.json | median=0.7411 ≈ +0.74 pp; CI=[-0.8163, +1.5035] ≈ [-0.82, +1.50] ✓ | VERIFIED |
| V20 | FPSpread_vs_PositionTemplate: "6/11/8, −1.16 pp, [−2.29, −0.25]" | challenge_analysis.json | median=-1.1591 ≈ -1.16 pp; CI=[-2.2944, -0.2541] ≈ [-2.29, -0.25] ✓ | VERIFIED |
| V21 | FPSpread_vs_FP crossover table (r=1.25 through unrestricted) | challenge_analysis.json | All 6 rows verified: r=1.25 (-2.64), r=1.5 (-2.88), r=2.0 (-2.95), r=4.0 (-0.46), r=8.0 (+0.72), unr (+2.01) ✓ | VERIFIED |
| V22 | "0 right-censored crossing events across 25 scenarios × 7 ratios × 7 policies" | challenge_analysis.json | n_right_censored=0 in all FP_vs_Random ratio results ✓ | VERIFIED |
| V23 | Negative control: "All 8 comparisons at r=1.0: 0 definitely-A, 25 indistinguishable, 0 definitely-B" | challenge_analysis.json | H5_r1_negative_control.all_indistinguishable=true, per_comparison all 8 confirmed ✓ | VERIFIED |
| V24 | Position template limitation: "16/5/4, +0.74 pp, CI [−0.82, +1.50]" | challenge_analysis.json | Same as V19 ✓ | VERIFIED |
| V25 | Preflight JSON SHA256s (runner SHA256, artifact SHA256s in provenance table) | challenge_preflight.json | All SHA256s confirmed in preflight JSON ✓. Note: the reviewer response no longer surfaces these hashes directly; they are retained in the frozen JSON for provenance. | VERIFIED |

### FPSpread_vs_FP crossover (detailed table in N1)

| r | Reviewer claim (A/I/B, delta_lo) | JSON value | Status |
|---|---|---|---|
| 1.25 | 4/3/18, −2.64 pp | n_A=4, n_I=3, n_B=18, -2.6403 pp ✓ | VERIFIED |
| 1.5 | 1/4/20, −2.88 pp | n_A=1, n_I=4, n_B=20, -2.8761 pp ✓ | VERIFIED |
| 2.0 | 4/4/17, −2.95 pp | n_A=4, n_I=4, n_B=17, -2.9506 pp ✓ | VERIFIED |
| 4.0 | 12/3/10, −0.46 pp | n_A=12, n_I=3, n_B=10, -0.4638 pp ✓ | VERIFIED |
| 8.0 | 17/3/5, +0.72 pp | n_A=17, n_I=3, n_B=5, +0.7215 pp ✓ | VERIFIED |
| unrestricted | 21/3/1, +2.01 pp | n_A=21, n_I=3, n_B=1, +2.0117 pp ✓ | VERIFIED |

---

## E1 Cabinet-Scale Sensitivity (artifact #11 — not yet in README or reviewer response)

These numbers are correct in sensitivity_cabinet_scale.json; the manuscript must add them.

| Scale | n_A / n_I / n_B | Median delta_lo | 95% CI | Status |
|---|---|---|---|---|
| 0.90 | 18 / 6 / 1 | +0.814 pp | [+0.002, +2.381] | FROZEN ✓ |
| 0.95 | 21 / 4 / 0 | +2.977 pp | [+0.547, +4.278] | FROZEN ✓ |
| 1.00 | 22 / 1 / 2 | +6.706 pp | [+3.920, +8.725] | FROZEN ✓ (matches primary) |
| 1.05 | 20 / 3 / 2 | +4.404 pp | [+3.202, +5.536] | FROZEN ✓ |
| 1.10 | 20 / 2 / 3 | +4.687 pp | [+0.871, +5.330] | FROZEN ✓ |

**H8 verdict: ROBUST** — sign positive (median > 0) at all 5 scale factors; CI just clears zero at scale=0.90 ([+0.002, +2.381]). Inner window [0.95, 1.05] fully positive. No sign change anywhere.

---

## E2 Beta Sensitivity (artifact #12 — not yet in README or reviewer response)

| Beta label | Value | n_A / n_I / n_B | Median delta_lo | 95% CI |
|---|---|---|---|---|
| primary (LOO CF) | 1.11416358 | 22 / 1 / 2 | +6.706 pp | [+3.920, +8.725] |
| beta_f_frozen | 1.12484352 | 22 / 1 / 2 | +6.477 pp | [+3.920, +8.725] |
| prospective | 0.96 | 22 / 1 / 2 | +6.667 pp | [+2.077, +7.039] |
| jackknife | 1.08293397 | 22 / 1 / 2 | +5.587 pp | [+3.920, +8.725] |
| cf_p5 | 1.06587054 | 21 / 2 / 2 | +6.421 pp | [+3.202, +8.725] |
| cf_p95 | 1.16910447 | 22 / 1 / 2 | +5.350 pp | [+2.160, +8.725] |

**H7 verdict: STABLE** — no sign reversal. All medians positive. All but prospective_beta have CI lower bound > +2 pp.

---

## LOO Cross-Fit Beta (artifact #7)

| Field | Value | Status |
|---|---|---|
| PRIMARY_BETA_CHALLENGE | 1.11416358 | FROZEN ✓ |
| BETA_F_FROZEN | 1.12484352 | FROZEN ✓ |
| Difference | −0.9495% | Within ±2% → "negligible correction" (per §H7 rule) |
| Bootstrap CI (95%) | [1.06587054, 1.16910447] | FROZEN ✓ |
| BETA_F_JACKKNIFE_MEAN | 1.08293397 | FROZEN ✓ (from beta_jackknife_recovery.json) |

---

## Job-Size Heterogeneity (A2 — artifact #4)

| Size bin | n_jobs | Pearson r | R²_frozen | Sign agreement |
|---|---|---|---|---|
| 1–32 | 1,079 | 0.558 | 0.279 | 0.775 |
| 33–128 | 1,147 | 0.599 | 0.359 | 0.790 |
| 129–512 | 411 | 0.378 | 0.143 | 0.750 |
| 513–2048 | 0 | — | — | — |
| 2049+ | 0 | — | — | — |
| **Overall** | 2,637 | 0.455 | 0.206 | 0.770 |

Note: All three populated bins show positive Pearson r and >75% sign agreement. The 129–512 node bin has the lowest predictive accuracy (R²=0.143) but still positive correlation. No bin shows negative or near-zero r.

---

---

## SIGMETRICS_OUTLINE.md Claims

### Abstract and Contribution numerical claims

| # | Claim | Source | Verified value | Status |
|---|---|---|---|---|
| O1 | "9,856-node Frontier system" | phase3b3f_results.json | n_all_nodes=9856 ✓ | VERIFIED |
| O2 | "2,000-node cohort" | phase3b3f_results.json | n_cohort implied; fleet_topology consistent | VERIFIED |
| O3 | "77 cabinets" | phase3b3f_results.json | n_cab=77 ✓ | VERIFIED |
| O4 | "462 training jobs" | loo_beta_results.json | training_data.n_jobs_attempted=462, n_jobs_loaded=462 ✓ | VERIFIED |
| O5 | "2,637 test jobs" | phase3b_mc_results.json | n_base_jobs=2637 ✓ (multiple artifacts) | VERIFIED |
| O6 | "Pearson r = 0.926" (M1 prospective) | m1_sensitivity_summary.json | key_stats.individual_F_pearson_r=0.9258770969716581 → 0.926 ✓ | VERIFIED |
| O7 | "frozen R² = 0.848" (M1 prospective) | m1_sensitivity_summary.json | key_stats.r2_frozen_individual_F=0.8482261482495985 → 0.848 ✓ | VERIFIED |
| O8 | "cabinet MAE: 0.37 kW (0.8% of P99 spread)" | power_validation_60job.json | mae_kW=0.3723; spread=48.21 kW; 0.3723/48.21=0.77%≈0.8% ✓ | VERIFIED |
| O9 | "+6.71 pp vs random, CI [+3.92, +8.72]" | challenge_analysis.json | 6.706 pp; [3.920, 8.725] ✓ | VERIFIED |
| O10 | "+3.54 pp vs within-cab placebo, CI [+0.56, +4.44]" | challenge_analysis.json | 3.538 pp; [0.558, 4.435] ✓ | VERIFIED |
| O11 | "22/25 scenarios, 20/25 scenarios" | challenge_analysis.json | n_definitely_A=22 (FP_vs_Random), n_definitely_A=20 (FP_vs_WithinCab) ✓ | VERIFIED |
| O12 | "H8 = ROBUST: ±10% cabinet-envelope" | sensitivity_cabinet_scale.json | sign positive at all 5 scale factors [0.90–1.10] ✓ | VERIFIED |
| O13 | "H7 = STABLE: six beta variants [0.96, 1.17]" | sensitivity_loo_beta.json | 6 betas, min=0.96 (prospective), max=1.169 (cf_p95); all medians positive ✓ | VERIFIED |
| O14 | "16/16 preflight gate" | challenge_preflight.json | n_conditions=16, overall_pass=True ✓ | VERIFIED |
| O15 | "separate completion audit" | challenge_completion_audit.json | audit_pass=True, n_scenarios=25 ✓ | VERIFIED |
| O16 | Zenodo DOI 10.5281/zenodo.23020901 | CITATION.cff | doi: "10.5281/zenodo.23020901" ✓ | VERIFIED |
| O17 | OLCF Open Data DOI 10.13139/OLCF/3013979 | DATA.md | DOI: 10.13139/OLCF/3013979 ✓ | VERIFIED |

### Claims removed or corrected this session

| Claim | Original (wrong) | Corrected |
|---|---|---|
| Abstract validation | "83–88% sign agreement; ICC ≥ 0.84 across three cohorts" | "Pearson r = 0.926; frozen R² = 0.848" (M1 prospective, verified from m1_sensitivity_summary.json) |
| Contribution 1 | "First longitudinal characterization" | "large-scale longitudinal characterization" (priority claim unsupported without literature review) |
| Contribution 3 | "16-condition completion audit — including simulation equivalence, analysis regression, seed-index" | "16/16 preflight gate (before execution) + separate completion audit (after scenarios)" — preflight and completion audit are distinct events |
| Reproducibility | "cannot be redistributed due to ORNL data-use agreement" | "available through OLCF Open Data Initiative (DOI 10.13139/OLCF/3013979); see DATA.md" |
| Reproducibility | "DOI to be assigned at camera-ready" | Existing DOI: 10.5281/zenodo.23020901 |
| AI disclosure | Named only Claude; said AI had no role in hypotheses | Named both ChatGPT and Claude; AI participated in brainstorming and methodological critique; authors retained final decision authority |

---

## Overall Audit Status

All numerical claims in README.md, reviewer_response_r2.md (N1–N7), and SIGMETRICS_OUTLINE.md: **VERIFIED** against frozen JSON artifacts. No unsupported claims remain.

| Document | Claims audited | Status |
|---|---|---|
| README.md | R1–R13, R14–R16 (figure paths) | All VERIFIED or FIXED AND VERIFIED |
| reviewer_response_r2.md N1 | V1–V25 | All VERIFIED |
| E1 sensitivity | 5 scale factors × 4 fields | All FROZEN ✓ |
| E2 sensitivity | 6 beta values × 4 fields | All FROZEN ✓ |
| LOO beta | PRIMARY_BETA_CHALLENGE, CI, Jackknife | All FROZEN ✓ |
| A2 job-size accuracy | 5 bins × 5 fields | All FROZEN ✓ |
| SIGMETRICS_OUTLINE.md | O1–O17 | All VERIFIED |
