alter table public.evidence_items
  add column if not exists classification_source text not null default 'unclassified',
  add column if not exists classification_reason text not null default '',
  add column if not exists classification_confidence numeric(4,3) not null default 0,
  add column if not exists source_platform text not null default '',
  add column if not exists acquisition_tool text not null default '';

alter table public.evidence_items
  drop constraint if exists evidence_items_classification_confidence_check;

alter table public.evidence_items
  add constraint evidence_items_classification_confidence_check
  check (classification_confidence >= 0 and classification_confidence <= 1);
