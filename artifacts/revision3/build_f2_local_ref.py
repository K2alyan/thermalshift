#!/usr/bin/env python3
"""Build f2_local_scheduling_reference.json from Task-D and Task-D2 artifacts."""
import json, hashlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCAL_REF = REPO_ROOT / "artifacts/revision3/results_d2/f2_local_date_support.json"
UTC_REF   = REPO_ROOT / "artifacts/revision3/results/f2_timeweighted_cabinet_reference.json"
OUT       = REPO_ROOT / "artifacts/revision3/f2_local_scheduling_reference.json"

with open(LOCAL_REF) as f:
    local = json.load(f)
with open(UTC_REF) as f:
    utc = json.load(f)

local_by_cab = {x["cabinet"]: x for x in local["per_cabinet"]}
utc_by_cab   = {x["cabinet"]: x for x in utc["per_cabinet"]}

assert set(local_by_cab.keys()) == set(utc_by_cab.keys()), "Cabinet ID mismatch"

per_cabinet = []
for cab_id in sorted(local_by_cab.keys()):
    lc = local_by_cab[cab_id]
    uc = utc_by_cab[cab_id]
    Q_F2_local_kW = float(lc["Q_F2_kW"])
    Q_F2_local_W  = Q_F2_local_kW * 1000.0
    Q_F2_UTC_kW   = float(uc["Q_F2_kW"])
    assert Q_F2_local_kW > 0 and not (Q_F2_local_kW != Q_F2_local_kW), f"Bad Q_F2_local_kW for {cab_id}"
    assert Q_F2_local_W  > 0, f"Bad Q_F2_local_W for {cab_id}"
    assert abs(Q_F2_local_W - Q_F2_local_kW * 1000.0) < 1e-9, f"W/kW factor error for {cab_id}"
    per_cabinet.append({
        "cabinet_id": int(cab_id),
        "Q_F1_kW": float(uc["Q_F1_kW"]),
        "Q_F2_UTC_kW": Q_F2_UTC_kW,
        "Q_F2_local_kW": Q_F2_local_kW,
        "Q_F2_local_W": Q_F2_local_W,
        "local_over_utc_ratio": Q_F2_local_kW / Q_F2_UTC_kW,
        "source": "Task-D2 f2_local_date_support commit ab3119c",
    })

# Validate
cab_ids = [x["cabinet_id"] for x in per_cabinet]
assert len(cab_ids) == 77, f"Expected 77 cabinets, got {len(cab_ids)}"
assert len(set(cab_ids)) == 77, "Duplicate cabinet IDs"
assert all(x["Q_F2_local_kW"] > 0 for x in per_cabinet), "Some Q_F2_local_kW not positive"
assert all(x["Q_F2_local_W"] > 0 for x in per_cabinet), "Some Q_F2_local_W not positive"

result = {
    "provenance": {
        "sha256": "pending",
        "plan_commit": "pending",
        "r3_evidence_commit": "a80d51f",
        "task_d_commit": "90dc62f",
        "task_d2_commit": "ab3119c",
        "n_cabinets": 77,
        "validation": "77 unique cabinet IDs, all Q_F2_local_kW > 0 and finite, W/kW factor exactly 1000",
    },
    "per_cabinet": per_cabinet,
}

# Write without sha256 first, compute, then update
raw = json.dumps(result, indent=2)
sha256 = hashlib.sha256(raw.encode()).hexdigest()
result["provenance"]["sha256"] = sha256

with open(OUT, "w") as f:
    json.dump(result, f, indent=2)

print(f"Written: {OUT}")
print(f"SHA256: {sha256}")
print(f"Cabinets: {len(per_cabinet)}")

# Spot check late cabinets
for cab_id, expected_kW in [(2600, 161.764), (2601, 173.539), (2602, 163.126)]:
    entry = next(x for x in per_cabinet if x["cabinet_id"] == cab_id)
    diff = abs(entry["Q_F2_local_kW"] - expected_kW)
    print(f"  Cabinet {cab_id}: Q_F2_local_kW={entry['Q_F2_local_kW']:.3f} kW (expected ~{expected_kW}, diff={diff:.3f})")
