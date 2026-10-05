# SIGMETRICS/POMACS 2027 Manuscript Outline

**Venue:** ACM SIGMETRICS / POMACS 2027 — Measurement and Applied Modeling
**Track:** Measurement & Applied Modeling

**Submission format (per 2027 CFP):**
- Up to **20 pages** of technical content
- **Single-column** format
- LaTeX: `\documentclass[acmsmall, screen, review]{acmart}`
- Unlimited reference pages
- Appendix allowed for technical correctness / additional validation only;
  reviewers are not required to read it

**Deadlines (Winter cycle):**
- Abstract registration: January 4, 2027
- Full paper submission: January 11, 2027

---

## Working Title

**Persistent Node-Level Thermal Fingerprints on Frontier: Measurement and Constraint-Aware Replay**

*Rationale:* The scheduling benefit is established through held-out constraint-aware replay, not live scheduler deployment. A title that implies realized production throughput ("enable scheduling-capacity advantage") invites the objection "you didn't deploy this scheduler." The working title names exactly what the paper demonstrates: measurement of persistent fingerprints and a constraint-aware replay study.

---

## Abstract (~175 words)

GPU supercomputers exhibit persistent node-level thermal heterogeneity: nodes that run
warm during one workload tend to run warm in subsequent workloads, independent of job
composition. We call this individual-node property a *thermal fingerprint* and characterize
its stability across 2,637 production workloads on the 9,856-node Frontier system. Fingerprint
rankings derived from 2024 training telemetry achieve 83–88% sign agreement with 2025
outcomes and ICC ≥ 0.84 across three independent validation cohorts.

We then quantify the scheduling-capacity advantage of fingerprint-aware placement through a
preregistered held-out constraint-aware replay study: 25 scenarios (sc30–sc54), 8 comparisons
in a factorial placebo structure, all run under a protocol frozen at a fixed Git commit before
any scenario was executed. At the preregistered 1.25× choice ratio, fingerprint-guided
placement yielded a median conservative bracket separation of +6.71 percentage points versus
random placement (bootstrap 95% CI [+3.92, +8.72] pp; 22/25 scenarios). Against a
within-cabinet permutation placebo that preserves cabinet-level score structure, the separation
was +3.54 pp (20/25; CI [+0.56, +4.44] pp), providing held-out evidence that individual node
identity contributes beyond cabinet membership. Results are robust to ±10% cabinet-envelope
calibration error and stable across six beta estimator variants. Fingerprint-guided placement
was not statistically separated from a thermally informed structural-position template.

---

## Contributions (5 bullets)

1. **Thermal fingerprint characterization at scale.** First longitudinal characterization of
   persistent node-level thermal heterogeneity across a production GPU supercomputer: 2,000-node
   cohort, 77 cabinets, 462 training jobs, 2,637 test jobs spanning two calendar years. Rank
   stability (ICC ≥ 0.84, sign agreement ≥ 83%) establishes that thermal identity is a durable
   property of individual nodes, not transient job-level noise.

2. **Validated operating-envelope replay model.** A stateful constraint-aware replay model
   reconstructs cabinet-level thermal budgets from raw telemetry and replays the full
   base workload exactly before adding incremental synthetic workload to measure scheduling-
   capacity yield. Cabinet power estimation MAE: 0.37 kW (0.8% of P99 spread across cabinets).

3. **Preregistered held-out challenge design.** Scientific runner, all comparison hypotheses,
   beta estimator, bootstrap parameters, and interpretation rules frozen at a fixed Git commit
   before any scenario is executed. A 16-condition completion audit — including simulation
   equivalence at 1e-9 tolerance, analysis regression test, and seed-index correctness — is
   required before analysis runs. This design separates prespecification from execution and
   provides verifiable provenance for all results.

4. **Factorial placebo structure for node-specificity.** Eight preregistered comparisons isolate
   the contribution of individual node identity from cabinet-level structure (within-cabinet
   permutation placebo), arbitrary global ranking (global permutation placebo), and spreading
   mechanics (FPSpread vs RandomSpread). Results distinguish node-specific signal from cabinet-
   level composition effects within the replay-model scope.

5. **Preregistered crossover: choice-set-size dependence.** FPSpread underperforms direct
   fingerprint selection at constrained choice ratios (r = 1.25–2.0) but outperforms at large
   choice sets (r ≥ 8.0, unrestricted). This crossover, preregistered before execution, is
   replicated exactly in the 25 held-out scenarios and is consistent with a binding-constraint
   regime shift — providing a testable hypothesis for scheduler design.

---

## Section Structure

| § | Title | Content | Pages (single-col) |
|---|---|---|---|
| 1 | Introduction | Thermal heterogeneity problem, measurement gap, contributions, paper map | 2.0 |
| 2 | Background and Related Work | Thermal management in HPC, node-level fingerprinting, scheduler measurement, preregistered experiments | 2.5 |
| 3 | Thermal Fingerprint Characterization | Frontier system, 2-year telemetry, fingerprint definition, temporal stability, three-cohort validation, job-size stratification | 3.5 |
| 4 | Constraint-Aware Replay Model | Cabinet power model, stateful replay, thermal budget constraints, model validation (MAE 0.37 kW, Spearman ρ) | 2.5 |
| 5 | Preregistered Challenge Protocol | Preregistration commit, 16-condition preflight, factorial placebo structure, LOO-CF beta estimator, bootstrap design, post-exposure disclosure | 2.0 |
| 6 | Primary Results | H4 (FP vs Random), node-specificity (FP vs WithinCab), global placebo, factorial table, position template non-separation | 2.5 |
| 7 | Robustness and Sensitivity | E1 (H8 cabinet-scale), E2 (H7 beta variants), crossover finding, batch-audit correction | 2.0 |
| 8 | Discussion and Limitations | Replay-model scope, T_thr not tested, position template not separated, no causal mechanism, fleet generalizability, AI/LLM use disclosure | 1.5 |
| 9 | Conclusion | Summary, open questions | 0.5 |
| — | References | — | unlimited |
| — | Appendix (optional) | Preflight condition list, amendment log, extended E1/E2 tables, provenance hashes | not counted |

**Total body: ~19 pages.** One page of buffer before the 20-page limit.

---

## Figure Allocation

| Fig | Panels | Section | Source / file |
|---|---|---|---|
| 1 | Fingerprint distribution + temporal stability | §3 | Regenerate from frozen `gate_f_heldout_analysis.json` and fingerprint telemetry |
| 2 | Capacity yield crossing illustration + delta_lo metric | §4 | Regenerate from replay model frozen output |
| 3 | Primary challenge results — forest plot of 8 comparisons at r = 1.25 | §6 | `artifacts/revision2/figures/fig_r2_factorial_r125.pdf` (300 dpi) |
| 4 | FPSpread vs FP crossover across ratio sweep | §6/7 | `artifacts/revision2/figures/fig_r2_fpspread_crossover.pdf` (300 dpi) |
| 5 | Robustness panels: E1 cabinet-scale (A) + E2 beta sensitivity (B) | §7 | `artifacts/revision2/figures/fig_r2_robustness.pdf` (300 dpi) |

**Note on Phase-1 figures:** Existing Phase-1 PNGs (130–180 dpi) are development/legacy figures and should not be allocated as final SIGMETRICS main-text figures. If a Phase-1 result is needed for a main-text figure (e.g., fingerprint distribution, capacity yield), regenerate that specific figure from the frozen analysis artifacts at submission time.

---

## Table Allocation

| Table | Content | Section |
|---|---|---|
| 1 | Fingerprint temporal stability: ICC, Pearson r, sign agreement by cohort | §3 |
| 2 | Factorial challenge results: 8 comparisons × n_A/n_I/n_B + median delta_lo + CI at r = 1.25 | §6 |
| 3 | E1/E2 sensitivity: scale factors and beta variants with verdicts | §7 |

---

## Generative-AI / LLM Use Disclosure

**Required per SIGMETRICS 2027 CFP:** Authors must disclose the extent of AI/LLM use in the
Methods section.

**Planned disclosure (draft for §8 or §5 Methods):**

> AI language model tools (Claude, Anthropic) were used as development aids in this work.
> Specific uses included: code review and debugging assistance for analysis scripts;
> audit of numerical claims against frozen JSON artifacts; prose drafting and editing;
> and figure-generation script development. All scientific hypotheses, study design,
> preregistration decisions, and interpretation of results were made by the authors.
> All numerical claims were verified by the authors against the frozen artifact record
> described in §5. Authors accept full responsibility for all content.

*Do not overstate or understate.* The AI tools did not determine which hypotheses to test,
which comparisons to preregister, or how to interpret ambiguous results. The tools were
used for implementation assistance and document drafting — both heavily author-reviewed.

---

## Reproducibility Declaration

**Required per SIGMETRICS 2027 CFP:** A short reproducibility paragraph expected in the
contributions section for accepted papers.

**Planned statement (draft for §1 or §5):**

> We release all analysis scripts, frozen preregistration plans, result JSONs, and
> figure-generation scripts at [repository URL]. Analysis plans are tied to specific
> Git commits with SHA256-verified runner binaries. Bootstrap seeds and all
> hyperparameters are recorded in the frozen artifact record (`final_output_audit.json`).
> Raw Frontier job telemetry (node power traces, job placement records) cannot be
> redistributed due to ORNL data-use agreement; however, all derived intermediate
> artifacts sufficient to reproduce our analyses from the fingerprint-estimation stage
> onward are released. Long-term archival target: Zenodo (DOI to be assigned at
> camera-ready stage).

**Items to be released:**
- `REVIEW2_CHALLENGE_PLAN.md` (preregistration)
- All analysis scripts (`phase3b_mc.py`, `challenge_runner.py`, `challenge_analysis.py`, etc.)
- All frozen result JSONs (`challenge_analysis.json`, `sensitivity_cabinet_scale.json`, etc.)
- Figure generation scripts (`fig_r2_main.py`, `fig_r2_robustness.py`)
- Amendment log and provenance hashes

**What cannot be released:** Raw Frontier telemetry (node power traces at 2-second intervals)
due to ORNL data-use agreement. Derived fingerprint scores and cabinet envelopes may be
releasable; confirm with ORNL data governance before camera-ready.

---

## Venue Alignment Notes

The SIGMETRICS 2027 CFP explicitly welcomes:
- HPC workload characterization
- Measurement of production systems
- Scheduling and resource management
- Energy and power management
- Simulation and modeling methodology
- Reproducibility and experimental design

This paper directly addresses all six. The preregistered challenge design and factorial
placebo structure are themselves methodological contributions relevant to reproducibility
at measurement venues.
