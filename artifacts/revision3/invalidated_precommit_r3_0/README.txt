INVALID FOR EVIDENCE — R3-0 began after an uncommitted import-path-only runner modification. No corrected-reference result was produced. Preserved solely for audit history.

Details:
- Runner committed at 6ee64b2 (SHA256: 4223f201cf5c925920b61bad7871c85d4d6784101d153e8abf453a73b09c11bf)
- Committed runner failed: ModuleNotFoundError: No module named 'r2_selectors'
- Runner was modified (sys.path insert for revision2/) and NOT recommitted before execution
- Run terminated after sc30 and sc31 completed (2/25 scenarios)
- This checkpoint must NOT be resumed by any valid R3-0 run
- The valid R3-0 run must start from scratch with the committed runner
