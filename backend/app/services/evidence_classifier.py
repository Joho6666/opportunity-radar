from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class Classification:
    category: str
    reason_code: str
    confidence: float
    evidence_grade: str
    payment_signal: str | None = None
    urgency_signal: str | None = None


# Creators, studios and freelancers advertising themselves ("商务合作私信", "个人承接", "接外包",
# "DM for collab") and people looking for work are sellers, not buyers.
_SELLER = re.compile(
    r"商务合作|合作.{0,4}(私信|联系|vx|微信)|接(广告|推广|单|外包|私活|代剪)|个人承接|承接|品牌推广|欢迎咨询|招(代理|商)|专业代做"
    r"|一对一定制|专业团队|我们团队|求(职|兼职)|找(兼职|工作)|出售一下自己|自荐|可接单"
    r"|本人.{0,12}(经验|程序员|开发|设计)|最近在接|也能安排|优惠价格|\d+(\.\d+)?\s*元起|我是.{0,20}(公司|工作室)|一家.{0,8}(公司|工作室)|全流程我一个人|做软件\s*\d+\s*年"
    r"|\bdm (me )?for collab|\bcollab\b|link in bio|available for hire|open for commissions|book a call|use code|i'?m a freelancer",
    re.I,
)
# Someone asking for help in their own voice ("有人接剪辑吗", "谁接代剪", "想找个剪辑老师").
_ASK = re.compile(
    r"有人接.{0,12}(吗|嘛|么)|谁(接|能接|能帮|会做)|急求|求(个|一个|靠谱的?|推荐)?.{0,4}(剪辑|设计师?|开发|代做|老师|师傅)"
    r"|想找(个|一个|位|一位)?|帮我|有人(吗|嘛|会|能)|找(會|会).{0,4}的"
    r"|looking for|need(ed)? (a|an|someone)\b|anyone (know|recommend)|recommend (a|an|me)\b",
    re.I,
)
# A request or a job opening, said either way.
_DEMAND = re.compile(
    r"找人|寻找|找个|找一[个位]|求推荐|求购|求助|预算|询价|外包|采购|定制|有偿|悬赏|需要.{0,10}(制作|开发|设计|剪辑|排版|做|帮)"
    r"|招聘|诚招|急招|招募|招(一|个|人|兼职|写手|设计|开发|工程师|助理|主播|剪辑|实习)"
    r"|\bhiring\b|\bseeking\b|\|\s*(remote|onsite|on-site|hybrid)\b",
    re.I,
)
# Demand strong enough to count as buyer intent without money or urgency.
_STRONG_DEMAND = re.compile(
    r"需要.{0,8}(制作|开发|设计|剪辑|排版)|找人|找个|找一[个位]|求推荐|外包|定制|求购|有偿|悬赏|招聘|诚招|急招|招募|招(一|个|兼职|写手|设计|开发|工程师|实习)"
    r"|\bhiring\b|\|\s*(remote|onsite|on-site|hybrid)\b",
    re.I,
)
# Articles about a topic rather than a request: channel lists, checklists, "how to choose", war stories.
_ADVICE = re.compile(
    r"怎么选|怎么找|去哪(里)?找项目|哪些(渠道|平台)|十大|渠道[！!]?$|平台推荐|常用平台|接单平台|先(写清|问清|搞清)|应该找谁|推荐[:：]"
    r"|\d+\s*(件事|点|大渠道)|\d+\s*个.{0,8}(平台|渠道)|避坑|血泪史|经历|指南|攻略|干货|先(看完|问)这|冤枉钱|省一半钱|靠谱吗",
    re.I,
)
_CONTENT = re.compile(r"怎么做|教程|求教程|有没有人能教|为什么|求方法|经验(分享|总结|贴)|how to|tutorial|\btips\b|why does", re.I)
_MONEY = re.compile(r"预算|报价|多少钱|付费|采购|有偿|\d+(\.\d+)?\s*(元|块|万|k\b|w\b)|[￥$£€]\s?\d+|\bbudget\b|\bpay(ing)?\b|\bquote\b|\brate\b|/hr\b|/hour\b", re.I)
_URGENT = re.compile(r"急|尽快|今天|明天|截止|月底|本周|\basap\b|\burgent\b|\btoday\b|\btomorrow\b|\bdeadline\b|this week", re.I)
# Platform hashtags ("#剪辑接单 #代剪") are SEO, not the poster's own words.
# Asking to be taught is an audience question, not a job ("有没有人能教我…").
_TEACH = re.compile(r"教(我|一下)|求教程|能教|学会|怎么学", re.I)
_HASHTAG = re.compile(r"#[^#\s]{1,30}#?")

# A post that labels itself ("[接单] 全栈开发", "【求职】") is a seller whatever else the title says.
_SELLER_TAG = re.compile(r"^\s*[\[【(（]\s*(接单|承接|自荐|求职|出售)\s*[\]】)）]")

_SELLER_RESULT = Classification(category="seller", reason_code="seller_self_promotion", confidence=0.6, evidence_grade="C")
_ADVICE_RESULT = Classification(category="content", reason_code="advice_or_listicle", confidence=0.66, evidence_grade="B")


_JOB = re.compile(r"招聘|全职|实习|岗位|求职|找工作|月薪|薪资|工资|\bfull[- ]?time\b|\bsalary\b|\bintern(ship)?\b|\bjob (opening|seeker)\b|\bhiring\b", re.I)
_PROJECT = re.compile(r"外包|项目制|付费项目|contract project|project[- ]based|freelance project", re.I)


def classify_tiktok(raw_text: str, *, title: str | None = None, engagement: dict | None = None) -> Classification:
    """Conservatively classify public evidence text from any source; engagement never creates buyer intent.

    A title, when given, is read first: it states what the post is ("[接单] 全栈开发" is a seller
    even if its body mentions 预算). Hashtags are ignored, and demand words inside a seller phrase
    ("接外包") do not count as demand.
    """
    if _JOB.search(f"{title or ''} {raw_text}") and not _PROJECT.search(f"{title or ''} {raw_text}"):
        return Classification("job", "employment_or_job_seeker", .9, "B")
    head = _HASHTAG.sub(" ", (title or "")).strip()
    body = _HASHTAG.sub(" ", raw_text).strip()
    if head and _SELLER_TAG.search(head):
        return _SELLER_RESULT
    if head and _SELLER.search(head) and not _ASK.search(head) and not _DEMAND.search(_SELLER.sub(" ", head)):
        return _SELLER_RESULT
    full = f"{head}\n{body}" if head and head not in body else body
    if _TEACH.search(full):
        return Classification(category="content", reason_code="audience_question_or_howto", confidence=0.72, evidence_grade="B")
    ask = _ASK.search(full)
    if not ask and re.search(r"我们团队(提供|承接)|专业团队|个人承接|专业代做|\bwe (offer|provide)\b", full, re.I):
        return _SELLER_RESULT
    if _ADVICE.search(full) and not ask:
        return _ADVICE_RESULT
    implicit = re.search(r"需要做(?:个|一|一个)|(?:长期合作|寻.{0,5}团队)",full) and re.search(r"项目|站点|网站|开发|制作|比价|小程序|交付|必备要求",full)
    if implicit and not _SELLER.search(full) and not _JOB.search(full):
        return Classification("buyer","implicit_project_request",.7,"B")
    without_seller = _SELLER.sub(" ", full)
    strong = _STRONG_DEMAND.search(without_seller)
    if _SELLER.search(full) and not strong and not ask:
        return _SELLER_RESULT
    if ask or _DEMAND.search(without_seller):
        from .evidence_facts import payment
        from .demand_qualification import qualification
        money = payment(full)["signal"]
        urgency = _URGENT.search(full)
        if ask or money or urgency or strong:
            return Classification(
                category="buyer",
                reason_code="explicit_request_budget_deadline",
                confidence=0.82,
                evidence_grade="A" if money and qualification(full)["actionable_candidate"] else "B",
                payment_signal=money,
                urgency_signal=urgency.group(0) if urgency else None,
            )
    if _CONTENT.search(full):
        return Classification(category="content", reason_code="audience_question_or_howto", confidence=0.72, evidence_grade="B")
    return Classification(category="market", reason_code="content_or_trend_without_buying_intent", confidence=0.58, evidence_grade="C")
