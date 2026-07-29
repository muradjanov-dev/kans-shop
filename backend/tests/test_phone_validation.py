import pytest

from app.bot.utils.helpers import is_valid_uz_phone, normalize_uz_phone


@pytest.mark.parametrize(
    "raw",
    [
        "+998901234567",
        "+998911234567",
        "+998331234567",
        "+998881234567",
        "+998771234567",
        "+998711234567",
    ],
)
def test_valid_uz_phone_accepted(raw: str) -> None:
    assert is_valid_uz_phone(raw) is True


@pytest.mark.parametrize(
    "raw",
    [
        "+998001234567",  # invalid operator prefix
        "+99890123456",  # too short
        "+9989012345678",  # too long
        "+998123456789",  # invalid operator prefix (12)
        "not a phone",
        "",
    ],
)
def test_invalid_uz_phone_rejected(raw: str) -> None:
    assert is_valid_uz_phone(raw) is False


def test_normalize_adds_country_code_for_local_number() -> None:
    assert normalize_uz_phone("901234567") == "+998901234567"


def test_normalize_strips_formatting() -> None:
    assert normalize_uz_phone("+998 90 123 45 67") == "+998901234567"
    assert normalize_uz_phone("+998 (90) 123-45-67") == "+998901234567"


def test_local_number_becomes_valid_after_normalization() -> None:
    assert is_valid_uz_phone("901234567") is True
