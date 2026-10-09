# Provenance Manifest

**Date:** 2026-10-09  
**Branch:** revision1/major-revision-analyses  
**Repository:** thermalops  

This manifest records the SHA256 checksums, git commits, and runner SHAs for all
scientific artifacts produced in the C1/C2/C3/C4 corrected-reference analyses.

---

## Repository State

- All tracked changes committed.  
- git status --porcelain --untracked-files=all: empty at audit time.  
- Current HEAD: ab8dc3b (C3 final audit: canonical replay launcher, equivalence gate, corrected analysis).  

---

## Frozen Scientific Runner SHAs

These SHAs were verified before each production run and are embedded in all output JSONs.

| Runner | SHA256 | Freeze commit |
|--------|--------|--------------|
| `c1_gate_f_run.py` | `7cb51ebcf541d9c04b932ef879ce5095d34195452ef88151418d01ce844b41ba` | 5733b73b |
| `c2_gate_f_run.py` | `e0de9d35a99715bc05c08177b08ad399bb25902fb492ef3487223135b7d3c44a` | 5733b73b |
| `c3_gate_f_run.py` | `3b4e9825462a5f8b80bc6f76c6938bcf88d460d12f782210474b38573654e91c` | 5733b73b |

All three runners share freeze commit `5733b73b`.

---

## Shared Reference Files

Both C2 and C3 use the corrected concurrent-load cabinet reference.

| File | SHA256 |
|------|--------|
| `f2_local_scheduling_reference.json` | `71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34` |
| `f2_replay_denominator.json` | `b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48` |

---

## C1 — Corrected-Reference Analysis (sc5-29, all ratios)

| Artifact | SHA256 | Commit |
|----------|--------|--------|
| `gate_f_sc5-29_all.json` (raw C1 merged) | `8d66349fb1158d212098adacec268b80afe2cf0f48e0b1afb035114313684ec3` | 54772b4 |
| `c1_correctedref_analysis.json` | `1540257b6d04f134c4362ae86f8c55c15cf8d010db79ee1a3982bb9e56308fb7` | 5edc860 |

C1 notes:
- 25 scenarios sc5-29; all ratios; N_WORKERS=3.
- sc5 run separately and verified for equivalence before sc6-29 merge (amendment documented).

---

## C2 — Corrected-Reference Analysis (sc30-54, r=1.25, 8-policy)

| Artifact | SHA256 | Commit |
|----------|--------|--------|
| `gate_f_sc30-54_1p25_c2manuscript.json` (raw C2 merged) | `b4dbc4bc0f8646f197d0a575f42dc785e97710f22460c7f2c8a1913866c6b129` | 65ca107 |
| `c2_correctedref_analysis.json` | `bcc319caddf9d092d14eed74dbc2da885a800644deadbd0d9b03a56ad8997653` | 96b2ade |

C2 notes:
- 25 scenarios sc30-54; r=1.25 only; 7 policies (full_fp, full_random, position_loo,
  full_fp_spread, random_spread, fp_global_placebo, fp_withincab_placebo).
- sc30 equivalence gate passed vs historical r3f2local (SHA 5982264f...).
- 8 comparisons with Holm-Bonferroni correction (8 tests, alpha=0.05).
- Post-outcome compatibility fixes (print encoding, scipy API) verified to produce
  zero scientific change; documented in C2_POSTRUN_COMPATIBILITY_NOTE.md (commit 271c51a).

---

## C4 — Cabinet Diagnostic (cabinets 2600/2601/2602)

| Artifact | SHA256 | Commit |
|----------|--------|--------|
| `c4_cabinet_diagnostic.json` | `28e7444019cc6f4c0383f5ea3e7bacd4f6832bbf6fbafc22ef4abf6e567c65c8` | 96b2ade |

C4 notes:
- Reads cabinet_accounting fields from C2 raw result.
- Audits node-hours and event-touches for late cabinets (2600/2601/2602).
- No new replay. Reads FP topology from fp_node_topology.csv.

---

## C3 — Threshold Sensitivity (P90/P95/P99)

### P90 (T=61.875 C)

| Artifact | SHA256 | Commit | Notes |
|----------|--------|--------|-------|
| `gate_f_sc30-54_1p25_t61p875_c3manuscript.json` (original P90) | `0cd2371a71d96c6e852c429e8fec17d4e0ab0e985dcd9b42003bcf6009bbe084` | 61c1d34 | Mixed-commit artifact: sc30-32 at 5f050eb, sc33-54 at 49da4c6; scientific runner SHA identical. |
| `gate_f_sc30-54_1p25_t61p875_c3canonical.json` (canonical replay) | `a94f72084de1eb2633cddd6f22157803a29a230adb03907d6407256bcaad2181` | d6dd2b9 | Single-commit clean replay; all 25 workers at HEAD 3a7bd3c; equivalence gate PASS (max_abs_diff=0.0). |

P90 provenance notes:
- Original P90 was affected by a mid-run commit (P99 invalidation markdown note committed
  at 49da4c6 during sc30-32 execution). The scientific runner SHA was unchanged; only
  INVALIDATED_C3_P99_CONCURRENT_LAUNCH.md differed.
- The original P90 is scientifically valid but has mixed-commit execution metadata.
- Canonical replay is a provenance-repair replay, not new scientific evidence.
- After canonical equivalence gate PASS: the canonical file becomes the submission artifact.
  Original is retained for historical traceability.

### P95 (T=63.625 C) — reuses accepted C2 result

| Artifact | SHA256 | Commit |
|----------|--------|--------|
| `gate_f_sc30-54_1p25_c2manuscript.json` (P95 source = C2 result) | `b4dbc4bc0f8646f197d0a575f42dc785e97710f22460c7f2c8a1913866c6b129` | 65ca107 |

P95 notes: P95 uses the accepted C2 corrected-reference result without re-running workers.

### P99 (T=66.6625 C)

| Artifact | SHA256 | Commit | Notes |
|----------|--------|--------|-------|
| `gate_f_sc30-54_1p25_t66p6625_c3manuscript.json` | `2fef4c49500e4f3c61bc2de63edf7ee7320be4d301a44544402e610eac6c5cbc` | 30312e5 | Single-commit clean run; git HEAD 61c1d34 for all 25 workers. |

P99 notes:
- Original P99 launch (task bx0m624ki) was terminated before any scenario completed
  due to simultaneous 6-worker resource-gate violation (documented: 49da4c6
  INVALIDATED_C3_P99_CONCURRENT_LAUNCH.md).
- Recorded P99 is from a clean sequential relaunch with N_WORKERS=3 as sole active run.

### C3 Threshold Analysis

| Artifact | SHA256 | Commit | Notes |
|----------|--------|--------|-------|
| `c3_threshold_analysis.json` (initial, original P90 SHA) | `54b2cfba2f29f34de8f862f698f83dbaea4927dbcf56b92d00657f010f4748ed` | 1c8b0ef | Uses original P90 SHA; superseded after canonical replay. |
| `c3_threshold_analysis.json` (final, canonical P90 SHA) | `(see committed file)` | (this commit) | Canonical P90 SHA pinned; numerical results verified unchanged from initial run. |

---

## SHA placeholder fill-in note

The c3_threshold_analysis.py script originally contained `sha: None` placeholders for
P90 and P99. These were filled with the actual SHA256 values after raw results were
committed — before any analysis was run. Filling SHA placeholders changes only input
pinning (what file is loaded and verified), not any calculation. The analysis script
SHA itself changes when placeholders are filled; the new script SHA is re-recorded in
each run's output JSON.

This fill-in is analogous to adding a known-good data file checksum to a verification
step — it is not a post-hoc modification of the analysis logic.

---

## Operational events (non-scientific)

| Event | Date | Record |
|-------|------|--------|
| P99 concurrent launch invalidated (6-worker resource gate violation) | 2026-10-09 | INVALIDATED_C3_P99_CONCURRENT_LAUNCH.md (49da4c6) |
| P90 mixed-commit artifact (markdown commit during run) | 2026-10-09 | See P90 provenance notes above; resolved by canonical replay |
| Post-C2 compatibility fixes (print encoding, scipy API) | 2026-10-09 | C2_POSTRUN_COMPATIBILITY_NOTE.md (271c51a); zero scientific change verified |
| c3_parallel_merge.py patched to allow commit-mismatch exception | 2026-10-09 | Commit 43e2fab; flag used only for original P90; not used for canonical replay or P99 |
