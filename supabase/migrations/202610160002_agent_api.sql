-- Local Edition Agent API：写操作幂等账本。
-- 用途：Agent/CLI 的写请求必须携带 Idempotency-Key；重复请求命中同一键时复用首次响应，
-- 保证重试不会重复建单、重复派发付费运行。仅后端可写，客户端只读自己的行。
-- 回滚：DROP TABLE IF EXISTS public.agent_idempotency;
create table if not exists public.agent_idempotency (
  user_id uuid not null references auth.users(id) on delete cascade,
  idempotency_key text not null check (char_length(idempotency_key) between 8 and 200),
  fingerprint text not null,
  status_code integer not null,
  response_body jsonb not null,
  created_at timestamptz not null default now(),
  primary key (user_id, idempotency_key)
);
create index if not exists agent_idempotency_user_created on public.agent_idempotency(user_id, created_at desc);
alter table public.agent_idempotency enable row level security;
create policy agent_idempotency_owner on public.agent_idempotency for select using(user_id=auth.uid());
-- 不做客户端写策略：幂等记录只由后端校验与写入。
