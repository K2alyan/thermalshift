# R3-0 Legacy Equivalence Report

**Result: PASS**

---

## Provenance

| Field | Value |
|---|---|
| Plan commit | c674209 |
| Plan version | 2.2 |
| Runner source commit | bfb658b |
| Runner SHA256 | 11bc0dd626d6246425ce8298c13e29355f80aeda910c38ffbf97ca1a0cc71e1a |
| Provenance commit | b5ff82b |
| Execution HEAD at launch | b5ff82b |
| Runner diff bfb658b..HEAD | empty (runner unchanged) |
| Raw R3 output SHA256 | 0f2736058fca95117d5a03cb43e08eab93145c3d5ea7c82054ecc4cb08ddea97 |
| Checker SHA256 | 0f58c29de8fa1cb8fee2c8c2c3bfecf62a5abf86591254ca5a8505f5a18d93e3 |
| Checker result SHA256 | 0b802feab4a8b32545f5597a924f24f1bb49e1354770fad8e9b81bbc3521dc07 |

---

## Equivalence Results

| Metric | Value |
|---|---|
| Scenarios checked | 25 (sc30–sc54, exactly) |
| Policies checked | full_fp, full_random |
| Ratio checked | 1.25 |
| Tolerance | 1e-09 |
| Total checks passed | 27,400 |
| Total failures | 0 |
| Maximum absolute numeric difference | 0 (exact integer match on seeds; floating-point budget fields match within 1e-09) |
| Lambda-count mismatches | 0 |
| Categorical mismatches | 0 |
| Missing/null-structure mismatches | 0 |
| Scenario-set mismatches | 0 |
| **Final verdict** | **PASS** |

---

## Pre-execution Verification

All of the following were confirmed before launch and are recorded in manifest V3 (commit b5ff82b):

| Check | Result |
|---|---|
| py_compile | PASS |
| ruff F821 undefined-name | PASS (0 errors) |
| Final result-dict name audit | PASS (all 19 names verified defined) |
| Canonical seed schedule 225/225 | PASS |
| Restricted-policy invariance 50/50 | PASS |
| Seed schedule mutation self-tests 5/5 | PASS |
| sc30 exact smoke equivalence (1,059 checks) | PASS (max diff 0.0) |

---

## Prior Attempt History

Runner 4913388 previously failed equivalence because policy RNG allocation depended on the restricted active-policy list. With `GATE_F_RESTRICT_POLICIES=full_fp,full_random`, `_COMPAT_POLICY_ORDER` was `['full_fp','full_random']` instead of the canonical `['full_random','full_fp',...]`, swapping the RNG streams assigned to each policy. The corrected runner bfb658b restores the frozen revision2 canonical policy-seed allocation by fixing `_COMPAT_POLICY_ORDER` to always default to `list(CHALLENGE_POLICY_IDS)`. Before the full rerun, all 225 canonical seed comparisons, 50 restricted-policy invariance comparisons, five negative mutation tests, and an exact sc30 software smoke comparison passed.

A complete incident history is recorded in `R3_0_EXECUTION_INCIDENTS.md`. Four execution attempts preceded this accepted run; all invalidated checkpoints and outputs are preserved in labelled archive directories and were not reused.

No F2/F3 corrected-reference analysis was executed.

---

## Files

| File | Role |
|---|---|
| `results/gate_f_sc30-54_1p25_r3legacy.json` | Raw R3-0 output (accepted equivalence evidence) |
| `check_r3_legacy_equivalence_result.json` | Checker output (PASS, 27,400 checks) |
| `R3_LEGACY_EQUIVALENCE_REPORT.md` | This document |
| `R3_0_EXECUTION_MANIFEST_V3.json` | Pre-execution provenance manifest |
| `R3_0_EXECUTION_INCIDENTS.md` | Full incident history (4 prior attempts) |
