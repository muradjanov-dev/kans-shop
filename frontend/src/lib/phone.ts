// Mirrors backend/app/bot/utils/helpers.py — keep the pattern in sync with docs/DB_SCHEMA.md.
const UZ_PHONE_RE = /^\+998(90|91|93|94|95|97|98|99|33|88|77|71)\d{7}$/;

export function normalizeUzPhone(raw: string): string {
  let digits = raw.trim().replace(/[^\d+]/g, "");
  if (!digits.startsWith("+")) {
    digits = digits.replace(/\+/g, "");
    if (digits.length === 9) digits = "998" + digits;
    digits = "+" + digits;
  }
  return digits;
}

export function isValidUzPhone(raw: string): boolean {
  return UZ_PHONE_RE.test(normalizeUzPhone(raw));
}
