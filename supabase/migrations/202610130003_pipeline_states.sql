-- Additive enum values; legacy saved/ignored remain valid.
alter type public.opportunity_status add value if not exists 'pending_verification';
alter type public.opportunity_status add value if not exists 'verified';
alter type public.opportunity_status add value if not exists 'ready_to_contact';
alter type public.opportunity_status add value if not exists 'replied';
alter type public.opportunity_status add value if not exists 'quoted';
