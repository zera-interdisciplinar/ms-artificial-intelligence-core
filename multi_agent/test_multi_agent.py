"""Contract tests: the concrete classes must satisfy the Protocols they are wired against."""

from multi_agent.multi_agent import IMultiAgentRepository, IMultiAgentService
from repository.multi_agent import MultiAgentRepository


class TestIMultiAgentRepository:
    def test_the_concrete_repository_satisfies_the_protocol(self):
        assert isinstance(MultiAgentRepository(), IMultiAgentRepository)

    def test_declares_the_methods_the_service_depends_on(self):
        for method in ("setup", "save_message", "retrieve_messages", "remove_thread"):
            assert callable(getattr(IMultiAgentRepository, method))

    def test_an_object_missing_a_method_does_not_satisfy_the_protocol(self):
        class Partial:
            def setup(self) -> None: ...
            def save_message(self, message) -> None: ...

        assert not isinstance(Partial(), IMultiAgentRepository)


class TestIMultiAgentService:
    def test_declares_setup_and_process_message(self):
        for method in ("setup", "process_message"):
            assert callable(getattr(IMultiAgentService, method))

    def test_an_object_missing_a_method_does_not_satisfy_the_protocol(self):
        class Partial:
            def setup(self, repository) -> None: ...

        assert not isinstance(Partial(), IMultiAgentService)
