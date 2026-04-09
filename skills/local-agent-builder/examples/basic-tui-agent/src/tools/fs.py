from typing import Dict, List
import os
import re
import contextvars
from agent_framework import tool
from tools.core import with_quota, _get_tool_rule

# --- WORKSPACE FILE SYSTEM ---
_IN_MEMORY_FS: Dict[str, str] = {}
session_dir_ctx = contextvars.ContextVar('session_dir', default="")

def _get_workspace_type() -> str:
    from config import cfg
    return cfg.get("settings", {}).get("workspace", {}).get("type", "memory")

def _get_workspace_dir() -> str:
    from config import cfg
    return cfg.get("settings", {}).get("workspace", {}).get("dir", ".")

def _get_safe_path(filename: str) -> str:
    # Safely allow subdirectories while blocking traversal hacks
    if ".." in filename or filename.startswith("/") or filename.startswith("\\"):
        return ""
    
    session_dir = session_dir_ctx.get()
    if session_dir:
        filename = os.path.join(session_dir, filename)

    if _get_workspace_type() == "disk":
        return os.path.join(_get_workspace_dir(), filename)
    return filename

def get_workspace_files() -> List[str]:
    """Helper for TUI to list files agnostic of storage backend."""
    session_dir = session_dir_ctx.get()
    
    if _get_workspace_type() == "disk":
        d = _get_workspace_dir()
        if session_dir:
            d = os.path.join(d, session_dir)
        if not os.path.isdir(d): return []
        return [os.path.join(session_dir, f) if session_dir else f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))]
        
    if session_dir:
        prefix = session_dir + "/"
        return [k for k in _IN_MEMORY_FS.keys() if k.startswith(prefix)]
    return list(_IN_MEMORY_FS.keys())

def get_workspace_file_content(filename: str) -> str | None:
    """Helper for TUI to read a file agnostic of storage backend."""
    path = _get_safe_path(filename)
    if not path: return None
    if _get_workspace_type() == "disk":
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        return None
    return _IN_MEMORY_FS.get(path)

@tool
@with_quota
def read_workspace_file(filename: str, start_line: int = 1, end_line: int = -1) -> str:
    """Read a stored text file. Use start_line and end_line bounds to read large files safely. Both bounds are 1-indexed."""
    try:
        content = get_workspace_file_content(filename)
        if content is None: return f"Error: '{filename}' not found."
        
        lines = content.splitlines()
        total = len(lines)
        
        max_lines = _get_tool_rule("read_workspace_file", "max_lines", 300)
        
        if end_line == -1: end_line = total
            
        start = max(1, start_line)
        end = min(total, end_line)
        
        if (end - start + 1) > max_lines:
            return f"Error: Requested {end - start + 1} lines, but your quota restricts you to {max_lines} lines per read. Use grep_workspace_file or chunked bounds."
            
        chunk = "\n".join(lines[start - 1:end])
        return f"--- {filename} [Lines {start}-{end} of {total}] ---\n{chunk}"
    except Exception as e:
        import traceback
        return f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}"

@tool
@with_quota
def write_workspace_file(filename: str, content: str) -> str:
    """Save content to your workspace."""
    try:
        path = _get_safe_path(filename)
        if not path: return f"Error: Invalid filename '{filename}'."
        if _get_workspace_type() == "disk":
            parent_dir = os.path.dirname(path)
            if parent_dir:
                os.makedirs(parent_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Wrote '{filename}' to disk."
        else:
            _IN_MEMORY_FS[path] = content
            return f"Wrote '{filename}' to memory."
    except Exception as e:
        import traceback
        return f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}"

@tool
@with_quota
def list_workspace_files() -> str:
    """List all files in your workspace, showing line and character counts."""
    files = get_workspace_files()
    if not files: return "Workspace empty."
    res = []
    for k in sorted(files):
        content = get_workspace_file_content(k) or ""
        res.append(f"{k} (Lines: {len(content.splitlines())}, Chars: {len(content)})")
    return "\n".join(res)

@tool
@with_quota
def grep_workspace_file(filename: str, pattern: str, context_lines: int = 2) -> str:
    """Search for a regex pattern within a file, returning matching lines with surrounding context."""
    try:
        content = get_workspace_file_content(filename)
        if content is None: return f"Error: '{filename}' not found."
        
        lines = content.splitlines()
        max_matches = _get_tool_rule("grep_workspace_file", "max_matches", 10)
        
        compiled = re.compile(pattern, re.IGNORECASE)
        matches = []
        for i, line in enumerate(lines):
            if compiled.search(line):
                matches.append(i)
                if len(matches) >= max_matches:
                    break
                    
        if not matches: return f"No matches found for '{pattern}'."
        
        out = []
        for match_idx in matches:
            start = max(0, match_idx - context_lines)
            end = min(len(lines), match_idx + context_lines + 1)
            out.append(f"--- Match near line {match_idx + 1} ---")
            for j in range(start, end):
                prefix = "> " if j == match_idx else "  "
                out.append(f"{j + 1:04d}{prefix}{lines[j]}")
                
        return "\n".join(out)
    except Exception as e:
        import traceback
        return f"Grep Error: {e}\n\nTraceback:\n{traceback.format_exc()}"

@tool(approval_mode="always_require")
@with_quota
def remove_workspace_file(filename: str) -> str:
    """A destructive action that mandates human oversight. Deletes a file."""
    try:
        path = _get_safe_path(filename)
        if not path: return f"Error: Invalid filename '{filename}'."
        if _get_workspace_type() == "disk":
            if os.path.exists(path):
                os.remove(path)
                return f"Deleted: {filename}"
        else:
            if path in _IN_MEMORY_FS:
                del _IN_MEMORY_FS[path]
                return f"Deleted: {filename}"
        return f"Error: '{filename}' not found."
    except Exception as e:
        import traceback
        return f"Error: {e}\n\nTraceback:\n{traceback.format_exc()}"
