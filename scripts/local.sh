#!/bin/bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_HOME="${OPPORTUNITY_RADAR_HOME:-$HOME/Library/Application Support/Opportunity Radar}"
RUNTIME_ROOT="$APP_HOME/app"
CONFIG_DIR="$APP_HOME/config"
LOG_DIR="$APP_HOME/logs"
BACKUP_DIR="$APP_HOME/backups"
LOCAL_ENV="$CONFIG_DIR/local.env"
RUNTIME_ENV="$CONFIG_DIR/local-runtime.env"
RUNTIME_MARKER="$CONFIG_DIR/runtime-source"
COMPOSE_PROJECT="${OPPORTUNITY_RADAR_COMPOSE_PROJECT:-opportunity-radar-local}"
COMPOSE=(docker compose -p "$COMPOSE_PROJECT" -f "$ROOT/docker-compose.local.yml" --env-file "$LOCAL_ENV")
DOMAIN="com.joho.opportunity-radar.local"
UID_NUM="$(id -u)"
AGENT_DIR="$HOME/Library/LaunchAgents"

die() { printf '错误：%s\n' "$1" >&2; exit 1; }
require_config() {
  [[ -f "$LOCAL_ENV" ]] || die "未找到私有本地配置：$LOCAL_ENV。请先恢复独立 Local Edition 数据库并初始化配置。"
  [[ ! -L "$APP_HOME" && ! -L "$CONFIG_DIR" && ! -L "$LOG_DIR" && ! -L "$BACKUP_DIR" ]] || die "本地应用目录不能通过符号链接重定向。"
  [[ ! -L "$LOCAL_ENV" ]] || die "local.env 不能是符号链接。"
  mkdir -p "$CONFIG_DIR" "$LOG_DIR" "$BACKUP_DIR"
  chmod 700 "$APP_HOME" "$CONFIG_DIR" "$LOG_DIR" "$BACKUP_DIR"
  chmod 600 "$LOCAL_ENV"
  [[ "$(stat -f '%Lp' "$LOCAL_ENV")" == "600" ]] || die "local.env 权限必须为 600。"
}
python_bin() {
  if [[ -x "$RUNTIME_ROOT/.venv/bin/python" ]]; then echo "$RUNTIME_ROOT/.venv/bin/python";
  elif [[ -x "$ROOT/.venv/bin/python" ]]; then echo "$ROOT/.venv/bin/python";
  elif [[ -x "$ROOT/backend/.venv/bin/python" ]]; then echo "$ROOT/backend/.venv/bin/python";
  else die "缺少项目 Python 虚拟环境，请按 backend/requirements.txt 安装依赖。"; fi
}
node_bin() { command -v node || die "未找到 Node.js。"; }
compose() { "${COMPOSE[@]}" "$@"; }

sync_runtime_app() {
  [[ ! -L "$RUNTIME_ROOT" ]] || die "本地运行副本不能是符号链接。"
  [[ -d "$ROOT/node_modules" && -x "$ROOT/.venv/bin/python" ]] || die "请先在仓库中安装 node_modules 和 .venv 依赖。"
  if [[ -d "$RUNTIME_ROOT" && ! -f "$RUNTIME_MARKER" ]]; then
    die "运行副本目录已存在但没有 Opportunity Radar 标记；为避免覆盖未知文件，已停止。"
  fi
  mkdir -p "$RUNTIME_ROOT"
  chmod 700 "$RUNTIME_ROOT"
  rsync -a \
    --exclude='/.git/' --exclude='/outputs/' --exclude='/.ui-design/' \
    --exclude='/.next/' --exclude='/.next-dev/' --exclude='/.next-local/' \
    --exclude='**/.env' --exclude='**/.env.*' \
    "$ROOT/" "$RUNTIME_ROOT/"
  chmod 700 "$RUNTIME_ROOT"
  printf '%s\n' "$ROOT" > "$RUNTIME_MARKER"
  chmod 600 "$RUNTIME_MARKER"
}

load_private_config() {
  require_config
  local py
  py="$(python_bin)"
  "$py" - "$LOCAL_ENV" "$RUNTIME_ENV" "$RUNTIME_ROOT" "$APP_HOME" "$py" "$(node_bin)" <<'PY'
from pathlib import Path
from urllib.parse import urlsplit
import os, sys
source, target, root, home = map(Path, sys.argv[1:5])
python_executable, node_executable = sys.argv[5:7]
values = {}
for line in source.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        key, value = line.split('=', 1)
        values[key.strip()] = value.strip().strip('"\'')
required = ('LOCAL_DATABASE_URL','LOCAL_REDIS_URL','LOCAL_PROXY_TOKEN','LOCAL_SESSION_SECRET','LOCAL_USER_ID','LOCAL_DB_PASSWORD')
missing = [key for key in required if not values.get(key)]
if missing: raise SystemExit('本地配置字段缺失：' + ', '.join(missing))
db = urlsplit(values['LOCAL_DATABASE_URL'].replace('postgresql+psycopg://','postgresql://'))
redis = urlsplit(values['LOCAL_REDIS_URL'])
if db.hostname not in ('127.0.0.1','localhost','::1') or redis.hostname not in ('127.0.0.1','localhost','::1'):
    raise SystemExit('本地版 PostgreSQL 与 Redis 必须仅连接 loopback。')
from urllib.parse import unquote
if unquote(db.password or '') != values['LOCAL_DB_PASSWORD']:
    raise SystemExit('本地数据库 URL 凭据与 Compose 数据库凭据不匹配。')
if len(values['LOCAL_PROXY_TOKEN']) < 64 or len(values['LOCAL_SESSION_SECRET']) < 64:
    raise SystemExit('本地认证凭据强度不足。')
api_port = values.get('LOCAL_API_PORT', '8015')
ui_port = values.get('LOCAL_UI_PORT', '3004')
origin = f'http://localhost:{ui_port}'
service = {
 'APP_ENV':'local','DATABASE_URL':values['LOCAL_DATABASE_URL'],'REDIS_URL':values['LOCAL_REDIS_URL'],
 'USE_IN_MEMORY_STORE':'false','AUTH_DISABLED':'false','LOCAL_USER_ID':values['LOCAL_USER_ID'],
 'LOCAL_PROXY_TOKEN':values['LOCAL_PROXY_TOKEN'],'LOCAL_SESSION_SECRET':values['LOCAL_SESSION_SECRET'],
 'LOCAL_API_PORT':api_port,'LOCAL_API_BASE_URL':f'http://127.0.0.1:{api_port}',
 'LOCAL_UI_PORT':ui_port,'LOCAL_UI_ORIGIN':origin,
 'LOCAL_RUNTIME_DIR':str(home/'run'),
 'LOCAL_PRIVATE_CONFIG_DIR':str(home/'config'),
 'CORS_ORIGINS':origin,'INCLUDE_MOCK_COLLECTOR':'false','PAID_API_ENABLED':'false',
 'ENABLE_AI_CLASSIFICATION':'false','LOCAL_CLASSIFIER_MODE':'off','LOCAL_CLASSIFIER_PATH':'',
 'ALLOW_RETENTION_DELETE':'false','TIKHUB_API_KEY':'','FIRECRAWL_API_KEY':'','LLM_API_KEY':'',
 'LLM_BASE_URL':'','LLM_MODEL':'','LLM_FAST_MODEL':'','GITHUB_TOKEN':'',
 'NEXT_PUBLIC_APP_MODE':'local','NEXT_PUBLIC_USE_MOCK':'false','NEXT_PUBLIC_AUTH_DISABLED':'false',
 'NEXT_PUBLIC_API_BASE_URL':'','NEXT_PUBLIC_SUPABASE_URL':'','NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY':'',
 'LOCAL_PYTHON_EXECUTABLE':python_executable,'LOCAL_NODE_EXECUTABLE':node_executable,
 'NODE_ENV':'production','NEXT_BUILD_DIR':'.next-local','PATH':'/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin',
}
# Only this explicit opt-in is imported; other development providers stay blank.
manual = values.get('LOCAL_MANUAL_TIKHUB_ENABLED', 'false').lower() == 'true'
service['LOCAL_MANUAL_TIKHUB_ENABLED'] = str(manual).lower()
if manual:
    if not values.get('TIKHUB_API_KEY'): raise SystemExit('手动 TikHub 已启用但未配置密钥。')
    service.update({
        'PAID_API_ENABLED':'true', 'TIKHUB_API_KEY':values['TIKHUB_API_KEY'],
        'TIKHUB_BASE_URL':values.get('TIKHUB_BASE_URL','https://api.tikhub.io'),
        'TIKHUB_ENDPOINT_PRICES_JSON':values.get('TIKHUB_ENDPOINT_PRICES_JSON','{}'),
        'TIKHUB_PRICE_RECEIPTS_JSON':values.get('TIKHUB_PRICE_RECEIPTS_JSON','{}'),
        'PAID_DAILY_COST_LIMIT':values.get('PAID_DAILY_COST_LIMIT','1'),
        'PAID_DAILY_REQUEST_LIMIT':values.get('PAID_DAILY_REQUEST_LIMIT','20'),
        'ALLOW_FAKE_IP_DNS':values.get('ALLOW_FAKE_IP_DNS','false'),
    })
    from urllib.parse import urlsplit
    if service['TIKHUB_BASE_URL'] not in ('https://api.tikhub.io','https://api.tikhub.dev'):
        raise SystemExit('TikHub 必须使用官方 HTTPS 地址。')
    from decimal import Decimal
    if not Decimal('0') < Decimal(service['PAID_DAILY_COST_LIMIT']) <= Decimal('1'):
        raise SystemExit('本机手动采集每日费用上限必须不超过 USD 1。')
    if not 1 <= int(service['PAID_DAILY_REQUEST_LIMIT']) <= 20:
        raise SystemExit('本机手动采集每日最多20请求。')
for key in ('HTTP_PROXY','HTTPS_PROXY','ALL_PROXY','NO_PROXY','http_proxy','https_proxy','all_proxy','no_proxy'):
    if os.environ.get(key): service[key] = os.environ[key]
target.parent.mkdir(parents=True, exist_ok=True); os.chmod(target.parent, 0o700)
if target.is_symlink(): raise SystemExit('local-runtime.env 不能是符号链接。')
target.write_text(''.join(f'{key}={value}\n' for key,value in service.items()))
os.chmod(target, 0o600)
PY
}

write_launch_agents() {
  local py
  py="$(python_bin)"
  mkdir -p "$AGENT_DIR"; chmod 700 "$AGENT_DIR"
  "$py" - "$RUNTIME_ENV" "$RUNTIME_ROOT" "$AGENT_DIR" "$LOG_DIR" <<'PY'
from pathlib import Path
import plistlib, sys
env_path, root, agents, logs = map(Path, sys.argv[1:])
wrapper = root/'scripts/local-service.sh'
for name in ('api','worker','scheduler','ui'):
    label=f'com.joho.opportunity-radar.local.{name}'
    plist={'Label':label,'ProgramArguments':['/bin/bash',str(wrapper),name,str(env_path)],'WorkingDirectory':str(root),
           'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':5,
           'StandardOutPath':str(logs/f'{name}.log'),'StandardErrorPath':str(logs/f'{name}.error.log')}
    target=agents/f'{label}.plist'
    target.write_bytes(plistlib.dumps(plist,fmt=plistlib.FMT_XML,sort_keys=True)); target.chmod(0o600)
PY
}

agent_state() {
  local name="$1" label="$DOMAIN.$1"
  local details state pid
  if details="$(launchctl print "gui/$UID_NUM/$label" 2>/dev/null)"; then
    state="$(printf '%s\n' "$details" | awk -F' = ' '/^[[:space:]]*state =/{print $2;exit}')"
    pid="$(printf '%s\n' "$details" | awk -F' = ' '/^[[:space:]]*pid =/{print $2;exit}')"
    printf '%-10s %s%s\n' "$name" "${state:-loaded}" "${pid:+ (pid $pid)}"
  else printf '%-10s stopped\n' "$name"; fi
}

service_heartbeat() {
  local name="$1" file="$APP_HOME/run/$1.heartbeat" stamp age
  if [[ ! -f "$file" || -L "$file" ]]; then printf '%-10s heartbeat missing\n' "$name"; return; fi
  stamp="$(cat "$file" 2>/dev/null || true)"
  if [[ ! "$stamp" =~ ^[0-9]+$ ]]; then printf '%-10s heartbeat invalid\n' "$name"; return; fi
  age="$(( $(date +%s) - stamp ))"
  if (( age < 0 || age > 35 )); then printf '%-10s heartbeat stale (%ss)\n' "$name" "$age"; else printf '%-10s healthy heartbeat (%ss ago)\n' "$name" "$age"; fi
}

services_healthy() {
  local api_port="$1" ui_port="$2" name file stamp age
  curl --max-time 2 -fsS "http://127.0.0.1:$api_port/ready" >/dev/null 2>&1 || return 1
  curl --resolve "localhost:$ui_port:127.0.0.1" --max-time 2 -fsS "http://localhost:$ui_port/" >/dev/null 2>&1 || return 1
  for name in api worker scheduler ui; do
    file="$APP_HOME/run/$name.heartbeat"
    [[ -f "$file" && ! -L "$file" ]] || return 1
    stamp="$(cat "$file" 2>/dev/null || true)"
    [[ "$stamp" =~ ^[0-9]+$ ]] || return 1
    age="$(( $(date +%s) - stamp ))"
    (( age >= 0 && age <= 35 )) || return 1
  done
}

assert_port_free() {
  local port="$1" label="$2"
  if lsof -nP -iTCP:"$port" -sTCP:LISTEN -t >/dev/null 2>&1; then die "$label 端口 $port 已被其他进程占用。"; fi
}

local_db_name() {
  python3 - "$LOCAL_ENV" <<'PY'
from pathlib import Path
from urllib.parse import urlsplit
import sys
values=dict(line.split('=',1) for line in Path(sys.argv[1]).read_text().splitlines() if '=' in line and not line.lstrip().startswith('#'))
url=values['LOCAL_DATABASE_URL'].strip().strip('"\'').replace('postgresql+psycopg://','postgresql://')
print(urlsplit(url).path.lstrip('/'))
PY
}

start() {
  [[ "$(uname -s)" == "Darwin" ]] || die "scripts/local.sh 当前面向 macOS LaunchAgent。"
  require_config
  sync_runtime_app
  load_private_config
  local py ui_port api_port
  py="$(python_bin)"; ui_port="$(awk -F= '$1=="LOCAL_UI_PORT"{print $2}' "$LOCAL_ENV" | tail -1)"; ui_port="${ui_port:-3004}"
  api_port="$(awk -F= '$1=="LOCAL_API_PORT"{print $2}' "$LOCAL_ENV" | tail -1)"; api_port="${api_port:-8015}"
  for name in ui scheduler worker api; do
    if launchctl print "gui/$UID_NUM/$DOMAIN.$name" >/dev/null 2>&1; then
      die "Local Edition 服务已注册。请先运行 scripts/local.sh stop，再重新启动；现有进程保持不变。"
    fi
  done
  local pg_port redis_port
  pg_port="$(awk -F= '$1=="LOCAL_PG_PORT"{print $2}' "$LOCAL_ENV" | tail -1)"; pg_port="${pg_port:-54330}"
  redis_port="$(awk -F= '$1=="LOCAL_REDIS_PORT"{print $2}' "$LOCAL_ENV" | tail -1)"; redis_port="${redis_port:-6380}"
  if ! docker inspect -f '{{.State.Running}}' opportunity-radar-local-postgres-1 2>/dev/null | rg -q '^true$'; then assert_port_free "$pg_port" PostgreSQL; fi
  if ! docker inspect -f '{{.State.Running}}' opportunity-radar-local-redis-1 2>/dev/null | rg -q '^true$'; then assert_port_free "$redis_port" Redis; fi
  assert_port_free "$api_port" API
  assert_port_free "$ui_port" Next.js
  compose up -d --wait postgres redis
  export APP_ENV=local DATABASE_URL="$(awk -F= '$1=="LOCAL_DATABASE_URL"{sub(/^[^=]*=/,"");print;exit}' "$LOCAL_ENV")"
  export REDIS_URL="$(awk -F= '$1=="LOCAL_REDIS_URL"{sub(/^[^=]*=/,"");print;exit}' "$LOCAL_ENV")"
  export LOCAL_USER_ID="$(awk -F= '$1=="LOCAL_USER_ID"{print $2;exit}' "$LOCAL_ENV")" USE_IN_MEMORY_STORE=false AUTH_DISABLED=false
  export LOCAL_PROXY_TOKEN="$(awk -F= '$1=="LOCAL_PROXY_TOKEN"{print $2;exit}' "$LOCAL_ENV")" LOCAL_SESSION_SECRET="$(awk -F= '$1=="LOCAL_SESSION_SECRET"{print $2;exit}' "$LOCAL_ENV")"
  export LOCAL_API_PORT="$api_port" LOCAL_UI_PORT="$ui_port" CORS_ORIGINS="http://localhost:$ui_port"
  export LOCAL_API_BASE_URL="http://127.0.0.1:$api_port" LOCAL_UI_ORIGIN="http://localhost:$ui_port"
  export PAID_API_ENABLED=false ENABLE_AI_CLASSIFICATION=false LOCAL_CLASSIFIER_MODE=off INCLUDE_MOCK_COLLECTOR=false ALLOW_RETENTION_DELETE=false
  export NEXT_PUBLIC_APP_MODE=local NEXT_PUBLIC_USE_MOCK=false NEXT_PUBLIC_AUTH_DISABLED=false NEXT_PUBLIC_API_BASE_URL='' NEXT_PUBLIC_SUPABASE_URL='' NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY='' NEXT_BUILD_DIR=.next-local
  (cd "$RUNTIME_ROOT/backend" && MIGRATIONS_DIR="$RUNTIME_ROOT/supabase/migrations" "$py" -m app.database.migrate)
  (cd "$RUNTIME_ROOT" && NEXT_BUILD_DIR=.next-local npm run build)
  write_launch_agents
  chmod 700 "$ROOT/scripts/local.sh" "$RUNTIME_ROOT/scripts/local-service.sh"
  local started_agents=()
  for name in api worker scheduler ui; do
    local label="$DOMAIN.$name" plist="$AGENT_DIR/$DOMAIN.$name.plist"
    if ! launchctl bootstrap "gui/$UID_NUM" "$plist"; then
      for registered in "${started_agents[@]}"; do launchctl bootout "gui/$UID_NUM/$DOMAIN.$registered" >/dev/null 2>&1 || true; done
      die "无法启动 $name 服务；本次已注册的其他服务已停止，数据库和备份保持不变。"
    fi
    started_agents+=("$name")
  done
  local ready=false
  for _ in {1..25}; do
    if services_healthy "$api_port" "$ui_port"; then ready=true; break; fi
    sleep 1
  done
  if [[ "$ready" != true ]]; then
    for name in ui scheduler worker api; do launchctl bootout "gui/$UID_NUM/$DOMAIN.$name" >/dev/null 2>&1 || true; done
    die "Local Edition 健康检查失败；已停止本次服务注册，数据库卷保留。请运行 scripts/local.sh logs 检查日志。"
  fi
  status
  printf '\n工作台地址：http://localhost:%s\n' "$ui_port"
  printf '直接打开即可使用，无需配对码。\n'
}

stop() {
  for name in ui scheduler worker api; do
    local label="$DOMAIN.$name"
    launchctl bootout "gui/$UID_NUM/$label" >/dev/null 2>&1 || true
  done
  if [[ -f "$LOCAL_ENV" ]]; then compose stop postgres redis >/dev/null 2>&1 || true; fi
  printf 'Local Edition 已停止；数据库卷和业务数据保留。\n'
}

status() {
  require_config
  printf '后台服务（用户 LaunchAgent）：\n'
  for name in api worker scheduler ui; do agent_state "$name"; done
  printf '\n服务心跳：\n'
  for name in api worker scheduler ui; do service_heartbeat "$name"; done
  local pg_port redis_port ui_port api_port
  pg_port="$(awk -F= '$1=="LOCAL_PG_PORT"{print $2}' "$LOCAL_ENV" | tail -1)"; pg_port="${pg_port:-54330}"
  redis_port="$(awk -F= '$1=="LOCAL_REDIS_PORT"{print $2}' "$LOCAL_ENV" | tail -1)"; redis_port="${redis_port:-6380}"
  ui_port="$(awk -F= '$1=="LOCAL_UI_PORT"{print $2}' "$LOCAL_ENV" | tail -1)"; ui_port="${ui_port:-3004}"
  api_port="$(awk -F= '$1=="LOCAL_API_PORT"{print $2}' "$LOCAL_ENV" | tail -1)"; api_port="${api_port:-8015}"
  compose ps 2>/dev/null || printf 'PostgreSQL/Redis: stopped or unavailable\n'
  if curl --max-time 2 -fsS "http://127.0.0.1:$api_port/ready" >/dev/null 2>&1; then printf 'API        healthy\n'; else printf 'API        unavailable\n'; fi
  if curl --resolve "localhost:$ui_port:127.0.0.1" --max-time 2 -fsS "http://localhost:$ui_port/" >/dev/null 2>&1; then printf 'Next.js    healthy (http://localhost:%s)\n' "$ui_port"; else printf 'Next.js    unavailable\n'; fi
}

backup() {
  require_config
  mkdir -p "$BACKUP_DIR"; chmod 700 "$BACKUP_DIR"
  local stamp file temporary dbname listfile config_copy
  umask 077
  stamp="$(date -u +%Y%m%dT%H%M%SZ)-$$"; file="$BACKUP_DIR/local-$stamp.dump"; temporary="$BACKUP_DIR/.local-$stamp.dump.tmp"; listfile="$BACKUP_DIR/local-$stamp.manifest"
  config_copy="$BACKUP_DIR/local-$stamp.env"
  dbname="$(local_db_name)"
  if ! compose exec -T postgres pg_dump -U postgres -Fc -d "$dbname" > "$temporary"; then rm -f "$temporary"; die "数据库快照失败；未保留不完整备份。"; fi
  chmod 600 "$temporary"
  if ! cat "$temporary" | compose exec -T postgres pg_restore --list > "$listfile"; then rm -f "$temporary" "$listfile"; die "备份归档无法读取，请保留现有数据并检查容器日志。"; fi
  mv "$temporary" "$file"
  python3 - "$LOCAL_ENV" "$BACKUP_DIR/local-$stamp.txt" "$stamp" "$dbname" "$COMPOSE_PROJECT" <<'PY'
from pathlib import Path
import sys
values=dict(line.split('=',1) for line in Path(sys.argv[1]).read_text().splitlines() if '=' in line and not line.lstrip().startswith('#'))
target=Path(sys.argv[2])
target.write_text(f"created_utc={sys.argv[3]}\ndatabase={sys.argv[4]}\nuser_id={values['LOCAL_USER_ID']}\npostgres_port={values.get('LOCAL_PG_PORT','54330')}\nredis_port={values.get('LOCAL_REDIS_PORT','6380')}\napi_port={values.get('LOCAL_API_PORT','8015')}\nui_port={values.get('LOCAL_UI_PORT','3004')}\nproject={sys.argv[5]}\nprivate_config_copy=local-{sys.argv[3]}.env\nprivate_config_mode=600\n")
target.chmod(0o600)
PY
  chmod 600 "$listfile"
  cp "$LOCAL_ENV" "$config_copy"
  chmod 600 "$config_copy"
  printf '已完成 PostgreSQL 一致性快照（Compose 项目 %s）：%s\n' "$COMPOSE_PROJECT" "$file"
  printf '必要的本地配置已保存到仅当前用户可读的备份文件：%s\n' "$config_copy"
  printf '备份清单：%s\n' "$BACKUP_DIR/local-$stamp.txt"
}

restore_test() {
  require_config
  [[ -f "${2:-}" ]] || die "用法：scripts/local.sh restore-test <备份.dump>"
  local name="$2" db="or_restore_$(date -u +%Y%m%d%H%M%S)_$$"
  compose exec -T postgres createdb -U postgres "$db"
  cat "$name" | compose exec -T postgres pg_restore --exit-on-error --no-owner -U postgres -d "$db"
  compose exec -T postgres psql -U postgres -d "$db" -Atc "select 'migrations='||count(*) from public.schema_migrations; select 'radars='||count(*) from public.radars; select 'evidence='||count(*) from public.evidence_items; select 'radar_evidence='||count(*) from public.radar_evidence;"
  printf '隔离恢复已保存在 Compose 项目 %s 的新数据库 %s；未覆盖当前数据库。\n' "$COMPOSE_PROJECT" "$db"
}

pair() {
  printf '本机配对已移除，请直接打开 http://localhost:3004（无需配对码）。\n'
}

logs() {
  local service="${2:-}"
  if [[ -z "$service" ]]; then tail -n 80 "$LOG_DIR"/*.log "$LOG_DIR"/*.error.log 2>/dev/null || true
  elif [[ "$service" =~ ^(api|worker|scheduler|ui)$ ]]; then tail -n 120 -f "$LOG_DIR/$service.log" "$LOG_DIR/$service.error.log"
  else die "logs 服务名应为 api、worker、scheduler 或 ui。"; fi
}

case "${1:-}" in
  start) start ;;
  stop) stop ;;
  status) status ;;
  backup) backup ;;
  restore-test) restore_test "$@" ;;
  pair) pair ;;
  logs) logs "$@" ;;
  *) printf '用法：scripts/local.sh {start|stop|status|backup|restore-test <dump>|pair|logs [api|worker|scheduler|ui]}\n'; exit 2 ;;
esac
