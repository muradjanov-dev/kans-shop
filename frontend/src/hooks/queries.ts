import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { useAuthStore } from "@/store/auth";
import type {
  Cart,
  Category,
  CheckoutPayload,
  LotLinksResponse,
  Order,
  Page,
  PayResponse,
  PaymentProvider,
  Product,
  PublicSettings,
} from "@/types/api";

export function useCategories(parentId?: number) {
  return useQuery({
    queryKey: ["categories", parentId ?? null],
    queryFn: async () => {
      const { data } = await api.get<Category[]>("/catalog/categories", {
        params: parentId ? { parent_id: parentId } : undefined,
      });
      return data;
    },
  });
}

export function useCategoryProducts(categoryId: number | undefined, page: number) {
  return useQuery({
    queryKey: ["category-products", categoryId, page],
    queryFn: async () => {
      const { data } = await api.get<Page<Product>>(
        `/catalog/categories/${categoryId}/products`,
        { params: { page, limit: 12 } },
      );
      return data;
    },
    enabled: categoryId !== undefined,
  });
}

export function useProductSearch(query: string, page: number) {
  return useQuery({
    queryKey: ["product-search", query, page],
    queryFn: async () => {
      const { data } = await api.get<Page<Product>>("/catalog/search", {
        params: { q: query, page, limit: 12 },
      });
      return data;
    },
    enabled: query.trim().length > 0,
  });
}

export function useProduct(productId: number | undefined) {
  return useQuery({
    queryKey: ["product", productId],
    queryFn: async () => {
      const { data } = await api.get<Product>(`/catalog/products/${productId}`);
      return data;
    },
    enabled: productId !== undefined,
  });
}

export function usePublicSettings() {
  return useQuery({
    queryKey: ["public-settings"],
    queryFn: async () => {
      const { data } = await api.get<PublicSettings>("/settings/public");
      return data;
    },
    staleTime: 5 * 60 * 1000,
  });
}

export function useCart(enabled: boolean) {
  const userId = useAuthStore((state) => state.userId);
  return useQuery({
    queryKey: ["cart", userId],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Cart>("/cart", { signal });
      return data;
    },
    enabled: enabled && Boolean(userId),
  });
}

export function useAddCartItem() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);
  return useMutation({
    mutationFn: async ({ productId, quantity, mutationKey }: { productId: number; quantity: number; mutationKey: string }) => {
      const { data } = await api.post<Cart>(
        "/cart/items",
        { product_id: productId, quantity },
        { headers: { "Idempotency-Key": mutationKey } },
      );
      return data;
    },
    retry: false,
    onSuccess: (data) => {
      const current = useAuthStore.getState();
      if (current.authEpoch === authEpoch && current.userId === userId && userId) {
        queryClient.setQueryData(["cart", userId], data);
      }
    },
  });
}

export function useUpdateCartItem() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);
  return useMutation({
    mutationFn: async ({ productId, quantity }: { productId: number; quantity: number }) => {
      const { data } = await api.patch<Cart>(`/cart/items/${productId}`, { quantity });
      return data;
    },
    retry: false,
    onSuccess: (data) => {
      const current = useAuthStore.getState();
      if (current.authEpoch === authEpoch && current.userId === userId && userId) {
        queryClient.setQueryData(["cart", userId], data);
      }
    },
  });
}

export function useRemoveCartItem() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);
  return useMutation({
    mutationFn: async (productId: number) => {
      const { data } = await api.delete<Cart>(`/cart/items/${productId}`);
      return data;
    },
    retry: false,
    onSuccess: (data) => {
      const current = useAuthStore.getState();
      if (current.authEpoch === authEpoch && current.userId === userId && userId) {
        queryClient.setQueryData(["cart", userId], data);
      }
    },
  });
}

export function useCheckout() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);
  return useMutation({
    mutationFn: async ({ payload, checkoutKey }: { payload: CheckoutPayload; checkoutKey: string }) => {
      const { data } = await api.post<Order>("/orders", payload, {
        headers: { "Idempotency-Key": checkoutKey },
      });
      return data;
    },
    onSuccess: () => {
      const current = useAuthStore.getState();
      if (current.authEpoch !== authEpoch || current.userId !== userId || !userId) return;
      void queryClient.invalidateQueries({ queryKey: ["cart", userId] });
      void queryClient.invalidateQueries({ queryKey: ["orders", userId] });
    },
    retry: false,
  });
}

export function usePayOrder() {
  return useMutation({
    mutationFn: async ({
      orderId,
      provider,
    }: {
      orderId: number;
      provider: PaymentProvider;
    }) => {
      const { data } = await api.post<PayResponse>(`/orders/${orderId}/pay`, { provider });
      return data;
    },
    retry: false,
  });
}

export function useLotLinks(orderId: number | null) {
  const userId = useAuthStore((state) => state.userId);
  return useQuery({
    queryKey: ["lot-links", userId, orderId],
    enabled: orderId !== null && Boolean(userId),
    queryFn: async ({ signal }) => {
      const { data } = await api.get<LotLinksResponse>(`/orders/${orderId}/lot-links`, { signal });
      return data;
    },
  });
}

export function useOrders(enabled: boolean) {
  const userId = useAuthStore((state) => state.userId);
  return useQuery({
    queryKey: ["orders", userId],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Order[]>("/orders", { signal });
      return data;
    },
    enabled: enabled && Boolean(userId),
  });
}

export function useOrder(orderId: number | undefined) {
  const userId = useAuthStore((state) => state.userId);
  return useQuery({
    queryKey: ["order", userId, orderId],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Order>(`/orders/${orderId}`, { signal });
      return data;
    },
    enabled: orderId !== undefined && Boolean(userId),
  });
}
