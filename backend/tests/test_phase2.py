"""Phase 2: listener gates, LLM signal extraction, pain points, cluster merge."""

import asyncio
from datetime import UTC, datetime

from app.core.config import Settings
from app.repositories.memory import MemoryRepository
from app.schemas.domain import ProfileUpsert, RadarCreate, RawItem
from app.schemas.intelligence import EventClusterRead, SignalRead
from app.services.ai_service import compile_listener_llm, extract_signals_llm
from app.services.clustering_service import ClusterState, assign_to_cluster
from app.services.cluster_maintenance import merge_similar_clusters
from app.services.listener_service import listener_matches, listener_boost, rule_compile
from app.services.pain_point_service import rebuild_for_radar
from app.services.radar_run_service import RadarRunService


def _item(url: str, title: str, content: str, author: str = "u1") -> RawItem:
    return RawItem(external_id=url, title=title, content=content, url=url, source="weibo", author=author)


class AsyncStubRegistry:
    def __init__(self, items):
        self.items = items

    async def search(self, slug: str, query: str):
        return list(self.items), None


def test_rule_compile_splits_positive_and_negative():
    config = rule_compile("寻找抱怨短视频制作太慢的商家，不要学生，排除接单中介")
    assert config.positive_signals
    assert any("学生" in term or "中介" in term for term in config.negative_signals)
    assert config.search_queries


def test_listener_negative_only_item_is_gated():
    config = rule_compile("寻找抱怨制作太慢的商家，不要学生")
    gated, hits = listener_matches("我是学生想学短视频", config)
    assert gated is False and hits == 0
    passes, hits = listener_matches("商家抱怨制作太慢，想批量生产", config)
    assert passes is True and hits > 0
    nomatch = listener_matches("今天天气不错", config)
    assert nomatch == (False, 0)  # no positive hit → not for this radar
    always = listener_matches("anything", None)
    assert always == (True, 0)


def test_listener_boost_capped():
    assert listener_boost(0) == 0
    assert listener_boost(1) == 5
    assert listener_boost(10) == 10


def test_compile_listener_llm_none_without_provider(monkeypatch):
    import app.services.ai_service as ai

    monkeypatch.setattr(ai, "get_provider", lambda: None)
    assert asyncio.run(compile_listener_llm("寻找有偿自动化需求的商家")) is None


class RecordingProvider:
    """Captures the model argument to prove fast-model routing."""

    def __init__(self, payload: dict):
        self.payload = payload
        self.used_model: str | None = None

    async def structured_output_with_usage(self, prompt: str, schema_name: str, model: str | None = None):
        self.used_model = model
        return self.payload, {"prompt_tokens": 10, "completion_tokens": 5}


async def _extract_with(provider) -> list | None:
    import app.services.ai_service as ai

    original = ai.get_provider
    ai.get_provider = lambda: provider
    try:
        return await extract_signals_llm("很多商家抱怨 AI 视频人物不一致，有偿求解决办法，预算 500 元")
    finally:
        ai.get_provider = original


def test_extract_signals_llm_routes_fast_model_and_validates(monkeypatch):
    payload = {"signals": [
        {"signal_type": "pain_point", "title": "人物不一致", "keywords": ["AI 视频"], "commercial_intent": 80, "payment_evidence": True, "urgency": 70, "confidence": 90},
        {"signal_type": "NOT_A_TYPE", "title": "bad"},
    ]}
    provider = RecordingProvider(payload)
    monkeypatch.setattr("app.services.ai_service.get_settings", lambda: Settings(llm_fast_model="fast-mini"))
    signals = asyncio.run(_extract_with(provider))
    assert provider.used_model == "fast-mini"
    assert signals is not None
    assert len(signals) == 1  # invalid type dropped
    assert signals[0].signal_type == "pain_point"
    assert signals[0].extraction_method == "llm"


def test_cluster_level_llm_signal_persisted_in_run(monkeypatch):
    repo = MemoryRepository()
    user_id = "sig-user"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "n8n", "level": "strong"}], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找 AI 自动化商业机会", keywords=["AI"]))
    items = [
        _item("https://a/1", "急招 AI 视频剪辑师傅", "人物不一致翻车，有偿求解决，预算 500 元"),
        _item("https://b/2", "电商短视频外包需求", "人物不一致翻车，有偿求解决，预算 600 元", author="u2"),
    ]
    payload = {"signals": [{"signal_type": "complaint", "title": "人物不一致", "keywords": ["AI 视频"], "commercial_intent": 70, "payment_evidence": True, "urgency": 80, "confidence": 88}]}
    provider = RecordingProvider(payload)
    monkeypatch.setattr("app.services.radar_run_service.get_provider", lambda: provider)
    monkeypatch.setattr("app.services.ai_service.get_provider", lambda: provider)
    monkeypatch.setattr("app.services.ai_service.get_settings", lambda: Settings(llm_fast_model="fast-mini"))
    run = asyncio.run(RadarRunService(repo, AsyncStubRegistry(items)).run(user_id, radar.id, repo.create_run(radar.id).id))
    assert run.status == "completed"
    stage = run.stage_stats
    assert stage["llm_signals_extracted"] >= 1
    llm_signals = [signal for signal in repo.signals if signal.extraction_method == "llm"]
    assert llm_signals and llm_signals[0].cluster_id is not None


async def _rebuild(repo, user_id, radar_id, signals, themes):
    return await rebuild_for_radar(repo, user_id, radar_id, signals, themes)


def test_pain_point_aggregation_metrics():
    repo = MemoryRepository()
    user_id = "pain-user"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找 AI 商业机会信号", keywords=["AI"]))
    signals = [
        SignalRead(id="s1", signal_type="pain_point", title="Agent 部署太难", keywords=["agent"], entities=["u1"], urgency=80, payment_evidence=True, commercial_intent=60, cluster_id="c1"),
        SignalRead(id="s2", signal_type="complaint", title="部署又失败了", keywords=["agent"], entities=["u2"], urgency=60, cluster_id="c1"),
    ]
    saved = asyncio.run(_rebuild(repo, user_id, radar.id, signals, {"c1": "Agent 部署困难"}))
    assert len(saved) == 1
    pain = saved[0]
    assert pain.theme == "Agent 部署困难"
    assert pain.mention_count == 2
    assert pain.unique_user_count == 2
    assert pain.payment_intent > 0
    assert pain.severity >= 40
    # growth on rebuild with higher count
    more = signals + [SignalRead(id="s3", signal_type="pain_point", title="还是难", keywords=["agent"], entities=["u3"], urgency=90, cluster_id="c1")]
    updated = asyncio.run(_rebuild(repo, user_id, radar.id, more, {"c1": "Agent 部署困难"}))
    assert updated[0].growth_rate > 0
    listed = repo.list_pain_points(user_id, radar_id=radar.id)
    assert listed and listed[0].theme == "Agent 部署困难"


def test_cluster_merge_merges_similar_centroids():
    repo = MemoryRepository()
    user_id = "merge-user"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找 AI 商业机会信号", keywords=["AI"]))
    base = [0.9, 0.1, 0.0, 0.0]
    big = EventClusterRead(id="11111111-1111-1111-1111-111111111111", title="大簇", document_count=7, centroid=base, source_count=3, unique_platforms=3)
    twin = EventClusterRead(id="22222222-2222-2222-2222-222222222222", title="孪生簇", document_count=3, centroid=[0.89, 0.11, 0.0, 0.0], source_count=2, unique_platforms=2)
    other = EventClusterRead(id="33333333-3333-3333-3333-333333333333", title="无关簇", document_count=2, centroid=[0.0, 0.0, 0.0, 0.95], source_count=1, unique_platforms=1)
    for cluster in (big, twin, other):
        repo.save_cluster(cluster, radar_id=radar.id)
    repo.cluster_members.append((twin.id, "raw-1"))
    repo.cluster_members.append((twin.id, "raw-2"))

    merged = merge_similar_clusters(repo, user_id, radar.id)
    assert merged == 1
    clusters = {cluster.id: cluster for cluster in repo.list_clusters(user_id, radar_id=radar.id)}
    assert twin.id not in clusters  # merged_into rows are hidden from listing
    survivors = repo.clusters
    target = next(cluster for cluster in survivors if cluster.id == big.id)
    assert target.document_count == 10
    source = next(cluster for cluster in survivors if cluster.id == twin.id)
    assert source.merged_into == big.id
    assert ("11111111-1111-1111-1111-111111111111", "raw-1") in repo.cluster_members


def test_full_run_with_listener_and_painpoints_end_to_end(monkeypatch):
    repo = MemoryRepository()
    user_id = "e2e-user"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "n8n", "level": "strong"}], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(
        name="E2E", goal="寻找 AI 自动化商业机会", keywords=["AI"],
        listener_description="寻找有偿自动化需求的商家，不要纯聊天灌水",
    ))
    items = [
        _item("https://a/1", "有偿找 n8n 自动化", "有偿找人搭工作流，预算 2000 元"),
        _item("https://b/2", "今天天气不错", "出去散步了一下午，心情很好"),
    ]
    monkeypatch.setattr("app.services.radar_run_service.get_provider", lambda: None)
    run = asyncio.run(RadarRunService(repo, AsyncStubRegistry(items)).run(user_id, radar.id, repo.create_run(radar.id).id))
    assert run.status == "completed"
    stage = run.stage_stats
    assert stage["gated_by_listener"] == 1  # weather item matched nothing positive
    assert stage["opportunities_found"] >= 1
    pains = repo.list_pain_points(user_id, radar_id=radar.id)
    assert isinstance(pains, list)  # no pain signals in this fixture → empty is fine
