# User Authentication & Profile System - Requirements

## Overview
사용자 인증 및 프로필 관리 시스템으로, 학습 진행 상황과 개인 정보를 안전하게 관리합니다.

## User Stories

### 1. User Registration (회원가입)
**As a** 신규 사용자  
**I want** 간단하게 회원가입하기를  
**So that** 학습을 시작하고 진행 상황을 저장할 수 있다

**Acceptance Criteria:**
- 1.1 이메일과 비밀번호로 회원가입할 수 있다
- 1.2 비밀번호는 최소 8자 이상, 영문/숫자/특수문자 포함이어야 한다
- 1.3 이메일 중복 체크를 수행한다
- 1.4 회원가입 시 자동으로 K8s 네임스페이스가 생성된다
- 1.5 가입 완료 후 자동으로 로그인된다

### 2. User Login (로그인)
**As a** 기존 사용자  
**I want** 로그인하여 내 학습 환경에 접속하기를  
**So that** 이전에 진행하던 학습을 이어서 할 수 있다

**Acceptance Criteria:**
- 2.1 이메일과 비밀번호로 로그인할 수 있다
- 2.2 로그인 성공 시 JWT 토큰이 발급된다
- 2.3 토큰은 24시간 동안 유효하다
- 2.4 로그인 실패 시 명확한 에러 메시지를 표시한다
- 2.5 5회 연속 실패 시 10분간 계정이 잠긴다

### 3. Profile Management (프로필 관리)
**As a** 사용자  
**I want** 내 프로필 정보를 수정하기를  
**So that** 최신 정보를 유지할 수 있다

**Acceptance Criteria:**
- 3.1 닉네임, 프로필 이미지를 수정할 수 있다
- 3.2 비밀번호 변경 시 현재 비밀번호 확인이 필요하다
- 3.3 프로필에 현재 티어와 누적 점수가 표시된다
- 3.4 완료한 미션 목록과 업적을 확인할 수 있다
- 3.5 프로필 수정 사항은 즉시 반영된다

### 4. Session Management (세션 관리)
**As a** 시스템  
**I want** 사용자 세션을 안전하게 관리하기를  
**So that** 보안을 유지하고 동시 접속을 제어할 수 있다

**Acceptance Criteria:**
- 4.1 JWT 토큰으로 인증 상태를 관리한다
- 4.2 토큰 만료 시 자동으로 로그아웃된다
- 4.3 로그아웃 시 토큰이 무효화된다
- 4.4 동일 계정으로 중복 로그인이 가능하다
- 4.5 30분간 활동이 없으면 자동 로그아웃된다

## Technical Requirements

### Security
- 비밀번호는 bcrypt로 해싱하여 저장
- JWT 토큰은 환경 변수의 시크릿 키로 서명
- HTTPS 통신 강제
- SQL Injection 방지

### Database
- 사용자 정보 테이블 (id, email, password_hash, nickname, created_at)
- 프로필 테이블 (user_id, tier, total_score, profile_image_url)
- 세션 테이블 (user_id, token, expires_at)

### Performance
- 로그인 응답 시간: 1초 이내
- 토큰 검증: 100ms 이내
- 동시 로그인 사용자: 최소 100명
