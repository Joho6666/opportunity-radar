import asyncio
from app.core.config import get_settings
from app.services.evidence_ingest import EvidenceBatch
from app.services.semantic_classifier import enrich_batch


def sample():
    return EvidenceBatch(batch_id="local-test",items=[{"source":"rss","url":"https://example.com/request","raw_text":"需要做个企业网站，找人帮我。","category":"buyer"}])


def test_missing_local_model_is_visible_without_paid_provider(monkeypatch):
    settings=get_settings()
    monkeypatch.setitem(settings.__dict__,"local_classifier_mode","shadow")
    monkeypatch.setitem(settings.__dict__,"local_classifier_path","/nonexistent/offline-model")
    result=asyncio.run(enrich_batch(sample()))
    assert result.items[0].category == "buyer"
    assert result.items[0].metadata.get("local_fallback") == "MODEL_MISSING"


def test_shadow_prediction_cannot_change_facts_or_verify_customer(monkeypatch):
    import app.services.local_classifier as local
    monkeypatch.setattr(get_settings(),"local_classifier_mode","shadow")
    class Model:
        def predict(self,text):return {"category":"seller","confidence":.91,"truncated":True,"chunk_conflict":False}
    monkeypatch.setattr(local,"load_model",lambda:Model())
    result=asyncio.run(enrich_batch(sample())).items[0]
    assert result.category == "buyer"
    assert result.metadata["local_category"] == "seller"
    assert result.metadata["needs_review"] == "true"
    assert result.payment_signal is None


def test_promotion_requires_real_holdout_support_and_comparison():
    from app.services.local_classifier import promotion_allowed
    report={"dataset_kind":"real_holdout","holdout_count":100,"true_buyers":30,"predicted_buyers":30,
            "buyer_precision":.9,"buyer_recall":.8,"baseline_buyer_recall":.8,"group_leakage":False,"train_count":100,"validation_count":50}
    assert promotion_allowed(report)
    for patch in ({"dataset_kind":"synthetic"},{"true_buyers":29},{"predicted_buyers":29},{"buyer_precision":.89},{"buyer_recall":.79},{"group_leakage":True}):
        assert not promotion_allowed({**report,**patch})
