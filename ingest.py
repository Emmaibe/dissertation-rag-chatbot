"""
ingest.py
---------
CLI script to ingest documents into the RAG vector store.
Run this once before starting the API or chatbot CLI.

Usage:
    python ingest.py

Author: Emmanuel Ibenwankwo
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from rag_pipeline import RAGPipeline

def main():
    print("=" * 60)
    print("RAG Chatbot — Document Ingestion")
    print("MSc Dissertation - Emmanuel Ibenwankwo - GCU 2025/26")
    print("=" * 60)

    pipeline = RAGPipeline()

    print("\nIngesting documents from ./data directory...")
    try:
        count = pipeline.ingest_documents()
        print(f"\n✅ Successfully ingested {count} chunks into ChromaDB.")
        stats = pipeline.get_stats()
        print(f"\nVector Store Stats:")
        for k, v in stats.items():
            print(f"  {k}: {v}")
    except Exception as e:
        print(f"\n❌ Ingestion failed: {e}")
        sys.exit(1)

    print("\nIngestion complete. You can now run the chatbot.")

if __name__ == "__main__":
    main()
