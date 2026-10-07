"""Repository-level checks for the Money Intelligence extensions (memory contract;
the same assertions run against Postgres via the shared contract when DATABASE_URL exists)."""

import asyncio

from app.repositories.memory import MemoryRepository
from app.schemas.domain import ProfileUpsert, RadarCreate
from app.schemas.intelligence import SignalRead
from app.services.radar_run_service import RadarRunService


def test_mark_raw_tracks_seen_count_and_last_seen():
    repo = MemoryRepository()
    radar = repo.create_radar("user-1", RadarCreate(name="R", goal="寻找 AI 视频商业机会", keywords=["AI"]))
    first = repo.mark_raw(radar.id, "https://example.com/a", None)
    row = repo.raw_row("https://example.com/a")
    assert row["seen_count"] == 1
    second = repo.mark_raw(radar.id, "https://example.com/a", None)
    assert first == second
    row = repo.raw_row("https://example.com/a")
    assert row["seen_count"] == 2
    assert row["last_seen_at"] >= row["first_seen_at"]


def test_signals_linked_to_radar_and_raw_item():
    repo = MemoryRepository()
    user_id = "user-2"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "PPT", "level": "strong"}], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"]))
    repo.create_run(radar.id)
    run = asyncio.run(RadarRunService(repo).run(user_id, radar.id, repo.create_run(radar.id).id))
    assert run.status == "completed"
    signals = repo.list_signals(user_id, radar_id=radar.id)
    assert signals, "预算/有偿 fixture 应产出 signal"
    assert all(signal.radar_id == radar.id for signal in signals)
    assert any(signal.payment_evidence for signal in signals)


def test_run_records_stage_funnel():
    repo = MemoryRepository()
    user_id = "user-3"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "PPT", "level": "strong"}], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"]))
    run = asyncio.run(RadarRunService(repo).run(user_id, radar.id, repo.create_run(radar.id).id))
    stage = run.stage_stats
    assert stage["collected"] == 8  # 2 planned queries × 4 fixtures
    assert stage["after_dedup"] == 4  # identical fixture set collapses
    assert stage["analyzed"] == stage["after_known"]
    assert stage["signals_extracted"] >= 1
    assert stage["clusters_touched"] >= 1
    assert stage["opportunities_found"] >= 1


def test_money_score_attached_to_created_opportunities():
    repo = MemoryRepository()
    user_id = "user-4"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "PPT", "level": "strong"}], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"]))
    asyncio.run(RadarRunService(repo).run(user_id, radar.id, repo.create_run(radar.id).id))
    opportunities = repo.list_opportunities(user_id)
    assert opportunities
    for opportunity in opportunities:
        assert opportunity.money_score is not None
        assert opportunity.money_breakdown and "payment_evidence" in opportunity.money_breakdown
        assert opportunity.information_edge is not None
        assert opportunity.verification_status == "unverified"


def test_clusters_saved_via_run():
    repo = MemoryRepository()
    user_id = "user-5"
    repo.save_profile(user_id, ProfileUpsert(display_name="测试", skills=[{"name": "PPT", "level": "strong"}], goals=["client"]))
    radar = repo.create_radar(user_id, RadarCreate(name="R", goal="寻找桂林 PPT 有偿需求", keywords=["PPT"]))
    asyncio.run(RadarRunService(repo).run(user_id, radar.id, repo.create_run(radar.id).id))
    clusters = repo.list_clusters(user_id, radar_id=radar.id)
    assert clusters
    assert all(cluster.document_count >= 1 for cluster in clusters)


def test_signal_rules_extract_payment_evidence():
    from app.schemas.domain import RawItem
    from app.services.signal_service import extract_signal

    paid = extract_signal(RawItem(external_id="1", title="求帮忙", content="有偿找一个能批量生成视频的人，预算 2000 元", url="https://x/1", source="weibo"))
    assert paid is not None
    assert paid.payment_evidence is True
    assert paid.commercial_intent >= 60
    assert paid.signal_type in {"purchase_intent", "outsourcing"}

    plain = extract_signal(RawItem(external_id="2", title="随便聊聊", content="今天天气不错，出去走了走", url="https://x/2", source="weibo"))
    assert plain is None
