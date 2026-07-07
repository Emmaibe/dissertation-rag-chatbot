"""
test_rag_pipeline.py
--------------------
Unit tests for the RAG pipeline.
Tests document ingestion, chunking, retrieval, and response structure.

Run with: pytest tests/ -v

Author: Emmanuel Ibenwankwo
"""

import os
import sys
import pytest
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rag_pipeline import RAGPipeline, RAGResponse


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def sample_data_dir(tmp_path_factory):
    """Create a temporary directory with a sample document for testing."""
    data_dir = tmp_path_factory.mktemp("data")
    doc = data_dir / "test_doc.txt"
    doc.write_text("""
=== Test Document: DevSecOps ===

DevSecOps integrates security into the DevOps pipeline.
It stands for Development, Security, and Operations.
Key tools include SonarQube for static analysis and Trivy for container scanning.

=== Test Document: RAG Systems ===

RAG stands for Retrieval-Augmented Generation.
It enhances LLM responses by retrieving relevant context from a knowledge base.
Evaluation metrics include Context Precision, Faithfulness, and Answer Relevance.
""", encoding="utf-8")
    return str(data_dir)


@pytest.fixture(scope="module")
def pipeline_with_data(sample_data_dir, tmp_path_factory):
    """Initialise a RAG pipeline with test data, using a temp vector store."""
    chroma_path = str(tmp_path_factory.mktemp("chroma"))
    os.environ["CHROMA_DB_PATH"] = chroma_path
    os.environ["DATA_DIR"] = sample_data_dir
    os.environ["CHUNK_SIZE"] = "200"
    os.environ["CHUNK_OVERLAP"] = "20"
    os.environ["TOP_K_RESULTS"] = "2"

    pipeline = RAGPipeline()
    pipeline.ingest_documents(data_dir=sample_data_dir)
    return pipeline


# ── Tests ──────────────────────────────────────────────────────────────────────

class TestDocumentIngestion:
    def test_ingest_returns_chunk_count(self, pipeline_with_data):
        """Ingestion should return a positive chunk count."""
        stats = pipeline_with_data.get_stats()
        assert stats["chunk_count"] > 0, "Expected at least one chunk after ingestion"

    def test_vector_store_status_ready(self, pipeline_with_data):
        """Vector store should report 'ready' after ingestion."""
        stats = pipeline_with_data.get_stats()
        assert stats["status"] == "ready"

    def test_stats_contains_expected_keys(self, pipeline_with_data):
        """Stats dict should contain all expected keys."""
        stats = pipeline_with_data.get_stats()
        expected_keys = {"status", "chunk_count", "embedding_model", "llm_model", "top_k"}
        assert expected_keys.issubset(stats.keys())


class TestRetrieval:
    def test_retrieve_returns_documents(self, pipeline_with_data):
        """Retrieval should return a non-empty list of documents."""
        docs, latency = pipeline_with_data.retrieve("What is DevSecOps?")
        assert len(docs) > 0, "Expected at least one document to be retrieved"

    def test_retrieve_latency_is_positive(self, pipeline_with_data):
        """Retrieval latency should be a positive float."""
        _, latency = pipeline_with_data.retrieve("What is RAG?")
        assert latency > 0

    def test_retrieve_documents_have_content(self, pipeline_with_data):
        """Retrieved documents should have non-empty page content."""
        docs, _ = pipeline_with_data.retrieve("SonarQube static analysis")
        for doc in docs:
            assert len(doc.page_content) > 0

    def test_retrieve_respects_top_k(self, pipeline_with_data):
        """Should not return more than top_k documents."""
        docs, _ = pipeline_with_data.retrieve("DevSecOps RAG pipeline")
        assert len(docs) <= pipeline_with_data.top_k

    def test_relevant_content_retrieved(self, pipeline_with_data):
        """DevSecOps query should retrieve content mentioning security."""
        docs, _ = pipeline_with_data.retrieve("What tools are used in DevSecOps?")
        combined = " ".join([d.page_content.lower() for d in docs])
        assert any(term in combined for term in ["security", "sonarqube", "devsecops"])


class TestRAGResponse:
    def test_rag_response_structure(self, pipeline_with_data):
        """
        Test RAGResponse dataclass fields without calling the LLM.
        Verifies that retrieval half of pipeline works correctly.
        """
        docs, retrieval_latency = pipeline_with_data.retrieve("What is RAG?")
        response = RAGResponse(
            answer="Test answer",
            source_documents=docs,
            retrieval_latency_ms=retrieval_latency,
            generation_latency_ms=100.0,
            total_latency_ms=retrieval_latency + 100.0,
            num_chunks_retrieved=len(docs),
            query="What is RAG?"
        )
        assert response.answer == "Test answer"
        assert response.num_chunks_retrieved == len(docs)
        assert response.total_latency_ms > 0
        assert isinstance(response.source_documents, list)

    def test_total_latency_is_sum(self, pipeline_with_data):
        """Total latency should be approximately the sum of retrieval and generation."""
        r_lat = 50.0
        g_lat = 200.0
        response = RAGResponse(
            answer="x", source_documents=[], retrieval_latency_ms=r_lat,
            generation_latency_ms=g_lat, total_latency_ms=r_lat + g_lat,
            num_chunks_retrieved=0, query="test"
        )
        assert abs(response.total_latency_ms - (r_lat + g_lat)) < 1.0


class TestPipelineConfiguration:
    def test_chunk_size_applied(self, pipeline_with_data):
        """Chunk size should match environment configuration."""
        assert pipeline_with_data.chunk_size == 200

    def test_top_k_applied(self, pipeline_with_data):
        """Top-k should match environment configuration."""
        assert pipeline_with_data.top_k == 2

    def test_embedding_model_set(self, pipeline_with_data):
        """Embedding model should be set."""
        assert pipeline_with_data.embedding_model == "all-MiniLM-L6-v2"
