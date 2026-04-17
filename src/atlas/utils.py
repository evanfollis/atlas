"""Shared utilities used across atlas modules."""

import hashlib


def claim_hash(claim: str) -> str:
    """Canonical claim → hypothesis ID. [:16] of SHA-256.

    Uses strip() to normalize whitespace before hashing — both runner and
    ingest paths must produce identical IDs for the same claim text.
    """
    return hashlib.sha256(claim.strip().encode()).hexdigest()[:16]
