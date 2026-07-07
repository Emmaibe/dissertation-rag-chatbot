"""
chatbot.py
----------
Interactive CLI chatbot for the RAG pipeline.
Run this to chat with your knowledge base in the terminal.

Usage:
    python chatbot.py

Author: Emmanuel Ibenwankwo
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from rag_pipeline import RAGPipeline


BANNER = """
╔══════════════════════════════════════════════════════════════╗
║         DevSecOps & LLMOps RAG Chatbot  v0.1.0              ║
║  MSc Dissertation - Emmanuel Ibenwankwo - GCU 2025/26        ║
║  Powered by: Groq (LLaMA 3) + ChromaDB + Sentence-BERT       ║
╚══════════════════════════════════════════════════════════════╝
Type your question and press Enter. Type 'quit' or 'exit' to stop.
Type 'stats' to see vector store statistics.
"""


def format_response(result):
    print("\n" + "─" * 60)
    print(f"🤖 Answer:\n{result.answer}")
    print("\n📚 Sources retrieved:")
    for i, doc in enumerate(result.source_documents, 1):
        snippet = doc.page_content[:120].replace("\n", " ")
        source = doc.metadata.get("source", "knowledge_base")
        print(f"  [{i}] {snippet}...")
        print(f"       Source: {os.path.basename(source)}")
    print(f"\n⏱  Metrics:")
    print(f"   Retrieval:  {result.retrieval_latency_ms:.1f}ms")
    print(f"   Generation: {result.generation_latency_ms:.1f}ms")
    print(f"   Total:      {result.total_latency_ms:.1f}ms")
    print(f"   Chunks retrieved: {result.num_chunks_retrieved}")
    print("─" * 60)


def main():
    print(BANNER)

    pipeline = RAGPipeline()

    # Check vector store is ready
    stats = pipeline.get_stats()
    if stats["status"] != "ready" or stats["chunk_count"] == 0:
        print("⚠️  Vector store is empty. Running document ingestion first...\n")
        try:
            count = pipeline.ingest_documents()
            print(f"✅ Ingested {count} chunks. Ready to chat!\n")
        except Exception as e:
            print(f"❌ Ingestion failed: {e}")
            print("Make sure your documents are in the ./data directory.")
            sys.exit(1)
    else:
        print(f"✅ Vector store ready — {stats['chunk_count']} chunks loaded.\n")

    # Check LLM is ready
    if pipeline.llm is None:
        print("❌ GROQ_API_KEY not set. Please:")
        print("   1. Copy .env.example to .env")
        print("   2. Add your Groq API key from https://console.groq.com")
        print("   3. Re-run this script")
        sys.exit(1)

    print("Ready! Ask me anything about DevSecOps, LLMOps, RAG, K3s, Ansible, or Prometheus.\n")

    while True:
        try:
            question = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye!")
            break

        if not question:
            continue

        if question.lower() in ("quit", "exit", "q"):
            print("Goodbye!")
            break

        if question.lower() == "stats":
            stats = pipeline.get_stats()
            print("\n📊 Pipeline Stats:")
            for k, v in stats.items():
                print(f"   {k}: {v}")
            print()
            continue

        try:
            result = pipeline.query(question)
            format_response(result)
        except Exception as e:
            print(f"\n❌ Error: {e}\n")

    print()


if __name__ == "__main__":
    main()
