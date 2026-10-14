"""Train/evaluate from a frozen, human-labelled export. Never collects or sends text.

Usage (from backend): ../.venv/bin/python ../scripts/train_local_classifier.py labels.json model-dir
First use downloads only the pinned public base weights. It does not call inference APIs.
"""
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app.services.label_dataset import partition, comparison
from app.services.local_classifier import BASE_MODEL,BASE_REVISION,LocalModel
from app.services.evaluate_classifier import CATEGORIES


def main():
    source,destination=map(Path,sys.argv[1:3])
    rows=json.loads(source.read_text())
    if isinstance(rows,dict):rows=rows["rows"]
    splits=partition(rows)
    counts={key:len(value) for key,value in splits.items()}
    if counts["train"]<100 or counts["validation"]<50 or counts["holdout"]<100:
        raise SystemExit("Insufficient real labels: "+json.dumps(counts)+"; remain in shadow mode")
    if any(sum(row["category"] == label for row in splits["train"])<5 for label in CATEGORIES):
        raise SystemExit("Training requires at least 5 real examples of each class")
    if destination.exists():raise SystemExit("Use a new model directory; frozen dataset/model versions are never overwritten")
    from datasets import Dataset
    from setfit import SetFitModel,Trainer,TrainingArguments
    import torch
    torch.set_num_threads(2)
    def dataset(name):return Dataset.from_list([{"text":r["text"],"label":CATEGORIES.index(r["category"])} for r in splits[name]])
    model=SetFitModel.from_pretrained(BASE_MODEL,revision=BASE_REVISION,device="cpu",labels=CATEGORIES)
    trainer=Trainer(model=model,args=TrainingArguments(output_dir=str(destination/"checkpoints"),seed=42,num_epochs=1,batch_size=8,report_to="none"),train_dataset=dataset("train"),eval_dataset=dataset("validation"))
    trainer.train()
    destination.mkdir(parents=True,exist_ok=True)
    model.save_pretrained(str(destination))
    manifest={"base_model":BASE_MODEL,"base_revision":BASE_REVISION,"labels":CATEGORIES,
              "dataset_digest":hashlib.sha256(source.read_bytes()).hexdigest(),"counts":counts,"seed":42,"evaluation":{}}
    (destination/"radar_manifest.json").write_text(json.dumps(manifest,indent=2))
    (destination/"frozen_splits.json").write_text(json.dumps(splits,ensure_ascii=False,indent=2))
    loaded=LocalModel(destination)
    report=comparison(splits["holdout"],loaded.predict,counts["train"],counts["validation"],splits=splits)
    manifest["evaluation"]=report["gate"]
    (destination/"radar_manifest.json").write_text(json.dumps(manifest,indent=2))
    (destination/"evaluation.json").write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({"counts":counts,"promotion_allowed":report["promotion_allowed"],"directory":str(destination)},ensure_ascii=False))


if __name__ == "__main__":main()
