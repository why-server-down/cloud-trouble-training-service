# Docker Compose Setup

## Start

The default stack runs the frontend, backend, PostgreSQL, and Qdrant:

```bash
bash setup-test-env.sh
```

On Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-test-env.ps1
```

The startup script copies the host kubeconfig into `.runtime/kubeconfig`, rewrites Docker
Desktop's loopback API address to `host.docker.internal`, and preserves TLS verification with
`tls-server-name: localhost`. This lets `kubectl` commands run from inside the backend container.

After the startup script has prepared `.runtime/kubeconfig`, direct Docker Compose usage is also
available:

```bash
docker compose up --build -d
```

## URLs

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Qdrant dashboard: http://localhost:6333/dashboard

## Optional Monitoring

Prometheus and Grafana run only when the `monitoring` profile is enabled:

```bash
bash setup-test-env.sh --monitoring
```

```powershell
powershell -ExecutionPolicy Bypass -File .\setup-test-env.ps1 -Monitoring
```

- Prometheus: http://localhost:9090
- Grafana: http://localhost:3001

## Optional OpenAI Tutor

The default `AI_BACKEND=mock` mode does not require an API key. To enable the OpenAI-backed
tutor, copy `.env.example` to `.env` and set:

```env
AI_BACKEND=openai
OPENAI_API_KEY=your-key
```

## Stop

```bash
docker compose down
```

Use `docker compose down -v` only when you intentionally want to remove PostgreSQL and Qdrant
data volumes.

## Kubernetes Access

The backend image includes `kubectl`. The startup scripts prepare a container-readable kubeconfig
from `$HOME/.kube/config`. The default Compose stack still keeps mission injection and validation
in mock mode.
