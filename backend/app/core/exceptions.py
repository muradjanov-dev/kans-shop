class KansShopError(Exception):
    """Base class for all domain errors. Carries a stable machine-readable code."""

    code: str = "INTERNAL_ERROR"
    http_status: int = 500

    def __init__(self, message: str, *, details: dict | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class NotFoundError(KansShopError):
    code = "NOT_FOUND"
    http_status = 404


class ProductNotFoundError(NotFoundError):
    code = "PRODUCT_NOT_FOUND"


class CategoryNotFoundError(NotFoundError):
    code = "CATEGORY_NOT_FOUND"


class OrderNotFoundError(NotFoundError):
    code = "ORDER_NOT_FOUND"


class CartEmptyError(KansShopError):
    code = "CART_EMPTY"
    http_status = 400


class OutOfStockError(KansShopError):
    code = "OUT_OF_STOCK"
    http_status = 409


class MinOrderAmountError(KansShopError):
    code = "MIN_ORDER_AMOUNT"
    http_status = 400


class InvalidPhoneError(KansShopError):
    code = "INVALID_PHONE"
    http_status = 400


class UnauthorizedError(KansShopError):
    code = "UNAUTHORIZED"
    http_status = 401


class ForbiddenError(KansShopError):
    code = "FORBIDDEN"
    http_status = 403


class RateLimitedError(KansShopError):
    code = "RATE_LIMITED"
    http_status = 429


class InvalidFileError(KansShopError):
    code = "INVALID_FILE"
    http_status = 400


class OrderAlreadyProcessedError(KansShopError):
    code = "ORDER_ALREADY_PROCESSED"
    http_status = 409
