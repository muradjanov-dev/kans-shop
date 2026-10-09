import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { AxiosRequestConfig } from "axios";
import { useAdminAuth } from "@/admin/AdminAuthProvider";
import { adminApi } from "@/admin/api";
import type {
  AdminAuditEvent,
  AdminBroadcast,
  AdminBroadcastDraftIn,
  AdminBroadcastLaunchIn,
  AdminBroadcastMediaOut,
  AdminBroadcastPreview,
  AdminBroadcastPreviewIn,
  AdminCategory,
  AdminOrder,
  AdminOrderDetail,
  AdminPage,
  AdminProduct,
  AdminStatsOverview,
  AdminStoreSettings,
  AdminTeamMember,
  AdminTrafficSource,
  AdminTrafficSourceDetail,
  AdminUser,
  AdminUserDetail,
} from "@/admin/adminTypes";

export const adminQueryKeys = {
  root: ["admin"] as const,
  dashboard: () => ["admin", "dashboard"] as const,
  orders: (filters: AdminOrderFilters = {}) => ["admin", "orders", filters] as const,
  order: (id: number) => ["admin", "orders", id] as const,
  categories: () => ["admin", "categories"] as const,
  products: (categoryId: number) => ["admin", "products", categoryId] as const,
  product: (id: number) => ["admin", "product", id] as const,
  users: (query: string, page: number) => ["admin", "users", query, page] as const,
  user: (id: number) => ["admin", "user", id] as const,
  stats: (period: AdminPeriod) => ["admin", "stats", period] as const,
  settings: () => ["admin", "settings"] as const,
  team: (page: number) => ["admin", "team", page] as const,
  sources: (page: number) => ["admin", "sources", page] as const,
  source: (id: number) => ["admin", "source", id] as const,
  audit: (filters: AdminAuditFilters) => ["admin", "audit", filters] as const,
  broadcast: (id: number) => ["admin", "broadcast", id] as const,
};

export interface AdminOrderFilters {
  status?: string;
  query?: string;
  date_from?: string;
  date_to?: string;
  page?: number;
  limit?: number;
}

export interface AdminAuditFilters {
  action?: string;
  resource_type?: string;
  actor_admin_id?: number;
  request_id?: string;
  page?: number;
  limit?: number;
}

export type AdminPeriod = "today" | "week" | "month";

function useAdminQuery<T>(
  queryKey: readonly unknown[],
  queryFn: () => Promise<T>,
  options: { enabled?: boolean } = {},
) {
  const { session, status } = useAdminAuth();
  return useQuery({
    queryKey: [...queryKey, session?.admin_id ?? "anonymous"],
    queryFn,
    enabled: status === "authenticated" && Boolean(session) && options.enabled !== false,
  });
}

async function get<T>(path: string, config?: AxiosRequestConfig): Promise<T> {
  return (await adminApi.get<T>(path, config)).data;
}

async function send<T>(method: "post" | "patch" | "put", path: string, body?: unknown): Promise<T> {
  return (await adminApi[method]<T>(path, body)).data;
}

export function useAdminOrders(filters: AdminOrderFilters = {}) {
  const normalized = { page: 1, limit: 20, ...filters };
  return useAdminQuery(
    adminQueryKeys.orders(normalized),
    () => get<AdminPage<AdminOrder>>("/admin/orders", { params: normalized }),
  );
}

export function useAdminOrder(id: number | null) {
  return useAdminQuery(
    adminQueryKeys.order(id ?? 0),
    () => get<AdminOrderDetail>(`/admin/orders/${id}`),
    { enabled: id !== null },
  );
}

export async function updateAdminOrderStatus(id: number, body: { status: string; comment?: string }) {
  return send<AdminOrder>("patch", `/admin/orders/${id}/status`, body);
}

export async function acceptAdminOrderPayment(id: number, expectedReceiptVersion: number) {
  return send<AdminOrder>("post", `/admin/orders/${id}/payment/accept`, { expected_receipt_version: expectedReceiptVersion });
}

export async function queueAdminOrderMessage(id: number, text: string, idempotencyKey: string) {
  return send<{ message_id: number; state: "queued" }>("post", `/admin/orders/${id}/message`, { text, idempotency_key: idempotencyKey });
}

export async function readAdminOrderReceipt(id: number): Promise<Blob> {
  return get<Blob>(`/orders/${id}/receipt`, { responseType: "blob" });
}

export function useAdminCategories() {
  return useAdminQuery(adminQueryKeys.categories(), () => get<AdminCategory[]>("/admin/categories"));
}

export async function getAdminCategories() {
  return get<AdminCategory[]>("/admin/categories");
}

export function useAdminProducts(categoryId: number | null) {
  return useAdminQuery(
    adminQueryKeys.products(categoryId ?? 0),
    () => get<AdminPage<AdminProduct>>("/admin/products", { params: { category_id: categoryId, page: 1, limit: 100 } }),
    { enabled: categoryId !== null },
  );
}

export function useAdminProduct(id: number | null) {
  return useAdminQuery(
    adminQueryKeys.product(id ?? 0),
    () => get<AdminProduct>(`/admin/products/${id}`),
    { enabled: id !== null },
  );
}

export async function getAdminProduct(id: number) {
  return get<AdminProduct>(`/admin/products/${id}`);
}

export async function createAdminProduct(body: Record<string, unknown>) {
  return send<AdminProduct>("post", "/admin/products", body);
}

export async function updateAdminProduct(id: number, body: Record<string, unknown>) {
  return send<AdminProduct>("patch", `/admin/products/${id}`, body);
}

export async function deleteAdminProduct(id: number) {
  await adminApi.delete(`/admin/products/${id}`);
}

export async function uploadAdminProductImage(id: number, file: File) {
  const data = new FormData();
  data.append("file", file);
  return send<AdminProduct>("post", `/admin/products/${id}/images`, data);
}

export async function updateAdminProductImage(id: number, imageId: number, body: { is_main: boolean; sort_order: number }) {
  return send<AdminProduct>("patch", `/admin/products/${id}/images/${imageId}`, body);
}

export async function deleteAdminProductImage(id: number, imageId: number) {
  return (await adminApi.delete<AdminProduct>(`/admin/products/${id}/images/${imageId}`)).data;
}

export async function createAdminCategory(body: Record<string, unknown>) {
  return send<AdminCategory>("post", "/admin/categories", body);
}

export async function updateAdminCategory(id: number, body: Record<string, unknown>) {
  return send<AdminCategory>("patch", `/admin/categories/${id}`, body);
}

export async function moveAdminCategory(id: number, body: { parent_id: number | null; expected_edit_version: number }) {
  return send<AdminCategory>("patch", `/admin/categories/${id}/move`, body);
}

export async function deleteAdminCategory(id: number) {
  await adminApi.delete(`/admin/categories/${id}`);
}

export async function uploadAdminCategoryImage(id: number, file: File) {
  const data = new FormData();
  data.append("file", file);
  return send<AdminCategory>("put", `/admin/categories/${id}/image`, data);
}

export async function deleteAdminCategoryImage(id: number) {
  return (await adminApi.delete<AdminCategory>(`/admin/categories/${id}/image`)).data;
}

export function useAdminUsers(query: string, page = 1) {
  return useAdminQuery(
    adminQueryKeys.users(query, page),
    () => get<AdminPage<AdminUser>>("/admin/users", { params: { query: query || undefined, page, limit: 20 } }),
  );
}

export function useAdminUser(id: number | null) {
  return useAdminQuery(
    adminQueryKeys.user(id ?? 0),
    () => get<AdminUserDetail>(`/admin/users/${id}`),
    { enabled: id !== null },
  );
}

export async function setAdminUserBlocked(id: number, blocked: boolean) {
  return send<AdminUser>("patch", `/admin/users/${id}/block`, { blocked });
}

export function useAdminStats(period: AdminPeriod) {
  return useAdminQuery(adminQueryKeys.stats(period), () => get<AdminStatsOverview>("/admin/stats/overview", { params: { period } }));
}

export async function exportAdminStats(period: AdminPeriod, language: "uz" | "ru") {
  return get<Blob>("/admin/stats/export.xlsx", {
    params: { period },
    responseType: "blob",
    headers: { "Accept-Language": language },
  });
}

export function useAdminSettings() {
  return useAdminQuery(adminQueryKeys.settings(), () => get<AdminStoreSettings>("/admin/settings"));
}

export async function getAdminSettings() {
  return get<AdminStoreSettings>("/admin/settings");
}

export async function updateAdminSettings(body: Record<string, unknown>) {
  return send<AdminStoreSettings>("patch", "/admin/settings", body);
}

export function useAdminTeam(page = 1) {
  return useAdminQuery(adminQueryKeys.team(page), () => get<AdminPage<AdminTeamMember>>("/admin/team", { params: { page, limit: 100 } }));
}

export async function createAdminTeamMember(body: { telegram_id: number; full_name: string; role: string }) {
  return send<AdminTeamMember>("post", "/admin/team", body);
}

export async function updateAdminTeamMember(id: number, body: Record<string, unknown>) {
  return send<AdminTeamMember>("patch", `/admin/team/${id}`, body);
}

export async function deleteAdminTeamMember(id: number) {
  await adminApi.delete(`/admin/team/${id}`);
}

export async function revokeAdminTeamSessions(id: number) {
  return send<{ revoked_sessions: number }>("post", `/admin/team/${id}/sessions/revoke`);
}

export function useAdminSources(page = 1) {
  return useAdminQuery(adminQueryKeys.sources(page), () => get<AdminPage<AdminTrafficSource>>("/admin/sources", { params: { page, limit: 100 } }));
}

export function useAdminSource(id: number | null) {
  return useAdminQuery(
    adminQueryKeys.source(id ?? 0),
    () => get<AdminTrafficSourceDetail>(`/admin/sources/${id}`),
    { enabled: id !== null },
  );
}

export async function createAdminSource(body: { name: string; code: string }) {
  return send<AdminTrafficSource>("post", "/admin/sources", body);
}

export async function updateAdminSource(id: number, body: { name?: string; active?: boolean }) {
  return send<AdminTrafficSourceDetail>("patch", `/admin/sources/${id}`, body);
}

export function useAdminAudit(filters: AdminAuditFilters) {
  const normalized = { page: 1, limit: 20, ...filters };
  return useAdminQuery(adminQueryKeys.audit(normalized), () => get<AdminPage<AdminAuditEvent>>("/admin/audit", { params: normalized }));
}

export async function invalidateAdminCatalog(queryClient: ReturnType<typeof useQueryClient>) {
  await queryClient.invalidateQueries({ queryKey: ["admin", "categories"] });
  await queryClient.invalidateQueries({ queryKey: ["admin", "products"] });
  await queryClient.invalidateQueries({ queryKey: ["admin", "product"] });
}

export async function uploadAdminBroadcastPhoto(file: File): Promise<AdminBroadcastMediaOut> {
  const data = new FormData();
  data.append("file", file);
  return (await adminApi.post<AdminBroadcastMediaOut>("/admin/broadcasts/media", data)).data;
}

export async function previewAdminBroadcast(content: AdminBroadcastPreviewIn): Promise<AdminBroadcastPreview> {
  return send<AdminBroadcastPreview>("post", "/admin/broadcasts/preview", content);
}

export async function createAdminBroadcastDraft(body: AdminBroadcastDraftIn): Promise<AdminBroadcast> {
  return send<AdminBroadcast>("post", "/admin/broadcasts", body);
}

export async function launchAdminBroadcast(id: number, body: AdminBroadcastLaunchIn): Promise<AdminBroadcast> {
  return send<AdminBroadcast>("post", `/admin/broadcasts/${id}/launch`, body);
}

export async function getAdminBroadcastProgress(id: number): Promise<AdminBroadcast> {
  return get<AdminBroadcast>(`/admin/broadcasts/${id}`);
}

export async function cancelAdminBroadcast(id: number): Promise<AdminBroadcast> {
  return send<AdminBroadcast>("post", `/admin/broadcasts/${id}/cancel`);
}

export function useAdminBroadcastProgress(id: number | null) {
  const { session, status } = useAdminAuth();
  return useQuery({
    queryKey: [...adminQueryKeys.broadcast(id ?? 0), session?.admin_id ?? "anonymous"],
    queryFn: () => getAdminBroadcastProgress(id!),
    enabled: status === "authenticated" && Boolean(session) && id !== null,
    refetchInterval: (query) => query.state.data?.status === "sending" ? 2000 : false,
  });
}
