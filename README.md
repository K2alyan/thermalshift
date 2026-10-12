# ThermalShift

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.23020901.svg)](https://doi.org/10.5281/zenodo.23020901)

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

**Answer: yes** — and a preregistered held-out challenge experiment provides evidence that individual node-level thermal fingerprints contribute scheduling value beyond cabinet-level structure and spreading alone under the historical operating-envelope replay model.

Across 25 held-out workload-replay scenarios (Gate F, sc5–sc29), thermal-fingerprint-aware placement showed a
positive capacity advantage over thermally unaware placement at every nondegenerate
availability level tested (fp node availability ratio r = 1.25–8.0), with median
conservative bracket separations of **+3.6 to +5.6 percentage points** and paired bootstrap
intervals across the held-out scenarios excluding zero at every ratio. When scheduler
availability is reduced to exactly the minimum required (r = 1.0), all policies converge
by construction — no selection freedom means no placement signal.

A subsequent preregistered challenge experiment (Review-2, sc30–sc54, 25 new scenarios) addressed whether that benefit reflects individual node-level thermal identity or cabinet-level structure. At the preregistered 1.25× choice ratio, fingerprint-guided placement produced a median conservative bracket separation of **+6.71 percentage points** versus random placement (bootstrap 95% CI [+3.92, +8.72] pp) and **+3.54 percentage points** versus a within-cabinet permutation placebo that preserves cabinet membership and score distribution while breaking the node–fingerprint association (95% CI [+0.56, +4.44] pp). Both intervals exclude zero. Spreading alone showed no clear primary-ratio advantage. See [Review-2 Challenge Results](#review-2-challenge-results-sc30sc54) below.

---

## The Signal Is Persistent and Prospective

The scheduling result rests on a prior empirical claim: that thermal fingerprints
carry real, durable predictive information about future node behavior.

| Validation | Result |
|------------|--------|
| 30-min fleet diagnostic vs. longitudinal fingerprint (FA, n=1,435 nodes) | Pearson r = 0.88 |
| Frozen 2024 fingerprint vs. node's typical 2025 thermal position | r = 0.926, R² = 0.848 |
| Power-only model MAE | 1.071 °C |
| Power + fingerprint model MAE | 0.718 °C |
| Test population | 2,000 nodes |

The r = 0.926 result is node-level aggregation over 2025 jobs using fingerprints learned
entirely from 2024 data — a prospective, out-of-sample prediction. It is not single-job
temperature prediction. This creates the scientific chain:

**signal exists → signal persists → signal predicts → signal changes a scheduling decision
→ decision creates capacity.**

---

## Key Definitions

**What the fingerprint measures.**
The thermal fingerprint FA_2024 is the mean per-node within-job temperature deviation:
for each training job, each node's mean temperature minus the job's mean temperature
across all participating nodes; then these residuals are averaged across all training jobs
for that node. No power regression is applied; no slot or cabinet covariate is conditioned
out. The separate validation analysis (Power-only MAE 1.071°C vs. Power+fingerprint MAE
0.718°C) measures FA's predictive value — it is not a step in FA's derivation. What the
fingerprint captures may reflect hardware heterogeneity (cooling efficiency, thermal
interface material, airflow path), persistent slot-specific effects, or both — the study
cannot distinguish these; see the hardware-vs-slot-assignment limitation in
`artifacts/manuscript_completion/FINAL_SCIENTIFIC_CLAIMS_AUDIT.md` (claim 12).

**What the replay model holds fixed and what changes.**
The 2,637 historical base workload jobs retain their original start times, durations,
requested node counts, and per-node power trajectories. A counterfactual replay assigns
cohort-node placements under each policy but does not delay, reschedule, or under-serve
any base job. Synthetic incremental jobs are added beyond the base workload. Only the
node-selection rule differs across policies; the workload is identical across all
policy comparisons within a scenario.

**Capacity's denominator.**
Capacity unlock is the maximum admitted incremental synthetic workload, expressed as a
fraction of the historical base node-hours, before the system exhausts its historical
thermal or power operating envelopes. A capacity unlock of 15% means the replay model
admitted 15% more cohort node-hours beyond the historical base load before a budget
constraint became binding. This is **not** application throughput, energy efficiency,
or wall-clock time — it is a replay-model accounting of absorbed synthetic node-hours
under historically calibrated constraints.

**What the choice ratio means.**
At ratio r, a job requesting k nodes receives min(eligible_count, ceil(r × k)) thermally
eligible candidate nodes, from which the scheduling policy selects k. At r = 1.25, a
four-node job receives min(eligible, ceil(5.0)) = min(eligible, 5) candidates; at r = 2.0,
it receives min(eligible, 8). The ceil ensures a single-node job at r = 1.25 receives 2
candidates (ceil(1.25) = 2), not 1. At r = 1.0, every job receives exactly k
candidates — no selection freedom exists — making all policies identical by construction.
The r = 1.0 row is therefore a negative control, not a competitive result.

**How crossing brackets and paired comparisons work.**
For each policy and scenario, the simulation sweeps an incremental load factor λ. The
capacity-unlock crossing is the λ at which the first budget constraint binds. Because
crossing falls between discrete λ grid points, each scenario produces a lower bound
(C_lower: last λ before binding) and an upper bound (C_upper: first λ where binding
occurs). The conservative bracket separation δ_lo = C_lower(A) − C_upper(B) is positive
only when policy A's lower bound strictly exceeds policy B's upper bound — a pessimistic
test that intentionally understates the advantage. Paired bootstrap comparisons resample
across the N scenarios (not nodes or jobs) with 5,000 replicates, seed 9999.

---

## Results at a Glance

> **Evidence hierarchy.** This repository spans several generations of the study with
> different preregistration status and reference definitions. The table below is the
> authoritative guide; the full claims audit is at
> `artifacts/manuscript_completion/FINAL_SCIENTIFIC_CLAIMS_AUDIT.md`.
>
> | Analysis | Scenarios | Reference type | Status | FP vs Random δ_lo at r=1.25 |
> |---|---|---|---|---|
> | Gate F (revision1 held-out) | sc5–sc29 | Original job-contribution | Preregistered held-out design | +4.77 pp (25/0/0) |
> | R2 Challenge | sc30–sc54 | Original job-contribution | Preregistered challenge — primary | +6.71 pp (22/1/2) |
> | C1 (corrected reference) | sc5–sc29 | Corrected concurrent-load | Post-exposure sensitivity | +16.17 pp (25/0/0) |
> | C2 (corrected reference) | sc30–sc54 | Corrected concurrent-load | Post-exposure sensitivity — primary claims source | +12.48 pp (25/0/0) |
> | Round-7 / PositionGroupHash | sc30–sc54 | Corrected reference | Post-exposure corrective robustness | FP vs PGH +7.265 pp (24/1/0) |
>
> Gate F and the R2 Challenge are preregistered. C1, C2, and Round-7 are post-exposure;
> C2 is the primary claims source per the scientific claims audit. Original Experiments 1
> and 2 (pre-R2, original reference) are superseded and not used for primary claims.

### Gate F held-out results (preregistered held-out design, original reference)

| Ratio r | full_fp wins | n_ind | full_random wins | Median δ_lo | 95% paired bootstrap CI |
|---|---|---|---|---|---|
| 1.0 (degenerate control) | 0 | 25 | 0 | −0.003 pp | [−0.301, 0.000] |
| 1.25 | **25** | 0 | 0 | +4.77 pp | [+2.59, +6.06] |
| 1.5  | **25** | 0 | 0 | +5.61 pp | [+3.18, +8.97] |
| 2.0  | **24** | 1 | 0 | +4.86 pp | [+3.56, +7.42] |
| 4.0  | **24** | 1 | 0 | +4.44 pp | [+3.17, +5.45] |
| 8.0  | **24** | 0 | 1 | +3.59 pp | [+2.59, +4.39] |
| unrestricted | **22** | 1 | 2 | +4.24 pp | [+2.87, +5.30] |

25 held-out scenarios (sc5–sc29), commit 301d269. δ_lo = C_lower(full_fp) − C_upper(full_random),
a pessimistic conservative bracket separation: positive only when full_fp's lower bound exceeds
full_random's upper bound. At r = 1.0 all policies converge by construction (no selection freedom),
explaining the near-zero δ_lo at the degenerate control. Bootstrap CIs are paired across
the 25 held-out replay scenarios; they are not population-level uncertainty bounds for real
deployments. Cabinet power was the dominant binding constraint for full_fp, increasing
from 20–21/25 scenarios at r = 1.25–1.5 to 24–25/25 at r ≥ 2 and unrestricted.

**Corrected-reference sensitivity (C1, post-exposure):** Rerunning the same sc5–sc29
scenarios with the corrected concurrent-load cabinet reference yields FP vs Random 25/0/0
at every nondegenerate ratio, with median δ_lo = +16.17 pp (95% CI [+11.53, +21.50]) at
r=1.25. The direction and sign are identical to Gate F; the magnitude is higher because the
corrected reference sets a tighter operating constraint, leaving more capacity unlocked by
fingerprint placement. C1 is a post-exposure analysis; the preregistered held-out design
is Gate F. See `artifacts/manuscript_completion/C1_CORRECTEDREF_ANALYSIS.md`.

**Historical development result (pre-correction, for reference):** The original 30-scenario
Phase 3B analysis estimated a median paired advantage of +15.5 pp (bootstrap 95% CI:
+11.5 to +21.9 pp) under the pre-correction cabinet-power model, using the FP-cap-10 policy
and an interpolated crossing metric. This result is superseded by the corrected-reference
analyses (C1/C2) and is not used for primary claims.

---

### Review-2 Challenge Results (sc30–sc54)

**Preregistered factorial decomposition — 25 new held-out scenarios.**
Scientific code frozen at Git commit 5733b73 (runner SHA256 750150c337a1f81368bdba35e2af6ccda23f2917297d5f9ab3ebf51dd8281856) before challenge execution. Analysis plan frozen at the same commit (5,000 bootstrap replicates, seed 9999). Completion audit passed all 16 checks before analysis was run. Evidence frozen at commit f1c78a3.

**Primary endpoint — FP vs Random at r = 1.25 (H4):**

| Metric | Value |
|--------|-------|
| n_definitely_FP / n_total | **22 / 25** |
| Median conservative bracket separation (delta_lo) | **+6.71 pp** |
| Bootstrap 95% CI | [+3.92, +8.72] pp |
| Verdict | **primary_success** |

**Preregistered factorial decomposition at r = 1.25:**

All eight comparisons, preregistered before challenge exposure. delta_lo = C_lower_A − C_upper_B; definitely_A when delta_lo > 0.

| Comparison | A / Indist / B | Median delta_lo | Bootstrap 95% CI |
|---|---|---|---|
| **FP vs Random** (primary) | **22 / 1 / 2** | +6.71 pp | [+3.92, +8.72] |
| **FP vs WithinCabPlacebo** (node-specificity) | **20 / 5 / 0** | +3.54 pp | [+0.56, +4.44] |
| FP vs GlobalPlacebo | 22 / 1 / 2 | +4.55 pp | [+2.95, +7.82] |
| FPSpread vs RandomSpread | 20 / 5 / 0 | +2.15 pp | [+0.52, +4.25] |
| RandomSpread vs Random | 8 / 14 / 3 | 0.00 pp | [−0.26, +0.03] |
| FPSpread vs FP | 4 / 3 / 18 | −2.64 pp | [−4.49, −2.00] |
| FP vs PositionTemplate | 16 / 5 / 4 | +0.74 pp | [−0.82, +1.50] |
| FPSpread vs PositionTemplate | 6 / 11 / 8 | −1.16 pp | [−2.29, −0.25] |

**Negative control (r = 1.0):** All 8 comparisons: 0 / 25 / 0 (all indistinguishable). No policy separates where no scheduling choice exists.

**Right-censored crossing events:** 0 across all 25 scenarios × 7 ratios × 7 policies.

**Node-specificity interpretation:**
The within-cabinet placebo preserves cabinet membership and the within-cabinet distribution of fingerprint scores while breaking the association between a particular node and its historical fingerprint. Fingerprint-guided placement beat this placebo in 20/25 held-out scenarios (median conservative bracket separation +3.54 pp, 95% CI [+0.56, +4.44] pp), providing held-out evidence that individual node-level fingerprint information contributes scheduling value beyond the cabinet-level score structure retained by the placebo.

The global placebo (22/25, +4.55 pp) shows that an arbitrary globally permuted ranking does not reproduce the observed advantage. FPSpread beating RandomSpread (20/25, +2.15 pp) provides evidence that fingerprint ranking adds value even when both policies use the spreading rule. RandomSpread vs Random (8/14/3, 0.00 pp) shows no clear primary-ratio advantage from spreading alone.

**Position-template limitation:** Fingerprint-guided placement was not statistically separated from the thermally informed structural-position template at the primary choice ratio (16/5/4, median delta_lo +0.74 pp, 95% CI [−0.82, +1.50] pp). The position template is thermally informed — it reflects the average historical fingerprint at each physical position — not a purely topological index. We do not claim fingerprints outperform all thermally informed placement strategies.

---

## Figures

| Figure | Description |
|--------|-------------|
| `artifacts/phase1/figures/fig_mc_paired.png` | Paired Random vs FP capacity across all 30 scenarios (Phase 3B development) |
| `artifacts/phase1/figures/fig_mc_dc_dist.png` | Distribution of paired ΔC with bootstrap CI (Phase 3B development) |
| `artifacts/phase1/figures/fig_mc_constraints.png` | Binding constraint breakdown and FP capacity by constraint type (Phase 3B development) |
| `artifacts/revision2/figures/fig_r2_factorial_r125.png` | Forest plot: 8 preregistered comparisons at r = 1.25 (Review-2, sc30–sc54) |
| `artifacts/revision2/figures/fig_r2_fpspread_crossover.png` | FPSpread vs FP crossover across ratio sweep (Review-2) |
| `artifacts/revision2/figures/fig_r2_policy_matrix.png` | Policy comparison matrix across all ratios (Review-2) |
| `artifacts/revision2/figures/fig_r2_robustness.png` | Supplemental: E1 cabinet-scale sensitivity and E2 beta sensitivity (H8=ROBUST, H7=STABLE) |

---

### Review-2 Sensitivity Analyses (E1/E2)

**Post-exposure disclosure:** Phases E1 and E2 were prespecified at Git commit 5733b73 before any challenge scenario (sc30–sc54) was executed. Execution occurred after primary challenge results (Phase G) were exposed, due to an omission discovered during post-analysis review. The analysis design (parameters, scenarios, comparisons, and interpretation rules) was not changed after primary-result exposure. Full disclosure: `artifacts/revision2/POST_EXPOSURE_SENSITIVITY_RECOVERY.md`.

**E1 — Cabinet-envelope scale sensitivity (H8 = ROBUST):**

FP_vs_Random at r = 1.25, 25 challenge scenarios, across 5 cabinet-envelope scale factors:

| Scale factor | n_A / n_I / n_B | Median delta_lo | 95% CI |
|---|---|---|---|
| 0.90 | 18 / 6 / 1 | +0.81 pp | [+0.002, +2.38] |
| 0.95 | 21 / 4 / 0 | +2.98 pp | [+0.55, +4.28] |
| **1.00 (primary)** | **22 / 1 / 2** | **+6.71 pp** | **[+3.92, +8.72]** |
| 1.05 | 20 / 3 / 2 | +4.40 pp | [+3.20, +5.54] |
| 1.10 | 20 / 2 / 3 | +4.69 pp | [+0.87, +5.33] |

H8 interpretation (frozen): Sign stable across [0.90, 1.10] → **ROBUST**. The median is positive at all five scale factors. At scale = 0.90 the CI just clears zero ([+0.002, +2.38]); at the primary scale the result is substantially above zero.

**E2 — Beta sensitivity (H7 = STABLE):**

FP_vs_Random at r = 1.25, 25 challenge scenarios, across 6 prespecified beta values:

| Beta label | Value | n_A / n_I / n_B | Median delta_lo |
|---|---|---|---|
| **Primary (LOO CF)** | **1.11416** | **22 / 1 / 2** | **+6.71 pp** |
| Frozen | 1.12484 | 22 / 1 / 2 | +6.48 pp |
| Prospective (M1) | 0.96 | 22 / 1 / 2 | +6.67 pp |
| Jackknife mean | 1.08293 | 22 / 1 / 2 | +5.59 pp |
| CF P5 (5th pct) | 1.06587 | 21 / 2 / 2 | +6.42 pp |
| CF P95 (95th pct) | 1.16910 | 22 / 1 / 2 | +5.35 pp |

H7 interpretation (frozen): No sign reversal across any beta value → **STABLE**. All medians positive; sign and qualitative verdict identical across all 6 beta values.

See `artifacts/revision2/sensitivity_cabinet_scale.json` (E1) and `artifacts/revision2/sensitivity_loo_beta.json` (E2).

---

## Mechanism

Fingerprint-aware placement does not reduce job heat. It **delays the accumulation** of
high-temperature node-hours by routing jobs to nodes with persistent thermal headroom
(low historical F-score).

Under the corrected revision1 model (Gate F), the dominant binding constraint for full_fp
is **cabinet electrical power** (B_cab_ratio: 20–21/25 scenarios at r = 1.25–1.5;
24–25/25 at r ≥ 2 and unrestricted). This is consistent with fingerprint-aware placement
concentrating high-demand jobs in thermally favorable cabinets, which may exhaust those
cabinets' power envelopes before the fleet-wide thermal budget is reached. The corrected
cabinet model (Gate C) is materially tighter than the pre-correction version, which bound
on node-level thermal budget (B_th) in 25/30 original Phase 3B scenarios.

The signal chain remains valid: persistent thermal differences create a real scheduling
signal, and exploiting that signal consistently delivers more capacity than ignoring it.
The revised model identifies cabinet power as the binding resource for the fingerprint-
aware policy — a distinction that matters for system operators weighing power versus
cooling constraints.

The Review-2 challenge experiment adds a further element to this chain: the association between individual nodes and their historical thermal fingerprints is load-bearing beyond cabinet-level structure. Permuting fingerprint scores among nodes within the same cabinet materially reduced scheduling performance in 20/25 held-out challenge scenarios. This does not establish a causal physical mechanism for the fingerprint; it establishes that the scheduling signal is not reducible to the cabinet-level structure retained by the placebo.

---

## Policy Regime Dependence (exploratory)

Gate F also evaluated a geographically diversified policy (full_fp_spread) that combines
thermal preference with cabinet-spread selection. Paired bootstrap comparison against
full_fp across the 25 held-out scenarios:

| Ratio r | FPSpread wins | n_ind | FP wins | Median ΔC_lower | 95% paired bootstrap CI |
|---|---|---|---|---|---|
| 1.25 | 3 | 3 | **19** | −3.36 pp | [−4.94, −1.88] |
| 1.5  | 1 | 3 | **21** | −3.29 pp | [−4.89, −2.40] |
| 2.0  | 3 | 5 | **17** | −2.88 pp | [−3.90, −1.30] |
| 4.0  | 16 | 3 | 6 | +0.54 pp | [−0.64, +1.74] |
| 8.0  | **20** | 4 | 1 | +1.53 pp | [+0.72, +2.99] |
| unrestricted | **20** | 3 | 2 | +2.85 pp | [+0.60, +3.70] |

FP's advantage over FPSpread is statistically robust at r = 1.25, 1.5, and 2.0 (bootstrap
intervals exclude zero in FP's favor). At r = 4.0, the two policies are statistically
indistinguishable (CI = [−0.64, +1.74], spanning zero). At r = 8.0 and unrestricted,
FPSpread's advantage over FP is statistically distinguishable (CI excludes zero in
FPSpread's favor). No single crossover ratio can be precisely identified from the current data.

Descriptive binding-constraint analysis shows that at r = 1.25, FPSpread is predominantly
node-thermally bound (B_ratio: 16/25 scenarios), while full_fp is cabinet-power bound.
At r = 8.0, FPSpread converges toward cabinet binding (19/25), matching full_fp's pattern.
This constraint-regime shift coincides with the performance reversal and is consistent with
a mechanism in which geographic diversification forces thermally inferior node selection
at low availability but can achieve diversification without that penalty at high availability.

**Gate F note:** The pre-specified Gate F confirmatory result is the full_fp vs full_random comparison at restricted ratios. The FPSpread regime dependence was exploratory in Gate F.

**Corrected-reference result (C1, post-exposure):** Under the corrected concurrent-load
reference on the same sc5–sc29 scenarios, FP beats FPSpread at **every nondegenerate
ratio** — verdicts 0/1/24 at r=1.25, 0/1/24 at r=1.5, 0/0/25 at r=2.0 and r=4.0,
0/4/21 at r=8.0, and 0/1/24 at unrestricted. This reverses the r=4.0, r=8.0, and
unrestricted crossover seen under the original reference. The corrected reference
imposes a tighter operating constraint; under it, FPSpread's geographic dispersion
forfeits thermally favorable capacity at every availability level tested.

**Review-2 challenge, FPSpread vs FP — all ratios (Plan H9, preregistered secondary):**
Plan H9 prespecified reporting FPSpread vs FP at all tested ratios. Results from the frozen
raw data (`gate_f_sc30-54_all_r2challenge_merged.json`), 25 scenarios, bootstrap seed 9999.
Classification: n_FPSpread = δ_lo > 0; n_FP = δ_hi < 0; n_I = brackets overlap.

| Ratio r | n_FPSpread / n_I / n_FP | Median δ_lo | 95% CI (δ_lo) | Median δ_hi | 95% CI (δ_hi) |
|---|---|---|---|---|---|
| 1.0 (degenerate) | 0 / 25 / 0 | −0.23 pp | [−0.41, 0.00] | +0.23 pp | [0.00, +0.41] |
| **1.25 (primary)** | **4 / 3 / 18** | **−2.64 pp** | **[−4.49, −2.00]** | **−2.15 pp** | **[−3.99, −0.19]** |
| 1.5 | 1 / 4 / 20 | −2.88 pp | [−5.86, −1.34] | −1.07 pp | [−5.25, −0.43] |
| 2.0 | 4 / 4 / 17 | −2.95 pp | [−3.99, −1.71] | −1.86 pp | [−3.23, +0.12] |
| 4.0 | 12 / 3 / 10 | −0.46 pp | [−2.65, +1.63] | +1.40 pp | [−1.35, +2.72] |
| 8.0 | 17 / 3 / 5 | +0.72 pp | [−0.10, +2.43] | +2.63 pp | [+1.05, +3.10] |
| unrestricted | 21 / 3 / 1 | +2.01 pp | [+1.21, +3.98] | +3.25 pp | [+2.11, +5.00] |

The crossover pattern from Gate F replicates in Review-2. At r=1.25 (primary endpoint)
and r=1.5, both δ_lo and δ_hi CIs exclude zero, indicating FP superior. At r=2.0, the
δ_lo CI excludes zero but the δ_hi CI marginally includes zero ([−3.23, +0.12]), so
full FP superiority at r=2.0 is not established — 17/25 scenarios show FP winning
definitively but the bootstrap median optimistic bound spans zero. At r=4.0 both
intervals span zero (indeterminate). At r=8.0, δ_lo CI marginally includes zero
but δ_hi CI excludes zero from above, indicating FPSpread trending positive. At
unrestricted, both intervals exclude zero from above (FPSpread superior). These are
preregistered secondary results (H9); the preregistered primary endpoint remains r=1.25 (H4).

A plausible interpretation — explicitly labeled as an interpretation, not a tested causal
mechanism — is that under limited candidate choice, forcing additional spreading restricts
direct exploitation of the most favorable individual nodes; once the choice set is large
enough, spreading and fingerprint selection can become complementary. The mechanism is
consistent with the binding-constraint regime shift but has not been separately tested.
Under the corrected reference, the crossover does not appear across the tested ratio range.

---

## Structural Position Analysis (post-exposure corrective robustness)

A reviewer raised the concern that the original C2 structural comparator (PositionLOO)
contained a formula defect: `(S_g − F_i) / (n_g − 1)` reverses node ranking within
structural groups, preferentially selecting hot nodes from groups where they are outliers.
PositionLOO was withdrawn and results are retained for provenance only. The accepted
replacement is **PositionGroupHash**: a group-constant structural score (chassis × slot ×
board × node_position) with BLAKE2b hash tie-breaking that is policy-blind and does not
leak individual node identity.

Round-7 is a **post-exposure corrective robustness analysis**, not a preregistered result.
Its value is that the corrected structural comparator produces a credible hierarchical
ordering that survives the methodology correction.

**Round-7 results (sc30–sc54, r=1.25, canonical beta=1.11416358):**

| Comparison | A/I/B | Median δ_lo | 95% CI |
|---|---|---|---|
| FP vs Random | 25/0/0 | +12.476 pp | [+11.095, +19.039] |
| FP vs WithinCabPlacebo | 24/1/0 | +10.883 pp | [+5.959, +17.399] |
| FP vs PositionGroupHash | 24/1/0 | +7.265 pp | [+5.120, +12.497] |
| PositionGroupHash vs Random | 21/4/0 | +4.582 pp | [+2.901, +8.224] |

The hierarchical ordering — Random < PositionGroupHash < WithinCabPlacebo < FP — is
consistent with a stratification from no fingerprint information (Random), through
group-level structural position (PGH), to cabinet-membership-preserving permuted
fingerprints (WithinCab), to individual node-level fingerprints (FP). FP and PGH
are both uncensored at r=1.25 (zero left-boundary scenarios each), making the
FP–PGH separation (+7.265 pp) a cleaner magnitude comparison than FP–Random (where
Random has 9/25 left-boundary scenarios). Beta sensitivity (β=0.960) preserves all
four verdicts with no B results; FP vs PGH: 23/2/0, +5.120 pp [+2.331, +11.219].

All Round-7 results must be labeled post-exposure corrective robustness in manuscript text.
See `artifacts/manuscript_completion/FINAL_SCIENTIFIC_FREEZE.md` for frozen values and
governance notes.

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
11. **Robustness** — 30 paired Monte Carlo development scenarios (common random numbers,
    varied workload draws and residual permutations) show FP-cap-10 outperforms random in
    all 30 under the pre-correction model. A preregistered held-out evaluation (Gate F, 25
    scenarios, sc5–sc29, original job-contribution reference) confirms the direction at every
    tested availability level (r = 1.25–8.0), with δ_lo ranging +3.6 to +5.6 pp. A
    preregistered challenge experiment (R2, sc30–sc54) independently replicates the primary
    finding: +6.71 pp vs Random (22/1/2) at r = 1.25. Post-exposure corrected-reference
    analyses (C2, sc30–sc54) show +12.48 pp under the revised concurrent-load cabinet
    reference and are the primary claims source per the scientific claims audit.

---

## Experimental Setup

> **Scope note:** This section documents the development-era parameters (Phase 3B, 30 scenarios,
> 8 load points, FP-cap-10 policy). The preregistered held-out evaluation (Gate F, sc5–sc29)
> and the Review-2 challenge experiment (sc30–sc54) use different scenario counts, policy sets,
> and load sweeps; their parameters are documented in
> `artifacts/revision1/analysis/r1_gate_f_heldout_analysis.py` and
> `artifacts/revision2/r2_challenge_orchestrator.py` respectively.

### Cohort

- 2,000 AMD MI250X GPU nodes across 77 Olympus rack HPE cabinets
- ~26 cohort nodes per cabinet (20.3% of each cabinet's 128 nodes)
- Thermal fingerprints: FA\_2024, trained on 2024 historical telemetry
- BETA\_F (revision1, frozen): 1.12484 (training-median; replaces published 0.957 test-set value); Review-2 primary: 1.11416 (LOO cross-fitted; −0.95% from frozen value, within the pre-specified negligible-correction threshold)
- Thermal threshold: T\_thr = 63.625°C primary / 60.602°C secondary (revision1 calibration)
- Cabinet power model: Corrected node-to-cabinet mapping (Gate C); 3.2% of original assignments
  corrected; cabinet P99 envelopes validated against telemetry (MAE 0.37 kW)

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
selected 2,637-job base workload, not all activity on those nodes. At the preregistered primary ratio (r = 1.25), the R2 Challenge median δ_lo of +6.71 pp
translates algebraically to approximately **5,300 additional cohort node-hours** per replay
window (replay-model translation only, not observed output), or approximately **0.07% of
total fleet activity** in those windows. The Gate F held-out δ_lo of +4.77 pp gives
approximately 3,800 cohort node-hours (~0.05%).

This figure is reported for scope honesty, not as the primary result. The experiment
has thermal fingerprints only for the 2,000-node study cohort. It does not show what
would happen if fingerprint-aware scheduling were deployed across all 9,856 Frontier nodes.
The cohort-relative capacity advantage — +6.71 pp (R2 Challenge, preregistered primary)
and +4.77 pp (Gate F, preregistered held-out) — is the correct primary metric.

---

## Economic Interpretation

The conventional path to more compute capacity is capital expenditure: buy more servers.
ThermalShift explores a different lever: **capacity yield** — extracting more useful work
from existing infrastructure by using measured thermal headroom more intelligently while
remaining within historical thermal and power operating envelopes.

The result is best framed as:

> Thermal fingerprints are schedulable information that existing telemetry infrastructure
> already generates. In held-out historical replay, using that information consistently
> allows the scheduler to accept materially more work before the same thermal and power
> operating envelopes are exhausted — with median conservative lower-bound advantages of
> +3.6 to +5.6 pp in cohort-relative capacity across 25 held-out scenarios and all tested
> availability levels (r = 1.25–8.0). The paired bootstrap intervals across those scenarios
> exclude zero at every ratio.

The +3.6 to +5.6 pp range (Gate F, preregistered held-out, original reference) and
+6.71 pp (R2 Challenge, preregistered) both reflect the corrected cabinet-power model and
the conservative δ_lo metric. An earlier development analysis estimated +15.5 pp under
the pre-correction model; that result is documented historically but is superseded by the
preregistered experiments and corrected-reference analyses (C2: +12.48 pp at r=1.25).

**What this is not:**

- A claim that Frontier (or any system) has a fixed percentage of spare capacity waiting to be
  reclaimed system-wide.
- A dollar-savings projection. Infrastructure costs, cooling, and capital amortization
  are not modeled.
- A claim that the advantage transfers directly from Frontier to cloud infrastructure.
  Thermal fingerprint distributions, cabinet power densities, and scheduling policies
  all differ across systems.

**What this is:**

- Evidence that persistent machine-level thermal heterogeneity, where it exists, is
  actionable scheduling information — and that the scheduling signal contains node-specific
  information beyond the cabinet-level structure retained by the within-cabinet placebo and
  beyond spreading alone, within the historical operating-envelope replay model.
- A replicable methodology: fingerprint derivation, stateful replay, Monte Carlo
  robustness testing, symmetric discrete-bound validation, preregistered factorial
  placebo decomposition.
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
  per-scenario variation in ΔC at n = 25. The variance is genuine but its structural
  drivers are not identified.

- **Corrected cabinet model changes binding regime.** The original development analysis
  (Phase 3B) was conducted with a pre-correction cabinet-power node mapping that placed
  3.2% of nodes in incorrect cabinets. The corrected mapping (Gate C) tightens cabinet
  power constraints and shifts the dominant binding regime from node-level thermal budget
  to cabinet power for fingerprint-aware policies. The Gate F held-out result
  (+3.6 to +5.6 pp, preregistered, original reference) and R2 Challenge (+6.71 pp,
  preregistered) both reflect the corrected model. The corrected-reference analysis C2
  shows +12.48 pp at r=1.25 under the revised concurrent-load cabinet reference and is
  the primary claims source per the scientific claims audit. The development-era +15.5 pp
  should not be used as the primary result.

- **Bootstrap intervals are scenario-specific, not population bounds.** The paired
  bootstrap intervals reported for Gate F are computed across the 25 held-out workload-
  replay scenarios. They quantify uncertainty in the median paired advantage over those
  scenarios; they do not represent population-level uncertainty bounds for real HPC
  deployments with different workloads, thermal profiles, or scheduling policies.

- **Position-template separation is unresolved at the primary ratio.** Fingerprint-guided
  placement was not statistically separated from the thermally informed structural-position
  template at r = 1.25 (16/5/4, median conservative bracket separation +0.74 pp, 95% CI
  [−0.82, +1.50] pp). The position template is thermally informed — it reflects the average
  historical fingerprint at each physical position — not a purely topological index. We do
  not claim fingerprints outperform all thermally informed placement strategies.

- **Node-level scheduling evidence is within the replay model.** The Review-2 challenge
  experiment provides held-out evidence that the association between individual nodes and
  their historical thermal fingerprints is load-bearing beyond cabinet-level structure in
  the historical operating-envelope replay model. This does not establish a causal physical
  mechanism for the fingerprint signal, and does not constitute evidence about live
  scheduling behavior outside the replay framework.

- **Cabinet-envelope scaling at ±10% (H8=ROBUST, with caveat at −10%).** The E1 sensitivity
  analysis tested FP_vs_Random under ±10% cabinet-envelope scaling. The sign of the advantage
  is positive at all five tested scale factors. At −10% scale, the advantage is substantially
  weakened (median +0.81 pp, 95% CI [+0.002, +2.38]), with the CI barely clearing zero.
  Claims of robustness to cabinet-envelope calibration error should not exceed this range.

- **Thermal threshold T_thr not directly tested.** The primary thermal threshold
  (T_thr = 63.625°C) was fixed at Gate F and was not separately varied in the Review-2
  sensitivity analyses. The E1 cabinet-scale sensitivity is a partial proxy for calibration
  uncertainty but does not directly test T_thr sensitivity.

- **Sensitivity analyses executed post-exposure.** Phases E1 and E2 were prespecified before
  challenge execution but run after primary results were observed, due to an omission
  discovered during post-analysis review. The design was not changed after exposure.
  Full disclosure: `artifacts/revision2/POST_EXPOSURE_SENSITIVITY_RECOVERY.md`.

---

## Reproducing the Results

All primary analyses (Gate F, R2 Challenge, C1/C2 corrected-reference, Round-7) can be
reproduced from the frozen artifacts in this repository. The raw Frontier telemetry
(`THERMALSHIFT_DATA_DIR`) is required only to re-derive fingerprints from scratch or
regenerate the base test-job parquet. The Phase 3B development analysis
(`phase3b_mc_analysis.py`) additionally requires the external OLCF job metadata file
`frontier-completed-job-info.parquet` for its workload-sensitivity section; without it
the script will raise `FileNotFoundError` at that step.

**Prerequisites:** Python 3.9+, packages in `requirements.txt`.

### Primary challenge experiment (R2, sc30–54)
```bash
python artifacts/revision2/r2_gate_f_challenge_analysis.py
# output: artifacts/revision2/challenge_analysis.json

python artifacts/revision2/analyze_sensitivity_e1.py
python artifacts/revision2/analyze_sensitivity_e2.py
```

### Corrected-reference analyses — primary claims source
```bash
python artifacts/manuscript_completion/analysis/c1_correctedref_analysis.py
# reads: artifacts/manuscript_completion/results/gate_f_sc5-29_all.json
# output: artifacts/manuscript_completion/results/c1_correctedref_analysis.json

python artifacts/manuscript_completion/analysis/c2_correctedref_analysis.py
# reads: artifacts/manuscript_completion/results/gate_f_sc30-54_1p25_c2manuscript.json
# output: artifacts/manuscript_completion/results/c2_correctedref_analysis.json
```

### Structural position analysis (Round-7, PositionGroupHash)
```bash
python artifacts/manuscript_completion/analysis/c7_analysis.py
# reads: artifacts/manuscript_completion/results/gate_f_sc30-54_1p0_1p25_c7primary.json
# output: artifacts/manuscript_completion/results/c7primary_analysis.json
```

### Gate F held-out evaluation (preregistered)
```bash
python artifacts/revision1/analysis/r1_gate_f_heldout_analysis.py
# reads per-scenario JSON files in artifacts/revision1/results/
# output: artifacts/revision1/results/gate_f_heldout_analysis.json
```

### Development analysis (Phase 3B, historical)

**Note:** `phase3b_mc_analysis.py` requires `frontier-completed-job-info.parquet` from the
OLCF dataset (set `THERMALSHIFT_DATA_DIR`). `phase3b_mc_validate.py` and
`phase3b_figures.py` run from frozen artifacts only.

```bash
python artifacts/phase1/analysis/phase3b_mc_analysis.py
python artifacts/phase1/analysis/phase3b_mc_validate.py
python artifacts/phase1/analysis/phase3b_figures.py
```

Provenance hashes for all frozen raw result files are recorded in
`artifacts/manuscript_completion/PROVENANCE_MANIFEST.md`.

---

## File Structure

```
thermalops/
  README.md         — this file
  DATA.md           — dataset access and derived artifact map
  requirements.txt  — Python dependencies
  artifacts/
    phase0/         — fleet fingerprint diagnostic (Phase 0)
    phase1/         — fingerprint derivation, capacity model, Phase 3B MC (development)
      analysis/
        phase3a_fingerprint_2024.parquet  thermal fingerprints (FA_2024, 2,000 nodes)
        phase3a_test_set.parquet          2,637 base test jobs
        phase3b_mc.py                     Monte Carlo simulation
        phase3b_mc_results.json           frozen MC outputs (30 dev scenarios)
        phase3b_mc_analysis.py            summary statistics
        phase3b_figures.py                figure generation
    revision1/      — Gate F held-out design, M1-M6 manuscript analyses
      analysis/
        r1_gate_f_heldout_analysis.py     frozen held-out summarizer (sc5-29)
        r1_gate_f_helpers.py              shared estimand functions
      results/
        gate_f_heldout_analysis.json      frozen Gate F output
    revision2/      — R2 preregistered challenge experiment (sc30-54)
      r2_challenge_orchestrator.py        parallel challenge runner
      r2_gate_f_challenge_analysis.py     preregistered analysis script
      figures/
        fig_r2_factorial_r125.png         primary result figure (8 comparisons, r=1.25)
        fig_r2_robustness.png             E1/E2 sensitivity panels
      results/
        gate_f_sc30-54_all_r2challenge_merged.json  frozen challenge outputs
        challenge_analysis.json                      frozen analysis output
    revision3/      — Task-D F2 reference construction, supplementary audits
    manuscript_completion/
      analysis/     — C1-C8 analysis scripts (corrected-reference, equivalence gates)
      runners/      — parallel execution infrastructure for C1-C8
      results/      — frozen raw simulation outputs and analysis JSONs
        gate_f_sc5-29_all.json              C1 raw (sc5-29, corrected reference)
        gate_f_sc30-54_1p25_c2manuscript.json  C2 raw (sc30-54, r=1.25)
        c1_correctedref_analysis.json       C1 frozen output
        c2_correctedref_analysis.json       C2 frozen output
        c7primary_analysis.json             Round-7 / PositionGroupHash frozen output
      PROVENANCE_MANIFEST.md               SHA256 hashes for all frozen raw files
      FINAL_SCIENTIFIC_CLAIMS_AUDIT.md     authoritative claims table with evidence sources
      FINAL_SCIENTIFIC_FREEZE.md           canonical accepted values and governance
  docs/
    PHASE_0_THERMAL_FINGERPRINT.md
    THERMALOPS_FEASIBILITY.md
```

---

## Citation Context

Frontier supercomputer: Oak Ridge Leadership Computing Facility, ORNL.
Hardware: HPE Cray EX, 77 Olympus rack HPE cabinets x 128 AMD compute nodes = 9,856 nodes; 4 AMD MI250X GPUs per node.
Dataset: OLCF Frontier job telemetry 2024–2025. DOI: [10.13139/OLCF/3013979](https://doi.ccs.ornl.gov/dataset/2cfa2292-3f9d-549c-b2d2-c9aff1557218).
Code archive: [10.5281/zenodo.23020901](https://doi.org/10.5281/zenodo.23020901).

---

## AI Disclosure

Claude (Anthropic) was used to verify the reproducibility audit of this repository — confirming that analysis scripts, frozen result artifacts, protocol documentation, and configuration files are present and consistent with the claims in the accompanying manuscript.
