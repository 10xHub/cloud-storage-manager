from datetime import datetime, timedelta, timezone
from pathlib import Path

from azure.core.exceptions import ResourceNotFoundError
from azure.storage.blob import BlobSasPermissions, ContentSettings, generate_blob_sas
from azure.storage.blob.aio import BlobServiceClient

from . import logger
from .base_storage import BaseCloudStorage, guess_content_type
from .exceptions import DeleteError, DownloadError, ListError, NotFoundError, UploadError
from .storage_schema import StorageConfig


def _connection_string_key(connection_string: str) -> str | None:
    """The AccountKey inside a connection string; None for a SAS-only one."""
    parts = dict(part.split("=", 1) for part in connection_string.split(";") if "=" in part)
    return {k.lower(): v for k, v in parts.items()}.get("accountkey")


def _content_settings(content_type: str | None) -> dict:
    # Untyped blobs are served as octet-stream, which browsers download instead of playing.
    return {"content_settings": ContentSettings(content_type=content_type)} if content_type else {}


class AzureBlobStorage(BaseCloudStorage):
    """Azure Blob Storage client implementation.

    Implements every BaseCloudStorage operation against one blob container, using the
    async SDK. Signed URLs are read-only blob SAS tokens signed with the account key.

    Attributes:
        account_name (str): Storage account name.
        container_name (str): Blob container name.
    """

    def __init__(self, config: StorageConfig):
        """Initialize Azure Blob storage client.

        Args:
            config: Configuration object containing azure.account_name,
                azure.container_name and one of azure.account_key / azure.connection_string.

        Raises:
            ValueError: If Azure configuration is missing from config.
        """
        if not config.azure:
            raise ValueError("Azure configuration is required")
        super().__init__(config)
        self.account_name = config.azure.account_name
        self.container_name = config.azure.container_name
        self._connection_string = config.azure.connection_string
        self._account_key = config.azure.account_key or _connection_string_key(
            config.azure.connection_string or ""
        )
        logger.info(f"AzureBlobStorage initialized with container: {self.container_name}")

    def _service_client(self) -> BlobServiceClient:
        if self._connection_string:
            return BlobServiceClient.from_connection_string(self._connection_string)
        return BlobServiceClient(
            account_url=f"https://{self.account_name}.blob.core.windows.net",
            credential=self._account_key,
        )

    async def upload(self, file_path: Path | str, cloud_path: str) -> str:
        """Upload a local file to the container; returns the blob path."""
        logger.info(f"Starting upload of {file_path} to azure://{self.container_name}/{cloud_path}")
        settings = _content_settings(guess_content_type(file_path))
        try:
            async with self._service_client() as client:
                blob = client.get_blob_client(self.container_name, cloud_path)
                with Path(file_path).open("rb") as file_obj:
                    await blob.upload_blob(file_obj, overwrite=True, **settings)
            return cloud_path
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise UploadError(f"Failed to upload file to Azure: {e}") from e

    async def upload_bytes(
        self, data: bytes, cloud_path: str, content_type: str | None = None
    ) -> str:
        """Upload in-memory bytes to the container; returns the blob path."""
        logger.info(f"Uploading {len(data)} bytes to azure://{self.container_name}/{cloud_path}")
        settings = _content_settings(content_type or guess_content_type(cloud_path))
        try:
            async with self._service_client() as client:
                blob = client.get_blob_client(self.container_name, cloud_path)
                await blob.upload_blob(data, overwrite=True, **settings)
            return cloud_path
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise UploadError(f"Failed to upload bytes to Azure: {e}") from e

    async def download_bytes(self, cloud_path: str) -> bytes:
        """Download the blob's content."""
        logger.info(f"Downloading azure://{self.container_name}/{cloud_path}")
        try:
            async with self._service_client() as client:
                blob = client.get_blob_client(self.container_name, cloud_path)
                downloader = await blob.download_blob()
                return await downloader.readall()
        except ResourceNotFoundError as e:
            raise NotFoundError(f"Azure blob not found: {cloud_path}") from e
        except Exception as e:
            logger.error(f"Download failed: {e}")
            raise DownloadError(f"Failed to download blob from Azure: {e}") from e

    async def list_objects(self, prefix: str) -> list[str]:
        """List blob names under `prefix`."""
        return list(await self.list_object_sizes(prefix))

    async def list_object_sizes(self, prefix: str) -> dict[str, int]:
        """Blob name -> size in bytes under `prefix`."""
        logger.info(f"Listing azure://{self.container_name}/{prefix}")
        try:
            async with self._service_client() as client:
                container = client.get_container_client(self.container_name)
                return {
                    b.name: b.size or 0
                    async for b in container.list_blobs(name_starts_with=prefix or None)
                }
        except Exception as e:
            logger.error(f"Listing failed: {e}")
            raise ListError(f"Failed to list blobs in Azure: {e}") from e

    async def delete(self, cloud_path: str) -> bool:
        """Delete a blob; a missing blob raises DeleteError, as GCP's delete does."""
        if not await self.delete_if_exists(cloud_path):
            raise DeleteError(f"Failed to delete blob from Azure: {cloud_path} does not exist")
        return True

    async def delete_if_exists(self, cloud_path: str) -> bool:
        """Delete a blob; False when it did not exist."""
        logger.info(f"Deleting azure://{self.container_name}/{cloud_path} if it exists")
        try:
            async with self._service_client() as client:
                await client.get_blob_client(self.container_name, cloud_path).delete_blob()
            return True
        except ResourceNotFoundError:
            return False
        except Exception as e:
            logger.error(f"Deletion failed: {e}")
            raise DeleteError(f"Failed to delete blob from Azure: {e}") from e

    async def get_public_url(self, cloud_path: str, expiration: int = 3600) -> str:
        """Generate a read-only SAS URL for the blob, valid for `expiration` seconds.

        The SAS does not override the response Content-Type, so the browser receives the
        type stored at upload.
        """
        logger.info(f"Generating SAS URL for azure://{self.container_name}/{cloud_path}")
        if not self._account_key:
            raise DownloadError("Azure SAS signing needs an account key in the configuration")
        try:
            sas = generate_blob_sas(
                account_name=self.account_name,
                container_name=self.container_name,
                blob_name=cloud_path,
                account_key=self._account_key,
                permission=BlobSasPermissions(read=True),
                expiry=datetime.now(timezone.utc) + timedelta(seconds=expiration),
            )
            async with self._service_client() as client:
                blob_url = client.get_blob_client(self.container_name, cloud_path).url
            logger.debug(f"Generated SAS URL (expires in {expiration}s)")
            return f"{blob_url}?{sas}"
        except Exception as e:
            logger.error(f"Failed to generate SAS URL: {e}")
            raise DownloadError(f"Failed to generate SAS URL: {e}") from e
