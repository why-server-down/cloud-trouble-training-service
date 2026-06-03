"""
각 chaos_type의 inject → K8s 상태 확인 → revert 순차 테스트.
실행: cd backend && source venv/bin/activate && python test_chaos.py
"""
import asyncio
import subprocess
import sys
import time

NS = "chaos-test"

# fmt: off
CHAOS_TYPES = [
    ("crash_loop",             "CrashLoopBackOff"),
    ("liveness_probe",         "RESTARTS 증가"),
    ("init_container_failure", "Init:CrashLoopBackOff"),
    ("node_selector_mismatch", "Pending"),
    ("configmap_misconfig",    "CrashLoopBackOff (nginx conf 오류)"),
    ("compound_probe_cascade", "ImagePullBackOff → 수정 후 Not Ready"),
    ("compound_crash_service", "CrashLoop + webapp-svc endpoints 0"),
    # 신규 타입
    ("wrong_image_registry",   "ImagePullBackOff (unauthorized)"),
    ("secret_ref_missing",     "CreateContainerConfigError"),
    ("pvc_unbound",            "Pod Pending (PVC 바인딩 대기)"),
    ("cpu_throttle",           "Running이지만 READY 0/1"),
    # 기존 메서드도 포함
    ("pod_failure",            "ImagePullBackOff"),
    ("memory_stress",          "OOMKilled"),
    ("service_misconfig",      "webapp-svc endpoints 0"),
    ("network_latency",        "nginx Not Ready"),
]
# fmt: on

RESET = "\033[0m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"


def p(color, msg):
    print(f"{color}{msg}{RESET}")


def kubectl(args: list[str]) -> str:
    result = subprocess.run(
        ["kubectl"] + args + ["-n", NS],
        capture_output=True, text=True, timeout=15
    )
    return (result.stdout + result.stderr).strip()


def show_state(label: str):
    pods = kubectl(["get", "pods", "-o", "wide"])
    p(CYAN, f"  [{label}] pods:\n{pods}")


async def test_chaos_type(injector, chaos_type: str, description: str) -> bool:
    p(BOLD, f"\n{'='*60}")
    p(BOLD, f"  chaos_type: {chaos_type}")
    p(YELLOW, f"  기대 증상: {description}")
    p(BOLD, f"{'='*60}")

    # ── inject ──────────────────────────────────────────────
    p(CYAN, "  [1/4] inject 시작...")
    result = await injector.inject(chaos_type, NS)
    if not result.success:
        p(RED, f"  ✗ inject 실패: {result.message}")
        return False
    p(GREEN, f"  ✓ inject 성공 (chaos_id={result.chaos_id})")

    # ── 상태 관찰 (15초) ─────────────────────────────────────
    p(CYAN, "  [2/4] 15초 대기 후 상태 확인...")
    await asyncio.sleep(15)
    show_state("주입 후")

    # compound_crash_service는 webapp-svc endpoint도 확인
    if chaos_type == "compound_crash_service":
        ep = kubectl(["get", "endpoints", "webapp-svc"])
        p(CYAN, f"  webapp-svc endpoints:\n{ep}")

    # ── revert ───────────────────────────────────────────────
    p(CYAN, "  [3/4] revert 시작...")
    reverted = await injector.revert(result.chaos_id)
    if not reverted:
        p(RED, "  ✗ revert 실패")
        return False
    p(GREEN, "  ✓ revert 성공")

    # ── 복구 확인 (30초) ─────────────────────────────────────
    p(CYAN, "  [4/4] 30초 대기 후 복구 확인...")
    await asyncio.sleep(30)
    show_state("복구 후")

    return True


async def main():
    # sys.path에 backend 루트 추가
    import os
    sys.path.insert(0, os.path.dirname(__file__))

    # K8s 환경변수 강제 설정 (테스트용)
    os.environ.setdefault("CHAOS_BACKEND", "chaos_mesh")
    os.environ.setdefault("VALIDATION_BACKEND", "k8s")
    os.environ.setdefault("AI_BACKEND", "mock")
    os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/k8s_survival")
    os.environ.setdefault("SECRET_KEY", "test-secret-key-for-chaos-testing")

    from app.services.chaos_injector import ChaosMeshInjector
    injector = ChaosMeshInjector()

    # 테스트할 타입 선택 (인수로 지정하거나 전체 실행)
    target_types = sys.argv[1:] if len(sys.argv) > 1 else None

    results: list[tuple[str, bool]] = []

    for chaos_type, description in CHAOS_TYPES:
        if target_types and chaos_type not in target_types:
            continue

        # nginx 정상 확인
        p(CYAN, f"\n  nginx 정상 상태 확인 중...")
        kubectl(["rollout", "status", "deployment/nginx", "--timeout=30s"])

        ok = await test_chaos_type(injector, chaos_type, description)
        results.append((chaos_type, ok))

        # 다음 테스트 전 nginx 완전 복구 대기
        p(CYAN, "  다음 테스트 전 nginx rollout 대기...")
        kubectl(["rollout", "status", "deployment/nginx", "--timeout=60s"])

    # ── 결과 요약 ────────────────────────────────────────────
    p(BOLD, f"\n{'='*60}")
    p(BOLD, "  테스트 결과 요약")
    p(BOLD, f"{'='*60}")
    passed = 0
    for ct, ok in results:
        mark = f"{GREEN}PASS{RESET}" if ok else f"{RED}FAIL{RESET}"
        print(f"  {mark}  {ct}")
        if ok:
            passed += 1
    p(BOLD, f"\n  {passed}/{len(results)} 통과")


if __name__ == "__main__":
    asyncio.run(main())
