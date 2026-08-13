from fastapi import APIRouter
from pydantic import BaseModel
router = APIRouter(prefix="/api/skills", tags=["Skills"])
class SkillRead(BaseModel): id: str; name: str; description: str
@router.get("", response_model=list[SkillRead])
async def skills(): return [SkillRead(id=f"skill-{index}", name=name, description=f"帮助你持续发现{name.replace('雷达','机会')}") for index,name in enumerate(["求职雷达","客户雷达","GitHub 项目雷达","商机雷达","本地需求雷达"])]
