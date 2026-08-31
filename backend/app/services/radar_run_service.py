from datetime import UTC, datetime, timedelta
from uuid import uuid4
from ..collectors.mock import MockCollector
from ..repositories.base import Repository
from ..schemas.domain import OpportunityRead, RadarRunStats
from .ai_service import analyze_raw_item, plan_queries
from .dedup_service import deduplicate
from .score_engine import calculate_score


class RadarRunService:
    def __init__(self, repository: Repository) -> None: self.repository = repository; self.collector = MockCollector()
    async def run(self, user_id: str, radar_id: str, run_id: str):
        radar = self.repository.get_radar(user_id, radar_id); profile = self.repository.get_profile(user_id)
        run = self.repository.get_run(user_id, run_id).model_copy(update={"status": "running"}); self.repository.save_run(run)
        try:
            queries = radar.queries or await plan_queries(radar)
            radar = radar.model_copy(update={"queries": queries, "status": "running"}); self.repository.save_radar(radar)
            raw = [item for query in queries for item in await self.collector.search(query.query)]
            unique, removed = deduplicate(raw)
            fresh = [item for item in unique if not self.repository.has_raw(radar.id, item.url)]
            known = len(unique) - len(fresh)
            created = []
            for item in fresh:
                analysis = await analyze_raw_item(item, [skill.name for skill in profile.skills])
                if analysis.is_opportunity:
                    score = calculate_score(analysis, radar.minimum_budget)
                    hourly = round(analysis.budget_min / analysis.estimated_hours), round(analysis.budget_max / analysis.estimated_hours)
                    opportunity = OpportunityRead(id=str(uuid4()), radar_id=radar.id, type=analysis.type, title=analysis.title, summary=analysis.summary, source=item.source, source_url=item.url, published_at=item.published_at, location=analysis.location, work_mode=analysis.work_mode, budget_min=analysis.budget_min, budget_max=analysis.budget_max, estimated_hours=analysis.estimated_hours, estimated_hourly_rate=hourly, match_score=analysis.skill_match, opportunity_score=score.opportunity_score, conversion_probability=analysis.conversion_probability, risk_score=analysis.risk, recommendation=score.recommendation, status="new", skills=analysis.skills, reasons=analysis.reasons, warnings=analysis.warnings)
                    self.repository.add_opportunity(opportunity); created.append(opportunity)
                self.repository.mark_raw(radar.id, item.url)
            stats = RadarRunStats(queries=len(queries), items_found=len(raw), duplicates_removed=removed + known, analyzed=len(fresh), opportunities_found=len(created), matched=len([x for x in created if x.match_score >= 75]), recommended=len([x for x in created if x.recommendation == "强烈推荐"]))
            finished_at = datetime.now(UTC)
            next_run_at = finished_at + timedelta(days=1) if radar.frequency == "daily" else None
            run = run.model_copy(update={"status": "completed", "stats": stats}); self.repository.save_run(run)
            self.repository.save_radar(radar.model_copy(update={"status": "active", "last_run_at": finished_at, "next_run_at": next_run_at, "stats": stats})); return run
        except Exception:
            run = run.model_copy(update={"status": "failed", "error_message": "雷达执行失败，请稍后重试。"}); self.repository.save_run(run); self.repository.save_radar(radar.model_copy(update={"status": "error"})); return run
