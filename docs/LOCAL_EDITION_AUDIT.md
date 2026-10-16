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

The directory is mode `700`; both files are mode `600`. The original database, its containers, and the user's source environment were not modified. A later isolated Local Edition restore and migration verification passed; its evidence is recorded below.

## Implementation sequence

1. Restore and validate the backup in an isolated PostgreSQL/Redis Compose project.
2. Build the Local Edition navigation/home/inbox and decouple Evidence saved/read state from Opportunities.
3. Add backward-compatible general Radar mode, many-to-many evidence attribution, feed/search and explainable general ranking.
4. Add formal local authentication and the same-origin API proxy while preserving Supabase/JWT behavior.
5. Add the local runner, durable queue reconciliation, launchd integration, private backup/restore commands, and settings for disabled/on-demand AI.
6. Run the requested isolated backend, frontend, security, persistence, visual, and free-source end-to-end checks; report any live-source or M4-specific gap explicitly.

## Local Edition implementation and verification (2026-10-15 to 2026-10-16)

Implementation is complete on `feat/local-edition`, based on local commit `739fd60` (which contains this audit). Code and documentation are committed locally; nothing was pushed or merged. The original project database and its containers were not changed. The isolated Local Edition services on ports 54330/6380 were stopped once and restarted through their lifecycle check; no database or volume was reset or removed, and the owner still has the same 3 evidence rows and 0 radars.

Implemented in the working tree:

- Local-only navigation and discovery dashboard, evidence inbox, radar creation/editing, saved/read state, general-information ranking, and multi-radar evidence attribution. Existing acquisition routes and API behavior remain available in cloud mode.
- Same-origin Next.js API routes, loopback-only Local API guards, one-time pairing and HttpOnly session/CSRF protections, and server-side-only proxy credentials.
- Local PostgreSQL/Redis Compose configuration, launchd service wrapper, and `scripts/local.sh` commands for start/stop/status/backup/restore-test/logs. Launchd runs a private code/dependency mirror under Application Support to avoid macOS `~/Documents` privacy denial. The real Local Edition start/stop/start lifecycle and all four service heartbeats passed. PostgreSQL and Redis recovered as healthy with the original volumes; no database was reset or removed.
- Shared buttons, Local Inbox search and filter controls meet the 44px touch-size target.

Validation evidence:

| Check | Result | Scope and limit |
|---|---|---|
| Backend pytest | 349 passed | Explicitly verified QA database `opportunity_radar_contract_20261015a` over loopback port 54334; Redis contract at 6384. Includes the opt-in Local Edition PostgreSQL contract. One upstream Starlette/AnyIO deprecation warning. No live paid API was called. |
| Frontend lint, TypeScript, Vitest | Passed; 54 Vitest tests | Local auth/proxy guard coverage included; completed after the redirect-host correction. Vitest emits expected unavailable-localStorage warnings from existing store tests. |
| Local production build | Passed after the final 44px touch-target adjustment | Built using `.next-local`; optimized build emitted webpack cache size advisories only. |
| Isolated Compose persistence | Passed in a fresh Compose project on ports 54335/6385 | PostgreSQL test row and Redis AOF key both survived container restart and health recovery. Test containers were removed with `compose down`; uniquely named test volumes were retained. This does not validate production backup restoration. |
| Migration repeatability | Passed | Applied the migration command twice against the explicit QA database; 21 migration ledger rows and the new Local Edition schema were present. The migration runner skipped already-recorded files with matching checksums. |
| Browser end-to-end | Passed with a free Hacker News RSS feed in isolated QA identity | Created a radar, fetched 20 items, saved 15, deduplicated 5 in the same run; a second run found all 20 as duplicates. QA retained 15 evidence rows, 1 saved row, and 0 unattached rows; saved state survived an API restart. Paid calls: 0. |
| Mobile interaction | 390px viewport; no horizontal overflow observed | Browser semantics and viewport state were inspected. Ego screenshot capture timed out, so visual screenshot review is still outstanding. |
| Real Local Edition startup, security and lifecycle | Passed on 2026-10-16 | `scripts/local.sh start` synced the working tree and dependencies to the private Application Support app directory, migrated the isolated `opportunity_radar_copy` database from 19 to 21 ledger entries, and launched all four services. API `/ready` and the UI returned healthy; `http://localhost:3004/` redirects to `/pair` and follows to 200. Direct API and same-origin proxy access without a paired session return 401; invalid Host, forwarded-host injection and cross-origin pairing return 403. The pair page is 200. `scripts/local.sh stop` followed by `start` restored PostgreSQL, Redis and all four services; owner-scoped row counts remained 0 radars and 3 evidence rows. Services are currently running at `http://localhost:3004`; owner pairing is still required before viewing data. |
| Local backup and isolated restore | Passed on 2026-10-16 | `scripts/local.sh backup` created a private custom-format PostgreSQL archive and private configuration copy. `scripts/local.sh restore-test` restored it into a new database without overwriting the active database; the copy reported 21 migrations, 503 total radars, 982 evidence rows and 457 radar-evidence links across all identities. The current owner remains scoped to 0 radars and 3 evidence rows. Backup and config files are mode 600 under the mode-700 private directory. |
| Performance comparison | Not completed | Baseline values above are shared-host snapshots and warm HTTP timings, not a controlled before/after comparison. No resource or performance improvement is claimed. |
| Target hardware and soak | Not completed | Current host is M6/16GB, not the target Mac mini M4. Seven-day reliability remains a future observation. |

### Test isolation incident

During an earlier test invocation, an explicitly empty `DATABASE_URL` was ignored by configuration loading, which then fell back to the repository `.env`. That invocation applied the two new migrations and created test records in the audit PostgreSQL instance on port 54329. No data was deleted. Testing against that audit instance was stopped; subsequent full pytest and end-to-end runs used the dedicated QA project/database on port 54334, and the Local Edition database on port 54330 was not touched. This incident is recorded so future test commands must provide a non-empty, explicit QA database URL and verify its host/database before pytest starts.

### Remaining verification gaps

- Final lint, TypeScript, 54 Vitest tests, Local production build, 349 pytest tests against an explicitly verified QA database URL, shell syntax checks, runtime default checks, and `git diff --check` passed after the redirect-host correction.
- Ego Browser could not produce screenshots because `Page.captureScreenshot` timed out. Ego Lite reported an available update (current version 0.5.1.13); the current TaskSpace was finished, and no upgrade was run without user approval.
- LaunchAgent recovery after a macOS reboot remains unverified. The Local Edition `stop`/`start` lifecycle passed, and owner-scoped data survived the restart.
- `launchctl print` during startup diagnosis expanded an inherited `MOSS_API_KEY` in tool output. The key was not copied into the repository, runtime configuration, or service logs; `scripts/local-service.sh` now starts each child with a clean allowlisted environment, and process inspection confirmed provider keys are absent. Treat the displayed key as exposed and rotate it at its provider.
- The free-source end-to-end run preceded the final launcher and redirect fixes; those changes do not alter collector or storage code, but the full browser collection flow has not been repeated against the newly launched Local UI. The RSS result remains a point-in-time observation rather than evidence of broad source coverage or long-term reliability.
