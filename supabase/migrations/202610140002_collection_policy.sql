-- Additive config only; existing Radars preserve their previous freshness rules.
ALTER TABLE public.radars ADD COLUMN IF NOT EXISTS collection_policy jsonb NOT NULL DEFAULT '{}'::jsonb;
