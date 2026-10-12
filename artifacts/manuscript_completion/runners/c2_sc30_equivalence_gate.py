#!/usr/bin/env python3
"""
c2_sc30_equivalence_gate.py — Post-merge historical equivalence check for C2 sc30

Compares sc30 full_fp and full_random at r=1.25 between:
  - Historical reference: gate_f_sc30-54_1p25_r3f2local.json (SHA-verified)
  - C2 merged output:     gate_f_sc30-54_1p25_c2manuscript.json

Comparison rules:
  - crossing dict: exact equality for str/bool/int; abs diff ≤ 1e-9 for float
  - lambda_rows: restrict to fields present in the historical reference before
    comparing (strips new cabinet-accounting fields added in C2); same numeric
    and exact-match rules apply row-by-row
  - Row counts must match
  - first_binding_constraint and status must match exactly

Exit codes: 0 = PASS, 1 = FAIL (any mismatch).
"""

import sys, json, hashlib, math
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
RESULTS   = REPO_ROOT / "artifacts" / "manuscript_completion" / "results"
REV3_RES  = REPO_ROOT / "artifacts" / "revision3" / "results"

_HIST_PATH = REV3_RES / "gate_f_sc30-54_1p25_r3f2local.json"
_HIST_SHA  = "5982264fcf719cc4746b23ae6ef0aaf9e22a9700e4b6ef3e19e49a98b5460dca"
_C2_PATH   = RESULTS  / "gate_f_sc30-54_1p25_c2manuscript.json"

_POLICIES  = ["full_fp", "full_random"]
_RATIO_KEY = "1.25"
_SC_IDX    = 30
_NUM_TOL   = 1e-9


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _get_sc30(data: dict) -> dict:
    for sc in data["scenario_results"]:
        if sc["scenario_idx"] == _SC_IDX:
            return sc
    raise KeyError(f"scenario_idx {_SC_IDX} not found")


def _compare_value(hist_val, c2_val, label: str) -> list[str]:
    """Return list of error strings (empty = match)."""
    if hist_val is None and c2_val is None:
        return []
    if isinstance(hist_val, float) or isinstance(c2_val, float):
        # numeric comparison
        try:
            hf = float(hist_val)
            cf = float(c2_val)
        except (TypeError, ValueError):
            return [f"{label}: cannot coerce to float — hist={hist_val!r} c2={c2_val!r}"]
        if math.isnan(hf) and math.isnan(cf):
            return []
        diff = abs(hf - cf)
        if diff > _NUM_TOL:
            return [f"{label}: numeric mismatch — hist={hf} c2={cf} diff={diff:.3e}"]
        return []
    # exact equality for str, int, bool, None
    if hist_val != c2_val:
        return [f"{label}: mismatch — hist={hist_val!r} c2={c2_val!r}"]
    return []


def _compare_crossing(hist_cross: dict, c2_cross: dict, prefix: str) -> list[str]:
    errors = []
    for key, hval in hist_cross.items():
        if key not in c2_cross:
            errors.append(f"{prefix}.crossing.{key}: missing from C2 output")
            continue
        errors.extend(_compare_value(hval, c2_cross[key], f"{prefix}.crossing.{key}"))
    return errors


def _compare_lambda_rows(hist_rows: list, c2_rows: list, prefix: str) -> list[str]:
    errors = []
    if len(hist_rows) != len(c2_rows):
        errors.append(
            f"{prefix}.lambda_rows: row count mismatch — "
            f"hist={len(hist_rows)} c2={len(c2_rows)}"
        )
        return errors

    # Fields defined by the historical reference; C2 may have extras (cabinet-accounting)
    hist_fields = set(hist_rows[0].keys()) if hist_rows else set()

    for i, (hr, cr) in enumerate(zip(hist_rows, c2_rows)):
        row_pfx = f"{prefix}.lambda_rows[{i}]"
        for field in hist_fields:
            if field not in cr:
                errors.append(f"{row_pfx}.{field}: missing from C2 row")
                continue
            errors.extend(_compare_value(hr[field], cr[field], f"{row_pfx}.{field}"))

    return errors


def main():
    errors_all = []

    # 1. SHA-verify historical reference
    if not _HIST_PATH.exists():
        print(f"[GATE FAIL] Historical reference not found: {_HIST_PATH}", file=sys.stderr)
        sys.exit(1)
    actual_sha = _sha256(_HIST_PATH)
    if actual_sha != _HIST_SHA:
        print(
            f"[GATE FAIL] Historical reference SHA256 mismatch\n"
            f"  expected: {_HIST_SHA}\n"
            f"  actual:   {actual_sha}",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"[OK] Historical reference SHA256 verified: {_HIST_SHA[:16]}...")

    # 2. Load C2 merged output
    if not _C2_PATH.exists():
        print(f"[GATE FAIL] C2 merged output not found: {_C2_PATH}", file=sys.stderr)
        sys.exit(1)
    print(f"[OK] C2 merged output found: {_C2_PATH.name}")

    hist_data = json.loads(_HIST_PATH.read_text())
    c2_data   = json.loads(_C2_PATH.read_text())

    hist_sc30 = _get_sc30(hist_data)
    c2_sc30   = _get_sc30(c2_data)

    # 3. Compare each policy
    for pol in _POLICIES:
        pfx = f"sc30.{_RATIO_KEY}.{pol}"

        hist_pol = hist_sc30["ratios"][_RATIO_KEY].get(pol)
        c2_pol   = c2_sc30["ratios"][_RATIO_KEY].get(pol)

        if hist_pol is None:
            errors_all.append(f"{pfx}: policy missing from historical reference")
            continue
        if c2_pol is None:
            errors_all.append(f"{pfx}: policy missing from C2 output")
            continue

        # crossing
        errors_all.extend(_compare_crossing(hist_pol["crossing"], c2_pol["crossing"], pfx))

        # lambda_rows
        errors_all.extend(
            _compare_lambda_rows(hist_pol["lambda_rows"], c2_pol["lambda_rows"], pfx)
        )

    # 4. Report
    print()
    if errors_all:
        print(f"[GATE FAIL] {len(errors_all)} mismatch(es):", file=sys.stderr)
        for e in errors_all:
            print(f"  MISMATCH: {e}", file=sys.stderr)
        sys.exit(1)
    else:
        print(f"[GATE PASS] sc30 equivalence verified — all fields match within tol={_NUM_TOL}")
        print(f"  Policies compared: {_POLICIES}")
        print(f"  Ratio: r={_RATIO_KEY}")
        print(f"  Crossing fields: exact str/bool/int, numeric diff <= {_NUM_TOL}")
        print(f"  Lambda rows: historical-field projection, same tolerance (<= {_NUM_TOL})")


if __name__ == "__main__":
    main()
