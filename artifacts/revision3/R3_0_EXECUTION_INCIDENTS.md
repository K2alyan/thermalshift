# R3-0 Execution Incidents

**Date:** 2026-10-05
**Subject:** Round-3 legacy equivalence run (R3-0) — pre-execution provenance incidents

No incident produced or exposed any F2/F3 corrected-reference result.

---

## Incident 1 — Uncommitted import-path modification

**Runner:** pre-commit modification of 6ee64b2 (sys.path insert for r2_selectors)
**Problem:** Runner was modified after commit and before launch; committed bytes != executing bytes.
**Scenarios completed:** sc30, sc31 (2/25)
**Disposition:** Terminated immediately upon detection. Archived at `invalidated_precommit_r3_0/`. Not reused.

---

## Incident 2 — Runtime NameError in final assembly (runner 850c863)

**Runner commit:** 850c863 (SHA256: a55a48197673fe8ef4c640cae10fc2872ece4f070128c7fc0350f65761bbde65)
**Problem:** `CABINET_REFERENCE_MODE` was referenced in the final result-dict assembly (line 1213) but never defined in the runner. All 25 scenario calculations completed correctly. The crash occurred only during final JSON assembly.
**Scenarios completed:** all 25 (sc30–sc54)
**Final output:** not written (runner crashed before `OUT_FILE.write_text(...)`)
**Disposition:** Run invalidated. Checkpoint subsequently overwritten by Incident 3 fresh run (commit-validation mismatch rejected reuse). Log archived at `invalidated_output_assembly_850c863/r3_run_850c863.log`.

---

## Incident 3 — Stale manifest (runner 4913388 without updated manifest)

**Runner commit:** 4913388 (SHA256: 022d12c54c7f0738c954a11fc7dd15b73622b312bf852c40c5b2ccb3e17ade37)
**Problem:** Runner 4913388 was committed and launched, but the pre-execution manifest (R3_0_EXECUTION_MANIFEST.json) still identified runner 850c863. The checkpoint guard correctly refused to reuse the 850c863 checkpoint (commit mismatch) and the run restarted from scratch. Terminated at 4/25 scenarios when the stale manifest was detected.
**Scenarios completed:** sc30–sc33 (4/25)
**Disposition:** Terminated. Checkpoint archived at `invalidated_stale_manifest_r3_0/`. Not reused.

---

---

## Incident 4 — Equivalence FAIL: policy seed schedule mismatch (runner 4913388)

**Runner commit:** 4913388 (SHA256: 022d12c54c7f0738c954a11fc7dd15b73622b312bf852c40c5b2ccb3e17ade37)
**Problem:** Runner 4913388 completed all 25 R3-0 scenarios and failed the frozen equivalence checker with 2,574 failures. full_fp reproduced exactly (0 failures); full_random did not reproduce (2,574 failures). Root cause: `_COMPAT_POLICY_ORDER` defaulted to `list(GATE_F_POLICIES)` instead of `list(CHALLENGE_POLICY_IDS)`. With `GATE_F_RESTRICT_POLICIES=full_fp,full_random`, `GATE_F_POLICIES` was `['full_fp','full_random']`, causing policy seeds to be drawn in that order rather than the canonical r2 order `['full_random','full_fp',...]`. This swapped the RNG streams assigned to full_fp and full_random. full_fp is deterministic with respect to its policy seed and passed; full_random is stochastic and received the wrong seed, producing divergent simulation outputs. No corrected-reference analysis was executed.
**Scenarios completed:** all 25 (sc30–sc54)
**Equivalence result:** FAIL (18,000 passed / 2,574 failed)
**Raw output SHA256:** 76aab0ab33136b226fd2b19d6613d29183509e826f98ce813ff359fc98057af9
**Archived at:** `failed_equivalence_seed_schedule/`
**Fix:** `_COMPAT_POLICY_ORDER` changed to default to `list(CHALLENGE_POLICY_IDS)` — one line. Committed as runner bfb658b.

---

## Resolution

All four incidents resolved. Corrected runner bfb658b committed. Provenance manifest V3 frozen before full rerun.
