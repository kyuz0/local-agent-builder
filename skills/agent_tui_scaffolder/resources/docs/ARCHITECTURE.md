# Architecture Rules for Local Agents

When designing a new local agent, you must actively collaborate with the user to determine the best architecture. **Do not assume an architecture.** Instead, ask the user questions and offer the following options to align on the right approach based on their task's complexity, context needs, and required tools:

> [!IMPORTANT]
> Once an architecture is carefully chosen, you **MUST** read [`PROMPTING.md`](./PROMPTING.md) for strict guidelines on crafting system instructions and formatting prompt engineering patterns for local models.

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

**Reference Implementation:** Do not write delegation loop handlers from scratch. Simply clone and adapt the `delegate_analysis` function explicitly documented in the scaffold at `examples/basic-tui-agent/src/chat.py`.

## 3. Strict Workflow DAGs (Deterministic Pipelines)

Sometimes conversational orchestration introduces too much unpredictability. If an operation has strong, sequential sub-steps (e.g., "Process Step A, then pass to Step B"), use Agent Framework's `.add_edge()` pipeline. 

**Reference Implementation:** View `https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows/control-flow/` for complete internal DAG execution paradigms.

*(Note: Sub-agents do **not** have to match their parent's pattern. An orchestrator can call a tool that triggers an entire deterministic DAG Workflow behind the scenes!)*

## 4. Handling Context Dynamically
- **Static Reading (Forbidden):** Returning 60,000 tokens of raw text to the agent.
- **Dynamic Reading (Mandatory):** Use targeted extraction tools (`grep_page`, `read_line_chunk`) if the sub-agent needs to search large files.
- **Markdown Conversion (Mandatory):** Whenever processing raw files (webpages, PDFs, raw HTML), use `markitdown` or `liteparse` to convert them to markdown before returning them to the LLM.

## 5. Reasoning Control
1. **Native Thinking (`<think>`)**: Expose `/toggle_thinking` to flip `chat_template_kwargs={"enable_thinking": True}` on the fly. Extract via `delta.model_extra["reasoning_content"]`. (See `examples/basic-tui-agent/src/main.py`).
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

**Reference implementation:** `examples/basic-tui-agent/src/chat.py` — module-level `_session`, `create_local_agent()` returns `(agent, session)`, `reset_session()` clears it.

## 7. Workspace and File Isolation
- **In-Memory (`mem://`)**: Use dictionaries or ephemeral stores for parsing and data-formatting. 
- **Confined Folder (`osfs://`)**: Sandbox file write/read logic tightly inside `./runs/latest/` to protect the host machine.

## 8. Tool Quota Enforcement
**Rule: You MUST use the @with_quota decorator on every tool to stop infinite local extraction loops.**
Small models often enter infinite loops if a scraper fails. Applying `@with_quota` natively tracks invocation limits (see `examples/basic-tui-agent/src/tools.py`).

