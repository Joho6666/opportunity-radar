create table if not exists public.collection_receipts (
 id text primary key, user_id uuid not null references auth.users(id), source text not null,
 fetched integer not null, effective integer not null, duplicates integer not null default 0,
 stale integer not null default 0, created_at timestamptz not null default now()
);
alter table public.collection_receipts enable row level security;
create policy collection_receipts_owner on public.collection_receipts for select using(user_id=auth.uid());
