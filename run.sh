#!/usr/bin/env bash

set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${PYTHON:-$ROOT_DIR/.venv/bin/python}"
SERVICE_HOST="${SERVICE_HOST:-127.0.0.1}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Shared Python environment not found: $PYTHON" >&2
  echo "Create it with: python3 -m venv .venv" >&2
  exit 1
fi

service_pids=()
services=(
  "crm|crm_service.app:app|8001|crm_service/app.py"
  "product|product_service.app:app|8002|product_service/app.py"
  "shopping|shopping_service.app:app|8003|shopping_service/app.py"
  "site|site_service.app:app|8004|site_service/app.py"
  "feedback|feedback_service.app:app|8005|feedback_service/app.py"
  "marketing|marketing_service.app:app|8006|marketing_service/app.py"
)

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

  free_port 8080
  echo "Starting simulator on http://$SERVICE_HOST:8080"
  PYTHONUNBUFFERED=1 "$PYTHON" "$server_file" &
  service_pids+=("$!")
}

for service in "${services[@]}"; do
  IFS="|" read -r name module port module_file <<< "$service"
  start_service "$name" "$module" "$port" "$module_file"
done
start_simulator

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