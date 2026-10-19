"""Versioned optional controls stored in existing source_config; legacy radars unchanged."""
from datetime import datetime, timedelta
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class HuntConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    regions: list[str] = Field(default_factory=list, max_length=10)
    roles: list[Literal["电商商家", "品牌方", "实体店", "创业者", "代运营工作室"]] = Field(default_factory=list, max_length=5)
    intents: list[Literal["找人制作", "咨询方案", "长期合作"]] = Field(default_factory=list, max_length=3)
    match_mode: Literal["local", "remote", "keep_unknown"] = "remote"
    start_at: datetime | None = None
    end_at: datetime | None = None

    @model_validator(mode="after")
    def bounded(self):
        if any(not region.strip() or len(region)>20 for region in self.regions):
            raise ValueError("地区为1–20字，最多10个")
        if bool(self.start_at) != bool(self.end_at):
            raise ValueError("自定义时间需要起止时间")
        if self.start_at and self.end_at:
            if not self.start_at.tzinfo or not self.end_at.tzinfo or not self.start_at < self.end_at or self.end_at-self.start_at > timedelta(days=30):
                raise ValueError("自定义时间须含时区，结束晚于开始，跨度最多30天")
        return self
