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

__all__ = [
    "tool_quotas_ctx",
    "with_quota",
    "get_workspace_files",
    "get_workspace_file_content",
    "WORKSPACE_TOOLS",
    "think_tool",
    "run_shell_command"
]
