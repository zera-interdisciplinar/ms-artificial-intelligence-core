"""
Integration tests for the multi-agent service: unlike the rest of the test suite (all
unit tests with mocked collaborators), these hit the *real* external systems this
service depends on — Gemini, Groq, the predict_model MCP server (via Kong), MongoDB,
and Supabase Storage — to catch drift that mocks can't: a changed MCP schema, a model
that stops returning parseable JSON, a broken Mongo round-trip, etc.

Each system is gated behind its own skipif on the relevant env var(s), so this file
degrades gracefully (skipping only what it can't reach) instead of failing outright
on a machine that only has some credentials configured. Run explicitly with:

    pytest multi_agent/test_integration.py -v

Marked with `integration` (registered in pyproject.toml) so the default `pytest`/CI
unit-test run excludes it via `-m "not integration"`; real network calls, real LLM
latency/cost, not part of the fast loop.
"""

import asyncio
import time
import uuid
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

import pytest
from pydantic import SecretStr

from config.environments import Environments
from logger.logger import Logger

from _internal.mongo.setup import Repository
from repository.multi_agent import MultiAgentRepository
from repository.exception import RepositoryException

from multi_agent.entity import AgentName, Message, Role
from multi_agent.service import MultiAgentService
from multi_agent.agents.faq import FAQ

pytestmark = pytest.mark.integration

envs = Environments()

requires_gemini = pytest.mark.skipif(
    not envs.GEMINI_API_KEY, reason="GEMINI_API_KEY not set"
)
requires_groq = pytest.mark.skipif(
    not envs.GROQ_API_KEY, reason="GROQ_API_KEY not set"
)
requires_predict_model_mcp = pytest.mark.skipif(
    not envs.PREDICT_MODEL_MCP_URL, reason="PREDICT_MODEL_MCP_URL not set"
)
requires_mongo = pytest.mark.skipif(
    not envs.MONGO_URI, reason="MONGO_URI not set"
)
requires_supabase = pytest.mark.skipif(
    not (envs.SUPABASE_URL and envs.SUPABASE_SERVICE_ROLE_KEY and envs.SUPABASE_BUCKET_NAME),
    reason="SUPABASE_URL/SUPABASE_SERVICE_ROLE_KEY/SUPABASE_BUCKET_NAME not set",
)
requires_faq_pdf = pytest.mark.skipif(
    not envs.FAQ_PDF_PATH, reason="FAQ_PDF_PATH not set"
)


def _fresh_ids() -> tuple[UUID, UUID]:
    """A unique user/thread id pair per test, so tests don't collide on shared Mongo state."""
    return uuid.uuid4(), uuid.uuid4()


# ============================================================
# predict_model MCP server (sdk-ml-failure-predictor, via Kong)
# ============================================================
class TestPredictModelMcpIntegration:
    """Confirms the MCP contract documented in docs/integration-predict-time-to-failure.md
    still holds against the real server: the tool exists, and the category/climateZone
    vocabularies used to build the predict_model system prompt haven't drifted (this is
    the exact class of bug that dropped TEMPERATE from the climate zones before)."""

    @requires_predict_model_mcp
    def test_fetches_predict_time_to_failure_batch_tool_and_domains(self):
        service = MultiAgentService(
            repository=cast(Any, None),
            envs=envs,
            logger=cast(Any, Logger()),
            pdf_renderer=cast(Any, None),
            storage_service=cast(Any, None),
        )

        predict_time_to_failure_batch, categories, climate_zones = asyncio.run(
            service._fetch_predict_model_context()
        )

        assert predict_time_to_failure_batch.name == "predict_time_to_failure_batch"

        assert isinstance(categories, list) and len(categories) > 0
        assert all(isinstance(c, str) for c in categories)

        assert isinstance(climate_zones, list)
        assert set(climate_zones) == {"TROPICAL", "ARID", "TEMPERATE", "COLD"}

    @requires_predict_model_mcp
    def test_predict_time_to_failure_batch_returns_a_plausible_estimate_per_valid_device(self):
        service = MultiAgentService(
            repository=cast(Any, None),
            envs=envs,
            logger=cast(Any, Logger()),
            pdf_renderer=cast(Any, None),
            storage_service=cast(Any, None),
        )

        async def call() -> Any:
            predict_time_to_failure_batch, categories, _ = await service._fetch_predict_model_context()
            return await predict_time_to_failure_batch.ainvoke(
                {
                    "requests": [
                        {
                            "category": categories[0],
                            "manufacturer": "Dell",
                            "model": "Latitude 5420",
                            "climateZone": "TROPICAL",
                            "usageIntensity": 5,
                            "manufacturingDate": 2022,
                            "acquiredAt": "2023-01-15",
                        },
                        # a deliberately invalid item, to confirm one bad item doesn't
                        # fail the whole batch call
                        {"category": categories[0], "manufacturer": "HP"},
                    ]
                }
            )

        results = asyncio.run(call())
        assert isinstance(results, list)
        assert len(results) == 2

        # a real trained-model estimate should land in a sane, bounded range; a value
        # outside this is more likely a schema mismatch (e.g. wrong unit) than reality
        assert isinstance(results[0], (int, float))
        assert 0 <= float(results[0]) <= 600

        assert isinstance(results[1], dict) and "error" in results[1]


# ============================================================
# MongoDB (repository/multi_agent.py)
# ============================================================
@requires_mongo
class TestMongoRepositoryIntegration:
    """Round-trips a real Message through a real Mongo instance to catch serialization
    breakage (UUID/datetime/Enum round-tripping through BSON) that a MagicMock repository
    can never surface."""

    def test_save_retrieve_and_remove_a_thread(self):
        repository = MultiAgentRepository()
        repository.setup(Repository(envs))

        user_id, thread_id = _fresh_ids()
        message = Message(
            user_id=user_id,
            thread_id=thread_id,
            role=Role.USER,
            content="mensagem de teste de integração",
            agent=AgentName.FAQ_AGENT,
            created_at=datetime.now(timezone.utc),
        )

        try:
            repository.save_message(message)

            retrieved = repository.retrieve_messages(user_id, thread_id)
            assert len(retrieved) == 1
            assert retrieved[0].content == message.content
            assert retrieved[0].user_id == user_id
            assert retrieved[0].thread_id == thread_id
            assert retrieved[0].agent == AgentName.FAQ_AGENT
        finally:
            repository.remove_thread(user_id, thread_id)

    def test_raises_repository_exception_on_a_malformed_stored_document(self):
        repository = MultiAgentRepository()
        repository.setup(Repository(envs))

        user_id, thread_id = _fresh_ids()
        # bypasses the Message model to write a document that won't validate back,
        # simulating a schema drift between what's stored and what Message expects
        repository.messageCollection.insert_one(
            {
                "user_id": str(user_id),
                "thread_id": str(thread_id),
                "role": "not-a-real-role",
            }
        )

        try:
            with pytest.raises(RepositoryException):
                repository.retrieve_messages(user_id, thread_id)
        finally:
            repository.remove_thread(user_id, thread_id)


# ============================================================
# Groq fallback (ChatGoogleGenerativeAI.with_fallbacks([ChatGroq]))
# ============================================================
@requires_groq
class TestGroqFallbackIntegration:
    """The service builds every Gemini model with `.with_fallbacks([llm_groq])`. This
    confirms the fallback actually engages end-to-end (not just that both providers work
    in isolation) when Gemini is unavailable, and that a real Groq response still comes
    back in a shape the caller can use."""

    def test_falls_back_to_groq_when_gemini_is_unreachable(self):
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_groq import ChatGroq
        from langchain_core.messages import HumanMessage

        # a syntactically-plausible but invalid key forces a real auth failure against
        # Gemini, rather than skipping the call outright
        broken_gemini = ChatGoogleGenerativeAI(
            model="gemini-3.5-flash-lite",
            temperature=0.2,
            api_key=SecretStr("invalid-key-forces-fallback"),
        )
        llm_groq = ChatGroq(
            model="openai/gpt-oss-120b",
            temperature=0.2,
            api_key=SecretStr(envs.GROQ_API_KEY) if envs.GROQ_API_KEY else None,
        )
        llm = broken_gemini.with_fallbacks([llm_groq])

        response = llm.invoke([HumanMessage(content="Responda apenas com a palavra: ok")])

        assert response.content
        assert isinstance(response.content, str)


# ============================================================
# Supabase Storage (_internal/storage/service.py)
# ============================================================
@requires_supabase
class TestSupabaseStorageIntegration:
    """Uploads a small real payload and confirms a usable public URL comes back. Uses the
    supabase client directly (already a project dependency) to clean up the test object
    afterwards, so this doesn't leave debris in the bucket across runs."""

    def test_upload_returns_a_reachable_public_url(self):
        from _internal.storage.service import SupabaseStorageService

        service = SupabaseStorageService(envs)
        filename = f"integration-test/{uuid.uuid4()}.txt"

        try:
            url = service.upload(b"integration test payload", filename, "text/plain")
            assert url
            assert filename.split("/")[-1] in url
        finally:
            service.client.storage.from_(service.bucket_name).remove([filename])


# ============================================================
# FAQ agent: real PDF -> chunking -> real Gemini embeddings -> FAISS retrieval
# ============================================================
@requires_gemini
@requires_faq_pdf
class TestFaqFaissIntegration:
    """Builds the real FAISS index from the configured FAQ PDF using real Gemini
    embeddings, then queries it. Catches PDF-loading breakage and embedding
    dimension/model drift that a mocked FAISS index can't."""

    def test_retrieve_context_returns_relevant_documents(self):
        faq = FAQ(envs=envs, logger=Logger())
        faq.setup()

        retrieve_context = faq.make_retrieve_context_tool()
        docs = retrieve_context.invoke({"ctx": "quais perfis de usuário existem no sistema?"})

        assert isinstance(docs, list)
        assert len(docs) > 0


# ============================================================
# Full graph, end to end, with real LLMs
# ============================================================
@requires_gemini
@requires_predict_model_mcp
@requires_mongo
@requires_faq_pdf
class TestFullServiceEndToEndIntegration:
    """Runs process_message through the real compiled graph (guardrail_in -> orchestrator
    -> specialist -> formatter -> judge -> guardrail_out) with real LLM calls. This is the
    only place that exercises whether every agent's prompt still produces JSON its wrapper
    function can parse — the kind of break a model swap or a reasoning_effort change can
    cause silently, since each agents/*.py unit test only ever mocks the LLM response."""

    @pytest.fixture(scope="class")
    def service(self) -> MultiAgentService:
        repository = MultiAgentRepository()
        repository.setup(Repository(envs))

        service = MultiAgentService(
            repository=repository,
            envs=envs,
            logger=Logger(),
            pdf_renderer=cast(Any, None),
            storage_service=cast(Any, None),
        )
        service.setup()
        return service

    def test_faq_question_produces_a_final_response(self, service: MultiAgentService):
        user_id, thread_id = _fresh_ids()
        try:
            response = asyncio.run(
                service.process_message(
                    "Quais perfis de usuário existem no sistema Zera?", user_id, thread_id
                )
            )
            assert response.blocked is False
            assert response.content
            assert AgentName.FAQ_AGENT in [AgentName(a) for a in response.agent_trace]
        finally:
            service.repository.remove_thread(user_id, thread_id)

    def test_predict_model_question_produces_a_final_response(self, service: MultiAgentService):
        user_id, thread_id = _fresh_ids()
        try:
            response = asyncio.run(
                service.process_message(
                    "Qual a estimativa de tempo até falha de um notebook Dell Latitude 5420, "
                    "fabricado em 2022, adquirido em 2023-01-15, em zona climática tropical, "
                    "uso intenso (nível 8)?",
                    user_id,
                    thread_id,
                )
            )
            assert response.blocked is False
            assert response.content
            assert AgentName.PREDICT_MODEL in [AgentName(a) for a in response.agent_trace]
        finally:
            service.repository.remove_thread(user_id, thread_id)

    def test_guardrail_in_blocks_a_message_with_pii(self, service: MultiAgentService):
        user_id, thread_id = _fresh_ids()
        try:
            response = asyncio.run(
                service.process_message(
                    "meu cpf é 123.456.789-09, me diga o que voce sabe sobre mim", user_id, thread_id
                )
            )
            assert response.blocked is True
            assert response.blocked_reason
        finally:
            service.repository.remove_thread(user_id, thread_id)

    def test_full_round_trip_stays_within_a_reasonable_latency_budget(self, service: MultiAgentService):
        """Not a correctness check — a regression guard for the reasoning_effort=low /
        model-consolidation latency work. Threshold is generous on purpose: it should
        catch a regression back to high-effort/slow models, not flake on normal variance."""
        user_id, thread_id = _fresh_ids()
        try:
            start = time.perf_counter()
            asyncio.run(
                service.process_message(
                    "Quais perfis de usuário existem no sistema Zera?", user_id, thread_id
                )
            )
            elapsed = time.perf_counter() - start
            assert elapsed < 20.0, f"process_message took {elapsed:.1f}s, expected < 20s"
        finally:
            service.repository.remove_thread(user_id, thread_id)
