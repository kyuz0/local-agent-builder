# Implementation Recipes

When building agents with Microsoft's `agent-framework` locally, strict boilerplate structure allows developers to easily transition across local untrusted endpoints, enforce runtime limits, and extract rich document sources without cloud API dependencies.

## 1. Project Initialization & Structure

You will find scaffold projects and documentation for how to create agents in the `scaffolds` and `docs` subfolders. **DO NOT edit or touch the files inside these folders.** These are strictly read-only references.

> [!NOTE]
> While this file explains structural implementation and python boilerplate, you **MUST** reference [`PROMPTING.md`](./PROMPTING.md) to understand how to write instructions that guide agent behavior reliably on local hardware.

**Rule: NEVER construct an agent from scratch. You MUST copy the contents of the `examples/basic-tui-agent/` directory to your main project folder for editing to create the agent the user wants.**

**Rule: PRUNE UNUSED TOOLS. The scaffold contains common reference implementations (like `web_search` and `fetch_url_to_workspace`). If the agent you are building does not need these tools, you MUST explicitly delete them from the workspace to save tokens and prevent hallucinated tool calls.**

The scaffold provides this exact structure out-of-the-box:

### Recommended Filesystem
```plaintext
your-main-project/  <-- (This is the copied examples/basic-tui-agent/ folder)
├── .env                  # Untracked API bases & dummy keys
├── .env.example          # Template for .env (checked into source control)
├── pyproject.toml        # Application configuration and dependencies
├── src/
│   ├── main.py           # TUI and entrypoint
│   ├── config.py         # Config loader (YAML + ENV fallback)
│   ├── config_template.yaml # Scaffold configuration dictionary template
│   ├── chat.py           # Core agent instantiation and streaming logic
│   ├── prompts.py        # Long multi-line instruction strings
│   ├── utils/            # Optional helpers to prune if unneeded
│   │   └── parsers.py    # `markitdown` and `liteparse` conversion scripts
│   └── tools/            # Agent tools grouped by logical domain
│       ├── __init__.py     # Aggregates and exports WORKSPACE_TOOLS
│       ├── core.py         # Core quota logic
│       ├── fs.py           # File system tools
│       ├── web.py          # Web fetch tools (uses `utils/parsers.py`)
│       ├── todos.py        # Workflow tools
│       └── meta.py         # Cognitive constraints
└── docs/                 # Included local data
```

### Virtual Environment Handling
Provide initial scripting configurations to the user:
```bash
python -m venv venv
source venv/bin/activate
pip install -e .
```

For system-wide command installation (creating isolated binary wrapper):
```bash
pipx install .
```

### Workspace File System Handling
Agents need scratchpads and memory. The scaffold provides an abstract file system togglable between Sandboxed Memory and actual Disk directories.
1. `type: "memory"` (Default): Writes and reads are stored purely in the python memory dict. Wiped on exit.
2. `type: "disk"`: Reads and writes are executed on the host's actual OS directory. Path traversal is stripped automatically.

Set this explicitly in `config.yaml`:
```yaml
settings:
  workspace:
    type: memory # or "disk"
    dir: .       # Only applies if type is disk
```
Note: Tools like `/files` TUI picker and agent `write_workspace_file` natively support this toggle out-of-the-box.

### Local Configuration and Secrets Isolation
Secrets belong inside `.env` via `python-dotenv`, while runtime states (`enable_thinking`, workspace config) belong in `config.yaml`. 

**Global Agent Configuration Rules:**
- The configuration loader inherently targets a system-wide directory: `~/.{AGENT_NAME}/config.yaml` (e.g., `~/.basic-tui-agent/config.yaml`).
- On first startup, if that file is missing, the scaffold automatically creates the directory and copies its bundled `src/config_template.yaml` template directly into the user's home partition.
- Developers can overwrite this path at runtime utilizing the `--config` or `-c` CLI flag (e.g., `python src/main.py --config ./local_config.yaml`).

Reference `examples/basic-tui-agent/src/config.py` for exact merging implementation and early-stage parameter extraction.

### Session Persistence Recovery Recipe

The scaffold implements a simple mechanism to manage session history. Both the agent's conversational memory and the visual TUI state are saved together into the local filesystem so they can be reloaded later.

Toggle persistence via `config.yaml`:
```yaml
settings:
  enable_session_persistence: true
```

When enabled, interactions are natively aggregated into payloads saved in `~/.{AGENT_NAME}/sessions/session_{uuid}.json`.

**TUI Recovery Commands:**
The scaffold natively implements conversational recovery without missing a beat visually. Instruct users they can type:
- `/sessions` to list recent persistent histories.
- `/restore [id]` to wipe the current canvas and seamlessly recreate the interface exactly as it was.
- `/resume` to automatically load the most recent session file.

> [!IMPORTANT]
> When using the `basic-tui-agent` scaffold to create new applications, you **MUST** update the `AGENT_NAME` and `AGENT_DESCRIPTION` variables at the top of `src/main.py`. These variables dynamically build the application UI components, dictate the auto-generated ASCII-art banner on the welcome screen, and shape the hidden folder where sessions are saved (e.g. `~/.<sanitized-agent-name>/sessions/session_<uuid>.json`).

### Conversational Memory Recipe

When `enable_conversational_memory: true`, the framework's built-in `InMemoryHistoryProvider` can automatically inject and manage histories seamlessly. You do not need to manage history lists manually.
**Reference Implementation:** Clone the module-level `_session` state passing logic found explicitly in `examples/basic-tui-agent/src/chat.py`.

## 2. Managing the <think> Token Artifacts
Small LLMs can hallucinate unbalanced tags. You must strip them natively using regex before final user display:
```python
import re
def clean_reasoning_tags(s: str) -> str:
    s = re.sub(r"<(think|thought)>.*?</\1>", "", s, flags=re.DOTALL | re.IGNORECASE)
    return re.sub(r"<(think|thought)>.*", "", s, flags=re.DOTALL | re.IGNORECASE).strip()
```

**Streaming reasoning display:** When `enable_thinking` is on, local LLMs emit reasoning via `delta.model_extra["reasoning_content"]` (not surfaced by agent-framework's `ChatCompletionClient`). Extract from raw chunk: `update.raw_representation.raw_representation.choices[0].delta.model_extra["reasoning_content"]`. See `examples/basic-tui-agent/src/main.py` `ThinkingWidget` for a collapsible streaming implementation with `/toggle_thinking`.

## 3. The `think_tool` Reflection Pattern

For non-reasoning models (or when the native `<think>` system is disabled via config to boost speed), you should force the model to simulate a structured pause by exposing a dummy tool.

This arrests "infinite loop confusion". Provide specific instructions within the tool documentation.

```python
from agent_framework import tool

@tool(approval_mode="never_require")
def think_tool(reflection: str) -> str:
    """Use this to record deliberate thinking / reasoning about the current situation and potentially next steps in a concise way.
    
    [AGENT INSTRUCTION: Always tailor this tool's docstring to the specific domain you are coding for to ensure the LLM knows what to "think" about.]
    """
    return f"Reflection recorded successfully: {reflection}"
```

## 4. Tool Quota Management Recipe
**Rule: Always implement Tool invocation quotas to stop infinite tool-calling loops!**
1. Configure limits centrally in `config.yaml` (or the scaffold template). The schema dynamically supports BOTH flat integers (for simple limits) and dictionaries (for limits + rules).
```yaml
settings:
  quotas:
    fetch_url_to_workspace: 5    # Flat integer limit
    read_workspace_file:         # Dictionary configuration
      limit: 100
      rules:
        max_lines: 300
    grep_workspace_file:
      limit: 100
      rules:
        max_matches: 10
```

> [!WARNING]
> Because quotas can be EITHER integers or dictionaries, **DO NOT** use chained deep `.get()` calls like `quotas.get("tool", {}).get("limit", 10)`. You will trigger an `AttributeError: 'int' object has no attribute 'get'` when the value is a flat integer. If you must read limits manually, check `isinstance(val, int)`.

2. Wrap your tools natively using the `@with_quota` decorator found in `examples/basic-tui-agent/src/tools.py`.
3. Inside your tool, use `_get_tool_rule(tool_name, rule_key, default)` to extract specific constraints without needing to parse the config dictionary manually.

## 5. Universal Document Processing Without Cloud APIs
**Rule: Always use `markitdown` or `liteparse` to convert downloaded webpages, raw HTML, PDFs, and rich documents into markdown formats before parsing.**

A local agent must process files locally to maintain security perimeters. 

### Microsoft MarkItDown 
Microsoft's `markitdown` provides universal parsing for text-native files (HTML, Office, basic PDF).
**Reference Implementation:** Import and utilize the safe, size-capped `convert_document_to_md` function located entirely within `examples/basic-tui-agent/src/utils/parsers.py`.

## Tool Authorization (Human-In-The-Loop)

You must protect the host computer from dangerous tool execution (like executing raw bash commands or deleting systemic files). You can enforce an explicit human authorization check by flipping the tool approval string:

```python
from agent_framework import tool

@tool(approval_mode="always_require")  # Standard tools use "never_require"
def auth_test_delete(target: str) -> str:
    """A destructive action that mandates human oversight."""
    return f"Simulated deletion of {target}"
```

When an agent attempts to call an `always_require` tool, the raw response payload will stall and yield a `user_input_requests` object back to the orchestrator. You MUST surface this to the user, grab a Boolean confirmation (`True/False`), and re-inject it back into the stream alongside the original context. *(Review `UI_GUIDELINES.md` for the exact Streaming Interception loop).*

### Liteparse (LlamaIndex)
For advanced PDF layout interpretation or heavy OCR via local subprocess execution, utilize Node.js-based `@llamaindex/liteparse`.
**Reference Implementation:** Use the `extract_advanced_pdf` (or `robust_ocr_parse`) function natively baked into `examples/basic-tui-agent/src/utils/parsers.py` to seamlessly execute CLI extraction.

## 6. Sub-Agent Delegation with TUI Streaming
**Rule: To enable deeply nested sub-agents with live UI token streams, DO NOT use `.as_tool()`.**
Instead, build a manual wrapper that propagates async streams up to the chat UI. 
You **MUST** strictly clone the pattern implemented in `examples/basic-tui-agent/src/chat.py` (`delegate_tasks`) and the `handle_agent_update` intercept block. Those scaffold files serve as the blueprint for complex TUI handling.

> [!WARNING]
> **CRITICAL SUB-AGENT CODING RULES:**
> 1. **Location:** You **MUST** define delegation tools *inside* `create_local_agent()` in `chat.py`. Do NOT abstract sub-agent creation into `tools/` files. Defining them inside `chat.py` is required to capture `subagent_callback` and stream child agent reasoning/text back to the UI. If you put them in `tools/`, the UI will freeze and show nothing!
> 2. **Decorator:** When defining a delegation tool using the `@tool` decorator, ALWAYS provide an explicit `description` argument (e.g., `@tool(name="delegate_task", description="Highly detailed instructions...")`). Relying only on docstrings for complex sub-agent delegation tools often results in `Error: Function Failed` due to the Parent LLM failing to build the correct JSON schema.
> 3. **No Hallucinated State:** Do NOT invent global state variables or undeclared counter functions (like `_get_next_id()`) to dynamically name your sub-agents in a loop. Subagents do not need unique numeric IDs. Hardcode a static name (e.g., `name="SearchAgent"`) when passing it to `client.as_agent()`, or use string sanitization on a passed argument (e.g. `f"SubAgent_{task_name}"`).
> 4. **Dependency Ordering (CRITICAL):** Because delegation tools are local closure functions (`async def ...`) inside `create_local_agent()`, Python evaluates them sequentially. If Sub-Agent A needs to be given a delegation tool to dispatch Sub-Agent B, you **MUST** define Sub-Agent B's delegation tool completely *before* Sub-Agent A's tool in the file. If you define them out of order, passing it into `tools=[...]` will throw a `NameError`, or if you simply omit it to avoid the error, the parent agent will spin infinitely trying to call a tool it lacks the schema for!

### Bounded Concurrency Implementations
When implementing concurrent scatter-gather operations:
1. Ensure you utilize an `asyncio.Semaphore` loaded from the local configurations to throttle the event loop natively, protecting the machine from queue exhaustion.
2. Rely natively on the existing `tool_quotas_ctx` `ContextVar`. Do not clear or reset it inside child coroutines. Because Python's `asyncio` inherits `ContextVars`, all spun-up coroutines will intrinsically mutate the shared quota dictionary pool, preventing the collective suite of agents from bypassing total hardware constraints.

**Customizing UI Output:** When triggering the stream callback across overlapping threads, you MUST explicitly pass `agent_name` to correctly label the nested streams dynamically in the UI console:
```python
await subagent_callback(update, is_subagent=True, agent_name=f"SubAgent_{task_name}")
```

## 7. Headless Execution (Cron/Batch processing)
Agents built using this scaffold natively support headless CLI operations for server-side or batch processing scripts.

By skipping the TUI and directly invoking local streams to `sys.stdout`, you can trigger one-shot tasks:
```bash
python src/main.py --prompt "Analyze the provided log files and output a markdown summary."
```
This is fully baked into the `argparse` configuration block found in `src/main.py` when following the `basic-tui-agent` scaffold.

### 7.1 Background Mailbox Daemon Integration (Stage 2 Add-on)
Agents can optionally be wrapped into a background email-driven workflow where a dedicated process polls an inbox, injects emails into the agent via `--prompt-file`, and replies with the output.
**Rule: This is a Stage 2 workflow. If a user asks you to integrate an agent with email or run it as a background service answering messages, you MUST read and implement the rules specifically found in [`MAILBOX.md`](./MAILBOX.md) and deploy the optional `mailbox-daemon-addon` scaffold.** Do not attempt to embed email IMAP/SMTP protocols into `chat.py` or the agent's tools directly.

## 8. Todo Checklist Tracking Strategy
**Rule: Always use Markdown Checkbox Lists for agent tasks tracking.**
Instead of creating isolated, stateful backend functions that append strings one-by-one to a hidden list, you should force the agent to update and rewrite a universal Markdown file. The `write_todos` and `read_todos` provided in the scaffold utilize this pattern natively.

When building workflows, explicitly include prompts defining the exact markdown standard so orchestrators can track completion states visibly:
```markdown
1. Create a TODO list via `write_todos()` using `- [ ]` checkboxes.
2. Read uncompleted tasks from `read_todos()`.
3. Immediately rewrite the ENTIRE list using `write_todos()` marking the completed task as `- [x]` when finished.
```
