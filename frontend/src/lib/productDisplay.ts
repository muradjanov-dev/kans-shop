import type { TranslationKey } from "@/lib/i18n";
import type { ProductUnit } from "@/types/api";

export const productUnitTranslationKey = {
  dona: "product.unit.dona",
  quti: "product.unit.quti",
  paket: "product.unit.paket",
  komplekt: "product.unit.komplekt",
} satisfies Record<ProductUnit, TranslationKey>;

function decimalParts(value: string): { whole: string; fraction: string } | null {
  const match = /^(\d+)(?:\.(\d+))?$/.exec(value.trim());
  if (!match) return null;
  return {
    whole: (match[1] ?? "0").replace(/^0+(?=\d)/, ""),
    fraction: match[2] ?? "",
  };
}

export function hasHigherOldPrice(oldPrice: string | null, price: string): boolean {
  if (!oldPrice) return false;
  const current = decimalParts(price);
  const previous = decimalParts(oldPrice);
  if (!current || !previous) return false;

  const scale = Math.max(current.fraction.length, previous.fraction.length);
  const currentValue = BigInt(`${current.whole}${current.fraction.padEnd(scale, "0")}`);
  const previousValue = BigInt(`${previous.whole}${previous.fraction.padEnd(scale, "0")}`);
  return previousValue > currentValue;
}
