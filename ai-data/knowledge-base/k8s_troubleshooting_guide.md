# Kubernetes Troubleshooting Guide

## Pod Troubleshooting

### ImagePullBackOff Error
**Symptom**: Pod status shows `ImagePullBackOff` or `ErrImagePull`

**Common Causes**:
- Image name is incorrect or misspelled
- Image tag doesn't exist
- Private registry authentication failed
- Network issues preventing image pull

**Diagnostic Commands**:
```bash
kubectl describe pod <pod-name>
kubectl get events --sort-by='.lastTimestamp'
```

**Solutions**:
1. Verify image name and tag in pod spec
2. Check image exists in registry
3. Verify imagePullSecrets if using private registry
4. Check network connectivity to registry

---

### CrashLoopBackOff Error
**Symptom**: Pod status shows `CrashLoopBackOff`

**Common Causes**:
- Application crashes immediately after starting
- Missing environment variables or configuration
- Port conflicts
- Resource limits too restrictive

**Diagnostic Commands**:
```bash
kubectl logs <pod-name>
kubectl logs <pod-name> --previous
kubectl describe pod <pod-name>
```

**Solutions**:
1. Check application logs for error messages
2. Verify all required environment variables are set
3. Check resource requests and limits
4. Verify application configuration

---

### Pending Status
**Symptom**: Pod remains in `Pending` state

**Common Causes**:
- Insufficient cluster resources (CPU/Memory)
- No nodes match pod's node selector
- PersistentVolumeClaim not bound
- Taints and tolerations mismatch

**Diagnostic Commands**:
```bash
kubectl describe pod <pod-name>
kubectl get nodes
kubectl top nodes
```

**Solutions**:
1. Check node resources availability
2. Verify node selectors and affinity rules
3. Check PVC status if using volumes
4. Review taints and tolerations

---

## Service Troubleshooting

### Service Not Accessible
**Symptom**: Cannot access service from within or outside cluster

**Diagnostic Commands**:
```bash
kubectl get svc
kubectl describe svc <service-name>
kubectl get endpoints <service-name>
```

**Common Issues**:
- Selector doesn't match pod labels
- Service port doesn't match container port
- Network policies blocking traffic

---

## ConfigMap and Secret Issues

### Configuration Not Loading
**Diagnostic Commands**:
```bash
kubectl get configmap <name> -o yaml
kubectl get secret <name> -o yaml
kubectl describe pod <pod-name>
```

**Common Issues**:
- ConfigMap/Secret not mounted correctly
- Wrong key names in volume mounts
- Pod not restarted after config update

