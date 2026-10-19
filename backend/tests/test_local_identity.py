"""身份设定：持久化、作为抓单默认值真实参与后端筛选，且不破坏旧雷达。"""
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_repository
from app.api.local import router as local_router
from app.api.radars import router as radars_router
from app.core.errors import AppError, app_error_handler
from app.core.security import CurrentUser
from app.repositories.memory import MemoryRepository

USER = "11111111-1111-4111-8111-111111111111"

IDENTITY = {
    "businesses": [
        {"id": "video", "name": "AI 电商视频 / 广告", "remote_deliverable": True},
        {"id": "web", "name": "小程序 / 网站轻开发", "remote_deliverable": False},
    ],
    "target_roles": ["电商商家", "品牌方", "代运营工作室", "独立卖家"],
    "service_mode": "regions",
    "regions": ["深圳"],
    "default_freshness_hours": 168,
    "preferred_sources": ["xiaohongshu", "douyin"],
    "buyer_keywords": ["找人做视频", "求视频制作", "视频外包"],
    "exclude_words": ["教程", "招聘", "承接"],
    "business_match_words": ["视频", "信息流"],
    "quote_style": "先确认需求量与交期，再给区间报价。",
}


def api_client(repo, uid=USER):
    api = FastAPI()
    api.include_router(local_router)
    api.include_router(radars_router)
    api.add_exception_handler(AppError, app_error_handler)
    api.dependency_overrides[get_current_user] = lambda: CurrentUser(id=uid)
    api.dependency_overrides[get_repository] = lambda: repo
    return TestClient(api)


def lead_payload(**overrides):
    payload = {
        "name": "身份默认值测试",
        "goal": "寻找需要视频制作的买方公开需求",
        "mode": "general",
        "minimum_budget": 0,
        "keywords": [],
        "sources": ["xiaohongshu"],
        "locations": [],
        "listener_description": "",
        "freshness_hours": 168,
        "frequency": "manual",
        "local_schedule_enabled": False,
        "source_config": {"lead_hunt": "true"},
        "collection_policy": {"required_terms": [], "excluded_terms": [], "match_mode": "any", "time_basis": "published", "include_unknown_dates": False, "sort": "latest", "activity_filter": "any", "min_interactions": 0},
    }
    payload.update(overrides)
    return payload


def test_identity_roundtrip_and_presets():
    repo = MemoryRepository()
    client = api_client(repo)
    empty = client.get("/api/local/identity")
    assert empty.status_code == 200
    assert empty.json()["identity"] is None
    presets = empty.json()["presets"]
    assert {item["id"] for item in presets["businesses"]} >= {"video", "drama", "web", "office", "workflow"}
    assert "电商商家" in presets["roles"]
    saved = client.put("/api/local/identity", json=IDENTITY)
    assert saved.status_code == 200
    assert saved.json()["identity"] == IDENTITY
    assert client.get("/api/local/identity").json()["identity"] == IDENTITY


@pytest.mark.parametrize("change", [
    {"target_roles": ["x" * 21]},
    {"target_roles": ["角色"] * 11},
    {"regions": []},  # service_mode=regions 时必须给出地区
    {"regions": ["深圳"] * 11},
    {"businesses": [{"id": f"b{i}", "name": "业务", "remote_deliverable": True} for i in range(11)]},
    {"preferred_sources": ["not_a_source"]},
    {"buyer_keywords": ["x" * 101]},
    {"exclude_words": ["词"] * 21},
    {"business_match_words": ["词"] + ["x" * 101]},
    {"quote_style": "长" * 501},
    {"age": 30},  # 敏感属性不属于身份画像
    {"monthly_income_goal": 100000},
])
def test_identity_out_of_bounds_rejected(change):
    client = api_client(MemoryRepository())
    response = client.put("/api/local/identity", json={**IDENTITY, **change})
    assert response.status_code == 422, response.text


def test_radar_create_gets_identity_hunt_defaults():
    repo = MemoryRepository()
    client = api_client(repo)
    assert client.put("/api/local/identity", json=IDENTITY).status_code == 200
    created = client.post("/api/radars", json=lead_payload())
    assert created.status_code == 201, created.text
    radar = client.get(f"/api/radars/{created.json()['id']}").json()
    assert radar["keywords"] == ["找人做视频", "求视频制作", "视频外包"]
    assert radar["collection_policy"]["required_terms"] == ["视频", "信息流"]
    assert radar["collection_policy"]["excluded_terms"] == ["教程", "招聘", "承接"]
    conditions = json.loads(radar["source_config"]["hunt_conditions"])
    assert conditions["roles"] == ["电商商家", "品牌方", "代运营工作室"]  # 自定义角色不入枚举
    assert conditions["regions"] == ["深圳"]
    assert conditions["match_mode"] == "local"  # 存在不可远程交付的业务


def test_keyword_fill_respects_six_request_budget():
    repo = MemoryRepository()
    client = api_client(repo)
    client.put("/api/local/identity", json=IDENTITY)
    created = client.post("/api/radars", json=lead_payload(sources=["xiaohongshu", "douyin", "weibo"]))
    radar = client.get(f"/api/radars/{created.json()['id']}").json()
    assert len(radar["keywords"]) == 2  # 3 平台 × 2 关键词 ≤ 6 次首屏请求
    assert len(radar["keywords"]) * len(radar["sources"]) <= 6


def test_explicit_user_values_are_never_overwritten():
    repo = MemoryRepository()
    client = api_client(repo)
    client.put("/api/local/identity", json=IDENTITY)
    payload = lead_payload(
        keywords=["自定义词"],
        source_config={"lead_hunt": "true", "hunt_conditions": json.dumps({"regions": ["北京"], "roles": ["创业者"], "intents": ["长期合作"], "match_mode": "keep_unknown"})},
        collection_policy={"required_terms": ["自定义业务词"], "excluded_terms": ["招生"], "match_mode": "any", "time_basis": "published", "include_unknown_dates": False, "sort": "latest", "activity_filter": "any", "min_interactions": 0},
    )
    created = client.post("/api/radars", json=payload)
    assert created.status_code == 201, created.text
    radar = client.get(f"/api/radars/{created.json()['id']}").json()
    assert radar["keywords"] == ["自定义词"]
    assert radar["collection_policy"]["required_terms"] == ["自定义业务词"]
    assert radar["collection_policy"]["excluded_terms"] == ["招生", "教程", "招聘", "承接"]  # 排除词并集，保留用户词
    conditions = json.loads(radar["source_config"]["hunt_conditions"])
    assert conditions["roles"] == ["创业者"]
    assert conditions["regions"] == ["北京"]
    assert conditions["match_mode"] == "keep_unknown"
    assert conditions["intents"] == ["长期合作"]


def test_without_identity_or_for_non_hunt_radars_nothing_changes():
    repo = MemoryRepository()
    client = api_client(repo)
    created = client.post("/api/radars", json=lead_payload())
    radar = client.get(f"/api/radars/{created.json()['id']}").json()
    assert radar["keywords"] == [] and "hunt_conditions" not in radar["source_config"]
    client.put("/api/local/identity", json=IDENTITY)
    regular = client.post("/api/radars", json={"name": "原有雷达", "goal": "寻找公开外包需求线索", "mode": "acquisition", "keywords": ["PPT"], "sources": ["hackernews"]})
    assert regular.status_code == 201, regular.text
    readback = client.get(f"/api/radars/{regular.json()['id']}").json()
    assert readback["collection_policy"]["excluded_terms"] == []
    assert readback["collection_policy"]["required_terms"] == []


def test_old_radars_are_not_recomputed_when_identity_is_saved():
    repo = MemoryRepository()
    client = api_client(repo)
    created = client.post("/api/radars", json=lead_payload(keywords=["找视频制作"]))
    before = client.get(f"/api/radars/{created.json()['id']}").json()
    assert client.put("/api/local/identity", json=IDENTITY).status_code == 200
    after = client.get(f"/api/radars/{created.json()['id']}").json()
    assert after == before


def test_edit_fills_only_empty_role_fields():
    repo = MemoryRepository()
    client = api_client(repo)
    client.put("/api/local/identity", json=IDENTITY)
    created = client.post("/api/radars", json=lead_payload(keywords=["找人做视频"])).json()
    updated = client.put(f"/api/radars/{created['id']}", json=lead_payload(
        keywords=["找人做视频"],
        source_config={"lead_hunt": "true", "hunt_conditions": json.dumps({"regions": ["深圳"], "roles": [], "intents": [], "match_mode": "local"})},
    ))
    assert updated.status_code == 200, updated.text
    conditions = json.loads(updated.json()["source_config"]["hunt_conditions"])
    assert conditions["roles"] == ["电商商家", "品牌方", "代运营工作室"]
    assert conditions["match_mode"] == "local"


def test_excluded_terms_participate_in_hunt_collection_filter():
    """排除词进入 collection_policy 后由现有 filter_page 真实过滤，不新增旁路。"""
    from datetime import UTC, datetime
    from app.schemas.collection import CollectionPolicy
    from app.schemas.domain import RadarCreate, RawItem
    from app.services.collection_filter import filter_page
    from app.services.hunt_conditions import assess_hunt

    now = datetime.now(UTC)
    item = RawItem(external_id="1", title="视频制作招聘", content="招聘视频制作人员，欢迎承接各种视频", source="xiaohongshu", url="https://example.org/1", published_at=now)
    excluded = CollectionPolicy(required_terms=["视频"], excluded_terms=["招聘", "承接"], time_basis="published", include_unknown_dates=False)
    kept, counts = filter_page([item], excluded, freshness_hours=168, now=now)
    assert kept == [] and counts["terms"] == 1
    allowed = CollectionPolicy(required_terms=["视频"], excluded_terms=[], time_basis="published", include_unknown_dates=False)
    kept2, counts2 = filter_page([item], allowed, freshness_hours=168, now=now)
    assert len(kept2) == 1 and counts2["terms"] == 0
    radar = RadarCreate(name="排除词测试", goal="寻找视频制作买方公开需求", mode="general", sources=["xiaohongshu"], keywords=["找人做视频"],
                        source_config={"lead_hunt": "true", "hunt_conditions": json.dumps({"regions": [], "roles": [], "intents": [], "match_mode": "remote"})},
                        collection_policy=allowed)
    assert assess_hunt(kept2[0], radar, now=now)["status"] in {"pending", "mismatch", "strict"}
