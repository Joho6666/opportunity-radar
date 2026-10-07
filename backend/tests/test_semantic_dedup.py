from app.schemas.domain import RawItem
from app.services.dedup_service import SemanticDedupState, deduplicate, is_semantic_duplicate, semantic_duplicate


def _item(url: str, title: str, content: str, source: str = "web_search") -> RawItem:
    return RawItem(external_id=url, title=title, content=content, url=url, source=source)


def test_level1_url_hash_dedup():
    items = [_item("https://a.com/x?utm=1", "T1", "C1"), _item("https://a.com/x", "T2", "C2")]
    unique, removed = deduplicate(items)
    assert len(unique) == 1
    assert removed == 1


def test_level2_content_hash_dedup_cross_url():
    items = [_item("https://a.com/1", "转载标题", "完全一样的内容正文"), _item("https://b.com/2", "转载标题", "完全一样的内容正文")]
    unique, removed = deduplicate(items)
    assert len(unique) == 1
    assert removed == 1


def test_level3_simhash_dedup_near_duplicate():
    base = "小商家不会做短视频内容，想找人批量生成 AI 视频"
    items = [
        _item("https://a.com/1", "帖子一", base),
        _item("https://b.com/2", "帖子二", base + "，预算充足"),
    ]
    unique, removed = deduplicate(items)
    assert len(unique) == 1
    assert removed == 1


def test_different_content_survives_all_levels():
    items = [
        _item("https://a.com/1", "AI 视频求推荐", "有没有批量生成电商广告视频的工具，求推荐"),
        _item("https://b.com/2", "STM32 求助", "毕业设计硬件调试一直翻车，有没有人能帮忙看看"),
    ]
    unique, removed = deduplicate(items)
    assert len(unique) == 2
    assert removed == 0


def test_level4_embedding_state_blocks_same_vector():
    item = _item("https://c.com/3", "工具求推荐", "有没有人能做批量生成")
    vector = [0.1] * 8
    state = SemanticDedupState()
    state.vectors.append(list(vector))
    assert is_semantic_duplicate(item, vector, state) is True


def test_level4_state_accumulates_accepted_items():
    first = _item("https://a.com/1", "first", "first content")
    second = _item("https://b.com/2", "second", "totally different body text")
    state = SemanticDedupState()
    assert is_semantic_duplicate(first, [0.5, 0.0, 0.1], state) is False
    assert is_semantic_duplicate(second, [0.0, 0.9, 0.2], state) is False
    assert len(state.vectors) == 2
    assert len(state.fingerprints) == 2


def test_legacy_semantic_duplicate_hook_still_works():
    base = "求大佬帮忙搭一个 n8n 自动化工作流，有偿"
    assert semantic_duplicate(_item("https://x/1", "t", base), [_item("https://x/2", "t2", base + "！")]) is True
    assert semantic_duplicate(_item("https://x/1", "t", base), [_item("https://x/3", "t3", "完全无关的硬件调试内容")]) is False
