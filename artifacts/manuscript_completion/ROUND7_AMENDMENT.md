# Round 7 Amendment — Pre-Execution Freeze Corrections

**Date:** 2026-10-09  
**Amends:** commit 1937f4c (Round 7 pre-execution draft)  
**Status:** Required before any sc30–sc54 execution is authorized

---

## Correction 1 — Terminology

Commit 1937f4c used the term **"preregistration freeze."** This was incorrect.

Round 7 is a **post-exposure corrective robustness analysis**, designed after the
position_loo mathematical artifact was identified through adversarial review.
It is not preregistered. It is not blind to prior results. It cannot be presented
in the manuscript as prespecified before the original experiments.

**Corrected terminology throughout:**  
> pre-execution freeze for a post-exposure corrective robustness analysis

Git history is not rewritten. This amendment document supersedes the commit message.

---

## Correction 2 — Structural Group-Size Audit and Singleton Rule

### Audit results (2,000-node cohort, key = chassis_slot_board_node_pos)

| Metric | Value |
|--------|-------|
| Total nodes | 2,000 |
| Total groups | 67 |
| Min group size | **1** |
| Median group size | 8.0 |
| Max group size | 73 |
| **Singleton groups (size=1)** | **10** |
| **Nodes in singleton groups** | **10** |
| Size-2 groups | 8 |
| Nodes in size-2 groups | 16 |
| Missing FA_2024 | 0 |

Group-size distribution:
```
size= 1:  10 groups  (singletons — AFFECTED BY THIS CORRECTION)
size= 2:   8 groups
size= 3:   5 groups
size= 4:   3 groups
size= 5:   1 group
size= 6:   5 groups
size= 7:   1 group
size= 8:   1 group
size= 9:   2 groups
size=10:   1 group
size=12:   1 group
size=19:   1 group
size=35:   1 group
size=43:   1 group
size=57:   1 group
size=60:   1 group
size=63:   3 groups
size=66:   5 groups
size=68:   5 groups
size=69:   2 groups
size=71:   4 groups
size=72:   3 groups
size=73:   2 groups
```

### Singleton hostnames and FA_2024 values

| hostname | group key | FA_2024 |
|----------|-----------|---------|
| frontier02996 | 3_1_1_0 | +1.717767 |
| frontier03142 | 4_2_1_0 | +0.583210 |
| frontier03647 | 3_7_0_0 | −1.483228 |
| frontier07728 | 2_7_1_0 | −0.210270 |
| frontier09159 | 4_3_0_0 | −4.152237 |
| frontier09160 | 4_3_1_0 | −2.564486 |
| frontier09161 | 4_4_0_0 | −3.551443 |
| frontier09281 | 4_0_0_0 | −2.209501 |
| frontier09405 | 3_6_0_0 | −1.621282 |
| frontier10192 | 4_7_1_0 | +1.336841 |

Global cohort mean FA_2024 (all 2,000 nodes, no NaN): **−0.03720489**

### Singleton rule (frozen)

The original draft's `build_position_group_hash_fa` assigned `group_mean` to all
group members uniformly, including singletons. For a singleton, group_mean =
(S_g - 0) / max(1, 1) = the node's own FA_2024. This reintroduces individual
identity through a structural wrapper.

**Corrected rule:**

| Group size | Score assigned |
|-----------|----------------|
| ≥ 2 | Arithmetic mean FA_2024 of entire group (all members get identical score) |
| = 1 | Global cohort mean FA_2024 = **−0.03720489** (neutral, no individual identity) |

This rule is frozen. No data-driven fallback hierarchy is permitted.  
No new fallback may be introduced after observing Round-7 results.

### Original full_loc singleton behavior (C1 audit)

For reference: the C1 `full_loc` selector did **not** apply the singleton correction.
- Source: `c1_gate_f_run.py` line 202: `pos_mean = fp_topo.groupby("pos_key")["FA_2024"].mean()`
- For a singleton group, `pos_mean` = the singleton's own FA_2024.
- Tie-break: **hostname lexicographic** — `sorted(available, key=lambda n: (LOC_FA_dict.get(n, 0.0), n))`  
  (not BLAKE2b hash)

This is the accurate description of C1 full_loc for manuscript comparison text.
`position_group_hash` differs in two ways: (1) singleton correction, (2) BLAKE2b tie-break.

---

## Correction 3 — Analysis Plan

### Removed
- Wilcoxon signed-rank tests (removed from c7_analysis.py)
- Holm-Bonferroni correction (removed)

This analysis is post-exposure corrective. Creating a new confirmatory testing
family would misrepresent the epistemological status of Round 7.

### Canonical-beta (beta=1.11416358) comparison set

**New structural comparisons (primary Round-7 evidence):**
1. `FP_vs_PositionGroupHash` — full_fp vs position_group_hash
2. `PositionGroupHash_vs_Random` — position_group_hash vs full_random

**Reproductions from accepted C2 (labeled as such; not new evidence):**
3. `FP_vs_Random` — full_fp vs full_random  
4. `FP_vs_WithinCab` — full_fp vs fp_withincab_placebo

### Metrics reported per comparison

- n_A / n_I / n_B (scenario verdicts by sign of delta_lo)
- Median delta_lo (pp)
- Median delta_hi (pp)   [delta_hi = C_upper(A) − C_lower(B)]
- Paired bootstrap 95% CI, 5,000 draws, seed 9999, percentile method (for delta_lo)
- Per-policy: median C_lower_pct, IQR (Q1–Q3); median C_upper_pct, IQR
- Left-boundary count (scenario where C_lower_pct = 0, status = left_boundary)
- Right-censor count
- First-binding constraint distribution (B_ratio / S_ratio / B_cab_ratio counts)

**No confirmatory p-value is reported.** If a sign test appears anywhere it
must be labeled "exploratory — not used for claims."

### Beta=0.960 sensitivity comparison set

All four comparisons above (FP_vs_PositionGroupHash, PositionGroupHash_vs_Random,
FP_vs_Random, FP_vs_WithinCab), same descriptive framework, no p-values.

---

## Correction 4 — Strengthened Equivalence Gate

`c7_equivalence_gate.py` previously checked only `C_lower_pct` and `C_upper_pct`.

The gate now checks the complete scientific record for `full_fp`, `full_random`,
`fp_withincab_placebo` at every lambda row and at the crossing level:

**Per lambda row (tolerance ≤1e-9 for floats, exact for ints/strings):**
- `lambda_val`, `capacity_unlock_pct`, `B_primary_h`, `S_primary_Cdoth`
- `B_secondary_h`, `B_cab_ratio`, `syn_node_hours`
- `n_syn_admit`, `n_drop_cap`, `n_drop_physical`, `n_drop_la`, `n_base_unserved`
- `mean_F_syn`, `cab_span_median`
- All `full_selector_eligible_count_*` and `exposed_selector_eligible_count_*` fields
- All `realized_selector_choice_mult_*` fields
- `B_primary_ratio`, `S_primary_ratio`, `infeasible`, `first_binding`
- Cabinet accounting (if present in both)

**Per scenario:**
- `scen_seed`, `wl_seed` (exact integer)
- `B_ref_s`, `S_ref_s` (≤1e-9)

**Per crossing:**
- `status` (exact), `C_lower_pct` (≤1e-9), `C_upper_pct` (≤1e-9)
- `first_binding_constraint` (exact), `right_censored` (exact)

Any difference in any pre-existing scientific field → STOP.

---

## Correction 5 — Beta Must Be Explicit at Launch

No default beta is allowed at launch time.

- Part C canonical run: `GATE_F_BETA=1.11416358`
- Part D sensitivity:   `GATE_F_BETA=0.960`
- `c7_launch_parallel.py` must abort if GATE_F_BETA is not set.

---

## Correction 6 — SC30 Smoke Before Full Run

After this amendment is committed, run **sc30 only** (`GATE_F_N_FIRST=30 GATE_F_N_DEV=1`)
before the full 25-scenario execution. Pass the strengthened full-field equivalence
gate (max diff ≤1e-9) before proceeding to sc31–sc54. Do not interpret
position_group_hash outcomes from sc30.

---

## Summary of Files Changed

| File | Change |
|------|--------|
| `c7_selectors.py` | Singleton correction; expanded unit tests |
| `c7_analysis.py` | Remove Wilcoxon/Holm; correct comparison set; descriptive framework |
| `c7_equivalence_gate.py` | Full-field equivalence (all lambda row fields) |
| `c7_launch_parallel.py` | Abort if GATE_F_BETA not set |
| `ROUND7_STRUCTURAL_BASELINE_AUDIT.md` | Singleton findings appended |
