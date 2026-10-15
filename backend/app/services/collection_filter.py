"""A single bounded page in, a traceable filtered page out. Never retries."""
from datetime import UTC, datetime, timedelta
from .post_ranking import signals


def filter_page(items, policy, *, freshness_hours, now=None):
    now = now or datetime.now(UTC)
    counts = {"stale": 0, "unknown_date": 0, "terms": 0, "activity": 0}
    kept = []
    cutoff = now - timedelta(hours=freshness_hours)
    for item in items:
        text = f"{item.title}\n{item.content}".casefold()
        obs = signals(published_at=item.published_at, updated_at=item.updated_at_source, author=item.author, engagement=item.engagement, now=now)
        selected_time = obs["published_at"] if policy.time_basis == "published" else obs["last_activity_at"]
        if selected_time and datetime.fromisoformat(selected_time) < cutoff:
            counts["stale"] += 1
            continue
        if not selected_time and not policy.include_unknown_dates:
            counts["unknown_date"] += 1
            continue
        hits = [term.casefold() in text for term in policy.required_terms]
        if any(term.casefold() in text for term in policy.excluded_terms) or (hits and not (all(hits) if policy.match_mode == "all" else any(hits))):
            counts["terms"] += 1
            continue
        recent = bool(selected_time)
        if ((policy.activity_filter != "any" and not (recent and obs["author_visible"]))
                or (policy.activity_filter == "discussion" and not (obs["comments"] is not None and obs["comments"] > 0))
                or (policy.min_interactions > 0 and (obs["interactions"] is None or obs["interactions"] < policy.min_interactions))):
            counts["activity"] += 1
            continue
        kept.append((item, obs, selected_time))
    kept.sort(key=lambda row: ((row[1]["heat_score"] if row[1]["heat_score"] is not None else -1), row[2] or "") if policy.sort == "hot" else (row[2] or "",), reverse=True)
    return [row[0] for row in kept], counts
