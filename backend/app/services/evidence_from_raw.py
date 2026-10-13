from __future__ import annotations

from ..schemas.domain import RawItem
from .evidence_classifier import classify_tiktok
from .evidence_ingest import EvidenceBatch


def raw_items_to_evidence_batch(*, source: str, query: str, items: list[RawItem], batch_id: str) -> EvidenceBatch:
    evidence = []
    for item in items:
        title = (item.title or "").strip()
        body = (item.content or "").strip()
        # Keep the title with the text: for forum and RSS posts it often carries the request itself.
        raw_text = f"{title}\n{body}" if title and body and title[:40] not in body else (body or title)
        classification = classify_tiktok(body or title, title=title, engagement=item.engagement)
        metadata = {str(key): str(value) for key, value in (item.metadata or {}).items() if value is not None}
        metadata["engagement"] = str(item.engagement or {})
        evidence.append({
            "source": source,
            "source_platform": item.platform or "",
            "acquisition_tool": metadata.get("acquisition_tool", source),
            "url": item.url,
            "raw_text": raw_text,
            "query": query,
            "external_id": item.external_id,
            "published_at": item.published_at,
            "category": classification.category,
            "payment_signal": classification.payment_signal,
            "urgency_signal": classification.urgency_signal,
            "metadata": metadata,
            "evidence_grade": classification.evidence_grade,
            "classification_source": "rule_v1",
            "classification_reason": classification.reason_code,
            "classification_confidence": classification.confidence,
        })
    return EvidenceBatch(batch_id=batch_id, items=evidence)
