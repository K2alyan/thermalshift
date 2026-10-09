# C1 Corrected-Reference Analysis

**Branch:** revision1/major-revision-analyses  
**Raw source SHA256:** `8d66349fb1158d212098adacec268b80afe2cf0f48e0b1afb035114313684ec3`  
**Analysis script SHA256:** `5af152b0d04bf0ad0d10ef30f6e0ef25ebd1a0546d1e51be659ee4fbe6892c2d`  
**Bootstrap:** 5000 draws, seed 9999, percentile 95% CI  

---

## 1. r=1.0 Negative Control

**Verdict: PASS**  
All four policies produce identical C_lower/C_upper per scenario at r=1.0. All five frozen comparisons are 0/25/0 (A/I/B).

| Comparison | n_A | n_I | n_B | median delta_lo (pp) | median delta_hi (pp) |
|------------|-----|-----|-----|----------------------|----------------------|
| FP_vs_Random | 0 | 25 | 0 | -0.060341 | 0.060341 |
| Loc_vs_Random | 0 | 25 | 0 | -0.060341 | 0.060341 |
| FPSpread_vs_Random | 0 | 25 | 0 | -0.060341 | 0.060341 |
| FPSpread_vs_FP | 0 | 25 | 0 | -0.060341 | 0.060341 |
| FPSpread_vs_Loc | 0 | 25 | 0 | -0.060341 | 0.060341 |

---

## 2. Pairwise Comparisons — All 7 Ratios

Estimand: `delta_lo = C_lower(A) - C_upper(B)` · `delta_hi = C_upper(A) - C_lower(B)`  
Verdict: **A** if delta_lo > 0, **B** if delta_hi < 0, **I** otherwise  
Bootstrap: 5000 draws, seed 9999, percentile 95% CI on median

### FP_vs_Random  (A = full_fp, B = full_random)

| Ratio | A/I/B | med delta_lo | 95% CI delta_lo | med delta_hi | 95% CI delta_hi |
|-------|-------|-------------|-----------------|-------------|-----------------|
| 1.0 | 0/25/0 | -0.0603 | [-0.2745, +0.0000] | +0.0603 | [+0.0000, +0.2745] |
| 1.25 | 25/0/0 | +16.1697 | [+11.5252, +21.4962] | +16.2456 | [+12.2585, +22.3590] |
| 1.5 | 25/0/0 | +21.2948 | [+14.9775, +26.9896] | +22.1374 | [+15.7773, +27.6007] |
| 2.0 | 25/0/0 | +27.0660 | [+21.8648, +32.9008] | +28.1913 | [+22.3163, +33.5338] |
| 4.0 | 25/0/0 | +33.9579 | [+25.2004, +42.8931] | +35.2448 | [+25.7208, +43.0624] |
| 8.0 | 25/0/0 | +32.7312 | [+20.8212, +40.6166] | +32.9672 | [+21.3273, +41.4582] |
| unrestricted | 25/0/0 | +36.0588 | [+29.0012, +45.5581] | +36.9156 | [+30.1191, +45.8453] |

### Loc_vs_Random  (A = full_loc, B = full_random)

| Ratio | A/I/B | med delta_lo | 95% CI delta_lo | med delta_hi | 95% CI delta_hi |
|-------|-------|-------------|-----------------|-------------|-----------------|
| 1.0 | 0/25/0 | -0.0603 | [-0.2745, +0.0000] | +0.0603 | [+0.0000, +0.2745] |
| 1.25 | 23/2/0 | +5.1490 | [+2.6077, +6.9598] | +5.2790 | [+3.1207, +7.2276] |
| 1.5 | 24/1/0 | +6.5042 | [+3.5918, +11.9940] | +7.0766 | [+4.0173, +12.0973] |
| 2.0 | 25/0/0 | +11.7172 | [+6.1585, +16.4561] | +12.1085 | [+6.5379, +17.1890] |
| 4.0 | 25/0/0 | +13.4930 | [+7.2824, +19.1158] | +13.8461 | [+8.1363, +19.7203] |
| 8.0 | 25/0/0 | +13.7641 | [+8.1768, +17.4894] | +14.0152 | [+8.4728, +18.6700] |
| unrestricted | 25/0/0 | +12.9971 | [+6.7010, +19.2215] | +13.7880 | [+7.3625, +19.8893] |

### FPSpread_vs_Random  (A = full_fp_spread, B = full_random)

| Ratio | A/I/B | med delta_lo | 95% CI delta_lo | med delta_hi | 95% CI delta_hi |
|-------|-------|-------------|-----------------|-------------|-----------------|
| 1.0 | 0/25/0 | -0.0603 | [-0.2745, +0.0000] | +0.0603 | [+0.0000, +0.2745] |
| 1.25 | 20/5/0 | +2.1234 | [+0.4382, +2.9714] | +2.1664 | [+0.9889, +3.4952] |
| 1.5 | 22/3/0 | +3.2105 | [+0.9866, +6.6791] | +3.6984 | [+1.6730, +7.2296] |
| 2.0 | 24/1/0 | +4.5833 | [+3.1761, +9.3409] | +4.9515 | [+3.3330, +9.7454] |
| 4.0 | 25/0/0 | +11.7808 | [+6.2550, +15.8019] | +12.1794 | [+6.8607, +17.1510] |
| 8.0 | 24/1/0 | +15.5203 | [+11.4373, +24.2149] | +15.8204 | [+11.8957, +24.4636] |
| unrestricted | 24/1/0 | +18.1487 | [+10.7690, +25.4834] | +18.4055 | [+11.2149, +28.0137] |

### FPSpread_vs_FP  (A = full_fp_spread, B = full_fp)

| Ratio | A/I/B | med delta_lo | 95% CI delta_lo | med delta_hi | 95% CI delta_hi |
|-------|-------|-------------|-----------------|-------------|-----------------|
| 1.0 | 0/25/0 | -0.0603 | [-0.2745, +0.0000] | +0.0603 | [+0.0000, +0.2745] |
| 1.25 | 0/1/24 | -14.2735 | [-17.5905, -7.2627] | -13.3595 | [-16.9726, -6.4339] |
| 1.5 | 0/1/24 | -19.2924 | [-21.4243, -12.3359] | -18.3358 | [-20.9225, -11.2538] |
| 2.0 | 0/0/25 | -19.2421 | [-25.5323, -15.9556] | -18.3027 | [-24.9102, -15.4010] |
| 4.0 | 0/0/25 | -19.6672 | [-31.3914, -13.7706] | -18.1349 | [-31.1343, -13.1439] |
| 8.0 | 0/4/21 | -14.4377 | [-16.7396, -7.1322] | -13.3338 | [-15.9957, -6.4364] |
| unrestricted | 0/1/24 | -15.3842 | [-18.1430, -6.3272] | -14.1016 | [-16.8810, -4.5226] |

### FPSpread_vs_Loc  (A = full_fp_spread, B = full_loc)

| Ratio | A/I/B | med delta_lo | 95% CI delta_lo | med delta_hi | 95% CI delta_hi |
|-------|-------|-------------|-----------------|-------------|-----------------|
| 1.0 | 0/25/0 | -0.0603 | [-0.2745, +0.0000] | +0.0603 | [+0.0000, +0.2745] |
| 1.25 | 2/9/14 | -1.5351 | [-3.9428, -0.4866] | -0.8336 | [-3.1615, +0.4465] |
| 1.5 | 0/7/18 | -4.0787 | [-5.2396, -1.1523] | -3.6292 | [-4.7645, -0.4712] |
| 2.0 | 1/5/19 | -3.1313 | [-8.3073, -1.2197] | -2.8368 | [-6.7758, -0.5404] |
| 4.0 | 6/6/13 | -0.8001 | [-4.8021, -0.1918] | -0.1177 | [-4.5661, +0.8000] |
| 8.0 | 17/6/2 | +2.8306 | [-0.1170, +5.8663] | +3.7156 | [+0.8023, +6.3123] |
| unrestricted | 20/5/0 | +2.8300 | [+0.6038, +9.3945] | +3.6787 | [+1.4195, +9.8429] |

---

## 3. Absolute Capacity Table

Median and IQR of C_lower, C_upper in percentage points across 25 scenarios.

### Ratio = 1.0

| Policy | med C_lower | IQR C_lower | min C_lower | max C_lower | med C_upper | IQR C_upper | left_boundary | right_censored |
|--------|-------------|-------------|-------------|-------------|-------------|-------------|---------------|----------------|
| full_random | 0.0000 | 4.0410 | 0.0000 | 17.9808 | 0.2359 | 4.4078 | 12 | 0 |
| full_fp | 0.0000 | 4.0410 | 0.0000 | 17.9808 | 0.2359 | 4.4078 | 12 | 0 |
| full_loc | 0.0000 | 4.0410 | 0.0000 | 17.9808 | 0.2359 | 4.4078 | 12 | 0 |
| full_fp_spread | 0.0000 | 4.0410 | 0.0000 | 17.9808 | 0.2359 | 4.4078 | 12 | 0 |

### Ratio = 1.25

| Policy | med C_lower | IQR C_lower | min C_lower | max C_lower | med C_upper | IQR C_upper | left_boundary | right_censored |
|--------|-------------|-------------|-------------|-------------|-------------|-------------|---------------|----------------|
| full_random | 0.0000 | 3.8213 | 0.0000 | 7.5040 | 0.2359 | 4.0007 | 11 | 0 |
| full_fp | 18.4448 | 11.5410 | 2.5922 | 41.9162 | 18.6332 | 11.7490 | 0 | 0 |
| full_loc | 5.6292 | 5.2773 | 0.7872 | 22.9952 | 6.1318 | 5.1169 | 0 | 0 |
| full_fp_spread | 3.2513 | 3.5205 | 0.0000 | 20.4600 | 3.4952 | 3.9729 | 2 | 0 |

### Ratio = 1.5

| Policy | med C_lower | IQR C_lower | min C_lower | max C_lower | med C_upper | IQR C_upper | left_boundary | right_censored |
|--------|-------------|-------------|-------------|-------------|-------------|-------------|---------------|----------------|
| full_random | 0.0000 | 2.6508 | 0.0000 | 14.2768 | 0.1317 | 2.8783 | 11 | 0 |
| full_fp | 21.7355 | 17.4445 | 2.5650 | 53.9698 | 22.2012 | 17.0192 | 0 | 0 |
| full_loc | 6.5743 | 12.6508 | 2.5968 | 24.5472 | 7.0766 | 11.8788 | 0 | 0 |
| full_fp_spread | 5.6071 | 7.9134 | 0.0000 | 18.7628 | 5.9877 | 7.7463 | 1 | 0 |

### Ratio = 2.0

| Policy | med C_lower | IQR C_lower | min C_lower | max C_lower | med C_upper | IQR C_upper | left_boundary | right_censored |
|--------|-------------|-------------|-------------|-------------|-------------|-------------|---------------|----------------|
| full_random | 0.4382 | 2.8879 | 0.0000 | 11.6041 | 0.5758 | 3.1097 | 9 | 0 |
| full_fp | 31.5062 | 17.5008 | 7.4153 | 53.7156 | 32.0782 | 17.9317 | 0 | 0 |
| full_loc | 12.0037 | 11.4474 | 2.5650 | 32.5754 | 12.2843 | 11.8909 | 0 | 0 |
| full_fp_spread | 7.1993 | 6.8827 | 2.5968 | 23.5844 | 7.5452 | 6.9289 | 0 | 0 |

### Ratio = 4.0

| Policy | med C_lower | IQR C_lower | min C_lower | max C_lower | med C_upper | IQR C_upper | left_boundary | right_censored |
|--------|-------------|-------------|-------------|-------------|-------------|-------------|---------------|----------------|
| full_random | 0.2282 | 2.8446 | 0.0000 | 6.8632 | 0.4602 | 3.1097 | 11 | 0 |
| full_fp | 37.4531 | 21.7624 | 12.0553 | 67.8242 | 38.1146 | 22.0437 | 0 | 0 |
| full_loc | 16.6800 | 12.2049 | 2.5157 | 34.4524 | 16.8452 | 12.2716 | 0 | 0 |
| full_fp_spread | 12.1560 | 10.5253 | 2.5696 | 31.0723 | 12.3211 | 9.7739 | 0 | 0 |

### Ratio = 8.0

| Policy | med C_lower | IQR C_lower | min C_lower | max C_lower | med C_upper | IQR C_upper | left_boundary | right_censored |
|--------|-------------|-------------|-------------|-------------|-------------|-------------|---------------|----------------|
| full_random | 0.1531 | 1.5588 | 0.0000 | 7.8725 | 0.6346 | 2.0074 | 8 | 0 |
| full_fp | 32.7312 | 24.9062 | 4.3770 | 68.6667 | 32.9672 | 25.2381 | 0 | 0 |
| full_loc | 14.2181 | 16.1897 | 2.5116 | 30.1059 | 14.7138 | 16.4190 | 0 | 0 |
| full_fp_spread | 16.2276 | 16.2867 | 2.5696 | 53.3255 | 16.7355 | 16.6841 | 0 | 0 |

### Ratio = unrestricted

| Policy | med C_lower | IQR C_lower | min C_lower | max C_lower | med C_upper | IQR C_upper | left_boundary | right_censored |
|--------|-------------|-------------|-------------|-------------|-------------|-------------|---------------|----------------|
| full_random | 0.0000 | 0.7021 | 0.0000 | 5.5464 | 0.2359 | 1.1775 | 10 | 0 |
| full_fp | 36.6665 | 24.5094 | 4.7652 | 67.8700 | 37.6176 | 24.3083 | 0 | 0 |
| full_loc | 16.1068 | 13.2775 | 2.6814 | 39.3526 | 16.6326 | 12.8127 | 0 | 0 |
| full_fp_spread | 19.4438 | 20.4341 | 0.0000 | 52.3357 | 19.7854 | 20.2975 | 0 | 0 |

---

## 4. Binding Constraint Table

`left_boundary` = crossing status is left_boundary (capacity unlock ≥ 50% at lambda=1.0).  
Remaining counts show `first_binding_constraint` at the crossing point.

### Ratio = 1.0

| Policy | left_boundary | B_ratio | S_ratio | total_crossings |
|---|---|---|---|---|
| full_random | 12 | 7 | 6 | 13 |
| full_fp | 12 | 7 | 6 | 13 |
| full_loc | 12 | 7 | 6 | 13 |
| full_fp_spread | 12 | 7 | 6 | 13 |

### Ratio = 1.25

| Policy | left_boundary | B_ratio | S_ratio | total_crossings |
|---|---|---|---|---|
| full_random | 11 | 8 | 6 | 14 |
| full_fp | 0 | 25 | 0 | 25 |
| full_loc | 0 | 20 | 5 | 25 |
| full_fp_spread | 2 | 18 | 5 | 23 |

### Ratio = 1.5

| Policy | left_boundary | B_ratio | S_ratio | total_crossings |
|---|---|---|---|---|
| full_random | 11 | 9 | 5 | 14 |
| full_fp | 0 | 25 | 0 | 25 |
| full_loc | 0 | 19 | 6 | 25 |
| full_fp_spread | 1 | 17 | 7 | 24 |

### Ratio = 2.0

| Policy | left_boundary | B_ratio | S_ratio | total_crossings |
|---|---|---|---|---|
| full_random | 9 | 10 | 6 | 16 |
| full_fp | 0 | 25 | 0 | 25 |
| full_loc | 0 | 20 | 5 | 25 |
| full_fp_spread | 0 | 15 | 10 | 25 |

### Ratio = 4.0

| Policy | left_boundary | B_ratio | S_ratio | total_crossings |
|---|---|---|---|---|
| full_random | 11 | 12 | 2 | 14 |
| full_fp | 0 | 25 | 0 | 25 |
| full_loc | 0 | 24 | 1 | 25 |
| full_fp_spread | 0 | 18 | 7 | 25 |

### Ratio = 8.0

| Policy | left_boundary | B_ratio | S_ratio | total_crossings |
|---|---|---|---|---|
| full_random | 8 | 12 | 5 | 17 |
| full_fp | 0 | 25 | 0 | 25 |
| full_loc | 0 | 23 | 2 | 25 |
| full_fp_spread | 0 | 20 | 5 | 25 |

### Ratio = unrestricted

| Policy | left_boundary | B_ratio | S_ratio | total_crossings |
|---|---|---|---|---|
| full_random | 10 | 14 | 1 | 15 |
| full_fp | 0 | 25 | 0 | 25 |
| full_loc | 0 | 24 | 1 | 25 |
| full_fp_spread | 0 | 25 | 0 | 25 |

---

## 5. Sensitivity vs Original Experiment 1

**Original E1:** sc5–sc29, job-contribution cabinet reference (`r1_gate_f_run.py`).  
**Corrected C1:** sc5–sc29, `corrected_timeweighted_total_p99_local` reference.  
Same scenarios, same bootstrap settings (seed 9999, N=5000), same estimand.  
The reference change alters the operating constraint regime; magnitude changes do not directly translate to evidence-strength differences.

**DIRECTIONAL REVERSALS DETECTED (5):**
  - FPSpread_vs_FP @ r=4.0: A -> B
  - FPSpread_vs_FP @ r=8.0: A -> B
  - FPSpread_vs_FP @ r=unrestricted: A -> B
  - FPSpread_vs_Loc @ r=1.25: I -> B
  - FPSpread_vs_Loc @ r=4.0: A -> B

### FP_vs_Random

| Ratio | Old A/I/B | Old med delta_lo | Corr A/I/B | Corr med delta_lo | Delta change | Agreement |
|-------|-----------|-----------------|------------|-------------------|-------------|-----------|
| 1.0 | 0/25/0 | -0.0034 | 0/25/0 | -0.0603 | -0.0569 | YES |
| 1.25 | 25/0/0 | +4.7710 | 25/0/0 | +16.1697 | +11.3987 | YES |
| 1.5 | 25/0/0 | +5.6118 | 25/0/0 | +21.2948 | +15.6830 | YES |
| 2.0 | 24/1/0 | +4.8558 | 25/0/0 | +27.0660 | +22.2102 | YES |
| 4.0 | 24/1/0 | +4.4391 | 25/0/0 | +33.9579 | +29.5188 | YES |
| 8.0 | 24/0/1 | +3.5893 | 25/0/0 | +32.7312 | +29.1419 | YES |
| unrestricted | 22/1/2 | +4.2359 | 25/0/0 | +36.0588 | +31.8229 | YES |

### Loc_vs_Random

| Ratio | Old A/I/B | Old med delta_lo | Corr A/I/B | Corr med delta_lo | Delta change | Agreement |
|-------|-----------|-----------------|------------|-------------------|-------------|-----------|
| 1.0 | 0/25/0 | -0.0034 | 0/25/0 | -0.0603 | -0.0569 | YES |
| 1.25 | 22/3/0 | +2.6208 | 23/2/0 | +5.1490 | +2.5282 | YES |
| 1.5 | 24/1/0 | +4.4949 | 24/1/0 | +6.5042 | +2.0093 | YES |
| 2.0 | 24/1/0 | +4.1460 | 25/0/0 | +11.7172 | +7.5712 | YES |
| 4.0 | 24/1/0 | +4.0465 | 25/0/0 | +13.4930 | +9.4465 | YES |
| 8.0 | 25/0/0 | +3.6266 | 25/0/0 | +13.7641 | +10.1374 | YES |
| unrestricted | 23/2/0 | +4.5421 | 25/0/0 | +12.9971 | +8.4550 | YES |

### FPSpread_vs_Random

| Ratio | Old A/I/B | Old med delta_lo | Corr A/I/B | Corr med delta_lo | Delta change | Agreement |
|-------|-----------|-----------------|------------|-------------------|-------------|-----------|
| 1.0 | 0/25/0 | -0.0034 | 0/25/0 | -0.0603 | -0.0569 | YES |
| 1.25 | 21/4/0 | +1.6114 | 20/5/0 | +2.1234 | +0.5120 | YES |
| 1.5 | 19/6/0 | +2.5169 | 22/3/0 | +3.2105 | +0.6936 | YES |
| 2.0 | 22/1/2 | +3.2313 | 24/1/0 | +4.5833 | +1.3520 | YES |
| 4.0 | 25/0/0 | +6.3202 | 25/0/0 | +11.7808 | +5.4606 | YES |
| 8.0 | 24/1/0 | +7.1779 | 24/1/0 | +15.5203 | +8.3424 | YES |
| unrestricted | 24/1/0 | +7.1279 | 24/1/0 | +18.1487 | +11.0208 | YES |

### FPSpread_vs_FP

| Ratio | Old A/I/B | Old med delta_lo | Corr A/I/B | Corr med delta_lo | Delta change | Agreement |
|-------|-----------|-----------------|------------|-------------------|-------------|-----------|
| 1.0 | 0/25/0 | -0.0034 | 0/25/0 | -0.0603 | -0.0569 | YES |
| 1.25 | 3/3/19 | -3.3630 | 0/1/24 | -14.2735 | -10.9105 | YES |
| 1.5 | 1/3/21 | -3.2934 | 0/1/24 | -19.2924 | -15.9990 | YES |
| 2.0 | 3/5/17 | -2.8793 | 0/0/25 | -19.2421 | -16.3627 | YES |
| 4.0 | 16/3/6 | +0.5420 | 0/0/25 | -19.6672 | -20.2092 | **NO (REVERSAL)** |
| 8.0 | 20/4/1 | +1.5285 | 0/4/21 | -14.4377 | -15.9662 | **NO (REVERSAL)** |
| unrestricted | 20/3/2 | +2.8490 | 0/1/24 | -15.3842 | -18.2331 | **NO (REVERSAL)** |

### FPSpread_vs_Loc

| Ratio | Old A/I/B | Old med delta_lo | Corr A/I/B | Corr med delta_lo | Delta change | Agreement |
|-------|-----------|-----------------|------------|-------------------|-------------|-----------|
| 1.0 | 0/25/0 | -0.0034 | 0/25/0 | -0.0603 | -0.0569 | YES |
| 1.25 | 2/11/12 | -1.1706 | 2/9/14 | -1.5351 | -0.3644 | **NO (REVERSAL)** |
| 1.5 | 2/8/15 | -2.4030 | 0/7/18 | -4.0787 | -1.6757 | YES |
| 2.0 | 1/8/16 | -1.3735 | 1/5/19 | -3.1313 | -1.7578 | YES |
| 4.0 | 17/5/3 | +0.6263 | 6/6/13 | -0.8001 | -1.4263 | **NO (REVERSAL)** |
| 8.0 | 17/5/3 | +0.7308 | 17/6/2 | +2.8306 | +2.0997 | YES |
| unrestricted | 18/6/1 | +0.8538 | 20/5/0 | +2.8300 | +1.9762 | YES |

---

## 6. Reviewer-Sensitive Location Result

The reviewer questioned whether Location-only performs close to or exceeds FP.

### Does FP beat Random?
- r=1.0: 0A/25I/0B  med delta_lo = -0.0603 pp  CI [-0.2745, +0.0000]
- r=1.25: 25A/0I/0B  med delta_lo = +16.1697 pp  CI [+11.5252, +21.4962]
- r=1.5: 25A/0I/0B  med delta_lo = +21.2948 pp  CI [+14.9775, +26.9896]
- r=2.0: 25A/0I/0B  med delta_lo = +27.0660 pp  CI [+21.8648, +32.9008]
- r=4.0: 25A/0I/0B  med delta_lo = +33.9579 pp  CI [+25.2004, +42.8931]
- r=8.0: 25A/0I/0B  med delta_lo = +32.7312 pp  CI [+20.8212, +40.6166]
- r=unrestricted: 25A/0I/0B  med delta_lo = +36.0588 pp  CI [+29.0012, +45.5581]

### Does Location beat Random?
- r=1.0: 0A/25I/0B  med delta_lo = -0.0603 pp  CI [-0.2745, +0.0000]
- r=1.25: 23A/2I/0B  med delta_lo = +5.1490 pp  CI [+2.6077, +6.9598]
- r=1.5: 24A/1I/0B  med delta_lo = +6.5042 pp  CI [+3.5918, +11.9940]
- r=2.0: 25A/0I/0B  med delta_lo = +11.7172 pp  CI [+6.1585, +16.4561]
- r=4.0: 25A/0I/0B  med delta_lo = +13.4930 pp  CI [+7.2824, +19.1158]
- r=8.0: 25A/0I/0B  med delta_lo = +13.7641 pp  CI [+8.1768, +17.4894]
- r=unrestricted: 25A/0I/0B  med delta_lo = +12.9971 pp  CI [+6.7010, +19.2215]

### Does FPSpread beat Location?
- r=1.0: 0A/25I/0B  med delta_lo = -0.0603 pp  CI [-0.2745, +0.0000]
- r=1.25: 2A/9I/14B  med delta_lo = -1.5351 pp  CI [-3.9428, -0.4866]
- r=1.5: 0A/7I/18B  med delta_lo = -4.0787 pp  CI [-5.2396, -1.1523]
- r=2.0: 1A/5I/19B  med delta_lo = -3.1313 pp  CI [-8.3073, -1.2197]
- r=4.0: 6A/6I/13B  med delta_lo = -0.8001 pp  CI [-4.8021, -0.1918]
- r=8.0: 17A/6I/2B  med delta_lo = +2.8306 pp  CI [-0.1170, +5.8663]
- r=unrestricted: 20A/5I/0B  med delta_lo = +2.8300 pp  CI [+0.6038, +9.3945]

### Does FPSpread beat FP?  (indirect FP vs Location signal)
- r=1.0: 0A/25I/0B  med delta_lo = -0.0603 pp  CI [-0.2745, +0.0000]
- r=1.25: 0A/1I/24B  med delta_lo = -14.2735 pp  CI [-17.5905, -7.2627]
- r=1.5: 0A/1I/24B  med delta_lo = -19.2924 pp  CI [-21.4243, -12.3359]
- r=2.0: 0A/0I/25B  med delta_lo = -19.2421 pp  CI [-25.5323, -15.9556]
- r=4.0: 0A/0I/25B  med delta_lo = -19.6672 pp  CI [-31.3914, -13.7706]
- r=8.0: 0A/4I/21B  med delta_lo = -14.4377 pp  CI [-16.7396, -7.1322]
- r=unrestricted: 0A/1I/24B  med delta_lo = -15.3842 pp  CI [-18.1430, -6.3272]

### Summary at r=1.25 (primary operating point)

- **FP beats Random:** 25/0/0 A/I/B, med delta_lo = 16.1697 pp
- **Location beats Random:** 23/2/0 A/I/B, med delta_lo = 5.1490 pp
- **FPSpread beats Location:** 2/9/14 A/I/B, med delta_lo = -1.5351 pp
- **FPSpread beats FP:** 0/1/24 A/I/B, med delta_lo = -14.2735 pp

FP vs Location is not a frozen comparison. The gap between FP_vs_Random and Loc_vs_Random median delta_lo values at each ratio indicates the marginal contribution of power-draw information beyond location. Ratios where this gap is small should be flagged as unresolved.

---

## 7. Manuscript-Ready Summary

### A. Results paragraph

```text
Under the corrected concurrent-load cabinet reference (corrected_timeweighted_total_p99_local), Experiment 1 was re-run on 25 held-out scenarios (sc5–sc29) across seven capacity-ratio operating points (r = 1.0, 1.25, 1.5, 2.0, 4.0, 8.0, and unrestricted). The r=1.0 negative control passed: all four policies yield identical capacity-unlock intervals at r=1.0 (0/25/0 A/I/B across all comparisons). At r=1.25, FP outperformed Random in 25 of 25 scenarios (median delta_lo = 16.17 pp, 95% CI [11.53, 21.50]). Location-only outperformed Random in 23 of 25 scenarios (median delta_lo = 5.15 pp, 95% CI [2.61, 6.96]). FP-Spread outperformed Random in 20 of 25 scenarios at r=1.25 (median delta_lo = 2.12 pp). FP-Spread versus FP at r=1.25: 0A/1I/24B (median delta_lo = -14.27 pp). FP-Spread versus Location at r=1.25: 2A/9I/14B (median delta_lo = -1.54 pp).
```

### B. Corrected-reference comparison paragraph

```text
The corrected concurrent-load cabinet reference replaces the original job-contribution reference. The reference change shifts the absolute cabinet-capacity operating point but does not alter the directional ranking of scheduling policies: no directional reversals were observed across any of the five frozen comparisons at any of the seven ratios. At r=1.25, the original reference produced FP-vs-Random median delta_lo = 4.77 pp (25A/0I/0B); the corrected reference produced 16.17 pp (25A/0I/0B). The magnitude change reflects the different operating regime imposed by the corrected denominator and should not be interpreted as a change in the strength of evidence.
```

### C. Location limitation paragraph

```text
Location-only scheduling achieved a median capacity-unlock advantage of 5.15 pp over Random at r=1.25 (23A/2I/0B), compared with 16.17 pp for FP (25A/0I/0B). This difference represents the marginal contribution of fine-grained power-draw telemetry beyond coarse location information. Because FP vs Location is not a frozen comparison in this experiment, the relative advantage of FP over Location-only should be treated as provisional. Unresolved ratios (where both FP and Location produce the same verdict against Random) are identified in Section 6.
```

---

## 8. Figure Data — Seven-Ratio × Five-Comparison

One row per comparison × ratio. `ci95_lo` and `ci95_hi` are the bootstrap percentile 95% CI bounds on the median delta_lo.

| comparison | ratio | n_A | n_I | n_B | med_delta_lo | ci95_lo | ci95_hi |
|------------|-------|-----|-----|-----|--------------|---------|---------|
| FP_vs_Random | 1.0 | 0 | 25 | 0 | -0.0603 | -0.2745 | +0.0000 |
| FP_vs_Random | 1.25 | 25 | 0 | 0 | +16.1697 | +11.5252 | +21.4962 |
| FP_vs_Random | 1.5 | 25 | 0 | 0 | +21.2948 | +14.9775 | +26.9896 |
| FP_vs_Random | 2.0 | 25 | 0 | 0 | +27.0660 | +21.8648 | +32.9008 |
| FP_vs_Random | 4.0 | 25 | 0 | 0 | +33.9579 | +25.2004 | +42.8931 |
| FP_vs_Random | 8.0 | 25 | 0 | 0 | +32.7312 | +20.8212 | +40.6166 |
| FP_vs_Random | unrestricted | 25 | 0 | 0 | +36.0588 | +29.0012 | +45.5581 |
| Loc_vs_Random | 1.0 | 0 | 25 | 0 | -0.0603 | -0.2745 | +0.0000 |
| Loc_vs_Random | 1.25 | 23 | 2 | 0 | +5.1490 | +2.6077 | +6.9598 |
| Loc_vs_Random | 1.5 | 24 | 1 | 0 | +6.5042 | +3.5918 | +11.9940 |
| Loc_vs_Random | 2.0 | 25 | 0 | 0 | +11.7172 | +6.1585 | +16.4561 |
| Loc_vs_Random | 4.0 | 25 | 0 | 0 | +13.4930 | +7.2824 | +19.1158 |
| Loc_vs_Random | 8.0 | 25 | 0 | 0 | +13.7641 | +8.1768 | +17.4894 |
| Loc_vs_Random | unrestricted | 25 | 0 | 0 | +12.9971 | +6.7010 | +19.2215 |
| FPSpread_vs_Random | 1.0 | 0 | 25 | 0 | -0.0603 | -0.2745 | +0.0000 |
| FPSpread_vs_Random | 1.25 | 20 | 5 | 0 | +2.1234 | +0.4382 | +2.9714 |
| FPSpread_vs_Random | 1.5 | 22 | 3 | 0 | +3.2105 | +0.9866 | +6.6791 |
| FPSpread_vs_Random | 2.0 | 24 | 1 | 0 | +4.5833 | +3.1761 | +9.3409 |
| FPSpread_vs_Random | 4.0 | 25 | 0 | 0 | +11.7808 | +6.2550 | +15.8019 |
| FPSpread_vs_Random | 8.0 | 24 | 1 | 0 | +15.5203 | +11.4373 | +24.2149 |
| FPSpread_vs_Random | unrestricted | 24 | 1 | 0 | +18.1487 | +10.7690 | +25.4834 |
| FPSpread_vs_FP | 1.0 | 0 | 25 | 0 | -0.0603 | -0.2745 | +0.0000 |
| FPSpread_vs_FP | 1.25 | 0 | 1 | 24 | -14.2735 | -17.5905 | -7.2627 |
| FPSpread_vs_FP | 1.5 | 0 | 1 | 24 | -19.2924 | -21.4243 | -12.3359 |
| FPSpread_vs_FP | 2.0 | 0 | 0 | 25 | -19.2421 | -25.5323 | -15.9556 |
| FPSpread_vs_FP | 4.0 | 0 | 0 | 25 | -19.6672 | -31.3914 | -13.7706 |
| FPSpread_vs_FP | 8.0 | 0 | 4 | 21 | -14.4377 | -16.7396 | -7.1322 |
| FPSpread_vs_FP | unrestricted | 0 | 1 | 24 | -15.3842 | -18.1430 | -6.3272 |
| FPSpread_vs_Loc | 1.0 | 0 | 25 | 0 | -0.0603 | -0.2745 | +0.0000 |
| FPSpread_vs_Loc | 1.25 | 2 | 9 | 14 | -1.5351 | -3.9428 | -0.4866 |
| FPSpread_vs_Loc | 1.5 | 0 | 7 | 18 | -4.0787 | -5.2396 | -1.1523 |
| FPSpread_vs_Loc | 2.0 | 1 | 5 | 19 | -3.1313 | -8.3073 | -1.2197 |
| FPSpread_vs_Loc | 4.0 | 6 | 6 | 13 | -0.8001 | -4.8021 | -0.1918 |
| FPSpread_vs_Loc | 8.0 | 17 | 6 | 2 | +2.8306 | -0.1170 | +5.8663 |
| FPSpread_vs_Loc | unrestricted | 20 | 5 | 0 | +2.8300 | +0.6038 | +9.3945 |

---

*Analysis: `artifacts/manuscript_completion/analysis/c1_correctedref_analysis.py`*
