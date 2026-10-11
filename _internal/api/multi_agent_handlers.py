from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from multi_agent.exception import UnitMismatchException
from multi_agent.multi_agent import IMultiAgentService

from _internal.mcp.auth import user_id_from_authorization

from .dto import (
    ConversationListResponse,
    ConversationMessageResponse,
    DisposalReportRequest,
    DisposalReportResponse,
    ProcessMessageRequest,
    ProcessMessageResponse,
)


def caller_user_id(authorization: str = Header(...)) -> UUID:
    """
    The caller, read from the Bearer that Kong already validated. Never taken from the
    body or the query: that would let any logged-in user act as someone else.
    """
    try:
        return user_id_from_authorization(authorization)
    except ValueError:
        raise HTTPException(status_code=401, detail="invalid bearer token")


def multi_agent_handlers(service: IMultiAgentService) -> APIRouter:
    new_router = APIRouter(prefix="/multi-agent", tags=["multi-agent"])

    @new_router.post("/process-message")
    async def process_message_endpoint(
        request: ProcessMessageRequest,
        user_id: UUID = Depends(caller_user_id),
        authorization: str = Header(...),
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
                request.content, user_id, request.thread_id, request.unit_id, authorization
            )
        except UnitMismatchException:
            raise HTTPException(status_code=403, detail="unit_id does not belong to this user")
        return ProcessMessageResponse(**response.model_dump())

    @new_router.get("/conversations")
    def list_conversations_endpoint(
        user_id: UUID = Depends(caller_user_id),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=20, ge=1, le=100),
    ) -> ConversationListResponse:
        """
        A page of the caller's conversations, most recently active first.
        preview is the first 40 characters of that thread's first message.
        """
        conversations = service.list_conversations(user_id, page, page_size)
        return ConversationListResponse(**conversations.model_dump())

    @new_router.get("/conversations/{thread_id}")
    def get_conversation_endpoint(
        thread_id: UUID,
        user_id: UUID = Depends(caller_user_id),
    ) -> list[ConversationMessageResponse]:
        """Every message exchanged in the thread, oldest first, scoped to the caller."""
        messages = service.get_conversation(user_id, thread_id)
        return [
            ConversationMessageResponse(role=message.role, content=message.content, created_at=message.created_at)
            for message in messages
        ]

    return new_router


def report_handlers(service: IMultiAgentService) -> APIRouter:
    new_router = APIRouter(prefix="/reports", tags=["reports"])

    @new_router.post("")
    async def create_disposal_report_endpoint(
        request: DisposalReportRequest,
        user_id: UUID = Depends(caller_user_id),
        authorization: str = Header(...),
    ) -> DisposalReportResponse:
        """Generate the PDF for a disposal, or return the URL already stored for that id.
        403 when the user's unit cannot be resolved or the disposal is another unit's."""
        try:
            report_url = await service.create_disposal_report(user_id, request.disposal_id, authorization)
        except UnitMismatchException:
            raise HTTPException(status_code=403, detail="disposal does not belong to this user's unit")
        return DisposalReportResponse(report_url=report_url)

    @new_router.get("/{disposal_id}")
    async def get_disposal_report_endpoint(
        disposal_id: str,
        user_id: UUID = Depends(caller_user_id),
        authorization: str = Header(...),
    ) -> DisposalReportResponse:
        """The stored PDF URL for this disposal; 404 also when it is another unit's."""
        try:
            report_url = await service.get_disposal_report(user_id, disposal_id, authorization)
        except UnitMismatchException:
            raise HTTPException(status_code=403, detail="the user's unit cannot be resolved")
        if report_url is None:
            raise HTTPException(status_code=404, detail="disposal report not found")
        return DisposalReportResponse(report_url=report_url)

    return new_router
