import logging
import re
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ..collectors.registry import registry
from ..core.config import get_settings
from ..repositories.base import Repository
from ..schemas.domain import OpportunityRead, RadarCreate, RadarRunStats
from ..schemas.intelligence import StageStats
from .ai_service import analyze_raw_item, bind_llm_context, extract_signals_llm, get_provider, plan_queries, reset_llm_context
from .budget_service import check_and_consume, estimate_tokens
from .change_detection import breakout_from_snapshots
from .clustering_service import ClusterState, assign_to_cluster, breakout_score as cluster_breakout, cluster_velocity, finalize_clusters
from .dedup_service import SemanticDedupState, deduplicate, is_semantic_duplicate
from .embedding_service import embed_texts
from .information_edge import edge_from_pipeline
from .listener_service import config_for_radar, listener_boost, listener_matches
from .money_score import score_from_analysis
from .pain_point_service import fill_solutions, rebuild_for_radar
from .score_engine import calculate_score
from .signal_service import extract_signal
from .trend_service import upsert_topic

logger = logging.getLogger(__name__)


def next_run_at(frequency: str, now: datetime) -> datetime | None:
    if frequency == "hourly":
        return now + timedelta(hours=1)
    if frequency == "weekly":
        return now + timedelta(days=7)
    if frequency == "daily":
        return now + timedelta(days=1)
    return now + timedelta(days=1)


def activity_time(item):
    """Platform-side last activity: max(published_at, updated_at_source).

    A repo created years ago but pushed today is ACTIVE today — freshness
    filtering must use activity time, never created_at alone. Items with no
    timestamps at all pass (they were never datable).
    """
    stamps = [item.published_at, getattr(item, "updated_at_source", None)]
    stamps = [value for value in stamps if value is not None]
    if not stamps:
        return None
    stamps = [value if value.tzinfo else value.replace(tzinfo=UTC) for value in stamps]
    return max(stamps)


def _hours_since(value: datetime | None, now: datetime) -> float | None:
    if value is None:
        return None
    value = value if value.tzinfo else value.replace(tzinfo=UTC)
    return max(0.0, (now - value).total_seconds() / 3600)


def _looks_relevant(item, radar: RadarCreate) -> bool:
    """Stage 0.5 keyword gate: keep items that mention any radar keyword (or a
    significant goal token). Items matching nothing skip the expensive LLM call."""
    text = f"{item.title} {item.content}".lower()
    terms = [keyword.lower() for keyword in radar.keywords if keyword.strip()]
    if not terms:
        terms = [token for token in re.findall(r"[\w\u4e00-\u9fff]{2,}", radar.goal.lower())][:8]
    return any(term in text for term in terms)


class RadarRunService:
    def __init__(self, repository: Repository, collectors=registry) -> None:
        self.repository = repository
        self.collectors = collectors

    async def run(self, user_id: str, radar_id: str, run_id: str):
        radar = self.repository.get_radar(user_id, radar_id)
        profile = self.repository.get_profile(user_id)
        run = self.repository.get_run(user_id, run_id).model_copy(update={"status": "running"})
        self.repository.save_run(run)
        token = bind_llm_context(repository=self.repository, user_id=user_id, radar_id=radar.id, run_id=run.id)
        try:
            preference = self.repository.get_preference(user_id)
            queries = radar.queries or await plan_queries(radar, preference)
            radar = radar.model_copy(update={"queries": queries, "status": "running"})
            self.repository.save_radar(radar)
            raw = []
            collector_errors = []
            for query in queries:
                source = query.source if hasattr(query, "source") else query["source"]
                text = query.query if hasattr(query, "query") else query["query"]
                items, error = await self.collectors.search(source, text)
                raw.extend(items)
                if error:
                    collector_errors.append(error)
            stage = StageStats(collected=len(raw))
            unique, removed = deduplicate(raw)
            stage.after_dedup = len(unique)
            now = datetime.now(UTC)
            cutoff = now - timedelta(hours=radar.freshness_hours)
            timed = [item for item in unique if (stamp := activity_time(item)) is None or stamp >= cutoff]
            stage.after_freshness = len(timed)
            vectors = embed_texts([f"{item.title} {item.content}" for item in timed]) if timed else []
            if vectors is not None:
                stage.embedding_calls = 1
            fresh = [item for item in timed if not self.repository.has_raw(radar.id, item.url)]
            stage.after_known = len(fresh)
            known = len(timed) - len(fresh)
            created = []
            signals = []
            semantic_removed = 0
            gated_off_topic = 0
            gated_low_relevance = 0
            gated_by_listener = 0
            budget_skipped = 0
            dedup_state = SemanticDedupState()
            cluster_state = ClusterState()
            seeded = cluster_state.seed_from(self.repository.list_clusters(user_id, radar_id=radar.id, limit=100))
            topic_vector = self._radar_topic_vector(radar, vectors is not None)
            settings = get_settings()
            listener_cfg = config_for_radar(radar)
            llm_available = get_provider() is not None
            cluster_platforms: dict[str, set[str]] = defaultdict(set)
            cluster_authors: dict[str, set[str]] = defaultdict(set)
            cluster_raw_ids: dict[str, list[str]] = defaultdict(list)
            cluster_payment: dict[str, int] = defaultdict(int)
            cluster_rep_text: dict[str, str] = {}
            trend_keywords: dict[str, int] = defaultdict(int)
            profile_skills = [skill.name for skill in profile.skills]
            for index, item in enumerate(fresh):
                vector = vectors[index] if vectors else None
                if vector is not None and self.repository.find_similar_raw(radar.id, vector) is not None:
                    # cross-run L4: this content (or a paraphrase) is already in history
                    semantic_removed += 1
                    self.repository.mark_raw(radar.id, item.url, item, embedding=vector)
                    continue
                if is_semantic_duplicate(item, vector, dedup_state):
                    semantic_removed += 1
                    continue
                item_signal = extract_signal(item)
                positive_hits = 0
                if listener_cfg is not None:
                    # the listener IS the user's relevance definition; it replaces Stage 0.5
                    passes_listener, positive_hits = listener_matches(f"{item.title} {item.content}", listener_cfg)
                    if not passes_listener:
                        self.repository.mark_raw(radar.id, item.url, item, embedding=vector)
                        gated_by_listener += 1
                        continue
                elif item_signal is None and not _looks_relevant(item, radar):
                    self.repository.mark_raw(radar.id, item.url, item, embedding=vector)
                    gated_off_topic += 1
                    continue
                if vector is not None and topic_vector is not None and settings.enable_relevance_gate:
                    from .embedding_service import cosine_similarity

                    if cosine_similarity(vector, topic_vector) < settings.relevance_similarity_threshold:
                        self.repository.mark_raw(radar.id, item.url, item, embedding=vector)
                        gated_low_relevance += 1
                        continue
                if llm_available and not await check_and_consume(user_id, estimate_tokens(f"{item.title} {item.content}")):
                    # daily token budget exhausted → circuit breaker, keep the raw record
                    self.repository.mark_raw(radar.id, item.url, item, embedding=vector)
                    budget_skipped += 1
                    continue
                cluster_id, _created, _similarity = assign_to_cluster(item, vector, cluster_state, cosine_threshold=self._cluster_threshold())
                signal = item_signal
                analysis = await analyze_raw_item(item, profile_skills, has_commercial_signal=signal is not None)
                raw_item_id = self.repository.mark_raw(radar.id, item.url, item, embedding=vector)
                cluster_platforms[cluster_id].add(item.source)
                if item.author:
                    cluster_authors[cluster_id].add(item.author)
                if raw_item_id:
                    cluster_raw_ids[cluster_id].append(raw_item_id)
                if cluster_id not in cluster_rep_text:
                    cluster_rep_text[cluster_id] = f"{item.title} {item.content}"
                stage.analyzed += 1
                if signal is not None:
                    stored = self.repository.add_signal(signal, radar_id=radar.id, raw_item_id=raw_item_id or None, cluster_id=None)
                    signals.append(stored)
                    stage.signals_extracted += 1
                    if stored.payment_evidence:
                        cluster_payment[cluster_id] += 1
                    for keyword in stored.keywords[:3]:
                        trend_keywords[keyword] += 1
                if analysis.is_opportunity:
                    cluster = cluster_state.clusters[cluster_id]
                    platforms = cluster_platforms[cluster_id]
                    published = item.published_at or getattr(item, "updated_at_source", None)
                    edge = edge_from_pipeline(
                        published,
                        document_sources=len(platforms),
                        cluster_documents=cluster.document_count,
                        demand_growth=min(1.0, cluster.document_count / 10.0),
                        competition=analysis.competition,
                    )
                    money = score_from_analysis(
                        analysis,
                        edge,
                        cluster_docs=cluster.document_count,
                        cluster_velocity=cluster_velocity(cluster.document_count, max(_hours_since(activity_time(item), now) or 1.0, 1.0)),
                        payment_signals=cluster_payment.get(cluster_id, 1 if signal is not None and signal.payment_evidence else 0),
                        cluster_platforms=len(platforms),
                        budget=max(analysis.budget_max, analysis.budget_min),
                        estimated_hours=analysis.estimated_hours,
                        minimum_budget=radar.minimum_budget,
                        profile_skills=profile_skills,
                        hours_since_published=_hours_since(published, now),
                        personal_fit_boost=listener_boost(positive_hits),
                    )
                    score = calculate_score(analysis, radar.minimum_budget, preference=preference, source=item.source)
                    hourly = round(analysis.budget_min / analysis.estimated_hours), round(analysis.budget_max / analysis.estimated_hours)
                    opportunity = OpportunityRead(
                        id=str(uuid4()), radar_id=radar.id, type=analysis.type, title=analysis.title, summary=analysis.summary, source=item.source, source_url=item.url, published_at=item.published_at, location=analysis.location, work_mode=analysis.work_mode, budget_min=analysis.budget_min, budget_max=analysis.budget_max, estimated_hours=analysis.estimated_hours, estimated_hourly_rate=hourly, match_score=analysis.skill_match, opportunity_score=score.opportunity_score, conversion_probability=analysis.conversion_probability, risk_score=analysis.risk, recommendation=score.recommendation, status="new", skills=analysis.skills, reasons=analysis.reasons, warnings=analysis.warnings,
                        money_score=money.total, money_breakdown=money.model_dump(), information_edge=edge.total, information_edge_breakdown=edge.model_dump(), verification_status="unverified",
                    )
                    self.repository.add_opportunity(opportunity, user_id=user_id)
                    created.append(opportunity)
            cluster_list = finalize_clusters(cluster_state, platform_map=cluster_platforms, author_map=cluster_authors)
            for cluster in cluster_list:
                velocity = cluster_velocity(cluster.document_count, 1.0)
                saved = self.repository.save_cluster(
                    cluster.model_copy(update={"velocity_24h": velocity, "breakout_score": cluster_breakout(cluster.document_count, velocity, cluster.source_count), "centroid": cluster_state.centroids.get(cluster.id)}),
                    radar_id=radar.id,
                    member_raw_item_ids=cluster_raw_ids.get(cluster.id, []),
                )
                cluster.id = saved.id
            stage.clusters_touched = len(cluster_list)
            stage.opportunities_found = len(created)
            stage.semantic_removed = semantic_removed
            stage.gated_off_topic = gated_off_topic
            stage.gated_low_relevance = gated_low_relevance
            stage.gated_by_listener = gated_by_listener
            stage.llm_budget_skipped = budget_skipped
            cluster_themes = {cluster.id: cluster.title for cluster in cluster_list}
            for cluster in cluster_list:
                # Stage 3: cheap-model multi-signal extraction on cluster representatives
                if cluster.document_count < 2 or not llm_available:
                    continue
                text = cluster_rep_text.get(cluster.id)
                if not text or not await check_and_consume(user_id, estimate_tokens(text)):
                    continue
                extracted = await extract_signals_llm(text)
                if not extracted:
                    continue
                for extracted_signal in extracted:
                    stored = self.repository.add_signal(
                        extracted_signal,
                        radar_id=radar.id,
                        raw_item_id=(cluster_raw_ids.get(cluster.id) or [None])[0],
                        cluster_id=cluster.id,
                    )
                    signals.append(stored)
                    stage.llm_signals_extracted += 1
            try:
                await rebuild_for_radar(self.repository, user_id, radar.id, signals, cluster_themes)
                if llm_available:
                    await fill_solutions(self.repository, user_id, radar.id)
            except Exception:
                logger.exception("pain point rebuild failed", extra={"radar_id": radar.id})
            for keyword, count in trend_keywords.items():
                topic = upsert_topic(None, radar.id, keyword, count, 0)
                self.repository.upsert_trend_topic(topic)
            self._detect_breakouts(radar.id, now)
            stats = RadarRunStats(queries=len(queries), items_found=len(raw), duplicates_removed=removed + known + semantic_removed + gated_off_topic + gated_low_relevance, analyzed=stage.analyzed, opportunities_found=len(created), matched=len([x for x in created if x.match_score >= 75]), recommended=len([x for x in created if x.recommendation == "强烈推荐"]))
            finished_at = datetime.now(UTC)
            error_code = "COLLECTORS_FAILED" if collector_errors and not raw else None
            error_message = "; ".join(error["message"] for error in collector_errors)[:500] if collector_errors else None
            run = run.model_copy(update={"status": "completed", "stats": stats, "error_code": error_code, "error_message": error_message, "collector_errors": collector_errors, "stage_stats": stage.model_dump()})
            self.repository.save_run(run)
            self.repository.save_radar(radar.model_copy(update={"status": "active", "last_run_at": finished_at, "next_run_at": next_run_at(radar.frequency, finished_at), "stats": stats}))
            return run
        except Exception as exc:
            logger.exception("radar run failed", extra={"radar_id": radar_id, "run_id": run_id, "error_code": "RADAR_RUN_FAILED"})
            run = run.model_copy(update={"status": "failed", "error_code": "RADAR_RUN_FAILED", "error_message": f"{type(exc).__name__}: {exc}"[:500]})
            self.repository.save_run(run)
            self.repository.save_radar(radar.model_copy(update={"status": "error"}))
            return run
        finally:
            reset_llm_context(token)

    def _cluster_threshold(self) -> float:
        from ..core.config import get_settings

        return get_settings().cluster_similarity_threshold

    def _radar_topic_vector(self, radar: RadarCreate, embeddings_available: bool) -> list[float] | None:
        """Stage 1 relevance reference vector: radar goal + keywords embedded once per run."""
        if not embeddings_available or not get_settings().enable_relevance_gate:
            return None
        from .embedding_service import embed_texts

        text = f"{radar.goal} {' '.join(radar.keywords)}".strip()
        vectors = embed_texts([text]) if text else None
        return vectors[0] if vectors else None

    def _detect_breakouts(self, radar_id: str, now: datetime) -> int:
        """Compare trailing topic snapshots against history; persist breakouts."""
        detected = 0
        try:
            topics = self.repository.list_trend_topics(radar_id=radar_id)
            for topic in topics:
                snapshots = self.repository.list_trend_snapshots(topic.id)
                result = breakout_from_snapshots(snapshots)
                if result is not None and result.is_breakout:
                    self.repository.save_change_event(result.to_event(topic.topic, "mention_count", "topic", radar_id), radar_id=radar_id)
                    detected += 1
        except Exception:
            logger.exception("breakout detection failed", extra={"radar_id": radar_id})
        return detected
