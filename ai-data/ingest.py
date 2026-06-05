"""
Knowledge-base 문서 로딩 및 fault_type 태그 맵핑 공용 모듈.
scripts/ingest_knowledge.py 와 backend의 자동 ingestion 서비스가 함께 사용한다.
"""

from pathlib import Path

try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document


# 파일 경로(부분 매칭) → fault_types 매핑
# "general" 태그: 장애 유형과 무관하게 항상 검색에 포함
FAULT_TYPE_TAGS: dict[str, list[str]] = {
    "troubleshooting/oomkilled":          ["oom_killed", "memory_stress", "cpu_throttle"],
    "troubleshooting/crashloopbackoff":   ["crash_loop", "pod_failure", "init_container_failure",
                                           "probe_failure", "liveness_probe_failure", "liveness_probe",
                                           "compound_probe_cascade", "configmap_misconfig",
                                           "secret_ref_missing", "network_latency"],
    "troubleshooting/imagepullbackoff":   ["image_pull_error", "wrong_image_registry", "pod_failure"],
    "troubleshooting/pending-pods":       ["node_selector_mismatch", "pvc_unbound"],
    "troubleshooting/service-misconfig":  ["service_misconfig", "service_selector_mismatch",
                                           "compound_crash_service"],
    "05-chaos-mesh/pod-chaos":            ["pod_failure", "crash_loop", "oom_killed",
                                           "liveness_probe_failure", "liveness_probe",
                                           "init_container_failure", "configmap_misconfig"],
    "02-komodor/incident-playbooks":      ["general"],
    "02-komodor/log-patterns":            ["general"],
    "06-prometheus/promql-queries":       ["general"],
    "commands/kubectl-basics":            ["general"],
}


def get_fault_types(rel_path: str) -> list[str]:
    """파일 경로 기반 fault_type 태그 반환. 매핑 없으면 general."""
    rel_normalized = rel_path.replace("\\", "/")
    for key, tags in FAULT_TYPE_TAGS.items():
        if key in rel_normalized:
            return tags
    return ["general"]


def load_all_documents(kb_dir: Path) -> list:
    """knowledge-base 디렉토리에서 모든 마크다운 파일을 재귀적으로 로드한다."""
    docs = []
    for md_file in kb_dir.rglob("*.md"):
        try:
            with open(md_file, "r", encoding="utf-8") as f:
                content = f.read()

            rel_path = md_file.relative_to(kb_dir)
            rel_str = str(rel_path)
            fault_types = get_fault_types(rel_str)

            docs.append(Document(
                page_content=content,
                metadata={
                    "source": rel_str,
                    "type": "markdown",
                    "filepath": str(md_file),
                    "category": rel_path.parts[0] if len(rel_path.parts) > 1 else "root",
                    "fault_types": fault_types,
                },
            ))
        except Exception as e:
            print(f"Warning: Failed to load {md_file}: {e}")

    return docs
