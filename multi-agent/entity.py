"""
Defines the classes for the multi-agent service and repository. The multi-agent service is responsible for processing messages and the multi-agent repository is responsible for storing and retrieving messages.
"""


from typing import Annotated, Protocol, Any
from langgraph.graph import MessagesState
from multi-
import operator

class Thread:
    """
    Represents a thread in the multi-agent system. A thread is a collection of messages exchanged between the user and the multi-agent system.
    """

    def __init__(self, user_id: str, thread_id: str):
        self.user_id = user_id
        self.thread_id = thread_id
        self.messages = []

    def add_message(self, message: str):
        """
        Adds a message to the thread.
        """
        self.messages.append(message)

    def get_messages(self) -> list[str]:
        """
        Returns the list of messages in the thread.
        """
        return self.messages
    
class State(MessagesState):
    """
    Represents the state of the multi-agent system. The state is a collection of threads, where each thread is identified by a user_id and a thread_id.
    """

    called_agents: Annotated[list[AgentName], operator.add]
    