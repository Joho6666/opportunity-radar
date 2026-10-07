-- Money Intelligence OS — Phase 1 数据基础
-- 依赖：202608130001_initial_schema.sql, 202608170001_opportunity_outcome.sql, 202609010001_runtime.sql
-- 原则：纯增量；不删列不改列类型；旧 API 契约不受影响。

create extension if not exists vector;

-- ============================================================
-- 1. raw_items 时间与语义扩展
--    first_seen_at/last_seen_at/seen_count 让"重复出现"成为趋势证据；
--    updated_at_source 保存平台侧最后活跃时间（GitHub pushed_at 等），
--    修复老仓库因 created_at 过旧被 freshness 过滤误杀的问题。
-- ============================================================
alter table public.raw_items
  add column if not exists platform text,
  add column if not exists language text,
  add column if not exists engagement jsonb not null default '{}'::jsonb,
  add column if not exists updated_at_source timestamptz,
  add column if not exists first_seen_at timestamptz not null default now(),
  add column if not exists last_seen_at timestamptz not null default now(),
  add column if not exists crawled_at timestamptz not null default now(),
  add column if not exists content_changed_at timestamptz,
  add column if not exists seen_count integer not null default 1,
  add column if not exists simhash bigint,
  add column if not exists embedding vector(1536),
  add column if not exists embedding_model text;

create index if not exists raw_items_last_seen_idx on public.raw_items(last_seen_at desc);
create index if not exists raw_items_source_idx on public.raw_items(source_id, last_seen_at desc);
create index if not exists raw_items_simhash_idx on public.raw_items(simhash) where simhash is not null;

-- The old unique(radar_id, content_hash) constraint silently swallowed
-- same-content/different-URL rows AFTER opportunities had already been created
-- (audit P1-1). Content dedup now lives in the pipeline (dedup levels 2-4);
-- the constraint becomes a plain index for lookups.
alter table public.raw_items drop constraint if exists raw_items_radar_id_content_hash_key;
create index if not exists raw_items_content_hash_idx on public.raw_items(radar_id, content_hash);

-- ============================================================
-- 2. signals — 从 RawDocument 抽出的有价值信号
-- ============================================================
create table if not exists public.signals (
  id uuid primary key default gen_random_uuid(),
  raw_item_id uuid references public.raw_items(id) on delete cascade,
  radar_id uuid references public.radars(id) on delete cascade,
  signal_type text not null check (signal_type in (
    'pain_point','purchase_intent','hiring','outsourcing','product_request',
    'feature_request','complaint','price_change','funding','policy','tender',
    'technology_growth','creator_trend','consumer_trend','supply_shortage')),
  title text not null default '',
  entities jsonb not null default '[]'::jsonb,
  keywords jsonb not null default '[]'::jsonb,
  intent text,
  sentiment text,
  commercial_intent integer not null default 0 check (commercial_intent between 0 and 100),
  payment_evidence boolean not null default false,
  urgency integer not null default 0 check (urgency between 0 and 100),
  confidence integer not null default 0 check (confidence between 0 and 100),
  extraction_method text not null default 'rule' check (extraction_method in ('rule','llm','hybrid')),
  occurred_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists signals_type_idx on public.signals(signal_type, created_at desc);
create index if not exists signals_radar_idx on public.signals(radar_id, created_at desc);
create index if not exists signals_raw_item_idx on public.signals(raw_item_id);

-- ============================================================
-- 3. event_clusters — 同一事件/需求的聚合
-- ============================================================
create table if not exists public.event_clusters (
  id uuid primary key default gen_random_uuid(),
  radar_id uuid references public.radars(id) on delete cascade,
  title text not null default '',
  summary text not null default '',
  centroid vector(1536),
  keyphrases jsonb not null default '[]'::jsonb,
  source_count integer not null default 0,
  document_count integer not null default 0,
  unique_authors integer not null default 0,
  unique_platforms integer not null default 0,
  velocity_1h numeric not null default 0,
  velocity_24h numeric not null default 0,
  velocity_7d numeric not null default 0,
  velocity_30d numeric not null default 0,
  engagement_growth numeric not null default 0,
  breakout_score integer not null default 0 check (breakout_score between 0 and 100),
  representative_item_ids jsonb not null default '[]'::jsonb,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  merged_into uuid references public.event_clusters(id) on delete set null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
create index if not exists event_clusters_radar_idx on public.event_clusters(radar_id, last_seen_at desc);

create table if not exists public.event_cluster_members (
  cluster_id uuid not null references public.event_clusters(id) on delete cascade,
  raw_item_id uuid not null references public.raw_items(id) on delete cascade,
  similarity numeric not null default 0,
  joined_at timestamptz not null default now(),
  primary key (cluster_id, raw_item_id)
);
create index if not exists event_cluster_members_item_idx on public.event_cluster_members(raw_item_id);

-- ============================================================
-- 4. trend_topics + trend_snapshots — 指标历史
-- ============================================================
create table if not exists public.trend_topics (
  id uuid primary key default gen_random_uuid(),
  radar_id uuid references public.radars(id) on delete cascade,
  topic text not null,
  metrics jsonb not null default '{}'::jsonb,
  mention_count integer not null default 0,
  engagement integer not null default 0,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  unique (radar_id, topic)
);
create index if not exists trend_topics_last_seen_idx on public.trend_topics(last_seen_at desc);

create table if not exists public.trend_snapshots (
  id uuid primary key default gen_random_uuid(),
  topic_id uuid not null references public.trend_topics(id) on delete cascade,
  captured_at timestamptz not null default now(),
  mention_count integer not null default 0,
  engagement integer not null default 0,
  metrics jsonb not null default '{}'::jsonb
);
create index if not exists trend_snapshots_topic_idx on public.trend_snapshots(topic_id, captured_at desc);

-- ============================================================
-- 5. change_events — 与基线相比的变化（breakout 检测产物）
-- ============================================================
create table if not exists public.change_events (
  id uuid primary key default gen_random_uuid(),
  radar_id uuid references public.radars(id) on delete cascade,
  subject_kind text not null default 'topic' check (subject_kind in ('topic','cluster','source','keyword')),
  subject_key text not null,
  metric_key text not null,
  baseline_value numeric not null default 0,
  current_value numeric not null default 0,
  change_rate numeric not null default 0,
  z_score numeric not null default 0,
  velocity numeric not null default 0,
  acceleration numeric not null default 0,
  momentum numeric not null default 0,
  breakout_score integer not null default 0 check (breakout_score between 0 and 100),
  is_breakout boolean not null default false,
  window_start timestamptz,
  window_end timestamptz,
  detected_at timestamptz not null default now()
);
create index if not exists change_events_radar_idx on public.change_events(radar_id, detected_at desc);
create index if not exists change_events_breakout_idx on public.change_events(is_breakout, detected_at desc);

-- ============================================================
-- 6. source_health — 每个 collector 的健康记录（全局一行/源）
-- ============================================================
create table if not exists public.source_health (
  slug text primary key,
  status text not null default 'unknown' check (status in ('healthy','degraded','unhealthy','unknown')),
  last_success_at timestamptz,
  last_failure_at timestamptz,
  last_error text,
  last_error_code text,
  runs_total integer not null default 0,
  runs_ok integer not null default 0,
  items_fetched integer not null default 0,
  success_rate numeric not null default 0,
  avg_latency_ms integer not null default 0,
  rate_limited_count integer not null default 0,
  error_count integer not null default 0,
  health_score integer not null default 100 check (health_score between 0 and 100),
  updated_at timestamptz not null default now()
);

-- ============================================================
-- 7. opportunities — MoneyScore / Information Edge / Verification
-- ============================================================
alter table public.opportunities
  add column if not exists money_score integer,
  add column if not exists money_breakdown jsonb,
  add column if not exists information_edge integer,
  add column if not exists information_edge_breakdown jsonb,
  add column if not exists verification_status text not null default 'unverified'
    check (verification_status in ('unverified','verified','invalidated','disputed')),
  add column if not exists verification_evidence jsonb,
  add column if not exists cluster_id uuid references public.event_clusters(id) on delete set null;

create index if not exists opportunities_money_idx on public.opportunities(user_id, money_score desc nulls last);

-- ============================================================
-- 8. daily_briefs — V2 结构（旧列保留，前端旧契约不破坏）
-- ============================================================
alter table public.daily_briefs
  add column if not exists top_opportunities jsonb not null default '[]'::jsonb,
  add column if not exists rising_trends jsonb not null default '[]'::jsonb,
  add column if not exists pain_points jsonb not null default '[]'::jsonb,
  add column if not exists payment_signals jsonb not null default '[]'::jsonb,
  add column if not exists job_market_signals jsonb not null default '[]'::jsonb,
  add column if not exists tender_signals jsonb not null default '[]'::jsonb,
  add column if not exists content_opportunities jsonb not null default '[]'::jsonb,
  add column if not exists today_actions jsonb not null default '[]'::jsonb,
  add column if not exists brief_version text not null default 'v2';

-- ============================================================
-- 9. llm_calls — 成本漏斗计量
-- ============================================================
alter table public.llm_calls
  add column if not exists stage text,
  add column if not exists input_count integer,
  add column if not exists output_count integer,
  add column if not exists prompt_tokens integer,
  add column if not exists completion_tokens integer,
  add column if not exists cost_usd numeric;

create index if not exists llm_calls_stage_idx on public.llm_calls(run_id, stage);

-- ============================================================
-- 10. radar_runs — 每级漏斗计数
-- ============================================================
alter table public.radar_runs
  add column if not exists stage_stats jsonb not null default '{}'::jsonb;

-- ============================================================
-- 11. RLS — 与现有策略同风格（owner 经 radar 关联；source_health 全局只读）
-- ============================================================
alter table public.signals enable row level security;
alter table public.event_clusters enable row level security;
alter table public.event_cluster_members enable row level security;
alter table public.trend_topics enable row level security;
alter table public.trend_snapshots enable row level security;
alter table public.change_events enable row level security;
alter table public.source_health enable row level security;

create policy "signals_owner" on public.signals for all using (exists(select 1 from public.radars r where r.id=radar_id and r.user_id=auth.uid())) with check (exists(select 1 from public.radars r where r.id=radar_id and r.user_id=auth.uid()));
create policy "clusters_owner" on public.event_clusters for all using (exists(select 1 from public.radars r where r.id=radar_id and r.user_id=auth.uid())) with check (exists(select 1 from public.radars r where r.id=radar_id and r.user_id=auth.uid()));
create policy "cluster_members_owner" on public.event_cluster_members for all using (exists(select 1 from public.radars r join public.event_clusters c on c.id=cluster_id where r.id=c.radar_id and r.user_id=auth.uid())) with check (exists(select 1 from public.radars r join public.event_clusters c on c.id=cluster_id where r.id=c.radar_id and r.user_id=auth.uid()));
create policy "trend_topics_owner" on public.trend_topics for all using (exists(select 1 from public.radars r where r.id=radar_id and r.user_id=auth.uid())) with check (exists(select 1 from public.radars r where r.id=radar_id and r.user_id=auth.uid()));
create policy "trend_snapshots_owner" on public.trend_snapshots for all using (exists(select 1 from public.radars r join public.trend_topics t on t.id=topic_id where r.id=t.radar_id and r.user_id=auth.uid())) with check (exists(select 1 from public.radars r join public.trend_topics t on t.id=topic_id where r.id=t.radar_id and r.user_id=auth.uid()));
create policy "change_events_owner" on public.change_events for all using (exists(select 1 from public.radars r where r.id=radar_id and r.user_id=auth.uid())) with check (exists(select 1 from public.radars r where r.id=radar_id and r.user_id=auth.uid()));
create policy "source_health_read" on public.source_health for select using (true);
