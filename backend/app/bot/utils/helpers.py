import re

# Per docs/DB_SCHEMA.md: +998(90|91|93|94|95|97|98|99|33|88|77|71)XXXXXXX
UZ_PHONE_RE = re.compile(r"^\+998(90|91|93|94|95|97|98|99|33|88|77|71)\d{7}$")


def normalize_uz_phone(raw: str) -> str:
    """Strip everything but digits and a leading '+', and add the '+998' country code if the
    user typed a local 9-digit number (e.g. Telegram's request_contact often omits it)."""
    digits = re.sub(r"[^\d+]", "", raw.strip())
    if not digits.startswith("+"):
        digits = digits.lstrip("+")
        if len(digits) == 9:
            digits = "998" + digits
        digits = "+" + digits
    return digits


def is_valid_uz_phone(raw: str) -> bool:
    return bool(UZ_PHONE_RE.match(normalize_uz_phone(raw)))
