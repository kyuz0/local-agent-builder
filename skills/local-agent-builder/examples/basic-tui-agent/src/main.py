from datetime import datetime
from textual import work, on
from textual.app import App, ComposeResult
from textual.widgets import Input, OptionList, Static, Collapsible, RichLog, Button
from textual.containers import VerticalScroll, Horizontal
from rich.markdown import Markdown
from chat import create_local_agent, reset_session
import asyncio
import json
import config
from agent_framework import Message
from textual import events
import os
import json
import uuid
import re
import sys
import argparse
from pathlib import Path
import pyfiglet

AGENT_NAME = config.APP_TITLE
AGENT_DESCRIPTION = config.APP_DESCRIPTION

_session_events = []
_current_call_by_source = {}
_current_text_by_source = {}
_current_session_id = str(uuid.uuid4())

def _write_log():
    if not config.cfg["settings"].get("enable_session_logging", False):
        return
        
    log_dir = Path.home() / f".{config.APP_NAME}-logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    log_file = log_dir / f"session_{_current_session_id}.json"
    try:
        with open(log_file, "w", encoding="utf-8") as f:
            json.dump(_session_events, f, indent=2)
    except Exception:
        pass

def log_prompt(prompt: str):
    global _session_events, _current_call_by_source, _current_text_by_source
    _session_events.append({
        "timestamp": datetime.now().isoformat(),
        "source": "User",
        "type": "prompt",
        "data": {"text": prompt}
    })
    _current_call_by_source.clear()
    _current_text_by_source.clear()
    _write_log()

def log_stream_content(source: str, content_type: str, raw_data_dict: dict):
    global _session_events, _current_call_by_source, _current_text_by_source
    
    if content_type == "text" or content_type == "reasoning":
        text_val = raw_data_dict.get("text")
        if not text_val: return
        _current_call_by_source[source] = None
        
        idx = _current_text_by_source.get(source)
        if idx is not None and idx < len(_session_events) and _session_events[idx]["type"] == content_type:
            _session_events[idx]["data"]["text"] += text_val
        else:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "source": source,
                "type": content_type,
                "data": {"text": text_val}
            }
            _session_events.append(entry)
            _current_text_by_source[source] = len(_session_events) - 1
            
    elif content_type == "function_call":
        _current_text_by_source[source] = None
        
        call_id = raw_data_dict.get("call_id")
        name = raw_data_dict.get("name")
        arguments = raw_data_dict.get("arguments", "")
        
        if call_id:
            entry = {
                "timestamp": datetime.now().isoformat(),
                "source": source,
                "type": "function_call",
                "data": {
                    "call_id": call_id,
                    "name": name,
                    "arguments": arguments
                }
            }
            _session_events.append(entry)
            _current_call_by_source[source] = len(_session_events) - 1
        else:
            idx = _current_call_by_source.get(source)
            if idx is not None and idx < len(_session_events):
                if arguments:
                    _session_events[idx]["data"]["arguments"] += arguments
            
    elif content_type == "function_result":
        _current_text_by_source[source] = None
        _current_call_by_source[source] = None
        
        entry = {
            "timestamp": datetime.now().isoformat(),
            "source": source,
            "type": "function_result",
            "data": raw_data_dict
        }
        _session_events.append(entry)
        
    _write_log()

class PromptInput(Input):
    """An Input that maintains command history navigated with Up/Down arrows."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._history: list[str] = []
        self._history_index: int = -1
        
    def on_key(self, event: events.Key) -> None:
        try:
            opt_list = self.app.query_one("#command-list", OptionList)
            if opt_list.display:
                if event.key == "up":
                    if opt_list.highlighted is not None and opt_list.highlighted > 0:
                        opt_list.highlighted -= 1
                    event.prevent_default()
                    return
                elif event.key == "down":
                    if opt_list.highlighted is None:
                        opt_list.highlighted = 0
                    elif opt_list.highlighted < opt_list.option_count - 1:
                        opt_list.highlighted += 1
                    event.prevent_default()
                    return
                elif event.key == "tab":
                    if opt_list.highlighted is not None:
                        opt = opt_list.get_option_at_index(opt_list.highlighted)
                        cmd = str(opt.prompt).split(" - ")[0]
                        self.value = cmd
                        self.cursor_position = len(cmd)
                    event.prevent_default()
                    return
                elif event.key == "enter":
                    if opt_list.highlighted is not None:
                        opt = opt_list.get_option_at_index(opt_list.highlighted)
                        cmd = str(opt.prompt).split(" - ")[0]
                        self.value = cmd
                        self.cursor_position = len(cmd)
                    # allow enter to propagate
        except Exception:
            pass

        if event.key == "up":
            if self._history and self._history_index > 0:
                self._history_index -= 1
                self.value = self._history[self._history_index]
            elif self._history and self._history_index == -1:
                self._history_index = len(self._history) - 1
                self.value = self._history[self._history_index]
            event.prevent_default()
        elif event.key == "down":
            if self._history_index != -1 and self._history_index < len(self._history) - 1:
                self._history_index += 1
                self.value = self._history[self._history_index]
            elif self._history_index == len(self._history) - 1:
                self._history_index = -1
                self.value = ""
            event.prevent_default()
            
    def record_history(self, val: str) -> None:
        if val:
            if not self._history or self._history[-1] != val:
                self._history.append(val)
        self._history_index = -1

class ApprovalWidget(Static):
    def __init__(self, action: str):
        super().__init__(classes="agent-bubble")
        self.action = action
        self.approved = False
        self.event = asyncio.Event()

    def compose(self) -> ComposeResult:
        yield Static(Markdown(f"**Tool approval required:** `{self.action}`"))
        with Horizontal(classes="approval-buttons"):
            yield Button("Approve", id="approve", variant="success")
            yield Button("Deny", id="deny", variant="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.approved = (event.button.id == "approve")
        self.event.set()
        self.remove()

class ThinkingWidget(Collapsible):
    """A collapsible widget that streams reasoning tokens in real time."""
    DOTS_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self):
        self._content = Static("", classes="thinking-text")
        self._buffer = ""
        self._frame_idx = 0
        super().__init__(self._content, title="💭 Thinking...", classes="thinking-collapsible")

    def on_mount(self) -> None:
        self.collapsed = False
        self._timer = self.set_interval(0.1, self._animate)

    def _animate(self) -> None:
        self._frame_idx = (self._frame_idx + 1) % len(self.DOTS_FRAMES)
        if not self.collapsed:
            self.title = f"💭 Thinking {self.DOTS_FRAMES[self._frame_idx]}"

    def append(self, text: str) -> None:
        self._buffer += text
        self._content.update(self._buffer)

    def finish(self) -> None:
        if hasattr(self, "_timer"):
            self._timer.stop()
        self.title = "💭 Thinking (done)"
        self.collapsed = True


class AgentMessageWidget(Static):
    def __init__(self, author: str):
        super().__init__(Markdown(f"**{author}:** "), classes="agent-bubble")
        self.author = author
        self.text = ""

    def append_text(self, new_text: str):
        self.text += new_text
        self.update(Markdown(f"**{self.author}:**\n{self.text}"))

class ProcessingWidget(Static):
    """Widget to display a processing indicator before the first response."""
    DOTS_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, agent_name: str = "Agent"):
        super().__init__("", classes="agent-bubble")
        self.agent_name = agent_name
        self._frame = 0
        self._start_time = datetime.now()
        
    def on_mount(self) -> None:
        self._timer = self.set_interval(0.1, self._animate_dots)
        self._animate_dots()

    def _animate_dots(self) -> None:
        self._frame = (self._frame + 1) % len(self.DOTS_FRAMES)
        elapsed = datetime.now() - self._start_time
        self.update(f"[b]{self.agent_name}:[/b] {self.DOTS_FRAMES[self._frame]} ({elapsed.total_seconds():.1f}s)")

    def stop(self) -> None:
        if hasattr(self, "_timer"):
            self._timer.stop()
        self.remove()

    def mark_stopped(self) -> None:
        if hasattr(self, "_timer"):
            self._timer.stop()
        elapsed = datetime.now() - self._start_time
        self.update(f"[b]{self.agent_name}:[/b] \N{OCTAGONAL SIGN} Stopped ({elapsed.total_seconds():.1f}s)")

    def mark_error(self, error_msg: str) -> None:
        if hasattr(self, "_timer"):
            self._timer.stop()
        self.update(f"[b]{self.agent_name}:[/b] [red]\N{CROSS MARK} Error: {error_msg}[/red]")

class ToolCallWidget(Collapsible):
    """Widget to display a tool call and its result."""
    DOTS_FRAMES = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

    def __init__(self, name: str, call_id: str, is_subagent: bool = False):
        self.call_id = call_id
        self.tool_name = name
        self.is_subagent = is_subagent
        self.args_text = ""
        self.result_text = ""
        self._done = False
        self._frame = 0
        self._start_time = datetime.now()
        
        self.args_log = RichLog(wrap=True, markup=True, highlight=True, min_width=20)
        self.args_log.border_title = "Arguments"
        
        self.result_log = RichLog(wrap=True, markup=True, highlight=True, min_width=20)
        self.result_log.border_title = "Result"
        
        agent_label = "Sub-Agent" if is_subagent else "Agent"
        title = f"\N{HAMMER AND WRENCH} \\[{agent_label}] {name} {self.DOTS_FRAMES[0]}"
        css_class = "subagent-tool" if is_subagent else "orchestrator-tool"
        super().__init__(
            self.args_log,
            self.result_log,
            title=title,
            classes=css_class,
            collapsed=True
        )

    def on_mount(self) -> None:
        self._timer = self.set_interval(0.1, self._animate_dots)

    def _animate_dots(self) -> None:
        if self._done:
            self._timer.stop()
            return
        self._frame = (self._frame + 1) % len(self.DOTS_FRAMES)
        elapsed = datetime.now() - self._start_time
        agent_label = "Sub-Agent" if self.is_subagent else "Agent"
        self.title = f"\N{HAMMER AND WRENCH} \\[{agent_label}] {self.tool_name} {self.DOTS_FRAMES[self._frame]} ({elapsed.total_seconds():.1f}s)"

    def append_args(self, text: str):
        self.args_text += text
        self.args_log.clear()
        self.args_log.write(self.args_text)

    def set_result(self, text: str):
        self.result_text = text
        self.result_log.clear()
        self.result_log.write(self.result_text)
        self._done = True
        elapsed = datetime.now() - self._start_time
        agent_label = "Sub-Agent" if self.is_subagent else "Agent"
        self.title = f"\N{HAMMER AND WRENCH} \\[{agent_label}] {self.tool_name} \N{WHITE HEAVY CHECK MARK} ({elapsed.total_seconds():.1f}s)"

    def mark_stopped(self):
        self._done = True
        elapsed = datetime.now() - self._start_time
        agent_label = "Sub-Agent" if self.is_subagent else "Agent"
        self.title = f"\N{HAMMER AND WRENCH} \\[{agent_label}] {self.tool_name} \N{OCTAGONAL SIGN} ({elapsed.total_seconds():.1f}s)"

class BasicTuiAgent(App):
    CSS = """
    #chat-container { height: 1fr; scrollbar-color: green; }
    .user-bubble { margin: 1 2; padding: 1; background: #333333; color: white; text-align: right; }
    .agent-bubble { margin: 1 2; padding: 1; color: white; }
    .orchestrator-tool { border-left: vkey blue; margin: 0 2 1 2; }
    .subagent-tool { border-left: vkey purple; margin: 0 2 1 6; }
    .thinking-collapsible { margin: 0 2 1 2; border-left: vkey #555555; }
    .thinking-collapsible CollapsibleTitle { color: #777777; text-style: italic; }
    .thinking-collapsible Contents { padding: 0; margin: 0; }
    .thinking-collapsible .thinking-text { color: #888888; margin: 0 1; height: auto; }
    RichLog { height: auto; max-height: 20; margin: 0 1; border: solid #333; }
    .approval-buttons { height: auto; margin-top: 1; margin-bottom: 1; }
    .file-viewer-wrapper { border: solid #4CAF50; margin: 1 2; max-height: 25; height: auto; overflow: hidden; background: #222222; }
    .file-viewer-collapsible { width: 1fr; height: auto; }
    .file-viewer-collapsible CollapsibleTitle { color: #81C784; text-style: bold; }
    .file-viewer-inner { position: relative; height: auto; }
    .title-copy-btn { dock: right; width: auto; height: 1; min-width: 3; border: none; background: transparent; color: #888888; padding: 0; margin: 0 1 0 0; }
    .title-copy-btn:hover { color: white; background: transparent; }
    #command-list { height: auto; max-height: 15; padding: 0 1; }
    """

    SLASH_COMMANDS = [("/stop", "Stop execution"), ("/new", "New conversation"), ("/exit", "Quit app"), ("/toggle_thinking", "Toggle reasoning trace capability"), ("/toggle_logging", "Toggle structured session logging"), ("/config", "Show current configuration"), ("/files", "Browse memory workspace files")]

    def compose(self) -> ComposeResult:
        yield VerticalScroll(id="chat-container")
        opt_list = OptionList(id="command-list")
        opt_list.display = False
        yield opt_list
        yield PromptInput(id="prompt-input", placeholder="Type a message or /command...")

    def _banner_widget(self) -> Static:
        try:
            ascii_art = pyfiglet.figlet_format(AGENT_NAME, font="doom")
        except Exception:
            ascii_art = AGENT_NAME + "\n"
            
        endpoint = config.cfg["api"]["openai_base_url"]
        model = config.cfg["api"]["openai_model"]
        thinking = "ON" if config.cfg["settings"]["enable_thinking"] else "OFF"
        thinking_color = "green" if config.cfg["settings"]["enable_thinking"] else "red"
        memory = "ON" if config.cfg["settings"].get("enable_conversational_memory", False) else "OFF"
        memory_color = "green" if config.cfg["settings"].get("enable_conversational_memory", False) else "red"
        logging_val = "ON" if config.cfg["settings"].get("enable_session_logging", False) else "OFF"
        logging_color = "green" if config.cfg["settings"].get("enable_session_logging", False) else "red"
        
        config_path = getattr(config, "_CONFIG_PATH", "Unknown")
        workspace_type = config.cfg.get("settings", {}).get("workspace", {}).get("type", "memory")
        workspace_dir = config.cfg.get("settings", {}).get("workspace", {}).get("dir", ".")
        workspace_disp = f"Disk ({workspace_dir})" if workspace_type == "disk" else "In-Memory"
        status_line = f"  [dim]Config Loaded:[/dim] [bright_black]{config_path}[/bright_black]  [dim]Workspace:[/dim] [yellow]{workspace_disp}[/yellow]\n  [dim]Endpoint:[/dim] [cyan]{endpoint}[/cyan]  [dim]Model:[/dim] [cyan]{model}[/cyan]  [dim]Thinking:[/dim] [{thinking_color}]{thinking}[/{thinking_color}]  [dim]Conv Memory:[/dim] [{memory_color}]{memory}[/{memory_color}]\n  [dim]Session ID:[/dim] [bright_black]{_current_session_id}[/bright_black]  [dim]Logging:[/dim] [{logging_color}]{logging_val}[/{logging_color}]"
        
        return Static(
            f"[bold green]{ascii_art}[/bold green]\n"
            f"  [bold green]{AGENT_DESCRIPTION}[/bold green]\n{status_line}\n\n"
            f"  [dim]Ready! Type a query or use / for commands.[/dim]\n", 
            classes="agent-bubble", id="banner"
        )

    def on_mount(self) -> None:
        self._is_agent_running = False
        self._file_picker_active = False
        self._filtered_cmds = []
        chat = self.query_one("#chat-container", VerticalScroll)
        chat.mount(self._banner_widget())
        self.query_one("#prompt-input", PromptInput).focus()

    def on_input_changed(self, event: Input.Changed) -> None:
        if getattr(self, "_file_picker_active", False): return
        val = event.value
        opt_list = self.query_one("#command-list", OptionList)
        if val.startswith("/"):
            filtered = [(cmd, desc) for cmd, desc in self.SLASH_COMMANDS if cmd.startswith(val.lower())]
            opt_list.clear_options()
            if filtered:
                for cmd, desc in filtered:
                    opt_list.add_option(f"{cmd} - {desc}")
                opt_list.highlighted = 0
                opt_list.display = True
            else:
                opt_list.display = False
        else:
            opt_list.display = False

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        query = event.value.strip()
        event.input.value = ""
        if isinstance(event.input, PromptInput):
            event.input.record_history(query)
            
        if getattr(self, "_file_picker_active", False):
            self._open_selected_file(query)
            return

        self.query_one("#command-list", OptionList).display = False
        
        if not query.startswith("/") and getattr(self, "_is_agent_running", False):
            chat = self.query_one("#chat-container", VerticalScroll)
            chat.mount(Static(Markdown("**System:**\nOperation running. Please type `/stop` first or wait until the current operation finishes."), classes="agent-bubble"))
            chat.scroll_end(animate=False)
            return
            
        if query == "/files":
            self._show_file_picker()
            if not self._file_picker_active:
                chat = self.query_one("#chat-container", VerticalScroll)
                chat.mount(Static(Markdown("**System:**\nNo files currently stored in workspace buffer."), classes="agent-bubble"))
                chat.scroll_end(animate=False)
            return
            
        if query == "/exit": self.exit()
        elif query == "/stop":
            self._is_agent_running = False
            self.workers.cancel_all()
            chat = self.query_one("#chat-container", VerticalScroll)
            for widget in self.query("ToolCallWidget"):
                if not widget._done:
                    widget.mark_stopped()
            for widget in self.query("ProcessingWidget"):
                widget.mark_stopped()
            for widget in self.query("ThinkingWidget"):
                widget.finish()
            chat.mount(Static(Markdown("**System:**\nStopped."), classes="agent-bubble"))
            chat.scroll_end(animate=False)
        elif query == "/new":
            self._is_agent_running = False
            self.workers.cancel_all()
            reset_session()
            
            global _current_session_id, _session_events, _current_call_by_source, _current_text_by_source
            _current_session_id = str(uuid.uuid4())
            _session_events.clear()
            _current_call_by_source.clear()
            _current_text_by_source.clear()
            
            chat = self.query_one("#chat-container", VerticalScroll)
            await chat.remove_children()
            chat.mount(self._banner_widget())
            chat.scroll_end(animate=False)
        elif query == "/toggle_thinking":
            config.cfg["settings"]["enable_thinking"] = not config.cfg["settings"]["enable_thinking"]
            config.save_config()
            state = "ON" if config.cfg["settings"]["enable_thinking"] else "OFF"
            chat = self.query_one("#chat-container", VerticalScroll)
            chat.mount(Static(Markdown(f"**System:**\nThinking capability is now **{state}**"), classes="agent-bubble"))
            chat.scroll_end(animate=False)
        elif query == "/toggle_logging":
            config.cfg["settings"]["enable_session_logging"] = not config.cfg["settings"].get("enable_session_logging", False)
            config.save_config()
            state = "ON" if config.cfg["settings"]["enable_session_logging"] else "OFF"
            chat = self.query_one("#chat-container", VerticalScroll)
            msg = f"**System:**\nSession logging is now **{state}**."
            if config.cfg["settings"]["enable_session_logging"]:
                log_dir = Path.home() / f".{config.APP_NAME}-logs"
                log_file = log_dir / f"session_{_current_session_id}.json"
                msg += f"\nLogging to: `{log_file}`"
                _write_log() # Force an initial write so the file exists
            chat.mount(Static(Markdown(msg), classes="agent-bubble"))
            chat.scroll_end(animate=False)
        elif query == "/config":
            chat = self.query_one("#chat-container", VerticalScroll)
            config_path = getattr(config, "_CONFIG_PATH", "Unknown")
            lines = [f"**System Configuration (Loaded from: `{config_path}`)**\n"]
            for section, values in config.cfg.items():
                lines.append(f"### {section.replace('_', ' ').title()}")
                if isinstance(values, dict):
                    for k, v in values.items():
                        lines.append(f"- **{k}:** `{v}`")
                else:
                    lines.append(f"- `{values}`")
                lines.append("")
            chat.mount(Static(Markdown("\n".join(lines)), classes="agent-bubble"))
            chat.scroll_end(animate=False)
        elif query: 
            log_prompt(query)
            self.run_agent(query)
    def _safe_scroll_end(self, chat: VerticalScroll) -> None:
        """Scroll to the bottom only if the user is already near the bottom."""
        if chat.max_scroll_y - chat.scroll_y <= 3:
            chat.scroll_end(animate=False)

    async def handle_agent_update(self, update, state, chat, is_subagent=False, agent_name=None):
        # --- Extract reasoning_content from raw chunk delta ---
        raw_reasoning = None
        chat_update = getattr(update, "raw_representation", None)
        raw_chunk = getattr(chat_update, "raw_representation", None)
        if raw_chunk and hasattr(raw_chunk, "choices"):
            for ch in raw_chunk.choices:
                delta = getattr(ch, "delta", None)
                if delta:
                    extras = getattr(delta, "model_extra", None) or {}
                    raw_reasoning = extras.get("reasoning_content")

        has_any_content = bool(update.contents) or bool(raw_reasoning)
        if not state.get("has_first_token", False) and has_any_content:
            state["has_first_token"] = True
            widget = state.get("processing_widget")
            if widget:
                widget.stop()
                state["processing_widget"] = None

        source_name = agent_name if agent_name else ("Sub-Agent" if is_subagent else "Agent")
        
        # Calculate dynamic nesting depth based on open, unresolved tool calls in the current state
        active_tools = sum(1 for w in state.get("calls", {}).values() if not w._done)
        depth = (1 + active_tools) if is_subagent else active_tools

        def apply_depth_style(widget):
            if depth > 0:
                widget.styles.margin = (0, 2, 1, 2 + (4 * depth))
                widget.styles.border_left = ("vkey", "purple" if depth > 0 else "blue")
            return widget

        if raw_reasoning:
            log_stream_content(source_name, "reasoning", {"text": raw_reasoning})
            if state.get("thinking_widget") is None:
                tw = ThinkingWidget()
                state["thinking_widget"] = tw
                chat.mount(apply_depth_style(tw))
            state["thinking_widget"].append(raw_reasoning)
            self._safe_scroll_end(chat)
        
        for content in update.contents:
            if content.type == "text_reasoning":
                reasoning_text = content.text or ""
                log_stream_content(source_name, "reasoning", {"text": reasoning_text})
                if not reasoning_text and content.protected_data:
                    try:
                        details = json.loads(content.protected_data)
                        if isinstance(details, list):
                            reasoning_text = "\n".join(
                                d.get("text", "") for d in details if isinstance(d, dict)
                            )
                    except Exception:
                        pass
                if reasoning_text:
                    if state.get("thinking_widget") is None:
                        tw = ThinkingWidget()
                        state["thinking_widget"] = tw
                        chat.mount(apply_depth_style(tw))
                    state["thinking_widget"].append(reasoning_text)
                    self._safe_scroll_end(chat)

            elif content.type == "text":
                if is_subagent:
                    # Suppress subagent text from pouring into the main chat console.
                    # It will be cleanly presented as the final Tool Result when the delegation tool returns.
                    continue

                if content.text:
                    log_stream_content(source_name, "text", {"text": content.text})
                    
                if state.get("thinking_widget") is not None:
                    state["thinking_widget"].finish()
                    state["thinking_widget"] = None
                if state["current_msg"] is None:
                    state["current_msg"] = AgentMessageWidget(source_name)
                    chat.mount(apply_depth_style(state["current_msg"]))
                state["current_msg"].append_text(content.text)
                self._safe_scroll_end(chat)
                
            elif content.type == "function_call":
                call_id = getattr(content, "call_id", None)
                name = getattr(content, "name", None)
                arguments = getattr(content, "arguments", "") or ""
                log_stream_content(source_name, "function_call", {
                    "call_id": call_id, "name": name, "arguments": arguments
                })
                
                state["current_msg"] = None
                if content.call_id:
                    state["current_call_id"] = content.call_id
                    if content.call_id not in state["calls"]:
                        widget = ToolCallWidget(name=content.name, call_id=content.call_id, is_subagent=is_subagent)
                        state["calls"][content.call_id] = widget
                        chat.mount(apply_depth_style(widget))
                    else:
                        widget = state["calls"][content.call_id]
                        
                    if content.arguments:
                        widget.append_args(content.arguments)
                else:
                    call_id = state["current_call_id"]
                    if call_id and call_id in state["calls"] and content.arguments:
                        state["calls"][call_id].append_args(content.arguments)
                        
            elif content.type == "function_result":
                call_id = getattr(content, "call_id", None)
                result = getattr(content, "result", "")
                log_stream_content(source_name, "function_result", {"call_id": call_id, "result": str(result)})
                
                state["current_msg"] = None
                target_widget = None
                if call_id and call_id in state["calls"]:
                    target_widget = state["calls"].pop(call_id)
                    
                if not target_widget:
                    target_name = getattr(content, "name", None)
                    if target_name:
                        for cid, cw in list(state["calls"].items()):
                            if cw.tool_name == target_name and not cw._done:
                                target_widget = state["calls"].pop(cid)
                                break

                if target_widget:
                    target_widget.set_result(str(getattr(content, "result", getattr(content, "content", "Executed."))))
                    
        self._safe_scroll_end(chat)

    @work(exclusive=True)
    async def run_agent(self, query: str):
        self._is_agent_running = True
        
        # [OPTIONAL SESSION DIRECTORY PATTERN]
        # Uncomment below to cleanly isolate and map ALL workspace file operations 
        # for this run to a subfolder (e.g. `run_timestamp/`). This ensures sub-agents
        # share the same flat paths without confusion.
        # import time
        # from tools.fs import session_dir_ctx
        # session_token = session_dir_ctx.set(f"run_{int(time.time())}")
        
        # Initialize tool quotas from config
        from tools import tool_quotas_ctx
        config_quotas = config.cfg.get("settings", {}).get("quotas", {})
        sub_quotas = {}
        for k, v in config_quotas.items():
            if isinstance(v, int) and v > 0:
                sub_quotas[k] = {"used": 0, "limit": v}
            elif isinstance(v, dict) and "limit" in v:
                sub_quotas[k] = {"used": 0, "limit": v["limit"], "rules": v.get("rules", {})}
        token = tool_quotas_ctx.set(sub_quotas)
        
        chat = self.query_one("#chat-container", VerticalScroll)
        chat.mount(Static(Markdown(f"**User:**\n{query}"), classes="user-bubble"))
        
        # Set up subagent callback context
        subagent_state = {"calls": {}, "current_call_id": None, "current_msg": None}

        async def ui_callback(update, is_subagent=True, **kwargs):
            await self.handle_agent_update(update, subagent_state, chat, is_subagent=is_subagent, agent_name=kwargs.get("agent_name"))
            
        # Create agent (re-reads config) and get session (None if conversational memory disabled)
        agent, session = create_local_agent(subagent_callback=ui_callback)
        current_input = query
        has_requests = True
        state = {"calls": {}, "current_call_id": None, "current_msg": None}
        
        while has_requests:
            has_requests = False
            user_input_requests = []
            
            stream = agent.run(current_input, session=session, stream=True)
            state["current_msg"] = None
            state["has_first_token"] = False
            state["processing_widget"] = ProcessingWidget("Agent")
            chat.mount(state["processing_widget"])
            self._safe_scroll_end(chat)
            
            try:
                async for update in stream:
                    await self.handle_agent_update(update, state, chat, is_subagent=False)
                    
                    if hasattr(update, "user_input_requests") and update.user_input_requests:
                        user_input_requests.extend(update.user_input_requests)

            except Exception as e:
                p_widget = state.get("processing_widget")
                if p_widget:
                    p_widget.mark_error(str(e))
                    state["processing_widget"] = None
                else:
                    chat.mount(Static(f"[red]Error: {str(e)}[/red]", classes="agent-bubble"))
                chat.scroll_end(animate=False)

            if user_input_requests:
                has_requests = True
                new_inputs = [query] if isinstance(current_input, str) else list(current_input)
                
                for req in user_input_requests:
                    # Mount the interactive widget
                    widget = ApprovalWidget(req.function_call.name)
                    chat.mount(widget)
                    chat.scroll_end(animate=False)
                    
                    # Pause loop to wait for physical user interaction event loop
                    await widget.event.wait()
                    
                    # Temporarily update the UI to show execution has begun without removing it from active state.
                    call_id = getattr(req.function_call, "id", None) if hasattr(req, "function_call") else None
                    target_widget = state["calls"].get(call_id)
                    
                    if not target_widget:
                        for cid, cw in state["calls"].items():
                            if hasattr(req, "function_call") and cw.tool_name == req.function_call.name and not cw._done:
                                target_widget = cw
                                break
                    
                    if target_widget and widget.approved:
                        args_dict = req.function_call.parse_arguments() or {}
                        # Statically find the python function to execute UI updates explicitly 
                        from tools import WORKSPACE_TOOLS
                        tool_func = next((t for t in WORKSPACE_TOOLS if t.name == req.function_call.name), None)
                        
                        try:
                            if tool_func and hasattr(tool_func, "func"):
                                # Run sync evaluation natively to stop the TUI loading spinner
                                result_str = str(tool_func.func(**args_dict))
                            else:
                                result_str = "Executed natively."
                        except Exception as e:
                            result_str = f"Error: {e}"
                            
                        target_widget.set_result(result_str)
                        
                        # Bypass the framework double-execution and just feed the literal explicitly back 
                        from agent_framework import Content
                        new_inputs.append(Message("assistant", [req.function_call]))
                        new_inputs.append(Message("tool", [Content.from_function_result(
                            call_id=req.function_call.call_id,
                            result=result_str
                        )]))
                        
                    elif target_widget and not widget.approved:
                        target_widget.set_result("Denied by user.")
                        new_inputs.append(Message("assistant", [req.function_call]))
                        new_inputs.append(Message("user", [req.to_function_approval_response(False)]))
                    else:
                        # Fallback for weird edge cases without widgets
                        new_inputs.append(Message("assistant", [req.function_call]))
                        new_inputs.append(Message("user", [req.to_function_approval_response(widget.approved)]))
                
                # Push back upstream and flush state 
                current_input = new_inputs
                
        from tools import tool_quotas_ctx
        tool_quotas_ctx.reset(token)
        self._is_agent_running = False

    def _render_cmd_list(self) -> None:
        panel = self.query_one("#command-list", OptionList)
        if not self._filtered_cmds:
            panel.display = False
            return
        panel.clear_options()
        for i, (cmd, desc) in enumerate(self._filtered_cmds):
            panel.add_option(f"{cmd} - {desc}")
        panel.highlighted = 0
        panel.display = True

    def _show_file_picker(self) -> None:
        from tools import get_workspace_files, get_workspace_file_content
        files = get_workspace_files()
        if not files:
            self._file_picker_files = []
            self._file_picker_active = False
            return
        self._file_picker_files = files
        self._file_picker_active = True
        self._filtered_cmds = [
            (f, f"{len((get_workspace_file_content(f) or '').encode('utf-8'))} bytes")
            for f in files
        ]
        self._render_cmd_list()

    def _display_file(self, filename: str, collapsed_by_default: bool = False) -> None:
        from tools import get_workspace_file_content
        from textual.containers import Vertical
        
        content = get_workspace_file_content(filename)
        if content is None: return
        
        chat_container = self.query_one("#chat-container", VerticalScroll)
        try:
            file_log = RichLog(wrap=True, markup=True, highlight=True, min_width=20)
            copy_btn = Button("📋", id=f"copy-btn-{id(file_log)}", classes="title-copy-btn")
            copy_btn._file_content = content
            inner = Vertical(copy_btn, file_log, classes="file-viewer-inner")
            viewer = Collapsible(inner, title=f"\N{OPEN FILE FOLDER} {filename}", classes="file-viewer-collapsible")
            wrapper = Vertical(viewer, classes="tool-call file-viewer-wrapper")
            chat_container.mount(wrapper)
            viewer.collapsed = collapsed_by_default
            file_log.write(content)
        except Exception as e:
            chat_container.mount(Static(Markdown(f"**System:**\nError reading {filename}: {e}"), classes="agent-bubble"))
        chat_container.scroll_end(animate=False)

    @on(Button.Pressed, ".title-copy-btn")
    def on_copy_button(self, event: Button.Pressed) -> None:
        if hasattr(event.button, "_file_content"):
            self.app.copy_to_clipboard(event.button._file_content)
            btn = event.button
            btn.label = "✅"
            def reset():
                btn.label = "📋"
            self.set_timer(2.0, reset)

    def _open_selected_file(self, filename: str) -> None:
        if not self._file_picker_active:
            return
        self._display_file(filename)
        self._file_picker_active = False
        self._filtered_cmds = []
        self.query_one("#command-list", OptionList).display = False

async def run_cli(prompt: str = None, prompt_file: str = None):
    """Run the agent in headless mode, streaming results to stdout."""
    from tools import tool_quotas_ctx
    config_quotas = config.cfg.get("settings", {}).get("quotas", {})
    sub_quotas = {}
    for k, v in config_quotas.items():
        if isinstance(v, int) and v > 0:
            sub_quotas[k] = {"used": 0, "limit": v}
        elif isinstance(v, dict) and "limit" in v:
            sub_quotas[k] = {"used": 0, "limit": v["limit"], "rules": v.get("rules", {})}
    token = tool_quotas_ctx.set(sub_quotas)

    async def cli_subagent_callback(update, is_subagent=True, **kwargs):
        agent_name = kwargs.get("agent_name") or getattr(update, "author_name", None) or "Sub-Agent"
        for content in update.contents:
            log_stream_content(agent_name, "content", {"type": content.type})
            if content.type == "function_call" and content.call_id:
                sys.stdout.write(f"\n\033[93m[{agent_name}] Calling {content.name}...\033[0m\n")

    agent, session = create_local_agent(subagent_callback=cli_subagent_callback)

    if prompt_file:
        try:
            with open(prompt_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                prompt = "\n\n".join([f"{msg.get('role', 'user').upper()}:\n{msg.get('content', '')}" for msg in data])
            else:
                prompt = json.dumps(data)
        except Exception as e:
            sys.stdout.write(f"\n\033[91mError reading prompt file: {e}\033[0m\n")
            return
            
    sys.stdout.write(f"\n\033[1mStarting task:\033[0m {prompt[:100]}...\n\n")
    start_time = datetime.now()
    
    try:
        stream = agent.run(prompt, session=session, stream=True)
        async for update in stream:
            for content in update.contents:
                if content.type == "text" and content.text:
                    sys.stdout.write(content.text)
                    sys.stdout.flush()
                elif content.type == "function_call" and content.call_id:
                    sys.stdout.write(f"\n\033[96m[Agent] Calling {content.name}...\033[0m\n")
                    
        elapsed = datetime.now() - start_time
        sys.stdout.write(f"\n\n\033[1mTask completed in {elapsed.total_seconds():.1f} seconds.\033[0m\n")
    except Exception as e:
        sys.stdout.write(f"\n\033[91mError:\033[0m {e}\n")
    finally:
        tool_quotas_ctx.reset(token)

def cli_main():
    parser = argparse.ArgumentParser(description="Basic Agent TUI / CLI Scaffold")
    parser.add_argument("--config", "-c", type=str, help="Path to config.yaml", default=None)
    parser.add_argument("--prompt", "-p", type=str, help="Run non-interactively with a specific prompt (headless mode)", default=None)
    parser.add_argument("--prompt-file", "-f", type=str, help="Run non-interactively reading a JSON context file", default=None)
    args, _ = parser.parse_known_args()

    if args.prompt_file:
        asyncio.run(run_cli(prompt_file=args.prompt_file))
    elif args.prompt:
        log_prompt(args.prompt)
        asyncio.run(run_cli(prompt=args.prompt))
    else:
        BasicTuiAgent().run()

if __name__ == "__main__":
    cli_main()
