import { useTranslate } from "@/lib/i18n";

interface QuantityStepperProps {
  quantity: number;
  min?: number;
  max?: number;
  onChange: (quantity: number) => void;
  disabled?: boolean;
}

export function QuantityStepper({ quantity, min = 1, max, onChange, disabled }: QuantityStepperProps) {
  const t = useTranslate();
  const atMaximum = max !== undefined && quantity >= max;
  return (
    <div className="flex items-center gap-3 rounded-lg border border-gray-200 dark:border-white/15">
      <button
        type="button"
        aria-label={t("quantity.decrease")}
        disabled={disabled || quantity <= min}
        onClick={() => onChange(Math.max(min, quantity - 1))}
        className="flex min-h-11 min-w-11 items-center justify-center text-lg font-medium text-gray-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-30 dark:text-gray-200"
      >
        −
      </button>
      <span className="min-w-6 text-center text-sm font-semibold text-gray-900 dark:text-white">
        {quantity}
      </span>
      <button
        type="button"
        aria-label={t("quantity.increase")}
        disabled={disabled || atMaximum}
        onClick={() => onChange(max === undefined ? quantity + 1 : Math.min(max, quantity + 1))}
        className="flex min-h-11 min-w-11 items-center justify-center text-lg font-medium text-gray-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand disabled:opacity-30 dark:text-gray-200"
      >
        +
      </button>
    </div>
  );
}
