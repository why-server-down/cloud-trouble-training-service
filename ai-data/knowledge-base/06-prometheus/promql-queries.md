# PromQL Queries for Kubernetes Troubleshooting

> **Source**: Prometheus Official Documentation  
> **Category**: Monitoring & Observability  
> **Last Updated**: 2024

## Overview

This guide provides essential PromQL queries for diagnosing Kubernetes resource issues, performance problems, and application health.

## Resource Monitoring

### CPU Metrics

#### Pod CPU Usage

```promql
# Current CPU usage by Pod (cores)
sum(rate(container_cpu_usage_seconds_total{pod!=""}[5m])) by (pod, namespace)

# CPU usage percentage (vs. requests)
sum(rate(container_cpu_usage_seconds_total{pod!=""}[5m])) by (pod) 
/ 
sum(kube_pod_container_resource_requests{resource="cpu"}) by (pod) * 100

# CPU usage percentage (vs. limits)
sum(rate(container_cpu_usage_seconds_total{pod!=""}[5m])) by (pod) 
/ 
sum(kube_pod_container_resource_limits{resource="cpu"}) by (pod) * 100

# Top 10 Pods by CPU usage
topk(10, sum(rate(container_cpu_usage_seconds_total{pod!=""}[5m])) by (pod, namespace))

# CPU throttling (indicates CPU limit hit)
rate(container_cpu_cfs_throttled_seconds_total{pod!=""}[5m])
```

#### Node CPU Usage

```promql
# Node CPU usage percentage
100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)

# Node CPU by mode
sum by (instance, mode) (rate(node_cpu_seconds_total[5m]))

# Nodes with high CPU (>80%)
(100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)) > 80
```

### Memory Metrics

#### Pod Memory Usage

```promql
# Current memory usage by Pod (bytes)
sum(container_memory_working_set_bytes{pod!=""}) by (pod, namespace)

# Memory usage in MB/GB
sum(container_memory_working_set_bytes{pod!=""}) by (pod) / 1024 / 1024

# Memory usage percentage (vs. requests)
sum(container_memory_working_set_bytes{pod!=""}) by (pod)
/
sum(kube_pod_container_resource_requests{resource="memory"}) by (pod) * 100

# Memory usage percentage (vs. limits)
sum(container_memory_working_set_bytes{pod!=""}) by (pod)
/
sum(kube_pod_container_resource_limits{resource="memory"}) by (pod) * 100

# Pods using >80% of memory limit
(sum(container_memory_working_set_bytes{pod!=""}) by (pod)
/
sum(kube_pod_container_resource_limits{resource="memory"}) by (pod)) > 0.8

# Top 10 Pods by memory usage
topk(10, sum(container_memory_working_set_bytes{pod!=""}) by (pod, namespace))
```

#### OOM Kills

```promql
# OOM killed containers
sum(kube_pod_container_status_terminated_reason{reason="OOMKilled"}) by (pod, namespace)

# OOMKill rate
rate(kube_pod_container_status_terminated_reason{reason="OOMKilled"}[5m])
```

#### Node Memory

```promql
# Node memory usage percentage
(1 - (node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes)) * 100

# Available memory in GB
node_memory_MemAvailable_bytes / 1024 / 1024 / 1024

# Nodes with low memory (<10% available)
((node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100) < 10
```

### Disk Metrics

```promql
# Disk usage percentage
(1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)) * 100

# Disk space available (GB)
node_filesystem_avail_bytes{mountpoint="/"} / 1024 / 1024 / 1024

# Nodes with high disk usage (>85%)
((1 - (node_filesystem_avail_bytes / node_filesystem_size_bytes)) * 100) > 85

# Disk I/O rate
rate(node_disk_io_time_seconds_total[5m])

# Disk read/write bytes
rate(node_disk_read_bytes_total[5m])
rate(node_disk_written_bytes_total[5m])
```

### Network Metrics

```promql
# Network receive bytes per second
rate(container_network_receive_bytes_total{pod!=""}[5m])

# Network transmit bytes per second
rate(container_network_transmit_bytes_total{pod!=""}[5m])

# Network errors
rate(container_network_receive_errors_total{pod!=""}[5m])
rate(container_network_transmit_errors_total{pod!=""}[5m])

# Top Pods by network usage
topk(10, sum(rate(container_network_transmit_bytes_total{pod!=""}[5m])) by (pod))
```

## Pod Health Metrics

### Pod Status

```promql
# Pods not running
count(kube_pod_status_phase{phase!="Running"}) by (namespace, phase)

# Pods in CrashLoopBackOff
sum(kube_pod_container_status_waiting_reason{reason="CrashLoopBackOff"}) by (pod, namespace)

# Pods in ImagePullBackOff
sum(kube_pod_container_status_waiting_reason{reason="ImagePullBackOff"}) by (pod, namespace)

# Pods in Pending state
sum(kube_pod_status_phase{phase="Pending"}) by (namespace)

# Pod restarts in last hour
increase(kube_pod_container_status_restarts_total[1h]) > 0
```

### Container Restarts

```promql
# Pod restart count
kube_pod_container_status_restarts_total

# Pods with recent restarts (last 30 minutes)
increase(kube_pod_container_status_restarts_total[30m]) > 0

# Restart rate
rate(kube_pod_container_status_restarts_total[5m])

# Pods with >5 restarts in last hour
increase(kube_pod_container_status_restarts_total[1h]) > 5
```

### Readiness and Liveness

```promql
# Pods not ready
sum(kube_pod_status_ready{condition="false"}) by (pod, namespace)

# Ready Pods percentage per deployment
sum(kube_pod_status_ready{condition="true"}) by (deployment)
/
sum(kube_deployment_spec_replicas) by (deployment) * 100

# Containers not ready
kube_pod_container_status_ready{ready="false"}
```

## Deployment Metrics

### Replica Status

```promql
# Desired vs. available replicas
kube_deployment_status_replicas_available / kube_deployment_spec_replicas

# Deployments with unavailable replicas
kube_deployment_status_replicas_unavailable > 0

# Deployment rollout status
kube_deployment_status_condition{condition="Progressing", status="true"}
```

### Resource Requests vs. Limits

```promql
# Total CPU requests by namespace
sum(kube_pod_container_resource_requests{resource="cpu"}) by (namespace)

# Total memory requests by namespace
sum(kube_pod_container_resource_requests{resource="memory"}) by (namespace) / 1024 / 1024 / 1024

# Pods without resource limits
count(kube_pod_container_resource_limits{resource="cpu"} == 0) by (pod)

# Cluster CPU allocation
sum(kube_pod_container_resource_requests{resource="cpu"}) 
/
sum(kube_node_status_allocatable{resource="cpu"}) * 100
```

## Node Health Metrics

### Node Status

```promql
# Nodes not ready
sum(kube_node_status_condition{condition="Ready", status="false"})

# Node conditions
kube_node_status_condition{condition=~"MemoryPressure|DiskPressure|PIDPressure|NetworkUnavailable"}

# Node count by status
count(kube_node_status_condition{condition="Ready", status="true"})
```

### Node Capacity

```promql
# Total cluster CPU capacity
sum(kube_node_status_capacity{resource="cpu"})

# Total cluster memory capacity (GB)
sum(kube_node_status_capacity{resource="memory"}) / 1024 / 1024 / 1024

# Node allocatable resources
sum(kube_node_status_allocatable{resource="cpu"}) by (node)
sum(kube_node_status_allocatable{resource="memory"}) by (node)
```

## Application Performance

### Request Rate (RED Method)

```promql
# Request rate (requests per second)
sum(rate(http_requests_total[5m])) by (service)

# Error rate (%)
sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
/
sum(rate(http_requests_total[5m])) by (service) * 100

# Success rate (%)
sum(rate(http_requests_total{status=~"2.."}[5m])) by (service)
/
sum(rate(http_requests_total[5m])) by (service) * 100

# 4xx error rate
sum(rate(http_requests_total{status=~"4.."}[5m])) by (service, status)
```

### Duration (Latency)

```promql
# Average latency
rate(http_request_duration_seconds_sum[5m])
/
rate(http_request_duration_seconds_count[5m])

# P50 latency
histogram_quantile(0.50, rate(http_request_duration_seconds_bucket[5m]))

# P95 latency
histogram_quantile(0.95, rate(http_request_duration_seconds_bucket[5m]))

# P99 latency
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))

# Slow requests (>1s)
sum(rate(http_request_duration_seconds_bucket{le="1"}[5m]))
```

## Alert-Worthy Queries

### High CPU

```promql
# Alert: Pod CPU usage >80%
(sum(rate(container_cpu_usage_seconds_total{pod!=""}[5m])) by (pod, namespace)
/
sum(kube_pod_container_resource_limits{resource="cpu"}) by (pod, namespace)) > 0.8
```

### High Memory

```promql
# Alert: Pod memory usage >85%
(sum(container_memory_working_set_bytes{pod!=""}) by (pod, namespace)
/
sum(kube_pod_container_resource_limits{resource="memory"}) by (pod, namespace)) > 0.85
```

### Pod Crashes

```promql
# Alert: Pod restarted in last 5 minutes
increase(kube_pod_container_status_restarts_total[5m]) > 0
```

### High Error Rate

```promql
# Alert: Error rate >5%
(sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)
/
sum(rate(http_requests_total[5m])) by (service)) > 0.05
```

### Slow Response

```promql
# Alert: P99 latency >1 second
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m])) > 1
```

## Troubleshooting Queries

### Find Resource-Constrained Pods

```promql
# Pods hitting CPU limits
(rate(container_cpu_cfs_throttled_seconds_total[5m]) > 0)

# Pods hitting memory limits
(sum(container_memory_working_set_bytes) by (pod)
/
sum(kube_pod_container_resource_limits{resource="memory"}) by (pod)) > 0.9
```

### Find Pods on Problematic Nodes

```promql
# Pods on nodes with high CPU
sum(container_cpu_usage_seconds_total{pod!=""}) by (pod, node)
and on(node)
(100 - (avg by (instance) (rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)) > 80
```

### Correlate Deployments with Issues

```promql
# Recent deployment changes (last hour)
changes(kube_deployment_status_observed_generation[1h]) > 0

# Deployment rollout in progress
kube_deployment_status_replicas_updated < kube_deployment_spec_replicas
```

## Query Best Practices

### 1. Use Appropriate Time Ranges

```promql
# Short-term (real-time monitoring)
[1m], [5m]

# Medium-term (trending)
[15m], [30m]

# Long-term (capacity planning)
[1h], [6h], [1d]
```

### 2. Aggregate Intelligently

```promql
# Sum across Pods
sum(metric) by (namespace)

# Average across nodes
avg(metric) by (cluster)

# Maximum value
max(metric)

# Top K
topk(10, metric)
```

### 3. Use Rate for Counters

```promql
# WRONG (counter always increases)
http_requests_total

# RIGHT (requests per second)
rate(http_requests_total[5m])
```

### 4. Handle Missing Data

```promql
# Use 'or' to provide default
metric or 0

# Use 'unless' to exclude
metric unless other_metric > 0
```

## Summary

Key PromQL patterns for Kubernetes:

1. **CPU**: `rate(container_cpu_usage_seconds_total[5m])`
2. **Memory**: `container_memory_working_set_bytes`
3. **Disk**: `node_filesystem_avail_bytes`
4. **Network**: `rate(container_network_*_bytes_total[5m])`
5. **Pod Health**: `kube_pod_status_phase`
6. **Restarts**: `kube_pod_container_status_restarts_total`

Always combine metrics with logs and events for complete troubleshooting picture.
