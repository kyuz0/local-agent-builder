from tools.core import tool_quotas_ctx, with_quota
from tools.fs import (
    get_workspace_files,
    get_workspace_file_content,
    read_workspace_file,
    write_workspace_file,
    list_workspace_files,
    grep_workspace_file,
    remove_workspace_file
)
from tools.web import fetch_url_to_workspace, web_search
from tools.todos import write_todos, read_todos
from tools.meta import think_tool
from tools.shell import run_shell_command
from tools.rag import (
    semantic_search,
    keyword_search,
    list_library_files,
    read_library_file,
    init_rag_tools
)

# -------------------------------------------------------------
# [!CAUTION] RULES FOR LLM CODING ASSISTANTS EDITING THIS:
# DO NOT define Sub-Agent Delegation functions inside this `tools/` directory!
# Sub-Agent configurations MUST strictly be defined in `src/app.py` directly using the `SubAgentConfig` schema within the `AgentBuilder`.
# The `engine/orchestrator.py` module automatically builds the delegation handlers (`delegate_tasks`) dynamically.
# -------------------------------------------------------------

WORKSPACE_TOOLS = [
    read_workspace_file,
    write_workspace_file,
    list_workspace_files,
    grep_workspace_file,
    fetch_url_to_workspace,
    web_search,
    write_todos,
    read_todos,
    remove_workspace_file,
    think_tool,
    run_shell_command
]

# RAG tools for document corpus search. Remove if your project does not use RAG.
RAG_TOOLS = [
    semantic_search,
    keyword_search,
    list_library_files,
    read_library_file
]

__all__ = [
    "tool_quotas_ctx",
    "with_quota",
    "WORKSPACE_TOOLS",
    "RAG_TOOLS",
    "init_rag_tools",
    # Individual tools (import these in app.py for selective per-agent tool assignment)
    "read_workspace_file",
    "write_workspace_file",
    "list_workspace_files",
    "grep_workspace_file",
    "remove_workspace_file",
    "fetch_url_to_workspace",
    "web_search",
    "write_todos",
    "read_todos",
    "think_tool",
    "run_shell_command",
    # RAG tools (remove if not using RAG)
    "semantic_search",
    "keyword_search",
    "list_library_files",
    "read_library_file",
    # TUI helpers (not agent tools)
    "get_workspace_files",
    "get_workspace_file_content",
]
