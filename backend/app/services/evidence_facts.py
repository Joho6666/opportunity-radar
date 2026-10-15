"""Source-stated amounts and temporal phrases only; unknown is never zero."""
import re

_BUDGET = re.compile(r"(?:预算|报价|报酬|费用|budget(?:\s+is|\s+of)?|compensation)\s*[:：]?\s*(?P<currency>[￥¥$]|USD|CNY)?\s*(?P<low>\d[\d,]*(?:\.\d+)?)\s*(?P<unit>万|[kK])?(?:\s*[-–~至到]\s*[￥¥$]?\s*(?P<high>\d[\d,]*(?:\.\d+)?)\s*(?P<highunit>万|[kK])?)?(?P<open>\s*[+＋]|\s*以上)?", re.I)
_TIME = r"(?:\d{4}[-年/]\d{1,2}[-月/]\d{1,2}日?|\d{1,2}月\d{1,2}日|\d+\s*(?:天|周|小时|days?|weeks?)内?|本周|下周|明天|今天|月底|this week|next week|tomorrow|today|\d{1,2}:\d{2})"
_DEADLINE = re.compile(r"(?:截止|交付|deadline|by)\s*[:：]?\s*(?:在|于)?\s*"+_TIME+r"|本周|下周|明天|今天|月底|this week|next week|tomorrow|today",re.I)
_MONEY = re.compile(r"预算|报价|报酬|付费|有偿|悬赏|\d+(?:\.\d+)?\s*(?:元|块|万)|[￥$£€]\s?\d+|\bbudget\b|\bpay(?:ing)?\b|\bquote\b",re.I)
_UNKNOWN = re.compile(r"(?:还没|尚未|未|没|不).{0,6}(?:确定|定|明确).{0,4}预算|预算.{0,5}(?:待定|未知|未定|待沟通|没确定)|budget.{0,12}(?:unknown|undecided|not set)",re.I)
_NO_BUDGET = re.compile(r"无预算|没有预算|不付费|免费帮|白嫖|\bno budget\b|\bunpaid\b|for free",re.I)


def clauses(text):
    return re.split(r"[，。！？；\n!?;]",text)


def payment(text):
    positives=[]; unknown=[]; unpaid=[]
    for clause in clauses(text):
        match=_MONEY.search(clause)
        if _NO_BUDGET.search(clause):
            unpaid.append(clause.strip())
        elif _UNKNOWN.search(clause) or re.search(r"(?:不是|并非|not)\s*(?:预算)?\s*[￥$]?\d+",clause,re.I):
            unknown.append(clause.strip())
        elif match:
            positives.append((match.group(0),clause.strip()))
    state="conflicting" if positives and (unpaid or unknown) else "no_budget" if unpaid else "unknown" if unknown or not positives else "explicit"
    return {"state":state,"signal":positives[0][0] if state == "explicit" else None,
            "quote":(positives[0][1] if positives else (unpaid or unknown or [None])[0])}


def facts(text):
    result={"budget_min":None,"budget_max":None,"budget_bound":None,"currency":None,"budget_evidence":None,
            "deadline":None,"deadline_evidence":None,"contact":None,"delivery_requirements":text[:500]}
    state=payment(text)
    if state["state"] == "explicit":
        match=_BUDGET.search(text)
        if match:
            unit={"万":10000,"k":1000,"":1}
            low=float(match["low"].replace(",",""))*unit.get((match["unit"] or match["highunit"] or "").lower(),1)
            high=float((match["high"] or match["low"]).replace(",",""))*unit.get((match["highunit"] or match["unit"] or "").lower(),1)
            if low <= high <= 100_000_000:
                currency="USD" if (match["currency"] or "").upper() in {"$","USD"} else "CNY" if match["currency"] or re.search(r"元|块|人民币",text[match.start():match.end()+4]) else None
                result.update(budget_min=int(low),budget_max=None if match["open"] else int(high),budget_bound="lower" if match["open"] else "range" if match["high"] else "exact",currency=currency,budget_evidence=match.group(0))
    deadline=_DEADLINE.search(text)
    if deadline:
        result.update(deadline=deadline.group(0),deadline_evidence=deadline.group(0))
    return result
