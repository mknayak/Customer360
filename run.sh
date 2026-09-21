#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "$ROOT_DIR/.env"
  set +a
fi
PYTHON="${PYTHON:-$ROOT_DIR/.venv/bin/python}"
SERVICE_HOST="${SERVICE_HOST:-127.0.0.1}"
CRM_PORT="${CRM_PORT:-8001}"
PRODUCT_PORT="${PRODUCT_PORT:-8002}"
SHOPPING_PORT="${SHOPPING_PORT:-8003}"
SITE_PORT="${SITE_PORT:-8004}"
FEEDBACK_PORT="${FEEDBACK_PORT:-8005}"
MARKETING_PORT="${MARKETING_PORT:-8006}"
EVENTS_PORT="${EVENTS_PORT:-8007}"
ORCHESTRATION_PORT="${ORCHESTRATION_PORT:-8008}"
AGENT_APP_PORT="${AGENT_APP_PORT:-8009}"
DATA_PLATFORM_PORT="${DATA_PLATFORM_PORT:-8010}"
SIMULATOR_PORT="${SIMULATOR_PORT:-8080}"
export EVENT_SERVICE_URL="${EVENT_SERVICE_URL:-http://$SERVICE_HOST:$EVENTS_PORT}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Shared Python environment not found: $PYTHON" >&2
  echo "Create it with: python3 -m venv .venv" >&2
  exit 1
fi

service_pids=()
services=(
  "crm|crm_service.app:app|$CRM_PORT|crm_service/app.py"
  "product|product_service.app:app|$PRODUCT_PORT|product_service/app.py"
  "shopping|shopping_service.app:app|$SHOPPING_PORT|shopping_service/app.py"
  "site|site_service.app:app|$SITE_PORT|site_service/app.py"
  "feedback|feedback_service.app:app|$FEEDBACK_PORT|feedback_service/app.py"
  "marketing|marketing_service.app:app|$MARKETING_PORT|marketing_service/app.py"
  "events|event_service.app:app|$EVENTS_PORT|event_service/app.py"
  "orchestration|orchestration_service.app:app|$ORCHESTRATION_PORT|orchestration_service/app.py"
)

agent_app_port="$AGENT_APP_PORT"
data_platform_port="$DATA_PLATFORM_PORT"

free_port() {
  local port="$1"
  local pids

  pids="$(lsof -tiTCP:"$port" -sTCP:LISTEN 2>/dev/null || true)"
  if [[ -z "$pids" ]]; then
    return
  fi

  echo "Force-stopping process(es) using port $port: $pids"
  while read -r pid; do
    [[ -z "$pid" ]] || kill -KILL "$pid" 2>/dev/null || true
  done <<< "$pids"
}

cleanup() {
  exit_code=$?
  trap - EXIT INT TERM
  if [[ ${#service_pids[@]} -gt 0 ]]; then
    for pid in "${service_pids[@]}"; do
      kill "$pid" 2>/dev/null || true
    done
    for pid in "${service_pids[@]}"; do
      wait "$pid" 2>/dev/null || true
    done
  fi
  exit "$exit_code"
}

trap cleanup EXIT INT TERM

start_service() {
  local name="$1"
  local module="$2"
  local port="$3"
  local module_file="$4"
  local service_dir="$ROOT_DIR/Enterprise/Services/$name"
  local app_file="$service_dir/$module_file"

  if [[ ! -f "$app_file" ]]; then
    echo "Skipping $name: $app_file does not exist yet"
    return
  fi

  free_port "$port"
  echo "Starting $name on http://$SERVICE_HOST:$port"
  PYTHONUNBUFFERED=1 "$PYTHON" -m uvicorn "$module" \
    --app-dir "$service_dir" \
    --host "$SERVICE_HOST" \
    --port "$port" &
  service_pids+=("$!")
}

start_simulator() {
  local simulator_dir="$ROOT_DIR/Enterprise/Simulator"
  local server_file="$simulator_dir/server.py"

  if [[ ! -f "$server_file" ]]; then
    echo "Skipping simulator: $server_file does not exist yet"
    return
  fi

  free_port "$SIMULATOR_PORT"
  echo "Starting simulator on http://$SERVICE_HOST:8080"
  PYTHONUNBUFFERED=1 "$PYTHON" "$server_file" &
  service_pids+=("$!")
}

start_agent_app() {
  local agent_app_module="Agent.app.main:app"
  local agent_app_dir="$ROOT_DIR"

  free_port "$agent_app_port"
  echo "Starting agent app on http://$SERVICE_HOST:$agent_app_port"
  PYTHONUNBUFFERED=1 "$PYTHON" -m uvicorn "$agent_app_module" \
    --app-dir "$agent_app_dir" \
    --host "$SERVICE_HOST" \
    --port "$agent_app_port" &
  service_pids+=("$!")
}

start_data_platform() {
  local data_platform_dir="$ROOT_DIR/Enterprise/DataPlatform"
  free_port "$data_platform_port"
  echo "Starting data platform on http://$SERVICE_HOST:$data_platform_port"
  PYTHONUNBUFFERED=1 "$PYTHON" -m uvicorn data_platform.app:app \
    --app-dir "$data_platform_dir" \
    --host "$SERVICE_HOST" \
    --port "$data_platform_port" &
  service_pids+=("$!")
}

for service in "${services[@]}"; do
  IFS="|" read -r name module port module_file <<< "$service"
  start_service "$name" "$module" "$port" "$module_file"
done
start_simulator
start_agent_app
start_data_platform

if [[ ${#service_pids[@]} -eq 0 ]]; then
  echo "No implemented services were found." >&2
  exit 1
fi

echo "Services are running. Press Ctrl+C to stop them."
while true; do
  for pid in "${service_pids[@]}"; do
    if ! kill -0 "$pid" 2>/dev/null; then
      wait "$pid" 2>/dev/null || true
      echo "A service stopped unexpectedly." >&2
      exit 1
    fi
  done
  sleep 1
done