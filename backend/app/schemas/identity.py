"""个人身份设定（Local Edition 业务画像）。

只描述公开经营角色与交付偏好：不含年龄、收入、性别等敏感属性，也不做任何推断。
一次保存后作为抓单默认值参与后端筛选（角色/地区/排除词/业务匹配词）。
"""
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .domain import SourceSlug

ALLOWED_SOURCES = set(get_args(SourceSlug))
# 与 lib/lead-hunt.ts 的 BUSINESS_PRESETS 保持同一组 id / 名称。
IDENTITY_BUSINESS_PRESETS = [
    {"id": "video", "name": "AI 电商视频 / 广告", "remote_deliverable": True, "match_words": ["电商", "商品", "带货", "广告", "产品视频", "信息流", "视频素材", "亚马逊", "AI视频", "视频生成"]},
    {"id": "drama", "name": "视频复刻 / AI 短剧", "remote_deliverable": True, "match_words": ["复刻", "短剧", "视频", "AI剧"]},
    {"id": "web", "name": "小程序 / 网站轻开发", "remote_deliverable": False, "match_words": ["小程序", "网站", "网页", "落地页", "官网"]},
    {"id": "office", "name": "PPT / Word / Excel", "remote_deliverable": True, "match_words": ["PPT", "Word", "Excel", "演示文稿", "表格", "文档"]},
    {"id": "workflow", "name": "Skill / 工作流自动化", "remote_deliverable": True, "match_words": ["自动化", "工作流", "Skill", "Agent", "n8n"]},
]
IDENTITY_ROLE_PRESETS = ["电商商家", "品牌方", "实体店", "创业者", "代运营工作室", "市场团队", "培训机构", "学生", "自由职业", "自媒体"]


class IdentityBusiness(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=40)
    remote_deliverable: bool = True


class IdentityProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    businesses: list[IdentityBusiness] = Field(default_factory=list, max_length=10)
    target_roles: list[str] = Field(default_factory=list, max_length=10)
    service_mode: Literal["remote", "unspecified", "regions"] = "remote"
    regions: list[str] = Field(default_factory=list, max_length=10)
    default_freshness_hours: Literal[24, 72, 168, 720] = 168
    preferred_sources: list[str] = Field(default_factory=list, max_length=10)
    buyer_keywords: list[str] = Field(default_factory=list, max_length=10)
    exclude_words: list[str] = Field(default_factory=list, max_length=20)
    business_match_words: list[str] = Field(default_factory=list, max_length=20)
    quote_style: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def bounded(self):
        def bounded_terms(values: list[str], minimum: int, maximum: int, label: str) -> None:
            for value in values:
                if not value.strip() or not minimum <= len(value) <= maximum:
                    raise ValueError(f"{label}需为 {minimum}–{maximum} 字，且不能为空白")
        bounded_terms(self.target_roles, 1, 20, "目标客户角色")
        bounded_terms(self.regions, 1, 20, "服务地区")
        bounded_terms(self.buyer_keywords, 1, 100, "买方关键词")
        bounded_terms(self.exclude_words, 1, 40, "排除词")
        bounded_terms(self.business_match_words, 1, 100, "业务匹配词")
        unknown = [source for source in self.preferred_sources if source not in ALLOWED_SOURCES]
        if unknown:
            raise ValueError("默认平台偏好包含未知来源")
        if self.service_mode == "regions" and not self.regions:
            raise ValueError("指定地区交付时至少需要一个地区")
        return self
