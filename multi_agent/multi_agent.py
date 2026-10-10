"""
Define the interface for multi-agent contracts and repository (interface).
"""

from typing import Optional, Protocol, runtime_checkable
from .entity import ConversationPage, DisposalReport, Message, AgentResponse, State, UserPreferences
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
        limit: int | None = 50,
    ) -> list[Message]:
        """
        Retrieve messages for a given user and thread, oldest first.
        limit caps how many of the most recent messages come back; None returns all of them.
        Raise RepositoryReadException if the retrieval fails.
        """
        ...

    def list_conversations(
        self,
        user_id: UUID,
        page: int = 1,
        page_size: int = 20,
    ) -> ConversationPage:
        """
        One page of a user's threads, newest activity first.
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

    def save_disposal_report(self, report: DisposalReport) -> None:
        """
        Save the stored PDF of one disposal.
        Raise RepositorySaveException if the save fails.
        """
        ...

    def get_disposal_report(self, disposal_id: str) -> DisposalReport | None:
        """
        The stored report for this disposal, or None if it was never generated.
        Raise RepositoryReadException if the retrieval fails.
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
        self, message: str, user_id: UUID, thread_id: UUID, unit_id: UUID, authorization: str
    ) -> AgentResponse:
        """
        Process a message and return the response from the multi-agent system.
        unit_id is the unit the caller claims the user belongs to; it is validated
        against ms-administrative-core before anything else runs. authorization is
        the caller's Authorization header, forwarded as-is to ms-administrative-core --
        this service never authenticates on the caller's behalf.
        Raise MultiAgentServiceException if the processing fails.
        Raise UnitMismatchException if unit_id is not the user's unit.
        """
        ...

    async def create_disposal_report(self, user_id: UUID, disposal_id: str, authorization: str) -> str:
        """
        Generate and store the PDF for one disposal, or return the URL already stored.
        authorization is the caller's Authorization header, forwarded to resolve the
        user's unit before get_disposal_report runs.
        Raise MultiAgentServiceException if generation or upload fails.
        Raise UnitMismatchException if the user's unit cannot be resolved.
        """
        ...

    def get_disposal_report(self, disposal_id: str) -> str | None:
        """The stored PDF URL for this disposal, or None if it was never generated."""
        ...