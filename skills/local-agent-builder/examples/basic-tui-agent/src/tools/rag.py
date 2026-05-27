# -------------------------------------------------------------
# [!CAUTION] RULES FOR LLM CODING ASSISTANTS EDITING THIS:
# 1. These tools query the pre-built RAG vector index. They do NOT trigger
#    embedding or ingestion — that happens programmatically at startup.
# 2. The VectorStore instance is wired in via init_rag_tools() from app.py.
# 3. These tools operate on the LIBRARY (user's document corpus), NOT the
#    workspace. Keep them separate from workspace tools (fs.py).
# 4. If your project does not use RAG, delete this file and remove the
#    imports from tools/__init__.py.
# -------------------------------------------------------------

from agent_framework import tool
from tools.core import with_quota, _get_tool_rule

# Module-level VectorStore reference, set by app.py at startup
_vectorstore = None


def init_rag_tools(vectorstore):
    """Wire the VectorStore instance into the RAG tools.
    
    Must be called once in app.py AFTER vectorstore.sync() completes
    and BEFORE tools are passed to the AgentBuilder.
    
    Usage in app.py:
        from utils.vectorstore import VectorStore
        from tools.rag import init_rag_tools
        
        vs = VectorStore(library_dir=..., embedding_url=..., ...)
        vs.sync()
        init_rag_tools(vs)
    """
    global _vectorstore
    _vectorstore = vectorstore


@tool
@with_quota
def semantic_search(query: str) -> str:
    """Search the document library using semantic similarity. Returns the most relevant chunks of text from the indexed documents.
    
    Use this tool to find information about broad topics, concepts, policies, or questions where exact wording may vary across documents.
    """
    if _vectorstore is None:
        return "Error: RAG vector store not initialized. Check app configuration."

    results = _vectorstore.semantic_search(query)
    if not results:
        return "No relevant documents found for this query."

    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] Source: {r['filename']} (relevance: {1 - r['distance']:.2f})\n{r['chunk_text']}")

    return "\n\n".join(parts)


@tool
@with_quota
def keyword_search(query: str) -> str:
    """Search for exact keyword matches across all indexed documents. Use this for finding specific names, IP addresses, IDs, or exact phrases."""
    if _vectorstore is None:
        return "Error: RAG vector store not initialized. Check app configuration."

    results = _vectorstore.keyword_search(query)
    if not results:
        return f"No exact matches found for '{query}'."

    parts = []
    for i, r in enumerate(results, 1):
        parts.append(f"[{i}] Source: {r['filename']}\n{r['chunk_text'].strip()}")

    return "\n\n".join(parts)


@tool
@with_quota
def list_library_files() -> str:
    """List all documents in the indexed library with their line count, character count, and number of chunks."""
    if _vectorstore is None:
        return "Error: RAG vector store not initialized. Check app configuration."

    files = _vectorstore.list_files()
    if not files:
        return "No documents found in the library."

    lines = []
    for f in files:
        lines.append(f"{f['filename']} (Lines: {f['lines']}, Chars: {f['chars']}, Chunks: {f['chunks']})")

    return "\n".join(lines)


@tool
@with_quota
def read_library_file(filename: str, start_line: int = 1, end_line: int = -1) -> str:
    """Read a specific range of lines from a document in the library. Lines are 1-indexed.
    
    Use this to read context around chunks found via semantic_search or keyword_search.
    """
    if _vectorstore is None:
        return "Error: RAG vector store not initialized. Check app configuration."

    max_lines = _get_tool_rule("read_library_file", "max_lines", 500)
    if end_line != -1 and (end_line - start_line + 1) > max_lines:
        return f"Error: Requested {end_line - start_line + 1} lines, but your quota restricts you to {max_lines} lines per read."

    result = _vectorstore.read_file(filename, start_line, end_line)
    if result is None:
        return f"Error: Document '{filename}' not found in the library."

    return result
