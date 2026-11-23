"""
AI 튜터 서비스 - ai-data 모듈을 FastAPI 백엔드와 연결하는 어댑터
"""

import sys
import os
import asyncio
import logging
import time
import uuid
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.ai.observability import (
    record_ai_call, record_ai_stage, record_retrieval, record_tutor_result,
)

logger = logging.getLogger(__name__)

# ai-data 경로를 Python path에 추가
_AI_DATA_PATH_CANDIDATES = (
    os.getenv("AI_DATA_DIR"),
    os.path.abspath("/app/ai-data"),
    os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../ai-data")),
)
_AI_DATA_PATH = next(
    (path for path in _AI_DATA_PATH_CANDIDATES if path and os.path.exists(path)),
    _AI_DATA_PATH_CANDIDATES[-1],
)
if _AI_DATA_PATH not in sys.path:
    sys.path.insert(0, _AI_DATA_PATH)


# 고정 미션 chaos_type → fault taxonomy canonical 이름 (ai-data/docs/fault-taxonomy-v1.md
# "Kubernetes legacy alias"). network_latency 는 실제로 readiness probe 장애라서
# 이름 그대로 LLM 에 넘기면 지연(latency) 문제로 오해한다.
_LEGACY_FAULT_ALIASES = {
    "pod_failure": "image_pull_error",
    "memory_stress": "oom_killed",
    "service_misconfig": "service_selector_mismatch",
    "network_latency": "probe_failure",
}

# LLM 을 쓰지 못할 때(AI_BACKEND=mock, 키 없음, 엔진 초기화 실패) 내보내는 준비 답변.
# 환경 → chaos_type → hint level. 각 chaos_type 은 그 환경 injector 가 실제로 주입하는
# 장애를 설명해야 하고, 레벨 규칙은 ai-data/prompts/socratic_tutor.md 를 따른다.
#   0: 관찰 질문만 (원인·명령 없음)
#   1: 조사할 영역만 짚는다 (원인·복구 없음)
#   2: 진단 개념과 진단 명령 (복구 명령 없음)
#   3: 근본 원인과 복구 명령, 그리고 왜 그렇게 고치는지
# 명령은 해당 환경 명령 정책(command_validator)을 통과하는 것만 쓴다.
# 터미널에 TTY·파이프·glob 확장이 없으므로 `kubectl edit`, `|`, `*` 를 쓰지 않는다.
# ponytail: Docker 대상 이름·CPU 값은 기본 설정(training-app/training-net/--cpus 1)을 적었다.
#   SANDBOX_TRAINING_* 를 바꾸는 배포가 생기면 settings 값으로 치환해야 한다.
_MOCK_HINTS: dict[str, dict[str, dict[int, str]]] = {
    "kubernetes": {
        "pod_failure": {
            0: "nginx Pod 목록에 STATUS가 서로 다른 Pod가 함께 보이나요? 정상으로 도는 Pod와 그렇지 않은 Pod는 각각 언제 만들어졌을까요?",
            1: "기존 Pod는 Running인데 새로 만들어진 Pod만 시작하지 못하고 있다면, 컨테이너가 뜨기 전 단계(이미지를 받아오는 과정)를 살펴볼 차례예요. 최근 Deployment에 어떤 변경이 있었는지도 함께 생각해 보세요.",
            2: "`kubectl get pods`에서 ErrImagePull 또는 ImagePullBackOff 상태인 Pod를 찾고, `kubectl describe pod <이름>`의 Events에서 어떤 이미지를 받으려다 실패했는지 확인해 보세요. 롤링 업데이트는 새 Pod가 준비될 때까지 기존 Pod를 남겨 두므로, Running 중인 기존 Pod의 Image 값과 비교하면 차이가 보일 거예요.",
            3: "원인: Deployment `nginx`의 이미지가 존재하지 않는 태그 `nginx:wrongtag`로 바뀌어 새 Pod가 이미지를 받지 못합니다(ImagePullBackOff). 롤링 업데이트라 기존 Pod는 Running으로 남아 있습니다.\n1. `kubectl describe pod <Running 중인 기존 Pod>`에서 정상 Image 값 확인\n2. `kubectl set image deployment/nginx nginx=<확인한 정상 이미지>` 또는 `kubectl rollout undo deployment/nginx`로 이미지 되돌리기\n3. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인\nPod를 지워도 Deployment가 같은 잘못된 이미지로 다시 만들기 때문에 해결되지 않아요. Deployment의 이미지 자체를 고쳐야 합니다.",
        },
        "memory_stress": {
            0: "nginx Pod의 STATUS와 RESTARTS 값이 어떻게 보이나요? 새로 만들어진 Pod가 같은 상태를 반복하고 있지는 않나요?",
            1: "새 Pod가 시작했다가 반복해서 종료되고 있다면, 컨테이너가 마지막에 왜 끝났는지와 Pod에 걸린 리소스 설정을 살펴볼 차례예요.",
            2: "`kubectl describe pod <이름>`에서 Last State의 Reason과 Exit Code, 그리고 Limits 항목을 확인해 보세요. 컨테이너가 memory limit보다 많은 메모리를 쓰면 커널이 강제로 종료합니다(Exit Code 137, 클러스터에 따라 Reason은 OOMKilled 또는 Error). 지금 limit 값이 nginx가 뜨기에 충분한지 생각해 보세요.",
            3: "원인: nginx 컨테이너의 memory limit이 6Mi로 너무 낮아 새 Pod가 시작하자마자 한도를 넘어 강제 종료(Exit Code 137)되고 CrashLoopBackOff를 반복합니다.\n1. `kubectl describe pod <이름>`에서 Last State의 Exit Code 137과 Limits의 memory 6Mi 확인\n2. `kubectl set resources deployment/nginx --limits=memory=128Mi`로 limit 상향\n3. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인\nPod를 재시작해도 같은 limit으로 다시 뜨기 때문에 해결되지 않아요. Deployment의 limit 자체를 올려야 합니다.",
        },
        "service_misconfig": {
            0: "웹페이지 요청은 Service를 거쳐 Pod로 전달돼요. Pod 자체는 정상으로 떠 있나요? 그렇다면 요청은 어디서 끊겼을까요?",
            1: "Pod가 정상이라면 Service가 트래픽을 보낼 Pod를 실제로 찾고 있는지 살펴볼 차례예요. Service가 어떤 기준으로 Pod를 고르는지 확인해 보세요.",
            2: "`kubectl describe svc webapp-svc`에서 Selector와 Endpoints를 확인하고, `kubectl get pods --show-labels`로 Pod label과 비교해 보세요. Endpoints가 비어 있다면 selector에 맞으면서 Ready인 Pod가 하나도 없다는 뜻이에요. Pod가 모두 Ready인데도 비어 있다면 selector와 label이 서로 맞는지 보세요.",
            3: "원인: `webapp-svc`의 selector가 `app: webapp-broken`이라 label이 `app: webapp`인 Pod를 고르지 못해 Endpoints가 비어 있습니다.\n1. `kubectl describe svc webapp-svc`에서 Selector와 빈 Endpoints 확인\n2. `kubectl patch svc webapp-svc -p '{\"spec\":{\"selector\":{\"app\":\"webapp\"}}}'`로 Service selector를 Pod label에 맞추기\n3. `kubectl get endpoints webapp-svc`로 Pod IP가 잡히는지 확인\n잘못된 것은 Service 쪽 selector이므로 Pod label이 아니라 Service를 고칩니다.",
        },
        "network_latency": {
            0: "nginx Pod의 STATUS는 Running인데 READY 열은 어떻게 보이나요? Running과 Ready는 같은 뜻일까요?",
            1: "Pod가 Running인데 Ready가 아니라면, Kubernetes가 Pod의 준비 상태를 판단하는 설정(Readiness Probe)을 살펴볼 차례예요. 그 판단 결과가 Service의 Endpoints와 어떻게 이어지는지도 생각해 보세요.",
            2: "`kubectl describe pod <이름>`에서 Readiness 항목과 Events의 Readiness probe failed 메시지를 확인하고, `kubectl get endpoints nginx-svc`가 비어 있는지 보세요. probe가 어떤 경로를 검사하고 있고, nginx가 그 경로에 실제로 응답하나요?",
            3: "원인: nginx의 readinessProbe가 존재하지 않는 경로 `/healthz-notexist`를 검사해 Pod가 Ready가 되지 못하고(READY 0/1) Service Endpoints가 비어 있습니다.\n1. `kubectl describe pod <이름>`에서 Readiness probe 실패 경로 확인\n2. `kubectl patch deployment nginx --type=json -p='[{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/0/readinessProbe\"}]'`로 probe 제거 (또는 probe 경로를 nginx가 응답하는 `/`로 수정)\n3. `kubectl get endpoints nginx-svc`로 Pod IP가 잡히는지 확인\nprobe가 성공해야 Pod가 Ready가 되고, Ready인 Pod만 Service Endpoints에 들어갑니다.",
        },
        # 아래는 AI 시나리오에만 나오는 장애다. 증상·메시지는 colima k3s 에 실제로 주입해 확인했다.
        "crash_loop": {
            0: "nginx Pod 중 STATUS가 Error와 CrashLoopBackOff를 오가는 Pod가 있나요? RESTARTS 숫자는 어떻게 변하고 있나요?",
            1: "컨테이너가 시작하자마자 끝나고 있다면, 컨테이너가 마지막에 어떻게 종료됐는지와 어떤 명령으로 시작하도록 되어 있는지 살펴볼 차례예요.",
            2: "`kubectl logs <이름>`으로 남긴 로그가 있는지 보고, `kubectl describe pod <이름>`에서 Last State의 Exit Code와 Command 항목을 확인해 보세요. 로그가 비어 있는데 바로 끝난다면 앱이 아니라 시작 명령 자체를 의심해 볼 만해요. Running 중인 기존 Pod의 Command와도 비교해 보세요.",
            3: "원인: Deployment `nginx`의 컨테이너 command가 `sh -c 'exit 1'`로 바뀌어 새 Pod가 nginx를 띄우지 않고 곧바로 종료(Exit Code 1)되며 CrashLoopBackOff를 반복합니다. 롤링 업데이트라 기존 Pod는 Running으로 남아 있습니다.\n1. `kubectl describe pod <새 Pod>`에서 Command `sh -c 'exit 1'`과 Exit Code 1 확인\n2. `kubectl patch deployment nginx --type=json -p='[{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/0/command\"}]'`로 command 제거 (또는 `kubectl rollout undo deployment/nginx`)\n3. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인\ncommand를 지우면 이미지에 정해진 기본 시작 명령(nginx)으로 돌아갑니다.",
        },
        "liveness_probe": {
            0: "nginx Pod의 RESTARTS 숫자가 계속 늘어나나요? 컨테이너가 시작은 하는데 얼마 못 가 다시 시작되는 것처럼 보이지는 않나요?",
            1: "컨테이너가 스스로 죽는 게 아니라 일정 시간마다 재시작된다면, Kubernetes가 컨테이너가 살아 있는지 판단하는 설정(Liveness Probe)을 살펴볼 차례예요.",
            2: "`kubectl describe pod <이름>`에서 Liveness 항목이 어떤 경로를 검사하는지와 Events의 `Liveness probe failed` 메시지를 확인해 보세요. Last State가 Exit Code 0(Completed)인데도 재시작된다면 앱이 스스로 실패한 게 아니라 kubelet이 컨테이너를 다시 시작시킨 것일 수 있어요. 검사하는 경로에 nginx가 실제로 응답하는지 생각해 보세요.",
            3: "원인: nginx의 livenessProbe가 존재하지 않는 경로 `/healthz-notexist`를 검사해 404로 실패하고, 실패 한 번(failureThreshold 1)마다 kubelet이 컨테이너를 재시작합니다. 새 Pod가 잠깐 Ready였다가 기존 Pod를 대체했기 때문에, 재시작과 대기(CrashLoopBackOff)를 반복하는 동안 Endpoints도 대부분 비어 있습니다.\n1. `kubectl describe pod <이름>`에서 Liveness 경로와 `Liveness probe failed: HTTP probe failed with statuscode: 404` 확인\n2. `kubectl patch deployment nginx --type=json -p='[{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/0/livenessProbe\"}]'`로 probe 제거 (또는 경로를 nginx가 응답하는 `/`로 수정)\n3. `kubectl get pods`로 RESTARTS가 더 늘지 않고 READY 1/1인지 확인\nreadinessProbe는 실패하면 트래픽만 빼지만, livenessProbe는 실패하면 컨테이너를 죽이고 다시 띄웁니다.",
        },
        "configmap_misconfig": {
            0: "새로 만들어진 nginx Pod가 Error나 CrashLoopBackOff를 반복하나요? 컨테이너가 끝나기 직전에 무언가 말을 남겼을까요?",
            1: "nginx가 시작하다 스스로 멈춘다면 로그와, Pod에 바깥에서 붙인 설정 파일(ConfigMap 마운트)을 살펴볼 차례예요.",
            2: "`kubectl logs <이름>`의 마지막 줄에서 nginx가 남긴 `[emerg]` 메시지를 찾고, `kubectl describe pod <이름>`의 Mounts에서 `/etc/nginx/nginx.conf`가 어디서 오는지 확인해 보세요. `kubectl get configmap nginx-broken-config -o yaml`로 그 설정 내용을 직접 볼 수 있어요.",
            3: "원인: ConfigMap `nginx-broken-config`의 nginx.conf가 세미콜론과 닫는 괄호가 빠진 채 `/etc/nginx/nginx.conf`에 마운트되어, nginx가 `directive \"listen\" is not terminated by \";\"` 오류로 시작하지 못합니다(Exit Code 1).\n1. `kubectl logs <새 Pod>`에서 `[emerg]` 오류와 줄 번호 확인\n2. `kubectl patch deployment nginx --type=json -p='[{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/0/volumeMounts\"},{\"op\":\"remove\",\"path\":\"/spec/template/spec/volumes\"}]'`로 깨진 설정 마운트 제거 (또는 `kubectl rollout undo deployment/nginx`)\n3. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인\n이 터미널은 `;`를 받지 않아 설정 파일을 직접 고칠 수 없어요. 마운트를 걷어 내면 이미지에 들어 있는 정상 nginx.conf로 돌아갑니다.",
        },
        "init_container_failure": {
            0: "새 nginx Pod의 STATUS가 `Init:`으로 시작하나요? 메인 컨테이너는 시작이라도 했을까요?",
            1: "STATUS가 Init 단계에 머물러 있다면 메인 컨테이너보다 먼저 실행되는 준비 컨테이너(initContainer)를 살펴볼 차례예요.",
            2: "`kubectl describe pod <이름>`에서 Init Containers 항목의 이름, Command, Exit Code를 확인하고, `kubectl logs <이름> -c <init 컨테이너 이름>`으로 그 컨테이너가 남긴 메시지를 보세요. initContainer가 성공해야 메인 컨테이너가 시작해요.",
            3: "원인: Deployment `nginx`에 항상 실패하는 initContainer `init-check`(`echo 'prerequisite check failed'; exit 1`)가 추가되어 새 Pod가 Init:Error·Init:CrashLoopBackOff에 머물고 nginx는 시작조차 못 합니다.\n1. `kubectl logs <새 Pod> -c init-check`에서 `prerequisite check failed` 확인\n2. `kubectl patch deployment nginx --type=json -p='[{\"op\":\"remove\",\"path\":\"/spec/template/spec/initContainers\"}]'`로 initContainer 제거 (또는 `kubectl rollout undo deployment/nginx`)\n3. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인\n메인 컨테이너는 문제가 없고 앞 단계가 막혀 있었으므로 initContainer를 걷어 내면 됩니다.",
        },
        "node_selector_mismatch": {
            0: "새 nginx Pod가 Pending에서 움직이지 않나요? 이 Pod는 어느 노드에서 실행될지 정해졌을까요?",
            1: "Pod가 Pending이고 컨테이너 오류도 없다면 스케줄러가 Pod를 놓을 노드를 찾지 못한 거예요. Pod가 노드에 요구하는 조건을 살펴볼 차례예요.",
            2: "`kubectl describe pod <이름>`에서 Node-Selectors 항목과 Events의 `FailedScheduling` 메시지를 확인해 보세요. `kubectl get events`에도 같은 메시지가 남아요. 그 조건에 맞는 노드가 클러스터에 있는지 생각해 보세요.",
            3: "원인: Deployment `nginx`에 존재하지 않는 노드 조건 `nodeSelector: disk=ssd-nonexistent`가 추가되어 새 Pod를 놓을 노드가 없습니다(`didn't match Pod's node affinity/selector`). 기존 Pod는 Running으로 남아 있습니다.\n1. `kubectl describe pod <새 Pod>`에서 Node-Selectors와 FailedScheduling 확인\n2. `kubectl patch deployment nginx --type=json -p='[{\"op\":\"remove\",\"path\":\"/spec/template/spec/nodeSelector\"}]'`로 nodeSelector 제거\n3. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인\n노드에 label을 붙일 권한은 없으니, 잘못된 조건을 Deployment에서 걷어 냅니다.",
        },
        "compound_probe_cascade": {
            0: "새 nginx Pod는 지금 어떤 STATUS인가요? 그 문제를 고치고 나면 Pod가 바로 READY 1/1이 될까요?",
            1: "컨테이너가 뜨기 전 단계(이미지 받기)와, 뜬 뒤 Pod의 준비 상태를 판단하는 설정(Readiness Probe)을 함께 살펴볼 차례예요. 문제가 하나가 아닐 수 있어요.",
            2: "`kubectl describe pod <이름>`의 Events에서 이미지 관련 오류를 확인하고, 같은 출력의 Readiness 항목이 어떤 경로를 검사하는지도 보세요. 하나를 고친 뒤에도 `kubectl get pods`의 READY가 1/1인지 다시 확인해야 해요.",
            3: "원인: 두 문제가 겹쳐 있습니다. 이미지가 존재하지 않는 태그 `nginx:wrongtag`이고(ImagePullBackOff), readinessProbe도 없는 경로 `/healthz-notexist`를 검사합니다. 이미지를 고쳐도 새 Pod가 READY 0/1에 머물러 롤아웃이 끝나지 않습니다.\n1. `kubectl describe pod <Running 중인 기존 Pod>`에서 정상 Image 값 확인\n2. `kubectl set image deployment/nginx nginx=<확인한 정상 이미지>`로 이미지 복구\n3. `kubectl patch deployment nginx --type=json -p='[{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/0/readinessProbe\"}]'`로 probe 제거\n4. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인\n두 번째 문제는 첫 번째를 고쳐야 드러나요. 고친 뒤 READY를 꼭 다시 확인하세요.",
        },
        "compound_crash_service": {
            0: "nginx Pod와 webapp Pod는 각각 어떤 상태인가요? 증상이 한 군데에서만 나고 있을까요?",
            1: "증상이 서로 다른 두 곳에서 날 수 있어요. 한쪽은 컨테이너가 시작하지 못하는 문제, 다른 쪽은 Service가 트래픽을 보낼 Pod를 찾지 못하는 문제인지 나눠서 살펴보세요.",
            2: "nginx 쪽은 `kubectl describe pod <이름>`에서 Exit Code와 Command를, webapp 쪽은 `kubectl describe svc webapp-svc`의 Selector·Endpoints와 `kubectl get pods --show-labels`의 label을 비교해 보세요. 두 문제는 서로 관계가 없어서 하나를 고쳐도 다른 하나는 남아요.",
            3: "원인: 서로 무관한 두 문제가 동시에 있습니다. nginx 컨테이너 command가 `sh -c 'exit 1'`로 바뀌어 새 Pod가 CrashLoopBackOff를 반복하고, `webapp-svc`의 selector가 `app: webapp-broken`이라 Endpoints가 비어 있습니다.\n1. `kubectl patch deployment nginx --type=json -p='[{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/0/command\"}]'`로 nginx command 제거\n2. `kubectl patch svc webapp-svc -p '{\"spec\":{\"selector\":{\"app\":\"webapp\"}}}'`로 Service selector를 Pod label에 맞추기\n3. `kubectl get pods`와 `kubectl get endpoints webapp-svc`로 둘 다 정상인지 확인\n두 문제의 조사 경로가 Deployment와 Service로 갈리므로 하나씩 따로 확인해야 합니다.",
        },
        "wrong_image_registry": {
            0: "새 nginx Pod는 시작했나요? 정상으로 도는 Pod와 그렇지 않은 Pod는 어떤 이미지를 쓰고 있을까요?",
            1: "새 Pod가 이미지를 받지 못한다면, 태그뿐 아니라 이미지를 어디서(레지스트리 주소) 받아오도록 되어 있는지도 살펴볼 차례예요.",
            2: "`kubectl describe pod <이름>`의 Events에서 `Failed to pull image` 메시지에 적힌 이미지 이름 전체를 확인하고, Running 중인 기존 Pod의 Image 값과 비교해 보세요. 이미지 이름 앞부분이 레지스트리 주소예요.",
            3: "원인: Deployment `nginx`의 이미지가 이 클러스터에서 접근할 수 없는 사설 레지스트리 주소 `private.registry.internal/nginx:latest`로 바뀌어 새 Pod가 이미지를 받지 못합니다(ImagePullBackOff). 기존 Pod는 Running으로 남아 있습니다.\n1. `kubectl describe pod <Running 중인 기존 Pod>`에서 정상 Image 값 확인\n2. `kubectl set image deployment/nginx nginx=<확인한 정상 이미지>` 또는 `kubectl rollout undo deployment/nginx`로 이미지 되돌리기\n3. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인\n태그 오류와 달리 레지스트리 주소 자체가 틀렸으므로, 같은 이름의 다른 태그로 바꿔도 해결되지 않아요.",
        },
        "secret_ref_missing": {
            0: "새 nginx Pod의 STATUS가 무엇인가요? 컨테이너가 시작했다가 죽은 걸까요, 아니면 시작하기 전에 멈춘 걸까요?",
            1: "컨테이너가 만들어지기 전에 멈췄다면, 컨테이너를 만들 때 필요한 설정(환경변수로 읽어 오는 Secret이나 ConfigMap)을 살펴볼 차례예요.",
            2: "`kubectl describe pod <이름>`에서 Environment Variables from 항목과 Events의 오류 메시지를 확인하고, `kubectl get secrets`로 그 이름의 Secret이 실제로 있는지 보세요.",
            3: "원인: Deployment `nginx`가 존재하지 않는 Secret `missing-app-secret`을 envFrom으로 참조해 새 Pod가 CreateContainerConfigError에 멈춰 있습니다(`secret \"missing-app-secret\" not found`).\n1. `kubectl describe pod <새 Pod>`에서 참조하는 Secret 이름 확인\n2. `kubectl create secret generic missing-app-secret --from-literal=key=value`로 Secret 만들기 (또는 `kubectl patch deployment nginx --type=json -p='[{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/0/envFrom\"}]'`로 참조 제거)\n3. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인\nSecret을 만들면 kubelet이 같은 Pod를 다시 시도해서 Pod를 지우지 않아도 시작됩니다.",
        },
        "pvc_unbound": {
            0: "새 nginx Pod가 Pending에서 움직이지 않나요? 이 Pod가 시작하려면 무엇이 먼저 준비되어야 할까요?",
            1: "Pod가 Pending이라면 스케줄러가 기다리는 조건을 봐야 해요. 이번에는 노드가 아니라 Pod가 붙이려는 저장소(PersistentVolumeClaim)를 살펴볼 차례예요.",
            2: "`kubectl describe pod <이름>`의 Events에서 `FailedScheduling` 메시지를 확인하고, `kubectl get pvc`와 `kubectl describe pvc nginx-data`로 PVC 상태와 그 Events를 보세요. PVC가 어떤 storageClass를 요청하고 있나요?",
            3: "원인: Deployment `nginx`가 PVC `nginx-data`를 마운트하는데, 이 PVC가 존재하지 않는 storageClass `nonexistent-storage`를 요청해 Pending에 머물고(`ProvisioningFailed`), 새 Pod도 스케줄되지 못합니다(`unbound immediate PersistentVolumeClaims`).\n1. `kubectl describe pvc nginx-data`에서 storageClass 오류 확인\n2. `kubectl patch deployment nginx --type=json -p='[{\"op\":\"remove\",\"path\":\"/spec/template/spec/containers/0/volumeMounts\"},{\"op\":\"remove\",\"path\":\"/spec/template/spec/volumes\"}]'`로 볼륨 마운트 제거\n3. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인한 뒤, 쓰지 않는 PVC는 `kubectl delete pvc nginx-data`로 정리 (확인 후 실행)\n이 터미널에서는 PVC를 새로 만들 수 없으니, 바인딩되지 않는 볼륨을 Deployment에서 걷어 냅니다.",
        },
        "cpu_throttle": {
            0: "새 nginx Pod의 STATUS는 Running인데 READY 열은 어떻게 보이나요? RESTARTS는 늘지 않는데 왜 준비가 안 될까요?",
            1: "Pod가 Running인데 Ready가 아니라면 준비 상태를 판단하는 검사(Readiness Probe)가 왜 실패하는지 봐야 해요. 검사 설정이 틀렸는지, 컨테이너가 검사를 제시간에 끝낼 자원이 없는지 나눠서 살펴보세요.",
            2: "`kubectl describe pod <이름>`에서 Events의 `Readiness probe failed` 메시지가 어떤 이유로 실패했는지 보고, 같은 출력의 Limits에서 cpu 값을 Running 중인 기존 Pod와 비교해 보세요. 검사가 시간 초과(timed out)로 실패한다면 CPU 상한을 의심해 볼 만해요.",
            3: "원인: nginx의 CPU limit이 1m(CPU의 0.1%)로 줄어, CPU를 조금 쓰는 readiness 검사가 1초 안에 끝나지 못하고 시간 초과로 실패합니다(`command timed out`). 새 Pod는 READY 0/1에 머물고 기존 Pod가 남아 있습니다. 메모리와는 관계없습니다.\n1. `kubectl describe pod <새 Pod>`에서 Limits cpu 1m과 Readiness probe 시간 초과 확인\n2. `kubectl set resources deployment/nginx --limits=cpu=100m --requests=cpu=50m`으로 CPU 상한 복구\n3. `kubectl get pods`로 새 Pod가 Running이고 READY 1/1인지 확인\n검사 내용은 정상이에요. probe를 지우면 증상만 가려지고 CPU 부족은 그대로 남으니 상한을 올려야 합니다.",
        },
        "default": {
            0: "지금 어떤 증상이 보이나요? 정상이 아닌 리소스가 무엇이고, 언제부터 그랬는지 먼저 살펴볼까요?",
            1: "정상이 아닌 리소스를 찾았다면, 그 리소스의 상세 정보와 최근 이벤트를 살펴볼 차례예요.",
            2: "`kubectl get pods`로 상태가 이상한 Pod를 찾고, `kubectl describe pod <이름>`의 Events와 `kubectl get events`에서 에러 메시지를 확인해 보세요.",
            3: "1. `kubectl get pods`와 `kubectl get events`로 문제 리소스 확인\n2. `kubectl describe pod <이름>`으로 원인 파악\n3. 원인에 맞게 Deployment·Service 설정을 고친 뒤 `kubectl get pods`로 정상화 확인",
        },
    },
    "docker": {
        "docker_container_stopped": {
            0: "`training-app` 컨테이너가 실행 중인 컨테이너 목록에 보이나요? 보이지 않는다면 목록에서 빠진 컨테이너는 어디서 확인할 수 있을까요?",
            1: "실행 중인 목록에 없다면, 멈춘 컨테이너까지 포함한 전체 목록에서 `training-app`의 상태를 살펴볼 차례예요.",
            2: "`docker ps`에는 실행 중인 컨테이너만 나와요. `docker ps -a`로 전체 목록을 보고 `training-app`의 STATUS가 Exited인지, `docker inspect training-app`의 State 항목에서 언제 종료됐는지 확인해 보세요.",
            3: "원인: `training-app` 컨테이너가 중지(Exited)되어 서비스를 하지 못합니다.\n1. `docker ps -a`로 Exited 상태 확인\n2. `docker start training-app`으로 컨테이너 다시 시작\n3. `docker ps`로 STATUS가 Up인지 확인\n컨테이너 설정은 그대로이므로 다시 시작하면 원래대로 동작합니다.",
        },
        "docker_network_disconnect": {
            0: "`training-app` 컨테이너는 실행 중인가요? 실행 중인데도 닿지 않는다면, 컨테이너가 다른 대상과 어떻게 연결되는지 떠올려 볼까요?",
            1: "컨테이너는 살아 있는데 통신이 안 된다면 네트워크 연결을 살펴볼 차례예요. 이 컨테이너가 어떤 Docker 네트워크에 붙어 있어야 하는지 생각해 보세요.",
            2: "`docker inspect training-app`의 NetworkSettings.Networks 항목을 확인하고, `docker network inspect training-net`의 Containers 목록과 비교해 보세요. 네트워크에 붙어 있지 않은 컨테이너는 그 네트워크의 다른 대상과 통신할 수 없어요.",
            3: "원인: `training-app`이 `training-net` 네트워크에서 분리되어 Networks가 비어 있습니다.\n1. `docker inspect training-app`에서 Networks가 비어 있는지 확인\n2. `docker network connect training-net training-app`으로 다시 연결\n3. `docker network inspect training-net`의 Containers에 `training-app`이 보이는지 확인\n컨테이너는 정상이므로 재시작이 아니라 네트워크 연결만 되돌리면 됩니다.",
        },
        "docker_cpu_throttle": {
            0: "`training-app`은 실행 중이고 네트워크도 연결돼 있는데 응답이 느린가요? 컨테이너가 쓸 수 있는 자원은 충분할까요?",
            1: "컨테이너에 걸린 자원 상한, 특히 CPU 상한이 정상 값인지 살펴볼 차례예요.",
            2: "`docker inspect training-app`의 HostConfig에서 NanoCpus 값을 확인해 보세요. NanoCpus는 1000000000이 CPU 1개라서, 지금 값이 CPU 몇 개에 해당하는지 계산해 보면 느린 이유가 보일 거예요. `docker stats --no-stream training-app`으로 사용량도 함께 볼 수 있어요.",
            3: "원인: `training-app`의 CPU 상한이 0.05개(NanoCpus=50000000)로 줄어 요청을 처리할 CPU가 부족합니다. 메모리 limit과는 관계없습니다.\n1. `docker inspect training-app`에서 HostConfig.NanoCpus=50000000 확인\n2. `docker update --cpus 1 training-app`으로 CPU 상한 복구\n3. `docker inspect training-app`에서 NanoCpus가 1000000000인지 확인\ndocker update는 실행 중인 컨테이너의 자원 상한을 바로 바꾸므로 재시작할 필요가 없습니다.",
        },
        "default": {
            0: "지금 어떤 증상이 보이나요? 훈련 컨테이너가 어떤 상태인지 먼저 살펴볼까요?",
            1: "컨테이너의 상태, 네트워크 연결, 자원 상한 중 어디가 평소와 다른지 살펴볼 차례예요.",
            2: "`docker ps -a`로 컨테이너 상태를 보고, `docker inspect <컨테이너>`의 State·NetworkSettings·HostConfig와 `docker logs <컨테이너>`에서 단서를 찾아보세요.",
            3: "1. `docker ps -a`로 문제 컨테이너 확인\n2. `docker inspect <컨테이너>`와 `docker logs <컨테이너>`로 원인 파악\n3. 원인에 맞게 docker start, docker network connect, docker update 중 필요한 명령으로 고친 뒤 `docker ps`로 정상화 확인",
        },
    },
    "linux": {
        "linux_process_flood": {
            0: "프로세스 목록을 보면 평소보다 많은 프로세스가 떠 있나요? 같은 이름이 반복해서 보이지는 않나요?",
            1: "같은 이름의 프로세스가 대량으로 떠 있다면, 그 프로세스가 무엇이고 몇 개나 되는지 살펴볼 차례예요.",
            2: "`ps aux`로 프로세스 목록을 보고 반복되는 이름을 찾아보세요. 이 터미널은 파이프(`|`)를 쓸 수 없으니 목록을 직접 훑어보거나 `pstree`로 어떤 부모 아래에 몰려 있는지 확인해 보세요.",
            3: "원인: `afterfail-worker` 프로세스 120개가 생성되어 프로세스 자리를 차지하고 있습니다.\n1. `ps aux`로 `afterfail-worker` 프로세스 확인\n2. `pkill -f afterfail-worker`로 한 번에 종료 (확인 후 실행)\n3. `ps aux`로 남은 `afterfail-worker`가 없는지 확인\n120개를 `kill <PID>`로 하나씩 지우기는 어려우므로, 명령줄 이름으로 한 번에 신호를 보내는 pkill -f를 씁니다.",
        },
        "linux_disk_pressure": {
            0: "작업 디렉터리에 파일을 더 쓸 수 있나요? 디스크 공간이 얼마나 남아 있는지 확인해 봤나요?",
            1: "공간이 부족해 보인다면, 어느 파일시스템이 가득 찼고 그 안에서 어떤 파일이 공간을 차지하는지 살펴볼 차례예요.",
            2: "`df -h`로 파일시스템별 사용률(Use%)을 확인하고, 사용률이 높은 `/tmp/afterfail`에서 `ls -al /tmp/afterfail`로 큰 파일을 찾아보세요. 이 터미널은 `*` 같은 와일드카드를 펼치지 않으니 경로를 그대로 적어야 해요.",
            3: "원인: `/tmp/afterfail`(64Mi tmpfs)이 `afterfail-fill.dat` 파일로 약 88% 차 있습니다.\n1. `ls -al /tmp/afterfail`로 `afterfail-fill.dat` 크기 확인\n2. `rm /tmp/afterfail/afterfail-fill.dat` 또는 `truncate -s 0 /tmp/afterfail/afterfail-fill.dat`로 공간 확보 (확인 후 실행)\n3. `df -h`로 `/tmp/afterfail` 사용률이 내려갔는지 확인\n공간을 차지한 파일 자체를 비워야 사용률이 내려갑니다.",
        },
        "linux_cpu_saturation": {
            0: "시스템이 느리게 느껴지나요? 지금 CPU를 많이 쓰는 무언가가 있을지, 부하 수치는 어떤지 먼저 살펴볼까요?",
            1: "프로세스 수는 많지 않은데 느리다면, 각 프로세스가 CPU를 얼마나 쓰는지 살펴볼 차례예요. 개수보다 사용률 순서가 중요해요.",
            2: "이 환경의 `ps aux`는 CPU 사용률 열을 보여주지 않아요. `top -b -n 1`로 한 번 찍어 CPU 사용률 순으로 맨 위에 오는 프로세스를 확인하고, `uptime`의 load average도 함께 보세요. 컨테이너 CPU 상한이 작아서 %CPU 숫자가 작아 보여도 계속 맨 위에 있다면 의심해 볼 만해요.",
            3: "원인: `afterfail-cpuburn` 프로세스 2개가 쉬지 않고 도는 루프로 CPU를 태우고 있습니다(컨테이너 CPU 상한 0.5개 안이라 %CPU 숫자는 작게 보입니다).\n1. `top -b -n 1`에서 맨 위의 `afterfail-cpuburn` 확인\n2. `pkill -f afterfail-cpuburn`으로 종료 (확인 후 실행)\n3. `top -b -n 1`과 `uptime`으로 부하가 내려가는지 확인\nCPU를 태우는 프로세스를 없애야 다른 프로세스가 CPU를 다시 쓸 수 있습니다.",
        },
        "default": {
            0: "지금 어떤 증상이 보이나요? 프로세스, 디스크, 메모리 중 어디가 평소와 다른지 먼저 살펴볼까요?",
            1: "이상해 보이는 자원을 찾았다면, 그 자원을 누가 얼마나 쓰고 있는지 살펴볼 차례예요.",
            2: "`ps aux`로 프로세스를, `df -h`로 디스크를, `free`로 메모리를, `top -b -n 1`과 `uptime`으로 CPU 부하를 확인해 보세요.",
            3: "1. `ps aux`, `df -h`, `free`, `top -b -n 1`로 문제 자원 확인\n2. 자원을 차지한 프로세스나 `/tmp/afterfail` 안의 파일 파악\n3. 원인에 맞게 `pkill -f <프로세스 이름>` 또는 `rm <파일 경로>`로 정리한 뒤 같은 명령으로 정상화 확인",
        },
    },
}


class TutorService:
    """
    AI 튜터 서비스
    - openai/gemini 모드: ai-data의 AITutorEngine 사용 (RAG + LLM)
    - mock 모드: 간단한 고정 응답 (OpenAI 키 없을 때)
    """

    def __init__(self):
        self._engine = None
        self._initialized = False

    def _init_engine(self):
        if self._initialized:
            return
        self._initialized = True

        if settings.AI_BACKEND not in ("openai", "gemini"):
            return

        if settings.AI_BACKEND == "gemini":
            if not settings.GEMINI_API_KEY:
                return
        else:
            if not settings.OPENAI_API_KEY:
                return

        try:
            from ai_engine import AITutorEngine
            from config import AISettings

            ai_settings = AISettings.from_backend_settings(settings)
            self._engine = AITutorEngine(
                use_rag=True,
                settings=ai_settings,
            )
        except Exception:
            logger.exception("AI tutor engine initialization failed; using mock fallback")
            self._engine = None

    async def get_hint(
        self,
        user_question: str,
        attempt_id: uuid.UUID,
        hint_level: int,
        mission_name: str,
        mission_level: int,
        chaos_type: str,
        namespace: str,
        db: AsyncSession | None = None,
        scenario_id: uuid.UUID | None = None,
    ):
        from app.schemas import TutorResult

        total_started = time.perf_counter()
        self._init_engine()

        # 같은 attempt의 최근 user/assistant 대화쌍 로드 (세션 간 연속성)
        conversation_history = await self._load_conversation(attempt_id, db)

        # DB attempt가 결정한 환경과 sandbox 범위에서 RuntimeContext 수집
        runtime_ctx: dict | None = None
        runtime_factory = None
        attempt_environment = "kubernetes"
        if db is not None:
            try:
                from app.services.runtime_context import (
                    get_runtime_context_collector,
                    format_k8s_state,
                    format_recent_commands,
                    format_events,
                )
                from app.models import MissionAttempt
                result = await db.execute(
                    select(MissionAttempt).where(MissionAttempt.id == attempt_id)
                )
                attempt = result.scalar_one_or_none()
                user_id = attempt.user_id if attempt else None
                attempt_environment = (
                    attempt.environment if attempt and attempt.environment else "kubernetes"
                )

                if user_id:
                    from app.services.sandbox_service import get_sandbox_service

                    sandbox = get_sandbox_service().reference_for(
                        user_id=user_id,
                        namespace=namespace,
                        environment=attempt_environment,
                    )
                    collector = get_runtime_context_collector()
                    runtime_factory = lambda: collector.collect(
                        user_id=user_id, namespace=namespace, db=db,
                        scenario_title=mission_name, difficulty=str(mission_level),
                        scenario_id=scenario_id, environment=attempt_environment,
                        sandbox=sandbox,
                    )
            except Exception:
                logger.exception("AI tutor runtime context collection failed")

        if self._engine is None:
            response = TutorResult(
                message=self._mock_response(
                    user_question, hint_level, chaos_type, attempt_environment
                ),
                hint_level=hint_level,
                environment=attempt_environment,
                fallback_used=True,
                error_code="mock_backend",
            )
        else:
            retrieval_request = self._retrieval_request(
                user_question, hint_level, chaos_type, attempt_environment
            )
            runtime_result, retrieval_result = await asyncio.gather(
                self._collect_runtime_with_timeout(
                    runtime_factory, attempt_environment, hint_level
                ),
                self._retrieve_with_timeout(
                    retrieval_request, attempt_environment, hint_level
                ),
            )
            runtime_ctx, context_ms, context_error = runtime_result
            retrieval, retrieval_ms, retrieval_error = retrieval_result
            response = await self._call_engine(
                user_question=user_question,
                hint_level=hint_level,
                mission_name=mission_name,
                mission_level=mission_level,
                chaos_type=chaos_type,
                namespace=namespace,
                conversation_history=conversation_history,
                attempt_id=str(attempt_id),
                runtime_ctx=runtime_ctx,
                fault_type=chaos_type,
                environment=attempt_environment,
                retrieval_result=retrieval,
            )
            breakdown = dict(response.latency_breakdown or {})
            breakdown.update({
                "context_ms": context_ms,
                "retrieval_ms": retrieval_ms,
                "total_ms": (time.perf_counter() - total_started) * 1000,
            })
            response.latency_breakdown = breakdown
            response.latency_ms = round(breakdown["total_ms"])
            pipeline_error = retrieval_error or context_error
            if pipeline_error and not response.error_code:
                response.error_code = pipeline_error
                response.fallback_used = True
            record_ai_stage(
                provider=settings.AI_BACKEND, model=self._engine.model,
                environment=attempt_environment, hint_level=hint_level,
                stage="total", result="fallback" if response.fallback_used else "success",
                duration_ms=breakdown["total_ms"],
            )

        record_tutor_result(
            provider=settings.AI_BACKEND, environment=attempt_environment,
            result="fallback" if response.fallback_used else "success",
        )

        # TutorMessage DB 저장
        if db is not None:
            await self._save_messages(db, attempt_id, user_question, response.message, hint_level)

        return response

    def _retrieval_request(self, question, hint_level, fault_type, environment):
        from ai_engine import TutorRequest
        return TutorRequest(
            user_question=question, hint_level=hint_level,
            chaos_type=fault_type, environment=environment,
        )

    async def _collect_runtime_with_timeout(self, factory, environment, hint_level):
        if factory is None:
            return None, 0.0, "runtime_unavailable"
        started = time.perf_counter()
        result = "success"
        error = None
        try:
            context = await asyncio.wait_for(
                factory(), timeout=settings.CONTEXT_COLLECTION_TIMEOUT
            )
        except asyncio.TimeoutError:
            context, result, error = None, "timeout", "runtime_timeout"
        except Exception:
            context, result, error = None, "error", "runtime_failed"
            logger.exception("AI tutor runtime context collection failed")
        elapsed = (time.perf_counter() - started) * 1000
        record_ai_stage(
            provider=settings.AI_BACKEND, model=self._engine.model,
            environment=environment, hint_level=hint_level,
            stage="context", result=result, duration_ms=elapsed,
        )
        return context, elapsed, error

    async def _retrieve_with_timeout(self, request, environment, hint_level):
        started = time.perf_counter()
        result = "success"
        error = None
        try:
            retrieval = await asyncio.wait_for(
                asyncio.to_thread(self._engine.retrieve, request),
                timeout=settings.RAG_SEARCH_TIMEOUT,
            )
            if retrieval.error_code:
                result, error = "fallback", retrieval.error_code
        except asyncio.TimeoutError:
            from ai_engine import RetrievalResult
            retrieval = RetrievalResult([], [], 0.0, error_code="retrieval_timeout")
            result, error = "timeout", "retrieval_timeout"
        except Exception:
            from ai_engine import RetrievalResult
            retrieval = RetrievalResult([], [], 0.0, error_code="retrieval_failed")
            result, error = "error", "retrieval_failed"
            logger.exception("AI tutor retrieval failed")
        elapsed = (time.perf_counter() - started) * 1000
        contamination = sum(
            source.get("environment") not in (None, environment)
            for source in retrieval.sources
        )
        retrieval_result = (
            result if result != "success"
            else "empty" if not retrieval.sources
            else "success"
        )
        record_retrieval(
            provider=settings.AI_BACKEND, environment=environment,
            result=retrieval_result, result_count=len(retrieval.sources),
            contamination_count=contamination,
        )
        record_ai_stage(
            provider=settings.AI_BACKEND, model=self._engine.model,
            environment=environment, hint_level=hint_level,
            stage="retrieval", result=result, duration_ms=elapsed,
        )
        record_ai_stage(
            provider=settings.AI_BACKEND, model=self._engine.model,
            environment=environment, hint_level=hint_level,
            stage="rerank", result=result, duration_ms=retrieval.rerank_ms,
        )
        return retrieval, elapsed, error

    async def _load_conversation(
        self, attempt_id: uuid.UUID, db: AsyncSession | None
    ) -> list[dict]:
        if db is None:
            return []
        try:
            from app.models import TutorMessage
            result = await db.execute(
                select(TutorMessage)
                .where(TutorMessage.attempt_id == attempt_id)
                .order_by(TutorMessage.created_at.desc())
                .limit(10)
            )
            msgs = result.scalars().all()
            return self._conversation_pairs(list(reversed(msgs)))
        except Exception:
            return []

    @staticmethod
    def _conversation_pairs(messages, max_pairs: int = 5, max_chars: int = 2_000) -> list[dict]:
        """시간순 user/assistant pair만 유지하고 최신 pair부터 예산에 맞춘다."""
        pairs = []
        pending_user = None
        for message in messages:
            if message.role == "user":
                pending_user = message
            elif message.role == "assistant" and pending_user is not None:
                pairs.append({
                    "user": str(pending_user.message)[:500],
                    "assistant": str(message.message)[:500],
                    "hint_level": message.hint_level,
                })
                pending_user = None

        selected = []
        used = 0
        for pair in reversed(pairs[-max_pairs:]):
            size = len(pair["user"]) + len(pair["assistant"])
            if selected and used + size > max_chars:
                break
            if size > max_chars:
                pair = {
                    **pair,
                    "user": pair["user"][: max_chars // 2],
                    "assistant": pair["assistant"][: max_chars // 2],
                }
                size = len(pair["user"]) + len(pair["assistant"])
            selected.append(pair)
            used += size
        return list(reversed(selected))

    async def _save_messages(
        self,
        db: AsyncSession,
        attempt_id: uuid.UUID,
        user_question: str,
        assistant_response: str,
        hint_level: int,
    ):
        started = time.perf_counter()
        try:
            from app.models import TutorMessage
            db.add(TutorMessage(
                attempt_id=attempt_id,
                role="user",
                message=user_question,
                hint_level=hint_level,
            ))
            db.add(TutorMessage(
                attempt_id=attempt_id,
                role="assistant",
                message=assistant_response,
                hint_level=hint_level,
            ))
            await db.commit()
        except Exception:
            logger.exception("AI tutor message persistence failed")

    async def _call_engine(
        self,
        user_question: str,
        hint_level: int,
        mission_name: str,
        mission_level: int,
        chaos_type: str,
        namespace: str,
        conversation_history: list[dict],
        attempt_id: str,
        runtime_ctx: dict | None,
        fault_type: str | None = None,
        environment: str = "kubernetes",
        retrieval_result=None,
    ):
        started = time.perf_counter()
        try:
            from ai_engine import TutorRequest
            from prompt_engine import MissionContext, TrainingContext, UserContext

            mission_ctx = MissionContext(
                mission_id=attempt_id,
                mission_name=mission_name,
                mission_level=mission_level,
                # 프롬프트(레벨 3 MISSION)에는 taxonomy 이름으로 넘긴다.
                # RAG 검색에 쓰는 fault_type 은 문서 태그와 맞춰야 하므로 그대로 둔다.
                chaos_type=_LEGACY_FAULT_ALIASES.get(chaos_type, chaos_type),
                expected_solution=_LEGACY_FAULT_ALIASES.get(chaos_type, chaos_type),
            )

            user_ctx = UserContext(
                user_id=attempt_id,
                hint_count=hint_level,
                previous_questions=[],
                conversation_history=conversation_history,
            )
            runtime_ctx = runtime_ctx or {
                "environment": environment, "scope": {"namespace": namespace},
                "mission": {}, "observations": {}, "recent_user_commands": [],
                "metrics": {}, "logs": [],
            }
            from app.ai.runtime_observations import prepare_runtime_context
            runtime_ctx = prepare_runtime_context(runtime_ctx, user_question, environment)
            training_ctx = TrainingContext(
                environment=environment,
                scope=runtime_ctx.get("scope", {"namespace": namespace}),
                mission={**runtime_ctx.get("mission", {}), **mission_ctx.__dict__},
                observations=runtime_ctx.get("observations", {}),
                recent_commands=runtime_ctx.get("recent_user_commands", []),
                metrics=runtime_ctx.get("metrics", {}),
                logs=runtime_ctx.get("logs", []),
                user=user_ctx.__dict__,
                collection_status=runtime_ctx.get("collection_status", {}),
            )

            request = TutorRequest(
                user_question=user_question,
                hint_level=hint_level,
                mission_ctx=mission_ctx,
                user_ctx=user_ctx,
                chaos_type=fault_type,
                environment=environment,
                training_ctx=training_ctx,
            )

            response = await asyncio.wait_for(
                asyncio.to_thread(
                    self._engine.get_response, request,
                    retrieval_result=retrieval_result,
                ),
                timeout=settings.OPENAI_TIMEOUT,
            )
            llm_ms = response.latency_breakdown.get("llm_ms", response.latency_ms)
            record_ai_stage(
                provider=settings.AI_BACKEND, model=self._engine.model,
                environment=environment, hint_level=hint_level,
                stage="llm", result="fallback" if response.fallback_used else "success",
                duration_ms=llm_ms,
            )
            record_ai_call(
                provider=settings.AI_BACKEND,
                purpose="tutor",
                result="fallback" if response.fallback_used else "success",
                duration_seconds=time.perf_counter() - started,
                token_usage=response.token_usage,
                model=self._engine.model,
            )
            from app.schemas import TutorResult
            return TutorResult(
                message=response.message,
                hint_level=response.hint_level,
                environment=response.environment,
                sources=response.sources,
                observations_used=response.observations_used,
                token_usage=response.token_usage,
                latency_ms=response.latency_ms,
                fallback_used=response.fallback_used,
                error_code=response.error_code,
                latency_breakdown=response.latency_breakdown,
            )

        except asyncio.TimeoutError:
            elapsed = (time.perf_counter() - started) * 1000
            record_ai_stage(
                provider=settings.AI_BACKEND, model=self._engine.model,
                environment=environment, hint_level=hint_level,
                stage="llm", result="timeout", duration_ms=elapsed,
            )
            record_ai_call(
                provider=settings.AI_BACKEND, purpose="tutor", result="fallback",
                duration_seconds=elapsed / 1000,
                model=self._engine.model,
            )
            from app.schemas import TutorResult
            return TutorResult(
                message="AI 튜터 응답 시간이 초과되었습니다. 잠시 후 다시 질문해 주세요.",
                hint_level=hint_level, environment=environment,
                fallback_used=True, error_code="provider_timeout",
                latency_ms=round(elapsed), latency_breakdown={"llm_ms": elapsed},
            )
        except Exception:
            record_ai_call(
                provider=settings.AI_BACKEND,
                purpose="tutor",
                result="fallback",
                duration_seconds=time.perf_counter() - started,
                model=self._engine.model,
            )
            logger.exception("AI tutor adapter call failed; using safe fallback")
            from app.schemas import TutorResult
            return TutorResult(
                message="현재 AI 튜터 응답을 생성하지 못했습니다. 잠시 후 다시 질문해 주세요.",
                hint_level=hint_level,
                environment=environment,
                fallback_used=True,
                error_code="adapter_failed",
            )

    def _get_pod_status_fallback(self, namespace: str) -> tuple[str, str]:
        """RuntimeContextCollector 실패 시 직접 K8s 조회 fallback."""
        try:
            from kubernetes import client, config
            try:
                config.load_incluster_config()
            except Exception:
                config.load_kube_config()

            core_api = client.CoreV1Api()
            pods = core_api.list_namespaced_pod(namespace=namespace)
            if not pods.items:
                return "Pod 없음", "네임스페이스에 Pod가 존재하지 않습니다"

            status_lines = []
            for pod in pods.items:
                phase = pod.status.phase or "Unknown"
                for cs in (pod.status.container_statuses or []):
                    if cs.state.waiting:
                        phase = cs.state.waiting.reason or "Waiting"
                    elif cs.state.terminated:
                        phase = f"Terminated({cs.state.terminated.reason or ''})"
                status_lines.append(f"{pod.metadata.name}: {phase}")

            events = core_api.list_namespaced_event(namespace=namespace)
            recent = []
            for ev in sorted(
                events.items,
                key=lambda e: e.last_timestamp.isoformat() if e.last_timestamp else "",
                reverse=True,
            )[:5]:
                if ev.message:
                    recent.append(f"- {ev.reason}: {ev.message[:100]}")

            return "\n".join(status_lines), "\n".join(recent) if recent else "이벤트 없음"
        except Exception as e:
            return "조회 실패", f"K8s API 오류: {e}"

    def _mock_response(
        self, question: str, hint_level: int, chaos_type: str,
        environment: str = "kubernetes",
    ) -> str:
        hints = _MOCK_HINTS.get(environment, _MOCK_HINTS["kubernetes"])
        # 다른 환경의 chaos_type 이 오면(예: Docker 시도에 Kubernetes 의 pod_failure) 쓰지 않는다.
        # 그 환경의 중립 답변으로 대신해야 Docker/Linux 에서 kubectl 을 안내하지 않는다.
        scenario = hints.get(chaos_type, hints["default"])
        return scenario.get(hint_level, scenario[0])

    def clear_history(self, attempt_id: uuid.UUID):
        pass  # 이제 DB가 단일 진실 공급원


# 싱글톤
_tutor_service: Optional[TutorService] = None


def get_tutor_service() -> TutorService:
    global _tutor_service
    if _tutor_service is None:
        _tutor_service = TutorService()
    return _tutor_service
