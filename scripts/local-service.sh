#!/bin/bash
set -euo pipefail

SERVICE="${1:-}"
ENV_FILE="${2:-}"
if [[ "${LOCAL_CLEAN_ENV:-}" != "1" ]]; then
  exec /usr/bin/env -i HOME="$HOME" USER="${USER:-$(id -un)}" LANG="${LANG:-en_US.UTF-8}" \
    PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" \
    LOCAL_CLEAN_ENV=1 /bin/bash "$0" "$SERVICE" "$ENV_FILE"
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ -f "$ENV_FILE" ]] || { printf 'Local Edition runtime config is missing.\n' >&2; exit 1; }
while IFS= read -r line || [[ -n "$line" ]]; do
  [[ -n "$line" && "$line" != \#* && "$line" == *=* ]] || continue
  key="${line%%=*}"
  value="${line#*=}"
  [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
  export "$key=$value"
done < "$ENV_FILE"

LOCAL_RUNTIME_DIR="${LOCAL_RUNTIME_DIR:-}"
[[ -n "$LOCAL_RUNTIME_DIR" ]] || { printf 'Local runtime directory is missing.\n' >&2; exit 1; }
mkdir -p "$LOCAL_RUNTIME_DIR"
chmod 700 "$LOCAL_RUNTIME_DIR"

case "$SERVICE" in
  api)
    cd "$ROOT/backend"
    command=("$LOCAL_PYTHON_EXECUTABLE" -m uvicorn app.main:app --host 127.0.0.1 --port "$LOCAL_API_PORT")
    ;;
  worker)
    cd "$ROOT/backend"
    command=("$LOCAL_PYTHON_EXECUTABLE" -m arq app.workers.settings.WorkerSettings)
    ;;
  scheduler)
    cd "$ROOT/backend"
    command=("$LOCAL_PYTHON_EXECUTABLE" -m app.workers.scheduler)
    ;;
  ui)
    cd "$ROOT"
    command=("$LOCAL_NODE_EXECUTABLE" node_modules/next/dist/bin/next start --hostname 127.0.0.1 --port "$LOCAL_UI_PORT")
    ;;
  *) printf 'Unknown Local Edition service.\n' >&2; exit 2 ;;
esac

heartbeat="$LOCAL_RUNTIME_DIR/$SERVICE.heartbeat"
temporary="$heartbeat.$$.tmp"
[[ ! -L "$heartbeat" && ! -L "$temporary" ]] || { printf 'Refusing symlink heartbeat path.\n' >&2; exit 1; }
rm -f "$heartbeat" "$temporary"
"${command[@]}" &
service_pid=$!
heartbeat_loop() {
  while kill -0 "$service_pid" >/dev/null 2>&1; do
    date +%s > "$temporary"
    mv "$temporary" "$heartbeat"
    sleep 10
  done
}
heartbeat_loop &
ticker_pid=$!
cleanup() {
  kill "$ticker_pid" >/dev/null 2>&1 || true
  kill "$service_pid" >/dev/null 2>&1 || true
  wait "$ticker_pid" >/dev/null 2>&1 || true
  wait "$service_pid" >/dev/null 2>&1 || true
  rm -f "$heartbeat" "$temporary"
}
trap cleanup EXIT TERM INT HUP
if wait "$service_pid"; then service_status=0; else service_status=$?; fi
kill "$ticker_pid" >/dev/null 2>&1 || true
wait "$ticker_pid" >/dev/null 2>&1 || true
rm -f "$heartbeat" "$temporary"
trap - EXIT TERM INT HUP
exit "$service_status"
