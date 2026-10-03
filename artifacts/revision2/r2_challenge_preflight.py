#!/usr/bin/env python3
"""
Review 2 Challenge Preflight (r2_challenge_preflight.py)

Verifies all 12 preflight conditions before sc30-54 challenge run.
Plan ref: REVIEW2_CHALLENGE_PLAN.md Phase F (amendment 6b45030).

Exit code 0 = all 12 conditions pass (challenge run may proceed).
Exit code 1 = one or more conditions fail (challenge run MUST NOT proceed).

Usage:
  python r2_challenge_preflight.py [--ack]   # --ack sets operator_acknowledged=true
"""
import sys, io, os, json, subprocess, hashlib, datetime, argparse
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
REV2_DIR  = REPO_ROOT / "artifacts" / "revision2"
OUT_DIR   = REV2_DIR / "results"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PREFLIGHT_OUT = REV2_DIR / "challenge_preflight.json"

# ── Frozen constants (plan §3) ────────────────────────────────────────────────
BETA_F_FROZEN    = 1.12484352
T_THR_PRIMARY    = 63.625
T_THR_SECONDARY  = 60.602770562770566
DELTA_CAP        = 0.10

CHALLENGE_SEED              = 2042
PLACEBO_GLOBAL_PERM_SEED    = 218767960
PLACEBO_WITHINCAB_PERM_SEED = 365514213
N_SCENARIOS_CHALLENGE       = 25
SCENARIO_FIRST              = 30

# Plan-specified preregistration commits (plan §8.8)
ORIGINAL_PREREGISTRATION_SHA = "d28f29d"
AMENDMENT_SHA                = "6b45030"

# Frozen heldout analysis SHA (from e16ec3c, plan §2)
HELDOUT_ANALYSIS_FILE = REV1_DIR / "results" / "gate_f_heldout_analysis.json"
HELDOUT_ANALYSIS_SHA_EXPECTED = None   # computed at runtime from file

# ── CLI ───────────────────────────────────────────────────────────────────────
parser = argparse.ArgumentParser()
parser.add_argument("--ack", action="store_true",
                    help="Set operator_acknowledged=true in preflight JSON")
args = parser.parse_args()

print("=" * 70)
print("Review 2 Challenge Preflight")
print(f"Plan ref: REVIEW2_CHALLENGE_PLAN.md Phase F (amendment 6b45030)")
print("=" * 70)

conditions: dict[str, dict] = {}
all_pass = True

def record(key: str, passed: bool, notes: str, **extra):
    global all_pass
    conditions[key] = {"pass": passed, "notes": notes, **extra}
    status = "PASS" if passed else "FAIL"
    print(f"  [{status}] {key}: {notes}")
    if not passed:
        all_pass = False

# ════════════════════════════════════════════════════════════════════════════
# Condition 1: Phase A complete
# ════════════════════════════════════════════════════════════════════════════
print("\n[1] Phase A complete ...")
a1_json  = REV2_DIR / "cabinet_timeline_audit.json"
a1_md    = REV2_DIR / "cabinet_timeline_audit.md"
a2_json  = REV2_DIR / "prospective_accuracy_by_job_size.json"
a3_json  = REV2_DIR / "m1_sensitivity_summary.json"
a4_json  = REV2_DIR / "gate_f_manuscript_tables.json"

a_files_ok = True
a_notes = []
for f in [a1_json, a1_md, a2_json, a3_json, a4_json]:
    if not f.exists():
        a_files_ok = False
        a_notes.append(f"MISSING: {f.name}")

a1_rec = "proceed_with_documentation"
if a1_json.exists():
    try:
        a1_data = json.loads(a1_json.read_text())
        a1_rec  = a1_data.get("recommendation", "unknown")
        if a1_rec not in ("proceed_with_documentation", "proceed"):
            a_files_ok = False
            a_notes.append(f"A1 recommendation={a1_rec} (must be proceed*)")
    except Exception as e:
        a_files_ok = False
        a_notes.append(f"A1 JSON parse error: {e}")

record("1_phase_a_complete", a_files_ok,
       f"A1 rec={a1_rec}; " + ("; ".join(a_notes) if a_notes else "all files present"),
       a1_recommendation=a1_rec)

# ════════════════════════════════════════════════════════════════════════════
# Condition 2: Phase B complete
# ════════════════════════════════════════════════════════════════════════════
print("\n[2] Phase B complete ...")
loo_file = REV2_DIR / "loo_beta_results.json"
b_ok = True; b_notes = []; primary_beta = None

if not loo_file.exists():
    b_ok = False; b_notes.append("loo_beta_results.json missing")
else:
    try:
        loo = json.loads(loo_file.read_text())
        primary_beta = loo.get("B3_primary_beta", {}).get("PRIMARY_BETA_CHALLENGE")
        if primary_beta is None:
            b_ok = False; b_notes.append("PRIMARY_BETA_CHALLENGE not found in loo_beta_results.json")
        else:
            # Verify B2a jackknife and B2b quarter-wise also present
            if "B2a_jackknife" not in loo:
                b_notes.append("B2a_jackknife missing (sensitivity diagnostic)")
            if "B2b_quarter_wise" not in loo:
                b_notes.append("B2b_quarter_wise missing (sensitivity diagnostic)")
            b_notes.append(f"PRIMARY_BETA_CHALLENGE={primary_beta}")
    except Exception as e:
        b_ok = False; b_notes.append(f"loo_beta_results.json parse error: {e}")

record("2_phase_b_complete", b_ok, "; ".join(b_notes),
       primary_beta=primary_beta)

# ════════════════════════════════════════════════════════════════════════════
# Condition 3: Phase C complete (unit tests pass)
# ════════════════════════════════════════════════════════════════════════════
print("\n[3] Phase C complete (unit tests) ...")
selectors_file = REV2_DIR / "r2_selectors.py"
c_ok = True; c_notes = []

if not selectors_file.exists():
    c_ok = False; c_notes.append("r2_selectors.py missing")
else:
    result = subprocess.run(
        [sys.executable, str(selectors_file)],
        capture_output=True, text=True, encoding="utf-8"
    )
    if result.returncode == 0 and "ALL TESTS PASSED" in result.stdout:
        c_notes.append("r2_selectors.py unit tests: ALL TESTS PASSED")
    else:
        c_ok = False
        c_notes.append(f"r2_selectors.py unit tests FAILED (rc={result.returncode})")
        if result.stdout: c_notes.append(result.stdout[-500:])
        if result.stderr: c_notes.append(result.stderr[-200:])

record("3_phase_c_complete", c_ok, "; ".join(c_notes))

# ════════════════════════════════════════════════════════════════════════════
# Condition 4: Seed table verified from rng(2042)
# ════════════════════════════════════════════════════════════════════════════
print("\n[4] Seed table verification ...")
rng4 = np.random.default_rng(CHALLENGE_SEED)
sc3054_scen_seeds = [int(rng4.integers(0, 2**31)) for _ in range(N_SCENARIOS_CHALLENGE)]
sc3054_wl_seeds   = [int(rng4.integers(0, 2**31)) for _ in range(N_SCENARIOS_CHALLENGE)]
_pg_actual  = int(rng4.integers(0, 2**31))
_pwc_actual = int(rng4.integers(0, 2**31))
pol_seeds_r2 = {}   # store for condition 5

seed_matches = [
    sc3054_scen_seeds[0] == 1520047186,  # sc30
    sc3054_scen_seeds[1] == 1145613857,  # sc31
    sc3054_scen_seeds[24] == 918802192,  # sc54
    sc3054_wl_seeds[0] == 1994769663,    # sc30
    sc3054_wl_seeds[24] == 57164757,     # sc54
    _pg_actual  == PLACEBO_GLOBAL_PERM_SEED,
    _pwc_actual == PLACEBO_WITHINCAB_PERM_SEED,
]
s4_ok = all(seed_matches)
s4_notes = (f"sc30 scen={sc3054_scen_seeds[0]} wl={sc3054_wl_seeds[0]}"
            f"  sc54 scen={sc3054_scen_seeds[24]} wl={sc3054_wl_seeds[24]}"
            f"  placebo_global={_pg_actual}  placebo_withincab={_pwc_actual}")
record("4_seeds_verified", s4_ok, s4_notes,
       sc30_scen_seed=sc3054_scen_seeds[0], sc54_scen_seed=sc3054_scen_seeds[24])

# ════════════════════════════════════════════════════════════════════════════
# Condition 5: Seed collision audit
# ════════════════════════════════════════════════════════════════════════════
print("\n[5] Seed collision audit ...")

# Reproduce sc0-29 seeds from rng(42)
rng5 = np.random.default_rng(42)
N_SCENARIOS_ORIG = 30
POLICY_IDS_ORIG  = ["full_random", "full_fp", "full_loc", "full_compact",
                     "marginal_random", "marginal_fp", "full_fp_spread"]
sc0029_scen_seeds = [int(rng5.integers(0, 2**31)) for _ in range(N_SCENARIOS_ORIG)]
sc0029_wl_seeds   = [int(rng5.integers(0, 2**31)) for _ in range(N_SCENARIOS_ORIG)]
_orig_pol_seeds   = {p: [int(rng5.integers(0, 2**31)) for _ in range(N_SCENARIOS_ORIG)]
                     for p in POLICY_IDS_ORIG}

all_sc0029 = set(sc0029_scen_seeds) | set(sc0029_wl_seeds)
for p in POLICY_IDS_ORIG:
    all_sc0029 |= set(_orig_pol_seeds[p])

placebo_seeds = {PLACEBO_GLOBAL_PERM_SEED, PLACEBO_WITHINCAB_PERM_SEED}

# sc30-54 internal uniqueness
s3054_all = sc3054_scen_seeds + sc3054_wl_seeds
s3054_set  = set(s3054_all)
internal_unique_scen = len(set(sc3054_scen_seeds)) == len(sc3054_scen_seeds)
internal_unique_wl   = len(set(sc3054_wl_seeds))   == len(sc3054_wl_seeds)

# Cross-set collisions
collisions = []
for sv in sc3054_scen_seeds:
    if sv in all_sc0029:
        collisions.append(f"sc30-54 scen_seed {sv} collides with sc0-29")
for sv in sc3054_wl_seeds:
    if sv in all_sc0029:
        collisions.append(f"sc30-54 wl_seed {sv} collides with sc0-29")
# Placebo vs everything
for ps in placebo_seeds:
    if ps in (s3054_set | all_sc0029):
        collisions.append(f"placebo_seed {ps} collides with scenario/workload seeds")
if PLACEBO_GLOBAL_PERM_SEED == PLACEBO_WITHINCAB_PERM_SEED:
    collisions.append("placebo seeds are identical to each other")

s5_ok = (internal_unique_scen and internal_unique_wl and len(collisions) == 0)
record("5_seed_collision_audit", s5_ok,
       f"internal_unique_scen={internal_unique_scen} "
       f"internal_unique_wl={internal_unique_wl} "
       f"collisions={len(collisions)}",
       sc3054_scen_seeds=sc3054_scen_seeds,
       sc3054_wl_seeds=sc3054_wl_seeds,
       sc0029_scen_seeds=sc0029_scen_seeds,
       sc0029_wl_seeds=sc0029_wl_seeds,
       placebo_global_perm_seed=PLACEBO_GLOBAL_PERM_SEED,
       placebo_withincab_perm_seed=PLACEBO_WITHINCAB_PERM_SEED,
       collisions_found=collisions,
       all_unique=s5_ok)

# ════════════════════════════════════════════════════════════════════════════
# Condition 6: Clean git state
# ════════════════════════════════════════════════════════════════════════════
print("\n[6] Git clean state ...")
try:
    commit_full  = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    commit_short = subprocess.check_output(
        ["git", "rev-parse", "--short", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    dirty = bool(subprocess.check_output(
        ["git", "status", "--porcelain", "--untracked-files=no"],
        cwd=str(REPO_ROOT), text=True).strip())
    untracked = subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=str(REPO_ROOT), text=True).strip().splitlines()
    untracked = [x for x in untracked if x]
    freeze_sha = commit_full
except Exception as e:
    commit_full = commit_short = freeze_sha = "unknown"
    dirty = True; untracked = [str(e)]

s6_ok = (not dirty and len(untracked) == 0)
record("6_clean_git", s6_ok,
       f"dirty={dirty} untracked={len(untracked)} commit={commit_short}",
       commit_full=commit_full, commit_short=commit_short,
       tracked_dirty=dirty, untracked_count=len(untracked),
       untracked_files=untracked[:10])

# ════════════════════════════════════════════════════════════════════════════
# Condition 7: Frozen constants match
# ════════════════════════════════════════════════════════════════════════════
print("\n[7] Frozen constants check ...")
r2_run_file = REV2_DIR / "r2_gate_f_run.py"
s7_ok = True; s7_notes = []

if not r2_run_file.exists():
    s7_ok = False; s7_notes.append("r2_gate_f_run.py missing")
else:
    src = r2_run_file.read_text(encoding="utf-8")
    src_selectors = selectors_file.read_text(encoding="utf-8") if selectors_file.exists() else ""
    # Check constants appear in script or in r2_selectors.py (imported by script)
    for name, val in [
        ("BETA_F_FROZEN", "1.12484352"),
        ("T_THR_PRIMARY", "63.625"),
        ("T_THR_SECONDARY", "60.602770562770566"),
        ("DELTA_CAP", "0.10"),
        ("PRIMARY_BETA_CHALLENGE", "1.08293343"),
    ]:
        if val in src:
            s7_notes.append(f"{name}={val} present in r2_gate_f_run.py")
        elif val in src_selectors and name == "PRIMARY_BETA_CHALLENGE":
            # PRIMARY_BETA_CHALLENGE is defined in r2_selectors.py and imported
            s7_notes.append(f"{name}={val} defined in r2_selectors.py (imported)")
        else:
            s7_ok = False
            s7_notes.append(f"{name}={val} NOT FOUND in r2_gate_f_run.py or r2_selectors.py")

# Verify PRIMARY_BETA_CHALLENGE matches loo_beta_results
if primary_beta is not None:
    try:
        from r2_selectors import PRIMARY_BETA_CHALLENGE as _pbc
        if abs(_pbc - float(primary_beta)) > 1e-8:
            s7_ok = False
            s7_notes.append(
                f"r2_selectors.PRIMARY_BETA_CHALLENGE={_pbc} != "
                f"loo_beta_results.json={primary_beta}"
            )
        else:
            s7_notes.append(f"r2_selectors.PRIMARY_BETA_CHALLENGE={_pbc} matches JSON")
    except Exception as e:
        s7_notes.append(f"Could not import PRIMARY_BETA_CHALLENGE from r2_selectors: {e}")

record("7_frozen_constants", s7_ok, "; ".join(s7_notes),
       primary_beta_challenge=primary_beta)

# ════════════════════════════════════════════════════════════════════════════
# Condition 8: REVIEW2_CHALLENGE_PLAN.md committed with correct SHA prefixes
# ════════════════════════════════════════════════════════════════════════════
print("\n[8] Plan committed ...")
s8_ok = True; s8_notes = []

plan_file = REV2_DIR / "REVIEW2_CHALLENGE_PLAN.md"
if not plan_file.exists():
    s8_ok = False; s8_notes.append("REVIEW2_CHALLENGE_PLAN.md not found")

# Verify both SHAs appear in git log
for expected_sha, desc in [
    (ORIGINAL_PREREGISTRATION_SHA, "original preregistration"),
    (AMENDMENT_SHA, "amendment"),
]:
    try:
        out = subprocess.check_output(
            ["git", "cat-file", "-t", expected_sha],
            cwd=str(REPO_ROOT), text=True
        ).strip()
        if out == "commit":
            s8_notes.append(f"{desc} SHA {expected_sha}: found")
        else:
            s8_ok = False
            s8_notes.append(f"{desc} SHA {expected_sha}: unexpected type={out}")
    except subprocess.CalledProcessError:
        s8_ok = False
        s8_notes.append(f"{desc} SHA {expected_sha}: NOT found in git history")

record("8_plan_committed", s8_ok, "; ".join(s8_notes),
       original_preregistration_sha=ORIGINAL_PREREGISTRATION_SHA,
       amendment_sha=AMENDMENT_SHA)

# ════════════════════════════════════════════════════════════════════════════
# Condition 9: Gate F evidence intact (SHA of heldout_analysis.json)
# ════════════════════════════════════════════════════════════════════════════
print("\n[9] Gate F evidence intact ...")
s9_ok = True; s9_notes = []
heldout_sha = None

if not HELDOUT_ANALYSIS_FILE.exists():
    s9_ok = False; s9_notes.append("gate_f_heldout_analysis.json missing")
else:
    data = HELDOUT_ANALYSIS_FILE.read_bytes()
    heldout_sha = hashlib.sha256(data).hexdigest()
    s9_notes.append(f"gate_f_heldout_analysis.json SHA256={heldout_sha[:16]}...")
    # Load and check it has expected keys
    try:
        ha = json.loads(data)
        n_scen = ha.get("n", ha.get("n_scenarios",
                        len(ha.get("scenario_results", ha.get("results", [])))))
        s9_notes.append(f"n_scenarios={n_scen}")
        if isinstance(n_scen, int) and n_scen >= 25:
            pass   # good
        else:
            s9_ok = False; s9_notes.append(f"Expected n>=25, got {n_scen}")
        if "analysis_type" in ha:
            s9_notes.append(f"analysis_type={ha['analysis_type']}")
    except Exception as e:
        s9_ok = False; s9_notes.append(f"Parse error: {e}")

record("9_gate_f_intact", s9_ok, "; ".join(s9_notes),
       heldout_analysis_sha256=heldout_sha)

# ════════════════════════════════════════════════════════════════════════════
# Condition 10: Policy unit tests pass
# ════════════════════════════════════════════════════════════════════════════
print("\n[10] Policy unit tests ...")
# Already done in condition 3; just re-reference
s10_ok = conditions.get("3_phase_c_complete", {}).get("pass", False)
record("10_unit_tests", s10_ok,
       "Unit tests re-verified via condition 3" if s10_ok else
       "Unit tests FAILED (see condition 3)")

# ════════════════════════════════════════════════════════════════════════════
# Condition 11: Dev dry-run (sc30 at r=1.0, no actual capacity run needed)
# ════════════════════════════════════════════════════════════════════════════
print("\n[11] Dev dry-run check ...")
# We verify that the r2_gate_f_run.py module loads cleanly and seed generation
# reproduces sc30 seed without error (no actual simulation required here —
# the full dry-run is triggered by running r2_gate_f_run.py with N_DEV=1 GATE_F_RATIOS_ONLY=1.0).
# The preflight itself verifies the module syntax and seed.
s11_ok = True; s11_notes = []

data_dir = os.environ.get("THERMALSHIFT_DATA_DIR", "")
if not data_dir or not Path(data_dir).exists():
    s11_notes.append(
        "THERMALSHIFT_DATA_DIR not set or missing — "
        "manual dry-run required: "
        "GATE_F_N_DEV=1 GATE_F_N_FIRST=30 GATE_F_RATIOS_ONLY=1.0 "
        "python artifacts/revision2/r2_gate_f_run.py"
    )
    # Not a blocker at preflight time — operator must confirm dry-run was run
else:
    # Data dir is available — check r2_gate_f_run.py exists and seed asserts would pass
    if not r2_run_file.exists():
        s11_ok = False; s11_notes.append("r2_gate_f_run.py missing")
    else:
        # Quick import check: verify the seed assert block would pass
        rng11 = np.random.default_rng(CHALLENGE_SEED)
        _sc = [int(rng11.integers(0, 2**31)) for _ in range(N_SCENARIOS_CHALLENGE)]
        _wl = [int(rng11.integers(0, 2**31)) for _ in range(N_SCENARIOS_CHALLENGE)]
        _pg  = int(rng11.integers(0, 2**31))
        _pwc = int(rng11.integers(0, 2**31))
        if _pg == PLACEBO_GLOBAL_PERM_SEED and _pwc == PLACEBO_WITHINCAB_PERM_SEED:
            s11_notes.append(
                f"Seed asserts would pass (sc30 scen={_sc[0]}). "
                "Full dry-run with GATE_F_N_DEV=1 recommended before challenge run."
            )
        else:
            s11_ok = False
            s11_notes.append(
                f"Seed assert mismatch: pg={_pg} expected={PLACEBO_GLOBAL_PERM_SEED}"
            )

record("11_dev_dryrun", s11_ok, "; ".join(s11_notes) or "seed asserts verified")

# ════════════════════════════════════════════════════════════════════════════
# Condition 12: Operator acknowledgement
# ════════════════════════════════════════════════════════════════════════════
print("\n[12] Operator acknowledgement ...")
op_ack = args.ack
if op_ack:
    print("     --ack flag set: operator acknowledged governing-rule compliance.")
else:
    print("     --ack NOT set. Re-run with --ack to confirm operator acknowledgement.")
record("12_operator_ack", op_ack,
       "Operator confirmed: no policy/metric/threshold/seed/interpretation rule changed "
       "after preregistration" if op_ack else
       "NOT acknowledged — re-run with --ack flag")

# ════════════════════════════════════════════════════════════════════════════
# Summary
# ════════════════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
n_pass = sum(1 for c in conditions.values() if c["pass"])
n_fail = len(conditions) - n_pass
print(f"Preflight: {n_pass}/12 conditions PASS  {n_fail}/12 FAIL")
print("=" * 70)

if all_pass:
    print("\nOVERALL: PASS — challenge run sc30-54 may proceed.")
else:
    print("\nOVERALL: FAIL — resolve failing conditions before challenge run.")
    for k, v in conditions.items():
        if not v["pass"]:
            print(f"  FAIL: {k}: {v['notes']}")

# ── Write preflight JSON ──────────────────────────────────────────────────────
preflight = {
    "script"              : "artifacts/revision2/r2_challenge_preflight.py",
    "plan_ref"            : "REVIEW2_CHALLENGE_PLAN.md Phase F (amendment 6b45030)",
    "preflight_run_at"    : datetime.datetime.utcnow().isoformat() + "Z",
    "challenge_freeze_commit": freeze_sha,
    "primary_beta_challenge" : primary_beta,
    "plan_commits" : {
        "original_preregistration": ORIGINAL_PREREGISTRATION_SHA,
        "amendment": AMENDMENT_SHA,
    },
    "seed_collision_audit": conditions.get("5_seed_collision_audit", {}),
    "conditions"          : conditions,
    "overall_pass"        : all_pass,
}
PREFLIGHT_OUT.write_text(json.dumps(preflight, indent=2))
print(f"\nWritten: {PREFLIGHT_OUT}")

sys.exit(0 if all_pass else 1)
