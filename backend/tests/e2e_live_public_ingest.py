import json
from urllib.request import Request, urlopen

from fastapi.testclient import TestClient
from app.api.deps import get_current_user, get_repository
from app.core.security import CurrentUser
from app.main import app
from app.repositories.memory import MemoryRepository

sources = [
    ("openmagpie", "https://raw.githubusercontent.com/obris-dev/openmagpie/main/README.md"),
    ("subscope", "https://raw.githubusercontent.com/dancolta/subscope/main/README.md"),
    ("harken", "https://raw.githubusercontent.com/VladUZH/harken/main/README.md"),
]
items = []
for project, url in sources:
    req = Request(url, headers={"User-Agent": "opportunity-radar-e2e/1.0"})
    text = urlopen(req, timeout=20).read().decode("utf-8")
    items.append({
        "source": "ego-lite-public-research",
        "url": url,
        "external_id": project,
        "raw_text": text[:12000],
        "category": "market",
        "query": "open source demand intelligence reference projects",
        "metadata": {"project": project},
    })

batch = {"batch_id": "ego-live-public-2026-10-11", "items": items}
repo = MemoryRepository()
app.dependency_overrides[get_repository] = lambda: repo
app.dependency_overrides[get_current_user] = lambda: CurrentUser(id="e2e-user")
try:
    client = TestClient(app)
    first = client.post("/api/intelligence/evidence/batches", json=batch)
    second = client.post("/api/intelligence/evidence/batches", json=batch)
    listed = client.get("/api/intelligence/evidence?category=market&limit=10")
finally:
    app.dependency_overrides.clear()

assert first.status_code == 200, first.text
assert first.json()["inserted"] == 3, first.text
assert second.json()["duplicates"] == 3, second.text
assert len(listed.json()) == 3, listed.text
print(json.dumps({
    "source": "live_public_fetch_via_ego_researched_urls",
    "batch_id": batch["batch_id"],
    "fetched_items": len(items),
    "first_insert": first.json()["inserted"],
    "second_duplicates": second.json()["duplicates"],
    "listed_items": len(listed.json()),
    "projects": [item["external_id"] for item in items],
}, ensure_ascii=False))
