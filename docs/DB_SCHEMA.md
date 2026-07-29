# Kans Shop — Database Schema

PostgreSQL 15+. All tables use `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`,
`created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()`
(updated via SQLAlchemy `onupdate=func.now()`). Money is `NUMERIC(12,2)` in UZS (no decimals in
practice, but NUMERIC avoids float rounding). Tables that are user-facing catalog data get
`is_active BOOLEAN NOT NULL DEFAULT true` for soft delete.

## users
| column | type | notes |
|---|---|---|
| telegram_id | BIGINT | UNIQUE, NOT NULL, indexed |
| username | VARCHAR(64) | nullable |
| first_name | VARCHAR(128) | |
| last_name | VARCHAR(128) | nullable |
| phone | VARCHAR(20) | nullable, E.164 |
| language | VARCHAR(2) | `uz`/`ru`, default `uz` |
| is_blocked | BOOLEAN | default false |
| is_admin | BOOLEAN | default false (denormalized flag; source of truth is `admins`) |
| last_active_at | TIMESTAMPTZ | nullable |
| source | VARCHAR(10) | `bot` / `webapp` — how the user first registered |

## admins
| column | type | notes |
|---|---|---|
| telegram_id | BIGINT | UNIQUE, NOT NULL |
| full_name | VARCHAR(128) | |
| role | ENUM admin_role | `superadmin`, `manager`, `operator` |
| is_active | BOOLEAN | default true |
| notifications_enabled | BOOLEAN | default true |

Role capability matrix (enforced in `core/security.py` + FastAPI deps + bot middleware):
- `superadmin` — everything, incl. admin management.
- `manager` — product/category CRUD + orders.
- `operator` — orders: view + status change only.

## categories
| column | type | notes |
|---|---|---|
| parent_id | BIGINT FK → categories.id | nullable, self-referencing (2 levels used) |
| name_uz, name_ru | VARCHAR(128) | |
| slug | VARCHAR(160) | UNIQUE |
| description_uz, description_ru | TEXT | nullable |
| image_url | TEXT | nullable |
| image_file_id | VARCHAR(255) | nullable (Telegram file_id) |
| sort_order | INT | default 0 |
| is_active | BOOLEAN | default true |
| products_count | INT | denormalized, maintained by product_service on create/deactivate |

## products
| column | type | notes |
|---|---|---|
| category_id | BIGINT FK → categories.id | NOT NULL |
| name_uz, name_ru | VARCHAR(255) | |
| description_uz, description_ru | TEXT | nullable |
| sku | VARCHAR(64) | UNIQUE |
| barcode | VARCHAR(64) | nullable |
| price | NUMERIC(12,2) | NOT NULL |
| old_price | NUMERIC(12,2) | nullable, for discount display |
| stock_qty | INT | NOT NULL, default 0 |
| unit | ENUM product_unit | `dona`,`quti`,`paket`,`komplekt` |
| min_order_qty | INT | default 1 |
| is_active | BOOLEAN | default true |
| is_featured | BOOLEAN | default false |
| sort_order | INT | default 0 |
| views_count | INT | default 0 |
| sold_count | INT | default 0 |

Index: GIN `pg_trgm` on `name_uz`, `name_ru` for search; btree on `category_id`, `is_active`.

## product_images
| column | type | notes |
|---|---|---|
| product_id | BIGINT FK → products.id | ON DELETE CASCADE |
| url | TEXT | nullable (Mini App) |
| telegram_file_id | VARCHAR(255) | nullable (bot) |
| is_main | BOOLEAN | default false |
| sort_order | INT | default 0 |

Both `url` and `telegram_file_id` are populated when an admin uploads via the bot: the bot keeps
`telegram_file_id` for fast re-send, the same bytes are also written to
`MEDIA_ROOT/products/{product_id}/...` and `url` set for the Mini App/admin panel.

## carts / cart_items
`carts`: `user_id` FK → users.id, **UNIQUE** (one active cart per user), `is_active`.
`cart_items`: `cart_id` FK, `product_id` FK, `quantity` INT ≥ 1, `price_snapshot` NUMERIC(12,2)
(price at the moment the item was added — used only for display before checkout; the order itself
re-snapshots at creation time), `UNIQUE(cart_id, product_id)`.

## orders
| column | type | notes |
|---|---|---|
| order_number | VARCHAR(20) | UNIQUE, `KANS-000123`, generated from a DB sequence |
| user_id | BIGINT FK → users.id | |
| order_type | ENUM order_type | `delivery`, `pickup`, `preorder` |
| status | ENUM order_status | `new`,`confirmed`,`preparing`,`delivering`,`completed`,`cancelled` |
| customer_name | VARCHAR(128) | |
| customer_phone | VARCHAR(20) | E.164 `+998XXXXXXXXX` |
| address, address_comment | TEXT | nullable, delivery only |
| latitude, longitude | NUMERIC(9,6) | nullable |
| comment | TEXT | nullable, customer note |
| subtotal, delivery_fee, discount, total | NUMERIC(12,2) | |
| payment_method | ENUM payment_method | `cash`,`card_transfer`,`click`,`payme` |
| payment_status | ENUM payment_status | `pending`,`receipt_uploaded`,`paid`,`failed` |
| receipt_file_id | VARCHAR(255) | nullable |
| receipt_url | TEXT | nullable |
| processed_by_admin_id | BIGINT FK → admins.id | nullable |
| confirmed_at, completed_at, cancelled_at | TIMESTAMPTZ | nullable |
| cancel_reason | TEXT | nullable |
| admin_message_ids | JSONB | `{"<admin_telegram_id>": <message_id>}` |
| source | VARCHAR(10) | `bot` / `webapp` |

## order_items
`order_id` FK, `product_id` FK → products.id **ON DELETE SET NULL**, `product_name_snapshot`,
`product_sku_snapshot`, `price` NUMERIC(12,2), `quantity` INT, `total` NUMERIC(12,2). Snapshots are
mandatory: price/name changes on the live product must never mutate historical orders.

## order_status_history
`order_id` FK, `from_status`, `to_status` (order_status enum, `from_status` nullable for the
initial `new` row), `changed_by_admin_id` FK → admins.id nullable (null = system), `comment`
nullable, `created_at`.

## settings
`key` VARCHAR(64) UNIQUE, `value` JSONB, `description` TEXT. Seeded keys: `delivery_fee`,
`free_delivery_from`, `min_order_amount`, `work_hours`, `card_number`, `card_holder`,
`support_username`, `shop_phone`, `is_shop_open`, `welcome_text_uz`, `welcome_text_ru`.

## broadcasts
`admin_id` FK → admins.id, `text` TEXT, `photo_file_id` VARCHAR(255) nullable, `button_text`
nullable, `button_url` nullable, `target` ENUM broadcast_target (`all`,`active`,`buyers`), `status`
ENUM broadcast_status (`draft`,`sending`,`completed`,`failed`), `sent_count` INT default 0,
`failed_count` INT default 0.

## favorites
`user_id` FK → users.id, `product_id` FK → products.id, `UNIQUE(user_id, product_id)`.

## Indexes (explicit, beyond PK/UNIQUE)
- `users(telegram_id)`
- `products(category_id)`, `products(is_active)`
- `orders(user_id)`, `orders(status)`, `orders(created_at DESC)`
- `cart_items(cart_id)`
- `GIN (name_uz gin_trgm_ops)`, `GIN (name_ru gin_trgm_ops)` on `products` (requires
  `CREATE EXTENSION pg_trgm`)

## Enums (Postgres native ENUM, mirrored as Python `enum.Enum`)
`admin_role`, `product_unit`, `order_type`, `order_status`, `payment_method`, `payment_status`,
`broadcast_target`, `broadcast_status`.
