from app.collectors.rss import _published, _updated


def test_updated_feed_time_is_not_original_publication():
    entry={"updated":"2026-10-14T12:00:00Z"}
    assert _published(entry) is None
    assert _updated(entry).isoformat() == "2026-10-14T12:00:00+00:00"
