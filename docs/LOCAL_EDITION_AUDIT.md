# Opportunity Radar Local Edition: audit and baseline

Audit date: 2026-10-15. Repository: `feat/local-edition`, based on `e6d0160c4fa9c2790f515719947d7251f89061e6` (`main` and `origin/main` matched when this work began). The pre-change worktree was clean. The main CI run for that commit passed frontend, backend, and Compose jobs: <https://github.com/Joho6666/opportunity-radar/actions/runs/38782106498>.

## Architecture at the baseline

```text
Next.js browser UI ── bearer/Supabase client ── FastAPI
                                                ├── PostgreSQL + pgvector
                                                ├── Redis / Arq worker
                                                └── Scheduler → collectors → Evidence + acquisition pipeline
```

The repository already has a reusable Evidence model, source collectors, collection policy, URL/content/SimHash deduplication, source health, PostgreSQL migrations, and Arq workers. Evidence is written before the acquisition-only opportunity gate, which makes a general-information path feasible. Historical Radar records have no mode field and must retain acquisition behavior when the new field is absent.

## Baseline measurements

| Measurement | Observation | Limits |
|---|---|---|
| Host | Apple M6, 16 GB RAM, 12 CPU cores | This is not the target M4 machine. System load was about 5.37/4.55/4.49 on a shared host. |
| Existing project database | PostgreSQL database approximately 21 MB; PostgreSQL and Redis healthy | This is the existing audit project, not the new local instance. |
| Existing signed-in local identity | 3 Evidence rows, 0 Radars | Other test identities remain isolated and are not part of Local Edition metrics. |
| Frontend checks | lint and TypeScript pass; Vitest 46/46 pass | At the baseline commit. |
| Backend offline tests | 296 passed, 47 infrastructure tests skipped | Database and Redis contracts were skipped; HTTP tests deny live network. |
| Existing UI | 3 warm HTTP requests: 204 ms, 58 ms, 79 ms; 29,733 bytes; all 200 | HTTP response time only, not browser FCP/LCP or cold start. |
| Existing processes | API process RSS about 9 MB; PostgreSQL 52 MB and Redis 11 MB at one sample | Shared-host snapshot, not a controlled idle benchmark. |
| Startup and free-source collection | Not measured in this audit | Measure against the isolated local deployment before claiming an improvement. |

## Authentication, storage, and task findings

- `APP_ENV=local` does not have its own runtime guard. The existing development `AUTH_DISABLED` path accepts direct loopback requests and is not suitable as formal local authentication.
- The UI directly targets `NEXT_PUBLIC_API_BASE_URL`; all local browser API calls need a same-origin proxy, including direct service fetches.
- `enqueue_radar_run()` runs the collection inline if Redis is absent. The local runner must persist the run first and leave it queued if Redis is unavailable.
- PostgreSQL `create_run` and `claim_run` already provide a useful single-run/atomic-claim foundation. Recovery is currently manual and has no worker heartbeat or local dispatch reconciliation.
- Existing evidence list defaults to 100 rows and buyer filtering; favorites are coupled to Opportunity status. General inbox needs evidence-local saved/read state, independent of customer conversion.
- Evidence currently stores one `radar_id` in metadata. Multi-topic attribution needs an additive relation, preserving the current metadata for compatibility.
- General query planning must not reuse the listener fallback that appends “有偿”. The general run path must not call buyer-only opportunity, price, profile-match, or conversion scoring.
- The local edition must use its configured owner ID for every query and aggregate. The cloned database may contain test identities; those records must never enter the personal workspace totals.

## Safe changes and risks

Safe additive changes: a separate Compose project and named volumes; new versioned migrations; optional Radar mode defaulting to the existing acquisition mode; Evidence bookmark/read state; radar-evidence links; local-only API routes behind a local runtime guard; and a UI edition flag that hides old navigation while retaining routes and data.

High-risk areas needing focused validation: cookie/CSRF/Host checks and the server-to-server local credential; ownership and existing RLS behavior; migration adoption/checksums; PostgreSQL snapshot restore; task dispatch after Redis or worker restart; scheduler scoping; and any interaction with copied paid authorization. Paid sources, paid models, mock collectors, and retention deletion remain disabled by default.

## Backup and isolation

Before code changes, a PostgreSQL custom-format backup and a private copy of the current backend environment were created under:

`~/Library/Application Support/Opportunity Radar/backups/pre-local-edition-20261015T194950Z/`

The directory is mode `700`; both files are mode `600`. The original database, its containers, and the user's source environment were not modified. The isolated restore and checksum/migration verification are the next baseline gate.

## Implementation sequence

1. Restore and validate the backup in an isolated PostgreSQL/Redis Compose project.
2. Build the Local Edition navigation/home/inbox and decouple Evidence saved/read state from Opportunities.
3. Add backward-compatible general Radar mode, many-to-many evidence attribution, feed/search and explainable general ranking.
4. Add formal local authentication and the same-origin API proxy while preserving Supabase/JWT behavior.
5. Add the local runner, durable queue reconciliation, launchd integration, private backup/restore commands, and settings for disabled/on-demand AI.
6. Run the requested isolated backend, frontend, security, persistence, visual, and free-source end-to-end checks; report any live-source or M4-specific gap explicitly.
