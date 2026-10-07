-- Minimal auth stub so the Supabase-style migrations run on plain PostgreSQL
-- (pgvector/pgvector:pg16 image). Supabase deployments already provide auth.users.
create schema if not exists auth;

create table if not exists auth.users (
  id uuid primary key,
  instance_id uuid,
  aud text,
  "role" text,
  email text,
  encrypted_password text,
  email_confirmed_at timestamptz,
  created_at timestamptz,
  updated_at timestamptz,
  confirmation_token text,
  recovery_token text,
  email_change_token_new text,
  email_change text,
  last_sign_in_at timestamptz,
  raw_app_meta_data jsonb,
  raw_user_meta_data jsonb
);

-- auth.uid() stub: with this compose setup the backend connects as the service
-- role and enforces ownership in the repository layer, so uid() maps to a
-- permissive default used by policies only.
--
-- ⚠ RLS TRAP: the backend connects as `postgres` superuser, which BYPASSES row
-- level security entirely — ownership is enforced by the repository layer
-- (user_id joins), not by RLS. If you redeploy with a scoped role and no JWT
-- request context, auth.uid() returns NULL and every policy silently denies
-- (empty results, no errors). Either keep the superuser service connection or
-- set request.jwt.claim.sub per connection.
create or replace function auth.uid() returns uuid
language sql stable as $$
  select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid
$$;
