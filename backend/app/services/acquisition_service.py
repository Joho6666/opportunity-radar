from datetime import UTC, datetime, timedelta
from ..core.errors import AppError

SALES_STAGES={"verified","ready_to_contact","contacted","replied","quoted","negotiating","won"}


def apply_pipeline(item, patch, evidence=None):
    details=dict(item.pipeline)
    versions=list(details.get("quote_versions",[]))
    events=list(details.get("follow_up_history",[]))
    duplicate=None
    event_is_new=False
    if patch.quote_draft is not None:
        duplicate=next((v for v in versions if patch.quote_request_id and v.get("request_id") == patch.quote_request_id),None)
        if duplicate:
            if duplicate["draft"] != patch.quote_draft:
                raise AppError("QUOTE_REQUEST_CONFLICT","相同请求标识对应不同报价，请刷新后重试。",409)
        else:
            current=int(details.get("quote_version",0))
            if patch.expected_quote_version is not None and patch.expected_quote_version != current:
                raise AppError("QUOTE_VERSION_CONFLICT","报价已更新，请刷新后保存新版本。",409)
            if current == 0 and details.get("quote_draft") and not versions:
                versions.append({"version":0,"request_id":None,"draft":details["quote_draft"],"created_at":None,"source_url":item.source_url,"legacy":True})
            versions.append({"version":current+1,"request_id":patch.quote_request_id,"draft":patch.quote_draft,
                             "created_at":datetime.now(UTC).isoformat(),"source_url":item.source_url})
            details.update(quote_versions=versions,quote_version=current+1)
    if patch.follow_up_event:
        event=patch.follow_up_event.model_dump()
        previous=next((x for x in events if x.get("request_id") == event["request_id"]),None)
        if previous:
            if any(previous.get(key) != value for key,value in event.items()):
                raise AppError("FOLLOW_UP_REQUEST_CONFLICT","相同请求标识对应不同跟进记录。",409)
        event_is_new=previous is None
        if event["quote_version"] is not None and not any(v["version"] == event["quote_version"] for v in versions):
            raise AppError("QUOTE_VERSION_NOT_FOUND","请选择已保存的报价版本。",422)
        if event["kind"] == "quote_sent" and event["quote_version"] is None:
            raise AppError("QUOTE_VERSION_REQUIRED","记录发送报价需关联报价版本。",422)
    status=patch.status or item.status
    verified=patch.verification_status or item.verification_status
    if evidence is not None:
        verified=evidence.verification_status
        if status in SALES_STAGES or (patch.follow_up_event and patch.follow_up_event.kind != "note"):
            from .demand_qualification import require_actionable
            require_actionable(evidence)
        if evidence.category != "buyer":
            verified="disputed"
    elif patch.verification_status == "verified" and not patch.notes:
        raise AppError("VERIFICATION_NOTES_REQUIRED","人工核实需记录依据。",422)
    if status in SALES_STAGES and verified != "verified":
        raise AppError("LEAD_NOT_VERIFIED","请先人工核实买方需求，再推进客户跟进。",409)
    if patch.follow_up_event and patch.follow_up_event.kind != "note" and verified != "verified":
        raise AppError("LEAD_NOT_VERIFIED","请先人工核实，再记录客户沟通与到账。",409)
    if status == "lost" and not (patch.loss_reason or details.get("loss_reason")):
        raise AppError("LOSS_REASON_REQUIRED","请记录流失原因。",422)
    if patch.next_follow_up_at and patch.next_follow_up_at.tzinfo is None:
        raise AppError("FOLLOW_UP_TIMEZONE_REQUIRED","跟进时间必须包含时区。",422)
    values=patch.model_dump(exclude_none=True,mode="json",exclude={"status","verification_status","actual_revenue","actual_hours","clear_follow_up","quote_request_id","expected_quote_version","follow_up_event"})
    if duplicate:values.pop("quote_draft",None)
    details.update(values)
    if patch.clear_follow_up:
        details.pop("next_follow_up_at",None)
    now=datetime.now(UTC).isoformat()
    if event_is_new:
        events.append({**event,"recorded_at":now,"source_url":item.source_url})
        details["follow_up_history"]=events
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
    if request.packages:
        packages=[p.model_dump() for p in request.packages]
    else:
        kind=request.service_type.lower()
        if any(x in kind for x in ("视频","video","广告")):
            deliverables=[["1条主视频、1种画幅、字幕"],["1条主视频、2种画幅、字幕与封面"],["1条主视频、2条短版、3种画幅、字幕与封面"]]
        elif any(x in kind for x in ("小程序","mini app")):
            deliverables=[["小程序核心页面原型、测试说明"],["小程序页面及核心流程、测试与发布准备说明"],["标准范围及后台配置、操作文档与交接"]]
        elif any(x in kind for x in ("网站","开发","website","web","app")):
            deliverables=[["核心页面或流程原型、测试说明"],["核心页面与业务流程实现、部署说明"],["标准范围及管理配置、操作文档与交接"]]
        else:
            deliverables=[["基础排版文件、PDF预览"],["排版与视觉统一、可编辑源文件、PDF预览"],["标准范围及图表优化、演示或使用说明"]]
        packages=[]
        for index,(name,multiplier,revisions) in enumerate([("基础版",1,1),("标准版",1.5,2),("高级版",2,3)]):
            packages.append({"name":name,"quantity":1,"deliverables":deliverables[index],"scope":request.scope+"；"+"、".join(deliverables[index]),
                "estimated_hours":round(request.estimated_hours*multiplier,2),"delivery_days":request.delivery_days+index*2,"revisions":revisions,
                "exclusions":"额外数量、素材购买、第三方服务、超范围修改另行确认；持续维护未包含"})
    plans=[]
    for package in packages:
        hours=package["estimated_hours"]
        amount=round(hours*request.hourly_rate+request.direct_cost,2)
        labor=round(hours*request.internal_hourly_cost,2) if request.internal_hourly_cost is not None else None
        plans.append({**package,"price":amount,"currency":"CNY","direct_cost":request.direct_cost,"labor_cost_estimate":labor,
                      "profit_before_tax":round(amount-request.direct_cost-labor,2) if labor is not None else None})
    now=datetime.now(UTC)
    return {"status":"draft","schema_version":2,"service_type":request.service_type,"source_url":item.source_url,"plans":plans,
            "selling_hourly_rate":request.hourly_rate,"internal_hourly_cost":request.internal_hourly_cost,
            "created_at":now.isoformat(),"valid_until":(now+timedelta(days=request.valid_days)).isoformat(),
            "payment_milestones":[x.model_dump() for x in request.payment_milestones],
            "assumptions":["价格基于本人设定的销售费率与工时；客户预算仍以原文证据为准","套餐数量和工时均为整包，工时应包含全部数量","方案必须人工编辑与审核后发送","税前利润估算扣除直接成本和内部工时成本；内部成本缺失时未知，税费未计入"],
            "ethical_scope":"论文服务仅提供方法辅导、规范修改和格式检查，不代写或伪造数据"}


def outreach_draft(item):
    return (f"你好，看到你在 {item.source_url} 发布的需求：{item.summary[:300]}。"
            "我可以先与你确认交付范围、素材、截止时间和预算，再提供可编辑的方案与报价。"
            "如果需求仍有效，欢迎通过你公开允许的渠道沟通。\n\n[人工审核草案：确认原帖、服务能力和联系渠道后自行发送]")
