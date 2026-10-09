import axios from "axios";
import { useMutation } from "@tanstack/react-query";
import { API_BASE_URL } from "@/lib/api";
import type { TokenPair } from "@/types/api";

export function useCustomerCodeLogin() {
  return useMutation({
    mutationFn: async (code: string) => {
      const { data } = await axios.post<TokenPair>(`${API_BASE_URL}/auth/customer/code`, { code });
      return data;
    },
    retry: false,
  });
}
