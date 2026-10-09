import { describe, expect, it } from "vitest";
import { hasHigherOldPrice, productUnitTranslationKey } from "@/lib/productDisplay";

describe("product display rules", () => {
  it("compares decimal old prices without rounding or truncating precision", () => {
    expect(hasHigherOldPrice("12000.1250001", "12000.125")).toBe(true);
    expect(hasHigherOldPrice("12000.1250000", "12000.125")).toBe(false);
    expect(hasHigherOldPrice("12000.1249999", "12000.125")).toBe(false);
  });

  it("maps every server product unit to its localized translation key", () => {
    expect(productUnitTranslationKey).toEqual({
      dona: "product.unit.dona",
      quti: "product.unit.quti",
      paket: "product.unit.paket",
      komplekt: "product.unit.komplekt",
    });
  });
});
