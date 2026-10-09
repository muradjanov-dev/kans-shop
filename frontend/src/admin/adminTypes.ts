import type { AdminRole, AdminSession } from "@/admin/api";

export type DecimalValue = string | number;

export interface AdminPage<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export type OrderStatus = "new" | "confirmed" | "preparing" | "delivering" | "completed" | "cancelled";
export type PaymentStatus = "pending" | "receipt_uploaded" | "paid" | "failed";
export type OrderType = "delivery" | "pickup" | "preorder";

export interface AdminOrderItem {
  id: number;
  product_id: number | null;
  product_name_snapshot: string;
  product_sku_snapshot: string;
  price: DecimalValue;
  quantity: number;
  total: DecimalValue;
}

export interface AdminOrder {
  id: number;
  order_number: string;
  status: OrderStatus;
  order_type: OrderType;
  customer_name: string;
  customer_phone: string;
  address: string | null;
  address_comment: string | null;
  comment: string | null;
  subtotal: DecimalValue;
  delivery_fee: DecimalValue;
  discount: DecimalValue;
  total: DecimalValue;
  payment_method: string;
  payment_status: PaymentStatus;
  receipt_url: string | null;
  payment_instructions: Record<string, unknown> | null;
  receipt_version: number;
  payment_reviewed_by_admin_id: number | null;
  payment_reviewed_at: string | null;
  cancel_reason: string | null;
  created_at: string;
  confirmed_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  has_receipt: boolean;
  items: AdminOrderItem[];
}

export interface AdminOrderDetail extends AdminOrder {
  status_history: Array<{
    id: number;
    from_status: OrderStatus | null;
    to_status: OrderStatus;
    changed_by_admin_id: number | null;
    comment: string | null;
    created_at: string;
  }>;
  payment_history: Array<{
    id: number;
    provider: string;
    state: string;
    amount: DecimalValue;
    created_at: string;
  }>;
  payment_review_history: Array<{
    id: number;
    actor_admin_id: number | null;
    actor_name_snapshot: string | null;
    action: string;
    created_at: string;
  }>;
}

export interface ProductImage {
  id: number;
  url: string | null;
  telegram_file_id: string | null;
  is_main: boolean;
  sort_order: number;
}

export interface AdminProduct {
  id: number;
  category_id: number;
  name_uz: string;
  name_ru: string;
  description_uz: string | null;
  description_ru: string | null;
  sku: string;
  barcode: string | null;
  price: DecimalValue;
  old_price: DecimalValue | null;
  stock_qty: number;
  unit: "dona" | "quti" | "paket" | "komplekt";
  min_order_qty: number;
  is_active: boolean;
  is_featured: boolean;
  lot_url: string | null;
  sort_order: number;
  views_count: number;
  sold_count: number;
  edit_version: number;
  images: ProductImage[];
}

export interface AdminCategory {
  id: number;
  parent_id: number | null;
  name_uz: string;
  name_ru: string;
  slug: string;
  description_uz: string | null;
  description_ru: string | null;
  image_url: string | null;
  sort_order: number;
  edit_version: number;
  is_active: boolean;
  products_count: number;
}

export interface AdminUser {
  id: number;
  telegram_id: number;
  username: string | null;
  first_name: string;
  last_name: string | null;
  phone: string | null;
  language: string;
  is_blocked: boolean;
  source: string;
  created_at: string;
  last_active_at: string | null;
}

export interface AdminUserDetail extends AdminUser {
  orders_count: number;
  first_touch_source: { id: number; name: string; code: string } | null;
}

export interface AdminStoreSettings {
  version: number;
  delivery_fee: string | null;
  free_delivery_from: string | null;
  min_order_amount: string | null;
  work_hours: string | null;
  card_number: string | null;
  card_holder: string | null;
  support_username: string | null;
  shop_phone: string | null;
  is_shop_open: boolean | null;
  welcome_text_uz: string | null;
  welcome_text_ru: string | null;
  readiness: Record<string, boolean>;
}

export type AdminStoreSettingsDraft = Omit<AdminStoreSettings, "version" | "readiness">;

export interface AdminStatsOverview {
  period: "today" | "week" | "month";
  orders_count: number;
  order_value: DecimalValue;
  paid_amount: DecimalValue;
  /** API compatibility field; display it using the order_value label. */
  revenue: DecimalValue;
  avg_check: DecimalValue;
  new_users: number;
  top_products: Array<{ name: string; sold: number }>;
}

export interface AdminTeamMember {
  id: number;
  telegram_id: number;
  full_name: string;
  role: AdminRole;
  is_active: boolean;
  notifications_enabled: boolean;
  created_at: string;
}

export interface AdminTrafficSource {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  clicks_count: number;
  created_at: string;
}

export interface AdminTrafficSourceDetail {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  bot_link: string;
  clicks: number;
  first_touch_users: number;
  orders_count: number;
  order_value: DecimalValue;
  created_at: string;
}

export interface AdminAuditEvent {
  id: number;
  created_at: string;
  actor_admin_id: number | null;
  actor_name_snapshot: string | null;
  action: string;
  resource_type: string;
  resource_id: string | null;
  request_id: string;
  before_json: Record<string, unknown> | null;
  after_json: Record<string, unknown> | null;
}

export type AdminBroadcastTarget = "all" | "active" | "buyers";
export type AdminBroadcastStatus = "draft" | "sending" | "completed" | "failed" | "cancelled";

export interface AdminBroadcastContent {
  target: AdminBroadcastTarget;
  text: string;
  photo_storage_key: string | null;
  photo_file_id: string | null;
  button_text: string | null;
  button_url: string | null;
}

export interface AdminBroadcastPreviewIn extends AdminBroadcastContent {}

export interface AdminBroadcastDraftIn extends AdminBroadcastContent {
  preview_fingerprint: string;
  preview_content_fingerprint: string;
  preview_count: number;
}

export interface AdminBroadcastLaunchIn {
  preview_fingerprint: string;
  preview_count: number;
  idempotency_key: string;
}

export interface AdminBroadcastPreview {
  preview_fingerprint: string;
  preview_content_fingerprint: string;
  preview_count: number;
}

export interface AdminBroadcastMediaOut {
  photo_storage_key: string;
}

export interface AdminBroadcast extends AdminBroadcastContent {
  id: number;
  status: AdminBroadcastStatus;
  sent_count: number;
  failed_count: number;
  pending_count: number;
  sending_count: number;
  cancelled_count: number;
  created_at: string;
  launched_at: string | null;
}

export type AdminSessionContext = AdminSession;
