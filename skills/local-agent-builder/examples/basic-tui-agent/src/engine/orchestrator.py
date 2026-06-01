import os
import asyncio
import re
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework import tool, AgentSession
from tools import WORKSPACE_TOOLS, tool_quotas_ctx, with_quota, think_tool, QuotaAbortException
from prompts import ORCHESTRATOR_INSTRUCTIONS, SUBAGENT_INSTRUCTIONS, SUBAGENT_DELEGATION_INSTRUCTIONS
import datetime
import config
import contextvars

# Module-level session for conversational memory persistence
_session = None
delegation_depth_ctx = contextvars.ContextVar('delegation_depth_ctx', default=0)
available_sub_agents_ctx = contextvars.ContextVar('available_sub_agents_ctx', default=[])

def apply_tool_permissions(tools: list) -> list:
    """Dynamically applies approval boundaries mapped in config.yaml."""
    perms = config.cfg.get("settings", {}).get("permissions", {})
    for t in tools:
        if hasattr(t, "name") and hasattr(t, "approval_mode"):
            if perms.get(t.name) == "require_approval":
                t.approval_mode = "always_require"
            else:
                t.approval_mode = "never_require"
    return tools

def _sanitize_name(name: str) -> str:
    """Ensure the name matches ^[a-zA-Z0-9_-]+$ for OpenAI API."""
    return re.sub(r'[^a-zA-Z0-9_-]', '_', name)

def _get_quota_format_vars() -> dict:
    """Extract all quotas from config as {tool_name_quota: int} format variables.
    
    Each key in settings.quotas (e.g. 'web_search') becomes a prompt variable
    named '{web_search_quota}' with its integer limit value. Both flat integers
    and dict-with-limit configs are handled transparently.
    """
    quotas = config.cfg.get("settings", {}).get("quotas", {})
    result = {}
    for key, val in quotas.items():
        result[key + "_quota"] = val.get("limit", 0) if isinstance(val, dict) else val
    return result

def _safe_format(template: str, **kwargs) -> str:
    """Format a template string, leaving unknown {keys} as literal text.
    
    Unlike str.format(), this does NOT crash on missing keys. Unknown
    placeholders stay as-is (e.g. '{custom_var}' remains '{custom_var}').
    This prevents a single missing key from nuking the entire prompt.
    """
    class _SafeDict(dict):
        def __missing__(self, key):
            return '{' + key + '}'
    return template.format_map(_SafeDict(**kwargs))

def _get_default_options():
    options = {"temperature": 0.0}
    # OpenAI's official API rejects "chat_template_kwargs"
    if "api.openai.com" not in config.cfg.get("api", {}).get("openai_base_url", ""):
        options["extra_body"] = {
            "chat_template_kwargs": {"enable_thinking": config.cfg["settings"].get("enable_thinking", False)}
        }
    return options

def _build_client():
    return OpenAIChatCompletionClient(
        base_url=config.cfg["api"]["openai_base_url"],
        api_key=os.getenv("OPENAI_API_KEY", "dummy"),
        model=config.cfg["api"]["openai_model"]
    )

def create_local_agent(builder, subagent_callback=None, session_data=None):
    """
    Returns (agent, session). Session is None when conversational memory is disabled.
    Agent is re-created each call to pick up config changes (thinking toggle).
    """
    global _session
    client = _build_client()
    
    # -------------------------------------------------------------
    # SDK Bounded Dispatcher
    # -------------------------------------------------------------
    # [!CAUTION] RULES FOR LLM CODING ASSISTANTS EDITING THIS:
    # 1. This engine module is OUT OF BOUNDS. Do not hardcode sub-agents here.
    # 2. Sub-agents MUST be defined in `src/app.py` via `SubAgentConfig`.
    # 3. The logic below dynamically reads the builder config and mounts the TUI streams.
    # -------------------------------------------------------------
    # -------------------------------------------------------------
    # Bounded Concurrent Sub-Agent Dispatcher
    # Utilizes inherited contextvars for shared cumulative quotas to prevent limit overruns.
    sem = asyncio.Semaphore(config.cfg.get("settings", {}).get("concurrency", {}).get("max_concurrent_tasks", 1))

    holds_token = contextvars.ContextVar('holds_token', default=False)

    async def _run_single_task(task_name: str, instructions: str, agent_id: str = None) -> str:
        async with sem:
            parent_depth = delegation_depth_ctx.get()
            depth_token = delegation_depth_ctx.set(parent_depth + 1)
            token_setter = holds_token.set(True)
            try:
                current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Look up the target agent from the CALLER's available sub-agents (scoped, not global)
                caller_sub_agents = available_sub_agents_ctx.get()
                target_config = None
                if agent_id and caller_sub_agents:
                    for conf in caller_sub_agents:
                        if conf.name == agent_id:
                            target_config = conf
                            break
                    if target_config is None:
                        return f"## Error for {task_name}\nFailed to delegate: Sub-agent named '{agent_id}' does not exist. Available sub-agents for this caller: {[c.name for c in caller_sub_agents]}.\n---"
                else:
                    target_config = caller_sub_agents[0] if caller_sub_agents else None
                    
                sub_tools = apply_tool_permissions(target_config.tools.copy() if target_config else [])
                # Only inject delegate_tasks if the TARGET agent has its own children
                target_children = target_config.sub_agents if target_config else []
                if target_children and delegate_tasks not in sub_tools:
                    sub_tools.append(delegate_tasks)
                if think_tool not in sub_tools:
                    sub_tools.append(think_tool)
                
                # Scope the available sub-agents for the target agent's own delegate_tasks calls
                children_token = available_sub_agents_ctx.set(target_children)
                    
                sub_instr = ""
                if target_config:
                    sub_instr = _safe_format(
                        target_config.instructions,
                        date=current_date,
                        task_name=task_name,
                        workspace_dir=config.cfg.get("settings", {}).get("workspace", {}).get("dir", "."),
                        delegation_instructions=SUBAGENT_DELEGATION_INSTRUCTIONS.format(
                            max_concurrency=config.cfg.get("settings", {}).get("concurrency", {}).get("max_concurrent_tasks", 1)
                        ),
                        **_get_quota_format_vars()
                    )
                else:
                    sub_instr = _safe_format(
                        SUBAGENT_INSTRUCTIONS,
                        date=current_date,
                        task_name=task_name,
                        workspace_dir=config.cfg.get("settings", {}).get("workspace", {}).get("dir", "."),
                        delegation_instructions=SUBAGENT_DELEGATION_INSTRUCTIONS.format(
                            max_concurrency=config.cfg.get("settings", {}).get("concurrency", {}).get("max_concurrent_tasks", 1)
                        ),
                        **_get_quota_format_vars()
                    )

                sub_agent = client.as_agent(
                    name=_sanitize_name(f"SubAgent_{task_name}"),
                    instructions=sub_instr,
                    tools=sub_tools,
                    default_options=_get_default_options()
                )
                final_text = ""
                current_input = instructions
                has_requests = True
                while has_requests:
                    has_requests = False
                    user_input_requests = []
                    
                    try:
                        stream = sub_agent.run(current_input, stream=True)
                        async for update in stream:
                            if subagent_callback:
                                await subagent_callback(update, is_subagent=True, agent_name=f"SubAgent_{task_name}")
                            for c in update.contents:
                                if c.type == "text" and c.text:
                                    final_text += c.text
                                    
                            if getattr(update, "user_input_requests", None):
                                user_input_requests.extend(update.user_input_requests)
                    except QuotaAbortException as e:
                        return f"## Error for {task_name}\nTask forcefully aborted: {str(e)}\n---"
                            
                    if user_input_requests:
                        has_requests = True
                        responses = []
                        if subagent_callback:
                            responses = await subagent_callback(None, is_subagent=True, agent_name=f"SubAgent_{task_name}", approval_requests=user_input_requests)
                            
                        new_inputs = [current_input] if isinstance(current_input, str) else list(current_input)
                        if responses:
                            new_inputs.extend(responses)
                        current_input = new_inputs
                        
                if subagent_callback:
                    await subagent_callback(None, is_subagent=True, agent_name=f"SubAgent_{task_name}", is_done=True)

                return f"## Result for {task_name}\n{final_text}\n---"
            finally:
                available_sub_agents_ctx.reset(children_token)
                holds_token.reset(token_setter)
                delegation_depth_ctx.reset(depth_token)

    # -------------------------------------------------------------
    # [!CAUTION] CONCURRENCY ARCHITECTURE FOR LLM CODING ASSISTANTS:
    # This template utilizes a global `asyncio.Semaphore` to rigidly enforce max limits.
    # To prevent deeply nested delegation streams from deadlocking (e.g. parent awaits child
    # and starves the token pool), `delegate_tasks` utilizes contextvars
    # to mathematically surrender its token while waiting, allowing children to safely execute.
    # -------------------------------------------------------------
    @tool(name="delegate_tasks", description="Delegate multiple independent tasks to specialized sub-agents to be executed concurrently. Pass a list of dictionaries, each with 'task_name', 'instructions', and optionally 'agent_id'.")
    @with_quota
    async def delegate_tasks(tasks: list[dict]) -> str:
        coroutines = []
        for t in tasks:
            name = t.get("task_name", "Unknown_Task")
            instr = t.get("instructions", "")
            aid = t.get("agent_id", None)
            coroutines.append(_run_single_task(name, instr, aid))
            
        was_holding = holds_token.get()
        if was_holding:
            sem.release()

        try:
            results = await asyncio.gather(*coroutines, return_exceptions=True)
        finally:
            if was_holding:
                await sem.acquire()
        
        final_output = []
        for res in results:
            if isinstance(res, Exception):
                final_output.append(f"## Error\nTask failed with exception: {res}\n---")
            else:
                final_output.append(str(res))
                
        return "\n\n".join(final_output)

    # -------------------------------------------------------------
    # [!CAUTION] RULES FOR LLM CODING ASSISTANTS EDITING THIS:
    # When adding or removing standard tools (e.g., pruning `web_search`), modify the `WORKSPACE_TOOLS` array or this `tools_list`.
    # DO NOT rewrite this entire function or file from scratch.
    # -------------------------------------------------------------
    # -------------------------------------------------------------
    # Orchestrator retains full access to its declared tools, gains `delegate_tasks` if it has sub_agents
    tools_list = apply_tool_permissions(builder.tools.copy())
    if builder.sub_agents:
        tools_list.append(delegate_tasks)
    # Set the orchestrator's available sub-agents for scoped delegation
    available_sub_agents_ctx.set(builder.sub_agents)
    current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    workspace_dir = config.cfg.get("settings", {}).get("workspace", {}).get("dir", ".")

    agent = client.as_agent(
        name=_sanitize_name(builder.name),
        instructions=_safe_format(
            builder.instructions,
            date=current_date,
            workspace_dir=workspace_dir,
            delegation_instructions=SUBAGENT_DELEGATION_INSTRUCTIONS.format(
                max_concurrency=config.cfg.get("settings", {}).get("concurrency", {}).get("max_concurrent_tasks", 1)
            ),
            **_get_quota_format_vars()
        ),
        tools=tools_list,
        default_options=_get_default_options()
    )
    
    session = None
    if config.cfg["settings"].get("enable_conversational_memory", False):
        if session_data is not None:
            _session = AgentSession.from_dict(session_data)
        elif _session is None:
            _session = agent.create_session()
        session = _session
    
    return agent, session

def reset_session():
    """Clear the conversation session (called by /new)."""
    global _session
    _session = None
