from collections import defaultdict
from datetime import date, datetime, timedelta
from uuid import uuid4
from ..core.errors import AppError
from ..schemas.domain import DailyBriefRead, OpportunityAction, OpportunityRead, PreferenceState, ProfileRead, ProfileUpsert, RadarCreate, RadarRead, RadarRunRead, RadarRunStats, RawItem
from ..schemas.intelligence import ChangeEventRead, EventClusterRead, PainPointRead, SignalRead, SourceHealthRead, TrendSnapshotRead, TrendTopicRead
from ..services.dedup_service import hash_url
from ..services.daily_intelligence import assemble
from ..services.income import potential_income_range


class MemoryRepository:
    """In-memory store mirroring the Supabase schema constraints.

    Raw items are tracked per radar by url_hash; re-seen URLs bump last_seen_at /
    seen_count (upsert semantics matching the Postgres ON CONFLICT DO UPDATE),
    turning repeat appearances into trend evidence.
    """

    def __init__(self) -> None:
        self.profiles: dict[str, ProfileRead] = {}
        self.radars: dict[str, RadarRead] = {}
        self.opportunities: dict[str, OpportunityRead] = {}
        self.runs: dict[str, RadarRunRead] = {}
        self.actions: dict[str, OpportunityAction] = {}
        self.action_log: list[tuple[str, str, OpportunityAction]] = []
        self.llm_calls: list[dict] = []
        self.events: list[dict] = []
        self.preferences: dict[str, PreferenceState] = {}
        self._raw_urls: dict[str, set[str]] = defaultdict(set)
        self._raw_items: dict[str, dict] = {}  # url_hash -> raw row mirror
        self.signals: list[SignalRead] = []
        self.clusters: list[EventClusterRead] = []
        self.cluster_members: list[tuple[str, str]] = []
        self.trend_topics: dict[tuple[str, str], TrendTopicRead] = {}
        self.trend_snapshots: list[TrendSnapshotRead] = []
        self.change_events: list[ChangeEventRead] = []
        self.source_health: dict[str, SourceHealthRead] = {}
        self.briefs: dict[tuple[str, str], DailyBriefRead] = {}
        self.pain_points: dict[tuple[str, str], PainPointRead] = {}

    def get_profile(self, user_id: str) -> ProfileRead:
        if user_id not in self.profiles:
            self.profiles[user_id] = ProfileRead(id=str(uuid4()), user_id=user_id, display_name="新用户", identity="", location="", monthly_income_goal=0, minimum_project_budget=0, available_hours_per_day=0, skills=[], goals=[])
        return self.profiles[user_id]

    def save_profile(self, user_id: str, value: ProfileUpsert) -> ProfileRead:
        profile = ProfileRead(id=self.get_profile(user_id).id, user_id=user_id, **value.model_dump())
        self.profiles[user_id] = profile
        return profile

    def list_radars(self, user_id: str) -> list[RadarRead]:
        return [item for item in self.radars.values() if item.user_id == user_id]

    def get_radar(self, user_id: str, radar_id: str) -> RadarRead:
        item = self.radars.get(radar_id)
        if not item or item.user_id != user_id:
            raise AppError("RADAR_NOT_FOUND", "未找到该机会雷达。", 404)
        return item

    def create_radar(self, user_id: str, value: RadarCreate) -> RadarRead:
        item = RadarRead(id=str(uuid4()), user_id=user_id, status="active", **value.model_dump())
        self.radars[item.id] = item
        return item

    def save_radar(self, item: RadarRead) -> RadarRead:
        self.radars[item.id] = item
        return item

    def delete_radar(self, user_id: str, radar_id: str) -> None:
        self.get_radar(user_id, radar_id)
        for run_id in [key for key, run in self.runs.items() if run.radar_id == radar_id]:
            del self.runs[run_id]
        for opportunity_id in [key for key, item in self.opportunities.items() if item.radar_id == radar_id]:
            del self.opportunities[opportunity_id]
            self.actions.pop(opportunity_id, None)
        self._raw_urls.pop(radar_id, None)
        self.signals = [signal for signal in self.signals if signal.radar_id != radar_id]
        self.clusters = [cluster for cluster in self.clusters if cluster.radar_id != radar_id]
        self.trend_topics = {key: topic for key, topic in self.trend_topics.items() if key[0] != radar_id}
        del self.radars[radar_id]

    def has_raw(self, radar_id: str, url: str) -> bool:
        return hash_url(url) in self._raw_urls[radar_id]

    def mark_raw(self, radar_id: str, url: str, item: RawItem | None = None, embedding: list[float] | None = None) -> str:
        digest = hash_url(item.url if item else url)
        seen_urls = self._raw_urls[radar_id]
        now = datetime.now()
        if digest in seen_urls and digest in self._raw_items:
            row = self._raw_items[digest]
            content_changed = bool(item) and row["content_hash"] != (str(hash(f"{item.title}|{item.content}")) if item else row["content_hash"])
            row["last_seen_at"] = now
            row["seen_count"] = row["seen_count"] + 1
            if content_changed:
                row["content_changed_at"] = now
                row["content_hash"] = str(hash(f"{item.title}|{item.content}"))
            if item is not None:
                row["engagement"] = item.engagement or row["engagement"]
            if embedding:
                row["embedding"] = embedding
            return row["id"]
        raw_id = str(uuid4())
        seen_urls.add(digest)
        self._raw_items[digest] = {
            "id": raw_id,
            "radar_id": radar_id,
            "url_hash": digest,
            "content_hash": str(hash(f"{item.title}|{item.content}")) if item else digest,
            "first_seen_at": now,
            "last_seen_at": now,
            "seen_count": 1,
            "engagement": item.engagement if item else {},
            "embedding": embedding,
        }
        return raw_id

    def find_similar_raw(self, radar_id: str, vector: list[float], threshold: float = 0.92) -> str | None:
        from ..services.embedding_service import cosine_similarity

        best_id: str | None = None
        best_similarity = 0.0
        for row in self._raw_items.values():
            stored = row.get("embedding")
            if not stored or row["radar_id"] != radar_id:
                continue
            similarity = cosine_similarity(vector, stored)
            if similarity >= threshold and similarity > best_similarity:
                best_id, best_similarity = row["id"], similarity
        return best_id

    def raw_row(self, url: str) -> dict | None:
        return self._raw_items.get(hash_url(url))

    def create_run(self, radar_id: str) -> RadarRunRead:
        run = RadarRunRead(id=str(uuid4()), radar_id=radar_id, status="queued", stats=RadarRunStats())
        self.runs[run.id] = run
        return run

    def save_run(self, run: RadarRunRead) -> RadarRunRead:
        self.runs[run.id] = run
        return run

    def get_run(self, user_id: str, run_id: str) -> RadarRunRead:
        run = self.runs.get(run_id)
        if not run:
            raise AppError("RUN_NOT_FOUND", "未找到该运行记录。", 404)
        self.get_radar(user_id, run.radar_id)
        return run

    def runs_of_user(self, user_id: str) -> list[RadarRunRead]:
        ids = {radar.id for radar in self.list_radars(user_id)}
        return [run for run in self.runs.values() if run.radar_id in ids]

    def add_opportunity(self, item: OpportunityRead, user_id: str | None = None) -> OpportunityRead:
        self.opportunities[item.id] = item
        return item

    def list_opportunities(self, user_id: str) -> list[OpportunityRead]:
        ids = {radar.id for radar in self.list_radars(user_id)}
        return [item for item in self.opportunities.values() if item.radar_id in ids]

    def get_opportunity(self, user_id: str, opportunity_id: str) -> OpportunityRead:
        item = self.opportunities.get(opportunity_id)
        if not item or item.radar_id not in {radar.id for radar in self.list_radars(user_id)}:
            raise AppError("OPPORTUNITY_NOT_FOUND", "未找到该机会。", 404)
        return item

    def save_opportunity(self, item: OpportunityRead) -> OpportunityRead:
        self.opportunities[item.id] = item
        return item

    def record_action(self, opportunity_id: str, payload: OpportunityAction, action: str | None = None) -> OpportunityAction:
        self.actions[opportunity_id] = payload
        self.action_log.append((opportunity_id, action or "updated", payload))
        return payload

    def scanned_count(self, user_id: str) -> int:
        return sum(run.stats.items_found for run in self.runs_of_user(user_id))

    def won_revenue(self, user_id: str) -> int:
        won = [item for item in self.list_opportunities(user_id) if item.status == "won"]
        total = 0
        for item in won:
            recorded = self.actions.get(item.id)
            if recorded and recorded.actual_revenue is not None:
                total += recorded.actual_revenue
            else:
                total += item.budget_max
        return total

    def daily_brief(self, user_id: str) -> DailyBriefRead:
        items = self.list_opportunities(user_id)
        recommended = [item for item in items if item.recommendation == "强烈推荐"]
        scanned = self.scanned_count(user_id) or len(items)
        low, high = potential_income_range(items)
        brief = assemble(items, signals=self.signals, clusters=self.clusters, changes=self.change_events)
        brief = brief.model_copy(update={
            "date": date.today(),
            "scanned_count": scanned,
            "opportunities_count": len(items),
            "recommended_count": len(recommended),
            "potential_income_min": low,
            "potential_income_max": high,
        })
        self.briefs[(user_id, brief.date.isoformat())] = brief
        return brief

    def get_brief(self, user_id: str, brief_date: date) -> DailyBriefRead | None:
        return self.briefs.get((user_id, brief_date.isoformat()))

    def list_due_radars(self, now: datetime) -> list[tuple[str, str]]:
        running = {run.radar_id for run in self.runs.values() if run.status in {"queued", "running"}}
        due: list[tuple[str, str]] = []
        for radar in self.radars.values():
            if radar.status != "active" or radar.id in running:
                continue
            if radar.next_run_at is None or radar.next_run_at <= now:
                due.append((radar.user_id, radar.id))
        return due

    def record_llm_call(self, user_id: str | None, radar_id: str | None, run_id: str | None, provider: str | None, model: str, latency_ms: int, fallbacked: bool, schema_name: str, stage: str | None = None, input_count: int | None = None, output_count: int | None = None, prompt_tokens: int | None = None, completion_tokens: int | None = None, cost_usd: float | None = None) -> None:
        self.llm_calls.append({"user_id": user_id, "radar_id": radar_id, "run_id": run_id, "provider": provider, "model": model, "latency_ms": latency_ms, "fallbacked": fallbacked, "schema_name": schema_name, "stage": stage, "input_count": input_count, "output_count": output_count, "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens, "cost_usd": cost_usd, "created_at": datetime.now()})

    def get_preference(self, user_id: str) -> PreferenceState:
        return self.preferences.get(user_id, PreferenceState()).model_copy(deep=True)

    def save_preference(self, user_id: str, state: PreferenceState) -> PreferenceState:
        self.preferences[user_id] = state.model_copy(deep=True)
        return self.preferences[user_id]

    def record_event(self, user_id: str, opportunity_id: str | None, event: str, metadata: dict | None = None) -> None:
        self.events.append({"user_id": user_id, "opportunity_id": opportunity_id, "event": event, "metadata": metadata or {}})

    # ---- Money Intelligence extensions ----

    def add_signal(self, signal: SignalRead, radar_id: str | None = None, raw_item_id: str | None = None, cluster_id: str | None = None) -> SignalRead:
        stored = signal.model_copy(update={"id": signal.id or str(uuid4()), "radar_id": radar_id, "raw_item_id": raw_item_id, "cluster_id": cluster_id})
        self.signals.append(stored)
        return stored

    def list_signals(self, user_id: str, radar_id: str | None = None, limit: int = 100) -> list[SignalRead]:
        radar_ids = {radar.id for radar in self.list_radars(user_id)}
        if radar_id:
            radar_ids &= {radar_id}
        selected = [signal for signal in self.signals if signal.radar_id in radar_ids]
        return selected[-limit:]

    def save_cluster(self, cluster: EventClusterRead, radar_id: str | None = None, member_raw_item_ids: list[str] | None = None) -> EventClusterRead:
        stored = cluster.model_copy(update={"id": cluster.id or str(uuid4()), "radar_id": radar_id})
        self.clusters = [item for item in self.clusters if item.id != stored.id]
        self.clusters.append(stored)
        for raw_item_id in member_raw_item_ids or []:
            pair = (stored.id, raw_item_id)
            if pair not in self.cluster_members:
                self.cluster_members.append(pair)
        return stored

    def list_clusters(self, user_id: str, radar_id: str | None = None, limit: int = 50) -> list[EventClusterRead]:
        radar_ids = {radar.id for radar in self.list_radars(user_id)}
        if radar_id:
            radar_ids &= {radar_id}
        selected = [cluster for cluster in self.clusters if cluster.radar_id in radar_ids and cluster.merged_into is None]
        return selected[-limit:]

    def upsert_trend_topic(self, topic: TrendTopicRead) -> TrendTopicRead:
        key = (topic.radar_id or "", topic.topic)
        self.trend_topics[key] = topic
        return topic

    def save_trend_snapshot(self, snapshot: TrendSnapshotRead) -> TrendSnapshotRead:
        stored = snapshot.model_copy(update={"id": str(uuid4())})
        self.trend_snapshots.append(stored)
        return stored

    def list_trend_topics(self, user_id: str | None = None, radar_id: str | None = None, limit: int = 100) -> list[TrendTopicRead]:
        topics = list(self.trend_topics.values())
        if radar_id:
            topics = [topic for topic in topics if topic.radar_id == radar_id]
        elif user_id:
            radar_ids = {radar.id for radar in self.list_radars(user_id)}
            topics = [topic for topic in topics if topic.radar_id in radar_ids]
        return topics[-limit:]

    def list_trend_snapshots(self, topic_id: str, limit: int = 720) -> list[TrendSnapshotRead]:
        # newest-first to match the Postgres ORDER BY captured_at DESC contract
        return [snapshot for snapshot in reversed(self.trend_snapshots) if snapshot.topic_id == topic_id][:limit]

    def save_change_event(self, event: ChangeEventRead, radar_id: str | None = None) -> ChangeEventRead:
        key = event.dedup_key or f"{radar_id or 'none'}:{event.subject_kind}:{event.subject_key}:{event.metric_key}:{(event.detected_at or datetime.now()).strftime('%Y-%m-%d')}"
        if any(existing.id != event.id and (existing.dedup_key or f"{existing.radar_id or 'none'}:{existing.subject_kind}:{existing.subject_key}:{existing.metric_key}:{(existing.detected_at or datetime.now()).strftime('%Y-%m-%d')}") == key for existing in self.change_events):
            return event  # idempotent: one breakout row per subject/metric/day
        stored = event.model_copy(update={"id": str(uuid4()), "radar_id": radar_id, "dedup_key": key})
        self.change_events.append(stored)
        return stored

    def list_change_events(self, user_id: str | None = None, radar_id: str | None = None, limit: int = 100) -> list[ChangeEventRead]:
        if radar_id:
            selected = [event for event in self.change_events if event.radar_id == radar_id]
        elif user_id:
            radar_ids = {radar.id for radar in self.list_radars(user_id)}
            selected = [event for event in self.change_events if event.radar_id in radar_ids]
        else:
            selected = list(self.change_events)
        return selected[-limit:]

    def record_source_health(self, slug: str, ok: bool, items: int, latency_ms: int, error_code: str | None = None, error_message: str | None = None) -> None:
        from ..services.source_health_service import record

        self.source_health[slug] = record(self.source_health.get(slug), slug, ok, items, latency_ms, error_code, error_message)

    def get_source_health(self, slug: str) -> SourceHealthRead | None:
        return self.source_health.get(slug)

    def list_source_health(self) -> list[SourceHealthRead]:
        return list(self.source_health.values())

    # ---- P1 guardrails / Phase 2 ----

    def cleanup_raw_items(self, days: int) -> int:
        cutoff = datetime.now() - timedelta(days=days)
        stale = [digest for digest, row in self._raw_items.items() if row["last_seen_at"] < cutoff]
        for digest in stale:
            row = self._raw_items.pop(digest)
            self._raw_urls.get(row["radar_id"], set()).discard(digest)
        return len(stale)

    def cleanup_llm_calls(self, days: int) -> int:
        cutoff = datetime.now() - timedelta(days=days)
        before = len(self.llm_calls)
        self.llm_calls = [call for call in self.llm_calls if call.get("created_at", datetime.now()) >= cutoff]
        return before - len(self.llm_calls)

    def merge_cluster(self, source_id: str, target_id: str) -> None:
        source = next((cluster for cluster in self.clusters if cluster.id == source_id), None)
        target = next((cluster for cluster in self.clusters if cluster.id == target_id), None)
        if source is None or target is None or source_id == target_id:
            return
        self.cluster_members = [
            (target_id if cluster_id == source_id else cluster_id, raw_item_id)
            for cluster_id, raw_item_id in self.cluster_members
        ]
        updated = target.model_copy(update={
            "document_count": target.document_count + source.document_count,
            "source_count": max(target.source_count, source.source_count),
            "unique_platforms": max(target.unique_platforms, source.unique_platforms),
        })
        self.clusters = [updated if cluster.id == target_id else (cluster.model_copy(update={"merged_into": target_id}) if cluster.id == source_id else cluster) for cluster in self.clusters]

    def upsert_pain_point(self, pain: PainPointRead) -> PainPointRead:
        key = (pain.radar_id or "", pain.theme)
        existing = self.pain_points.get(key)
        if existing is not None:
            stored = pain.model_copy(update={
                "id": existing.id,
                "first_seen_at": existing.first_seen_at,
                "growth_rate": round((pain.mention_count - existing.mention_count) / max(existing.mention_count, 1), 4),
            })
        else:
            stored = pain.model_copy(update={"id": str(uuid4())})
        self.pain_points[key] = stored
        return stored

    def list_pain_points(self, user_id: str, radar_id: str | None = None, limit: int = 50) -> list[PainPointRead]:
        radar_ids = {radar.id for radar in self.list_radars(user_id)}
        if radar_id:
            radar_ids &= {radar_id}
        selected = [pain for pain in self.pain_points.values() if pain.radar_id in radar_ids]
        return sorted(selected, key=lambda item: item.severity, reverse=True)[:limit]

    def list_radar_pairs(self) -> list[tuple[str, str]]:
        return [(radar.user_id, radar.id) for radar in self.radars.values()]


repository = MemoryRepository()
