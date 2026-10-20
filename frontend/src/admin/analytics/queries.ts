import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useAdminAuth } from "@/admin/AdminAuthProvider";
import { adminApi } from "@/admin/api";
import type {
  AnalyticsBehavior,
  AnalyticsCustomerDetail,
  AnalyticsCustomers,
  AnalyticsPeriod,
  AnalyticsProducts,
  AnalyticsSales,
  AnalyticsSummary,
} from "@/admin/analytics/types";

type Report = {
  summary: AnalyticsSummary;
  behavior: AnalyticsBehavior;
  products: AnalyticsProducts;
  sales: AnalyticsSales;
};

/**
 * Analytics reports keep showing the previous period while the next one loads, so the
 * dashboard never flashes empty when the period changes (it dims instead).
 */
function useAnalyticsQuery<T>(key: readonly unknown[], path: string, params: Record<string, unknown>, enabled = true) {
  const { session, status } = useAdminAuth();
  return useQuery({
    queryKey: ["admin", "analytics", ...key, session?.admin_id ?? "anonymous"],
    queryFn: async ({ signal }) => (await adminApi.get<T>(path, { params, signal })).data,
    enabled: status === "authenticated" && Boolean(session) && enabled,
    placeholderData: keepPreviousData,
    staleTime: 60_000,
  });
}

export function useAnalyticsReport<K extends keyof Report>(
  report: K,
  period: AnalyticsPeriod,
  includeStaff: boolean,
  enabled = true,
) {
  const params = report === "sales" ? { period } : { period, include_staff: includeStaff };
  return useAnalyticsQuery<Report[K]>([report, params], `/admin/analytics/${report}`, params, enabled);
}

export function useAnalyticsCustomers(
  period: AnalyticsPeriod,
  includeStaff: boolean,
  page: number,
  query: string,
  enabled = true,
) {
  const params = { period, include_staff: includeStaff, page, limit: 20, query: query.trim() || undefined };
  return useAnalyticsQuery<AnalyticsCustomers>(["customers", params], "/admin/analytics/customers", params, enabled);
}

export function useAnalyticsCustomer(userId: number | null, period: AnalyticsPeriod) {
  const params = { period };
  return useAnalyticsQuery<AnalyticsCustomerDetail>(
    ["customer", userId, params],
    `/admin/analytics/customers/${userId}`,
    params,
    userId !== null,
  );
}
