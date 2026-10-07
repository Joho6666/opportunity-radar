"""P1 guardrails: budget, retention, brief history, payment aggregation, config."""

import asyncio
from datetime import UTC, datetime, timedelta

from app.core.config import Settings
from app.repositories.memory import MemoryRepository
from app.schemas.domain import ProfileUpsert, RadarCreate, RawItem
from app.services.radar_run_service import RadarRunService


class _StubProvider:
    async def structured_output_with_usage(self, prompt: str, schema_name: str, model: str | None = None):
        return {}, None


class StubRegistry:
    def __init__(self, items):
        self.items = items

    async def search(self, slug: str, query: str):
        return list(self.items), None


def _item(url: str, title: str, content: str) -> RawItem:
    return RawItem(external_id=url, title=title, content=content, url=url, source="weibo", author="u1")


PAID = ("有偿找一个会 n8n 的人搭自动化工作流，预算 2000 元")


def _repo(user_id: str = "p1-user"):
    repo = MemoryRepository()
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "n8n", "level": "strong"}], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找 AI 自动化商业机会", keywords=["AI"]))
    return repo, user_id, radar


def test_budget_exhaustion_skips_llm_without_failing_run(monkeypatch):
    repo, user_id, radar = _repo()
    monkeypatch.setattr("app.services.budget_service.get_settings", lambda: Settings(llm_daily_token_budget=15))
    import app.services.radar_run_service as rrs

    monkeypatch.setattr(rrs, "get_settings", lambda: Settings(llm_daily_token_budget=15))
    monkeypatch.setattr(rrs, "get_provider", lambda: _StubProvider())
    items = [
        _item("https://a/1", "AI 求助一", PAID),
        _item("https://b/2", "AI 求助二", "有偿找一个会 n8n 的人搭流程，预算 3000 元"),
    ]
    service = RadarRunService(repo, StubRegistry(items))
    run = asyncio.run(service.run(user_id, radar.id, repo.create_run(radar.id).id))
    assert run.status == "completed"
    stage = run.stage_stats
    # second item exceeded the tiny budget → LLM skipped (fallback path not taken either)
    assert stage["llm_budget_skipped"] >= 1
    assert stage["analyzed"] == 1  # only the first item was LLM-analyzed


def test_budget_unlimited_by_default(monkeypatch):
    repo, user_id, radar = _repo()
    items = [
        _item("https://s/1", "AI 有偿需求一", "有偿找 n8n 搭自动化工作流，预算 1000 元"),
        _item("https://s/2", "AI 有偿需求二", "有偿找人做数据处理脚本，报价 1200 元"),
        _item("https://s/3", "AI 有偿需求三", "有偿求一个网页爬虫小工具，预算 900 元"),
    ]
    run = asyncio.run(RadarRunService(repo, StubRegistry(items)).run(user_id, radar.id, repo.create_run(radar.id).id))
    assert run.stage_stats["llm_budget_skipped"] == 0
    assert run.stage_stats["analyzed"] == 3


def test_retention_cleanup_removes_expired_rows():
    repo = MemoryRepository()
    user_id, radar = "ret-user", None
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找 AI 自动化商业机会", keywords=["AI"]))
    repo.mark_raw(radar.id, "https://old/1", _item("https://old/1", "old", "old content"))
    row = repo.raw_row("https://old/1")
    row["last_seen_at"] = datetime.now() - timedelta(days=120)
    repo.mark_raw(radar.id, "https://new/2", _item("https://new/2", "new", "fresh content"))
    repo.record_llm_call(user_id, radar.id, None, None, "m", 10, True, "s")
    repo.llm_calls[0]["created_at"] = datetime.now() - timedelta(days=60)

    assert repo.cleanup_raw_items(90) == 1
    assert repo.raw_row("https://old/1") is None
    assert repo.has_raw(radar.id, "https://new/2") is True
    assert repo.cleanup_llm_calls(30) == 1
    assert repo.llm_calls == []


def test_brief_history_roundtrip():
    from datetime import date

    repo, user_id, _radar = _repo("brief-user")
    brief = repo.daily_brief(user_id)
    stored = repo.get_brief(user_id, brief.date)
    assert stored is not None
    assert stored.date == brief.date
    assert stored.brief_version == "v2"
    assert repo.get_brief(user_id, date(2020, 1, 1)) is None


def test_payment_evidence_aggregates_across_cluster(monkeypatch):
    """同簇两条付款信号 → payment 维度高于单条上限（55）。"""
    repo, user_id, radar = _repo("pay-user")
    items = [
        _item("https://a/1", "急招 AI 视频剪辑师傅", PAID),
        _item("https://b/2", "电商短视频外包需求", PAID),
    ]
    run = asyncio.run(RadarRunService(repo, StubRegistry(items)).run(user_id, radar.id, repo.create_run(radar.id).id))
    assert run.stats.opportunities_found >= 1
    opportunities = repo.list_opportunities(user_id)
    scored = [item for item in opportunities if item.money_breakdown]
    assert scored
    assert all(item.money_breakdown["payment_evidence"] > 0 for item in scored)
    best = max(item.money_breakdown["payment_evidence"] for item in scored)
    assert best > 55  # single-item cap was 55 (payment_signals=1 → 30, +25 intent bonus)


def test_listener_fields_persist_on_radar():
    repo, user_id, _radar = _repo("listener-user")
    radar = repo.create_radar(user_id, RadarCreate(
        name="L", goal="寻找短视频制作痛点的商家", keywords=["短视频"],
        listener_description="寻找正在抱怨短视频制作太慢、希望自动批量生产视频的商家",
    ))
    assert radar.listener_description
    config = radar.listener_config
    assert config is None or isinstance(config, dict)  # compiled at API layer, not in repo


def test_radar_listener_config_survives_save():
    repo, user_id, _radar = _repo("listener-save")
    radar = repo.create_radar(user_id, RadarCreate(name="L", goal="寻找 AI 自动化商业机会", keywords=["AI"]))
    radar = repo.save_radar(radar.model_copy(update={"listener_config": {"positive_signals": ["批量"], "negative_signals": [], "search_queries": [], "exclusion_rules": []}}))
    assert repo.get_radar(user_id, radar.id).listener_config["positive_signals"] == ["批量"]
