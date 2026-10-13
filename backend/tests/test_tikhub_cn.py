"""Domestic TikHub parsers on payloads shaped like real responses (content is synthetic)."""
import asyncio
from datetime import UTC, datetime

import pytest

from app.collectors import tikhub_cn
from app.collectors.text import clean_text
from app.collectors.tikhub_cn import DouyinCollector, parse_douyin, parse_weibo, parse_weibo_time, parse_xiaohongshu, parse_zhihu
from app.core.config import Settings
from app.services.evidence_classifier import classify_tiktok

NOW = datetime(2026, 10, 13, 4, 0, tzinfo=UTC)  # 12:00 Beijing time


def test_xiaohongshu_note_maps_to_raw_item():
    payload = {"data": {"data": {"items": [{"note": {
        "id": "n1", "title": "想找人做小程序", "desc": "预算 3000，有人接吗", "timestamp": 1791788804,
        "user": {"nickname": "小王"}, "xsec_token": "tok", "liked_count": "3", "comments_count": "1", "collected_count": "2", "type": "normal",
    }}, {"note": {}}]}}}
    [item] = parse_xiaohongshu(payload, "小程序")
    assert item.external_id == "n1" and item.source == "xiaohongshu" and item.platform == "xiaohongshu"
    assert item.url == "https://www.xiaohongshu.com/explore/n1?xsec_token=tok&xsec_source=pc_search"
    assert item.title == "想找人做小程序" and item.content == "预算 3000，有人接吗"
    assert item.published_at == datetime.fromtimestamp(1791788804, tz=UTC)
    assert item.engagement == {"likes": 3, "comments": 1, "collects": 2}


def test_weibo_post_maps_and_parses_chinese_time():
    payload = {"data": {"parsed_data": {"results": [{
        "weibo_id": "w1", "content": "<b>急招</b>短视频剪辑&amp;后期", "user_nick": "某公司", "publish_time": "10月12日 10:55",
        "post_url": "//weibo.com/123/abc?refer_flag=1", "interaction": {"repost_count": "0", "comment_count": "2", "like_count": "5"},
    }]}}}
    [item] = parse_weibo(payload, "剪辑", now=NOW)
    assert item.url == "https://weibo.com/123/abc"
    assert item.content == "急招短视频剪辑&后期"
    assert item.published_at == datetime(2026, 10, 12, 2, 55, tzinfo=UTC)


@pytest.mark.parametrize("raw, expected", [
    ("刚刚", datetime(2026, 10, 13, 4, 0, tzinfo=UTC)),
    ("5分钟前", datetime(2026, 10, 13, 3, 55, tzinfo=UTC)),
    ("今天 08:30", datetime(2026, 10, 13, 0, 30, tzinfo=UTC)),
    ("昨天 23:10", datetime(2026, 10, 12, 15, 10, tzinfo=UTC)),
    ("2025年12月30日 09:00", datetime(2025, 12, 30, 1, 0, tzinfo=UTC)),
    ("12月30日 09:00", datetime(2025, 12, 30, 1, 0, tzinfo=UTC)),  # a December date seen in October is last year
    ("not a time", None),
])
def test_parse_weibo_time(raw, expected):
    assert parse_weibo_time(raw, NOW) == expected


def test_zhihu_keeps_articles_and_answers_and_skips_other_cards():
    payload = {"data": {"data": [
        {"type": "ai_zhida", "object": {}},
        {"type": "search_result", "object": {"id": "a1", "type": "article", "title": "<em>接私活</em>的渠道", "excerpt": "正文", "created_time": 1790955559, "author": {"name": "作者"}, "voteup_count": 4}},
        {"type": "search_result", "object": {"id": "ans1", "type": "answer", "question": {"id": "q9", "name": "去哪找外包？"}, "excerpt": "回答"}},
        {"type": "relevant_query", "object": {}},
    ]}}
    article, answer = parse_zhihu(payload, "私活")
    assert article.url == "https://zhuanlan.zhihu.com/p/a1" and article.title == "接私活的渠道"
    assert answer.url == "https://www.zhihu.com/question/q9/answer/ans1" and answer.title == "去哪找外包？"


def test_douyin_card_keeps_top_comments():
    payload = {"data": {"data": [{"aweme_info": {
        "aweme_id": "7695912449523101107", "desc": "想找个能帮我剪辑的老师，有人吗？", "create_time": 1791520454,
        "author": {"nickname": "某人"}, "statistics": {"digg_count": 25, "comment_count": 195, "share_count": 0, "play_count": 0},
    }, "comment_list": [{"text": "我可以"}, {"text": "私信你了"}]}, {"aweme_info": {"aweme_id": "x"}}]}}
    [item] = parse_douyin(payload, "剪辑")
    assert item.url == "https://www.douyin.com/video/7695912449523101107"
    assert item.metadata["top_comments"] == "我可以 | 私信你了"
    assert item.engagement["comments"] == 195


def test_douyin_collector_posts_to_configured_base_url(monkeypatch):
    calls = []

    async def fake_post_json(url, payload, **kwargs):
        calls.append((url, payload, kwargs["headers"]["Authorization"]))
        return {"code": 200, "data": {"data": []}}

    monkeypatch.setattr(tikhub_cn, "get_settings", lambda: Settings(tikhub_api_key="k", tikhub_base_url="https://api.tikhub.dev/"))
    monkeypatch.setattr(tikhub_cn.fetcher, "post_json", fake_post_json)
    assert asyncio.run(DouyinCollector().search(" 剪辑 ")) == []
    assert calls == [("https://api.tikhub.dev/api/v1/douyin/search/fetch_general_search_v1", {"keyword": "剪辑", "cursor": 0, "sort_type": "0", "publish_time": "7"}, "Bearer k")]


def test_collector_refuses_without_key(monkeypatch):
    monkeypatch.setattr(tikhub_cn, "get_settings", lambda: Settings(tikhub_api_key=""))
    with pytest.raises(RuntimeError, match="TIKHUB_API_KEY"):
        asyncio.run(DouyinCollector().search("剪辑"))


def test_clean_text_strips_markup_and_entities():
    assert clean_text("<p>I&#x27;m <em>hiring</em></p><p>Remote&nbsp;OK</p>") == "I'm hiring\nRemote OK"
    assert clean_text(None) == ""


@pytest.mark.parametrize("text, title, expected", [
    # buyers asking in their own voice, even under seller hashtags
    ("有人接视频剪辑嘛#剪辑代剪 #接单接单", None, "buyer"),
    ("谁接代剪\n急求#接代剪 #剪辑接单", None, "buyer"),
    ("想找會剪輯的朋友#三角洲行动", None, "buyer"),
    ("正文没有关键词", "[私活]有一个 im 需求寻找一位 flutter 客户端", "buyer"),
    ("WordPress 站点主题制作，长期合作", "招一个业余兼职小说/剧本写手", "buyer"),
    # sellers, including demand words inside seller phrases
    ("可以做官网和小程序，预算多少都能聊", "个人承接网站及前端开发项目", "market"),
    ("35 岁被辞了可以自己接外包啊", None, "market"),
    ("本人5年大厂经验，独立设计开发小程序", "独立软件设计：小程序好看好用", "market"),
    ("简单页面修改：29.9 元起，预算不多也能安排", None, "market"),
    # articles about the topic, not requests
    ("找人开发软件，先写清这5件事", None, "content"),
    ("程序员接私活，十大渠道！", None, "content"),
    ("2026年靠谱的10个程序员兼职平台", None, "content"),
    # job posts: "3 年经验" is a requirement, not a how-to
    ("负责后端开发，要求 3 年经验，薪资 15-25k", "remote 高级 PHP 开发工程师 招聘", "buyer"),
    ("AssumeAI | AI Engineer (£30/hr) | Contract | REMOTE (UK)", None, "buyer"),
])
def test_domestic_and_forum_classification(text, title, expected):
    assert classify_tiktok(text, title=title).category == expected


def test_self_labelled_seller_title_wins_over_demand_words():
    assert classify_tiktok("我能帮你做官网和小程序", title="[接单]全栈开发 | 创业者软件定制 | 官网 / 小程序").category == "market"
    assert classify_tiktok("要求熟悉 React", title="【求职】前端开发，可远程").category == "market"
