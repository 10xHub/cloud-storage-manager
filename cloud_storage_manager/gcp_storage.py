import asyncio
from pathlib import Path

from google.cloud import storage
from google.cloud.exceptions import NotFound
from google.oauth2 import service_account

from . import logger
from .base_storage import BaseCloudStorage, guess_content_type
from .exceptions import DeleteError, DownloadError, ListError, NotFoundError, UploadError
from .storage_schema import StorageConfig


class GcpClientStorage(BaseCloudStorage):
    """Google Cloud Storage client implementation.

    This class implements the BaseCloudStorage interface for Google Cloud Storage.
    It provides methods for uploading, deleting files and generating signed URLs
    for temporary access to private objects.

    Attributes:
        credentials: The GCP service account credentials.
        bucket_name (str): Name of the GCP storage bucket.
        client: The GCP storage client instance.
        bucket: The GCP bucket instance.

    Example:
        config = StorageConfig(gcp={
            'credentials': {...},
            'bucket_name': 'my-bucket'
        })
        storage = GcpClientStorage(config)
        await storage.upload('path.txt', 'remote/path.txt')
    """

    def __init__(self, config: StorageConfig):
        """Initialize GCP storage client.

        Args:
            config: Configuration object containing GCP settings.
                Must include gcp.credentials (dict) and gcp.bucket_name (str).

        Raises:
            ValueError: If GCP configuration is missing from config.
        """
        if not config.gcp:
            raise ValueError("GCP configuration is required")
        super().__init__(config)
        self.credentials = service_account.Credentials.from_service_account_info(
            config.gcp.credentials
        )
        self.bucket_name = config.gcp.bucket_name
        self.client = storage.Client(credentials=self.credentials)
        self.bucket = self.client.get_bucket(self.bucket_name)
        logger.info(f"GcpClientStorage initialized with bucket: {self.bucket_name}")

    async def upload(self, file_path: Path | str, cloud_path: str | None = None) -> str:
        """Upload a file to Google Cloud Storage bucket.

        Args:
            file_path: Local filesystem path of the file to upload.
                Can be string or Path object.
            cloud_path: Target path in GCP bucket. If None, uses the original filename.

        Returns:
            The GCP object path where the file was uploaded.

        Raises:
            UploadError: If the upload operation fails for any reason.
        """
        if cloud_path is None:
            cloud_path = Path(file_path).name

        logger.info(f"Starting upload of {file_path} to gs://{self.bucket_name}/{cloud_path}")
        try:
            return await asyncio.to_thread(self._upload_file, file_path, cloud_path)
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise UploadError(f"Failed to upload file to GCP: {e}") from e

    async def upload_bytes(
        self, data: bytes, cloud_path: str, content_type: str | None = None
    ) -> str:
        """Upload in-memory bytes to the GCP bucket; returns the object path."""
        logger.info(f"Uploading {len(data)} bytes to gs://{self.bucket_name}/{cloud_path}")
        content_type = content_type or guess_content_type(cloud_path)
        try:
            await asyncio.to_thread(
                self.bucket.blob(cloud_path).upload_from_string, data, content_type=content_type
            )
            return cloud_path
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise UploadError(f"Failed to upload bytes to GCP: {e}") from e

    async def download_bytes(self, cloud_path: str) -> bytes:
        """Download the GCP object's content."""
        logger.info(f"Downloading gs://{self.bucket_name}/{cloud_path}")
        try:
            return await asyncio.to_thread(self.bucket.blob(cloud_path).download_as_bytes)
        except NotFound as e:
            raise NotFoundError(f"GCP object not found: {cloud_path}") from e
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise DownloadError(f"Failed to download file from GCP: {e}") from e

    async def list_objects(self, prefix: str) -> list[str]:
        """List GCP object names under `prefix`."""
        return list(await self.list_object_sizes(prefix))

    async def list_object_sizes(self, prefix: str) -> dict[str, int]:
        """GCP object name -> size in bytes under `prefix`."""
        logger.info(f"Listing gs://{self.bucket_name}/{prefix}")
        try:
            return await asyncio.to_thread(self._list_sizes, prefix)
        except Exception as e:
            logger.error(f"Listing failed: {e}")
            raise ListError(f"Failed to list objects in GCP: {e}") from e

    async def delete(self, cloud_path: str) -> bool:
        """Delete a file from Google Cloud Storage bucket.

        Args:
            cloud_path: The object path in GCP bucket to delete.

        Returns:
            True if deletion was successful.

        Raises:
            DeleteError: If the deletion operation fails, including a missing object.
        """
        logger.info(f"Deleting gs://{self.bucket_name}/{cloud_path}")
        try:
            return await asyncio.to_thread(self._delete_file, cloud_path)
        except Exception as e:
            logger.error(f"Deletion failed: {e}")
            raise DeleteError(f"Failed to delete file from GCP: {e}") from e

    async def delete_if_exists(self, cloud_path: str) -> bool:
        """Delete a GCP object; False when it did not exist."""
        logger.info(f"Deleting gs://{self.bucket_name}/{cloud_path} if it exists")
        try:
            return await asyncio.to_thread(self._delete_file, cloud_path)
        except NotFound:
            return False
        except Exception as e:
            logger.error(f"Deletion failed: {e}")
            raise DeleteError(f"Failed to delete file from GCP: {e}") from e

    async def get_public_url(self, cloud_path: str, expiration: int = 3600) -> str:
        """Generate a temporary signed URL for accessing a private GCP object.

        Args:
            cloud_path: The object path in GCP bucket.
            expiration: URL validity duration in seconds. Defaults to 1 hour (3600 seconds).

        Returns:
            A signed URL that provides temporary access to the private object.

        Raises:
            DownloadError: If URL generation fails.
        """
        logger.info(f"Generating signed URL for gs://{self.bucket_name}/{cloud_path}")
        try:
            return await asyncio.to_thread(self._generate_signed_url, cloud_path, expiration)
        except Exception as e:
            logger.error(f"Failed to generate signed URL: {e}")
            raise DownloadError(f"Failed to generate signed URL: {e}") from e

    def _upload_file(self, file_path: str | Path, cloud_path: str) -> str:
        """Perform synchronous file upload to GCP bucket.

        Internal method used by the async upload method.

        Args:
            file_path: Local file path to upload.
            cloud_path: Target path in GCP bucket.

        Returns:
            The GCP object path where file was uploaded.
        """
        blob = self.bucket.blob(cloud_path)
        blob.upload_from_filename(str(file_path))
        logger.debug(f"Successfully uploaded to gs://{self.bucket_name}/{cloud_path}")
        return cloud_path

    def _delete_file(self, cloud_path: str) -> bool:
        """Perform synchronous file deletion from GCP bucket.

        Internal method used by the async delete method.

        Args:
            cloud_path: Object path in GCP bucket to delete.

        Returns:
            True if deletion was successful.
        """
        blob = self.bucket.blob(cloud_path)
        blob.delete()
        logger.debug(f"Successfully deleted gs://{self.bucket_name}/{cloud_path}")
        return True

    def _list_sizes(self, prefix: str) -> dict[str, int]:
        """Name -> size for every object under `prefix`.

        `list_blobs` pages lazily over HTTP as it is iterated, so it is drained here on the
        worker thread rather than back on the event loop.
        """
        return {b.name: b.size or 0 for b in self.bucket.list_blobs(prefix=prefix)}

    def _generate_signed_url(self, cloud_path: str, expiration: int) -> str:
        """Generate a signed URL for temporary object access.

        Internal method used by the async get_public_url method.

        Args:
            cloud_path: Object path in GCP bucket.
            expiration: URL validity duration in seconds.

        Returns:
            A signed URL for temporary object access.
        """
        blob = self.bucket.blob(cloud_path)
        url = blob.generate_signed_url(expiration=expiration, method="GET", version="v4")
        logger.debug(f"Generated signed URL (expires in {expiration}s)")
        return url
