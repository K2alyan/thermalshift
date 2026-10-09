# C2 Post-Run Compatibility Note

**Branch:** revision1/major-revision-analyses  
**Raw C2 commit:** 65ca107  
**Analysis commit:** 96b2ade  
**This note commit:** (see git log)

---

## Context

Three scripts were modified after C2 results existed but before this note was
written. All three changes were required by platform/API constraints, not by
scientific considerations. This note documents each change and independently
verifies that no scientific result was altered.

---

## 1. c2_sc30_equivalence_gate.py — Unicode console character

**Change:** `≤` (U+2264) replaced by `<=` in one trailing `print()` call.  
**Why:** Windows console (cp1252) cannot encode U+2264; the gate raised
`UnicodeEncodeError` after printing `[GATE PASS]`.  
**Scientific impact:** None. The change is in a print statement that executes
after the gate logic has already exited successfully. The equivalence
calculation (field-by-field numeric comparison with tol=1e-9) is unchanged.  
**Verification:** The gate re-ran cleanly and printed `[GATE PASS]` with
exit code 0. The equivalence check itself is identical.

---

## 2. c4_cabinet_diagnostic.py — Unicode box-drawing console text

**Change:** `──` (U+2500 box-drawing) replaced by `--` in one console
summary header line.  
**Why:** Same cp1252 encoding constraint as above.  
**Scientific impact:** None. The change is in a `print()` call that produces
a human-readable console header after all JSON and Markdown outputs are
already written. The cabinet-accounting aggregation, enrichment ratios, and
per-scenario distributions are unchanged.  
**Verification:** C4 re-ran and produced identical JSON and Markdown outputs.

---

## 3. c2_correctedref_analysis.py — scipy sign-test API

**Change:** `scipy.stats.binom_test(k, n, 0.5, alternative="two-sided")`
replaced by `scipy.stats.binomtest(k, n, 0.5, alternative="two-sided").pvalue`  
**Why:** `scipy.stats.binom_test` was removed in scipy ≥ 1.12. The installed
environment only provides the current `binomtest` API. The two functions
implement the same two-sided exact binomial test.  
**Scientific impact:** Requires independent verification (see below).

### Independent verification of sign-test results

For each of the 8 comparisons, the two-sided binomial p-value was recomputed
directly using `math.comb` (no scipy dependency):

```
p = min(1, 2 * sum(comb(n, i) for i in range(k_min + 1)) / 2**n)
where n = n_A + n_B  (decisive scenarios only)
      k_min = min(n_A, n_B)
```

Results (all |diff| = 0.00e+00 relative to both scipy.binomtest and stored value):

| Comparison | n_A | n_B | n | k_min | exact p (math.comb) | stored p | diff |
|---|---|---|---|---|---|---|---|
| FP_vs_Random | 25 | 0 | 25 | 0 | 5.960464e-08 | 5.960464e-08 | 0 |
| FP_vs_WithinCab | 24 | 0 | 24 | 0 | 1.192093e-07 | 1.192093e-07 | 0 |
| FP_vs_Global | 25 | 0 | 25 | 0 | 5.960464e-08 | 5.960464e-08 | 0 |
| FP_vs_PositionLOO | 25 | 0 | 25 | 0 | 5.960464e-08 | 5.960464e-08 | 0 |
| FPSpread_vs_RandSpread | 23 | 0 | 23 | 0 | 2.384186e-07 | 2.384186e-07 | 0 |
| FPSpread_vs_FP | 0 | 25 | 25 | 0 | 5.960464e-08 | 5.960464e-08 | 0 |
| RandSpread_vs_Random | 5 | 6 | 11 | 5 | 1.000000e+00 | 1.000000e+00 | 0 |
| FPSpread_vs_PositionLOO | 24 | 0 | 24 | 0 | 1.192093e-07 | 1.192093e-07 | 0 |

Note on RandSpread_vs_Random: n=11, k_min=5. The exact mass
sum(comb(11,i) for i in range(6)) / 2^11 = 1024/2048 = 0.5, so p = min(1, 2*0.5) = 1.0
exactly. This is consistent with a symmetric binomial distribution at its median.

### Independent Holm-Bonferroni verification

Holm adjustment recomputed independently from the 8 raw p-values above
(same algorithm: sort ascending, adjusted[i] = min(1, max(running_max, (k-rank)*p_raw))):

| Comparison | stored Holm p | indep Holm p | diff |
|---|---|---|---|
| FP_vs_Random | 4.768372e-07 | 4.768372e-07 | 0 |
| FP_vs_WithinCab | 4.768372e-07 | 4.768372e-07 | 0 |
| FP_vs_Global | 4.768372e-07 | 4.768372e-07 | 0 |
| FP_vs_PositionLOO | 4.768372e-07 | 4.768372e-07 | 0 |
| FPSpread_vs_RandSpread | 4.768372e-07 | 4.768372e-07 | 0 |
| FPSpread_vs_FP | 4.768372e-07 | 4.768372e-07 | 0 |
| RandSpread_vs_Random | 1.000000e+00 | 1.000000e+00 | 0 |
| FPSpread_vs_PositionLOO | 4.768372e-07 | 4.768372e-07 | 0 |

All 8 raw p-values and all 8 Holm-adjusted p-values match the stored values
with |diff| = 0 (exact, since k_min=0 in 7 of 8 cases uses integer arithmetic).

---

## Verdict

**POST-OUTCOME COMPATIBILITY FIX VERIFIED — NO SCIENTIFIC RESULT CHANGE**

The three post-outcome edits are confirmed to be print/API compatibility fixes
only. The A/I/B tallies, median delta_lo values, bootstrap CIs, sign-test
p-values, and Holm-adjusted p-values in c2_correctedref_analysis.json are
unchanged and independently verified.
