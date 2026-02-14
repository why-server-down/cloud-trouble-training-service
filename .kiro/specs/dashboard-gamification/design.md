# Dashboard & Gamification System - Design Document

## 1. System Architecture

### 1.1 High-Level Architecture
```
┌─────────────┐      ┌──────────────┐      ┌─────────────┐
│   Frontend  │─────▶│   Backend    │─────▶│  Database   │
│ (Dashboard) │◀─────│  (FastAPI)   │◀─────│ (Postgres)  │
└─────────────┘      └──────────────┘      └─────────────┘
       │                     │
       │                     │
       └────WebSocket────────┘
         (Real-time updates)
```

### 1.2 Component Breakdown

**Frontend Components:**
- ScoreDisplay: 실시간 점수 표시
- SkillRadarChart: 역량 레이더 차트
- LearningCurveGraph: 성장 곡선 그래프
- TierBadge: 티어 배지 및 진행률
- Leaderboard: 순위표
- AchievementPanel: 업적 목록

**Backend Services:**
- AnalyticsService: 학습 데이터 분석
- LeaderboardService: 순위 계산 및 캐싱
- AchievementService: 업적 검증 및 부여
- TierService: 티어 계산 및 승급

## 2. Data Models

### 2.1 Database Schema

```python
class UserStats(Base):
    user_id: UUID
    total_score: int
    missions_completed: int
    total_time_spent: int  # seconds
    hints_used: int
    current_tier: str
    skill_scores: JSON  # {troubleshooting: 80, resource: 60, network: 70, ops: 50}
    
class MissionCompletion(Base):
    id: UUID
    user_id: UUID
    mission_id: UUID
    attempt_number: int
    completion_time: int  # seconds
    score: int
    hints_used: int
    completed_at: datetime
    
class Achievement(Base):
    id: UUID
    name: str
    description: str
    icon: str
    condition_type: str  # 'mission_complete', 'speed', 'no_hints', 'retry'
    condition_value: JSON
    points_bonus: int
    is_hidden: bool
    
class UserAchievement(Base):
    user_id: UUID
    achievement_id: UUID
    unlocked_at: datetime
    
class LeaderboardEntry(Base):
    user_id: UUID
    rank: int
    total_score: int
    period: str  # 'all_time', 'weekly', 'monthly'
    updated_at: datetime
```

## 3. Core Algorithms

### 3.1 Skill Score Calculation

```python
class AnalyticsService:
    SKILL_CATEGORIES = {
        'troubleshooting': ['level-1-pod-failure', 'level-2-memory-stress'],
        'resource': ['level-2-memory-stress'],
        'network': ['level-3-service-config', 'level-4-network-latency'],
        'ops': ['level-4-network-latency']
    }
    
    async def calculate_skill_scores(self, user_id: str) -> Dict[str, float]:
        """
        Calculates skill scores based on completed missions
        Returns scores normalized to 0-100
        """
        completions = await self.get_user_completions(user_id)
        
        skill_scores = {skill: 0.0 for skill in self.SKILL_CATEGORIES}
        
        for skill, mission_ids in self.SKILL_CATEGORIES.items():
            relevant_completions = [
                c for c in completions 
                if c.mission_id in mission_ids
            ]
            
            if not relevant_completions:
                continue
            
            # Calculate average score for this skill
            avg_score = sum(c.score for c in relevant_completions) / len(relevant_completions)
            
            # Factor in number of completions (more = higher confidence)
            completion_factor = min(len(relevant_completions) / 3, 1.0)
            
            # Normalize to 0-100
            skill_scores[skill] = avg_score * completion_factor
        
        return skill_scores
```

### 3.2 Learning Curve Analysis

```python
class LearningCurveAnalyzer:
    async def analyze_progress(
        self, 
        user_id: str, 
        mission_id: str
    ) -> LearningCurveData:
        """
        Analyzes user's progress on a specific mission
        """
        attempts = await self.get_mission_attempts(user_id, mission_id)
        
        if not attempts:
            return None
        
        # Sort by attempt number
        attempts.sort(key=lambda a: a.attempt_number)
        
        # Extract time and hint trends
        time_trend = [a.completion_time for a in attempts]
        hint_trend = [a.hints_used for a in attempts]
        score_trend = [a.score for a in attempts]
        
        # Calculate improvement metrics
        time_improvement = self._calculate_improvement(time_trend)
        hint_reduction = self._calculate_improvement(hint_trend, inverse=True)
        
        # Calculate percentile rank
        all_times = await self.get_all_completion_times(mission_id)
        percentile = self._calculate_percentile(attempts[-1].completion_time, all_times)
        
        return LearningCurveData(
            attempts=len(attempts),
            time_trend=time_trend,
            hint_trend=hint_trend,
            score_trend=score_trend,
            time_improvement_pct=time_improvement,
            hint_reduction_pct=hint_reduction,
            percentile_rank=percentile
        )
    
    def _calculate_improvement(
        self, 
        values: List[float], 
        inverse: bool = False
    ) -> float:
        """
        Calculates improvement percentage
        inverse=True means lower is better (e.g., hints)
        """
        if len(values) < 2:
            return 0.0
        
        first = values[0]
        last = values[-1]
        
        if first == 0:
            return 0.0
        
        improvement = ((first - last) / first) * 100
        
        return improvement if not inverse else -improvement
```

### 3.3 Tier System

```python
class TierService:
    TIERS = [
        {'name': 'Bronze', 'min_score': 0, 'max_score': 200, 'color': '#CD7F32'},
        {'name': 'Silver', 'min_score': 201, 'max_score': 500, 'color': '#C0C0C0'},
        {'name': 'Gold', 'min_score': 501, 'max_score': 1000, 'color': '#FFD700'},
        {'name': 'Platinum', 'min_score': 1001, 'max_score': 2000, 'color': '#E5E4E2'},
        {'name': 'DevOps Master', 'min_score': 2001, 'max_score': float('inf'), 'color': '#B9F2FF'}
    ]
    
    async def calculate_tier(self, total_score: int) -> TierInfo:
        """
        Calculates user's tier based on total score
        """
        for tier in self.TIERS:
            if tier['min_score'] <= total_score <= tier['max_score']:
                # Calculate progress to next tier
                if tier['max_score'] == float('inf'):
                    progress = 100.0
                else:
                    range_size = tier['max_score'] - tier['min_score']
                    current_progress = total_score - tier['min_score']
                    progress = (current_progress / range_size) * 100
                
                return TierInfo(
                    name=tier['name'],
                    color=tier['color'],
                    min_score=tier['min_score'],
                    max_score=tier['max_score'],
                    progress=progress,
                    next_tier=self._get_next_tier(tier['name'])
                )
    
    async def check_tier_upgrade(
        self, 
        user_id: str, 
        old_score: int, 
        new_score: int
    ) -> Optional[TierUpgrade]:
        """
        Checks if user upgraded tier
        """
        old_tier = await self.calculate_tier(old_score)
        new_tier = await self.calculate_tier(new_score)
        
        if old_tier.name != new_tier.name:
            return TierUpgrade(
                old_tier=old_tier.name,
                new_tier=new_tier.name,
                unlocked_at=datetime.now()
            )
        
        return None
```

### 3.4 Leaderboard Management

```python
class LeaderboardService:
    async def update_leaderboard(
        self, 
        user_id: str, 
        new_score: int,
        period: str = 'all_time'
    ):
        """
        Updates leaderboard after score change
        Uses Redis for caching
        """
        # Update user's score in sorted set
        await self.redis.zadd(
            f"leaderboard:{period}",
            {user_id: new_score}
        )
        
        # Get user's new rank
        rank = await self.redis.zrevrank(f"leaderboard:{period}", user_id)
        
        # Update database (async)
        asyncio.create_task(
            self._update_leaderboard_db(user_id, rank + 1, new_score, period)
        )
        
        return rank + 1
    
    async def get_leaderboard(
        self, 
        period: str = 'all_time',
        limit: int = 100
    ) -> List[LeaderboardEntry]:
        """
        Gets top N users from leaderboard
        """
        # Try cache first
        cached = await self.redis.zrevrange(
            f"leaderboard:{period}",
            0, limit - 1,
            withscores=True
        )
        
        if cached:
            return [
                LeaderboardEntry(
                    user_id=user_id,
                    rank=idx + 1,
                    total_score=int(score)
                )
                for idx, (user_id, score) in enumerate(cached)
            ]
        
        # Fallback to database
        return await self._get_leaderboard_from_db(period, limit)
    
    async def get_user_rank(self, user_id: str, period: str = 'all_time') -> int:
        """
        Gets user's current rank
        """
        rank = await self.redis.zrevrank(f"leaderboard:{period}", user_id)
        return rank + 1 if rank is not None else None
```

### 3.5 Achievement System

```python
class AchievementService:
    async def check_achievements(
        self, 
        user_id: str, 
        event_type: str,
        event_data: dict
    ):
        """
        Checks if user unlocked any achievements
        """
        # Get all achievements for this event type
        achievements = await self.get_achievements_by_event(event_type)
        
        # Get user's unlocked achievements
        unlocked = await self.get_user_achievements(user_id)
        unlocked_ids = {a.achievement_id for a in unlocked}
        
        newly_unlocked = []
        
        for achievement in achievements:
            if achievement.id in unlocked_ids:
                continue
            
            # Check if condition is met
            if await self._check_condition(user_id, achievement, event_data):
                await self._unlock_achievement(user_id, achievement)
                newly_unlocked.append(achievement)
        
        return newly_unlocked
    
    async def _check_condition(
        self, 
        user_id: str,
        achievement: Achievement,
        event_data: dict
    ) -> bool:
        """
        Checks if achievement condition is met
        """
        condition_type = achievement.condition_type
        condition_value = achievement.condition_value
        
        if condition_type == 'mission_complete':
            # Check if specific mission completed
            return event_data.get('mission_id') == condition_value['mission_id']
        
        elif condition_type == 'speed':
            # Check if completed within time limit
            return event_data.get('completion_time') <= condition_value['max_time']
        
        elif condition_type == 'no_hints':
            # Check if completed without hints
            return event_data.get('hints_used') == 0
        
        elif condition_type == 'retry':
            # Check if completed after N retries
            attempts = await self.get_mission_attempts(
                user_id, 
                event_data.get('mission_id')
            )
            return len(attempts) >= condition_value['min_attempts']
        
        return False

# Achievement Definitions
ACHIEVEMENTS = [
    {
        'name': '완벽주의자',
        'description': '힌트 없이 미션 완료',
        'condition_type': 'no_hints',
        'condition_value': {},
        'points_bonus': 50,
        'is_hidden': False
    },
    {
        'name': '스피드러너',
        'description': '5분 이내에 미션 완료',
        'condition_type': 'speed',
        'condition_value': {'max_time': 300},
        'points_bonus': 30,
        'is_hidden': False
    },
    {
        'name': '불굴의 의지',
        'description': '10회 재도전 후 성공',
        'condition_type': 'retry',
        'condition_value': {'min_attempts': 10},
        'points_bonus': 100,
        'is_hidden': True
    }
]
```

## 4. API Endpoints

```python
@router.get("/api/dashboard/stats")
async def get_user_stats(current_user: User = Depends(get_current_user)):
    """
    Gets user's overall statistics
    """
    stats = await analytics_service.get_user_stats(current_user.id)
    skill_scores = await analytics_service.calculate_skill_scores(current_user.id)
    tier = await tier_service.calculate_tier(stats.total_score)
    
    return DashboardStats(
        total_score=stats.total_score,
        missions_completed=stats.missions_completed,
        current_tier=tier,
        skill_scores=skill_scores
    )

@router.get("/api/dashboard/learning-curve/{mission_id}")
async def get_learning_curve(
    mission_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Gets learning curve data for a mission
    """
    curve_data = await learning_curve_analyzer.analyze_progress(
        current_user.id,
        mission_id
    )
    return curve_data

@router.get("/api/leaderboard")
async def get_leaderboard(
    period: str = 'all_time',
    limit: int = 100
):
    """
    Gets leaderboard
    """
    entries = await leaderboard_service.get_leaderboard(period, limit)
    return entries

@router.get("/api/achievements")
async def get_achievements(current_user: User = Depends(get_current_user)):
    """
    Gets user's achievements
    """
    unlocked = await achievement_service.get_user_achievements(current_user.id)
    all_achievements = await achievement_service.get_all_achievements()
    
    return AchievementsResponse(
        unlocked=unlocked,
        total=len(all_achievements),
        progress=(len(unlocked) / len(all_achievements)) * 100
    )
```

## 5. Real-time Updates

```python
# WebSocket for real-time score updates
@router.websocket("/ws/dashboard/{user_id}")
async def dashboard_websocket(websocket: WebSocket, user_id: str):
    await websocket.accept()
    
    try:
        while True:
            # Send score updates every second
            stats = await analytics_service.get_user_stats(user_id)
            await websocket.send_json({
                'type': 'score_update',
                'score': stats.total_score
            })
            
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
```

## 6. Frontend Implementation

```typescript
// SkillRadarChart.tsx
import { Radar } from 'react-chartjs-2';

export function SkillRadarChart({ skillScores }: Props) {
  const data = {
    labels: ['트러블슈팅', '리소스 관리', '네트워크', '운영'],
    datasets: [{
      label: '내 역량',
      data: [
        skillScores.troubleshooting,
        skillScores.resource,
        skillScores.network,
        skillScores.ops
      ],
      backgroundColor: 'rgba(54, 162, 235, 0.2)',
      borderColor: 'rgb(54, 162, 235)',
    }]
  };
  
  return <Radar data={data} />;
}
```

## 7. Performance Optimizations

```python
# Cache leaderboard for 5 minutes
@cache(ttl=300)
async def get_leaderboard(period: str, limit: int):
    pass

# Batch achievement checks
async def check_achievements_batch(user_ids: List[str], event_type: str):
    pass

# Pre-calculate daily stats
@scheduled(cron="0 0 * * *")  # Daily at midnight
async def calculate_daily_stats():
    pass
```

## 8. Testing Strategy

### Property-Based Tests
- Property: Skill scores are always between 0-100
- Property: Tier progress is always between 0-100
- Property: Leaderboard ranks are sequential (1, 2, 3, ...)
- Property: Achievement unlock is idempotent
