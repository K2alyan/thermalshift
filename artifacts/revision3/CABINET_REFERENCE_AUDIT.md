# Cabinet Reference Audit

**Plan ref:** `artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §C`
**Post-exposure label:** produced after sc30–sc54 primary results were observed
**Source:** `artifacts/revision1/results/cabinet_power_envelopes.json`

---

## 1. Legacy Cabinet Envelope Construction

### Formula

```
P_cab_j = (mean_power_j / node_count_j) × n_nodes_in_cabinet_j
```

where:
- `mean_power_j` = mean instantaneous total power reported by the job scheduler (kW)
- `node_count_j` = number of nodes allocated to job j
- `n_nodes_in_cabinet_j` = count of job-j nodes that reside in cabinet j (CORRECT topology)

Applied to all jobs with `mean_power > 0`. The per-cabinet P99 (`per_cabinet_p99_kW_correct`) is the 99th percentile of per-job contributions over all 152,400 jobs.

### Key distinction (verbatim)

> The legacy cabinet envelope (P99 of per-job contributions) is **not** the same statistical object as the P99 of observed concurrent cabinet power over time. These are different estimators. The former is a marginal P99 over individual job contributions, each treated as an independent draw; the latter integrates simultaneous job loads at each moment. The legacy estimator is used in all sc0–sc54 results. Corrected-mode analyses (F2/F3) test sensitivity to the alternative estimator.

---

## 2. Per-Cabinet P99 Values

Source: `cabinet_power_envelopes.json["per_cabinet_p99_kW_correct"]`  
n_jobs_used: 152,400

### Fleet summary

| Statistic | Value (kW) |
|---|---|
| Fleet median P99 | 92.487 |
| Fleet min P99 | 68.741 |
| Fleet max P99 | 95.978 |

### Late-commissioned cabinets

| Cabinet | P99 (kW) | Notes |
|---|---|---|
| 2600 | 71.171 | First appeared 2024-11-22; coolest of the three |
| 2601 | 74.009 | First appeared 2024-07-18 |
| 2602 | 68.741 | First appeared 2024-07-18; lowest P99 in fleet |

Late cabinets have substantially lower P99 (68–74 kW vs fleet median 92 kW), computed from their active operational period. These tighter envelopes impose more conservative power constraints on those cabinets in the simulation. The FP selector preferentially picks late cabinets because their FA_2024 means are the lowest in the fleet (−1.24 to −2.22 vs fleet mean −0.037).

---

## 3. E1 Cabinet-Scale Behavior

E1 (`analyze_sensitivity_e1.py`) multiplies each cabinet's P99 by `CAB_SCALE ∈ {0.90, 0.95, 1.00, 1.05, 1.10}`.

| CAB_SCALE | Effective P99 multiplier | B_cab denominator change | Interpretation |
|---|---|---|---|
| 0.90 | ×0.90 | −10% | Tighter cabinet budget |
| 0.95 | ×0.95 | −5% | Tighter |
| 1.00 | ×1.00 | unchanged | Primary (baseline) |
| 1.05 | ×1.05 | +5% | More permissive |
| 1.10 | ×1.10 | +10% | Most permissive |

**E1 is a cabinet-reference-scale sensitivity** — it tests uniform mis-estimation of the cabinet P99 ceiling. It is **not** a fixed-budget test (the absolute budget changes with scale). It is **not** T_thr sensitivity (T_thr controls which node-hours count as thermal exceedances; scale controls the cabinet power ceiling).

---

## 4. Replay Cabinet Power Formula

The simulator assigns synthetic jobs using the same uniform node-power approximation:

```
P_cab_replay_j = (mean_power_j / node_count_j) × k_synthetic_j
```

where `k_synthetic_j` is the number of synthetic nodes assigned to cabinet j for job j. The cabinet constraint triggers when this exceeds the P99 ceiling, adjusted by `CAB_SCALE`.

**This exposure is not the same as concurrent observed cabinet power.** Multiple simultaneous replay jobs contribute independently; their individual contributions are checked against the ceiling but are not summed for the cabinet at each moment. This is a consequence of the discrete-event simulation structure and is an additional distinction from the F2/F3 concurrent-power estimators.

---

## 5. Sources

- `artifacts/revision1/results/cabinet_power_envelopes.json`
- `artifacts/revision2/cabinet_timeline_audit.json` (late-cabinet commissioning dates)
- `artifacts/revision2/r2_gate_f_run.py` (lines referencing `cab_p99_W` and `CAB_SCALE`)
- `artifacts/revision2/analyze_sensitivity_e1.py` (E1 scale factor application)
- `artifacts/revision3/THIRD_REVIEW_ANALYSIS_PLAN.md §C, §F, §J`
