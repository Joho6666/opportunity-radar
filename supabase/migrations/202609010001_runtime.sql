alter table public.radar_runs
  add column if not exists error_code text;

create table if not exists public.llm_calls (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete cascade,
  radar_id uuid references public.radars(id) on delete set null,
  run_id uuid references public.radar_runs(id) on delete set null,
  provider text,
  model text,
  latency_ms integer,
  fallbacked boolean not null default false,
  schema_name text,
  created_at timestamptz default now()
);

create table if not exists public.user_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  opportunity_id uuid references public.opportunities(id) on delete set null,
  event text not null check (event in ('viewed','saved','ignored','contacted','applied','won','lost')),
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz default now()
);

create table if not exists public.user_preference_state (
  user_id uuid primary key references auth.users(id) on delete cascade,
  skill_weights jsonb not null default '{}'::jsonb,
  type_weights jsonb not null default '{}'::jsonb,
  source_weights jsonb not null default '{}'::jsonb,
  location_weights jsonb not null default '{}'::jsonb,
  keyword_weights jsonb not null default '{}'::jsonb,
  min_budget_hint integer,
  recommendation_threshold integer,
  updated_at timestamptz default now()
);

alter table public.llm_calls enable row level security;
alter table public.user_events enable row level security;
alter table public.user_preference_state enable row level security;

create policy "llm_calls_owner" on public.llm_calls for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "user_events_owner" on public.user_events for all using (user_id = auth.uid()) with check (user_id = auth.uid());
create policy "preference_owner" on public.user_preference_state for all using (user_id = auth.uid()) with check (user_id = auth.uid());
