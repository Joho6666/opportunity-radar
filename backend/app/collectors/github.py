from datetime import UTC, datetime
from urllib.parse import urlencode
from .base import CollectorCapabilities, SourceAdapter
from .http import fetcher
from ..core.config import get_settings
from ..schemas.domain import RawItem


class GitHubCollector(SourceAdapter):
    slug = "github"

    def capabilities(self) -> CollectorCapabilities:
        return CollectorCapabilities(search=True, timeline=True, detail=True, change_detection=True)

    async def search(self, query: str) -> list[RawItem]:
        items, next_cursor = await self.search_page(query)
        for item in items: item.metadata["next_cursor"] = next_cursor
        return items

    async def search_page(self, query: str, cursor: str | None = None) -> tuple[list[RawItem], str | None]:
        page = int(cursor or 1)
        if not 1 <= page <= 100:
            raise ValueError("Invalid page")
        if query.startswith("issues:"):
            return await self._issues(query.removeprefix("issues:").strip(), page)
        q = query.strip() or "AI agent stars:>20"
        token = get_settings().github_token
        headers = {"Accept": "application/vnd.github+json"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        payload = await fetcher.get_json("https://api.github.com/search/repositories?" + urlencode({"q": q, "sort": "updated", "order": "desc", "per_page": 10, "page":page}), headers=headers)
        items: list[RawItem] = []
        for repo in payload.get("items", []):
            html_url = repo.get("html_url") or ""
            if not html_url:
                continue
            description = repo.get("description") or ""
            topics = ", ".join(repo.get("topics") or [])
            created_at = _parse_dt(repo.get("created_at"))
            updated_at = _parse_dt(repo.get("updated_at"))
            pushed_at = _parse_dt(repo.get("pushed_at"))
            items.append(
                RawItem(
                    external_id=str(repo.get("id") or html_url),
                    title=repo.get("full_name") or repo.get("name") or html_url,
                    content=f"{description}\n{topics}".strip(),
                    url=html_url,
                    author=(repo.get("owner") or {}).get("login"),
                    source=self.slug,
                    # published_at stays the repo creation date (true publication);
                    # activity freshness is carried by updated_at_source (pushed_at).
                    published_at=created_at,
                    updated_at_source=pushed_at or updated_at,
                    platform="github",
                    language=repo.get("language"),
                    engagement={"stars": repo.get("stargazers_count"), "forks": repo.get("forks_count"), "watchers": repo.get("watchers_count"), "open_issues": repo.get("open_issues_count")},
                    metadata={
                        "stars": repo.get("stargazers_count"),
                        "language": repo.get("language"),
                        "topics": repo.get("topics") or [],
                        "created_at": repo.get("created_at"),
                        "updated_at": repo.get("updated_at"),
                        "pushed_at": repo.get("pushed_at"),
                        "query": query,
                    },
                )
            )
        return items, str(page + 1) if page * 10 < min(payload.get("total_count", 0), 1000) else None

    async def _issues(self, query: str, page: int):
        headers={"Accept":"application/vnd.github+json"}
        if get_settings().github_token:
            headers["Authorization"]=f"Bearer {get_settings().github_token}"
        payload=await fetcher.get_json("https://api.github.com/search/issues?"+urlencode({"q":query+" is:issue is:open","sort":"updated","order":"desc","per_page":10,"page":page}),headers=headers)
        items=[RawItem(external_id=str(row["id"]),title=row.get("title") or "",content=row.get("body") or row.get("title") or "",url=row["html_url"],author=(row.get("user") or {}).get("login"),source=self.slug,platform="github",published_at=_parse_dt(row.get("created_at")),updated_at_source=_parse_dt(row.get("updated_at")),metadata={"query":query,"content_kind":"issue","state":row.get("state"),"repository_url":row.get("repository_url")}) for row in payload.get("items",[]) if row.get("id") and row.get("html_url")]
        return items,str(page+1) if page*10 < min(payload.get("total_count",0),1000) else None


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None
