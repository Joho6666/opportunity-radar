from datetime import UTC, datetime
from ..core.errors import AppError

SALES_STAGES={"verified","ready_to_contact","contacted","replied","quoted","negotiating","won"}


def apply_pipeline(item, patch, evidence=None):
    details=dict(item.pipeline)
    status=patch.status or item.status
    verified=patch.verification_status or item.verification_status
    if evidence is not None:
        verified=evidence.verification_status
        if evidence.category != "buyer":
            verified="disputed"
    elif patch.verification_status == "verified" and not patch.notes:
        raise AppError("VERIFICATION_NOTES_REQUIRED","人工核实需记录依据。",422)
    if status in SALES_STAGES and verified != "verified":
        raise AppError("LEAD_NOT_VERIFIED","请先人工核实买方需求，再推进客户跟进。",409)
    if status == "lost" and not (patch.loss_reason or details.get("loss_reason")):
        raise AppError("LOSS_REASON_REQUIRED","请记录流失原因。",422)
    if patch.next_follow_up_at and patch.next_follow_up_at.tzinfo is None:
        raise AppError("FOLLOW_UP_TIMEZONE_REQUIRED","跟进时间必须包含时区。",422)
    values=patch.model_dump(exclude_none=True,mode="json",exclude={"status","verification_status","actual_revenue","actual_hours","clear_follow_up"})
    details.update(values)
    if patch.clear_follow_up:
        details.pop("next_follow_up_at",None)
    now=datetime.now(UTC).isoformat()
    if status != item.status:
        details.setdefault(f"{status}_at",now)
    # Cumulative stage timestamps survive forward and backward transitions.
    closed_at=item.closed_at
    if status in {"won","lost"} and status != item.status:
        closed_at=datetime.now(UTC)
    return item.model_copy(update={"status":status,"verification_status":verified,"pipeline":details,
        "actual_revenue":patch.actual_revenue if patch.actual_revenue is not None else item.actual_revenue,
        "actual_hours":patch.actual_hours if patch.actual_hours is not None else item.actual_hours,"closed_at":closed_at})


def quote_draft(item, request):
    plans=[]
    for name,multiplier,revisions in [("基础版",1,1),("标准版",1.5,2),("高级版",2,3)]:
        hours=round(request.estimated_hours*multiplier,2)
        amount=round(hours*request.hourly_rate+request.direct_cost,2)
        plans.append({"name":name,"price":amount,"currency":"CNY","estimated_hours":hours,"direct_cost":request.direct_cost,
                      "gross_margin_before_tax":round(amount-request.direct_cost,2),"delivery_days":request.delivery_days,
                      "revisions":revisions,"scope":request.scope,"exclusions":"超出范围、素材购买、额外修改需另行确认"})
    return {"status":"draft","service_type":request.service_type,"source_url":item.source_url,"plans":plans,
            "assumptions":["价格基于人工输入的费率与工时；客户预算仍以原文证据为准","方案必须人工编辑与审核后发送","毛收益未扣除自身人工、税费；不是净利润"],
            "ethical_scope":"论文服务仅提供方法辅导、规范修改和格式检查，不代写或伪造数据"}


def outreach_draft(item):
    return (f"你好，看到你在 {item.source_url} 发布的需求：{item.summary[:300]}。"
            "我可以先与你确认交付范围、素材、截止时间和预算，再提供可编辑的方案与报价。"
            "如果需求仍有效，欢迎通过你公开允许的渠道沟通。\n\n[人工审核草案：确认原帖、服务能力和联系渠道后自行发送]")
