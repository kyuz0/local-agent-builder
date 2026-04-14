import tempfile
import json
import uuid
import os
import subprocess
from pathlib import Path
import config
from agent_framework import tool

@tool
def run_shell_command(command: str, cwd: str = ".") -> str:
    """Execute a bash command on the host securely. Provide a string 'command' and optionally 'cwd' (current working directory).
    Always use this tool when you need to run compilation, python execution, or read advanced system states."""
    
    shell_cfg = config.cfg.get("settings", {}).get("shell", {})
    target_cwd = os.path.abspath(cwd)
    if not os.path.exists(target_cwd):
        return f"Error: The working directory '{target_cwd}' does not exist."

    sandbox_cfg = shell_cfg.get("sandbox", {})
    if not sandbox_cfg.get("enabled", False):
        print(f"\n\033[93m[WARNING] Executing shell command without SRT sandbox: {command}\033[0m\n")
        try:
            result = subprocess.run(["bash", "-c", command], cwd=target_cwd, capture_output=True, text=True, timeout=120)
            return f"Exit code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
        except subprocess.TimeoutExpired:
            return "Error: Command timed out after 120 seconds."
        except Exception as e:
            return f"Error executing command: {e}"

    # Anthropic SRT Sandbox Logic
    network_domains = sandbox_cfg.get("network_domains", [])
    network_block = {
        "allowedDomains": network_domains if network_domains else ["sandbox.local"],
        "deniedDomains": []
    }

    env_whitelist = sandbox_cfg.get("env_whitelist", ["PATH", "HOME", "TERM", "LANG", "USER", "SHELL", "TMPDIR", "TMP"])
    safe_env = {k: os.environ[k] for k in env_whitelist if k in os.environ}

    deny_workspace_patterns = sandbox_cfg.get("deny_workspace_patterns", [])
    deny_write = []
    deny_read = [os.path.expanduser("~")]
    
    for pattern in deny_workspace_patterns:
        # Match using rglob directly in the workspace root
        for match in Path(target_cwd).rglob(pattern):
            deny_write.append(str(match.absolute()))
            deny_read.append(str(match.absolute()))

    home = os.path.expanduser("~")
    allow_read = [
        target_cwd,
        "/tmp",
        os.path.join(home, ".bun"),
        os.path.join(home, ".npm"),
        os.path.join(home, ".cargo"),
        os.path.join(home, ".nvm"),
        os.path.join(home, ".local", "share", "uv"),
        os.path.join(home, ".vscode-server")
    ]
    allow_read = [p for p in allow_read if os.path.exists(p)]

    srt_config = {
        "network": network_block,
        "filesystem": {
            "denyRead": deny_read,
            "allowRead": allow_read,
            "allowWrite": [target_cwd, "/tmp"],
            "denyWrite": deny_write
        }
    }
    
    settings_file = os.path.join(tempfile.gettempdir(), f"srt-settings-{uuid.uuid4().hex[:8]}.json")
    try:
        with open(settings_file, "w") as f:
            json.dump(srt_config, f)
            
        args = ["srt", "--settings", settings_file, "bash", "-c", command]
        result = subprocess.run(args, cwd=target_cwd, env=safe_env, capture_output=True, text=True, timeout=120)
        return f"Exit code: {result.returncode}\nStdout:\n{result.stdout}\nStderr:\n{result.stderr}"
    except subprocess.TimeoutExpired:
        return "Error: Command timed out after 120 seconds."
    except Exception as e:
        return f"Error executing sandboxed command: {str(e)}\n\n(Did you install 'srt'? Ensure it's in your PATH)."
    finally:
        try:
            os.remove(settings_file)
        except OSError:
            pass
