from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from ..core.config import get_settings
from ..core.errors import AppError
from ..schemas.domain import DailyBriefRead, OpportunityAction, OpportunityRead, PreferenceState, ProfileRead, ProfileUpsert, QueryPlanItem, RadarCreate, RadarRead, RadarRunRead, RadarRunStats, RawItem, SkillInput
from ..schemas.intelligence import ChangeEventRead, EventClusterRead, SignalRead, SourceHealthRead, TrendSnapshotRead, TrendTopicRead


def vector_literal(vector: list[float]) -> str:
    """Serialize a float list into a pgvector literal '[0.1,0.2,...]' (no spaces)."""
    return "[" + ",".join(f"{float(value):.7g}" for value in vector) + "]"
from ..services.dedup_service import content_hash, hash_url
from ..services.income import potential_income_range
from .preference_store import load_preference, store_event, store_preference


def as_uuid(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError):
        return str(uuid5(NAMESPACE_URL, str(value)))


class PostgresRepository:
    """SQLAlchemy-backed store. All SQL uses bound parameters; no string interpolation of user input."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def _conn(self):
        return self.engine.begin()

    def _ensure_user(self, conn: Connection, user_id: str) -> str:
        uid = as_uuid(user_id)
        exists = conn.execute(text("SELECT 1 FROM auth.users WHERE id = CAST(:id AS uuid)"), {"id": uid}).first()
        if exists:
            return uid
        conn.execute(
            text(
                "INSERT INTO auth.users (id, instance_id, aud, role, email, encrypted_password, email_confirmed_at, created_at, updated_at, confirmation_token, recovery_token, email_change_token_new, email_change, raw_app_meta_data, raw_user_meta_data) "
                "VALUES (CAST(:id AS uuid), '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', :email, '', NOW(), NOW(), NOW(), '', '', '', '', CAST(:app AS jsonb), CAST(:user_meta AS jsonb)) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": uid, "email": f"{uid}@local.test", "app": "{}", "user_meta": "{}"},
        )
        return uid

    def get_profile(self, user_id: str) -> ProfileRead:
        uid = as_uuid(user_id)
        with self._conn() as conn:
            self._ensure_user(conn, user_id)
            row = conn.execute(text("SELECT id, user_id, display_name, identity, location, monthly_income_goal, minimum_project_budget, available_hours_per_day FROM profiles WHERE user_id = CAST(:uid AS uuid)"), {"uid": uid}).mappings().first()
            if row is None:
                profile_id = str(uuid4())
                conn.execute(
                    text("INSERT INTO profiles (id, user_id, display_name, identity, location, monthly_income_goal, minimum_project_budget, available_hours_per_day) VALUES (CAST(:id AS uuid), CAST(:uid AS uuid), :name, '', '', 0, 0, 0)"),
                    {"id": profile_id, "uid": uid, "name": "新用户"},
                )
                return ProfileRead(id=profile_id, user_id=str(uid), display_name="新用户", identity="", location="", monthly_income_goal=0, minimum_project_budget=0, available_hours_per_day=0, skills=[], goals=[])
            return self._profile_from_row(conn, row)

    def save_profile(self, user_id: str, value: ProfileUpsert) -> ProfileRead:
        current = self.get_profile(user_id)
        uid = as_uuid(user_id)
        with self._conn() as conn:
            conn.execute(
                text("UPDATE profiles SET display_name=:display_name, identity=:identity, location=:location, monthly_income_goal=:monthly_income_goal, minimum_project_budget=:minimum_project_budget, available_hours_per_day=:available_hours_per_day, updated_at=NOW() WHERE user_id=CAST(:uid AS uuid)"),
                {"display_name": value.display_name, "identity": value.identity, "location": value.location, "monthly_income_goal": value.monthly_income_goal, "minimum_project_budget": value.minimum_project_budget, "available_hours_per_day": value.available_hours_per_day, "uid": uid},
            )
            conn.execute(text("DELETE FROM profile_skills WHERE profile_id=CAST(:pid AS uuid)"), {"pid": current.id})
            conn.execute(text("DELETE FROM profile_goals WHERE profile_id=CAST(:pid AS uuid)"), {"pid": current.id})
            for skill in value.skills:
                conn.execute(
                    text("INSERT INTO profile_skills (profile_id, skill_name, skill_level) VALUES (CAST(:pid AS uuid), :name, :level)"),
                    {"pid": current.id, "name": skill.name, "level": skill.level},
                )
            for goal in value.goals:
                conn.execute(text("INSERT INTO profile_goals (profile_id, goal) VALUES (CAST(:pid AS uuid), :goal)"), {"pid": current.id, "goal": goal})
        return ProfileRead(id=current.id, user_id=str(uid), **value.model_dump())

    def _profile_from_row(self, conn: Connection, row) -> ProfileRead:
        pid = str(row["id"])
        skills = [SkillInput(name=item["skill_name"], level=item["skill_level"]) for item in conn.execute(text("SELECT skill_name, skill_level FROM profile_skills WHERE profile_id=CAST(:pid AS uuid)"), {"pid": pid}).mappings()]
        goals = [item["goal"] for item in conn.execute(text("SELECT goal FROM profile_goals WHERE profile_id=CAST(:pid AS uuid)"), {"pid": pid}).mappings()]
        return ProfileRead(id=pid, user_id=str(row["user_id"]), display_name=row["display_name"], identity=row["identity"] or "", location=row["location"] or "", monthly_income_goal=row["monthly_income_goal"] or 0, minimum_project_budget=row["minimum_project_budget"] or 0, available_hours_per_day=float(row["available_hours_per_day"] or 0), skills=skills, goals=goals)

    def list_radars(self, user_id: str) -> list[RadarRead]:
        uid = as_uuid(user_id)
        with self._conn() as conn:
            rows = conn.execute(text("SELECT * FROM radars WHERE user_id=CAST(:uid AS uuid) ORDER BY created_at DESC"), {"uid": uid}).mappings().all()
            return [self._radar_from_row(conn, row) for row in rows]

    def get_radar(self, user_id: str, radar_id: str) -> RadarRead:
        uid = as_uuid(user_id)
        rid = as_uuid(radar_id)
        with self._conn() as conn:
            row = conn.execute(text("SELECT * FROM radars WHERE id=CAST(:rid AS uuid) AND user_id=CAST(:uid AS uuid)"), {"rid": rid, "uid": uid}).mappings().first()
            if row is None:
                raise AppError("RADAR_NOT_FOUND", "未找到该机会雷达。", 404)
            return self._radar_from_row(conn, row)

    def create_radar(self, user_id: str, value: RadarCreate) -> RadarRead:
        uid = as_uuid(user_id)
        radar_id = str(uuid4())
        item = RadarRead(id=radar_id, user_id=str(uid), status="active", **value.model_dump())
        with self._conn() as conn:
            self._ensure_user(conn, user_id)
            self._insert_radar_row(conn, item)
            self._replace_radar_children(conn, item)
        return item

    def save_radar(self, item: RadarRead) -> RadarRead:
        with self._conn() as conn:
            conn.execute(
                text(
                    "UPDATE radars SET name=:name, description=:description, goal=:goal, status=CAST(:status AS radar_status), minimum_budget=:minimum_budget, frequency=:frequency, freshness_hours=:freshness_hours, last_run_at=:last_run_at, next_run_at=:next_run_at, last_stats=CAST(:last_stats AS jsonb), listener_description=:listener_description, listener_config=CAST(:listener_config AS jsonb), updated_at=NOW() WHERE id=CAST(:id AS uuid)"
                ),
                {
                    "id": as_uuid(item.id),
                    "name": item.name,
                    "description": item.description,
                    "goal": item.goal,
                    "status": item.status,
                    "minimum_budget": item.minimum_budget,
                    "frequency": item.frequency,
                    "freshness_hours": item.freshness_hours,
                    "last_run_at": item.last_run_at,
                    "next_run_at": item.next_run_at,
                    "last_stats": json.dumps(item.stats.model_dump()),
                    "listener_description": item.listener_description,
                    "listener_config": json.dumps(item.listener_config) if item.listener_config else None,
                },
            )
            self._replace_radar_children(conn, item)
        return item

    def delete_radar(self, user_id: str, radar_id: str) -> None:
        self.get_radar(user_id, radar_id)
        with self._conn() as conn:
            conn.execute(text("DELETE FROM radars WHERE id=CAST(:rid AS uuid) AND user_id=CAST(:uid AS uuid)"), {"rid": as_uuid(radar_id), "uid": as_uuid(user_id)})

    def _insert_radar_row(self, conn: Connection, item: RadarRead) -> None:
        conn.execute(
            text(
                "INSERT INTO radars (id, user_id, name, description, goal, status, minimum_budget, frequency, freshness_hours, last_run_at, next_run_at, last_stats, listener_description, listener_config) "
                "VALUES (CAST(:id AS uuid), CAST(:user_id AS uuid), :name, :description, :goal, CAST(:status AS radar_status), :minimum_budget, :frequency, :freshness_hours, :last_run_at, :next_run_at, CAST(:last_stats AS jsonb), :listener_description, CAST(:listener_config AS jsonb))"
            ),
            {
                "id": as_uuid(item.id),
                "user_id": as_uuid(item.user_id),
                "name": item.name,
                "description": item.description,
                "goal": item.goal,
                "status": item.status,
                "minimum_budget": item.minimum_budget,
                "frequency": item.frequency,
                "freshness_hours": item.freshness_hours,
                "last_run_at": item.last_run_at,
                "next_run_at": item.next_run_at,
                "last_stats": json.dumps(item.stats.model_dump()),
                "listener_description": item.listener_description,
                "listener_config": json.dumps(item.listener_config) if item.listener_config else None,
            },
        )

    def _replace_radar_children(self, conn: Connection, item: RadarRead) -> None:
        rid = as_uuid(item.id)
        conn.execute(text("DELETE FROM radar_keywords WHERE radar_id=CAST(:rid AS uuid)"), {"rid": rid})
        conn.execute(text("DELETE FROM radar_locations WHERE radar_id=CAST(:rid AS uuid)"), {"rid": rid})
        conn.execute(text("DELETE FROM radar_sources WHERE radar_id=CAST(:rid AS uuid)"), {"rid": rid})
        conn.execute(text("DELETE FROM radar_queries WHERE radar_id=CAST(:rid AS uuid)"), {"rid": rid})
        for keyword in item.keywords:
            conn.execute(text("INSERT INTO radar_keywords (radar_id, keyword) VALUES (CAST(:rid AS uuid), :keyword)"), {"rid": rid, "keyword": keyword})
        for location in item.locations:
            conn.execute(text("INSERT INTO radar_locations (radar_id, location) VALUES (CAST(:rid AS uuid), :location)"), {"rid": rid, "location": location})
        for slug in item.sources:
            source_id = self._source_id(conn, slug)
            conn.execute(text("INSERT INTO radar_sources (radar_id, source_id, enabled) VALUES (CAST(:rid AS uuid), CAST(:sid AS uuid), TRUE) ON CONFLICT (radar_id, source_id) DO NOTHING"), {"rid": rid, "sid": source_id})
        for query in item.queries:
            conn.execute(
                text("INSERT INTO radar_queries (radar_id, query, source, priority) VALUES (CAST(:rid AS uuid), :query, :source, :priority)"),
                {"rid": rid, "query": query.query, "source": query.source, "priority": query.priority},
            )

    def _source_id(self, conn: Connection, slug: str) -> str:
        row = conn.execute(text("SELECT id FROM sources WHERE slug=:slug"), {"slug": slug}).first()
        if row:
            return str(row[0])
        source_id = str(uuid4())
        conn.execute(
            text("INSERT INTO sources (id, slug, name, type, status) VALUES (CAST(:id AS uuid), :slug, :name, :type, 'available') ON CONFLICT (slug) DO NOTHING"),
            {"id": source_id, "slug": slug, "name": slug, "type": slug},
        )
        row = conn.execute(text("SELECT id FROM sources WHERE slug=:slug"), {"slug": slug}).first()
        return str(row[0]) if row else source_id

    def _radar_from_row(self, conn: Connection, row) -> RadarRead:
        rid = str(row["id"])
        keywords = [item["keyword"] for item in conn.execute(text("SELECT keyword FROM radar_keywords WHERE radar_id=CAST(:rid AS uuid)"), {"rid": rid}).mappings()]
        locations = [item["location"] for item in conn.execute(text("SELECT location FROM radar_locations WHERE radar_id=CAST(:rid AS uuid)"), {"rid": rid}).mappings()]
        allowed = {"mock", "public_web", "github", "hackernews", "rss", "web_search"}
        sources = [item["slug"] for item in conn.execute(text("SELECT s.slug FROM radar_sources rs JOIN sources s ON s.id=rs.source_id WHERE rs.radar_id=CAST(:rid AS uuid)"), {"rid": rid}).mappings() if item["slug"] in allowed]
        queries = [QueryPlanItem(query=item["query"], source=item["source"] if item["source"] in allowed else "mock", priority=item["priority"]) for item in conn.execute(text("SELECT query, source, priority FROM radar_queries WHERE radar_id=CAST(:rid AS uuid) ORDER BY priority DESC"), {"rid": rid}).mappings()]
        stats_raw = row["last_stats"] if "last_stats" in row.keys() else {}
        if isinstance(stats_raw, str):
            stats_raw = json.loads(stats_raw or "{}")
        stats = RadarRunStats.model_validate(stats_raw or {})
        listener_config = row["listener_config"] if "listener_config" in row.keys() else None
        if isinstance(listener_config, str):
            listener_config = json.loads(listener_config) if listener_config else None
        payload = {
            "id": rid,
            "user_id": str(row["user_id"]),
            "name": row["name"],
            "description": row["description"] or "",
            "goal": row["goal"],
            "status": row["status"],
            "minimum_budget": row["minimum_budget"] or 0,
            "frequency": row["frequency"] or "daily",
            "freshness_hours": row["freshness_hours"] or 72,
            "keywords": keywords,
            "locations": locations,
            "sources": sources or ["mock"],
            "queries": queries,
            "last_run_at": row["last_run_at"],
            "next_run_at": row["next_run_at"],
            "stats": stats,
            "listener_description": row["listener_description"] if "listener_description" in row.keys() and row["listener_description"] else "",
            "listener_config": listener_config if isinstance(listener_config, dict) else None,
        }
        return RadarRead.model_validate(payload)

    def has_raw(self, radar_id: str, url: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(text("SELECT 1 FROM raw_items WHERE radar_id=CAST(:rid AS uuid) AND url_hash=:url_hash LIMIT 1"), {"rid": as_uuid(radar_id), "url_hash": hash_url(url)}).first()
            return row is not None

    def mark_raw(self, radar_id: str, url: str, item: RawItem | None = None, embedding: list[float] | None = None) -> str:
        title = item.title if item else url
        content = item.content if item else ""
        author = item.author if item else None
        published_at = item.published_at if item else None
        external_id = item.external_id if item else url
        source_slug = item.source if item else "mock"
        metadata = item.metadata if item else {}
        platform = item.platform if item else None
        language = item.language if item else None
        engagement = item.engagement if item else {}
        updated_at_source = item.updated_at_source if item else None
        digest = hash_url(item.url if item else url)
        body_hash = content_hash(item) if item else hash_url(f"{title}|{content}")
        with self._conn() as conn:
            source_id = self._source_id(conn, source_slug)
            row = conn.execute(
                text(
                    "INSERT INTO raw_items (radar_id, source_id, external_id, title, content, url, author, published_at, content_hash, url_hash, raw_data, processing_status, platform, language, engagement, updated_at_source, embedding, embedding_model) "
                    "VALUES (CAST(:rid AS uuid), CAST(:sid AS uuid), :external_id, :title, :content, :url, :author, :published_at, :content_hash, :url_hash, CAST(:raw_data AS jsonb), 'processed', :platform, :language, CAST(:engagement AS jsonb), :updated_at_source, CAST(:embedding AS vector), :embedding_model) "
                    "ON CONFLICT (radar_id, url_hash) DO UPDATE SET "
                    "last_seen_at=NOW(), seen_count=raw_items.seen_count + 1, engagement=EXCLUDED.engagement, "
                    "content_changed_at=CASE WHEN raw_items.content_hash <> EXCLUDED.content_hash THEN NOW() ELSE raw_items.content_changed_at END, "
                    "content_hash=EXCLUDED.content_hash, title=EXCLUDED.title, raw_data=EXCLUDED.raw_data, updated_at_source=EXCLUDED.updated_at_source, "
                    "embedding=COALESCE(EXCLUDED.embedding, raw_items.embedding), embedding_model=COALESCE(EXCLUDED.embedding_model, raw_items.embedding_model) "
                    "RETURNING id, seen_count"
                ),
                {
                    "rid": as_uuid(radar_id),
                    "sid": source_id,
                    "external_id": external_id,
                    "title": title[:500] if title else url,
                    "content": content or title or url,
                    "url": item.url if item else url,
                    "author": author,
                    "published_at": published_at,
                    "content_hash": body_hash,
                    "url_hash": digest,
                    "raw_data": json.dumps(metadata or {}),
                    "platform": platform,
                    "language": language,
                    "engagement": json.dumps(engagement or {}),
                    "updated_at_source": updated_at_source,
                    "embedding": vector_literal(embedding) if embedding else None,
                    "embedding_model": get_settings().embedding_model if embedding else None,
                },
            ).mappings().first()
            return str(row["id"]) if row else ""

    def find_similar_raw(self, radar_id: str, vector: list[float], threshold: float = 0.92) -> str | None:
        # cosine distance <= 1 - threshold
        with self._conn() as conn:
            row = conn.execute(
                text(
                    "SELECT id FROM raw_items WHERE radar_id=CAST(:rid AS uuid) AND embedding IS NOT NULL "
                    "AND embedding <=> CAST(:vec AS vector) <= :max_distance ORDER BY embedding <=> CAST(:vec AS vector) LIMIT 1"
                ),
                {"rid": as_uuid(radar_id), "vec": vector_literal(vector), "max_distance": 1.0 - threshold},
            ).first()
            return str(row[0]) if row else None

    def create_run(self, radar_id: str) -> RadarRunRead:
        run = RadarRunRead(id=str(uuid4()), radar_id=str(as_uuid(radar_id)), status="queued", stats=RadarRunStats())
        with self._conn() as conn:
            conn.execute(
                text("INSERT INTO radar_runs (id, radar_id, status, query_count, items_found, items_deduplicated, items_analyzed, opportunities_found, matched_count, recommended_count) VALUES (CAST(:id AS uuid), CAST(:rid AS uuid), :status, 0, 0, 0, 0, 0, 0, 0)"),
                {"id": run.id, "rid": as_uuid(radar_id), "status": run.status},
            )
        return run

    def save_run(self, run: RadarRunRead) -> RadarRunRead:
        finished = datetime.now(UTC) if run.status in {"completed", "failed"} else None
        with self._conn() as conn:
            conn.execute(
                text(
                    "UPDATE radar_runs SET status=:status, finished_at=COALESCE(:finished_at, finished_at), query_count=:query_count, items_found=:items_found, items_deduplicated=:items_deduplicated, items_analyzed=:items_analyzed, opportunities_found=:opportunities_found, matched_count=:matched_count, recommended_count=:recommended_count, error_message=:error_message, error_code=:error_code, stage_stats=CAST(:stage_stats AS jsonb) WHERE id=CAST(:id AS uuid)"
                ),
                {
                    "id": as_uuid(run.id),
                    "status": run.status,
                    "finished_at": finished,
                    "query_count": run.stats.queries,
                    "items_found": run.stats.items_found,
                    "items_deduplicated": run.stats.duplicates_removed,
                    "items_analyzed": run.stats.analyzed,
                    "opportunities_found": run.stats.opportunities_found,
                    "matched_count": run.stats.matched,
                    "recommended_count": run.stats.recommended,
                    "error_message": run.error_message,
                    "error_code": run.error_code,
                    "stage_stats": json.dumps(run.stage_stats or {}),
                },
            )
        return run

    def get_run(self, user_id: str, run_id: str) -> RadarRunRead:
        with self._conn() as conn:
            row = conn.execute(text("SELECT rr.* FROM radar_runs rr JOIN radars r ON r.id=rr.radar_id WHERE rr.id=CAST(:id AS uuid) AND r.user_id=CAST(:uid AS uuid)"), {"id": as_uuid(run_id), "uid": as_uuid(user_id)}).mappings().first()
            if row is None:
                raise AppError("RUN_NOT_FOUND", "未找到该运行记录。", 404)
            return self._run_from_row(row)

    def runs_of_user(self, user_id: str) -> list[RadarRunRead]:
        with self._conn() as conn:
            rows = conn.execute(text("SELECT rr.* FROM radar_runs rr JOIN radars r ON r.id=rr.radar_id WHERE r.user_id=CAST(:uid AS uuid)"), {"uid": as_uuid(user_id)}).mappings().all()
            return [self._run_from_row(row) for row in rows]

    def _run_from_row(self, row) -> RadarRunRead:
        stats = RadarRunStats(queries=row["query_count"] or 0, items_found=row["items_found"] or 0, duplicates_removed=row["items_deduplicated"] or 0, analyzed=row["items_analyzed"] or 0, opportunities_found=row["opportunities_found"] or 0, matched=row["matched_count"] or 0, recommended=row["recommended_count"] or 0)
        return RadarRunRead(id=str(row["id"]), radar_id=str(row["radar_id"]), status=row["status"], stats=stats, error_message=row["error_message"], error_code=row["error_code"] if "error_code" in row.keys() else None)

    def add_opportunity(self, item: OpportunityRead, user_id: str | None = None) -> OpportunityRead:
        with self._conn() as conn:
            uid = as_uuid(user_id) if user_id else None
            if uid is None:
                owner = conn.execute(text("SELECT user_id FROM radars WHERE id=CAST(:rid AS uuid)"), {"rid": as_uuid(item.radar_id)}).first()
                if owner is None:
                    raise AppError("RADAR_NOT_FOUND", "未找到该机会雷达。", 404)
                uid = str(owner[0])
            self._upsert_opportunity(conn, item, uid)
        return item

    def list_opportunities(self, user_id: str) -> list[OpportunityRead]:
        with self._conn() as conn:
            rows = conn.execute(text("SELECT * FROM opportunities WHERE user_id=CAST(:uid AS uuid) ORDER BY created_at DESC"), {"uid": as_uuid(user_id)}).mappings().all()
            return [self._opportunity_from_row(conn, row) for row in rows]

    def get_opportunity(self, user_id: str, opportunity_id: str) -> OpportunityRead:
        with self._conn() as conn:
            row = conn.execute(text("SELECT * FROM opportunities WHERE id=CAST(:id AS uuid) AND user_id=CAST(:uid AS uuid)"), {"id": as_uuid(opportunity_id), "uid": as_uuid(user_id)}).mappings().first()
            if row is None:
                raise AppError("OPPORTUNITY_NOT_FOUND", "未找到该机会。", 404)
            return self._opportunity_from_row(conn, row)

    def save_opportunity(self, item: OpportunityRead) -> OpportunityRead:
        with self._conn() as conn:
            owner = conn.execute(text("SELECT user_id FROM opportunities WHERE id=CAST(:id AS uuid)"), {"id": as_uuid(item.id)}).first()
            if owner is None:
                owner = conn.execute(text("SELECT user_id FROM radars WHERE id=CAST(:rid AS uuid)"), {"rid": as_uuid(item.radar_id)}).first()
            if owner is None:
                raise AppError("OPPORTUNITY_NOT_FOUND", "未找到该机会。", 404)
            self._upsert_opportunity(conn, item, str(owner[0]))
        return item

    def _upsert_opportunity(self, conn: Connection, item: OpportunityRead, user_id: str) -> None:
        hours = max(float(item.estimated_hours or 1), 1)
        conn.execute(
            text(
                "INSERT INTO opportunities (id, user_id, radar_id, type, title, summary, source, source_url, published_at, location, work_mode, budget_min, budget_max, currency, estimated_hours, match_score, opportunity_score, conversion_probability, risk_score, recommendation, status, actual_revenue, actual_hours, closed_at, money_score, money_breakdown, information_edge, information_edge_breakdown, verification_status) "
                "VALUES (CAST(:id AS uuid), CAST(:user_id AS uuid), CAST(:radar_id AS uuid), CAST(:type AS opportunity_type), :title, :summary, :source, :source_url, :published_at, :location, :work_mode, :budget_min, :budget_max, :currency, :estimated_hours, :match_score, :opportunity_score, :conversion_probability, :risk_score, :recommendation, CAST(:status AS opportunity_status), :actual_revenue, :actual_hours, :closed_at, :money_score, CAST(:money_breakdown AS jsonb), :information_edge, CAST(:information_edge_breakdown AS jsonb), :verification_status) "
                "ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, summary=EXCLUDED.summary, status=EXCLUDED.status, match_score=EXCLUDED.match_score, opportunity_score=EXCLUDED.opportunity_score, conversion_probability=EXCLUDED.conversion_probability, risk_score=EXCLUDED.risk_score, recommendation=EXCLUDED.recommendation, actual_revenue=EXCLUDED.actual_revenue, actual_hours=EXCLUDED.actual_hours, closed_at=EXCLUDED.closed_at, money_score=EXCLUDED.money_score, money_breakdown=EXCLUDED.money_breakdown, information_edge=EXCLUDED.information_edge, information_edge_breakdown=EXCLUDED.information_edge_breakdown, verification_status=EXCLUDED.verification_status, updated_at=NOW()"
            ),
            {
                "id": as_uuid(item.id),
                "user_id": as_uuid(user_id),
                "radar_id": as_uuid(item.radar_id),
                "type": item.type,
                "title": item.title,
                "summary": item.summary,
                "source": item.source,
                "source_url": item.source_url,
                "published_at": item.published_at,
                "location": item.location,
                "work_mode": item.work_mode,
                "budget_min": item.budget_min,
                "budget_max": item.budget_max,
                "currency": item.currency,
                "estimated_hours": hours,
                "match_score": item.match_score,
                "opportunity_score": item.opportunity_score,
                "conversion_probability": item.conversion_probability,
                "risk_score": item.risk_score,
                "recommendation": item.recommendation,
                "status": item.status,
                "actual_revenue": None,
                "actual_hours": None,
                "closed_at": None,
                "money_score": item.money_score,
                "money_breakdown": json.dumps(item.money_breakdown) if item.money_breakdown else None,
                "information_edge": item.information_edge,
                "information_edge_breakdown": json.dumps(item.information_edge_breakdown) if item.information_edge_breakdown else None,
                "verification_status": item.verification_status,
            },
        )
        oid = as_uuid(item.id)
        conn.execute(text("DELETE FROM opportunity_skills WHERE opportunity_id=CAST(:id AS uuid)"), {"id": oid})
        conn.execute(text("DELETE FROM opportunity_reasons WHERE opportunity_id=CAST(:id AS uuid)"), {"id": oid})
        conn.execute(text("DELETE FROM opportunity_warnings WHERE opportunity_id=CAST(:id AS uuid)"), {"id": oid})
        for skill in item.skills:
            conn.execute(text("INSERT INTO opportunity_skills (opportunity_id, skill, matched) VALUES (CAST(:id AS uuid), :skill, TRUE) ON CONFLICT (opportunity_id, skill) DO NOTHING"), {"id": oid, "skill": skill})
        for reason in item.reasons:
            conn.execute(text("INSERT INTO opportunity_reasons (opportunity_id, reason) VALUES (CAST(:id AS uuid), :reason)"), {"id": oid, "reason": reason})
        for warning in item.warnings:
            conn.execute(text("INSERT INTO opportunity_warnings (opportunity_id, warning) VALUES (CAST(:id AS uuid), :warning)"), {"id": oid, "warning": warning})

    def _opportunity_from_row(self, conn: Connection, row) -> OpportunityRead:
        oid = str(row["id"])
        skills = [item["skill"] for item in conn.execute(text("SELECT skill FROM opportunity_skills WHERE opportunity_id=CAST(:id AS uuid)"), {"id": oid}).mappings()]
        reasons = [item["reason"] for item in conn.execute(text("SELECT reason FROM opportunity_reasons WHERE opportunity_id=CAST(:id AS uuid)"), {"id": oid}).mappings()]
        warnings = [item["warning"] for item in conn.execute(text("SELECT warning FROM opportunity_warnings WHERE opportunity_id=CAST(:id AS uuid)"), {"id": oid}).mappings()]
        hours = float(row["estimated_hours"] or 1) or 1
        low = round((row["budget_min"] or 0) / hours)
        high = round((row["budget_max"] or 0) / hours)
        money_breakdown = row["money_breakdown"] if "money_breakdown" in row.keys() else None
        edge_breakdown = row["information_edge_breakdown"] if "information_edge_breakdown" in row.keys() else None
        if isinstance(money_breakdown, str):
            money_breakdown = json.loads(money_breakdown)
        if isinstance(edge_breakdown, str):
            edge_breakdown = json.loads(edge_breakdown)
        return OpportunityRead(
            id=oid,
            radar_id=str(row["radar_id"]),
            type=row["type"],
            title=row["title"],
            summary=row["summary"],
            source=row["source"],
            source_url=row["source_url"],
            published_at=row["published_at"],
            location=row["location"] or "",
            work_mode=row["work_mode"] or "online",
            budget_min=row["budget_min"] or 0,
            budget_max=row["budget_max"] or 0,
            currency=row["currency"] or "CNY",
            estimated_hours=hours,
            estimated_hourly_rate=(low, high),
            match_score=row["match_score"],
            opportunity_score=row["opportunity_score"],
            conversion_probability=row["conversion_probability"],
            risk_score=row["risk_score"],
            recommendation=row["recommendation"],
            status=row["status"],
            skills=skills,
            reasons=reasons,
            warnings=warnings,
            money_score=row["money_score"] if "money_score" in row.keys() else None,
            money_breakdown=money_breakdown,
            information_edge=row["information_edge"] if "information_edge" in row.keys() else None,
            information_edge_breakdown=edge_breakdown,
            verification_status=row["verification_status"] if "verification_status" in row.keys() and row["verification_status"] else "unverified",
        )

    def record_action(self, opportunity_id: str, payload: OpportunityAction, action: str | None = None) -> OpportunityAction:
        with self._conn() as conn:
            row = conn.execute(text("SELECT user_id, status FROM opportunities WHERE id=CAST(:id AS uuid)"), {"id": as_uuid(opportunity_id)}).mappings().first()
            if row is None:
                raise AppError("OPPORTUNITY_NOT_FOUND", "未找到该机会。", 404)
            status = action or row["status"]
            conn.execute(
                text("INSERT INTO opportunity_actions (user_id, opportunity_id, action, metadata, actual_revenue, actual_hours, closed_at) VALUES (CAST(:uid AS uuid), CAST(:oid AS uuid), CAST(:action AS opportunity_status), CAST(:metadata AS jsonb), :actual_revenue, :actual_hours, :closed_at)"),
                {
                    "uid": str(row["user_id"]),
                    "oid": as_uuid(opportunity_id),
                    "action": status,
                    "metadata": json.dumps({}),
                    "actual_revenue": payload.actual_revenue,
                    "actual_hours": payload.actual_hours,
                    "closed_at": payload.closed_at,
                },
            )
            conn.execute(
                text("UPDATE opportunities SET actual_revenue=COALESCE(:actual_revenue, actual_revenue), actual_hours=COALESCE(:actual_hours, actual_hours), closed_at=COALESCE(:closed_at, closed_at), updated_at=NOW() WHERE id=CAST(:id AS uuid)"),
                {"id": as_uuid(opportunity_id), "actual_revenue": payload.actual_revenue, "actual_hours": payload.actual_hours, "closed_at": payload.closed_at},
            )
        return payload

    def scanned_count(self, user_id: str) -> int:
        with self._conn() as conn:
            value = conn.execute(text("SELECT COALESCE(SUM(rr.items_found), 0) FROM radar_runs rr JOIN radars r ON r.id=rr.radar_id WHERE r.user_id=CAST(:uid AS uuid)"), {"uid": as_uuid(user_id)}).scalar()
            return int(value or 0)

    def won_revenue(self, user_id: str) -> int:
        with self._conn() as conn:
            rows = conn.execute(text("SELECT o.id, o.budget_max, o.actual_revenue FROM opportunities o WHERE o.user_id=CAST(:uid AS uuid) AND o.status='won'"), {"uid": as_uuid(user_id)}).mappings().all()
            total = 0
            for row in rows:
                if row["actual_revenue"] is not None:
                    total += int(row["actual_revenue"])
                    continue
                action = conn.execute(text("SELECT actual_revenue FROM opportunity_actions WHERE opportunity_id=CAST(:id AS uuid) AND actual_revenue IS NOT NULL ORDER BY created_at DESC LIMIT 1"), {"id": str(row["id"])}).first()
                total += int(action[0]) if action and action[0] is not None else int(row["budget_max"] or 0)
            return total

    def daily_brief(self, user_id: str) -> DailyBriefRead:
        from ..services.daily_intelligence import assemble

        items = self.list_opportunities(user_id)
        recommended = [item for item in items if item.recommendation == "强烈推荐"]
        scanned = self.scanned_count(user_id) or len(items)
        low, high = potential_income_range(items)
        uid = as_uuid(user_id)
        signals = self.list_signals(user_id, limit=200)
        clusters = self.list_clusters(user_id, limit=50)
        changes = self.list_change_events(user_id=user_id, limit=50)
        brief = assemble(items, signals=signals, clusters=clusters, changes=changes)
        brief = brief.model_copy(update={
            "scanned_count": scanned,
            "opportunities_count": len(items),
            "recommended_count": len(recommended),
            "potential_income_min": low,
            "potential_income_max": high,
        })
        with self._conn() as conn:
            self._ensure_user(conn, user_id)
            conn.execute(
                text(
                    "INSERT INTO daily_briefs (user_id, date, scanned_count, opportunities_count, recommended_count, potential_income_min, potential_income_max, summary, signals, avoid, actions, top_opportunities, rising_trends, pain_points, payment_signals, job_market_signals, tender_signals, content_opportunities, today_actions, brief_version) "
                    "VALUES (CAST(:uid AS uuid), :date, :scanned_count, :opportunities_count, :recommended_count, :potential_income_min, :potential_income_max, :summary, CAST(:signals AS jsonb), CAST(:avoid AS jsonb), CAST(:actions AS jsonb), CAST(:top_opportunities AS jsonb), CAST(:rising_trends AS jsonb), CAST(:pain_points AS jsonb), CAST(:payment_signals AS jsonb), CAST(:job_market_signals AS jsonb), CAST(:tender_signals AS jsonb), CAST(:content_opportunities AS jsonb), CAST(:today_actions AS jsonb), :brief_version) "
                    "ON CONFLICT (user_id, date) DO UPDATE SET scanned_count=EXCLUDED.scanned_count, opportunities_count=EXCLUDED.opportunities_count, recommended_count=EXCLUDED.recommended_count, potential_income_min=EXCLUDED.potential_income_min, potential_income_max=EXCLUDED.potential_income_max, summary=EXCLUDED.summary, signals=EXCLUDED.signals, avoid=EXCLUDED.avoid, actions=EXCLUDED.actions, top_opportunities=EXCLUDED.top_opportunities, rising_trends=EXCLUDED.rising_trends, pain_points=EXCLUDED.pain_points, payment_signals=EXCLUDED.payment_signals, job_market_signals=EXCLUDED.job_market_signals, tender_signals=EXCLUDED.tender_signals, content_opportunities=EXCLUDED.content_opportunities, today_actions=EXCLUDED.today_actions, brief_version=EXCLUDED.brief_version"
                ),
                {
                    "uid": uid,
                    "date": brief.date,
                    "scanned_count": brief.scanned_count,
                    "opportunities_count": brief.opportunities_count,
                    "recommended_count": brief.recommended_count,
                    "potential_income_min": brief.potential_income_min,
                    "potential_income_max": brief.potential_income_max,
                    "summary": brief.summary,
                    "signals": json.dumps(brief.signals),
                    "avoid": json.dumps(brief.avoid),
                    "actions": json.dumps(brief.actions),
                    "top_opportunities": json.dumps(brief.top_opportunities),
                    "rising_trends": json.dumps(brief.rising_trends),
                    "pain_points": json.dumps(brief.pain_points),
                    "payment_signals": json.dumps(brief.payment_signals),
                    "job_market_signals": json.dumps(brief.job_market_signals),
                    "tender_signals": json.dumps(brief.tender_signals),
                    "content_opportunities": json.dumps(brief.content_opportunities),
                    "today_actions": json.dumps(brief.today_actions),
                    "brief_version": brief.brief_version,
                },
            )
        return brief

    def list_due_radars(self, now: datetime) -> list[tuple[str, str]]:
        with self._conn() as conn:
            rows = conn.execute(
                text(
                    "SELECT r.user_id::text AS user_id, r.id::text AS radar_id FROM radars r "
                    "WHERE r.status = 'active' AND (r.next_run_at IS NULL OR r.next_run_at <= :now) "
                    "AND NOT EXISTS (SELECT 1 FROM radar_runs rr WHERE rr.radar_id = r.id AND rr.status IN ('queued', 'running'))"
                ),
                {"now": now},
            ).mappings().all()
            return [(row["user_id"], row["radar_id"]) for row in rows]

    def list_radar_pairs(self) -> list[tuple[str, str]]:
        with self._conn() as conn:
            rows = conn.execute(text("SELECT user_id::text AS user_id, id::text AS radar_id FROM radars")).mappings().all()
            return [(row["user_id"], row["radar_id"]) for row in rows]

    def record_llm_call(self, user_id: str | None, radar_id: str | None, run_id: str | None, provider: str | None, model: str, latency_ms: int, fallbacked: bool, schema_name: str, stage: str | None = None, input_count: int | None = None, output_count: int | None = None, prompt_tokens: int | None = None, completion_tokens: int | None = None, cost_usd: float | None = None) -> None:
        with self._conn() as conn:
            conn.execute(
                text(
                    "INSERT INTO llm_calls (user_id, radar_id, run_id, provider, model, latency_ms, fallbacked, schema_name, stage, input_count, output_count, prompt_tokens, completion_tokens, cost_usd) "
                    "VALUES (CAST(:user_id AS uuid), CAST(:radar_id AS uuid), CAST(:run_id AS uuid), :provider, :model, :latency_ms, :fallbacked, :schema_name, :stage, :input_count, :output_count, :prompt_tokens, :completion_tokens, :cost_usd)"
                ),
                {
                    "user_id": as_uuid(user_id) if user_id else None,
                    "radar_id": as_uuid(radar_id) if radar_id else None,
                    "run_id": as_uuid(run_id) if run_id else None,
                    "provider": provider,
                    "model": model,
                    "latency_ms": latency_ms,
                    "fallbacked": fallbacked,
                    "schema_name": schema_name,
                    "stage": stage,
                    "input_count": input_count,
                    "output_count": output_count,
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "cost_usd": cost_usd,
                },
            )

    def get_preference(self, user_id: str) -> PreferenceState:
        with self._conn() as conn:
            return load_preference(conn, as_uuid(user_id))

    def save_preference(self, user_id: str, state: PreferenceState) -> PreferenceState:
        with self._conn() as conn:
            self._ensure_user(conn, user_id)
            store_preference(conn, as_uuid(user_id), state)
        return state

    def record_event(self, user_id: str, opportunity_id: str | None, event: str, metadata: dict | None = None) -> None:
        with self._conn() as conn:
            self._ensure_user(conn, user_id)
            store_event(conn, as_uuid(user_id), as_uuid(opportunity_id) if opportunity_id else None, event, metadata or {})

    # ---- Money Intelligence extensions (Phase 1) ----

    def add_signal(self, signal: SignalRead, radar_id: str | None = None, raw_item_id: str | None = None, cluster_id: str | None = None) -> SignalRead:
        signal_id = str(uuid4())
        with self._conn() as conn:
            conn.execute(
                text(
                    "INSERT INTO signals (id, raw_item_id, radar_id, cluster_id, signal_type, title, entities, keywords, intent, sentiment, commercial_intent, payment_evidence, urgency, confidence, extraction_method, occurred_at) "
                    "VALUES (CAST(:id AS uuid), CAST(:raw_item_id AS uuid), CAST(:radar_id AS uuid), CAST(:cluster_id AS uuid), :signal_type, :title, CAST(:entities AS jsonb), CAST(:keywords AS jsonb), :intent, :sentiment, :commercial_intent, :payment_evidence, :urgency, :confidence, :extraction_method, :occurred_at)"
                ),
                {
                    "id": signal_id,
                    "raw_item_id": as_uuid(raw_item_id) if raw_item_id else None,
                    "radar_id": as_uuid(radar_id) if radar_id else None,
                    "cluster_id": as_uuid(cluster_id) if cluster_id else None,
                    "signal_type": signal.signal_type,
                    "title": signal.title[:500],
                    "entities": json.dumps(signal.entities),
                    "keywords": json.dumps(signal.keywords),
                    "intent": signal.intent,
                    "sentiment": signal.sentiment,
                    "commercial_intent": signal.commercial_intent,
                    "payment_evidence": signal.payment_evidence,
                    "urgency": signal.urgency,
                    "confidence": signal.confidence,
                    "extraction_method": signal.extraction_method,
                    "occurred_at": signal.occurred_at,
                },
            )
        return signal.model_copy(update={"id": signal_id, "radar_id": radar_id, "raw_item_id": raw_item_id, "cluster_id": cluster_id})

    def list_signals(self, user_id: str, radar_id: str | None = None, limit: int = 100) -> list[SignalRead]:
        with self._conn() as conn:
            rows = conn.execute(
                text(
                    "SELECT s.* FROM signals s JOIN radars r ON r.id=s.radar_id WHERE r.user_id=CAST(:uid AS uuid) "
                    "AND (CAST(:rid AS uuid) IS NULL OR s.radar_id=CAST(:rid AS uuid)) ORDER BY s.created_at DESC LIMIT :limit"
                ),
                {"uid": as_uuid(user_id), "rid": as_uuid(radar_id) if radar_id else None, "limit": limit},
            ).mappings().all()
            return [
                SignalRead(
                    id=str(row["id"]),
                    raw_item_id=str(row["raw_item_id"]) if row["raw_item_id"] else None,
                    radar_id=str(row["radar_id"]) if row["radar_id"] else None,
                    cluster_id=str(row["cluster_id"]) if row.get("cluster_id") else None,
                    signal_type=row["signal_type"],
                    title=row["title"] or "",
                    entities=row["entities"] if isinstance(row["entities"], list) else [],
                    keywords=row["keywords"] if isinstance(row["keywords"], list) else [],
                    intent=row["intent"],
                    sentiment=row["sentiment"],
                    commercial_intent=row["commercial_intent"] or 0,
                    payment_evidence=bool(row["payment_evidence"]),
                    urgency=row["urgency"] or 0,
                    confidence=row["confidence"] or 0,
                    extraction_method=row["extraction_method"] or "rule",
                    occurred_at=row["occurred_at"],
                    created_at=row["created_at"],
                )
                for row in rows
            ]

    def save_cluster(self, cluster: EventClusterRead, radar_id: str | None = None, member_raw_item_ids: list[str] | None = None) -> EventClusterRead:
        cluster_id = str(uuid4()) if cluster.id.startswith("cluster-") else cluster.id
        with self._conn() as conn:
            conn.execute(
                text(
                    "INSERT INTO event_clusters (id, radar_id, title, summary, keyphrases, centroid, source_count, document_count, unique_authors, unique_platforms, velocity_1h, velocity_24h, velocity_7d, velocity_30d, engagement_growth, breakout_score, representative_item_ids) "
                    "VALUES (CAST(:id AS uuid), CAST(:radar_id AS uuid), :title, :summary, CAST(:keyphrases AS jsonb), CAST(:centroid AS vector), :source_count, :document_count, :unique_authors, :unique_platforms, :velocity_1h, :velocity_24h, :velocity_7d, :velocity_30d, :engagement_growth, :breakout_score, CAST(:representative AS jsonb)) "
                    "ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, summary=EXCLUDED.summary, keyphrases=EXCLUDED.keyphrases, centroid=COALESCE(EXCLUDED.centroid, event_clusters.centroid), source_count=EXCLUDED.source_count, document_count=EXCLUDED.document_count, unique_authors=EXCLUDED.unique_authors, unique_platforms=EXCLUDED.unique_platforms, velocity_24h=EXCLUDED.velocity_24h, breakout_score=EXCLUDED.breakout_score, representative_item_ids=EXCLUDED.representative_item_ids, last_seen_at=NOW(), updated_at=NOW()"
                ),
                {
                    "id": as_uuid(cluster_id),
                    "radar_id": as_uuid(radar_id) if radar_id else None,
                    "title": cluster.title[:500],
                    "summary": cluster.summary[:2000],
                    "keyphrases": json.dumps(cluster.keyphrases),
                    "centroid": vector_literal(cluster.centroid) if cluster.centroid else None,
                    "source_count": cluster.source_count,
                    "document_count": cluster.document_count,
                    "unique_authors": cluster.unique_authors,
                    "unique_platforms": cluster.unique_platforms,
                    "velocity_1h": cluster.velocity_1h,
                    "velocity_24h": cluster.velocity_24h,
                    "velocity_7d": cluster.velocity_7d,
                    "velocity_30d": cluster.velocity_30d,
                    "engagement_growth": cluster.engagement_growth,
                    "breakout_score": cluster.breakout_score,
                    "representative": json.dumps(cluster.representative_item_ids[:5]),
                },
            )
            for raw_item_id in member_raw_item_ids or []:
                conn.execute(
                    text("INSERT INTO event_cluster_members (cluster_id, raw_item_id) VALUES (CAST(:cid AS uuid), CAST(:rid AS uuid)) ON CONFLICT (cluster_id, raw_item_id) DO NOTHING"),
                    {"cid": as_uuid(cluster_id), "rid": as_uuid(raw_item_id)},
                )
        return cluster.model_copy(update={"id": cluster_id, "radar_id": radar_id})

    def list_clusters(self, user_id: str, radar_id: str | None = None, limit: int = 50) -> list[EventClusterRead]:
        with self._conn() as conn:
            rows = conn.execute(
                text(
                    "SELECT c.* FROM event_clusters c JOIN radars r ON r.id=c.radar_id WHERE r.user_id=CAST(:uid AS uuid) "
                    "AND (CAST(:rid AS uuid) IS NULL OR c.radar_id=CAST(:rid AS uuid)) AND c.merged_into IS NULL ORDER BY c.last_seen_at DESC LIMIT :limit"
                ),
                {"uid": as_uuid(user_id), "rid": as_uuid(radar_id) if radar_id else None, "limit": limit},
            ).mappings().all()
            return [
                EventClusterRead(
                    id=str(row["id"]),
                    radar_id=str(row["radar_id"]) if row["radar_id"] else None,
                    title=row["title"] or "",
                    summary=row["summary"] or "",
                    keyphrases=row["keyphrases"] if isinstance(row["keyphrases"], list) else [],
                    centroid=list(row["centroid"]) if row.get("centroid") is not None else None,
                    source_count=row["source_count"] or 0,
                    document_count=row["document_count"] or 0,
                    unique_authors=row["unique_authors"] or 0,
                    unique_platforms=row["unique_platforms"] or 0,
                    velocity_1h=float(row["velocity_1h"] or 0),
                    velocity_24h=float(row["velocity_24h"] or 0),
                    velocity_7d=float(row["velocity_7d"] or 0),
                    velocity_30d=float(row["velocity_30d"] or 0),
                    engagement_growth=float(row["engagement_growth"] or 0),
                    breakout_score=row["breakout_score"] or 0,
                    representative_item_ids=row["representative_item_ids"] if isinstance(row["representative_item_ids"], list) else [],
                    first_seen_at=row["first_seen_at"],
                    last_seen_at=row["last_seen_at"],
                )
                for row in rows
            ]

    def upsert_trend_topic(self, topic: TrendTopicRead) -> TrendTopicRead:
        with self._conn() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO trend_topics (radar_id, topic, metrics, mention_count, engagement) "
                    "VALUES (CAST(:rid AS uuid), :topic, CAST(:metrics AS jsonb), :mention_count, :engagement) "
                    "ON CONFLICT (radar_id, topic) DO UPDATE SET metrics=EXCLUDED.metrics, mention_count=trend_topics.mention_count + EXCLUDED.mention_count, engagement=trend_topics.engagement + EXCLUDED.engagement, last_seen_at=NOW() "
                    "RETURNING id, mention_count, engagement"
                ),
                {
                    "rid": as_uuid(topic.radar_id) if topic.radar_id else None,
                    "topic": topic.topic,
                    "metrics": json.dumps(topic.metrics),
                    "mention_count": topic.mention_count,
                    "engagement": topic.engagement,
                },
            ).mappings().first()
            if row is None:
                return topic
            return topic.model_copy(update={"id": str(row["id"]), "mention_count": row["mention_count"], "engagement": row["engagement"]})

    def save_trend_snapshot(self, snapshot: TrendSnapshotRead) -> TrendSnapshotRead:
        snapshot_id = str(uuid4())
        with self._conn() as conn:
            conn.execute(
                text(
                    "INSERT INTO trend_snapshots (id, topic_id, captured_at, mention_count, engagement, metrics) "
                    "VALUES (CAST(:id AS uuid), CAST(:topic_id AS uuid), COALESCE(:captured_at, NOW()), :mention_count, :engagement, CAST(:metrics AS jsonb))"
                ),
                {
                    "id": snapshot_id,
                    "topic_id": as_uuid(snapshot.topic_id),
                    "captured_at": snapshot.captured_at,
                    "mention_count": snapshot.mention_count,
                    "engagement": snapshot.engagement,
                    "metrics": json.dumps(snapshot.metrics),
                },
            )
        return snapshot.model_copy(update={"id": snapshot_id})

    def list_trend_topics(self, user_id: str | None = None, radar_id: str | None = None, limit: int = 100) -> list[TrendTopicRead]:
        query = "SELECT t.* FROM trend_topics t"
        conditions = []
        params: dict = {"limit": limit}
        if radar_id:
            conditions.append("t.radar_id=CAST(:rid AS uuid)")
            params["rid"] = as_uuid(radar_id)
        elif user_id:
            query += " JOIN radars r ON r.id=t.radar_id"
            conditions.append("r.user_id=CAST(:uid AS uuid)")
            params["uid"] = as_uuid(user_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY t.last_seen_at DESC LIMIT :limit"
        with self._conn() as conn:
            rows = conn.execute(text(query), params).mappings().all()
            return [
                TrendTopicRead(
                    id=str(row["id"]),
                    radar_id=str(row["radar_id"]) if row["radar_id"] else None,
                    topic=row["topic"],
                    mention_count=row["mention_count"] or 0,
                    engagement=row["engagement"] or 0,
                    metrics=row["metrics"] if isinstance(row["metrics"], dict) else {},
                    first_seen_at=row["first_seen_at"],
                    last_seen_at=row["last_seen_at"],
                )
                for row in rows
            ]

    def list_trend_snapshots(self, topic_id: str, limit: int = 720) -> list[TrendSnapshotRead]:
        with self._conn() as conn:
            rows = conn.execute(
                text("SELECT * FROM trend_snapshots WHERE topic_id=CAST(:tid AS uuid) ORDER BY captured_at DESC LIMIT :limit"),
                {"tid": as_uuid(topic_id), "limit": limit},
            ).mappings().all()
            return [
                TrendSnapshotRead(
                    id=str(row["id"]),
                    topic_id=str(row["topic_id"]),
                    captured_at=row["captured_at"],
                    mention_count=row["mention_count"] or 0,
                    engagement=row["engagement"] or 0,
                    metrics=row["metrics"] if isinstance(row["metrics"], dict) else {},
                )
                for row in rows
            ]

    def save_change_event(self, event: ChangeEventRead, radar_id: str | None = None) -> ChangeEventRead:
        event_id = str(uuid4())
        dedup_key = event.dedup_key or f"{radar_id or 'none'}:{event.subject_kind}:{event.subject_key}:{event.metric_key}:{(event.detected_at or datetime.now(UTC)).strftime('%Y-%m-%d')}"
        with self._conn() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO change_events (id, radar_id, subject_kind, subject_key, metric_key, baseline_value, current_value, change_rate, z_score, velocity, acceleration, momentum, breakout_score, is_breakout, dedup_key) "
                    "VALUES (CAST(:id AS uuid), CAST(:rid AS uuid), :subject_kind, :subject_key, :metric_key, :baseline_value, :current_value, :change_rate, :z_score, :velocity, :acceleration, :momentum, :breakout_score, :is_breakout, :dedup_key) "
                    "ON CONFLICT (dedup_key) DO NOTHING RETURNING id"
                ),
                {
                    "id": event_id,
                    "rid": as_uuid(radar_id) if radar_id else None,
                    "subject_kind": event.subject_kind,
                    "subject_key": event.subject_key[:500],
                    "metric_key": event.metric_key[:200],
                    "baseline_value": event.baseline_value,
                    "current_value": event.current_value,
                    "change_rate": event.change_rate,
                    "z_score": event.z_score,
                    "velocity": event.velocity,
                    "acceleration": event.acceleration,
                    "momentum": event.momentum,
                    "breakout_score": event.breakout_score,
                    "is_breakout": event.is_breakout,
                    "dedup_key": dedup_key,
                },
            ).first()
            if row is None:
                return event.model_copy(update={"dedup_key": dedup_key})  # already recorded today
        return event.model_copy(update={"id": event_id, "radar_id": radar_id, "dedup_key": dedup_key})

    def list_change_events(self, user_id: str | None = None, radar_id: str | None = None, limit: int = 100) -> list[ChangeEventRead]:
        query = "SELECT c.* FROM change_events c"
        conditions = []
        params: dict = {"limit": limit}
        if radar_id:
            conditions.append("c.radar_id=CAST(:rid AS uuid)")
            params["rid"] = as_uuid(radar_id)
        elif user_id:
            query += " JOIN radars r ON r.id=c.radar_id"
            conditions.append("r.user_id=CAST(:uid AS uuid)")
            params["uid"] = as_uuid(user_id)
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY c.detected_at DESC LIMIT :limit"
        with self._conn() as conn:
            rows = conn.execute(text(query), params).mappings().all()
            return [
                ChangeEventRead(
                    id=str(row["id"]),
                    radar_id=str(row["radar_id"]) if row["radar_id"] else None,
                    subject_kind=row["subject_kind"] or "topic",
                    subject_key=row["subject_key"] or "",
                    metric_key=row["metric_key"] or "",
                    baseline_value=float(row["baseline_value"] or 0),
                    current_value=float(row["current_value"] or 0),
                    change_rate=float(row["change_rate"] or 0),
                    z_score=float(row["z_score"] or 0),
                    velocity=float(row["velocity"] or 0),
                    acceleration=float(row["acceleration"] or 0),
                    momentum=float(row["momentum"] or 0),
                    breakout_score=row["breakout_score"] or 0,
                    is_breakout=bool(row["is_breakout"]),
                    detected_at=row["detected_at"],
                )
                for row in rows
            ]

    def record_source_health(self, slug: str, ok: bool, items: int, latency_ms: int, error_code: str | None = None, error_message: str | None = None) -> None:
        current = self.get_source_health(slug)
        from ..services.source_health_service import record

        updated = record(current, slug, ok, items, latency_ms, error_code, error_message)
        with self._conn() as conn:
            conn.execute(
                text(
                    "INSERT INTO source_health (slug, status, last_success_at, last_failure_at, last_error, last_error_code, runs_total, runs_ok, items_fetched, success_rate, avg_latency_ms, rate_limited_count, error_count, health_score) "
                    "VALUES (:slug, :status, :last_success_at, :last_failure_at, :last_error, :last_error_code, :runs_total, :runs_ok, :items_fetched, :success_rate, :avg_latency_ms, :rate_limited_count, :error_count, :health_score) "
                    "ON CONFLICT (slug) DO UPDATE SET status=EXCLUDED.status, last_success_at=EXCLUDED.last_success_at, last_failure_at=EXCLUDED.last_failure_at, last_error=EXCLUDED.last_error, last_error_code=EXCLUDED.last_error_code, runs_total=EXCLUDED.runs_total, runs_ok=EXCLUDED.runs_ok, items_fetched=EXCLUDED.items_fetched, success_rate=EXCLUDED.success_rate, avg_latency_ms=EXCLUDED.avg_latency_ms, rate_limited_count=EXCLUDED.rate_limited_count, error_count=EXCLUDED.error_count, health_score=EXCLUDED.health_score, updated_at=NOW()"
                ),
                {
                    "slug": slug,
                    "status": updated.status,
                    "last_success_at": updated.last_success_at,
                    "last_failure_at": updated.last_failure_at,
                    "last_error": updated.last_error,
                    "last_error_code": updated.last_error_code,
                    "runs_total": updated.runs_total,
                    "runs_ok": updated.runs_ok,
                    "items_fetched": updated.items_fetched,
                    "success_rate": updated.success_rate,
                    "avg_latency_ms": updated.avg_latency_ms,
                    "rate_limited_count": updated.rate_limited_count,
                    "error_count": updated.error_count,
                    "health_score": updated.health_score,
                },
            )

    def get_source_health(self, slug: str) -> SourceHealthRead | None:
        with self._conn() as conn:
            row = conn.execute(text("SELECT * FROM source_health WHERE slug=:slug"), {"slug": slug}).mappings().first()
            if row is None:
                return None
            return SourceHealthRead(
                slug=row["slug"],
                status=row["status"] or "unknown",
                last_success_at=row["last_success_at"],
                last_failure_at=row["last_failure_at"],
                last_error=row["last_error"],
                last_error_code=row["last_error_code"],
                runs_total=row["runs_total"] or 0,
                runs_ok=row["runs_ok"] or 0,
                items_fetched=row["items_fetched"] or 0,
                success_rate=float(row["success_rate"] or 0),
                avg_latency_ms=row["avg_latency_ms"] or 0,
                rate_limited_count=row["rate_limited_count"] or 0,
                error_count=row["error_count"] or 0,
                health_score=row["health_score"] or 0,
            )

    def list_source_health(self) -> list[SourceHealthRead]:
        with self._conn() as conn:
            rows = conn.execute(text("SELECT slug FROM source_health ORDER BY slug")).mappings().all()
            return [self.get_source_health(row["slug"]) for row in rows if self.get_source_health(row["slug"]) is not None]

    # ---- P1 guardrails / Phase 2 ----

    def get_brief(self, user_id: str, brief_date: date) -> DailyBriefRead | None:
        with self._conn() as conn:
            row = conn.execute(
                text("SELECT * FROM daily_briefs WHERE user_id=CAST(:uid AS uuid) AND date=:brief_date LIMIT 1"),
                {"uid": as_uuid(user_id), "brief_date": brief_date},
            ).mappings().first()
        if row is None:
            return None
        return self._brief_from_row(row)

    def _brief_from_row(self, row) -> DailyBriefRead:
        def _json_list(key: str) -> list:
            value = row[key] if key in row.keys() else None
            if isinstance(value, str):
                value = json.loads(value) if value else []
            return value if isinstance(value, list) else []

        return DailyBriefRead(
            date=row["date"],
            scanned_count=row["scanned_count"] or 0,
            opportunities_count=row["opportunities_count"] or 0,
            recommended_count=row["recommended_count"] or 0,
            potential_income_min=row["potential_income_min"] or 0,
            potential_income_max=row["potential_income_max"] or 0,
            summary=row["summary"] or "",
            signals=_json_list("signals"),
            avoid=_json_list("avoid"),
            actions=_json_list("actions"),
            top_opportunities=_json_list("top_opportunities"),
            rising_trends=_json_list("rising_trends"),
            pain_points=_json_list("pain_points"),
            payment_signals=_json_list("payment_signals"),
            job_market_signals=_json_list("job_market_signals"),
            tender_signals=_json_list("tender_signals"),
            content_opportunities=_json_list("content_opportunities"),
            today_actions=_json_list("today_actions"),
            brief_version=row["brief_version"] if "brief_version" in row.keys() and row["brief_version"] else "v2",
        )

    def cleanup_raw_items(self, days: int) -> int:
        with self._conn() as conn:
            result = conn.execute(
                text("DELETE FROM raw_items WHERE last_seen_at < NOW() - CAST(:days || ' days' AS interval)"),
                {"days": str(days)},
            )
            return result.rowcount or 0

    def cleanup_llm_calls(self, days: int) -> int:
        with self._conn() as conn:
            result = conn.execute(
                text("DELETE FROM llm_calls WHERE created_at < NOW() - CAST(:days || ' days' AS interval)"),
                {"days": str(days)},
            )
            return result.rowcount or 0

    def merge_cluster(self, source_id: str, target_id: str) -> None:
        if source_id == target_id:
            return
        with self._conn() as conn:
            conn.execute(
                text(
                    "INSERT INTO event_cluster_members (cluster_id, raw_item_id) "
                    "SELECT CAST(:target AS uuid), raw_item_id FROM event_cluster_members WHERE cluster_id=CAST(:source AS uuid) "
                    "ON CONFLICT (cluster_id, raw_item_id) DO NOTHING"
                ),
                {"source": as_uuid(source_id), "target": as_uuid(target_id)},
            )
            conn.execute(text("DELETE FROM event_cluster_members WHERE cluster_id=CAST(:source AS uuid)"), {"source": as_uuid(source_id)})
            conn.execute(
                text(
                    "UPDATE event_clusters SET document_count = document_count + (SELECT document_count FROM event_clusters WHERE id=CAST(:source AS uuid)), updated_at=NOW() WHERE id=CAST(:target AS uuid)"
                ),
                {"source": as_uuid(source_id), "target": as_uuid(target_id)},
            )
            conn.execute(
                text("UPDATE event_clusters SET merged_into=CAST(:target AS uuid), updated_at=NOW() WHERE id=CAST(:source AS uuid)"),
                {"source": as_uuid(source_id), "target": as_uuid(target_id)},
            )

    def upsert_pain_point(self, pain: PainPointRead) -> PainPointRead:
        pain_id = str(uuid4())
        with self._conn() as conn:
            row = conn.execute(
                text(
                    "INSERT INTO pain_points (id, radar_id, theme, title, summary, mention_count, growth_rate, platform_count, unique_user_count, severity, payment_intent, current_solutions, solution_satisfaction, cluster_id) "
                    "VALUES (CAST(:id AS uuid), CAST(:rid AS uuid), :theme, :title, :summary, :mention_count, :growth_rate, :platform_count, :unique_user_count, :severity, :payment_intent, :current_solutions, :solution_satisfaction, CAST(:cluster_id AS uuid)) "
                    "ON CONFLICT (radar_id, theme) DO UPDATE SET "
                    "title=EXCLUDED.title, summary=EXCLUDED.summary, mention_count=EXCLUDED.mention_count, "
                    "growth_rate=CASE WHEN pain_points.mention_count > 0 THEN ROUND((EXCLUDED.mention_count - pain_points.mention_count)::numeric / pain_points.mention_count, 4) ELSE 0 END, "
                    "platform_count=EXCLUDED.platform_count, unique_user_count=EXCLUDED.unique_user_count, severity=EXCLUDED.severity, payment_intent=EXCLUDED.payment_intent, current_solutions=EXCLUDED.current_solutions, solution_satisfaction=EXCLUDED.solution_satisfaction, cluster_id=EXCLUDED.cluster_id, last_seen_at=NOW(), updated_at=NOW() "
                    "RETURNING id, first_seen_at, growth_rate"
                ),
                {
                    "id": pain_id,
                    "rid": as_uuid(pain.radar_id) if pain.radar_id else None,
                    "theme": pain.theme[:200],
                    "title": pain.title[:500],
                    "summary": pain.summary[:2000],
                    "mention_count": pain.mention_count,
                    "growth_rate": pain.growth_rate,
                    "platform_count": pain.platform_count,
                    "unique_user_count": pain.unique_user_count,
                    "severity": pain.severity,
                    "payment_intent": pain.payment_intent,
                    "current_solutions": pain.current_solutions[:1000],
                    "solution_satisfaction": pain.solution_satisfaction,
                    "cluster_id": as_uuid(pain.cluster_id) if pain.cluster_id else None,
                },
            ).mappings().first()
        if row is None:
            return pain
        return pain.model_copy(update={"id": str(row["id"]), "first_seen_at": row["first_seen_at"], "growth_rate": float(row["growth_rate"] or 0)})

    def list_pain_points(self, user_id: str, radar_id: str | None = None, limit: int = 50) -> list[PainPointRead]:
        with self._conn() as conn:
            rows = conn.execute(
                text(
                    "SELECT p.* FROM pain_points p JOIN radars r ON r.id=p.radar_id WHERE r.user_id=CAST(:uid AS uuid) "
                    "AND (CAST(:rid AS uuid) IS NULL OR p.radar_id=CAST(:rid AS uuid)) ORDER BY p.severity DESC LIMIT :limit"
                ),
                {"uid": as_uuid(user_id), "rid": as_uuid(radar_id) if radar_id else None, "limit": limit},
            ).mappings().all()
            return [
                PainPointRead(
                    id=str(row["id"]),
                    radar_id=str(row["radar_id"]) if row["radar_id"] else None,
                    theme=row["theme"] or "",
                    title=row["title"] or "",
                    summary=row["summary"] or "",
                    mention_count=row["mention_count"] or 0,
                    growth_rate=float(row["growth_rate"] or 0),
                    platform_count=row["platform_count"] or 0,
                    unique_user_count=row["unique_user_count"] or 0,
                    severity=row["severity"] or 0,
                    payment_intent=row["payment_intent"] or 0,
                    current_solutions=row["current_solutions"] or "",
                    solution_satisfaction=row["solution_satisfaction"],
                    cluster_id=str(row["cluster_id"]) if row.get("cluster_id") else None,
                    first_seen_at=row["first_seen_at"],
                    last_seen_at=row["last_seen_at"],
                )
                for row in rows
            ]
