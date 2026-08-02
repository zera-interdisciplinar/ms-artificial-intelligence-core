"""FastAPI application entrypoint for the Zera ms-artificial-intelligence-core service."""

from logger.logger import logger
from config.environments import Environments
from _internal.mongo.setup import Repository

# MultiAgentRepository imports
from repository.multi_agent import MultiAgentRepository
from multi_agent.multi_agent import IMultiAgentRepository

# MultiAgentService imports
from multi_agent.multi_agent import IMultiAgentService
from multi_agent.service import MultiAgentService

# RouterAPI imports
from _internal.api.router import RouterAPI

myLogger = logger()
myLogger.Info("Booting up ms-artificial-intelligence-core service")

envs = Environments()

# Open a new connection to the MongoDB database using the environment variables
repository = Repository(envs)

# create the MultiAgentRepository instance
multi_agent_repository: IMultiAgentRepository = MultiAgentRepository()
multi_agent_repository.setup(repository)

myLogger.Info("MultiAgentRepository setup complete")

# create the multi-agent service instance
multi_agent_service: IMultiAgentService = MultiAgentService(
    repository=multi_agent_repository,
    envs=envs,
    logger=myLogger
)
multi_agent_service.setup()

myLogger.Info("MultiAgentService setup complete")

# create the FastAPI app and router
app = RouterAPI(envs, myLogger)

# build the API router using the multi-agent service
app.BuildAPI(multi_agent_service)

# list-and-serve the API endpoints
if __name__ == "__main__":
    myLogger.Info("Starting ms-artificial-intelligence-core service")
    app.run()