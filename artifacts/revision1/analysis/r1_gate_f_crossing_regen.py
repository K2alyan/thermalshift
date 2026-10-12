#!/usr/bin/env python3
"""
r1_gate_f_crossing_regen.py

Deterministic crossing regeneration for gate_f_sc0-4_unr.json.

Reads the stored lambda_rows and scenario-level B_ref_s/S_ref_s from the
sc0-4 unrestricted Gate F output, applies the frozen v3 capacity-ordered
classify_crossing to every (scenario, policy) pair, and writes a clean JSON
without hand-patch metadata.

This is the canonical code-based fix for the pre-v3-fix runner output that
was temporarily corrected by a manual patch to sc4/unrestricted/full_loc.
No simulation data is required — only the stored JSON.
"""

import sys, io, json, ast, subprocess
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

import numpy as np
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
REV1_DIR  = REPO_ROOT / "artifacts" / "revision1"
OUT_DIR   = REV1_DIR / "results"
IN_FILE   = OUT_DIR / "gate_f_sc0-4_unr.json"
RUN_PY    = REV1_DIR / "analysis" / "r1_gate_f_run.py"


def _load_classify_crossing():
    """Extract classify_crossing from r1_gate_f_run.py via AST."""
    src = RUN_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    func_src = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "classify_crossing":
            func_src = ast.get_source_segment(src, node)
            break
    if func_src is None:
        raise RuntimeError("classify_crossing not found in r1_gate_f_run.py")
    ns = {"np": np}
    exec(func_src, ns)
    return ns["classify_crossing"]


def _git_head():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    except Exception:
        return "unknown"


print("Gate F Crossing Regen (v3 capacity-ordered, from stored lambda_rows)")
print("=" * 70)

classify_crossing = _load_classify_crossing()
print("  classify_crossing loaded from r1_gate_f_run.py via AST")

with open(IN_FILE) as f:
    d = json.load(f)

n_changed = 0
n_total   = 0
changes   = []

for item in d["scenario_results"]:
    sc_idx  = item["scenario_idx"]
    b_ref_s = item["B_ref_s"]
    s_ref_s = item["S_ref_s"]

    for ratio_key, pol_dict in item["ratios"].items():
        for pol, pol_data in pol_dict.items():
            lrows   = pol_data.get("lambda_rows", [])
            old_cx  = pol_data.get("crossing", {})
            n_total += 1

            # Deep-copy rows so classify_crossing's in-place annotation
            # does not mutate the stored lambda_rows.
            import copy
            rows_copy = copy.deepcopy(lrows)
            new_cx = classify_crossing(rows_copy, b_ref_s, s_ref_s, None)

            # Remove internal annotation keys that classify_crossing adds
            # (we only keep the canonical crossing fields).
            clean_cx = {
                k: v for k, v in new_cx.items()
                if k in ("status", "C_lower_pct", "C_upper_pct",
                         "first_binding_constraint", "right_censored")
            }

            # Check if the crossing changed (ignore metadata keys).
            def _cx_key(cx):
                return (cx.get("status"),
                        round(cx.get("C_lower_pct", 0.0) or 0.0, 12),
                        round(cx.get("C_upper_pct", 0.0) or 0.0, 12))

            old_key = _cx_key(old_cx)
            new_key = _cx_key(clean_cx)
            if old_key != new_key:
                n_changed += 1
                changes.append({
                    "sc": sc_idx, "ratio": ratio_key, "policy": pol,
                    "old_C_lower": old_cx.get("C_lower_pct"),
                    "old_C_upper": old_cx.get("C_upper_pct"),
                    "new_C_lower": clean_cx.get("C_lower_pct"),
                    "new_C_upper": clean_cx.get("C_upper_pct"),
                })
                print(f"  CHANGED sc{sc_idx}/{ratio_key}/{pol}: "
                      f"[{old_cx.get('C_lower_pct', '?'):.4f},{old_cx.get('C_upper_pct', '?'):.4f}]"
                      f" -> [{clean_cx.get('C_lower_pct', '?'):.4f},{clean_cx.get('C_upper_pct', '?'):.4f}]")

            pol_data["crossing"] = clean_cx

# Remove hand-patch metadata fields.
d.pop("crossing_corrections", None)
d.pop("crossing_correction_note", None)

# Add regen provenance note.
d["crossing_regen_note"] = (
    "Crossings regenerated deterministically by r1_gate_f_crossing_regen.py. "
    "v3 capacity-ordered classify_crossing applied to stored lambda_rows using "
    "stored B_ref_s and S_ref_s. Prior hand-patch metadata removed."
)
d["crossing_regen_head"] = _git_head()

with open(IN_FILE, "w") as f:
    json.dump(d, f, indent=2)

print()
print(f"  {n_total} (scenario, ratio, policy) cells processed")
print(f"  {n_changed} crossings changed from stored values")
if changes:
    print()
    print("  Changed crossings:")
    for c in changes:
        print(f"    sc{c['sc']}/{c['ratio']}/{c['policy']}: "
              f"old=[{c['old_C_lower']:.6f},{c['old_C_upper']:.6f}] "
              f"new=[{c['new_C_lower']:.6f},{c['new_C_upper']:.6f}]")
print()
print(f"  Saved: {IN_FILE}")
print("  Done.")
