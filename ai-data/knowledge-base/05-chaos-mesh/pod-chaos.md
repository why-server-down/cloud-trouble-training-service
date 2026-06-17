# Chaos Mesh Pod Chaos Experiments

> **Source**: Chaos Mesh Official Documentation  
> **Category**: Chaos Engineering  
> **Last Updated**: 2024

## Overview

Chaos Mesh PodChaos allows you to simulate Pod failures and test application resilience in Kubernetes environments.

## Pod Chaos Actions

### 1. pod-kill

Kills one or more Pods to test restart and recovery mechanisms.

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: pod-kill-example
  namespace: chaos-testing
spec:
  action: pod-kill
  mode: one  # or 'all', 'fixed', 'fixed-percent', 'random-max-percent'
  selector:
    namespaces:
      - default
    labelSelectors:
      app: myapp
  gracePeriod: 0  # Force kill (SIGKILL)
  duration: "30s"
  scheduler:
    cron: "@every 2m"
```

**Use Cases**:
- Test deployment restart policies
- Verify stateless application recovery
- Test service failover
- Validate health checks

**What to Monitor**:
- Pod restart count
- Service availability
- Error rates
- Recovery time

### 2. pod-failure

Makes Pods unavailable by making them unschedulable or not ready.

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: pod-failure-example
spec:
  action: pod-failure
  mode: fixed
  value: "2"  # Affect 2 Pods
  duration: "60s"
  selector:
    namespaces:
      - default
    labelSelectors:
      app: myapp
      tier: frontend
```

**Difference from pod-kill**:
- Pod-kill: Pod is killed and recreated
- Pod-failure: Pod exists but marked as failed/not ready

**Use Cases**:
- Test readiness probe behavior
- Verify service endpoint removal
- Test load balancer response

### 3. container-kill

Kills specific container in a Pod.

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: container-kill-example
spec:
  action: container-kill
  mode: one
  containerNames:
    - nginx
    - sidecar
  selector:
    namespaces:
      - default
    labelSelectors:
      app: myapp
  duration: "10s"
```

**Use Cases**:
- Test multi-container Pod behavior
- Verify sidecar restart policies
- Test container dependencies

## Selection Modes

### mode: one
Randomly select one Pod.

```yaml
spec:
  mode: one
```

### mode: all
Select all Pods matching selector.

```yaml
spec:
  mode: all
```

### mode: fixed
Select fixed number of Pods.

```yaml
spec:
  mode: fixed
  value: "3"
```

### mode: fixed-percent
Select percentage of Pods.

```yaml
spec:
  mode: fixed-percent
  value: "50"  # 50% of Pods
```

### mode: random-max-percent
Randomly select up to percentage.

```yaml
spec:
  mode: random-max-percent
  value: "75"  # Up to 75% of Pods
```

## Advanced Selector

```yaml
spec:
  selector:
    namespaces:
      - production
      - staging
    labelSelectors:
      app: myapp
      version: v2
    # Exclude specific Pods
    expressionSelectors:
      - key: critical
        operator: NotIn
        values:
          - "true"
    # Select by field
    fieldSelectors:
      status.phase: Running
    # Select by node
    nodeSelectors:
      kubernetes.io/hostname: node-1
    # Pod name patterns
    pods:
      default:  # namespace
        - myapp-7d4f8b9c-abc12
```

## Scheduling

### One-time Execution

```yaml
spec:
  duration: "60s"  # Run for 60 seconds then stop
```

### Recurring Execution

```yaml
spec:
  duration: "30s"
  scheduler:
    cron: "@every 5m"  # Every 5 minutes, run for 30 seconds
```

### Cron Format

```yaml
# Standard cron format
cron: "0 9 * * *"  # Every day at 9:00 AM

# Predefined schedules
cron: "@hourly"    # Every hour
cron: "@daily"     # Every day at midnight
cron: "@weekly"    # Every week on Sunday
cron: "@monthly"   # Every month on 1st
cron: "@yearly"    # Every year on Jan 1

# Custom intervals
cron: "@every 30s"
cron: "@every 10m"
cron: "@every 2h"
```

## Real-World Scenarios

### Scenario 1: Test Deployment Resilience

**Objective**: Verify that killing Pods doesn't impact service availability.

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: deployment-resilience-test
spec:
  action: pod-kill
  mode: one
  selector:
    namespaces:
      - production
    labelSelectors:
      app: api-gateway
  duration: "10s"
  scheduler:
    cron: "@every 2m"
```

**Expected Behavior**:
- Pod is killed
- New Pod is created immediately
- Service remains available (other replicas handle traffic)
- No error rate increase

**Validation**:
```bash
# Monitor Pod restarts
kubectl get pods -w -l app=api-gateway

# Check error rates
kubectl logs -l app=api-gateway | grep -c ERROR

# Test service availability
while true; do curl -s http://api-gateway/health; sleep 1; done
```

### Scenario 2: Test Stateful Application Recovery

**Objective**: Verify stateful app properly recovers after Pod kill.

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: stateful-recovery-test
spec:
  action: pod-kill
  mode: one
  selector:
    labelSelectors:
      app: redis
      role: master
  duration: "5s"
```

**Validation**:
- Data persists after restart (PersistentVolume)
- Connections are re-established
- Replication resumes (if applicable)

### Scenario 3: Test Pod Disruption Budget

**Objective**: Verify PDB prevents excessive simultaneous failures.

```yaml
# First, create PDB
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: myapp-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: myapp
---
# Then, try to kill multiple Pods
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: pdb-test
spec:
  action: pod-kill
  mode: fixed
  value: "5"  # Try to kill 5 Pods
  selector:
    labelSelectors:
      app: myapp
  duration: "30s"
```

**Expected Behavior**:
- Only enough Pods are killed to respect PDB
- PDB prevents killing if minAvailable would be violated

### Scenario 4: Test Cascading Failures

**Objective**: Test if backend failure affects frontend.

```yaml
# Kill backend Pods
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: backend-failure
spec:
  action: pod-failure
  mode: all
  selector:
    labelSelectors:
      app: backend-service
  duration: "120s"
```

**Validation**:
- Frontend handles backend unavailability gracefully
- Circuit breakers activate
- Timeouts are respected
- User sees appropriate error messages

## Combining with Workflow

Run multiple chaos experiments in sequence.

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: Workflow
metadata:
  name: pod-chaos-workflow
spec:
  entry: the-entry
  templates:
    - name: the-entry
      templateType: Serial
      deadline: 5m
      children:
        - workflow-pod-kill
        - workflow-pod-failure
    
    - name: workflow-pod-kill
      templateType: PodChaos
      deadline: 2m
      podChaos:
        action: pod-kill
        mode: one
        selector:
          labelSelectors:
            app: myapp
    
    - name: workflow-pod-failure
      templateType: PodChaos
      deadline: 2m
      podChaos:
        action: pod-failure
        mode: fixed
        value: "2"
        selector:
          labelSelectors:
            app: myapp
```

## Monitoring Chaos Experiments

### Check Experiment Status

```bash
# List all chaos experiments
kubectl get podchaos

# Describe experiment
kubectl describe podchaos <name>

# Check experiment logs
kubectl logs -n chaos-mesh -l app.kubernetes.io/component=controller-manager
```

### Metrics to Track

1. **Availability Metrics**:
   - Service uptime
   - Request success rate
   - Error rate

2. **Performance Metrics**:
   - Latency (p50, p95, p99)
   - Throughput
   - Queue depth

3. **Recovery Metrics**:
   - Time to recovery
   - Pod restart time
   - Connection re-establishment time

### Prometheus Queries

```promql
# Pod restart rate
rate(kube_pod_container_status_restarts_total[5m])

# Service availability
sum(rate(http_requests_total{status=~"2.."}[5m])) / sum(rate(http_requests_total[5m]))

# Error rate during chaos
sum(rate(http_requests_total{status=~"5.."}[5m])) by (service)

# Recovery time
histogram_quantile(0.99, rate(http_request_duration_seconds_bucket[5m]))
```

## Best Practices

### 1. Start Small

```yaml
# Start with single Pod
spec:
  mode: one
  duration: "10s"
  
# Gradually increase scope
spec:
  mode: fixed-percent
  value: "25"
  duration: "60s"
```

### 2. Use Namespaces

Isolate chaos experiments to specific environments.

```yaml
spec:
  selector:
    namespaces:
      - staging
      - testing
    # Never in production initially
```

### 3. Set Duration Limits

Always specify duration to prevent indefinite chaos.

```yaml
spec:
  duration: "60s"  # Always set!
```

### 4. Monitor Actively

Watch experiments in real-time.

```bash
# Terminal 1: Watch Pods
kubectl get pods -w

# Terminal 2: Watch events
kubectl get events -w

# Terminal 3: Monitor metrics
watch -n 1 'curl -s http://prometheus/api/v1/query?query=up'
```

### 5. Have Rollback Plan

```bash
# Pause experiment
kubectl annotate podchaos <name> experiment.chaos-mesh.org/pause=true

# Delete experiment
kubectl delete podchaos <name>

# Emergency: Delete all chaos experiments
kubectl delete podchaos --all
```

## Troubleshooting

### Experiment Not Working

```bash
# Check Chaos Mesh installation
kubectl get pods -n chaos-mesh

# Check CRD installed
kubectl get crd | grep chaos-mesh

# Check experiment status
kubectl describe podchaos <name>

# Check controller logs
kubectl logs -n chaos-mesh -l app.kubernetes.io/component=controller-manager
```

### Pods Not Being Killed

**Common Issues**:
1. Selector doesn't match any Pods
2. PodDisruptionBudget preventing kills
3. Insufficient permissions

**Debug**:
```bash
# Test selector
kubectl get pods -l app=myapp

# Check PDB
kubectl get pdb

# Check RBAC
kubectl auth can-i delete pods --as=system:serviceaccount:chaos-mesh:chaos-controller-manager
```

## Safety Guidelines

1. **Never run in production** without thorough testing
2. **Always set duration** limits
3. **Use PodDisruptionBudgets** to prevent excessive failures
4. **Monitor actively** during experiments
5. **Have rollback procedures** ready
6. **Schedule during** low-traffic periods initially
7. **Start with** non-critical services
8. **Document** expected vs. actual behavior

## Summary

Chaos Mesh PodChaos enables:

- **pod-kill**: Terminate Pods to test restart
- **pod-failure**: Make Pods unavailable
- **container-kill**: Kill specific containers
- **Flexible selectors**: Target specific Pods
- **Scheduling**: Recurring or one-time experiments
- **Workflows**: Complex multi-step scenarios

Use chaos engineering to proactively find and fix resilience issues before they impact production.
