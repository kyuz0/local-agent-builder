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

# -------------------------------------------------------------
# [!CAUTION] RULES FOR LLM CODING ASSISTANTS EDITING THIS:
# DO NOT define Sub-Agent Delegation functions (e.g., `delegate_search`) inside this `tools/` directory!
# Delegation tools MUST strictly remain inside `chat.py` inside `create_local_agent()` so they can capture the `subagent_callback` closure.
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
    think_tool
]

__all__ = [
    "tool_quotas_ctx",
    "with_quota",
    "get_workspace_files",
    "get_workspace_file_content",
    "WORKSPACE_TOOLS",
    "think_tool"
]
