-- Additive provenance; historical reservations and business records are preserved.
alter table public.billing_calls add column price_receipt jsonb;
