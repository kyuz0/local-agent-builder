import os
import asyncio
from agent_framework.openai import OpenAIChatCompletionClient
from agent_framework import tool, AgentSession
from tools import WORKSPACE_TOOLS, tool_quotas_ctx, with_quota, think_tool
from prompts import ORCHESTRATOR_INSTRUCTIONS, SUBAGENT_INSTRUCTIONS, SUBAGENT_DELEGATION_INSTRUCTIONS
import datetime
import config
import contextvars

# Module-level session for conversational memory persistence
_session = None

def _build_client():
    return OpenAIChatCompletionClient(
        base_url=config.cfg["api"]["openai_base_url"],
        api_key=os.getenv("OPENAI_API_KEY", "dummy"),
        model=config.cfg["api"]["openai_model"]
    )

def create_local_agent(subagent_callback=None, session_data=None):
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
    # -------------------------------------------------------------
    # Bounded Concurrent Sub-Agent Dispatcher
    # Utilizes inherited contextvars for shared cumulative quotas to prevent limit overruns.
    sem = asyncio.Semaphore(config.cfg.get("settings", {}).get("concurrency", {}).get("max_concurrent_tasks", 1))

    holds_token = contextvars.ContextVar('holds_token', default=False)

    async def _run_single_task(task_name: str, instructions: str) -> str:
        async with sem:
            token_setter = holds_token.set(True)
            try:
                current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                sub_agent = client.as_agent(
                    name=f"SubAgent_{task_name.replace(' ', '_')}",
                    instructions=SUBAGENT_INSTRUCTIONS.format(date=current_date, task_name=task_name),
                    tools=[WORKSPACE_TOOLS[0], WORKSPACE_TOOLS[3], think_tool], # read_workspace_file, grep_workspace_file, think
                    default_options={
                        "temperature": 0.0,
                        "extra_body": {
                            "chat_template_kwargs": {"enable_thinking": config.cfg["settings"]["enable_thinking"]}
                        }
                    }
                )
                final_text = ""
                stream = sub_agent.run(instructions, stream=True)
                async for update in stream:
                    if subagent_callback:
                        await subagent_callback(update, is_subagent=True, agent_name=f"SubAgent_{task_name}")
                    for c in update.contents:
                        if c.type == "text" and c.text:
                            final_text += c.text
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
    @tool(name="delegate_tasks", description="Delegate multiple independent tasks to specialized sub-agents to be executed concurrently. Pass a list of dictionaries, each with 'task_name' and 'instructions'.")
    @with_quota
    async def delegate_tasks(tasks: list[dict]) -> str:
        coroutines = []
        for t in tasks:
            name = t.get("task_name", "Unknown_Task")
            instr = t.get("instructions", "")
            coroutines.append(_run_single_task(name, instr))
            
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
    # Orchestrator retains full access to WORKSPACE_TOOLS but gains `delegate_tasks`
    tools_list = WORKSPACE_TOOLS + [delegate_tasks]
    current_date = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Define orchestrator strict quotas
    q_orch_delegate = 3
    q_orch_fetch = 10

    agent = client.as_agent(
        name="Scaffold_Agent",
        instructions=ORCHESTRATOR_INSTRUCTIONS.format(
            date=current_date,
            delegation_instructions=SUBAGENT_DELEGATION_INSTRUCTIONS.format(
                max_concurrency=config.cfg.get("settings", {}).get("concurrency", {}).get("max_concurrent_tasks", 1)
            ),
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
