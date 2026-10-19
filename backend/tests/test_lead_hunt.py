"""Offline lead-hunt contracts: no paid requests, no private config."""
import asyncio
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import pytest
from app.collectors import tikhub_cn
from app.collectors.registry import CollectorRegistry
from app.core.config import Settings
from app.repositories.memory import MemoryRepository
from app.schemas.domain import RadarCreate, RawItem
from app.services.radar_run_service import RadarRunService


@pytest.mark.parametrize("hours,xhs,douyin", [(24,"一天内","3"),(168,"一周内","7"),(720,"半年内","30")])
def test_provider_window_contract(monkeypatch, hours, xhs, douyin):
    calls = []
    async def get(url, **kwargs):
        calls.append((urlsplit(url).path, {k:v[0] for k,v in parse_qs(urlsplit(url).query, keep_blank_values=True).items()}))
        return {"code":200,"data":{"data":{"items":[]}}}
    async def post(url, args, **kwargs):
        calls.append((urlsplit(url).path, args))
        return {"code":200,"data":{"data":[]}}
    monkeypatch.setattr(tikhub_cn, "get_settings", lambda: Settings(tikhub_api_key="offline-fixture"))
    monkeypatch.setattr(tikhub_cn.fetcher,"get_json",get)
    monkeypatch.setattr(tikhub_cn.fetcher,"post_json",post)
    async def run():
        registry = CollectorRegistry([tikhub_cn.XiaohongshuCollector(), tikhub_cn.DouyinCollector()])
        for source in ["xiaohongshu","douyin"]:
            items,error = await registry.search(source,"找人做电商视频",source_config={"freshness_hours":str(hours)})
            assert not error and items == []
    asyncio.run(run())
    assert calls[0][0] == "/api/v1/xiaohongshu/app_v2/search_notes"
    assert calls[0][1] == {"keyword":"找人做电商视频","page":"1","sort_type":"time_descending","time_filter":xhs,"note_type":"不限","search_id":"","search_session_id":"","source":"explore_feed","ai_mode":"0"}
    assert calls[1][0] == "/api/v1/douyin/search/fetch_video_search_v3"
    assert calls[1][1] == {"query":"找人做电商视频","date_type":douyin,"label_type":0,"duration_type":0}


def test_saved_hunt_passes_config_and_filters_real_publish_time_and_business():
    repo = MemoryRepository()
    uid = "11111111-1111-4111-8111-111111111111"
    radar = repo.create_radar(uid, RadarCreate(name="电商视频抓单",goal="电商视频服务",mode="general",sources=["xiaohongshu"],keywords=["找人做视频"],frequency="manual",freshness_hours=24,source_config={"lead_hunt":"true","freshness_hours":"24"},collection_policy={"required_terms":["电商","商品"],"time_basis":"published","include_unknown_dates":False}))
    calls=[]
    now=datetime.now(UTC)
    class Collector:
        async def search(self, source, query, **kwargs):
            calls.append((source,query,kwargs))
            return [RawItem(external_id=str(i),title=title,content=title,url=f"https://example.org/{i}",source="xiaohongshu",published_at=when) for i,(title,when) in enumerate([
                ("急需找人做电商商品视频，预算一千元",now),
                ("找人做电商视频，预算两千元",now-timedelta(days=2)),
                ("找人做电商视频，但是没有时间",None),
                ("找人开发网站，预算一千元",now),
            ])],None
    result=asyncio.run(RadarRunService(repo,Collector()).run(uid,radar.id,repo.create_run(radar.id).id))
    assert result.status == "completed"
    assert calls == [("xiaohongshu","找人做视频",{"source_config":radar.source_config})]
    feed=repo.list_intelligence_feed(uid,radar_id=radar.id)
    assert len(feed)==1 and str(feed[0].url)=="https://example.org/0"
    assert feed[0].category == "buyer"
    assert result.stage_stats["collection_filtered"] == {"stale":1,"unknown_date":1,"terms":1,"activity":0}
    assert not repo.llm_calls


def test_failed_hunt_is_not_successful_empty_result():
    repo=MemoryRepository(); uid="11111111-1111-4111-8111-111111111111"
    radar=repo.create_radar(uid,RadarCreate(name="抓单",goal="视频",mode="general",sources=["douyin"],source_config={"lead_hunt":"true"}))
    class Collector:
        async def search(self,*args,**kwargs):
            return [],{"source":"douyin","error_code":"PAID_API_DISABLED","message":"付费调用关闭"}
    result=asyncio.run(RadarRunService(repo,Collector()).run(uid,radar.id,repo.create_run(radar.id).id))
    assert result.status == "failed" and result.error_code == "COLLECTORS_FAILED"


def test_per_platform_stats_and_acceptance_mark_unmet_platform_partial():
    repo = MemoryRepository(); uid = "11111111-1111-4111-8111-111111111111"
    radar = repo.create_radar(uid, RadarCreate(
        name="双平台抓单", goal="视频制作", mode="general", sources=["xiaohongshu", "douyin"],
        keywords=["家居 找视频拍摄"], freshness_hours=168,
        source_config={"lead_hunt": "true", "freshness_hours": "168"},
        collection_policy={"required_terms": ["家居"], "time_basis": "published", "include_unknown_dates": False}))
    calls = []
    now = datetime.now(UTC)

    class Collector:
        async def search(self, source, query, **kwargs):
            calls.append((source, query))
            if source == "xiaohongshu":
                return [RawItem(external_id="1", title="家居店找人做视频，预算充足", content="家居店找人做视频，预算充足",
                                url="https://example.org/xhs-home", source="xiaohongshu", published_at=now)], None
            return [], None

    result = asyncio.run(RadarRunService(repo, Collector()).run(uid, radar.id, repo.create_run(radar.id).id))
    assert calls == [("xiaohongshu", "家居 找视频拍摄"), ("douyin", "家居")]
    stats = {row["source"]: row for row in result.stage_stats["source_stats"]}
    assert stats["xiaohongshu"] == {**stats["xiaohongshu"], "requests": 1, "returned": 1, "ingested": 1, "queries": ["家居 找视频拍摄"]}
    assert stats["douyin"]["requests"] == 1 and stats["douyin"]["returned"] == 0 and stats["douyin"]["ingested"] == 0
    assert result.stage_stats["acceptance"] == {"passed": False, "selected": 2, "passed_sources": 1, "unmet_sources": ["douyin"]}
    assert result.status == "partial"
    assert "未达标平台：douyin" in result.error_message


def test_source_override_rerun_only_queries_that_platform():
    repo = MemoryRepository(); uid = "11111111-1111-4111-8111-111111111111"
    radar = repo.create_radar(uid, RadarCreate(
        name="单平台重跑", goal="视频制作", mode="general", sources=["xiaohongshu", "douyin"],
        keywords=["家居 找视频拍摄"], freshness_hours=168,
        source_config={"lead_hunt": "true", "freshness_hours": "168"},
        collection_policy={"required_terms": ["家居"], "time_basis": "published", "include_unknown_dates": False}))
    calls = []
    now = datetime.now(UTC)
    class Collector:
        async def search(self, source, query, **kwargs):
            calls.append((source, query))
            return [RawItem(external_id="1", title="家居店找人做视频", content="家居店找人做视频，预算充足",
                            url="https://example.org/retry", source=source, published_at=now)], None
    run = repo.create_run(radar.id)
    run = repo.save_run(run.model_copy(update={"stage_stats": {**run.stage_stats, "source_override": "douyin", "query_override": "找拍摄"}}))
    result = asyncio.run(RadarRunService(repo, Collector()).run(uid, radar.id, run.id))
    assert calls == [("douyin", "找拍摄")]
    assert result.status == "completed"
    assert result.stage_stats["acceptance"] == {"passed": True, "selected": 1, "passed_sources": 1, "unmet_sources": []}


def test_rerun_source_route_requires_confirmation_and_records_override(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api import radars as radars_api
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    repo = MemoryRepository(); uid = "11111111-1111-4111-8111-111111111111"
    radar = repo.create_radar(uid, RadarCreate(name="重跑", goal="视频", mode="general", sources=["douyin", "xiaohongshu"],
                                               keywords=["家居 找视频拍摄"], source_config={"lead_hunt": "true"}))
    async def noop(*args, **kwargs):
        return None
    monkeypatch.setattr(radars_api, "enqueue_radar_run", noop)
    api = FastAPI(); api.include_router(radars_api.router)
    api.dependency_overrides[get_current_user] = lambda: CurrentUser(id=uid)
    api.dependency_overrides[get_repository] = lambda: repo
    with TestClient(api) as client:
        denied = client.post(f"/api/radars/{radar.id}/rerun-source", json={"source": "douyin", "query": "找拍摄", "confirmed": False})
        assert denied.status_code == 400
        missing = client.post(f"/api/radars/{radar.id}/rerun-source", json={"source": "weibo", "query": "找拍摄", "confirmed": True})
        assert missing.status_code == 400
        accepted = client.post(f"/api/radars/{radar.id}/rerun-source", json={"source": "douyin", "query": "找拍摄", "confirmed": True})
        assert accepted.status_code == 202
        body = accepted.json()
        assert body["stage_stats"]["source_override"] == "douyin"
        assert body["stage_stats"]["query_override"] == "找拍摄"
        assert body["stage_stats"]["rerun_reason"] == "manual_short_keyword"


def test_sources_route_is_authenticated_configuration_only(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.local import router
    from app.api.deps import get_current_user
    from app.core.security import CurrentUser
    api = FastAPI()
    api.include_router(router)
    with TestClient(api, raise_server_exceptions=False) as client:
        assert client.get("/api/local/sources").status_code != 200
    api.dependency_overrides[get_current_user] = lambda: CurrentUser(id="11111111-1111-4111-8111-111111111111")
    from app.api.deps import get_repository
    from app.repositories.memory import MemoryRepository
    api.dependency_overrides[get_repository] = lambda: MemoryRepository()
    settings = Settings(_env_file=None, app_env="local", tikhub_api_key="private-offline-fixture", paid_api_enabled=False)
    monkeypatch.setattr("app.api.local.get_settings", lambda: settings)
    with TestClient(api) as client:
        response = client.get("/api/local/sources")
        assert response.status_code == 200
        by_id = {row["id"]:row for row in response.json()["items"]}
        assert {"xiaohongshu","douyin","github","hackernews","rss"} <= by_id.keys()
        assert "mock" not in by_id
        assert not by_id["xiaohongshu"]["available"] and by_id["xiaohongshu"]["status"] == "付费关闭" and by_id["xiaohongshu"]["configured"]
        assert "date_type" in by_id["douyin"]["time_policy"]  # v3 原生时间档已实测接通
        assert by_id["douyin"]["status"] == "付费关闭"
        assert "付费调用关闭" in by_id["xiaohongshu"]["detail"]
        assert "private-offline-fixture" not in response.text
        monkeypatch.setattr(settings,"tikhub_api_key","")
        unconfigured = next(item for item in client.get("/api/local/sources").json()["items"] if item["id"] == "xiaohongshu")
        assert unconfigured["status"] == "未配置"
        assert not unconfigured["configured"] and not unconfigured["paid_enabled"]


def test_radar_http_roundtrip_keeps_hunt_fields_without_network():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.radars import router
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    api=FastAPI(); api.include_router(router); repo=MemoryRepository()
    api.dependency_overrides[get_current_user]=lambda: CurrentUser(id="11111111-1111-4111-8111-111111111111")
    api.dependency_overrides[get_repository]=lambda: repo
    payload={"name":"电商视频 · 抓单","goal":"寻找需要电商视频服务的买方公开需求","mode":"general","minimum_budget":0,"frequency":"manual","local_schedule_enabled":False,"freshness_hours":720,"keywords":["找人做电商视频","求广告视频制作"],"sources":["xiaohongshu","douyin"],"source_config":{"lead_hunt":"true","business":"video","freshness_hours":"720"},"collection_policy":{"required_terms":["电商","广告"],"time_basis":"published","include_unknown_dates":False}}
    with TestClient(api) as client:
        created=client.post("/api/radars",json=payload)
        assert created.status_code==201
        saved=client.get("/api/radars/"+created.json()["id"])
        assert saved.status_code==200
        for field in ["sources","keywords","source_config","freshness_hours","mode","frequency","local_schedule_enabled"]:
            assert saved.json()[field]==payload[field]
        assert saved.json()["collection_policy"]["required_terms"]==["电商","广告"]
        assert not repo.llm_calls and not repo.runs
