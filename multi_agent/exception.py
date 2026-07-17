class MultiAgentServiceException(Exception):
    """Base class for exceptions in the multi-agent service."""
    pass

class MultiAgentServiceNotSetupException(MultiAgentServiceException):
    """Exception raised when the multi-agent service is not set up properly."""
    pass