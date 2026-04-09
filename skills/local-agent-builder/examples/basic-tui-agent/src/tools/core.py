import contextvars
import functools
import asyncio

# --- TOOL QUOTA SYSTEM ---
# Protects local LLM workflows from infinite retry loops (e.g., repeatedly failing to parse a URL)
tool_quotas_ctx = contextvars.ContextVar('tool_quotas', default=None)

def check_quota(tool_name: str) -> str | None:
    """Check if the specific tool has exceeded its per-invocation quota."""
    ctx = tool_quotas_ctx.get()
    if ctx and tool_name in ctx:
        if ctx[tool_name]["used"] >= ctx[tool_name]["limit"]:
            return (
                f"Error: Quota reached. You have used the '{tool_name}' tool "
                f"{ctx[tool_name]['limit']} times out of your limit. "
                f"You MUST summarize what you've done and state clearly that you "
                f"had to stop due to quota limits."
            )
        ctx[tool_name]["used"] += 1
    return None

def _get_tool_rule(tool_name: str, rule_key: str, default_val: int) -> int:
    """Extract custom quota rules (like max_lines) for a specific tool."""
    ctx = tool_quotas_ctx.get()
    if ctx and tool_name in ctx and "rules" in ctx[tool_name]:
        return ctx[tool_name]["rules"].get(rule_key, default_val)
    return default_val

def with_quota(func):
    """Decorator to enforce quotas dynamically based on the function's name and surface full diagnostic tracebacks safely."""
    import traceback
    if asyncio.iscoroutinefunction(func):
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            if err := check_quota(func.__name__): return err
            try:
                return await func(*args, **kwargs)
            except Exception as e:
                return f"CRITICAL TOOL EXECUTION ERROR: {func.__name__} failed internally.\n\nException Details:\n{traceback.format_exc()}"
        return async_wrapper
    else:
        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            if err := check_quota(func.__name__): return err
            try:
                return func(*args, **kwargs)
            except Exception as e:
                return f"CRITICAL TOOL EXECUTION ERROR: {func.__name__} failed internally.\n\nException Details:\n{traceback.format_exc()}"
        return sync_wrapper
