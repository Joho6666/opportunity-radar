alter table public.opportunities add column if not exists pipeline_data jsonb not null default '{}';
-- A failed run must not leave a permanent queued/running reservation after restarts.
create unique index if not exists radar_runs_single_active on public.radar_runs(radar_id) where status in ('queued','running');
