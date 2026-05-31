# Architecture Rules for Local Agents

When designing a new local agent, you must evaluate the best architecture for the user based on the complexity of their task.

> [!CAUTION]
> **ANTI-PATTERNS (WHAT NOT TO DO):**
> 1. **Do NOT ask the user what model they are using.** The scaffold is pre-optimized for small local LLMs (e.g., via config quotas, context isolation, and prompt engineering). Assume the user is using a small local LLM.
> 2. **Do NOT design unbounded parallel execution pipelines.** When writing tools that spawn multiple sub-agents (e.g. `delegate_tasks`), you MUST use an `asyncio.Semaphore` tied to the user's configured `max_concurrency`. This ensures that even if an agent delegates 50 tasks at once, they queue gracefully and never exceed the configured maximum concurrency limits. Furthermore, to prevent recursive deadlocks, a parent agent waiting on gathering its children MUST yield its semaphore token back to the pool via `contextvars` (see `src/engine/orchestrator.py` for implementation).
> 3. **Concurrent vs Sequential Confusion:** Do NOT instruct the Orchestrator to batched-delegate dependent tasks (e.g., `Task B requires Task A`). Prompts must strictly guide the agent to perform sequential logic for dependent chains, reserving `asyncio.gather` strictly for independent prongs of execution.

> [!IMPORTANT]
> Once an architecture is carefully chosen based on the paradigms below, you **MUST** read [`PROMPTING.md`](./PROMPTING.md) for strict guidelines on crafting system instructions and formatting prompt engineering patterns for local models.

## 1. The Flat Agent (Simple Tasks)
**Guidance: Propose this for straightforward tasks that require minimal context.**

```text
+-----------------------+
|         Agent         |
|-----------------------|
| - Tool 1              |
| - Tool 2              |
+-----------------------+
```

A single "flat" agent loop is fast and viable when dealing with known boundaries—like calculating math formulas, formatting structured text, or basic conversational retrieval.

```python
from agent_framework.openai import OpenAIChatClient

def run_flat_agent():
    client = OpenAIChatClient(
        base_url="http://localhost:8080/v1",
        api_key="dummy",
        model_id="local-model"
    )
    
    agent = client.as_agent(
        name="math_expert",
        instructions="You are a strict data-formatter. You never browse the internet.",
        tools=[format_date_tool, convert_currency_tool],
        default_options={"temperature": 0.0}
    )
    
    response = agent.run("Please convert 600 USD to GBP.")
    return response.text
```

## 2. Tool-Delegation Sub-Agents (Complex Extraction)
**Guidance: Propose this when a task involves consuming large context, reading heavy files, or performing highly specialized workflows.**

```text
+-----------------------------------+
|         Orchestrator Agent        |
|-----------------------------------|
| - Tool 1 (e.g., general tool)     |
| - Tool 2 (delegate_to_subagent)   |
+-----------------+-----------------+
                  | calls
                  v
       +--------------------+
       |    Sub-Agent 1     |
       |--------------------|
       | - Specific Tool A  |
       | - Specific Tool B  |
       | - call_subagent_2  |
       +--------+-----------+
                | calls
                v
       +--------------------+
       |    Sub-Agent 2     |
       |--------------------|
       | - Specialized Tool |
       +--------------------+
```

Typically, sub-agents are scoped to a specific task and only contain tools for that task. However, designing a general-purpose sub-agent with many tools is also possible if the orchestrator strictly prompts it for the task. The choice depends on the use-case:

- **Scoped Sub-Agents:**
  - **Pros:** Low token usage, high reliability on small local LLMs, avoids tool confusion.
  - **Cons:** Rigid; requires declaring many distinct agents.
- **General-Purpose Sub-Agents:**
  - **Pros:** Highly flexible and reusable across different dynamic tasks.
  - **Cons:** Bloats context window, high risk of tool hallucination on smaller/local hardware models.

**Paradigm: Context Weight Management**
Managing context windows is critical for local LLMs. You must actively prevent "context rot" by employing the following techniques:

1.  **Sub-Agent Offloading:** Pass data-intensive operations (massive web searches, grepping full files) to a Sub-Agent. The child agent absorbs the massive context payload and simply returns a compressed semantic summary to the Orchestrator.
2.  **Strict Chunking (Read Limits):** Enforce rigid read limits in your extraction tools. Never dump raw web pages or massive files into the agent; always restrict readings to a maximum number of lines (e.g., 500-line chunks) or strict token limits.
3.  **Tool Quotas (Max Calls):** Strictly cap the number of times an agent can invoke specific tools using `@with_quota` (e.g., max 3 scraper retries). This prevents models from entering infinite extraction loops that exponentially bloat context history.

**Reference Implementation:** Do not write delegation loop handlers from scratch. Simply define your sub-agents in `src/app.py` via `SubAgentConfig` and the Engine handles the concurrency logic explicitly documented in the framework at `examples/basic-tui-agent/src/engine/orchestrator.py`.

### Nested Sub-Agent Delegation (Multi-Tier)
The orchestration engine natively supports multi-level nested delegation (e.g. Orchestrator -> Search Sub-Agent -> Page Analyzer Sub-Agent) out-of-the-box.
To configure nested sub-agents:
1. **Define leaf agents first:** Define each sub-agent as a `SubAgentConfig` in `src/app.py`, starting from the deepest (leaf) agents and working up. Leaf agents have no `sub_agents` field.
2. **Declare each agent's children:** Set `sub_agents=[...]` on each `SubAgentConfig` to specify which children that agent can delegate to (e.g. `searcher = SubAgentConfig(..., sub_agents=[analyzer])`).
3. **Register top-level children with the builder:** Pass only the Orchestrator's direct children in the `AgentBuilder` constructor (e.g. `sub_agents=[searcher]`). Do NOT put all agents in a flat list.
4. **No Orchestrator Edits:** The engine automatically injects `delegate_tasks` only into agents that have children. Leaf agents (empty `sub_agents`) do NOT get `delegate_tasks`. You **MUST NOT** modify `src/engine/orchestrator.py`.
5. **Invoke via `delegate_tasks`:** The parent sub-agent (e.g., Searcher) can call `delegate_tasks` specifying the child sub-agent's name as the `agent_id` parameter (e.g. `agent_id="Analyzer"`). It can only see its own declared children.

#### app.py Pattern for Multi-Tier Sub-Agents

**CRITICAL: Each sub-agent gets its own unique prompt constant, its own selective tool list, AND declares its own children via `sub_agents`.**

- Each `SubAgentConfig` MUST reference a **separate, dedicated prompt constant** from `prompts.py` (e.g., `SEARCH_SUBAGENT_INSTRUCTIONS`, `ANALYZER_SUBAGENT_INSTRUCTIONS`). Do NOT reuse the same prompt for different sub-agent types.
- Each `SubAgentConfig` MUST have a **selective tool list** — import individual tools and pass only the ones that sub-agent needs. Do NOT use `WORKSPACE_TOOLS` (which includes everything) for specialized sub-agents.
- Each `SubAgentConfig` declares its own children via `sub_agents=[...]`. The engine only injects `delegate_tasks` into agents that have children. Leaf agents (empty `sub_agents`) cannot delegate — this is enforced structurally, not by prompts.
- **Tool separation enforces the delegation hierarchy.** If a parent agent has the tools its child is supposed to use, it will never delegate. Withhold tools to force delegation.

```python
# src/app.py — CORRECT multi-tier pattern
from prompts import (
    ORCHESTRATOR_INSTRUCTIONS,
    SEARCH_SUBAGENT_INSTRUCTIONS,      # Dedicated prompt for Searcher
    ANALYZER_SUBAGENT_INSTRUCTIONS,    # Dedicated prompt for Analyzer
    SUBAGENT_DELEGATION_INSTRUCTIONS,
)

# 1. Leaf agent (Analyzer) — file reading only, NO web, NO delegation
#    No sub_agents = no delegate_tasks tool injected (leaf node)
analyzer = SubAgentConfig(
    name="Analyzer",
    instructions=ANALYZER_SUBAGENT_INSTRUCTIONS,
    tools=[read_workspace_file, grep_workspace_file, think_tool]
)

# 2. Middle agent (Searcher) — web only, NO file reading (forces delegation to Analyzer)
#    sub_agents=[analyzer] = can ONLY delegate to Analyzer, nothing else
searcher = SubAgentConfig(
    name="Searcher",
    instructions=SEARCH_SUBAGENT_INSTRUCTIONS,
    tools=[web_search, fetch_url_to_workspace, think_tool],
    sub_agents=[analyzer]
)

# 3. Orchestrator — task management only, NO web, NO file reading
#    sub_agents=[searcher] = can ONLY delegate to Searcher, cannot bypass to Analyzer
app = AgentBuilder(
    name=config.APP_TITLE,
    instructions=ORCHESTRATOR_INSTRUCTIONS,
    tools=[write_workspace_file, list_workspace_files, write_todos, read_todos, think_tool],
    sub_agents=[searcher]
)
```

> [!CAUTION]
> **ANTI-PATTERNS:**
> - Do NOT give `WORKSPACE_TOOLS` to every sub-agent. That defeats the entire delegation architecture.
> - Do NOT reuse the same prompt constant (e.g., `SUBAGENT_INSTRUCTIONS`) for both Searcher and Analyzer. Each agent type needs its own dedicated instructions explaining its specific role, tools, and delegation targets.
> - Do NOT try to be clever by combining or conditionally formatting a single shared prompt for multiple agent roles. Each sub-agent type gets its own `NAME_INSTRUCTIONS` constant in `prompts.py`.
> - Do NOT put all sub-agents in the top-level `sub_agents=[searcher, analyzer]` on `AgentBuilder`. The `sub_agents` field on each `SubAgentConfig` defines which children THAT agent can see. The Orchestrator should only see `[searcher]`, and the Searcher should only see `[analyzer]`.

#### prompts.py Pattern for Multi-Tier Sub-Agents

Each sub-agent type MUST have its own dedicated prompt constant. Name them clearly: `SEARCH_SUBAGENT_INSTRUCTIONS`, `ANALYZER_SUBAGENT_INSTRUCTIONS`, etc.

Keep backward compatibility aliases at the bottom of `prompts.py` to prevent `ImportError` crashes in the engine:

```python
# src/prompts.py — at the bottom, after all prompt constants
# Backward compatibility aliases (engine may import these names)
SUBAGENT_INSTRUCTIONS = SEARCH_SUBAGENT_INSTRUCTIONS
```


## 3. Strict Workflow DAGs (Deterministic Pipelines)

Sometimes conversational orchestration introduces too much unpredictability. If an operation has strong, sequential sub-steps (e.g., "Process Step A, then pass to Step B"), use Agent Framework's `.add_edge()` pipeline. 

**Reference Implementation:** View `https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows/control-flow/` for complete internal DAG execution paradigms.

*(Note: Sub-agents do **not** have to match their parent's pattern. An orchestrator can call a tool that triggers an entire deterministic DAG Workflow behind the scenes!)*

## 4. Handling Context Dynamically
- **Static Reading (Forbidden):** Returning 60,000 tokens of raw text to the agent.
- **Dynamic Reading (Mandatory):** Use targeted extraction tools (`grep_page`, `read_line_chunk`) if the sub-agent needs to search large files.
- **Markdown Conversion (Mandatory):** Whenever processing raw files (webpages, PDFs, raw HTML), use `markitdown` or `liteparse` to convert them to markdown before returning them to the LLM.

## 5. Reasoning Control
1. **Native Thinking (`<think>`)**: Expose `/toggle_thinking` to flip `chat_template_kwargs={"enable_thinking": True}` on the fly. Extract via `delta.model_extra["reasoning_content"]`. (See `examples/basic-tui-agent/src/engine/tui.py`).
2. **`think_tool` Strategy**: Include a dummy `@tool(approval_mode="never_require") def think_tool(reflection: str): return "Recorded"` to force the model to plan before executing.

## 6. Conversational Memory
Multi-turn memory is handled by `AgentSession`.

```python
# Stateless (no memory):
agent.run(query, stream=True)

# Stateful (with memory):
session = agent.create_session()
agent.run(query, session=session, stream=True)  # history auto-managed
```

Toggle via `config.yaml` `settings.enable_conversational_memory`. Reset via `/new` command (clears session + UI). When disabled, `session=None` is passed and each turn is independent.

**Reference implementation:** `examples/basic-tui-agent/src/engine/orchestrator.py` — module-level `_session`, `create_local_agent()` returns `(agent, session)`, `reset_session()` clears it.

## 7. Workspace and File Isolation
- **In-Memory (`mem://`)**: Use dictionaries or ephemeral stores for parsing and data-formatting. 
- **Confined Folder (`osfs://`)**: Sandbox file write/read logic tightly inside `./runs/latest/` to protect the host machine.

## 8. Tool Quota Enforcement
**Rule: You MUST use the @with_quota decorator on every tool to stop infinite local extraction loops.**
Small models often enter infinite loops if a scraper fails. Applying `@with_quota` natively tracks invocation limits (see `examples/basic-tui-agent/src/tools.py`).

