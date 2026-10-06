#!/usr/bin/env python3
"""
F2 reference unit tests — verify F2 mode loads correct thresholds and denominator.
Runs without executing any scheduling scenario.
"""
import json, hashlib, sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
REV1_DIR = REPO_ROOT / "artifacts" / "revision1"
REV3_DIR = REPO_ROOT / "artifacts" / "revision3"

results = []

def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((name, status, detail))
    print(f"  [{status}] {name}" + (f": {detail}" if detail else ""))
    return cond

print("F2 Reference Unit Tests")
print("=" * 60)

# Load F1 reference (cabinet_power_envelopes.json)
f1_env_path = REV1_DIR / "results" / "cabinet_power_envelopes.json"
with open(f1_env_path) as f:
    f1_env = json.load(f)
f1_kW = {int(float(k)): v for k, v in f1_env["per_cabinet_p99_kW_correct"].items()}
f1_W  = {c: v * 1000.0 for c, v in f1_kW.items()}

# Load F2 reference
f2_ref_path = REV3_DIR / "f2_local_scheduling_reference.json"
with open(f2_ref_path) as f:
    f2_ref = json.load(f)
f2_per_cab = {int(x["cabinet_id"]): x for x in f2_ref["per_cabinet"]}

# Load F2 denominator
denom_path = REV3_DIR / "f2_denominator.json"
with open(denom_path) as f:
    denom = json.load(f)

print("\n--- Check 1: F1 legacy thresholds load from cabinet_power_envelopes.json ---")
cab2000_f1_W = f1_W.get(2000)
check("F1 cab 2000 threshold > 0", cab2000_f1_W is not None and cab2000_f1_W > 0,
      f"{cab2000_f1_W:.1f} W")

print("\n--- Check 2: F2-local reference has exactly 77 cabinets ---")
check("F2 reference has 77 cabinets", len(f2_per_cab) == 77, str(len(f2_per_cab)))

print("\n--- Checks 3-5: Late-cabinet F2 threshold values ---")
# From Task-D2 f2_local_date_support: 2600->161.764 kW, 2601->173.539 kW, 2602->163.126 kW
expected = {2600: 161.764, 2601: 173.539, 2602: 163.126}
for cab, exp_kW in expected.items():
    if cab in f2_per_cab:
        got_kW = f2_per_cab[cab]["Q_F2_local_kW"]
        got_W  = f2_per_cab[cab]["Q_F2_local_W"]
        check(f"F2 threshold cab {cab} ~ {exp_kW} kW",
              abs(got_kW - exp_kW) < 0.1,
              f"{got_kW:.3f} kW (diff {abs(got_kW - exp_kW):.4f})")
    else:
        check(f"F2 threshold cab {cab} present", False, "missing from reference")

print("\n--- Check 6: F2 and F1 thresholds differ for cab 2600 ---")
f2_W_2600 = f2_per_cab[2600]["Q_F2_local_W"] if 2600 in f2_per_cab else None
f1_W_2600 = f1_W.get(2600)
check("F2 != F1 for cab 2600 (no aliasing)",
      f2_W_2600 is not None and f1_W_2600 is not None and abs(f2_W_2600 - f1_W_2600) > 1.0,
      f"F2={f2_W_2600:.1f} W, F1={f1_W_2600:.1f} W")

print("\n--- Check 7: F2 denominator artifact loads, B_cab_hist > 0 ---")
B_cab_hist_F2 = denom["aggregate"]["B_cab_hist_F2_h"]
check("F2 denominator B_cab_hist_F2 > 0", B_cab_hist_F2 > 0,
      f"{B_cab_hist_F2:.4f} h")
check("F2 denominator n_cabinets == 77",
      denom["aggregate"]["n_cabinets"] == 77,
      str(denom["aggregate"]["n_cabinets"]))

print("\n--- Check 8: F2 aggregate exceedance fraction ~ 1% ---")
exc_frac = denom["aggregate"]["aggregate_exceedance_fraction"]
check("F2 aggregate exceedance in [0.5%, 1.5%]",
      0.005 <= exc_frac <= 0.015,
      f"{exc_frac:.4%}")

print("\n--- Check 9: F2 threshold units are W (not kW) ---")
all_f2_W = [x["Q_F2_local_W"] for x in f2_ref["per_cabinet"]]
min_W = min(all_f2_W)
max_W = max(all_f2_W)
check("All F2 thresholds in W range (100,000–300,000 W)",
      all(100_000 <= w <= 300_000 for w in all_f2_W),
      f"range [{min_W:.0f}, {max_W:.0f}] W")

print("\n--- Check 10: W/kW factor exactly 1000 for all cabinets ---")
max_unit_err = max(
    abs(x["Q_F2_local_W"] - x["Q_F2_local_kW"] * 1000.0)
    for x in f2_ref["per_cabinet"]
)
check("W = kW × 1000 within 1e-9 for all cabinets",
      max_unit_err < 1e-9,
      f"max error = {max_unit_err:.2e}")

print("\n--- Check 11: No duplicate cabinet IDs ---")
cab_ids = [x["cabinet_id"] for x in f2_ref["per_cabinet"]]
check("No duplicate cabinet IDs", len(cab_ids) == len(set(cab_ids)),
      f"{len(cab_ids)} IDs, {len(set(cab_ids))} unique")

print("\n--- Check 12: All F2 thresholds finite and > 0 ---")
all_finite = all(x["Q_F2_local_kW"] > 0 and x["Q_F2_local_W"] > 0
                 for x in f2_ref["per_cabinet"])
check("All F2 thresholds > 0 and finite", all_finite)

# Load replay denominator and verify it is NOT the Task-D denominator
replay_denom_path = REV3_DIR / "f2_replay_denominator.json"
taskd_denom_path  = REV3_DIR / "f2_denominator.json"
with open(replay_denom_path) as f:
    replay_denom = json.load(f)
with open(taskd_denom_path) as f:
    taskd_denom = json.load(f)

B_replay = replay_denom["aggregate"]["B_cab_hist_F2_replay_h"]
B_taskd  = taskd_denom["aggregate"]["B_cab_hist_F2_h"]

print("\n--- Check 13: Replay denominator artifact loads, B_F2_replay > 0 ---")
check("F2 replay denominator B_cab_hist_F2_replay_h > 0", B_replay > 0,
      f"{B_replay:.4f} h")

print("\n--- Check 14: Replay denominator != Task-D denominator (not aliased) ---")
check("B_cab_hist_F2_replay != B_cab_hist_F2_taskD",
      abs(B_replay - B_taskd) > 100.0,
      f"replay={B_replay:.2f} h  taskD={B_taskd:.2f} h  diff={abs(B_replay-B_taskd):.2f} h")

print("\n--- Check 15: Runner source does NOT load f2_denominator.json for B_cab_hist ---")
runner_src = (REPO_ROOT / "artifacts" / "revision3" / "r3_gate_f_run.py").read_text(encoding="utf-8")
# The task-D denominator path must not appear in the scheduling denominator block
taskd_key_in_runner = '"B_cab_hist_F2_h"' in runner_src
check("Runner does not use B_cab_hist_F2_h (Task-D key) for scheduling",
      not taskd_key_in_runner,
      "key found in runner source — runner still reads Task-D denominator" if taskd_key_in_runner
      else "key absent from runner source")

print("\n--- Check 16: Runner uses B_cab_hist_F2_replay_h (replay key) ---")
replay_key_in_runner = '"B_cab_hist_F2_replay_h"' in runner_src
check("Runner uses B_cab_hist_F2_replay_h for scheduling",
      replay_key_in_runner,
      "key found" if replay_key_in_runner else "key missing from runner source")

print("\n--- Check 17: F2 replay denominator has 77 per-cabinet entries ---")
check("Replay denominator has 77 per-cabinet entries",
      len(replay_denom["per_cabinet"]) == 77,
      str(len(replay_denom["per_cabinet"])))

print("\n" + "=" * 60)
n_pass = sum(1 for _, s, _ in results if s == "PASS")
n_fail = sum(1 for _, s, _ in results if s == "FAIL")
print(f"Result: {n_pass}/{len(results)} PASS, {n_fail} FAIL")

if n_fail > 0:
    print("\nFAILED checks:")
    for name, status, detail in results:
        if status == "FAIL":
            print(f"  FAIL: {name}: {detail}")
    sys.exit(1)
else:
    print("ALL PASS")
    sys.exit(0)
