# Kubernetes Debugging Guide

> **Source**: Kubernetes Official Documentation  
> **Category**: Troubleshooting  
> **Last Updated**: 2024

## Overview

This guide provides official Kubernetes debugging techniques and best practices for diagnosing and resolving issues with applications running in Kubernetes clusters.

## Debugging Workflow

```
1. Identify the Problem
   ↓
2. Check Application Logs
   ↓
3. Inspect Pod Status
   ↓
4. Examine Events
   ↓
5. Verify Configuration
   ↓
6. Test Network Connectivity
   ↓
7. Review Resource Usage
   ↓
8. Check Node Health
```

## 1. Debugging Pods

### Check Pod Status

```bash
# List all Pods
kubectl get pods

# Get Pod details
kubectl get pod <pod-name> -o wide

# Describe Pod (most important command)
kubectl describe pod <pod-name>

# Get Pod YAML
kubectl get pod <pod-name> -o yaml

# Watch Pod status in real-time
kubectl get pods --watch
```

### Common Pod Issues

#### Pod is Pending

**Check**:
```bash
# See why Pod is not scheduled
kubectl describe pod <pod-name> | grep -A 10 Events:

# Check node resources
kubectl describe nodes | grep -A 5 "Allocated resources"

# Check PVC status (if using persistent volumes)
kubectl get pvc
```

**Common Reasons**:
- Insufficient CPU or memory on nodes
- No nodes match Pod's nodeSelector or affinity rules
- Taints on nodes without matching tolerations
- PersistentVolumeClaim is not bound
- Image pull secrets are missing

#### Pod is Running but not Ready

**Check**:
```bash
# Check readiness probe
kubectl describe pod <pod-name> | grep -A 5 "Readiness"

# Check conditions
kubectl get pod <pod-name> -o jsonpath='{.status.conditions[?(@.type=="Ready")]}'

# Check container status
kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[*]}'
```

**Common Reasons**:
- Readiness probe is failing
- Container is still starting up
- Application is not yet ready to serve traffic
- Dependencies (databases, other services) are not available

#### Pod is CrashLoopBackOff

**Check**:
```bash
# View current logs
kubectl logs <pod-name>

# View previous container logs
kubectl logs <pod-name> --previous

# Check exit code
kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.exitCode}'

# Check restart count
kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[0].restartCount}'
```

**Common Reasons**:
- Application crashes on startup
- Missing environment variables or configuration
- Failed liveness probe
- Port already in use
- Missing dependencies

## 2. Debugging Services

### Check Service Status

```bash
# List services
kubectl get services

# Describe service
kubectl describe service <service-name>

# Check endpoints
kubectl get endpoints <service-name>

# Test service DNS
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup <service-name>
```

### Common Service Issues

#### No Endpoints

**Symptoms**: Service exists but has no endpoints

**Check**:
```bash
# Verify Pod labels match Service selector
kubectl get pods --show-labels
kubectl describe service <service-name> | grep Selector

# Check if Pods are ready
kubectl get pods -l app=<label>
```

**Resolution**:
- Ensure Pod labels match Service selector exactly
- Verify Pods are in Ready state
- Check readiness probes

#### Cannot Connect to Service

**Check**:
```bash
# Test from within cluster
kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -- bash
# Inside the container:
curl http://<service-name>:<port>

# Check service type
kubectl get service <service-name> -o jsonpath='{.spec.type}'

# For ClusterIP, verify you're testing from within cluster
# For NodePort, check firewall rules
# For LoadBalancer, check cloud provider integration
```

## 3. Debugging Networking

### Pod-to-Pod Communication

```bash
# Get Pod IP
kubectl get pod <pod-name> -o jsonpath='{.status.podIP}'

# Test connectivity from another Pod
kubectl run -it --rm debug --image=nicolaka/netshoot --restart=Never -- bash
ping <pod-ip>
curl http://<pod-ip>:<port>

# Check network policies
kubectl get networkpolicy
kubectl describe networkpolicy <policy-name>
```

### DNS Resolution

```bash
# Test DNS resolution
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup kubernetes.default

# Test service DNS
kubectl run -it --rm debug --image=busybox --restart=Never -- nslookup <service-name>.<namespace>.svc.cluster.local

# Check CoreDNS logs
kubectl logs -n kube-system -l k8s-app=kube-dns

# Verify CoreDNS ConfigMap
kubectl get configmap coredns -n kube-system -o yaml
```

### Network Policy Debugging

```bash
# List network policies
kubectl get networkpolicy -A

# Describe policy
kubectl describe networkpolicy <policy-name>

# Check if Pod is selected by policy
kubectl get pod <pod-name> --show-labels
```

**Common Issues**:
- NetworkPolicy blocks traffic by default (deny-all policy)
- Ingress/Egress rules don't match Pod selectors
- Namespace selectors are incorrect

## 4. Debugging Storage

### PersistentVolumeClaim Issues

```bash
# Check PVC status
kubectl get pvc

# Describe PVC
kubectl describe pvc <pvc-name>

# Check PV
kubectl get pv

# Check storage class
kubectl get storageclass
```

**Common Issues**:

#### PVC Stuck in Pending

**Check**:
```bash
kubectl describe pvc <pvc-name> | grep -A 10 Events:
```

**Reasons**:
- No PersistentVolume available matching the claim
- StorageClass does not exist or cannot provision
- Insufficient storage on underlying system
- Access mode mismatch

#### Pod Cannot Mount Volume

**Check**:
```bash
kubectl describe pod <pod-name> | grep -A 10 "Events:"
kubectl describe pod <pod-name> | grep -A 5 "Volumes:"
```

**Reasons**:
- Volume already mounted to another Pod (ReadWriteOnce)
- Node cannot access storage backend
- Permissions issues
- CSI driver problems

## 5. Debugging Container Images

### Image Pull Issues

```bash
# Check image name
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[*].image}'

# Check image pull policy
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[*].imagePullPolicy}'

# Test image pull manually
docker pull <image-name>

# Check image pull secrets
kubectl get pod <pod-name> -o jsonpath='{.spec.imagePullSecrets[*].name}'
kubectl get secret <secret-name> -o yaml
```

### Image Pull Secrets

```bash
# Create docker registry secret
kubectl create secret docker-registry <secret-name> \
  --docker-server=<registry-url> \
  --docker-username=<username> \
  --docker-password=<password> \
  --docker-email=<email>

# Verify secret
kubectl get secret <secret-name> -o yaml

# Add to ServiceAccount
kubectl patch serviceaccount default -p '{"imagePullSecrets": [{"name": "<secret-name>"}]}'
```

## 6. Debugging Resource Constraints

### Check Resource Usage

```bash
# Requires metrics-server
kubectl top nodes
kubectl top pods
kubectl top pod <pod-name> --containers

# Check resource requests and limits
kubectl describe pod <pod-name> | grep -A 10 "Limits:\|Requests:"

# Check node allocatable resources
kubectl describe node <node-name> | grep -A 10 "Allocatable:"
```

### Resource Pressure

```bash
# Check node conditions
kubectl describe node <node-name> | grep -A 10 "Conditions:"

# Check for evicted Pods
kubectl get pods -A | grep Evicted

# Check kubelet logs
journalctl -u kubelet | grep -i "evict\|oom"
```

**Node Conditions**:
- `MemoryPressure`: Node is running out of memory
- `DiskPressure`: Node is running out of disk space
- `PIDPressure`: Too many processes on node
- `NetworkUnavailable`: Network is not properly configured

## 7. Debugging with kubectl debug

### Debug Running Pod

```bash
# Create debug container in Pod (Kubernetes 1.23+)
kubectl debug <pod-name> -it --image=busybox --target=<container-name>

# Debug with different image
kubectl debug <pod-name> -it --image=nicolaka/netshoot

# Debug with ephemeral container
kubectl debug <pod-name> -it --image=busybox --target=<container-name> --share-processes
```

### Debug Failed Pod

```bash
# Create copy of Pod with different command
kubectl debug <pod-name> -it --copy-to=<new-pod-name> --container=<container-name> -- sh

# Debug with different image
kubectl debug <pod-name> -it --copy-to=<new-pod-name> --set-image=<container-name>=busybox
```

### Debug Node

```bash
# Create debug Pod on node
kubectl debug node/<node-name> -it --image=ubuntu

# Access node filesystem
# Node root filesystem is mounted at /host
ls /host
chroot /host
```

## 8. Debugging RBAC

### Check Permissions

```bash
# Check if you can perform action
kubectl auth can-i get pods
kubectl auth can-i delete pods
kubectl auth can-i create deployments

# Check for specific user/serviceaccount
kubectl auth can-i get pods --as=system:serviceaccount:default:my-sa
kubectl auth can-i get pods --as=user@example.com

# Check permissions across all resources
kubectl auth can-i --list
```

### Debug ServiceAccount Permissions

```bash
# Get ServiceAccount
kubectl get serviceaccount <sa-name> -o yaml

# Check roles and rolebindings
kubectl get rolebinding -A | grep <sa-name>
kubectl get clusterrolebinding | grep <sa-name>

# Describe role
kubectl describe role <role-name>
kubectl describe clusterrole <clusterrole-name>
```

## 9. Debugging with Logs

### Application Logs

```bash
# View logs
kubectl logs <pod-name>

# Follow logs
kubectl logs -f <pod-name>

# Previous container logs
kubectl logs <pod-name> --previous

# Multi-container Pod
kubectl logs <pod-name> -c <container-name>

# All containers
kubectl logs <pod-name> --all-containers=true

# Logs with timestamp
kubectl logs <pod-name> --timestamps

# Recent logs
kubectl logs <pod-name> --tail=100
kubectl logs <pod-name> --since=1h
```

### System Logs

```bash
# API server logs
kubectl logs -n kube-system kube-apiserver-<node-name>

# Controller manager logs
kubectl logs -n kube-system kube-controller-manager-<node-name>

# Scheduler logs
kubectl logs -n kube-system kube-scheduler-<node-name>

# CoreDNS logs
kubectl logs -n kube-system -l k8s-app=kube-dns

# Kubelet logs (on node)
journalctl -u kubelet -f
```

## 10. Debugging with Events

### View Events

```bash
# All events in namespace
kubectl get events

# Sort by timestamp
kubectl get events --sort-by='.lastTimestamp'

# Filter by object
kubectl get events --field-selector involvedObject.name=<pod-name>

# Filter by type
kubectl get events --field-selector type=Warning

# Events for specific resource
kubectl describe pod <pod-name> | grep -A 10 Events:
```

### Event Types

- **Normal**: Informational events
- **Warning**: Potential issues

**Common Warning Events**:
- `FailedScheduling`: Pod cannot be scheduled
- `FailedMount`: Cannot mount volume
- `BackOff`: Container is in CrashLoopBackOff
- `Unhealthy`: Liveness/Readiness probe failed
- `FailedCreatePodSandBox`: Cannot create Pod network
- `ImagePullBackOff`: Cannot pull image

## 11. Advanced Debugging Tools

### Ephemeral Debug Container

```yaml
# Add debug container to running Pod
apiVersion: v1
kind: Pod
metadata:
  name: myapp
spec:
  containers:
  - name: app
    image: myapp:1.0
  ephemeralContainers:
  - name: debug
    image: nicolaka/netshoot
    stdin: true
    tty: true
```

Apply with:
```bash
kubectl debug <pod-name> -it --image=nicolaka/netshoot --target=app
```

### Network Debugging Tools

```bash
# Use netshoot for comprehensive network debugging
kubectl run netshoot --rm -i --tty --image nicolaka/netshoot -- bash

# Inside the container:
# - nslookup, dig: DNS testing
# - curl, wget: HTTP testing
# - ping, traceroute: Network connectivity
# - tcpdump: Packet capture
# - netstat, ss: Socket statistics
# - iperf3: Network performance
```

### Process Debugging

```bash
# Debug with process namespace sharing
kubectl debug <pod-name> -it --image=busybox --share-processes --copy-to=debug-pod

# Inside debug container, can see all processes
ps aux
```

## 12. Debugging Checklist

### Quick Diagnostic Commands

```bash
# 1. Pod status
kubectl get pod <pod-name> -o wide

# 2. Detailed Pod info
kubectl describe pod <pod-name>

# 3. Logs
kubectl logs <pod-name> [--previous]

# 4. Events
kubectl get events --field-selector involvedObject.name=<pod-name>

# 5. Resource usage
kubectl top pod <pod-name>

# 6. Service connectivity
kubectl get endpoints <service-name>

# 7. Network policy
kubectl get networkpolicy

# 8. Node status
kubectl get nodes
kubectl describe node <node-name>
```

### Systematic Troubleshooting

1. **Identify Symptoms**: What is not working?
2. **Check Events**: `kubectl describe` and `kubectl get events`
3. **Review Logs**: Application and system logs
4. **Verify Configuration**: Specs, ConfigMaps, Secrets
5. **Test Connectivity**: Network, DNS, Services
6. **Check Resources**: CPU, memory, storage
7. **Review RBAC**: Permissions and access
8. **Examine Node**: Node health and capacity

## Common Debugging Scenarios

### Scenario 1: Application Not Responding

```bash
# 1. Check if Pod is running
kubectl get pod <pod-name>

# 2. Check if service has endpoints
kubectl get endpoints <service-name>

# 3. Test direct Pod access
POD_IP=$(kubectl get pod <pod-name> -o jsonpath='{.status.podIP}')
kubectl run curl --rm -i --tty --image=curlimages/curl -- curl http://$POD_IP:<port>

# 4. Check readiness probe
kubectl describe pod <pod-name> | grep -A 5 "Readiness"

# 5. Check logs
kubectl logs <pod-name>
```

### Scenario 2: High Memory Usage

```bash
# 1. Check current usage
kubectl top pod <pod-name>

# 2. Check limits
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[0].resources}'

# 3. Check for OOMKills
kubectl describe pod <pod-name> | grep -i oom

# 4. Get detailed metrics (if metrics-server installed)
kubectl get --raw /apis/metrics.k8s.io/v1beta1/namespaces/default/pods/<pod-name>
```

### Scenario 3: Intermittent Failures

```bash
# 1. Watch Pod status
kubectl get pods --watch

# 2. Follow logs in real-time
kubectl logs -f <pod-name>

# 3. Monitor events
kubectl get events --watch

# 4. Check for resource constraints
kubectl top nodes
kubectl describe nodes | grep -A 5 "Allocated resources"

# 5. Review recent restarts
kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[*].restartCount}'
```

## Best Practices

1. **Always start with `kubectl describe`**: Provides comprehensive information including events
2. **Check logs**: Both current and previous logs for crashed containers
3. **Use labels**: Make filtering and identifying resources easier
4. **Set up monitoring**: Metrics-server, Prometheus for proactive issue detection
5. **Enable verbose logging**: During development/debugging
6. **Use ephemeral debug containers**: For production debugging without changing Pods
7. **Automate health checks**: Liveness and readiness probes
8. **Implement proper logging**: Structured logs, appropriate log levels
9. **Use namespaces**: Isolate workloads for easier debugging
10. **Document common issues**: Build runbooks for your team

## References

- [Debugging Pods - Kubernetes Docs](https://kubernetes.io/docs/tasks/debug/debug-application/)
- [Debug Running Pods](https://kubernetes.io/docs/tasks/debug/debug-application/debug-running-pod/)
- [kubectl debug](https://kubernetes.io/docs/reference/kubectl/generated/kubectl_debug/)
- [Troubleshoot Applications](https://kubernetes.io/docs/tasks/debug/debug-application/)
- [Troubleshoot Clusters](https://kubernetes.io/docs/tasks/debug/debug-cluster/)

## Summary

Effective Kubernetes debugging requires:

1. **Systematic approach**: Follow a consistent workflow
2. **Right tools**: kubectl, logs, events, metrics
3. **Understanding**: Know Pod lifecycle and states
4. **Practice**: Familiarity with common issues
5. **Documentation**: Keep runbooks updated

Start with simple commands (`kubectl get`, `kubectl describe`, `kubectl logs`) and progressively use more advanced tools (`kubectl debug`, ephemeral containers) as needed.
