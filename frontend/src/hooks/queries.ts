import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { setCustomerCartFromServer } from "@/lib/cartCache";
import { useAuthStore } from "@/store/auth";
import type {
  Cart,
  Category,
  CheckoutPayload,
  LotLinksResponse,
  Order,
  OrderHistoryItem,
  OrderTimelineEvent,
  Page,
  PayResponse,
  PaymentProvider,
  Product,
  PublicSettings,
} from "@/types/api";

export const customerQueryKeys = {
  profile: (userId: string | null) => ["profile", userId] as const,
  addresses: (userId: string | null) => ["addresses", userId] as const,
  orderHistoryRoot: (userId: string | null) => ["order-history", userId] as const,
  orderHistory: (userId: string | null, page: number) => ["order-history", userId, page] as const,
  orderTimelineRoot: (userId: string | null) => ["order-timeline", userId] as const,
  orderTimeline: (userId: string | null, orderId: number) => ["order-timeline", userId, orderId] as const,
  favoritesRoot: (userId: string | null) => ["favorites", userId] as const,
  favorites: (userId: string | null, page: number) => ["favorites", userId, page] as const,
  favoriteState: (userId: string | null, productId: number) => ["favorite-state", userId, productId] as const,
};

export function useCategories(parentId?: number) {
  return useQuery({
    queryKey: ["categories", parentId ?? null],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Category[]>("/catalog/categories", {
        params: parentId ? { parent_id: parentId } : undefined,
        signal,
      });
      return data;
    },
  });
}

export function useFeaturedProducts(limit = 10) {
  return useQuery({
    queryKey: ["featured-products", limit],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Product[]>("/catalog/featured", {
        params: { limit },
        signal,
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
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Product>(`/catalog/products/${productId}`, { signal });
      return data;
    },
    enabled: productId !== undefined,
  });
}

export function usePublicSettings() {
  return useQuery({
    queryKey: ["public-settings"],
    queryFn: async ({ signal }) => {
      const { data } = await api.get<PublicSettings>("/settings/public", { signal });
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
    onSuccess: async (data) => {
      if (!userId) return;
      await setCustomerCartFromServer(queryClient, userId, authEpoch, data);
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
    onSuccess: async (data) => {
      if (!userId) return;
      await setCustomerCartFromServer(queryClient, userId, authEpoch, data);
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
    onSuccess: async (data) => {
      if (!userId) return;
      await setCustomerCartFromServer(queryClient, userId, authEpoch, data);
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
      void queryClient.invalidateQueries({ queryKey: customerQueryKeys.orderHistoryRoot(userId) });
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

export function useOrderHistory(page: number) {
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  return useQuery({
    queryKey: customerQueryKeys.orderHistory(userId, page),
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Page<OrderHistoryItem>>("/orders/history", {
        params: { page, limit: 24 },
        signal,
      });
      return data;
    },
    enabled: Boolean(accessToken && userId) && Number.isSafeInteger(page) && page > 0,
  });
}

export function useOrderTimeline(orderId: number | undefined) {
  const accessToken = useAuthStore((state) => state.accessToken);
  const userId = useAuthStore((state) => state.userId);
  return useQuery({
    queryKey: userId && orderId !== undefined
      ? customerQueryKeys.orderTimeline(userId, orderId)
      : customerQueryKeys.orderTimelineRoot(userId),
    queryFn: async ({ signal }) => {
      const { data } = await api.get<unknown>(`/orders/${orderId}/timeline`, { signal });
      if (!Array.isArray(data)) return [];
      return data.map((event) => {
        const record = event && typeof event === "object"
          ? event as Record<string, unknown>
          : {};
        return {
          status: record.status,
          occurred_at: record.occurred_at,
        } as unknown as OrderTimelineEvent;
      });
    },
    enabled: Boolean(accessToken && userId) &&
      orderId !== undefined && Number.isSafeInteger(orderId) && orderId > 0,
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
