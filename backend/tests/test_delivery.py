import asyncio
from jose import jwt
from fastapi.testclient import TestClient
from app.main import app
from app.repositories.memory import MemoryRepository
from app.schemas.domain import ProfileUpsert, RadarCreate
from app.services.radar_run_service import RadarRunService


def make_repo(user_id: str = "delivery-user"):
    repo = MemoryRepository()
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "PPT", "level": "strong"}], goals=["client"]))
    return repo, user_id


def run_once(repo: MemoryRepository, user_id: str, radar_id: str):
    run = repo.create_run(radar_id)
    result = asyncio.run(RadarRunService(repo).run(user_id, radar_id, run.id))
    assert result.status == "completed"
    return result


def test_reruns_do_not_duplicate_opportunities():
    repo, user_id = make_repo()
    radar = repo.create_radar(user_id, RadarCreate(name="PPT", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"]))
    run_once(repo, user_id, radar.id); first = len(repo.list_opportunities(user_id))
    second = run_once(repo, user_id, radar.id)
    assert first > 0
    assert len(repo.list_opportunities(user_id)) == first
    assert second.stats.duplicates_removed > 0
    assert second.stats.opportunities_found == 0


def test_radar_stats_and_schedule_are_updated_after_run():
    repo, user_id = make_repo()
    radar = repo.create_radar(user_id, RadarCreate(name="PPT", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"]))
    run_once(repo, user_id, radar.id)
    saved = repo.get_radar(user_id, radar.id)
    assert saved.stats.items_found > 0
    assert saved.last_run_at is not None
    assert saved.next_run_at is not None


def test_delete_radar_cleans_runs_and_opportunities():
    repo, user_id = make_repo()
    radar = repo.create_radar(user_id, RadarCreate(name="PPT", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"]))
    run_once(repo, user_id, radar.id)
    assert repo.list_opportunities(user_id)
    repo.delete_radar(user_id, radar.id)
    assert repo.list_opportunities(user_id) == []
    assert repo.runs_of_user(user_id) == []


def test_won_revenue_uses_actual_revenue_over_budget():
    repo, user_id = make_repo()
    radar = repo.create_radar(user_id, RadarCreate(name="PPT", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"], locations=["桂林"]))
    run_once(repo, user_id, radar.id)
    item = repo.list_opportunities(user_id)[0]
    repo.save_opportunity(item.model_copy(update={"status": "won"}))
    assert repo.won_revenue(user_id) == item.budget_max
    from app.schemas.domain import OpportunityAction
    repo.record_action(item.id, OpportunityAction(actual_revenue=123))
    assert repo.won_revenue(user_id) == 123


def test_api_pipeline_summary_reports_income():
    token = jwt.encode({"sub": "pipeline-user", "aud": "authenticated"}, "", algorithm="HS256")
    headers = {"Authorization": f"Bearer {token}"}
    with TestClient(app) as client:
        client.put("/api/profile", headers=headers, json={"display_name": "测试", "skills": [{"name": "PPT", "level": "strong"}], "goals": ["client"]})
        radar = client.post("/api/radars", headers=headers, json={"name": "雷达", "goal": "寻找桂林 PPT 有偿需求", "keywords": ["PPT"], "locations": ["桂林"]}).json()
        assert client.post(f"/api/radars/{radar['id']}/run", headers=headers).status_code == 202
        opportunities = client.get("/api/opportunities", headers=headers).json()
        won = client.post(f"/api/opportunities/{opportunities[0]['id']}/win", headers=headers, json={"actual_revenue": 250}).json()
        assert won["status"] == "won"
        summary = client.get("/api/pipeline/summary", headers=headers).json()
        assert summary["income"] == 250
        assert summary["counts"]["won"] == 1
        dashboard = client.get("/api/dashboard", headers=headers).json()
        assert dashboard["won_revenue"] == 250
        assert dashboard["scanned"] > 0
