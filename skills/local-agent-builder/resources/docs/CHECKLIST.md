# Local Agent Implementation Checklist

> **Instructions for the Coding Assistant:** Before finalizing your implementation plan or returning control to the user, you MUST cross-reference your proposed logic and generated code against this checklist. Failure to verify these items will result in fatal structural errors.

### 1. Scaffold Integrity & Reuse
- [ ] **No Rewrites:** Did I firmly reject any impulses to rewrite the architecture from scratch? 
- [ ] **Light Modifications Only:** Did I copy the basic scaffold, modify as little as possible (since it works like a charm), and focus MOST edits strictly on `src/app.py`, `src/prompts.py`, `pyproject.toml`, `README.md`, and config YAML (`src/config_template.yaml`) to configure the required agent and subagent structures, leaving the core engine (`src/engine/`) completely untouched?
- [ ] **No Tool Rewrites:** Did I avoid rewriting existing tools (like files, web search, or parsing tools)? Did I prioritize reusing them as-is, make only minimal changes based on comments and documentation guidance, and reject writing new tool logic from scratch?
- [ ] **Prompt Preservation & Formatting Safety:** Did I retain all essential format keys (e.g., `{task_name}`, `{date}`, `{delegation_instructions}`, `{delegate_quota}`, `{fetch_quota}`) in my customized prompts? Did I ensure sub-agent instructions contain `{task_name}` so child agents actually receive the task query, rather than running blindly?
- [ ] **Task Context Propagation:** Did I instruct the Orchestrator to analyze the user's query, break it down into specific tasks/angles, and pass *those specific angles* to sub-agents via the `delegate_tasks` tool (rather than passing generic or hardcoded instructions)?
- [ ] **String Interpolation Safety:** Did I avoid using single braces `{}` for un-interpolated placeholder variables inside system prompts passed to `.format()`? (e.g. use `{{run_folder}}` or `<run_folder>` so Python doesn't throw a fatal `KeyError`).
- [ ] **Anti-Looping Traps:** Did I inject a strict `<Anti-Looping>` clause into my `ORCHESTRATOR_INSTRUCTIONS` demanding that it NEVER call the exact same tool with identical arguments twice in a row? (Crucial to break `write_todos` infinite loops on small local models!).
- [ ] **Application Branding & Packaging:** Did I rename the default `basic-tui-agent` into a sensible, task-specific identity? This requires updating the `name` field in `pyproject.toml`, the `[project.scripts]` executable definition, AND the `APP_NAME`, `APP_TITLE`, and `APP_DESCRIPTION` constants at the top of `src/config.py`.

### 2. Sub-Agent Delegation (Strict Validation)
- [ ] **Location Restraint:** Are ALL of my sub-agents configured purely as `SubAgentConfig` definitions inside `src/app.py`? (Do not try to edit `engine/orchestrator.py` manually).
- [ ] **Nested Delegation Registry:** Did I register all nested sub-agents in the flat `sub_agents=[...]` list of the `AgentBuilder` in `src/app.py` instead of rewriting the orchestrator to pass configurations manually?
- [ ] **Dependency Ordering (CRITICAL):** Did I define deeply-nested sub-agents *before* their parent agents sequentially in the file? (e.g., defining `delegate_analyzer` above `delegate_searcher` so it can be passed into `tools=[]` without a `NameError`).
- [ ] **No Hallucinated State:** Am I statically hardcoding the `name="SubAgent"` in `client.as_agent()`? I MUST NOT invent global list counters (`_get_next_id()`).
- [ ] **Decorator Safety:** Does every delegation `@tool` have an explicit, strongly-typed `description` to prevent JSON schema generation failures?
- [ ] **Stream Execution:** Did I correctly wrap `sub_agent.run(..., stream=True)` and await `subagent_callback` to ensure the TUI doesn't freeze?

### 3. Tool Quotas & Execution
- [ ] **Clean Quota Configs (CRITICAL LIMIT CHECK):** Did I safely extract the integer limit from `config_template.yaml` instead of passing a raw `dict` dictionary? (e.g., extracting `.get("limit", 5)`). If you pass a dict into `tool_quotas_ctx.set(...)`, it will trigger a `TypeError` (int >= dict) causing `Error: Function failed.`!
- [ ] **Schema Omission Trap:** Did I actually inject the specific delegation tool into the sub-agent's `tools=[...]` array? (If the agent thinks about delegating but never calls the tool, it's because I forgot to attach the tool to it).
- [ ] **Architectural Boundaries:** Did I withhold inappropriate tools from the Orchestrator (e.g. stripping `web_search`) to force proper sub-agent delegation?

### 4. Optional Extensions
- [ ] **Mailbox Segregation:** If asked to execute via email, did I use the `mailbox-daemon-addon` daemon pattern entirely decoupled from `app.py`?
- [ ] **Storage & Path Mapping:** Is in-memory vs disk storage configured correctly? If the user asked for isolated workflow runs or per-session directories, did I explicitly uncomment the `session_dir_ctx` setup in `engine/tui.py` so that all files are transparently routed to the active namespace, avoiding sub-agent flat-path confusion?
- [ ] **Shell Execution Safety:** If I included the `run_shell_command` tool, did I only do so because the user explicitly requested it? (If not, REMOVE IT NOW to secure the environment). If included, did I configure the Anthropic SRT sandbox constraints safely in `config.yaml` if this applies to the use-case?
