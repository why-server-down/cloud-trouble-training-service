# Kubernetes Pod Lifecycle and States

> **Source**: Kubernetes Official Documentation  
> **Category**: Core Concepts  
> **Last Updated**: 2024

## Overview

This document provides an authoritative reference for understanding Kubernetes Pod lifecycle phases, conditions, and status reasons based on the official Kubernetes documentation.

## Pod Phase

A Pod's `status` field is a `PodStatus` object, which has a `phase` field. The phase of a Pod is a simple, high-level summary of where the Pod is in its lifecycle.

### Pod Phases

| Phase | Description |
|-------|-------------|
| **Pending** | The Pod has been accepted by the Kubernetes cluster, but one or more of the containers has not been set up and made ready to run. This includes time a Pod spends waiting to be scheduled as well as the time spent downloading container images over the network. |
| **Running** | The Pod has been bound to a node, and all of the containers have been created. At least one container is still running, or is in the process of starting or restarting. |
| **Succeeded** | All containers in the Pod have terminated successfully, and will not be restarted. |
| **Failed** | All containers in the Pod have terminated, and at least one container has terminated in failure (exited with non-zero status or was terminated by the system). |
| **Unknown** | The state of the Pod could not be obtained, typically due to an error in communicating with the node where the Pod should be running. |

## Pod Conditions

A Pod has a PodStatus, which has an array of PodConditions through which the Pod has or has not passed:

### Condition Types

- **PodScheduled**: the Pod has been scheduled to a node
- **ContainersReady**: all containers in the Pod are ready
- **Initialized**: all init containers have completed successfully
- **Ready**: the Pod is able to serve requests and should be added to the load balancing pools of all matching Services

### Condition Status

Each condition has a `status` field with one of three possible values:
- **True**: The condition is satisfied
- **False**: The condition is not satisfied
- **Unknown**: The condition status cannot be determined

## Container States

Kubernetes tracks the state of each container inside a Pod. Once the scheduler assigns a Pod to a Node, the kubelet starts creating containers for that Pod using a container runtime.

### Three Possible Container States

#### 1. Waiting

A container in the `Waiting` state is still running the operations it requires in order to complete start up. Examples:
- Pulling container image from registry
- Applying Secret data
- Waiting for init containers to complete

**Common Waiting Reasons**:
- `ContainerCreating`: Container is being created
- `PodInitializing`: Init containers are running
- `CrashLoopBackOff`: Container is waiting to restart after crashing

#### 2. Running

The `Running` state indicates that a container is executing without issues. If there was a postStart hook configured, it has already executed and finished.

**Characteristics**:
- Main process (PID 1) is running
- Liveness probes are passing (if configured)
- Container is performing its intended function

#### 3. Terminated

A container in the `Terminated` state began execution and then either ran to completion or failed for some reason.

**Exit Codes**:
- `0`: Success (clean exit)
- `1-127`: Application error
- `128+n`: Fatal error signal (e.g., 137 = 128 + 9 = SIGKILL)
- `137`: OOMKilled (Out of Memory)
- `143`: SIGTERM (graceful shutdown request)

**Termination Reasons**:
- `Completed`: Container finished successfully
- `Error`: Container exited with error
- `OOMKilled`: Container was killed due to out-of-memory
- `ContainerCannotRun`: Container failed to start

## Pod Status Reasons

### Common Status Reasons

#### CrashLoopBackOff

**Description**: Container is failing repeatedly and Kubernetes is backing off before attempting to restart it again.

**Causes**:
- Application crashes immediately on startup
- Misconfigured command or arguments
- Missing dependencies or configuration files
- Port conflicts
- Failed liveness probes

**Backoff Strategy**:
- Initial delay: 10 seconds
- Maximum delay: 5 minutes
- Exponential backoff with randomization

#### ImagePullBackOff

**Description**: Kubernetes cannot pull the container image from the registry.

**Causes**:
- Image name or tag is incorrect
- Image does not exist in registry
- Authentication credentials are missing or invalid
- Network connectivity issues to registry
- Registry rate limits exceeded

**Backoff Behavior**:
- Kubernetes retries with exponential backoff
- Maximum backoff: 5 minutes
- Will continue retrying indefinitely

#### ErrImagePull

**Description**: Initial failure to pull the container image. This will transition to `ImagePullBackOff` if the problem persists.

#### CreateContainerConfigError

**Description**: Error creating the container configuration, typically due to missing ConfigMaps, Secrets, or invalid volume mounts.

**Common Causes**:
- Referenced ConfigMap or Secret does not exist
- Invalid volume mount configuration
- Security context conflicts

#### InvalidImageName

**Description**: The specified image name is not valid.

#### Evicted

**Description**: Pod was evicted from the node due to resource pressure.

**Eviction Signals**:
- `memory.available`: Available memory on node
- `nodefs.available`: Available disk space on node's filesystem
- `nodefs.inodesFree`: Available inodes on node's filesystem
- `imagefs.available`: Available disk space for container runtime
- `imagefs.inodesFree`: Available inodes for container runtime

**Eviction Thresholds**:
```yaml
# Soft eviction
evictionSoft:
  memory.available: "1.5Gi"
  nodefs.available: "10%"
evictionSoftGracePeriod:
  memory.available: "1m30s"
  nodefs.available: "2m"

# Hard eviction
evictionHard:
  memory.available: "100Mi"
  nodefs.available: "5%"
```

## Pod Restart Policy

The `restartPolicy` field applies to all containers in the Pod:

- **Always** (default): Always restart the container when it terminates
- **OnFailure**: Restart only if the container exits with non-zero status
- **Never**: Never restart the container

**Important Notes**:
- Restart policy only applies to containers managed by the kubelet on the same node
- The kubelet restarts containers with exponential back-off delay (10s, 20s, 40s, ..., capped at 5 minutes)
- The back-off timer resets after 10 minutes of successful execution

## Init Containers

Init containers are specialized containers that run before app containers in a Pod.

**Characteristics**:
- Always run to completion
- Each init container must complete successfully before the next one starts
- If an init container fails, the Pod will not start until it succeeds (respecting restartPolicy)

**Common Use Cases**:
- Wait for a Service to be created
- Register this Pod with a remote server
- Clone a git repository into a volume
- Generate configuration files

**Status**:
When init containers are running, Pod status shows:
```
Status: Init:0/3  # 0 out of 3 init containers completed
```

## Debugging Pod States

### Key kubectl Commands

```bash
# Get Pod status
kubectl get pod <pod-name>

# Detailed Pod information
kubectl describe pod <pod-name>

# Check Pod conditions
kubectl get pod <pod-name> -o jsonpath='{.status.conditions[*]}'

# Check container states
kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[*].state}'

# View container logs
kubectl logs <pod-name> [-c <container-name>]

# View previous container logs (after crash)
kubectl logs <pod-name> --previous

# Check events
kubectl get events --field-selector involvedObject.name=<pod-name>
```

### Analyzing Pod Status

```bash
# Get comprehensive Pod status
kubectl get pod <pod-name> -o yaml

# Key sections to check:
# - status.phase: Overall Pod phase
# - status.conditions: Detailed conditions
# - status.containerStatuses: Individual container states
# - status.initContainerStatuses: Init container states
# - status.reason: Human-readable reason for current state
# - status.message: Detailed message about state
```

## Common Troubleshooting Scenarios

### Scenario 1: Pod Stuck in Pending

**Symptoms**:
```
NAME        READY   STATUS    RESTARTS   AGE
my-pod      0/1     Pending   0          5m
```

**Investigation Steps**:
1. Check if Pod is scheduled: `kubectl describe pod <pod-name> | grep Node:`
2. Check events: `kubectl describe pod <pod-name> | grep -A 10 Events:`
3. Check node resources: `kubectl describe nodes | grep -A 5 "Allocated resources"`

**Common Causes**:
- Insufficient resources (CPU, memory)
- Node selector or affinity rules preventing scheduling
- Taints on nodes without matching tolerations
- PersistentVolumeClaim not bound

### Scenario 2: Pod in CrashLoopBackOff

**Symptoms**:
```
NAME        READY   STATUS             RESTARTS   AGE
my-pod      0/1     CrashLoopBackOff   5          5m
```

**Investigation Steps**:
1. Check logs: `kubectl logs <pod-name> --previous`
2. Check exit code: `kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[0].lastState.terminated.exitCode}'`
3. Check restart count: `kubectl get pod <pod-name> -o jsonpath='{.status.containerStatuses[0].restartCount}'`

**Common Exit Codes**:
- `0`: Success (should not crash)
- `1`: Application error
- `137`: OOMKilled (128 + 9)
- `139`: Segmentation fault (128 + 11)
- `143`: SIGTERM (128 + 15)

### Scenario 3: Container OOMKilled

**Symptoms**:
```
NAME        READY   STATUS      RESTARTS   AGE
my-pod      0/1     OOMKilled   3          2m
```

**Investigation Steps**:
```bash
# Check memory limits
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[0].resources}'

# Check actual memory usage (requires metrics-server)
kubectl top pod <pod-name>

# Check termination reason
kubectl describe pod <pod-name> | grep -A 5 "Last State"
```

**Resolution**:
- Increase memory limits
- Optimize application memory usage
- Add memory requests to ensure proper scheduling
- Consider using Vertical Pod Autoscaler

### Scenario 4: ImagePullBackOff

**Symptoms**:
```
NAME        READY   STATUS             RESTARTS   AGE
my-pod      0/1     ImagePullBackOff   0          2m
```

**Investigation Steps**:
```bash
# Check image name
kubectl get pod <pod-name> -o jsonpath='{.spec.containers[0].image}'

# Check pull status
kubectl describe pod <pod-name> | grep -A 10 "Events:"

# Verify imagePullSecrets
kubectl get pod <pod-name> -o jsonpath='{.spec.imagePullSecrets}'
```

**Common Issues**:
- Typo in image name or tag
- Private registry without credentials
- Network issues
- Registry rate limits (Docker Hub)

## Best Practices

### 1. Resource Management

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: resource-demo
spec:
  containers:
  - name: app
    image: myapp:1.0
    resources:
      requests:
        memory: "64Mi"
        cpu: "250m"
      limits:
        memory: "128Mi"
        cpu: "500m"
```

**Guidelines**:
- Always set resource requests for proper scheduling
- Set memory limits to prevent OOMKills on other Pods
- CPU limits are optional (can cause throttling)
- Requests should reflect typical usage
- Limits should allow for spikes

### 2. Health Checks

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: health-demo
spec:
  containers:
  - name: app
    image: myapp:1.0
    livenessProbe:
      httpGet:
        path: /healthz
        port: 8080
      initialDelaySeconds: 15
      periodSeconds: 10
      failureThreshold: 3
    readinessProbe:
      httpGet:
        path: /ready
        port: 8080
      initialDelaySeconds: 5
      periodSeconds: 5
      failureThreshold: 3
    startupProbe:
      httpGet:
        path: /startup
        port: 8080
      initialDelaySeconds: 0
      periodSeconds: 10
      failureThreshold: 30
```

**Probe Types**:
- **livenessProbe**: Restart container if fails
- **readinessProbe**: Remove from service if fails
- **startupProbe**: Protect slow-starting containers

### 3. Graceful Shutdown

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: graceful-demo
spec:
  terminationGracePeriodSeconds: 30
  containers:
  - name: app
    image: myapp:1.0
    lifecycle:
      preStop:
        exec:
          command: ["/bin/sh", "-c", "sleep 15"]
```

**Shutdown Sequence**:
1. Pod set to "Terminating" state
2. preStop hook executes (if defined)
3. SIGTERM sent to main process
4. Grace period countdown starts (default 30s)
5. SIGKILL sent if process still running after grace period

### 4. Pod Disruption Budgets

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: myapp
```

**Purpose**:
- Protect against voluntary disruptions
- Ensure minimum availability during:
  - Node draining
  - Cluster upgrades
  - Application updates

## References

- [Pod Lifecycle - Kubernetes Docs](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/)
- [Pod Phase - API Reference](https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/pod-v1/#PodStatus)
- [Container States - Kubernetes Docs](https://kubernetes.io/docs/concepts/workloads/pods/pod-lifecycle/#container-states)
- [Init Containers](https://kubernetes.io/docs/concepts/workloads/pods/init-containers/)
- [Pod Disruption](https://kubernetes.io/docs/concepts/workloads/pods/disruptions/)

## Summary

Understanding Pod states and lifecycle is fundamental to Kubernetes troubleshooting:

1. **Phase** indicates high-level status (Pending, Running, Succeeded, Failed, Unknown)
2. **Conditions** provide detailed state information (PodScheduled, ContainersReady, Initialized, Ready)
3. **Container States** show individual container status (Waiting, Running, Terminated)
4. **Status Reasons** explain why a Pod is in a particular state (CrashLoopBackOff, ImagePullBackOff, etc.)
5. **Restart Policy** determines container restart behavior
6. **Resource management**, **health checks**, and **graceful shutdown** are critical for reliable Pods

Always start troubleshooting with `kubectl describe pod` and `kubectl logs` to understand the current state and history of your Pods.
