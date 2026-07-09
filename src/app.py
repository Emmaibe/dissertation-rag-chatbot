"""
app.py
------
FastAPI REST API backend for the RAG chatbot.
Exposes endpoints for document ingestion, querying, the chat UI,
Prometheus metrics, and session-based conversation memory.

Author: Emmanuel Ibenwankwo
Project: An AI-Augmented DevSecOps and LLMOps Platform for a
         Production-Style RAG Chatbot
Institution: Glasgow Caledonian University - MSc Computer Science
"""

import os
import time
import uuid
import logging
import pathlib
from contextlib import asynccontextmanager
from typing import List, Optional, Dict
from collections import defaultdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from prometheus_fastapi_instrumentator import Instrumentator

import sys
sys.path.insert(0, os.path.dirname(__file__))

from rag_pipeline import RAGPipeline, RAGResponse

logger = logging.getLogger(__name__)

# Global pipeline instance
pipeline: Optional[RAGPipeline] = None

# In-memory conversation history store
# Key: session_id, Value: list of {"role": "user"|"assistant", "content": str}
conversation_store: Dict[str, List[dict]] = defaultdict(list)
MAX_HISTORY_TURNS = 10

# Greeting shortcut — bypasses RAG pipeline for informal openers
GREETINGS = {
    "hi", "hello", "hey", "hiya", "howdy",
    "how are you", "what can you do", "help",
    "what do you do", "who are you", "what are you"
}

GREETING_RESPONSE = (
    "Hello! I'm the GCU DevSecOps Knowledge Assistant. "
    "I can answer questions about MSc Computer Science modules at "
    "Glasgow Caledonian University — including module descriptions, "
    "credit values, SCQF levels, subject areas, and assessment methods. "
    "Try asking me about a specific module!"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the RAG pipeline on startup."""
    global pipeline
    logger.info("Starting RAG chatbot API...")
    pipeline = RAGPipeline()
    yield
    logger.info("Shutting down RAG chatbot API...")


app = FastAPI(
    title="RAG Chatbot API",
    description=(
        "Production-style RAG chatbot API for MSc Dissertation: "
        "'An AI-Augmented DevSecOps and LLMOps Platform for a Production-Style RAG Chatbot'"
    ),
    version="0.1.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Prometheus instrumentation
# Automatically exposes GET /metrics with:
#   http_requests_total — request count by method, handler, status
#   http_request_duration_seconds — latency histogram per endpoint
#   http_requests_in_progress — concurrent requests gauge
Instrumentator().instrument(app).expose(app)


# ── Request / Response Models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str
    session_id: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "question": "How many credits is the Masters Project?",
                "session_id": "optional-existing-session-id"
            }
        }


class SourceDocument(BaseModel):
    content: str
    source: str


class QueryResponse(BaseModel):
    question: str
    answer: str
    session_id: str
    source_documents: List[SourceDocument]
    metrics: dict


class IngestResponse(BaseModel):
    status: str
    chunks_ingested: int
    message: str


# ── Helpers ────────────────────────────────────────────────────────────────────

def build_history_context(session_id: str) -> str:
    """Build a formatted string of recent conversation history."""
    history = conversation_store[session_id]
    if not history:
        return ""
    lines = ["Previous conversation:"]
    for turn in history[-MAX_HISTORY_TURNS:]:
        role = "User" if turn["role"] == "user" else "Assistant"
        lines.append(f"{role}: {turn['content']}")
    return "\n".join(lines)


def store_turn(session_id: str, question: str, answer: str):
    """Append a user/assistant turn to the session history."""
    conversation_store[session_id].append({"role": "user", "content": question})
    conversation_store[session_id].append({"role": "assistant", "content": answer})
    if len(conversation_store[session_id]) > MAX_HISTORY_TURNS * 2:
        conversation_store[session_id] = conversation_store[session_id][-(MAX_HISTORY_TURNS * 2):]


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/", tags=["Health"])
def root():
    """Root endpoint — confirms API is running."""
    return {
        "service": "RAG Chatbot API",
        "version": "0.1.0",
        "status": "running",
        "author": "Emmanuel Ibenwankwo",
        "project": "MSc Dissertation - GCU 2025/26",
        "ui": "/ui",
        "metrics": "/metrics"
    }


@app.get("/ui", response_class=HTMLResponse, tags=["UI"])
def serve_ui():
    """Serve the chat UI at GET /ui."""
    html_path = pathlib.Path(__file__).parent.parent / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="UI file not found")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/health", tags=["Health"])
def health_check():
    """Health check for Kubernetes liveness/readiness probes."""
    stats = pipeline.get_stats() if pipeline else {"status": "not_initialised"}
    return {
        "status": "healthy" if stats.get("status") == "ready" else "degraded",
        "pipeline": stats,
        "timestamp": time.time()
    }


@app.post("/ingest", response_model=IngestResponse, tags=["Ingestion"])
def ingest_documents():
    """Ingest documents from the data directory into the vector store."""
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialised")
    try:
        count = pipeline.ingest_documents()
        return IngestResponse(
            status="success",
            chunks_ingested=count,
            message=f"Successfully ingested and embedded {count} chunks into ChromaDB."
        )
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/query", response_model=QueryResponse, tags=["Query"])
def query(request: QueryRequest):
    """
    Query the RAG chatbot with a natural language question.
    Pass session_id from a previous response to maintain conversation memory.
    """
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialised")

    question = request.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    session_id = request.session_id or str(uuid.uuid4())

    # Greeting shortcut — no RAG needed
    if question.lower().rstrip("?!.") in GREETINGS:
        store_turn(session_id, question, GREETING_RESPONSE)
        return QueryResponse(
            question=question,
            answer=GREETING_RESPONSE,
            session_id=session_id,
            source_documents=[],
            metrics={
                "retrieval_latency_ms": 0,
                "generation_latency_ms": 0,
                "total_latency_ms": 0,
                "num_chunks_retrieved": 0,
            }
        )

    try:
        # Prepend conversation history for context-aware retrieval
        history_context = build_history_context(session_id)
        augmented_question = (
            f"{history_context}\n\nCurrent question: {question}"
            if history_context else question
        )

        result: RAGResponse = pipeline.query(augmented_question)

        source_docs = [
            SourceDocument(
                content=doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
                source=doc.metadata.get("source", "knowledge_base")
            )
            for doc in result.source_documents
        ]

        store_turn(session_id, question, result.answer)

        return QueryResponse(
            question=question,
            answer=result.answer,
            session_id=session_id,
            source_documents=source_docs,
            metrics={
                "retrieval_latency_ms": round(result.retrieval_latency_ms, 2),
                "generation_latency_ms": round(result.generation_latency_ms, 2),
                "total_latency_ms": round(result.total_latency_ms, 2),
                "num_chunks_retrieved": result.num_chunks_retrieved,
            }
        )
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error(f"Query failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/session/{session_id}", tags=["Session"])
def clear_session(session_id: str):
    """Clear conversation history for a session."""
    if session_id in conversation_store:
        del conversation_store[session_id]
    return {"status": "cleared", "session_id": session_id}


@app.get("/stats", tags=["Health"])
def get_stats():
    """Return pipeline and vector store statistics."""
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialised")
    return pipeline.get_stats()