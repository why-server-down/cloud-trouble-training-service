#!/bin/bash

# K8s Survival Camp - 테스트 환경 자동 구축 스크립트

echo "========================================"
echo "K8s Survival Camp - 테스트 환경 구축"
echo "========================================"
echo ""

# 색상 정의
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 1. Docker 및 Kubernetes 확인
echo -e "${YELLOW}[1/6] Docker 및 Kubernetes 확인 중...${NC}"
if ! docker info &> /dev/null; then
    echo -e "${RED}❌ Docker가 실행되지 않았습니다. Docker Desktop을 시작해주세요.${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Docker 실행 중${NC}"

if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}❌ Kubernetes가 실행되지 않았습니다.${NC}"
    echo -e "${YELLOW}   Docker Desktop → Settings → Kubernetes → Enable Kubernetes${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Kubernetes 실행 중${NC}"
echo ""

# 2. PostgreSQL 컨테이너 시작
echo -e "${YELLOW}[2/6] PostgreSQL 컨테이너 시작 중...${NC}"
if docker ps --filter "name=postgres" --format "{{.Names}}" | grep -q "postgres"; then
    echo -e "${GREEN}✅ PostgreSQL 이미 실행 중${NC}"
else
    docker-compose up -d postgres
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ PostgreSQL 시작 완료${NC}"
        echo "   5초 대기 중..."
        sleep 5
    else
        echo -e "${RED}❌ PostgreSQL 시작 실패${NC}"
        exit 1
    fi
fi
echo ""

# 3. 테스트용 네임스페이스 생성
echo -e "${YELLOW}[3/6] 테스트용 Kubernetes 네임스페이스 생성 중...${NC}"
NAMESPACE="user-e8e9ed5e-d985-419b-ad6c-0db9eaa0978c"

if kubectl get namespace $NAMESPACE &> /dev/null; then
    echo -e "${GREEN}✅ 네임스페이스 이미 존재: $NAMESPACE${NC}"
else
    kubectl create namespace $NAMESPACE
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✅ 네임스페이스 생성 완료: $NAMESPACE${NC}"
    else
        echo -e "${RED}❌ 네임스페이스 생성 실패${NC}"
        exit 1
    fi
fi
echo ""

# 4. 테스트용 Pod 생성
echo -e "${YELLOW}[4/6] 테스트용 Pod 생성 중...${NC}"

if kubectl get pod nginx-pod -n $NAMESPACE &> /dev/null; then
    echo -e "${GREEN}✅ nginx-pod 이미 존재${NC}"
else
    kubectl run nginx-pod --image=nginx -n $NAMESPACE
    echo -e "${GREEN}✅ nginx-pod 생성 완료${NC}"
fi

if kubectl get pod busybox-pod -n $NAMESPACE &> /dev/null; then
    echo -e "${GREEN}✅ busybox-pod 이미 존재${NC}"
else
    kubectl run busybox-pod --image=busybox -n $NAMESPACE -- sleep 3600
    echo -e "${GREEN}✅ busybox-pod 생성 완료${NC}"
fi
echo ""

# 5. 백엔드 환경 확인
echo -e "${YELLOW}[5/6] 백엔드 환경 확인 중...${NC}"
if [ -f "backend/.env" ]; then
    echo -e "${GREEN}✅ backend/.env 파일 존재${NC}"
else
    if [ -f "backend/.env.example" ]; then
        cp backend/.env.example backend/.env
        echo -e "${GREEN}✅ backend/.env 파일 생성 완료${NC}"
    else
        echo -e "${RED}❌ backend/.env.example 파일이 없습니다${NC}"
        exit 1
    fi
fi

if [ -d "backend/venv" ]; then
    echo -e "${GREEN}✅ Python 가상환경 존재${NC}"
else
    echo -e "${YELLOW}⚠️  Python 가상환경이 없습니다. 생성 중...${NC}"
    cd backend
    python3 -m venv venv
    source venv/Scripts/activate
    pip install -r requirements.txt
    cd ..
    echo -e "${GREEN}✅ Python 가상환경 생성 완료${NC}"
fi
echo ""

# 6. 프론트엔드 환경 확인
echo -e "${YELLOW}[6/6] 프론트엔드 환경 확인 중...${NC}"
if [ -f "frontend/.env.development" ]; then
    echo -e "${GREEN}✅ frontend/.env.development 파일 존재${NC}"
else
    if [ -f "frontend/.env.example" ]; then
        cp frontend/.env.example frontend/.env.development
        echo -e "${GREEN}✅ frontend/.env.development 파일 생성 완료${NC}"
    else
        echo -e "${RED}❌ frontend/.env.example 파일이 없습니다${NC}"
        exit 1
    fi
fi

if [ -d "frontend/node_modules" ]; then
    echo -e "${GREEN}✅ Node.js 패키지 설치됨${NC}"
else
    echo -e "${YELLOW}⚠️  Node.js 패키지가 없습니다. 설치 중...${NC}"
    cd frontend
    npm install
    cd ..
    echo -e "${GREEN}✅ Node.js 패키지 설치 완료${NC}"
fi
echo ""

# 완료 메시지
echo -e "${CYAN}========================================${NC}"
echo -e "${GREEN}✅ 테스트 환경 구축 완료!${NC}"
echo -e "${CYAN}========================================${NC}"
echo ""
echo -e "${YELLOW}다음 명령어로 서버를 시작하세요:${NC}"
echo ""
echo -e "${NC}1. 백엔드 서버 시작:${NC}"
echo "   cd backend"
echo "   source venv/Scripts/activate"
echo "   python -m uvicorn app.main:app --reload"
echo ""
echo -e "${NC}2. 프론트엔드 서버 시작 (새 터미널):${NC}"
echo "   cd frontend"
echo "   npm run dev"
echo ""
echo -e "${NC}3. 브라우저에서 접속:${NC}"
echo "   http://localhost:5173"
echo ""
echo -e "${NC}4. 테스트 계정:${NC}"
echo "   회원가입 후 로그인하세요"
echo ""
echo -e "${CYAN}========================================${NC}"
echo ""

# Pod 상태 확인
echo -e "${YELLOW}현재 Pod 상태:${NC}"
kubectl get pods -n $NAMESPACE
echo ""
