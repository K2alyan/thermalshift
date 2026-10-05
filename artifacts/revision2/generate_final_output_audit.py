#!/usr/bin/env python3
"""
Phase I — Final Output Audit (§13).

Verifies all 13 required Phase I artifacts exist, records SHA256 for each.
Also records additional provenance fields:
  - sensitivity runner SHA256
  - sensitivity baseline equivalence PASS status
  - post-exposure governance recovery note SHA256
  - explicit post-exposure disclosure field
  - beta_jackknife_recovery.json provenance

Writes: artifacts/revision2/final_output_audit.json

Per §13, this is artifact #13 itself; it self-certifies via its own content.
This script is idempotent; running it again regenerates the audit.
"""
import sys, io, json, hashlib, datetime
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

REPO_ROOT = Path(__file__).resolve().parents[2]
REV2_DIR  = REPO_ROOT / "artifacts" / "revision2"
RES       = REV2_DIR / "results"

def sha256(path: Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        return None

def check(path: Path) -> dict:
    exists = path.exists()
    return {
        "path": str(path.relative_to(REPO_ROOT)),
        "exists": exists,
        "sha256": sha256(path) if exists else None,
    }

print("=== Phase I Final Output Audit (§13) ===")
print("Artifacts 1–12: prerequisite evidence artifacts.")
print("Artifact 13: this file (final_output_audit.json) — verifies 1–12 and records SHA256s.")
print()

# ── 12 required artifacts (plan §13 items 1–12) ───────────────────────────────
# Item 9 in plan says "gate_f_sc30-54_r2challenge.json"; actual file is the merged variant.
# Record both the plan name and the actual file found.
REQUIRED = [
    (1,  "REVIEW2_CHALLENGE_PLAN.md",               REV2_DIR / "REVIEW2_CHALLENGE_PLAN.md"),
    (2,  "cabinet_timeline_audit.json",              REV2_DIR / "cabinet_timeline_audit.json"),
    (3,  "cabinet_timeline_audit.md",               REV2_DIR / "cabinet_timeline_audit.md"),
    (4,  "prospective_accuracy_by_job_size.json",   REV2_DIR / "prospective_accuracy_by_job_size.json"),
    (5,  "m1_sensitivity_summary.json",             REV2_DIR / "m1_sensitivity_summary.json"),
    (6,  "gate_f_manuscript_tables.json",           REV2_DIR / "gate_f_manuscript_tables.json"),
    (7,  "loo_beta_results.json",                   REV2_DIR / "loo_beta_results.json"),
    (8,  "challenge_preflight.json",                REV2_DIR / "challenge_preflight.json"),
    (9,  "results/gate_f_sc30-54_all_r2challenge_merged.json",
                                                    RES / "gate_f_sc30-54_all_r2challenge_merged.json"),
    (10, "challenge_analysis.json",                 REV2_DIR / "challenge_analysis.json"),
    (11, "sensitivity_cabinet_scale.json",          REV2_DIR / "sensitivity_cabinet_scale.json"),
    (12, "sensitivity_loo_beta.json",               REV2_DIR / "sensitivity_loo_beta.json"),
]

items = []
all_present = True
for item_no, label, path in REQUIRED:
    entry = check(path)
    entry["item"] = item_no
    entry["label"] = label
    items.append(entry)
    status = "OK" if entry["exists"] else "MISSING"
    if not entry["exists"]:
        all_present = False
    print(f"  [{status:>7}] {item_no:>2}. {label}")
    if entry["sha256"]:
        print(f"            SHA256: {entry['sha256']}")

print()

# ── Additional provenance fields ──────────────────────────────────────────────
sens_runner_path  = REV2_DIR / "r2_sensitivity_run.py"
equiv_path        = REV2_DIR / "sensitivity_runner_equivalence.json"
jackknife_path    = REV2_DIR / "beta_jackknife_recovery.json"
recovery_doc_path = REV2_DIR / "POST_EXPOSURE_SENSITIVITY_RECOVERY.md"

sens_runner_sha = sha256(sens_runner_path)
print(f"  Sensitivity runner SHA256: {sens_runner_sha}")

# Equivalence pass status
equiv_pass = None
equiv_sha  = sha256(equiv_path)
if equiv_path.exists():
    eq = json.loads(equiv_path.read_text())
    equiv_pass = eq.get("status") == "PASS"
    print(f"  Equivalence check: {eq.get('status')} (SHA256: {equiv_sha})")
else:
    print("  Equivalence check: MISSING")

# Jackknife recovery
jackknife_sha = sha256(jackknife_path)
jackknife_mean = None
jackknife_xcheck_pass = None
if jackknife_path.exists():
    jk = json.loads(jackknife_path.read_text())
    jackknife_mean = jk.get("BETA_F_JACKKNIFE_MEAN")
    jackknife_xcheck_pass = jk.get("cross_check", {}).get("pass")
    print(f"  BETA_F_JACKKNIFE_MEAN: {jackknife_mean:.8f}  cross_check={'PASS' if jackknife_xcheck_pass else 'FAIL'}")

recovery_doc_sha = sha256(recovery_doc_path)
print(f"  POST_EXPOSURE_SENSITIVITY_RECOVERY.md SHA256: {recovery_doc_sha}")

print()

# ── Overall status ─────────────────────────────────────────────────────────────
phase_i_pass = (all_present and equiv_pass is True and jackknife_xcheck_pass is True)
status_str   = "PASS" if phase_i_pass else "FAIL"

n_present = sum(1 for e in items if e["exists"])
n_expected = len(items)  # 12 prerequisite artifacts

print(f"Phase I audit: {status_str}")
print(f"  {n_present}/{n_expected} prerequisite artifacts verified; "
      f"final_output_audit.json generated as artifact 13 — "
      f"{n_present + (1 if phase_i_pass else 0)}/13 Phase-I outputs complete.")
if not all_present:
    missing = [e["label"] for e in items if not e["exists"]]
    print(f"  MISSING artifacts: {missing}")
if equiv_pass is False:
    print("  Equivalence check: FAIL — sensitivity runner is not equivalent to frozen challenge")
if equiv_pass is None:
    print("  Equivalence check: NOT FOUND — run check_sensitivity_equivalence.py first")
if jackknife_xcheck_pass is False:
    print("  Jackknife cross-check: FAIL — beta recovery did not reproduce stored FE slope")

result = {
    "script": "artifacts/revision2/generate_final_output_audit.py",
    "plan_ref": "REVIEW2_CHALLENGE_PLAN.md §13",
    "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    "phase_i_overall": status_str,
    "n_prerequisite_artifacts_expected": n_expected,
    "n_prerequisite_artifacts_present": n_present,
    "prerequisite_artifacts_pass": all_present,
    "final_output_audit_generated": True,
    "n_phase_i_outputs_total": 13,
    "phase_i_outputs_complete": n_present + (1 if phase_i_pass else 0),
    "phase_i_complete": phase_i_pass,
    "phase_i_artifact_summary": (
        f"{n_present}/{n_expected} prerequisite artifacts verified; "
        f"final_output_audit.json generated as artifact 13 — "
        f"{n_present + (1 if phase_i_pass else 0)}/13 Phase-I outputs complete."
    ),
    "required_artifacts": items,
    "additional_provenance": {
        "sensitivity_runner_sha256": sens_runner_sha,
        "sensitivity_runner_path": str(sens_runner_path.relative_to(REPO_ROOT)),
        "sensitivity_equivalence_status": "PASS" if equiv_pass else ("FAIL" if equiv_pass is False else "MISSING"),
        "sensitivity_equivalence_sha256": equiv_sha,
        "beta_jackknife_recovery_sha256": jackknife_sha,
        "BETA_F_JACKKNIFE_MEAN": jackknife_mean,
        "jackknife_cross_check_pass": jackknife_xcheck_pass,
        "post_exposure_recovery_doc_sha256": recovery_doc_sha,
    },
    "post_exposure_disclosure": (
        "Phase E1 and E2 sensitivity analyses were prespecified and design-frozen at "
        "Git commit 5733b73, before any challenge scenario (sc30-sc54) was executed. "
        "However, execution occurred after primary challenge results (Phase G) were "
        "exposed, due to an omission discovered during post-analysis review. "
        "This is disclosed explicitly per POST_EXPOSURE_SENSITIVITY_RECOVERY.md. "
        "The analysis design (parameters, scenarios, comparisons, and interpretation "
        "rules) was not changed after primary-result exposure."
    ),
}

out_path = REV2_DIR / "final_output_audit.json"
out_path.write_text(json.dumps(result, indent=2))
print(f"\nWritten: {out_path}")
print(f"SHA256: {sha256(out_path)}")
