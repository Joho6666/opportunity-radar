from ..schemas.domain import RawItem

RULES = {"先交钱": 35, "培训费": 35, "保证金": 30, "私下交易": 20, "日赚过万": 25, "高薪轻松": 20, "内容不详": 10}


def risk_adjustment(item: RawItem) -> tuple[int, list[str]]:
    text = f"{item.title} {item.content}".lower(); matches = [key for key in RULES if key in text]
    return min(60, sum(RULES[key] for key in matches)), [f"检测到风险提示：{key}" for key in matches]
