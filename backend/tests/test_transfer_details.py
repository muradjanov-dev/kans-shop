import pytest

from app.bot.utils.i18n import SUPPORTED_LANGUAGES, translate
from app.bot.utils.transfer_details import is_bank_account, transfer_details_text

ACCOUNT = "20208000600999115001"
HOLDER = '"KANS SHOP" MCHJ, STIR 306089114, MFO 01183'


@pytest.mark.parametrize(
    ("number", "expected"),
    [
        (ACCOUNT, True),
        ("2020 8000 6009 9911 5001", True),
        ("8600 1234 5678 9012", False),
        ("8600123456789012", False),
        ("", False),
        (None, False),
    ],
)
def test_is_bank_account(number: object, expected: bool) -> None:
    assert is_bank_account(number) is expected


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_bank_account_gets_bank_transfer_steps_and_order_purpose(lang: str) -> None:
    def translator(key: str, **kwargs: object) -> str:
        return translate(lang, key, **kwargs)

    text = transfer_details_text(
        translator, number=ACCOUNT, holder=HOLDER, total="250 000", order_number="KANS-000043"
    )

    assert ACCOUNT in text
    assert HOLDER in text
    assert "250 000" in text
    assert "KANS-000043" in text
    assert text != translator(
        "checkout.card_details", card_number=ACCOUNT, card_holder=HOLDER, total="250 000"
    )
    assert "{" not in text


def test_bank_account_without_order_uses_generic_purpose() -> None:
    def translator(key: str, **kwargs: object) -> str:
        return translate("uz", key, **kwargs)

    text = transfer_details_text(translator, number=ACCOUNT, holder=HOLDER, total="1")

    assert "Bank hisob raqami" in text
    assert translate("uz", "checkout.bank_purpose_generic") in text


def test_card_number_keeps_card_wording() -> None:
    def translator(key: str, **kwargs: object) -> str:
        return translate("uz", key, **kwargs)

    text = transfer_details_text(
        translator, number="8600 1234 5678 9012", holder="Kans Shop", total="1"
    )

    assert text == translate(
        "uz",
        "checkout.card_details",
        card_number="8600 1234 5678 9012",
        card_holder="Kans Shop",
        total="1",
    )
