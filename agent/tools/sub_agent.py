
from typing import Literal

from langchain_core.tools import tool

type AgentName = Literal[
    "resume_advice",
    "interview_prepare"
]

type Prompt = str

type AgentResponse = dict[AgentName, list[Prompt]]

type AgentCall = dict[AgentName, list[Prompt]]

@tool
async def call_sub_agents(agent_calls: AgentCall) -> AgentResponse:
    """
    Calls the specified sub-agents with the given prompts and returns their responses.
    Args:
        agent_calls: A dictionary where keys are agent names and values are lists of prompts to be sent to the respective agents.
    Returns:
        AgentResponse: A dictionary where keys are agent names and values are lists of responses from the respective agents.

    Notes:
        You can call multiple sub-agents in a single call by including multiple entries in the `agent_calls` dictionary. Each entry should specify the agent name and the corresponding prompts to be sent to that agent.
        Here are two different agents you can call:
        1. "resume_advice": This agent provides advice on how to improve a resume. 
        2. "interview_prepare": This agent provides advice on how to prepare for job interviews, including common questions and tips for answering them.
    Example:
        agent_calls = {
            "resume_advice": [
                "Make advice on how to improve user's resume.",
                "What are some common mistakes to avoid in a resume?"
            ],
            "interview_prepare": [
                "Provide tips on how to prepare for a job interview.",
                "Prepare a list of common interview questions and how to answer them."
            ]
        }
    
    """
    pass

__all__ = [
    call_sub_agents,
    AgentName,
    Prompt,
    AgentResponse,
    AgentCall
]