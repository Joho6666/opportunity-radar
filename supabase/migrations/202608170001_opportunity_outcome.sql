-- 机会成交结果字段：与内存仓库 OpportunityAction 的 actual_revenue / actual_hours / closed_at 对齐
alter table public.opportunities
  add column if not exists actual_revenue integer,
  add column if not exists actual_hours numeric,
  add column if not exists closed_at timestamptz;

-- 雷达运行统计快照，与 RadarRead.stats 对齐（便于列表页展示，避免每次联表 radar_runs）
alter table public.radars
  add column if not exists last_stats jsonb not null default '{}'::jsonb;
