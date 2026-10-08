from contextlib import asynccontextmanager

from logger.logger import Logger
from config.environments import Environments

from fastapi import FastAPI, APIRouter

from multi_agent.multi_agent import IMultiAgentService

from _internal.mcp.server import build_mcp

from .multi_agent_handlers import multi_agent_handlers, report_handlers

# uvicorn
from uvicorn import run as uvicorn_run



class RouterAPI:
    """
    RouterAPI is a class that provides an implementation for our routing API requests to the appropriate handlers. It serves as a central point for managing API endpoints and their corresponding logic.
    """
    
    _app: FastAPI
    
    envs: Environments
    logger: Logger

    def __init__(self, envs: Environments, logger: Logger) -> None:
        self.envs = envs
        self.logger = logger

    def BuildAPI(self, multi_agent_service: IMultiAgentService) -> None:
        """
        BuildAPI is a method that sets up the API endpoints and their corresponding logic. It initializes the necessary components and prepares the API for handling requests.
        """
        mcp = None
        if self.envs.SELF_MCP_URL:
            mcp = build_mcp(
                multi_agent_service,
                multi_agent_service.admin_core,
                self.logger,
                self.envs,
            )
            mcp_app = mcp.streamable_http_app()

            @asynccontextmanager
            async def lifespan(_app):
                async with mcp.session_manager.run():
                    yield
        else:
            mcp_app = None

            @asynccontextmanager
            async def lifespan(_app):
                yield

        self._app = FastAPI(lifespan=lifespan)

        @self._app.get("/health", tags=["health"])
        async def health_check() -> dict[str, str]:
            return {"status": "ok"}

        group_v1 = APIRouter(prefix="/api/v1", tags=["v1"])

        group_v1.include_router(multi_agent_handlers(multi_agent_service))
        group_v1.include_router(report_handlers(multi_agent_service))

        self._app.include_router(group_v1)

        # After the API routes, so /health and /api/v1 keep winning.
        if mcp_app is not None:
            self._app.mount("/", mcp_app)

    def run(self) -> None:
        """
        Run is a method that starts the API server and listens for incoming requests. It takes an optional port parameter to specify the port on which the server should run.
        """
        
        uvicorn_run(
            app = self._app,
            port = int(self.envs.APP_PORT),
            host = self.envs.APP_HOST,
        )
        
        
        