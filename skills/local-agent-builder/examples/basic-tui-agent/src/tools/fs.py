from typing import Dict, List
import os
import re
from agent_framework import tool
from tools.core import with_quota, _get_tool_rule

# --- WORKSPACE FILE SYSTEM ---
_IN_MEMORY_FS: Dict[str, str] = {}

def _get_workspace_type() -> str:
    from config import cfg
    return cfg.get("settings", {}).get("workspace", {}).get("type", "memory")

def _get_workspace_dir() -> str:
    from config import cfg
    return cfg.get("settings", {}).get("workspace", {}).get("dir", ".")

def _get_safe_path(filename: str) -> str:
    clean_name = os.path.basename(filename)
    if not clean_name or clean_name != filename: return ""
    if _get_workspace_type() == "disk":
        return os.path.join(_get_workspace_dir(), clean_name)
    return clean_name

def get_workspace_files() -> List[str]:
    """Helper for TUI to list files agnostic of storage backend."""
    if _get_workspace_type() == "disk":
        d = _get_workspace_dir()
        if not os.path.isdir(d): return []
        return [f for f in os.listdir(d) if os.path.isfile(os.path.join(d, f))]
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
    except Exception as e: return f"Error: {e}"

@tool
@with_quota
def write_workspace_file(filename: str, content: str) -> str:
    """Save content to your workspace."""
    try:
        path = _get_safe_path(filename)
        if not path: return f"Error: Invalid filename '{filename}'."
        if _get_workspace_type() == "disk":
            os.makedirs(_get_workspace_dir(), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Wrote '{filename}' to disk."
        else:
            _IN_MEMORY_FS[path] = content
            return f"Wrote '{filename}' to memory."
    except Exception as e: return f"Error: {e}"

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
    except Exception as e: return f"Grep Error: {e}"

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
    except Exception as e: return f"Error: {e}"
