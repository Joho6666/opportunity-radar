-- Money Intelligence OS — Phase 2 (P1 guardrails need no DDL except listener columns;
-- pain_points table + listener fields + cluster-level signals)

-- 1) Natural language listener (openmagpie-style): description compiled once into
--    positive/negative signals + query suggestions, cached on the radar row.
alter table public.radars
  add column if not exists listener_description text not null default '',
  add column if not exists listener_config jsonb;

-- 2) Cluster-level signals (LLM extraction writes one signal per cluster).
alter table public.signals
  add column if not exists cluster_id uuid references public.event_clusters(id) on delete set null;
create index if not exists signals_cluster_idx on public.signals(cluster_id);

-- 3) PainPoint Engine — aggregated user pain themes per radar.
create table if not exists public.pain_points (
  id uuid primary key default gen_random_uuid(),
  radar_id uuid references public.radars(id) on delete cascade,
  theme text not null,
  title text not null default '',
  summary text not null default '',
  mention_count integer not null default 0,
  growth_rate numeric not null default 0,
  platform_count integer not null default 0,
  unique_user_count integer not null default 0,
  severity integer not null default 0 check (severity between 0 and 100),
  payment_intent integer not null default 0 check (payment_intent between 0 and 100),
  current_solutions text not null default '',
  solution_satisfaction integer check (solution_satisfaction between 0 and 100),
  cluster_id uuid references public.event_clusters(id) on delete set null,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (radar_id, theme)
);
create index if not exists pain_points_radar_idx on public.pain_points(radar_id, severity desc);

alter table public.pain_points enable row level security;
create policy "pain_points_owner" on public.pain_points for all
  using (exists(select 1 from public.radars r where r.id=radar_id and r.user_id=auth.uid()))
  with check (exists(select 1 from public.radars r where r.id=radar_id and r.user_id=auth.uid()));
