# Round-7 Analysis Verdict Classification Fix

Generated: 2026-10-10  
Branch: revision1/major-revision-analyses

## Status

The Round-7 canonical-beta raw simulation (commit 1e31568, SHA
`7bca547c...`) is ACCEPTED and unchanged. This document records a
post-outcome fix to the analysis script only.

## What happened

After the canonical-beta production run completed and c7primary_analysis.json
was generated, a verdict inconsistency was identified:

- Accepted C2 result: FP_vs_WithinCab = 24A / 1I / 0B
- Round-7 reproduction: FP_vs_WithinCab = 24A / 0I / 1B

Since the raw FP and fp_withincab_placebo outputs are bit-identical between C2
and C7 (proven by the full-field equivalence gate: 253,455 fields, 0 failures,
max diff = 0.0), the Round-7 analysis must reproduce the C2 verdict exactly.
The discrepancy was therefore an analysis-code bug, not a simulation problem.

## Bug identified

File: `artifacts/manuscript_completion/analysis/c7_analysis.py`

Incorrect verdict logic (pre-fix):
```
delta_lo = C_lower(A) - C_upper(B)
if delta_lo > 0:    n_A += 1
elif delta_lo < 0:  n_B += 1   # WRONG — classifies B from delta_lo alone
else:               n_I += 1
```

The bug classified any scenario with `delta_lo < 0` as B, regardless of
`delta_hi`. This misclassifies the straddling case where the intervals overlap:
`delta_lo < 0 < delta_hi`.

## Correct verdict rule (frozen)

```
delta_lo(A,B) = C_lower(A) - C_upper(B)
delta_hi(A,B) = C_upper(A) - C_lower(B)

A  iff  delta_lo > 0                (strict)
B  iff  delta_hi < 0                (strict)
I  otherwise                        (straddle, right-censored B, zero boundary)
```

## Fix applied

Verdict logic restructured to compute delta_lo and delta_hi before
classification, then apply the three-way rule with strict inequalities.
Right-censored B remains I regardless of delta_hi.

## Scope of fix

Only the A/I/B verdict counting was incorrect. These items were NOT affected
and do NOT change:

- Raw simulation data (frozen at commit 1e31568)
- C_lower_pct / C_upper_pct per scenario (from raw data)
- delta_lo per scenario (arithmetic unchanged)
- delta_hi per scenario (arithmetic unchanged)
- Median delta_lo / delta_hi
- Bootstrap confidence intervals (seed 9999, 5000 draws)
- Absolute capacity statistics
- Binding constraint distributions

## Regression verification

After the fix, the corrected verdict logic was verified against the accepted
C2 raw result (gate_f_sc30-54_1p25_c2manuscript.json):

| Comparison | Corrected C7 | Accepted C2 | Status |
|---|---|---|---|
| FP_vs_Random | 25/0/0 | 25/0/0 | PASS |
| FP_vs_WithinCab | 24/1/0 | 24/1/0 | PASS |

Straddling scenario for FP_vs_WithinCab: sc51.

## Unit tests added

`test_c7_verdict.py` covers:
- T1: Definite A (delta_lo > 0)
- T2: Definite B (delta_hi < 0)
- T3: Straddle I (delta_lo < 0 < delta_hi)
- T4: Zero delta_lo boundary → I (not A)
- T5: Zero delta_hi boundary → I (not B)
- T6: Right-censored B → I
- T7: Left-boundary A, straddle → I
- T8: Both at zero → I
- T9: FP-vs-WithinCab straddler pattern → I

All 9 pass. Both regression comparisons pass.

## Analysis rerun

c7primary_analysis.json was regenerated from the same frozen raw file
(SHA `7bca547c...`) using the corrected analysis script. The raw
production commit (1e31568) was not amended or replaced.

## Transparency note

This fix occurred after the PositionGroupHash raw result was already computed
and in hand. The fix was limited to verdict categorization in the analysis
script. The raw capacities, crossings, and all simulation mechanics were not
modified. The fix was committed separately from the raw production result.
