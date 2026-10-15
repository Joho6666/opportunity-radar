"""Refresh public counters without manufacturing new leads or re-verifying text."""


def refreshed_observation(current, incoming):
    keys = {"engagement", "raw_author", "updated_at_source"}
    public = {key: incoming.metadata[key] for key in keys if key in incoming.metadata}
    if not public:
        return current
    return current.model_copy(update={
        "metadata": {**current.metadata, **public, "last_observed_at": incoming.captured_at.isoformat()},
        "published_at": incoming.published_at or current.published_at,
    })
