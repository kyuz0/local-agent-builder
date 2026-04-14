# Running Shell Commands Securely

Giving autonomous agents access to the local shell introduces security risks. The `local-agent-builder` scaffold ships with an optional, highly constrained `run_shell_command` tool located in `src/tools/shell.py`.

## 1. Using the Shell Tool
Most agents will not need shell access. The tool is loaded by default in `WORKSPACE_TOOLS` inside `examples/basic-tui-agent/src/tools/__init__.py`. 

**CRITICAL RULE:** Unless the user explicitly asks for an agent to run bash, python subprocesses, or compile code, you **MUST** explicitly remove `run_shell_command` from the `WORKSPACE_TOOLS` array. 

### Approval Mode Constraint
The `run_shell_command` is deliberately hardcoded with `@tool(approval_mode="always_require")`. Even if included, it will securely prompt the user for human-in-the-loop (HITL) approval via the UI before actually executing. Do not change this unless requested.

## 2. Sandboxing (Anthropic SRT)
If the agent must securely execute scripts or compilers, the scaffold natively integrates **Anthropic SRT** (Sandbox Runtime) isolation. 

You must securely configure the sandbox limits inside the user's `config.yaml` to ensure the agent uses OS-level compartmentalisation.

```yaml
settings:
  shell:
    enabled: true                  # Prevents the tool from early terminating with an error
    sandbox:
      enabled: true                # Wraps command in `srt` binary
      env_whitelist:               # Scraps host environment keys out of the sub-process
        - "PATH"
        - "HOME"
        - "USER"
      network_domains: ["*"]       # Specific allowed domains. Use ["*"] to allow all outbound traffic. Empty [] means airgapped!
      deny_workspace_patterns:     # Explicitly blocks read/write access using exact matches from the workspace root
        - "**/*.env"
        - "**/*.secret"
```

### Caveats and Constraints
1. **OS Constraints**: Anthropic SRT runs natively over Linux (`bwrap`) and macOS (`sandbox-exec`). **It does not support Windows**. If you are on Windows, you must disable the sandbox.
2. **Dependency**: If `sandbox: enabled: true`, the host machine must have the `srt` executable installed and globally accessible via `$PATH`. 
3. **Network Airgapped By Default**: The `network_domains` array strictly defaults to an airgap. If you require outbound internet connectivity (e.g., pulling from `npm` or `pip`), you must explicitly populate specific domains or use `["*"]` to unrestrict it entirely.
4. **Deny Path Logic**: The `deny_workspace_patterns` executes Python's `rglob` inside the workspace root dynamically, converting the blocked extensions into hard absolute paths that Anthropic SRT can explicitly forbid via `denyRead` and `denyWrite` flags.
