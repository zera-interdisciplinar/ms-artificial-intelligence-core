from fastapi import APIRouter
from multi_agent.multi_agent import IMultiAgentService

from multi_agent.entity import Message

def multi_agent_handlers(service: IMultiAgentService) -> APIRouter:
    new_router = APIRouter(prefix="/multi-agent", tags=["multi-agent"])
    
    @new_router.post("/process-message")
    async def process_message_endpoint(message: Message):
        """
        Process a message through the multi-agent service. It takes a Message object as input and returns the response from the multi-agent system.
        """
        
        response = service.process_message(
            message.content, message.user_id, message.thread_id
        )
        return response
        
        
        
    
    
    return new_router