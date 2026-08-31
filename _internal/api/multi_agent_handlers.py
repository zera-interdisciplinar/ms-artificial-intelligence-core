from fastapi import APIRouter
from multi_agent.multi_agent import IMultiAgentService

from .dto import ProcessMessageRequest, ProcessMessageResponse

def multi_agent_handlers(service: IMultiAgentService) -> APIRouter:
    new_router = APIRouter(prefix="/multi-agent", tags=["multi-agent"])

    @new_router.post("/process-message")
    async def process_message_endpoint(request: ProcessMessageRequest) -> ProcessMessageResponse:
        """
        Process a message through the multi-agent service. It takes a ProcessMessageRequest as
        input and returns the response from the multi-agent system.
        """

        response = await service.process_message(
            request.content, request.user_id, request.thread_id
        )
        return ProcessMessageResponse(**response.model_dump())

    return new_router
