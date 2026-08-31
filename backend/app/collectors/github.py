from datetime import UTC, datetime
from urllib.parse import urlencode
from .base import SourceAdapter
from .http import fetcher
from ..core.config import get_settings
from ..schemas.domain import RawItem


class GitHubCollector(SourceAdapter):
    slug = "github"

    async def search(self, query: str) -> list[RawItem]:
        q = query.strip() or "AI agent stars:>20"
        token = get_settings().github_token
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = await fetcher.get_json("https://api.github.com/search/repositories?" + urlencode({"q": q, "sort": "updated", "order": "desc", "per_page": 10}), headers=headers)
        items: list[RawItem] = []
        for repo in payload.get("items", []):
            html_url = repo.get("html_url") or ""
            if not html_url:
                continue
            description = repo.get("description") or ""
            topics = ", ".join(repo.get("topics") or [])
            items.append(
                RawItem(
                    external_id=str(repo.get("id") or html_url),
                    title=repo.get("full_name") or repo.get("name") or html_url,
                    content=f"{description}\n{topics}".strip(),
                    url=html_url,
                    author=(repo.get("owner") or {}).get("login"),
                    source=self.slug,
                    published_at=_parse_dt(repo.get("created_at") or repo.get("pushed_at")),
                    metadata={"stars": repo.get("stargazers_count"), "language": repo.get("language"), "topics": repo.get("topics") or [], "query": query},
                )
            )
        return items


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None
