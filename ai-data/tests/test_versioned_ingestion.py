from copy import deepcopy

import pytest
from langchain.schema import Document
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams

import rag_service as rag_module
from config import AISettings
from ingest import attach_chunk_metadata
from rag_service import DocumentIngestionError, RAGService


def _document(source_id: str, content: str, chunk_index: int = 0) -> Document:
    return attach_chunk_metadata(
        [
            Document(
                page_content=content,
                metadata={
                    "source_id": source_id,
                    "source": f"{source_id}.md",
                    "version": "2026-08-29",
                    "environments": ["general"],
                    "fault_types": ["general"],
                },
            )
        ]
    )[0]


@pytest.fixture
def rag():
    return RAGService(
        collection_name="afterfail_knowledge_v2",
        use_memory=True,
        settings=AISettings(AI_BACKEND="mock"),
    )


def test_same_documents_are_idempotent(rag):
    documents = [_document("source-a", "alpha"), _document("source-b", "beta")]

    first = rag.sync_documents(documents)
    second = rag.sync_documents(deepcopy(documents))

    assert first.added == 2
    assert second.added == second.updated == second.deleted == 0
    assert second.unchanged == 2
    assert rag.get_collection_stats()["document_count"] == 2
    assert rag.needs_sync(documents) is False


def test_changed_source_replaces_only_its_stale_chunk(rag):
    original = [_document("source-a", "alpha"), _document("source-b", "beta")]
    rag.sync_documents(original)

    changed = [_document("source-a", "alpha changed"), _document("source-b", "beta")]
    assert rag.needs_sync(changed) is True
    report = rag.sync_documents(changed)

    assert report.updated == 1
    assert report.deleted == 1
    assert report.unchanged == 1
    assert report.added == 0
    assert rag.get_collection_stats()["document_count"] == 2
    assert rag.search_knowledge(
        "alpha changed", environment="kubernetes", top_k=2, min_similarity=0
    )[0].content


def test_point_id_uses_source_chunk_and_content_hash(rag):
    document = _document("source-a", "stable content")

    first = rag._point_id(document, 99)
    second = rag._point_id(deepcopy(document), 3)

    assert first == second


def test_dimension_mismatch_preserves_existing_collection(monkeypatch):
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="afterfail_knowledge_v2",
        vectors_config=VectorParams(size=8, distance=Distance.COSINE),
    )
    monkeypatch.setattr(rag_module, "QdrantClient", lambda *args, **kwargs: client)

    service = RAGService(
        collection_name="afterfail_knowledge_v2",
        use_memory=True,
        settings=AISettings(AI_BACKEND="mock"),
    )
    names = {collection.name for collection in client.get_collections().collections}

    assert "afterfail_knowledge_v2" in names
    assert service.collection_name in names
    assert service.collection_name != "afterfail_knowledge_v2"


def test_alias_changes_only_after_nonempty_collection(rag):
    with pytest.raises(DocumentIngestionError, match="빈 collection"):
        rag.promote_alias("afterfail_knowledge")

    rag.sync_documents([_document("source-a", "validated")])
    rag.promote_alias("afterfail_knowledge")

    aliases = {alias.alias_name: alias.collection_name for alias in rag.client.get_aliases().aliases}
    assert aliases["afterfail_knowledge"] == rag.collection_name


def test_failed_alias_switch_keeps_previous_alias(monkeypatch):
    client = QdrantClient(":memory:")
    client.create_collection(
        collection_name="previous_v1",
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
    )
    monkeypatch.setattr(rag_module, "QdrantClient", lambda *args, **kwargs: client)
    previous = RAGService(
        collection_name="previous_v1",
        use_memory=True,
        settings=AISettings(AI_BACKEND="mock"),
    )
    previous.sync_documents([_document("old", "old validated")])
    previous.promote_alias("afterfail_knowledge")

    candidate = RAGService(
        collection_name="candidate_v2",
        use_memory=True,
        settings=AISettings(AI_BACKEND="mock"),
    )
    candidate.sync_documents([_document("new", "new validated")])
    monkeypatch.setattr(
        client,
        "update_collection_aliases",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("switch failed")),
    )

    with pytest.raises(RuntimeError, match="switch failed"):
        candidate.promote_alias("afterfail_knowledge")

    aliases = {alias.alias_name: alias.collection_name for alias in client.get_aliases().aliases}
    assert aliases["afterfail_knowledge"] == "previous_v1"
