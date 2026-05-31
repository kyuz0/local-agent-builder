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
        from tools.fs import _get_safe_path
        path = _get_safe_path("_todos.md")
        if not path:
            return "Error: could not resolve path for _todos.md"
        if _get_workspace_type() == "disk":
            parent_dir = os.path.dirname(path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(todos)
        else:
            _IN_MEMORY_FS[path] = todos
        return "Todos saved successfully."
    except Exception as e:
        import traceback
        return f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}"

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
    except Exception as e:
        import traceback
        return f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}"
