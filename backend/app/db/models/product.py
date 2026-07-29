from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.models.enums import ProductUnit, pg_enum
from app.db.models.mixins import IDMixin, TimestampMixin

if TYPE_CHECKING:
    from app.db.models.category import Category
    from app.db.models.product_image import ProductImage


class Product(IDMixin, TimestampMixin, Base):
    __tablename__ = "products"

    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    name_uz: Mapped[str] = mapped_column(String(255), nullable=False)
    name_ru: Mapped[str] = mapped_column(String(255), nullable=False)
    description_uz: Mapped[str | None] = mapped_column(Text)
    description_ru: Mapped[str | None] = mapped_column(Text)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(64))
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    old_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    stock_qty: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    unit: Mapped[ProductUnit] = mapped_column(
        pg_enum(ProductUnit, "product_unit"), nullable=False
    )
    min_order_qty: Mapped[int] = mapped_column(Integer, server_default="1", nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, server_default="true", nullable=False, index=True
    )
    is_featured: Mapped[bool] = mapped_column(Boolean, server_default="false", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    views_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)
    sold_count: Mapped[int] = mapped_column(Integer, server_default="0", nullable=False)

    category: Mapped["Category"] = relationship("Category")
    images: Mapped[list["ProductImage"]] = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.sort_order",
    )

    def __repr__(self) -> str:
        return f"<Product id={self.id} sku={self.sku}>"
