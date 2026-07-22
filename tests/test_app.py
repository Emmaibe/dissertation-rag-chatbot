"""
Unit tests for the FastAPI application layer.
These tests avoid external LLM calls by replacing the global pipeline with
a lightweight dummy object.
"""

import os
import sys

import pytest
from fastapi import HTTPException
from langchain_core.documents import Document

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import app as api


class DummyPipeline:
    def get_stats(self):
        return {
            "status": "ready",
            "chunk_count": 7,
            "embedding_model": "all-MiniLM-L6-v2",
            "llm_model": "llama-3.3-70b-versatile",
            "top_k": 4,
        }

    def ingest_documents(self):
        return 7

    def query(self, question):
        return api.RAGResponse(
            answer=f"Answered: {question}",
            source_documents=[
                Document(
                    page_content="The Programming Principles module is worth 15 credits.",
                    metadata={"source": "gcu_modules_corpus.txt"},
                )
            ],
            retrieval_latency_ms=10.123,
            generation_latency_ms=20.456,
            total_latency_ms=30.579,
            num_chunks_retrieved=1,
            query=question,
        )


@pytest.fixture(autouse=True)
def reset_app_state():
    original_pipeline = api.pipeline
    api.pipeline = DummyPipeline()
    api.conversation_store.clear()
    yield
    api.pipeline = original_pipeline
    api.conversation_store.clear()


def test_root_endpoint_returns_service_metadata():
    response = api.root()

    assert response["service"] == "RAG Chatbot API"
    assert response["status"] == "running"
    assert response["ui"] == "/ui"
    assert response["metrics"] == "/metrics"


def test_health_check_reports_healthy_when_pipeline_ready():
    response = api.health_check()

    assert response["status"] == "healthy"
    assert response["pipeline"]["chunk_count"] == 7
    assert "timestamp" in response


def test_stats_endpoint_returns_pipeline_stats():
    response = api.get_stats()

    assert response["status"] == "ready"
    assert response["embedding_model"] == "all-MiniLM-L6-v2"


def test_stats_endpoint_rejects_uninitialised_pipeline():
    api.pipeline = None

    with pytest.raises(HTTPException) as exc:
        api.get_stats()

    assert exc.value.status_code == 503
    assert exc.value.detail == "Pipeline not initialised"


def test_ingest_endpoint_returns_chunk_count():
    response = api.ingest_documents()

    assert response.status == "success"
    assert response.chunks_ingested == 7
    assert "Successfully ingested" in response.message


def test_query_rejects_blank_question():
    with pytest.raises(HTTPException) as exc:
        api.query(api.QueryRequest(question="   "))

    assert exc.value.status_code == 400
    assert exc.value.detail == "Question cannot be empty"


def test_query_greeting_bypasses_rag_pipeline():
    response = api.query(api.QueryRequest(question="Hi", session_id="session-1"))

    assert response.session_id == "session-1"
    assert response.source_documents == []
    assert response.metrics["num_chunks_retrieved"] == 0
    assert len(api.conversation_store["session-1"]) == 2


def test_query_uses_pipeline_and_formats_sources():
    response = api.query(api.QueryRequest(
        question="How many credits is the Programming Principles module?",
        session_id="session-2",
    ))

    assert response.session_id == "session-2"
    assert response.answer.startswith("Answered:")
    assert response.metrics["total_latency_ms"] == 30.58
    assert response.source_documents[0].source == "gcu_modules_corpus.txt"


def test_conversation_history_is_added_to_follow_up_query():
    api.store_turn("session-3", "What is Programming Principles?", "It is a module.")

    response = api.query(api.QueryRequest(
        question="How many credits is it?",
        session_id="session-3",
    ))

    assert "Previous conversation:" in response.answer
    assert "Current question: How many credits is it?" in response.answer


def test_clear_session_removes_conversation_history():
    api.store_turn("session-4", "Hello", "Hi")

    response = api.clear_session("session-4")

    assert response == {"status": "cleared", "session_id": "session-4"}
    assert "session-4" not in api.conversation_store
