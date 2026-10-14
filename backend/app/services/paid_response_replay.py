"""Pure snapshot replay. Never sends HTTP, writes business data or verifies customers."""
from datetime import datetime
from ..collectors.tikhub_cn import parse_douyin, parse_xiaohongshu, parse_weibo, parse_zhihu
from .evidence_from_raw import raw_items_to_evidence_batch
from .evidence_ingest import normalize_evidence


def replay_response(source: str, payload: dict, query: str, captured_at: datetime, call_id: str) -> list[dict]:
    parsers = {"douyin":parse_douyin,"xiaohongshu":parse_xiaohongshu,"weibo":parse_weibo,"zhihu":parse_zhihu}
    items = parse_weibo(payload,query,now=captured_at) if source == "weibo" else parsers[source](payload,query)
    if not items:
        return []
    batch = raw_items_to_evidence_batch(source=source,query=query,items=items,batch_id=call_id)
    batch = batch.model_copy(update={"items":[item.model_copy(update={"captured_at":captured_at}) for item in batch.items]})
    return [record.model_dump(mode="json") for record in normalize_evidence(batch)]
