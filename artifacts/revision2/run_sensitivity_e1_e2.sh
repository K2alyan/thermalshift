#!/usr/bin/env bash
# Phase E1 and E2 sensitivity runs.
# Run AFTER baseline equivalence check passes.
# Each run: sc30-54, r=1.25, FP+Random only.
#
# E1: 4 non-baseline scale factors (1.00 comes from baseline run)
# E2: 5 non-primary beta values (primary comes from baseline run)
#
# Expected output files in artifacts/revision2/results/:
#   gate_f_sc30-54_1p25_r2sensitivity_sc{scale}_bprimary.json  (E1)
#   gate_f_sc30-54_1p25_r2sensitivity_sc1p00_b{beta}.json      (E2)
#
# Each run takes ~2 hours. Run in separate terminals or sequentially.

set -euo pipefail

LOG_DIR="artifacts/revision2/results"
RUNNER="artifacts/revision2/r2_sensitivity_run.py"
BASE_ENV="THERMALSHIFT_DATA_DIR=C:/Users/kalya/Downloads GATE_F_RATIOS_ONLY=1.25 GATE_F_RESTRICT_POLICIES=full_random,full_fp GATE_F_N_DEV=25 GATE_F_N_FIRST=30"

echo "=== Phase E1: Cabinet-Reference Sensitivity ==="
echo "Scale factors: 0.90, 0.95, 1.05, 1.10 (1.00 = baseline)"
echo

# E1: scale=0.90
echo "--- E1 scale=0.90 ---"
THERMALSHIFT_DATA_DIR="C:/Users/kalya/Downloads" \
  GATE_F_RATIOS_ONLY="1.25" \
  GATE_F_RESTRICT_POLICIES="full_random,full_fp" \
  GATE_F_N_DEV=25 GATE_F_N_FIRST=30 \
  GATE_F_CAB_SCALE="0.90" \
  python "$RUNNER" > "$LOG_DIR/sensitivity_e1_sc0p90.log" 2>&1
echo "E1 scale=0.90 done"

# E1: scale=0.95
echo "--- E1 scale=0.95 ---"
THERMALSHIFT_DATA_DIR="C:/Users/kalya/Downloads" \
  GATE_F_RATIOS_ONLY="1.25" \
  GATE_F_RESTRICT_POLICIES="full_random,full_fp" \
  GATE_F_N_DEV=25 GATE_F_N_FIRST=30 \
  GATE_F_CAB_SCALE="0.95" \
  python "$RUNNER" > "$LOG_DIR/sensitivity_e1_sc0p95.log" 2>&1
echo "E1 scale=0.95 done"

# E1: scale=1.05
echo "--- E1 scale=1.05 ---"
THERMALSHIFT_DATA_DIR="C:/Users/kalya/Downloads" \
  GATE_F_RATIOS_ONLY="1.25" \
  GATE_F_RESTRICT_POLICIES="full_random,full_fp" \
  GATE_F_N_DEV=25 GATE_F_N_FIRST=30 \
  GATE_F_CAB_SCALE="1.05" \
  python "$RUNNER" > "$LOG_DIR/sensitivity_e1_sc1p05.log" 2>&1
echo "E1 scale=1.05 done"

# E1: scale=1.10
echo "--- E1 scale=1.10 ---"
THERMALSHIFT_DATA_DIR="C:/Users/kalya/Downloads" \
  GATE_F_RATIOS_ONLY="1.25" \
  GATE_F_RESTRICT_POLICIES="full_random,full_fp" \
  GATE_F_N_DEV=25 GATE_F_N_FIRST=30 \
  GATE_F_CAB_SCALE="1.10" \
  python "$RUNNER" > "$LOG_DIR/sensitivity_e1_sc1p10.log" 2>&1
echo "E1 scale=1.10 done"

echo
echo "=== Phase E2: Beta Sensitivity ==="
echo "Betas: FROZEN, PROSPECTIVE, JACKKNIFE, CF_P5, CF_P95 (primary = baseline)"
echo

# E2: BETA_F_FROZEN = 1.12484352
echo "--- E2 beta=BETA_F_FROZEN (1.12484352) ---"
THERMALSHIFT_DATA_DIR="C:/Users/kalya/Downloads" \
  GATE_F_RATIOS_ONLY="1.25" \
  GATE_F_RESTRICT_POLICIES="full_random,full_fp" \
  GATE_F_N_DEV=25 GATE_F_N_FIRST=30 \
  GATE_F_SENSITIVITY_BETA="1.12484352" \
  python "$RUNNER" > "$LOG_DIR/sensitivity_e2_b1p12484352.log" 2>&1
echo "E2 BETA_F_FROZEN done"

# E2: BETA_F_PROSPECTIVE = 0.96
echo "--- E2 beta=BETA_F_PROSPECTIVE (0.96) ---"
THERMALSHIFT_DATA_DIR="C:/Users/kalya/Downloads" \
  GATE_F_RATIOS_ONLY="1.25" \
  GATE_F_RESTRICT_POLICIES="full_random,full_fp" \
  GATE_F_N_DEV=25 GATE_F_N_FIRST=30 \
  GATE_F_SENSITIVITY_BETA="0.96" \
  python "$RUNNER" > "$LOG_DIR/sensitivity_e2_b0p96.log" 2>&1
echo "E2 BETA_F_PROSPECTIVE done"

# E2: BETA_F_JACKKNIFE_MEAN = 1.08293397
echo "--- E2 beta=BETA_F_JACKKNIFE_MEAN (1.08293397) ---"
THERMALSHIFT_DATA_DIR="C:/Users/kalya/Downloads" \
  GATE_F_RATIOS_ONLY="1.25" \
  GATE_F_RESTRICT_POLICIES="full_random,full_fp" \
  GATE_F_N_DEV=25 GATE_F_N_FIRST=30 \
  GATE_F_SENSITIVITY_BETA="1.08293397" \
  python "$RUNNER" > "$LOG_DIR/sensitivity_e2_b1p08293397.log" 2>&1
echo "E2 BETA_F_JACKKNIFE_MEAN done"

# E2: BETA_F_CF_P5 = 1.06587054
echo "--- E2 beta=BETA_F_CF_P5 (1.06587054) ---"
THERMALSHIFT_DATA_DIR="C:/Users/kalya/Downloads" \
  GATE_F_RATIOS_ONLY="1.25" \
  GATE_F_RESTRICT_POLICIES="full_random,full_fp" \
  GATE_F_N_DEV=25 GATE_F_N_FIRST=30 \
  GATE_F_SENSITIVITY_BETA="1.06587054" \
  python "$RUNNER" > "$LOG_DIR/sensitivity_e2_b1p06587054.log" 2>&1
echo "E2 BETA_F_CF_P5 done"

# E2: BETA_F_CF_P95 = 1.16910447
echo "--- E2 beta=BETA_F_CF_P95 (1.16910447) ---"
THERMALSHIFT_DATA_DIR="C:/Users/kalya/Downloads" \
  GATE_F_RATIOS_ONLY="1.25" \
  GATE_F_RESTRICT_POLICIES="full_random,full_fp" \
  GATE_F_N_DEV=25 GATE_F_N_FIRST=30 \
  GATE_F_SENSITIVITY_BETA="1.16910447" \
  python "$RUNNER" > "$LOG_DIR/sensitivity_e2_b1p16910447.log" 2>&1
echo "E2 BETA_F_CF_P95 done"

echo
echo "=== All E1/E2 sensitivity runs complete ==="
echo "Next: run analyze_sensitivity_e1.py and analyze_sensitivity_e2.py"
echo "Then: run generate_final_output_audit.py"
