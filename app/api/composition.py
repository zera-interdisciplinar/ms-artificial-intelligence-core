"""
Composition root: the only place that picks concrete adapters and injects them
into the core. Kept apart from main.py so tests can compose without booting uvicorn.
"""

import asyncio
from typing import cast

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_groq import ChatGroq
from pydantic import SecretStr
from redis.asyncio import Redis

from logger.logger import Logger
from config.environments import Environments
from _internal.mongo.setup import Repository
from _internal.admin_core.client import AdminCoreClient
from _internal.storage.service import SupabaseStorageService
from _internal.storage.pdf import PdfRenderer
from _internal.mcp.clients import fetch_ms_inventory_tools, fetch_predict_model_context
from repository.multi_agent import MultiAgentRepository
from multi_agent.async_redis_saver import AsyncRedisSaver
from multi_agent.agents.faq import FAQ
from multi_agent.service import MultiAgentService


def build_llm(envs: Environments, model: str) -> BaseChatModel:
    """Gemini with Groq as fallback when Gemini is not available."""
    gemini = ChatGoogleGenerativeAI(
        model=model,
        temperature=0.2,
        top_p=0.9,
        api_key=SecretStr(envs.GEMINI_API_KEY) if envs.GEMINI_API_KEY else None,
        reasoning_effort="low",
    )
    groq = ChatGroq(
        model=envs.LLM_FALLBACK_MODEL,
        temperature=0.2,
        api_key=SecretStr(envs.GROQ_API_KEY) if envs.GROQ_API_KEY else None,
    )
    # RunnableWithFallbacks behaves as a chat model at runtime; cast only hides the type error
    return cast(BaseChatModel, gemini.with_fallbacks([groq]))


def build_service(envs: Environments, logger: Logger, store: Redis) -> tuple[MultiAgentService, AdminCoreClient]:
    repository = MultiAgentRepository()
    repository.setup(Repository(envs))
    logger.Info("MultiAgentRepository setup complete")

    # conversation state shared by every replica; Redis drops idle threads after the session TTL
    checkpointer = AsyncRedisSaver(
        redis_url=envs.REDIS_URL,
        ttl={"default_ttl": max(1, envs.SESSION_TTL_SECONDS // 60), "refresh_on_read": True},
    )
    checkpointer.setup()

    # cross-repo tools (via Kong) and the FAQ index
    logger.Info("Fetching predict_model and ms-inventory MCP tools")
    predict_tool, valid_categories, valid_climate_zones = asyncio.run(fetch_predict_model_context(envs))
    inventory_tools = asyncio.run(fetch_ms_inventory_tools(envs))
    faq = FAQ(envs, logger)
    faq.setup()

    admin_core = AdminCoreClient(envs, logger, store)

    service = MultiAgentService(
        repository=repository,
        session_history_limit=envs.SESSION_HISTORY_LIMIT,
        logger=logger,
        pdf_renderer=PdfRenderer(),
        storage_service=SupabaseStorageService(envs),
        unit_resolver=admin_core,
        llm=build_llm(envs, envs.LLM_MODEL),
        llm_fast=build_llm(envs, envs.LLM_FAST_MODEL),
        checkpointer=checkpointer,
        faq_retriever=faq.make_retrieve_context_tool(),
        predict_tool=predict_tool,
        valid_categories=valid_categories,
        valid_climate_zones=valid_climate_zones,
        inventory_tools=inventory_tools,
    )
    service.setup()
    logger.Info("MultiAgentService setup complete")
    return service, admin_core
