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
    "市场团队": r"(?:我们|本公司|公司)(?:的)?市场部|(?:我|我们)(?:是|在)[^。！？\n]{0,6}市场部",
    "培训机构": r"(?:我们|我|本公司)(?:是|开|做|经营)[^。！？\n]{0,10}(?:培训机构|教培机构|教育机构)",
    "学生": r"(?:我|我们|本人)(?:是|为|在读|就是)?[^。！？\n]{0,8}(?:在校生|大学生|研究生|学生)",
    "自由职业": r"(?:我|本人)(?:是|做|属于)?[^。！？\n]{0,6}自由职业",
    "自媒体": r"(?:我|我们|本人)(?:是|做)[^。！？\n]{0,8}(?:自媒体|博主|UP主|up主)",
}
INTENT_PATTERNS = {
    "找人制作": r"找人[^。！？\n]{0,20}(?:做|制作|开发|拍摄)|求[^。！？\n]{0,12}(?:制作|开发)|(?:有|有没有)[^。！？\n]{0,30}(?:做|制作|生成|拍摄)[^。！？\n]{0,20}(?:吗|公司)|(?:需要|寻找|想找)[^。！？\n]{0,15}(?:外包|供应商|制作团队)",
    "询价报价": r"(?:多少钱|什么价|怎么收费|费用多少|价格多少)|(?:求|想问|问下|问一下|咨询下)[^。！？\n]{0,6}(?:报价|价格|费用)",
    "咨询方案": r"(?:想|需要|求|请教|有没有)[^。！？\n]{0,15}(?:方案|怎么做|如何实现)",
    "长期合作": r"(?:可|希望|寻求|需要|找)[^。！？\n]{0,8}长期合作",
}


def _role_pattern(role: str) -> str:
    preset = ROLE_PATTERNS.get(role)
    if preset:
        return preset
    token = re.escape(role.strip())
    return rf"(?:我|我们|本人|本公司)(?:是|做|为|属于|在做)?[^。！？\n]{{0,8}}{token}"


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
OVERSEAS_REGIONS = {
    "美国": ("美国", "美國", "USA", "US", "United States"),
    "加拿大": ("加拿大", "Canada"),
    "英国": ("英国", "英國", "UK", "United Kingdom"),
    "德国": ("德国", "德國", "Germany"),
    "日本": ("日本", "Japan"),
    "新加坡": ("新加坡", "Singapore"),
    "马来西亚": ("马来西亚", "馬來西亞", "Malaysia"),
    "澳大利亚": ("澳大利亚", "澳大利亞", "Australia"),
}
PLACE_QUERY_SKIP = {
    "中国", "广东", "浙江", "江苏", "山东", "福建", "四川", "湖北", "湖南", "河南", "安徽", "陕西",
    "辽宁", "河北", "江西", "云南", "广西", "海南", "山西", "贵州", "黑龙江", "吉林", "甘肃",
    "内蒙古", "新疆", "西藏", "宁夏", "青海", "香港", "澳门", "台湾", "台北", "高雄",
    "加利福尼亚", "洛杉矶", "旧金山", "圣何塞", "纽约州", "纽约", "得克萨斯", "休斯顿", "达拉斯", "奥斯汀",
    "华盛顿州", "西雅图", "华盛顿特区", "佛罗里达", "迈阿密", "伊利诺伊", "芝加哥",
    "安大略", "多伦多", "渥太华", "不列颠哥伦比亚", "温哥华", "魁北克", "蒙特利尔",
    "英格兰", "伦敦", "曼彻斯特", "苏格兰", "爱丁堡", "巴伐利亚", "慕尼黑", "柏林", "汉堡", "北威", "科隆",
    "东京都", "东京", "大阪府", "大阪", "神奈川县", "横滨", "吉隆坡", "槟城", "柔佛", "新山",
    "新南威尔士", "悉尼", "维多利亚", "墨尔本", "昆士兰", "布里斯班", "迪拜", "阿布扎比",
    "曼谷", "胡志明市", "河内", "雅加达", "首尔", "巴黎", "泰国", "越南", "印尼", "韩国", "法国", "阿联酋",
}
REGION_QUERY_SKIP = DOUYIN_CITY_NAMES | set(OVERSEAS_REGIONS) | PLACE_QUERY_SKIP
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
    kept = [token for token in tokens if token not in REGION_QUERY_SKIP and not re.fullmatch(r".{2,4}[市省区县]", token)]
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


def _region_aliases(region: str) -> tuple[str, ...]:
    folded = region.strip().casefold()
    for aliases in OVERSEAS_REGIONS.values():
        if folded in {alias.casefold() for alias in aliases}:
            return aliases
    return (region.removesuffix("市").removesuffix("省"),)


def _region_quote(text: str, region: str) -> str | None:
    """Project/service context only. A bare country mention or query word is not evidence."""
    for alias in _region_aliases(region):
        if re.search(r"[A-Za-z]", alias):
            escaped = re.escape(alias)
            pattern = rf"(?:in|for|from|across)\s+(?:the\s+)?{escaped}\b|(?:the\s+)?{escaped}\s+(?:market|amazon|clients?|customers?|sellers?)"
        else:
            token = re.escape(alias)
            pattern = (
                rf"{token}(?:市|省)?(?:有(?:没有)?[^。！？\n]{{0,30}}(?:做|拍摄|制作|公司)|(?:本地|地区|同城|市场|站)[^。！？\n]{{0,20}}|[^。！？\n]{{0,8}}(?:项目|门店|实体店|客户|卖家))"
                rf"|(?:我们|公司|项目|服务地点|拍摄地点|所在地|面向|出海)(?:是|在|位于|到|：|:){{0,2}}{token}(?:市|省)?"
            )
        match = re.search(pattern, text, re.I)
        if match:
            return match.group(0)
    return None


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
    buyer=find(INTENT_PATTERNS["找人制作"] + "|" + INTENT_PATTERNS["咨询方案"] + "|" + INTENT_PATTERNS["询价报价"])
    seller=find(r"(?:我们|本公司|本人)(?:提供|承接|专做)[^。！？\n]{0,30}|(?:制作接单|欢迎咨询|接单中)")
    if buyer:
        evidence["买方需求"]=buyer
        if seller: missing.append("买卖方混合表述需人工核实")
    elif seller:
        conflicts.append("服务推广，未找到买方采购原文")
    else:
        missing.append("买方采购意图")
    if cfg.roles:
        quote=next((found for role in cfg.roles if (found:=find(_role_pattern(role)))), None)
        if quote: evidence["目标角色"]=quote
        else: missing.append("目标角色")
    if cfg.intents:
        quote=next((found for choice in cfg.intents if (found:=find(INTENT_PATTERNS[choice]))), None)
        if quote: evidence["需求意图"]=quote
        else: missing.append("需求意图")
    if cfg.regions:
        # Only project/service/self-business context. An IP/profile/query city is not evidence.
        quote=None
        for region in cfg.regions:
            quote=_region_quote(text, region)
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
