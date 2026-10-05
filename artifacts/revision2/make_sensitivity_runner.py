#!/usr/bin/env python3
"""
Generate r2_sensitivity_run.py from frozen r2_gate_f_run.py.
Applies exactly the allowed changes; all scientific logic is line-identical.
Run once; verify SHA256 of output; do not re-run.
"""
import re
from pathlib import Path

SRC  = Path(__file__).parent / "r2_gate_f_run.py"
DEST = Path(__file__).parent / "r2_sensitivity_run.py"

lines = SRC.read_text(encoding="utf-8").splitlines(keepends=True)
out   = []
i     = 0
n     = len(lines)

def emit(text):
    out.append(text if text.endswith("\n") else text + "\n")

# ── patch table ──────────────────────────────────────────────────────────────
# Each entry: (match_text, action, replacement_lines)
# action: "replace" = replace matched line; "after" = emit replacement after match

PATCH_DOCSTRING_TARGET = '"""'
PATCH_DOCSTRING_DONE   = False

while i < n:
    line = lines[i]
    stripped = line.rstrip("\n")

    # ── 1. Replace docstring header ─────────────────────────────────────────
    if not PATCH_DOCSTRING_DONE and stripped.startswith('"""') and i < 10:
        emit('"""\n')
        emit('Review-2 Sensitivity Runner: r2_sensitivity_run.py\n')
        emit('\n')
        emit('Derived from frozen r2_gate_f_run.py (commit 5733b73).\n')
        emit('Allowed additions only:\n')
        emit('  GATE_F_SENSITIVITY_BETA  — non-compat beta override\n')
        emit('  GATE_F_CAB_SCALE         — cabinet-envelope multiplicative scale\n')
        emit('All scientific logic is otherwise line-identical to the frozen runner.\n')
        emit('Seeds always drawn for all 7 CHALLENGE_POLICY_IDS in original order.\n')
        emit('Per-scenario seed assertions against challenge_seed_index_audit.json.\n')
        emit('\n')
        emit('Environment variables (additions; all original vars still apply):\n')
        emit('  GATE_F_SENSITIVITY_BETA  — override BETA_CHALLENGE (non-compat mode)\n')
        emit('  GATE_F_CAB_SCALE         — multiply all cab_p99_W values (default 1.00)\n')
        emit('"""\n')
        PATCH_DOCSTRING_DONE = True
        # Skip original docstring block
        i += 1
        while i < n and not lines[i].rstrip("\n").endswith('"""'):
            i += 1
        i += 1  # skip closing """
        continue

    # ── 2. After BETA_CHALLENGE = PRIMARY_BETA_CHALLENGE, add sensitivity override ──
    if stripped == "BETA_CHALLENGE   = PRIMARY_BETA_CHALLENGE   # imported from r2_selectors.py":
        emit(line)
        emit("\n")
        emit("# Sensitivity-only beta override (non-compat mode) — Phase E2\n")
        emit("_SENS_BETA_ENV = os.environ.get(\"GATE_F_SENSITIVITY_BETA\", \"\")\n")
        emit("if _SENS_BETA_ENV:\n")
        emit("    BETA_CHALLENGE = float(_SENS_BETA_ENV)\n")
        emit("\n")
        emit("# Cabinet scale — Phase E1\n")
        emit("CAB_SCALE = float(os.environ.get(\"GATE_F_CAB_SCALE\", \"1.00\"))\n")
        i += 1
        continue

    # ── 3. Fix _COMPAT_POLICY_ORDER to always use full CHALLENGE_POLICY_IDS ──
    if "_COMPAT_POLICY_ORDER_ENV = os.environ.get" in stripped:
        emit("# Always draw seeds for all 7 policies in original challenge order\n")
        emit("# (do not use GATE_F_POLICIES for draw order — breaks pol_seed values)\n")
        emit("_COMPAT_POLICY_ORDER = list(CHALLENGE_POLICY_IDS)\n")
        i += 1
        # Skip the next two lines (original _COMPAT_POLICY_ORDER block)
        while i < n and "_COMPAT_POLICY_ORDER" in lines[i]:
            i += 1
        continue

    # ── 4. Change output suffix to r2sensitivity ─────────────────────────────
    if '_run_suffix = "r2compat" if _is_compat else "r2challenge"' in stripped:
        emit("# Sensitivity runs get a unique suffix encoding scale and beta\n")
        emit("_beta_tag  = os.environ.get(\"GATE_F_SENSITIVITY_BETA\", \"primary\").replace(\".\", \"p\")\n")
        emit("_scale_tag = os.environ.get(\"GATE_F_CAB_SCALE\", \"1p00\").replace(\".\", \"p\")\n")
        emit('_run_suffix = f"r2sensitivity_sc{_scale_tag}_b{_beta_tag}"\n')
        i += 1
        continue

    # ── 5. Apply cabinet scale after loading cab_p99_W ───────────────────────
    if "cab_p99_W = {c: cab_p99_W.get(c, _p99_med) for c in all_cabinets}" in stripped:
        emit(line)
        emit("if CAB_SCALE != 1.00:\n")
        emit("    cab_p99_W = {c: CAB_SCALE * v for c, v in cab_p99_W.items()}\n")
        emit('print(f"    CAB_SCALE={CAB_SCALE}  BETA_CHALLENGE={BETA_CHALLENGE}")\n')
        i += 1
        continue

    # ── 6. Add seed-assertion loader after line about script/plan_ref print ──
    if '# pol_seeds: draw in policy order; compat mode uses r1\'s original 7-policy draw order' in stripped:
        # Insert seed assertion setup before this block
        emit("\n")
        emit("# ── Per-scenario seed assertions (against frozen challenge_seed_index_audit.json) ──\n")
        emit("_seed_audit_path = Path(__file__).parent / \"challenge_seed_index_audit.json\"\n")
        emit("_seed_audit = json.loads(_seed_audit_path.read_text()) if _seed_audit_path.exists() else None\n")
        emit("\n")
        emit("def _assert_scenario_seeds(sc_abs: int, scen_seed_val: int, wl_seed_val: int, pol_seeds_map: dict):\n")
        emit("    if _seed_audit is None:\n")
        emit("        print(f\"    [seed_assert] WARNING: audit file not found, skipping assertion for sc{sc_abs}\")\n")
        emit("        return\n")
        emit("    key = f\"sc{sc_abs}\"\n")
        emit("    ref = _seed_audit.get(\"scenario_table\", {}).get(key)\n")
        emit("    if ref is None:\n")
        emit("        raise AssertionError(f\"Seed audit has no entry for {key}\")\n")
        emit("    if scen_seed_val != ref[\"scen_seed\"]:\n")
        emit("        raise AssertionError(f\"sc{sc_abs} scen_seed mismatch: got {scen_seed_val}, expected {ref['scen_seed']}\")\n")
        emit("    if wl_seed_val != ref[\"wl_seed\"]:\n")
        emit("        raise AssertionError(f\"sc{sc_abs} wl_seed mismatch: got {wl_seed_val}, expected {ref['wl_seed']}\")\n")
        emit("    for pol in (\"full_random\", \"full_fp\"):\n")
        emit("        got = pol_seeds_map.get(pol, [None] * 30)[sc_abs - SEED_INDEX_BASE]\n")
        emit("        exp = ref[f\"pol_seed_{pol}\"]\n")
        emit("        if got != exp:\n")
        emit("            raise AssertionError(f\"sc{sc_abs} pol_seed[{pol}] mismatch: got {got}, expected {exp}\")\n")
        emit("    print(f\"    [seed_assert] sc{sc_abs}: PASS (scen={scen_seed_val} wl={wl_seed_val} \"\n")
        emit("          f\"random={pol_seeds_map['full_random'][sc_abs-SEED_INDEX_BASE]} \"\n")
        emit("          f\"fp={pol_seeds_map['full_fp'][sc_abs-SEED_INDEX_BASE]})\")\n")
        emit("\n")
        emit(line)
        i += 1
        continue

    # ── 7. Call seed assertion inside the main scenario loop ─────────────────
    if "scen_seed = scen_seeds[_si]" in stripped and "print" not in stripped:
        emit(line)
        # Next line after scen_seed assignment: add assertion call
        emit("    _assert_scenario_seeds(s_abs, scen_seed, wl_seeds[_si], pol_seeds)\n")
        i += 1
        continue

    # ── 8. Change script name in output JSON ─────────────────────────────────
    if '"script"                 : "artifacts/revision2/r2_gate_f_run.py",' in stripped:
        emit('    "script"                 : "artifacts/revision2/r2_sensitivity_run.py",\n')
        emit('    "sensitivity_beta"       : BETA_CHALLENGE,\n')
        emit('    "cab_scale"              : CAB_SCALE,\n')
        emit('    "sensitivity_beta_env"   : os.environ.get("GATE_F_SENSITIVITY_BETA", "primary"),\n')
        emit('    "cab_scale_env"          : os.environ.get("GATE_F_CAB_SCALE", "1.00"),\n')
        i += 1
        continue

    # ── 9. Update plan_ref in output JSON ────────────────────────────────────
    if '"plan_ref"               : "REVIEW2_CHALLENGE_PLAN.md Phase D (amendment 6b45030)",' in stripped:
        emit('    "plan_ref"               : "REVIEW2_CHALLENGE_PLAN.md Phase E1/E2 (post-exposure sensitivity recovery)",\n')
        i += 1
        continue

    # ── Default: emit line unchanged ─────────────────────────────────────────
    out.append(line)
    i += 1

DEST.write_text("".join(out), encoding="utf-8")
print(f"Written: {DEST}")
print(f"Lines: {len(out)} (original: {n})")

import hashlib
sha = hashlib.sha256(DEST.read_bytes()).hexdigest()
print(f"SHA256: {sha}")
