# Sasori Mailbox Daemon Pattern

When building an agentic workflow that needs to be accessed via email, you must strictly implement the **Sasori** plugin pattern. 

**Rule: Do NOT add IMAP/SMTP logic to `app.py`. Email processing MUST be delegated to the global Sasori daemon.**

This is an optional **Stage 2 Add-on**. You must instruct the user to install `packages/sasori` globally via `pipx`.

## The Sasori Architecture
The Sasori Daemon runs infinitely in the background, handling email requests for your local agents. It prevents VRAM starvation by queueing inbound jobs and managing concurrency limits (`MAX_CONCURRENT_AGENTS=1`).

1. **One Inbox:** The daemon polls the IMAP server.
2. **Handlers Directory:** The daemon dynamically loads plugins from the user's `~/.sasori/handlers/` directory.
3. **Routing & Queue:** Incoming emails matching a plugin's `agent_tag` (using case-insensitive `startswith()`) are appended to the SQLite backend as `QUEUED`. 
4. **Execution:** The daemon drains the queue up to the concurrency limit, piping agent `stdout` natively into text files on disk (`/tmp/thread_{id}.out`).

## The `STATUS` and `STOP` Intercepts
Sasori handles operational control automatically without touching the agent code:
- **Global `STATUS`**: A user emailing "STATUS" with no thread tag will receive a list of all `RUNNING` agents.
- **Thread `STATUS`**: Replying "STATUS" inside a thread dynamically reads the tail of `/tmp/thread_{id}.out` and replies with elapsed runtime and logs.
- **`STOP`**: Sends `SIGTERM` to the mapped Linux Process ID and drops the thread to `STOPPED`.

## Writing a Plugin (Your Role)

When the user requests email support, write a standard Python file structured like this:

```python
from sasori.handler import BaseMailboxHandler
import re

class MyAgentHandler(BaseMailboxHandler):
    # The prefix (case-insensitive) the daemon will look for
    agent_tag = "[my-agent]" 
    # The pipx installed CLI executable
    agent_command = "my-agent"

    def process_result(self, thread_id: str, stdout_file: str, original_body: str) -> tuple[str, list]:
        """
        By default, this method reads `stdout_file` and returns it as a string with no attachments.
        If your agent generates a file, override this to parse the file output dynamically!
        """
        reply_text, attachments = super().process_result(thread_id, stdout_file, original_body)
        
        # Example override: Extracting PDF paths to attach them
        match = re.search(r'REPORT_SAVED:\s*(/.+pdf)', reply_text)
        if match:
             attachments.append(match.group(1).strip())
             reply_text = reply_text.replace(match.group(0), "See attached report.")
        
        return reply_text, attachments

# You MUST expose the array below for the dynamic loader!
HANDLERS = [MyAgentHandler()]
```

Instruct the user to save this file into `~/.sasori/handlers/my_agent_plugin.py` and restart Sasori.
