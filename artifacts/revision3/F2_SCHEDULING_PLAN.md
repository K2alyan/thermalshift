# F2 Scheduling Plan

## Primary F2 Cabinet Reference

**Reference name:** F2_local_date_support  
**Full label:** corrected_timeweighted_total_p99_local  
**Definition:** Time-weighted P99 of observed reconstructed concurrent cabinet power over America/New_York calendar end-date support blocks, converted to UTC for event integration.

## Rationale for Local-Date Definition

The `date_dir` field in the telemetry parquet has been empirically resolved as the America/New_York local calendar end date. This was established by an exhaustive audit:
- 152,400/152,400 exact matches confirmed in Task-D2 audit commit ab3119c
- The local-date interpretation is the factually correct one

## Relationship to UTC Variant

The original UTC Task-D F2 reference (f2_timeweighted_cabinet_reference.json) is retained as `F2_UTC_support_sensitivity`. It is not overwritten or relabeled. The local-date variant is a metadata-semantics correction, not a performance-driven choice.

## Pre-analysis Governance Statement

The switch from UTC to local-date support is a metadata-semantics correction made BEFORE any F2 scheduling result was observed. It is not selected based on policy performance. The correction was identified, validated, and frozen in Task-D2 before any scheduling experiment with F2 thresholds was run.

## Frozen Evidence Chain

| Artifact | Commit |
|---|---|
| R3-0 equivalence run (27,400/0 checks) | a80d51f |
| Task-D (UTC F2 reference, frozen) | 90dc62f |
| Task-D provenance audit | a83bfa1 |
| Task-D2 (local-date audit, 152,400/152,400 match) | ab3119c |

## Authorized Run Parameters

- Scenarios: sc30-sc54 (25 scenarios)
- Policies: full_fp, full_random
- Ratio: 1.25
- Cabinet reference mode: corrected_timeweighted_total_p99_local
