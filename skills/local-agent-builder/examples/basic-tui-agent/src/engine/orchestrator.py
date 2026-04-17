import os
import asyncio
import re
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework import tool, AgentSession
from tools import WORKSPACE_TOOLS, tool_quotas_ctx, with_quota, think_tool
from prompts import ORCHESTRATOR_INSTRUCTIONS, SUBAGENT_INSTRUCTIONS, SUBAGENT_DELEGATION_INSTRUCTIONS
import datetime
import config
import contextvars

# Module-level session for conversational memory persistence
_session = None

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
            token_setter = holds_token.set(True)
            try:
                current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                target_config = builder.sub_agents[0] if builder.sub_agents else None
                if agent_id and builder.sub_agents:
                    for conf in builder.sub_agents:
                        if conf.name == agent_id:
                            target_config = conf
                            break
                            
                sub_tools = apply_tool_permissions(target_config.tools.copy() if target_config else [])
                if think_tool not in sub_tools:
                    sub_tools.append(think_tool)
                    
                sub_instr = ""
                if target_config:
                    try:
                        sub_instr = target_config.instructions.format(date=current_date, task_name=task_name)
                    except KeyError:
                        sub_instr = target_config.instructions
                else:
                    sub_instr = SUBAGENT_INSTRUCTIONS.format(date=current_date, task_name=task_name)

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
                    
                    stream = sub_agent.run(current_input, stream=True)
                    async for update in stream:
                        if subagent_callback:
                            await subagent_callback(update, is_subagent=True, agent_name=f"SubAgent_{task_name}")
                        for c in update.contents:
                            if c.type == "text" and c.text:
                                final_text += c.text
                                
                        if getattr(update, "user_input_requests", None):
                            user_input_requests.extend(update.user_input_requests)
                            
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
                holds_token.reset(token_setter)

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
    # Orchestrator retains full access to WORKSPACE_TOOLS but gains `delegate_tasks`
    tools_list = apply_tool_permissions(builder.tools.copy())
    if builder.sub_agents:
        tools_list.append(delegate_tasks)
    current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Define orchestrator strict quotas
    q_orch_delegate = 3
    q_orch_fetch = 10

    agent = client.as_agent(
        name=_sanitize_name(builder.name),
        instructions=builder.instructions.format(
            date=current_date,
            delegation_instructions=SUBAGENT_DELEGATION_INSTRUCTIONS.format(
                max_concurrency=config.cfg.get("settings", {}).get("concurrency", {}).get("max_concurrent_tasks", 1)
            ),
            delegate_quota=q_orch_delegate,
            fetch_quota=q_orch_fetch
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
