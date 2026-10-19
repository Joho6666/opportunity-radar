# tikhub_live fixtures — provenance

These JSON fixtures are trimmed copies of real paid TikHub search responses
made on 2026-10-16 (see `backend/app/collectors/tikhub-live-verification.json`
for each endpoint's request id and evidence summary; the full sanitized
responses stay outside the repo in the operator's scratch archive).

- Structure and field names are untouched; long public text fields are
  truncated and non-essential personal-data blobs (avatars, signatures,
  biographies) were dropped to keep fixtures small.
- `*_missing_date.json` variants keep the same structure but remove the
  publish-time field, so tests can prove unknown dates stay unknown and are
  dropped by the freshness filter instead of being treated as fresh.
- Fixtures are NOT live calls and never prove uptime; they lock the parser
  contract. Re-verify with a real bounded call before trusting a changed
  provider.
