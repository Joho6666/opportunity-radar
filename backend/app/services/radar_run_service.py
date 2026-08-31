from datetime import UTC, datetime, timedelta
import logging
from uuid import uuid4
from ..collectors.registry import registry
from ..repositories.base import Repository
from ..schemas.domain import OpportunityRead, RadarRunStats
from .ai_service import analyze_raw_item, bind_llm_context, plan_queries, reset_llm_context
from .dedup_service import deduplicate
from .score_engine import calculate_score

logger = logging.getLogger(__name__)


def next_run_at(frequency: str, now: datetime) -> datetime | None:
    if frequency == "hourly":
        return now + timedelta(hours=1)
    if frequency == "weekly":
        return now + timedelta(days=7)
    if frequency == "daily":
        return now + timedelta(days=1)
    return now + timedelta(days=1)


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
            queries = radar.queries or await plan_queries(radar)
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
            unique, removed = deduplicate(raw)
            cutoff = datetime.now(UTC) - timedelta(hours=radar.freshness_hours)
            unique = [item for item in unique if item.published_at is None or _aware(item.published_at) >= cutoff]
            fresh = [item for item in unique if not self.repository.has_raw(radar.id, item.url)]
            known = len(unique) - len(fresh)
            created = []
            for item in fresh:
                analysis = await analyze_raw_item(item, [skill.name for skill in profile.skills])
                if analysis.is_opportunity:
                    score = calculate_score(analysis, radar.minimum_budget)
                    hourly = round(analysis.budget_min / analysis.estimated_hours), round(analysis.budget_max / analysis.estimated_hours)
                    opportunity = OpportunityRead(id=str(uuid4()), radar_id=radar.id, type=analysis.type, title=analysis.title, summary=analysis.summary, source=item.source, source_url=item.url, published_at=item.published_at, location=analysis.location, work_mode=analysis.work_mode, budget_min=analysis.budget_min, budget_max=analysis.budget_max, estimated_hours=analysis.estimated_hours, estimated_hourly_rate=hourly, match_score=analysis.skill_match, opportunity_score=score.opportunity_score, conversion_probability=analysis.conversion_probability, risk_score=analysis.risk, recommendation=score.recommendation, status="new", skills=analysis.skills, reasons=analysis.reasons, warnings=analysis.warnings)
                    self.repository.add_opportunity(opportunity, user_id=user_id)
                    created.append(opportunity)
                self.repository.mark_raw(radar.id, item.url, item)
            stats = RadarRunStats(queries=len(queries), items_found=len(raw), duplicates_removed=removed + known, analyzed=len(fresh), opportunities_found=len(created), matched=len([x for x in created if x.match_score >= 75]), recommended=len([x for x in created if x.recommendation == "强烈推荐"]))
            finished_at = datetime.now(UTC)
            error_code = "COLLECTORS_FAILED" if collector_errors and not raw else None
            error_message = "; ".join(error["message"] for error in collector_errors)[:500] if collector_errors else None
            run = run.model_copy(update={"status": "completed", "stats": stats, "error_code": error_code, "error_message": error_message, "collector_errors": collector_errors})
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


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)
