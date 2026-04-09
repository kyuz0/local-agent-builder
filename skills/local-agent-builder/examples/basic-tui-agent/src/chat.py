import os
import asyncio
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework import tool
from tools import WORKSPACE_TOOLS, tool_quotas_ctx, with_quota, think_tool
from prompts import ORCHESTRATOR_INSTRUCTIONS, SUBAGENT_INSTRUCTIONS, SUBAGENT_DELEGATION_INSTRUCTIONS
import datetime
import config

# Module-level session for conversational memory persistence
_session = None

def _build_client():
    return OpenAIChatCompletionClient(
        base_url=config.cfg["api"]["openai_base_url"],
        api_key=os.getenv("OPENAI_API_KEY", "dummy"),
        model=config.cfg["api"]["openai_model"]
    )

def create_local_agent(subagent_callback=None):
    """
    Returns (agent, session). Session is None when conversational memory is disabled.
    Agent is re-created each call to pick up config changes (thinking toggle).
    """
    global _session
    client = _build_client()
    
    # -------------------------------------------------------------
    # SUB-AGENT DELEGATION EXAMPLE
    # -------------------------------------------------------------
    # [!CAUTION] RULES FOR LLM CODING ASSISTANTS EDITING THIS:
    # 1. LOCATION: ALWAYS define delegation tools INSIDE this `create_local_agent()` function. DO NOT move them to `tools/`.
    # 2. NO HALLUCINATIONS: DO NOT invent global counters or use `_get_next_id()` to name sub-agents dynamically. Hardcode `name="SubAgentName"` below.
    # 3. REUSE: Read `IMPLEMENTATION.md` Section 6 before attempting to add or modify sub-agent delegations. Do not rewrite from scratch.
    # 4. DEPENDENCY ORDERING (CRITICAL): Python evaluates these local closure functions sequentially. If Sub-Agent A uses a delegation tool for Sub-Agent B, you MUST define Sub-Agent B's tool completely ABOVE Sub-Agent A's tool. Otherwise, you will get a NameError or falsely omit the schema!
    # -------------------------------------------------------------
    # Define sub-agent strict quotas
    q_sub_read = config.cfg.get("settings", {}).get("quotas", {}).get("read_workspace_file", {}).get("limit", 10)
    q_sub_grep = config.cfg.get("settings", {}).get("quotas", {}).get("grep_workspace_file", {}).get("limit", 15)
    max_read_lines = config.cfg.get("settings", {}).get("quotas", {}).get("read_workspace_file", {}).get("rules", {}).get("max_lines", 300)
    q_sub_think = 5

    @tool(name="delegate_file_analysis", description="Delegate deep file analysis to a specialized sub-agent. This is MANDATORY for inspecting file contents to prevent polluting your context window.")
    @with_quota
    async def delegate_file_analysis(filename: str, instructions: str) -> str:
        from tools.fs import _get_safe_path, _get_workspace_dir, _get_workspace_type, _IN_MEMORY_FS
        path = _get_safe_path(filename)
        total_lines = 0
        if path:
            if _get_workspace_type() == "disk" and os.path.exists(path):
                with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                    total_lines = sum(1 for _ in f)
            elif _get_workspace_type() == "memory" and path in _IN_MEMORY_FS:
                total_lines = len(_IN_MEMORY_FS[path].splitlines())
        else:
            return "Error: Invalid file."
            
        current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Build dynamic subagent on-demand to inject specific filename and stats
        sub_agent = client.as_agent(
            name="file_analyzer",
            instructions=SUBAGENT_INSTRUCTIONS.format(
                date=current_date,
                filename=filename,
                total_file_lines=total_lines,
                max_read_lines=max_read_lines,
                read_quota=q_sub_read,
                grep_quota=q_sub_grep,
                think_quota=q_sub_think
            ),
            tools=[WORKSPACE_TOOLS[0], WORKSPACE_TOOLS[3], think_tool], # read_workspace_file, grep_workspace_file
            default_options={
                "temperature": 0.0,
                "extra_body": {
                    "chat_template_kwargs": {"enable_thinking": config.cfg["settings"]["enable_thinking"]}
                }
            }
        )

        # Give sub-agent its own quotas
        token = tool_quotas_ctx.set({
            "read_workspace_file": {"used": 0, "limit": q_sub_read},
            "grep_workspace_file": {"used": 0, "limit": q_sub_grep},
            "think_tool": {"used": 0, "limit": q_sub_think}
        })
        try:
            final_text = ""
            stream = sub_agent.run(instructions, stream=True)
            async for update in stream:
                if subagent_callback:
                    await subagent_callback(update, is_subagent=True)
                for c in update.contents:
                    if c.type == "text" and c.text:
                        final_text += c.text
            return final_text
        finally:
            tool_quotas_ctx.reset(token)

    # -------------------------------------------------------------
    # [!CAUTION] RULES FOR LLM CODING ASSISTANTS EDITING THIS:
    # When adding or removing standard tools (e.g., pruning `web_search`), modify the `WORKSPACE_TOOLS` array or this `tools_list`.
    # DO NOT rewrite this entire function or file from scratch.
    # -------------------------------------------------------------
    # Orchestrator retains full access to WORKSPACE_TOOLS but gains `delegate_file_analysis`
    tools_list = WORKSPACE_TOOLS + [delegate_file_analysis]
    current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Define orchestrator strict quotas
    q_orch_delegate = 3
    q_orch_fetch = 10

    agent = client.as_agent(
        name="Scaffold_Agent",
        instructions=ORCHESTRATOR_INSTRUCTIONS.format(
            date=current_date,
            delegation_instructions=SUBAGENT_DELEGATION_INSTRUCTIONS,
            delegate_quota=q_orch_delegate,
            fetch_quota=q_orch_fetch
        ),
        tools=tools_list,
        default_options={
            "temperature": 0.0,
            "extra_body": {
                "chat_template_kwargs": {"enable_thinking": config.cfg["settings"]["enable_thinking"]}
            }
        }
    )
    
    session = None
    if config.cfg["settings"].get("enable_conversational_memory", False):
        if _session is None:
            _session = agent.create_session()
        session = _session
    
    return agent, session

def reset_session():
    """Clear the conversation session (called by /new)."""
    global _session
    _session = None
