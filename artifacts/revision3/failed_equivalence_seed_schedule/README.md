# Failed Equivalence Attempt — Policy Seed Schedule Mismatch

**Runner commit:** 4913388
**Equivalence result:** FAIL
**full_fp:** reproduced (0 failures of ~9,000 full_fp checks)
**full_random:** did not reproduce (2,574 failures)
**Checks passed:** 18,000
**Checks failed:** 2,574
**Raw output SHA256:** 76aab0ab33136b226fd2b19d6613d29183509e826f98ce813ff359fc98057af9
**Checker result SHA256:** 00646684375a7a62324f078d7ae5f9b5c26ffbf86aaad223ecbdd4648dba2298

**Suspected cause:** Policy-seed schedule mismatch. `GATE_F_RESTRICT_POLICIES=full_fp,full_random`
caused `_COMPAT_POLICY_ORDER` to be `['full_fp','full_random']` instead of the full canonical
`CHALLENGE_POLICY_IDS` order. This swapped the RNG streams assigned to full_fp and full_random.
full_fp is deterministic with respect to its policy seed and passed; full_random diverged.

**No F2/F3 corrected-reference analysis was executed.**

This run will never be reused as accepted equivalence evidence.
This directory is audit history only.
