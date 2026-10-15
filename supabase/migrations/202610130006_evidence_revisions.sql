-- Preserve every source-text revision; a changed verified source needs new review.
create table if not exists public.evidence_revisions (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id),
 evidence_id uuid not null references evidence_items(id), previous jsonb not null,
 created_at timestamptz not null default now()
);
alter table public.evidence_revisions enable row level security;
create policy evidence_revisions_owner on public.evidence_revisions for select using(user_id=auth.uid());
