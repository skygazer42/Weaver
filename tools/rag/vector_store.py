"""
Vector Store for RAG Pipeline.

Stores and retrieves document embeddings using ChromaDB.
"""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from tools.rag.document_loader import Document

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    import chromadb
    from chromadb.config import Settings
    CHROMADB_AVAILABLE = True
except ImportError:
    chromadb = None
    CHROMADB_AVAILABLE = False


class VectorStore:
    """
    Vector storage and retrieval using ChromaDB.

    Supports:
    - Local persistent storage
    - In-memory storage for testing
    - Similarity search with metadata filtering
    """

    def __init__(
        self,
        collection_name: str = "weaver_documents",
        persist_directory: Optional[str] = None,
        embedding_function: Optional[Any] = None,
    ):
        """
        Initialize the vector store.

        Args:
            collection_name: Name of the ChromaDB collection
            persist_directory: Directory for persistent storage (None for in-memory)
            embedding_function: Optional custom embedding function
        """
        if not CHROMADB_AVAILABLE:
            raise ImportError(
                "chromadb is required for vector storage. "
                "Install with: pip install chromadb"
            )

        self.collection_name = collection_name
        self.persist_directory = persist_directory

        # Initialize ChromaDB client
        if persist_directory:
            Path(persist_directory).mkdir(parents=True, exist_ok=True)
            self.client = chromadb.PersistentClient(
                path=persist_directory,
                settings=Settings(anonymized_telemetry=False),
            )
        else:
            self.client = chromadb.Client(
                settings=Settings(anonymized_telemetry=False),
            )

        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name=collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        self.embedding_function = embedding_function
        logger.info(f"Initialized vector store: {collection_name}")

    def add_documents(
        self,
        documents: List[Document],
        embeddings: Optional[List[List[float]]] = None,
    ) -> List[str]:
        """
        Add documents to the vector store.

        Args:
            documents: List of Document objects
            embeddings: Pre-computed embeddings (computed if not provided)

        Returns:
            List of document IDs
        """
        if not documents:
            return []

        # Prepare data for ChromaDB
        ids = [doc.chunk_id for doc in documents]
        texts = [doc.content for doc in documents]
        metadatas = [doc.metadata for doc in documents]

        # Compute embeddings if not provided
        if embeddings is None and self.embedding_function:
            embeddings = self.embedding_function.embed_documents(texts)

        # Add to collection
        if embeddings:
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=texts,
                metadatas=metadatas,
            )
        else:
            # Let ChromaDB use its default embedding
            self.collection.add(
                ids=ids,
                documents=texts,
                metadatas=metadatas,
            )

        logger.info(f"Added {len(documents)} documents to vector store")
        return ids

    def search(
        self,
        query: str,
        query_embedding: Optional[List[float]] = None,
        n_results: int = 5,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Tuple[Document, float]]:
        """
        Search for similar documents.

        Args:
            query: Search query text
            query_embedding: Pre-computed query embedding
            n_results: Number of results to return
            filter_metadata: Optional metadata filter

        Returns:
            List of (Document, score) tuples
        """
        # Compute query embedding if not provided
        if query_embedding is None and self.embedding_function:
            query_embedding = self.embedding_function.embed_query(query)

        # Build query kwargs
        query_kwargs = {"n_results": n_results}

        if query_embedding:
            query_kwargs["query_embeddings"] = [query_embedding]
        else:
            query_kwargs["query_texts"] = [query]

        if filter_metadata:
            query_kwargs["where"] = filter_metadata

        # Execute search
        results = self.collection.query(**query_kwargs)

        # Convert to Document objects
        documents_with_scores = []

        if results and results.get("documents"):
            docs = results["documents"][0]
            metadatas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
            distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
            ids = results["ids"][0] if results.get("ids") else [""] * len(docs)

            for i, (text, metadata, distance, doc_id) in enumerate(zip(docs, metadatas, distances, ids)):
                # Convert distance to similarity score (cosine distance -> similarity)
                score = 1.0 - distance

                doc = Document(
                    content=text,
                    metadata=metadata,
                    chunk_id=doc_id,
                )
                documents_with_scores.append((doc, score))

        return documents_with_scores

    def delete_documents(
        self,
        ids: Optional[List[str]] = None,
        filter_metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Delete documents from the vector store.

        Args:
            ids: List of document IDs to delete
            filter_metadata: Delete documents matching this filter

        Returns:
            Number of documents deleted
        """
        try:
            if ids:
                self.collection.delete(ids=ids)
                return len(ids)
            elif filter_metadata:
                self.collection.delete(where=filter_metadata)
                return -1  # Unknown count
            return 0
        except Exception as e:
            logger.error(f"Delete error: {e}")
            return 0

    def get_document(self, doc_id: str) -> Optional[Document]:
        """
        Get a specific document by ID.

        Args:
            doc_id: Document ID

        Returns:
            Document if found, None otherwise
        """
        try:
            result = self.collection.get(ids=[doc_id])
            if result and result.get("documents"):
                return Document(
                    content=result["documents"][0],
                    metadata=result["metadatas"][0] if result.get("metadatas") else {},
                    chunk_id=doc_id,
                )
        except Exception as e:
            logger.error(f"Get document error: {e}")
        return None

    def list_documents(
        self,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        List documents in the store.

        Args:
            limit: Maximum documents to return
            offset: Offset for pagination

        Returns:
            List of document metadata dicts
        """
        try:
            result = self.collection.get(
                limit=limit,
                offset=offset,
                include=["metadatas"],
            )

            documents = []
            if result and result.get("ids"):
                for i, doc_id in enumerate(result["ids"]):
                    metadata = result["metadatas"][i] if result.get("metadatas") else {}
                    documents.append({
                        "id": doc_id,
                        **metadata,
                    })
            return documents

        except Exception as e:
            logger.error(f"List documents error: {e}")
            return []

    def count(self) -> int:
        """Get the number of documents in the store."""
        return self.collection.count()

    def clear(self) -> None:
        """Delete all documents from the store."""
        self.client.delete_collection(self.collection_name)
        self.collection = self.client.get_or_create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        logger.info(f"Cleared vector store: {self.collection_name}")
