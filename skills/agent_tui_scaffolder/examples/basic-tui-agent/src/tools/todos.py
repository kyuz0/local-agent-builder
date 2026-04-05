import os
from agent_framework import tool
from tools.core import with_quota
from tools.fs import _get_workspace_type, _get_workspace_dir, get_workspace_file_content, _IN_MEMORY_FS

@tool
@with_quota
def write_todos(todos: str) -> str:
    """Write or update a todo list for the orchestrator task.

    Use this to track your plan and mark items as completed.
    Use markdown checkboxes so you can see progress at a glance:

        - [x] Completed task
        - [ ] Pending task
        - [ ] Another pending task

    Call read_todos() first to see the current list, then rewrite the
    full list with updated checkboxes when items are done.

    Args:
        todos: The full todo list string with checkboxes to save.
    """
    try:
        path = "_todos.md"
        if _get_workspace_type() == "disk":
            os.makedirs(_get_workspace_dir(), exist_ok=True)
            with open(os.path.join(_get_workspace_dir(), path), "w", encoding="utf-8") as f:
                f.write(todos)
        else:
            _IN_MEMORY_FS[path] = todos
        return "Todos saved successfully."
    except Exception as e: return f"Error: {e}"

@tool
@with_quota
def read_todos() -> str:
    """Read the current todo list to review progress.

    Use this before continuing work to see which tasks are done ([x])
    and which are still pending ([ ]).
    """
    try:
        content = get_workspace_file_content("_todos.md")
        if content:
            return content
        return "No todos have been saved yet."
    except Exception as e: return f"Error: {e}"
