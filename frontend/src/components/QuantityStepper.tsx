interface QuantityStepperProps {
  quantity: number;
  min?: number;
  onChange: (quantity: number) => void;
  disabled?: boolean;
}

export function QuantityStepper({ quantity, min = 1, onChange, disabled }: QuantityStepperProps) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-gray-200 dark:border-white/15">
      <button
        type="button"
        disabled={disabled || quantity <= min}
        onClick={() => onChange(quantity - 1)}
        className="flex size-9 items-center justify-center text-lg font-medium text-gray-700 disabled:opacity-30 dark:text-gray-200"
      >
        −
      </button>
      <span className="min-w-6 text-center text-sm font-semibold text-gray-900 dark:text-white">
        {quantity}
      </span>
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange(quantity + 1)}
        className="flex size-9 items-center justify-center text-lg font-medium text-gray-700 disabled:opacity-30 dark:text-gray-200"
      >
        +
      </button>
    </div>
  );
}
