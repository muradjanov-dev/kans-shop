import math
from collections.abc import Sequence

from pydantic import BaseModel

from app.services.common import Page


class PageOut[T](BaseModel):
    items: Sequence[T]
    total: int
    page: int
    limit: int
    total_pages: int

    @classmethod
    def from_page(cls, page: Page) -> "PageOut[T]":
        total_pages = max(1, math.ceil(page.total / page.limit)) if page.limit else 1
        return cls(
            items=page.items,
            total=page.total,
            page=page.page,
            limit=page.limit,
            total_pages=total_pages,
        )
