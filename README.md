# Local Agent Builder

The aim of this project is to provide a boilerplate *Skill* that developers can plug into coding assistants (like OpenCode) to generate agentic workflows. It uses the Microsoft [agent-framework](https://github.com/microsoft/agent-framework) library and provides a functional Terminal User Interface (TUI) as the baseline scaffold. When working with resource-constrained local models, auto-generated agents often lack the architecture to isolate context, impose loop limitations, and handle file reading efficiently.

This project provides a template that includes quotas, contextual boundaries, and sub-agent delegation functionality to help generated agents execute within the bounds of local hardware.

## Tooling & Verification
This skill is designed to help **Local AI Coding Agents** build **Local Agent Workflows**.

- **Scaffolding LLM Compatibility**: Tested via OpenCode utilizing the **Qwen 3.5 (122B)** model to comprehend the skill rules and construct applications using the `basic-tui-agent` scaffold.
- **Agent Workflow LLM Compatibility**: The generated agents and workflows have been validated running locally on the **Qwen 3.5** model family.
- **Hardware Profile**: Tested on local consumer hardware, specifically AMD Ryzen AI HX 370 (Strix Halo) and AMD Ryzen 9 7900 systems.

## Getting Started

If you are using a coding agent like OpenCode, place this repository folder into your active skills directory (e.g., `~/.opencode/skills/`). Following the embedded `SKILL.md` rules, the coding agent will know how to bootstrap and template your local agent applications using Microsoft's Agent-Framework.

### Repository Structure
- `SKILL.md`: The primary directive file loaded by the coding assistant.
- `resources/docs/`: The architectural rulebooks outlining context isolation, UI constraints, and LLM prompt engineering strategies for local execution.
- `examples/basic-tui-agent/`: The read-only baseline scaffold that coding assistants copy when beginning a new local agent project.

Read the built-in [AGENTS.md](./AGENTS.md) for more details regarding how the specific execution loops were designed to navigate hardware limits.
