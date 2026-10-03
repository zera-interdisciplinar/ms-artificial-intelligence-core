from datetime import datetime, timezone

import pytest
from pymongo.errors import PyMongoError

from multi_agent.entity import ConversationPage, ConversationPreview, DisposalReport, Message, Role, UserPreferences
from repository.exception import RepositoryException
from repository.multi_agent import MultiAgentRepository


@pytest.fixture
def repo(mongo_repository) -> MultiAgentRepository:
    repository = MultiAgentRepository()
    repository.setup(mongo_repository)
    return repository


class TestSetup:
    def test_binds_the_message_and_preferences_collections(self, mongo_repository):
        repository = MultiAgentRepository()

        repository.setup(mongo_repository)

        assert repository.repository is mongo_repository
        assert repository.messageCollection is mongo_repository.db["messages"]
        assert repository.preferencesCollection is mongo_repository.db["user_preferences"]
        assert repository.disposalReportCollection is mongo_repository.db["disposal_reports"]

    def test_creates_the_expected_indexes(self, mongo_repository):
        repository = MultiAgentRepository()

        repository.setup(mongo_repository)

        repository.messageCollection.create_index.assert_called_once_with(
            [("user_id", 1), ("thread_id", 1), ("created_at", -1)]
        )
        repository.preferencesCollection.create_index.assert_called_once_with(
            [("user_id", 1)], unique=True
        )
        repository.disposalReportCollection.create_index.assert_called_once_with(
            [("disposal_id", 1)], unique=True
        )


class TestSaveMessage:
    def test_inserts_the_message_with_stringified_ids(self, repo, message):
        repo.save_message(message)

        repo.messageCollection.insert_one.assert_called_once()
        document = repo.messageCollection.insert_one.call_args.args[0]
        assert document["user_id"] == str(message.user_id)
        assert document["thread_id"] == str(message.thread_id)
        assert document["role"] == "user"

    def test_stores_created_at_as_a_real_datetime(self, repo, message):
        """created_at must sort/TTL correctly in Mongo, so it can't be a string."""
        repo.save_message(message)

        document = repo.messageCollection.insert_one.call_args.args[0]
        assert isinstance(document["created_at"], datetime)

    def test_wraps_a_driver_failure(self, repo, message):
        repo.messageCollection.insert_one.side_effect = PyMongoError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to save message: connection refused"):
            repo.save_message(message)


class TestRetrieveMessages:
    def test_queries_by_stringified_user_and_thread_sorted_and_limited(self, repo, user_id, thread_id):
        cursor = repo.messageCollection.find.return_value
        cursor.sort.return_value = cursor
        cursor.limit.return_value = iter([])

        repo.retrieve_messages(user_id, thread_id, limit=10)

        repo.messageCollection.find.assert_called_once_with(
            {"user_id": str(user_id), "thread_id": str(thread_id)}
        )
        cursor.sort.assert_called_once_with("created_at", -1)
        cursor.limit.assert_called_once_with(10)

    def test_returns_validated_messages_oldest_first(self, repo, message, user_id, thread_id):
        answer = message.model_copy(update={"content": "três perfis"})
        cursor = repo.messageCollection.find.return_value
        cursor.sort.return_value = cursor
        # Mongo returns newest-first (per the sort above); the repository must reverse it.
        cursor.limit.return_value = iter([
            answer.model_dump(mode="python") | {"user_id": str(user_id), "thread_id": str(thread_id)},
            message.model_dump(mode="python") | {"user_id": str(user_id), "thread_id": str(thread_id)},
        ])

        messages = repo.retrieve_messages(user_id, thread_id)

        assert messages == [message, answer]

    def test_returns_empty_when_the_thread_has_no_messages(self, repo, user_id, thread_id):
        cursor = repo.messageCollection.find.return_value
        cursor.sort.return_value = cursor
        cursor.limit.return_value = iter([])

        assert repo.retrieve_messages(user_id, thread_id) == []

    def test_returns_every_message_when_the_limit_is_omitted(self, repo, message, user_id, thread_id):
        answer = message.model_copy(update={"content": "três perfis", "role": Role.ASSISTANT})
        cursor = repo.messageCollection.find.return_value
        cursor.sort.return_value = iter([
            answer.model_dump(mode="python") | {"user_id": str(user_id), "thread_id": str(thread_id)},
            message.model_dump(mode="python") | {"user_id": str(user_id), "thread_id": str(thread_id)},
        ])

        messages = repo.retrieve_messages(user_id, thread_id, limit=None)

        assert messages == [message, answer]
        cursor.limit.assert_not_called()

    def test_wraps_a_driver_failure(self, repo, user_id, thread_id):
        repo.messageCollection.find.side_effect = PyMongoError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to retrieve messages"):
            repo.retrieve_messages(user_id, thread_id)

    def test_wraps_a_malformed_document(self, repo, user_id, thread_id):
        cursor = repo.messageCollection.find.return_value
        cursor.sort.return_value = cursor
        cursor.limit.return_value = iter([{"user_id": "not-a-uuid"}])

        with pytest.raises(RepositoryException, match="Failed to retrieve messages"):
            repo.retrieve_messages(user_id, thread_id)


class TestListConversations:
    def test_aggregates_by_user_newest_activity_first(self, repo, user_id):
        repo.messageCollection.aggregate.return_value = iter([{"items": [], "total": []}])

        repo.list_conversations(user_id, page=2, page_size=5)

        pipeline = repo.messageCollection.aggregate.call_args.args[0]
        assert pipeline[0] == {"$match": {"user_id": str(user_id)}}
        assert pipeline[-2] == {"$sort": {"last_message_at": -1}}
        assert pipeline[-1]["$facet"]["items"] == [{"$skip": 5}, {"$limit": 5}]

    def test_returns_a_page_with_the_first_forty_characters(self, repo, user_id, thread_id):
        last_at = datetime(2026, 7, 16, 13, 0, 0, tzinfo=timezone.utc)
        repo.messageCollection.aggregate.return_value = iter([{
            "items": [{"_id": str(thread_id), "preview": "a" * 80, "last_message_at": last_at}],
            "total": [{"count": 1}],
        }])

        page = repo.list_conversations(user_id)

        assert page == ConversationPage(
            items=[ConversationPreview(
                thread_id=thread_id,
                last_message_at=last_at,
                preview="a" * 40,
            )],
            page=1,
            page_size=20,
            total=1,
        )

    def test_returns_an_empty_page_when_the_user_has_no_threads(self, repo, user_id):
        repo.messageCollection.aggregate.return_value = iter([{"items": [], "total": []}])

        page = repo.list_conversations(user_id, page=1, page_size=20)

        assert page.items == []
        assert page.total == 0

    def test_wraps_a_driver_failure(self, repo, user_id):
        repo.messageCollection.aggregate.side_effect = PyMongoError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to list conversations"):
            repo.list_conversations(user_id)


class TestPreferences:
    def test_get_preferences_returns_none_when_never_recorded(self, repo, user_id):
        repo.preferencesCollection.find_one.return_value = None

        assert repo.get_preferences(user_id) is None

    def test_get_preferences_returns_validated_preferences(self, repo, preferences, user_id):
        repo.preferencesCollection.find_one.return_value = preferences.model_dump(mode="python") | {
            "user_id": str(user_id)
        }

        assert repo.get_preferences(user_id) == preferences

    def test_get_preferences_wraps_a_driver_failure(self, repo, user_id):
        repo.preferencesCollection.find_one.side_effect = PyMongoError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to retrieve preferences"):
            repo.get_preferences(user_id)

    def test_upsert_preferences_updates_by_stringified_user_id(self, repo, preferences):
        repo.upsert_preferences(preferences)

        repo.preferencesCollection.update_one.assert_called_once()
        filter_arg, update_arg = repo.preferencesCollection.update_one.call_args.args[:2]
        assert filter_arg == {"user_id": str(preferences.user_id)}
        assert update_arg["$set"]["user_id"] == str(preferences.user_id)
        assert repo.preferencesCollection.update_one.call_args.kwargs["upsert"] is True

    def test_upsert_preferences_wraps_a_driver_failure(self, repo, preferences):
        repo.preferencesCollection.update_one.side_effect = PyMongoError("connection refused")

        with pytest.raises(RepositoryException, match="Failed to save preferences"):
            repo.upsert_preferences(preferences)


class TestDisposalReport:
    def test_inserts_the_report_with_a_stringified_user_id(self, repo, user_id):
        report = DisposalReport(
            disposal_id="42",
            user_id=user_id,
            report_url="https://storage/disposal-42.pdf",
            created_at=datetime.now(timezone.utc),
        )

        repo.save_disposal_report(report)

        document = repo.disposalReportCollection.insert_one.call_args.args[0]
        assert document["disposal_id"] == "42"
        assert document["user_id"] == str(user_id)
        assert document["report_url"] == "https://storage/disposal-42.pdf"

    def test_returns_the_stored_report(self, repo, user_id):
        created_at = datetime.now(timezone.utc)
        repo.disposalReportCollection.find_one.return_value = {
            "disposal_id": "42",
            "user_id": str(user_id),
            "report_url": "https://storage/disposal-42.pdf",
            "created_at": created_at,
        }

        report = repo.get_disposal_report("42")

        assert report is not None
        assert report.disposal_id == "42"
        assert report.report_url == "https://storage/disposal-42.pdf"
        repo.disposalReportCollection.find_one.assert_called_once_with({"disposal_id": "42"})

    def test_returns_none_when_the_disposal_has_no_report(self, repo):
        repo.disposalReportCollection.find_one.return_value = None

        assert repo.get_disposal_report("42") is None
