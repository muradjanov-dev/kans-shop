"""Shared inventory policy for the bot and public storefront."""

from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.repositories import setting_repository

STOCK_TRACKING_SETTING = "stock_tracking_enabled"


class _MinimumOrderProduct(Protocol):
    min_order_qty: int


@dataclass(frozen=True)
class InventoryPolicy:
    """The current shop policy while preserving product stock as real inventory data."""

    stock_tracking_enabled: bool

    def minimum_quantity(self, product: _MinimumOrderProduct) -> int:
        if not self.stock_tracking_enabled:
            return 1
        return max(1, product.min_order_qty)


async def get_inventory_policy(session: AsyncSession) -> InventoryPolicy:
    value = await setting_repository.get_value(session, STOCK_TRACKING_SETTING, True)
    # The safe default preserves the existing no-oversell behavior for missing or malformed
    # settings. Do not accept strings such as "false" as a boolean.
    enabled = value if isinstance(value, bool) else True
    return InventoryPolicy(stock_tracking_enabled=enabled)
