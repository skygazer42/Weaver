"""
Text Embedder for RAG Pipeline.

Generates embeddings using OpenAI API or compatible endpoints.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Check for optional dependencies
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OpenAI = None
    OPENAI_AVAILABLE = False


class Embedder:
    """
    Generate text embeddings using OpenAI API.

    Supports OpenAI and compatible APIs (Azure, local models).
    """

    def __init__(
        self,
        model: str = "text-embedding-3-small",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        dimensions: Optional[int] = None,
    ):
        """
        Initialize the embedder.

        Args:
            model: Embedding model name
            api_key: OpenAI API key (uses env var if not provided)
            base_url: Custom API base URL
            dimensions: Output embedding dimensions (for models that support it)
        """
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            )

        from common.config import settings

        self.model = model
        self.dimensions = dimensions

        client_kwargs = {
            "api_key": api_key or settings.openai_api_key,
        }
        if base_url or settings.openai_base_url:
            client_kwargs["base_url"] = base_url or settings.openai_base_url

        self.client = OpenAI(**client_kwargs)

    def embed(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for a list of texts.

        Args:
            texts: List of text strings to embed

        Returns:
            List of embedding vectors
        """
        if not texts:
            return []

        # OpenAI has a limit on batch size
        batch_size = 100
        all_embeddings = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]

            try:
                kwargs = {"model": self.model, "input": batch}
                if self.dimensions:
                    kwargs["dimensions"] = self.dimensions

                response = self.client.embeddings.create(**kwargs)
                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

            except Exception as e:
                logger.error(f"Embedding error: {e}")
                # Return zero vectors for failed batch
                dim = self.dimensions or 1536
                all_embeddings.extend([[0.0] * dim] * len(batch))

        return all_embeddings

    def embed_single(self, text: str) -> List[float]:
        """
        Generate embedding for a single text.

        Args:
            text: Text string to embed

        Returns:
            Embedding vector
        """
        embeddings = self.embed([text])
        return embeddings[0] if embeddings else []

    def embed_query(self, query: str) -> List[float]:
        """
        Embed a search query.

        Some models use different embeddings for queries vs documents.
        This method handles that distinction if needed.

        Args:
            query: Search query text

        Returns:
            Query embedding vector
        """
        return self.embed_single(query)

    def embed_documents(self, documents: List[str]) -> List[List[float]]:
        """
        Embed a list of documents.

        Args:
            documents: List of document texts

        Returns:
            List of document embedding vectors
        """
        return self.embed(documents)
