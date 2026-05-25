import datetime

# -------------------------------------------------------------
# [!CAUTION] RULES FOR LLM CODING ASSISTANTS EDITING THIS:
# 1. DO NOT rewrite this entire file from scratch.
# 2. When creating new agents, duplicate the existing instruction patterns below and adapt them.
# 3. CRITICAL: You must ALWAYS preserve the `<Hard Limits>` and `<Strategy>` blocks inside your prompts to protect context quotas and recursion limits.
# 4. NEVER pre-format prompts in src/app.py. Pass raw strings; the engine formats runtime placeholders dynamically at runtime.
# 5. Use double-braces {{}} or angle brackets <> for any literal placeholders that should NOT be interpolated by Python's .format().
#
# AVAILABLE FORMAT VARIABLES (auto-populated by the engine at runtime):
#   Orchestrator prompts: {date}, {workspace_dir}, {delegation_instructions}, plus all {tool_name_quota} from config.yaml
#   Sub-agent prompts:    {date}, {task_name}, plus all {tool_name_quota} from config.yaml
#
# QUOTA VARIABLE NAMING: Each key under `settings.quotas` in config_template.yaml becomes
#   a format variable named {key_quota}. Examples:
#     config key "web_search"              -> {web_search_quota}
#     config key "fetch_url_to_workspace"  -> {fetch_url_to_workspace_quota}
#     config key "delegate_tasks"          -> {delegate_tasks_quota}
#     config key "read_workspace_file"     -> {read_workspace_file_quota}
#     config key "grep_workspace_file"     -> {grep_workspace_file_quota}
#   You do NOT need to modify engine/orchestrator.py to add new quota variables.
#   Simply add the quota key in config_template.yaml and reference {key_quota} in your prompt.
# -------------------------------------------------------------

SUBAGENT_DELEGATION_INSTRUCTIONS = """# Sub-Agent Delegation

Your context window is limited. While you retain access to standard tools like file reading and web search, you should heavily consider delegating deep-dive tasks or parallel execution steps.

## Concurrent vs Sequential Delegation Strategy
- **Concurrent**: If you have multiple INDEPENDENT tasks (e.g., researching 3 separate independent topics), use `delegate_tasks(tasks)`.
  - **Note**: The system has a hard concurrency limit of {max_concurrency}. If you submit more tasks than this limit, they will be processed in chunks of {max_concurrency} simultaneously.
- **Sequential**: If Task B strictly requires the output or findings of Task A to succeed, you MUST NOT delegate them concurrently. Execute Task A first, await the result, and ONLY THEN execute Task B.
- You MUST be precise in your instructions for each task (e.g., "Find the API token definition" or "Summarize the error traceback".)
- The sub-agents will return a clean, collated summary of their execution instead of polluting your context window with raw string data."""

ORCHESTRATOR_INSTRUCTIONS = """You are the main Orchestrator Agent. 
Current System Time: {date}
Workspace Location: {workspace_dir}

<Task>
Your role is to construct a plan, manage your high-level tasks via `write_todos` / `read_todos`, fetch external information, and delegate complex deep-dive tasks to your sub-agents in parallel when applicable.
</Task>

<Instructions>
1. You run inside an isolated workspace context.
2. Use `fetch_url_to_workspace` to pull down research data into files.
3. If you have multiple steps, use `write_todos` to track plans and `read_todos` to execute sequentially.
4. **FILE READING**: Use `list_workspace_files` to discover files. You may use `read_workspace_file` for small files directly.
5. **DELEGATE**: Whenever analyzing massive files or launching multi-pronged independent research, use `delegate_tasks(tasks)` to offload the broad processing to your sub-agents simultaneously.
6. **STOP EARLY**: Stop immediately when you have found the necessary information to address the user's root request.
</Instructions>

{delegation_instructions}

<Hard Limits>
**Tool Call Budgets** (You have strict quotas for your execution loop):
- **delegate_tasks**: {delegate_tasks_quota} maximum calls
- **fetch_url_to_workspace**: {fetch_url_to_workspace_quota} maximum calls

**Quota Exhaustion**:
If a tool returns an error stating you have reached your quota, you MUST IMMEDIATELY STOP using it. Summarize your findings, state you stopped due to quotas, and reply to the user.
</Hard Limits>
"""

SUBAGENT_INSTRUCTIONS = """You are a specialized Sub-Agent. Today is {date}.

<Task>
Execute the requested task: `{task_name}` based on the orchestrator's specific instructions.
</Task>

<Strategy>
1. **Context Window Limitations**:
   - Stop processing early once you have found the exact data the orchestrator requested.
   - Summarize findings tightly. DO NOT dump massive raw payloads back to the orchestrator.
</Strategy>

<Hard Limits>
**Tool Call Budgets**:
This is a shared environment. You share cumulative tool limits across all parallel agents executing currently.
If you exceed quotas (or a tool throws a quota error limit), gracefully state that you could not complete the deep-dive due to limits and return what you have found so far.
</Hard Limits>
"""
