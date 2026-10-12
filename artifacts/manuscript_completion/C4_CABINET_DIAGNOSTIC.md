# C4 Cabinet Accounting Diagnostic

**Source:** `gate_f_sc30-54_1p25_c2manuscript.json`  
**SHA256:** `b4dbc4bc0f8646f197d0a575f42dc785e97710f22460c7f2c8a1913866c6b129`  
**Ratio:** r=1.25  **Scenarios:** 25 (sc30–sc54)  
**FP cohort size:** 2000 nodes  
**FA_2024 available:** True  

---

## 1. Per-Cabinet Summary

| Cabinet | FP nodes | Structural% | FP node-hr% | Rnd node-hr% | FP/Rnd | FP/Struct |
|---------|----------|------------|------------|-------------|--------|----------|
| 2600 | 26 | 1.30% | 1.50% | 1.31% | 1.15x | 1.16x |
| 2601 | 26 | 1.30% | 1.42% | 1.26% | 1.13x | 1.09x |
| 2602 | 26 | 1.30% | 1.45% | 1.25% | 1.16x | 1.12x |
| **Combined** | — | 3.90% | 4.37% | 3.82% | 1.15x | 1.12x |

---

## 2. Per-Scenario Node-Hour Share Distribution (full_fp)

| Cabinet | median% | q25% | q75% | min% | max% |
|---------|---------|------|------|------|------|
| 2600 | 1.50% | 1.48% | 1.54% | 1.40% | 1.59% |
| 2601 | 1.42% | 1.39% | 1.44% | 1.35% | 1.50% |
| 2602 | 1.45% | 1.42% | 1.48% | 1.39% | 1.52% |

---

## 3. Per-Scenario Node-Hour Share Distribution (full_random)

| Cabinet | median% | q25% | q75% | min% | max% |
|---------|---------|------|------|------|------|
| 2600 | 1.31% | 1.29% | 1.34% | 1.22% | 1.38% |
| 2601 | 1.25% | 1.22% | 1.30% | 1.19% | 1.33% |
| 2602 | 1.24% | 1.21% | 1.29% | 1.19% | 1.34% |

---

## 4. FA_2024 Distribution for Target Cabinets

| Cabinet | n_nodes | median FA | q25 FA | q75 FA | mean FA |
|---------|---------|----------|--------|--------|--------|
| 2600 | 26 | -2.2230 | -2.9275 | -1.5267 | -2.2206 |
| 2601 | 26 | -1.3413 | -1.9089 | -0.8729 | -1.2440 |
| 2602 | 26 | -1.7854 | -2.3384 | -1.4817 | -1.8411 |

---

## 5. Interpretation

Cabinets 2600–2602 together hold 3.90% of FP cohort nodes structurally. Under full_fp they receive 4.37% of selected node-hours (enrichment vs structural: 1.12x; vs random: 1.15x). Under full_random they receive 3.82% (consistent with random allocation relative to structural share: 1.12x random/structural = 0.98x).
