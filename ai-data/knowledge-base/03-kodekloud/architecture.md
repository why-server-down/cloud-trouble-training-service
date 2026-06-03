# Kubernetes Architecture Essentials

> **Source**: KodeKloud Training Materials  
> **Category**: Core Architecture  
> **Last Updated**: 2024

## Kubernetes Cluster Architecture

### Control Plane Components

```
┌─────────────────────────────────────────────────────────┐
│                    CONTROL PLANE                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │  API Server  │  │  Scheduler   │  │  Controller  │  │
│  │              │  │              │  │   Manager    │  │
│  └──────────────┘  └──────────────┘  └──────────────┘  │
│         ▲                                      ▲         │
│         │                                      │         │
│         └────────────────┬──────────────────── │         │
│                          │                     │         │
│                   ┌──────▼──────┐             │         │
│                   │    etcd     │             │         │
│                   │  (Key-Value │             │         │
│                   │    Store)   │             │         │
│                   └─────────────┘             │         │
└─────────────────────────────────────────────────────────┘
                              │
                  ┌───────────┴──────────┐
                  │                       │
         ┌────────▼──────┐       ┌───────▼─────┐
         │   Worker      │       │   Worker    │
         │   Node 1      │       │   Node 2    │
         └───────────────┘       └─────────────┘
```

#### 1. API Server (kube-apiserver)

**Role**: Front-end for Kubernetes control plane

**Responsibilities**:
- Exposes Kubernetes API
- Authenticates and authorizes requests
- Validates and configures API objects
- Serves as communication hub

**Key Points**:
- All components communicate through API server
- Only component that talks to etcd
- Stateless (can run multiple instances)
- RESTful interface

**Common Issues**:
```bash
# Check API server health
kubectl get --raw /healthz

# View API server logs
kubectl logs -n kube-system kube-apiserver-<node-name>

# Common errors:
# - "connection refused" → API server down
# - "Unauthorized" → Authentication issue
# - "Forbidden" → Authorization issue
```

#### 2. etcd

**Role**: Distributed key-value store for cluster state

**What it stores**:
- Cluster configuration
- State of all objects (Pods, Services, etc.)
- Secrets and ConfigMaps
- Node information

**Key Points**:
- Single source of truth
- Distributed and highly-available
- Uses Raft consensus algorithm
- Backup is critical

**Backup/Restore**:
```bash
# Backup etcd
ETCDCTL_API=3 etcdctl snapshot save /backup/snapshot.db \
  --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key

# Restore etcd
ETCDCTL_API=3 etcdctl snapshot restore /backup/snapshot.db \
  --data-dir=/var/lib/etcd-restore
```

#### 3. Scheduler (kube-scheduler)

**Role**: Assigns Pods to Nodes

**Scheduling Process**:
1. **Filtering**: Find nodes that meet Pod requirements
   - Resource requirements (CPU, memory)
   - Node selectors
   - Affinity/Anti-affinity rules
   - Taints and tolerations
   - Pod topology spread

2. **Scoring**: Rank filtered nodes
   - Resource balance
   - Pod spreading
   - Affinity scores
   - Custom priorities

3. **Binding**: Assign Pod to highest-scoring node

**Scheduling Constraints**:

```yaml
# Node Selector
apiVersion: v1
kind: Pod
metadata:
  name: nginx
spec:
  nodeSelector:
    disktype: ssd
  containers:
  - name: nginx
    image: nginx

# Node Affinity
affinity:
  nodeAffinity:
    requiredDuringSchedulingIgnoredDuringExecution:
      nodeSelectorTerms:
      - matchExpressions:
        - key: kubernetes.io/e2e-az-name
          operator: In
          values:
          - e2e-az1
          - e2e-az2

# Pod Anti-Affinity (spread Pods)
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        labelSelector:
          matchExpressions:
          - key: app
            operator: In
            values:
            - myapp
        topologyKey: kubernetes.io/hostname
```

**Debugging Scheduling**:
```bash
# Check scheduler logs
kubectl logs -n kube-system kube-scheduler-<node-name>

# Check why Pod not scheduled
kubectl describe pod <pod-name> | grep -A 10 Events:

# Common reasons:
# - "Insufficient cpu" → Not enough CPU
# - "Insufficient memory" → Not enough memory
# - "Node didn't match Pod's node affinity" → Affinity rules
# - "Node had taints" → Taints without tolerations
```

#### 4. Controller Manager (kube-controller-manager)

**Role**: Runs controller processes

**Key Controllers**:

1. **Node Controller**: Monitors node health
   - Detects node failures
   - Evicts Pods from failed nodes
   - Updates node status

2. **Replication Controller**: Maintains desired replica count
   - Creates/deletes Pods
   - Watches ReplicaSets, Deployments

3. **Endpoints Controller**: Populates Endpoints objects
   - Links Services to Pods
   - Updates endpoints when Pods change

4. **Service Account Controller**: Creates default ServiceAccounts

5. **Namespace Controller**: Cleans up deleted namespaces

**Control Loop Pattern**:
```
┌─────────────────────┐
│  Observe Current    │
│  State              │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Compare with       │
│  Desired State      │
└──────────┬──────────┘
           │
           ▼
┌─────────────────────┐
│  Take Action to     │
│  Reconcile          │
└─────────────────────┘
```

### Worker Node Components

#### 1. Kubelet

**Role**: Node agent that ensures containers are running

**Responsibilities**:
- Registers node with API server
- Watches for PodSpecs from API server
- Manages container lifecycle
- Reports Pod and node status
- Executes probes (liveness, readiness)
- Mounts volumes

**Key Points**:
- Runs on every node
- Primary "node agent"
- Communicates with container runtime

**Configuration**:
```bash
# Kubelet config file (usually)
/var/lib/kubelet/config.yaml

# Common kubelet flags:
--pod-manifest-path=/etc/kubernetes/manifests  # Static Pods
--cluster-dns=10.96.0.10                       # CoreDNS IP
--cluster-domain=cluster.local                 # Cluster domain
```

**Troubleshooting**:
```bash
# Check kubelet status
systemctl status kubelet

# View kubelet logs
journalctl -u kubelet -f

# Check kubelet config
kubectl get cm kubelet-config -n kube-system -o yaml
```

#### 2. Container Runtime

**Role**: Pulls images and runs containers

**Supported Runtimes**:
- **containerd**: Most common (Docker's runtime)
- **CRI-O**: Lightweight alternative
- **Docker** (deprecated, still works via containerd)

**Container Runtime Interface (CRI)**:
- Standard interface between kubelet and runtime
- Allows pluggable runtimes

**Common Commands**:
```bash
# containerd
crictl ps                    # List containers
crictl pods                  # List Pods
crictl images                # List images
crictl logs <container-id>   # View logs

# Check runtime
kubectl get nodes -o wide    # See runtime version
```

#### 3. kube-proxy

**Role**: Maintains network rules for Pod communication

**Responsibilities**:
- Implements Service abstraction
- Manages iptables/IPVS rules
- Enables Pod-to-Service communication
- Load balancing across Pod replicas

**Proxy Modes**:

1. **iptables** (default):
   - Uses iptables rules
   - Good performance
   - No load balancing (random selection)

2. **IPVS**:
   - Better performance at scale
   - True load balancing algorithms
   - More efficient

3. **userspace** (deprecated):
   - Legacy mode
   - Slower performance

**Service Implementation**:
```
Client Pod → kube-proxy rules → Service VIP → Backend Pods
```

**Debugging**:
```bash
# Check kube-proxy logs
kubectl logs -n kube-system -l k8s-app=kube-proxy

# View iptables rules
iptables-save | grep <service-name>

# Test service connectivity
kubectl run test --rm -i --tty --image=busybox -- wget -O- http://<service>:port
```

## Pod Lifecycle

### Pod Creation Flow

```
1. User submits Pod to API Server
        ↓
2. API Server writes to etcd
        ↓
3. Scheduler watches for unscheduled Pods
        ↓
4. Scheduler assigns Pod to Node
        ↓
5. Kubelet on Node watches for new Pods
        ↓
6. Kubelet tells container runtime to pull image
        ↓
7. Container runtime pulls image
        ↓
8. Container runtime creates container
        ↓
9. Kubelet reports status to API Server
        ↓
10. API Server updates etcd
```

### Init Containers

**Purpose**: Run before app containers

**Use Cases**:
- Wait for dependencies
- Register with external services
- Clone repositories
- Generate configuration

**Example**:
```yaml
apiVersion: v1
kind: Pod
metadata:
  name: myapp
spec:
  initContainers:
  - name: init-db
    image: busybox
    command: ['sh', '-c', 'until nslookup db-service; do sleep 2; done']
  containers:
  - name: app
    image: myapp:1.0
```

### Container Probes

#### Liveness Probe
- Detects if container is alive
- Restarts container if fails

#### Readiness Probe
- Detects if container is ready to serve traffic
- Removes from Service endpoints if fails

#### Startup Probe
- Protects slow-starting containers
- Disables liveness/readiness until passes

**Example**:
```yaml
livenessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 30
  periodSeconds: 10

readinessProbe:
  httpGet:
    path: /ready
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 5
```

## Networking Model

### Kubernetes Networking Requirements

1. **All Pods can communicate** with all other Pods without NAT
2. **All Nodes can communicate** with all Pods without NAT
3. **IP seen by Pod** is same as IP seen by others

### Pod Networking

```
┌──────────────────────────────────────┐
│           Node                       │
│  ┌────────────┐    ┌────────────┐  │
│  │   Pod 1    │    │   Pod 2    │  │
│  │ 10.244.1.2 │    │ 10.244.1.3 │  │
│  └─────┬──────┘    └─────┬──────┘  │
│        │                 │          │
│        └────────┬────────┘          │
│                 │                   │
│          ┌──────▼──────┐            │
│          │   veth      │            │
│          │   bridge    │            │
│          └──────┬──────┘            │
│                 │                   │
│          ┌──────▼──────┐            │
│          │   Node NIC  │            │
│          │ 192.168.1.10│            │
│          └─────────────┘            │
└──────────────────────────────────────┘
```

### Service Types

1. **ClusterIP** (default):
   - Internal cluster IP
   - Only accessible within cluster

2. **NodePort**:
   - Exposes on each Node's IP at static port
   - Accessible from outside cluster
   - Port range: 30000-32767

3. **LoadBalancer**:
   - External load balancer (cloud provider)
   - Assigns external IP

4. **ExternalName**:
   - Maps to DNS name
   - No proxying

## Storage Architecture

### Volume Types

1. **emptyDir**: Temporary, Pod-scoped
2. **hostPath**: Node's filesystem (use with caution)
3. **PersistentVolume**: Cluster-level storage
4. **ConfigMap**: Configuration data
5. **Secret**: Sensitive data

### PersistentVolume vs PersistentVolumeClaim

```
Administrator creates PV → User requests storage via PVC → Kubernetes binds PVC to PV
```

## Summary

Key architectural concepts:

1. **Control plane** manages cluster state
2. **Worker nodes** run application workloads
3. **API server** is central communication hub
4. **etcd** stores all cluster state
5. **Scheduler** places Pods on Nodes
6. **Controllers** maintain desired state
7. **Kubelet** manages containers on nodes
8. **kube-proxy** manages networking

Understanding architecture is essential for troubleshooting!
