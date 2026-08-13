from abc import ABC, abstractmethod
from ..schemas.domain import RawItem


class SourceAdapter(ABC):
    slug: str

    @abstractmethod
    async def search(self, query: str) -> list[RawItem]: ...

    async def fetch(self, item: RawItem) -> RawItem:
        return item

    async def normalize(self, item: RawItem) -> RawItem:
        return item
