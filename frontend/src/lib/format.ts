export function formatPrice(value: string | number): string {
  const num = typeof value === "string" ? parseFloat(value) : value;
  return new Intl.NumberFormat("fr-FR").format(Math.round(num)).replace(/ /g, " ");
}

export function formatExactPrice(value: string): string {
  const match = /^(-?)(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return "—";
  const sign = match[1] ?? "";
  const whole = new Intl.NumberFormat("fr-FR").format(BigInt(match[2]!)).replace(/ /g, " ");
  const fraction = match[3]?.replace(/0+$/, "");
  return `${sign}${whole}${fraction ? `.${fraction}` : ""}`;
}

export function formatDateTime(value: string, language: "uz" | "ru"): string | null {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return null;
  return new Intl.DateTimeFormat(language === "ru" ? "ru-RU" : "uz-UZ", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(timestamp));
}

export function localizedField<T extends string>(
  language: "uz" | "ru",
  obj: Record<`${T}_uz` | `${T}_ru`, string | null>,
  field: T,
): string {
  const value = language === "ru" ? obj[`${field}_ru`] : obj[`${field}_uz`];
  return value ?? "";
}
