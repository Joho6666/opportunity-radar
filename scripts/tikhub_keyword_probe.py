"""The authorized four first pages and optional continuation, via the local API.

No API key is handled here. The server owns all pricing, authorization and caps.
Run with --execute only after confirming official endpoint prices. Re-running
uses deterministic request identities; it cannot pay again for a completed call.
"""
import argparse
import json
import uuid
from pathlib import Path
import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output",type=Path)
    parser.add_argument("--execute",action="store_true")
    args = parser.parse_args()
    probes = [("xiaohongshu","找人做PPT"),("weibo","求助 Word排版"),("douyin","找人剪视频"),("xiaohongshu","找人开发小程序")]
    with httpx.Client(base_url="http://127.0.0.1:8013",timeout=120,trust_env=False) as client:
        runtime = client.get("/api/intelligence/evidence/runtime").raise_for_status().json()
        report = {"kind":"bounded-tikhub-probe","billing_batch_id":runtime.get("billing_batch_id"),"executed":False,"calls":[],"blocking_reason":None}
        def save():
            report["billing"] = client.get("/api/billing/status").raise_for_status().json()
            report["funnel"] = client.get("/api/dashboard/acquisition").raise_for_status().json()
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
        if not args.execute or not runtime["paid_api_enabled"] or any(not runtime["sources"][source].get("estimated_request_cost_usd") for source,_ in probes):
            report["blocking_reason"] = "Real calls disabled or official tariffs missing; no TikHub requests made."
            save();print(report["blocking_reason"]);return
        batch = runtime["billing_batch_id"]
        if not batch:
            raise SystemExit("Cumulative batch required")
        report["executed"] = True
        first_cursor = None
        for index in range(5):
            if index == 4:
                if not first_cursor:break
                source,query = probes[0];cursor=first_cursor
            else:
                source,query = probes[index];cursor=None
            request_id=str(uuid.uuid5(uuid.NAMESPACE_URL,f"{batch}:{index}:{source}:{query}"))
            response=client.post("/api/intelligence/evidence/collect",params={"source":source,"query":query,"max_age_days":30},json={"manual_confirmed":True,"request_id":request_id,"billing_batch_id":batch,"cursor":cursor})
            result=response.json()
            report["calls"].append({"source":source,"query":query,"request_id":request_id,"status":response.status_code,"result":result})
            if index == 0 and response.is_success:first_cursor=result.get("next_cursor")
            save()
            if not response.is_success:break
        save();print({"calls":len(report["calls"]),"billing":report["billing"]["batch"]})


if __name__ == "__main__":
    main()
