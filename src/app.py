"""
app.py
------
FastAPI REST API backend for the RAG chatbot.
Exposes endpoints for document ingestion and querying.

Author: Emmanuel Ibenwankwo
Project: An AI-Augmented DevSecOps and LLMOps Platform for a
         Production-Style RAG Chatbot
Institution: Glasgow Caledonian University - MSc Computer Science
"""

import os
import time
import logging
from contextlib import asynccontextmanager
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add src to path when running from project root
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


# Initialise FastAPI app
app = FastAPI(
    title="RAG Chatbot API",
    description=(
        "Production-style RAG chatbot API for MSc Dissertation: "
        "'An AI-Augmented DevSecOps and LLMOps Platform for a Production-Style RAG Chatbot'"
    ),
    version="0.1.0",
    lifespan=lifespan
)

# CORS middleware (allows browser-based front end to connect)
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
        "project": "MSc Dissertation - GCU 2025/26"
    }


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
