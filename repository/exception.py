class RepositoryException(Exception):
     """Base class for exceptions in the repository."""
     pass

class RepositorySaveException(RepositoryException):
    """Exception raised for errors in the repository save operation."""
    pass

class RepositoryReadException(RepositoryException):
    """Exception raised for errors in the repository read operation."""
    pass

class RepositoryDeleteException(RepositoryException):
    """Exception raised for errors in the repository delete operation."""
    pass