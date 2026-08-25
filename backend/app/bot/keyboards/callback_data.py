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


# --- Admin: main menu ---
class AdminMenuCallback(CallbackData, prefix="amenu"):
    section: str  # "orders" | "categories" | "products" | "stats" | "broadcast" | "users" | "settings"


# --- Admin: categories ---
class AdminCategoryListCallback(CallbackData, prefix="acatl"):
    parent_id: int  # ROOT_CATEGORY_ID = top level


class AdminCategoryDetailCallback(CallbackData, prefix="acatd"):
    category_id: int


class AdminCategoryActionCallback(CallbackData, prefix="acata"):
    category_id: int
    action: str  # "toggle_active" | "delete_request" | "delete_confirm" | "add_sub"


# --- Admin: products ---
class AdminProductListCallback(CallbackData, prefix="aprodl"):
    category_id: int
    page: int


class AdminProductDetailCallback(CallbackData, prefix="aprodd"):
    product_id: int


class AdminProductFieldEditCallback(CallbackData, prefix="aprodf"):
    product_id: int
    field: str  # "name_uz" | "name_ru" | "description_uz" | "description_ru" | "price" | "sku"


class AdminProductActionCallback(CallbackData, prefix="aproda"):
    product_id: int
    action: str
    # "toggle_active" | "delete_request" | "delete_confirm" | "add_photo" | "finish_add_photo"
    # | "stock_p10" | "stock_p50" | "stock_m1" | "stock_custom"


class AdminUnitCallback(CallbackData, prefix="aunit"):
    value: str  # ProductUnit.value


class AdminProductCategoryChooseCallback(CallbackData, prefix="aprodcc"):
    category_id: int


class AdminImagesFinishCallback(CallbackData, prefix="aimgfin"):
    pass


class AdminFormCancelCallback(CallbackData, prefix="acancel"):
    pass


class AdminFormSaveCallback(CallbackData, prefix="asave"):
    pass


# --- Admin: orders list ---
class AdminOrderFilterCallback(CallbackData, prefix="aofilt"):
    status: str  # "all" or OrderStatus.value
    page: int


# --- Admin: users ---
class AdminUserListCallback(CallbackData, prefix="ausrl"):
    page: int


class AdminUserActionCallback(CallbackData, prefix="ausra"):
    user_id: int
    action: str  # "block" | "unblock"


# --- Admin: settings ---
class AdminSettingEditCallback(CallbackData, prefix="asetf"):
    key: str


# --- Admin: broadcast ---
class BroadcastButtonChoiceCallback(CallbackData, prefix="bcbtn"):
    add_button: bool


class BroadcastTargetCallback(CallbackData, prefix="bctgt"):
    target: str  # "all" | "active" | "buyers"


class BroadcastConfirmCallback(CallbackData, prefix="bcconf"):
    action: str  # "send" | "cancel"


# --- Admin: stats ---
class StatsPeriodCallback(CallbackData, prefix="statp"):
    period: str  # "today" | "week" | "month"


class StatsExportCallback(CallbackData, prefix="statexp"):
    period: str


# --- Mandatory channel subscription ---
# The one callback the subscription gate lets through, so a user who has just joined can
# re-run the check without being blocked by the very middleware they are trying to satisfy.
class CheckSubscriptionCallback(CallbackData, prefix="checksub"):
    pass


# --- Main menu (inline) ---
# Replaces the old persistent reply keyboard; `action` mirrors the menu.* locale keys.
class MenuCallback(CallbackData, prefix="mainmenu"):
    action: str  # "catalog" | "cart" | "orders" | "favorites" | "about" | "contact"
    #             | "settings" | "admin" | "menu"


# --- Admin: traffic sources (campaign deep links) ---
class AdminSourceDetailCallback(CallbackData, prefix="asrcd"):
    source_id: int


class AdminSourceActionCallback(CallbackData, prefix="asrca"):
    source_id: int
    action: str  # "toggle" | "delete_request" | "delete_confirm"


class AdminSourceAddCallback(CallbackData, prefix="asrcadd"):
    pass


# --- Admin: managing admins themselves (superadmin only) ---
class AdminManageDetailCallback(CallbackData, prefix="amngd"):
    admin_id: int


class AdminManageActionCallback(CallbackData, prefix="amnga"):
    admin_id: int
    action: str  # "toggle" | "remove_request" | "remove_confirm" | "role_menu"


class AdminManageAddCallback(CallbackData, prefix="amngadd"):
    pass


class AdminRoleChooseCallback(CallbackData, prefix="amngrole"):
    admin_id: int  # 0 while creating a not-yet-persisted admin
    role: str
