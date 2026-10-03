from multi_agent.entity import ConversationPage, ConversationPreview, DisposalReport, Message, UserPreferences
from _internal.mongo.setup import Repository
from pymongo.collection import Collection
from repository.exception import RepositoryReadException, RepositorySaveException
from uuid import UUID

_PREVIEW_LENGTH = 40


class MultiAgentRepository():
    """
    Repository class for managing multi-agent messages and user preferences in the database.
    """

    repository: Repository
    messageCollection: Collection
    preferencesCollection: Collection
    disposalReportCollection: Collection

    def setup(self, repository: Repository) -> None:
        """
        Setup the AgentRepository, connecting to the database, setting up the collections and indexes.
        Raise RepositoryException if the setup fails.
        """
        self.repository = repository
        self.messageCollection = self.repository.db["messages"]
        self.preferencesCollection = self.repository.db["user_preferences"]
        self.disposalReportCollection = self.repository.db["disposal_reports"]

        self.messageCollection.create_index([("user_id", 1), ("thread_id", 1), ("created_at", -1)])
        self.preferencesCollection.create_index([("user_id", 1)], unique=True)
        self.disposalReportCollection.create_index([("disposal_id", 1)], unique=True)

    def save_message(
            self,
            message: Message,
    ) -> None:
        """
        Save a message in the database.
        Raise RepositorySaveException if the save fails.
        """
        try:
            doc = message.model_dump(mode="python")
            doc["user_id"] = str(doc["user_id"])
            doc["thread_id"] = str(doc["thread_id"])
            self.messageCollection.insert_one(doc)
        except Exception as e:
            raise RepositorySaveException(f"Failed to save message: {e}")

    def retrieve_messages(
            self,
            user_id: UUID,
            thread_id: UUID,
            limit: int | None = 50,
    ) -> list[Message]:
        """
        Retrieve messages for a given user and thread, oldest first.
        limit caps how many of the most recent messages come back; None returns all of them.
        Raise RepositoryReadException if the retrieval fails.
        """
        try:
            cursor = (
                self.messageCollection
                .find({"user_id": str(user_id), "thread_id": str(thread_id)})
                .sort("created_at", -1)
            )
            if limit is not None:
                cursor = cursor.limit(limit)
            return [Message.model_validate(message) for message in reversed(list(cursor))]
        except Exception as e:
            raise RepositoryReadException(f"Failed to retrieve messages: {e}")

    def list_conversations(
            self,
            user_id: UUID,
            page: int = 1,
            page_size: int = 20,
    ) -> ConversationPage:
        """
        One page of a user's threads, newest activity first.
        preview is the first 40 characters of the thread's first message.
        Raise RepositoryReadException if the retrieval fails.
        """
        try:
            pipeline = [
                {"$match": {"user_id": str(user_id)}},
                {"$sort": {"created_at": 1}},
                {"$group": {
                    "_id": "$thread_id",
                    "preview": {"$first": "$content"},
                    "last_message_at": {"$max": "$created_at"},
                }},
                {"$sort": {"last_message_at": -1}},
                {"$facet": {
                    "items": [{"$skip": (page - 1) * page_size}, {"$limit": page_size}],
                    "total": [{"$count": "count"}],
                }},
            ]
            result = next(self.messageCollection.aggregate(pipeline), {"items": [], "total": []})
            total = result["total"][0]["count"] if result["total"] else 0
            return ConversationPage(
                items=[
                    ConversationPreview(
                        thread_id=doc["_id"],
                        last_message_at=doc["last_message_at"],
                        preview=(doc.get("preview") or "")[:_PREVIEW_LENGTH],
                    )
                    for doc in result["items"]
                ],
                page=page,
                page_size=page_size,
                total=total,
            )
        except Exception as e:
            raise RepositoryReadException(f"Failed to list conversations: {e}")

    def get_preferences(self, user_id: UUID) -> UserPreferences | None:
        """
        Retrieve the long-term preferences for a given user, or None if never recorded.
        Raise RepositoryReadException if the retrieval fails.
        """
        try:
            doc = self.preferencesCollection.find_one({"user_id": str(user_id)})
            return UserPreferences.model_validate(doc) if doc else None
        except Exception as e:
            raise RepositoryReadException(f"Failed to retrieve preferences: {e}")

    def upsert_preferences(self, preferences: UserPreferences) -> None:
        """
        Insert or update the long-term preferences for a given user.
        Raise RepositorySaveException if the save fails.
        """
        try:
            doc = preferences.model_dump(mode="python")
            doc["user_id"] = str(doc["user_id"])
            self.preferencesCollection.update_one(
                {"user_id": doc["user_id"]}, {"$set": doc}, upsert=True
            )
        except Exception as e:
            raise RepositorySaveException(f"Failed to save preferences: {e}")

    def save_disposal_report(self, report: DisposalReport) -> None:
        """
        Save the stored PDF of one disposal.
        Raise RepositorySaveException if the save fails.
        """
        try:
            doc = report.model_dump(mode="python")
            doc["user_id"] = str(doc["user_id"])
            self.disposalReportCollection.insert_one(doc)
        except Exception as e:
            raise RepositorySaveException(f"Failed to save disposal report: {e}")

    def get_disposal_report(self, disposal_id: str) -> DisposalReport | None:
        """
        The stored report for this disposal, or None if it was never generated.
        Raise RepositoryReadException if the retrieval fails.
        """
        try:
            doc = self.disposalReportCollection.find_one({"disposal_id": disposal_id})
            return DisposalReport.model_validate(doc) if doc else None
        except Exception as e:
            raise RepositoryReadException(f"Failed to retrieve disposal report: {e}")
