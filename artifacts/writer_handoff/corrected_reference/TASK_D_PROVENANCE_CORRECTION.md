# Task-D Provenance Correction

**Date:** 2026-10-06  
**Plan commit:** c674209  
**R3 evidence commit:** a80d51f

## Statement of Provenance Deviation

1. The Task-D F2 methodology was specified externally in a chat instruction before Task-D computation began.

2. During Claude Code execution, Task-D result files already existed in the working tree before git commit f403998 was made. Therefore f403998 is a repository capture of the externally pre-specified Task-D method and code, NOT a cryptographic pre-computation git freeze.

3. 90dc62f contains the first committed Task-D result package.

4. No scheduling-policy simulation result had been run or observed during Task D.

5. No F2-vs-F1 scheduling outcome influenced the Task-D reference construction.

6. History was not rewritten.

## Correct Description of Commits

- **f403998** = first committed repository capture of the externally pre-specified Task-D method (TASK_D_F2_REFERENCE_PLAN.md, task_d_f2_reference_plan.json, task_d_f2_reference.py staged; result files were already present in working tree but not yet committed).

- **90dc62f** = first committed Task-D result package (all result files, figures, and markdown reports staged and committed for the first time).

## Provenance Metadata

| Field | Value |
|-------|-------|
| plan_commit | c674209 |
| r3_evidence_commit | a80d51f |
| date | 2026-10-06 |
