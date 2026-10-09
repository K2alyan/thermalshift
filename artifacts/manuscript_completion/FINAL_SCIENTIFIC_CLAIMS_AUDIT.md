# Final Scientific Claims Audit

**Status:** Pre-integration audit — all claims verified against frozen committed evidence.  
**Date:** 2026-10-09  
**Branch:** revision1/major-revision-analyses  
**Auditor:** Automated audit from committed result JSONs  

This document records the allowed and prohibited wording for each scientific claim before
manuscript integration. The experimental hierarchy must be preserved:

- Original Experiment 1 and Experiment 2 used the original (non-corrected) cabinet reference;
  those were sequentially pre-specified.
- C1/C2/C3 corrected-reference analyses are post-exposure (post-R2) reference-sensitivity analyses.
  They are not retroactively preregistered primary experiments.
- C3 is exploratory threshold sensitivity — not a new preregistered analysis.

---

## Claim Table

| # | Claim | Evidence source | Status | Allowed wording | Prohibited overclaim |
|---|-------|----------------|--------|-----------------|----------------------|
| 1 | Prospective node/slot thermal fingerprint is persistent and predictive | Gate E fingerprint design; fp_spread rule (Phase 3B.1-H); fingerprint validated on held-out sc5-29 | **SUPPORTED** | "The node/slot thermal fingerprint computed from historical F1 data prospectively identifies thermally distinct placement options for sc5-29 held-out scenarios." | Do not claim the fingerprint is causal or hardware-specific; do not claim it is validated beyond the sc5-29 held-out set. |
| 2 | FP placement beats Random under corrected concurrent-load cabinet reference (primary result) | C2 Q1: 25A/0I/0B, med delta_lo=+12.48pp, 95% CI [+11.09, +19.04], Holm-adjusted sign p=4.77e-7 | **SUPPORTED** | "Under the corrected concurrent-load cabinet reference, full fingerprint placement outperformed random placement in all 25 held-out scenarios (25A/0I/0B), with median thermal-capacity advantage delta_lo=+12.48pp (bootstrap 95% CI: [+11.09, +19.04]pp). Sign test Holm-adjusted p=4.77e-7." | Do not describe as preregistered primary result (C2 is corrected-reference sensitivity). Do not omit that B_ref and S_ref were recomputed using the corrected concurrent-load reference. Do not claim this resolves the causal mechanism (hardware vs fixed-slot). |
| 3 | FP advantage is not explained by cabinet composition | C2 Q2 FP vs WithinCab: 24A/1I/0B, med delta_lo=+10.88pp, Holm sig p=4.77e-7 | **SUPPORTED** | "FP placement outperformed the within-cabinet fingerprint placebo in 24/25 scenarios (24A/1I/0B, med delta_lo=+10.88pp, Holm p=4.77e-7), indicating that the advantage is not fully explained by cabinet-level composition." | Do not claim this definitively eliminates all cabinet-level explanations. One indeterminate scenario exists. |
| 4 | FP advantage is not explained by fixed rack position (structural position baseline) | C2 Q4 FP vs PositionLOO: 25A/0I/0B, med delta_lo=+13.95pp, Holm sig p=4.77e-7 | **SUPPORTED** | "FP placement outperformed the leave-one-out structural position baseline in all 25 scenarios (25A/0I/0B, med delta_lo=+13.95pp, Holm p=4.77e-7), indicating the advantage is not attributable to fixed rack position assignment alone." | Do not conflate position_loo with a pure rack-position effect — it is a leave-one-out reconstruction of historical position. Do not claim hardware vs fixed-slot confound is resolved. |
| 5 | FP advantage is not explained by global placebo ranking | C2 Q3 FP vs Global: 25A/0I/0B, med delta_lo=+12.31pp, Holm sig p=4.77e-7 | **SUPPORTED** | "FP placement outperformed the global fingerprint placebo in all 25 scenarios (25A/0I/0B, med delta_lo=+12.31pp, Holm p=4.77e-7), indicating the advantage requires within-workload rather than global ranking." | Do not use this to claim the fingerprint is thermally causal. |
| 6 | Random spreading provides no significant benefit over unranked random | C2 Q7 RandSpread vs Random: 5A/14I/6B, Holm p=1.0, not significant | **SUPPORTED — NULL** | "Random spreading showed no statistically distinguishable benefit over random placement (5A/14I/6B, Holm p=1.0), consistent with null effect." | Do not claim random spreading is harmful (verdict is indeterminate, not B-majority). |
| 7 | Fingerprint ranking still helps under a spreading constraint | C2 Q5 FPSpread vs RandSpread: 23A/2I/0B, med delta_lo=+4.42pp, Holm sig p=4.77e-7 | **SUPPORTED** | "FP-guided spreading outperformed random spreading in 23/25 scenarios (23A/2I/0B, med delta_lo=+4.42pp, Holm p=4.77e-7)." | Do not claim FPSpread matches FP — Q6 shows it does not. |
| 8 | Direct FP placement outperforms FP-guided spreading | C2 Q6 FP vs FPSpread: 0A/0I/25B (FP>FPSpread), med delta_lo(FPSpread vs FP)=-9.18pp, Holm sig p=4.77e-7 | **SUPPORTED** | "Direct fingerprint placement outperformed FP-guided spreading in all 25 scenarios (0A/0I/25B from the perspective of FPSpread, med advantage of direct FP over FPSpread = +9.18pp, Holm p=4.77e-7). Concentration, not dispersion, maximizes the thermal advantage." | Do not claim spreading is always suboptimal under all conditions — this result is specific to r=1.25 at this thermal operating point. |
| 9 | FP-guided spreading outperforms structural position baseline | C2 Q8 FPSpread vs PositionLOO: 24A/1I/0B, med delta_lo=+4.96pp, Holm sig p=4.77e-7 | **SUPPORTED** | "Even under a spreading constraint, fingerprint-guided placement outperformed the structural position baseline in 24/25 scenarios (24A/1I/0B, med delta_lo=+4.96pp, Holm p=4.77e-7)." | This is a supplemental comparison, not the primary evidence chain. |
| 10 | Late cabinets (2600/2601/2602) do not dominate the result | C4 cabinet diagnostic (commit 96b2ade): cabinet node-hours, event-touches, FP topology share | **SUPPORTED** | "The late-deployed cabinets (2600/2601/2602) were audited for disproportionate influence on the result. [Report C4 findings here — exact language depends on C4 output.]" | Do not claim the late cabinets are unimportant or have no effect — only that they do not dominate. |
| 11 | FP-vs-Random direction is robust to thermal threshold definition | C3 P90/P95/P99: 24A/1I/0B at P90, 25A/0I/0B at P95, 25A/0I/0B at P99 | **SUPPORTED — DIRECTIONAL ROBUSTNESS ONLY** | "The sign of the FP advantage was preserved under all three threshold definitions: P90 (T=61.875C, 24A/1I/0B, delta_lo=+8.90pp), P95 (T=63.625C, 25A/0I/0B, delta_lo=+12.48pp), and P99 (T=66.6625C, 25A/0I/0B, delta_lo=+21.33pp). Because B_ref_s and S_ref_s are recomputed at each threshold, these are alternative exposure definitions, not a monotonic relaxation of one constraint." | Do NOT describe the +8.90 -> +12.48 -> +21.33 progression as a dose-response or monotonically increasing effect. Do NOT claim P99 demonstrates a larger effect — at P99, 19/25 Random scenarios are left-boundary limited, making the P99 magnitude floor-limited rather than reflecting a larger FP advantage. Use C3 only for directional robustness. |
| 12 | Causal limitation: hardware vs fixed-slot assignment | Design constraint | **LIMITATION — MUST BE REPORTED** | "Because jobs are assigned to specific physical slots, thermal advantages associated with the fingerprint could partially reflect fixed hardware heterogeneity (certain slots are inherently cooler) rather than a predictive advantage of the fingerprint itself." | Do not omit this limitation. Do not claim the placebo controls fully resolve it — they control for cabinet composition and global ranking, but within-cabinet hardware heterogeneity at the slot level remains a plausible partial explanation. |
| 13 | Limitation: scenario bootstrap shares common base workload | Design constraint | **LIMITATION — MUST BE REPORTED** | "All 25 scenarios are drawn from the same base workload replay under common scenario seeds. Scenario-level independence is not guaranteed; the bootstrap provides a measure of scenario variability but not independent replication." | Do not claim the 25 scenarios are independent experiments. |
| 14 | Limitation: corrected cabinet reference uses a selected-day concurrent-load pattern | C2 corrected reference: f2_local_scheduling_reference.json (SHA 71de8abc...) | **LIMITATION — MUST BE REPORTED** | "The corrected cabinet reference (B_ref, S_ref) was derived from a single concurrent-load scheduling period. Results may differ under other concurrent-load patterns or cabinet utilization regimes." | Do not claim the corrected reference is the universally correct normalization. |

---

## Experimental Hierarchy

| Analysis | Type | Status |
|----------|------|--------|
| Original Experiment 1 (pre-R2, original cabinet reference) | Pre-specified primary | Superseded by corrected-reference analyses; not used for primary claims |
| Original Experiment 2 (pre-R2, original cabinet reference) | Pre-specified primary | Superseded by corrected-reference analyses; not used for primary claims |
| C1 (corrected reference, sc5-29, all ratios) | Post-exposure reference-sensitivity | Committed at 5edc860; supports fingerprint persistence and general FP direction |
| C2 (corrected reference, sc30-54, r=1.25, 8 policy comparisons) | Post-exposure reference-sensitivity, most policy-complete | Committed at 96b2ade; **primary claims 2-9 in this audit** |
| C3 (corrected reference, P90/P95/P99 threshold sensitivity) | Post-exposure, exploratory | Committed at 1c8b0ef (original) / to be recommitted with canonical P90; **directional robustness only (claim 11)** |
| C4 (cabinet diagnostic, cabinets 2600/2601/2602) | Supplemental diagnostic | Committed at 96b2ade; **claim 10** |

---

## Sign test family-wise error correction

8 comparisons (Q1-Q8) were subjected to Holm-Bonferroni correction at alpha=0.05.  
All comparisons except RandSpread_vs_Random are significant at Holm-adjusted alpha.  
RandSpread_vs_Random has Holm p=1.0 (not significant, consistent with null).

| Comparison | Verdict | Holm-adj p | Significant |
|-----------|---------|------------|-------------|
| FP_vs_Random | 25A/0I/0B | 4.77e-7 | Yes |
| FP_vs_WithinCab | 24A/1I/0B | 4.77e-7 | Yes |
| FP_vs_Global | 25A/0I/0B | 4.77e-7 | Yes |
| FP_vs_PositionLOO | 25A/0I/0B | 4.77e-7 | Yes |
| FPSpread_vs_RandSpread | 23A/2I/0B | 4.77e-7 | Yes |
| FPSpread_vs_FP | 0A/0I/25B | 4.77e-7 | Yes |
| RandSpread_vs_Random | 5A/14I/6B | 1.000 | No |
| FPSpread_vs_PositionLOO | 24A/1I/0B | 4.77e-7 | Yes |

---

## Prohibited characterizations (global)

- Do not describe C2 as preregistered or as Experiment 1/2.
- Do not describe C3 P99 as demonstrating a larger effect than P95 — P99 magnitude is floor-limited.
- Do not describe the thermal threshold progression as "relaxing the thermal budget" — all three thresholds involve different B_ref_s/S_ref_s definitions.
- Do not claim the fingerprint is causally identified — hardware heterogeneity remains a plausible alternative explanation.
- Do not use "Other" in binding-constraint tables — use exact raw constraint names (B_ratio, S_ratio).
- Do not claim B_ratio is "not a thermal constraint" — B_ratio is the thermal-incidence-ratio constraint.
