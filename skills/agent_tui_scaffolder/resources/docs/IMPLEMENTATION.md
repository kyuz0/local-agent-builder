# Implementation Recipes

When building agents with Microsoft's `agent-framework` locally, strict boilerplate structure allows developers to easily transition across local untrusted endpoints, enforce runtime limits, and extract rich document sources without cloud API dependencies.

## 1. Project Initialization & Structure

You will find scaffold projects and documentation for how to create agents in the `scaffolds` and `docs` subfolders. **DO NOT edit or touch the files inside these folders.** These are strictly read-only references.

**Rule: NEVER construct an agent from scratch. You MUST copy the contents of the `examples/basic-tui-agent/` directory to your main project folder for editing to create the agent the user wants.**

**Rule: PRUNE UNUSED TOOLS. The scaffold contains common reference implementations (like `web_search` and `fetch_url_to_workspace`). If the agent you are building does not need these tools, you MUST explicitly delete them from the workspace to save tokens and prevent hallucinated tool calls.**

The scaffold provides this exact structure out-of-the-box:

### Recommended Filesystem
```plaintext
your-main-project/  <-- (This is the copied examples/basic-tui-agent/ folder)
├── .env                  # Untracked API bases & dummy keys
├── .env.example          # Template for .env (checked into source control)
├── requirements.txt      # Python dependencies
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
pip install agent-framework python-dotenv httpx textual beautifulsoup4
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

### Session Logging Recipe

For debugging and traceability, implement a session-level JSON logger that captures prompts, reasoning traces, text outputs, and function calls.

Toggle logging via `config.yaml`:
```yaml
settings:
  enable_session_logging: false
```

> [!IMPORTANT]
> When using the `basic-tui-agent` scaffold to create new applications, you **MUST** update the `AGENT_NAME` and `AGENT_DESCRIPTION` variables at the top of `src/main.py`. These variables dynamically build the application UI components, dictate the auto-generated ASCII-art banner on the welcome screen, and shape the hidden folder where session logs are saved (e.g. `~/.<sanitized-agent-name>-logs/session_<uuid>.json`).

### Conversational Memory Recipe

When `enable_conversational_memory: true`, hold a module-level `AgentSession` and pass it to each `agent.run()`:

```python
from agent_framework import AgentSession

_session = None

def create_agent():
    agent = client.as_agent(name="my_agent", instructions=prompt, tools=tools)
    session = None
    if config.cfg["settings"].get("enable_conversational_memory", False):
        global _session
        if _session is None:
            _session = agent.create_session()
        session = _session
    return agent, session

def reset_session():
    global _session
    _session = None
```

The framework's built-in `InMemoryHistoryProvider` auto-injects when a session is provided. No manual history management needed. See `examples/basic-tui-agent/src/chat.py`.

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
1. Configure limits centrally in `config.yaml` (or the scaffold template). The schema should support both invocation counts (`limit`) and custom constraints (`rules`).
```yaml
settings:
  quotas:
    fetch_url_to_workspace: 
      limit: 5
    read_workspace_file:
      limit: 100
      rules:
        max_lines: 300
    grep_workspace_file:
      limit: 100
      rules:
        max_matches: 10
```
2. Wrap your tools natively using the `@with_quota` decorator found in `examples/basic-tui-agent/src/tools.py`.
3. Inside your tool, use `_get_tool_rule(tool_name, rule_key, default)` to extract specific constraints and reject LLM calls that exceed the bounds.

## 5. Universal Document Processing Without Cloud APIs
**Rule: Always use `markitdown` or `liteparse` to convert downloaded webpages, raw HTML, PDFs, and rich documents into markdown formats before parsing.**

A local agent must process files locally to maintain security perimeters. 

### Microsoft MarkItDown 
Universal parser for native Python integration (HTML, Excels, Word, simple PDFs).
*[Requires: `pip install markitdown`]*
```python
from bs4 import BeautifulSoup
from markitdown import MarkItDown

# Instantiate cleanly. Do NOT hold context inside this unless caching deliberately.
_markitdown = MarkItDown()

def convert_document_to_md(filepath: str) -> str:
    md = MarkItDown()
    result = md.convert(filepath)
    if not result.text_content:
       return "Document could not be parsed."
    return result.text_content
```

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
If advanced PDF layout interpretation is demanded, use `liteparse` via local subprocess execution. Because it utilizes Node.js, wrap the execution cleanly:

```bash
# Required global installation
npm install -g @llamaindex/liteparse
```

```python
import subprocess
import shutil

def extract_advanced_pdf(filepath: str) -> str:
    """Utilizes Liteparse for layout comprehension of complex PDFs"""
    if not shutil.which("liteparse"):
        raise EnvironmentError("liteparse is missing. Run: npm i -g @llamaindex/liteparse")

    result = subprocess.run(
        ["liteparse", filepath], 
        capture_output=True, 
        text=True,
        check=True
    )
    return result.stdout
```

## 6. Sub-Agent Delegation with TUI Streaming
**Rule: To enable deeply nested sub-agents with live UI token streams, DO NOT use `.as_tool()`.**
Instead, build a manual wrapper that propagates async streams up to the chat UI. 
You **MUST** strictly clone the pattern implemented in `examples/basic-tui-agent/src/chat.py` (`delegate_analysis`) and the `handle_agent_update` intercept block. Those scaffold files serve as the blueprint for complex TUI handling.

## 7. Headless Execution (Cron/Batch processing)
Agents built using this scaffold natively support headless CLI operations for server-side or batch processing scripts.

By skipping the TUI and directly invoking local streams to `sys.stdout`, you can trigger one-shot tasks:
```bash
python src/main.py --prompt "Analyze the provided log files and output a markdown summary."
```
This is fully baked into the `argparse` configuration block found in `src/main.py` when following the `basic-tui-agent` scaffold.

## 8. Todo Checklist Tracking Strategy
**Rule: Always use Markdown Checkbox Lists for agent tasks tracking.**
Instead of creating isolated, stateful backend functions that append strings one-by-one to a hidden list, you should force the agent to update and rewrite a universal Markdown file. The `write_todos` and `read_todos` provided in the scaffold utilize this pattern natively.

When building workflows, explicitly include prompts defining the exact markdown standard so orchestrators can track completion states visibly:
```markdown
1. Create a TODO list via `write_todos()` using `- [ ]` checkboxes.
2. Read uncompleted tasks from `read_todos()`.
3. Immediately rewrite the ENTIRE list using `write_todos()` marking the completed task as `- [x]` when finished.
```
