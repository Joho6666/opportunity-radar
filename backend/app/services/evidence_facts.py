"""Extract only source-stated facts; absent amounts and contact details stay unknown."""
import re

_BUDGET = re.compile(r"(?:预算|报价|budget(?:\s+is|\s+of)?)\s*[:：]?\s*(?P<currency>[￥¥$]|USD|CNY)?\s*(?P<low>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>万|[kK])?(?:\s*[-–~至到]\s*[￥¥$]?\s*(?P<high>\d[\d,]*(?:\.\d+)?)\s*(?P<highunit>万|[kK])?)?", re.I)
_DEADLINE = re.compile(r"(?:截止|交付|deadline|by)\s*[:：]?\s*[^，。\n;]{1,50}|本周|明天|今天|月底|this week|tomorrow|today", re.I)


def facts(text: str) -> dict:
    match = _BUDGET.search(text)
    result = {"budget_min": None, "budget_max": None, "currency": None, "budget_evidence": None,
              "deadline": None, "deadline_evidence": None, "contact": None, "delivery_requirements": text[:500]}
    if match:
        unit = {"万":10000,"k":1000,"":1}
        low = float(match["low"].replace(",", "")) * unit.get((match["unit"] or match["highunit"] or "").lower(),1)
        high = float((match["high"] or match["low"]).replace(",", "")) * unit.get((match["highunit"] or match["unit"] or "").lower(),1)
        if low <= high <= 100_000_000:
            result.update(budget_min=int(low),budget_max=int(high),currency="USD" if (match["currency"] or "").upper() in {"$","USD"} else "CNY" if match["currency"] or re.search(r"元|块|人民币",text[match.start():match.end()+4]) else None,budget_evidence=match.group(0))
    deadline = _DEADLINE.search(text)
    if deadline:
        result.update(deadline=deadline.group(0), deadline_evidence=deadline.group(0))
    return result
