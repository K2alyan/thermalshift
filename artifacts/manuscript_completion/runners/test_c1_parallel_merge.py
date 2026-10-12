#!/usr/bin/env python3
"""
test_c1_parallel_merge.py — Merger validation tests (no new simulation required)

Tests use synthetic per-scenario JSON fixtures constructed from the sc5 result
extracted from the interrupted sequential run. All tests run without touching
THERMALSHIFT_DATA_DIR.

Run: python3 test_c1_parallel_merge.py
Exit: 0 if all tests pass, 1 if any fail.
"""

import sys, json, hashlib, subprocess, tempfile, shutil, os
from pathlib import Path

REPO_ROOT    = Path(__file__).resolve().parents[3]
RUNNERS      = Path(__file__).parent
MERGER       = RUNNERS / "c1_parallel_merge.py"
RUNNER       = RUNNERS / "c1_gate_f_run.py"
SEQ_REF      = REPO_ROOT / "artifacts" / "manuscript_completion" / "SEQUENTIAL_SC5_REFERENCE.json"
CKPT_FILE    = REPO_ROOT / "artifacts" / "manuscript_completion" / "INVALIDATED_C1_SEQUENTIAL_CHECKPOINT.json"

_RUNNER_SHA256       = "7cb51ebcf541d9c04b932ef879ce5095d34195452ef88151418d01ce844b41ba"
_F2_REFERENCE_SHA256 = "71de8abcd92cb8b800aecb401f1dc2a4edbcada8a971e72afa6491778d290c34"
_F2_DENOM_SHA256     = "b0594373af48fe6bb840ddc32c5628d7c3c26384e11c42fd58f4b9b27555ce48"
_FREEZE_COMMIT       = "e2df32a883fff8f26d93511483dfdae63fe0b730"

# ── Fixture construction ──────────────────────────────────────────────────────

def _load_sc5_result() -> dict:
    with open(SEQ_REF) as f:
        return json.load(f)


def _make_worker_json(sc_idx: int, sc_result: dict, overrides: dict = None) -> dict:
    """Build a synthetic per-scenario worker JSON (same schema as c1_gate_f_run.py output)."""
    d = {
        "git_commit_full":              "e44fedd1234567890abcdef1234567890abcdef12",
        "git_commit_short":             "e44fedd",
        "git_tracked_dirty":            False,
        "git_untracked_present":        True,
        "git_untracked_count":          3,
        "script":                       "c1_gate_f_run.py",
        "n_dev":                        1,
        "n_first":                      sc_idx,
        "gate_f_ratios":                ["1.0", "1.25", "1.5", "2.0", "4.0", "8.0", "unrestricted"],
        "gate_f_policies":              ["full_random", "full_fp", "full_loc", "full_fp_spread"],
        "lambda_sweep":                 [1.00, 1.06, 1.10, 1.15, 1.20, 1.30, 1.40,
                                         1.50, 1.55, 1.60, 1.70, 1.80, 1.90, 2.00],
        "target_pp":                    0.50,
        "cabinet_reference_mode":       "corrected_timeweighted_total_p99_local",
        "f2_reference_sha256":          _F2_REFERENCE_SHA256,
        "f2_replay_denominator_sha256": _F2_DENOM_SHA256,
        "B_cab_hist_F2_replay_h":       871.3691666666647,
        "scientific_freeze_commit":     _FREEZE_COMMIT,
        "scenario_results":             [dict(sc_result, scenario_idx=sc_idx)],
        "elapsed_total_s":              3000.0,
    }
    if overrides:
        d.update(overrides)
    return d


# ── Test harness ──────────────────────────────────────────────────────────────

_passed = 0
_failed = 0


def _run_merger(tmp: Path, files: list[Path], n_first: int, n_dev: int,
                extra_args: list = None) -> tuple[int, str]:
    """Run the merger and return (returncode, combined stdout+stderr)."""
    out_path = tmp / "merged_output.json"
    cmd = [
        sys.executable, str(MERGER),
        "--files", *[str(f) for f in files],
        "--n-first", str(n_first),
        "--n-dev",   str(n_dev),
        "--out",     str(out_path),
    ] + (extra_args or [])
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
    out = r.stdout + r.stderr
    return r.returncode, out, out_path


def test(name: str, expect_pass: bool, files_fn, n_first: int, n_dev: int,
         extra_args=None, post_check=None):
    """
    post_check(tmp, out_path) -> optional extra assertions run while tmp is still alive.
    """
    global _passed, _failed
    with tempfile.TemporaryDirectory() as tmp_str:
        tmp = Path(tmp_str)
        files = files_fn(tmp)
        rc, out, out_path = _run_merger(tmp, files, n_first, n_dev, extra_args)
        passed = (rc == 0) == expect_pass
        symbol = "[PASS]" if passed else "[FAIL]"
        result = "pass" if rc == 0 else "fail"
        expected = "pass" if expect_pass else "fail"

        # Run post-check while tmp dir is still alive
        extra_ok = True
        if passed and post_check and rc == 0:
            try:
                post_check(tmp, out_path)
            except Exception as exc:
                passed = False
                extra_ok = False
                symbol = "[FAIL]"
                out += f"\n  post_check exception: {exc}"

        print(f"  {symbol} {name}  (expected={expected}, got={result})")
        if not passed or not extra_ok:
            _failed += 1
            for line in out.splitlines()[-6:]:
                print(f"           {line}")
        else:
            _passed += 1
    return passed


# ── Individual tests ──────────────────────────────────────────────────────────

def main():
    sc5 = _load_sc5_result()

    print("\n=== C1 Parallel Merge — Validation Tests ===\n")

    # ── T1: Single valid sc5 file — should PASS ───────────────────────────────
    def t1_files(tmp):
        d = _make_worker_json(5, sc5)
        p = tmp / "gate_f_sc5-5_all.json"
        p.write_text(json.dumps(d))
        return [p]
    test("T1: single valid sc5 file", expect_pass=True, files_fn=t1_files,
         n_first=5, n_dev=1)

    # ── T2: Two valid files sc5+sc6 merged to sc5-6 ───────────────────────────
    def t2_files(tmp):
        files = []
        for sc in [5, 6]:
            d = _make_worker_json(sc, sc5)
            p = tmp / f"gate_f_sc{sc}-{sc}_all.json"
            p.write_text(json.dumps(d))
            files.append(p)
        return files
    def t2_check(tmp, out_path):
        with open(out_path) as f:
            m = json.load(f)
        sc_idxs = [s["scenario_idx"] for s in m["scenario_results"]]
        assert sc_idxs == [5, 6], f"Expected sorted [5,6], got {sc_idxs}"
        assert m["n_first"] == 5 and m["n_dev"] == 2
        print(f"         scenario_idx order verified: {sc_idxs}")
    test("T2: two valid files sc5+sc6 -> sc5-6 merged, sorted", expect_pass=True,
         files_fn=t2_files, n_first=5, n_dev=2, post_check=t2_check)

    # ── T3: Duplicate scenario_idx — should FAIL ──────────────────────────────
    def t3_files(tmp):
        files = []
        for i in range(2):
            d = _make_worker_json(5, sc5)
            p = tmp / f"dup_{i}.json"
            p.write_text(json.dumps(d))
            files.append(p)
        return files
    test("T3: duplicate scenario_idx rejected", expect_pass=False,
         files_fn=t3_files, n_first=5, n_dev=2)

    # ── T4: Missing scenario (only sc5, but n_dev=2 expects sc5+sc6) — FAIL ──
    def t4_files(tmp):
        d = _make_worker_json(5, sc5)
        p = tmp / "gate_f_sc5-5_all.json"
        p.write_text(json.dumps(d))
        return [p]
    test("T4: missing scenario_idx rejected (sc6 absent)", expect_pass=False,
         files_fn=t4_files, n_first=5, n_dev=2)

    # ── T5: Scenario outside sc5–29 (sc30 given but n_first=5,n_dev=25) — FAIL
    def t5_files(tmp):
        d = _make_worker_json(30, sc5)
        p = tmp / "gate_f_sc30-30_all.json"
        p.write_text(json.dumps(d))
        return [p]
    test("T5: out-of-range scenario_idx rejected (sc30 in sc5-29 range)", expect_pass=False,
         files_fn=t5_files, n_first=5, n_dev=25)

    # ── T6: Wrong f2_reference_sha256 — should FAIL ───────────────────────────
    def t6_files(tmp):
        d = _make_worker_json(5, sc5, overrides={"f2_reference_sha256": "deadbeef" * 8})
        p = tmp / "gate_f_sc5-5_all.json"
        p.write_text(json.dumps(d))
        return [p]
    test("T6: f2_reference_sha256 mismatch rejected", expect_pass=False,
         files_fn=t6_files, n_first=5, n_dev=1)

    # ── T7: Wrong f2_replay_denominator_sha256 — should FAIL ─────────────────
    def t7_files(tmp):
        d = _make_worker_json(5, sc5, overrides={"f2_replay_denominator_sha256": "cafebabe" * 8})
        p = tmp / "gate_f_sc5-5_all.json"
        p.write_text(json.dumps(d))
        return [p]
    test("T7: f2_replay_denominator_sha256 mismatch rejected", expect_pass=False,
         files_fn=t7_files, n_first=5, n_dev=1)

    # ── T8: git_tracked_dirty = True — should FAIL ────────────────────────────
    def t8_files(tmp):
        d = _make_worker_json(5, sc5, overrides={"git_tracked_dirty": True})
        p = tmp / "gate_f_sc5-5_all.json"
        p.write_text(json.dumps(d))
        return [p]
    test("T8: dirty-run metadata rejected (git_tracked_dirty=True)", expect_pass=False,
         files_fn=t8_files, n_first=5, n_dev=1)

    # ── T9: Wrong script name — should FAIL ───────────────────────────────────
    def t9_files(tmp):
        d = _make_worker_json(5, sc5, overrides={"script": "some_other_runner.py"})
        p = tmp / "gate_f_sc5-5_all.json"
        p.write_text(json.dumps(d))
        return [p]
    test("T9: wrong script name rejected", expect_pass=False,
         files_fn=t9_files, n_first=5, n_dev=1)

    # ── T10: Wrong scientific_freeze_commit — should FAIL ─────────────────────
    def t10_files(tmp):
        d = _make_worker_json(5, sc5, overrides={"scientific_freeze_commit": "0000000"})
        p = tmp / "gate_f_sc5-5_all.json"
        p.write_text(json.dumps(d))
        return [p]
    test("T10: wrong scientific_freeze_commit rejected", expect_pass=False,
         files_fn=t10_files, n_first=5, n_dev=1)

    # ── T11: git_commit_full mismatch across workers — should FAIL ────────────
    def t11_files(tmp):
        files = []
        for i, sc in enumerate([5, 6]):
            commit = "aaaaaaaabbbbbbbbccccccccddddddddeeeeeeee" if i == 0 else "ffffffffffffffffffffffffffffffffffffffff"
            d = _make_worker_json(sc, sc5, overrides={"git_commit_full": commit})
            p = tmp / f"sc{sc}.json"
            p.write_text(json.dumps(d))
            files.append(p)
        return files
    test("T11: git_commit_full mismatch across workers rejected", expect_pass=False,
         files_fn=t11_files, n_first=5, n_dev=2)

    # ── T12: Results are byte-for-byte preserved in merged output ─────────────
    def t12_files(tmp):
        files = []
        for sc in [5, 6]:
            d = _make_worker_json(sc, sc5)
            p = tmp / f"sc{sc}.json"
            p.write_text(json.dumps(d))
            files.append(p)
        return files
    def t12_check(tmp, out_path):
        with open(out_path) as f:
            m = json.load(f)
        merged_sc5 = next(s for s in m["scenario_results"] if s["scenario_idx"] == 5)
        assert merged_sc5["ratios"] == sc5["ratios"], "Ratios not preserved byte-for-byte"
        assert merged_sc5["scen_seed"] == sc5["scen_seed"]
        assert merged_sc5["B_ref_s"] == sc5["B_ref_s"]
        print(f"         Scientific fields preserved exactly in merged output")
    test("T12: scenario fields preserved byte-for-byte after merge", expect_pass=True,
         files_fn=t12_files, n_first=5, n_dev=2, post_check=t12_check)

    # ── T13: Dry-run mode validates without writing ────────────────────────────
    def t13_files(tmp):
        d = _make_worker_json(5, sc5)
        p = tmp / "gate_f_sc5-5_all.json"
        p.write_text(json.dumps(d))
        return [p]
    def _t13(tmp):
        files = t13_files(tmp)
        # Run with --dry-run; output file must not exist afterward
        out_path = tmp / "merged_output.json"
        cmd = [sys.executable, str(MERGER),
               "--files", str(files[0]),
               "--n-first", "5", "--n-dev", "1",
               "--out", str(out_path), "--dry-run"]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT))
        if r.returncode != 0:
            print(f"         dry-run failed: {r.stderr}")
            return False
        if out_path.exists():
            print(f"         dry-run wrote output file — should not have")
            return False
        print(f"         dry-run passed, no file written")
        return True
    global _passed, _failed
    if _t13(Path(tempfile.mkdtemp())):
        print(f"  [PASS] T13: dry-run validates without writing output")
        _passed += 1
    else:
        print(f"  [FAIL] T13: dry-run validates without writing output")
        _failed += 1

    # ── Summary ───────────────────────────────────────────────────────────────
    total = _passed + _failed
    print(f"\n=== Results: {_passed}/{total} passed ===")
    if _failed:
        print(f"FAILED: {_failed} test(s)")
        sys.exit(1)
    else:
        print("All merger validation tests PASSED.")


if __name__ == "__main__":
    main()
