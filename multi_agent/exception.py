class MultiAgentServiceException(Exception):
    """Base class for exceptions in the multi-agent service."""
    pass

class MultiAgentServiceNotSetupException(MultiAgentServiceException):
    """Exception raised when the multi-agent service is not set up properly."""
    pass

class UnitMismatchException(MultiAgentServiceException):
    """Raised when the unit_id in the request is not the one ms-administrative-core
    has for that user. Answered as 403: the client proposes, the admin-core decides."""
    pass
