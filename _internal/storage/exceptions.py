class StorageServiceException(Exception):
    """Base class for exceptions raised by the storage integration."""
    pass

class PDFRenderException(StorageServiceException):
    """Exception raised when the HTML content fails to be rendered into a PDF."""
    pass

class StorageUploadException(StorageServiceException):
    """Exception raised when a file fails to be uploaded to the storage provider."""
    pass

class StorageConfigurationException(StorageServiceException):
    """Exception raised when required storage configuration (env vars) is missing."""
    pass
