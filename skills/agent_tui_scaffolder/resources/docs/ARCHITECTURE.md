# Architecture Rules for Local Agents

When designing a new local agent, you must actively collaborate with the user to determine the best architecture. **Do not assume an architecture.** Instead, ask the user questions and offer the following options to align on the right approach based on their task's complexity, context needs, and required tools:

## 1. The Flat Agent (Simple Tasks)
**Guidance: Propose this for straightforward tasks that require minimal context.**
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

**Paradigm: Context Weight Management**
While your Orchestrator can absolutely retain a comprehensive set of baseline tools (like native file reading or baseline web searching), passing heavily data-intensive operations to a Sub-Agent is the best way to prevent the Orchestrator from suffering "context rot."

For example, performing a massive, multi-page deep web search or grepping thousands of log lines will dump tens of thousands of tokens into the active generation block. By offloading this explicit task into a `delegate_file_analysis` or `delegate_web_research` proxy tool, the Sub-Agent absorbs the massive context payload and simply returns a compressed semantic summary to the Orchestrator. This "divide and conquer" technique is critical for keeping local LLMs responsive.

```python
from agent_framework import tool

# 1. Define the child agent that will do heavy lifting
analyzer_agent = client.as_agent(
    name="url_analyzer",
    instructions="Fetch the URL, find the answer, and summarize it briefly. Do NOT return raw text.",
    tools=[fetch_webpage_content]
)

# 2. Expose the child to the main orchestrator as a Tool
@tool(name="delegate_research")
async def delegate_research(query: str, url: str) -> str:
    """Delegate a heavy reading task to a sub-agent."""
    # The sub-agent has a separate AgentSession automatically!
    response = await analyzer_agent.run(f"Look for {query} in {url}")
    return response.text

# 3. Main orchestrator remains fast and uncluttered
orchestrator = client.as_agent(
    name="orchestrator",
    instructions="You are a planner. Use `delegate_research` to find facts safely.",
    tools=[delegate_research]
)
```

## 3. Strict Workflow DAGs (Deterministic Pipelines)

Sometimes conversational orchestration introduces too much unpredictability. If an operation has strong, sequential sub-steps (e.g., "Process Step A, then pass to Step B"), use Agent Framework's `WorkflowBuilder`. 

You can review `https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows/control-flow/` for internal paradigms.

```python
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler

class StepNode(Executor):
    def __init__(self, step_name: str):
        super().__init__(id=step_name)
        self.step_name = step_name

    @handler
    async def process_node(self, state: str, ctx: WorkflowContext[str, str]) -> None:
        # Perform rigid python logic here (DB writing, API uploads)
        result = f"Finished {self.step_name}"
        await ctx.yield_output(result)

workflow = (
    WorkflowBuilder(start_executor=StepNode("Ingestion"))
    .add_edge(StepNode("Ingestion"), StepNode("Processing"))
    .build()
)

await workflow.run("start")
```
*(Note: Sub-agents do **not** have to match their parent's pattern. An orchestrator can call a tool that triggers an entire DAG Workflow behind the scenes!)*

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

## 9. Session State & Memory Continuity
- **Single-Turn**: Default `agent.run()`. No memory. Fastest execution.
- **Multi-Turn**: Use `AgentSession`. See `examples/basic-tui-agent/src/chat.py` for persistent memory implementation.

