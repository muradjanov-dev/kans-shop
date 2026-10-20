"""Customer-facing transfer requisites for a `card_transfer` order.

The store keeps a single pair of transfer requisites (`card_number`, `card_holder`). Kans Shop
receives transfers to its company bank account: Uzbek bank account numbers are 20 digits,
payment cards are 16. A bank transfer needs different wording, a payment purpose and steps.
"""

import re
from collections.abc import Callable

_BANK_ACCOUNT = re.compile(r"\d{20}")


def is_bank_account(number: object) -> bool:
    if not isinstance(number, str):
        return False
    return _BANK_ACCOUNT.fullmatch(re.sub(r"[\s-]", "", number)) is not None


def transfer_details_text(
    translator: Callable[..., str],
    *,
    number: str,
    holder: str,
    total: str,
    order_number: str | None = None,
) -> str:
    if not is_bank_account(number):
        return translator(
            "checkout.card_details", card_number=number, card_holder=holder, total=total
        )
    purpose = (
        translator("checkout.bank_purpose_order", number=order_number)
        if order_number
        else translator("checkout.bank_purpose_generic")
    )
    return translator(
        "checkout.bank_details",
        card_number=number,
        card_holder=holder,
        total=total,
        purpose=purpose,
    )
