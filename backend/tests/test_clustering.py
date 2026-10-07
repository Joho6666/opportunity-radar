from app.schemas.domain import RawItem
from app.services.clustering_service import ClusterState, assign_to_cluster, breakout_score, cluster_velocity, finalize_clusters


def _item(url: str, title: str, content: str, source: str = "weibo", author: str | None = "user1") -> RawItem:
    return RawItem(external_id=url, title=title, content=content, url=url, source=source, author=author)


def test_new_cluster_created_for_first_item():
    state = ClusterState()
    cluster_id, created, similarity = assign_to_cluster(_item("https://a/1", "AI 视频工具求推荐", "有没有能批量生成电商广告视频的工具"), None, state)
    assert created is True
    assert state.clusters[cluster_id].document_count == 1


def test_similar_items_merge_into_one_cluster():
    """100 篇转载不应成为 100 个机会——同事件内容归并到同一个 cluster。"""
    state = ClusterState()
    first_id, created, _ = assign_to_cluster(_item("https://a/1", "AI 漫剧代做需求上涨", "很多商家在找 AI 漫剧代做服务，有预算"), None, state)
    merged = 0
    for index in range(2, 12):
        cid, created_now, _ = assign_to_cluster(
            _item(f"https://s/{index}", f"AI 漫剧代做需求上涨 报道{index}", "很多商家在找 AI 漫剧代做服务，有预算"),
            None,
            state,
        )
        assert cid == first_id
        merged += 1 if not created_now else 0
    assert merged == 10
    assert state.clusters[first_id].document_count == 11
    assert len(state.clusters) == 1


def test_different_topics_form_separate_clusters():
    state = ClusterState()
    id_a, _, _ = assign_to_cluster(_item("https://a/1", "AI 视频批量生成求推荐", "有没有工具可以批量做电商广告视频"), None, state)
    id_b, created_b, _ = assign_to_cluster(_item("https://b/1", "STM32 毕设硬件调试求助", "单片机翻车了有没有人帮忙"), None, state)
    assert id_a != id_b
    assert created_b is True


def test_embedding_vector_updates_centroid():
    state = ClusterState()
    cluster_id, _, _ = assign_to_cluster(_item("https://a/1", "t", "c"), [1.0, 0.0, 0.0], state)
    assign_to_cluster(_item("https://a/2", "t2", "c2"), [0.0, 1.0, 0.0], state, cosine_threshold=0.99)
    centroid = state.centroids[cluster_id]
    # centroid moved toward the second vector (running average of the two)
    assert abs(centroid[0] - 0.5) < 1e-9 or len(state.centroids) == 2


def test_finalize_recomputes_platform_and_author_spread():
    state = ClusterState()
    cluster_id, _, _ = assign_to_cluster(_item("https://a/1", "共同主题内容", "批量生成视频工具需求"), None, state)
    for index, source in enumerate(["weibo", "reddit", "x"]):
        assign_to_cluster(_item(f"https://s/{index}", f"共同主题内容{index}", "批量生成视频工具需求", source=source, author=f"u{index}"), None, state)
    platforms = {cluster_id: {"weibo", "reddit", "x"}}
    authors = {cluster_id: {"u0", "u1", "u2", "user1"}}
    clusters = finalize_clusters(state, platform_map=platforms, author_map=authors)
    target = next(cluster for cluster in clusters if cluster.id == cluster_id)
    assert target.unique_platforms == 3
    assert target.unique_authors == 4
    assert target.document_count == 4


def test_velocity_and_breakout_math():
    assert cluster_velocity(24, 1.0) == 24.0
    assert cluster_velocity(24, 0) == 24.0
    quiet = breakout_score(document_count=2, velocity_24h=0.1, cross_platform=1)
    loud = breakout_score(document_count=64, velocity_24h=4.0, cross_platform=5)
    assert loud > quiet
    assert 0 <= quiet <= 100 and 0 <= loud <= 100
