# ADR-006: ChromaDB for RAG Memory

## Status
`Accepted`

## Date
2026-09-05

## Context
JARVIS needs to remember past conversations to provide contextually relevant
responses (e.g., "You mentioned earlier that..."). This requires a vector
database to store conversation embeddings and perform semantic similarity
search when composing a new prompt.

## Decision
Use **ChromaDB** (`chromadb>=0.4.0`) as the default memory/RAG provider,
running in persistent local mode. Embeddings are generated using ChromaDB's
default built-in model (`all-MiniLM-L6-v2` via ONNX), which runs locally on
CPU.

Data is persisted to `data/chroma/` on disk. Memory operations are run in
background threads (via `asyncio.to_thread`) to avoid blocking the main
voice loop.

## Consequences

### Positive
- Runs fully locally — no API costs, no data leaves the machine.
- Persistent storage: memory survives JARVIS restarts.
- Simple Python API; no separate server process needed.
- ONNX-based embedding model requires no GPU.

### Negative / Trade-offs
- First-run downloads a ~80 MB ONNX embedding model from S3.
- ChromaDB is heavyweight (many transitive dependencies: grpc, kubernetes,
  opentelemetry...).
- Semantic search quality is limited by the small `all-MiniLM-L6-v2` model.
- For very large memory stores (10,000+ turns), query speed may degrade.

## Alternatives Considered
- **Pinecone**: Managed cloud vector DB, excellent performance but requires
  an API key and costs money. Rejected for local-first requirement.
- **Qdrant**: More lightweight than ChromaDB with a local mode. Good future
  provider candidate.
- **SQLite with keyword search**: Much simpler and lighter but lacks semantic
  (meaning-based) similarity. Would miss related context that uses different
  words. Rejected.
- **In-memory dict**: Extremely simple but loses all memory on restart.
  Rejected.
