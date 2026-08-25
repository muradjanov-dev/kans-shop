// Mirrors backend/app/api/schemas/*.py and backend/app/db/models/enums.py.
// Decimal fields are serialized as JSON strings by Pydantic/FastAPI, so they're typed `string`
// here and parsed with parseFloat() at render time — see src/lib/format.ts.

export type ProductUnit = "dona" | "quti" | "paket" | "komplekt";
export type OrderType = "delivery" | "pickup" | "preorder";
export type OrderStatus =
  | "new"
  | "confirmed"
  | "preparing"
  | "delivering"
  | "completed"
  | "cancelled";
export type PaymentMethod =
  | "cash"
  | "card_transfer"
  | "click"
  | "payme"
  | "paynet"
  | "tender";
export type PaymentProvider = "click" | "payme" | "paynet";
export type PaymentStatus = "pending" | "receipt_uploaded" | "paid" | "failed";

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface Category {
  id: number;
  parent_id: number | null;
  name_uz: string;
  name_ru: string;
  slug: string;
  description_uz: string | null;
  description_ru: string | null;
  image_url: string | null;
  sort_order: number;
  is_active: boolean;
  products_count: number;
}

export interface ProductImage {
  id: number;
  url: string | null;
  telegram_file_id: string | null;
  is_main: boolean;
  sort_order: number;
}

export interface Product {
  id: number;
  category_id: number;
  name_uz: string;
  name_ru: string;
  description_uz: string | null;
  description_ru: string | null;
  sku: string;
  price: string;
  old_price: string | null;
  stock_qty: number;
  unit: ProductUnit;
  min_order_qty: number;
  is_active: boolean;
  is_featured: boolean;
  lot_url: string | null;
  views_count: number;
  sold_count: number;
  images: ProductImage[];
}

export interface CartItem {
  id: number;
  product_id: number;
  quantity: number;
  price_snapshot: string;
  product: Product;
}

export interface Cart {
  items: CartItem[];
  subtotal: string;
  items_count: number;
}

export interface OrderItem {
  id: number;
  product_id: number | null;
  product_name_snapshot: string;
  product_sku_snapshot: string;
  price: string;
  quantity: number;
  total: string;
}

export interface Order {
  id: number;
  order_number: string;
  status: OrderStatus;
  order_type: OrderType;
  customer_name: string;
  customer_phone: string;
  address: string | null;
  address_comment: string | null;
  comment: string | null;
  subtotal: string;
  delivery_fee: string;
  discount: string;
  total: string;
  payment_method: PaymentMethod;
  payment_status: PaymentStatus;
  receipt_url: string | null;
  cancel_reason: string | null;
  created_at: string;
  confirmed_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  items: OrderItem[];
}

export interface CheckoutPayload {
  order_type: OrderType;
  customer_name: string;
  customer_phone: string;
  payment_method: PaymentMethod;
  address?: string | null;
  address_comment?: string | null;
  latitude?: number | null;
  longitude?: number | null;
  comment?: string | null;
}

export interface PayResponse {
  payment_url: string;
}

export interface LotLink {
  product_name: string;
  url: string;
}

export interface LotLinksResponse {
  links: LotLink[];
  missing: string[];
}

export interface PublicSettings {
  delivery_fee: number | null;
  free_delivery_from: number | null;
  min_order_amount: number | null;
  work_hours: string | null;
  card_number: string | null;
  card_holder: string | null;
  support_username: string | null;
  shop_phone: string | null;
  is_shop_open: boolean | null;
  welcome_text_uz: string | null;
  welcome_text_ru: string | null;
  enabled_payment_providers: PaymentProvider[];
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: string;
  is_admin: boolean;
}

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: Record<string, unknown>;
  };
}
