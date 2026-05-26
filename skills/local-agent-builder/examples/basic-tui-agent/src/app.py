import warnings
warnings.filterwarnings("ignore", message=".*is experimental and may change.*")

from engine.sdk import AgentBuilder, SubAgentConfig
from tools import (
    WORKSPACE_TOOLS,
    read_workspace_file,
    write_workspace_file,
    list_workspace_files,
    grep_workspace_file,
    fetch_url_to_workspace,
    web_search,
    write_todos,
    read_todos,
    think_tool,
)
from prompts import ORCHESTRATOR_INSTRUCTIONS, SUBAGENT_INSTRUCTIONS
import config

# 1. Define Sub-Agents (Optional)
# NOTE: Do NOT pre-format instructions here (e.g. SUBAGENT_INSTRUCTIONS.format(...)).
# The engine formats runtime variables like {date} or {task_name} dynamically at runtime.
#
# TOOL ASSIGNMENT: Use WORKSPACE_TOOLS if the agent needs all tools.
# For selective tools (e.g. withholding web_search from an analyzer), import
# individual tools above and pass an explicit list: tools=[read_workspace_file, grep_workspace_file]
researcher = SubAgentConfig(
    name="Researcher",
    instructions=SUBAGENT_INSTRUCTIONS,
    tools=WORKSPACE_TOOLS
)

# 2. Assemble Main Agent
# NOTE: Do NOT pre-format instructions here (e.g. ORCHESTRATOR_INSTRUCTIONS.format(...)).
# The engine handles formatting dynamically at runtime.
app = AgentBuilder(
    name=config.APP_TITLE,
    description=config.APP_DESCRIPTION,
    instructions=ORCHESTRATOR_INSTRUCTIONS,
    tools=WORKSPACE_TOOLS,
    sub_agents=[researcher]
)

def cli_main():
    app.start()

if __name__ == "__main__":
    cli_main()
