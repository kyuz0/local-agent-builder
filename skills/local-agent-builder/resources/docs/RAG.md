# RAG & Vector Search Guide

## Architecture Overview

The scaffold supports local Retrieval-Augmented Generation (RAG) using a sqlite-vec backed vector database. The architecture strictly separates **programmatic ingestion** (startup) from **LLM querying** (runtime).

```
STARTUP (app.py)                          RUNTIME (Agent Loop)
┌─────────────────────────┐               ┌─────────────────────────┐
│ 1. Read RAG config      │               │ Agent tools:            │
│ 2. Instantiate VectorStore              │ • semantic_search()     │
│ 3. vectorstore.sync()   │──────────────>│ • keyword_search()      │
│    - Scan library dir   │  .rag.db      │ • list_library_files()  │
│    - Parse (liteparse)  │               │ • read_library_file()   │
│    - Chunk (semchunk)   │               │                         │
│    - Embed (/v1/embeddings)             │ Agent NEVER triggers    │
│    - Store (sqlite-vec) │               │ embedding or ingestion. │
│ 4. init_rag_tools(vs)   │               └─────────────────────────┘
└─────────────────────────┘
```

> [!CAUTION]
> **Document embedding is a programmatic utility, NOT an agent tool.** The `VectorStore` class (`src/utils/vectorstore.py`) handles all ingestion logic. It must NEVER be decorated with `@tool` or passed to the `AgentBuilder`. Only the wrapper tools in `src/tools/rag.py` are agent-facing.

## Setup in app.py

To enable RAG in your agent application, add the following to `src/app.py`:

```python
from utils.vectorstore import VectorStore
from tools.rag import init_rag_tools, semantic_search, keyword_search, list_library_files, read_library_file
from tools.meta import think_tool
import config

# --- RAG Setup (runs at startup, before the agent loop) ---
rag_cfg = config.cfg.get("settings", {}).get("rag", {})
if rag_cfg.get("enabled", False):
    vs = VectorStore(
        library_dir=rag_cfg.get("library_dir", f"~/.{config.APP_NAME}/libraries"),
        embedding_url=config.cfg["api"].get("embedding_base_url", config.cfg["api"]["openai_base_url"]),
        embedding_model=config.cfg["api"].get("embedding_model", config.cfg["api"]["openai_model"]),
        chunk_size=rag_cfg.get("chunk_size", 1000),
        chunk_overlap=rag_cfg.get("chunk_overlap", 150),
        search_results=rag_cfg.get("search_results", 5),
    )
    stats = vs.sync()
    print(f"RAG index: {stats['new']} new, {stats['unchanged']} unchanged, {stats['total_chunks']} total chunks")
    init_rag_tools(vs)

# --- Agent Setup ---
builder = AgentBuilder(
    name=config.APP_NAME,
    instructions=ORCHESTRATOR_INSTRUCTIONS,
    tools=[semantic_search, keyword_search, list_library_files, read_library_file, think_tool],
)
```

## Configuration

### config_template.yaml

```yaml
api:
  openai_base_url: http://localhost:8080/v1
  openai_model: local-model
  # Embedding endpoint — defaults to same as LLM. Remove if not using RAG.
  embedding_base_url: http://localhost:8080/v1
  embedding_model: local-model

settings:
  rag:
    enabled: true                            # Toggle RAG on/off
    library_dir: "~/.{APP_NAME}/libraries"   # Document directory to index
    chunk_size: 1000                         # Characters per chunk
    chunk_overlap: 150                       # Overlap between chunks
    search_results: 5                        # Default k for semantic search
  quotas:
    semantic_search: 20
    keyword_search: 20
    list_library_files: 10
    read_library_file:
      limit: 50
      rules:
        max_lines: 500
```

### Embedding Endpoint

The embedding endpoint must be OpenAI-compatible (`/v1/embeddings`). By default it uses the same host as the LLM. For llama.cpp, start the server with `--embeddings` to enable the endpoint:

```bash
./llama-server -m your-model.gguf --port 8080 --embeddings
```

If you use a separate embedding model on a different port, override:
```yaml
api:
  embedding_base_url: http://localhost:8081/v1
  embedding_model: nomic-embed-text
```

### Library Directory

The library directory is where users place documents to be indexed. The vector database (`.rag.db`) is automatically created inside this directory:

```
~/.my-rag-agent/libraries/
├── .rag.db              ← Auto-created sqlite-vec database
├── report_q1.pdf
├── employee_handbook.docx
└── api_reference.md
```

## Agent Tools

The following tools are available in `src/tools/rag.py`:

| Tool | Purpose | Quota Key |
|------|---------|-----------|
| `semantic_search(query)` | KNN vector search over embedded chunks | `semantic_search` |
| `keyword_search(query)` | Exact case-insensitive text match | `keyword_search` |
| `list_library_files()` | List indexed documents with stats | `list_library_files` |
| `read_library_file(filename, start, end)` | Read line range from raw document | `read_library_file` |

> [!IMPORTANT]
> **Library tools vs. Workspace tools:** RAG tools read from the **library directory** (user's document corpus). Workspace tools (`read_workspace_file`, `write_workspace_file`) operate on the agent's **scratchpad**. A RAG agent typically has both — library tools for reading the corpus, workspace tools for writing reports and notes.

## Document Parsing

The `VectorStore.sync()` method parses files in this priority order:
1. **liteparse** (LlamaIndex) — preferred for PDFs and complex layouts with spatial accuracy
2. **markitdown** (Microsoft) — fallback for standard documents (HTML, Office, basic PDF)
3. **Plain text** — last resort for `.txt`, `.md`, and similar files

## Anti-Patterns

1. **Never let the LLM trigger embedding.** Ingestion is deterministic and happens at startup. There is no tool for the agent to call to "index a document."
2. **Never expose VectorStore internals.** The class, the DB connection, and the embedding function are implementation details. Only the 4 tools in `rag.py` are agent-facing.
3. **Never give the agent both `semantic_search` AND direct file system access to the library dir.** If the agent can `read_workspace_file` on the library path, it will bypass the vector index entirely.
4. **Never skip `init_rag_tools()`.** If you forget to call it, all RAG tools return "Error: RAG vector store not initialized."

## Pruning RAG (If Not Needed)

If your project does not use RAG:
1. Remove `sqlite-vec` and `semchunk` from `pyproject.toml`
2. Delete `src/tools/rag.py` and `src/utils/vectorstore.py`
3. Remove the RAG tool imports from `src/tools/__init__.py`
4. Remove `embedding_base_url`, `embedding_model` from `api` config
5. Remove the `settings.rag` block and RAG quota entries from `config_template.yaml`
