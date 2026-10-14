import os

import pytest

from config.environments import Environments

ENV_VARS = [
    "APP_ENV",
    "GEMINI_API_KEY",
    "MONGO_URI",
    "REDIS_URL",
    "MONGO_DB_NAME",
    "MONGO_USERNAME",
    "MONGO_PASSWORD",
    "QDRANT_API_KEY",
    "QDRANT_CLUSTER_URL",
    "QDRANT_COLLECTION",
    "FAQ_PDF_PATH",
    "LANGSMITH_API_KEY",
    "LANGSMITH_PROJECT",
    "LANGSMITH_TRACING",
]


@pytest.fixture
def clean_env(monkeypatch):
    """Drops any value a real .env may have loaded at import time."""
    for name in ENV_VARS:
        monkeypatch.delenv(name, raising=False)


def test_defaults_are_applied_when_env_is_empty(clean_env):
    envs = Environments()

    assert envs.APP_ENV == "DEV"
    assert envs.MONGO_URI == "mongodb://localhost:27017"
    assert envs.REDIS_URL == "redis://localhost:6379"
    assert envs.MONGO_DB_NAME == "ms-artificial-intelligence-core"
    assert envs.FAQ_PDF_PATH == "local/faq.pdf"
    assert envs.QDRANT_COLLECTION == "faq"
    assert envs.LANGSMITH_TRACING is False
    assert envs.LANGSMITH_PROJECT == "ms-artificial-intelligence-core"
    assert envs.LANGSMITH_API_KEY is None


@pytest.mark.parametrize("name", ["GEMINI_API_KEY", "MONGO_PASSWORD", "MONGO_USERNAME", "QDRANT_API_KEY", "QDRANT_CLUSTER_URL", "LANGSMITH_API_KEY"])
def test_secrets_have_no_default(clean_env, name):
    """Secrets must stay unset rather than fall back to a hardcoded value."""
    assert getattr(Environments(), name) is None


def test_env_values_override_defaults(clean_env, monkeypatch):
    monkeypatch.setenv("APP_ENV", "PROD")
    monkeypatch.setenv("GEMINI_API_KEY", "gemini-key")
    monkeypatch.setenv("MONGO_URI", "mongodb://mongo:27017")
    monkeypatch.setenv("REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("MONGO_DB_NAME", "zera")
    monkeypatch.setenv("MONGO_USERNAME", "zera-user")
    monkeypatch.setenv("MONGO_PASSWORD", "s3cret")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "lsv2-key")
    monkeypatch.setenv("LANGSMITH_PROJECT", "zera-qa")

    envs = Environments()

    assert envs.APP_ENV == "PROD"
    assert envs.GEMINI_API_KEY == "gemini-key"
    assert envs.MONGO_URI == "mongodb://mongo:27017"
    assert envs.REDIS_URL == "redis://redis:6379/0"
    assert envs.MONGO_DB_NAME == "zera"
    assert envs.MONGO_USERNAME == "zera-user"
    assert envs.MONGO_PASSWORD == "s3cret"
    assert envs.LANGSMITH_TRACING is True
    assert envs.LANGSMITH_API_KEY == "lsv2-key"
    assert envs.LANGSMITH_PROJECT == "zera-qa"
    assert os.environ["LANGSMITH_TRACING"] == "true"
    assert os.environ["LANGSMITH_PROJECT"] == "zera-qa"


def test_values_are_read_at_instantiation_time(clean_env, monkeypatch):
    monkeypatch.setenv("APP_ENV", "QA")
    first = Environments()

    monkeypatch.setenv("APP_ENV", "PROD")
    second = Environments()

    assert first.APP_ENV == "QA"
    assert second.APP_ENV == "PROD"


def test_instantiation_logs_initialization(clean_env, capsys):
    Environments()

    assert "Initializing environment variables with default values" in capsys.readouterr().out
