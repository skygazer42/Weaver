"""
Local Document RAG Pipeline.

Provides functionality for:
- Document parsing (PDF, DOCX, TXT, MD)
- Text embedding (OpenAI embeddings)
- Vector storage (ChromaDB)
- Retrieval-augmented generation
"""

from tools.rag.document_loader import Document, DocumentLoader
from tools.rag.embedder import Embedder
from tools.rag.rag_tool import RAGTool, rag_search
from tools.rag.vector_store import VectorStore

__all__ = [
    "DocumentLoader",
    "Document",
    "Embedder",
    "VectorStore",
    "RAGTool",
    "rag_search",
]
