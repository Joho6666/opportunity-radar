from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import JSONB, UUID, insert
from sqlalchemy.engine import Connection
from ..schemas.domain import PreferenceState

metadata = MetaData()
preference_table = Table(
    "user_preference_state",
    metadata,
    Column("user_id", UUID),
    Column("skill_weights", JSONB),
    Column("type_weights", JSONB),
    Column("source_weights", JSONB),
    Column("location_weights", JSONB),
    Column("keyword_weights", JSONB),
    Column("min_budget_hint", Integer),
    Column("recommendation_threshold", Integer),
    Column("updated_at", DateTime),
)
event_table = Table(
    "user_events",
    metadata,
    Column("user_id", UUID),
    Column("opportunity_id", UUID),
    Column("event", String),
    Column("metadata", JSONB),
)


def load_preference(conn: Connection, uid: str) -> PreferenceState:
    row = conn.execute(select(preference_table).where(preference_table.c.user_id == uid)).mappings().first()
    if row is None:
        return PreferenceState()
    data = dict(row)
    return PreferenceState(
        skill_weights=data.get("skill_weights") or {},
        type_weights=data.get("type_weights") or {},
        source_weights=data.get("source_weights") or {},
        location_weights=data.get("location_weights") or {},
        keyword_weights=data.get("keyword_weights") or {},
        min_budget_hint=data.get("min_budget_hint"),
        recommendation_threshold=data.get("recommendation_threshold"),
    )


def store_preference(conn: Connection, uid: str, state: PreferenceState) -> None:
    values = {
        "user_id": uid,
        "skill_weights": state.skill_weights,
        "type_weights": state.type_weights,
        "source_weights": state.source_weights,
        "location_weights": state.location_weights,
        "keyword_weights": state.keyword_weights,
        "min_budget_hint": state.min_budget_hint,
        "recommendation_threshold": state.recommendation_threshold,
    }
    stmt = insert(preference_table).values(**values)
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id"],
        set_={key: getattr(stmt.excluded, key) for key in values if key != "user_id"},
    )
    conn.execute(stmt)


def store_event(conn: Connection, uid: str, opportunity_id: str | None, event: str, metadata: dict) -> None:
    conn.execute(insert(event_table).values(user_id=uid, opportunity_id=opportunity_id, event=event, metadata=metadata))
