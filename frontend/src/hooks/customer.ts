import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import { customerQueryKeys } from "@/hooks/queries";
import { useAuthStore } from "@/store/auth";
import type { Address, FavoritePage, FavoriteState, Page, Product, Profile } from "@/types/api";

export type ProfileUpdate = Partial<Profile>;

export interface AddressInput {
  label: string;
  address_text: string;
  address_comment: string | null;
}

export type AddressUpdate = Partial<AddressInput>;

function isCurrentOwner(userId: string | null, authEpoch: number): userId is string {
  const current = useAuthStore.getState();
  return Boolean(userId && current.userId === userId && current.authEpoch === authEpoch);
}

export function useCustomerProfile() {
  const userId = useAuthStore((state) => state.userId);
  return useQuery({
    queryKey: customerQueryKeys.profile(userId),
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Profile>("/profile", { signal });
      return data;
    },
    enabled: Boolean(userId),
    retry: false,
  });
}

export function useUpdateCustomerProfile() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);
  return useMutation({
    mutationFn: async (profile: ProfileUpdate) => {
      if (!isCurrentOwner(userId, authEpoch)) throw new Error("Customer session changed");
      const { data } = await api.patch<Profile>("/profile", profile);
      return data;
    },
    onSuccess: (profile) => {
      if (!isCurrentOwner(userId, authEpoch)) return;
      queryClient.setQueryData(customerQueryKeys.profile(userId), profile);
    },
    retry: false,
  });
}

export function useAddresses(enabled = true) {
  const userId = useAuthStore((state) => state.userId);
  return useQuery({
    queryKey: customerQueryKeys.addresses(userId),
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Address[]>("/addresses", { signal });
      return data;
    },
    enabled: enabled && Boolean(userId),
    retry: false,
  });
}

export function useAddressMutations() {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);

  const refreshAddresses = () => {
    if (isCurrentOwner(userId, authEpoch)) {
      void queryClient.invalidateQueries({ queryKey: customerQueryKeys.addresses(userId) });
    }
  };
  const createAddress = useMutation({
    mutationFn: async (address: AddressInput) => {
      if (!isCurrentOwner(userId, authEpoch)) throw new Error("Customer session changed");
      const { data } = await api.post<Address>("/addresses", address);
      return data;
    },
    onSuccess: refreshAddresses,
    retry: false,
  });
  const updateAddress = useMutation({
    mutationFn: async ({ addressId, address }: { addressId: number; address: AddressUpdate }) => {
      if (!isCurrentOwner(userId, authEpoch)) throw new Error("Customer session changed");
      const { data } = await api.patch<Address>(`/addresses/${addressId}`, address);
      return data;
    },
    onSuccess: refreshAddresses,
    retry: false,
  });
  const setDefaultAddress = useMutation({
    mutationFn: async (addressId: number) => {
      if (!isCurrentOwner(userId, authEpoch)) throw new Error("Customer session changed");
      const { data } = await api.put<Address>(`/addresses/${addressId}/default`);
      return data;
    },
    onSuccess: refreshAddresses,
    retry: false,
  });
  const deleteAddress = useMutation({
    mutationFn: async (addressId: number) => {
      if (!isCurrentOwner(userId, authEpoch)) throw new Error("Customer session changed");
      await api.delete<void>(`/addresses/${addressId}`);
      return addressId;
    },
    onSuccess: refreshAddresses,
    retry: false,
  });

  return { createAddress, updateAddress, setDefaultAddress, deleteAddress };
}

export function useFavorites(page = 1) {
  const userId = useAuthStore((state) => state.userId);
  return useQuery<FavoritePage>({
    queryKey: customerQueryKeys.favorites(userId, page),
    queryFn: async ({ signal }) => {
      const { data } = await api.get<Page<Product>>("/favorites", {
        params: { page, limit: 24 },
        signal,
      });
      return data;
    },
    enabled: Boolean(userId),
    retry: false,
  });
}

export function useFavoriteState(productId: number) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((state) => state.userId);
  const authEpoch = useAuthStore((state) => state.authEpoch);
  const query = useQuery({
    queryKey: customerQueryKeys.favoriteState(userId, productId),
    queryFn: async ({ signal }) => {
      const { data } = await api.get<FavoriteState>(`/favorites/${productId}`, { signal });
      return data;
    },
    enabled: Boolean(userId) && Number.isSafeInteger(productId) && productId > 0,
    retry: false,
  });
  const mutation = useMutation({
    mutationFn: async (isFavorite: boolean) => {
      if (!isCurrentOwner(userId, authEpoch)) throw new Error("Customer session changed");
      if (isFavorite) {
        await api.delete<void>(`/favorites/${productId}`);
        return false;
      }
      await api.put<void>(`/favorites/${productId}`);
      return true;
    },
    onSuccess: (isFavorite) => {
      if (!isCurrentOwner(userId, authEpoch)) return;
      queryClient.setQueryData<FavoriteState>(customerQueryKeys.favoriteState(userId, productId), {
        is_favorite: isFavorite,
      });
      void queryClient.invalidateQueries({ queryKey: customerQueryKeys.favoritesRoot(userId) });
    },
    retry: false,
  });

  return {
    ...query,
    isFavorite: query.data?.is_favorite ?? false,
    isMutationPending: mutation.isPending,
    toggle: () => {
      if (query.data) mutation.mutate(query.data.is_favorite);
      else void query.refetch();
    },
  };
}
