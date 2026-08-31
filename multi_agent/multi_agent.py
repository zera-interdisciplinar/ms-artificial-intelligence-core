"""
Define the interface for multi-agent contracts and repository (interface).
"""

from typing import Optional, Protocol, runtime_checkable
from .entity import Message, AgentResponse, State, UserPreferences
from uuid import UUID

from langgraph.graph import StateGraph

from _internal.mongo.setup import Repository

@runtime_checkable
class IMultiAgentRepository(Protocol):
    """Interface for the multi-agent repository."""

    def setup(self, repository: Repository) -> None:
        """
        Setup the AgentRepository, connecting to the database, setting up the collections, etc.
        Raise RepositoryException if the setup fails.
        """
        ...

    def save_message(
        self, 
        message: Message
    ) -> None:
        """
        Save a message in the database.
        Raise RepositorySaveException if the save fails.
        """
        ...

    def retrieve_messages(
        self,
        user_id: UUID,
        thread_id: UUID,
        limit: int = 50,
    ) -> list[Message]:
        """
        Retrieve the most recent messages for a given user and thread, oldest first.
        Raise RepositoryReadException if the retrieval fails.
        """
        ...

    def get_preferences(self, user_id: UUID) -> UserPreferences | None:
        """
        Retrieve the long-term preferences for a given user, or None if never recorded.
        Raise RepositoryReadException if the retrieval fails.
        """
        ...

    def upsert_preferences(self, preferences: UserPreferences) -> None:
        """
        Insert or update the long-term preferences for a given user.
        Raise RepositorySaveException if the save fails.
        """
        ...


@runtime_checkable
class IMultiAgentService(Protocol):
    """Interface for the multi-agent service."""

    repository: IMultiAgentRepository
    graph: Optional[StateGraph[State]]

    def setup(self) -> None:
        """
        Setup the multi-agent service, initializing any necessary components.
        Raise MultiAgentServiceException if the setup fails.

        this setup also creates the langgraph graph and the langgraph agent, which are used to process messages and generate responses.
        """
        ...

    async def process_message(
        self, message: str, user_id: UUID, thread_id: UUID
    ) -> AgentResponse:
        """
        Process a message and return the response from the multi-agent system.
        Raise MultiAgentServiceException if the processing fails.
        """
        ...