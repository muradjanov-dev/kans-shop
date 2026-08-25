import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
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
  return useQuery({
    queryKey: ["cart"],
    queryFn: async () => {
      const { data } = await api.get<Cart>("/cart");
      return data;
    },
    enabled,
  });
}

export function useAddCartItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ productId, quantity }: { productId: number; quantity: number }) => {
      const { data } = await api.post<Cart>("/cart/items", {
        product_id: productId,
        quantity,
      });
      return data;
    },
    onSuccess: (data) => queryClient.setQueryData(["cart"], data),
  });
}

export function useUpdateCartItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async ({ productId, quantity }: { productId: number; quantity: number }) => {
      const { data } = await api.patch<Cart>(`/cart/items/${productId}`, { quantity });
      return data;
    },
    onSuccess: (data) => queryClient.setQueryData(["cart"], data),
  });
}

export function useRemoveCartItem() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (productId: number) => {
      const { data } = await api.delete<Cart>(`/cart/items/${productId}`);
      return data;
    },
    onSuccess: (data) => queryClient.setQueryData(["cart"], data),
  });
}

export function useCheckout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (payload: CheckoutPayload) => {
      const { data } = await api.post<Order>("/orders", payload);
      return data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cart"] });
      queryClient.invalidateQueries({ queryKey: ["orders"] });
    },
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
  });
}

export function useLotLinks(orderId: number | null) {
  return useQuery({
    queryKey: ["lot-links", orderId],
    enabled: orderId !== null,
    queryFn: async () => {
      const { data } = await api.get<LotLinksResponse>(`/orders/${orderId}/lot-links`);
      return data;
    },
  });
}

export function useOrders(enabled: boolean) {
  return useQuery({
    queryKey: ["orders"],
    queryFn: async () => {
      const { data } = await api.get<Order[]>("/orders");
      return data;
    },
    enabled,
  });
}

export function useOrder(orderId: number | undefined) {
  return useQuery({
    queryKey: ["order", orderId],
    queryFn: async () => {
      const { data } = await api.get<Order>(`/orders/${orderId}`);
      return data;
    },
    enabled: orderId !== undefined,
  });
}
