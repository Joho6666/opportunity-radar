-- Local Edition 个人身份设定（业务画像）。
-- 复用 local_settings 配置表，仅新增可空 JSONB 列；老雷达与既有数据不受影响。
-- 回滚：ALTER TABLE public.local_settings DROP COLUMN IF EXISTS identity_profile;
ALTER TABLE public.local_settings
  ADD COLUMN IF NOT EXISTS identity_profile jsonb;
