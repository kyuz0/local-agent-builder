---
name: local-agent-builder
description: Complete blueprint, constraints, and scaffolding for building agentic workflows optimized for local LLMs.
---
# Local LLM Agent Development Guide

You are instructed to build agentic workflows specifically optimized for **Local LLMs** (e.g., Qwen 3.5, Gemma-4). Your primary objective is strict context management, low memory bandwidth utilization, and robust parsing of LLM outputs on constrained hardware.

You **MUST** use Microsoft's **agent-framework** to implement these tasks.

You must rigorously adhere to the blueprints mapped out in the `resources/docs/` directory.

## Required Blueprints
Familiarize yourself with and deploy the exact recipes documented below. 

You will find the scaffold project and documentation for how to create agents in the `examples` and `resources` subfolders of this skill. **DO NOT edit or touch the files inside these folders.** These are strictly read-only references for you.

> **MANDATORY CHECKLIST:** Before presenting any `implementation_plan.md` or completing your final code generation, you MUST explicitly evaluate your work against **[CHECKLIST.md](resources/docs/CHECKLIST.md)**. Use it as a literal verification mechanism to ensure you have not violated dependency ordering or scaffold integrity.

> **CRITICAL PATH RESOLUTION FOR AI AGENTS:** Since this skill may be loaded from a global skills directory (e.g., `~/opencode/skills/`) or local skills directory (e.g., `.opencode/skills/`), all file paths mentioned below (like `resources/...` and `examples/...`) are relative to the folder containing this `SKILL.md` file. You **MUST** resolve these to their absolute paths using `SKILL.md`'s location before using your tools to list, read, or copy them. Do not assume they are in the current working directory.

> [!TIP]
> **CONTEXT MANAGEMENT: AVOID BLINDLY READING ALL FILES.**
> Your context window is precious! Do **not** blindly read every `.md` document in the `resources/docs/` folder. Usually, you only need to read `ARCHITECTURE.md` and `IMPLEMENTATION.md` and possibly `TOOLS.md`. Skip documents like `SHELL.md` or `MAILBOX.md` unless the user explicitly requests those specific advanced capabilities.

**MANDATORY STARTING STEPS FOR BUILDING NEW APPLICATIONS:** 
- **STAGE 1 (Baseline Scaffold):** First, you **MUST** copy the entire contents of the `examples/basic-tui-agent/` directory to the main project working directory as your primary starting point, and read its `README.md`.
    - Always rely on `pyproject.toml` for adding new dependencies. Do **not** create a `requirements.txt` file.
    - Modify the `name` field in the `[project]` block of the copied `pyproject.toml` to reflect the agent you are building (e.g., `name = "local-research-agent"`).
    - Modify the `[project.scripts]` block in the copied `pyproject.toml` to name the system-wide executable command after the agent you are building (e.g. `local-research-agent = "src.app:cli_main"`).
    - Instruct the user to install the agent using `pipx install .` in the final `README.md`.
- **STAGE 2 (Optional Extensions):** *ONLY* if the user explicitly requests email, background execution, or Mailbox responder features, you must instruct the user to install the global `sasori` daemon (`pipx install ./packages/sasori`). Do NOT write from-scratch polling logic. Instead, write an `[agent_name]_plugin.py` file inheriting from `sasori.handler.BaseMailboxHandler`, and instruct the user to place it in their `~/.sasori/handlers/` directory. Remind the user they'll need to restart the `sasori` daemon.

> [!CAUTION]
> **STRICT REUSE DIRECTIVE: DO NOT REWRITE FROM SCRATCH OR INVENT PATTERNS.**
> You are explicitly forbidden from rewriting the core scaffold architecture. Your task is to perform **LIGHT MODIFICATIONS** to the provided `basic-tui-agent` files. 
> - **Always reuse** the existing scaffold code, tools (`src/app.py`, `tools/`), UI widgets, and logic wrappers wherever possible.
> - **The `engine/` Directory is out-of-bounds:** Do NOT edit files inside `src/engine/` unless strictly necessary. It works out-of-the-box and provides the TUI and Textual logic, shielded so you only need to declare configurations in `src/app.py`.
> - **Never invent or hallucinate architectures.** If a feature is needed, the required pattern is almost certainly already established inside the `resources/docs/` documents or as exemplary code within the scaffold. 
> - Read the code, mimic its native structural patterns exactly, and only inject the specific business logic the user requested.

1. **[Architecture](resources/docs/ARCHITECTURE.md)**: Rules for context management and Flat vs Sub-Agent pipelines. **(CRITICAL: Configure sub-agents via the AgentBuilder SDK inside `src/app.py`!)**
2. **[Implementation](resources/docs/IMPLEMENTATION.md)**: Vital Python boilerplates for `<think>` tag scraping, TUI integrations, and Headless CLI (`--prompt`, `--auto-approve`, `--resume`) batch processing. Includes rules on deleting (`pruning`) optional features like `markitdown` parsers or `web_search` to save context if unneeded.
3. **[Tools](resources/docs/TOOLS.md)**: Copy-paste snippets for Web Search, Parsing, Virtual FS, and **[Shell Execution](resources/docs/SHELL.md)**. (*Note: The shell tool introduces monumental security risks. You must explicitly remove `run_shell_command` from the scaffold if unused, unless the user specifically demands bash or compilation capabilities!*)
4. **[UI Guidelines](resources/docs/UI_GUIDELINES.md)**: Textual rendering rules, spanning the `OptionList` dropdown components and the collapsible workspace file viewers natively triggered via `/files` commands (dynamically reads from in-memory or on-disk based on `config.yaml`).
5. **[Coding Guidelines](resources/docs/CODING_GUIDELINES.md)**: LLM-focused code quality constraints (e.g. flat directory layouts over nesting, strict type hints, and eliminating useless inline comments to preserve tokens).
6. **[Prompting & Delegation Guidelines](resources/docs/PROMPTING.md)**: Architectural rules for structuring Microsoft Agent-Framework pipelines.
7. **[Mailbox Daemon Pattern](resources/docs/MAILBOX.md)**: Architectural rules for wrapping agents into an optional background email workflow.

## Internal & External References
You should search through and read the official Microsoft agent-framework documentation and samples before guessing APIs or mechanisms:

**Agent Framework Examples (Search inside these web URLs or even pull the entire github repo is you need to have stuff locally that you can inspect):**
- **Core Agent Patterns**: Inspect `https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/`
- **DAG Workflow Patterns**: Inspect `https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows/` (specifically `checkpoint/` and `control-flow/` examples)

**External Web Documentation:**
- **Microsoft agent-framework**: [Documentation](https://learn.microsoft.com/en-us/agent-framework/) | [GitHub Repository](https://github.com/microsoft/agent-framework)
- **Textual (UI Framework)**: [Documentation](https://textual.textualize.io/)
- **Document Extractors**: [MarkItDown](https://github.com/microsoft/markitdown) | [LlamaIndex Liteparse](https://www.npmjs.com/package/@llamaindex/liteparse)
