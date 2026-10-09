import type { QueryClient } from "@tanstack/react-query";
import { useAuthStore } from "@/store/auth";
import type { Cart } from "@/types/api";

export async function setCustomerCartFromServer(
  queryClient: QueryClient,
  userId: string,
  authEpoch: number,
  cart: Cart,
): Promise<boolean> {
  const isCurrentSession = () => {
    const current = useAuthStore.getState();
    return Boolean(
      current.accessToken &&
      current.userId === userId &&
      current.authEpoch === authEpoch,
    );
  };

  if (!isCurrentSession()) return false;
  await queryClient.cancelQueries({ queryKey: ["cart", userId], exact: true });
  if (!isCurrentSession()) return false;

  queryClient.setQueryData(["cart", userId], cart);
  return true;
}
