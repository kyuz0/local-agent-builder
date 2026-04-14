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
   python src/app.py
   ```

4. **CLI & Headless Mode**
   You can run the agent headlessly to process background tasks or scripts:
   ```bash
   python src/app.py --prompt "Analyze the provided log files."
   ```
   **Useful Flags**:
   - `--auto-approve`: Bypasses all visual Human-In-The-Loop tool safeguards, allowing tasks to run fully unattended.
   - `--list-sessions`: Prints out your previously saved interaction histories.
   - `--resume <session_id>`: Restores a previous context state. Functions interactively by booting into the TUI, or headlessly if appended alongside a `--prompt`.

## Included Tooling (Update As Developed)
- **Unified Workspace FS (`fs`)**: A `pyfilesystem2` boundary for safely executing I/O loops without leaving rogue files on your disk.
- **URL Fetching**: A strict `BeautifulSoup` integration passing filtered Markdown back to the agent instead of massive DOM trees to save context.

## Security & Permissions

This scaffold utilizes a dynamic configuration framework that automatically builds your `config.yaml` inside your active user directory (e.g., `~/.basic-tui-agent/config.yaml` or similar).

### 1. Human-in-The-Loop Tool Approvals
By default, the Agent requires explicit human authorization before executing potentially destructive capabilities. You can toggle interdictions for specific Python functions by assigning them within the `permissions` block:
```yaml
settings:
  permissions:
    run_shell_command: require_approval
    remove_workspace_file: require_approval
```
> *(When running in CI pipelines or headlessly with `--auto-approve`, these visual intercept panels are bypassed!)*

### 2. SRT Subprocess Sandboxing
To protect your host OS when delegating terminal execution, the scaffold ships with integrated SRT (Simple Runtime Isolation) configurations specifically built for the Shell bindings:
```yaml
settings:
  shell:
    sandbox:
      enabled: true              # Wrap spawned Popen targets with isolation layers
      env_whitelist:             # Provide the strictly available environment context
        - "PATH"
        - "HOME"
        - "TERM"
      network_domains:           # Strict egress firewall. Leaving this array EMPTY completely AIRGAPS the task!
        - "github.com"           # Allow git clone operations
        - "pypi.org"             # Allow pip installations
      deny_workspace_patterns:   # Inject absolute glob boundaries to shield sensitive trees from analysis
        - "**/*.env"
        - "**/*_rsa"
```
