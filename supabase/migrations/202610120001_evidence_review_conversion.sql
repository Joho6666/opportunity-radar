-- Evidence review and conversion state. Apply after evidence_items and opportunities.
alter table public.evidence_items
  add column if not exists notes text not null default '',
  add column if not exists converted_opportunity_id uuid references public.opportunities(id) on delete set null;
alter table public.opportunities
  add column if not exists evidence_id text,
  add column if not exists metadata jsonb not null default '{}'::jsonb;
create unique index if not exists opportunities_user_evidence_idx
  on public.opportunities(user_id, evidence_id) where evidence_id is not null;
