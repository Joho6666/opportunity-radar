"""Conservative, no-AI checks on source text only, never search/author/IP evidence."""
import re
from datetime import UTC, datetime, timedelta
from ..schemas.hunt import HuntConditions

ROLE_PATTERNS = {
    "电商商家": r"(?:我们|我|本公司|公司|本人)(?:是|做|经营|在做|主营)[^。！？\n]{0,12}(?:电商商家|电商卖家|亚马逊卖家|淘宝商家|网店|电商)",
    "品牌方": r"(?:我们|我|本公司|公司|本人)(?:是|做|经营|在做)[^。！？\n]{0,12}品牌(?:方|商)",
    "实体店": r"(?:我们|我|本人)(?:是|有|开|经营|在经营)[^。！？\n]{0,12}(?:实体店|门店|店铺)",
    "创业者": r"(?:我|我们|本人)(?:是|正在|在)?(?:创业者|创业|创办)",
    "代运营工作室": r"(?:我们|我|本公司|本人)(?:是|做|经营)[^。！？\n]{0,12}(?:代运营|工作室)",
}
INTENT_PATTERNS = {
    "找人制作": r"找人[^。！？\n]{0,20}(?:做|制作|开发|拍摄)|求[^。！？\n]{0,12}(?:制作|开发)|(?:有|有没有)[^。！？\n]{0,30}(?:做|制作|生成|拍摄)[^。！？\n]{0,20}(?:吗|公司)|(?:需要|寻找|想找)[^。！？\n]{0,15}(?:外包|供应商|制作团队)",
    "咨询方案": r"(?:想|需要|求|请教|有没有)[^。！？\n]{0,15}(?:方案|怎么做|如何实现)",
    "长期合作": r"(?:可|希望|寻求|需要|找)[^。！？\n]{0,8}长期合作",
}


def conditions_for(radar):
    raw = radar.source_config.get("hunt_conditions") if radar.source_config.get("lead_hunt") == "true" else None
    return HuntConditions.model_validate_json(raw) if raw else None


# 抖音搜索对长短语几乎零召回。父代理 2026-10-18 真实调用证据：
# 「找拍摄」→8 条、「家居」→1000 条；「家居 找视频拍摄」→0、「圣诞 视频 制作 求推荐」→0。
# 证据只用于确定截短规则，本轮没有再次付费调用（见 fixtures/douyin_short_keyword_evidence.json）。
DOUYIN_CITY_NAMES = {
    "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "西安", "南京", "苏州", "天津",
    "长沙", "郑州", "东莞", "佛山", "宁波", "青岛", "合肥", "昆明", "福州", "厦门", "济南", "大连",
    "沈阳", "哈尔滨", "长春", "石家庄", "太原", "南昌", "贵阳", "南宁", "海口", "兰州", "西宁",
    "银川", "乌鲁木齐", "呼和浩特", "拉萨", "桂林", "柳州", "珠海", "中山", "惠州", "汕头", "温州",
    "嘉兴", "绍兴", "台州", "金华", "泉州", "烟台", "潍坊", "徐州", "常州", "南通", "扬州", "洛阳",
}
DOUYIN_LEADING = ("找人", "求推荐", "求", "需要", "想找", "帮我", "有没有", "哪里", "怎么", "做一个", "做")
DOUYIN_TRAILING = ("制作", "拍摄", "剪辑", "外包", "需求", "推荐", "开发", "设计", "服务", "团队", "公司")


def _strip_douyin_affixes(token: str) -> str:
    value = token.strip("，,。.！!？?、/|:：;；()（）[]【】\"'“”")
    changed = True
    while changed:
        changed = False
        for prefix in DOUYIN_LEADING:
            if value.startswith(prefix) and len(value) - len(prefix) >= 2:
                value = value[len(prefix):]
                changed = True
                break
    while len(value) > 4:
        for suffix in DOUYIN_TRAILING:
            if value.endswith(suffix) and len(value) - len(suffix) >= 2:
                value = value[:-len(suffix)]
                changed = True
                break
        if not changed:
            break
        changed = False
    return value[:4] if len(value) > 4 else value


def shorten_douyin_keyword(value: str) -> str:
    """把买方长短语压成抖音能召回的核心 2–4 字词（不改变小红书/微博等长短语）。"""
    tokens = [token for token in re.split(r"[\s，,、/|]+", value or "") if token]
    kept = [token for token in tokens if token not in DOUYIN_CITY_NAMES and not re.fullmatch(r".{2,4}[市省区县]", token)]
    for token in kept or tokens:
        core = _strip_douyin_affixes(token)
        if 2 <= len(core) <= 4:
            return core
    return ""


def hunt_topics(radar, source: str | None = None):
    topics = list(radar.keywords)
    if not topics:
        return topics
    if source == "douyin":
        # 抖音只发短词；去重后仍受关键词/请求上限约束，地区词不拼进来（会重新变长）。
        short = [term for term in dict.fromkeys(shorten_douyin_keyword(topic) for topic in topics) if term]
        return short[: min(3, 6 // max(1, len(radar.sources)))]
    cfg = conditions_for(radar)
    if not cfg or not cfg.regions:
        return topics
    limit = min(3, 6 // max(1, len(radar.sources)))
    # Base query is always retained. Region variants replace later slots, never
    # increase the provider budget. More regions still participate in matching.
    if limit >= 2:
        topics = topics[:limit]
        variant = f"{cfg.regions[0]} {topics[0]}"
        if len(topics) < limit:
            topics.append(variant)
        else:
            topics[-1] = variant
    return topics


def assess_hiring_signal(item):
    """LinkedIn jobs are leads *about* hiring, never a buyer's own request.

    Kept separate from assess_hunt so a job title such as "找人做视频" cannot be
    mistaken for a buyer post, and so the UI can label the class honestly.
    """
    evidence = {"公司": item.metadata.get("company") or item.author or "",
                "职位": item.metadata.get("job_title") or item.title,
                "逻辑": "在招视频相关岗位的公司通常有持续的视频制作/剪辑需求"}
    if item.metadata.get("location"):
        evidence["地点"] = item.metadata["location"]
    if item.published_at:
        evidence["职位发布时间"] = item.published_at.astimezone(UTC).isoformat()
    return {"status": "hiring_signal", "evidence": evidence,
            "missing": ["不是买方直接需求；需另行找到该公司的采购/需求原文"],
            "conflicts": [], "evidence_level": "职位搜索结果（未抓取职位详情）",
            "match_mode": "hiring_signal"}


def assess_hunt(item, radar, now=None):
    cfg=conditions_for(radar)
    if cfg is None:
        return None
    now=now or datetime.now(UTC)
    text=f"{item.title}\n{item.content}"
    evidence={}; missing=[]; conflicts=[]
    def find(pattern):
        match=re.search(pattern,text,re.I)
        return match.group(0) if match else None
    published=item.published_at
    if published:
        published=published if published.tzinfo else published.replace(tzinfo=UTC)
        start=cfg.start_at or now-timedelta(hours=radar.freshness_hours)
        end=cfg.end_at or now
        if start<=published<=end:
            evidence["原帖发布时间"]=published.astimezone(UTC).isoformat()
        else:
            conflicts.append("原帖发布时间不在所选范围")
    else:
        missing.append("原帖发布时间")
    terms=radar.collection_policy.required_terms
    hit=next((term for term in terms if term.casefold() in text.casefold()),None)
    if hit:
        evidence["业务"]=hit
    elif terms:
        conflicts.append("正文未命中业务匹配词")
    buyer=find(INTENT_PATTERNS["找人制作"] + "|" + INTENT_PATTERNS["咨询方案"])
    seller=find(r"(?:我们|本公司|本人)(?:提供|承接|专做)[^。！？\n]{0,30}|(?:制作接单|欢迎咨询|接单中)")
    if buyer:
        evidence["买方需求"]=buyer
        if seller: missing.append("买卖方混合表述需人工核实")
    elif seller:
        conflicts.append("服务推广，未找到买方采购原文")
    else:
        missing.append("买方采购意图")
    for field,selected,patterns in [("目标角色",cfg.roles,ROLE_PATTERNS),("需求意图",cfg.intents,INTENT_PATTERNS)]:
        if selected:
            quote=next((q for choice in selected if (q:=find(patterns[choice]))),None)
            if quote: evidence[field]=quote
            else: missing.append(field)
    if cfg.regions:
        # Only project/service/self-business context. An IP/profile/query city is not evidence.
        quote=None
        for region in cfg.regions:
            r=re.escape(region.removesuffix("市").removesuffix("省"))
            quote=find(rf"{r}(?:市|省)?(?:有(?:没有)?[^。！？\n]{{0,30}}(?:做|拍摄|制作|公司)|(?:本地|地区|同城)[^。！？\n]{{0,20}}|[^。！？\n]{{0,8}}(?:项目|门店|实体店))|(?:我们|公司|项目|服务地点|拍摄地点|所在地)(?:是|在|位于|：|:){{0,2}}{r}(?:市|省)?")
            if quote: break
        if quote: evidence["需求地区"]=quote
        else: missing.append("需求地区")
    if cfg.match_mode=="local" and not cfg.regions:
        missing.append("本地需求地区未选择")
    remote=find(r"(?:可远程|接受远程|远程合作|线上合作|不限地区|全国接洽)")
    if remote: evidence["合作方式"]=remote
    if cfg.match_mode=="local" and remote and "需求地区" not in evidence:
        conflicts.append("仅有远程描述，未确认本地项目")
    full=item.metadata.get("content_kind") in {"post_detail","full_text","article","rss_entry"}
    if not full: missing.append("完整正文核验")
    return {"status":"mismatch" if conflicts else "pending" if missing else "strict", "evidence":evidence,"missing":missing,"conflicts":conflicts,"evidence_level":"完整正文（规则核验）" if full else "搜索摘要（未核实完整正文）", "match_mode":cfg.match_mode}
