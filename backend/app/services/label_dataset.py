"""Tenant-reviewed labels; grouped deterministic splits with no synthetic padding."""
import hashlib
import re
from collections import defaultdict
from .evaluate_classifier import CATEGORIES, evaluate
from .evidence_classifier import classify_tiktok


def content_group(text):
    return hashlib.sha256(re.sub(r"\s+","",text).lower().encode()).hexdigest()


def partition(rows):
    groups=defaultdict(list)
    aliases={}
    # Merge explicit origin groups and identical text; preserve these units in splits.
    def root(key):
        aliases.setdefault(key,key)
        while aliases[key] != key:
            aliases[key]=aliases[aliases[key]];key=aliases[key]
        return key
    for row in rows:
        if row.get("human_label") is not True or row.get("dataset_kind","real") != "real" or row.get("category") not in CATEGORIES:
            raise ValueError("Only explicitly human-labelled real evidence is eligible")
        a,b=root(row["group_id"]),root("text:"+content_group(row["text"]))
        aliases[b]=a
        if row.get("source_url"):
            aliases[root("url:"+row["source_url"])]=a
    for row in rows:groups[root(row["group_id"])].append(row)
    units=sorted(groups.values(),key=lambda unit:(min(row.get("published_at") or row.get("captured_at") or "" for row in unit),min(row["id"] for row in unit)))
    result={"train":[],"validation":[],"holdout":[]}
    for unit in units:
        target="train" if len(result["train"])<100 else "validation" if len(result["validation"])<50 else "holdout"
        result[target].extend(sorted(unit,key=lambda row:row["id"]))
    return result


def split_leakage(splits):
    owners={}
    for name,rows in splits.items():
        for row in rows:
            keys=["id:"+row["id"],"group:"+row["group_id"],"text:"+content_group(row["text"])]
            if row.get("source_url"):keys.append("url:"+row["source_url"])
            for key in keys:
                if key in owners and owners[key] != name:return True
                owners[key]=name
    return False


def comparison(holdout,local_predict,train_count,validation_count,splits=None):
    baseline=evaluate(holdout)
    predictions={row["id"]:local_predict(row["text"]) for row in holdout}
    # evaluate accepts the classifier signature used by the existing rules.
    from types import SimpleNamespace
    by_text={row["text"]:predictions[row["id"]] for row in holdout}
    model=evaluate(holdout,classifier=lambda text,**_:SimpleNamespace(category=by_text[text]["category"]))
    buyer=model["metrics"]["buyer"]
    gate={"dataset_kind":"real_holdout","holdout_count":len(holdout),"train_count":train_count,"validation_count":validation_count,
          "true_buyers":buyer["support"],"predicted_buyers":sum(row["buyer"] for row in model["confusion_matrix"].values()),
          "buyer_precision":buyer["precision"],"buyer_recall":buyer["recall"],"baseline_buyer_recall":baseline["metrics"]["buyer"]["recall"],"group_leakage":split_leakage(splits) if splits else None}
    for report in (baseline,model):report["dataset"]="human-labelled real holdout; sparse class support is not a production estimate"
    from .local_classifier import promotion_allowed
    return {"baseline":baseline,"local":model,"gate":gate,"promotion_allowed":promotion_allowed(gate),
            "review_ratio":sum(predictions[r["id"]]["confidence"]<.8 or predictions[r["id"]]["truncated"] or predictions[r["id"]]["chunk_conflict"] or predictions[r["id"]]["category"] != classify_tiktok(r["text"]).category for r in holdout)/len(holdout) if holdout else None,
            "fact_errors":"requires separate human-labelled facts; not measured"}
