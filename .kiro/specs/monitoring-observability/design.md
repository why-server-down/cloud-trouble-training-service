# Monitoring & Observability System - Design Document

## 1. System Architecture

### 1.1 High-Level Architecture
```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│ Kubernetes  │─────▶│  Prometheus  │─────▶│   Grafana   │
│  Cluster    │      │  (Metrics)   │      │ (Dashboard) │
└─────────────┘      └──────────────┘      └─────────────┘
       │                     │
       │                     │
       ▼                     ▼
┌─────────────┐      ┌──────────────┐
│    Loki     │      │ AlertManager │
│   (Logs)    │      │  (Alerts)    │
└─────────────┘      └──────────────┘
```

### 1.2 Component Breakdown

**Monitoring Stack:**
- Prometheus: 메트릭 수집 및 저장
- Grafana: 시각화 대시보드
- Loki: 로그 집계
- AlertManager: 알림 관리
- Node Exporter: 노드 메트릭
- kube-state-metrics: K8s 리소스 메트릭

## 2. Prometheus Configuration

### 2.1 Scrape Configs

```yaml
# prometheus.yml
global:
  scrape_interval: 5s
  evaluation_interval: 5s
  external_labels:
    cluster: 'k8s-survival-camp'

scrape_configs:
  # Kubernetes API Server
  - job_name: 'kubernetes-apiservers'
    kubernetes_sd_configs:
      - role: endpoints
    scheme: https
    tls_config:
      ca_file: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    bearer_token_file: /var/run/secrets/kubernetes.io/serviceaccount/token
    relabel_configs:
      - source_labels: [__meta_kubernetes_namespace, __meta_kubernetes_service_name, __meta_kubernetes_endpoint_port_name]
        action: keep
        regex: default;kubernetes;https

  # Kubernetes Nodes
  - job_name: 'kubernetes-nodes'
    kubernetes_sd_configs:
      - role: node
    relabel_configs:
      - action: labelmap
        regex: __meta_kubernetes_node_label_(.+)

  # Kubernetes Pods
  - job_name: 'kubernetes-pods'
    kubernetes_sd_configs:
      - role: pod
    relabel_configs:
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_scrape]
        action: keep
        regex: true
      - source_labels: [__meta_kubernetes_pod_annotation_prometheus_io_path]
        action: replace
        target_label: __metrics_path__
        regex: (.+)
      - source_labels: [__address__, __meta_kubernetes_pod_annotation_prometheus_io_port]
        action: replace
        regex: ([^:]+)(?::\d+)?;(\d+)
        replacement: $1:$2
        target_label: __address__
      - action: labelmap
        regex: __meta_kubernetes_pod_label_(.+)
      - source_labels: [__meta_kubernetes_namespace]
        action: replace
        target_label: kubernetes_namespace
      - source_labels: [__meta_kubernetes_pod_name]
        action: replace
        target_label: kubernetes_pod_name

  # Mission Applications
  - job_name: 'mission-apps'
    kubernetes_sd_configs:
      - role: pod
        namespaces:
          names:
            - user-*
    relabel_configs:
      - source_labels: [__meta_kubernetes_namespace]
        action: replace
        target_label: namespace
      - source_labels: [__meta_kubernetes_pod_name]
        action: replace
        target_label: pod
```

### 2.2 Recording Rules

```yaml
# recording_rules.yml
groups:
  - name: mission_validation
    interval: 5s
    rules:
      # Pod health
      - record: mission:pod_healthy
        expr: |
          kube_pod_status_phase{phase="Running"} == 1
      
      # HTTP success rate
      - record: mission:http_success_rate
        expr: |
          sum(rate(http_requests_total{code=~"2.."}[1m])) by (namespace, pod)
          /
          sum(rate(http_requests_total[1m])) by (namespace, pod)
      
      # Response time
      - record: mission:http_response_time_p95
        expr: |
          histogram_quantile(0.95,
            sum(rate(http_request_duration_seconds_bucket[1m])) by (namespace, pod, le)
          )
      
      # Memory usage ratio
      - record: mission:memory_usage_ratio
        expr: |
          container_memory_usage_bytes
          /
          container_spec_memory_limit_bytes
      
      # CPU usage
      - record: mission:cpu_usage
        expr: |
          rate(container_cpu_usage_seconds_total[1m])

  - name: system_metrics
    interval: 15s
    rules:
      # Total active users
      - record: system:active_users_total
        expr: |
          count(count by (user_id) (kube_namespace_labels{label_user_id!=""}))
      
      # Total missions in progress
      - record: system:missions_in_progress
        expr: |
          count(mission_attempt_status{status="in_progress"})
      
      # Cluster resource usage
      - record: system:cluster_cpu_usage
        expr: |
          sum(rate(container_cpu_usage_seconds_total[5m]))
      
      - record: system:cluster_memory_usage
        expr: |
          sum(container_memory_usage_bytes)
```

### 2.3 Alert Rules

```yaml
# alert_rules.yml
groups:
  - name: system_alerts
    rules:
      # Pod stuck in pending
      - alert: PodStuckPending
        expr: |
          kube_pod_status_phase{phase="Pending"} == 1
          and
          time() - kube_pod_created > 300
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Pod {{ $labels.pod }} stuck in Pending state"
          description: "Pod has been pending for more than 5 minutes in namespace {{ $labels.namespace }}"
      
      # High CPU usage
      - alert: HighCPUUsage
        expr: |
          system:cluster_cpu_usage > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Cluster CPU usage above 80%"
          description: "Current CPU usage: {{ $value | humanizePercentage }}"
      
      # High memory usage
      - alert: HighMemoryUsage
        expr: |
          system:cluster_memory_usage / system:cluster_memory_total > 0.8
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "Cluster memory usage above 80%"
      
      # High error rate
      - alert: HighErrorRate
        expr: |
          (
            sum(rate(http_requests_total{code=~"5.."}[5m]))
            /
            sum(rate(http_requests_total[5m]))
          ) > 0.1
        for: 2m
        labels:
          severity: critical
        annotations:
          summary: "Error rate above 10%"
          description: "Current error rate: {{ $value | humanizePercentage }}"
```

## 3. Mission Validation Queries

### 3.1 Validation Query Templates

```python
class MissionValidationQueries:
    """
    Prometheus queries for mission validation
    """
    
    QUERIES = {
        'level-1-pod-failure': '''
            mission:pod_healthy{namespace="{namespace}", pod=~"web-app.*"} == 1
        ''',
        
        'level-2-memory-stress': '''
            mission:memory_usage_ratio{namespace="{namespace}", pod=~"shopping-app.*"} < 0.9
            and
            mission:pod_healthy{namespace="{namespace}", pod=~"shopping-app.*"} == 1
        ''',
        
        'level-3-service-config': '''
            mission:http_success_rate{namespace="{namespace}", service="backend"} > 0.95
            and
            rate(http_requests_total{namespace="{namespace}", service="backend"}[1m]) > 0
        ''',
        
        'level-4-network-latency': '''
            mission:http_response_time_p95{namespace="{namespace}"} < 1
            and
            probe_success{namespace="{namespace}", probe_type="liveness"} == 1
        '''
    }
    
    @classmethod
    def get_query(cls, mission_id: str, namespace: str) -> str:
        """
        Gets validation query for mission
        """
        query_template = cls.QUERIES.get(mission_id)
        if not query_template:
            raise ValueError(f"No validation query for mission {mission_id}")
        
        return query_template.format(namespace=namespace)
```

### 3.2 Validation Service

```python
class PrometheusClient:
    def __init__(self):
        self.base_url = os.getenv('PROMETHEUS_URL', 'http://prometheus:9090')
    
    async def query(self, query: str) -> dict:
        """
        Executes Prometheus query
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/query",
                params={'query': query}
            ) as response:
                return await response.json()
    
    async def query_range(
        self,
        query: str,
        start: datetime,
        end: datetime,
        step: str = '15s'
    ) -> dict:
        """
        Executes range query
        """
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/api/v1/query_range",
                params={
                    'query': query,
                    'start': start.timestamp(),
                    'end': end.timestamp(),
                    'step': step
                }
            ) as response:
                return await response.json()

class MissionValidationService:
    def __init__(self):
        self.prometheus = PrometheusClient()
    
    async def validate_mission(
        self,
        mission_id: str,
        namespace: str
    ) -> bool:
        """
        Validates mission completion using Prometheus
        """
        # Get validation query
        query = MissionValidationQueries.get_query(mission_id, namespace)
        
        # Execute query
        result = await self.prometheus.query(query)
        
        # Evaluate result
        return self._evaluate_result(result)
    
    def _evaluate_result(self, result: dict) -> bool:
        """
        Evaluates Prometheus query result
        """
        if result['status'] != 'success':
            return False
        
        data = result.get('data', {})
        results = data.get('result', [])
        
        if not results:
            return False
        
        # Check if any result has value > 0
        for item in results:
            value = float(item['value'][1])
            if value > 0:
                return True
        
        return False
```

## 4. Grafana Dashboards

### 4.1 System Overview Dashboard

```json
{
  "dashboard": {
    "title": "K8s Survival Camp - System Overview",
    "panels": [
      {
        "title": "Active Users",
        "targets": [{
          "expr": "system:active_users_total"
        }],
        "type": "stat"
      },
      {
        "title": "Missions In Progress",
        "targets": [{
          "expr": "system:missions_in_progress"
        }],
        "type": "stat"
      },
      {
        "title": "Cluster CPU Usage",
        "targets": [{
          "expr": "system:cluster_cpu_usage"
        }],
        "type": "graph"
      },
      {
        "title": "Cluster Memory Usage",
        "targets": [{
          "expr": "system:cluster_memory_usage"
        }],
        "type": "graph"
      },
      {
        "title": "Mission Success Rate by Level",
        "targets": [{
          "expr": "sum(mission_completion_total{status='completed'}) by (mission_level) / sum(mission_attempt_total) by (mission_level)"
        }],
        "type": "bargauge"
      },
      {
        "title": "Average Completion Time",
        "targets": [{
          "expr": "avg(mission_completion_time_seconds) by (mission_id)"
        }],
        "type": "table"
      }
    ]
  }
}
```

### 4.2 Mission Monitoring Dashboard

```json
{
  "dashboard": {
    "title": "Mission Monitoring",
    "templating": {
      "list": [
        {
          "name": "namespace",
          "type": "query",
          "query": "label_values(kube_namespace_labels, namespace)"
        }
      ]
    },
    "panels": [
      {
        "title": "Pod Status",
        "targets": [{
          "expr": "kube_pod_status_phase{namespace='$namespace'}"
        }],
        "type": "stat"
      },
      {
        "title": "HTTP Request Rate",
        "targets": [{
          "expr": "rate(http_requests_total{namespace='$namespace'}[1m])"
        }],
        "type": "graph"
      },
      {
        "title": "Response Time (p95)",
        "targets": [{
          "expr": "mission:http_response_time_p95{namespace='$namespace'}"
        }],
        "type": "graph"
      },
      {
        "title": "Memory Usage",
        "targets": [{
          "expr": "container_memory_usage_bytes{namespace='$namespace'}"
        }],
        "type": "graph"
      }
    ]
  }
}
```

## 5. Loki Configuration

### 5.1 Loki Config

```yaml
# loki-config.yml
auth_enabled: false

server:
  http_listen_port: 3100

ingester:
  lifecycler:
    ring:
      kvstore:
        store: inmemory
      replication_factor: 1
  chunk_idle_period: 5m
  chunk_retain_period: 30s

schema_config:
  configs:
    - from: 2024-01-01
      store: boltdb
      object_store: filesystem
      schema: v11
      index:
        prefix: index_
        period: 24h

storage_config:
  boltdb:
    directory: /loki/index
  filesystem:
    directory: /loki/chunks

limits_config:
  enforce_metric_name: false
  reject_old_samples: true
  reject_old_samples_max_age: 168h  # 7 days
  retention_period: 72h  # 3 days
```

### 5.2 Log Queries

```python
class LokiClient:
    def __init__(self):
        self.base_url = os.getenv('LOKI_URL', 'http://loki:3100')
    
    async def query_logs(
        self,
        namespace: str,
        pod: str = None,
        level: str = None,
        limit: int = 100
    ) -> List[str]:
        """
        Queries logs from Loki
        """
        # Build LogQL query
        query = f'{{namespace="{namespace}"}}'
        
        if pod:
            query = f'{{namespace="{namespace}", pod="{pod}"}}'
        
        if level:
            query += f' |= "{level}"'
        
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"{self.base_url}/loki/api/v1/query_range",
                params={
                    'query': query,
                    'limit': limit
                }
            ) as response:
                result = await response.json()
                return self._parse_logs(result)
    
    def _parse_logs(self, result: dict) -> List[str]:
        """
        Parses Loki query result
        """
        logs = []
        for stream in result.get('data', {}).get('result', []):
            for value in stream.get('values', []):
                timestamp, log_line = value
                logs.append(log_line)
        return logs
```

## 6. AlertManager Configuration

```yaml
# alertmanager.yml
global:
  resolve_timeout: 5m
  slack_api_url: '${SLACK_WEBHOOK_URL}'

route:
  group_by: ['alertname', 'cluster']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 12h
  receiver: 'slack-notifications'
  routes:
    - match:
        severity: critical
      receiver: 'slack-critical'

receivers:
  - name: 'slack-notifications'
    slack_configs:
      - channel: '#k8s-survival-alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
  
  - name: 'slack-critical'
    slack_configs:
      - channel: '#k8s-survival-critical'
        title: '🚨 CRITICAL: {{ .GroupLabels.alertname }}'
        text: '{{ range .Alerts }}{{ .Annotations.description }}{{ end }}'
```

## 7. Deployment

```yaml
# infra/monitoring/prometheus-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: prometheus
        image: prom/prometheus:latest
        args:
          - '--config.file=/etc/prometheus/prometheus.yml'
          - '--storage.tsdb.retention.time=7d'
        volumeMounts:
        - name: config
          mountPath: /etc/prometheus
        - name: storage
          mountPath: /prometheus
      volumes:
      - name: config
        configMap:
          name: prometheus-config
      - name: storage
        persistentVolumeClaim:
          claimName: prometheus-storage
```

## 8. Testing Strategy

### Property-Based Tests
- Property: Metrics are collected every 5 seconds ± 1 second
- Property: Alert fires within 5 minutes of condition being met
- Property: Logs are retained for exactly 3 days
- Property: Validation queries return boolean results
