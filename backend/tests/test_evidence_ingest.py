from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.services.evidence_ingest import EvidenceBatch, normalize_evidence


def test_normalize_evidence_deduplicates_same_external_item():
    batch = EvidenceBatch(
        batch_id="cue-2026-10-11",
        items=[
            {
                "source": "cue",
                "url": "https://example.test/post/1?utm_source=x",
                "external_id": "post-1",
                "raw_text": "预算三千，寻找短视频广告制作服务。",
            },
            {
                "source": "cue",
                "url": "https://example.test/post/1?utm_source=y",
                "external_id": "post-1",
                "raw_text": "预算三千，寻找短视频广告制作服务。",
            },
        ],
    )

    records = normalize_evidence(batch, now=datetime(2026, 10, 11, tzinfo=UTC))

    assert len(records) == 1
    assert records[0].evidence_id
    assert records[0].captured_at.isoformat() == "2026-10-11T00:00:00+00:00"
    assert records[0].verification_status == "unverified"
    assert records[0].classification_source == "unclassified"
    assert records[0].classification_confidence == 0


def test_evidence_requires_verbatim_text_and_http_url():
    with pytest.raises(ValidationError):
        EvidenceBatch(
            batch_id="bad",
            items=[{"source": "cue", "url": "not-a-url", "raw_text": "short"}],
        )
