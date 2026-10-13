alter table public.evidence_items drop constraint if exists evidence_items_category_check;
alter table public.evidence_items add constraint evidence_items_category_check check(category in ('buyer','seller','job','content','market'));
create table if not exists public.evidence_reviews (
 id uuid primary key default gen_random_uuid(), user_id uuid not null references auth.users(id),
 evidence_id uuid not null references evidence_items(id), previous jsonb not null, correction jsonb not null,
 created_at timestamptz not null default now()
);
alter table public.evidence_reviews enable row level security;
create policy evidence_reviews_owner on public.evidence_reviews for select using(user_id=auth.uid());
