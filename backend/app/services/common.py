import math
from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_CATALOG_PAGE_SIZE = 8


@dataclass(frozen=True)
class Page[T]:
    items: Sequence[T]
    total: int
    page: int
    limit: int

    @property
    def total_pages(self) -> int:
        return max(1, math.ceil(self.total / self.limit)) if self.limit else 1

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:
        return self.page > 1
