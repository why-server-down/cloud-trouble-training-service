# Kubernetes Log Patterns and Analysis

> **Source**: Komodor Best Practices  
> **Category**: Log Analysis  
> **Last Updated**: 2024

## Overview

This guide provides common log patterns seen in Kubernetes environments and how to interpret them for effective troubleshooting.

## Common Error Patterns

### Pattern 1: CrashLoopBackOff Logs

#### Application Startup Failure
```
Error: Cannot find module '/app/server.js'
    at Module._resolveFilename (node:internal/modules/cjs/loader:1039:15)
    at Module._load (node:internal/modules/cjs/loader:885:27)
```

**Interpretation**: Missing file or incorrect WORKDIR in Dockerfile

**Action**:
```bash
# Check Pod filesystem
kubectl exec <pod-name> -- ls -la /app/

# Verify Dockerfile COPY/ADD commands
# Fix and rebuild image
```

#### Port Already in Use
```
Error: listen EADDRINUSE: address already in use :::8080
```

**Interpretation**: Another process using the port or multiple containers trying to bind same port

**Action**: Check containerPort in Pod spec, ensure no duplicate ports

#### Database Connection Refused
```
MongoNetworkError: failed to connect to server [db:27017] on first connect
Error: connect ECONNREFUSED 10.0.0.5:5432
```

**Interpretation**: Database service not available or wrong connection string

**Action**:
```bash
# Test database connectivity
kubectl run db-test --rm -i --tty --image=postgres:15 -- psql -h <db-svc> -U <user>

# Check Service and Endpoints
kubectl get svc <db-service>
kubectl get endpoints <db-service>
```

### Pattern 2: OOMKilled Logs

#### Memory Exhaustion
```
<--- Last few GCs --->
[1:0x5615f4e00000]   145623 ms: Mark-sweep 2048.0 (2084.0) -> 2048.0 (2084.0) MB
[1:0x5615f4e00000]   FATAL ERROR: Reached heap limit Allocation failed
```

**Interpretation**: Node.js heap memory exhausted

**Action**: Increase memory limits or fix memory leak

#### Python Memory Error
```
MemoryError: Unable to allocate 256 MiB for an array
numpy.core._exceptions.MemoryError
```

**Interpretation**: Python process ran out of memory

**Action**: Optimize data processing or increase resources

### Pattern 3: ImagePull Errors

#### Private Registry Authentication
```
Failed to pull image "private-reg.io/myapp:v1": 
  rpc error: code = Unknown desc = failed to pull and unpack image:
  failed to resolve reference: pull access denied
```

**Interpretation**: Missing or invalid imagePullSecrets

**Action**:
```bash
# Create secret
kubectl create secret docker-registry regcred \
  --docker-server=private-reg.io \
  --docker-username=<user> \
  --docker-password=<pass>

# Add to deployment
kubectl patch deployment <name> -p \
  '{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"regcred"}]}}}}'
```

#### Tag Not Found
```
Error response from daemon: manifest for myapp:latets not found
```

**Interpretation**: Typo in image tag or tag doesn't exist

**Action**: Fix image tag in deployment

### Pattern 4: Readiness/Liveness Probe Failures

#### HTTP Probe Failure
```
Readiness probe failed: HTTP probe failed with statuscode: 500
Liveness probe failed: Get "http://10.244.0.5:8080/health": dial tcp 10.244.0.5:8080: connect: connection refused
```

**Interpretation**: Health endpoint not responding or returning errors

**Action**:
```bash
# Test endpoint directly
kubectl exec <pod-name> -- curl -v http://localhost:8080/health

# Check application logs
kubectl logs <pod-name>

# Adjust probe timing
# - Increase initialDelaySeconds
# - Increase periodSeconds
# - Increase failureThreshold
```

### Pattern 5: Volume Mount Errors

#### Volume Not Available
```
Unable to attach or mount volumes: 
  failed to attach volume "pvc-123": 
  Volume is already exclusively attached to one node
```

**Interpretation**: PersistentVolume with ReadWriteOnce already mounted elsewhere

**Action**: Delete old Pod or use ReadWriteMany volume

#### Permission Denied
```
Error: EACCES: permission denied, open '/data/config.json'
```

**Interpretation**: Container user lacks permissions on mounted volume

**Action**:
```yaml
# Add securityContext
securityContext:
  fsGroup: 1000
  runAsUser: 1000
```

## Log Analysis Techniques

### 1. Pattern Matching

```bash
# Find errors in logs
kubectl logs <pod-name> | grep -i error

# Find specific patterns
kubectl logs <pod-name> | grep "connection refused"

# Count occurrences
kubectl logs <pod-name> | grep -c "timeout"

# Show context around matches
kubectl logs <pod-name> | grep -A 5 -B 5 "fatal"
```

### 2. Time-based Analysis

```bash
# Recent logs
kubectl logs <pod-name> --since=1h
kubectl logs <pod-name> --since-time=2024-01-01T12:00:00Z

# Logs with timestamps
kubectl logs <pod-name> --timestamps

# Tail logs
kubectl logs <pod-name> --tail=100
```

### 3. Multi-container Logs

```bash
# Specific container
kubectl logs <pod-name> -c <container-name>

# All containers
kubectl logs <pod-name> --all-containers=true

# Follow multiple containers
kubectl logs -f <pod-name> --all-containers=true --prefix=true
```

### 4. Log Aggregation

```bash
# All Pods in deployment
kubectl logs -l app=myapp --tail=50

# Previous container instance
kubectl logs <pod-name> --previous

# Multiple namespaces
for ns in $(kubectl get ns -o name | cut -d/ -f2); do
  kubectl logs -n $ns -l app=myapp --tail=10
done
```

## Structured Logging Best Practices

### JSON Logging Format

```json
{
  "timestamp": "2024-01-15T10:30:00Z",
  "level": "ERROR",
  "message": "Database connection failed",
  "error": "ECONNREFUSED",
  "service": "api-gateway",
  "pod": "api-gateway-7d4f8b9c-x5k2m",
  "trace_id": "abc123",
  "user_id": "user-456"
}
```

**Benefits**:
- Easy to parse and query
- Supports log aggregation tools
- Enables correlation across services

### Log Levels

```
TRACE: Very detailed, debug-level info
DEBUG: Diagnostic information
INFO: Normal operational messages
WARN: Warning messages, potential issues
ERROR: Error messages, something failed
FATAL: Critical errors, application crash
```

### Contextual Information

Include in logs:
- Timestamp (ISO 8601 format)
- Log level
- Service/component name
- Request ID / Trace ID
- User ID (if applicable)
- Error details
- Stack traces (for errors)

## Common Kubernetes System Logs

### Kubelet Logs

```bash
# On node
journalctl -u kubelet -f

# Common patterns:
# - "Failed to pull image"
# - "Container runtime error"
# - "Evicting pod"
# - "Node NotReady"
```

### API Server Logs

```bash
kubectl logs -n kube-system kube-apiserver-<node>

# Common patterns:
# - Authentication failures
# - Authorization denials
# - Admission webhook errors
# - API request errors
```

### CoreDNS Logs

```bash
kubectl logs -n kube-system -l k8s-app=kube-dns

# Common patterns:
# - DNS query errors
# - Upstream DNS failures
# - Configuration errors
```

## Log Retention and Management

### Best Practices

1. **Log Rotation**: Prevent disk space issues
2. **Log Aggregation**: Centralize logs (ELK, Loki, etc.)
3. **Log Sampling**: Sample high-volume logs
4. **Structured Logging**: Use JSON format
5. **Log Levels**: Use appropriate log levels
6. **Sensitive Data**: Redact passwords, tokens, PII

### Kubernetes Log Locations

```bash
# Container logs
/var/log/containers/*.log

# Pod logs
/var/log/pods/

# Kubelet logs
journalctl -u kubelet

# Container runtime logs
journalctl -u docker  # or containerd
```

## Troubleshooting Checklist

When analyzing logs:

1. **Check timing**: When did the error start?
2. **Check frequency**: Is it consistent or intermittent?
3. **Check correlation**: Do errors coincide with deployments/changes?
4. **Check patterns**: Are there common error messages?
5. **Check context**: What was happening before the error?
6. **Check impact**: Which users/services are affected?
7. **Check resources**: Are resource limits being hit?
8. **Check dependencies**: Are external services healthy?

## Summary

Effective log analysis requires:

1. **Structured logging**: Use consistent, parseable formats
2. **Contextual information**: Include relevant metadata
3. **Pattern recognition**: Know common error signatures
4. **Aggregation**: Centralize logs for analysis
5. **Retention**: Keep logs long enough for investigation
6. **Automation**: Alert on critical patterns

Always correlate logs with metrics and events for complete picture.
