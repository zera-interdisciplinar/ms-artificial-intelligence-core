"""
FAQ agent will use FAISS to retrieve the most 6 relevant passages from the knowledge base (a suport pdf) and then use a LLM to generate an answer based on the retrieved passages.
Pipeline for FAIIS: read -> preprocess -> chunking -> embedding -> FAISS -> context retrieval -> LLM answer generation.


FAQ agent package with a wrapper function to parse its output into a json format to update the state with answer and sources.
"""

from typing import Any, Optional

from config.environments import Environments

from ..entity import State, AgentName
from .message_utils import parse_json_message, with_preferences
from logger.logger import Logger
from pydantic import SecretStr

# langchain imports
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from langchain_core.tools import BaseTool

from langchain.tools import tool
from langgraph.graph.state import CompiledStateGraph

class FAQ:
    """
    Class that holds the faq_agent and the functions that use it.
    """

    _faiss_indexes: FAISS
    envs: Environments
    logger: Logger

    def __init__(self, envs: Environments, logger: Logger) -> None:
        self.faq_agent: Optional[CompiledStateGraph] = None
        self.envs = envs
        self.logger = logger

    def setup(self) -> None:
        """
        Setup function to initialize the FAQ agent and the FAISS index from a document.
        """
        
        pdf_path = self.envs.FAQ_PDF_PATH
        self.logger.Info(f"Setting up FAQ agent with PDF path: {pdf_path}")
        
        loader = PyPDFLoader(pdf_path)
        documents = loader.load()
        self.logger.Info(f"Loaded {len(documents)} documents from PDF: {pdf_path}")
        
        splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
        docs = splitter.split_documents(documents)
        self.logger.Info(f"Split documents into {len(docs)} chunks for FAISS index")

        api_key = SecretStr(self.envs.GEMINI_API_KEY) if self.envs.GEMINI_API_KEY else None
        
        embeddings = GoogleGenerativeAIEmbeddings(
            model = "gemini-embedding-2-preview",
            api_key = api_key,
        )
        
        self.logger.Info("Creating FAISS index from document chunks")
        faiss_indexes = FAISS.from_documents(docs, embeddings)
        self._faiss_indexes = faiss_indexes
        self.logger.Info("FAISS index created successfully")
        
        
    def make_retrieve_context_tool(self) -> BaseTool:
        """
        Builds the retrieve_context tool bound to this FAQ instance's FAISS index.
        """

        @tool("retrieve_context", description="Retrieve the most relevant passages from the FAISS index based on the input context.")
        def retrieve_context(ctx: str) -> list[Document]:
            """
            Retrieve the most relevant passages from the FAISS index based on the input context. It receives only the context string and returns a list of relevant documents.
            """
            self.logger.Info(f"Retrieving context for query: {ctx}")
            docs = self._faiss_indexes.similarity_search(ctx, k=6)
            self.logger.Info(f"Retrieved {len(docs)} relevant documents from FAISS index")
            return docs

        return retrieve_context


    async def faq_func(self, state: State) -> dict[str, Any]:
        """
        Wraps faq_agent so its JSON output is parsed and projected into answer/sources.
        """
        assert self.faq_agent is not None, "faq_agent is not set; call setup() and assign faq_agent before invoking"
        request = with_preferences(state["current_request"], state.get("user_preferences"))
        response = await self.faq_agent.ainvoke({"messages": request})
        self.logger.Info("FAQ agent invoked")

        self.logger.Debug(f"FAQ raw response={response['messages'][-1].content}")
        formated_response = parse_json_message(response["messages"][-1].content)
        self.logger.Debug(f"FAQ formatted response={formated_response}")

        return {
            "called_agents": [AgentName.FAQ_AGENT],
            "answer": formated_response["answer"],
            "sources": formated_response["sources"],
        }
