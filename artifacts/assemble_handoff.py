"""
assemble_handoff.py — one-shot writer handoff package assembler.
Run from repo root: python3 artifacts/assemble_handoff.py
"""
import os, shutil
from pathlib import Path

repo = Path.cwd()   # run from repo root
dst  = repo / 'artifacts' / 'writer_handoff'

if dst.exists():
    shutil.rmtree(dst)
dst.mkdir(parents=True)

missing = []

def cp(src_rel, dst_rel):
    src = repo / src_rel
    d   = dst / dst_rel
    d.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copy2(src, d)
        size = d.stat().st_size
        print(f'  OK  {dst_rel}  ({size:,}b)')
        return True
    else:
        print(f'  MISSING  {src_rel}')
        missing.append(src_rel)
        return False


# -- MANUSCRIPT ------------------------------------------------------
print('\n-- manuscript/ --')
cp('artifacts/manuscript_completion/thermalops_manuscript.tex',
   'manuscript/thermalops_manuscript.tex')
cp('artifacts/manuscript_completion/thermalops.bib',
   'manuscript/thermalops.bib')
cp('artifacts/revision2/SIGMETRICS_OUTLINE.md',
   'manuscript/SIGMETRICS_OUTLINE_revision2.md')
cp('artifacts/revision2/reviewer_response_r2.md',
   'manuscript/reviewer_response_r2.md')

# -- AUDIT & CLAIMS ------------------------------------------------─
print('\n-- audit/ --')
cp('artifacts/manuscript_completion/FINAL_SCIENTIFIC_CLAIMS_AUDIT.md',
   'audit/FINAL_SCIENTIFIC_CLAIMS_AUDIT.md')
cp('artifacts/manuscript_completion/PROVENANCE_MANIFEST.md',
   'audit/PROVENANCE_MANIFEST.md')
cp('artifacts/manuscript_completion/MANUSCRIPT_INTEGRATION_AUDIT.md',
   'audit/MANUSCRIPT_INTEGRATION_AUDIT.md')
cp('artifacts/manuscript_completion/STALE_VALUE_SCAN.md',
   'audit/STALE_VALUE_SCAN.md')
cp('artifacts/revision2/FINAL_NUMERICAL_CLAIM_AUDIT.md',
   'audit/FINAL_NUMERICAL_CLAIM_AUDIT_revision2.md')
cp('artifacts/revision2/FINAL_REVIEWER_COVERAGE_MATRIX.md',
   'audit/FINAL_REVIEWER_COVERAGE_MATRIX.md')
cp('artifacts/revision2/POST_EXPOSURE_SENSITIVITY_RECOVERY.md',
   'audit/POST_EXPOSURE_SENSITIVITY_RECOVERY.md')

# -- FINGERPRINT / PROSPECTIVE VALIDATION --------------------------─
print('\n-- fingerprint/ --')
cp('artifacts/phase1/analysis/phase3a_results.json',
   'fingerprint/phase3a_results.json')
cp('artifacts/revision2/m1_sensitivity_summary.json',
   'fingerprint/m1_sensitivity_summary.json')
cp('artifacts/revision2/prospective_accuracy_by_job_size.json',
   'fingerprint/prospective_accuracy_by_job_size.json')

# Phase1 figures (best effort)
for name in [
    'phase3a_fingerprint_scatter.png',
    'phase3a_prospective.png',
    'phase3a_node_hist.png',
    'phase3a_stability.png',
]:
    cp(f'artifacts/phase1/analysis/{name}', f'fingerprint/figures/{name}')

# -- REPLAY MODEL --------------------------------------------------─
print('\n-- replay_model/ --')
cp('artifacts/revision1/results/power_validation_60job.json',
   'replay_model/power_validation_60job.json')
cp('artifacts/revision1/results/fleet_topology.json',
   'replay_model/fleet_topology.json')
cp('artifacts/revision1/results/cabinet_power_envelopes.json',
   'replay_model/cabinet_power_envelopes.json')
cp('artifacts/revision2/cabinet_timeline_audit.json',
   'replay_model/cabinet_timeline_audit.json')

# -- PROTOCOL / GOVERNANCE ------------------------------------------
print('\n-- protocol/ --')
cp('artifacts/revision1/analysis/GATE_F_DESIGN.md',
   'protocol/GATE_F_DESIGN.md')
cp('artifacts/manuscript_completion/MANUSCRIPT_COMPUTE_ADDENDUM.md',
   'protocol/MANUSCRIPT_COMPUTE_ADDENDUM.md')
cp('artifacts/manuscript_completion/PARALLEL_EXECUTION_AMENDMENT.md',
   'protocol/PARALLEL_EXECUTION_AMENDMENT.md')
cp('artifacts/manuscript_completion/C2_POSTRUN_COMPATIBILITY_NOTE.md',
   'protocol/C2_POSTRUN_COMPATIBILITY_NOTE.md')
cp('artifacts/manuscript_completion/CORRECTED_REFERENCE_SAME_ESTIMAND.md',
   'protocol/CORRECTED_REFERENCE_SAME_ESTIMAND.md')
cp('artifacts/manuscript_completion/corrected_reference_same_estimand.json',
   'protocol/corrected_reference_same_estimand.json')

# -- ORIGINAL EXPERIMENTS (job-contribution reference) --------------
print('\n-- original_experiments/ --')
cp('artifacts/revision2/challenge_analysis.json',
   'original_experiments/challenge_analysis_E2.json')
cp('artifacts/revision2/challenge_preflight.json',
   'original_experiments/challenge_preflight.json')
cp('artifacts/revision2/gate_f_manuscript_tables.json',
   'original_experiments/gate_f_manuscript_tables.json')
cp('artifacts/revision1/results/gate_f_heldout_analysis.json',
   'original_experiments/gate_f_heldout_analysis_E1.json')
cp('artifacts/revision2/r2_vs_r1_equivalence.json',
   'original_experiments/r2_vs_r1_equivalence.json')
cp('artifacts/revision2/loo_beta_results.json',
   'original_experiments/loo_beta_results.json')
cp('artifacts/revision2/sensitivity_loo_beta.json',
   'original_experiments/sensitivity_loo_beta.json')

# -- CORRECTED-REFERENCE ANALYSES ----------------------------------─
print('\n-- corrected_reference/ --')
cp('artifacts/manuscript_completion/C1_CORRECTEDREF_ANALYSIS.md',
   'corrected_reference/C1_CORRECTEDREF_ANALYSIS.md')
cp('artifacts/manuscript_completion/results/c1_correctedref_analysis.json',
   'corrected_reference/c1_correctedref_analysis.json')
cp('artifacts/manuscript_completion/C2_CORRECTEDREF_ANALYSIS.md',
   'corrected_reference/C2_CORRECTEDREF_ANALYSIS.md')
cp('artifacts/manuscript_completion/results/c2_correctedref_analysis.json',
   'corrected_reference/c2_correctedref_analysis.json')
cp('artifacts/manuscript_completion/c2_loo_diagnostic.json',
   'corrected_reference/c2_loo_diagnostic.json')
cp('artifacts/manuscript_completion/C4_CABINET_DIAGNOSTIC.md',
   'corrected_reference/C4_CABINET_DIAGNOSTIC.md')
cp('artifacts/manuscript_completion/results/c4_cabinet_diagnostic.json',
   'corrected_reference/c4_cabinet_diagnostic.json')
cp('artifacts/revision2/late_cab_cohort_diagnostic.json',
   'corrected_reference/late_cab_cohort_diagnostic.json')
cp('artifacts/revision3/F2_PRIMARY_RESULT.md',
   'corrected_reference/F2_PRIMARY_RESULT.md')
cp('artifacts/revision3/TASK_D_PROVENANCE_CORRECTION.md',
   'corrected_reference/TASK_D_PROVENANCE_CORRECTION.md')
f1f2_path = 'artifacts/revision3/results/F1_VS_F2_CABINET_REFERENCE_AUDIT.md'
cp(f1f2_path, 'corrected_reference/F1_VS_F2_CABINET_REFERENCE_AUDIT.md')

# -- RAW MERGED SCENARIO RESULTS ------------------------------------
print('\n-- raw_merged/ --')
cp('artifacts/manuscript_completion/results/gate_f_sc5-29_all.json',
   'raw_merged/gate_f_sc5-29_all_C1.json')
cp('artifacts/manuscript_completion/results/gate_f_sc30-54_1p25_c2manuscript.json',
   'raw_merged/gate_f_sc30-54_1p25_c2manuscript_C2_P95.json')
cp('artifacts/manuscript_completion/results/gate_f_sc30-54_1p25_t61p875_c3canonical.json',
   'raw_merged/gate_f_sc30-54_1p25_t61p875_c3canonical_P90.json')
# Mixed-commit P90 — superseded for provenance; retained for completeness
cp('artifacts/manuscript_completion/results/gate_f_sc30-54_1p25_t61p875_c3manuscript.json',
   'raw_merged/gate_f_sc30-54_1p25_t61p875_c3manuscript_P90_MIXEDCOMMIT.json')
cp('artifacts/manuscript_completion/results/gate_f_sc30-54_1p25_t66p6625_c3manuscript.json',
   'raw_merged/gate_f_sc30-54_1p25_t66p6625_c3manuscript_P99.json')
cp('artifacts/revision2/results/gate_f_sc30-54_all_r2challenge_merged.json',
   'raw_merged/gate_f_sc30-54_all_r2challenge_merged_E2original.json')

# -- THRESHOLD SENSITIVITY ------------------------------------------
print('\n-- threshold_sensitivity/ --')
cp('artifacts/manuscript_completion/C3_THRESHOLD_ANALYSIS.md',
   'threshold_sensitivity/C3_THRESHOLD_ANALYSIS.md')
cp('artifacts/manuscript_completion/results/c3_threshold_analysis.json',
   'threshold_sensitivity/c3_threshold_analysis.json')
cp('artifacts/manuscript_completion/INVALIDATED_C3_P99_CONCURRENT_LAUNCH.md',
   'threshold_sensitivity/INVALIDATED_C3_P99_CONCURRENT_LAUNCH.md')

# -- FIGURES (existing) --------------------------------------------─
print('\n-- figures/existing/ --')
for ext in ['pdf', 'png']:
    for name in [
        'fig_r2_factorial_r125',
        'fig_r2_robustness',
        'fig_r2_fpspread_crossover',
        'fig_r2_policy_matrix',
    ]:
        cp(f'artifacts/revision2/figures/{name}.{ext}',
           f'figures/existing/revision2_{name}.{ext}')

for i in range(1, 6):
    cp(f'artifacts/revision3/figures/D{i}.png',
       f'figures/existing/revision3_D{i}.png')

# -- FIGURE GENERATION SCRIPTS --------------------------------------
print('\n-- figures/scripts/ --')
cp('artifacts/revision2/figures/fig_r2_main.py',
   'figures/scripts/fig_r2_main.py')
cp('artifacts/revision2/figures/fig_r2_robustness.py',
   'figures/scripts/fig_r2_robustness.py')

# -- ANALYSIS SCRIPTS ----------------------------------------------─
print('\n-- analysis_scripts/ --')
for script in [
    'c1_correctedref_analysis.py',
    'c2_correctedref_analysis.py',
    'c3_threshold_analysis.py',
    'c4_cabinet_diagnostic.py',
]:
    cp(f'artifacts/manuscript_completion/analysis/{script}',
       f'analysis_scripts/{script}')
cp('artifacts/manuscript_completion/runners/c3_p90_equivalence_gate.py',
   'analysis_scripts/c3_p90_equivalence_gate.py')

# -- SUMMARY --------------------------------------------------------
print('\n-- Summary --')
file_count = sum(1 for _ in dst.rglob('*') if _.is_file())
total_size = sum(f.stat().st_size for f in dst.rglob('*') if f.is_file())
print(f'Files copied: {file_count}')
print(f'Total size:   {total_size:,} bytes  ({total_size/1024/1024:.1f} MB)')
print(f'Missing:      {len(missing)}')
for m in missing:
    print(f'  {m}')
