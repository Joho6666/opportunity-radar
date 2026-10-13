create table if not exists public.billing_authorizations (
 user_id uuid not null references auth.users(id), scope text not null,
 enabled boolean not null default false, providers jsonb not null default '[]',
 allow_scheduled boolean not null default false,
 run_requests integer not null check(run_requests > 0), daily_requests integer not null check(daily_requests > 0),
 run_micros bigint not null check(run_micros > 0), daily_micros bigint not null check(daily_micros > 0),
 updated_at timestamptz not null default now(), primary key(user_id, scope)
);
create table if not exists public.billing_calls (
 id uuid primary key, user_id uuid not null references auth.users(id), scope text not null,
 run_id text not null, provider text not null, source text not null, scheduled boolean not null,
 status text not null default 'reserved', reserved_micros bigint not null, estimated_tokens integer not null default 0,
 prompt_tokens integer, completion_tokens integer, actual_tokens integer, actual_micros bigint,
 created_at timestamptz not null default now()
);
create index if not exists billing_calls_user_date on public.billing_calls(user_id, created_at);
create index if not exists billing_calls_user_run on public.billing_calls(user_id, run_id);
alter table public.billing_authorizations enable row level security;
alter table public.billing_calls enable row level security;
create policy billing_authorizations_owner on public.billing_authorizations for select using(user_id=auth.uid());
create policy billing_calls_owner on public.billing_calls for select using(user_id=auth.uid());
-- No direct client writes: reservations and grants pass through authenticated backend validation.
