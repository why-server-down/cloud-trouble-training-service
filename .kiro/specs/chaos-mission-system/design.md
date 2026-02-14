# Chaos Mission System - Design Document

## 1. System Architecture

### 1.1 High-Level Architecture
```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Frontend  │─────▶│   Backend    │─────▶│ Kubernetes  │
│ (Mission UI)│◀─────│  (FastAPI)   │◀─────│   Cluster   │
└─────────────┘      └──────────────┘      └─────────────┘
                            │
                            ├─────▶ ┌─────────────┐
                            │       │ Chaos Mesh  │
                            │       │   Engine    │
                            │       └─────────────┘
                            │
                            ├─────▶ ┌─────────────┐
                            │       │ Prometheus  │
                            │       │  (Metrics)  │
                            │       └─────────────┘
                            │
                            └─────▶ ┌─────────────┐
                                    │  Database   │
                                    │ (Postgres)  │
                                    └─────────────┘
```

### 1.2 Component Breakdown

**Backend Services:**
- MissionManager: 미션 생성 및 관리
- ChaosInjector: Chaos Mesh 제어
- ValidationService: 미션 완료 검증
- ScoringService: 점수 계산
- NamespaceManager: 사용자별 네임스페이스 관리

## 2. Data Models

### 2.1 Database Schema

```python
class Mission(Base):
    id: UUID
    name: str
    level: int
    description: str
    chaos_type: str  # 'pod_failure', 'memory_stress', 'network_latency', 'service_config'
    chaos_spec: JSON
    validation_query: str  # Prometheus query
    base_score: int
    time_limit: int  # seconds
    
class MissionAttempt(Base):
    id: UUID
    user_id: UUID
    mission_id: UUID
    namespace: str
    status: str  # 'in_progress', 'completed', 'failed', 'abandoned'
    start_time: datetime
    end_time: datetime
    final_score: int
    hints_used: int
    
class MissionProgress(Base):
    id: UUID
    attempt_id: UUID
    timestamp: datetime
    validation_result: bool
    current_score: int
    notes: str
```

## 3. Mission Scenarios

### 3.1 Level 1: Pod Failure (ImagePullBackOff)

```yaml
# Mission Config
name: "사라진 웹페이지"
chaos_type: "pod_failure"
base_score: 100
time_limit: 1200  # 20 minutes

# Initial Deployment (with typo)
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web-app
spec:
  replicas: 1
  template:
    spec:
      containers:
      - name: nginx
        image: ngin:latest  # Typo: should be 'nginx'
        
# Validation Query
up{job="web-app"} == 1
```

### 3.2 Level 2: Memory Stress (OOMKilled)

```yaml
# Mission Config
name: "터져버린 쇼핑몰"
chaos_type: "memory_stress"
base_score: 100
time_limit: 1500  # 25 minutes

# Chaos Mesh Spec
apiVersion: chaos-mesh.org/v1alpha1
kind: StressChaos
metadata:
  name: memory-stress
spec:
  mode: one
  selector:
    namespaces:
      - user-{user_id}
    labelSelectors:
      app: shopping-app
  stressors:
    memory:
      workers: 1
      size: 512MB
      
# Validation Query
container_memory_usage_bytes < container_spec_memory_limit_bytes
```

### 3.3 Level 3: Service Misconfiguration

```yaml
# Mission Config
name: "끊어진 연결고리"
chaos_type: "service_config"
base_score: 100
time_limit: 1800  # 30 minutes

# Service with wrong selector
apiVersion: v1
kind: Service
metadata:
  name: backend-service
spec:
  selector:
    app: backend-wrong  # Should be 'backend'
  ports:
  - port: 8080
    
# Validation Query
http_requests_total{code="200", service="backend"} > 0
```

### 3.4 Level 4: Network Latency

```yaml
# Mission Config
name: "좀비 서버의 습격"
chaos_type: "network_latency"
base_score: 100
time_limit: 2100  # 35 minutes

# Chaos Mesh Spec
apiVersion: chaos-mesh.org/v1alpha1
kind: NetworkChaos
metadata:
  name: network-delay
spec:
  action: delay
  mode: one
  selector:
    namespaces:
      - user-{user_id}
  delay:
    latency: "2s"
    
# Validation Query
probe_success{probe_type="liveness"} == 1
```

## 4. Core Algorithms

### 4.1 Mission Initialization

```python
class MissionManager:
    async def initialize_mission(
        self, 
        user_id: str, 
        mission_id: str
    ) -> MissionAttempt:
        """
        Initializes mission environment
        Timeout: 30 seconds
        """
        mission = await self.get_mission(mission_id)
        namespace = f"user-{user_id}"
        
        # Create namespace if not exists
        await self.namespace_manager.ensure_namespace(namespace)
        
        # Apply initial K8s resources
        await self.apply_mission_resources(mission, namespace)
        
        # Wait for resources to be ready
        await self.wait_for_ready(namespace, timeout=30)
        
        # Create attempt record
        attempt = MissionAttempt(
            user_id=user_id,
            mission_id=mission_id,
            namespace=namespace,
            status='in_progress',
            start_time=datetime.now(),
            final_score=mission.base_score
        )
        await self.db.save(attempt)
        
        # Schedule chaos injection (10 seconds delay)
        asyncio.create_task(
            self.schedule_chaos_injection(attempt.id, delay=10)
        )
        
        return attempt
```

### 4.2 Chaos Injection

```python
class ChaosInjector:
    async def inject_chaos(
        self, 
        attempt_id: str
    ) -> bool:
        """
        Injects chaos based on mission type
        """
        attempt = await self.get_attempt(attempt_id)
        mission = await self.get_mission(attempt.mission_id)
        
        chaos_spec = self.build_chaos_spec(
            mission.chaos_type,
            mission.chaos_spec,
            attempt.namespace
        )
        
        try:
            # Apply Chaos Mesh resource
            await self.chaos_client.create_namespaced_custom_object(
                group="chaos-mesh.org",
                version="v1alpha1",
                namespace=attempt.namespace,
                plural=self.get_chaos_plural(mission.chaos_type),
                body=chaos_spec
            )
            
            logger.info(f"Chaos injected for attempt {attempt_id}")
            return True
            
        except Exception as e:
            logger.error(f"Chaos injection failed: {e}")
            # Retry mission initialization
            await self.mission_manager.restart_mission(attempt_id)
            return False
    
    def build_chaos_spec(
        self, 
        chaos_type: str, 
        spec: dict, 
        namespace: str
    ) -> dict:
        """
        Builds Chaos Mesh spec from template
        """
        base_spec = {
            "apiVersion": "chaos-mesh.org/v1alpha1",
            "kind": self.get_chaos_kind(chaos_type),
            "metadata": {
                "name": f"chaos-{chaos_type}",
                "namespace": namespace
            },
            "spec": {
                **spec,
                "selector": {
                    "namespaces": [namespace]
                }
            }
        }
        return base_spec
```

### 4.3 Mission Validation

```python
class ValidationService:
    def __init__(self):
        self.prometheus_client = PrometheusClient()
    
    async def start_validation_loop(self, attempt_id: str):
        """
        Continuously validates mission completion
        Runs every 5 seconds
        """
        while True:
            attempt = await self.get_attempt(attempt_id)
            
            if attempt.status != 'in_progress':
                break
            
            # Check if mission is completed
            is_complete = await self.validate_mission(attempt)
            
            if is_complete:
                await self.complete_mission(attempt)
                break
            
            await asyncio.sleep(5)
    
    async def validate_mission(self, attempt: MissionAttempt) -> bool:
        """
        Validates mission using Prometheus query
        """
        mission = await self.get_mission(attempt.mission_id)
        
        # Execute Prometheus query
        query = mission.validation_query.replace(
            "{namespace}", attempt.namespace
        )
        
        result = await self.prometheus_client.query(query)
        
        # Log validation result
        await self.log_validation(attempt.id, result)
        
        return self.evaluate_result(result)
    
    def evaluate_result(self, result: dict) -> bool:
        """
        Evaluates Prometheus query result
        """
        if not result.get('data', {}).get('result'):
            return False
        
        # Check if any result value is truthy
        for item in result['data']['result']:
            value = float(item['value'][1])
            if value > 0:
                return True
        
        return False
```

### 4.4 Scoring System

```python
class ScoringService:
    TIME_PENALTY_PER_MINUTE = 2
    MIN_SCORE = 20
    
    async def calculate_score(self, attempt: MissionAttempt) -> int:
        """
        Calculates final score based on time and hints
        """
        mission = await self.get_mission(attempt.mission_id)
        
        # Start with base score
        score = mission.base_score
        
        # Time penalty
        elapsed_minutes = (attempt.end_time - attempt.start_time).seconds // 60
        time_penalty = elapsed_minutes * self.TIME_PENALTY_PER_MINUTE
        score -= time_penalty
        
        # Hint penalty
        hint_penalties = await self.get_hint_penalties(attempt.id)
        score -= sum(hint_penalties)
        
        # Ensure minimum score
        score = max(score, self.MIN_SCORE)
        
        return score
    
    async def update_realtime_score(self, attempt_id: str):
        """
        Updates score in real-time (called every minute)
        """
        attempt = await self.get_attempt(attempt_id)
        
        if attempt.status != 'in_progress':
            return
        
        # Calculate current score
        current_score = await self.calculate_score(attempt)
        
        # Update attempt
        attempt.final_score = current_score
        await self.db.save(attempt)
        
        # Notify frontend via WebSocket
        await self.notify_score_update(attempt.user_id, current_score)
```

## 5. API Endpoints

```python
@router.post("/api/missions/{mission_id}/start")
async def start_mission(
    mission_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Starts a new mission attempt
    """
    # Check if user has active attempt
    active_attempt = await mission_manager.get_active_attempt(current_user.id)
    if active_attempt:
        raise HTTPException(400, "You already have an active mission")
    
    # Initialize mission
    attempt = await mission_manager.initialize_mission(
        current_user.id, 
        mission_id
    )
    
    # Start validation loop
    asyncio.create_task(validation_service.start_validation_loop(attempt.id))
    
    # Start score update loop
    asyncio.create_task(scoring_service.start_score_update_loop(attempt.id))
    
    return MissionStartResponse(
        attempt_id=attempt.id,
        namespace=attempt.namespace,
        mission=await mission_manager.get_mission(mission_id)
    )

@router.post("/api/missions/attempts/{attempt_id}/abandon")
async def abandon_mission(
    attempt_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Abandons current mission
    """
    attempt = await mission_manager.get_attempt(attempt_id)
    
    if attempt.user_id != current_user.id:
        raise HTTPException(403, "Not your mission")
    
    attempt.status = 'abandoned'
    attempt.end_time = datetime.now()
    attempt.final_score = 0
    await db.save(attempt)
    
    # Cleanup resources
    await namespace_manager.cleanup_namespace(attempt.namespace)
    
    return {"message": "Mission abandoned"}

@router.get("/api/missions/attempts/{attempt_id}/status")
async def get_mission_status(
    attempt_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Gets current mission status
    """
    attempt = await mission_manager.get_attempt(attempt_id)
    
    return MissionStatusResponse(
        status=attempt.status,
        current_score=attempt.final_score,
        elapsed_time=(datetime.now() - attempt.start_time).seconds,
        hints_used=attempt.hints_used
    )
```

## 6. Performance & Scalability

### 6.1 Resource Quotas

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: user-quota
  namespace: user-{user_id}
spec:
  hard:
    requests.cpu: "2"
    requests.memory: 2Gi
    limits.cpu: "4"
    limits.memory: 4Gi
    pods: "10"
```

### 6.2 Namespace Cleanup

```python
async def cleanup_expired_namespaces():
    """
    Cleans up namespaces from abandoned missions
    Runs every hour
    """
    expired_attempts = await db.query(
        MissionAttempt
    ).filter(
        MissionAttempt.status.in_(['completed', 'abandoned']),
        MissionAttempt.end_time < datetime.now() - timedelta(hours=1)
    ).all()
    
    for attempt in expired_attempts:
        await namespace_manager.delete_namespace(attempt.namespace)
```

## 7. Testing Strategy

### 7.1 Property-Based Tests
- Property: Mission initialization completes within 30 seconds
- Property: Chaos injection occurs exactly 10 seconds after start
- Property: Validation runs every 5 seconds ± 1 second
- Property: Final score is always >= MIN_SCORE

## 8. Deployment

```yaml
# backend/app/config/missions.yaml
missions:
  - id: "level-1-pod-failure"
    name: "사라진 웹페이지"
    level: 1
    chaos_type: "pod_failure"
    validation_query: 'up{job="web-app",namespace="{namespace}"} == 1'
    base_score: 100
    time_limit: 1200
```
