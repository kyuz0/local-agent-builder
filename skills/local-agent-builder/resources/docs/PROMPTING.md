# Agent Prompting Guidelines

When building agents using the `basic-tui-agent` scaffold and the Microsoft Agent Framework, you MUST structure your prompts to maximize tool execution reliability and strictly bound LLM context rot. 

Always adhere to the following architecture seen in optimal blueprints (like `local-research`):

## 1. Domain Segregation (Orchestrator vs Sub-Agent)
Never build a monolithic "god prompt". Split instructions by domain:
- **`ORCHESTRATOR_INSTRUCTIONS`**: The top-level agent prompt. Focus entirely on *planning*, *delegation*, and managing global state via tools (like `write_todos`).
- **`SUBAGENT_INSTRUCTIONS`**: The isolated worker prompt. Focus strictly on *execution* and *extraction* (e.g., searching, grepping, calculating).
- **`SUBAGENT_DELEGATION_INSTRUCTIONS`**: A highly strategic subset of instructions injected into the Orchestrator explaining *when* and *how* to use its `delegate_task` tool. Tell the orchestrator exactly what to pass into the sub-agent and how to parallelize requests.

## 2. Dynamic Quota Injection
Agent tool schemas define what a tool *does*, but prompts define *when to stop using it*. The engine **auto-populates** quota format variables from `config_template.yaml` into all prompt templates at runtime. You do NOT need to modify `src/engine/orchestrator.py` to add quota variables.

**Naming Convention:** Each key under `settings.quotas` in your config YAML becomes a prompt format variable named `{key_quota}`:
```yaml
# config_template.yaml
settings:
  quotas:
    web_search: 10               # -> {web_search_quota} = 10
    delegate_tasks: 5            # -> {delegate_tasks_quota} = 5
    fetch_url_to_workspace: 5    # -> {fetch_url_to_workspace_quota} = 5
    read_workspace_file:         # -> {read_workspace_file_quota} = 50
      limit: 50
      rules:
        max_lines: 300
```

To use in prompts, simply reference the variable:
```python
# In prompts.py
SUBAGENT_INSTRUCTIONS = "... \nYou have {web_search_quota} searches maximum. \n..."
# The engine calls .format(**_get_quota_format_vars()) automatically — no manual formatting needed!
```

> [!WARNING]
> **Quotas are GLOBAL** — shared across ALL agents in the system, not per-agent.
> Each key under `settings.quotas` MUST appear exactly once.
> YAML silently drops duplicate keys (only the last value survives), so do NOT create separate per-agent quota sections with duplicate key names.

If an agent has `N` active quotas in its execution loop, all `N` must be visibly documented in its instructions so it can strategize its remaining bandwidth.

## 3. Strict `<Hard Limits>` Semantic Tagging
The Microsoft Agent Framework relies on iterative tool execution loops. You must explicitly teach the LLM to yield control (Stop Early) rather than burning tokens in endless recursive calls. Define a `<Hard Limits>` XML block:

```markdown
<Hard Limits>
**Quota Exhaustion**:
If a tool returns a quota reached error, you MUST IMMEDIATELY STOP using it. 
Summarize what you have so far and yield to the user.

**Stop Early**:
Do not maximize your quotas. Stop immediately when:
1. You have sufficient information to answer the core query.
2. The last 2 searches returned highly redundant data.
</Hard Limits>
```

## 4. Forced Reflexion (`think_tool`)
Always inject a lightweight `think_tool(reflection: str)` into your generic sub-agents and explicitly mandate its usage after heavy operations.
```markdown
<Show Your Thinking>
After reading a massive file or making a web search, use `think_tool` to analyze the payload:
- What did I just find?
- What is still missing?
- Can I answer the question now?
</Show Your Thinking>
```
This inserts a structural pause into the LLM's autoregressive generation loop, sharply improving downstream tool parameters and reducing hallucinations on large chunks of retrieved data.

## 5. Anti-Looping Traps (CRITICAL for Local LLMs)
Small local LLMs (under 32B parameters) possess notoriously weak state-tracking capabilities. If they use a tool (like `write_todos` or `think_tool`) and it succeeds without drastically altering the semantic context, their attention mechanisms will heavily weight the exact same tokens and repeat the identical tool call infinitely. 

You MUST inject a strict anti-looping directive into the Orchestrator and every Sub-Agent's system prompt:

```markdown
<Anti-Looping>
NEVER call the exact same tool with the exact same arguments consecutively. 
If you just used `write_todos` to track your plan, DO NOT call it again in the next step. You must forcefully execute the next logical step in your plan (e.g., delegate the task, read a file, or write a report).
If you find yourself caught in a loop, immediately summarize your findings and stop.
</Anti-Looping>
```

## 6. String Interpolation Safety & Startup Formatting Rules (Python Runtime Trap)
When using formatting variables in prompt strings, you must follow these strict rules to avoid crashing the Python runtime with a `KeyError`:
1. **NEVER Pre-Format Prompts in `src/app.py`:** Do not call `.format()` on system prompt strings (such as `ORCHESTRATOR_INSTRUCTIONS` or `SUBAGENT_INSTRUCTIONS`) inside `src/app.py`. The orchestration engine dynamically formats them at runtime (e.g., inserting `{date}`, `{task_name}`, `{delegation_instructions}`, etc.). Pre-formatting them at startup will throw a `KeyError` because runtime variables like `{task_name}` are not yet available at startup. Always pass the raw, unformatted prompt strings directly to the `AgentBuilder` and `SubAgentConfig` constructors.
2. **Double-Braces for Non-Runtime Placeholders:** When writing custom instructions that contain literal braces (e.g., explaining JSON schemas, XML blocks, or writing placeholders like `{{run_folder}}` that the LLM should read), you **MUST** use double-braces `{{placeholder}}` or angle brackets `<placeholder>` so Python's `.format()` method ignores them at runtime. Any single-brace `{placeholder}` that is not explicitly supplied by the engine's `.format()` calls in `src/engine/orchestrator.py` will cause a fatal `KeyError` crash.

## 7. Placeholder Variable Preservation & Task Context Propagation (CRITICAL)
When editing, customizing, or extending system prompts (especially in `src/prompts.py`), you must ensure that all required format placeholder keys are retained and that task context is correctly passed down to child agents.

**Available Format Variables (auto-populated by the engine — do NOT modify `engine/orchestrator.py` to add more):**

| Variable | Available In | Source |
|---|---|---|
| `{date}` | Orchestrator + Sub-agents | Current datetime, auto-set |
| `{workspace_dir}` | Orchestrator + Sub-agents | `settings.workspace.dir` from config |
| `{task_name}` | Sub-agents only | Passed from parent via `delegate_tasks` |
| `{delegation_instructions}` | Orchestrator + Sub-agents | Content of `SUBAGENT_DELEGATION_INSTRUCTIONS` |
| `{tool_name_quota}` | Orchestrator + Sub-agents | Every key under `settings.quotas` in config (see §2) |

> [!TIP]
> The engine uses a **safe formatter** that leaves unknown `{keys}` as literal text instead of crashing. If you add a custom placeholder like `{my_custom_var}` that isn't in the table above, it simply stays as `{my_custom_var}` in the rendered prompt. It won't crash the application, but the LLM will see it as literal text.

1. **Do NOT Strip Essential Placeholders:** The scaffold templates (like `SUBAGENT_INSTRUCTIONS` and `ORCHESTRATOR_INSTRUCTIONS`) are pre-optimized. They contain Python format keys (like `{date}`, `{task_name}`, `{delegation_instructions}`, `{delegate_tasks_quota}`, `{fetch_url_to_workspace_quota}`) that the orchestration engine *expects* to interpolate via `.format()`. If you delete `{task_name}` from a sub-agent's instructions, the sub-agent will never receive the actual query or task details and will run blindly!
2. **Explicitly Command Task Breakdown & Propagation:** In the Orchestrator's instructions, you must explicitly direct it to analyze the user's query (e.g., read it from `query.md` or the initial input), break it down into highly specific research angles/tasks, and pass *those specific angles* to the sub-agents via the `delegate_tasks` tool (rather than passing generic or hardcoded instructions).
3. **Verify String Format Alignment:** Before completing execution, cross-reference `src/prompts.py` against `src/app.py` and `src/engine/orchestrator.py` to verify that every format key used by the code exists in your prompt strings, and that all variable context is propagated correctly.
4. **Align Sub-Agent Config Names and Prompt Instructions:** Ensure that the `name` parameter in `SubAgentConfig` definitions inside `src/app.py` matches exactly with the `agent_id` expected by the prompt instructions and passed to the `delegate_tasks` tool. For example, if you register the analyzer sub-agent as `name="Analyzer"`, you must instruct the parent agent to pass `"agent_id": "Analyzer"` when delegating to it. Do not use mismatching names like configuring `"Analyzer"` but prompting the agent to pass `"agent_id": "page_analyzer"`, as this will trigger execution failures.
5. **Use Auto-Populated Quota Variables:** Reference quota limits using the `{tool_name_quota}` convention (e.g. `{web_search_quota}`, `{delegate_tasks_quota}`) documented in §2. Do NOT invent custom format keys that require modifying `engine/orchestrator.py`.

## 8. Agent-ID Routing in Delegation Prompts (Multi-Agent Systems)
In multi-agent systems with more than one sub-agent type (e.g., Searcher + Analyzer), the LLM does **not** inherently know which sub-agent to target when calling `delegate_tasks`. The `agent_id` parameter routes delegation to the correct sub-agent by matching the `name` field in `SubAgentConfig`. If `agent_id` is omitted, the engine silently defaults to `sub_agents[0]`, which is almost certainly the wrong agent.

**You MUST explicitly teach the LLM the available agent names and when to use each one in the system prompt.** Include a concrete call example directly in the prompt:

```markdown
<Delegation Routing>
When delegating research tasks, you MUST always specify the target agent.
Available sub-agents: "Searcher" (for web research), "Analyzer" (for document reading).

Example:
delegate_tasks(tasks=[
  {{"task_name": "Research topic X", "instructions": "Search for ...", "agent_id": "Searcher"}},
  {{"task_name": "Research topic Y", "instructions": "Search for ...", "agent_id": "Searcher"}}
])
</Delegation Routing>
```

> [!CAUTION]
> **Double-Brace Trap:** The examples above use double-braces `{{` and `}}` because they will be embedded inside Python prompt strings processed by `.format()`. Single braces `{` are reserved for engine variables like `{date}` and `{task_name}`. If you use single braces for JSON, Python throws `ValueError: Invalid format specifier`. See §6 for details.

> [!WARNING]
> **Common Mistake:** The coding agent writes prose like "dispatch Search Sub-Agents" in the prompt but never tells the LLM the exact `agent_id` string. The LLM has no way to know the name is `"Searcher"` unless you spell it out. Always include a concrete JSON example showing the exact `agent_id` value.

## 9. Data-Flow Integrity in Nested Pipelines
When Agent A produces output that Agent B depends on (e.g., a filename), Agent A's prompt **MUST** instruct it to capture that output and embed it into the delegation `instructions` for Agent B. Without this, Agent B is dispatched without knowing what to operate on.

**The Critical Pattern: Fetch → Capture Filename → Delegate with Filename**

In a Searcher→Analyzer pipeline:
1. The Searcher calls `fetch_url_to_workspace(url, filename)` which returns a confirmation like `"Fetched URL successfully to 'microsoft_ai_research_143022.md'"`.
2. The Searcher's prompt **MUST** instruct it to capture the filename from this response.
3. The Searcher **MUST** pass the exact filename in the delegation instructions to the Analyzer.

**Prompt pattern to include in the Searcher's instructions:**

```markdown
<Data Flow Rule>
After fetching a URL, the tool returns a message containing the saved filename.
You MUST capture this filename and pass it to the Analyzer in your delegation instructions.

Example:
1. You call: fetch_url_to_workspace(url="https://example.com/article", filename="example_article_143022")
2. Tool returns: "Fetched URL successfully to 'example_article_143022.md'"
3. You delegate: delegate_tasks(tasks=[
     {{"task_name": "Analyze example_article_143022.md",
      "instructions": "Read the file 'example_article_143022.md' and extract key findings about ...",
      "agent_id": "Analyzer"}}
   ])
</Data Flow Rule>
```

> [!CAUTION]
> **Double-Brace Trap:** All JSON curly braces in the above example use `{{` and `}}` because they are embedded in Python prompt strings processed by `.format()`. Using single braces `{` causes `ValueError: Invalid format specifier` at runtime. See §6.

> [!CAUTION]
> **Anti-Pattern: Tool Leaking.** If a parent agent (e.g., Searcher) is given the tools that its child agent (e.g., Analyzer) is supposed to use (like `read_workspace_file`), the LLM will skip delegation entirely and read files itself. This defeats the architecture by bloating the parent's context window. **Always withhold child-specific tools from the parent** to force proper delegation.

