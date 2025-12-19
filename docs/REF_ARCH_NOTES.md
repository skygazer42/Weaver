# Reference repo patterns to reuse (langchain-langgraph-V1.0)
- LangGraph API/runtime packages enable hosted graphs, replay, and cloud deployment; can import export_graph_mermaid for visualization.
- Uses langgraph-cli and langgraph-sdk for remote execution; consider adding CLI for graph testing.
- Includes sentence-transformers + pypdf for local RAG ingestion; can mirror for offline retrieval.
- Bigtool/prebuilt for graph composition; consider for modular subgraphs (deepsearch, support, code-exec).
- Rich LangChain provider set (groq, deepseek, google-genai, ollama) to enable multi-vendor failover; our abstraction already supports base_url/azure, add more client factories if needed.
