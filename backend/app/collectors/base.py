from abc import ABC, abstractmethod
from dataclasses import dataclass
from ..schemas.domain import RawItem


@dataclass(frozen=True)
class CollectorCapabilities:
    """What a source adapter can do; the intelligence layer schedules by capability,
    not by slug. New adapters must fill this honestly — healthcheck defaults to True."""

    search: bool = True
    timeline: bool = False
    comments: bool = False
    profile: bool = False
    detail: bool = False
    historical: bool = False
    realtime: bool = False
    change_detection: bool = False


class SourceAdapter(ABC):
    slug: str

    @abstractmethod
    async def search(self, query: str) -> list[RawItem]: ...

    async def search_page(self, query: str, cursor: str | None = None) -> tuple[list[RawItem], str | None]:
        if cursor is not None:
            from ..core.errors import AppError
            raise AppError("PAGINATION_UNSUPPORTED", "此来源未验证游标分页。", 400)
        return await self.search(query), None

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities()

    async def healthcheck(self) -> bool:
        """Cheap reachability probe; default optimistic so tests never hit the network."""
        return True

    async def fetch(self, item: RawItem) -> RawItem:
        return item

    async def normalize(self, item: RawItem) -> RawItem:
        return item
