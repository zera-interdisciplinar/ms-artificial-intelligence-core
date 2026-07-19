from logger.logger import logger
from config.environments import Environments

from fastapi import FastAPI, APIRouter

from multi_agent.multi_agent import IMultiAgentService

from .multi_agent_handlers import multi_agent_handlers

# uvicorn
from uvicorn import run as uvicorn_run



class RouterAPI:
    """
    RouterAPI is a class that provides an implementation for our routing API requests to the appropriate handlers. It serves as a central point for managing API endpoints and their corresponding logic.
    """
    
    _app: FastAPI
    
    def __init__(self, envs: Environments, logger: logger):
        self.envs = envs
        self.logger = logger
        
    def BuildAPI(self, multi_agent_service: IMultiAgentService):
        """
        BuildAPI is a method that sets up the API endpoints and their corresponding logic. It initializes the necessary components and prepares the API for handling requests.
        """
        self._app = FastAPI()
        
        group_v1 = APIRouter(prefix="/api/v1", tags=["v1"])
        
        multi_agent_router = multi_agent_handlers(multi_agent_service)
        
        group_v1.include_router(multi_agent_router)
        
        self._app.include_router(group_v1)
    
    def run(self):
        """
        Run is a method that starts the API server and listens for incoming requests. It takes an optional port parameter to specify the port on which the server should run.
        """
        
        uvicorn_run(
            app = self._app,
            port = int(self.envs.APP_PORT)
        )
        
        
        