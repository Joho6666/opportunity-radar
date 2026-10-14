from datetime import UTC, datetime
from collections import Counter, defaultdict


def acquisition_metrics(repo,user_id):
    # Repository reads are tenant-scoped; source health is not used as customer evidence.
    evidence=repo.list_evidence(user_id,limit=100000)
    items=[x for x in repo.list_opportunities(user_id) if x.type != "job"]
    today=datetime.now(UTC).date()
    collection=repo.collection_counts(user_id)
    buyer=[x for x in evidence if x.category == "buyer" and x.verification_status != "invalidated"]
    verified=[x for x in buyer if x.verification_status == "verified"]
    contactable=[x for x in items if x.verification_status == "verified" and x.status == "ready_to_contact"]
    counts=Counter(x.status for x in items)
    def reached(stage):
        return sum(bool(x.pipeline.get(f"{stage}_at")) or x.status == stage for x in items)
    contacted,replied,quoted,won=[reached(stage) for stage in ("contacted","replied","quoted","won")]
    income=[x.actual_revenue for x in items if x.actual_revenue is not None]
    source=defaultdict(lambda:{"evidence":0,"buyer":0,"verified_buyer":0})
    for record in evidence:
        row=source[record.source];row["evidence"]+=1
        if record in buyer:row["buyer"]+=1
        if record in verified:row["verified_buyer"]+=1
    for name, stats in collection.get("sources",{}).items():
        source[name].update(stats)
    for row in source.values():
        row.setdefault("collected",0)
        row["buyer_ratio"]=round(row["buyer"]/row["evidence"],4) if row["evidence"] else None
    return {"measurement":"tenant records; counts are unique evidence and recorded stage timestamps; day boundary UTC",
            "today_unique_evidence":sum(x.captured_at.astimezone(UTC).date() == today for x in evidence),
            "collected":collection["collected"],"today_collected":collection["today"],"effective_evidence":sum(x.verification_status != "invalidated" for x in evidence),
            "buyer_evidence":len(buyer),"verified_buyer":len(verified),"contactable":len(contactable),
            "contacted":contacted,"replied":replied,"quoted":quoted,"won":won,
            "reply_rate":round(replied/contacted,4) if contacted else None,
            "quote_rate":round(quoted/replied,4) if replied else None,
            "win_rate":round(won/quoted,4) if quoted else None,
            "actual_revenue":sum(income) if income else None,"pipeline_counts":dict(counts),"source_yield":dict(source)}
