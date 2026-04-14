from engine.sdk import AgentBuilder, SubAgentConfig
from tools import WORKSPACE_TOOLS
from prompts import ORCHESTRATOR_INSTRUCTIONS, SUBAGENT_INSTRUCTIONS
import config

# 1. Define Sub-Agents (Optional)
researcher = SubAgentConfig(
    name="Researcher",
    instructions=SUBAGENT_INSTRUCTIONS,
    tools=WORKSPACE_TOOLS
)

# 2. Assemble Main Agent
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
