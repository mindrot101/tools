"""Compare two analysis jobs by unique packet content hash."""
from typing import Any, Dict

import storage


def compare(job_a: str, job_b: str) -> Dict[str, Any]:
    a = storage.packet_hashes(job_a, unique_only=True)
    b = storage.packet_hashes(job_b, unique_only=True)
    only_a, only_b, common = a - b, b - a, a & b
    union = len(a | b) or 1
    return {
        "job_a": job_a, "job_b": job_b,
        "a_unique": len(a), "b_unique": len(b),
        "only_in_a": len(only_a), "only_in_b": len(only_b),
        "common": len(common),
        "similarity": round(len(common) / union, 4),
        "sample_only_a": storage.sample_by_hashes(job_a, only_a, 25),
        "sample_only_b": storage.sample_by_hashes(job_b, only_b, 25),
    }
