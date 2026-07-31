from aiogram.filters.callback_data import CallbackData

# Sentinel category_id meaning "the top-level category list", used for back-navigation targets.
# Real category ids are BigInteger autoincrement starting at 1, so 0 is never a real category.
ROOT_CATEGORY_ID = 0

# Where a product detail view was opened from — determines what "back"/re-render targets.
ORIGIN_CATEGORY = "cat"
ORIGIN_SEARCH = "search"


class LanguageCallback(CallbackData, prefix="lang"):
    code: str


class CategoryCallback(CallbackData, prefix="cat"):
    category_id: int


class ProductListCallback(CallbackData, prefix="plist"):
    category_id: int
    page: int


class ProductCallback(CallbackData, prefix="prod"):
    product_id: int
    category_id: int
    page: int


class SearchPageCallback(CallbackData, prefix="spage"):
    page: int


class SearchProductCallback(CallbackData, prefix="sprod"):
    product_id: int
    page: int


# --- Product detail: quantity picker / add-to-cart / favorite ---
# `origin`+`ref_id`+`page` let these buttons re-render the exact same product detail view
# (and know how "back" should behave) regardless of whether the product was reached via
# category browsing (origin="cat", ref_id=category_id) or search (origin="search", ref_id=0).


class ProductQtyCallback(CallbackData, prefix="pqty"):
    product_id: int
    origin: str
    ref_id: int
    page: int
    qty: int
    action: str  # "inc" | "dec"


class AddToCartCallback(CallbackData, prefix="addcart"):
    product_id: int
    qty: int
    origin: str
    ref_id: int
    page: int


class FavoriteToggleCallback(CallbackData, prefix="fav"):
    product_id: int
    origin: str
    ref_id: int
    page: int


# --- Cart ---
class CartItemQtyCallback(CallbackData, prefix="citem"):
    product_id: int
    action: str  # "inc" | "dec" | "remove"


class CartActionCallback(CallbackData, prefix="cart"):
    action: str  # "clear" | "clear_confirm" | "clear_cancel" | "checkout"


# --- Checkout FSM ---
class OrderTypeCallback(CallbackData, prefix="otype"):
    value: str  # OrderType.value


class UseDefaultNameCallback(CallbackData, prefix="usename"):
    pass


class SkipStepCallback(CallbackData, prefix="skip"):
    step: str


class PaymentMethodCallback(CallbackData, prefix="pay"):
    value: str  # PaymentMethod.value


class CheckoutNavCallback(CallbackData, prefix="cknav"):
    action: str  # "back" | "cancel" | "confirm" | "edit"


# --- Order history ---
class OrderListCallback(CallbackData, prefix="olist"):
    page: int


class OrderDetailCallback(CallbackData, prefix="odetail"):
    order_id: int
    page: int


class ReorderCallback(CallbackData, prefix="reorder"):
    order_id: int


# --- Favorites ---
class FavoriteRemoveCallback(CallbackData, prefix="favrm"):
    product_id: int


# --- Admin: order notification card ---
class AdminConfirmCallback(CallbackData, prefix="aconf"):
    order_id: int


class AdminAdvanceCallback(CallbackData, prefix="aadv"):
    order_id: int
    to_status: str  # OrderStatus.value


class AdminCancelRequestCallback(CallbackData, prefix="acreq"):
    order_id: int


class AdminCancelReasonCallback(CallbackData, prefix="acrsn"):
    order_id: int
    reason: str  # "out_of_stock" | "no_response" | "rejected" | "other"


class AdminMessageCustomerCallback(CallbackData, prefix="amsg"):
    order_id: int


class AdminWriteViaBotCallback(CallbackData, prefix="awrite"):
    order_id: int


class AdminViewReceiptCallback(CallbackData, prefix="arcpt"):
    order_id: int


class AdminBackToOrderCallback(CallbackData, prefix="aback"):
    order_id: int
