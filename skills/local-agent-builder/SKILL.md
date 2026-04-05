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

> **CRITICAL PATH RESOLUTION FOR AI AGENTS:** Since this skill may be loaded from a global skills directory (e.g., `~/opencode/skills/`) or local skills directory (e.g., `.opencode/skills/`), all file paths mentioned below (like `resources/...` and `examples/...`) are relative to the folder containing this `SKILL.md` file. You **MUST** resolve these to their absolute paths using `SKILL.md`'s location before using your tools to list, read, or copy them. Do not assume they are in the current working directory.

**MANDATORY FIRST STEP: When building a new app, you MUST copy the entire contents of the `examples/basic-tui-agent/` directory (located in this skill's folder) to the main project working directory as your starting point**, and read its `README.md`.

1. **[Architecture](resources/docs/ARCHITECTURE.md)**: Rules for context management and Flat vs Sub-Agent pipelines. **(CRITICAL: Sub-agent loop handlers MUST reside in `chat.py`, never in `tools/`!)**
2. **[Implementation](resources/docs/IMPLEMENTATION.md)**: Vital Python boilerplates for `<think>` tag scraping, TUI integrations, and Headless CLI (`--prompt`) batch processing. Includes rules on deleting (`pruning`) optional features like `markitdown` parsers or `web_search` to save context if unneeded.
3. **[Tools](resources/docs/TOOLS.md)**: Copy-paste snippets for Web Search, Parsing, and Virtual FS.
4. **[UI Guidelines](resources/docs/UI_GUIDELINES.md)**: Textual rendering rules, spanning the `OptionList` dropdown components and the collapsible workspace file viewers natively triggered via `/files` commands (dynamically reads from in-memory or on-disk based on `config.yaml`).
5. **[Coding Guidelines](resources/docs/CODING_GUIDELINES.md)**: LLM-focused code quality constraints (e.g. flat directory layouts over nesting, strict type hints, and eliminating useless inline comments to preserve tokens).
6. **[Prompting & Delegation Guidelines](resources/docs/PROMPTING.md)**: Architectural rules for structuring Microsoft Agent-Framework pipelines.

## Internal & External References
You should search through and read the official Microsoft agent-framework documentation and samples before guessing APIs or mechanisms:

**Agent Framework Examples (Search inside these web URLs or even pull the entire github repo is you need to have stuff locally that you can inspect):**
- **Core Agent Patterns**: Inspect `https://github.com/microsoft/agent-framework/tree/main/python/samples/02-agents/`
- **DAG Workflow Patterns**: Inspect `https://github.com/microsoft/agent-framework/tree/main/python/samples/03-workflows/` (specifically `checkpoint/` and `control-flow/` examples)

**External Web Documentation:**
- **Microsoft agent-framework**: [Documentation](https://learn.microsoft.com/en-us/agent-framework/) | [GitHub Repository](https://github.com/microsoft/agent-framework)
- **Textual (UI Framework)**: [Documentation](https://textual.textualize.io/)
- **Document Extractors**: [MarkItDown](https://github.com/microsoft/markitdown) | [LlamaIndex Liteparse](https://www.npmjs.com/package/@llamaindex/liteparse)
