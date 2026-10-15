from datetime import UTC, datetime, timedelta

from app.services.radar_run_service import align_vectors_to_items
from app.schemas.domain import RawItem


def _item(external_id: str, hours_ago: int) -> RawItem:
    return RawItem(
        external_id=external_id,
        title=external_id,
        content=f"content-{external_id}",
        url=f"https://example.test/{external_id}",
        source="test",
        published_at=datetime.now(UTC) - timedelta(hours=hours_ago),
    )


def test_align_vectors_drops_known_items_without_shifting_new_item_vectors():
    known = _item("known", 1)
    fresh = _item("fresh", 1)
    vectors = [[1.0], [2.0]]

    aligned = align_vectors_to_items([known, fresh], vectors, {known.url})

    assert aligned == [(fresh, [2.0])]
