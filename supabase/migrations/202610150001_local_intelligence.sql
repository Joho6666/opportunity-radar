-- Local Edition general monitoring fields. Existing rows remain acquisition mode.
ALTER TABLE public.radars
  ADD COLUMN IF NOT EXISTS monitoring_mode text NOT NULL DEFAULT 'acquisition'
    CHECK (monitoring_mode IN ('acquisition', 'general')),
  ADD COLUMN IF NOT EXISTS local_schedule_enabled boolean NOT NULL DEFAULT false;
CREATE UNIQUE INDEX IF NOT EXISTS radars_id_user_owner_uq ON public.radars(id, user_id);

ALTER TABLE public.evidence_items
  ADD COLUMN IF NOT EXISTS is_saved boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS is_read boolean NOT NULL DEFAULT false;
CREATE UNIQUE INDEX IF NOT EXISTS evidence_items_id_user_owner_uq ON public.evidence_items(id, user_id);
ALTER TABLE public.radar_runs ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz;

CREATE TABLE IF NOT EXISTS public.radar_evidence (
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  radar_id uuid NOT NULL,
  evidence_id uuid NOT NULL,
  run_id uuid REFERENCES public.radar_runs(id) ON DELETE SET NULL,
  discovered_at timestamptz NOT NULL DEFAULT now(),
  relevance_score smallint NOT NULL DEFAULT 0 CHECK (relevance_score BETWEEN 0 AND 100),
  relevance_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  PRIMARY KEY (radar_id, evidence_id),
  FOREIGN KEY (radar_id, user_id) REFERENCES public.radars(id, user_id) ON DELETE CASCADE,
  FOREIGN KEY (evidence_id, user_id) REFERENCES public.evidence_items(id, user_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS radar_evidence_user_discovered_idx
  ON public.radar_evidence(user_id, discovered_at DESC);
CREATE INDEX IF NOT EXISTS radar_evidence_evidence_idx
  ON public.radar_evidence(evidence_id, discovered_at DESC);
ALTER TABLE public.radar_evidence ENABLE ROW LEVEL SECURITY;
CREATE POLICY "radar_evidence_owner" ON public.radar_evidence
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

CREATE TABLE IF NOT EXISTS public.local_settings (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  ai_mode text NOT NULL DEFAULT 'off' CHECK (ai_mode IN ('off', 'on_demand')),
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE public.local_settings ENABLE ROW LEVEL SECURITY;
CREATE POLICY "local_settings_owner" ON public.local_settings
  FOR ALL USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

INSERT INTO public.radar_evidence(user_id, radar_id, evidence_id, discovered_at)
SELECT evidence.user_id, radar.id, evidence.id, evidence.captured_at
FROM public.evidence_items AS evidence
JOIN public.radars AS radar
  ON radar.id::text = evidence.metadata->>'radar_id'
 AND radar.user_id = evidence.user_id
WHERE evidence.metadata->>'radar_id' ~ '^[0-9a-fA-F-]{36}$'
ON CONFLICT (radar_id, evidence_id) DO NOTHING;
