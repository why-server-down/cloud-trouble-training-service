# Kubernetes Incident Response Playbooks

> **Source**: Komodor Best Practices  
> **Category**: Incident Management  
> **Last Updated**: 2024

## Overview

This document provides battle-tested playbooks for responding to common Kubernetes incidents in production environments. These playbooks are based on real-world incidents and follow SRE best practices.

## Incident Response Framework

```
DETECT → TRIAGE → DIAGNOSE → MITIGATE → RESOLVE → POST-MORTEM
```

### Severity Levels

| Level | Response Time | Description |
|-------|--------------|-------------|
| **P0** | Immediate | Service completely down, customer-facing |
| **P1** | < 15 min | Severe degradation, significant customer impact |
| **P2** | < 1 hour | Moderate impact, some features unavailable |
| **P3** | < 4 hours | Minor issue, workaround available |

## Playbook 1: Pod Crash Loop Emergency

### Symptoms
- Multiple Pods in CrashLoopBackOff state
- Service degradation or complete outage
- High restart count on Pods
- Customer reports of errors

### Immediate Actions (First 5 Minutes)

```bash
# 1. Identify affected Pods
kubectl get pods -A | grep CrashLoopBackOff

# 2. Check recent deployments
kubectl rollout history deployment/<name>

# 3. Get immediate logs
kubectl logs <pod-name> --tail=50 --previous

# 4. Check recent events
kubectl get events --sort-by='.lastTimestamp' | head -20
```

### Triage Questions

1. **When did this start?** Check Pod age and restart count
2. **What changed recently?** Deployment, ConfigMap, Secret updates
3. **Is this affecting all Pods or specific ones?** Check node distribution
4. **Are there any error patterns in logs?** Application errors, connection failures

### Diagnosis Steps

```bash
# Check exit codes
kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.exitCode}'

# Common exit codes:
# 137 = OOMKilled
# 1 = Application error
# 139 = Segmentation fault
# 143 = SIGTERM

# Check resource constraints
kubectl describe pod <pod-name> | grep -A 10 "Limits:\|Requests:"

# Check configuration
kubectl describe pod <pod-name> | grep -A 10 "Environment:"
kubectl get configmap <cm-name> -o yaml
kubectl get secret <secret-name> -o yaml

# Check dependencies
kubectl get svc
kubectl get endpoints <service-name>
```

### Common Root Causes & Solutions

#### Cause 1: Missing or Invalid Configuration

**Symptoms**:
```
Error: ENOENT: no such file or directory, open '/app/config.json'
Error: Required environment variable API_KEY is not set
```

**Solution**:
```bash
# Check ConfigMap/Secret exists
kubectl get configmap <name>
kubectl get secret <name>

# Verify Pod has correct volume mounts
kubectl describe pod <pod-name> | grep -A 10 "Mounts:"

# Quick fix: Update ConfigMap and restart
kubectl edit configmap <name>
kubectl rollout restart deployment/<name>
```

#### Cause 2: Database Connection Failure

**Symptoms**:
```
Error: connect ECONNREFUSED 10.0.0.1:5432
MongoNetworkError: failed to connect to server
```

**Solution**:
```bash
# Test database connectivity
kubectl run db-test --rm -i --tty --image=postgres:15 -- psql -h <db-host> -U <user>

# Check Service and Endpoints
kubectl get svc <db-service-name>
kubectl get endpoints <db-service-name>

# Verify DNS resolution
kubectl run dns-test --rm -i --tty --image=busybox -- nslookup <db-service-name>

# Check network policies
kubectl get networkpolicy
```

#### Cause 3: Application Code Bug

**Symptoms**:
```
TypeError: Cannot read property 'foo' of undefined
panic: runtime error: invalid memory address
```

**Solution**:
```bash
# Rollback to previous version
kubectl rollout undo deployment/<name>

# Or rollback to specific revision
kubectl rollout history deployment/<name>
kubectl rollout undo deployment/<name> --to-revision=<number>

# Verify rollback
kubectl rollout status deployment/<name>
```

### Mitigation Strategies

#### Strategy 1: Immediate Rollback
```bash
# Fastest way to restore service
kubectl rollout undo deployment/<name>
kubectl rollout status deployment/<name>
```

#### Strategy 2: Scale Down Affected Pods
```bash
# If partial functionality is better than total failure
kubectl scale deployment/<name> --replicas=0
kubectl scale deployment/<healthy-name> --replicas=5
```

#### Strategy 3: Emergency Patch
```bash
# Fix critical config issue
kubectl set env deployment/<name> API_KEY=<value>

# Update image to hotfix version
kubectl set image deployment/<name> container=image:hotfix
```

### Resolution Checklist

- [ ] Service restored to normal operation
- [ ] Error rate returned to baseline
- [ ] Customer impact resolved
- [ ] Monitoring alerts cleared
- [ ] Root cause identified
- [ ] Incident timeline documented
- [ ] Post-mortem scheduled

## Playbook 2: Out of Memory (OOM) Crisis

### Symptoms
- Pods showing OOMKilled status
- Frequent restarts with exit code 137
- Memory usage at or near limits
- Slow application performance before crash

### Immediate Actions

```bash
# 1. Identify OOMKilled Pods
kubectl get pods -A -o json | jq '.items[] | select(.status.containerStatuses[]?.lastState.terminated.reason == "OOMKilled") | .metadata.name'

# 2. Check current memory usage
kubectl top pods --sort-by=memory

# 3. Check memory limits
kubectl get pods -o=jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.containers[0].resources.limits.memory}{"\n"}{end}'

# 4. Review recent memory trends (if metrics available)
kubectl get --raw /apis/metrics.k8s.io/v1beta1/namespaces/<ns>/pods/<pod-name>
```

### Diagnosis

```bash
# Check OOM events
kubectl describe pod <pod-name> | grep -i "oom"

# Get termination message
kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.message}'

# Check logs before crash
kubectl logs <pod-name> --previous --tail=100

# Analyze memory usage patterns
kubectl top pod <pod-name> --containers
```

### Emergency Mitigation

#### Option 1: Increase Memory Limits (Quick Fix)

```bash
# Edit deployment
kubectl edit deployment <name>

# Increase limits
resources:
  limits:
    memory: "2Gi"  # Increased from 1Gi
  requests:
    memory: "1Gi"  # Increased from 512Mi

# Or use patch
kubectl patch deployment <name> -p '{"spec":{"template":{"spec":{"containers":[{"name":"<container>","resources":{"limits":{"memory":"2Gi"}}}]}}}}'
```

#### Option 2: Scale Out (Distribute Load)

```bash
# Increase replicas to distribute memory load
kubectl scale deployment <name> --replicas=5

# Add HPA for auto-scaling
kubectl autoscale deployment <name> --cpu-percent=70 --min=3 --max=10
```

#### Option 3: Enable Memory Limits

```bash
# If no limits set, add them
kubectl set resources deployment <name> --limits=memory=1Gi --requests=memory=512Mi
```

### Root Cause Analysis

**Common Memory Issues**:

1. **Memory Leak**: Usage grows continuously
2. **Traffic Spike**: Temporary high load
3. **Inefficient Code**: Poor memory management
4. **Cache Bloat**: Unbounded cache growth
5. **Large Requests**: Processing huge payloads

**Investigation Commands**:

```bash
# Check application metrics
kubectl port-forward <pod-name> 8080:8080
curl http://localhost:8080/metrics | grep memory

# Enable memory profiling (Node.js example)
kubectl exec <pod-name> -- node --expose-gc --heap-prof app.js

# Check for file descriptor leaks
kubectl exec <pod-name> -- ls -la /proc/1/fd | wc -l
```

### Long-term Solutions

1. **Optimize Application**:
   - Fix memory leaks
   - Implement proper garbage collection
   - Use streaming for large data
   - Implement pagination

2. **Right-size Resources**:
   - Profile actual usage
   - Set appropriate limits
   - Use VPA (Vertical Pod Autoscaler)

3. **Implement Monitoring**:
   - Set memory usage alerts
   - Track memory growth trends
   - Monitor garbage collection metrics

## Playbook 3: Image Pull Failures

### Symptoms
- Pods stuck in ImagePullBackOff or ErrImagePull
- New deployments failing to start
- Rollouts stuck in progress

### Immediate Actions

```bash
# 1. Identify affected Pods
kubectl get pods | grep ImagePullBackOff

# 2. Check image name
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[0].image}'

# 3. Check pull error
kubectl describe pod <pod-name> | grep -A 10 "Events:"

# 4. Verify image exists
docker pull <image-name>  # Or use crane/skopeo
```

### Common Causes

#### Cause 1: Typo in Image Name

**Error**:
```
Failed to pull image "myapp:latets": rpc error: code = NotFound
```

**Solution**:
```bash
# Fix typo
kubectl set image deployment/<name> container=myapp:latest

# Or edit deployment
kubectl edit deployment <name>
```

#### Cause 2: Missing Image Pull Secrets

**Error**:
```
Failed to pull image "private-registry.io/myapp:latest": 
  pull access denied, repository does not exist or may require authorization
```

**Solution**:
```bash
# Create secret
kubectl create secret docker-registry regcred \
  --docker-server=private-registry.io \
  --docker-username=<user> \
  --docker-password=<pass> \
  --docker-email=<email>

# Add to deployment
kubectl patch deployment <name> -p '{"spec":{"template":{"spec":{"imagePullSecrets":[{"name":"regcred"}]}}}}'

# Or add to ServiceAccount
kubectl patch serviceaccount default -p '{"imagePullSecrets":[{"name":"regcred"}]}'
```

#### Cause 3: Registry Rate Limiting

**Error**:
```
toomanyrequests: You have reached your pull rate limit
```

**Solution**:
```bash
# Option 1: Use authenticated pulls (Docker Hub)
kubectl create secret docker-registry dockerhub \
  --docker-server=docker.io \
  --docker-username=<user> \
  --docker-password=<pass>

# Option 2: Use image cache/proxy
# Set up local registry mirror

# Option 3: Use alternative registry
# Push to ghcr.io, gcr.io, or ECR
```

### Quick Recovery

```bash
# Option 1: Rollback to working version
kubectl rollout undo deployment/<name>

# Option 2: Fix image tag
kubectl set image deployment/<name> container=<working-image>

# Option 3: Use imagePullPolicy: IfNotPresent
kubectl patch deployment <name> -p '{"spec":{"template":{"spec":{"containers":[{"name":"<container>","imagePullPolicy":"IfNotPresent"}]}}}}'
```

## Playbook 4: Service Disruption

### Symptoms
- 5xx errors from application
- Connection timeouts
- Service has no endpoints
- Load balancer not routing traffic

### Immediate Actions

```bash
# 1. Check Service and Endpoints
kubectl get svc <service-name>
kubectl get endpoints <service-name>

# 2. Verify Pod labels match Service selector
kubectl get pods --show-labels
kubectl describe svc <service-name> | grep Selector

# 3. Test direct Pod connectivity
POD_IP=$(kubectl get pod <pod-name> -o jsonpath='{.status.podIP}')
kubectl run test --rm -i --tty --image=curlimages/curl -- curl http://$POD_IP:<port>

# 4. Check readiness probes
kubectl describe pod <pod-name> | grep -A 5 "Readiness"
```

### Common Issues

#### Issue 1: No Healthy Pods

**Symptoms**: Service has 0 endpoints

**Solution**:
```bash
# Check why Pods are not ready
kubectl get pods -l app=<label>
kubectl describe pod <pod-name> | grep -A 5 "Conditions:"

# Common fixes:
# - Fix readiness probe
# - Fix application health endpoint
# - Increase initialDelaySeconds
```

#### Issue 2: Label Mismatch

**Symptoms**: Pods running but Service has no endpoints

**Solution**:
```bash
# Check labels
kubectl get pods --show-labels
kubectl get svc <service-name> -o jsonpath='{.spec.selector}'

# Fix labels
kubectl label pod <pod-name> app=myapp --overwrite
```

#### Issue 3: Network Policy Blocking Traffic

**Solution**:
```bash
# Check network policies
kubectl get networkpolicy
kubectl describe networkpolicy <policy-name>

# Temporary fix: Remove policy
kubectl delete networkpolicy <policy-name>

# Permanent fix: Update policy
kubectl edit networkpolicy <policy-name>
```

## Playbook 5: Node Failure

### Symptoms
- Pods on specific node showing NotReady
- Node status shows NotReady
- Pods being evicted
- High CPU/Memory on node

### Immediate Actions

```bash
# 1. Identify problematic nodes
kubectl get nodes

# 2. Check node conditions
kubectl describe node <node-name> | grep -A 10 "Conditions:"

# 3. Check Pods on node
kubectl get pods --all-namespaces -o wide --field-selector spec.nodeName=<node-name>

# 4. Cordon node to prevent new Pods
kubectl cordon <node-name>
```

### Node Issues

#### Issue 1: Node Out of Resources

```bash
# Check node resources
kubectl describe node <node-name> | grep -A 10 "Allocated resources:"

# Check for pressure
kubectl describe node <node-name> | grep -i "pressure"

# Drain node
kubectl drain <node-name> --ignore-daemonsets --delete-emptydir-data
```

#### Issue 2: Node Network Issues

```bash
# Check kubelet logs (on node)
journalctl -u kubelet -n 100

# Check CNI logs
kubectl logs -n kube-system -l k8s-app=<cni-name>

# Restart kubelet (on node)
systemctl restart kubelet
```

### Recovery

```bash
# After fixing issue, uncordon node
kubectl uncordon <node-name>

# Verify Pods can schedule
kubectl get pods -o wide
```

## Incident Communication Template

```
## Incident Summary
- **Severity**: P0/P1/P2/P3
- **Status**: Investigating/Identified/Monitoring/Resolved
- **Impact**: [Customer-facing description]
- **Start Time**: [UTC timestamp]
- **Components Affected**: [Services/systems]

## Current Status
[Brief description of current state]

## Actions Taken
1. [Action 1]
2. [Action 2]

## Next Steps
- [Next action with ETA]

## Customer Impact
- [Description of user-facing impact]
- [Workaround if available]
```

## Post-Incident Checklist

- [ ] Service fully restored
- [ ] Monitoring confirmed normal
- [ ] Incident timeline created
- [ ] Root cause identified
- [ ] Stakeholders notified
- [ ] Post-mortem scheduled within 48 hours
- [ ] Action items created
- [ ] Playbook updated (if needed)

## Prevention Strategies

1. **Implement Progressive Delivery**:
   - Blue/Green deployments
   - Canary releases
   - Feature flags

2. **Robust Health Checks**:
   - Proper readiness probes
   - Liveness probes with appropriate thresholds
   - Startup probes for slow-starting apps

3. **Resource Management**:
   - Set appropriate limits and requests
   - Use HPA/VPA
   - Monitor resource trends

4. **Chaos Engineering**:
   - Regular chaos tests
   - Game days
   - Failure injection

5. **Monitoring & Alerting**:
   - Comprehensive metrics
   - Actionable alerts
   - On-call runbooks

## References

- [Komodor Kubernetes Troubleshooting Guide](https://komodor.com/learn/kubernetes-troubleshooting/)
- [Google SRE Book - Incident Response](https://sre.google/sre-book/incident-response/)
- [PagerDuty Incident Response](https://response.pagerduty.com/)

## Summary

Effective incident response requires:

1. **Preparation**: Have playbooks ready
2. **Speed**: Quick triage and mitigation
3. **Communication**: Keep stakeholders informed
4. **Learning**: Post-mortems and prevention

Remember: **Restore service first, investigate root cause second.**
