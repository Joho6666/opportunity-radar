from datetime import UTC, datetime
from .base import CollectorCapabilities, SourceAdapter
from ..schemas.domain import RawItem


class MockCollector(SourceAdapter):
    """Fixture collector for tests/demo only; excluded from production registries."""

    slug = "mock"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True)

    async def search(self, query: str) -> list[RawItem]:
        now = datetime.now(UTC)
        fixtures = [
            ("ppt-guilin", "桂林｜急需毕业答辩 PPT", "3 天内完成约 20 页毕业答辩 PPT，已有基础内容，预算 200–300 元。", "https://mock.local/ppt-guilin"),
            ("ai-intern", "远程｜招聘 AI 自动化实习生", "协助搭建 n8n 工作流、整理提示词与测试 AI Agent，月薪 4000–6000 元。", "https://mock.local/ai-intern"),
            ("n8n-flow", "求 n8n 工作流搭建", "表单、飞书与表格自动化，预算 800–1600 元，需一周内交付。", "https://mock.local/n8n-flow"),
            ("miniapp", "找人开发简单微信小程序", "校园活动报名页面与基础后端对接，预算 1500–3000 元。", "https://mock.local/miniapp"),
        ]
        return [RawItem(external_id=item_id, title=title, content=content, url=url, author="Mock 用户", source=self.slug, published_at=now, platform="mock", engagement={}, metadata={"query": query}) for item_id, title, content, url in fixtures]
