# Cloud-Native Resilience Patterns

> **Source**: CNCF Best Practices  
> **Category**: SRE & Resilience  
> **Last Updated**: 2024

## Overview

This document covers cloud-native resilience patterns based on CNCF recommendations for building reliable microservices in Kubernetes.

## Core Resilience Principles

### 1. Design for Failure

**Assume everything will fail**:
- Services will crash
- Networks will partition
- Dependencies will be unavailable
- Disks will fill up

**Key Practices**:
- Implement retries with exponential backoff
- Use circuit breakers
- Set appropriate timeouts
- Design for graceful degradation

### 2. Health Checks

#### Liveness Probe
Detects if application is alive. Restart container if fails.

```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 15
  periodSeconds: 10
  timeoutSeconds: 5
  failureThreshold: 3
```

#### Readiness Probe
Detects if application is ready for traffic. Remove from service if fails.

```yaml
readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 3
```

**Best Practices**:
- Liveness checks basic functionality (process alive, critical threads running)
- Readiness checks dependencies (database connected, caches warmed)
- Don't use same endpoint for both
- Keep checks lightweight (< 1 second)
- Set appropriate initialDelaySeconds for slow-starting apps

### 3. Resource Limits and Requests

```yaml
resources:
  requests:
    memory: "256Mi"
    cpu: "500m"
  limits:
    memory: "512Mi"
    cpu: "1000m"
```

**Guidelines**:
- **Requests**: Guaranteed resources for scheduling
- **Limits**: Maximum allowed resources
- Set memory limits to prevent OOMKills
- CPU limits can cause throttling (consider omitting)
- Use VPA (Vertical Pod Autoscaler) for right-sizing

### 4. Pod Disruption Budgets

Ensure minimum availability during voluntary disruptions (node maintenance, cluster upgrades).

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: myapp-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: myapp
```

**Options**:
- `minAvailable`: Minimum Pods that must remain available
- `maxUnavailable`: Maximum Pods that can be unavailable

## Deployment Patterns

### 1. Rolling Updates

Default Kubernetes deployment strategy.

```yaml
spec:
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1        # Max new Pods created
      maxUnavailable: 0  # Max old Pods unavailable
```

**Benefits**:
- Zero downtime
- Gradual rollout
- Easy rollback

### 2. Blue-Green Deployment

Run two identical environments, switch traffic atomically.

```yaml
# Blue deployment
apiVersion: v1
kind: Service
metadata:
  name: myapp
spec:
  selector:
    app: myapp
    version: blue  # Switch to 'green' to cutover
```

**Benefits**:
- Instant rollback
- Full testing before cutover
- No mixed versions

**Trade-offs**:
- Requires 2x resources temporarily
- All-or-nothing cutover

### 3. Canary Deployment

Gradually shift traffic to new version.

```yaml
# Using Flagger
apiVersion: flagger.app/v1beta1
kind: Canary
metadata:
  name: myapp
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  service:
    port: 80
  analysis:
    interval: 1m
    threshold: 5
    maxWeight: 50
    stepWeight: 10
    metrics:
    - name: request-success-rate
      thresholdRange:
        min: 99
```

**Progressive Traffic Shift**:
```
10% → Monitor → 20% → Monitor → 50% → Monitor → 100%
```

**Benefits**:
- Early detection of issues
- Minimal blast radius
- Data-driven rollout

### 4. Feature Flags

Decouple deployment from release.

```yaml
env:
- name: FEATURE_NEW_ALGORITHM
  value: "false"
```

**Code Example**:
```javascript
if (process.env.FEATURE_NEW_ALGORITHM === 'true') {
  return newAlgorithm();
} else {
  return oldAlgorithm();
}
```

**Benefits**:
- Deploy anytime, enable when ready
- Gradual rollout
- Instant rollback (toggle flag)
- A/B testing

## Retry and Timeout Patterns

### 1. Exponential Backoff

```javascript
async function retryWithBackoff(fn, maxRetries = 3) {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (i === maxRetries - 1) throw error;
      const delay = Math.min(1000 * Math.pow(2, i), 30000);
      await sleep(delay + Math.random() * 1000); // Add jitter
    }
  }
}
```

**Key Points**:
- Increase delay exponentially: 1s, 2s, 4s, 8s...
- Add jitter to prevent thundering herd
- Cap maximum delay
- Only retry transient errors

### 2. Circuit Breaker

Prevent cascading failures by failing fast when service is down.

```
States: CLOSED → OPEN → HALF_OPEN → CLOSED

CLOSED: Normal operation
  ↓ (failure threshold exceeded)
OPEN: Fail immediately
  ↓ (after timeout)
HALF_OPEN: Test with limited requests
  ↓ (if successful)
CLOSED: Resume normal operation
```

**Implementation (Node.js)**:
```javascript
class CircuitBreaker {
  constructor(threshold = 5, timeout = 60000) {
    this.failureCount = 0;
    this.threshold = threshold;
    this.timeout = timeout;
    this.state = 'CLOSED';
    this.nextAttempt = Date.now();
  }

  async call(fn) {
    if (this.state === 'OPEN') {
      if (Date.now() < this.nextAttempt) {
        throw new Error('Circuit breaker is OPEN');
      }
      this.state = 'HALF_OPEN';
    }

    try {
      const result = await fn();
      this.onSuccess();
      return result;
    } catch (error) {
      this.onFailure();
      throw error;
    }
  }

  onSuccess() {
    this.failureCount = 0;
    this.state = 'CLOSED';
  }

  onFailure() {
    this.failureCount++;
    if (this.failureCount >= this.threshold) {
      this.state = 'OPEN';
      this.nextAttempt = Date.now() + this.timeout;
    }
  }
}
```

### 3. Timeouts

Always set timeouts for external calls.

```javascript
const controller = new AbortController();
const timeoutId = setTimeout(() => controller.abort(), 5000);

try {
  const response = await fetch(url, {
    signal: controller.signal
  });
  return await response.json();
} catch (error) {
  if (error.name === 'AbortError') {
    console.error('Request timed out');
  }
  throw error;
} finally {
  clearTimeout(timeoutId);
}
```

**Timeout Guidelines**:
- Set realistic timeouts based on SLAs
- Use different timeouts for different operations
- Consider downstream timeouts
- Log timeout occurrences

## Graceful Shutdown

Handle SIGTERM to shutdown cleanly.

```javascript
// Node.js example
const server = http.createServer(app);

process.on('SIGTERM', () => {
  console.log('SIGTERM received, starting graceful shutdown');
  
  server.close(() => {
    console.log('HTTP server closed');
    
    // Close database connections
    db.close(() => {
      console.log('Database connections closed');
      process.exit(0);
    });
  });

  // Force shutdown after 30 seconds
  setTimeout(() => {
    console.error('Forced shutdown after timeout');
    process.exit(1);
  }, 30000);
});
```

**Kubernetes Configuration**:
```yaml
spec:
  terminationGracePeriodSeconds: 30
  containers:
  - name: app
    lifecycle:
      preStop:
        exec:
          command: ["/bin/sh", "-c", "sleep 15"]
```

**Shutdown Sequence**:
1. Pod receives SIGTERM
2. preStop hook executes
3. Container process receives SIGTERM
4. Grace period countdown (default 30s)
5. SIGKILL if still running

## Rate Limiting

Protect services from overload.

```javascript
const rateLimit = require('express-rate-limit');

const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // Limit each IP to 100 requests per windowMs
  message: 'Too many requests, please try again later'
});

app.use('/api/', limiter);
```

**Kubernetes Ingress Rate Limiting**:
```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  annotations:
    nginx.ingress.kubernetes.io/limit-rps: "10"
    nginx.ingress.kubernetes.io/limit-connections: "5"
```

## Bulkheading

Isolate resources to prevent cascading failures.

### Resource Isolation

```yaml
# Separate deployments for critical vs. non-critical workloads
apiVersion: apps/v1
kind: Deployment
metadata:
  name: critical-api
spec:
  replicas: 3
  template:
    spec:
      priorityClassName: high-priority
      resources:
        requests:
          memory: "1Gi"
          cpu: "1000m"
        limits:
          memory: "2Gi"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: background-jobs
spec:
  template:
    spec:
      priorityClassName: low-priority
```

### Connection Pool Limits

```javascript
const pool = new Pool({
  host: 'postgres-service',
  database: 'mydb',
  max: 20, // Maximum connections
  idleTimeoutMillis: 30000,
  connectionTimeoutMillis: 2000,
});
```

## Observability for Resilience

### 1. Structured Logging

```javascript
logger.info({
  event: 'order_created',
  order_id: orderId,
  user_id: userId,
  amount: amount,
  trace_id: traceId
});
```

### 2. Metrics

**RED Method**:
- **Rate**: Requests per second
- **Errors**: Number of failed requests
- **Duration**: Time taken to serve requests

**USE Method** (for resources):
- **Utilization**: % time resource is busy
- **Saturation**: Queue depth or wait time
- **Errors**: Error count

### 3. Distributed Tracing

Correlate requests across services.

```javascript
const tracer = require('dd-trace').init();

app.get('/api/users/:id', async (req, res) => {
  const span = tracer.scope().active();
  span.setTag('user.id', req.params.id);
  
  try {
    const user = await fetchUser(req.params.id);
    res.json(user);
  } catch (error) {
    span.setTag('error', true);
    span.log({ event: 'error', message: error.message });
    throw error;
  }
});
```

## Auto-scaling

### Horizontal Pod Autoscaler (HPA)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: myapp-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  minReplicas: 2
  maxReplicas: 10
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Resource
    resource:
      name: memory
      target:
        type: Utilization
        averageUtilization: 80
```

### Vertical Pod Autoscaler (VPA)

Automatically adjusts CPU and memory requests.

```yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: myapp-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: myapp
  updatePolicy:
    updateMode: "Auto"
```

## Chaos Engineering

Test resilience by injecting failures.

### Pod Failure

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: PodChaos
metadata:
  name: pod-kill
spec:
  action: pod-kill
  mode: one
  selector:
    namespaces:
      - default
    labelSelectors:
      app: myapp
  scheduler:
    cron: "@every 10m"
```

### Network Delay

```yaml
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: network-delay
spec:
  action: delay
  mode: one
  selector:
    namespaces:
      - default
    labelSelectors:
      app: myapp
  delay:
    latency: "100ms"
    correlation: "25"
    jitter: "50ms"
  duration: "5m"
```

## Summary

Build resilient systems with:

1. **Assume failures** will happen
2. **Health checks** for liveness and readiness
3. **Resource limits** to prevent resource exhaustion
4. **Retry logic** with exponential backoff
5. **Circuit breakers** to prevent cascading failures
6. **Graceful shutdown** to finish in-flight requests
7. **Rate limiting** to prevent overload
8. **Auto-scaling** to handle load
9. **Observability** to detect issues
10. **Chaos engineering** to test resilience

Resilience is not a feature, it's a mindset.
