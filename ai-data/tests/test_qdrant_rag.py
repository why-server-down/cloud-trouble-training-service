"""
Test suite for Qdrant-based RAG Service
Tests document ingestion, search, and error handling
"""

from types import SimpleNamespace

import pytest
from langchain.schema import Document
from config import AISettings
from rag_service import (
    RAGService,
    RAGServiceError,
    QdrantConnectionError,
    DocumentIngestionError,
    SearchError
)
from tests.fakes import DeterministicFakeEmbeddings


@pytest.fixture
def rag_service():
    """Create RAG service with in-memory Qdrant for testing"""
    service = RAGService(
        collection_name="test_k8s_docs",
        use_memory=True,
        settings=AISettings(AI_BACKEND="mock", RAG_MIN_SIMILARITY=0.1),
    )
    service.embeddings = DeterministicFakeEmbeddings(service.EMBEDDING_DIMENSION)
    return service


@pytest.fixture
def sample_documents():
    """Sample documents for testing"""
    return [
        Document(
            page_content="Pod is in CrashLoopBackOff status. Check logs with kubectl logs.",
            metadata={"source": "troubleshooting.md", "type": "guide", "environments": ["kubernetes"]}
        ),
        Document(
            page_content="ImagePullBackOff means the image cannot be pulled. Check image name and registry.",
            metadata={"source": "errors.md", "type": "guide", "environments": ["kubernetes"]}
        ),
        Document(
            page_content="Use kubectl describe pod to see detailed pod information and events.",
            metadata={"source": "commands.md", "type": "reference", "environments": ["kubernetes"]}
        )
    ]


class TestRAGServiceInitialization:
    """Test RAG service initialization"""
    
    def test_initialization_success(self, rag_service):
        """Test successful initialization"""
        assert rag_service is not None
        assert rag_service.collection_name == "test_k8s_docs"
        assert rag_service.EMBEDDING_DIMENSION == 1536
    
    def test_collection_creation(self, rag_service):
        """Test collection is created"""
        stats = rag_service.get_collection_stats()
        assert stats["collection_name"] == "test_k8s_docs"
        assert stats["document_count"] == 0
        assert stats["vector_dimension"] == 1536
        assert stats["distance_metric"] == "cosine"


class TestDocumentIngestion:
    """Test document ingestion"""
    
    def test_ingest_documents(self, rag_service, sample_documents):
        """Test ingesting documents"""
        count = rag_service.ingest_documents(sample_documents)
        assert count == 3
        
        stats = rag_service.get_collection_stats()
        assert stats["document_count"] == 3
    
    def test_ingest_empty_list(self, rag_service):
        """Test ingesting empty document list"""
        count = rag_service.ingest_documents([])
        assert count == 0
    
    def test_ingest_with_metadata(self, rag_service):
        """Test documents are stored with metadata"""
        docs = [
            Document(
                page_content="Test content",
                metadata={"source": "test.md", "custom_field": "value", "environments": ["general"]}
            )
        ]
        count = rag_service.ingest_documents(docs)
        assert count == 1
        
        # Search to verify metadata
        results = rag_service.search_knowledge(
            "Test content", environment="kubernetes", top_k=1
        )
        assert len(results) > 0
        assert results[0].metadata["source"] == "test.md"
        assert results[0].metadata["custom_field"] == "value"
        assert results[0].metadata["environments"] == ["general"]


class TestSearch:
    """Test search functionality"""
    
    def test_search_relevant_documents(self, rag_service, sample_documents):
        """Test searching for relevant documents"""
        # Ingest documents
        rag_service.ingest_documents(sample_documents)
        
        # Search
        results = rag_service.search_knowledge(
            "Pod CrashLoopBackOff", environment="kubernetes", top_k=2
        )
        
        assert len(results) > 0
        assert results[0].similarity > 0.2
        assert "CrashLoopBackOff" in results[0].content
    
    def test_search_with_top_k(self, rag_service, sample_documents):
        """Test search with top_k parameter"""
        rag_service.ingest_documents(sample_documents)
        
        results = rag_service.search_knowledge(
            "kubectl", environment="kubernetes", top_k=1
        )
        assert len(results) <= 1
    
    def test_search_with_min_similarity(self, rag_service, sample_documents):
        """Test search with minimum similarity threshold"""
        rag_service.ingest_documents(sample_documents)
        
        results = rag_service.search_knowledge(
            "completely unrelated query xyz123",
            environment="kubernetes",
            min_similarity=0.9
        )
        # Should return few or no results due to high threshold
        assert len(results) == 0 or results[0].similarity >= 0.9
    
    def test_search_with_source_filter(self, rag_service, sample_documents):
        """Test search with source metadata filter"""
        rag_service.ingest_documents(sample_documents)
        
        results = rag_service.search_knowledge(
            "kubectl",
            environment="kubernetes",
            filter_source="commands.md"
        )
        
        if len(results) > 0:
            assert all(r.source == "commands.md" for r in results)

    def test_fault_filter_excludes_other_fault_documents(self, rag_service):
        documents = [
            Document(
                page_content="CrashLoop logs and restart count",
                metadata={"source": "crash.md", "fault_types": ["crash_loop"], "environments": ["kubernetes"]},
            ),
            Document(
                page_content="CrashLoop and image registry",
                metadata={"source": "image.md", "fault_types": ["image_pull_error"], "environments": ["kubernetes"]},
            ),
            Document(
                page_content="General diagnostic workflow",
                metadata={"source": "general.md", "fault_types": ["general"], "environments": ["general"]},
            ),
        ]
        rag_service.ingest_documents(documents)

        results = rag_service.search_knowledge(
            "CrashLoop logs", environment="kubernetes", fault_type="crash_loop", min_similarity=0
        )

        assert {result.source for result in results} == {"crash.md", "general.md"}

    def test_environment_and_fault_filters_are_combined(self, rag_service):
        documents = [
            Document(
                page_content="Docker network disconnect",
                metadata={
                    "source": "docker.md",
                    "environments": ["docker"],
                    "fault_types": ["container_network_disconnect"],
                },
            ),
            Document(
                page_content="Kubernetes network disconnect",
                metadata={
                    "source": "kubernetes.md",
                    "environments": ["kubernetes"],
                    "fault_types": ["container_network_disconnect"],
                },
            ),
            Document(
                page_content="General network workflow",
                metadata={
                    "source": "general.md",
                    "environments": ["general"],
                    "fault_types": ["general"],
                },
            ),
        ]
        rag_service.ingest_documents(documents)

        results = rag_service.search_knowledge(
            "network disconnect",
            environment="docker",
            fault_type="container_network_disconnect",
            top_k=5,
            min_similarity=0,
        )

        assert {result.source for result in results} == {"docker.md", "general.md"}

    @pytest.mark.parametrize("environment", [None, "", "application", "Docker"])
    def test_missing_or_invalid_environment_is_rejected(self, rag_service, environment):
        with pytest.raises(SearchError, match="environment"):
            rag_service.search_knowledge("query", environment=environment)

    def test_explicit_zero_top_k_is_not_replaced_by_default(self, rag_service):
        results = rag_service.search_knowledge(
            "query", environment="kubernetes", top_k=0, min_similarity=0
        )

        assert results == []

    def test_hybrid_reranking_promotes_exact_command_and_records_scores(
        self, rag_service, monkeypatch
    ):
        captured = {}

        def query_points(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                points=[
                    SimpleNamespace(
                        score=0.90,
                        payload={
                            "source": "general.md",
                            "source_id": "general",
                            "title": "일반 점검",
                            "content": "서비스 상태를 차례로 확인합니다",
                            "authority": 0.25,
                        },
                    ),
                    SimpleNamespace(
                        score=0.85,
                        payload={
                            "source": "command.md",
                            "source_id": "command",
                            "title": "kubectl describe pod 명령",
                            "content": "kubectl describe pod 로 Events를 확인합니다",
                            "authority": 1.0,
                        },
                    ),
                ]
            )

        monkeypatch.setattr(rag_service.client, "query_points", query_points)

        first = rag_service.search_knowledge(
            "kubectl describe pod",
            environment="kubernetes",
            top_k=2,
            min_similarity=0,
        )
        second = rag_service.search_knowledge(
            "kubectl describe pod",
            environment="kubernetes",
            top_k=2,
            min_similarity=0,
        )

        assert captured["limit"] == 20
        assert [document.source for document in first] == ["command.md", "general.md"]
        assert [document.source for document in second] == ["command.md", "general.md"]
        assert first[0].metadata["semantic_score"] == 0.85
        assert first[0].metadata["keyword_score"] == 1.0
        assert first[0].metadata["final_score"] == pytest.approx(0.8875)

    def test_reranking_can_be_disabled_for_vector_baseline(
        self, rag_service, monkeypatch
    ):
        captured = {}

        def query_points(**kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                points=[
                    SimpleNamespace(
                        score=0.8,
                        payload={"source": "vector.md", "content": "vector"},
                    )
                ]
            )

        monkeypatch.setattr(rag_service.client, "query_points", query_points)

        results = rag_service.search_knowledge(
            "query",
            environment="kubernetes",
            top_k=3,
            min_similarity=0,
            rerank=False,
        )

        assert captured["limit"] == 3
        assert results[0].metadata["semantic_score"] == 0.8
        assert results[0].metadata["final_score"] == 0.8
    
    def test_search_empty_collection(self, rag_service):
        """Test search on empty collection"""
        results = rag_service.search_knowledge("test query", environment="kubernetes")
        assert len(results) == 0


class TestAugmentPrompt:
    """Test prompt augmentation"""
    
    def test_augment_prompt_with_knowledge(self, rag_service, sample_documents):
        """Test augmenting prompt with retrieved knowledge"""
        rag_service.ingest_documents(sample_documents)
        
        base_prompt = "You are a helpful assistant."
        user_question = "Why is my pod crashing?"
        
        augmented = rag_service.augment_prompt(
            base_prompt, user_question, environment="kubernetes", top_k=2
        )
        
        assert base_prompt in augmented
        assert user_question in augmented
        assert "RELEVANT DOCUMENTATION" in augmented
    
    def test_augment_prompt_no_results(self, rag_service):
        """Test augmenting prompt when no documents found"""
        base_prompt = "You are a helpful assistant."
        user_question = "Test question"
        
        augmented = rag_service.augment_prompt(
            base_prompt, user_question, environment="kubernetes"
        )
        
        # Should return base prompt when no docs found
        assert base_prompt in augmented


class TestCollectionManagement:
    """Test collection management operations"""
    
    def test_clear_collection(self, rag_service, sample_documents):
        """Test clearing collection"""
        # Add documents
        rag_service.ingest_documents(sample_documents)
        stats = rag_service.get_collection_stats()
        assert stats["document_count"] == 3
        
        # Clear collection
        rag_service.clear_collection()
        stats = rag_service.get_collection_stats()
        assert stats["document_count"] == 0
    
    def test_get_collection_stats(self, rag_service):
        """Test getting collection statistics"""
        stats = rag_service.get_collection_stats()
        
        assert "collection_name" in stats
        assert "document_count" in stats
        assert "vector_dimension" in stats
        assert "distance_metric" in stats
        assert stats["vector_dimension"] == 1536
        assert stats["distance_metric"] == "cosine"


class TestDocumentLoading:
    """Test document loading from files"""
    
    def test_load_documents_directory_not_found(self, rag_service):
        """Test loading from non-existent directory"""
        with pytest.raises(RAGServiceError, match="Directory not found"):
            rag_service.load_documents("./nonexistent-directory")
    
    def test_chunk_documents(self, rag_service, sample_documents):
        """Test document chunking"""
        chunks = rag_service.chunk_documents(sample_documents, chunk_size=50, chunk_overlap=10)
        
        # Should create chunks
        assert len(chunks) >= len(sample_documents)
    
    def test_chunk_empty_documents(self, rag_service):
        """Test chunking empty document list"""
        chunks = rag_service.chunk_documents([])
        assert len(chunks) == 0


class TestErrorHandling:
    """Test error handling"""
    
    def test_invalid_api_key(self, monkeypatch):
        """Test initialization with invalid API key"""
        # This test would require mocking config
        # Skipping for now as it requires environment setup
        pass
    
    def test_search_error_handling(self, rag_service):
        """Test search error handling"""
        # Search should not raise error even with invalid query
        try:
            results = rag_service.search_knowledge("", environment="kubernetes")
            assert isinstance(results, list)
        except SearchError:
            # SearchError is acceptable
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
