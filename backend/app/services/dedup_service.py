"""Four-level dedup pipeline.

Level 1  url_hash        exact URL (query string stripped)
Level 2  content_hash    normalized title+content sha256
Level 3  simhash         near-duplicate fingerprints (Hamming distance)
Level 4  embedding       cosine similarity against previously seen vectors

Levels 1-3 are deterministic and free. Level 4 activates only when embeddings
are available; otherwise it is a no-op. The public entrypoints keep the old
signatures so existing callers and tests keep working.
"""

import hashlib
import re
from dataclasses import dataclass, field

from ..schemas.domain import RawItem
from .embedding_service import cosine_similarity
from .simhash import hamming_distance, simhash64


def normalized_text(value: str) -> str:
    return re.sub(r"\W+", "", value.lower()).strip()


def hash_url(url: str) -> str:
    return hashlib.sha256(url.split("?")[0].lower().encode()).hexdigest()


def content_hash(item: RawItem) -> str:
    return hashlib.sha256(normalized_text(f"{item.title}|{item.content}").encode()).hexdigest()


def url_hash(item: RawItem) -> str:
    return hash_url(item.url)


def simhash_of(item: RawItem) -> int:
    return simhash64(f"{item.title} {item.content}")


def deduplicate(items: list[RawItem]) -> tuple[list[RawItem], int]:
    """Within-run dedup across levels 1-3 (url, content, simhash)."""
    seen: set[str] = set()
    fingerprints: list[int] = []
    unique: list[RawItem] = []
    removed = 0
    for item in items:
        url_digest = url_hash(item)
        body_digest = content_hash(item)
        if f"u:{url_digest}" in seen or f"c:{body_digest}" in seen:
            removed += 1
            continue
        fingerprint = simhash_of(item)
        if fingerprint and any(hamming_distance(fingerprint, other) <= 12 for other in fingerprints):
            removed += 1
            continue
        seen.add(f"u:{url_digest}")
        seen.add(f"c:{body_digest}")
        fingerprints.append(fingerprint)
        unique.append(item)
    return unique, removed


@dataclass
class SemanticDedupState:
    """Carrier for embedding-based dedup context within a single run."""

    vectors: list[list[float]] = field(default_factory=list)
    fingerprints: list[int] = field(default_factory=list)


def semantic_duplicate(item: RawItem, known: list[RawItem], threshold: float = 0.92) -> bool:
    """Legacy two-argument hook kept for compatibility: simhash-only check."""
    fingerprint = simhash_of(item)
    if not fingerprint:
        return False
    return any(hamming_distance(fingerprint, simhash_of(other)) <= 12 for other in known)


def is_semantic_duplicate(item: RawItem, vector: list[float] | None, state: SemanticDedupState, cosine_threshold: float = 0.92) -> bool:
    """Level 4: compare against vectors of already-accepted items."""
    if vector:
        for other in state.vectors:
            if cosine_similarity(vector, other) >= cosine_threshold:
                return True
    fingerprint = simhash_of(item)
    if fingerprint and any(hamming_distance(fingerprint, other) <= 12 for other in state.fingerprints):
        return True
    if vector:
        state.vectors.append(vector)
    if fingerprint:
        state.fingerprints.append(fingerprint)
    return False
