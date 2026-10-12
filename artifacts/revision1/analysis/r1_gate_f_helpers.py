#!/usr/bin/env python3
"""
Gate F helper functions: BLAKE2b node priority, event UIDs, shortlist construction.

Frozen definitions from GATE_F_DESIGN.md §4.2–§4.4. No data dependency.
"""

import hashlib
import math


def choice_priority(scenario_seed: int, event_uid: str, hostname: str) -> tuple:
    """
    Returns (uint64_priority, hostname) sort key.
    Sort ascending: lowest value → first in shortlist.
    Canonical definition: §4.2 GATE_F_DESIGN.md.
    """
    key = scenario_seed.to_bytes(8, "big", signed=False)
    msg = event_uid.encode("utf-8") + b"\x00" + hostname.encode("utf-8")
    digest = hashlib.blake2b(msg, key=key, digest_size=8).digest()
    return int.from_bytes(digest, "big"), hostname


def make_event_uid(job_type: str, *, job_idx: int = None,
                   scenario_seed: int = None, generation_ordinal: int = None) -> str:
    """
    Returns frozen event_uid string for a scheduling event (§4.3).
    job_type: 'base' or 'syn'.
    """
    if job_type == "base":
        return f"base:{job_idx}"
    if job_type == "syn":
        return f"syn:{scenario_seed}:{generation_ordinal}"
    raise ValueError(f"Unknown job_type: {job_type!r}")


def syn_generation_ordinal(job_idx: int) -> int:
    """
    Converts synthetic job_idx (negative: -(i+1)) to generation_ordinal (0-based: i).
    Matches sample_synthetic_pool: job_idx = -(np.arange(len(syn)) + 1).
    """
    return abs(job_idx) - 1


def gate_f_shortlist(full_eligible, scenario_seed: int, event_uid: str, r, k: int) -> list:
    """
    Returns Gate F shortlist C_p,r from full_eligible (A_full,p).
    full_eligible: iterable of hostnames; must satisfy |full_eligible| >= k.
    r: float for restricted ratios; None or float('inf') for unrestricted.
    k: job cohort node count.
    Returns ordered list of hostnames (ascending hash priority).
    """
    ordered = sorted(full_eligible, key=lambda h: choice_priority(scenario_seed, event_uid, h))
    if r is None or (isinstance(r, float) and math.isinf(r)):
        return ordered  # C_p,unrestricted = A_full,p
    m = min(len(ordered), math.ceil(r * k))
    return ordered[:m]
