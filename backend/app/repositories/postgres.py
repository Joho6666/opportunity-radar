from __future__ import annotations

import json
from datetime import UTC, date, datetime
from uuid import UUID, uuid4, uuid5, NAMESPACE_URL
from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine
from ..core.errors import AppError
from ..schemas.domain import DailyBriefRead, OpportunityAction, OpportunityRead, ProfileRead, ProfileUpsert, QueryPlanItem, RadarCreate, RadarRead, RadarRunRead, RadarRunStats, RawItem, SkillInput
from ..services.dedup_service import content_hash, hash_url
from ..services.income import potential_income_range


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
                    "UPDATE radars SET name=:name, description=:description, goal=:goal, status=CAST(:status AS radar_status), minimum_budget=:minimum_budget, frequency=:frequency, freshness_hours=:freshness_hours, last_run_at=:last_run_at, next_run_at=:next_run_at, last_stats=CAST(:last_stats AS jsonb), updated_at=NOW() WHERE id=CAST(:id AS uuid)"
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
                "INSERT INTO radars (id, user_id, name, description, goal, status, minimum_budget, frequency, freshness_hours, last_run_at, next_run_at, last_stats) "
                "VALUES (CAST(:id AS uuid), CAST(:user_id AS uuid), :name, :description, :goal, CAST(:status AS radar_status), :minimum_budget, :frequency, :freshness_hours, :last_run_at, :next_run_at, CAST(:last_stats AS jsonb))"
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
        }
        return RadarRead.model_validate(payload)

    def has_raw(self, radar_id: str, url: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(text("SELECT 1 FROM raw_items WHERE radar_id=CAST(:rid AS uuid) AND url_hash=:url_hash LIMIT 1"), {"rid": as_uuid(radar_id), "url_hash": hash_url(url)}).first()
            return row is not None

    def mark_raw(self, radar_id: str, url: str, item: RawItem | None = None) -> None:
        title = item.title if item else url
        content = item.content if item else ""
        author = item.author if item else None
        published_at = item.published_at if item else None
        external_id = item.external_id if item else url
        source_slug = item.source if item else "mock"
        metadata = item.metadata if item else {}
        digest = hash_url(item.url if item else url)
        body_hash = content_hash(item) if item else hash_url(f"{title}|{content}")
        with self._conn() as conn:
            source_id = self._source_id(conn, source_slug)
            conn.execute(
                text(
                    "INSERT INTO raw_items (radar_id, source_id, external_id, title, content, url, author, published_at, content_hash, url_hash, raw_data, processing_status) "
                    "VALUES (CAST(:rid AS uuid), CAST(:sid AS uuid), :external_id, :title, :content, :url, :author, :published_at, :content_hash, :url_hash, CAST(:raw_data AS jsonb), 'processed') "
                    "ON CONFLICT DO NOTHING"
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
                },
            )

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
                    "UPDATE radar_runs SET status=:status, finished_at=COALESCE(:finished_at, finished_at), query_count=:query_count, items_found=:items_found, items_deduplicated=:items_deduplicated, items_analyzed=:items_analyzed, opportunities_found=:opportunities_found, matched_count=:matched_count, recommended_count=:recommended_count, error_message=:error_message, error_code=:error_code WHERE id=CAST(:id AS uuid)"
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
                "INSERT INTO opportunities (id, user_id, radar_id, type, title, summary, source, source_url, published_at, location, work_mode, budget_min, budget_max, currency, estimated_hours, match_score, opportunity_score, conversion_probability, risk_score, recommendation, status, actual_revenue, actual_hours, closed_at) "
                "VALUES (CAST(:id AS uuid), CAST(:user_id AS uuid), CAST(:radar_id AS uuid), CAST(:type AS opportunity_type), :title, :summary, :source, :source_url, :published_at, :location, :work_mode, :budget_min, :budget_max, :currency, :estimated_hours, :match_score, :opportunity_score, :conversion_probability, :risk_score, :recommendation, CAST(:status AS opportunity_status), :actual_revenue, :actual_hours, :closed_at) "
                "ON CONFLICT (id) DO UPDATE SET title=EXCLUDED.title, summary=EXCLUDED.summary, status=EXCLUDED.status, match_score=EXCLUDED.match_score, opportunity_score=EXCLUDED.opportunity_score, conversion_probability=EXCLUDED.conversion_probability, risk_score=EXCLUDED.risk_score, recommendation=EXCLUDED.recommendation, actual_revenue=EXCLUDED.actual_revenue, actual_hours=EXCLUDED.actual_hours, closed_at=EXCLUDED.closed_at, updated_at=NOW()"
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
        items = self.list_opportunities(user_id)
        recommended = [item for item in items if item.recommendation == "强烈推荐"]
        scanned = self.scanned_count(user_id) or len(items)
        low, high = potential_income_range(items)
        brief = DailyBriefRead(
            date=date.today(),
            scanned_count=scanned,
            opportunities_count=len(items),
            recommended_count=len(recommended),
            potential_income_min=low,
            potential_income_max=high,
            summary="AI 已按匹配度、收益与风险为你整理今日机会。",
            signals=["AI 自动化需求上升", "远程机会持续增加"],
            avoid=["需求范围模糊且预算偏低的项目"],
            actions=[f"优先联系：{item.title}" for item in recommended[:3]],
        )
        with self._conn() as conn:
            conn.execute(
                text(
                    "INSERT INTO daily_briefs (user_id, date, scanned_count, opportunities_count, recommended_count, potential_income_min, potential_income_max, summary, signals, avoid, actions) "
                    "VALUES (CAST(:uid AS uuid), :date, :scanned_count, :opportunities_count, :recommended_count, :potential_income_min, :potential_income_max, :summary, CAST(:signals AS jsonb), CAST(:avoid AS jsonb), CAST(:actions AS jsonb)) "
                    "ON CONFLICT (user_id, date) DO UPDATE SET scanned_count=EXCLUDED.scanned_count, opportunities_count=EXCLUDED.opportunities_count, recommended_count=EXCLUDED.recommended_count, potential_income_min=EXCLUDED.potential_income_min, potential_income_max=EXCLUDED.potential_income_max, summary=EXCLUDED.summary, signals=EXCLUDED.signals, avoid=EXCLUDED.avoid, actions=EXCLUDED.actions"
                ),
                {
                    "uid": as_uuid(user_id),
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

    def record_llm_call(self, user_id: str | None, radar_id: str | None, run_id: str | None, provider: str | None, model: str, latency_ms: int, fallbacked: bool, schema_name: str) -> None:
        with self._conn() as conn:
            conn.execute(
                text(
                    "INSERT INTO llm_calls (user_id, radar_id, run_id, provider, model, latency_ms, fallbacked, schema_name) "
                    "VALUES (CAST(:user_id AS uuid), CAST(:radar_id AS uuid), CAST(:run_id AS uuid), :provider, :model, :latency_ms, :fallbacked, :schema_name)"
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
                },
            )
