-- Additive debugging caps and response receipts; historical migrations stay intact.
create table public.billing_batches (
 id text primary key, user_id uuid not null references auth.users(id),
 enabled boolean not null default false, providers jsonb not null,
 sources jsonb not null, request_limit integer not null check(request_limit > 0),
 cost_limit_micros bigint not null check(cost_limit_micros > 0),
 request_limit_micros bigint not null check(request_limit_micros > 0),
 created_at timestamptz not null default now()
);
alter table public.billing_calls add column batch_id text references public.billing_batches(id);
alter table public.billing_calls add column endpoint text;
create index billing_calls_batch on public.billing_calls(batch_id);
create table public.provider_responses (
 call_id uuid primary key references public.billing_calls(id),
 user_id uuid not null references auth.users(id),
 endpoint text not null, query text, status_code integer not null,
 request_id text, payload jsonb not null, captured_at timestamptz not null default now()
);
create table public.collection_requests (
 id text not null, user_id uuid not null references auth.users(id),
 fingerprint text not null, status text not null default 'running',
 result jsonb, created_at timestamptz not null default now(),
 primary key(user_id,id)
);
create table public.collector_cursors (
 id text primary key, user_id uuid not null references auth.users(id),
 source text not null, query text not null, state jsonb not null,
 expires_at timestamptz not null default now()+interval '24 hours'
);
alter table public.billing_batches enable row level security;
alter table public.provider_responses enable row level security;
alter table public.collection_requests enable row level security;
alter table public.collector_cursors enable row level security;
create policy billing_batches_owner on public.billing_batches for select using(user_id=auth.uid());
create policy provider_responses_owner on public.provider_responses for select using(user_id=auth.uid());
create policy collection_requests_owner on public.collection_requests for select using(user_id=auth.uid());
-- No direct client writes; cursors contain provider session identifiers and are backend-only.
