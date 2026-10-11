from app.repositories.memory import MemoryRepository
from app.services.evidence_ingest import EvidenceBatch, EvidenceInput, evidence_identity


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


def test_identity_namespaces_external_ids():
    a = EvidenceInput(source="github", external_id="123", url="https://example.test/a", raw_text="真实原文足够长，用于身份键测试。")
    b = a.model_copy(update={"source": "hackernews"})
    assert evidence_identity(a) != evidence_identity(b)


def test_duplicate_response_uses_stored_id_and_counts_batch_duplicates():
    repo = MemoryRepository()
    batch = _batch("one")
    repeated = batch.model_copy(update={"items": [batch.items[0], batch.items[0]]})
    first = repo.upsert_evidence_batch("owner", repeated)
    second = repo.upsert_evidence_batch("owner", repeated.model_copy(update={"batch_id": "two"}))
    assert (first.inserted, first.duplicates) == (1, 1)
    assert (second.inserted, second.duplicates) == (0, 2)
    assert first.records[0].evidence_id == second.records[0].evidence_id
    assert first.records[0].evidence_id == repo.list_evidence("owner")[0].evidence_id
