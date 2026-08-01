export function formatPrice(value: string | number): string {
  const num = typeof value === "string" ? parseFloat(value) : value;
  return new Intl.NumberFormat("fr-FR").format(Math.round(num)).replace(/ /g, " ");
}

export function localizedField<T extends string>(
  language: "uz" | "ru",
  obj: Record<`${T}_uz` | `${T}_ru`, string | null>,
  field: T,
): string {
  const value = language === "ru" ? obj[`${field}_ru`] : obj[`${field}_uz`];
  return value ?? "";
}
