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

## Resolution

All three incidents resolved by:
1. Terminating the affected run
2. Archiving partial evidence under clearly-labelled invalidated directories
3. Writing a corrected pre-execution manifest (R3_0_EXECUTION_MANIFEST_V2.json) identifying runner 4913388 with static preflight PASS, 25/25 seed check, and all invalidated-run disclosures
4. Running a valid R3-0 from scratch with runner 4913388 and manifest V2 committed before launch
