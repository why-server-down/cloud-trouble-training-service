# AfterFail - Mission Playbook

## Level 1: Basic Pod Issues

### Mission 1.1: ImagePullBackOff
**Scenario**: Pod cannot pull container image

**Expected Solution**:
```bash
# 1. Check pod status
kubectl get pods

# 2. Describe pod to see error
kubectl describe pod <pod-name>

# 3. Fix image name in deployment
kubectl edit deployment <deployment-name>
# or
kubectl set image deployment/<deployment-name> <container-name>=<correct-image>
```

**Common Mistakes**:
- Typo in image name
- Wrong image tag
- Missing registry URL

**Hint Progression**:
- Level 0: "Check the pod's status and events"
- Level 1: "Look at the image name in the pod specification"
- Level 2: "Use `kubectl describe pod` to see the exact error"
- Level 3: "The image name has a typo. Use `kubectl edit` to fix it"

---

### Mission 1.2: CrashLoopBackOff
**Scenario**: Application crashes immediately after starting

**Expected Solution**:
```bash
# 1. Check logs
kubectl logs <pod-name>

# 2. Check previous container logs
kubectl logs <pod-name> --previous

# 3. Common fixes:
# - Add missing environment variable
# - Fix configuration
# - Adjust resource limits
```

**Hint Progression**:
- Level 0: "What do the application logs tell you?"
- Level 1: "Check if all required environment variables are set"
- Level 2: "Use `kubectl logs` to see why the app is crashing"
- Level 3: "Add the missing DATABASE_URL environment variable"

---

## Level 2: Service and Networking

### Mission 2.1: Service Not Reachable
**Scenario**: Service exists but pods cannot communicate

**Expected Solution**:
```bash
# 1. Check service endpoints
kubectl get endpoints <service-name>

# 2. Verify service selector matches pod labels
kubectl describe svc <service-name>
kubectl get pods --show-labels

# 3. Fix selector in service
kubectl edit svc <service-name>
```

**Hint Progression**:
- Level 0: "How does a Service find its Pods?"
- Level 1: "Compare the Service selector with Pod labels"
- Level 2: "Use `kubectl get endpoints` to see if pods are registered"
- Level 3: "The selector label is wrong. Change `app=fronted` to `app=frontend`"

---

## Level 3: Configuration Issues

### Mission 3.1: ConfigMap Not Loading
**Scenario**: Application cannot read configuration

**Expected Solution**:
```bash
# 1. Check if ConfigMap exists
kubectl get configmap

# 2. Verify ConfigMap is mounted
kubectl describe pod <pod-name>

# 3. Check volume mount path
# Fix in deployment spec if needed
```

---

## Level 4: Resource Management

### Mission 4.1: Pod Evicted Due to Resources
**Scenario**: Pods being evicted due to resource pressure

**Expected Solution**:
```bash
# 1. Check node resources
kubectl top nodes
kubectl describe node <node-name>

# 2. Check pod resource requests/limits
kubectl describe pod <pod-name>

# 3. Adjust resource requests
kubectl edit deployment <deployment-name>
```

**Hint Progression**:
- Level 0: "What happens when a node runs out of resources?"
- Level 1: "Check the node's available memory and CPU"
- Level 2: "Use `kubectl top nodes` and compare with pod requests"
- Level 3: "Reduce memory request from 2Gi to 512Mi"

