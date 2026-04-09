# Template Agent Scaffolding

> **AGENT DIRECTIVE**: This `README.md` is a living template. As you build features on top of this scaffolding package, you MUST update this file to document your exact technical stack, execution steps, and custom prompt injection tools.

This repository is built using the **Microsoft Agent Framework** and the **Textual** TUI library, configured by default to target local, un-authenticated OpenAI-compatible servers (e.g. `llama.cpp` hosted on `http://localhost:8080/v1`).

## Setup Instructions

1. **Create the Environment & Install**
   ```bash
   python -m venv venv
   source venv/bin/activate
   pip install -e .
   ```

   **System-Wide Installation (Optional):**
   To install the agent as a standalone, system-wide terminal command:
   ```bash
   pipx install .
   ```

2. **Configure Endpoints**
   By default, the application uses an OpenAI compatible API on localhost:8080 (such as llama-server from llama.cpp). If you wish to use alternative APIs, create a `.env` file containing:
   ```env
   OPENAI_API_BASE=http://localhost:8080/v1
   OPENAI_API_KEY=dummy
   OPENAI_MODEL=local-model
   ```

3. **Run the TUI**
   ```bash
   python src/main.py
   ```

## Included Tooling (Update As Developed)
- **Unified Workspace FS (`fs`)**: A `pyfilesystem2` boundary for safely executing I/O loops without leaving rogue files on your disk.
- **URL Fetching**: A strict `BeautifulSoup` integration passing filtered Markdown back to the agent instead of massive DOM trees to save context.
