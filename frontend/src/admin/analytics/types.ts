import type { DecimalValue } from "@/admin/adminTypes";

export type AnalyticsPeriod = "today" | "week" | "month" | "quarter";

export interface AnalyticsCount {
  key: string;
  count: number;
}

export interface AnalyticsAmount {
  key: string;
  count: number;
  amount: DecimalValue;
}

export interface AnalyticsTimelinePoint {
  day: string;
  visitors: number;
  sessions: number;
  orders: number;
  revenue: DecimalValue;
}

export interface AnalyticsSalesSummary {
  orders: number;
  revenue: DecimalValue;
  paid_amount: DecimalValue;
  avg_check: DecimalValue;
  items_sold: number;
  cancelled: number;
  customers: number;
  new_customers: number;
  returning_customers: number;
}

export interface AnalyticsSummary {
  period: AnalyticsPeriod;
  since: string;
  until: string;
  visitors: number;
  new_visitors: number;
  returning_visitors: number;
  signed_in_visitors: number;
  sessions: number;
  page_views: number;
  engaged_seconds: number;
  avg_session_seconds: number;
  bounce_rate: number;
  product_views: number;
  cart_adds: number;
  conversion_rate: number;
  platforms: AnalyticsCount[];
  devices: AnalyticsCount[];
  sources: AnalyticsCount[];
  timeline: AnalyticsTimelinePoint[];
  sales: AnalyticsSalesSummary;
}

export interface AnalyticsSection {
  path: string;
  section: string;
  position: number;
  sessions: number;
  reach_rate: number;
  total_seconds: number;
  avg_seconds: number;
}

export interface AnalyticsPageStat {
  path: string;
  views: number;
  sessions: number;
  total_seconds: number;
  avg_seconds: number;
}

export interface AnalyticsScroll {
  path: string;
  page_views: number;
  reached_25: number;
  reached_50: number;
  reached_75: number;
  reached_90: number;
}

export interface AnalyticsClick {
  section: string | null;
  target: string | null;
  label: string | null;
  clicks: number;
  sessions: number;
}

export interface AnalyticsSearch {
  term: string;
  searches: number;
  sessions: number;
  zero_results: number;
}

export interface AnalyticsFunnelStep {
  key: string;
  sessions: number;
}

export interface AnalyticsBehavior {
  period: AnalyticsPeriod;
  sessions: number;
  sections: AnalyticsSection[];
  pages: AnalyticsPageStat[];
  scroll: AnalyticsScroll[];
  clicks: AnalyticsClick[];
  funnel: AnalyticsFunnelStep[];
  hours: number[];
  searches: AnalyticsSearch[];
  filters: AnalyticsCount[];
  carousel: AnalyticsCount[];
}

export interface AnalyticsProductInterest {
  product_id: number;
  name: string;
  price: DecimalValue | null;
  image_url: string | null;
  impressions: number;
  views: number;
  viewers: number;
  view_seconds: number;
  cart_adds: number;
  favorites: number;
  ordered_qty: number;
  revenue: DecimalValue;
}

export interface AnalyticsProducts {
  period: AnalyticsPeriod;
  products: AnalyticsProductInterest[];
  interested_not_bought: AnalyticsProductInterest[];
}

export interface AnalyticsCustomer {
  user_id: number;
  name: string;
  username: string | null;
  phone: string | null;
  sessions: number;
  engaged_seconds: number;
  page_views: number;
  first_seen: string;
  last_seen: string;
  platform: string;
  products_viewed: number;
  cart_adds: number;
  orders: number;
  revenue: DecimalValue;
  interests: string[];
}

export interface AnalyticsCustomers {
  period: AnalyticsPeriod;
  items: AnalyticsCustomer[];
  total: number;
  page: number;
  limit: number;
  guest_visitors: number;
  guest_sessions: number;
}

export interface AnalyticsCustomerSession {
  started_at: string;
  last_seen_at: string;
  engaged_seconds: number;
  page_views: number;
  platform: string;
  device: string;
  entry_path: string | null;
}

export interface AnalyticsCustomerProduct {
  product_id: number;
  name: string;
  views: number;
  view_seconds: number;
  cart_adds: number;
  favorites: number;
  ordered_qty: number;
}

export interface AnalyticsCustomerEvent {
  occurred_at: string;
  type: string;
  path: string | null;
  section: string | null;
  target: string | null;
  label: string | null;
  product_name: string | null;
  value: number | null;
}

export interface AnalyticsCustomerDetail {
  period: AnalyticsPeriod;
  customer: AnalyticsCustomer;
  sessions: AnalyticsCustomerSession[];
  products: AnalyticsCustomerProduct[];
  searches: string[];
  events: AnalyticsCustomerEvent[];
}

export interface AnalyticsHeatCell {
  weekday: number;
  hour: number;
  orders: number;
}

export interface AnalyticsSales {
  period: AnalyticsPeriod;
  summary: AnalyticsSalesSummary;
  statuses: AnalyticsAmount[];
  payment_methods: AnalyticsAmount[];
  order_types: AnalyticsAmount[];
  categories: AnalyticsAmount[];
  top_products: Array<{ name: string; quantity: number; revenue: DecimalValue }>;
  top_customers: Array<{ user_id: number; name: string; orders: number; revenue: DecimalValue }>;
  heatmap: AnalyticsHeatCell[];
  avg_items_per_order: number;
}
