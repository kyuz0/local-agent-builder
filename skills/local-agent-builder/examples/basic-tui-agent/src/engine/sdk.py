from typing import List, Callable, Optional
from pydantic import BaseModel, Field

class SubAgentConfig(BaseModel):
    name: str = Field(..., description="Name of the subagent without spaces")
    instructions: str = Field(..., description="Instructions for the subagent. Use {date} and {task_name} placeholders.")
    tools: List[Callable] = Field(default_factory=list, description="List of tool functions for the subagent")

class AgentBuilder:
    def __init__(self, name: str, description: str, instructions: str, tools: List[Callable], sub_agents: Optional[List[SubAgentConfig]] = None):
        self.name = name
        self.description = description
        self.instructions = instructions
        self.tools = tools
        self.sub_agents = sub_agents or []
        
    def start(self):
        from engine.tui import cli_main
        cli_main(self)
