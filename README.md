# RAG Chatbot — Baseline Implementation
**An AI-Augmented DevSecOps and LLMOps Platform for a Production-Style RAG Chatbot**  
*Emmanuel Ibenwankwo | MSc Computer Science | Glasgow Caledonian University | 2025/26*

---

## Overview

This is the **Phase 1 baseline RAG chatbot** — a minimal but production-structured implementation that forms the foundation of the dissertation artefact. It demonstrates the core retrieve-then-generate pipeline before CI/CD, containerisation, and cloud deployment are added in later phases.

**Stack:**
- 🧠 **LLM**: Groq API (LLaMA 3.3 70B) — free, API-based, mirrors production architecture
- 📦 **Embeddings**: `all-MiniLM-L6-v2` via sentence-transformers — runs locally, no API cost
- 🗄️ **Vector Store**: ChromaDB — persistent, local
- 🔗 **Orchestration**: LangChain
- 🌐 **API**: FastAPI + Uvicorn
- 🧪 **Testing**: pytest

---

## Quick Setup (5 minutes)

### 1. Clone and install dependencies
```bash
git clone <your-repo-url>
cd rag-chatbot
pip install -r requirements.txt
```

### 2. Get your free Groq API key
1. Go to [https://console.groq.com](https://console.groq.com)
2. Sign up (free, no credit card needed)
3. Click **API Keys → Create API Key**
4. Copy the key

### 3. Configure environment
```bash
cp .env.example .env
# Edit .env and replace 'your_groq_api_key_here' with your actual key
```

### 4. Ingest documents
```bash
python ingest.py
```

### 5. Chat in the terminal
```bash
python chatbot.py
```

### 6. Or start the REST API
```bash
cd src
uvicorn app:app --reload --host 0.0.0.0 --port 8000
```
Then open: [http://localhost:8000/docs](http://localhost:8000/docs) for the interactive Swagger UI.

---

## Project Structure

```
rag-chatbot/
├── data/
│   └── devops_knowledge_base.txt    # Placeholder corpus (7 documents)
├── src/
│   ├── rag_pipeline.py              # Core RAG pipeline (ingest, retrieve, generate)
│   └── app.py                       # FastAPI REST API
├── tests/
│   └── test_rag_pipeline.py         # Unit tests (pytest)
├── chatbot.py                       # Interactive CLI chatbot
├── ingest.py                        # Document ingestion CLI
├── requirements.txt
├── .env.example
└── README.md
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET    | `/`       | Service info |
| GET    | `/health` | Health check (for K8s probes) |
| GET    | `/stats`  | Vector store statistics |
| POST   | `/ingest` | Ingest documents into ChromaDB |
| POST   | `/query`  | Query the RAG chatbot |

### Example query
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "What is DevSecOps?"}'
```

---

## Running Tests

```bash
pytest tests/ -v
pytest tests/ -v --cov=src --cov-report=term-missing
```

---

## RAG Pipeline Architecture

```
User Query
    │
    ▼
[Embedding Model]  ←── all-MiniLM-L6-v2 (local)
    │
    ▼
[ChromaDB Vector Store]  ←── similarity search (top-k=4)
    │
    ▼
[Retrieved Chunks]
    │
    ▼
[Prompt Assembly]  ←── system prompt + context + question
    │
    ▼
[Groq LLM]  ←── LLaMA 3.3 70B (API)
    │
    ▼
[Grounded Answer + Metrics]
```

---

## Evaluation Metrics (RAGAS — Phase 3)

| Metric | Description |
|--------|-------------|
| Context Precision | % of retrieved chunks genuinely relevant |
| Faithfulness | Answer grounded in context, not model hallucination |
| Answer Relevance | Answer addresses the user's question |
| Response Latency | End-to-end wall-clock time (tracked by Prometheus in Phase 3) |

---

## Next Steps (Dissertation Phases)

- **Phase 2**: Jenkins CI/CD pipeline, SonarQube, Docker containerisation
- **Phase 3**: K3s deployment on AWS EC2, Ansible automation, Prometheus/Grafana, RAGAS evaluation
# dissertation-rag-chatbot
