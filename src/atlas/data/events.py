"""Curated structured events dataset — Phase B1.

Small, high-trust seed of timestamped crypto events for event-study use.
Each entry has: date (UTC), category, asset scope, and a short descriptor.
Dates are the commonly-cited effective date, not anticipation date. Callers
doing event studies should decide for themselves whether to use the event
date or shift to an announcement date.

This is a curated file — not a fetched feed. Add new events deliberately
after verifying the date from at least one primary source. Avoid speculative
events; we want precision over recall.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class Event:
    date: datetime           # UTC, midnight unless a more specific time is known
    category: str            # halving, fork, merge, regulatory, collapse, listing, outage, macro
    scope: tuple[str, ...]   # asset symbols affected, e.g. ("BTC",) or ("BTC","ETH")
    label: str               # short descriptor
    source: str              # primary-source citation (URL or exchange/gov body)


def _d(y: int, m: int, d: int) -> datetime:
    return datetime(y, m, d, tzinfo=timezone.utc)


# Curated list. If you add an entry, cite a primary source in `source`.
EVENTS: list[Event] = [
    # --- BTC halvings (supply shocks; dates from blockchain) ---
    Event(_d(2016, 7, 9),  "halving",    ("BTC",),        "BTC 2nd halving (block 420000)", "blockchain"),
    Event(_d(2020, 5, 11), "halving",    ("BTC",),        "BTC 3rd halving (block 630000)", "blockchain"),
    Event(_d(2024, 4, 20), "halving",    ("BTC",),        "BTC 4th halving (block 840000)", "blockchain"),

    # --- Protocol milestones ---
    Event(_d(2017, 8, 1),  "fork",       ("BTC",),        "Bitcoin Cash fork",              "bitcoincash.org"),
    Event(_d(2022, 9, 15), "merge",      ("ETH",),        "Ethereum Merge (PoS transition)", "ethereum.org"),
    Event(_d(2023, 4, 12), "fork",       ("ETH",),        "Shapella (withdrawal enablement)", "ethereum.org"),
    Event(_d(2024, 3, 13), "fork",       ("ETH",),        "Dencun (EIP-4844 blobs)",        "ethereum.org"),

    # --- Regulatory / listing events ---
    Event(_d(2021, 4, 14), "listing",    ("BTC","ETH"),   "Coinbase direct listing on NASDAQ", "sec.gov"),
    Event(_d(2024, 1, 10), "regulatory", ("BTC",),        "US spot BTC ETF approvals",       "sec.gov"),
    Event(_d(2024, 5, 23), "regulatory", ("ETH",),        "US spot ETH ETF 19b-4 approvals", "sec.gov"),
    Event(_d(2023, 6, 5),  "regulatory", ("BTC","ETH"),   "SEC sues Binance",                "sec.gov"),
    Event(_d(2023, 6, 6),  "regulatory", ("BTC","ETH"),   "SEC sues Coinbase",               "sec.gov"),

    # --- Collapses / cascades ---
    Event(_d(2020, 3, 12), "macro",      ("BTC","ETH"),   "COVID crash (Black Thursday)",    "market wide"),
    Event(_d(2022, 5, 9),  "collapse",   ("BTC","ETH"),   "Terra/Luna UST depeg begins",     "market wide"),
    Event(_d(2022, 6, 13), "collapse",   ("BTC","ETH"),   "Celsius withdrawal freeze",       "celsius.network"),
    Event(_d(2022, 11, 8), "collapse",   ("BTC","ETH"),   "FTX solvency crisis begins",      "market wide"),
    Event(_d(2023, 3, 10), "macro",      ("BTC","ETH"),   "SVB collapse / USDC depeg",       "market wide"),
]


def events_in_scope(asset: str, category: str | None = None) -> list[Event]:
    """Filter events affecting `asset`, optionally restricted to a category."""
    out = [e for e in EVENTS if asset in e.scope]
    if category is not None:
        out = [e for e in out if e.category == category]
    return sorted(out, key=lambda e: e.date)
