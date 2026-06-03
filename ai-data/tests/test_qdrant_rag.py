"""
Test suite for Qdrant-based RAG Service
Tests document ingestion, search, and error handling
"""

import pytest
from langchain.schema import Document
from rag_service import (
    RAGService,
    RAGServiceError,
    QdrantConnectionError,
    DocumentIngestionError,
    SearchError
)


@pytest.fixture
def rag_service():
    """Create RAG service with in-memory Qdrant for testing"""
    return RAGService(
        collection_name="test_k8s_docs",
        use_memory=True  # Use in-memory mode for tests
    )


@pytest.fixture
def sample_documents():
    """Sample documents for testing"""
    return [
        Document(
            page_content="Pod is in CrashLoopBackOff status. Check logs with kubectl logs.",
            metadata={"source": "troubleshooting.md", "type": "guide"}
        ),
        Document(
            page_content="ImagePullBackOff means the image cannot be pulled. Check image name and registry.",
            metadata={"source": "errors.md", "type": "guide"}
        ),
        Document(
            page_content="Use kubectl describe pod to see detailed pod information and events.",
            metadata={"source": "commands.md", "type": "reference"}
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
                metadata={"source": "test.md", "custom_field": "value"}
            )
        ]
        count = rag_service.ingest_documents(docs)
        assert count == 1
        
        # Search to verify metadata
        results = rag_service.search_knowledge("Test content", top_k=1)
        assert len(results) > 0
        assert results[0].metadata["source"] == "test.md"
        assert results[0].metadata["custom_field"] == "value"


class TestSearch:
    """Test search functionality"""
    
    def test_search_relevant_documents(self, rag_service, sample_documents):
        """Test searching for relevant documents"""
        # Ingest documents
        rag_service.ingest_documents(sample_documents)
        
        # Search
        results = rag_service.search_knowledge("Pod CrashLoopBackOff", top_k=2)
        
        assert len(results) > 0
        assert results[0].similarity > 0.5
        assert "CrashLoopBackOff" in results[0].content
    
    def test_search_with_top_k(self, rag_service, sample_documents):
        """Test search with top_k parameter"""
        rag_service.ingest_documents(sample_documents)
        
        results = rag_service.search_knowledge("kubectl", top_k=1)
        assert len(results) <= 1
    
    def test_search_with_min_similarity(self, rag_service, sample_documents):
        """Test search with minimum similarity threshold"""
        rag_service.ingest_documents(sample_documents)
        
        results = rag_service.search_knowledge(
            "completely unrelated query xyz123",
            min_similarity=0.9
        )
        # Should return few or no results due to high threshold
        assert len(results) == 0 or results[0].similarity >= 0.9
    
    def test_search_with_source_filter(self, rag_service, sample_documents):
        """Test search with source metadata filter"""
        rag_service.ingest_documents(sample_documents)
        
        results = rag_service.search_knowledge(
            "kubectl",
            filter_source="commands.md"
        )
        
        if len(results) > 0:
            assert all(r.source == "commands.md" for r in results)
    
    def test_search_empty_collection(self, rag_service):
        """Test search on empty collection"""
        results = rag_service.search_knowledge("test query")
        assert len(results) == 0


class TestAugmentPrompt:
    """Test prompt augmentation"""
    
    def test_augment_prompt_with_knowledge(self, rag_service, sample_documents):
        """Test augmenting prompt with retrieved knowledge"""
        rag_service.ingest_documents(sample_documents)
        
        base_prompt = "You are a helpful assistant."
        user_question = "Why is my pod crashing?"
        
        augmented = rag_service.augment_prompt(base_prompt, user_question, top_k=2)
        
        assert base_prompt in augmented
        assert user_question in augmented
        assert "RELEVANT DOCUMENTATION" in augmented
    
    def test_augment_prompt_no_results(self, rag_service):
        """Test augmenting prompt when no documents found"""
        base_prompt = "You are a helpful assistant."
        user_question = "Test question"
        
        augmented = rag_service.augment_prompt(base_prompt, user_question)
        
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
            results = rag_service.search_knowledge("")
            assert isinstance(results, list)
        except SearchError:
            # SearchError is acceptable
            pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
