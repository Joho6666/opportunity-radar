from app.repositories.memory import MemoryRepository
from app.services.evidence_ingest import EvidenceBatch


def _batch(batch_id: str) -> EvidenceBatch:
    return EvidenceBatch(
        batch_id=batch_id,
        items=[
            {
                "source": "cue",
                "url": "https://example.test/buyer-1",
                "external_id": "buyer-1",
                "raw_text": "预算三千，寻找 AI 视频广告制作。",
                "category": "buyer",
                "payment_signal": "预算三千",
            },
            {
                "source": "cue",
                "url": "https://example.test/content-1",
                "external_id": "content-1",
                "raw_text": "很多商家不知道如何持续生产广告素材。",
                "category": "content",
            },
        ],
    )


def test_memory_evidence_upsert_is_idempotent_across_repeated_batches():
    repository = MemoryRepository()

    first = repository.upsert_evidence_batch("user-1", _batch("batch-1"))
    second = repository.upsert_evidence_batch("user-1", _batch("batch-2"))

    assert first.inserted == 2
    assert first.duplicates == 0
    assert second.inserted == 0
    assert second.duplicates == 2
    assert len(repository.list_evidence("user-1")) == 2
    assert len(repository.list_evidence("user-1", category="buyer")) == 1
    assert repository.list_evidence("user-2") == []
