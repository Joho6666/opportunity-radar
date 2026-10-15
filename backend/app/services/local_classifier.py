"""Optional local SetFit classifier; defaults to shadow, never generates facts."""
import json
import math
from functools import lru_cache
from pathlib import Path
from .evaluate_classifier import CATEGORIES
from ..core.config import get_settings

BASE_MODEL="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
BASE_REVISION="e8f8c211226b894fcb81acc59f3b34ba3efd5f42"


def promotion_allowed(report):
    try:
        if any(not math.isfinite(report[key]) or not 0<=report[key]<=1 for key in ("buyer_precision","buyer_recall","baseline_buyer_recall")):return False
        return (report["dataset_kind"] == "real_holdout" and report["holdout_count"] >= 100
                and report["train_count"] >= 100 and report["validation_count"] >= 50
                and report["true_buyers"] >= 30 and report["predicted_buyers"] >= 30
                and report["buyer_precision"] >= .9 and report["buyer_recall"] >= report["baseline_buyer_recall"]
                and report["group_leakage"] is False)
    except (KeyError,TypeError,ValueError):
        return False


class LocalModel:
    def __init__(self,path):
        from setfit import SetFitModel
        import torch
        torch.set_num_threads(2)
        self.manifest=json.loads((path/"radar_manifest.json").read_text())
        if self.manifest.get("base_model") != BASE_MODEL or self.manifest.get("base_revision") != BASE_REVISION or self.manifest.get("labels") != CATEGORIES:
            raise ValueError("MODEL_MANIFEST_INVALID")
        self.model=SetFitModel.from_pretrained(str(path),local_files_only=True,device="cpu")

    def predict(self,raw):
        body=self.model.model_body
        ids=body.tokenizer.encode(raw,add_special_tokens=False)
        width=min(126,body.max_seq_length-2)
        chunks=[ids[start:start+width] for start in range(0,len(ids),max(1,width-32))] or [[]]
        truncated=len(chunks)>8
        if truncated:chunks=chunks[:4]+chunks[-4:]
        texts=[body.tokenizer.decode(chunk,skip_special_tokens=True) for chunk in chunks]
        rows=self.model.predict_proba(texts,as_numpy=True).tolist()
        if any(len(row) != len(CATEGORIES) or any(not math.isfinite(p) or not 0<=p<=1 for p in row) for row in rows):
            raise ValueError("Invalid local classifier probabilities")
        scores=[sum(row[i] for row in rows)/len(rows) for i in range(len(CATEGORIES))]
        winner=max(range(len(scores)),key=scores.__getitem__)
        return {"category":CATEGORIES[winner],"confidence":round(scores[winner],4),"truncated":truncated,
                "chunk_conflict":len({max(range(len(row)),key=row.__getitem__) for row in rows})>1,
                "promotion_allowed":promotion_allowed(self.manifest.get("evaluation",{}))}


@lru_cache(maxsize=1)
def _load(path,modified):
    return LocalModel(Path(path))


def load_model():
    path=Path(get_settings().local_classifier_path)
    manifest=path/"radar_manifest.json"
    if not get_settings().local_classifier_path or not manifest.is_file():
        raise FileNotFoundError("MODEL_MISSING")
    return _load(str(path.resolve()),manifest.stat().st_mtime_ns)


def enrich_local(batch):
    settings=get_settings()
    if settings.local_classifier_mode == "off":return batch
    try:
        model=load_model()
    except Exception as exc:
        code="MODEL_MISSING" if isinstance(exc,FileNotFoundError) else "DEPENDENCY_MISSING" if isinstance(exc,ImportError) else "MODEL_LOAD_FAILED"
        return batch.model_copy(update={"items":[record.model_copy(update={"metadata":{**record.metadata,"local_fallback":code}}) for record in batch.items]})
    items=[]
    for record in batch.items:
        if record.metadata.get("incremental_known") == "true":items.append(record);continue
        try:
            label=model.predict(record.raw_text)
            conflict=label["category"] != record.category
            review=conflict or label["confidence"] < .8 or label["truncated"] or label["chunk_conflict"]
            active=settings.local_classifier_mode == "active" and label.get("promotion_allowed",False) and not review
            metadata={**record.metadata,"local_category":label["category"],"local_confidence":str(label["confidence"]),
                      "local_mode":"active" if active else "shadow","local_truncated":str(label["truncated"]).lower(),
                      "local_chunk_conflict":str(label["chunk_conflict"]).lower(),
                      "local_promotion_blocked":str(settings.local_classifier_mode == "active" and not active).lower(),
                      "local_disagreement":str(conflict).lower(),"needs_review":"true" if review else record.metadata.get("needs_review","false")}
            updates={"metadata":metadata}
            if active:updates.update(category=label["category"],classification_source="local_setfit",classification_confidence=label["confidence"])
            items.append(record.model_copy(update=updates))
        except Exception:
            items.append(record.model_copy(update={"metadata":{**record.metadata,"local_fallback":"INFERENCE_FAILED","needs_review":"true"}}))
    return batch.model_copy(update={"items":items})
