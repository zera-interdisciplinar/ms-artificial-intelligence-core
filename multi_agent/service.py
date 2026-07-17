from typing import Protocol, runtime_checkable

from multi_agent.multi_agent import IMultiAgentRepository, IMultiAgentService
from langchain_google_genai import ChatGoogleGenerativeAI
from .entity import Message, AgentResponse, State
from uuid import UUID

from langgraph.graph import StateGraph, START, END
from langgraph.graph.state import CompiledStateGraph

from config.environments import Environments
from logger.logger import logger

class MultiAgentService(IMultiAgentService):
    """Concrete implementation of the multi-agent service."""

    graph: StateGraph[State]
    __app: CompiledStateGraph[State]

    def __init__(self, repository: IMultiAgentRepository, envs: Environments, logger: logger):
        self.repository = repository
        self.envs = envs
        self.logger = logger

    def setup(self, repository: IMultiAgentRepository) -> None:
        """
        Setup the MultiAgentService with the provided repository.
        """
        self.logger.Info("Setting up the multi-agent service")

        # initializes the model
        self.logger.Info("initializing the gemini llm")
        llm_gemini = ChatGoogleGenerativeAI(
            model = "gemini-2.5-flash",
            temperature = 0.2,
            top_p = 0.9,
            google_api_key = self.envs.GEMINI_API_KEY,
        )

        # initializes the system agents
        

        

