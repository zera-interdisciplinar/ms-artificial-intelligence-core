from unittest.mock import patch

import pytest

from _internal.mongo.setup import Repository


@pytest.fixture
def envs():
    class Envs:
        MONGO_URI = "mongodb://mongo:27017"
        MONGO_DB_NAME = "zera"
        MONGO_USERNAME = "zera-user"
        MONGO_PASSWORD = "s3cret"

    return Envs()


@pytest.fixture
def mongo_client():
    with patch("_internal.mongo.setup.MongoClient") as client:
        yield client


def test_connects_using_the_configured_credentials(envs, mongo_client):
    Repository(envs)

    mongo_client.assert_called_once_with(
        "mongodb://mongo:27017", username="zera-user", password="s3cret"
    )


def test_selects_the_configured_database(envs, mongo_client):
    repository = Repository(envs)

    assert repository.client is mongo_client.return_value
    assert repository.db is mongo_client.return_value["zera"]


def test_logs_the_initialization(envs, mongo_client, capsys):
    Repository(envs)

    assert "Initializing MongoDB repository" in capsys.readouterr().out


def test_credentials_are_not_logged(envs, mongo_client, capsys):
    Repository(envs)

    assert "s3cret" not in capsys.readouterr().out
