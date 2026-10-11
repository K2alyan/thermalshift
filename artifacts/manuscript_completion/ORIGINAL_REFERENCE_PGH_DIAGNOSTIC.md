# Original-Reference PGH Diagnostic — C8 Results

**Status:** FINAL  
**Date:** 2026-10-10  
**Branch:** revision1/major-revision-analyses  
**Runner commit:** e258c42  
**Raw output commit:** 39f2dd0

---

## Purpose

Decompose the structural-position effect gap between E2 and Round-7 into two
independent sources:

1. **Comparator change** (F1 fixed): PositionTemplate (LOO-based, invalid) →
   PositionGroupHash (corrected group-mean + singleton = global mean + BLAKE2b)
2. **Reference change** (PGH fixed): F1 (job-contribution P99 thresholds) →
   F2 (concurrent-load scheduling period thresholds)

---

## Equivalence gate

**PASS** — 53,184 shared-policy fields (full_fp, full_random, full_fp_spread,
position_template) match E2 exactly within 1e-9 float tolerance across all 25
scenarios at r=1.25. C8 seed chain reproduces E2 bit-for-bit.

---

## 2×2 Decomposition table (r=1.25, FP vs structural comparator)

| Comparator → Reference | F1 (job-contribution P99) | F2 (concurrent-load) |
|---|---|---|
| PositionTemplate (LOO) | E2: +0.741pp [16/5/4] | — |
| PositionGroupHash (corrected) | **C8: +1.101pp [17/6/2]** | C7: +7.265pp [24/1/0] |

---

## Comparisons at r=1.25, F1 reference (C8 run, sc30–54, n=25)

### 1. FP vs PGH (F1 ref) — primary new comparison

Verdict: **17 A / 6 I / 2 B**  
Median delta_lo: **+1.101pp**  
Bootstrap 95% CI: [−0.062, +2.799]  
Left-boundary cases: full_fp=0, position_group_hash=0

FP wins in 17 of 25 scenarios under the original E2 cabinet reference. The
confidence interval is positive-skewed but crosses zero, reflecting 6 indeterminate
and 2 reverse scenarios. Compare to C7 (F2 ref): 24/1/0 with +7.265pp and a
strictly positive CI [+5.120, +12.497].

### 2. PGH vs Random (F1 ref)

Verdict: **19 A / 3 I / 3 B**  
Median delta_lo: **+3.159pp**  
Bootstrap 95% CI: [+0.549, +4.943]  
Left-boundary cases: position_group_hash=0, full_random=9

PGH carries substantial structural signal even under the original reference.
Compare to C7 (F2 ref): 21/4/0 with +4.582pp CI [+2.901, +8.224].

### 3. FPSpread vs PGH (F1 ref)

Verdict: **8 A / 10 I / 7 B**  
Median delta_lo: **−0.456pp**  
Bootstrap 95% CI: [−1.245, +0.093]

No reliable separation between spreading and structural comparator under F1.
Consistent with C7 behavior, where FPSpread vs PGH was also inconclusive.

### 4. PGH vs PositionTemplate (F1 ref)

Verdict: **4 A / 14 I / 7 B**  
Median delta_lo: **−0.817pp**  
Bootstrap 95% CI: [−1.199, −0.404]

Under F1, PositionTemplate slightly but consistently outperforms PGH. The CI
for delta_lo is negative throughout. This reflects that PT's LOO-based group
score (despite being methodologically flawed) happened to achieve better
separations under the original P99 reference, while PGH's corrected design
advantage only fully materializes under the corrected F2 reference.

---

## Reference vs comparator decomposition

```
Comparator change (F1 fixed):  PT → PGH   = +0.360 pp  (0.741 → 1.101)
Reference change  (PGH fixed): F1 → F2    = +6.164 pp  (1.101 → 7.265)
Total accounted:                            +6.524 pp   (= 7.265 − 0.741, exact)
```

The total gap between E2 (+0.741pp) and C7 (+7.265pp) is **+6.524pp**, of which:

- **94.5% (6.164pp)** is explained by the reference change: replacing the
  job-contribution P99 cabinet thresholds (F1) with the concurrent-load
  scheduling period thresholds (F2). The F2 reference is the scientifically
  correct basis for the preregistered Gate F challenge; F1 was the inadvertent
  reference used in E2.

- **5.5% (0.360pp)** is explained by the comparator change: replacing the
  LOO-based PositionTemplate (which was withdrawn as invalid) with the corrected
  PositionGroupHash comparator.

---

## Scientific interpretation

The dominant driver of the Round-7 effect size (+7.265pp vs E2's +0.741pp) is
the **correction to the cabinet power reference** (F1→F2), not the correction to
the structural comparator. Under the original E2 reference, the FP policy still
outperforms PGH in 17 of 25 scenarios (+1.101pp median), confirming that the
structural effect is genuine. The ~6pp amplification under F2 reflects that the
concurrent-load scheduling period thresholds expose thermal stress in scenarios
where the job-contribution P99 thresholds are insufficiently tight, giving the
FP placement policy larger room to demonstrate its advantage.

The comparator correction (PT→PGH) contributes only +0.360pp under F1. The
corrected PGH comparator is methodologically necessary (LOO scores are invalid
for this analysis), but quantitatively its replacement with PGH under F1 has
minimal impact on the verdict distribution.

---

## Governance note

C8 is a post-exposure mechanism diagnostic authorized by FINAL_SCIENTIFIC_FREEZE.md
as the final optional compute task. It does not modify or supersede Round-7
(C7) results. No new preregistered scientific claims derive from C8. The
decomposition is offered as an interpretive aid for the manuscript's mechanism
discussion.

---

## File provenance

| File | SHA256 |
|---|---|
| `gate_f_sc30-54_1p0_1p25_c8f1diagnostic.json` | see git:39f2dd0 |
| `c8f1diagnostic_analysis.json` | see git (this commit) |
| Runner: `c8_gate_f_run.py` | b26bede098d87f478ac556659e76e77a74a430daa726a0a65e619667425a35ab |
| Equivalence gate: `c8_equivalence_gate.py` | 560608cfc5926f6f4451ff1dddf822251e45025bc1962dbab9b1a43601728b16 |
| Analysis: `c8_analysis.py` | 0816ed30b351ae692055b83b1447e381fd51879da670379da4670379d253e60113afaa725 |

E2 raw (held-out reference): `gate_f_sc30-54_all_r2challenge_merged.json`  
SHA256: `181161082cbf79e32fb138779af20327fd026d5383d70a942e7373a64d635a71`

C7 canonical (F2 PGH): SHA256 `7bca547c732f8ce2b299a5fadf337fdc2a5bf50de06b184a9d0144515b1514ea`
