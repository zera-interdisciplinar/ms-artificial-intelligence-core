from multi_agent.entity import Message, Thread
from _internal.mongo.setup import Repository
from pymongo.collection import Collection
from repository.exception import RepositoryException
from uuid import UUID

class MultiAgentRepository():
    """
    Repository class for managing multi-agent threads and messages in the database.
    """

    repository: Repository
    threadCollection: Collection
    messageCollection: Collection

    def setup(self, repository: Repository) -> None:
        """
        Setup the AgentRepository, connecting to the database, setting up the collections, etc.
        Raise RepositoryException if the setup fails.
        """
        self.repository = repository
        self.threadCollection = self.repository.db["threads"]
        self.messageCollection = self.repository.db["messages"]
    
    def save_message(
            self,
            message: Message,
    ) -> None:
        """
        Save a message in the database.
        Raise RepositoryException if the save fails.
        """
        try:
            self.messageCollection.insert_one(message.model_dump(mode="json"))
        except Exception as e:
            raise RepositoryException(f"Failed to save message: {e}")
        
    def retrieve_messages(
            self,
            user_id: UUID,
            thread_id: UUID,
    ) -> list[Message]:
        """
        Retrieve messages from the database for a given user and thread.
        Raise RepositoryException if the retrieval fails.
        """
        try:
            messages = self.messageCollection.find({"user_id": str(user_id), "thread_id": str(thread_id)})
            return [Message.model_validate(message) for message in messages]
        except Exception as e:
            raise RepositoryException(f"Failed to retrieve messages: {e}")
        
    def remove_thread(self, user_id: UUID, thread_id: UUID) -> None:
        """
        Remove a thread from the database.
        Raise RepositoryException if the removal fails.
        """
        try:
            self.threadCollection.delete_one({"user_id": str(user_id), "thread_id": str(thread_id)})
        except Exception as e:
            raise RepositoryException(f"Failed to remove thread: {e}")