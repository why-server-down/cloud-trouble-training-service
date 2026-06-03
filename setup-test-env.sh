#!/usr/bin/env bash
set -euo pipefail

COMPOSE_ARGS=()
if [[ "${1:-}" == "--monitoring" ]]; then
  COMPOSE_ARGS+=(--profile monitoring)
fi

echo "Starting K8s Survival Camp with Docker Compose..."

if ! docker info >/dev/null 2>&1; then
  echo "Docker is not running. Start Docker Desktop and retry." >&2
  exit 1
fi

HOST_KUBECONFIG="${KUBECONFIG:-$HOME/.kube/config}"
RUNTIME_KUBECONFIG=".runtime/kubeconfig"

if [[ ! -f "$HOST_KUBECONFIG" ]]; then
  echo "Kubeconfig not found at $HOST_KUBECONFIG. Enable Docker Desktop Kubernetes first." >&2
  exit 1
fi

mkdir -p .runtime
sed '/server: https:\/\/127\.0\.0\.1:/ {
  s#https://127\.0\.0\.1:#https://host.docker.internal:#
  a\
    tls-server-name: localhost
}' "$HOST_KUBECONFIG" > "$RUNTIME_KUBECONFIG"
echo "Prepared container kubeconfig: $RUNTIME_KUBECONFIG"

docker compose "${COMPOSE_ARGS[@]}" up --build -d

echo "Waiting for the backend health endpoint..."
for attempt in {1..30}; do
  if curl --fail --silent http://localhost:8000/health >/dev/null; then
    echo "Environment is ready."
    echo "Frontend: http://localhost:3000"
    echo "Backend API docs: http://localhost:8000/docs"
    echo "Qdrant dashboard: http://localhost:6333/dashboard"
    if [[ "${1:-}" == "--monitoring" ]]; then
      echo "Prometheus: http://localhost:9090"
      echo "Grafana: http://localhost:3001"
    fi
    exit 0
  fi

  sleep 2
done

echo "Backend did not become healthy. Inspect logs with: docker compose logs backend" >&2
exit 1
