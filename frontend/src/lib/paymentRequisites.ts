/**
 * The store keeps a single pair of transfer requisites (`card_number`, `card_holder`).
 * Kans Shop receives transfers to its company bank account: Uzbek bank account numbers are
 * 20 digits, payment cards are 16. Customers need different wording and steps for each.
 */
export function isBankAccountNumber(value: string | null | undefined): boolean {
  return typeof value === "string" && /^\d{20}$/.test(value.replace(/[\s-]/g, ""));
}
