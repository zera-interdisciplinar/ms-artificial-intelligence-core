import pytest

from multi_agent.exception import MultiAgentServiceException
from repository.exception import RepositoryException


def test_service_exception_keeps_its_message():
    with pytest.raises(MultiAgentServiceException, match="boom"):
        raise MultiAgentServiceException("boom")


def test_service_exception_is_catchable_as_an_exception():
    assert issubclass(MultiAgentServiceException, Exception)


def test_service_and_repository_exceptions_are_unrelated():
    """The service layer must not accidentally swallow repository failures."""
    assert not issubclass(MultiAgentServiceException, RepositoryException)
    assert not issubclass(RepositoryException, MultiAgentServiceException)
