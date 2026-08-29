import copy
import json
from pathlib import Path

import pytest
from langchain_text_splitters import RecursiveCharacterTextSplitter

import ingest
from ingest import (
    MetadataValidationError,
    attach_chunk_metadata,
    build_load_report,
    load_all_documents,
    load_manifest,
    validate_manifest,
)


AI_DATA_DIR = Path(__file__).resolve().parents[1]
KNOWLEDGE_BASE_DIR = AI_DATA_DIR / "knowledge-base"


def _metadata(
    *,
    source_id="test-source",
    environments=None,
    fault_types=None,
):
    return {
        "source_id": source_id,
        "title": "테스트 문서",
        "environments": environments or ["kubernetes"],
        "fault_types": fault_types or ["oom_killed", "memory_stress", "cpu_throttle"],
        "authority": 0.9,
        "version": "2026-08-29",
    }


def _write_fixture(kb_dir: Path, documents: dict[str, tuple[str, dict]]) -> None:
    manifest = {"schema_version": "1.0", "documents": {}}
    for source, (content, metadata) in documents.items():
        path = kb_dir / source
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        manifest["documents"][source] = metadata
    (kb_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False), encoding="utf-8"
    )


def test_existing_kubernetes_documents_all_have_valid_metadata():
    documents = load_all_documents(KNOWLEDGE_BASE_DIR)
    kubernetes_documents = [
        document
        for document in documents
        if document.metadata["environments"] == ["kubernetes"]
    ]

    assert len(documents) == 30
    assert len(kubernetes_documents) == 17
    assert len({document.metadata["source_id"] for document in documents}) == 30
    for document in documents:
        assert document.metadata["title"]
        assert document.metadata["fault_types"]
        assert 0 <= document.metadata["authority"] <= 1
        assert document.metadata["version"] == "2026-08-29"


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("environments", ["application"], "잘못된 environment"),
        ("fault_types", ["unknown_fault"], "잘못된 fault type"),
    ],
)
def test_invalid_environment_or_fault_fails(field, value, message):
    manifest = load_manifest(KNOWLEDGE_BASE_DIR / "manifest.json")
    broken = copy.deepcopy(manifest)
    broken["troubleshooting/oomkilled.md"][field] = value

    with pytest.raises(MetadataValidationError, match=message):
        validate_manifest(broken, manifest.keys())


def test_duplicate_source_id_fails():
    manifest = load_manifest(KNOWLEDGE_BASE_DIR / "manifest.json")
    broken = copy.deepcopy(manifest)
    broken["README.md"]["source_id"] = broken[
        "01-kubernetes-docs/debugging-guide.md"
    ]["source_id"]

    with pytest.raises(MetadataValidationError, match="source_id 중복"):
        validate_manifest(broken, manifest.keys())


def test_unmapped_document_is_not_silently_general(tmp_path):
    _write_fixture(
        tmp_path,
        {"unmapped.md": ("내용", _metadata(fault_types=["general"]))},
    )

    with pytest.raises(MetadataValidationError, match="fault type mapping이 없는"):
        load_all_documents(tmp_path)


def test_manifest_missing_document_mapping_fails(tmp_path):
    _write_fixture(
        tmp_path,
        {
            "troubleshooting/oomkilled.md": ("OOM 내용", _metadata()),
        },
    )
    extra = tmp_path / "troubleshooting" / "extra.md"
    extra.write_text("추가 문서", encoding="utf-8")

    with pytest.raises(MetadataValidationError, match="manifest mapping이 없는"):
        load_all_documents(tmp_path)


def test_empty_and_oversized_documents_are_rejected(tmp_path, monkeypatch):
    _write_fixture(
        tmp_path,
        {"troubleshooting/oomkilled.md": (" ", _metadata())},
    )
    with pytest.raises(MetadataValidationError, match="내용이 비어"):
        load_all_documents(tmp_path)

    document = tmp_path / "troubleshooting" / "oomkilled.md"
    document.write_text("12345", encoding="utf-8")
    monkeypatch.setattr(ingest, "MAX_DOCUMENT_BYTES", 4)
    with pytest.raises(MetadataValidationError, match="제한을 초과"):
        load_all_documents(tmp_path)


def test_chunks_have_index_hash_and_source_report():
    documents = load_all_documents(KNOWLEDGE_BASE_DIR)
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=100)
    chunks = attach_chunk_metadata(splitter.split_documents(documents))
    report = build_load_report(documents, chunks)

    assert report.document_count == 30
    assert report.chunk_count == len(chunks)
    assert set(report.chunks_by_source) == {
        document.metadata["source"] for document in documents
    }
    indexes_by_source: dict[str, list[int]] = {}
    for chunk in chunks:
        source = chunk.metadata["source"]
        indexes_by_source.setdefault(source, []).append(chunk.metadata["chunk_index"])
        assert len(chunk.metadata["content_hash"]) == 64
    for indexes in indexes_by_source.values():
        assert indexes == list(range(len(indexes)))
