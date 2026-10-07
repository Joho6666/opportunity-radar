"""P0 fixes regression tests: cross-run memory, real cost funnel, idempotent events."""

import asyncio
from datetime import UTC, datetime

from app.ai.provider import LLMProvider
from app.repositories.memory import MemoryRepository
from app.schemas.domain import ProfileUpsert, RadarCreate, RawItem
from app.schemas.intelligence import EventClusterRead
from app.services.ai_service import analyze_raw_item
from app.services.clustering_service import ClusterState, assign_to_cluster
from app.services.radar_run_service import RadarRunService


def _item(url: str, title: str, content: str, source: str = "weibo") -> RawItem:
    return RawItem(external_id=url, title=title, content=content, url=url, source=source, author="u1")


V1 = [1.0, 0.0, 0.0, 0.0]
V2 = [0.0, 1.0, 0.0, 0.0]


class StubRegistry:
    """Returns fixed items regardless of slug/query (like the Broken pattern)."""

    def __init__(self, items: list[RawItem]):
        self.items = items

    async def search(self, slug: str, query: str):
        return list(self.items), None


def _repo_with_radar(user_id: str = "p0-user"):
    repo = MemoryRepository()
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "n8n", "level": "strong"}], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找 AI 自动化商业机会", keywords=["AI"]))
    return repo, user_id, radar


def _run(repo, user_id: str, radar_id: str, collectors):
    return asyncio.run(RadarRunService(repo, collectors).run(user_id, radar_id, repo.create_run(radar_id).id))


def test_mark_raw_persists_embedding_and_find_similar_raw_hits():
    repo = MemoryRepository()
    radar = repo.create_radar("u", RadarCreate(name="R", goal="寻找 AI 商业机会", keywords=["AI"]))
    raw_id = repo.mark_raw(radar.id, "https://a/1", _item("https://a/1", "t", "c"), embedding=V1)
    assert raw_id
    assert repo.find_similar_raw(radar.id, V1) == raw_id
    assert repo.find_similar_raw(radar.id, [0.0, 0.0, 0.0, 1.0]) is None
    assert repo.find_similar_raw("other-radar", V1) is None  # scoped to radar


COMMERCIAL = ("很多商家在找 AI 自动化代做服务，有预算有偿")


def test_cluster_grows_across_runs_via_seeded_state():
    repo = MemoryRepository()
    user_id, radar = "u", None
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找 AI 商业机会", keywords=["AI"]))

    # Run 1: item A creates a cluster; saved with its centroid
    state1 = ClusterState()
    cluster_id, created, _ = assign_to_cluster(_item("https://a/1", "AI 漫剧代做需求上涨", COMMERCIAL), None, state1)
    cluster = state1.clusters[cluster_id]
    repo.save_cluster(cluster, radar_id=radar.id)

    # Run 2: seeded with run 1's cluster; paraphrase under a NEW URL merges in
    state2 = ClusterState()
    state2.seed_from(repo.list_clusters(user_id, radar_id=radar.id))
    assert state2.seeded_ids
    cluster_id_2, created_2, _ = assign_to_cluster(_item("https://b/2", "AI 漫剧代做需求上涨了", COMMERCIAL), None, state2)
    assert cluster_id_2 == cluster_id
    assert created_2 is False
    merged = state2.clusters[cluster_id]
    assert merged.document_count == 2
    repo.save_cluster(merged, radar_id=radar.id)

    clusters = repo.list_clusters(user_id, radar_id=radar.id)
    assert len(clusters) == 1
    assert clusters[0].document_count == 2


def _patch_embeddings(monkeypatch, vectors: list[list[float]] | None):
    import app.services.radar_run_service as rrs

    if vectors is None:  # embeddings unavailable
        monkeypatch.setattr(rrs, "embed_texts", lambda texts: None)
    else:
        monkeypatch.setattr(rrs, "embed_texts", lambda texts: [vectors[i % len(vectors)] for i in range(len(texts))])


def test_cross_run_semantic_dedup_skips_llm_and_opportunities(monkeypatch):
    repo, user_id, radar = _repo_with_radar()
    run1_items = [
        _item("https://a/1", "AI 自动化求帮忙", COMMERCIAL),
        _item("https://b/1", "AI 智能体部署求救", "agent 部署搞不定，有偿求助"),
    ]
    _patch_embeddings(monkeypatch, [V1, V2])
    run1 = _run(repo, user_id, radar.id, StubRegistry(run1_items))
    assert run1.status == "completed"
    first_opportunities = len(repo.list_opportunities(user_id))
    assert first_opportunities >= 1

    # Run 2: same CONTENT, different URLs → URL dedup misses, embedding L4 catches
    run2_items = [
        _item("https://c/2", "AI 自动化求帮忙（转载）", COMMERCIAL),
        _item("https://d/2", "AI 智能体部署求救（转载）", "agent 部署搞不定，有偿求助"),
    ]
    run2 = _run(repo, user_id, radar.id, StubRegistry(run2_items))
    stage = run2.stage_stats
    assert stage["semantic_removed"] == 2
    assert stage["analyzed"] == 0
    assert run2.stats.opportunities_found == 0
    assert len(repo.list_opportunities(user_id)) == first_opportunities


def test_stage_gate_skips_llm_for_items_without_any_relevance(monkeypatch):
    repo, user_id, radar = _repo_with_radar()
    _patch_embeddings(monkeypatch, None)  # no embeddings in this scenario
    noise = _item("https://w/1", "今天天气不错", "出去散步了一下午，心情很好")
    run = _run(repo, user_id, radar.id, StubRegistry([noise]))
    stage = run.stage_stats
    assert stage["gated_off_topic"] == 1
    assert stage["analyzed"] == 0
    assert run.stats.opportunities_found == 0


def test_stage_gate_does_not_block_items_with_payment_signals(monkeypatch):
    repo, user_id, radar = _repo_with_radar()
    _patch_embeddings(monkeypatch, None)
    paid = _item("https://p/1", "急事求帮忙", "有偿找一个会 n8n 的人搭工作流，预算 2000 元")
    run = _run(repo, user_id, radar.id, StubRegistry([paid]))
    stage = run.stage_stats
    # has a signal → passes Stage 0.5 even though "PPT"-style keywords don't match
    assert stage["gated_off_topic"] == 0
    assert stage["analyzed"] == 1
    assert stage["signals_extracted"] == 1


def test_fallback_requires_commercial_signal():
    noise = _item("https://w/1", "今天天气不错", "出去散步了一下午")
    analysis = asyncio.run(analyze_raw_item(noise, [], has_commercial_signal=False))
    assert analysis.is_opportunity is False
    paid = _item("https://p/1", "有偿求助", "有偿找人搭自动化工作流")
    analysis = asyncio.run(analyze_raw_item(paid, []))
    assert analysis.is_opportunity is True


class UsageProvider(LLMProvider):
    def __init__(self, payload: dict, usage: dict):
        self.payload = payload
        self.usage = usage

    async def structured_output(self, prompt: str, schema_name: str) -> dict:
        return self.payload

    async def structured_output_with_usage(self, prompt: str, schema_name: str) -> tuple[dict, dict | None]:
        return self.payload, self.usage


def test_llm_usage_and_cost_recorded(monkeypatch):
    import app.services.ai_service as ai

    payload = {"is_opportunity": True, "type": "client", "title": "t", "summary": "s", "location": "线上", "work_mode": "online", "skills": [], "budget_min": 100, "budget_max": 200, "estimated_hours": 2, "commercial_intent": 80, "skill_match": 80, "conversion_probability": 70, "urgency": 60, "competition": 40, "risk": 10, "reasons": [], "warnings": []}
    provider = UsageProvider(payload, {"prompt_tokens": 1000, "completion_tokens": 500})
    monkeypatch.setattr(ai, "get_provider", lambda: provider)
    repo = MemoryRepository()
    token = ai.bind_llm_context(repository=repo, user_id="u", radar_id="r", run_id="run")
    try:
        analysis = asyncio.run(analyze_raw_item(_item("https://x/1", "有偿 AI 工作", "有偿找人做 AI 自动化，预算 500 元"), []))
    finally:
        ai.reset_llm_context(token)
    assert analysis.is_opportunity is True
    call = repo.llm_calls[-1]
    assert call["prompt_tokens"] == 1000
    assert call["completion_tokens"] == 500


def test_change_event_idempotent_per_day():
    from app.services.change_detection import detect_daily_breakout

    repo = MemoryRepository()
    radar = repo.create_radar("u", RadarCreate(name="R", goal="寻找 AI 商业机会", keywords=["AI"]))
    result = detect_daily_breakout([18.0, 17.0, 19.0, 18.0, 18.0, 18.0, 18.0], 97.0)
    first = repo.save_change_event(result.to_event("AI 视频", "mention_count", "topic", radar.id), radar_id=radar.id)
    second = repo.save_change_event(result.to_event("AI 视频", "mention_count", "topic", radar.id), radar_id=radar.id)
    events = repo.list_change_events(user_id="u")
    assert len(events) == 1
    assert first.id == events[0].id
    assert second.dedup_key == first.dedup_key


def test_memory_list_clusters_returns_centroid_after_save():
    repo = MemoryRepository()
    radar = repo.create_radar("u", RadarCreate(name="R", goal="寻找 AI 商业机会", keywords=["AI"]))
    cluster = EventClusterRead(id="11111111-1111-1111-1111-111111111111", title="t", summary="s", centroid=[0.5, 0.5, 0.0], document_count=3)
    repo.save_cluster(cluster, radar_id=radar.id)
    loaded = repo.list_clusters("u", radar_id=radar.id)
    assert loaded[0].centroid == [0.5, 0.5, 0.0]
    assert loaded[0].document_count == 3
