"""
ACL for the external MCP facade.
The method does not know about tools. It receives an already identified caller
and runs the same graph the app uses.


The ACL shell was made to be a simple adapter in case of needing to change the provider. This will be probably used in future when scaling the service.
"""

from uuid import UUID

from multi_agent.entity import AgentResponse
from multi_agent.multi_agent import IMultiAgentService


async def acl_process_message(
    service: IMultiAgentService,
    content: str,
    thread_id: UUID,
    user_id: UUID,
    authorization: str,
) -> AgentResponse:
    """Call process_message. The facade only knows the user; the unit is the one
    ms-administrative-core has for them (unit_id=None)."""

    return await service.process_message(content, user_id, thread_id, None, authorization)
