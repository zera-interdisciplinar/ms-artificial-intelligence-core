from multi_agent.entity import Message, UserPreferences
from _internal.mongo.setup import Repository
from pymongo.collection import Collection
from repository.exception import RepositoryReadException, RepositorySaveException
from uuid import UUID

class MultiAgentRepository():
    """
    Repository class for managing multi-agent messages and user preferences in the database.
    """

    repository: Repository
    messageCollection: Collection
    preferencesCollection: Collection

    def setup(self, repository: Repository) -> None:
        """
        Setup the AgentRepository, connecting to the database, setting up the collections and indexes.
        Raise RepositoryException if the setup fails.
        """
        self.repository = repository
        self.messageCollection = self.repository.db["messages"]
        self.preferencesCollection = self.repository.db["user_preferences"]

        self.messageCollection.create_index([("user_id", 1), ("thread_id", 1), ("created_at", -1)])
        self.preferencesCollection.create_index([("user_id", 1)], unique=True)

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
            limit: int = 50,
    ) -> list[Message]:
        """
        Retrieve the most recent messages for a given user and thread, oldest first.
        Raise RepositoryReadException if the retrieval fails.
        """
        try:
            messages = (
                self.messageCollection
                .find({"user_id": str(user_id), "thread_id": str(thread_id)})
                .sort("created_at", -1)
                .limit(limit)
            )
            return [Message.model_validate(message) for message in reversed(list(messages))]
        except Exception as e:
            raise RepositoryReadException(f"Failed to retrieve messages: {e}")

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
