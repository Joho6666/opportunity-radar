"""Four free public API requests; no login, paid API, manual verification or outreach.
Run from backend: ../.venv/bin/python ../scripts/live_free_probe.py OUTPUT_JSON
"""
import asyncio
import json
import sys
from datetime import UTC,datetime
from pathlib import Path
from uuid import uuid4
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app.collectors.http import fetcher
from app.collectors.github import GitHubCollector
from app.collectors.hackernews import HackerNewsCollector
from app.core.config import get_settings
from app.database.client import create_database_engine
from app.repositories.postgres import PostgresRepository
from app.schemas.domain import RadarCreate,QueryPlanItem,ProfileUpsert
from app.services.radar_run_service import RadarRunService
from app.services.acquisition_metrics import acquisition_metrics

async def main():
    settings=get_settings()
    if settings.paid_api_enabled:raise RuntimeError("Live probe requires paid API disabled")
    fetcher.retries=0;fetcher.min_interval=1
    uid=str(uuid4());repo=PostgresRepository(create_database_engine())
    repo.save_profile(uid,ProfileUpsert(display_name="真实免费探针（未人工核实）",skills=[{"name":"PPT"},{"name":"video"},{"name":"website"}],goals=["client"]))
    results=[]
    scenarios=[("个人文档",[("hackernews","comments: presentation design"),("github","issues: powerpoint freelancer")]),("企业制作",[("hackernews","comments: video ads"),("github","issues: website freelance")])]
    adapters={"hackernews":HackerNewsCollector(),"github":GitHubCollector()}
    original=fetcher.get_json;shapes=[]
    async def observed(url,**kwargs):
        payload=await original(url,**kwargs)
        shapes.append({"endpoint":url.split("?")[0],"keys":list(payload) if isinstance(payload,dict) else type(payload).__name__,"items_type":type(payload.get("items",payload.get("hits"))).__name__ if isinstance(payload,dict) else None})
        if not isinstance(payload,dict) or not isinstance(payload.get("items",payload.get("hits")),list):raise RuntimeError("Live response contract mismatch")
        return payload
    fetcher.get_json=observed
    for name,queries in scenarios:
        radar=repo.create_radar(uid,RadarCreate(name="免费探针："+name,goal="寻找公开且可追溯的客户需求，不代表已核实客户",sources=[x[0] for x in queries],keywords=["PPT","presentation","video","website","freelance"],freshness_hours=720))
        radar=repo.save_radar(radar.model_copy(update={"status":"paused","queries":[QueryPlanItem(source=source,query=query,priority=50) for source,query in queries]}))
        cache={};probes=[]
        for source,query in queries:
            try:
                items,next_cursor=await adapters[source].search_page(query)
                cache[(source,query)]=(items,None)
                probes.append({"source":source,"query":query,"received":len(items),"next_cursor":next_cursor,"items":[item.model_dump(mode="json") for item in items]})
            except Exception as exc:
                error={"source":source,"error_code":getattr(exc,"code",type(exc).__name__),"message":"公开探针失败，未替换为合成样本"}
                cache[(source,query)]=([],error);probes.append({"source":source,"query":query,"error":error})
        class Recorded:
            async def search(self,source,query):return cache[(source,query)]
        run=await RadarRunService(repo,Recorded()).run(uid,radar.id,repo.create_run(radar.id).id)
        repo.save_radar(repo.get_radar(uid,radar.id).model_copy(update={"status":"paused"}))
        results.append({"name":name,"radar_id":radar.id,"run":run.model_dump(mode="json"),"probes":probes})
    report={"kind":"live-free-public-api-probe","captured_at":datetime.now(UTC).isoformat(),"user_id":uid,"max_network_requests":4,"paid_enabled":False,"response_contracts":shapes,"scenarios":results,"funnel":acquisition_metrics(repo,uid),"limitations":"No human verification, customer contact or sale; buyer labels are predictions only."}
    Path(sys.argv[1]).write_text(json.dumps(report,ensure_ascii=False,indent=2))
    print(json.dumps({"user_id":uid,"response_contracts":shapes,"funnel":report["funnel"]},ensure_ascii=False))
asyncio.run(main())
