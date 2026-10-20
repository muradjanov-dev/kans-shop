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

const UZ_MONTHS = [
  "yanvar", "fevral", "mart", "aprel", "may", "iyun",
  "iyul", "avgust", "sentabr", "oktabr", "noyabr", "dekabr",
];

/**
 * "21-oktabr 2026, 14:05". Browsers have no proper Uzbek date names (Chrome prints
 * "2026 M10 21"), so Uzbek dates are spelled out here; Russian uses the browser's own.
 */
export function formatUzDateTime(date: Date, withTime = true): string {
  const day = `${date.getDate()}-${UZ_MONTHS[date.getMonth()]} ${date.getFullYear()}`;
  if (!withTime) return day;
  const time = `${String(date.getHours()).padStart(2, "0")}:${String(date.getMinutes()).padStart(2, "0")}`;
  return `${day}, ${time}`;
}

export function formatDateTime(value: string, language: "uz" | "ru"): string | null {
  const timestamp = Date.parse(value);
  if (!Number.isFinite(timestamp)) return null;
  if (language === "uz") return formatUzDateTime(new Date(timestamp));
  return new Intl.DateTimeFormat("ru-RU", {
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
