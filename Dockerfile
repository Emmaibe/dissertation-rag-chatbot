# Dockerfile - RAG Chatbot
# Emmanuel Ibenwankwo - MSc Dissertation 2025/26
# An AI-Augmented DevSecOps and LLMOps Platform for a Production-Style RAG Chatbot
#
# Design notes:
#   - Multi-stage build: compiler tooling not present in final image,
#     reducing attack surface and Trivy-reportable CVEs.
#   - Runs as non-root user (Sysdig, 2026; container security best practice).
#   - torch installed as CPU-only wheel before requirements.txt so pip
#     reuses it rather than pulling the 1.5GB CUDA build.
#   - ChromaDB data NOT baked into the image — mounted as a volume
#     (docker -v locally; PersistentVolumeClaim under K3s).
#   - index.html copied into /app so GET /ui can serve it.
#   - tests/ copied into /app so pytest can run inside the container
#     during the CI pipeline Unit Tests stage.
#   - CHROMA_DB_PATH and DATA_DIR intentionally omitted from ENV so
#     they are injected exclusively by the K8s ConfigMap at runtime,
#     preventing the Dockerfile defaults from overriding the cluster config.

# ---------- Stage 1: build ----------
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch FIRST so sentence-transformers does not pull CUDA
RUN pip install --no-cache-dir \
    torch==2.5.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Explicitly install test dependencies so they are available when
# running pytest inside the container during the CI pipeline
RUN pip install --no-cache-dir pytest pytest-cov

# Pre-download embedding model for fast cold start (no HuggingFace at runtime)
ARG EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV HF_HOME=/build/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

# Copy installed packages and cached model from builder
COPY --from=builder /usr/local /usr/local
COPY --from=builder /build/.cache/huggingface /home/app/.cache/huggingface

# Copy application source and data
COPY src/ ./src/
COPY data/ ./data/
COPY tests/ ./tests/
COPY chatbot.py ingest.py ./

# Copy chat UI — served at GET /ui by app.py
COPY index.html ./index.html

# CHROMA_DB_PATH and DATA_DIR are deliberately excluded here.
# They are injected by the K8s ConfigMap (rag-chatbot-config) at runtime
# so the cluster config always takes precedence over any baked-in defaults.
ENV PYTHONUNBUFFERED=1 \
    HF_HOME=/home/app/.cache/huggingface

VOLUME ["/data/chroma_db"]

RUN mkdir -p /data/chroma_db && chown -R app:app /app /home/app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status==200 else sys.exit(1)"

WORKDIR /app/src
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]