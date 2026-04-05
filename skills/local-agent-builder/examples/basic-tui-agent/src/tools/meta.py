from agent_framework import tool
from tools.core import with_quota

@tool(approval_mode="never_require")
@with_quota
def think_tool(reflection: str) -> str:
    """Use this to record deliberate thinking / reasoning about the current situation and potentially next steps in a concise way."""
    return f"Reflection recorded: {reflection}"
