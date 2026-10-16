"""FastAPI application entrypoint for the Zera ms-artificial-intelligence-core service."""

from redis.asyncio import Redis

from logger.logger import Logger
from config.environments import Environments
from _internal.api.router import RouterAPI
from app.api.composition import build_service

myLogger = Logger()
myLogger.Info("Booting up ms-artificial-intelligence-core service")

envs = Environments()
if envs.LANGSMITH_TRACING:
    myLogger.Info(f"LangSmith tracing enabled project={envs.LANGSMITH_PROJECT}")

redis = Redis.from_url(envs.REDIS_URL)
multi_agent_service, admin_core_client = build_service(envs, myLogger, redis)

app = RouterAPI(envs, myLogger)
app.BuildAPI(multi_agent_service, admin_core_client, redis)

if __name__ == "__main__":
    myLogger.Info("Starting ms-artificial-intelligence-core service")
    app.run()
