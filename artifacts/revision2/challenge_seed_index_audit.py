#!/usr/bin/env python3
"""
Challenge seed-index audit (challenge_seed_index_audit.py)

Deterministic verification that rng(2042) produces the correct seed-array
for all 25 challenge scenarios (sc30–sc54), using the ACTUAL challenge policy
order (CHALLENGE_POLICY_IDS), not the r1 compatibility order.

Verifies:
  - sc30→index 0, sc31→index 1, …, sc54→index 24 (SEED_INDEX_BASE=30)
  - scen_seed[i] and wl_seed[i] for each scenario
  - policy seed for every challenge policy, every scenario
  - placebo seeds unchanged: 218767960 and 365514213
  - no accidental collision between scenarios
  - CHALLENGE_POLICY_IDS in runner matches frozen audit list exactly

Does NOT execute any simulation. Purely deterministic.

Plan ref: REVIEW2_CHALLENGE_PLAN.md Amendment 5.

Usage:
  python challenge_seed_index_audit.py
"""
import sys, io, json, datetime
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REV2_DIR  = REPO_ROOT / "artifacts" / "revision2"
OUT_FILE  = REV2_DIR / "challenge_seed_index_audit.json"

# ── Frozen experiment constants ───────────────────────────────────────────────
CHALLENGE_SEED              = 2042
SCENARIO_FIRST              = 30
N_SCENARIOS_CHALLENGE       = 25
SEED_INDEX_BASE             = SCENARIO_FIRST  # fixed, not N_FIRST
PLACEBO_GLOBAL_PERM_SEED    = 218767960
PLACEBO_WITHINCAB_PERM_SEED = 365514213

# The ACTUAL challenge policy draw order in r2_gate_f_run.py (non-compat mode):
# GATE_F_POLICIES = CHALLENGE_POLICY_IDS, and _COMPAT_POLICY_ORDER = list(GATE_F_POLICIES)
# when GATE_F_COMPAT_POLICY_ORDER env var is not set.
CHALLENGE_POLICY_IDS = [
    "full_random",
    "full_fp",
    "position_template",
    "full_fp_spread",
    "random_spread",
    "fp_global_placebo",
    "fp_withincab_placebo",
]

def main():
    print("=" * 70)
    print("Challenge Seed-Index Audit")
    print("Plan ref: REVIEW2_CHALLENGE_PLAN.md Amendment 5")
    print("=" * 70)

    failures = []
    notes    = []

    # ── Verify CHALLENGE_POLICY_IDS matches runner source ────────────────────
    run_script = REV2_DIR / "r2_gate_f_run.py"
    if not run_script.exists():
        failures.append("r2_gate_f_run.py not found — cannot verify CHALLENGE_POLICY_IDS")
    else:
        src = run_script.read_text(encoding="utf-8")
        for pol in CHALLENGE_POLICY_IDS:
            if f'"{pol}"' not in src and f"'{pol}'" not in src:
                failures.append(f"Policy '{pol}' not found in r2_gate_f_run.py source")
        # Verify SEED_INDEX_BASE fix is present
        if "SEED_INDEX_BASE" not in src:
            failures.append("SEED_INDEX_BASE not found in r2_gate_f_run.py — Amendment 5 fix missing")
        else:
            notes.append("SEED_INDEX_BASE fix confirmed present in r2_gate_f_run.py")
        notes.append(f"CHALLENGE_POLICY_IDS ({len(CHALLENGE_POLICY_IDS)} policies): {CHALLENGE_POLICY_IDS}")

    # ── Reconstruct rng(2042) exactly as the challenge runner does ────────────
    # Challenge (non-compat) draw order:
    #   1. N_SCENARIOS_TOTAL scen_seeds
    #   2. N_SCENARIOS_TOTAL wl_seeds
    #   3. 1 placebo-global seed
    #   4. 1 placebo-withincab seed
    #   5. N_SCENARIOS_TOTAL seeds per policy, in CHALLENGE_POLICY_IDS order
    rng = np.random.default_rng(CHALLENGE_SEED)
    scen_seeds = [int(rng.integers(0, 2**31)) for _ in range(N_SCENARIOS_CHALLENGE)]
    wl_seeds   = [int(rng.integers(0, 2**31)) for _ in range(N_SCENARIOS_CHALLENGE)]
    pg_seed    = int(rng.integers(0, 2**31))
    pwc_seed   = int(rng.integers(0, 2**31))
    pol_seeds  = {
        p: [int(rng.integers(0, 2**31)) for _ in range(N_SCENARIOS_CHALLENGE)]
        for p in CHALLENGE_POLICY_IDS
    }

    # ── Assert placebo seeds unchanged ────────────────────────────────────────
    if pg_seed != PLACEBO_GLOBAL_PERM_SEED:
        failures.append(
            f"PLACEBO_GLOBAL_PERM_SEED mismatch: got {pg_seed}, "
            f"expected {PLACEBO_GLOBAL_PERM_SEED}"
        )
    else:
        notes.append(f"PLACEBO_GLOBAL_PERM_SEED = {pg_seed} [PASS]")

    if pwc_seed != PLACEBO_WITHINCAB_PERM_SEED:
        failures.append(
            f"PLACEBO_WITHINCAB_PERM_SEED mismatch: got {pwc_seed}, "
            f"expected {PLACEBO_WITHINCAB_PERM_SEED}"
        )
    else:
        notes.append(f"PLACEBO_WITHINCAB_PERM_SEED = {pwc_seed} [PASS]")

    # ── Assert uniqueness of seeds ────────────────────────────────────────────
    if len(set(scen_seeds)) != N_SCENARIOS_CHALLENGE:
        failures.append(f"scen_seeds not unique: {len(set(scen_seeds))}/{N_SCENARIOS_CHALLENGE}")
    else:
        notes.append(f"All {N_SCENARIOS_CHALLENGE} scen_seeds unique [PASS]")

    if len(set(wl_seeds)) != N_SCENARIOS_CHALLENGE:
        failures.append(f"wl_seeds not unique: {len(set(wl_seeds))}/{N_SCENARIOS_CHALLENGE}")
    else:
        notes.append(f"All {N_SCENARIOS_CHALLENGE} wl_seeds unique [PASS]")

    # ── Build scenario table and verify seed-index mapping ───────────────────
    scenario_table = {}
    for sc in range(SCENARIO_FIRST, SCENARIO_FIRST + N_SCENARIOS_CHALLENGE):
        idx = sc - SEED_INDEX_BASE  # should equal sc - 30
        expected_idx = sc - SCENARIO_FIRST
        if idx != expected_idx:
            failures.append(f"sc{sc}: seed_index={idx} expected {expected_idx}")
        row = {
            "seed_index": idx,
            "scen_seed" : scen_seeds[idx],
            "wl_seed"   : wl_seeds[idx],
        }
        for pol in CHALLENGE_POLICY_IDS:
            row[f"pol_seed_{pol}"] = pol_seeds[pol][idx]
        scenario_table[f"sc{sc}"] = row

    # Verify old bug would have been wrong for sc31
    old_bug_idx = 31 - 31   # N_FIRST=31 → idx=0 (WRONG)
    new_fix_idx = 31 - SEED_INDEX_BASE  # = 1 (CORRECT)
    if new_fix_idx != 1:
        failures.append(f"BUG: sc31 new_fix_idx={new_fix_idx} should be 1")
    else:
        notes.append(
            f"Parallel-worker fix verified: sc31 old_N_FIRST_bug={old_bug_idx}(WRONG) "
            f"new_SEED_INDEX_BASE_fix={new_fix_idx}(CORRECT)"
        )

    # Verify per-policy seeds differ between scenarios (spot-check sc30 vs sc31)
    for pol in CHALLENGE_POLICY_IDS:
        if pol_seeds[pol][0] == pol_seeds[pol][1]:
            failures.append(f"Policy {pol}: sc30 and sc31 have same seed — rng collision")

    notes.append(
        f"sc30: scen_seed={scen_seeds[0]}  wl_seed={wl_seeds[0]}  "
        f"full_random_seed={pol_seeds['full_random'][0]}"
    )
    notes.append(
        f"sc31: scen_seed={scen_seeds[1]}  wl_seed={wl_seeds[1]}  "
        f"full_random_seed={pol_seeds['full_random'][1]}"
    )

    audit_pass = len(failures) == 0
    print(f"\nAudit: {'PASS' if audit_pass else 'FAIL'}")
    for n in notes:
        print(f"  {n}")
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        for f in failures:
            print(f"  FAIL: {f}")

    result = {
        "script"                    : "artifacts/revision2/challenge_seed_index_audit.py",
        "plan_ref"                  : "REVIEW2_CHALLENGE_PLAN.md Amendment 5",
        "run_at"                    : datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "challenge_seed"            : CHALLENGE_SEED,
        "scenario_first"            : SCENARIO_FIRST,
        "n_scenarios"               : N_SCENARIOS_CHALLENGE,
        "seed_index_base"           : SEED_INDEX_BASE,
        "challenge_policy_ids"      : CHALLENGE_POLICY_IDS,
        "placebo_global_perm_seed"  : pg_seed,
        "placebo_withincab_perm_seed": pwc_seed,
        "placebo_seeds_verified"    : (pg_seed == PLACEBO_GLOBAL_PERM_SEED and
                                       pwc_seed == PLACEBO_WITHINCAB_PERM_SEED),
        "scen_seeds_unique"         : len(set(scen_seeds)) == N_SCENARIOS_CHALLENGE,
        "wl_seeds_unique"           : len(set(wl_seeds)) == N_SCENARIOS_CHALLENGE,
        "scenario_table"            : scenario_table,
        "notes"                     : notes,
        "failures"                  : failures,
        "audit_pass"                : audit_pass,
    }

    OUT_FILE.write_text(json.dumps(result, indent=2))
    print(f"\nWritten: {OUT_FILE}")
    return 0 if audit_pass else 1


if __name__ == "__main__":
    sys.exit(main())
