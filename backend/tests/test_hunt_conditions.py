import asyncio
import json
from datetime import UTC, datetime
import pytest
from app.schemas.domain import RadarCreate, RawItem
from app.services.ai_service import plan_queries


def radar(**conditions):
    return RadarCreate(name="test", goal="电商视频", mode="general", sources=["xiaohongshu"], keywords=["找人做视频", "视频外包"], source_config={"lead_hunt":"true", "hunt_conditions":json.dumps({"regions":["深圳"], "roles":["电商商家"], "intents":["找人制作"], "match_mode":"remote", **conditions})}, collection_policy={"required_terms":["视频", "信息流", "亚马逊"], "time_basis":"published", "include_unknown_dates":False})


def test_geo_queries_keep_unqualified_control_and_request_cap():
    r=radar()
    queries=asyncio.run(plan_queries(r))
    assert queries[0].query == "找人做视频"
    assert any("深圳" in q.query for q in queries)
    assert len(queries)<=3 and len(queries)*len(r.sources)<=6


def test_douyin_gets_short_core_terms_while_other_platforms_keep_long_phrases():
    from pathlib import Path
    from app.services.hunt_conditions import shorten_douyin_keyword
    evidence = json.loads((Path(__file__).parent / "fixtures/tikhub_live/douyin_short_keyword_evidence.json").read_text())
    returned = {call["query"]: call["returned"] for call in evidence["calls"]}
    assert returned["找拍摄"] == 8 and returned["家居"] == 1000
    assert returned["家居 找视频拍摄"] == 0 and returned["圣诞 视频 制作 求推荐"] == 0
    cases = {"家居 找视频拍摄": "家居", "圣诞 视频 制作 求推荐": "圣诞", "找人做电商视频": "电商视频",
             "桂林 找人做视频": "视频", "小程序开发": "小程序", "AI视频制作": "AI视频"}
    for long, short in cases.items():
        assert shorten_douyin_keyword(long) == short
    r = radar().model_copy(update={"sources": ["douyin", "xiaohongshu"],
                                   "keywords": ["家居 找视频拍摄", "找人做电商视频"]})
    queries = asyncio.run(plan_queries(r))
    douyin = [q.query for q in queries if q.source == "douyin"]
    xhs = [q.query for q in queries if q.source == "xiaohongshu"]
    assert douyin == ["家居", "电商视频"]
    assert xhs[:2] == ["家居 找视频拍摄", "找人做电商视频"]
    assert "深圳" in xhs[2]
    assert len(queries) == 5


def test_douyin_short_terms_respect_total_request_cap():
    r = radar().model_copy(update={"sources": ["douyin", "xiaohongshu"],
                                   "keywords": ["家居 找视频拍摄", "找人做电商视频", "圣诞 视频 制作 求推荐"]})
    queries = asyncio.run(plan_queries(r))
    assert len(queries) <= 6
    assert len([q for q in queries if q.source == "douyin"]) <= 3


def test_original_evidence_unknown_role_not_guessed_from_author_or_query():
    from app.services.hunt_conditions import assess_hunt
    item=RawItem(external_id="1",title="备战黑五",content="深圳有做产品信息流拍摄的吗？公司需要外包3-400条的3-5s素材",source="xiaohongshu",url="https://example.org/1",author="电商商家",published_at=datetime.now(UTC),metadata={"query":"深圳电商商家"})
    match=assess_hunt(item,radar())
    assert match["status"]=="pending"
    assert "目标角色" in match["missing"]
    assert match["evidence"]["需求地区"] in item.content
    assert match["evidence_level"]=="搜索摘要（未核实完整正文）"


def test_overseas_country_counts_only_in_service_context_including_english_alias():
    from app.services.hunt_conditions import assess_hunt, shorten_douyin_keyword
    item = RawItem(external_id="1", title="美国站", content="我们在美国做亚马逊，找人做产品视频", source="xiaohongshu", url="https://example.org/us", published_at=datetime.now(UTC))
    match = assess_hunt(item, radar(regions=["美国"], roles=[], intents=[]))
    assert "美国" in match["evidence"]["需求地区"]
    english = item.model_copy(update={"title": "video editor", "content": "Looking for a video editor for the US market. We need a team."})
    assert "US" in assess_hunt(english, radar(regions=["美国"], roles=[], intents=[]))["evidence"]["需求地区"]
    alias = item.model_copy(update={"title": "找视频", "content": "服务地点：美国，找人做视频"})
    assert "美国" in assess_hunt(alias, radar(regions=["USA"], roles=[], intents=[]))["evidence"]["需求地区"]
    unrelated = item.model_copy(update={"title": "找视频", "content": "看到一个美国博主，另外找人做视频", "metadata": {"query": "美国"}})
    assert "需求地区" in assess_hunt(unrelated, radar(regions=["美国"], roles=[], intents=[]))["missing"]
    assert shorten_douyin_keyword("美国 找人做视频") == "视频"
    assert shorten_douyin_keyword("广东 找人做视频") == "视频"
    assert shorten_douyin_keyword("洛杉矶 找人做视频") == "视频"
    assert shorten_douyin_keyword("加利福尼亚 找人做视频") == "视频"


def test_personas_and_quote_intent_count_only_from_self_description():
    from app.services.hunt_conditions import assess_hunt
    item = RawItem(external_id="1", title="找视频", content="我是大学生，找人做毕业视频", source="xiaohongshu", url="https://example.org/student", published_at=datetime.now(UTC))
    assert "大学生" in assess_hunt(item, radar(roles=["学生"], intents=[]))["evidence"]["目标角色"]
    assert "目标角色" in assess_hunt(item.model_copy(update={"content": "招生啦，适合学生学视频", "author": "学生"}), radar(roles=["学生"], intents=[]))["missing"]
    assert "自由职业" in assess_hunt(item.model_copy(update={"content": "本人是自由职业，想找人剪一条视频"}), radar(roles=["自由职业"], intents=[]))["evidence"]["目标角色"]
    assert "自媒体" in assess_hunt(item.model_copy(update={"content": "我们是自媒体，求视频制作"}), radar(roles=["自媒体"], intents=[]))["evidence"]["目标角色"]
    assert "市场部" in assess_hunt(item.model_copy(update={"content": "我们市场部需要一条产品视频"}), radar(roles=["市场团队"], intents=[]))["evidence"]["目标角色"]
    assert "培训机构" in assess_hunt(item.model_copy(update={"content": "我们是培训机构，找人做课程视频"}), radar(roles=["培训机构"], intents=[]))["evidence"]["目标角色"]
    quoted = assess_hunt(item.model_copy(update={"content": "产品视频怎么收费"}), radar(roles=[], intents=["询价报价"]))
    assert "怎么收费" in quoted["evidence"]["需求意图"]
    assert "买方需求" in quoted["evidence"]
    seller = assess_hunt(item.model_copy(update={"content": "报价私信，欢迎咨询，我们提供视频服务"}), radar(roles=[], intents=["询价报价"]))
    assert seller["status"] == "mismatch"
    assert "需求意图" not in seller["evidence"]


def test_custom_audience_matches_only_when_they_state_it():
    from app.services.hunt_conditions import assess_hunt
    item = RawItem(external_id="1", title="找视频", content="我们是跨境卖家，找人做产品视频", source="xiaohongshu", url="https://example.org/custom", published_at=datetime.now(UTC))
    assert "跨境卖家" in assess_hunt(item, radar(roles=["跨境卖家"], intents=[]))["evidence"]["目标角色"]
    mentioned = item.model_copy(update={"content": "想找跨境卖家做视频", "author": "跨境卖家"})
    assert "目标角色" in assess_hunt(mentioned, radar(roles=["跨境卖家"], intents=[]))["missing"]


def test_remote_unknown_region_retained_and_seller_not_strict():
    from app.services.hunt_conditions import assess_hunt
    item=RawItem(external_id="1",title="找外包",content="我们是电商商家，找人做视频，可长期合作",source="xiaohongshu",url="https://example.org/1",published_at=datetime.now(UTC))
    assert assess_hunt(item,radar())["status"]=="pending"
    assert "需求地区" in assess_hunt(item,radar())["missing"]
    seller=item.model_copy(update={"content":"深圳电商商家视频制作接单，欢迎咨询，我们提供视频服务"})
    assert assess_hunt(seller,radar())["status"]=="mismatch"


def test_custom_window_and_unknown_time_never_strict():
    from app.services.hunt_conditions import assess_hunt
    r=radar(start_at="2026-10-01T00:00:00Z",end_at="2026-10-02T00:00:00Z")
    item=RawItem(external_id="1",title="找视频",content="我们是深圳电商商家，找人做视频",source="xiaohongshu",url="https://example.org/1",published_at=datetime(2026,10,1,12,tzinfo=UTC),metadata={"content_kind":"post_detail"})
    assert assess_hunt(item,r)["status"]=="strict"
    assert assess_hunt(item.model_copy(update={"published_at":None}),r)["status"]=="pending"
    assert assess_hunt(item.model_copy(update={"published_at":datetime(2026,10,3,tzinfo=UTC)}),r)["status"]=="mismatch"


@pytest.mark.parametrize("change", [{"roles":["人"]},{"regions":["a"]*11},{"start_at":"2026-10-02T00:00:00Z","end_at":"2026-10-01T00:00:00Z"},{"match_mode":"bogus"}])
def test_json_conditions_validate_at_api_boundary(change):
    with pytest.raises(ValueError):
        radar(**change)


def exercise_saved_worker(repo):
    from datetime import timedelta
    from uuid import uuid4
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.api.radars import router
    from app.api.deps import get_current_user, get_repository
    from app.core.security import CurrentUser
    from app.services.radar_run_service import RadarRunService
    uid=str(uuid4()); api=FastAPI(); api.include_router(router)
    api.dependency_overrides[get_current_user]=lambda: CurrentUser(id=uid)
    api.dependency_overrides[get_repository]=lambda: repo
    payload=radar().model_dump(mode="json")
    with TestClient(api) as client:
        created=client.post("/api/radars",json=payload)
        assert created.status_code==201, created.text
        rid=created.json()["id"]
        changed={**payload,"freshness_hours":72,"source_config":{**payload["source_config"],"hunt_conditions":radar(match_mode="local").source_config["hunt_conditions"]}}
        assert client.put(f"/api/radars/{rid}",json=changed).status_code==200
        saved=client.get(f"/api/radars/{rid}").json()
        assert saved["source_config"]==changed["source_config"] and saved["freshness_hours"]==72
        assert client.post("/api/radars",json={**changed,"keywords":["a","b","c","d"]}).status_code==422
        assert client.post("/api/radars",json={**changed,"keywords":["a","b","c"],"sources":["xiaohongshu","douyin","weibo"]}).status_code==422
        now=datetime.now(UTC)
        bodies=["我们是深圳电商商家，找人做视频，预算待定", "深圳有做视频的吗？需要外包素材", "深圳电商视频制作接单，欢迎咨询，我们提供视频服务", "有没有专注做亚马逊AI视频生成的公司，专注亚马逊的外包公司可以联系我。可长期合作，可远程合作"]
        items=[RawItem(external_id=str(i),title=f"视频测试{i}",content=body,url=f"https://example.org/{uid}/{i}",source="xiaohongshu",published_at=now,metadata={"content_kind":"post_detail"}) for i,body in enumerate(bodies)]
        items += [items[0].model_copy(update={"url":f"https://example.org/{uid}/old","external_id":"old","title":"历史老项目","content":"求团队制作园林景区航拍视频，每年秋天都要安排无人机拍摄", "published_at":now-timedelta(days=10),"metadata":{"comment_published_at":now.isoformat()}}),items[0].model_copy(update={"url":f"https://example.org/{uid}/unknown","external_id":"unknown","title":"发布时间未知","content":"请教直播间引流视频推广转化方案，有没有靠谱公司接这些活？", "published_at":None})]
        calls=[]
        class Collector:
            async def search(self,source,query,**kwargs):
                calls.append(query)
                return items,None
        result=asyncio.run(RadarRunService(repo,Collector()).run(uid,rid,repo.create_run(rid).id))
        assert result.status=="completed", result
        assert calls==[q.query for q in asyncio.run(plan_queries(repo.get_radar(uid,rid)))]
        feed=repo.list_intelligence_feed(uid,radar_id=rid)
        matches={str(record.url).rsplit("/",1)[-1]:record.intelligence_ranking["hunt_match"] for record in feed}
        assert len(matches)==4
        assert matches["0"]["status"]=="strict"
        assert matches["1"]["status"]=="pending" and "目标角色" in matches["1"]["missing"]
        assert matches["2"]["status"]=="mismatch"
        assert matches["3"]["status"]=="mismatch"
        assert result.stage_stats["collection_filtered"]["unknown_date"]==1
        assert result.stage_stats["collection_filtered"]["stale"]==1
        remote=radar(match_mode="remote").source_config["hunt_conditions"]
        client.put(f"/api/radars/{rid}",json={**changed,"source_config":{**changed["source_config"],"hunt_conditions":remote}})
        assert client.get(f"/api/radars/{rid}").json()["queries"]==[]
        result=asyncio.run(RadarRunService(repo,Collector()).run(uid,rid,repo.create_run(rid).id))
        assert result.status=="completed"
        remote_feed=repo.list_intelligence_feed(uid,radar_id=rid)
        item=next(r for r in remote_feed if str(r.url).endswith("/3"))
        assert item.intelligence_ranking["hunt_match"]["status"]=="pending"
        # Historical custom windows use original UTC dates, not the 30d preset
        # nor fresh comment timestamps; a one-hour widening must not leak rows.
        start=now-timedelta(days=11)
        end=now-timedelta(days=9)
        custom=radar(start_at=start.isoformat(),end_at=end.isoformat()).model_dump(mode="json")
        custom["freshness_hours"]=24
        custom_id=client.post("/api/radars",json=custom).json()["id"]
        result=asyncio.run(RadarRunService(repo,Collector()).run(uid,custom_id,repo.create_run(custom_id).id))
        assert result.status=="completed"
        custom_feed=repo.list_intelligence_feed(uid,radar_id=custom_id)
        assert len(custom_feed)==1 and str(custom_feed[0].url).endswith("/old"), str(result.stage_stats) + str(result.stats)


def test_api_save_edit_read_worker_classification_roundtrip():
    from app.repositories.memory import MemoryRepository
    exercise_saved_worker(MemoryRepository())


def test_postgres_controls_and_match_evidence_roundtrip_with_rollback():
    """All rows are isolated inside a rolled-back outer transaction, not real user data."""
    from contextlib import nullcontext
    from app.core.config import get_settings
    from app.database.client import create_database_engine
    from app.repositories.postgres import PostgresRepository
    if not get_settings().database_url:
        pytest.skip("PostgreSQL not configured")
    engine=create_database_engine()
    with engine.connect() as conn:
        transaction=conn.begin()
        try:
            repo=PostgresRepository(engine)
            repo._conn=lambda: nullcontext(conn)
            exercise_saved_worker(repo)
        finally:
            transaction.rollback()
    engine.dispose()
