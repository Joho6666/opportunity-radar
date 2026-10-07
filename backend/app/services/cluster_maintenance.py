"""Cluster maintenance: nightly merge of near-identical clusters.

Clusters whose centroids are cosine > 0.90 are merged (larger absorbs smaller):
members reattach, document counts add up, the source row keeps merged_into for
traceability. Split/drift handling is deliberately deferred (see
backend/README_INTELLIGENCE.md); the centroid drift data is already being
recorded for it.
"""

import logging
from itertools import combinations

from ..repositories.base import Repository
from .embedding_service import cosine_similarity

logger = logging.getLogger(__name__)

MERGE_SIMILARITY = 0.90
MAX_CLUSTERS_PER_RADAR = 200


def merge_similar_clusters(repository: Repository, user_id: str, radar_id: str, threshold: float = MERGE_SIMILARITY) -> int:
    clusters = [cluster for cluster in repository.list_clusters(user_id, radar_id=radar_id, limit=MAX_CLUSTERS_PER_RADAR) if cluster.centroid]
    if len(clusters) < 2:
        return 0
    clusters.sort(key=lambda cluster: cluster.document_count, reverse=True)
    merged = 0
    retired: set[str] = set()
    for big, small in combinations(clusters, 2):
        if big.id in retired or small.id in retired:
            continue
        if cosine_similarity(big.centroid, small.centroid) >= threshold:
            repository.merge_cluster(small.id, big.id)
            retired.add(small.id)
            merged += 1
    if merged:
        logger.info("cluster maintenance merged", extra={"radar_id": radar_id, "merged": merged})
    return merged


async def run_maintenance(repository: Repository, radars: list[tuple[str, str]]) -> int:
    total = 0
    for user_id, radar_id in radars:
        try:
            total += merge_similar_clusters(repository, user_id, radar_id)
        except Exception:
            logger.exception("cluster maintenance failed", extra={"radar_id": radar_id})
    return total
