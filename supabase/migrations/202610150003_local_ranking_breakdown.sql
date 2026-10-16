-- Preserve the complete, versioned general-information ranking explanation.
ALTER TABLE public.radar_evidence
  ADD COLUMN IF NOT EXISTS relevance_breakdown jsonb NOT NULL DEFAULT '{}'::jsonb;
