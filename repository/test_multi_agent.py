from uuid import uuid4

import pytest
from pymongo.errors import PyMongoError

from multi_agent.entity import Message
from repository.exception import RepositoryException
from repository.multi_agent import MultiAgentRepository


@pytest.fixture
def repo(mongo_repository) -> MultiAgentRepository:
    repository = MultiAgentRepository()
    repository.setup(mongo_repository)
    return repository


class TestSetup:
    def test_binds_the_thread_and_message_collections(self, mongo_repository):
        repository = MultiAgentRepository()

        repository.setup(mongo_repository)

        assert repository.repository is mongo_repository
        assert repository.threadCollection is mongo_repository.db["threads"]
        assert repository.messageCollection is mongo_repository.db["messages"]

    def test_thread_and_message_collections_are_distinct(self, repo):
        assert repo.threadCollection is not repo.messageCollection


class TestSaveMessage:
    def test_inserts_the_json_encoded_message(self, repo, message):
        repo.save_message(message)

        repo.messageCollection.insert_one.assert_called_once_with(
            message.model_dump(mode="json")
        )

    def test_stores_uuids_and_enums_as_strings(self, repo, message):
        """retrieve_messages queries by string ids, so the write must match."""
        repo.save_message(message)

        document = repo.messageCollection.insert_one.call_args.args[0]
        assert document["user_id"] == str(message.user_id)
        assert document["thread_id"] == str(message.thread_id)
        assert document["role"] == "user"
        assert isinstance(document["created_at"], str)

    def test_wraps_a_driver_failure(self, repo, message):
        repo.messageCollection.insert_one.side_effect = PyMongoError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to save message: connection refused"):
            repo.save_message(message)

    def test_does_not_touch_the_thread_collection(self, repo, message):
        repo.save_message(message)

        repo.threadCollection.insert_one.assert_not_called()


class TestRetrieveMessages:
    def test_queries_by_stringified_user_and_thread(self, repo, user_id, thread_id):
        repo.messageCollection.find.return_value = []

        repo.retrieve_messages(user_id, thread_id)

        repo.messageCollection.find.assert_called_once_with(
            {"user_id": str(user_id), "thread_id": str(thread_id)}
        )

    def test_returns_validated_messages(self, repo, message, user_id, thread_id):
        repo.messageCollection.find.return_value = iter([message.model_dump(mode="json")])

        messages = repo.retrieve_messages(user_id, thread_id)

        assert messages == [message]
        assert isinstance(messages[0], Message)

    def test_preserves_the_cursor_order(self, repo, message, user_id, thread_id):
        answer = message.model_copy(update={"content": "três perfis"})
        repo.messageCollection.find.return_value = iter(
            [message.model_dump(mode="json"), answer.model_dump(mode="json")]
        )

        assert repo.retrieve_messages(user_id, thread_id) == [message, answer]

    def test_returns_empty_when_the_thread_has_no_messages(self, repo, user_id, thread_id):
        repo.messageCollection.find.return_value = iter([])

        assert repo.retrieve_messages(user_id, thread_id) == []

    def test_wraps_a_driver_failure(self, repo, user_id, thread_id):
        repo.messageCollection.find.side_effect = PyMongoError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to retrieve messages"):
            repo.retrieve_messages(user_id, thread_id)

    def test_wraps_a_malformed_document(self, repo, user_id, thread_id):
        repo.messageCollection.find.return_value = iter([{"user_id": "not-a-uuid"}])

        with pytest.raises(RepositoryException, match="Failed to retrieve messages"):
            repo.retrieve_messages(user_id, thread_id)


class TestRemoveThread:
    def test_deletes_the_matching_thread(self, repo, user_id, thread_id):
        repo.remove_thread(user_id, thread_id)

        repo.threadCollection.delete_one.assert_called_once_with(
            {"user_id": str(user_id), "thread_id": str(thread_id)}
        )

    def test_is_silent_when_nothing_matched(self, repo, user_id, thread_id):
        repo.threadCollection.delete_one.return_value.deleted_count = 0

        assert repo.remove_thread(user_id, uuid4()) is None

    def test_wraps_a_driver_failure(self, repo, user_id, thread_id):
        repo.threadCollection.delete_one.side_effect = PyMongoError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to remove thread"):
            repo.remove_thread(user_id, thread_id)
