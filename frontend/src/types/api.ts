// Mirrors backend/app/api/schemas/*.py and backend/app/db/models/enums.py.
// Decimal fields are serialized as JSON strings by Pydantic/FastAPI, so they're typed `string`
// here and parsed with parseFloat() at render time — see src/lib/format.ts.

export type ProductUnit = "dona" | "quti" | "paket" | "komplekt";
export type CatalogSort = "default" | "price_asc" | "price_desc" | "newest";

export interface CatalogQuery {
  q: string;
  category: number | null;
  min_price: string;
  max_price: string;
  in_stock: boolean;
  sort: CatalogSort;
  page: number;
}
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

export interface OrderHistoryItem {
  id: number;
  order_number: string;
  created_at: string;
  status: OrderStatus;
  payment_status: PaymentStatus;
  order_type: OrderType;
  total: string;
}

export interface OrderTimelineEvent {
  status: OrderStatus;
  occurred_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  limit: number;
  total_pages: number;
}

export interface Profile {
  display_name: string;
  phone: string | null;
  language: "uz" | "ru";
}

export interface Address {
  id: number;
  label: string;
  address_text: string;
  address_comment: string | null;
  is_default: boolean;
}

export interface FavoriteState {
  is_favorite: boolean;
}

export interface Category {
  id: number;
  parent_id: number | null;
  name_uz: string;
  name_ru: string;
  slug: string;
  edit_version?: number;
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
  edit_version?: number;
  images: ProductImage[];
}

export type FavoritePage = Page<Product>;

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
  payment_instructions: { card_number: string; card_holder: string } | null;
  receipt_version: number;
  has_receipt: boolean;
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
  comment?: string | null;
  purchase_contract_version: 1;
  expected_total: string;
  expected_quote: string;
}

export interface CheckoutQuote {
  subtotal: string;
  delivery_fee: string | null;
  total: string | null;
  payment_methods: PaymentMethod[];
  ready: boolean;
  reasons: string[];
  quote_fingerprint: string | null;
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
  work_hours?: string | null;
  card_number: string | null;
  card_holder: string | null;
  support_username?: string | null;
  shop_phone?: string | null;
  is_shop_open: boolean | null;
  welcome_text_uz?: string | null;
  welcome_text_ru?: string | null;
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
