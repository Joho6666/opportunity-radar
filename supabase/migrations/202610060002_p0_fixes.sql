-- Money Intelligence OS — P0 fixes
-- 1) change_events idempotency: run-time and scheduler-time breakout detection must
--    not write duplicate rows for the same subject/metric/day.
-- 2) HNSW index on raw_items.embedding (embeddings start being persisted in P0).

alter table public.change_events
  add column if not exists dedup_key text;

-- Backfill for rows created before this migration (best effort; collisions keep first).
update public.change_events
set dedup_key = concat(coalesce(radar_id::text, 'none'), ':', subject_kind, ':', subject_key, ':', metric_key, ':', to_char(coalesce(window_end, detected_at), 'YYYY-MM-DD'))
where dedup_key is null;

create unique index if not exists change_events_dedup_key_idx on public.change_events(dedup_key);

create index if not exists raw_items_embedding_hnsw_idx
  on public.raw_items using hnsw (embedding vector_cosine_ops)
  with (m = 16, ef_construction = 200);
