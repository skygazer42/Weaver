# RAG optimization (step14)
- Add chunking config (size/overlap) and splitter selection per content type.
- Enable sentence-transformers embeddings when local mode; fallback to OpenAI/ DashScope otherwise.
- Store source tags and scores in store for later query expansion.
- Add optional web crawler hydration already in deepsearch; consider caching scraped content.
