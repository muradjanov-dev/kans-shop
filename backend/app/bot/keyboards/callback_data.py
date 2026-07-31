from aiogram.filters.callback_data import CallbackData

# Sentinel category_id meaning "the top-level category list", used for back-navigation targets.
# Real category ids are BigInteger autoincrement starting at 1, so 0 is never a real category.
ROOT_CATEGORY_ID = 0


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
