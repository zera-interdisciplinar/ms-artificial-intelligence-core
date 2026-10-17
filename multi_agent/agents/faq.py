"""
FAQ agent retrieves the 6 most relevant passages from a Qdrant collection
and uses an LLM to answer from those passages.

Indexing is offline: script/index_faq.py. Boot only connects to the existing collection.
"""

from typing import Any

from config.environments import Environments

from ..entity import State, AgentName, GraphNodeFunc, RedirectTo
from .message_utils import parse_json_message, request_with_history
from logger.logger import Logger
from pydantic import SecretStr, ValidationError

from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_qdrant import QdrantVectorStore
from langchain_core.documents import Document
from langchain_core.tools import BaseTool
from langchain_core.vectorstores import VectorStore

from langchain.tools import tool
from langgraph.graph.state import CompiledStateGraph

_logger = Logger()


class FAQ:
    """
    Qdrant collection over the support PDF, exposed to faq_agent as retrieve_context.
    Connected in the composition root; the core only receives the tool.
    """

    _store: VectorStore
    envs: Environments
    logger: Logger

    def __init__(self, envs: Environments, logger: Logger) -> None:
        self.envs = envs
        self.logger = logger

    def setup(self) -> None:
        if not self.envs.QDRANT_CLUSTER_URL or not self.envs.QDRANT_API_KEY:
            raise ValueError("QDRANT_CLUSTER_URL and QDRANT_API_KEY are required")
        collection = self.envs.QDRANT_COLLECTION
        self.logger.Info(
            f"Connecting FAQ retriever to Qdrant collection {collection} at {self.envs.QDRANT_CLUSTER_URL}"
        )
        self._store = QdrantVectorStore.from_existing_collection(
            embedding=GoogleGenerativeAIEmbeddings(
                model="gemini-embedding-2-preview",
                api_key=SecretStr(self.envs.GEMINI_API_KEY) if self.envs.GEMINI_API_KEY else None,
            ),
            collection_name=collection,
            url=self.envs.QDRANT_CLUSTER_URL,
            api_key=self.envs.QDRANT_API_KEY,
        )
        self.logger.Info("FAQ Qdrant store connected")

    def make_retrieve_context_tool(self) -> BaseTool:
        @tool("retrieve_context", description="Retrieve the most relevant passages from the FAQ index based on the input context.")
        def retrieve_context(ctx: str) -> list[Document]:
            """
            Retrieve the most relevant passages from the FAQ index based on the input context. It receives only the context string and returns a list of relevant documents.
            """
            self.logger.Info(f"Retrieving context for query: {ctx}")
            docs = self._store.similarity_search(ctx, k=6)
            self.logger.Info(f"Retrieved {len(docs)} relevant documents from Qdrant")
            return docs

        return retrieve_context


def make_faq_func(faq_agent: CompiledStateGraph) -> GraphNodeFunc:
    """
    Wraps faq_agent so its JSON output is parsed and projected into answer/sources.
    """

    async def faq_func(state: State) -> dict[str, Any]:
        request = request_with_history(
            state["current_request"], state.get("messages"), state.get("user_preferences")
        )
        response = await faq_agent.ainvoke({"messages": request})
        _logger.Info("FAQ agent invoked")

        _logger.Debug(f"FAQ raw response={response['messages'][-1].content}")
        formated_response = parse_json_message(response["messages"][-1].content, "answer", "sources")
        _logger.Debug(f"FAQ formatted response={formated_response}")

        return {
            "called_agents": [AgentName.FAQ_AGENT],
            "answer": formated_response["answer"],
            "sources": formated_response["sources"],
            "redirect_to": _redirect_to(formated_response.get("redirect_to")),
        }

    return faq_func


def _redirect_to(raw: Any) -> RedirectTo | None:
    if not raw:
        return None
    try:
        return RedirectTo.model_validate(raw)
    except ValidationError:
        return None
