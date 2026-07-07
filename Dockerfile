# Dockerfile - RAG Chatbot
# Emmanuel Ibenwankwo - MSc Dissertation 2025/26
# An AI-Augmented DevSecOps and LLMOps Platform for a Production-Style RAG Chatbot
#
# Design notes (for dissertation write-up):
#   - Multi-stage build: build deps (gcc etc.) not present in final image,
#     reducing attack surface and Trivy-reportable CVEs.
#   - Runs as a non-root user (Sysdig, 2026; container security best practice).
#   - torch is installed as the CPU-only wheel BEFORE requirements.txt,
#     so pip reuses it rather than pulling the 1.5GB CUDA variant that
#     sentence-transformers would otherwise trigger.
#   - ChromaDB data is NOT baked into the image. CHROMA_DB_PATH points to
#     /data/chroma_db, expected to be a mounted volume at runtime
#     (docker -v locally; a PersistentVolumeClaim under K3s).
#   - The embedding model is pre-downloaded at build time for fast cold starts.

# ---------- Stage 1: build ----------
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch FIRST so sentence-transformers reuses it
# instead of pulling the full CUDA build (~1.5GB saved, build timeout avoided)
RUN pip install --no-cache-dir --user \
    torch==2.5.1+cpu \
    --index-url https://download.pytorch.org/whl/cpu

COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Pre-download the embedding model so the container has no HuggingFace
# dependency at runtime (faster cold start, works in air-gapped K8s)
ARG EMBEDDING_MODEL=all-MiniLM-L6-v2
ENV HF_HOME=/build/.cache/huggingface
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('${EMBEDDING_MODEL}')"

# ---------- Stage 2: runtime ----------
FROM python:3.12-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app

# Copy installed packages and cached model from builder
COPY --from=builder /root/.local /home/app/.local
COPY --from=builder /build/.cache/huggingface /home/app/.cache/huggingface

# Copy application source
COPY src/ ./src/
COPY data/ ./data/
COPY chatbot.py ingest.py ./

ENV PATH=/home/app/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/home/app/.cache/huggingface \
    CHROMA_DB_PATH=/data/chroma_db \
    DATA_DIR=/app/data

VOLUME ["/data/chroma_db"]

RUN mkdir -p /data/chroma_db && chown -R app:app /app /home/app /data

USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0) if urllib.request.urlopen('http://localhost:8000/health', timeout=3).status==200 else sys.exit(1)"

WORKDIR /app/src
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]