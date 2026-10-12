#!/usr/bin/env bash
# c1_launch.sh — Hardened launcher for c1_gate_f_run.py
#
# Refuses to run unless GATE_F_N_FIRST and GATE_F_N_DEV are supplied explicitly.
# This prevents the sc0-4 dev-scenario default from being silently selected on
# production invocations (root cause of the 2026-10-07 invalid launch).
#
# Usage:
#   THERMALSHIFT_DATA_DIR=<path> \
#   GATE_F_N_FIRST=5 GATE_F_N_DEV=25 \
#   bash artifacts/manuscript_completion/runners/c1_launch.sh
#
# For production C1 (sc5-29, all 7 ratios):
#   GATE_F_N_FIRST=5 GATE_F_N_DEV=25
#
# For a single-scenario smoke at sc5:
#   GATE_F_N_FIRST=5 GATE_F_N_DEV=1 GATE_F_RATIOS_ONLY="1.25"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RUNNER="$SCRIPT_DIR/c1_gate_f_run.py"

EXPECTED_SHA="7cb51ebcf541d9c04b932ef879ce5095d34195452ef88151418d01ce844b41ba"

# ── 1. Require explicit scenario range ────────────────────────────────────────
if [[ -z "${GATE_F_N_FIRST:-}" ]]; then
    echo "ERROR: GATE_F_N_FIRST is not set." >&2
    echo "  Set it explicitly. Production C1: GATE_F_N_FIRST=5" >&2
    echo "  Omitting this variable causes the runner to default to sc0-4 (dev scenarios)." >&2
    exit 1
fi

if [[ -z "${GATE_F_N_DEV:-}" ]]; then
    echo "ERROR: GATE_F_N_DEV is not set." >&2
    echo "  Set it explicitly. Production C1: GATE_F_N_DEV=25" >&2
    echo "  Omitting this variable causes the runner to default to N_DEV=5." >&2
    exit 1
fi

# ── 2. Require THERMALSHIFT_DATA_DIR ─────────────────────────────────────────
if [[ -z "${THERMALSHIFT_DATA_DIR:-}" ]]; then
    echo "ERROR: THERMALSHIFT_DATA_DIR is not set." >&2
    exit 1
fi
if [[ ! -f "${THERMALSHIFT_DATA_DIR}/frontier-completed-job-info.parquet" ]]; then
    echo "ERROR: frontier-completed-job-info.parquet not found in THERMALSHIFT_DATA_DIR." >&2
    echo "  Path: ${THERMALSHIFT_DATA_DIR}" >&2
    exit 1
fi

# ── 3. Verify runner SHA ──────────────────────────────────────────────────────
if command -v sha256sum &>/dev/null; then
    ACTUAL_SHA=$(sha256sum "$RUNNER" | awk '{print $1}')
elif command -v shasum &>/dev/null; then
    ACTUAL_SHA=$(shasum -a 256 "$RUNNER" | awk '{print $1}')
else
    echo "WARNING: Cannot verify runner SHA (no sha256sum or shasum found)." >&2
    ACTUAL_SHA="unknown"
fi

if [[ "$ACTUAL_SHA" != "$EXPECTED_SHA" && "$ACTUAL_SHA" != "unknown" ]]; then
    echo "ERROR: c1_gate_f_run.py SHA256 mismatch." >&2
    echo "  Expected: $EXPECTED_SHA" >&2
    echo "  Actual:   $ACTUAL_SHA" >&2
    echo "  Runner has been modified. Verify before running." >&2
    exit 1
fi

# ── 4. Check git state ────────────────────────────────────────────────────────
cd "$REPO_ROOT"
GIT_HEAD=$(git log --oneline -1 2>/dev/null || echo "unknown")
GIT_DIRTY=$(git status --porcelain --untracked-files=no 2>/dev/null || echo "unknown")
if [[ -n "$GIT_DIRTY" ]]; then
    echo "ERROR: Working tree has uncommitted tracked changes." >&2
    echo "  Commit or stash before running." >&2
    git status --short >&2
    exit 1
fi

# ── 5. Check no output already exists ────────────────────────────────────────
SCEN_END=$(( GATE_F_N_FIRST + GATE_F_N_DEV - 1 ))
RATIO_TAG="${GATE_F_RATIOS_ONLY:-}"
RATIO_TAG_SAFE=$(echo "$RATIO_TAG" | tr ',' '_' | tr '.' 'p' | sed 's/unrestricted/unr/g')
[[ -z "$RATIO_TAG_SAFE" ]] && RATIO_TAG_SAFE="all"
OUT_FILE="$REPO_ROOT/artifacts/manuscript_completion/results/gate_f_sc${GATE_F_N_FIRST}-${SCEN_END}_${RATIO_TAG_SAFE}.json"

if [[ -f "$OUT_FILE" ]]; then
    echo "ERROR: Production output already exists at:" >&2
    echo "  $OUT_FILE" >&2
    echo "  Move or rename it before rerunning." >&2
    exit 1
fi

CKPT_FILE="${OUT_FILE%.json}_checkpoint.json"
if [[ -f "$CKPT_FILE" ]]; then
    echo "WARNING: A checkpoint file exists: $CKPT_FILE" >&2
    echo "  The c1 runner will ABORT if it finds a checkpoint (checkpoint REUSE is prohibited)." >&2
    echo "  Delete the checkpoint before launching." >&2
    exit 1
fi

# ── 6. Pre-run header ─────────────────────────────────────────────────────────
echo "================================================================"
echo "C1 PRODUCTION LAUNCH"
echo "================================================================"
echo "  git HEAD:              $GIT_HEAD"
echo "  Runner SHA256:         $ACTUAL_SHA"
echo "  GATE_F_N_FIRST:        $GATE_F_N_FIRST"
echo "  GATE_F_N_DEV:          $GATE_F_N_DEV"
echo "  Scenario range:        sc${GATE_F_N_FIRST}–sc${SCEN_END}"
echo "  GATE_F_RATIOS_ONLY:    ${GATE_F_RATIOS_ONLY:-(all 7)}"
echo "  THERMALSHIFT_DATA_DIR: $THERMALSHIFT_DATA_DIR"
echo "  Expected output:       $OUT_FILE"
echo "  Launch time:           $(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo "================================================================"

# ── 7. Execute ────────────────────────────────────────────────────────────────
exec python3 "$RUNNER"
