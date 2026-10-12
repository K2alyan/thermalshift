# C3 Threshold Sensitivity Analysis

**Exploratory post-exposure threshold sensitivity. Not preregistered primary evidence.**  

**Scenarios:** sc30-sc54 (n=25)  
**Ratio:** r=1.25  **Comparison:** full_fp vs full_random  
**Estimand:** delta_lo = C_lower(FP) - C_upper(Random); verdict A if > 0, B if delta_hi < 0  
**Bootstrap:** 5000 draws, seed 9999, percentile 95% CI  

**P90 source:** `gate_f_sc30-54_1p25_t61p875_c3canonical.json` SHA256: `a94f72084de1eb26...`  
**P95 source:** `gate_f_sc30-54_1p25_c2manuscript.json` SHA256: `b4dbc4bc0f8646f1...`  
**P99 source:** `gate_f_sc30-54_1p25_t66p6625_c3manuscript.json` SHA256: `2fef4c49500e4f3c...`  

---

## 1. FP vs Random Summary — P90 / P95 / P99

| Threshold | T (C) | A/I/B | med delta_lo | 95% CI delta_lo | med delta_hi | 95% CI delta_hi |
|-----------|-------|-------|-------------|-----------------|-------------|-----------------|
| P90 | 61.875 | 24A/1I/0B | +8.8969 | [+4.9471, +14.4977] | +9.7335 | [+6.0953, +14.6940] |
| P95 | 63.625 | 25A/0I/0B | +12.4755 | [+11.0948, +19.0385] | +12.9394 | [+11.3673, +20.4635] |
| P99 | 66.6625 | 25A/0I/0B | +21.3322 | [+16.3927, +25.3642] | +21.5723 | [+16.5926, +26.0659] |

---

## 2. Absolute Capacity

### FP (full_fp)

| Threshold | med C_lower | q25 | q75 | IQR | med C_upper | n_lb | n_rc |
|-----------|------------|-----|-----|-----|------------|------|------|
| P90 | 11.3240 | 8.2922 | 17.7622 | 9.4700 | 11.6948 | 0 | 0 |
| P95 | 15.3541 | 12.2331 | 22.8298 | 10.5967 | 15.5561 | 0 | 0 |
| P99 | 21.3322 | 15.9185 | 33.6989 | 17.7804 | 21.5723 | 0 | 0 |

### Random (full_random)

| Threshold | med C_lower | q25 | q75 | IQR | med C_upper | n_lb | n_rc |
|-----------|------------|-----|-----|-----|------------|------|------|
| P90 | 1.0901 | 0.1199 | 2.7296 | 2.6097 | 1.3712 | 3 | 0 |
| P95 | 0.1028 | 0.0000 | 3.4807 | 3.4807 | 0.5752 | 9 | 0 |
| P99 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 19 | 0 |

---

## 3. Binding Constraints — Mechanism Check

**Constraint definitions:**  
- `B_ratio`: thermal-incidence constraint — the ratio (B_actual / B_ref_s) reaches the capacity boundary before the severity ratio does.  
  B_ref_s is the historical thermal-incidence reference recomputed at each threshold.  
- `S_ratio`: thermal-severity constraint — the ratio (S_actual / S_ref_s) reaches the capacity boundary first.  
  S_ref_s is the historical thermal-severity reference recomputed at each threshold.  
- `n_lb`: scenarios classified as left-boundary (no crossing found within lambda sweep).  

Note: B_ratio and S_ratio are both thermal constraints. The distinction is incidence (B) vs severity (S) as the binding exposure dimension.

First binding constraint for full_fp (scenarios with a crossing only):

| Threshold | n_crossing | B_ratio | S_ratio | n_lb |
|-----------|-----------|---------|---------|------|
| P90 | 25 | 25 | 0 | 0 |
| P95 | 25 | 25 | 0 | 0 |
| P99 | 25 | 5 | 20 | 0 |

First binding constraint for full_random:

| Threshold | n_crossing | B_ratio | S_ratio | n_lb |
|-----------|-----------|---------|---------|------|
| P90 | 22 | 18 | 4 | 3 |
| P95 | 16 | 14 | 2 | 9 |
| P99 | 6 | 2 | 4 | 19 |

Mechanism interpretation:  
- At P90 and P95, FP crossings are driven entirely by B_ratio (thermal-incidence ratio).  
- At P99, FP shifts to predominantly S_ratio (thermal-severity ratio), consistent with higher-threshold scenarios accumulating more severity exposure before the incidence ratio binds.  
- Random is increasingly left-boundary limited as the threshold rises: 3/25 at P90, 9/25 at P95, 19/25 at P99. At P99, most Random scenarios never reach a crossing within the lambda sweep.  

---

## 4. Direction Persistence

Direction consistent (FP majority) across all three threshold definitions: **YES**  

- P90 (61.875 C): 24A/1I/0B  med delta_lo = +8.8969 pp  (Random left-boundary: 3/25)
- P95 (63.625 C): 25A/0I/0B  med delta_lo = +12.4755 pp  (Random left-boundary: 9/25)
- P99 (66.6625 C): 25A/0I/0B  med delta_lo = +21.3322 pp  (Random left-boundary: 19/25)

---

## 5. Interpretation Note

This analysis is exploratory threshold sensitivity. The C3 result supports one primary conclusion: **the sign of the FP advantage does not reverse across threshold definitions.** That is the defensible C3 claim.

**What these thresholds are not:**  
Each threshold (P90, P95, P99) involves recomputing both B_ref_s and S_ref_s from the historical distribution at that threshold level. These are therefore three alternative definitions of historical thermal exposure, not one nested capacity constraint that is progressively relaxed. The estimated magnitude differs across definitions; do not interpret the +8.90 -> +12.48 -> +21.33 pp progression as a monotonic dose-response to a loosening constraint.

**P99 floor limitation:**  
At P99 (T=66.6625 C), 19/25 Random scenarios are left-boundary limited — the Random policy never reaches a crossing within the lambda sweep. The +21.33 pp estimate at P99 is substantially floor-limited by Random's near-zero capacity, not solely by increased FP advantage. The P99 result is useful for confirming directional robustness; its magnitude should not be described as a larger effect.

**Primary evidence:**  
The primary preregistered evidence is the C2 corrected-reference result at P95 (T=63.625 C). P90 and P99 are post-hoc sensitivity probes reported equally without selective emphasis.
