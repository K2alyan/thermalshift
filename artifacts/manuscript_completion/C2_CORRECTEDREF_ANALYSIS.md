# C2 Corrected-Reference Analysis

**Branch:** revision1/major-revision-analyses  
**Raw source SHA256:** `b4dbc4bc0f8646f197d0a575f42dc785e97710f22460c7f2c8a1913866c6b129`  
**Analysis script SHA256:** `233dd9329e8982781d1128362bb60973fbde999b7b0527bf21ea0223751bbc5f`  
**Scenarios:** sc30-sc54 (n=25)  
**Ratio:** r=1.25 only  
**Bootstrap:** 5000 draws, seed 9999, percentile 95% CI  
**Multiple testing:** Holm-Bonferroni, k=8, alpha=0.05  

---

## 1. Eight Pairwise Comparisons at r=1.25

Estimand: `delta_lo = C_lower(A) - C_upper(B)` · `delta_hi = C_upper(A) - C_lower(B)`  
Verdict: **A** if delta_lo > 0, **B** if delta_hi < 0, **I** otherwise  
Sign test: two-sided binomial on decisive (A or B) scenarios; Holm-adjusted p.

| # | Comparison | A/I/B | Decisive | med delta_lo | 95% CI delta_lo | Sign p (raw) | Sign p (Holm) | Sig? |
|---|-----------|-------|----------|-------------|-----------------|-------------|--------------|------|
| 1 | FP_vs_Random | 25A/0I/0B | 25 | +12.4755 | [+11.0948, +19.0385] | 0.0000 | 0.0000 | YES |
| 2 | FP_vs_WithinCab | 24A/1I/0B | 24 | +10.8828 | [+5.9586, +17.3991] | 0.0000 | 0.0000 | YES |
| 3 | FP_vs_Global | 25A/0I/0B | 25 | +12.3136 | [+10.8828, +17.3991] | 0.0000 | 0.0000 | YES |
| 4 | FP_vs_PositionLOO | 25A/0I/0B | 25 | +13.9477 | [+12.2331, +21.9755] | 0.0000 | 0.0000 | YES |
| 5 | FPSpread_vs_RandSpread | 23A/2I/0B | 23 | +4.4153 | [+2.1392, +5.4217] | 0.0000 | 0.0000 | YES |
| 6 | FPSpread_vs_FP | 0A/0I/25B | 25 | -9.1823 | [-17.9098, -6.6040] | 0.0000 | 0.0000 | YES |
| 7 | RandSpread_vs_Random | 5A/14I/6B | 11 | -0.1895 | [-0.5840, +0.0000] | 1.0000 | 1.0000 | no |
| 8 | FPSpread_vs_PositionLOO | 24A/1I/0B | 24 | +4.9611 | [+2.2553, +8.3403] | 0.0000 | 0.0000 | YES |

---

## 2. Q1–Q8 Answers

### Q1: FP_vs_Random
**A:** `full_fp`  **B:** `full_random`  
**Result:** 25A/0I/0B  
**Conclusion:** full_fp beats full_random in 25/25 scenarios (25 decisive, 25A/0I/0B); median delta_lo=+12.4755pp; sign test Holm-significant.  

### Q2: FP_vs_WithinCab
**A:** `full_fp`  **B:** `fp_withincab_placebo`  
**Result:** 24A/1I/0B  
**Conclusion:** full_fp beats fp_withincab_placebo in 24/25 scenarios (24 decisive, 24A/1I/0B); median delta_lo=+10.8828pp; sign test Holm-significant.  

### Q3: FP_vs_Global
**A:** `full_fp`  **B:** `fp_global_placebo`  
**Result:** 25A/0I/0B  
**Conclusion:** full_fp beats fp_global_placebo in 25/25 scenarios (25 decisive, 25A/0I/0B); median delta_lo=+12.3136pp; sign test Holm-significant.  

### Q4: FP_vs_PositionLOO
**A:** `full_fp`  **B:** `position_loo`  
**Result:** 25A/0I/0B  
**Conclusion:** full_fp beats position_loo in 25/25 scenarios (25 decisive, 25A/0I/0B); median delta_lo=+13.9477pp; sign test Holm-significant.  

### Q5: FPSpread_vs_RandSpread
**A:** `full_fp_spread`  **B:** `random_spread`  
**Result:** 23A/2I/0B  
**Conclusion:** full_fp_spread beats random_spread in 23/25 scenarios (23 decisive, 23A/2I/0B); median delta_lo=+4.4153pp; sign test Holm-significant.  

### Q6: FPSpread_vs_FP
**A:** `full_fp_spread`  **B:** `full_fp`  
**Result:** 0A/0I/25B  
**Conclusion:** full_fp beats full_fp_spread in 25/25 scenarios (25 decisive, 0A/0I/25B); median delta_lo=-9.1823pp; sign test Holm-significant.  

### Q7: RandSpread_vs_Random
**A:** `random_spread`  **B:** `full_random`  
**Result:** 5A/14I/6B  
**Conclusion:** Indeterminate: 5A/14I/6B in 25 scenarios; median delta_lo=-0.1895pp; sign test not Holm-significant.  

### Q8: FPSpread_vs_PositionLOO
**A:** `full_fp_spread`  **B:** `position_loo`  
**Result:** 24A/1I/0B  
**Conclusion:** full_fp_spread beats position_loo in 24/25 scenarios (24 decisive, 24A/1I/0B); median delta_lo=+4.9611pp; sign test Holm-significant.  

---

## 3. Absolute Capacity — r=1.25

| Policy | med C_lower | q25 | q75 | IQR | n_lb | n_rc |
|--------|------------|-----|-----|-----|------|------|
| full_random | 0.1028 | 0.0000 | 3.4807 | 3.4807 | 9 | 0 |
| full_fp | 15.3541 | 12.2331 | 22.8298 | 10.5967 | 0 | 0 |
| position_loo | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 19 | 0 |
| full_fp_spread | 5.4165 | 2.3820 | 11.3436 | 8.9616 | 0 | 0 |
| random_spread | 0.1199 | 0.0000 | 3.9072 | 3.9072 | 10 | 0 |
| fp_global_placebo | 0.6414 | 0.0000 | 4.3829 | 4.3829 | 5 | 0 |
| fp_withincab_placebo | 4.0375 | 1.0722 | 10.8275 | 9.7553 | 2 | 0 |

---

## 4. Binding Constraints — r=1.25

| Policy | n_crossing | B_ratio | B_thermal | Other | n_left_boundary |
|--------|-----------|---------|-----------|-------|----------------|
| full_random | 16 | 14 | 0 | 2 | 9 |
| full_fp | 25 | 25 | 0 | 0 | 0 |
| position_loo | 6 | 4 | 0 | 2 | 19 |
| full_fp_spread | 25 | 19 | 0 | 6 | 0 |
| random_spread | 15 | 11 | 0 | 4 | 10 |
| fp_global_placebo | 20 | 15 | 0 | 5 | 5 |
| fp_withincab_placebo | 23 | 20 | 0 | 3 | 2 |

---

## 5. Manuscript-Ready Summary Paragraph

In the C2 held-out experiment (sc30–sc54, n=25, r=1.25, corrected concurrent-load cabinet reference), full_fp outperformed full_random in 25 of 25 scenarios (25A/0I/0B; median delta_lo = +12.4755 pp, 95% CI [+11.09, +19.04] pp; Holm p = 0.0000). The thermal-incidence advantage was not reproduced by the within-cabinet placebo (24A/1I/0B; Holm p = 0.0000) nor by the global permutation placebo (25A/0I/0B; Holm p = 0.0000), establishing that the effect is specific to thermal-incidence signal rather than incidental scheduling structure. Relative to the leave-one-out position baseline, full_fp achieved 25A/0I/0B (Holm p = 0.0000). Spread extensions: FPSpread vs RandomSpread (23A/2I/0B; Holm p = 0.0000); FPSpread vs FP (A=thermally specific vs spread diluted) (0A/0I/25B; Holm p = 0.0000); RandomSpread vs Random (5A/14I/6B; Holm p = 1.0000); FPSpread vs position_loo (24A/1I/0B; Holm p = 0.0000).
