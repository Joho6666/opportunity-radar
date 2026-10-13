#!/usr/bin/env bash
set -euo pipefail
# Run only against the caller's explicitly selected isolated Compose project.
project="${COMPOSE_PROJECT_NAME:-opportunity-radar-smoke}"
export API_PORT="${API_PORT:-8012}"
compose=(docker compose -p "$project")
"${compose[@]}" up -d --build
for attempt in {1..45}; do
  if curl -fsS "http://127.0.0.1:$API_PORT/ready" > /dev/null; then break; fi
  sleep 2
done
curl -fsS "http://127.0.0.1:$API_PORT/ready"
"${compose[@]}" ps -a
"${compose[@]}" exec -T postgres psql -U postgres -d opportunity_radar -v ON_ERROR_STOP=1 -c "INSERT INTO auth.users(id) VALUES('00000000-0000-0000-0000-00000000abcd') ON CONFLICT DO NOTHING; INSERT INTO profiles(user_id,display_name) VALUES('00000000-0000-0000-0000-00000000abcd','compose-persistence-contract') ON CONFLICT(user_id) DO NOTHING;"
"${compose[@]}" exec -T redis redis-cli SET radar-smoke-persistence survives-restart EX 600
"${compose[@]}" exec -T redis redis-cli SAVE
"${compose[@]}" restart postgres redis backend
for attempt in {1..45}; do
  if curl -fsS "http://127.0.0.1:$API_PORT/ready" > /dev/null; then break; fi
  sleep 2
done
curl -fsS "http://127.0.0.1:$API_PORT/ready"
pg_value=$("${compose[@]}" exec -T postgres psql -U postgres -d opportunity_radar -tAc "SELECT display_name FROM profiles WHERE user_id='00000000-0000-0000-0000-00000000abcd'")
redis_value=$("${compose[@]}" exec -T redis redis-cli GET radar-smoke-persistence)
test "$pg_value" = compose-persistence-contract
test "$redis_value" = survives-restart
"${compose[@]}" run --rm migrate
printf '\nCompose readiness, PostgreSQL/Redis restart persistence and migration no-op passed.\n'
