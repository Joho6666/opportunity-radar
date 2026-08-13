from collections import defaultdict
from datetime import UTC, datetime, date
from uuid import uuid4
from ..core.errors import AppError
from ..schemas.domain import DailyBriefRead, OpportunityRead, ProfileRead, ProfileUpsert, RadarCreate, RadarRead, RadarRunRead, RadarRunStats


class MemoryRepository:
    def __init__(self) -> None:
        self.profiles: dict[str, ProfileRead] = {}
        self.radars: dict[str, RadarRead] = {}
        self.opportunities: dict[str, OpportunityRead] = {}
        self.runs: dict[str, RadarRunRead] = {}

    def get_profile(self, user_id: str) -> ProfileRead:
        if user_id not in self.profiles:
            self.profiles[user_id] = ProfileRead(id=str(uuid4()), user_id=user_id, display_name="新用户", identity="", location="", monthly_income_goal=0, minimum_project_budget=0, available_hours_per_day=0, skills=[], goals=[])
        return self.profiles[user_id]

    def save_profile(self, user_id: str, value: ProfileUpsert) -> ProfileRead:
        profile = ProfileRead(id=self.get_profile(user_id).id, user_id=user_id, **value.model_dump())
        self.profiles[user_id] = profile; return profile

    def list_radars(self, user_id: str) -> list[RadarRead]: return [item for item in self.radars.values() if item.user_id == user_id]
    def get_radar(self, user_id: str, radar_id: str) -> RadarRead:
        item = self.radars.get(radar_id)
        if not item or item.user_id != user_id: raise AppError("RADAR_NOT_FOUND", "未找到该机会雷达。", 404)
        return item
    def create_radar(self, user_id: str, value: RadarCreate) -> RadarRead:
        item = RadarRead(id=str(uuid4()), user_id=user_id, status="active", **value.model_dump())
        self.radars[item.id] = item; return item
    def save_radar(self, item: RadarRead) -> RadarRead: self.radars[item.id] = item; return item
    def delete_radar(self, user_id: str, radar_id: str) -> None: self.get_radar(user_id, radar_id); del self.radars[radar_id]
    def create_run(self, radar_id: str) -> RadarRunRead:
        run = RadarRunRead(id=str(uuid4()), radar_id=radar_id, status="queued", stats=RadarRunStats())
        self.runs[run.id] = run; return run
    def save_run(self, run: RadarRunRead) -> RadarRunRead: self.runs[run.id] = run; return run
    def get_run(self, user_id: str, run_id: str) -> RadarRunRead:
        run = self.runs.get(run_id)
        if not run: raise AppError("RUN_NOT_FOUND", "未找到该运行记录。", 404)
        self.get_radar(user_id, run.radar_id); return run
    def add_opportunity(self, item: OpportunityRead) -> OpportunityRead: self.opportunities[item.id] = item; return item
    def list_opportunities(self, user_id: str) -> list[OpportunityRead]:
        ids = {r.id for r in self.list_radars(user_id)}; return [o for o in self.opportunities.values() if o.radar_id in ids]
    def get_opportunity(self, user_id: str, opportunity_id: str) -> OpportunityRead:
        item = self.opportunities.get(opportunity_id)
        if not item or item.radar_id not in {r.id for r in self.list_radars(user_id)}: raise AppError("OPPORTUNITY_NOT_FOUND", "未找到该机会。", 404)
        return item
    def save_opportunity(self, item: OpportunityRead) -> OpportunityRead: self.opportunities[item.id] = item; return item
    def daily_brief(self, user_id: str) -> DailyBriefRead:
        items = self.list_opportunities(user_id); recommended = [i for i in items if i.recommendation == "强烈推荐"]
        budgets = [i.budget_max for i in items if i.status not in {"ignored", "lost"}]
        return DailyBriefRead(date=date.today(), scanned_count=len(items) * 4, opportunities_count=len(items), recommended_count=len(recommended), potential_income_min=sum(i.budget_min for i in recommended), potential_income_max=sum(i.budget_max for i in recommended), summary="AI 已按匹配度、收益与风险为你整理今日机会。", signals=["AI 自动化需求上升", "远程机会持续增加"], avoid=["需求范围模糊且预算偏低的项目"], actions=[f"优先联系：{i.title}" for i in recommended[:3]])


repository = MemoryRepository()
