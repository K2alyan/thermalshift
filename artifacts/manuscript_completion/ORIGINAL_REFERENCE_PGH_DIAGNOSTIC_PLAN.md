# Original-Reference PGH Diagnostic Plan

**Status:** Pre-execution freeze  
**Date:** 2026-10-09  
**Branch:** revision1/major-revision-analyses

## Purpose

Decompose the structural-position effect into two independent sources of change
between E2 (original Experiment 2) and Round-7:

1. **Reference change** F1→F2: job-contribution P99 thresholds → concurrent-load
   scheduling period thresholds
2. **Comparator change** PositionTemplate→PGH: LOO-based group score (withdrawn
   as invalid) → group-constant group-mean score with BLAKE2b tie-break

The 2×2 decomposition cells:

| Comparator ↓ / Reference → | F1 (job-contribution P99) | F2 (concurrent-load) |
|---|---|---|
| PositionTemplate (LOO-based) | E2 result: +0.741pp [16/5/4] | not available |
| PositionGroupHash (corrected) | **C8 diagnostic (this run)** | Round-7 C7: +7.265pp [24/1/0] |

C8 fills the lower-left cell, allowing:
- Comparator-change effect (F1 fixed): (F1, PGH) − (F1, PT)
- Reference-change effect (PGH fixed): (F2, PGH) − (F1, PGH)

---

## Scientific context

- E2 raw SHA: `181161082cbf79e32fb138779af20327fd026d5383d70a942e7373a64d635a71`
  Path: `artifacts/revision2/results/gate_f_sc30-54_all_r2challenge_merged.json`
  E2 FP vs PositionTemplate: +0.741pp [16/5/4] at r=1.25

- C7 canonical SHA: `7bca547c732f8ce2b299a5fadf337fdc2a5bf50de06b184a9d0144515b1514ea`
  C7 FP vs PGH (F2 ref): +7.265pp [24/1/0] at r=1.25

---

## Governance

C8 is a **post-exposure mechanism diagnostic**, not a new preregistered analysis.
It does not modify or supersede Round-7 results. No new scientific claims derive
from C8 beyond the decomposition of reference vs comparator change.

Compute freeze (FINAL_SCIENTIFIC_FREEZE.md) applies: this run is explicitly
authorized as the final optional diagnostic. No further runs after C8.

---

## Frozen design

### Active policies (5 total)

| Policy | Selector | Notes |
|---|---|---|
| `full_fp` | Ascending FA_2024 sort | Primary policy |
| `full_random` | Uniform random | Baseline |
| `full_fp_spread` | FP-guided cabinet spread | Spreading control |
| `position_template` | Ascending LOC_FA (group-mean, no singleton correction) | E2 structural comparator |
| `position_group_hash` | Group-mean FA with singleton=global_mean, BLAKE2b | C7 corrected structural comparator |

### Reference

F1 original E2 reference: `artifacts/revision1/results/cabinet_power_envelopes.json`
SHA256: `per_cabinet_p99_kW_correct` field structure (same as loaded in r2_gate_f_run.py)

### Seed chain (rng(2042), identical to C7)

```
Draws  1-25:  scen_seeds
Draws 26-50:  wl_seeds
Draw  51:     _pg_seed  = 218767960  (PLACEBO_GLOBAL_PERM_SEED, consumed for positional identity)
Draw  52:     _pwc_seed = 365514213  (PLACEBO_WITHINCAB_PERM_SEED, consumed for positional identity)
Draws 53-77:  full_random pol_seeds (E2 slot 1)
Draws 78-102: full_fp pol_seeds (E2 slot 2)
Draws 103-127: position_template pol_seeds (E2 slot 3)
Draws 128-152: full_fp_spread pol_seeds (E2 slot 4)
Draws 153-177: random_spread pol_seeds (E2 slot 5, consumed not used)
Draws 178-202: fp_global_placebo pol_seeds (E2 slot 6, consumed not used)
Draws 203-227: fp_withincab_placebo pol_seeds (E2 slot 7, consumed not used)
Draws 228-252: position_group_hash pol_seeds (slot 8, same as C7)
```

The consumed-not-used draws (slots 5-7) maintain positional identity with E2.
The position_group_hash seeds are identical to C7 canonical-beta run.

### Beta and threshold

- BETA_CHALLENGE = 1.11416358 (PRIMARY_BETA_CHALLENGE)
- T_THR_PRIMARY = 63.625°C
- Ratios: [1.0, 1.25]

---

## Equivalence gate (required before production commit)

After SC30 smoke and full run, verify that C8 reproduces E2 exactly for the 4
shared policies (full_fp, full_random, full_fp_spread, position_template) at r=1.25:
- 0 failures
- max_abs_diff ≤ 1e-9

Shared policies use identical F1 reference, identical seed chain → must reproduce
E2 bit-for-bit within floating-point tolerance.

---

## Analysis: 4 comparisons (descriptive only)

At r=1.25, for each scenario sc30-54, compute verdict and delta_lo/delta_hi:

1. FP vs PGH (F1 ref): primary new comparison
2. PGH vs Random (F1 ref): structural signal under original reference
3. FPSpread vs PGH (F1 ref): spreading vs structural comparator
4. PGH vs PositionTemplate (F1 ref): comparator-to-comparator

No Holm-Bonferroni. No Wilcoxon. Descriptive bootstrap 95% CI (seed=9999, 5000 draws).

---

## Runner

File: `artifacts/manuscript_completion/runners/c8_gate_f_run.py`  
SHA256: `b26bede098d87f478ac556659e76e77a74a430daa726a0a65e619667425a35ab`

Supporting files:

| File | SHA256 |
|---|---|
| `c8_launch_parallel.py` | `4faf156e8c9f30d8f9028194eac2d9a36d53773e44f5176f291ee2c9411599ed` |
| `c8_merge.py` | `9607fa4788b2811ec9c88a6f43758fcb52ebd6caf0c5f9da439477df65a978eb` |
| `c8_equivalence_gate.py` | `560608cfc5926f6f4451ff1dddf822251e45025bc1962dbab9b1a43601728b16` |
| `c8_analysis.py` | `0816ed30b351ae692055b83b1447e381fd51879da670379d253e60113afaa725` |

---

## Execution sequence

1. Commit this plan and all new code before any scenario execution
2. SC30 smoke: `GATE_F_N_DEV=1 GATE_F_N_FIRST=30 GATE_F_RATIOS_ONLY=1.0,1.25 python c8_gate_f_run.py`
   — Verify smoke output is consistent with E2 sc30 for shared policies
   — Move smoke output to `results/preflight/` subdirectory
3. Full run: `GATE_F_RATIOS_ONLY=1.0,1.25 python c8_launch_parallel.py` (N_WORKERS=3)
4. Merge: `python c8_merge.py`
5. Equivalence gate: `C8_FILE=... E2_FILE=... python c8_equivalence_gate.py`
   — Must PASS (0 failures) before committing raw
6. Commit raw output (before any analysis)
7. Run analysis: `python c8_analysis.py`
8. Commit analysis output and ORIGINAL_REFERENCE_PGH_DIAGNOSTIC.md
