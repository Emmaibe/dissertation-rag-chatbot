"""
app.py
------
FastAPI REST API backend for the RAG chatbot.
Exposes endpoints for document ingestion, querying, and the chat UI.

Author: Emmanuel Ibenwankwo
Project: An AI-Augmented DevSecOps and LLMOps Platform for a
         Production-Style RAG Chatbot
Institution: Glasgow Caledonian University - MSc Computer Science
"""

import os
import time
import logging
import pathlib
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import sys
sys.path.insert(0, os.path.dirname(__file__))

from rag_pipeline import RAGPipeline, RAGResponse

logger = logging.getLogger(__name__)

# Global pipeline instance
pipeline: Optional[RAGPipeline] = None


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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response Models ──────────────────────────────────────────────────

class QueryRequest(BaseModel):
    question: str

    class Config:
        json_schema_extra = {
            "example": {"question": "What is DevSecOps?"}
        }


class SourceDocument(BaseModel):
    content: str
    source: str


class QueryResponse(BaseModel):
    question: str
    answer: str
    source_documents: List[SourceDocument]
    metrics: dict


class IngestResponse(BaseModel):
    status: str
    chunks_ingested: int
    message: str


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
        "ui": "/ui"
    }


@app.get("/ui", response_class=HTMLResponse, tags=["UI"])
def serve_ui():
    """
    Serve the chat UI.
    The HTML file is co-located in the repo root and copied into the
    container at /app/index.html by the Dockerfile COPY src/ step.
    Access at http://<host>:30080/ui
    """
    html_path = pathlib.Path(__file__).parent.parent / "index.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="UI file not found")
    return HTMLResponse(content=html_path.read_text(encoding="utf-8"))


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint for Kubernetes liveness/readiness probes."""
    stats = pipeline.get_stats() if pipeline else {"status": "not_initialised"}
    return {
        "status": "healthy" if stats.get("status") == "ready" else "degraded",
        "pipeline": stats,
        "timestamp": time.time()
    }


@app.post("/ingest", response_model=IngestResponse, tags=["Ingestion"])
def ingest_documents():
    """
    Ingest documents from the data directory into the vector store.
    Call this once on first setup, or whenever the corpus changes.
    """
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


GREETINGS = {"hi", "hello", "hey", "how are you", "what can you do", "help"}

@app.post("/query", response_model=QueryResponse, tags=["Query"])
def query(request: QueryRequest):
    """
    Query the RAG chatbot with a natural language question.
    Returns the answer, source documents, and latency metrics.
    """

    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialised")

    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    q = request.question.strip().lower().rstrip("?!.")
    if q in GREETINGS:
        return QueryResponse(
            question=request.question,
            answer="Hello! I'm the GCU DevSecOps Knowledge Assistant. I can answer questions about MSc Computer Science modules at Glasgow Caledonian University. Try asking me about a specific module, assessment methods, or credit values.",
            source_documents=[],
            metrics={"retrieval_latency_ms": 0, "generation_latency_ms": 0, "total_latency_ms": 0,
                     "num_chunks_retrieved": 0}
        )

    try:
        result: RAGResponse = pipeline.query(request.question)

        source_docs = [
            SourceDocument(
                content=doc.page_content[:300] + "..." if len(doc.page_content) > 300 else doc.page_content,
                source=doc.metadata.get("source", "knowledge_base")
            )
            for doc in result.source_documents
        ]

        return QueryResponse(
            question=result.query,
            answer=result.answer,
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


@app.get("/stats", tags=["Health"])
def get_stats():
    """Return pipeline and vector store statistics."""
    if pipeline is None:
        raise HTTPException(status_code=503, detail="Pipeline not initialised")
    return pipeline.get_stats()