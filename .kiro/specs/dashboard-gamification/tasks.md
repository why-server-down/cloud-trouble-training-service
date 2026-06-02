# Dashboard & Gamification System - Tasks

## Current Implementation Status

### Implemented
- [x] Calculate dashboard statistics from existing `mission_attempts` records
- [x] Calculate normalized skill scores for troubleshooting, resources, network, and operations
- [x] Calculate Bronze, Silver, Gold, Platinum, and DevOps Master tiers with progress
- [x] Return completion-time learning curve data
- [x] Return all-time leaderboard data and highlight the current user
- [x] Evaluate first recovery, no-hints, speed-runner, and retry achievements
- [x] Expose dashboard stats, learning curve, leaderboard, and achievement APIs
- [x] Render tier progress, SVG skill radar, learning curve, Top 10 leaderboard, and achievements
- [x] Refresh the learning dashboard every 15 seconds
- [x] Show the learning dashboard in the main workspace when no mission is active
- [x] Show Grafana observability panels in the same workspace slot while a mission is active
- [x] Add tier boundary and progress tests

### Remaining Work
- [ ] Persist `UserStats`, `MissionCompletion`, `Achievement`, `UserAchievement`, and `LeaderboardEntry` tables
- [ ] Add Alembic migrations and indexes for persisted statistics
- [ ] Add Redis caching for leaderboard queries
- [ ] Add weekly and monthly leaderboard periods
- [ ] Persist achievement unlock events and apply bonus points to the user score
- [ ] Add tier-upgrade and achievement-unlock notifications
- [ ] Replace 15-second polling with WebSocket score updates
- [ ] Add score deduction and completion celebration animations
- [ ] Add learning-curve hint bars, tooltips, percentile rank, and improvement percentages
- [ ] Add skill-radar tooltips and related-mission drill-down
- [ ] Add leaderboard period selector and Top 100 pagination
- [ ] Add frontend component tests, API integration tests, and property-based tests

> The sections below preserve the original implementation checklist. Completed items above describe the current usable first version; unchecked items below remain the target architecture where they are more detailed.

## Phase 1: Database Setup

### Task 1: Database Schema Implementation
- [ ] 1.1 Create UserStats table
- [ ] 1.2 Create MissionCompletion table
- [ ] 1.3 Create Achievement table
- [ ] 1.4 Create UserAchievement table
- [ ] 1.5 Create LeaderboardEntry table
- [ ] 1.6 Add indexes
- [ ] 1.7 Create migration scripts

### Task 2: Redis Setup for Caching
- [ ] 2.1 Install Redis
- [ ] 2.2 Configure Redis client
- [ ] 2.3 Test Redis connection
- [ ] 2.4 Set up cache key patterns
- [ ] 2.5 Test cache operations

## Phase 2: Analytics Service

### Task 3: Skill Score Calculation
- [ ] 3.1 Create AnalyticsService class
- [ ] 3.2 Define skill categories mapping
- [ ] 3.3 Implement skill score calculation
- [ ] 3.4 Implement score normalization
- [ ] 3.5 Test skill calculations

### Task 4: Learning Curve Analysis
- [ ] 4.1 Create LearningCurveAnalyzer class
- [ ] 4.2 Implement progress analysis
- [ ] 4.3 Calculate improvement metrics
- [ ] 4.4 Calculate percentile ranking
- [ ] 4.5 Test learning curve data

### Task 5: User Statistics Tracking
- [ ] 5.1 Implement stats update on mission completion
- [ ] 5.2 Track total score
- [ ] 5.3 Track missions completed
- [ ] 5.4 Track total time spent
- [ ] 5.5 Track hints used

## Phase 3: Tier System

### Task 6: Tier Service Implementation
- [ ] 6.1 Create TierService class
- [ ] 6.2 Define tier thresholds
- [ ] 6.3 Implement tier calculation
- [ ] 6.4 Calculate tier progress
- [ ] 6.5 Test tier calculations

### Task 7: Tier Upgrade Detection
- [ ] 7.1 Implement tier upgrade check
- [ ] 7.2 Create upgrade notification
- [ ] 7.3 Award tier badge
- [ ] 7.4 Update user profile
- [ ] 7.5 Test tier upgrades

## Phase 4: Leaderboard System

### Task 8: Leaderboard Service
- [ ] 8.1 Create LeaderboardService class
- [ ] 8.2 Implement Redis sorted set for rankings
- [ ] 8.3 Implement leaderboard update
- [ ] 8.4 Implement rank retrieval
- [ ] 8.5 Test leaderboard operations

### Task 9: Leaderboard Periods
- [ ] 9.1 Implement all-time leaderboard
- [ ] 9.2 Implement weekly leaderboard
- [ ] 9.3 Implement monthly leaderboard
- [ ] 9.4 Schedule periodic resets
- [ ] 9.5 Test period calculations

### Task 10: Leaderboard Caching
- [ ] 10.1 Cache top 100 users
- [ ] 10.2 Implement 5-minute refresh
- [ ] 10.3 Fallback to database
- [ ] 10.4 Test cache performance
- [ ] 10.5 Monitor cache hit rate

## Phase 5: Achievement System

### Task 11: Achievement Definitions
- [ ] 11.1 Define achievement data structure
- [ ] 11.2 Create achievement seed data
- [ ] 11.3 Implement hidden achievements
- [ ] 11.4 Define point bonuses
- [ ] 11.5 Load achievements into database

### Task 12: Achievement Service
- [ ] 12.1 Create AchievementService class
- [ ] 12.2 Implement condition checking
- [ ] 12.3 Implement achievement unlock
- [ ] 12.4 Award bonus points
- [ ] 12.5 Test achievement logic

### Task 13: Achievement Types
- [ ] 13.1 Implement "mission_complete" type
- [ ] 13.2 Implement "speed" type
- [ ] 13.3 Implement "no_hints" type
- [ ] 13.4 Implement "retry" type
- [ ] 13.5 Test each achievement type

## Phase 6: Real-time Updates

### Task 14: WebSocket Setup
- [ ] 14.1 Create WebSocket endpoint
- [ ] 14.2 Implement connection management
- [ ] 14.3 Handle disconnections
- [ ] 14.4 Test WebSocket connections
- [ ] 14.5 Add error handling

### Task 15: Score Update Broadcasting
- [ ] 15.1 Broadcast score updates
- [ ] 15.2 Implement 1-second update interval
- [ ] 15.3 Send tier upgrade notifications
- [ ] 15.4 Send achievement unlocks
- [ ] 15.5 Test real-time updates

## Phase 7: API Endpoints

### Task 16: Dashboard Stats API
- [ ] 16.1 Create stats endpoint
- [ ] 16.2 Return user statistics
- [ ] 16.3 Return skill scores
- [ ] 16.4 Return current tier
- [ ] 16.5 Test stats endpoint

### Task 17: Learning Curve API
- [ ] 17.1 Create learning curve endpoint
- [ ] 17.2 Return attempt history
- [ ] 17.3 Return improvement metrics
- [ ] 17.4 Return percentile rank
- [ ] 17.5 Test learning curve endpoint

### Task 18: Leaderboard API
- [ ] 18.1 Create leaderboard endpoint
- [ ] 18.2 Support period parameter
- [ ] 18.3 Support limit parameter
- [ ] 18.4 Return user's rank
- [ ] 18.5 Test leaderboard endpoint

### Task 19: Achievement API
- [ ] 19.1 Create achievements endpoint
- [ ] 19.2 Return unlocked achievements
- [ ] 19.3 Return all achievements
- [ ] 19.4 Calculate progress percentage
- [ ] 19.5 Test achievement endpoint

## Phase 8: Frontend Components

### Task 20: Score Display Component
- [ ] 20.1 Create ScoreDisplay component
- [ ] 20.2 Show current score
- [ ] 20.3 Animate score changes
- [ ] 20.4 Connect to WebSocket
- [ ] 20.5 Test score display

### Task 21: Skill Radar Chart
- [ ] 21.1 Install Chart.js or Recharts
- [ ] 21.2 Create SkillRadarChart component
- [ ] 21.3 Render radar chart
- [ ] 21.4 Add tooltips
- [ ] 21.5 Test chart rendering

### Task 22: Learning Curve Graph
- [ ] 22.1 Create LearningCurveGraph component
- [ ] 22.2 Render time trend line
- [ ] 22.3 Render hint trend bars
- [ ] 22.4 Add interactive tooltips
- [ ] 22.5 Test graph rendering

### Task 23: Tier Badge Component
- [ ] 23.1 Create TierBadge component
- [ ] 23.2 Display tier icon
- [ ] 23.3 Show progress bar
- [ ] 23.4 Add tier upgrade animation
- [ ] 23.5 Test tier display

### Task 24: Leaderboard Component
- [ ] 24.1 Create Leaderboard component
- [ ] 24.2 Display top 100 users
- [ ] 24.3 Highlight current user
- [ ] 24.4 Add period selector
- [ ] 24.5 Test leaderboard UI

### Task 25: Achievement Panel
- [ ] 25.1 Create AchievementPanel component
- [ ] 25.2 Display unlocked achievements
- [ ] 25.3 Show locked achievements
- [ ] 25.4 Add unlock animation
- [ ] 25.5 Test achievement display

## Phase 9: Testing

### Task 26: Unit Testing
- [ ] 26.1 Test skill score calculation
- [ ] 26.2 Test tier calculation
- [ ] 26.3 Test leaderboard operations
- [ ] 26.4 Test achievement checking
- [ ] 26.5 Test learning curve analysis

### Task 27: Integration Testing
- [ ] 27.1 Test complete dashboard flow
- [ ] 27.2 Test tier upgrade flow
- [ ] 27.3 Test achievement unlock flow
- [ ] 27.4 Test leaderboard updates
- [ ] 27.5 Test WebSocket updates

### Task 28: Property-Based Testing
- [ ] 28.1 Write PBT: Skill scores 0-100
- [ ] 28.2 Write PBT: Tier progress 0-100
- [ ] 28.3 Write PBT: Leaderboard ranks sequential
- [ ] 28.4 Write PBT: Achievement unlock idempotent
- [ ] 28.5 Run all property tests
