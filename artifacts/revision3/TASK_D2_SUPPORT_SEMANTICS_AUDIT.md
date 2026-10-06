# Task D2 — Support Semantics Audit

plan_commit=c674209  
date=2026-10-06

## Background

The public Frontier dataset contains 152,400 jobs that ended on selected days (not a complete
scheduler trace). Jobs active during a selected period but ending on an unselected day are
absent from this dataset and cannot be identified from it.

Task D used each unique date_dir value as a full UTC 24-hour support interval
[date_dir 00:00 UTC, date_dir+1 00:00 UTC). There are 135 unique dates, merged into
106 contiguous blocks totaling 3,240 calendar hours of support.

## Audit Objectives

This audit determines:

1. Whether date_dir represents UTC or local (America/New_York) time, and what fraction
   of job end_time values fall within the corresponding calendar day.

2. Whether boundary-crossing jobs (jobs starting before a support block or ending after one)
   were correctly incorporated via clipping, or incorrectly omitted.

3. Whether treating selected dates as full 24-hour UTC support materially affects Q_F2
   relative to alternative support definitions (Eastern local-date, unclipped observed,
   interior-trimmed).

4. Whether alternative support conventions using the same observed jobs materially change F2
   (with "materially" defined by the frozen decision thresholds below).

## Decision Thresholds (Frozen Before Results)

Applied after computing sensitivity variants; not reverse-engineered:

- Support-robust: all variants within median ratio ±2%, no cabinet >5%,
  Spearman >= 0.95, late cabinets qualitatively low.
- Moderately sensitive: median ratio <=5% but some cabinets >5% or Spearman <0.95.
- Materially dependent: median ratio >5%, systematic >10%, or major rank changes.

## Scope

This is sensitivity analysis only. No scheduling policy is run. Frozen Task-D results in
artifacts/revision3/results/ are not modified. All output goes to artifacts/revision3/
and artifacts/revision3/results_d2/.

## Missing-Workload Limitation

Because inclusion is based on jobs ending on selected days, there may be jobs active during
a selected support interval whose end date is unselected and therefore absent from the dataset.
This missing concurrent load is not identifiable from this dataset alone. Therefore no F2
variant may be described as actual cabinet power, complete cabinet power, or measured fleet
cabinet load. The correct description is: observed reconstructed concurrent cabinet power
from the public job sample.
