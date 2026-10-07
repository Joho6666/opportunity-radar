"""Incremental event clustering.

Groups documents discussing the same event/need into one EventCluster:
  - with embeddings: cosine similarity against the cluster centroid (>= 0.82);
  - without embeddings: token Jaccard fallback (zero cost).
Centroids are running averages so clusters drift with the conversation. Pure
in-process logic; persistence is delegated to the repository.
"""

import math
import re
from dataclasses import dataclass, field

from ..schemas.domain import RawItem
from ..schemas.intelligence import EventClusterRead

from .embedding_service import cosine_similarity
from .simhash import _features as _cjk_features


def _tokens(text: str) -> set[str]:
    """CJK-aware tokenizer: char bigrams for Chinese runs, words for ASCII.
    Whole-sentence tokens make Jaccard unstable across paraphrases."""
    return set(_cjk_features(text or ""))


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / len(left | right)


@dataclass
class ClusterState:
    """In-process cluster registry; one instance per run, optionally seeded with
    clusters persisted by PREVIOUS runs so the same event keeps growing one
    cluster instead of being re-created from scratch every run."""

    clusters: dict[str, EventClusterRead] = field(default_factory=dict)
    centroids: dict[str, list[float]] = field(default_factory=dict)
    token_sets: dict[str, set[str]] = field(default_factory=dict)
    member_counts: dict[str, int] = field(default_factory=dict)
    seeded_ids: set[str] = field(default_factory=set)

    def seed_from(self, clusters: list[EventClusterRead]) -> int:
        """Load persisted clusters (id + centroid + keyphrases) as merge targets."""
        for cluster in clusters:
            self.clusters[cluster.id] = cluster
            self.member_counts[cluster.id] = max(cluster.document_count, 1)
            if cluster.centroid:
                self.centroids[cluster.id] = list(cluster.centroid)
            self.token_sets[cluster.id] = set(cluster.keyphrases) | _tokens(f"{cluster.title} {cluster.summary}")
            self.seeded_ids.add(cluster.id)
        return len(clusters)

    def _new_cluster_id(self) -> str:
        index = len(self.clusters) + 1
        while f"cluster-{index}" in self.clusters:
            index += 1
        return f"cluster-{index}"

    def _make_cluster(self, item: RawItem, cluster_id: str) -> EventClusterRead:
        platforms = {item.source}
        authors = {item.author} if item.author else set()
        return EventClusterRead(
            id=cluster_id,
            radar_id=None,
            title=item.title[:200],
            summary=item.content[:280],
            keyphrases=sorted(list(_tokens(f"{item.title} {item.content}")))[:12],
            source_count=len(platforms),
            document_count=1,
            unique_authors=len(authors),
            unique_platforms=len(platforms),
            velocity_1h=0,
            velocity_24h=0,
            velocity_7d=0,
            velocity_30d=0,
            engagement_growth=0,
            breakout_score=0,
            representative_item_ids=[item.external_id],
            first_seen_at=None,
            last_seen_at=None,
        )


def assign_to_cluster(
    item: RawItem,
    vector: list[float] | None,
    state: ClusterState,
    cosine_threshold: float = 0.82,
    jaccard_threshold: float = 0.45,
) -> tuple[str, bool, float]:
    """Returns (cluster_id, created, similarity)."""
    item_tokens = _tokens(f"{item.title} {item.content}")
    best_id: str | None = None
    best_similarity = 0.0
    for cluster_id, tokens in state.token_sets.items():
        similarity = jaccard_similarity(item_tokens, tokens)
        if vector and state.centroids.get(cluster_id):
            similarity = max(similarity, cosine_similarity(vector, state.centroids[cluster_id]))
        if similarity > best_similarity:
            best_id, best_similarity = cluster_id, similarity
    threshold = max(cosine_threshold if vector else 0.0, jaccard_threshold)
    if best_id is not None and best_similarity >= threshold:
        cluster = state.clusters[best_id].model_copy()
        cluster.document_count += 1
        platforms = {item.source}
        cluster.source_count = max(cluster.source_count, len(platforms))
        if item.author:
            cluster.unique_authors += 0  # repository recomputes distinct authors
        cluster.last_seen_at = None
        cluster.representative_item_ids = (cluster.representative_item_ids + [item.external_id])[-5:]
        state.clusters[best_id] = cluster
        state.member_counts[best_id] = state.member_counts.get(best_id, 1) + 1
        if vector and state.centroids.get(best_id):
            old = state.centroids[best_id]
            n = state.member_counts[best_id]
            state.centroids[best_id] = [((old[i] * (n - 1)) + vector[i]) / n for i in range(len(old))]
        elif vector:
            state.centroids[best_id] = list(vector)
        state.token_sets[best_id] = state.token_sets[best_id] | item_tokens
        return best_id, False, best_similarity
    cluster_id = state._new_cluster_id()
    state.clusters[cluster_id] = state._make_cluster(item, cluster_id)
    state.member_counts[cluster_id] = 1
    if vector:
        state.centroids[cluster_id] = list(vector)
    state.token_sets[cluster_id] = item_tokens
    return cluster_id, True, 1.0


def finalize_clusters(state: ClusterState, platform_map: dict[str, set[str]] | None = None, author_map: dict[str, set[str]] | None = None) -> list[EventClusterRead]:
    """Recompute cross-cluster stats from repository-fed maps before persisting."""
    platform_map = platform_map or {}
    author_map = author_map or {}
    output: list[EventClusterRead] = []
    for cluster_id, cluster in state.clusters.items():
        platforms = platform_map.get(cluster_id, set())
        authors = author_map.get(cluster_id, set())
        updated = cluster.model_copy(update={
            "source_count": max(cluster.source_count, len(platforms) or 1),
            "unique_platforms": len(platforms) or 1,
            "unique_authors": max(cluster.unique_authors, len(authors)),
        })
        output.append(updated)
    return output


def cluster_velocity(document_count: int, first_seen_hours: float) -> float:
    """Docs per hour since the cluster first appeared (simple, testable)."""
    if first_seen_hours <= 0:
        return float(document_count)
    return round(document_count / first_seen_hours, 4)


def breakout_score(document_count: int, velocity_24h: float, cross_platform: int) -> int:
    """0-100 heuristic: volume + velocity + cross-platform spread."""
    volume_component = min(40, int(math.log2(max(document_count, 1)) * 10))
    velocity_component = min(40, int(velocity_24h * 8))
    spread_component = min(20, cross_platform * 5)
    return min(100, volume_component + velocity_component + spread_component)
