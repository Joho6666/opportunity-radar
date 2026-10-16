-- Optional per-Radar source configuration, such as a specific public RSS feed.
-- Existing records retain empty configuration and acquisition behavior.
ALTER TABLE public.radars
  ADD COLUMN IF NOT EXISTS source_config jsonb NOT NULL DEFAULT '{}'::jsonb;
