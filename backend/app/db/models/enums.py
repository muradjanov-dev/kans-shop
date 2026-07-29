import enum

from sqlalchemy import Enum as SAEnum


def pg_enum(enum_cls: type[enum.Enum], name: str, **kwargs) -> SAEnum:
    """Native Postgres ENUM storing the Python enum's `.value` (lowercase, per DB_SCHEMA.md)
    instead of SQLAlchemy's default of the member `.name` (uppercase)."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=True,
        values_callable=lambda obj: [e.value for e in obj],
        **kwargs,
    )


class UserSource(enum.StrEnum):
    BOT = "bot"
    WEBAPP = "webapp"


class AdminRole(enum.StrEnum):
    SUPERADMIN = "superadmin"
    MANAGER = "manager"
    OPERATOR = "operator"


class ProductUnit(enum.StrEnum):
    DONA = "dona"
    QUTI = "quti"
    PAKET = "paket"
    KOMPLEKT = "komplekt"


class OrderType(enum.StrEnum):
    DELIVERY = "delivery"
    PICKUP = "pickup"
    PREORDER = "preorder"


class OrderStatus(enum.StrEnum):
    NEW = "new"
    CONFIRMED = "confirmed"
    PREPARING = "preparing"
    DELIVERING = "delivering"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PaymentMethod(enum.StrEnum):
    CASH = "cash"
    CARD_TRANSFER = "card_transfer"
    CLICK = "click"
    PAYME = "payme"


class PaymentStatus(enum.StrEnum):
    PENDING = "pending"
    RECEIPT_UPLOADED = "receipt_uploaded"
    PAID = "paid"
    FAILED = "failed"


class BroadcastTarget(enum.StrEnum):
    ALL = "all"
    ACTIVE = "active"
    BUYERS = "buyers"


class BroadcastStatus(enum.StrEnum):
    DRAFT = "draft"
    SENDING = "sending"
    COMPLETED = "completed"
    FAILED = "failed"
