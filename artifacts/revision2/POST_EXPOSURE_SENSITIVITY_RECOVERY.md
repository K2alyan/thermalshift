# Post-Exposure Sensitivity Recovery Record

**Created:** 2026-10-04  
**Relevant commits:** 5733b73 (freeze), f1c78a3 (evidence freeze), be4d41c (manuscript draft)

---

## What happened

Phase I of REVIEW2_CHALLENGE_PLAN.md (§13) lists 13 required artifacts that must
exist before any manuscript text is edited. Three are absent:

- `artifacts/revision2/sensitivity_cabinet_scale.json` (Phase E1)
- `artifacts/revision2/sensitivity_loo_beta.json` (Phase E2)
- `artifacts/revision2/final_output_audit.json` (Phase I audit)

`gate_f_manuscript_tables.json` explicitly records the cabinet sensitivity as
`"pending — requires new simulation runs (Phase E1)"`.

The manuscript was drafted at commit be4d41c before these Phase I artifacts existed.
This is a governance deviation from REVIEW2_CHALLENGE_PLAN.md §13.

The omission was discovered during post-analysis review before manuscript submission.

---

## What was preregistered

E1 and E2 specifications were frozen in REVIEW2_CHALLENGE_PLAN.md at commit 5733b73,
before any challenge scenario (sc30–sc54) was executed.

**Phase E1 (Cabinet-Reference Sensitivity, §E1):**  
Run FP vs Random at r=1.25 on sc30–54 with cabinet-envelope scale factors
[0.90, 0.95, 1.00, 1.05, 1.10]. Apply H8 exactly:
- sign change within [0.95, 1.05] → key limitation;
- sign stable across [0.90, 1.10] → robust.

**Phase E2 (Beta Sensitivity, §E2 as amended):**  
Run FP vs Random at r=1.25 on sc30–54 with prespecified beta values:
1. PRIMARY_BETA_CHALLENGE = 1.11416358 (primary LOO cross-fit beta)
2. BETA_F_FROZEN = 1.12484352 (original model estimate)
3. BETA_F_PROSPECTIVE = 0.96 (prospective slope from M1)
4. BETA_F_JACKKNIFE_MEAN (leave-one-job-out of FE slope, §B2a of v1 implementation)
5. BETA_F_CF_P5 = 1.06587054
6. BETA_F_CF_P95 = 1.16910447

**Phase I audit (§13):** Verifies all 13 required outputs present with SHA256s.

---

## What was not changed

No E1/E2 parameter, scenario set, comparison, bootstrap setting, or interpretation
rule was changed after primary-result exposure. Specifically:

- Scale factors: [0.90, 0.95, 1.00, 1.05, 1.10] (from §E1, frozen at 5733b73)
- Beta values: six values above (from §E2 as amended, frozen at 5733b73)
- Comparison: FP vs Random only
- Ratio: r=1.25 only
- Scenarios: sc30–sc54 (same as primary challenge)
- Bootstrap: 5,000 replicates, seed 9999 (same as challenge analysis)
- H8 interpretation rule: unchanged
- H7 beta-stability interpretation rule: unchanged
- No additional beta values or scale factors added

---

## What is different about these runs

Because the primary challenge results were exposed before this omission was
discovered, E1 and E2 cannot be described as blindly executed alongside the
primary challenge. They are:

> **Prespecified sensitivity analyses executed after primary-result exposure
> due to an execution omission. The analysis design (parameters, scenarios,
> comparisons, and interpretation rules) was frozen before any challenge
> scenario was executed.**

This distinction will be disclosed explicitly in the manuscript and any
supplementary provenance record.

---

## Implementation constraints

A separate sensitivity runner (r2_sensitivity_run.py) was derived from the
frozen r2_gate_f_run.py with only the following additions:

1. `GATE_F_SENSITIVITY_BETA` — non-compat beta override (applies in non-compat mode)
2. `GATE_F_CAB_SCALE` — cabinet-envelope multiplicative scale factor
3. Output path/suffix: "r2sensitivity" (does not overwrite challenge outputs)
4. Seed draw order hardcoded to CHALLENGE_POLICY_IDS (all 7, original order),
   to preserve correct policy seeds when restricting to FP+Random only
5. Per-scenario seed assertions against the frozen challenge_seed_index_audit.json

All scientific logic is otherwise line-identical to r2_gate_f_run.py at 5733b73.

---

## Baseline equivalence requirement

Before any non-baseline sensitivity is trusted, the sensitivity runner was
required to exactly reproduce the frozen challenge FP and Random results at:
- cab_scale = 1.00, beta = 1.11416358, sc30–54, r=1.25

Results written to: `artifacts/revision2/sensitivity_runner_equivalence.json`

---

## Manuscript editing status

Manuscript editing (README.md, reviewer_response_r2.md) is paused until:
1. BETA_F_JACKKNIFE_MEAN recovered and source/provenance reported
2. Baseline equivalence PASS
3. E1 and E2 runs complete
4. final_output_audit.json generated

Existing commit be4d41c is not modified or reverted.
