import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { AddressFormDialog } from "@/features/customer/AddressFormDialog";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import { useAddressMutations, useAddresses } from "@/hooks/customer";
import { useTranslate } from "@/lib/i18n";
import { useAuthStore } from "@/store/auth";
import type { Address } from "@/types/api";

export function AddressesPage() {
  const t = useTranslate();
  const userId = useAuthStore((state) => state.userId);
  const accessToken = useAuthStore((state) => state.accessToken);
  const { openLogin } = useCustomerAuth();
  const addressesQuery = useAddresses();
  const { createAddress, updateAddress, setDefaultAddress, deleteAddress } = useAddressMutations();
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editingAddress, setEditingAddress] = useState<Address | null>(null);
  const [actionError, setActionError] = useState(false);
  const dialogOwnerId = useRef<string | null>(null);
  const isAuthenticated = Boolean(accessToken && userId);
  const showDialog = Boolean(dialogOpen && userId && dialogOwnerId.current === userId);
  const addresses = addressesQuery.data ?? [];

  useEffect(() => {
    if (dialogOpen && dialogOwnerId.current && dialogOwnerId.current !== userId) {
      dialogOwnerId.current = null;
      setDialogOpen(false);
      setEditingAddress(null);
      setActionError(false);
    }
  }, [dialogOpen, userId]);

  function openCreateDialog() {
    dialogOwnerId.current = userId;
    setEditingAddress(null);
    setActionError(false);
    setDialogOpen(true);
  }

  function openEditDialog(address: Address) {
    dialogOwnerId.current = userId;
    setEditingAddress(address);
    setActionError(false);
    setDialogOpen(true);
  }

  async function saveAddress(value: Parameters<typeof createAddress.mutateAsync>[0]) {
    if (!useAuthStore.getState().userId) {
      openLogin();
      throw new Error("Sign in to save an address");
    }
    if (editingAddress) {
      await updateAddress.mutateAsync({ addressId: editingAddress.id, address: value });
    } else {
      await createAddress.mutateAsync(value);
    }
  }

  async function runAddressAction(action: () => Promise<unknown>) {
    setActionError(false);
    try {
      await action();
    } catch {
      setActionError(true);
    }
  }

  return (
    <section aria-labelledby="addresses-title" className="mx-auto max-w-3xl p-4 sm:p-6">
      <div className="mb-4 flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-slate-900 dark:text-white" id="addresses-title">{t("account.addresses_title")}</h1>
        <Link className="inline-flex min-h-11 items-center rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium dark:border-white/10 dark:bg-slate-900" to="/profile">
          {t("nav.profile")}
        </Link>
      </div>

      {!isAuthenticated && (
        <div className="mb-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-900">
          <p className="mb-3 text-sm text-slate-600 dark:text-slate-300">{t("account.sign_in_required")}</p>
          <button className="min-h-11 rounded-lg bg-brand px-5 font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" onClick={openLogin} type="button">
            {t("auth.sign_in")}
          </button>
        </div>
      )}

      {addressesQuery.isError && (
        <div className="mb-4 flex items-center justify-between gap-3 rounded-lg bg-red-50 p-3 text-sm text-red-800 dark:bg-red-950/40 dark:text-red-200" role="alert">
          <span>{t("addresses.load_error")}</span>
          <button className="min-h-11 px-2 font-semibold underline focus-visible:outline-2 focus-visible:outline-brand" onClick={() => void addressesQuery.refetch()} type="button">
            {t("account.retry")}
          </button>
        </div>
      )}
      {actionError && <p className="mb-4 text-sm text-red-700 dark:text-red-200" role="alert">{t("addresses.action_error")}</p>}

      {isAuthenticated && (
        <div className="flex flex-col gap-3">
          {addressesQuery.isLoading && <p className="py-6 text-center text-sm text-slate-500" role="status">{t("common.loading")}</p>}
          {!addressesQuery.isLoading && addresses.length === 0 && (
            <p className="rounded-xl border border-dashed border-slate-300 p-5 text-center text-sm text-slate-500 dark:border-white/15 dark:text-slate-400">{t("addresses.empty")}</p>
          )}
          {addresses.map((address) => (
            <article className="rounded-xl border border-slate-200 bg-white p-4 dark:border-white/10 dark:bg-slate-900" key={address.id}>
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="font-semibold text-slate-900 dark:text-white">{address.label}</h2>
                    {address.is_default && <span className="rounded-full bg-violet-100 px-2 py-1 text-xs font-medium text-violet-900 dark:bg-violet-400/20 dark:text-violet-100">{t("addresses.default_badge")}</span>}
                  </div>
                  <p className="mt-1 whitespace-pre-line text-sm text-slate-700 dark:text-slate-200">{address.address_text}</p>
                  {address.address_comment && <p className="mt-1 whitespace-pre-line text-sm text-slate-500 dark:text-slate-400">{address.address_comment}</p>}
                </div>
                <div className="flex flex-wrap gap-2">
                  {!address.is_default && (
                    <button className="min-h-11 rounded-lg border border-slate-300 px-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15" disabled={setDefaultAddress.isPending} onClick={() => void runAddressAction(() => setDefaultAddress.mutateAsync(address.id))} type="button">
                      {t("addresses.default", { label: address.label })}
                    </button>
                  )}
                  <button className="min-h-11 rounded-lg border border-slate-300 px-3 text-sm font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-white/15" onClick={() => openEditDialog(address)} type="button">
                    {t("addresses.edit", { label: address.label })}
                  </button>
                  <button className="min-h-11 rounded-lg border border-red-300 px-3 text-sm font-medium text-red-700 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand dark:border-red-300/40 dark:text-red-200" disabled={deleteAddress.isPending} onClick={() => void runAddressAction(() => deleteAddress.mutateAsync(address.id))} type="button">
                    {t("addresses.delete", { label: address.label })}
                  </button>
                </div>
              </div>
            </article>
          ))}
          {addresses.length < 20 && (
            <button className="min-h-11 self-start rounded-lg bg-brand px-5 font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand" onClick={openCreateDialog} type="button">
              {t("addresses.add")}
            </button>
          )}
        </div>
      )}

      {showDialog && (
        <AddressFormDialog
          address={editingAddress}
          key={`${editingAddress?.id ?? "new"}`}
          onCancel={() => {
            dialogOwnerId.current = null;
            setDialogOpen(false);
            setEditingAddress(null);
          }}
          onSubmit={saveAddress}
        />
      )}
    </section>
  );
}
