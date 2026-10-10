"""
Application entrypoint for the MCP External Partner service.
The goal here is to provide a MCP server that can be used by external partners to interact with the Zera platform.

It has it's own http logic and only uses the multi_agent service in commum to the api.
"""

from _internal.admin_core.client import AdminCoreClient
from app.api.main import pdf_renderer
from logger.logger import Logger
from config.environments import Environments
from _internal.mongo.setup import Repository
from multi_agent.multi_agent import IMultiAgentRepository, MultiAgentRepository
from multi_agent.service import IMultiAgentService, MultiAgentService
from _internal.mcp.server import build_mcp

myLogger = Logger()
myLogger.Info("Booting up mcp-external-partner service")

envs = Environments()

# Open a new connection to the MongoDB database using the environment variables
repository = Repository(envs)

# create the admin core client instance
admin_core_client = AdminCoreClient(envs, myLogger)

# create the MultiAgentRepository instance
multi_agent_repository: IMultiAgentRepository = MultiAgentRepository()
multi_agent_repository.setup(envs)

myLogger.Info("MultiAgentRepository setup complete")

# create the MultiAgentService instance
multi_agent_service: IMultiAgentService = MultiAgentService(
    repository=multi_agent_repository,
    envs=envs,
    logger=myLogger,
    pdf_renderer=pdf_renderer,
    admin_core=admin_core_client,
    # we do not need the storage service here because our mcp flow didnt use that
)
multi_agent_service.setup()

myLogger.Info("MultiAgentService setup complete")

# one tool in front of the ACL. The host keeps the Bearer.
mcp = build_mcp(multi_agent_service, admin_core_client, myLogger, envs)

myLogger.Info("MCP External Partner service booted successfully")

if __name__ == "__main__":
    myLogger.Info("Starting MCP External Partner service")
    mcp.run(transport="streamable-http")