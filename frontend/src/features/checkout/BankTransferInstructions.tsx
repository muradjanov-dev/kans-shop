import { useTranslate, type TranslationKey } from "@/lib/i18n";
import { formatExactPrice } from "@/lib/format";
import type { Order } from "@/types/api";
import { ReceiptUpload } from "./ReceiptUpload";

const STEPS: TranslationKey[] = [
  "checkout.bank_step_1",
  "checkout.bank_step_2",
  "checkout.bank_step_3",
  "checkout.bank_step_4",
];

/** Payment requisites and steps for a transfer to the shop's bank account (not a card). */
export function BankTransferInstructions({
  order,
  className = "rounded-2xl bg-[var(--paper)] p-5 dark:bg-slate-800",
}: {
  order: Order;
  className?: string;
}) {
  const t = useTranslate();
  const instructions = order.payment_instructions;
  if (!instructions) return null;

  async function copyAccountNumber(): Promise<void> {
    if (!instructions || !navigator.clipboard?.writeText) return;
    await navigator.clipboard.writeText(instructions.card_number).catch(() => undefined);
  }

  const rows: { label: TranslationKey; value: string; mono?: boolean }[] = [
    { label: "checkout.bank_account", value: instructions.card_number, mono: true },
    { label: "checkout.bank_recipient", value: instructions.card_holder },
    { label: "checkout.bank_amount", value: `${formatExactPrice(order.total)} ${t("common.som")}` },
    {
      label: "checkout.bank_purpose",
      value: t("checkout.bank_purpose_value", { number: order.order_number }),
    },
  ];

  return (
    <section className={className}>
      <h2 className="mb-3 text-xl font-bold text-brand dark:text-white">
        {t("checkout.bank_transfer_title")}
      </h2>
      <dl className="flex flex-col gap-2">
        {rows.map((row) => (
          <div key={row.label}>
            <dt className="text-xs text-[var(--muted)] dark:text-gray-400">{t(row.label)}</dt>
            <dd
              className={`break-words text-[var(--ink)] dark:text-white ${
                row.mono ? "font-mono text-base" : "text-sm font-medium"
              }`}
            >
              {row.value}
            </dd>
          </div>
        ))}
      </dl>
      <button
        type="button"
        onClick={() => void copyAccountNumber()}
        className="mt-3 text-sm font-semibold text-brand dark:text-white"
      >
        {t("checkout.copy_account")}
      </button>
      <h3 className="mt-4 text-sm font-semibold text-[var(--ink)] dark:text-white">
        {t("checkout.bank_steps_title")}
      </h3>
      <ol className="mt-2 flex list-decimal flex-col gap-1 pl-5 text-sm text-[var(--ink)] dark:text-gray-200">
        {STEPS.map((step) => (
          <li key={step}>{t(step)}</li>
        ))}
      </ol>
      <ReceiptUpload order={order} />
    </section>
  );
}
