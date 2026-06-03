param(
    [switch]$Monitoring
)

$ErrorActionPreference = "Stop"

Write-Host "Starting K8s Survival Camp with Docker Compose..."

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Docker is not running. Start Docker Desktop and retry."
}

$hostKubeconfig = Join-Path $HOME ".kube\config"
$runtimeDirectory = Join-Path $PSScriptRoot ".runtime"
$runtimeKubeconfig = Join-Path $runtimeDirectory "kubeconfig"

if (-not (Test-Path $hostKubeconfig)) {
    Write-Error "Kubeconfig not found at $hostKubeconfig. Enable Docker Desktop Kubernetes first."
}

New-Item -ItemType Directory -Force -Path $runtimeDirectory *> $null
$kubeconfigContent = Get-Content -Raw $hostKubeconfig
$kubeconfigContent = $kubeconfigContent -replace "server: https://127\.0\.0\.1:", "server: https://host.docker.internal:"
$kubeconfigContent = $kubeconfigContent -replace "(?m)^(\s*server: https://host\.docker\.internal:[^\r\n]+)", "`$1`r`n    tls-server-name: localhost"
Set-Content -Path $runtimeKubeconfig -Value $kubeconfigContent -Encoding utf8
Write-Host "Prepared container kubeconfig: $runtimeKubeconfig"

$composeArgs = @()
if ($Monitoring) {
    $composeArgs += "--profile"
    $composeArgs += "monitoring"
}

docker compose @composeArgs up --build -d
if ($LASTEXITCODE -ne 0) {
    throw "Docker Compose startup failed."
}

Write-Host "Waiting for the backend health endpoint..."
for ($attempt = 1; $attempt -le 30; $attempt++) {
    try {
        $response = Invoke-WebRequest -Uri "http://localhost:8000/health" -UseBasicParsing -TimeoutSec 2
        if ($response.StatusCode -eq 200) {
            Write-Host "Environment is ready."
            Write-Host "Frontend: http://localhost:3000"
            Write-Host "Backend API docs: http://localhost:8000/docs"
            Write-Host "Qdrant dashboard: http://localhost:6333/dashboard"
            if ($Monitoring) {
                Write-Host "Prometheus: http://localhost:9090"
                Write-Host "Grafana: http://localhost:3001"
            }
            exit 0
        }
    } catch {
        Start-Sleep -Seconds 2
    }
}

Write-Error "Backend did not become healthy. Inspect logs with: docker compose logs backend"
