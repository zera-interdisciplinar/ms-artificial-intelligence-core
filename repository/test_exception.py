import pytest

from repository.exception import (
    RepositoryDeleteException,
    RepositoryException,
    RepositoryReadException,
    RepositorySaveException,
)

SPECIALIZED = [
    RepositorySaveException,
    RepositoryReadException,
    RepositoryDeleteException,
]


@pytest.mark.parametrize("exception", SPECIALIZED)
def test_specialized_exceptions_derive_from_the_base(exception):
    """A caller catching RepositoryException must catch every repository failure."""
    with pytest.raises(RepositoryException):
        raise exception("boom")


@pytest.mark.parametrize("exception", [RepositoryException, *SPECIALIZED])
def test_exceptions_keep_their_message(exception):
    with pytest.raises(exception, match="boom"):
        raise exception("boom")


@pytest.mark.parametrize("exception", SPECIALIZED)
def test_specialized_exceptions_are_not_interchangeable(exception):
    siblings = [other for other in SPECIALIZED if other is not exception]

    for sibling in siblings:
        assert not issubclass(exception, sibling)
