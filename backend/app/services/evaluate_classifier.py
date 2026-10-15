import json
from pathlib import Path
from .evidence_classifier import classify_tiktok

CATEGORIES = ["buyer", "seller", "job", "content", "market"]


def evaluate(samples, classifier=classify_tiktok):
    matrix={label:{prediction:0 for prediction in CATEGORIES} for label in CATEGORIES}
    errors=[]
    for sample in samples:
        prediction=classifier(sample["text"],title=sample.get("title")).category
        matrix[sample["category"]][prediction]+=1
        if prediction != sample["category"]:
            errors.append({"id":sample["id"],"expected":sample["category"],"predicted":prediction})
    metrics={}
    for label in CATEGORIES:
        tp=matrix[label][label]
        count=sum(matrix[label].values())
        predicted=sum(row[label] for row in matrix.values())
        precision=tp/predicted if predicted else 0
        recall=tp/count if count else 0
        metrics[label]={"precision":round(precision,4),"recall":round(recall,4),"f1":round(2*precision*recall/(precision+recall),4) if precision+recall else 0,"support":count}
    return {"dataset":"synthetic bilingual v1; not a live accuracy estimate", "samples":len(samples),"metrics":metrics,"confusion_matrix":matrix,"errors":errors}


if __name__ == "__main__":
    samples=json.loads(Path("tests/fixtures/evidence_golden.json").read_text())
    print(json.dumps(evaluate(samples),ensure_ascii=False,indent=2))
