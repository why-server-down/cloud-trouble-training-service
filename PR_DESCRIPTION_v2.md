# 웹 터미널 기능 개선 및 환경 설정 자동화

## 📋 요약
웹 터미널에 명령어 히스토리, 자동완성, 터미널 단축키 등 필수 기능을 추가하고, 환경변수 관리 및 테스트 환경 자동 구축 스크립트를 구현했습니다.

## ✨ 주요 변경사항

### 1. 터미널 기능 개선
- **명령어 히스토리** (↑/↓ 키)
  - 이전/다음 명령어 탐색
  - 히스토리 끝에서 빈 줄로 이동
  
- **명령어 자동완성** (Tab 키)
  - kubectl 명령어 자동완성
  - 여러 매칭 시 목록 표시
  - 단일 매칭 시 자동 완성
  
- **터미널 단축키**
  - Ctrl+C: 현재 입력 취소
  - Ctrl+L: 화면 지우기
  
- **네임스페이스 프롬프트**
  - 프롬프트에 네임스페이스 표시: `[user-e8e9ed5e-d...]$`
  - 헤더에도 네임스페이스 정보 표시

### 2. 환경변수 관리
- **하드코딩된 URL 제거**
  - API URL: `import.meta.env.VITE_API_BASE_URL`
  - WebSocket URL: `import.meta.env.VITE_WS_BASE_URL`
  
- **환경변수 파일**
  - `.env.development`: 개발 환경 설정
  - `.env.example`: 템플릿 파일
  - `vite-env.d.ts`: TypeScript 타입 정의
  
- **Docker 환경 대응**
  - 환경변수로 백엔드 서비스명 설정 가능
  - 로컬/Docker 환경 모두 지원

### 3. 테스트 환경 자동화
- **setup-test-env.sh** 스크립트 추가
  - Docker/Kubernetes 확인
  - PostgreSQL 자동 시작
  - 테스트 네임스페이스 생성
  - 테스트 Pod 생성 (nginx, busybox)
  - 백엔드/프론트엔드 환경 자동 설정

### 4. 출력 포맷 개선
- 터미널 출력 줄바꿈 정상화 (`\n` → `\r\n`)
- 프롬프트 중복 출력 제거
- 명령어 실행 후 자동 프롬프트 표시

## 🔧 기술 세부사항

### Frontend 변경사항
```
frontend/
├── src/
│   ├── components/Terminal/Terminal.tsx    # 히스토리, 자동완성, 단축키, 프롬프트
│   ├── hooks/useTerminalWebSocket.ts       # 환경변수, 프롬프트 처리
│   ├── services/api.ts                     # 환경변수 적용
│   ├── App.tsx                             # 네임스페이스 상태 관리
│   ├── components/Login/Login.tsx          # 네임스페이스 전달
│   └── vite-env.d.ts                       # 환경변수 타입 정의 (신규)
├── .env.development                        # 개발 환경 설정 (신규)
├── .env.example                            # 환경변수 템플릿 (신규)
├── .gitignore                              # .env 파일 제외
└── ENV_SETUP.md                            # 환경변수 가이드 (신규)
```

### Infrastructure
```
setup-test-env.sh                           # 테스트 환경 자동 구축 (신규)
```

## 🎯 구현된 요구사항

### web-terminal-interface/requirements.md 기준
- ✅ 1.2 명령어 자동완성 (kubectl)
- ✅ 1.3 명령어 히스토리 (↑/↓)
- ✅ 1.4 터미널 단축키 (Ctrl+C, Ctrl+L)
- ✅ 1.5 ANSI 색상 지원 (xterm.js 기본 지원)
- ✅ 3.4 네임스페이스 프롬프트 표시

## 🧪 테스트 방법

### 자동 설정 (추천)
```bash
chmod +x setup-test-env.sh
./setup-test-env.sh
```

### 수동 설정
```bash
# 1. 네임스페이스 생성
kubectl create namespace user-e8e9ed5e-d985-419b-ad6c-0db9eaa0978c
kubectl run nginx-pod --image=nginx -n user-e8e9ed5e-d985-419b-ad6c-0db9eaa0978c
kubectl run busybox-pod --image=busybox -n user-e8e9ed5e-d985-419b-ad6c-0db9eaa0978c -- sleep 3600

# 2. 백엔드 실행
cd backend
source venv/bin/activate  # Windows: venv\Scripts\activate
python -m uvicorn app.main:app --reload

# 3. 프론트엔드 실행
cd frontend
npm run dev
```

### 기능 테스트
1. 로그인 후 터미널 접속
2. `kub` 입력 후 Tab → 자동완성 확인
3. `kubectl get pods` 실행
4. ↑ 키로 이전 명령어 확인
5. Ctrl+L로 화면 지우기
6. Ctrl+C로 입력 취소
7. 프롬프트에 네임스페이스 표시 확인

## 📊 테스트 결과
- ✅ 명령어 히스토리 작동
- ✅ Tab 자동완성 작동
- ✅ Ctrl+C, Ctrl+L 단축키 작동
- ✅ 네임스페이스 프롬프트 표시
- ✅ 환경변수 적용 확인
- ✅ 출력 포맷 정상
- ✅ Windows 환경 호환성 확인

## 🔜 향후 개선사항
- [ ] 더 많은 kubectl 명령어 자동완성
- [ ] 명령어 히스토리 영구 저장
- [ ] 터미널 테마 커스터마이징
- [ ] 다중 터미널 탭 지원

## 📚 관련 문서
- [환경변수 설정 가이드](frontend/ENV_SETUP.md)
- [터미널 테스트 가이드](docs/terminal-test-guide.md)
- [요구사항 명세](.kiro/specs/web-terminal-interface/requirements.md)
