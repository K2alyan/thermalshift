# Reviewer Response — Review-2 (ThermalShift)

**Prepared from frozen challenge evidence at commit f1c78a3.**
**Do not edit numerical claims without re-running the frozen analysis pipeline.**

---

## Response to Reviewer Concern N1: Node-Level vs. Cabinet-Level Confounding

**Concern (paraphrase):** The fingerprint scheduling advantage could reflect cabinet-level
structure or other correlated signals rather than individual node-level thermal identity.
The original experiment cannot isolate the contribution of node-specific fingerprint ranking.

---

### Overview

We agree that the original Gate F experiment could not separate individual node-level
fingerprint identity from cabinet-level structure. To address this directly, we designed,
preregistered, and executed a 25-scenario held-out challenge experiment with a factorial
placebo structure (Review-2, sc30–sc54).

The scientific code and analysis plan were frozen at Git commit 5733b73
(runner SHA256 750150c337a1f81368bdba35e2af6ccda23f2917297d5f9ab3ebf51dd8281856)
before any challenge scenario was executed. The analysis plan specifies 5,000 bootstrap
replicates, bootstrap seed 9999, and all eight preregistered comparisons. A 16-check
completion audit — verifying seeds, provenance, structural integrity, and absence of
NaN/Inf across all 25 × 7 × 7 output cells — passed before analysis was run. Results
are frozen at evidence commit f1c78a3 (merged artifact SHA256
181161082cbf79e32fb138779af20327fd026d5383d70a942e7373a64d635a71, analysis SHA256
3a8bbd0aba95209e8d383bb94f9b57b93df98a37d8cfa7423d8db0db115edac4).

---

### Primary Result (H4)

At the preregistered 1.25× choice ratio, fingerprint-guided placement (full_fp)
produced a median conservative bracket separation of **+6.71 percentage points** versus
random placement (bootstrap 95% CI [+3.92, +8.72] pp; 22/25 held-out scenarios
definitely FP, 1 indistinguishable, 2 definitely random). The preregistered threshold
was 13/25; the result is designated **primary_success**.

The bracket separation is delta_lo = C_lower(full_fp) − C_upper(full_random), the
conservative lower bound on the capacity advantage: the lower bound of the FP bracket
exceeds the upper bound of the random bracket.

---

### Decisive Node-Specificity Test: FP vs. Within-Cabinet Permutation Placebo

The within-cabinet permutation placebo (fp_withincab_placebo) preserves cabinet
membership and the within-cabinet distribution of fingerprint scores while breaking
the association between a particular node and its historical fingerprint. Nodes within
each cabinet receive a randomly permuted fingerprint score drawn from the same cabinet's
score distribution, so the cabinet-level composition of assigned scores is unchanged
but no individual node retains its own fingerprint.

Fingerprint-guided placement beat this placebo in **20/25 held-out scenarios** (5
indistinguishable, 0 definitely placebo; median conservative bracket separation
+3.54 pp, bootstrap 95% CI [+0.56, +4.44] pp). This provides held-out evidence
that the association between individual nodes and their historical thermal fingerprints
is load-bearing beyond the cabinet-level score structure retained by the placebo:
permuting fingerprint scores among nodes within the same cabinet materially reduced
scheduling performance.

We use "provides held-out evidence that … contributes … beyond cabinet-level structure"
rather than "proves" or "directly isolates." The result is within the historical
operating-envelope replay model and does not establish a causal physical mechanism for
the fingerprint signal.

---

### Complementary Factorial Comparisons at r = 1.25

All comparisons are preregistered. delta_lo = C_lower_A − C_upper_B.

| Comparison | A / Indist / B | Median delta_lo | Bootstrap 95% CI |
|---|---|---|---|
| **FP vs Random** (primary endpoint) | **22 / 1 / 2** | +6.71 pp | [+3.92, +8.72] |
| **FP vs WithinCabPlacebo** (node-specificity) | **20 / 5 / 0** | +3.54 pp | [+0.56, +4.44] |
| FP vs GlobalPlacebo | 22 / 1 / 2 | +4.55 pp | [+2.95, +7.82] |
| FPSpread vs RandomSpread | 20 / 5 / 0 | +2.15 pp | [+0.52, +4.25] |
| RandomSpread vs Random | 8 / 14 / 3 | 0.00 pp | [−0.26, +0.03] |
| FPSpread vs FP | 4 / 3 / 18 | −2.64 pp | [−4.49, −2.00] |
| FP vs PositionTemplate | 16 / 5 / 4 | +0.74 pp | [−0.82, +1.50] |
| FPSpread vs PositionTemplate | 6 / 11 / 8 | −1.16 pp | [−2.29, −0.25] |

**Interpretation of the factorial pattern:**

1. **Global placebo (22/25, +4.55 pp):** The effect is not reproduced by a globally
   permuted arbitrary ranking. The result requires real fingerprint rankings, not
   fingerprint-shaped noise.

2. **FPSpread vs RandomSpread (20/25, +2.15 pp):** Fingerprint ranking retains
   scheduling value even when both compared policies use the spreading rule. The
   advantage is not attributable solely to the spreading mechanism.

3. **RandomSpread vs Random (8/14/3, 0.00 pp, CI [−0.26, +0.03]):** Spreading alone
   shows no clear primary-ratio advantage. The primary-ratio improvement in full_fp
   is not explained by spreading mechanics.

Together, these comparisons address the N1 concern substantially better than FP-vs-Random
alone and provide held-out evidence that the scheduling signal contains node-specific
information beyond cabinet membership, arbitrary global permutation, and spreading alone
within the historical operating-envelope replay model.

---

### Negative Control (r = 1.0)

All 8 comparisons at r = 1.0: 0 definitely-A, 25 indistinguishable, 0 definitely-B.
At r = 1.0 the scheduler has no candidate choice, so no policy can create separation.
This confirms the comparison machinery does not generate spurious separation where
no scheduling choice exists.

Zero right-censored crossing events occurred across all 25 scenarios × 7 ratios ×
7 policies (1,225 policy×ratio cells total).

---

### Important Limitation: Position Template

Fingerprint-guided placement was **not statistically separated** from the thermally
informed structural-position template at the primary choice ratio (16/5/4, median
conservative bracket separation +0.74 pp, 95% CI [−0.82, +1.50] pp, spanning zero).

The position template is thermally informed: it reflects the average historical
fingerprint at each physical structural position (chassis/slot/board/node_pos), not
a purely topological index. We do not claim fingerprints outperform all thermally
informed placement strategies. A defensible statement is:

> Node-specific fingerprint ranking adds scheduling information beyond cabinet
> membership and spreading, while its advantage over a thermally informed
> structural-position template is not statistically resolved at the primary choice ratio.

---

### Recommended Updated Main-Text Claim

**Replace:** "the current experiment does not isolate how much benefit is uniquely
individual-node fingerprint ranking"

**With:**

> Persistent node-level thermal fingerprints provide held-out scheduling value beyond
> random placement, within-cabinet permutation placebos, and spreading alone under the
> historical operating-envelope replay model.

**Quantitative form:**

> At the preregistered 1.25× choice ratio, fingerprint-guided placement produced a
> median conservative bracket separation of 6.71 percentage points versus random
> placement (bootstrap 95% CI [+3.92, +8.72] pp) and 3.54 percentage points versus
> the within-cabinet permutation placebo (95% CI [+0.56, +4.44] pp). Both intervals
> exclude zero.

**Required boundary sentence:**

> Fingerprint-guided placement was not statistically separated from the thermally
> informed structural-position template at the primary choice ratio.

---

### Secondary Finding: Choice-Set-Dependent FPSpread Crossover (preregistered)

The FPSpread vs FP comparison shows a crossover across the ratio sweep, preregistered
as a secondary finding:

| Ratio | A (FPSpread) / I / B (FP) | Median delta_lo |
|---|---|---|
| r = 1.25 | 4 / 3 / **18** | −2.64 pp |
| r = 1.5  | 1 / 4 / **20** | −2.88 pp |
| r = 2.0  | 4 / 4 / **17** | −2.95 pp |
| r = 4.0  | 12 / 3 / 10    | −0.46 pp |
| r = 8.0  | **17** / 3 / 5 | +0.72 pp |
| unrestricted | **21** / 3 / 1 | +2.01 pp |

A plausible interpretation — explicitly labeled as interpretation, not a tested
causal mechanism — is that under limited candidate choice, imposing a spreading
constraint prevents direct exploitation of the most favorable individual nodes; once
the choice set is large enough, spreading and fingerprint selection become complementary.
This is consistent with the binding-constraint regime shift documented in Gate F but
has not been separately tested as a causal claim.

---

### Provenance Summary

| Item | Value |
|---|---|
| Frozen Git commit | 5733b73 |
| Frozen runner SHA256 | 750150c337a1f81368bdba35e2af6ccda23f2917297d5f9ab3ebf51dd8281856 |
| Evidence-freeze commit | f1c78a3 |
| Merged artifact SHA256 | 181161082cbf79e32fb138779af20327fd026d5383d70a942e7373a64d635a71 |
| Analysis SHA256 | 3a8bbd0aba95209e8d383bb94f9b57b93df98a37d8cfa7423d8db0db115edac4 |
| Completion audit SHA256 | 33ff32a8a9a996d9c26c1aa94a302b2696010fdd7def1223ce741891f14f2768 |
| n_scenarios | 25 (sc30–sc54) |
| Bootstrap replicates | 5,000 |
| Bootstrap seed | 9999 |
| Completion audit | PASS (16/16 checks) |
| Seed mismatches | 0 |
| NaN/Inf fields | 0 |
| Invariant violations | 0 |
| Right-censored crossings | 0 |
| sc30/sc31/sc32 SHA256 verified | true |
| Incident record present | true |
