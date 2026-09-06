from fastapi import APIRouter, Header, HTTPException
from multi_agent.exception import UnitMismatchException
from multi_agent.multi_agent import IMultiAgentService

from .dto import ProcessMessageRequest, ProcessMessageResponse

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

    return new_router
