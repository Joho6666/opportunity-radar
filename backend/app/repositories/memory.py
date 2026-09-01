from collections import defaultdict
from datetime import date, datetime
from uuid import uuid4
from ..core.errors import AppError
from ..schemas.domain import DailyBriefRead, OpportunityAction, OpportunityRead, PreferenceState, ProfileRead, ProfileUpsert, RadarCreate, RadarRead, RadarRunRead, RadarRunStats, RawItem
from ..services.dedup_service import hash_url
from ..services.income import potential_income_range


class MemoryRepository:
    """In-memory store mirroring the Supabase schema constraints.

    Raw item URLs are tracked per radar by url_hash so repeated runs stay
    deduplicated, matching unique(radar_id, url_hash) in the SQL schema.
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
        del self.radars[radar_id]

    def has_raw(self, radar_id: str, url: str) -> bool:
        return hash_url(url) in self._raw_urls[radar_id]

    def mark_raw(self, radar_id: str, url: str, item: RawItem | None = None) -> None:
        self._raw_urls[radar_id].add(hash_url(url))
        if item is not None:
            self._raw_urls[radar_id].add(hash_url(item.url))

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
        return DailyBriefRead(
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

    def list_due_radars(self, now: datetime) -> list[tuple[str, str]]:
        running = {run.radar_id for run in self.runs.values() if run.status in {"queued", "running"}}
        due: list[tuple[str, str]] = []
        for radar in self.radars.values():
            if radar.status != "active" or radar.id in running:
                continue
            if radar.next_run_at is None or radar.next_run_at <= now:
                due.append((radar.user_id, radar.id))
        return due

    def record_llm_call(self, user_id: str | None, radar_id: str | None, run_id: str | None, provider: str | None, model: str, latency_ms: int, fallbacked: bool, schema_name: str) -> None:
        self.llm_calls.append({"user_id": user_id, "radar_id": radar_id, "run_id": run_id, "provider": provider, "model": model, "latency_ms": latency_ms, "fallbacked": fallbacked, "schema_name": schema_name})

    def get_preference(self, user_id: str) -> PreferenceState:
        return self.preferences.get(user_id, PreferenceState()).model_copy(deep=True)

    def save_preference(self, user_id: str, state: PreferenceState) -> PreferenceState:
        self.preferences[user_id] = state.model_copy(deep=True)
        return self.preferences[user_id]

    def record_event(self, user_id: str, opportunity_id: str | None, event: str, metadata: dict | None = None) -> None:
        self.events.append({"user_id": user_id, "opportunity_id": opportunity_id, "event": event, "metadata": metadata or {}})


repository = MemoryRepository()
