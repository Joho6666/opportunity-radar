"""Versioned optional controls stored in existing source_config; legacy radars unchanged."""
from datetime import datetime, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

HUNT_ROLE_PRESETS = (
    "电商商家", "品牌方", "实体店", "创业者", "代运营工作室",
    "市场团队", "培训机构", "学生", "自由职业", "自媒体",
)


class HuntConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regions: list[str] = Field(default_factory=list, max_length=10)
    roles: list[str] = Field(default_factory=list, max_length=12)
    intents: list[Literal["找人制作", "询价报价", "咨询方案", "长期合作"]] = Field(default_factory=list, max_length=4)
    match_mode: Literal["local", "remote", "keep_unknown"] = "remote"
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def bounded(self):
        if any(not region.strip() or len(region)>20 for region in self.regions):
            raise ValueError("地区为1–20字，最多10个")
        if any(len(role.strip()) < 2 or len(role.strip()) > 20 for role in self.roles):
            raise ValueError("角色为2–20字，最多12个")
        if bool(self.start_at) != bool(self.end_at):
            raise ValueError("自定义时间需要起止时间")
        if self.start_at and self.end_at:
            if not self.start_at.tzinfo or not self.end_at.tzinfo or not self.start_at < self.end_at or self.end_at-self.start_at > timedelta(days=30):
                raise ValueError("自定义时间须含时区，结束晚于开始，跨度最多30天")
        return self
