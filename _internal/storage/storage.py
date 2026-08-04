from typing import Protocol


class IStorageService(Protocol):
    """Storage service interface. Responsible for persisting file bytes to a storage provider and returning a public/shareable URL."""

    def upload(self, content: bytes, filename: str, content_type: str) -> str:
        """
        Upload file content to the storage provider.

        Args:
            content (bytes): The raw file content to upload.
            filename (str): The name to store the file under.
            content_type (str): The MIME type of the file.

        Returns:
            str: The URL where the uploaded file can be accessed.
        """
        ...
