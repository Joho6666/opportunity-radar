import asyncio
from jose import jwt
from fastapi.testclient import TestClient
from app.main import app
from app.collectors.mock import MockCollector
from app.repositories.memory import MemoryRepository
from app.schemas.domain import OpportunityAnalysis, ProfileUpsert, RadarCreate
from app.services.ai_service import analyze_raw_item, plan_queries
from app.services.dedup_service import deduplicate
from app.services.radar_run_service import RadarRunService
from app.services.risk_rules import risk_adjustment
from app.services.score_engine import calculate_score


def test_score_engine_recommendation_is_programmatic():
    analysis = OpportunityAnalysis(is_opportunity=True,type="client",title="PPT",summary="",budget_min=200,budget_max=300,estimated_hours=3,commercial_intent=95,skill_match=96,conversion_probability=82,urgency=88,competition=45,risk=18)
    result = calculate_score(analysis, 200)
    assert 0 <= result.opportunity_score <= 100
    assert result.recommendation in {"强烈推荐", "值得考虑", "一般", "不建议"}


def test_mock_collector_deduplicates_and_analyzes():
    async def scenario():
        items = await MockCollector().search("桂林 PPT 有偿")
        unique, removed = deduplicate(items + [items[0]])
        analysis = await analyze_raw_item(unique[0], ["PPT"])
        assert removed == 1
        assert analysis.is_opportunity is True
        assert analysis.title == "桂林｜急需毕业答辩 PPT"
    asyncio.run(scenario())


def test_query_planner_returns_structured_queries():
    async def scenario():
        queries = await plan_queries(RadarCreate(name="客户雷达", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"]))
        assert queries[0].priority >= 70
        assert "PPT" in queries[0].query
    asyncio.run(scenario())


def test_risk_rules_raise_known_scam_signals():
    async def scenario():
        item = (await MockCollector().search("test"))[0].model_copy(update={"content":"先交钱培训费"})
        score, warnings = risk_adjustment(item)
        assert score >= 60 and warnings
    asyncio.run(scenario())


def test_radar_run_mock_pipeline_creates_opportunities():
    async def scenario():
        repo = MemoryRepository(); user_id = "test-user"
        repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name":"PPT","level":"strong"}], goals=["client"]))
        radar = repo.create_radar(user_id, RadarCreate(name="PPT 雷达", goal="寻找桂林 PPT 有偿需求", minimum_budget=200, keywords=["PPT"], locations=["桂林"]))
        run = repo.create_run(radar.id)
        result = await RadarRunService(repo).run(user_id, radar.id, run.id)
        assert result.status == "completed"
        assert result.stats.opportunities_found > 0
        assert repo.list_opportunities(user_id)
    asyncio.run(scenario())


def test_api_radar_run_and_opportunity_action():
    token = jwt.encode({"sub": "api-test-user", "aud": "authenticated"}, "", algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        profile = client.put("/api/profile", headers=headers, json={"display_name":"测试用户","skills":[{"name":"PPT","level":"strong"}],"goals":["client"]})
        assert profile.status_code == 200
        radar = client.post("/api/radars", headers=headers, json={"name":"测试雷达","goal":"寻找桂林 PPT 兼职","keywords":["PPT"],"locations":["桂林"]}).json()
        run = client.post(f"/api/radars/{radar['id']}/run", headers=headers)
        assert run.status_code == 202
        opportunities = client.get("/api/opportunities", headers=headers).json()
        assert opportunities
        action = client.post(f"/api/opportunities/{opportunities[0]['id']}/save", headers=headers, json={})
        assert action.json()["status"] == "saved"
