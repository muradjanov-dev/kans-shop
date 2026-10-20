import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { isBankAccountNumber } from "@/lib/paymentRequisites";
import { renderWithProviders } from "@/test/renderWithProviders";
import type { Order } from "@/types/api";
import { BankTransferInstructions } from "./BankTransferInstructions";

const order: Order = {
  id: 43,
  order_number: "KANS-000043",
  status: "new",
  order_type: "pickup",
  customer_name: "Ali",
  customer_phone: "+998901234567",
  address: null,
  address_comment: null,
  comment: null,
  subtotal: "250000.00",
  delivery_fee: "0.00",
  discount: "0.00",
  total: "250000.00",
  payment_method: "card_transfer",
  payment_status: "pending",
  payment_instructions: {
    card_number: "20208000600999115001",
    card_holder: '"KANS SHOP" MCHJ, STIR 306089114, MFO 01183',
  },
  receipt_version: 0,
  has_receipt: false,
  receipt_url: null,
  cancel_reason: null,
  created_at: "2026-10-20T00:00:00Z",
  confirmed_at: null,
  completed_at: null,
  cancelled_at: null,
  items: [],
};

describe("isBankAccountNumber", () => {
  it("recognises 20-digit Uzbek bank accounts and rejects payment cards", () => {
    expect(isBankAccountNumber("20208000600999115001")).toBe(true);
    expect(isBankAccountNumber("2020 8000 6009 9911 5001")).toBe(true);
    expect(isBankAccountNumber("8600 1234 5678 9012")).toBe(false);
    expect(isBankAccountNumber("")).toBe(false);
    expect(isBankAccountNumber(null)).toBe(false);
  });
});

describe("BankTransferInstructions", () => {
  it("labels the number as a bank account and explains how to pay", () => {
    renderWithProviders(<BankTransferInstructions order={order} />);

    const section = screen.getByRole("heading", { name: "Bank hisobiga o'tkazma" }).closest("section");
    expect(section).not.toBeNull();
    const panel = within(section as HTMLElement);
    expect(panel.getByText("Bank hisob raqami")).toBeInTheDocument();
    expect(panel.getByText("20208000600999115001")).toBeInTheDocument();
    expect(panel.getByText('"KANS SHOP" MCHJ, STIR 306089114, MFO 01183')).toBeInTheDocument();
    expect(panel.getByText("Buyurtma №KANS-000043 uchun to'lov")).toBeInTheDocument();
    expect(panel.getByRole("button", { name: "Hisob raqamini nusxalash" })).toBeInTheDocument();
    expect(panel.getAllByRole("listitem")).toHaveLength(4);
    expect(panel.queryByText(/Karta raqami/)).toBeNull();
  });
});
