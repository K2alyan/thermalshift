# Final Scientific Freeze

Generated: 2026-10-10  
Branch: revision1/major-revision-analyses  
HEAD at freeze: 6de1488

## Status

ALL SCIENTIFIC COMPUTE IS COMPLETE. No further simulation runs, beta values,
threshold analyses, ICC analyses, placebo permutations, or scheduling policy
comparisons are authorized. The compute phase is closed.

---

## Position-LOO withdrawal

Position-LOO (the leave-one-out reconstructed structural position comparator
used in the original C2 analysis) is **withdrawn as a scheduling comparator**.

Reason: the LOO formula `(S_g - F_i) / (n_g - 1)` reverses node ranking
within structural groups. Nodes with above-average group FA receive a lower
LOO score than nodes with below-average FA — the opposite of the intended
group-mean signal. This artifact causes the policy to preferentially select
hot nodes from groups where they are outliers, invalidating position_loo as
a fair structural baseline.

Historical files (raw results, analysis outputs referencing position_loo) are
retained for provenance traceability only. The position_loo numbers must not
appear as scheduling evidence in the final manuscript.

---

## PositionGroupHash — accepted fair structural comparator

PositionGroupHash is the accepted replacement structural comparator. Design:

- Group key: chassis × slot × board × node_position
- Group score: mean FA_2024 for groups of size ≥ 2
- Singleton score: global cohort mean FA_2024 (−0.03720489) — neutral fallback,
  not own FA, preventing identity leakage
- Sort: ascending (lower group-mean FA → higher priority)
- Tie-break: BLAKE2b hash (key=scenario_seed, msg=event_uid+hostname) —
  policy-blind, deterministic, cryptographically uniform
- 10 singleton groups identified; 67 total groups

Round 7 is a **post-exposure corrective robustness analysis**, not a
preregistered primary result. Its value is that an adversarial review exposed
a mathematically defective control, the corrected comparator produces a
credible hierarchical result, and the substantive ordering survives.

---

## Accepted final values

### Canonical beta (beta_F = 1.11416358)

Raw commit: 1e31568  
Raw SHA: `7bca547c732f8ce2b299a5fadf337fdc2a5bf50de06b184a9d0144515b1514ea`  
Analysis commit: 3bbb568  
Analysis script SHA: `439c59044cd8d45cdbca82e68603792e41046809d7d73c6b89207556e85f40e0`  
Analysis output SHA: `8e4608d7f3fc52c66c8af9d10265e8cc68ba9bcebabf7a1fea90732cb5e3ce56`

| Comparison | A/I/B | Median delta_lo | 95% CI | Median delta_hi |
|---|---|---|---|---|
| FP vs Random [REP] | 25/0/0 | +12.476 pp | [+11.095, +19.039] | +12.939 pp |
| FP vs WithinCab [REP] | 24/1/0 | +10.883 pp | [+5.959, +17.399] | +11.468 pp |
| FP vs PositionGroupHash [NEW] | 24/1/0 | +7.265 pp | [+5.120, +12.497] | +7.977 pp |
| PositionGroupHash vs Random [NEW] | 21/4/0 | +4.582 pp | [+2.901, +8.224] | +4.763 pp |

### Absolute capacities (canonical beta, median C_lower / C_upper, r=1.25, 25 scenarios)

| Policy | Median C_lower | Median C_upper | Left-boundary | Right-censored |
|---|---|---|---|---|
| full_fp | 15.35% | 15.56% | 0 | 0 |
| position_group_hash | 8.45% | 8.65% | 0 | 0 |
| fp_withincab_placebo | 4.04% | 4.23% | 2 | 0 |
| full_random | 0.10% | 0.58% | 9 | 0 |

FP and PositionGroupHash have **zero left-boundary scenarios** in the canonical
structural comparison. This makes FP–PGH a cleaner magnitude comparison than
FP–Random, where Random is substantially floor-limited.

### Beta sensitivity (beta_F = 0.960)

Raw commit: d51d89c  
Raw SHA: `3c1f38babca9ec69b4604684621ab03d87daef7d3b659f167bf249356d6cfa3f`  
Analysis commit: 6de1488  
Analysis output SHA: `e1dcf7007615f8e4f01265de1aaa7cce1d59cf11c658aabd360d4c3323e88391`  
Differential audit: 1,750 upstream fields, 0 failures — beta_F confirmed as
the only scientific change.

| Comparison | A/I/B | Median delta_lo | 95% CI | Median delta_hi |
|---|---|---|---|---|
| FP vs Random [REP] | 25/0/0 | +10.477 pp | [+6.893, +17.642] | +11.367 pp |
| FP vs WithinCab [REP] | 24/1/0 | +6.893 pp | [+4.489, +14.831] | +7.468 pp |
| FP vs PositionGroupHash [NEW] | 23/2/0 | +5.120 pp | [+2.331, +11.219] | +6.064 pp |
| PositionGroupHash vs Random [NEW] | 23/2/0 | +3.428 pp | [+2.004, +6.091] | +4.219 pp |

Beta=0.960 represents weaker fingerprint-to-temperature coupling, not a
tighter budget. All four comparisons preserve direction. No B verdicts at either
beta. FP and PGH remain uncensored at beta=0.960.

---

## Verdict logic (frozen)

```
delta_lo(A,B) = C_lower(A) - C_upper(B)
delta_hi(A,B) = C_upper(A) - C_lower(B)

A  iff  delta_lo > 0   (strict)
B  iff  delta_hi < 0   (strict)
I  otherwise           (straddle, right-censored B, zero boundary)
```

Verdict-fix commit: 3bbb568. Bug (delta_lo < 0 → B) corrected; C2 regression
verified (FP_vs_Random 25/0/0, FP_vs_WithinCab 24/1/0, sc51 correctly I).
9 unit tests + 2 C2 regression tests pass.

---

## Governance notes

- Round 7 is **post-exposure corrective robustness**, not preregistered evidence.
- Beta=0.960 is a post-exposure sensitivity using an independently motivated
  coefficient that predates Round-7 outcomes.
- The corrected verdict fix occurred after the PositionGroupHash raw result
  existed. It was limited to verdict categorization only; raw capacities and
  crossings were not modified. Documented in ROUND7_ANALYSIS_VERDICT_FIX.md.
- No Holm-Bonferroni correction is applied to Round-7. No Wilcoxon tests.
  Any sign test output is exploratory only and must not determine claims.
- The FP–PGH and PGH–Random results must be labeled post-exposure corrective
  robustness analysis in all manuscript text.
- Do not present +7.265 pp as an independently replicated effect.
- Do not describe the structural hierarchy as causal proof of device identity.
