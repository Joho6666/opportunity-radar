-- Evidence inbox: raw demand signals with idempotent identity per user.
create table if not exists public.evidence_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  identity_key text not null,
  batch_id text not null,
  source text not null,
  url text not null,
  external_id text,
  raw_text text not null,
  query text not null default '',
  published_at timestamptz,
  captured_at timestamptz not null default now(),
  category text not null default 'market' check (category in ('buyer','content','market')),
  buyer_type text,
  problem text,
  payment_signal text,
  urgency_signal text,
  metadata jsonb not null default '{}'::jsonb,
  evidence_grade text not null default 'C' check (evidence_grade in ('A','B','C')),
  verification_status text not null default 'unverified' check (verification_status in ('unverified','verified','invalidated','disputed')),
  created_at timestamptz not null default now(),
  unique (user_id, identity_key)
);
create index if not exists evidence_items_user_captured_idx on public.evidence_items(user_id, captured_at desc);
create index if not exists evidence_items_user_category_idx on public.evidence_items(user_id, category, captured_at desc);

alter table public.evidence_items enable row level security;
create policy "evidence_items_owner" on public.evidence_items
  for all using (user_id = auth.uid()) with check (user_id = auth.uid());
