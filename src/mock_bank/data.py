from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Account:
    type: str
    account_number: str
    balance: str


@dataclass(frozen=True)
class Member:
    member_id: str
    name: str
    status: str
    accounts: tuple[Account, ...]


MEMBERS: dict[str, Member] = {
    "12345": Member(
        member_id="12345",
        name="Alex Morgan",
        status="Active",
        accounts=(
            Account(type="Savings", account_number="S-1044", balance="$4,821.37"),
            Account(type="Checking", account_number="C-8821", balance="$1,205.12"),
        ),
    ),
    "67890": Member(
        member_id="67890",
        name="Jordan Lee",
        status="Active",
        accounts=(
            Account(type="Savings", account_number="S-2207", balance="$2,614.09"),
            Account(type="Checking", account_number="C-9013", balance="$734.51"),
        ),
    ),
}


# Synthetic IDs reserved for deterministic demo states.
NOT_FOUND_MEMBER_ID = "99999"
SLOW_MEMBER_ID = "55555"
PERMISSION_DENIED_MEMBER_ID = "77777"
