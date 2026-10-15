"""Intent is independent of availability, payment and delivery eligibility."""
import hashlib
import json
import re
from datetime import UTC, datetime
from ..core.errors import AppError
from .evidence_facts import clauses, payment, facts

_CLOSED=re.compile(r"需求.{0,3}(?:已取消|取消了|结束|已完成)|已经找到人|已找到.{0,5}(?:人|团队)|已解决|已成交|不再需要|\b(?:filled|cancelled|canceled|no longer needed|already hired)\b",re.I)
_RISK=re.compile(r"(?:代写|买卖).{0,8}(?:毕业论文|学位论文)|(?:毕业论文|学位论文).{0,8}代写|伪造.{0,6}(?:数据|证明)|刷单|诈骗|\bfake (?:data|reviews)\b|write my (?:thesis|dissertation)",re.I)


def text_digest(raw):
    return hashlib.sha256(raw.encode()).hexdigest()


def qualification(raw, metadata=None):
    closed=next((clause.strip() for clause in clauses(raw) if _CLOSED.search(clause) and not re.search(r"未取消|没有取消|未解决|not (?:filled|cancelled|canceled)",clause,re.I)),None)
    # Only a complete, explicit deadline can prove expiry. Relative/month-only
    # expressions remain unknown; a post's last reply is not a deadline.
    deadline=facts(raw)["deadline"]
    match=re.search(r"(\d{4})[-年/](\d{1,2})[-月/](\d{1,2})",deadline or "")
    expired=False
    if match:
        try:expired=datetime(*map(int,match.groups()),tzinfo=UTC).date()<datetime.now(UTC).date()
        except ValueError:pass
    if expired and not closed:closed=deadline
    risk=next((clause.strip() for clause in clauses(raw) if _RISK.search(clause) and not re.search(r"不代写|拒绝代写|禁止伪造|不伪造",clause)),None)
    paid=payment(raw)
    result={"availability":"closed" if closed else "unknown","availability_quote":closed,
            "payment":paid["state"],"payment_quote":paid["quote"],
            "eligibility":"excluded" if risk else "needs_review","eligibility_quote":risk,
            "reason":"明确截止日期已过期" if expired else "已取消或已完成" if closed else "服务范围不适用" if risk else "有效性和交付能力需人工核实",
            "method":"rule_v3","source_digest":text_digest(raw)}
    try:
        review=json.loads((metadata or {}).get("qualification_review","{}"))
        if review.get("source_digest") == result["source_digest"]:
            for key in ("availability","payment","eligibility"):
                if key in review:result[key]=review[key]
            result["review_notes"]=review.get("notes","")
            result["reviewed_at"]=review.get("reviewed_at")
    except (TypeError,ValueError):
        pass
    if closed:result["availability"]="closed"
    if risk:result["eligibility"]="excluded"
    result["actionable_candidate"]=result["availability"] != "closed" and result["eligibility"] != "excluded"
    return result


def review_updates(record, review):
    updates=review.model_dump(exclude_none=True)
    metadata=dict(record.metadata)
    for key in ("title","summary","budget_min","budget_max"):
        if key in updates:metadata[key]=str(updates.pop(key))
    assessment=updates.pop("assessment",None)
    label_group=updates.pop("label_group",None)
    if label_group is not None:metadata["label_group"]=label_group
    if assessment is not None:
        if not (review.notes or record.notes).strip():
            raise AppError("REVIEW_NOTES_REQUIRED","状态纠正需填写原文核实依据。",422)
        previous=json.loads(metadata.get("qualification_review","{}"))
        if previous.get("source_digest") != text_digest(record.raw_text):previous={}
        metadata["qualification_review"]=json.dumps({**previous,**assessment,"notes":review.notes or record.notes,"reviewed_at":datetime.now(UTC).isoformat(),"source_digest":text_digest(record.raw_text)},ensure_ascii=False)
    updated=record.model_copy(update={**updates,"metadata":metadata})
    if updated.verification_status == "verified" and not updated.assessment["actionable_candidate"]:
        raise AppError("DEMAND_NOT_ACTIONABLE","原文需求已关闭或服务不适用，不能标记为有效客户。",409)
    if review.category is not None or review.verification_status == "verified":
        metadata["human_label_digest"]=text_digest(record.raw_text)
        metadata["human_label_at"]=datetime.now(UTC).isoformat()
    return updated


def require_actionable(evidence):
    if not evidence.assessment["actionable_candidate"]:
        raise AppError("DEMAND_NOT_ACTIONABLE","原文需求已关闭或服务不适用。",409)
