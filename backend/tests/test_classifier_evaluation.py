import asyncio
import json
from pathlib import Path
from app.services.evaluate_classifier import evaluate
from app.services.evidence_facts import facts
from app.services.semantic_classifier import enrich_batch
from app.services.evidence_ingest import EvidenceBatch


def test_golden_dataset_reproducible():
    samples=json.loads(Path("tests/fixtures/evidence_golden.json").read_text())
    assert len(samples)>=50
    assert {s["language"] for s in samples} == {"zh","en"}
    report=evaluate(samples)
    assert report == evaluate(samples)
    # This is a fixed regression gate on a synthetic corpus, not a product claim.
    assert report["metrics"]["buyer"]["precision"] >= .8
    assert sum(sum(row.values()) for row in report["confusion_matrix"].values()) == len(samples)


def test_facts_never_fill_absent_budget_or_contact():
    assert facts("急求简历设计，多少钱请报价")["budget_min"] is None
    assert facts("报价1000至2000元，本周交付")["budget_max"] == 2000
    assert facts("预算2万，月底交付")["budget_min"] == 20000
    assert facts("budget $500-800")["currency"] == "USD"
    assert facts("预算2-3万元")["budget_min"] == 20000
    assert facts("预算2000，找人排版")["currency"] is None
    assert facts("need help")["contact"] is None


def test_model_hallucination_falls_back(monkeypatch):
    from app.core.config import Settings
    class Provider:
        async def structured_output_with_usage(self,*args,**kwargs):
            return {"category":"buyer","confidence":.9,"reason":"bad","intent_quote":"invented buyer","payment_quote":"budget $9999"},None
    monkeypatch.setattr("app.services.semantic_classifier.get_settings",lambda:Settings(enable_ai_classification=True,llm_fast_model="cheap"))
    monkeypatch.setattr("app.services.semantic_classifier.get_provider",lambda:Provider())
    batch=EvidenceBatch(batch_id="x",items=[{"source":"rss","url":"https://example.com/x","raw_text":"A public video tutorial example","category":"content"}])
    result=asyncio.run(enrich_batch(batch))
    assert result.items[0].category == "content"
    assert result.items[0].metadata["semantic_fallback"] == "ValueError"
