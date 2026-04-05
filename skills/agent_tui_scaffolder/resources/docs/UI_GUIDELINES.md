# UI & TUI Guidelines for Agent Framework

When building terminal interfaces for Local LLMs, transparency is mandatory. Local generation is often slow, and without visible intermediate tool tracking, users will assume the application crashed. The standard interface architecture for `agent-framework` uses the `Textual` Python library.

## 1. Chat Container Architectures and Constraints

To differentiate user queries from raw agent generation text explicitly, utilize nested `VerticalScroll` layouts and strict structural margins.

### CSS Mapping
```css
#chat-container {
    height: 1fr;
    scrollbar-color: $primary;
}

.user-bubble {
    margin: 1 2;
    padding: 1;
    background: $boost;
    color: $text;
    border: round $primary;
    text-align: right;
}

.agent-bubble {
    margin: 1 2;
    padding: 1;
    color: $text;
}
```

## 2. Dynamic Slash Commands (`OptionList`)

Provide conversational intercepts using `/` commands (like `/stop`, `/config`, `/think_toggle`). Map an `OptionList` above the raw `Input` box and tie its visibility state directly to text mutations.

> [!TIP]
> When extending the `basic-tui-agent` scaffold, you can add new commands by appending tuples to the `SLASH_COMMANDS` array inside `src/main.py`. Handle the execution logic inside the `on_input_submitted()` interface hook. Do NOT render the full `SLASH_COMMANDS` list manually inside the welcome screen banner, as the command list is meant to grow dynamically without consuming horizontal/vertical layout space.

> [!NOTE]
> The scaffold includes a built-in `/config` command (implemented in `src/main.py`) which renders the currently loaded `config.cfg` structure dynamically via markdown. If you add highly specialized settings or commands that require explicit UI visibility mapping, remember to check and update this `/config` display hook if the default dictionary iteration loop cannot capture it natively.

```python
from textual.app import App, ComposeResult
from textual.widgets import Input, OptionList
from textual import events

class AgentTerminal(App):
    SLASH_COMMANDS = [
        ("/stop", "Emergency stop generation"),
        ("/toggle_thinking", "Enable/Disable slow reasoning models")
    ]

    def compose(self) -> ComposeResult:
        # Visually hide the command list on startup
        opt_list = OptionList(id="command-list")
        opt_list.display = False
        yield opt_list
        yield Input(id="prompt-input", placeholder="Chat or use / ...")

    def on_input_changed(self, event: Input.Changed) -> None:
        """Trigger autocompletion filters when text shifts"""
        val = event.value
        opt_list = self.query_one("#command-list", OptionList)
        
        if val.startswith("/"):
            filtered = [
                (cmd, desc) for cmd, desc in self.SLASH_COMMANDS
                if cmd.startswith(val.lower())
            ]
            opt_list.clear_options()
            for cmd, desc in filtered:
                opt_list.add_option(f"{cmd} - {desc}")
            opt_list.display = True
        else:
            opt_list.display = False
            
    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Intercept the submission event"""
        val = event.value.strip()
        opt_list = self.query_one("#command-list", OptionList)
        opt_list.display = False # hide upon submit
        
        if val.lower() == "/stop":
            # Fire cancellation logic globally
            pass
```

## 3. Rendering Asynchronous Hierarchical Tool Execution

A core mechanism of local `agent-framework` execution is handling tool-call delegations inside real-time async streams. Because sub-agents spawn nested trees, you must differentiate parent tools from child tools visually using nested `Collapsible` arrays logic.

### CSS Hierarchy Strategy
```css
/* Color code nested delegations to prevent screen-clutter */
.orchestrator-tool { border-left: vkey $primary; }
.subagent-tool { border-left: vkey $secondary; margin: 0 2 1 6; }
.nested-subagent-tool { border-left: vkey $accent; margin: 0 2 1 10; }
```

### Stream Pipeline Architecture
**Rule: To render deeply nested Sub-Agents and async tools without UI-freezing, you MUST inject AgentFramework's `AgentResponseUpdate` chunks into the DOM directly.**
Do not attempt to write this loop from scratch. Clone `handle_agent_update` and `ToolCallWidget` exactly as implemented in `examples/basic-tui-agent/src/main.py`.

## 4. Human-in-the-Loop (HITL) Asynchronous Interception
If the agent invokes a tool marked with `@tool(approval_mode="always_require")` (like a destructive file operation), the chunk will yield `user_input_requests`.
**Rule: You must halt the asynchronous loop, retrieve boolean approval, and manually push a synthetic context trace back.**
Clone the HITL loop intercept implemented in `examples/basic-tui-agent/src/main.py` explicitly.
```
