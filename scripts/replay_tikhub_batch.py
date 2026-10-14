"""Read and replay only one batch's saved responses. No network or business writes.

Run from backend, optionally --labels /path/to/reference-labels.json. Labels are
{id,category,split} with split=development|holdout, keyed by evidence_id.
"""
import argparse
import json
import sys
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from sqlalchemy import text
from app.core.config import get_settings
from app.database.client import create_database_engine
from app.services.paid_response_replay import replay_response
from app.services.evaluate_classifier import evaluate


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("--labels",type=Path)
    args = parser.parse_args()
    batch = get_settings().paid_batch_id
    if not batch:
        raise SystemExit("PAID_BATCH_ID is required; refusing to read other batches")
    with create_database_engine().connect() as conn:
        snapshots = conn.execute(text("SELECT c.id,c.source,p.query,p.payload,p.status_code,p.captured_at FROM provider_responses p JOIN billing_calls c ON c.id=p.call_id WHERE c.batch_id=:batch AND c.user_id=CAST(:uid AS uuid) ORDER BY p.captured_at"), {"batch":batch,"uid":get_settings().local_user_id}).mappings().all()
    records, errors = [], []
    for row in snapshots:
        try:
            if row["status_code"] != 200:
                errors.append({"call_id":str(row["id"]),"status_code":row["status_code"]})
                continue
            records.extend(replay_response(row["source"],row["payload"],row["query"] or "",row["captured_at"],str(row["id"])))
        except Exception as exc:
            errors.append({"call_id":str(row["id"]),"error_code":getattr(exc,"code",type(exc).__name__)})
    unique = {record["evidence_id"]:record for record in records}
    reports = {}
    if args.labels:
        labels = json.loads(args.labels.read_text())
        if len({label["id"] for label in labels}) != len(labels):
            raise SystemExit("Duplicate reference labels")
        if any(label["id"] not in unique or label["split"] not in {"development","holdout"} for label in labels):
            raise SystemExit("Labels must reference captured evidence and declare development/holdout")
        for split in ("development","holdout"):
            samples = [{"id":label["id"],"text":unique[label["id"]]["raw_text"],"title":unique[label["id"]]["metadata"].get("raw_title"),"category":label["category"]} for label in labels if label["split"] == split]
            if samples:
                reports[split] = {**evaluate(samples),"dataset":"reference labels on captured public text; "+split,"sufficient_for_accuracy_claim":False}
    report = {"kind":"offline-response-replay","batch_id":batch,"network_requests":0,"business_writes":0,"snapshots":len(snapshots),"unique_evidence":len(unique),"category_counts":dict(Counter(record["category"] for record in unique.values())),"errors":errors,"evaluation":reports or None,"records":list(unique.values()),"limitations":"No human verification, contact or sales. Unlabelled predictions are not accuracy measurements."}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print({key:report[key] for key in ("snapshots","unique_evidence","category_counts","errors")})


if __name__ == "__main__":
    main()
