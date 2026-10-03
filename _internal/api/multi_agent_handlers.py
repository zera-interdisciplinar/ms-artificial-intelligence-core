from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query
from multi_agent.exception import UnitMismatchException
from multi_agent.multi_agent import IMultiAgentService

from .dto import (
    ConversationListResponse,
    ConversationMessageResponse,
    ProcessMessageRequest,
    ProcessMessageResponse,
)

def multi_agent_handlers(service: IMultiAgentService) -> APIRouter:
    new_router = APIRouter(prefix="/multi-agent", tags=["multi-agent"])

    @new_router.post("/process-message")
    async def process_message_endpoint(
        request: ProcessMessageRequest, authorization: str = Header(...)
    ) -> ProcessMessageResponse:
        """
        Process a message through the multi-agent service. It takes a ProcessMessageRequest as
        input and returns the response from the multi-agent system.

        Answers 403 when unit_id is not the unit ms-administrative-core has for the user:
        the caller proposes the unit, the admin-core decides. The Authorization header is
        forwarded to ms-administrative-core as-is: authenticating the caller is not this
        service's responsibility.
        """

        try:
            response = await service.process_message(
                request.content, request.user_id, request.thread_id, request.unit_id, authorization
            )
        except UnitMismatchException:
            raise HTTPException(status_code=403, detail="unit_id does not belong to this user")
        return ProcessMessageResponse(**response.model_dump())

    @new_router.get("/conversations")
    async def list_conversations_endpoint(
        user_id: UUID = Query(...),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> ConversationListResponse:
        """
        A page of the user's conversations, most recently active first.
        preview is the first 40 characters of that thread's first message.
        """
        conversations = service.repository.list_conversations(user_id, page, page_size)
        return ConversationListResponse(**conversations.model_dump())

    @new_router.get("/conversations/{thread_id}")
    async def get_conversation_endpoint(
        thread_id: UUID,
        user_id: UUID = Query(...),
    ) -> list[ConversationMessageResponse]:
        """Every message exchanged in the thread, oldest first, scoped to the user."""
        messages = service.repository.retrieve_messages(user_id, thread_id, limit=None)
        return [
            ConversationMessageResponse(role=message.role, content=message.content, created_at=message.created_at)
            for message in messages
        ]

    return new_router
