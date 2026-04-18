"""Shared utilities used across atlas modules."""

import hashlib
import re


def claim_canonical(claim: str) -> str:
    """Normalize claim text to a canonical form before hashing.

    Lowercase, collapse whitespace, strip trailing punctuation.
    """
    s = claim.strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[.!?,]+$", "", s)
    return s


def claim_hash(claim: str) -> str:
    """Canonical claim → hypothesis ID. [:16] of SHA-256."""
    return hashlib.sha256(claim_canonical(claim).encode()).hexdigest()[:16]
