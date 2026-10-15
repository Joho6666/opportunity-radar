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
    assert calls == [("https://api.tikhub.dev/api/v1/douyin/search/fetch_general_search_v1", {"keyword": "剪辑", "cursor": 0, "sort_type": "2", "publish_time": "7", "search_id": "", "backtrace": ""}, "Bearer k")]


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
    ("可以做官网和小程序，预算多少都能聊", "个人承接网站及前端开发项目", "seller"),
    ("35 岁被辞了可以自己接外包啊", None, "seller"),
    ("本人5年大厂经验，独立设计开发小程序", "独立软件设计：小程序好看好用", "seller"),
    ("简单页面修改：29.9 元起，预算不多也能安排", None, "seller"),
    # articles about the topic, not requests
    ("找人开发软件，先写清这5件事", None, "content"),
    ("程序员接私活，十大渠道！", None, "content"),
    ("2026年靠谱的10个程序员兼职平台", None, "content"),
    # job posts: "3 年经验" is a requirement, not a how-to
    ("负责后端开发，要求 3 年经验，薪资 15-25k", "remote 高级 PHP 开发工程师 招聘", "job"),
    ("AssumeAI | AI Engineer (£30/hr) | Contract | REMOTE (UK)", None, "buyer"),
])
def test_domestic_and_forum_classification(text, title, expected):
    assert classify_tiktok(text, title=title).category == expected


def test_self_labelled_seller_title_wins_over_demand_words():
    assert classify_tiktok("我能帮你做官网和小程序", title="[接单]全栈开发 | 创业者软件定制 | 官网 / 小程序").category == "seller"
    assert classify_tiktok("要求熟悉 React", title="【求职】前端开发，可远程").category == "job"


@pytest.mark.parametrize("parser",[parse_douyin,parse_xiaohongshu,parse_weibo,parse_zhihu])
@pytest.mark.parametrize("payload",[{}, {"data":None}, {"data":{"data":"changed","parsed_data":None}}])
def test_domestic_schema_changes_are_visible(parser,payload):
    from app.core.errors import AppError
    with pytest.raises(AppError):parser(payload,"需求")

@pytest.mark.parametrize("parser,payload",[
    (parse_xiaohongshu,{"data":{"data":{"items":[]}}}),
    (parse_weibo,{"data":{"parsed_data":{"results":[]}}}),
    (parse_douyin,{"data":{"data":[]}}),
    (parse_zhihu,{"data":{"data":[]}}),
])
def test_empty_domestic_success_is_distinct_from_schema_failure(parser,payload):
    assert parser(payload,"需求") == []


def test_comment_author_and_evidence_identity_stay_separate():
    payload={"data":{"data":[{"aweme_info":{"aweme_id":"v1","desc":"我们专业团队提供剪辑服务","author":{"nickname":"服务商"}},"comment_list":[{"cid":"c1","text":"需要制作商品视频，请问报价多少","user":{"nickname":"买方"}},{"text":"没有ID的评论不能当作独立证据"}]}]}}
    video,comment=parse_douyin(payload,"视频")
    assert video.author == "服务商" and comment.author == "买方"
    assert video.external_id != comment.external_id
    assert comment.metadata["parent_video_id"] == "v1"
    assert classify_tiktok(comment.content).category == "buyer"

@pytest.mark.parametrize("cls,key,cursor",[
    (tikhub_cn.XiaohongshuCollector,"page",2),
    (tikhub_cn.WeiboCollector,"page",2),
    (tikhub_cn.ZhihuCollector,"offset","20"),
    (tikhub_cn.DouyinCollector,"cursor",20),
])
def test_domestic_cursor_is_explicit_and_bounded(monkeypatch,cls,key,cursor):
    from urllib.parse import urlparse,parse_qs
    calls=[]
    async def get(url,**kwargs):calls.append(parse_qs(urlparse(url).query));return {"code":200,"data":{"data":[],"parsed_data":{"results":[]}}}
    async def post(url,args,**kwargs):calls.append(args);return {"code":200,"data":{"data":[]}}
    if cls is tikhub_cn.XiaohongshuCollector:
        async def get(url,**kwargs):calls.append(parse_qs(urlparse(url).query));return {"code":200,"data":{"data":{"items":[]}}}
    monkeypatch.setattr(tikhub_cn,"get_settings",lambda:Settings(tikhub_api_key="offline-only"))
    monkeypatch.setattr(tikhub_cn.fetcher,"get_json",get);monkeypatch.setattr(tikhub_cn.fetcher,"post_json",post)
    assert asyncio.run(cls().search_page("需求",str(cursor))) == ([],None)
    value=calls[0][key]
    assert str(value[0] if isinstance(value,list) else value) == str(cursor)
    with pytest.raises(ValueError):asyncio.run(cls().search_page("需求","-1"))

@pytest.mark.parametrize("raw",["今天 99:99","2026年2月30日","昨天 25:00"])
def test_invalid_weibo_dates_are_unknown(raw):
    assert parse_weibo_time(raw,NOW) is None


@pytest.mark.parametrize("cls,first,expected", [
    (tikhub_cn.XiaohongshuCollector, {"data": {"items": [], "has_more": True, "search_id": "s1", "search_session_id": "session1"}}, {"page": "2", "search_id": "s1", "search_session_id": "session1"}),
    (tikhub_cn.DouyinCollector, {"data": [], "has_more": True, "cursor": 20, "search_id": "s2", "backtrace": "b2"}, {"cursor": 20, "search_id": "s2", "backtrace": "b2"}),
])
def test_empty_page_keeps_provider_sessions(cls, first, expected, monkeypatch):
    from urllib.parse import urlparse, parse_qs
    calls = []
    async def get(url, **kwargs):
        args = {k:v[0] for k,v in parse_qs(urlparse(url).query).items()}
        calls.append(args)
        return {"code": 200, "data": first if len(calls) == 1 else {"data": {"items": []}}}
    async def post(url, args, **kwargs):
        calls.append(args)
        return {"code": 200, "data": first if len(calls) == 1 else {"data": []}}
    monkeypatch.setattr(tikhub_cn, "get_settings", lambda: Settings(tikhub_api_key="offline-only"))
    monkeypatch.setattr(tikhub_cn.fetcher, "get_json", get)
    monkeypatch.setattr(tikhub_cn.fetcher, "post_json", post)
    async def run():
        adapter = cls()
        items, cursor = await adapter.search_page("找人")
        assert items == [] and cursor
        await adapter.search_page("找人", cursor)
    asyncio.run(run())
    for key, value in expected.items():
        assert calls[1][key] == value


def test_incomplete_search_session_does_not_offer_charged_next_page(monkeypatch):
    async def get(url, **kwargs):
        return {"code":200,"data":{"data":{"items":[],"has_more":True}}}
    monkeypatch.setattr(tikhub_cn,"get_settings",lambda:Settings(tikhub_api_key="offline-only"))
    monkeypatch.setattr(tikhub_cn.fetcher,"get_json",get)
    assert asyncio.run(tikhub_cn.XiaohongshuCollector().search_page("PPT")) == ([],None)
