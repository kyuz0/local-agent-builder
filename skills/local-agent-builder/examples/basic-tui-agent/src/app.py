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
#
# DELEGATION CHAIN: Use sub_agents=[] on SubAgentConfig to control which children
# each agent can delegate to. Only agents with sub_agents get the delegate_tasks tool.
# Example for a 3-tier chain (Orchestrator -> Searcher -> Analyzer):
#
#   analyzer = SubAgentConfig(name="Analyzer", instructions=ANALYZER_INSTRUCTIONS,
#       tools=[read_workspace_file, grep_workspace_file, think_tool])  # leaf: no sub_agents
#
#   searcher = SubAgentConfig(name="Searcher", instructions=SEARCHER_INSTRUCTIONS,
#       tools=[web_search, fetch_url_to_workspace, think_tool],
#       sub_agents=[analyzer])  # can only delegate to Analyzer
#
#   app = AgentBuilder(..., sub_agents=[searcher])  # orchestrator can only delegate to Searcher
#
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
