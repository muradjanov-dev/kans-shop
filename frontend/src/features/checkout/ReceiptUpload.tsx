import { useEffect, useState } from "react";
import { useReceiptBlob, useUploadReceipt } from "@/hooks/checkout";
import { useTranslate } from "@/lib/i18n";
import type { Order } from "@/types/api";

const MAX_RECEIPT_BYTES = 5 * 1024 * 1024;
const ALLOWED_RECEIPT_TYPES = new Set(["image/jpeg", "image/png", "image/webp", "application/pdf"]);
const ACTIVE_ORDER_STATUSES = new Set(["new", "confirmed", "preparing", "delivering"]);

export function ReceiptUpload({ order }: { order: Order }) {
  const t = useTranslate();
  const upload = useUploadReceipt();
  const displayOrder = upload.data ?? order;
  const receipt = useReceiptBlob(order.id, displayOrder.has_receipt);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [receiptUrl, setReceiptUrl] = useState<string | null>(null);
  const eligible =
    displayOrder.payment_method === "card_transfer" &&
    Boolean(displayOrder.payment_instructions) &&
    displayOrder.payment_status !== "paid" &&
    ACTIVE_ORDER_STATUSES.has(displayOrder.status);

  useEffect(() => {
    if (!receipt.data) {
      setReceiptUrl(null);
      return;
    }
    const url = URL.createObjectURL(receipt.data);
    setReceiptUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [receipt.data]);

  function selectFile(file: File | undefined): void {
    setFileError(null);
    if (!file) {
      setSelectedFile(null);
      return;
    }
    if (!ALLOWED_RECEIPT_TYPES.has(file.type)) {
      setSelectedFile(null);
      setFileError(t("checkout.receipt_invalid_type"));
      return;
    }
    if (file.size > MAX_RECEIPT_BYTES) {
      setSelectedFile(null);
      setFileError(t("checkout.receipt_too_large"));
      return;
    }
    setSelectedFile(file);
  }

  function submitFile(): void {
    if (!selectedFile || !eligible) return;
    upload.mutate({ orderId: order.id, file: selectedFile }, {
      onSuccess: () => setSelectedFile(null),
    });
  }

  return (
    <div className="mt-4 flex flex-col gap-3 border-t border-gray-100 pt-4">
      {displayOrder.payment_status === "receipt_uploaded" && (
        <p className="text-sm text-amber-700" role="status">{t("checkout.receipt_pending")}</p>
      )}
      {displayOrder.payment_status === "paid" && (
        <p className="text-sm font-medium text-green-700" role="status">{t("checkout.payment_status.paid")}</p>
      )}

      {displayOrder.has_receipt && receipt.isLoading && (
        <p className="text-xs text-gray-500">{t("checkout.receipt_loading")}</p>
      )}
      {displayOrder.has_receipt && receipt.isError && (
        <div className="flex items-center justify-between gap-2 text-xs text-red-600" role="alert">
          <span>{t("checkout.receipt_load_error")}</span>
          <button type="button" onClick={() => void receipt.refetch()} className="font-semibold underline">
            {t("common.retry")}
          </button>
        </div>
      )}
      {receiptUrl && !receipt.isFetching && receipt.data?.type.startsWith("image/") && (
        <img src={receiptUrl} alt={t("checkout.receipt_preview")} className="max-h-72 rounded-lg object-contain" />
      )}
      {receiptUrl && !receipt.isFetching && receipt.data?.type === "application/pdf" && (
        <a href={receiptUrl} target="_blank" rel="noreferrer" className="text-sm font-medium text-brand">
          {t("checkout.open_receipt_pdf")}
        </a>
      )}

      {eligible && (
        <>
          <label className="flex flex-col gap-1 text-xs text-gray-600">
            <span>{t("checkout.receipt_upload_hint")}</span>
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,application/pdf"
              aria-label={t("checkout.receipt_file_label")}
              onChange={(event) => selectFile(event.currentTarget.files?.[0])}
              disabled={upload.isPending}
              className="text-sm file:mr-3 file:rounded-lg file:border-0 file:bg-brand/10 file:px-3 file:py-2 file:font-semibold file:text-brand"
            />
          </label>
          {selectedFile && <p className="text-xs text-gray-500">{selectedFile.name}</p>}
          {fileError && <p role="alert" className="text-xs text-red-600">{fileError}</p>}
          {upload.isError && <p role="alert" className="text-xs text-red-600">{t("checkout.receipt_upload_error")}</p>}
          <button
            type="button"
            onClick={submitFile}
            disabled={!selectedFile || upload.isPending}
            className="rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50"
          >
            {upload.isPending
              ? t("checkout.receipt_uploading")
              : t(displayOrder.has_receipt ? "checkout.replace_receipt" : "checkout.upload_receipt")}
          </button>
        </>
      )}
    </div>
  );
}
