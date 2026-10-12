"""
Ports of the multi-agent core. The core depends only on these; adapters
(_internal/*, repository/*) implement them and app/api/composition.py wires them.
"""

from typing import Protocol, runtime_checkable
from .entity import ConversationPage, DisposalReport, Message, AgentResponse, UserPreferences
from uuid import UUID


@runtime_checkable
class IMultiAgentRepository(Protocol):
    """Interface for the multi-agent repository."""

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
        Save the stored PDF of one disposal. The first report saved for a disposal
        wins: a concurrent second save is a no-op, never an overwrite.
        Raise RepositorySaveException if the save fails.
        """
        ...

    def get_disposal_report(self, disposal_id: str) -> DisposalReport | None:
        """
        The stored report for this disposal, or None if it was never generated.
        Raise RepositoryReadException if the retrieval fails.
        """
        ...


class IUnitResolver(Protocol):
    """ms-administrative-core, the authority on which unit a user belongs to."""

    async def get_unit_id(self, user_id: UUID, authorization: str) -> UUID | None:
        """The user's unit, or None when the user cannot be resolved."""
        ...


class IStorageService(Protocol):
    """Persists file bytes to a storage provider and returns a public/shareable URL."""

    def upload(self, content: bytes, filename: str, content_type: str) -> str:
        """Upload the content and return the URL where it can be accessed."""
        ...


class IPdfRenderer(Protocol):
    """Renders HTML into PDF bytes."""

    def render(self, html: str) -> bytes:
        ...


@runtime_checkable
class IMultiAgentService(Protocol):
    """Interface for the multi-agent service."""

    def setup(self) -> None:
        """
        Build the agents and compile the langgraph graph.
        Raise MultiAgentServiceException if the setup fails.
        """
        ...

    async def process_message(
        self, message: str, user_id: UUID, thread_id: UUID, unit_id: UUID | None, authorization: str
    ) -> AgentResponse:
        """
        Process a message and return the response from the multi-agent system.
        unit_id is the unit the caller claims the user belongs to, validated against
        ms-administrative-core before anything else runs; None means "use the user's
        unit" (callers that only know who the user is, like the MCP facade).
        authorization is forwarded as-is to ms-administrative-core.
        Raise UnitMismatchException if the unit is not the user's or cannot be resolved.
        """
        ...

    async def create_disposal_report(self, user_id: UUID, disposal_id: str, authorization: str) -> str:
        """
        Generate and store the PDF for one disposal, or return the URL already stored.
        Raise UnitMismatchException if the user's unit cannot be resolved or the
        stored report belongs to another unit.
        """
        ...

    async def get_disposal_report(self, user_id: UUID, disposal_id: str, authorization: str) -> str | None:
        """The stored PDF URL for this disposal, or None if it was never generated or is another unit's.
        Raise UnitMismatchException if the user's unit cannot be resolved."""
        ...

    def list_conversations(self, user_id: UUID, page: int, page_size: int) -> ConversationPage:
        """One page of the user's conversations, most recently active first."""
        ...

    def get_conversation(self, user_id: UUID, thread_id: UUID) -> list[Message]:
        """Every message of the thread, oldest first, scoped to the user."""
        ...
