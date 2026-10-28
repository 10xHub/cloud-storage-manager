import mimetypes
from abc import ABC, abstractmethod
from pathlib import Path

from .storage_schema import StorageConfig


def guess_content_type(path: Path | str) -> str | None:
    """Content type from a file name's extension, or None when it is unknown."""
    return mimetypes.guess_type(str(path))[0]


class BaseCloudStorage(ABC):
    """Abstract base class for cloud storage operations.

    Only the three 0.1.x operations (upload, delete, get_public_url) are abstract, so a
    subclass written against 0.1.x still instantiates. The operations added in 0.2.0 raise
    NotImplementedError until a subclass provides them; every built-in provider does.

    Attributes:
        config (StorageConfig): Configuration object for the cloud storage.
    """

    def __init__(self, config: StorageConfig):
        """Initialize the cloud storage interface.

        Args:
            config (StorageConfig): Configuration object for the cloud storage.
        """
        self.config = config

    def _unsupported(self, operation: str) -> NotImplementedError:
        return NotImplementedError(f"{type(self).__name__} does not implement {operation}")

    @abstractmethod
    async def upload(self, file_path: Path | str, cloud_path: str) -> str:
        """Upload a local file to cloud storage.

        Args:
            file_path (Path | str): Local path to the file to be uploaded.
            cloud_path (str): Destination path in cloud storage.

        Returns:
            str: The path of the uploaded file in cloud storage.

        Raises:
            UploadError: If the upload fails.
        """

    async def upload_bytes(
        self, data: bytes, cloud_path: str, content_type: str | None = None
    ) -> str:
        """Upload in-memory bytes to cloud storage.

        Args:
            data (bytes): The object's content.
            cloud_path (str): Destination path in cloud storage.
            content_type (str | None): Stored content type; guessed from cloud_path when None.

        Returns:
            str: The path of the uploaded object in cloud storage.

        Raises:
            UploadError: If the upload fails.
        """
        raise self._unsupported("upload_bytes")

    async def download_bytes(self, cloud_path: str) -> bytes:
        """Download an object's content.

        Args:
            cloud_path (str): Path to the object in cloud storage.

        Returns:
            bytes: The object's content.

        Raises:
            NotFoundError: If the object does not exist.
            DownloadError: If the download fails for any other reason.
        """
        raise self._unsupported("download_bytes")

    async def list_objects(self, prefix: str) -> list[str]:
        """List the names of every object under a prefix.

        Args:
            prefix (str): Path prefix; an empty string lists the whole bucket.

        Returns:
            list[str]: Object names, across every page of the listing.

        Raises:
            ListError: If the listing fails.
        """
        raise self._unsupported("list_objects")

    async def list_object_sizes(self, prefix: str) -> dict[str, int]:
        """Map every object under a prefix to its size in bytes.

        Args:
            prefix (str): Path prefix; an empty string lists the whole bucket.

        Returns:
            dict[str, int]: Object name to size in bytes.

        Raises:
            ListError: If the listing fails.
        """
        raise self._unsupported("list_object_sizes")

    @abstractmethod
    async def delete(self, cloud_path: str) -> bool:
        """Delete a file from cloud storage, as 0.1.x did.

        A missing object gets each cloud's own answer, unchanged since 0.1.x: GCP and Azure
        raise DeleteError, S3 deletes nothing and returns True. delete_if_exists gives the
        same answer on every cloud.

        Args:
            cloud_path (str): Path to the file in cloud storage to be deleted.

        Returns:
            bool: True once the delete request succeeded.

        Raises:
            DeleteError: If the deletion fails.
        """

    async def delete_if_exists(self, cloud_path: str) -> bool:
        """Delete an object, reporting whether it was there, the same way on every cloud.

        Args:
            cloud_path (str): Path to the object in cloud storage.

        Returns:
            bool: True if the object was deleted, False if it did not exist.

        Raises:
            DeleteError: If the deletion fails for any other reason.
        """
        raise self._unsupported("delete_if_exists")

    @abstractmethod
    async def get_public_url(self, cloud_path: str, expiration: int = 3600) -> str:
        """Generate a time-limited, read-only signed URL for the file.

        Args:
            cloud_path (str): Path to the file in cloud storage.
            expiration (int, optional): URL expiration time in seconds. Defaults to 3600.

        Returns:
            str: Signed URL for reading the file.

        Raises:
            DownloadError: If URL generation fails.
        """
