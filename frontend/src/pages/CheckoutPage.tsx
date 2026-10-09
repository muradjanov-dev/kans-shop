import { Link } from "react-router-dom";
import { Spinner } from "@/components/Spinner";
import { useCustomerAuth } from "@/features/customer-auth/CustomerAuthProvider";
import { CheckoutForm } from "@/features/checkout/CheckoutForm";
import { CheckoutSuccess } from "@/features/checkout/CheckoutSuccess";
import { useCheckoutFlow } from "@/features/checkout/useCheckoutFlow";
import { useAddressMutations, useAddresses, type AddressInput } from "@/hooks/customer";
import { useTranslate } from "@/lib/i18n";

export function CheckoutPage() {
  const t = useTranslate();
  const flow = useCheckoutFlow();
  const { openLogin } = useCustomerAuth();
  const addresses = useAddresses(flow.isAuthenticated && flow.orderType === "delivery");
  const addressMutations = useAddressMutations();

  function saveAddress(address: AddressInput) {
    return addressMutations.createAddress.mutateAsync(address);
  }

  if (flow.isResettingOwner) return <Spinner />;

  if (!flow.isAuthenticated) {
    return (
      <div className="flex flex-col items-center gap-3 p-6 text-center">
        <p className="text-sm text-gray-600">{t("checkout.login_required")}</p>
        <button
          type="button"
          onClick={openLogin}
          className="min-h-11 rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand"
        >
          {t("auth.sign_in")}
        </button>
      </div>
    );
  }

  if (flow.createdOrder) return <CheckoutSuccess order={flow.createdOrder} />;

  if (flow.recoveryRequired) {
    return (
      <div className="flex flex-col items-center gap-3 p-6 text-center">
        <p className="text-sm text-amber-800" role="alert">{t("checkout.recovery_required")}</p>
        <Link to="/orders" className="rounded-lg bg-brand px-5 py-2.5 text-sm font-semibold text-white">
          {t("nav.orders")}
        </Link>
      </div>
    );
  }

  if (flow.cartLoading) return <Spinner />;

  return (
    <CheckoutForm
      flow={flow}
      addresses={addresses.data ?? []}
      addressesError={addresses.isError}
      retryAddresses={() => void addresses.refetch()}
      saveAddress={saveAddress}
      savingAddress={addressMutations.createAddress.isPending}
    />
  );
}
