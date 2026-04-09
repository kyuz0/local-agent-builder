# Agent Prompting Guidelines

When building agents using the `basic-tui-agent` scaffold and the Microsoft Agent Framework, you MUST structure your prompts to maximize tool execution reliability and strictly bound LLM context rot. 

Always adhere to the following architecture seen in optimal blueprints (like `local-research`):

## 1. Domain Segregation (Orchestrator vs Sub-Agent)
Never build a monolithic "god prompt". Split instructions by domain:
- **`ORCHESTRATOR_INSTRUCTIONS`**: The top-level agent prompt. Focus entirely on *planning*, *delegation*, and managing global state via tools (like `write_todos`).
- **`SUBAGENT_INSTRUCTIONS`**: The isolated worker prompt. Focus strictly on *execution* and *extraction* (e.g., searching, grepping, calculating).
- **`SUBAGENT_DELEGATION_INSTRUCTIONS`**: A highly strategic subset of instructions injected into the Orchestrator explaining *when* and *how* to use its `delegate_task` tool. Tell the orchestrator exactly what to pass into the sub-agent and how to parallelize requests.

## 2. Dynamic Quota Injection
Agent tool schemas define what a tool *does*, but prompts define *when to stop using it*. Always use Python's `.format()` to inject active quotas directly into the prompt on initialization:

```python
# BAD: Hardcoded limits
"You can search the web 5 times."

# GOOD: Injected dynamically
SUBAGENT_INSTRUCTIONS = "... \nYou have {search_quota} searches maximum. \n..."
client.as_agent(instructions=SUBAGENT_INSTRUCTIONS.format(search_quota=5), ...)
```

If an agent has `N` active quotas in its execution loop, all `N` must be visibly documented in its instructions so it can strategize its remaining bandwidth.

## 3. Strict `<Hard Limits>` Semantic Tagging
The Microsoft Agent Framework relies on iterative tool execution loops. You must explicitly teach the LLM to yield control (Stop Early) rather than burning tokens in endless recursive calls. Define a `<Hard Limits>` XML block:

```markdown
<Hard Limits>
**Quota Exhaustion**:
If a tool returns a quota reached error, you MUST IMMEDIATELY STOP using it. 
Summarize what you have so far and yield to the user.

**Stop Early**:
Do not maximize your quotas. Stop immediately when:
1. You have sufficient information to answer the core query.
2. The last 2 searches returned highly redundant data.
</Hard Limits>
```

## 4. Forced Reflexion (`think_tool`)
Always inject a lightweight `think_tool(reflection: str)` into your generic sub-agents and explicitly mandate its usage after heavy operations.
```markdown
<Show Your Thinking>
After reading a massive file or making a web search, use `think_tool` to analyze the payload:
- What did I just find?
- What is still missing?
- Can I answer the question now?
</Show Your Thinking>
```
This inserts a structural pause into the LLM's autoregressive generation loop, sharply improving downstream tool parameters and reducing hallucinations on large chunks of retrieved data.

## 5. Anti-Looping Traps (CRITICAL for Local LLMs)
Small local LLMs (under 32B parameters) possess notoriously weak state-tracking capabilities. If they use a tool (like `write_todos` or `think_tool`) and it succeeds without drastically altering the semantic context, their attention mechanisms will heavily weight the exact same tokens and repeat the identical tool call infinitely. 

You MUST inject a strict anti-looping directive into the Orchestrator and every Sub-Agent's system prompt:

```markdown
<Anti-Looping>
NEVER call the exact same tool with the exact same arguments consecutively. 
If you just used `write_todos` to track your plan, DO NOT call it again in the next step. You must forcefully execute the next logical step in your plan (e.g., delegate the task, read a file, or write a report).
If you find yourself caught in a loop, immediately summarize your findings and stop.
</Anti-Looping>
```

## 6. String Interpolation Safety (Python Runtime Trap)
When giving generic instructions or placeholders within a prompt, **NEVER** use single braces `{}` (e.g. `{run_folder}`) unless that variable is explicitly passed to Python's `.format()` method during agent initialization in `chat.py`. 
If you generate a bare `{placeholder}` in a Python system prompt string and the scaffold calls `.format(date=current_date)`, Python will throw a fatal `KeyError` and crash the application instantly. 
To safely write structural placeholders in prompt templates, use double-braces `{{placeholder}}` or angle brackets `<placeholder>`.
