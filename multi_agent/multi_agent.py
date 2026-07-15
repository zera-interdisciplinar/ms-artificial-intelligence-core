"""
Define the interface for multi-agent contracts and repository (interface).
"""

from typing import Protocol, runtime_checkable
from .entity import Message, AgentResponse
from uuid import UUID

@runtime_checkable
class IMultiAgentRepository(Protocol):
    """Interface for the multi-agent repository."""

    def setup(self) -> None:
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
    ) -> list[Message]:
        """
        Retrieve messages from the database for a given user and thread.
        Raise RepositoryReadException if the retrieval fails.
        """
        ...

    def remove_thread(self, user_id: UUID, thread_id: UUID) -> None:
        """
        Remove a thread and all its messages from the database for a given user and thread.
        Raise RepositoryDeleteException if the removal fails.
        """
        ...


@runtime_checkable
class IMultiAgentService(Protocol):
    """Interface for the multi-agent service."""

    def process_message(
        self, message: str, user_id: UUID, thread_id: UUID
    ) -> AgentResponse:
        """
        Process a message and return the response from the multi-agent system.
        Raise MultiAgentServiceException if the processing fails.
        """
        ...