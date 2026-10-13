"""Replay saved live API responses after a fix; no new network requests."""
import sys,json,asyncio
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"backend"))
from app.database.client import create_database_engine
from app.repositories.postgres import PostgresRepository
from app.schemas.domain import RawItem
from app.services.radar_run_service import RadarRunService
from app.services.acquisition_metrics import acquisition_metrics
async def main():
    path=Path(sys.argv[1]);report=json.loads(path.read_text());repo=PostgresRepository(create_database_engine());uid=report["user_id"]
    for scenario in report["scenarios"]:
        recorded={(p["source"],p["query"]):([RawItem.model_validate(x) for x in p.get("items",[])],p.get("error")) for p in scenario["probes"]}
        class Saved:
            async def search(self,source,query):return recorded[(source,query)]
        run=await RadarRunService(repo,Saved()).run(uid,scenario["radar_id"],repo.create_run(scenario["radar_id"]).id)
        scenario["replay_after_fix"]=run.model_dump(mode="json")
        repo.save_radar(repo.get_radar(uid,scenario["radar_id"]).model_copy(update={"status":"paused"}))
    report["funnel"]=acquisition_metrics(repo,uid);report["replay_note"]="Saved real responses replayed locally; zero additional HTTP calls."
    path.write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps(report["funnel"],ensure_ascii=False))
asyncio.run(main())
