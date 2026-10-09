import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type { CheckoutQuote, Order, OrderType, PaymentMethod } from "@/types/api";

export function useCheckoutQuote(
  orderType: OrderType,
  paymentMethod: PaymentMethod,
  cartRevision: string,
  enabled: boolean,
) {
  const userId = useAuthStore((state) => state.userId);
  return useQuery({
    queryKey: ["cart", userId, "checkout-quote", orderType, paymentMethod, cartRevision],
    queryFn: async ({ signal }) => {
      const { data } = await api.post<CheckoutQuote>(
        "/orders/quote",
        { order_type: orderType, payment_method: paymentMethod },
        { signal },
      );
      return data;
    },
    enabled: enabled && Boolean(userId),
    retry: false,
  });
}

export function useUploadReceipt() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);
  return useMutation({
    mutationFn: async ({ orderId, file }: { orderId: number; file: File }) => {
      const body = new FormData();
      body.append("file", file);
      const { data } = await api.post<Order>(`/orders/${orderId}/receipt`, body);
      return data;
    },
    retry: false,
    onSuccess: (order, variables) => {
      const current = useAuthStore.getState();
      if (current.authEpoch !== authEpoch || current.userId !== userId || !userId) return;
      queryClient.setQueryData(["order", userId, variables.orderId], order);
      void queryClient.invalidateQueries({ queryKey: ["orders", userId] });
      void queryClient.invalidateQueries({ queryKey: ["order", userId, variables.orderId, "receipt"] });
    },
  });
}

export function useReceiptBlob(orderId: number, enabled: boolean) {
  const userId = useAuthStore((state) => state.userId);
  return useQuery({
    queryKey: ["order", userId, orderId, "receipt"],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Blob>(`/orders/${orderId}/receipt`, {
        responseType: "blob",
        signal,
      });
      return data;
    },
    enabled: enabled && Boolean(userId),
    retry: false,
  });
}
