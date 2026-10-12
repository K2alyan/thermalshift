# Stale Value Scan

**Date:** 2026-10-09  
**Scanned file:** `artifacts/manuscript_completion/thermalops_manuscript.tex`  
**Script:** manual regex scan via Python; run at manuscript-integration time.

This document records the scan for forbidden internal names, stale numerical values,
and prohibited characterizations. All items must be CLEAN before submission.

---

## Scan Results

### Forbidden internal names

| Pattern | Found? | Notes |
|---------|--------|-------|
| Gate F | CLEAN | not present |
| C1, C2, C3, C4 (internal analysis labels) | CLEAN | not present |
| F1, F2 (internal reference labels) | CLEAN | not present |
| revision1, revision2, revision3 | CLEAN | not present |
| reviewer-requested | CLEAN | not present |
| accepted run | CLEAN | not present |
| Task-D | CLEAN | not present |

### Stale numerical values

| Pattern | Found? | Notes |
|---------|--------|-------|
| 15.5 (old threshold) | CLEAN | not present |
| 12.76 (old value) | CLEAN | not present |
| R² = 0.857 or 0.8572 (old node R²) | CLEAN | not present |
| R² = 0.2067 (job-level R², must not appear as node-level) | CLEAN | not present |
| 0.4547 (job-level Pearson, must not appear as node-level) | CLEAN | not present |
| 6.706 (raw original value, should only appear rounded as 6.71 in §6.1) | CLEAN | not present |

### Values expected in manuscript at specific locations

| Value | Expected location | Actual location | Correct? |
|-------|------------------|-----------------|----------|
| +6.71 pp | §6.1 only (original result, historical) | §6.1 (line ~23113) | YES — correct |
| 22/25 | §6.1 only | §6.1 | YES — correct |
| +3.54 pp | §6.1 only | §6.1 (line ~23250) | YES — correct |
| 20/25 (WithinCab original) | §6.1 only | §6.1 | YES — correct |

These values appear only in the original-results paragraph (§6.1), as intended.
They are not claimed as primary results.

### Prohibited characterizations

| Pattern | Found? | Notes |
|---------|--------|-------|
| "Other" (binding constraint category) | CLEAN | replaced with B_ratio / S_ratio |
| "thermal budget relaxes" | CLEAN | not present |
| "no thermal constraint" | CLEAN | not present |
| dose-response framing for P99 | CLEAN | P99 magnitude explicitly flagged as floor-limited |

---

## Bibliography [VERIFY] entries

The following bibliography entries in `thermalops.bib` are marked [VERIFY] and
require author/venue/page confirmation before submission:

| Cite key | Issue |
|----------|-------|
| `tapas` | Tentatively Etinski et al. IPDPS 2010; confirm this is the intended TAPAS system |
| `pal` | Tentatively Tang et al. TPDS 2008; confirm this is the intended PAL system |
| `sinha2023thermal` | Author list and venue need confirmation |
| `ostrouchov2020machine` | Author list and venue need confirmation |
| `inadomi2015hpc` | Author list confirmed via revision2 audit; page range needs confirmation |
| `exadigit` | Confirm primary ExaDigiT system publication |

---

## Items NOT scanned (manual review required)

- Figure content (figures are currently [TODO] placeholders; stale values cannot
  appear in figures until figures are regenerated with corrected-reference data)
- Appendix A preflight list (16 conditions) — confirm still current
- DOI placeholders in Appendix D (zenodo DOI, OLCF dataset DOI)

---

## Scan verdict

**CLEAN** for all forbidden strings and stale numerical values.  
**ACTION REQUIRED** for bibliography [VERIFY] entries before submission.  
**ACTION REQUIRED** for figure regeneration (all figures currently TODO placeholders).
