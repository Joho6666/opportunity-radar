"""Explainable ranking, never a calibrated probability or a source-stated fact."""
from datetime import UTC, datetime


def priority(evidence, *, skills=(), minimum_budget=0, published_at=None, estimated_hours=None, competition=None):
    import json
    facts=json.loads(evidence.metadata.get("facts","{}"))
    text=evidence.raw_text.lower()
    fit=min(100,sum(30 for skill in skills if skill.lower() in text)) if skills else 50
    amount=facts.get("budget_max")
    budget=50 if amount is None or facts.get("currency") != "CNY" else 90 if amount >= minimum_budget else 20
    if published_at and published_at.tzinfo is None:published_at=published_at.replace(tzinfo=UTC)
    age=(datetime.now(UTC)-published_at).total_seconds()/3600 if published_at else None
    confidence={"A":90,"B":65,"C":35}.get(evidence.evidence_grade,35)
    dimensions={
        "需求明确程度":(85 if evidence.category == "buyer" else 20,"分类预测；需人工确认交付范围",.2),
        "预算匹配":(budget,"预算未知或币种未确认" if amount is None or facts.get("currency") != "CNY" else f"原文预算 {amount} CNY；个人最低预算 {minimum_budget}",.15),
        "交付能力匹配":(fit,"按技能词匹配，未验证实际能力",.2),
        "竞争程度":(50 if competition is None else max(0,100-competition),"未知，使用中性分" if competition is None else "模型/人工预测，非平台事实",.1),
        "预计工作量":(50 if estimated_hours is None else max(0,100-estimated_hours*3),"工时未知，需人工估算" if estimated_hours is None else f"人工/模型估算 {estimated_hours} 小时",.1),
        "需求紧急程度":(80 if evidence.urgency_signal else 50,"原文时效线索；未出现具体日期不能推算" if evidence.urgency_signal else "紧急程度未知",.1),
        "证据可信度":(confidence,evidence.evidence_grade+" 级证据；"+("发布时间未知" if age is None else f"来源活动距今 {max(0,age):.0f} 小时"),.15),
    }
    score=round(sum(value*weight for value,_,weight in dimensions.values()))
    return {"kind":"prediction","score":score,"verification":evidence.verification_status,"factors":{name:{"score":value,"reason":reason,"weight":weight} for name,(value,reason,weight) in dimensions.items()},"reasons":[f"{name} {value:.0f}/100：{reason}" for name,(value,reason,_) in dimensions.items()]}
