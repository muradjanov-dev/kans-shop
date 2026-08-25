"""Guards against the failure mode `translate()` is built for: a missing key is returned
verbatim, so a typo ships as literal `checkout.pay_button` text in a customer's chat rather
than raising anywhere. These tests turn that into a test failure instead.
"""

import json
import re
from pathlib import Path

import pytest

from app.bot.utils.i18n import SUPPORTED_LANGUAGES, translate

LOCALES_DIR = Path(__file__).resolve().parents[1] / "app" / "locales"
APP_DIR = Path(__file__).resolve().parents[1] / "app"

# Keys built at runtime from a variable part (f"admin.product_field_{field}" and friends).
# Listed here so the "referenced in code" sweep below can skip the f-string it cannot resolve.
DYNAMIC_KEY_PREFIXES = (
    "admin.product_field_",
    "checkout.payment_",
    "admin.payment_",
    "orders.status_",
    "checkout.type_",
    "admin.source_status_",
    "units.",
)


def _load(lang: str) -> dict:
    return json.loads((LOCALES_DIR / f"{lang}.json").read_text(encoding="utf-8"))


def _flatten(node: dict, prefix: str = "") -> set[str]:
    keys: set[str] = set()
    for key, value in node.items():
        path = f"{prefix}{key}"
        if isinstance(value, dict):
            keys |= _flatten(value, f"{path}.")
        else:
            keys.add(path)
    return keys


def test_uz_and_ru_have_identical_key_sets() -> None:
    uz_keys = _flatten(_load("uz"))
    ru_keys = _flatten(_load("ru"))
    assert uz_keys - ru_keys == set(), f"missing in ru.json: {sorted(uz_keys - ru_keys)}"
    assert ru_keys - uz_keys == set(), f"missing in uz.json: {sorted(ru_keys - uz_keys)}"


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_no_locale_value_is_empty(lang: str) -> None:
    empty = [key for key in _flatten(_load(lang)) if not translate(lang, key).strip()]
    assert empty == [], f"{lang}.json has empty values: {empty}"


@pytest.mark.parametrize("lang", SUPPORTED_LANGUAGES)
def test_placeholders_match_across_languages(lang: str) -> None:
    """A {placeholder} present in one language but not the other means .format() raises a
    KeyError (extra placeholder) or silently drops data (missing one) for that language."""
    uz = _load("uz")
    placeholder = re.compile(r"\{(\w+)\}")

    for key in sorted(_flatten(uz)):
        uz_value = translate("uz", key)
        other_value = translate(lang, key)
        if not isinstance(uz_value, str) or not isinstance(other_value, str):
            continue
        assert set(placeholder.findall(uz_value)) == set(
            placeholder.findall(other_value)
        ), f"placeholder mismatch for {key} between uz and {lang}"


def test_every_translation_key_used_in_code_exists() -> None:
    """Sweeps the source for literal `_("some.key")` / `translator("some.key")` calls and
    asserts each resolves. Catches the common slip of adding a handler string but forgetting
    the locale entry."""
    uz_keys = _flatten(_load("uz"))
    pattern = re.compile(r"""["']((?:[a-z_]+)\.(?:[a-z0-9_]+))["']""")

    missing: set[str] = set()
    for path in APP_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for match in pattern.finditer(source):
            key = match.group(1)
            # Only consider strings whose first segment is a real locale section, so paths
            # like "app.services" or "sqlalchemy.orm" are not mistaken for keys.
            section = key.split(".")[0]
            if section not in _load("uz"):
                continue
            if key in uz_keys or key.startswith(DYNAMIC_KEY_PREFIXES):
                continue
            # `ForeignKey("orders.id")` and friends collide with the locale-key shape.
            context = source[max(0, match.start() - 120) : match.end()]
            if "ForeignKey" in context or "relationship(" in context:
                continue
            missing.add(f"{key} ({path.relative_to(APP_DIR)})")

    assert (
        missing == set()
    ), f"translation keys used in code but absent from uz.json: {sorted(missing)}"


def test_dynamic_payment_and_status_keys_resolve() -> None:
    """The f-string keys excluded above, resolved through the real lookup tables so every
    PaymentMethod / OrderStatus / editable field an admin or customer can hit is translated."""
    from app.bot.handlers.user.checkout import PAYMENT_LABEL_KEYS
    from app.bot.keyboards.inline.admin_products import EDITABLE_FIELDS
    from app.bot.keyboards.inline.orders import STATUS_LABEL_KEYS
    from app.bot.utils.admin_order_card import ADMIN_PAYMENT_LABEL_KEYS
    from app.db.models.enums import OrderStatus, PaymentMethod

    # Every enum member must have an entry in its label map, or the bot falls back to a
    # wrong/blank label for an order paid that way.
    assert set(PAYMENT_LABEL_KEYS) == {m.value for m in PaymentMethod}
    assert set(ADMIN_PAYMENT_LABEL_KEYS) == set(PaymentMethod)
    assert set(STATUS_LABEL_KEYS) == {s.value for s in OrderStatus}

    label_keys = (
        list(PAYMENT_LABEL_KEYS.values())
        + list(ADMIN_PAYMENT_LABEL_KEYS.values())
        + list(STATUS_LABEL_KEYS.values())
        + [f"admin.product_field_{field}" for field in EDITABLE_FIELDS]
    )
    for lang in SUPPORTED_LANGUAGES:
        for key in label_keys:
            assert translate(lang, key) != key, f"{lang}: {key} is untranslated"
