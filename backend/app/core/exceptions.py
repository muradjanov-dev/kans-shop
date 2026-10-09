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


class UserNotFoundError(NotFoundError):
    code = "USER_NOT_FOUND"


class CartEmptyError(KansShopError):
    code = "CART_EMPTY"
    http_status = 400


class OutOfStockError(KansShopError):
    code = "OUT_OF_STOCK"
    http_status = 409


class MinimumOrderQuantityError(KansShopError):
    code = "MIN_ORDER_QUANTITY"
    http_status = 400


class IdempotencyConflictError(KansShopError):
    code = "IDEMPOTENCY_CONFLICT"
    http_status = 409


class AddressLimitExceededError(KansShopError):
    code = "ADDRESS_LIMIT_EXCEEDED"
    http_status = 409


class ClientUpdateRequiredError(KansShopError):
    code = "CLIENT_UPDATE_REQUIRED"
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


class AdminSessionRequiredError(UnauthorizedError):
    code = "ADMIN_SESSION_REQUIRED"


class AdminSessionInvalidError(AdminSessionRequiredError):
    """A formerly valid session was revoked because its owner or lifetime changed."""


class ForbiddenError(KansShopError):
    code = "FORBIDDEN"
    http_status = 403


class AdminRoleRequiredError(ForbiddenError):
    code = "ADMIN_ROLE_REQUIRED"


class CsrfFailedError(ForbiddenError):
    code = "CSRF_FAILED"


class UnsupportedMediaTypeError(KansShopError):
    code = "UNSUPPORTED_MEDIA_TYPE"
    http_status = 415


class GoneError(KansShopError):
    code = "GONE"
    http_status = 410


class InvalidOrExpiredAdminCodeError(UnauthorizedError):
    code = "INVALID_OR_EXPIRED_CODE"


class RateLimitedError(KansShopError):
    code = "RATE_LIMITED"
    http_status = 429


class InvalidFileError(KansShopError):
    code = "INVALID_FILE"
    http_status = 400


class OrderAlreadyProcessedError(KansShopError):
    code = "ORDER_ALREADY_PROCESSED"
    http_status = 409


class ReceiptVersionConflictError(KansShopError):
    code = "RECEIPT_VERSION_CONFLICT"
    http_status = 409


class PaymentAcceptanceUnavailableError(KansShopError):
    code = "PAYMENT_ACCEPTANCE_UNAVAILABLE"
    http_status = 409


class CategoryInUseError(KansShopError):
    code = "CATEGORY_IN_USE"
    http_status = 409


class CatalogEditConflictError(KansShopError):
    code = "ENTITY_CONFLICT"
    http_status = 409


class StoreSettingsConflictError(KansShopError):
    code = "ENTITY_CONFLICT"
    http_status = 409


class AdminAlreadyExistsError(KansShopError):
    code = "ENTITY_CONFLICT"
    http_status = 409


class LastSuperadminRequiredError(KansShopError):
    code = "LAST_SUPERADMIN_REQUIRED"
    http_status = 409


class SkuAlreadyExistsError(KansShopError):
    code = "SKU_ALREADY_EXISTS"
    http_status = 409


class PaymentGatewayError(KansShopError):
    code = "PAYMENT_GATEWAY_ERROR"
    http_status = 502


class InvalidSignatureError(KansShopError):
    code = "INVALID_SIGNATURE"
    http_status = 401


class TransactionNotFoundError(NotFoundError):
    code = "TRANSACTION_NOT_FOUND"


class AmountMismatchError(KansShopError):
    code = "AMOUNT_MISMATCH"
    http_status = 400


class PaymentAlreadyProcessedError(KansShopError):
    code = "PAYMENT_ALREADY_PROCESSED"
    http_status = 409


class PaymentNotConfiguredError(KansShopError):
    code = "PAYMENT_NOT_CONFIGURED"
    http_status = 400


class CheckoutUnavailableError(KansShopError):
    code = "CHECKOUT_UNAVAILABLE"
    http_status = 409


class QuoteChangedError(KansShopError):
    code = "QUOTE_CHANGED"
    http_status = 409


class CheckoutValidationError(KansShopError):
    code = "VALIDATION_ERROR"
    http_status = 422
