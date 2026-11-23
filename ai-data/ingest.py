"""Knowledge 문서 metadata 검증, 로딩, chunk 추적 공용 모듈."""

from __future__ import annotations

import hashlib
import json
import re
import warnings
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document


MANIFEST_FILENAME = "manifest.json"
SUPPORTED_ENVIRONMENTS = frozenset({"kubernetes", "docker", "linux", "general"})
ALLOWED_FAULT_TYPES = frozenset(
    {
        "general", "image_pull_error", "crash_loop", "oom_killed",
        "probe_failure", "liveness_probe_failure", "liveness_probe",
        "service_selector_mismatch", "configmap_misconfig",
        "init_container_failure", "node_selector_mismatch",
        "compound_probe_cascade", "compound_crash_service",
        "wrong_image_registry", "secret_ref_missing", "pvc_unbound",
        "cpu_throttle", "pod_failure", "memory_stress",
        "service_misconfig", "network_latency",
        "container_network_disconnect", "volume_mount_error",
        "container_oom", "container_cpu_throttle", "linux_disk_pressure",
        "linux_cpu_saturation", "linux_process_flood", "linux_oom",
        "disk_io_stress", "zombie_process", "orphan_process",
        "service_failure",
    }
)
MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
WARN_DOCUMENT_BYTES = 1024 * 1024
_SOURCE_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_VERSION_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_REQUIRED_FIELDS = {
    "source_id", "title", "environments", "fault_types", "authority", "version"
}


class MetadataValidationError(ValueError):
    """manifest 또는 문서 metadata가 계약과 맞지 않는다."""


# 기존 경로 기반 taxonomy를 호환·교차검증 용도로 유지한다.
# mapping이 없는 파일을 general로 암묵 처리하지 않는다.
FAULT_TYPE_TAGS: dict[str, list[str]] = {
    "troubleshooting/oomkilled": ["oom_killed", "memory_stress", "cpu_throttle"],
    "troubleshooting/crashloopbackoff": [
        "crash_loop", "pod_failure", "init_container_failure", "probe_failure",
        "liveness_probe_failure", "liveness_probe", "compound_probe_cascade", "configmap_misconfig",
        "secret_ref_missing", "network_latency",
    ],
    "troubleshooting/imagepullbackoff": [
        "image_pull_error", "wrong_image_registry", "pod_failure"
    ],
    "troubleshooting/pending-pods": ["node_selector_mismatch", "pvc_unbound"],
    "troubleshooting/service-misconfig": [
        "service_misconfig", "service_selector_mismatch", "compound_crash_service"
    ],
    "05-chaos-mesh/pod-chaos": [
        "pod_failure", "crash_loop", "oom_killed", "liveness_probe_failure", "liveness_probe",
        "init_container_failure", "configmap_misconfig",
    ],
    "02-komodor/incident-playbooks": ["general"],
    "02-komodor/log-patterns": ["general"],
    "06-prometheus/promql-queries": ["general"],
    "commands/kubectl-basics": ["general"],
    "01-kubernetes-docs/debugging-guide": ["general"],
    "01-kubernetes-docs/pod-states": ["general"],
    "03-kodekloud/architecture": ["general"],
    "04-cncf/resilience-patterns": ["general"],
    "07-docker/container-lifecycle": ["container_oom", "container_cpu_throttle"],
    "07-docker/diagnostic-commands": ["general"],
    "07-docker/network-troubleshooting": ["container_network_disconnect"],
    "07-docker/storage-troubleshooting": ["volume_mount_error"],
    "07-docker/resource-troubleshooting": ["container_oom", "container_cpu_throttle"],
    "07-docker/safe-recovery-playbook": [
        "container_network_disconnect", "volume_mount_error",
        "container_oom", "container_cpu_throttle",
    ],
    "08-linux/process-states": ["linux_process_flood", "zombie_process", "orphan_process"],
    "08-linux/oom-cgroup": ["linux_cpu_saturation", "linux_oom"],
    "08-linux/disk-io": ["linux_disk_pressure", "disk_io_stress"],
    "08-linux/resource-observation": ["linux_cpu_saturation", "linux_disk_pressure", "linux_oom", "disk_io_stress"],
    "08-linux/service-logs": ["service_failure"],
    "08-linux/network-sockets": ["service_failure"],
    "08-linux/safe-recovery-playbook": [
        "linux_disk_pressure", "linux_cpu_saturation", "linux_process_flood",
        "linux_oom", "disk_io_stress", "zombie_process",
        "orphan_process", "service_failure",
    ],
    "k8s_troubleshooting_guide": ["general"],
    "survival_camp_playbook": ["general"],
    "README.md": ["general"],
}


@dataclass(frozen=True)
class LoadReport:
    document_count: int
    chunk_count: int
    chunks_by_source: dict[str, int]


def get_fault_types(rel_path: str) -> list[str]:
    """경로 기반 fault tag를 반환하며, mapping 누락은 명시적으로 실패한다."""
    normalized = rel_path.replace("\\", "/")
    for key, tags in FAULT_TYPE_TAGS.items():
        if key in normalized:
            return list(tags)
    raise MetadataValidationError(f"fault type mapping이 없는 문서입니다: {normalized}")


def load_manifest(manifest_path: Path) -> dict[str, dict]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MetadataValidationError(f"metadata manifest가 없습니다: {manifest_path}") from exc
    except json.JSONDecodeError as exc:
        raise MetadataValidationError(f"metadata manifest JSON이 올바르지 않습니다: {exc}") from exc
    documents = payload.get("documents")
    if not isinstance(documents, dict):
        raise MetadataValidationError("manifest.documents는 object여야 합니다")
    return {str(path).replace("\\", "/"): metadata for path, metadata in documents.items()}


def _validate_string_list(source: str, field: str, value: object) -> list[str]:
    if not isinstance(value, list) or not value or not all(
        isinstance(item, str) and item for item in value
    ):
        raise MetadataValidationError(f"{source}: {field}는 비어 있지 않은 문자열 배열이어야 합니다")
    if len(set(value)) != len(value):
        raise MetadataValidationError(f"{source}: {field}에 중복 값이 있습니다")
    return value


def validate_manifest(manifest: dict[str, dict], document_paths: Iterable[str]) -> None:
    actual_paths = {path.replace("\\", "/") for path in document_paths}
    manifest_paths = set(manifest)
    missing = sorted(actual_paths - manifest_paths)
    extra = sorted(manifest_paths - actual_paths)
    if missing:
        raise MetadataValidationError(f"manifest mapping이 없는 문서: {', '.join(missing)}")
    if extra:
        raise MetadataValidationError(f"존재하지 않는 manifest 문서: {', '.join(extra)}")

    source_ids: dict[str, str] = {}
    for source, metadata in manifest.items():
        if not isinstance(metadata, dict):
            raise MetadataValidationError(f"{source}: metadata는 object여야 합니다")
        missing_fields = sorted(_REQUIRED_FIELDS - set(metadata))
        if missing_fields:
            raise MetadataValidationError(
                f"{source}: 필수 metadata 누락: {', '.join(missing_fields)}"
            )
        source_id = metadata["source_id"]
        if not isinstance(source_id, str) or not _SOURCE_ID_PATTERN.fullmatch(source_id):
            raise MetadataValidationError(f"{source}: source_id 형식이 올바르지 않습니다")
        if source_id in source_ids:
            raise MetadataValidationError(
                f"source_id 중복: {source_id} ({source_ids[source_id]}, {source})"
            )
        source_ids[source_id] = source
        if not isinstance(metadata["title"], str) or not metadata["title"].strip():
            raise MetadataValidationError(f"{source}: title이 비어 있습니다")

        environments = _validate_string_list(source, "environments", metadata["environments"])
        invalid_environments = sorted(set(environments) - SUPPORTED_ENVIRONMENTS)
        if invalid_environments:
            raise MetadataValidationError(
                f"{source}: 잘못된 environment: {', '.join(invalid_environments)}"
            )
        fault_types = _validate_string_list(source, "fault_types", metadata["fault_types"])
        invalid_faults = sorted(set(fault_types) - ALLOWED_FAULT_TYPES)
        if invalid_faults:
            raise MetadataValidationError(
                f"{source}: 잘못된 fault type: {', '.join(invalid_faults)}"
            )
        if set(fault_types) != set(get_fault_types(source)):
            raise MetadataValidationError(
                f"{source}: manifest fault_types가 FAULT_TYPE_TAGS와 일치하지 않습니다"
            )

        authority = metadata["authority"]
        if (
            isinstance(authority, bool)
            or not isinstance(authority, (int, float))
            or not 0 <= authority <= 1
        ):
            raise MetadataValidationError(f"{source}: authority는 0과 1 사이 숫자여야 합니다")
        version = metadata["version"]
        if not isinstance(version, str) or not _VERSION_PATTERN.fullmatch(version):
            raise MetadataValidationError(f"{source}: version은 YYYY-MM-DD 형식이어야 합니다")


def load_all_documents(kb_dir: Path, manifest_path: Path | None = None) -> list[Document]:
    """manifest 검증 후 모든 Markdown 문서를 결정적 경로 순서로 로드한다."""
    kb_dir = Path(kb_dir)
    markdown_files = sorted(kb_dir.rglob("*.md"))
    relative_paths = [path.relative_to(kb_dir).as_posix() for path in markdown_files]
    manifest = load_manifest(manifest_path or kb_dir / MANIFEST_FILENAME)
    validate_manifest(manifest, relative_paths)

    documents: list[Document] = []
    for md_file, source in zip(markdown_files, relative_paths):
        raw = md_file.read_bytes()
        if not raw.strip():
            raise MetadataValidationError(f"내용이 비어 있는 문서입니다: {source}")
        if len(raw) > MAX_DOCUMENT_BYTES:
            raise MetadataValidationError(
                f"문서 크기가 {MAX_DOCUMENT_BYTES} bytes 제한을 초과했습니다: {source}"
            )
        if len(raw) > WARN_DOCUMENT_BYTES:
            warnings.warn(f"큰 문서입니다 ({len(raw)} bytes): {source}", stacklevel=2)
        try:
            content = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MetadataValidationError(f"UTF-8 문서가 아닙니다: {source}") from exc

        declared = manifest[source]
        metadata = {
            **declared,
            "source": source,
            "filepath": str(md_file),
            "category": Path(source).parts[0] if len(Path(source).parts) > 1 else "root",
            "content_type": "knowledge",
            "updated_at": declared["version"],
            "language": "ko",
        }
        documents.append(Document(page_content=content, metadata=metadata))
    return documents


def attach_chunk_metadata(chunks: Iterable[Document]) -> list[Document]:
    """source별 chunk_index와 내용 기반 SHA-256 hash를 붙인다."""
    indexes: Counter[str] = Counter()
    annotated: list[Document] = []
    for chunk in chunks:
        source = chunk.metadata.get("source")
        if not isinstance(source, str) or not source:
            raise MetadataValidationError("chunk에 source metadata가 없습니다")
        metadata = dict(chunk.metadata)
        metadata["chunk_index"] = indexes[source]
        metadata["content_hash"] = hashlib.sha256(
            chunk.page_content.encode("utf-8")
        ).hexdigest()
        indexes[source] += 1
        annotated.append(Document(page_content=chunk.page_content, metadata=metadata))
    return annotated


def build_load_report(
    documents: Iterable[Document], chunks: Iterable[Document] = ()
) -> LoadReport:
    document_list = list(documents)
    chunk_list = list(chunks)
    counts = Counter(str(chunk.metadata.get("source", "unknown")) for chunk in chunk_list)
    return LoadReport(
        document_count=len(document_list),
        chunk_count=len(chunk_list),
        chunks_by_source=dict(sorted(counts.items())),
    )
