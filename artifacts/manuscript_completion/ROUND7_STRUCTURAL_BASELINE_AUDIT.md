# Round 7 Structural Baseline Audit

**Date:** 2026-10-09  
**Branch:** revision1/major-revision-analyses  
**Purpose:** Audit the frozen position_loo implementation before designing the replacement.  
**Files inspected:** `artifacts/manuscript_completion/runners/c2_gate_f_run.py`,
`artifacts/manuscript_completion/runners/c2_selectors.py`,
`artifacts/manuscript_completion/runners/c1_gate_f_run.py`

---

## 1. C1 full_loc Implementation (Experiment-1 Reference)

### Score computation

File: `c1_gate_f_run.py` lines 195–208.

```python
fp_topo["pos_key"] = (fp_topo["chassis"].astype(str) + "_" +
                      fp_topo["slot"].astype(str)    + "_" +
                      fp_topo["board"].astype(str)   + "_" +
                      fp_topo["node_pos"].astype(str))
fp_topo["FA_2024"] = fp_topo["hostname"].map(FA_dict)
pos_mean = fp_topo.groupby("pos_key")["FA_2024"].mean().rename("FA_loc")
fp_topo  = fp_topo.join(pos_mean, on="pos_key")
LOC_FA_dict = dict(zip(fp_topo["hostname"].values, fp_topo["FA_loc"].values))
_glob_mean  = float(np.nanmean(list(LOC_FA_dict.values())))
LOC_FA_dict = {k: (v if not np.isnan(v) else _glob_mean)
               for k, v in LOC_FA_dict.items()}
```

### Group key

`pos_key = chassis + "_" + slot + "_" + board + "_" + node_pos`  
(four-field exact structural position)

### Group-constant property

**YES.** Every node in the same structural group receives exactly the same score.  
`groupby("pos_key")["FA_2024"].mean()` is joined back to the full topology,
so all nodes sharing a `pos_key` receive the same group mean.

### Score formula

Simple unweighted arithmetic mean of FA_2024 across all pre-2025 observations
for nodes sharing the same structural position. No leave-one-out, no self-exclusion.

### Sort direction and selector

File: `c1_gate_f_run.py` lines 518–520.

```python
def select_loc_canonical(available, k):
    s = sorted(available, key=lambda n: (LOC_FA_dict.get(n, 0.0), n))
    return s[:min(k, len(s))]
```

**ASCENDING sort** (lower FA = cooler = preferred). Correct direction for
thermal-aware selection.

### Tie-breaking rule

**Hostname lexicographic ordering.** The sort key is `(LOC_FA_dict.get(n, 0.0), n)`.
Python's `sorted` is stable; within the same group, two nodes with identical
group scores are ordered by hostname string comparison.

### BLAKE2b hash used?

**NO.** No hash at any stage of the LOC selector.

### FA_2024 used for tie-breaking?

**NO.** The LOC score IS the group mean of FA_2024. Nodes within the same group
have the same score. The tie-break is purely hostname-lexicographic.

### NaN handling

Positions with no FA_2024 observations receive the global cohort mean.

---

## 2. C2 position_loo Implementation (Experiment-2, Used in Accepted Run)

### Score computation

File: `c2_gate_f_run.py` function `build_position_loo_fa` lines 263–337.

Four-level fallback hierarchy (all within-chassis):

| Level | Group key | Formula |
|-------|-----------|---------|
| 1 | (chassis, slot, board, node_pos) | `(S_g - F_i) / max(n_g - 1, 1)` |
| 2 | (chassis, slot, board) | same formula, larger group |
| 3 | (chassis, slot) | same formula, larger group |
| 4 | global cohort | `(S_total - F_i) / max(N - 1, 1)` |

Level 1 applies to 1,990/2,000 nodes; Level 3 applies to 3 nodes; Level 4
(global fallback) applies to 7 nodes.

### Group-constant property

**NO.** Within the same Level-1 group, every node receives a different LOO score:
`LOO_i = (S_g - F_i) / (n_g - 1)`, which depends on the individual node's F_i.

### Sort direction and selector

File: `c2_gate_f_run.py` lines 344–348.

```python
def select_position_loo(available, k, loo_fa_dict: dict):
    scored = [(loo_fa_dict.get(n, 0.0), n) for n in available]
    scored.sort(key=lambda x: -x[0])
    return [n for _, n in scored[:k]]
```

**DESCENDING sort** (higher LOO score = preferred). Implicit hostname tie-break
via list ordering (not deterministic under arbitrary Python list ordering).

### Tie-breaking rule

No explicit secondary sort key. The tuple `(score, hostname)` is not constructed.
Tie-breaking among equal LOO scores is determined by the order of `available`
(which is arbitrary) combined with Python sort stability.

### BLAKE2b hash used?

**NO.** `choice_priority` (BLAKE2b) is used only in the Gate F Stage-1 shortlist
(`gate_f_shortlist`), not in the Stage-2 policy selector.

### FA_2024 used for tie-breaking?

**NOT directly.** LOO score IS a function of FA_2024, but within a group,
two nodes will rarely have equal LOO scores (only if their group-mates happen to
have identical FA contributions when the node is removed). So in practice,
FA_2024 implicitly determines within-group ordering via the LOO formula.

---

## 3. Mathematical Selection Artifact in position_loo

The LOO formula `LOO_i = (S_g - F_i) / (n_g - 1)` has two properties that make
it unsuitable as a cross-group scheduling comparator:

### Property 1: Within-group ranking reversal

Within a fixed group, `LOO_i` is a strictly decreasing function of `F_i`.
The cooler node (lower `F_i`) gets a higher LOO score. With **descending** sort,
the cooler node is selected first. Within a single group, this is correct.

### Property 2: Cross-group systematic bias (the artifact)

Consider two groups:

| Group | Nodes | FA values | LOO scores |
|-------|-------|-----------|-----------|
| P_cool | A, B | 1, 2 | LOO_A = 2, LOO_B = 1 |
| P_hot  | C, D | 8, 9 | LOO_C = 9, LOO_D = 8 |

With descending sort across all four nodes: C(9) > D(8) > A(2) > B(1).

**position_loo preferentially selects nodes from hot position groups.**

The LOO score of any node is approximately the mean of its group-mates' FA values.
Nodes in hot groups have high LOO scores (hot group-mates) and are selected first.
Nodes in cool groups have low LOO scores (cool group-mates) and are selected last.

This is the algebraic reversal: the cross-group ranking by LOO score is the
**opposite** of the cross-group ranking by individual FA. The accepted C2 run
with position_loo therefore produces an inflated FP-vs-position_loo separation,
because position_loo acts as a heat-maximizing (not heat-minimizing) policy in
the cross-group dimension.

### Implication for accepted C2 claims

The following accepted C2 result **cannot be interpreted as a fair structural
position comparator**:

| Comparison | n_A/n_I/n_B | Median Δ_lo |
|-----------|-------------|------------|
| FP vs position_loo | 25/0/0 | +13.95 pp |

This comparison is preserved in provenance as an invalid structural-selection
control. **The claim that FP outperforms a fair structural-position policy
requires re-evaluation against the corrected position_group_hash comparator.**

---

## 4. C2 position_loo Status

**PRESERVED** in the committed C2 raw merged file
(`gate_f_sc30-54_1p25_c2manuscript.json`, SHA `b4dbc4bc...`) and in
`c2_correctedref_analysis.json`.

**NOT DELETED.** The artifact is available for full auditability.

**WITHDRAWN as a valid structural-position comparator.** The FP-vs-position_loo
claim is superseded by FP-vs-position_group_hash from the Round 7 structural run.

---

## 5. Frozen position_group_hash Policy Definition

### Group key

Identical to C1 full_loc: `chassis + "_" + slot + "_" + board + "_" + node_pos`

### Score computation

Pre-2025 arithmetic mean of FA_2024 for ALL nodes sharing the same structural
group key. No leave-one-out. No self-exclusion. Every node in the same group
receives exactly the same score.

NaN FA_2024 values replaced with global cohort mean before group mean computation
(same as full_loc / position_template).

### Sort direction

**ASCENDING.** Lower group score = cooler structural position = preferred.
(Same direction as full_loc / full_fp.)

### Tie-breaking rule

Within tied groups (same group score), nodes are ordered by the same event-specific
policy-blind BLAKE2b hash used for the Gate F Stage-1 shortlist:

```python
key    = scenario_seed.to_bytes(8, "big", signed=False)
msg    = event_uid.encode("utf-8") + b"\x00" + hostname.encode("utf-8")
digest = hashlib.blake2b(msg, key=key, digest_size=8).digest()
hash_val = int.from_bytes(digest, "big")
sort_key = (group_score, hash_val)
```

**Hostname NOT used** as secondary sort key (to avoid any deterministic
bias from hostname ordering).

**FA_2024 NOT used** to break ties (the group score already encodes position-level
FA information; individual node FA must not introduce node-specificity).

### Definition does not change after observing results

This definition was fixed before any Round 7 scenario was executed.

---

## 6. Comparison of Position Policies

| Property | full_loc (C1) | position_loo (C2) | position_group_hash (C7) |
|----------|--------------|-------------------|--------------------------|
| Group key | (chassis,slot,board,node_pos) | 4-level fallback | (chassis,slot,board,node_pos) |
| Group-constant score | YES | NO | YES |
| Self-exclusion (LOO) | NO | YES | NO |
| Sort direction | ascending | descending | ascending |
| Tie-break | hostname | implicit | BLAKE2b hash |
| Cross-group bias | none | systematic hot-group bias | none |
| Valid scheduler comparator | YES | NO | YES |

---

## 7. Summary Verdict

- `full_loc` (C1): valid structural comparator; used in Experiment 1.
- `position_loo` (C2): invalid cross-group comparator; WITHDRAWN as structural
  evidence; preserved in provenance.
- `position_group_hash` (C7): valid corrected comparator; same structural
  logic as full_loc, BLAKE2b tie-breaking, no LOO bias.
