import { useCustomerAuthActions } from "@/features/customer-auth/CustomerAuthProvider";

export function useCartActions() {
  const { add, retry, cancelLogin, pending, errorCode } = useCustomerAuthActions();
  return { add, retry, cancelLogin, pending, errorCode };
}
