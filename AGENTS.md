# Repository Development Guidelines

This file provides system context for coding assistants tasked with modifying or extending *this* repository (the `local-agent-builder` skill).

## Project Purpose
This repository provides the core template, constraints, and documentation for a Skill that *other* coding agents use to build local AI workflows. Your task, when editing this codebase, is to maintain the simplicity and efficiency of these scaffolding blueprints.

## Technical Scope & Constraints
When making changes to the source code, examples, or documentation within this repository, keep in mind:

1. **Hardware & Model Targets**: All templates and workflows must take into account that they need to run on consumer hardware meaning context needs to be as small as feasible and instructions direct and simple (e.g., AMD Strix Halo, AMD Radeon 7900).
2. **Simplicity First**: Avoid over-engineering. If adding utilities or tools to the scaffold, ensure they do not bloat the template unnecessarily.

## Repository Structure & Editing Guidelines

When modifying this project, keep the following scope in mind for each core component:

- **`skills/agent_tui_scaffolder/SKILL.md`**: The primary entry point loaded by end-user coding agents. When adding new capabilities or major rules to the scaffold, update this file so the external agent is aware of them. Keep instructions terse.
- **`skills/agent_tui_scaffolder/resources/docs/`**: The system rulebooks (e.g., `IMPLEMENTATION.md`, `ARCHITECTURE.md`). Update these if you change the scaffold architecture or add new operational patterns.
- **`skills/agent_tui_scaffolder/examples/basic-tui-agent/`**: The core application scaffold that gets copied by the end-user agent. If you modify the baseline loop, tools, or configuration logic (`chat.py`, `tools/`, `config.py`), ensure the changes preserve efficiency for local consumer hardware (7B-32B models).

*Note: The specific guidelines for how the generated local agents should behave are defined in `SKILL.md` and the `docs/` folder.*
