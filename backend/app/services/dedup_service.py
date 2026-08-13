import hashlib
import re
from ..schemas.domain import RawItem


def normalized_text(value: str) -> str:
    return re.sub(r"\W+", "", value.lower()).strip()


def content_hash(item: RawItem) -> str:
    return hashlib.sha256(normalized_text(f"{item.title}|{item.content}").encode()).hexdigest()


def url_hash(item: RawItem) -> str:
    return hashlib.sha256(item.url.split("?")[0].lower().encode()).hexdigest()


def deduplicate(items: list[RawItem]) -> tuple[list[RawItem], int]:
    seen: set[str] = set(); unique: list[RawItem] = []
    for item in items:
        signature = f"{url_hash(item)}:{content_hash(item)}"
        if signature not in seen:
            seen.add(signature); unique.append(item)
    return unique, len(items) - len(unique)


async def semantic_duplicate(_: RawItem, __: list[RawItem]) -> bool:
    """Reserved pgvector hook; V0.1 only performs deterministic hash deduplication."""
    return False
